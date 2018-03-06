import pybullet as p
import time
import pybullet_data
import argparse
import numpy as np
from motion_planners.rrt_connect import birrt, direct_path


REST_LEFT_ARM = [2.13539289, 1.29629967, 3.74999698, -0.15000005, 10000., -0.10000004, 10000.]

LEFT_ARM_LINK = 'l_gripper_palm_link'

LEFT_JOINT_NAMES = ['l_shoulder_pan_joint', 'l_shoulder_lift_joint', 'l_upper_arm_roll_joint',
                    'l_elbow_flex_joint', 'l_forearm_roll_joint', 'l_wrist_flex_joint', 'l_wrist_roll_joint']
RIGHT_JOINT_NAMES = ['r_shoulder_pan_joint', 'r_shoulder_lift_joint', 'r_upper_arm_roll_joint',
                     'r_elbow_flex_joint', 'r_forearm_roll_joint', 'r_wrist_flex_joint', 'r_wrist_roll_joint']
HEAD_JOINT_NAMES = ['head_pan_joint', 'head_tilt_joint']

LEFT_GRIPPER_NAME = 'l_gripper_l_finger_joint'

def rightarm_from_leftarm(config):
  right_from_left = np.array([-1, 1, -1, 1, -1, 1, 1])
  return config*right_from_left

REST_RIGHT_ARM = rightarm_from_leftarm(REST_LEFT_ARM)

#LEFT_ARM_JOINTS = [15,16,17,18,19,20,21]
#RIGHT_ARM_JOINTS = [27,28,29,30,31,32,33]
#HEAD_JOINTS = [13,14]
# openrave-robot.py robots/pr2-beta-static.zae --info manipulators

TORSO_JOINT = 'torso_lift_joint'

REVOLUTE_LIMITS = -np.pi, np.pi
#REVOLUTE_LIMITS = -10000, 10000

BASE_LIMITS = ([-2.5, -2.5, 0], [2.5, 2.5, 0])

class Pose(object):
    def __init__(self, position, orientation):
        self.position = position
        self.orientation = orientation

class Conf(object):
    def __init__(self):
        pass

# https://docs.google.com/document/d/10sXEhzFRSnvFcl3XxNGhnD4N2SedqwdAvK3dsihxVUA/edit#

def get_joint_type(body, joint):
    return p.getJointInfo(body, joint)[2]

def is_movable(body, joint):
    return get_joint_type(body, joint) != p.JOINT_FIXED

def is_circular(body, joint):
    lower = p.getJointInfo(body, joint)[8]
    upper = p.getJointInfo(body, joint)[9]
    return upper < lower

def get_joint_limits(body, joint):
    if is_circular(body, joint):
        return REVOLUTE_LIMITS
    return p.getJointInfo(body, joint)[8:10]

def create_box(w, l, h, color=(1, 0, 0, 1)):
    half_extents = [w/2., l/2., h/2.]
    collision_id = p.createCollisionShape(p.GEOM_BOX, halfExtents=half_extents)
    if (color is None) or not has_gui():
        visual_id = -1
    else:
        visual_id = p.createVisualShape(p.GEOM_BOX, halfExtents=half_extents, rgbaColor=color)
    return p.createMultiBody(baseCollisionShapeIndex=collision_id,
                             baseVisualShapeIndex=visual_id) # basePosition | baseOrientation
    # linkCollisionShapeIndices | linkVisualShapeIndices

def create_plane():
    collision_id = p.createVisualShape(p.GEOM_PLANE, normal=[])

def create_mesh():
    raise NotImplementedError()

def create_cylinder(radius, height):
    collision_id =  p.createCollisionShape(p.GEOM_CYLINDER, radius=radius, height=height)

def create_capsule(radius, height):
    collision_id = p.createCollisionShape(p.GEOM_CAPSULE, radius=radius, height=height)

def create_sphere(radius):
    collision_id = p.createCollisionShape(p.GEOM_SPHERE, radius=radius)

def get_lower_upper(body):
    return p.getAABB(body)

def get_center_extent(body):
    lower, upper = get_lower_upper(body)
    center = (np.array(lower) + upper) / 2
    extents = (np.array(upper) - lower)
    return center, extents

def get_shape_data(body):
    return p.getVisualShapeData(body)

def get_max_velocity(body, joint):
    return p.getJointInfo(body, joint)[11]

def get_num_joints(body):
    return p.getNumJoints(body)

def get_joints(body):
    return range(get_num_joints(body))

def get_movable_joints(body): # 45 / 87 on pr2
    return [joint for joint in get_joints(body) if is_movable(body, joint)]

def joint_from_movable(body, index):
    return get_joints(body)[index]

def get_joint_name(body, joint):
    return p.getJointInfo(body, joint)[1]

def get_link_name(body, link):
    return p.getJointInfo(body, link)[12]

def get_name(body):
    return p.getBodyInfo(body)[1]

def get_base_link(body):
    return p.getBodyInfo(body)[0]

def get_pose(body):
    point, quat = p.getBasePositionAndOrientation(body) # [x,y,z,w]
    return np.concatenate([point, quat])

def get_point(body):
    return p.getBasePositionAndOrientation(body)[0]

def get_quat(body):
    return p.getBasePositionAndOrientation(body)[1]

def get_base_values(body):
    x, y, _ = get_point(body)
    roll, pitch, yaw = euler_from_quat(get_quat(body))
    assert (abs(roll) < 1e-3) and (abs(pitch) < 1e-3)
    return (x, y, yaw)

def set_base_values(body, values):
    _, _, z = get_point(body)
    x, y, theta = values
    set_point(body, (x, y, z))
    set_quat(body, z_rotation(theta))

def set_pose(body, point, quat):
    p.resetBasePositionAndOrientation(body, point, quat)

def set_point(body, point):
    _, quat = p.getBasePositionAndOrientation(body)
    p.resetBasePositionAndOrientation(body, point, quat)

def set_quat(body, quat):
    p.resetBasePositionAndOrientation(body, get_point(body), quat)

def get_link_pose(body, link): # Local vs world?
    #point, quat = p.getLinkState(body, link)[0:2] # Local
    point, quat = p.getLinkState(body, link)[4:6] # World
    return point, quat
    #return np.concatenate([point, quat])

def joint_from_name(body, name):
    for joint in xrange(get_num_joints(body)):
        if get_joint_name(body, joint) == name:
            return joint
    raise ValueError(body, name)

def link_from_name(body, name):
    for link in xrange(get_num_joints(body)):
        if get_link_name(body, link) == name:
            return link
    raise ValueError(body, name)

def body_from_name(name):
    for body in xrange(get_num_bodies()):
        if get_name(body) == name:
            return body
    raise ValueError(name)

#def set_joint(body, joint, value):
#    p.setJointMotorControl2(bodyUniqueId=body,
#                            jointIndex=joint,
#                            controlMode=p.POSITION_CONTROL,
#                            targetPosition=value,
#                            force=maxForce)

def set_joint_position(body, joint, value):
    p.resetJointState(body, joint, value)

def get_joint_position(body, joint):
    return p.getJointState(body, joint)[0]

def get_num_bodies():
    return p.getNumBodies()

def get_bodies():
    return range(get_num_bodies())

def get_body_names():
    return map(get_name, get_bodies())

def get_joints(body):
    return range(get_num_joints(body))

def get_joint_names(body):
    return [get_joint_name(body, joint) for joint in get_joints(body)]

def quat_from_euler(euler):
    return p.getQuaternionFromEuler(euler)

def euler_from_quat(quat):
    return p.getEulerFromQuaternion(quat)

def z_rotation(theta):
    return quat_from_euler([0, 0, theta])

def matrix_from_quat(quat):
    return p.getMatrixFromQuaternion(quat)

def quat_from_matrix(matrix):
    return p.getMatrixFromQuaternion(matrix)

def pairwise_collision(body1, body2, max_distance=0.001): # 10000
    return len(p.getClosestPoints(body1, body2, max_distance)) != 0 # getContactPoints

def env_collision(body1):
    for body2 in get_bodies():
        if (body1 != body2) and pairwise_collision(body1, body2):
        #if pairwise_collision(body1, body2):
            return True
    return False

def wrap_angle(theta):
    return (theta + np.pi) % (2 * np.pi) - np.pi

def wrap_joint(body, joint, value):
    if is_circular(body, joint):
        return wrap_angle(value)
    return value

def circular_difference(theta2, theta1):
    return wrap_angle(theta2 - theta1)

def plan_base_motion(body, end_conf, **kwargs):
    def sample_fn():
        x, y, _ = np.random.uniform(*BASE_LIMITS)
        theta = np.random.uniform(*REVOLUTE_LIMITS)
        return (x, y, theta)

    def difference_fn(q2, q1):
        #return np.array(q2) - np.array(q1)
        dx, dy = np.array(q2[:2]) - np.array(q1[:2])
        dtheta = circular_difference(q2[2], q1[2])
        return (dx, dy, dtheta)

    weights = 1*np.ones(3)
    def distance_fn(q1, q2):
        difference = np.array(difference_fn(q2, q1))
        return np.sqrt(np.dot(weights, difference * difference))
        #return np.linalg.norm(np.array(q2) - np.array(q1))

    resolutions = 0.05*np.ones(3)
    def extend_fn(q1, q2):
        steps = np.abs(np.divide(difference_fn(q2, q1), resolutions))
        n = int(np.max(steps)) + 1
        q = q1
        for i in xrange(n):
            q = tuple((1. / (n - i)) * np.array(difference_fn(q2, q)) + q)
            yield q
            # TODO: should wrap these joints

    def collision_fn(q):
        set_base_values(body, q)
        return env_collision(body)

    start_conf = get_base_values(body)
    return birrt(start_conf, end_conf, distance_fn,
                 sample_fn, extend_fn, collision_fn, **kwargs)

def set_joint_positions(body, joints, values):
    assert len(joints) == len(values)
    for joint, value in zip(joints, values):
        set_joint_position(body, joint, value)

def get_joint_positions(body, joints):
    return tuple(get_joint_position(body, joint) for joint in joints)

def violates_limits(body, joints, values):
    for joint, value in zip(joints, values):
        if not is_circular(body, joint):
            lower, upper = get_joint_limits(body, joint)
            if (value < lower) or (upper < value):
                return True
    return False

def sample_joints(body, joints):
    values = []
    for joint in joints:
        limits = REVOLUTE_LIMITS if is_circular(body, joint) \
            else get_joint_limits(body, joint)
        values.append(np.random.uniform(*limits))
    return tuple(values)

def plan_joint_motion(body, joints, end_conf, **kwargs):
    assert len(joints) == len(end_conf)

    sample_fn = lambda: sample_joints(body, joints)

    def difference_fn(q2, q1):
        difference = []
        for joint, value2, value1 in zip(joints, q2, q1):
            difference.append((value2 - value1) if is_circular(body, joint)
                              else circular_difference(value2, value1))
        return tuple(difference)

    # TODO: custom weights and step sizes
    weights = 1*np.ones(len(joints))
    def distance_fn(q1, q2):
        diff = np.array(difference_fn(q2, q1))
        return np.sqrt(np.dot(weights, diff * diff))

    resolutions = 0.05*np.ones(len(joints))
    def extend_fn(q1, q2):
        steps = np.abs(np.divide(difference_fn(q2, q1), resolutions))
        num_steps = int(np.max(steps)) + 1
        q = q1
        for i in xrange(num_steps):
            q = tuple((1. / (num_steps - i)) * np.array(difference_fn(q2, q)) + q)
            yield q
            # TODO: should wrap these joints

    def collision_fn(q):
        if violates_limits(body, joints, q):
            return True
        set_joint_positions(body, joints, q)
        return env_collision(body)

    start_conf = get_joint_positions(body, joints)
    return birrt(start_conf, end_conf, distance_fn,
                 sample_fn, extend_fn, collision_fn, **kwargs)

def is_connected():
    return p.getConnectionInfo()['isConnected']

def get_connection():
    return p.getConnectionInfo()['connectionMethod']

def has_gui():
    return get_connection() == p.GUI

def sample_placement(top_body, bottom_body, max_attempts=50):
    bottom_aabb = get_lower_upper(bottom_body)
    for _ in xrange(max_attempts):
        theta = np.random.uniform(*REVOLUTE_LIMITS)
        quat = z_rotation(theta)
        set_quat(top_body, quat)
        center, extent = get_center_extent(top_body)
        lower = (np.array(bottom_aabb[0]) + extent/2)[:2]
        upper = (np.array(bottom_aabb[1]) - extent/2)[:2]
        if np.any(upper < lower):
          continue
        x, y = np.random.uniform(lower, upper)
        z = (bottom_aabb[1] + extent/2.)[2]
        point = np.array([x, y, z]) + (get_point(top_body) - center)
        set_point(top_body, point)
        return point, quat
    return None

def unit_from_theta(theta):
    return np.array([np.cos(theta), np.sin(theta)])

def sample_reachable_base(robot, point, max_attempts=50):
    reachable_range = (0.25, 1.0)
    for _ in xrange(max_attempts):
        radius = np.random.uniform(*reachable_range)
        x, y = radius*unit_from_theta(np.random.uniform(-np.pi, np.pi)) + point[:2]
        yaw = np.random.uniform(*REVOLUTE_LIMITS)
        base_values = (x, y, yaw)
        set_base_values(robot, base_values)
        return base_values
        #_, _, z = get_point(robot)
        #point = (x, y, z)
        #set_point(robot, point)
        #quat = z_rotation(yaw)
        #set_quat(robot, quat)
        #return (point, quat)
    return None

def main():
    parser = argparse.ArgumentParser()  # Automatically includes help
    parser.add_argument('-viewer', action='store_true', help='enable viewer.')
    args = parser.parse_args()

    client = p.connect(p.GUI) if args.viewer else p.connect(p.DIRECT)

    p.setAdditionalSearchPath(pybullet_data.getDataPath())  # optionally
    print pybullet_data.getDataPath()

    #p.setGravity(0, 0, -10)
    #planeId = p.loadURDF("plane.urdf")
    table = p.loadURDF("table/table.urdf", 0, 0, 0, 0, 0, 0.707107, 0.707107)

    # boxId = p.loadURDF("r2d2.urdf",cubeStartPos, cubeStartOrientation)
    # boxId = p.loadURDF("pr2.urdf")
    pr2 = p.loadURDF("/Users/caelan/Programs/Installation/pr2_description/pr2_local.urdf",
                     useFixedBase=False) # flags=p.URDF_USE_SELF_COLLISION_EXCLUDE_PARENT
    #pr2 = p.loadURDF("pr2_description/urdf/pr2_simplified.urdf", useFixedBase=False)

    print pr2
    # for i in range (10000):
    #    p.stepSimulation()
    #    time.sleep(1./240.)

    print get_joint_names(pr2)
    print joint_from_name(pr2, TORSO_JOINT)
    print get_joint_position(pr2, joint_from_name(pr2, TORSO_JOINT))

    raw_input('Continue?')

    print set_joint_position(pr2, joint_from_name(pr2, TORSO_JOINT), 0.2)  # Updates automatically

    print get_name(pr2)
    print get_body_names()
    # print p.getBodyUniqueId(pr2)
    print get_joint_names(pr2)

    #for joint, value in zip(LEFT_ARM_JOINTS, REST_LEFT_ARM):
    #    set_joint_position(pr2, joint, value)
    # for name, value in zip(LEFT_JOINT_NAMES, REST_LEFT_ARM):
    #     joint = joint_from_name(pr2, name)
    #     #print name, joint, get_joint_position(pr2, joint), value
    #     print name, get_joint_limits(pr2, joint), get_joint_type(pr2, joint), get_link_name(pr2, joint)
    #     set_joint_position(pr2, joint, value)
    #     #print name, joint, get_joint_position(pr2, joint), value
    # for name, value in zip(RIGHT_JOINT_NAMES, REST_RIGHT_ARM):
    #     set_joint_position(pr2, joint_from_name(pr2, name), value)

    print p.getNumJoints(pr2)
    jointId = 0
    print p.getJointInfo(pr2, jointId)
    print p.getJointState(pr2, jointId)

    # for i in xrange(10):
    #     #lower, upper = BASE_LIMITS
    #     #q = np.random.rand(len(lower))*(np.array(upper) - np.array(lower)) + lower
    #     q = np.random.uniform(*BASE_LIMITS)
    #     theta = np.random.uniform(*REVOLUTE_LIMITS)
    #     quat = z_rotation(theta)
    #     print q, theta, quat, env_collision(pr2)
    #     #set_point(pr2, q)
    #     set_pose(pr2, q, quat)
    #     #p.getMouseEvents()
    #     #p.getKeyboardEvents()
    #     raw_input('Continue?') # Stalls because waiting for input
    #
    # # TODO: self collisions
    # for i in xrange(10):
    #     for name in LEFT_JOINT_NAMES:
    #         joint = joint_from_name(pr2, name)
    #         value = np.random.uniform(*get_joint_limits(pr2, joint))
    #         set_joint_position(pr2, joint, value)
    #     raw_input('Continue?')



    start = (-2, -2, 0)
    set_base_values(pr2, start)

    # #start = get_base_values(pr2)
    # goal = (2, 2, 0)
    # p.addUserDebugLine(start, goal, lineColorRGB=(1, 1, 0)) # addUserDebugText
    # print start, goal
    # raw_input('Plan?')
    # path = plan_base_motion(pr2, goal)
    # print path
    # if path is None:
    #     return
    # print len(path)
    # for bq in path:
    #     set_base_values(pr2, bq)
    #     raw_input('Continue?')



    # left_joints = [joint_from_name(pr2, name) for name in LEFT_JOINT_NAMES]
    # for joint in left_joints:
    #     print joint, get_joint_name(pr2, joint), get_joint_limits(pr2, joint), \
    #         is_circular(pr2, joint), get_joint_position(pr2, joint)
    #
    # #goal = np.zeros(len(left_joints))
    # goal = []
    # for name, value in zip(LEFT_JOINT_NAMES, REST_LEFT_ARM):
    #     joint = joint_from_name(pr2, name)
    #     goal.append(wrap_joint(pr2, joint, value))
    #
    # path = plan_joint_motion(pr2, left_joints, goal)
    # print path
    # for q in path:s
    #     set_joint_positions(pr2, left_joints, q)
    #     raw_input('Continue?')

    print p.JOINT_REVOLUTE, p.JOINT_PRISMATIC, p.JOINT_FIXED, p.JOINT_POINT2POINT, p.JOINT_GEAR # 0 1 4 5 6

    print len(get_movable_joints(pr2))

    for joint in xrange(get_num_joints(pr2)):
        if is_movable(pr2, joint):
            print joint, get_joint_name(pr2, joint), get_joint_type(pr2, joint)

    joints = [joint_from_name(pr2, name) for name in LEFT_JOINT_NAMES]
    set_joint_positions(pr2, joints, sample_joints(pr2, joints))
    print get_joint_positions(pr2, joints) # Need to print before the display updates?




    #for i in xrange(10):
    box = create_box(.07, .05, .15)
    #set_point(box, (1, 1, 0))

    for _ in xrange(20):
        print sample_placement(box, table)
        #print sample_placement(box, table)
        sample_reachable_base(pr2, get_point(box))
        print get_base_values(pr2)
        raw_input('Placed!')


    origin = (0, 0, 0)
    link = link_from_name(pr2, LEFT_ARM_LINK)
    point, quat = get_link_pose(pr2, link)
    print point, quat
    p.addUserDebugLine(origin, point, lineColorRGB=(1, 1, 0))  # addUserDebugText
    raw_input('Continue?')

    movable_joints = get_movable_joints(pr2)
    current_conf = get_joint_positions(pr2, movable_joints)

    #ik_conf = p.calculateInverseKinematics(pr2, link, point)
    #ik_conf = p.calculateInverseKinematics(pr2, link, point, quat)

    min_limits = [get_joint_limits(pr2, joint)[0] for joint in movable_joints]
    max_limits = [get_joint_limits(pr2, joint)[1] for joint in movable_joints]
    max_velocities = [get_max_velocity(pr2, joint) for joint in movable_joints] # Range of Jacobian
    print min_limits
    print max_limits
    print max_velocities
    ik_conf = p.calculateInverseKinematics(pr2, link, point, quat, lowerLimits=min_limits,
                                           upperLimits=max_limits, jointRanges=max_velocities, restPoses=current_conf)


    value_from_joint = dict(zip(movable_joints, ik_conf))
    print [value_from_joint[joint] for joint in joints]

    #print len(ik_conf), ik_conf
    set_joint_positions(pr2, movable_joints, ik_conf)
    #print len(movable_joints), get_joint_positions(pr2, movable_joints)
    print get_joint_positions(pr2, joints)

    raw_input('Finish?')

    p.disconnect()

    # createConstraint


if __name__ == '__main__':
    main()