#!/usr/bin/env python

#from __future__ import print_function

import IPython
import numpy
import random
import pb_robot
import pb_robot.utils_noBase as utils
import pb_robot.viz as viz

def GeodesicError(t1, t2):
    """
    Computes the error in global coordinates between two transforms.
    @param t1 current transform
    @param t2 goal transform
    @return a 4-vector of [dx, dy, dz, solid angle]
    """
    trel = numpy.dot(numpy.linalg.inv(t1), t2)
    trans = numpy.dot(t1[0:3, 0:3], trel[0:3, 3])
    angle, _, _ = pb_robot.transformations.rotation_from_matrix(trel) 
    return numpy.hstack((trans, angle))

def GeodesicDistance(t1, t2, r=1.0):
    """
    Computes the geodesic distance between two transforms
    @param t1 current transform
    @param t2 goal transform
    @param r in units of meters/radians converts radians to meters
    """
    error = GeodesicError(t1, t2)
    error[3] = r * error[3]
    return numpy.linalg.norm(error)

def randomConfiguration(yumi):
    (lower, upper) = yumi.right_arm.GetJointLimits() 
    dofs = numpy.zeros(len(lower))
    for i in xrange(len(lower)):
        dofs[i] = random.uniform(lower[i], upper[i])
    return dofs

def main(): 
    utils.connect(use_gui=True)
    utils.disable_real_time()

    yumi = pb_robot.yumi.Yumi() 
    utils.set_default_camera()
    #utils.dump_world()

    yumi.left_arm.SetJointValues([2, 0, 0, 0, 0, 0, 0])

    current_t = yumi.right_hand.get_link_pose()
    new_p = (0.58, 0.0, 0.515) 
    target_p = (new_p, current_t[1])
    #viz.draw_pose(target_p, length=0.5, width=10)
    #f = utils.inverse_kinematics(yumi, right_hand, target_p)

    qs = [[0, 0, 0, 0, 0, 0, 0],
          [1, 0, 0, 0, 0, 0, 0]]

    for i in xrange(100):
        q = randomConfiguration(yumi)
        pose = yumi.right_arm.ComputeFK(q)
        full_solved_q = yumi.right_arm.ComputeIK(pb_robot.geometry.pose_from_tform(pose))  # edit ComputeIK
        if full_solved_q is None:
            #print("No solution")
            continue
        solved_q = full_solved_q[0:7]
        solved_pose = yumi.right_arm.ComputeFK(solved_q)
        error = GeodesicDistance(pose, solved_pose)
        second_error = utils.is_pose_close(pb_robot.geometry.pose_from_tform(pose), 
                                           pb_robot.geometry.pose_from_tform(solved_pose))
        print((error < 0.002) and second_error)

    IPython.embed()
  
    print('Quit?')
    utils.wait_for_user()
    utils.disconnect()

if __name__ == '__main__':
    main()
