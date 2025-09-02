import cv2
import numpy as np


def get_hit_contours(mask, cnts, config):  # MARK: GET HIT CONTOURS
    """Znajduje kontury, które są trafione przez promienie wychodzące z punktu centralnego.

    Funkcja wykonuje skanowanie promieniami w 360 stopniach z punktu centralnego
    i identyfikuje kontury, które są trafione przez te promienie.

    Args:
        mask: Obraz maski używany do określenia kształtu
        cnts: Lista konturów do sprawdzenia
        config: Słownik zawierający parametry konfiguracji:
            - angle_step: Krok kąta dla skanowania promieniami (w stopniach)
            - step_size: Rozmiar kroku dla promieni
            - center_point: Punkt centralny (x, y) do skanowania

    Returns:
        tuple: (hit_contours, labeled_mask) - lista trafionych konturów i maska z etykietami

    Example:
        >>> config = {
        ...     "angle_step": 5,
        ...     "step_size": 2,
        ...     "center_point": [320, 240]
        ... }
        >>> hit_contours, labeled_mask = get_hit_contours(mask, contours, config)
    """
    def label_contours(image_shape, contours):
        """Tworzy maskę z etykietami gdzie każdy kontur ma unikalną etykietę."""
        labeled_mask = np.zeros(image_shape, dtype=np.int32)
        for i, cnt in enumerate(contours, start=1):  # start labels from 1
            cv2.drawContours(labeled_mask, [cnt], -1, i, -1)  # fill the contour
        return labeled_mask

    def ray_scan_labeled(labeled_mask, center, angle_step=1, step_size=1):
        """Skanuje promieniami maskę z etykietami i zwraca trafienia."""
        hits = {}
        height, width = labeled_mask.shape
        for angle in np.arange(0, 360, angle_step):
            rad = np.deg2rad(angle)
            dx = np.cos(rad)
            dy = np.sin(rad)
            x, y = center[0], center[1]

            # Step along the ray until we go out of bounds or hit a contour pixel.
            while 0 <= int(x) < width and 0 <= int(y) < height:
                label = labeled_mask[int(y), int(x)]
                if label != 0:  # nonzero means a contour pixel
                    if label not in hits:
                        hits[label] = []
                    hits[label].append((x, y))
                    break
                x += dx * step_size
                y += dy * step_size

        return hits

    angle_step = config["angle_step"]
    step_size = config["step_size"]
    center_point = config["center_point"]

    labeled_mask = label_contours(mask.shape, cnts)
    hits = ray_scan_labeled(labeled_mask, center_point, angle_step, step_size)
    hit_contour_ids = list(hits.keys())
    hit_contours = [cnts[label - 1] for label in hit_contour_ids]
    return hit_contours, labeled_mask
