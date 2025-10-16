from copy import deepcopy

import cv2
import numpy as np


def prepare_image_output(image, cnts, rect, box):  # MARK: PREPARE IMAGE OUTPUT
    """Przygotowuje obraz wyjściowy z narysowanymi konturami i punktami.

    Funkcja tworzy kopię obrazu i rysuje na niej kontury, narożniki pudełka
    i centrum prostokąta dla celów wizualizacji.

    Args:
        image: Obraz wejściowy do wizualizacji
        cnts: Lista konturów do narysowania
        rect: Krotka zawierająca (center, size, angle) prostokąta
        box: Lista 4 narożników pudełka

    Returns:
        np.ndarray: Obraz z narysowanymi konturami i punktami

    Example:
        >>> image = cv2.imread("test.jpg")
        >>> contours = find_contours(mask)
        >>> rect = ((320, 240), (100, 50), 45)
        >>> box = [[270, 215], [370, 215], [370, 265], [270, 265]]
        >>> output_image = prepare_image_output(image, contours, rect, box)
        >>> cv2.imshow("Output", output_image)
    """
    image_copy = deepcopy(image)
    for cnt in cnts:
        cv2.drawContours(image_copy, [cnt], -1, (0, 255, 0), 2)

    for point in box:
        cv2.circle(image_copy, (int(point[0]), int(point[1])), 10, (0, 0, 255), -1)

    cv2.circle(image_copy, (int(rect[0][0]), int(rect[0][1])), 10, (0, 0, 255), -1)
    box_int = np.intp(box)
    cv2.drawContours(image_copy, [box_int], -1, (0, 255, 0), 2)

    return image_copy
