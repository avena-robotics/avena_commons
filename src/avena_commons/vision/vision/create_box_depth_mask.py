import cv2
import numpy as np


def create_box_depth_mask(depth_image, config):  # MARK: CREATE BOX DEPTH MASK
    """Tworzy maskę głębi do detekcji pudełka na podstawie wartości głębi.

    Funkcja oblicza medianę głębi w centralnym obszarze obrazu i tworzy maskę
    dla pikseli znajdujących się w określonym zakresie głębi względem mediany.

    Args:
        depth_image: Obraz głębi z kamery (wartości w mm)
        config: Słownik zawierający parametry konfiguracji maski:
            - center_point: Punkt centralny (x, y) do obliczenia mediany
            - center_size: Rozmiar centralnego obszaru do obliczenia mediany
            - depth_range: Zakres akceptowalnych wartości głębi
            - depth_bias: Przesunięcie dla obliczenia głębi
            - min_non_zero_percentage: Minimalny procent niezerowych pikseli

    Returns:
        np.ndarray lub None: Binarna maska głębi lub None jeśli za mało danych

    Example:
        >>> config = {
        ...     "center_point": [320, 240],
        ...     "center_size": 50,
        ...     "depth_range": 100,
        ...     "depth_bias": 50,
        ...     "min_non_zero_percentage": 0.1
        ... }
        >>> mask = create_box_depth_mask(depth_image, config)
    """
    center_of_the_image = config["center_point"]
    center_size = config["center_size"]

    depth_image_cropped = depth_image[
        center_of_the_image[1] - center_size : center_of_the_image[1] + center_size,
        center_of_the_image[0] - center_size : center_of_the_image[0] + center_size,
    ]

    depth_image_cropped_0 = depth_image_cropped[depth_image_cropped == 0].flatten()
    depth_image_cropped_non_0 = depth_image_cropped[depth_image_cropped != 0].flatten()

    non_zero_percentage = len(depth_image_cropped_non_0) / (
        len(depth_image_cropped_0) + len(depth_image_cropped_non_0)
    )

    if non_zero_percentage < config["min_non_zero_percentage"]:
        return None

    median_depth = np.median(depth_image_cropped_non_0)

    depth_range = [
        int(median_depth - config["depth_range"] - config["depth_bias"]),
        int(median_depth - config["depth_bias"]),
    ]

    return cv2.inRange(depth_image, depth_range[0], depth_range[1])
