import cv2
import numpy as np
from scipy.spatial.transform import Rotation as R


def calculate_pose_pnp(
    corners: list,
    *,
    a: float,
    b: float,
    z: float,
    camera_matrix: np.ndarray,
) -> tuple:
    """
    Calculate object pose using PnP algorithm.

    Args:
        corners: List of 4 corner points in image coordinates
        a: Object width
        b: Object height
        camera_params: Camera intrinsic parameters [fx, fy, cx, cy]
        z: Depth value

    Returns:
        tuple: (tx, ty, tz, rx, ry, rz) containing translation and rotation
        If test=True: also returns reprojection error
    """
    # camera_matrix = np.array(
    #     [
    #         [camera_params[0], 0, camera_params[2]],
    #         [0, camera_params[1], camera_params[3]],
    #         [0, 0, 1],
    #     ],
    #     dtype=np.float32,
    # )
    fake_camera_distortion = np.array(
        [0, 0, 0, 0, 0], dtype=np.float32
    )  # zdjecie jest juz undistorted

    points_3d = np.array(
        [
            [-a / 2, b / 2, 0],  # Dolny lewy róg
            [a / 2, b / 2, 0],  # Dolny prawy róg
            [a / 2, -b / 2, 0],  # Górny prawy róg
            [-a / 2, -b / 2, 0],  # Górny lewy róg
        ],
        dtype=np.float32,
    )
    corners = np.array(corners, dtype=np.float32)

    _, rot_vec, trans_vec = cv2.solvePnP(
        points_3d,
        corners,
        camera_matrix,
        fake_camera_distortion,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    translation = trans_vec.flatten().tolist()
    rot_vec_flat = np.array([
        rot_vec
    ]).flatten()  # Upewnij się, że rot_vec jest jednowymiarowy
    rotation = R.from_rotvec(rot_vec_flat)
    euler_angles = rotation.as_euler("xyz", degrees=True)

    return (
        translation[0],
        translation[1],
        translation[2],
        0.0,  # euler_angles[0],
        0.0,  # euler_angles[1],
        euler_angles[2],
    )
