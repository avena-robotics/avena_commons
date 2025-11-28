import math


def validate_rectangle(rect, box, image, config):  # MARK: VALIDATE RECT
    """Waliduje prostokąt wykrytego pudełka pod kątem różnych kryteriów.

    Funkcja wykonuje szereg testów walidacyjnych na wykrytym prostokącie pudełka:
    sprawdza rozmiary, proporcje, odległość od centrum, kąt obrotu i pozycję narożników.

    Args:
        rect: Krotka zawierająca (center, size, angle) prostokąta
        box: Lista 4 narożników pudełka
        image: Obraz do sprawdzenia granic
        config: Słownik zawierający parametry walidacji:
            - box_ratio_range: Zakres akceptowalnych proporcji [min, max]
            - center_point: Punkt centralny (x, y) oczekiwanego obszaru
            - max_distance: Maksymalna odległość od centrum
            - max_angle: Maksymalny kąt odchylenia od poziomu

    Returns:
        bool: True jeśli prostokąt przechodzi wszystkie testy walidacyjne, False w przeciwnym razie

    Example:
        >>> rect = ((320, 240), (900, 600), 30)
        >>> box = [[270, 190], [370, 190], [370, 290], [270, 290]]
        >>> config = {
        ...     "box_ratio_range": [1.2, 2.0],
        ...     "center_point": [320, 240],
        ...     "max_distance": 100,
        ...     "max_angle": 30
        ... }
        >>> is_valid = validate_rectangle(rect, box, image, config)
    """
    # if rect[1][0] > rect[1][1]:
    #     long = rect[1][0]
    #     short = rect[1][1]
    # else:
    #     long = rect[1][1]
    #     short = rect[1][0]

    long = rect[1][0]
    short = rect[
        1
    ][
        1
    ]  # simplified #TO jest żle zależne of obrotu pudełka gdy jest większe od 45 stopni to long i short się zamieniają

    angle = rect[2]
    if angle > 45:
        long, short = short, long  # swap
        print("Swapped sides due to angle:", angle)

    # 0. check if box is not too small or too big
    if (
        long < config["side_length"]["long"][0]
        or long > config["side_length"]["long"][1]
        or short < config["side_length"]["short"][0]
        or short > config["side_length"]["short"][1]
    ):
        return False

    ratio = long / short
    if ratio > config["box_ratio_range"][1] or ratio < config["box_ratio_range"][0]:
        return False

    # 2. check distance between center of the rect and assumed center of the box
    center_rect = rect[0]
    center_box = config["center_point"]
    distance = math.sqrt(
        (center_rect[0] - center_box[0]) ** 2 + (center_rect[1] - center_box[1]) ** 2
    )
    if distance > config["max_distance"]:
        return (False,)

    # 3. check box angle
    if angle == 45:
        return False
    if angle < 45 and angle > config["max_angle"]:
        return False
    if angle > 45 and angle < 90 - config["max_angle"]:
        return False

    # 4. check if box corner is not near the edge of the image
    for corner in box:
        if (
            corner[0] < 0
            or corner[0] > image.shape[1]
            or corner[1] < 0
            or corner[1] > image.shape[0]
        ):
            return False

    return True
