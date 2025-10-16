import cv2


def create_box_color_mask(color_image, config):
    """Tworzy maskę kolorową do detekcji pudełka w przestrzeni barw HSV.

    Funkcja konwertuje obraz BGR do HSV i tworzy binarną maskę na podstawie
    zadanych progów dla składowych Hue, Saturation i Value.

    Args:
        color_image: Obraz kolorowy w formacie BGR
        config: Słownik zawierający parametry progów HSV:
            - hsv_h_min/max: Zakres odcienia (0-179)
            - hsv_s_min/max: Zakres nasycenia (0-255)
            - hsv_v_min/max: Zakres jasności (0-255)

    Returns:
        np.ndarray: Binarna maska (0 lub 255) na podstawie progów HSV

    Example:
        >>> config = {
        ...     "hsv_h_min": 0, "hsv_h_max": 10,
        ...     "hsv_s_min": 100, "hsv_s_max": 255,
        ...     "hsv_v_min": 50, "hsv_v_max": 255
        ... }
        >>> mask = create_box_color_mask(bgr_image, config)
        >>> cv2.imshow("Color Mask", mask)
    """
    hsv_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv_image)

    mask_h = cv2.inRange(h, config["hsv_h_min"], config["hsv_h_max"])
    mask_s = cv2.inRange(s, config["hsv_s_min"], config["hsv_s_max"])
    mask_v = cv2.inRange(v, config["hsv_v_min"], config["hsv_v_max"])

    mask = mask_h & mask_s & mask_v
    return mask
