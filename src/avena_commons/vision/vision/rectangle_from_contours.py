import cv2
import numpy as np


def rectangle_from_contours(cnts):
    """Tworzy prostokąt o minimalnym polu z listy konturów.

    Funkcja łączy wszystkie punkty z konturów i znajduje prostokąt o minimalnym polu
    który obejmuje wszystkie punkty.

    Args:
        cnts: Lista konturów do połączenia

    Returns:
        tuple: (rect, box) - prostokąt i jego narożniki
            - rect: Krotka (center, size, angle) prostokąta
            - box: Lista 4 narożników prostokąta

    Example:
        >>> contours = [contour1, contour2]
        >>> rect, box = rectangle_from_contours(contours)
        >>> print(f"Centrum: {rect[0]}, Rozmiar: {rect[1]}, Kąt: {rect[2]}")
    """
    combined_points = np.vstack([cnt.reshape(-1, 2) for cnt in cnts])
    rect = cv2.minAreaRect(combined_points)
    box = cv2.boxPoints(rect).tolist()
    return rect, box
