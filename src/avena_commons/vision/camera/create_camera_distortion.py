import numpy as np


def create_camera_distortion(distortion_coefficients):
    """Tworzy macierz współczynników zniekształcenia kamery.

    Funkcja konwertuje listę współczynników zniekształcenia kamery na
    tablicę NumPy w formacie wymaganym przez OpenCV. Współczynniki
    zniekształcenia są używane do korekcji zniekształceń soczewki
    w algorytmach kalibracji kamery.

    Args:
        distortion_coefficients: Lista lub tablica współczynników zniekształcenia
            [k1, k2, p1, p2, k3] gdzie:
            - k1, k2, k3: Współczynniki radialnego zniekształcenia
            - p1, p2: Współczynniki tangencjalnego zniekształcenia

    Returns:
        numpy.ndarray: Tablica współczynników zniekształcenia w formacie float32

    Example:
        >>> distortion_coeffs = [0.1, -0.2, 0.001, 0.002, 0.05]
        >>> camera_distortion = create_camera_distortion(distortion_coeffs)
        >>> print(f"Typ: {camera_distortion.dtype}, Kształt: {camera_distortion.shape}")
    """
    camera_distortion = np.array(distortion_coefficients, dtype=np.float32)

    return camera_distortion
