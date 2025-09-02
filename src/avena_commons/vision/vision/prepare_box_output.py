import numpy as np


def prepare_box_output(rect, box, depth_image, config):
    """Przygotowuje dane wyjściowe dla wykrytego pudełka.

    Funkcja przetwarza dane prostokąta i pudełka, sortuje narożniki w określonej kolejności
    i oblicza głębię na podstawie mediany wartości w centralnym obszarze.

    Args:
        rect: Krotka zawierająca (center, size, angle) prostokąta
        box: Lista 4 narożników pudełka
        depth_image: Obraz głębi do obliczenia odległości
        config: Słownik zawierający parametry konfiguracji:
            - center_size: Rozmiar centralnego obszaru do obliczenia głębi

    Returns:
        tuple: (center, sorted_corners, angle, z) - centrum, posortowane narożniki, kąt i głębia

    Example:
        >>> rect = ((320, 240), (100, 50), 45)
        >>> box = [[270, 215], [370, 215], [370, 265], [270, 265]]
        >>> config = {"center_size": 20}
        >>> center, corners, angle, z = prepare_box_output(rect, box, depth_image, config)
    """
    center = rect[0]
    angle = rect[2]

    sorted_corners = sorted(box, key=lambda point: (point[0]))
    left = sorted_corners[0:2]
    right = sorted_corners[2:4]
    left_y = sorted(left, key=lambda point: (point[1]))
    right_y = sorted(right, key=lambda point: (point[1]))
    sorted_corners = [left_y[1], right_y[1], right_y[0], left_y[0]]

    z = (
        np.median(
            depth_image[
                int(center[1]) - config["center_size"] : int(center[1])
                + config["center_size"],
                int(center[0]) - config["center_size"] : int(center[0])
                + config["center_size"],
            ]
        )
    ) / 1000
    return center, sorted_corners, angle, z
