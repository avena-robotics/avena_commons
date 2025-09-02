import cv2


def remove_edge_contours(contours, image_shape, config):
    """Usuwa kontury znajdujące się zbyt blisko krawędzi obrazu.

    Funkcja filtruje kontury, usuwając te, które znajdują się zbyt blisko
    krawędzi obrazu w określonym marginesie.

    Args:
        contours: Lista konturów do przefiltrowania
        image_shape: Kształt obrazu (height, width)
        config: Słownik zawierający parametry konfiguracji:
            - edge_margin: Margines od krawędzi w pikselach (domyślnie 5)

    Returns:
        list: Lista przefiltrowanych konturów

    Example:
        >>> config = {"edge_margin": 10}
        >>> filtered_contours = remove_edge_contours(contours, (480, 640), config)
    """
    margin = config.get("edge_margin", 5)  # Default margin of 5 pixels from edge
    height, width = image_shape

    filtered_cnts = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        # Check if contour is too close to any edge
        if (
            x > margin  # Not too close to left edge
            and y > margin  # Not too close to top edge
            and x + w < width - margin  # Not too close to right edge
            and y + h < height - margin
        ):  # Not too close to bottom edge
            filtered_cnts.append(cnt)

    return filtered_cnts
