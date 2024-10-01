"""
# Utility Functions Module

This module is a collection of utility functions that are likely used for various mathematical and transformation operations, particularly in the context of robotics, simulations, or computer graphics. The functions cover a wide range of tasks, from quaternion and Euler angle manipulations to filtering and interpolation.

# Classes and Objects

## Catchtime
- [catchtime](./util/catchtime.html): A class that measures the time taken to execute a block of code.  

## ControlLoop
- [control_loop](./util/control_loop.html): A class that controls the loop of the program and measures the time taken to execute a block of code.  

Example of usage:
```python
from lib.util.control_loop import ControlLoop
## Create a control loop
control_loop = ControlLoop("MyControlLoop", period=0.002)

try:
    while True:
        control_loop.loop_begin()
        # Your code here
        control_loop.loop_end()
except KeyboardInterrupt:
    pass 
```  
## ErrorManager
- [error_level](./util/error_level.html): A class that manages error codes.  

Example of usage:
```python
try:
    error_manager = ErrorManager(message_logger, suffix)

    while True:
        error_manager.set_error(ErrorCodes.CONNECTION_ERROR, "Failed to connect to the server")

        current_error = error_manager.current_error    # => lista [ErrorInfo(ErrorCodes.CONNECTION_ERROR, ErrorGroups.CRITICAL, "Failed to connect to the server", ...])
        if error_manager.check_current_group(ErrorGroups.CRITICAL):
            #Przerwij program
            error_manager.ack_errors()
        elif error_manager.check_current_group(ErrorGroups.ERROR):
            #powtórz program
            error_manager.ack_errors()
        elif error_manager.check_current_group(ErrorGroups.WARNING):
            #kontynuuj program, nic nie rób

        if check_current_error = error_manager.check_current_error(ErrorCodes.CONNECTION_ERROR):
            # do something for this specific error
except KeyboardInterrupt:
    pass
finally:
    error_manager.stop()
```  

## LimitedQueue
- [limited_queue](./util/limited_queue.html): A class that implements a queue with a maximum size.  

## Logger
- [logger](./util/logger.html): A set of classes that logs data to a file.  

Example of usage:
```python
from lib.util.logger import Logger, MessageLogger, DataLogger, info, debug, warning, error

## Create a logger
msg_logger = MessageLogger(f"/0001_control_loop1.log", debug=True)

info(f"Trajectory updated from file traj1 in 0.1 ms.", message_logger)
debug(f"PID values reset for joint 1", message_logger)
warning(f"Time to load trajectory: 2 ms", message_logger)
error(f"Time to load trajectory: 5 ms", message_logger)
```  
## Monitor
- [monitor](./util/monitor.html): A class that monitors the CPU cores usage, disk space usage, and network usage.  


## Connector / Worker
- [Connector-Worker](./util/worker.html): Two classes that manage connector/worker processes. Which are used as a template to build non-blocking communication between processes. 


# Functions and Their Usage

1. `interpolate`: Interpolates between two values based on a given alpha value.
2. `moving_average_filter`: Applies a moving average filter to a list of values.
3. `ramp_smoothing`: Smooths a list of values using a ramp function.
4. `interpolate_rconfigs`: Interpolates between two robot configurations.
5. `calculate_factor`: Calculates a factor based on a given alpha value.
6. `calculate_factors`: Calculates factors for a list of alpha values.
7. `limit_acc`: Limits the acceleration of a value based on a maximum acceleration.
8. `limit_vel`: Limits the velocity of a value based on a maximum velocity.
9. `calculate_derivative`: Calculates the derivative of a list of values.
10. `find_closest_pose`: Finds the closest pose to a given pose in a list of poses.
11. `clip_goal_position`: Clips the goal position based on the maximum allowed distance.
12. `check_distance`: Checks the distance between two points.
13. `update_similar_attr`: Updates similar attributes in two objects.
14. `get_quaternion_from_euler`: Converts Euler angles to a quaternion.
15. `euler_from_quaternion`: Converts a quaternion to Euler angles.
16. `degrees_to_radians`: Converts degrees to radians.
17. `radians_to_degrees`: Converts radians to degrees.
18. `rotate_vector_by_euler`: Rotates a vector using Euler angles.
19. `create_transformation_matrix`: Creates a transformation matrix from translation and rotation.
20. `rotate_transformation_matrix`: Rotates a transformation matrix.
21. `pose_from_transformation_matrix`: Extracts a pose from a transformation matrix.
22. `rotate_pose`: Rotates a pose.
23. `quaternion_angle_diff`: Calculates the angle difference between two quaternions.
24. `calculate_rms`: Calculates the root mean square of a list of values.
25. `angle_axis_to_quaternion`: Converts an angle-axis representation to a quaternion.
26. `joints_set_current_position_to_goal_position`: utility that sets the current position of joints to the goal position.
27. `string_to_float_list`: Converts a string of float values to a list of floats.
28. `rotate_points_around_center`: Rotates a list of points around a center point.
29. `rotate_quat_in_euler`: Rotates a quaternion using Euler angles.
30. `rotation_matrix_to_euler_angles`: Converts a rotation matrix to Euler angles.
31. `rotation_matrix_to_rvec`: Converts a rotation matrix to a rotation vector.
32. `euler_to_rotation_matrix`: Converts Euler angles to a rotation matrix.

Usage Example:
```python
from lib.utils import get_quaternion_from_euler, rotate_vector_by_euler, calculate_rms

# Convert Euler angles to quaternion
euler_angles = [0.0, 1.57, 0.0]  # Example Euler angles
quaternion = get_quaternion_from_euler(euler_angles)

# Rotate a vector using the Euler angles
vector = [1.0, 0.0, 0.0]
rotated_vector = rotate_vector_by_euler(vector, euler_angles)

# Calculate RMS of some error values
errors = [0.1, 0.2, 0.15, 0.05]
rms_error = calculate_rms(errors)

print(f"Quaternion: {quaternion}")
print(f"Rotated Vector: {rotated_vector}")
print(f"RMS Error: {rms_error}")
```
"""

from .utils import interpolate
from .utils import moving_average_filter
from .utils import ramp_smoothing
from .utils import interpolate_rconfigs
from .utils import calculate_factor
from .utils import calculate_factors
from .utils import limit_acc
from .utils import limit_vel
from .utils import calculate_derivative
from .utils import find_closest_pose
from .utils import clip_goal_position
from .utils import check_distance
from .utils import update_similar_attr
from .utils import get_quaternion_from_euler
from .utils import euler_from_quaternion
from .utils import degrees_to_radians
from .utils import radians_to_degrees
from .utils import rotate_vector_by_euler
from .utils import create_transformation_matrix
from .utils import rotate_transformation_matrix
from .utils import pose_from_transformation_matrix
from .utils import rotate_pose
from .utils import quaternion_angle_diff
from .utils import calculate_rms
from .utils import angle_axis_to_quaternion
from .utils import joints_set_current_position_to_goal_position
from .utils import string_to_float_list
from .utils import rotate_points_around_center
from .utils import rotate_quat_in_euler
from .utils import rotation_matrix_to_euler_angles
from .utils import rotation_matrix_to_rvec
from .utils import euler_to_rotation_matrix
