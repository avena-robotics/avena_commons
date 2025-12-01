import numpy as np
from scipy.spatial.transform import Rotation as R


def transform_camera_to_base(
    item_pose, current_tcp, camera_tool_offset, is_rotation=False
):
    """Transform position from camera coordinates to robot base coordinates.

    Args:
        item_pose (list): [x, y, z, rx, ry, rz] Position and orientation of item in camera frame
        current_tcp (list): [x, y, z, rx, ry, rz] Current TCP position in base frame
        camera_tool_offset (list): [x, y, z, rx, ry, rz] Camera offset from TCP
        is_rotation (bool): If True, rotate item around Z axis by 180 degrees

    Returns:
        list: Transformed target position in robot base coordinates [x, y, z, rx, ry, rz]

    The transformation takes into account:
    - Current TCP position
    - Camera offset from TCP
    - Item pose from camera detection
    - Optional Z-axis rotation (180 degrees)

    Uses rotation matrices and homogeneous transformations for coordinate conversion.
    """
    # Create transformation matrices
    T_base_tcp = create_transform_matrix(
        current_tcp
    )  # base position in robot base coordinates
    T_tcp_camera = create_transform_matrix(camera_tool_offset)  # camera relative to TCP

    # Create transformation matrix for camera detection
    item_pose_oryginal_euler = item_pose[3:]
    temp_item_pose = item_pose[:3] + [
        0.0,
        0.0,
        0.0,
    ]  # do not rotate object in x,y. Only z later
    T_camera_object_temp = create_transform_matrix(temp_item_pose)

    # Calculate complete transformation
    T_goal = T_base_tcp @ T_tcp_camera @ T_camera_object_temp

    if is_rotation:
        # Rotate chosen items in Z axis by 180 degrees
        Rz = R.from_euler("z", 180, degrees=True)
        T_goal[0:3, 0:3] = T_goal[0:3, 0:3] @ Rz.as_matrix()

    new_camera_object_euler = R.from_matrix(T_goal[0:3, 0:3]).as_euler(
        "xyz", degrees=True
    )

    new_camera_object_euler[2] = (
        new_camera_object_euler[2] - item_pose_oryginal_euler[2]
    ) % 360
    if new_camera_object_euler[2] > 180:
        new_camera_object_euler[2] -=360

    # Normalize all rotation angles
    # rx, ry, rz = [normalize_angle(angle) for angle in new_camera_object_euler]
    rx, ry, rz = new_camera_object_euler

    # Extract position and euler angles from final transformation
    pos = T_goal[:3, 3]

    return [pos[0], pos[1], pos[2], rx, ry, rz]


def normalize_angle(angle):
    """Normalize angle to range [-180, 180] degrees.

    Args:
        angle (float): Input angle in degrees

    Returns:
        float: Normalized angle in range [-180, 180]
    """
    angle = angle % 360
    if angle > 180:
        angle -= 360
    return angle


def euler_to_rotation_matrix(rx, ry, rz):
    """Convert euler angles to rotation matrix.

    Args:
        rx (float): Rotation around X axis in degrees
        ry (float): Rotation around Y axis in degrees
        rz (float): Rotation around Z axis in degrees

    Returns:
        np.ndarray: 3x3 rotation matrix
    """
    # Convert to radians
    rx, ry, rz = np.radians([rx, ry, rz])

    # Rotation matrices around x, y, z
    Rx = np.array([
        [1, 0, 0],
        [0, np.cos(rx), -np.sin(rx)],
        [0, np.sin(rx), np.cos(rx)],
    ])

    Ry = np.array([
        [np.cos(ry), 0, np.sin(ry)],
        [0, 1, 0],
        [-np.sin(ry), 0, np.cos(ry)],
    ])

    Rz = np.array([
        [np.cos(rz), -np.sin(rz), 0],
        [np.sin(rz), np.cos(rz), 0],
        [0, 0, 1],
    ])

    # Combined rotation matrix
    R = Rz @ Ry @ Rx
    return R


def create_transform_matrix(pos):
    """Create 4x4 homogeneous transformation matrix from position and orientation.

    Args:
        pos (list): [x, y, z, rx, ry, rz] Position and euler angles in degrees

    Returns:
        np.ndarray: 4x4 homogeneous transformation matrix
    """
    T = np.eye(4)
    T[:3, :3] = euler_to_rotation_matrix(pos[3], pos[4], pos[5])
    T[:3, 3] = pos[:3]
    return T
