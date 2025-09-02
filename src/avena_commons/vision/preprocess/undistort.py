import cv2


def undistort(image, camera_matrix, camera_distortion):  # MARK: UNDISTORT
    """Koryguje zniekształcenia soczewki w obrazie.

    Funkcja koryguje zniekształcenia soczewki kamery w obrazie używając
    parametrów kalibracji kamery. Jest to niezbędne dla precyzyjnych
    pomiarów wizyjnych i poprawnego mapowania perspektywicznego.

    Args:
        image: Obraz wejściowy ze zniekształceniami (numpy.ndarray)
        camera_matrix: Macierz kamery zawierająca parametry wewnętrzne:
            [[fx, 0, cx],
             [0, fy, cy],
             [0, 0, 1]]
            gdzie fx, fy to ogniskowe, a cx, cy to punkt główny
        camera_distortion: Współczynniki zniekształcenia kamery (numpy.ndarray)

    Returns:
        numpy.ndarray: Obraz bez zniekształceń soczewki

    Example:
        >>> distorted_image = cv2.imread('distorted.jpg')
        >>> camera_matrix = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
        >>> dist_coeffs = np.array([k1, k2, p1, p2, k3])
        >>> corrected_image = undistort(distorted_image, camera_matrix, dist_coeffs)
    """

    return cv2.undistort(image, camera_matrix, camera_distortion)
