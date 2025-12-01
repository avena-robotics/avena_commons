import cv2
import numpy as np


def blend(
    image1: np.ndarray, image2: np.ndarray, merge_image_weight: float
) -> np.ndarray:
    """Łączy dwa obrazy używając ważonej średniej.

    Funkcja łączy dwa obrazy używając ważonej średniej, gdzie pierwszy obraz
    ma wagę merge_image_weight, a drugi obraz ma wagę (1 - merge_image_weight).
    Jest to przydatne do mieszania obrazów, tworzenia efektów przejścia
    lub łączenia różnych wersji tego samego obrazu.

    Args:
        image1: Pierwszy obraz do połączenia (numpy.ndarray)
        image2: Drugi obraz do połączenia (numpy.ndarray)
        merge_image_weight: Waga pierwszego obrazu (0.0-1.0), gdzie:
            0.0 = tylko drugi obraz, 1.0 = tylko pierwszy obraz

    Returns:
        numpy.ndarray: Połączony obraz o tym samym rozmiarze co obrazy wejściowe

    Example:
        >>> image1 = cv2.imread('image1.jpg')
        >>> image2 = cv2.imread('image2.jpg')
        >>> blended = blend(image1, image2, 0.7)  # 70% image1, 30% image2
        >>> cv2.imshow('Blended', blended)
    """
    blended_image = cv2.addWeighted(
        image1,
        merge_image_weight,
        image2,
        1 - merge_image_weight,
        0,
    )
    return blended_image
