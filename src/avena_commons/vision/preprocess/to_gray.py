import cv2
import numpy as np


def to_gray(image: np.ndarray) -> np.ndarray:
    """Konwertuje obraz kolorowy na obraz w skali szarości.

    Funkcja konwertuje obraz z przestrzeni barw BGR (Blue-Green-Red) na
    obraz w skali szarości używając standardowej konwersji OpenCV.
    Jest to podstawowa operacja w przetwarzaniu obrazów, często używana
    jako pierwszy krok w wielu algorytmach wizyjnych.

    Args:
        image: Obraz wejściowy w formacie BGR (numpy.ndarray)

    Returns:
        numpy.ndarray: Obraz w skali szarości o tym samym rozmiarze co obraz wejściowy

    Example:
        >>> color_image = cv2.imread('color_image.jpg')
        >>> gray_image = to_gray(color_image)
        >>> cv2.imshow('Gray', gray_image)
    """
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
