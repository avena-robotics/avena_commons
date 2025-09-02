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
    """Oblicza pozycję obiektu używając algorytmu PnP (Perspective-n-Point).

    Funkcja wykorzystuje algorytm solvePnP z OpenCV do wyznaczenia pozycji i orientacji
    obiektu na podstawie znanych punktów 3D i ich projekcji na obrazie 2D.

    Args:
        corners: Lista 4 punktów narożnych w współrzędnych obrazu (x, y)
        a: Szerokość obiektu w jednostkach rzeczywistych
        b: Wysokość obiektu w jednostkach rzeczywistych  
        z: Wartość głębi (odległość) obiektu
        camera_matrix: Macierz parametrów wewnętrznych kamery (3x3)

    Returns:
        tuple: Krotka zawierająca (tx, ty, tz, rx, ry, rz) - translację i rotację obiektu
            - tx, ty, tz: współrzędne translacji w mm
            - rx, ry, rz: kąty rotacji w stopniach (tylko rz jest używany)

    Example:
        >>> corners = [[100, 200], [300, 200], [300, 400], [100, 400]]
        >>> camera_matrix = np.array([[500, 0, 320], [0, 500, 240], [0, 0, 1]])
        >>> pose = calculate_pose_pnp(corners, a=50.0, b=30.0, z=1000.0, camera_matrix=camera_matrix)
        >>> print(f"Pozycja: {pose[:3]}, Rotacja: {pose[3:]}")
    """
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
