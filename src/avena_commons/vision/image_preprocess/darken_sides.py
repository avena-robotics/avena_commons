import numpy as np


def darken_sides(
    image: np.ndarray,
    *,
    top: float = 0.0,
    bottom: float = 0.0,
    left: float = 0.0,
    right: float = 0.0,
    darkness_factor: float = 0.0,  # domyslnie pelne zaciemnienie
) -> np.ndarray:
    """
    Zaciemnia wybrane obszary obrazu z każdej strony.

    Args:
        image: Obraz wejściowy (BGR lub grayscale)
        top: Procent wysokości do zaciemnienia od góry (0.0-1.0)
        bottom: Procent wysokości do zaciemnienia od dołu (0.0-1.0)
        left: Procent szerokości do zaciemnienia z lewej (0.0-1.0)
        right: Procent szerokości do zaciemnienia z prawej (0.0-1.0)
        darkness_factor: Współczynnik zaciemnienia (0.0 = całkowicie czarne, 1.0 = bez zmian)

    Returns:
        Obraz z zaciemnionymi obszarami

    Example:
        # Zaciemnij ćwiartki z lewej i prawej
        result = darken_sides(image, left=0.25, right=0.25, darkness_factor=0.2)

        # Zaciemnij górne 10% i dolne 15%
        result = darken_sides(image, top=0.1, bottom=0.15, darkness_factor=0.3)
    """
    if not (0.0 <= darkness_factor <= 1.0):
        raise ValueError("darkness_factor must be between 0.0 and 1.0")

    for param, name in [
        (top, "top"),
        (bottom, "bottom"),
        (left, "left"),
        (right, "right"),
    ]:
        if not (0.0 <= param <= 1.0):
            raise ValueError(f"{name} must be between 0.0 and 1.0")

    result = image.copy()
    height, width = image.shape[:2]

    # Oblicz piksele do zaciemnienia
    top_pixels = int(height * top)
    bottom_pixels = int(height * bottom)
    left_pixels = int(width * left)
    right_pixels = int(width * right)

    # Zaciemnij górę
    if top_pixels > 0:
        result[:top_pixels, :] = (result[:top_pixels, :] * darkness_factor).astype(
            image.dtype
        )

    # Zaciemnij dół
    if bottom_pixels > 0:
        result[height - bottom_pixels :, :] = (
            result[height - bottom_pixels :, :] * darkness_factor
        ).astype(image.dtype)

    # Zaciemnij lewą stronę
    if left_pixels > 0:
        result[:, :left_pixels] = (result[:, :left_pixels] * darkness_factor).astype(
            image.dtype
        )

    # Zaciemnij prawą stronę
    if right_pixels > 0:
        result[:, width - right_pixels :] = (
            result[:, width - right_pixels :] * darkness_factor
        ).astype(image.dtype)

    return result
