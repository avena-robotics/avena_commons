import numpy as np


def create_camera_matrix(camera_params):
    """Tworzy macierz kamery z parametrów wewnętrznych.

    Funkcja tworzy macierz kamery w formacie wymaganym przez OpenCV
    z parametrów wewnętrznych kamery. Macierz kamery zawiera informacje
    o ogniskowych i punkcie głównym, niezbędne do transformacji
    współrzędnych obrazu na współrzędne świata.

    Args:
        camera_params: Lista parametrów kamery [fx, fy, cx, cy] gdzie:
            - fx: Ogniskowa w kierunku X (piksele)
            - fy: Ogniskowa w kierunku Y (piksele)
            - cx: Współrzędna X punktu głównego (piksele)
            - cy: Współrzędna Y punktu głównego (piksele)

    Returns:
        numpy.ndarray: Macierz kamery 3x3 w formacie float32:
            [[fx, 0, cx],
             [0, fy, cy],
             [0, 0, 1]]

    Example:
        >>> params = [800.0, 800.0, 320.0, 240.0]  # fx, fy, cx, cy
        >>> camera_matrix = create_camera_matrix(params)
        >>> print(f"Macierz kamery:\n{camera_matrix}")
    """
    return np.array(
        [
            [camera_params[0], 0, camera_params[2]],
            [0, camera_params[1], camera_params[3]],
            [0, 0, 1],
        ],
        dtype=np.float32,
    )
