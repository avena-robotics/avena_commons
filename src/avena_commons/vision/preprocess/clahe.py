import cv2
import numpy as np


def clahe(image: np.ndarray, *, clip_limit: float, grid_size: int) -> np.ndarray:
    """Poprawia kontrast obrazu używając algorytmu CLAHE.

    Funkcja stosuje Contrast Limited Adaptive Histogram Equalization (CLAHE)
    do poprawy lokalnego kontrastu obrazu. CLAHE jest szczególnie skuteczny
    w przypadku obrazów z niejednorodnym oświetleniem, ponieważ przetwarza
    obraz w małych regionach (tiles) z ograniczeniem wzmocnienia szumu.

    Args:
        image: Obraz wejściowy w formacie OpenCV (numpy.ndarray)
        config: Słownik z konfiguracją CLAHE zawierający:
            - clip_limit (float): Limit przycinania histogramu (np. 2.0)
            - grid_size (int): Rozmiar siatki dla lokalnego przetwarzania (np. 8)

    Returns:
        numpy.ndarray: Obraz z poprawionym kontrastem lokalnym

    Example:
        >>> config = {"clip_limit": 2.0, "grid_size": 8}
        >>> enhanced_image = create_clahe(input_image, config)
    """
    return cv2.createCLAHE(
        clipLimit=clip_limit,
        tileGridSize=(grid_size, grid_size),
    ).apply(image)
