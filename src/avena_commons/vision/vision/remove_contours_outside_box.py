import cv2


def remove_contours_outside_box(
    contours, config
):  # MARK: REMOVE CONTOURS OUTSIDE EXPECTED BOX
    """Usuwa kontury znajdujące się poza oczekiwanym obszarem pudełka.

    Funkcja filtruje kontury, pozostawiając tylko te, które znajdują się
    w określonym obszarze wokół punktu centralnego, i sortuje je według odległości od centrum.

    Args:
        contours: Lista konturów do przefiltrowania
        config: Słownik zawierający parametry konfiguracji:
            - center_point: Punkt centralny (x, y) oczekiwanego obszaru
            - expected_width: Oczekiwana szerokość obszaru
            - expected_height: Oczekiwana wysokość obszaru

    Returns:
        list: Lista przefiltrowanych konturów posortowanych według odległości od centrum

    Example:
        >>> config = {
        ...     "center_point": [320, 240],
        ...     "expected_width": 200,
        ...     "expected_height": 150
        ... }
        >>> filtered_contours = remove_contours_outside_box(contours, config)
    """

    def distance_from_center(cnt, center_point):
        """Oblicza odległość konturu od punktu centralnego."""
        x, y, w, h = cv2.boundingRect(cnt)
        return (
            (x + w / 2 - center_point[0]) ** 2 + (y + h / 2 - center_point[1]) ** 2
        ) ** 0.5

    center_point = config["center_point"]
    box_expected_width = config["expected_width"]
    box_expected_height = config["expected_height"]

    expected_bbox = (
        center_point[0] - box_expected_width // 2,
        center_point[1] - box_expected_height // 2,
        box_expected_width,
        box_expected_height,
    )

    box_cnts = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if not (
            x + w < expected_bbox[0]  # contour is left of bbox
            or x > expected_bbox[0] + expected_bbox[2]  # contour is right of bbox
            or y + h < expected_bbox[1]  # contour is above bbox
            or y > expected_bbox[1] + expected_bbox[3]
        ):  # contour is below bbox
            box_cnts.append(contour)

    box_cnts.sort(key=lambda cnt: distance_from_center(cnt, center_point))

    return box_cnts
