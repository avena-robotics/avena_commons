import numpy as np

from avena_commons.vision.vision.propagate import propagate


def propagate_by_shape(depth, mask, r_wide=2.0, r_tall=0.5):
    """Propaguje wartości głębi na podstawie kształtu obszaru dziury.

    Funkcja analizuje kształt obszaru dziury (stosunek szerokości do wysokości)
    i wybiera odpowiedni kierunek propagacji dla optymalnego wypełnienia.

    Args:
        depth: Obraz głębi z dziurami do wypełnienia
        mask: Maska binarna określająca obszary dziur (255 = dziura)
        r_wide: Próg dla obszarów szerokich (domyślnie 2.0)
        r_tall: Próg dla obszarów wysokich (domyślnie 0.5)

    Returns:
        np.ndarray: Obraz głębi z wypełnionymi dziurami

    Example:
        >>> depth = np.array([[100, 0, 200], [0, 0, 0], [300, 0, 400]])
        >>> mask = np.array([[0, 255, 0], [255, 255, 255], [0, 255, 0]])
        >>> filled = propagate_by_shape(depth, mask, r_wide=2.0, r_tall=0.5)
    """
    ys, xs = np.where(mask)

    h = ys.max() - ys.min() + 1
    w = xs.max() - xs.min() + 1
    ratio = w / h

    if ratio > r_wide:
        direction = "horizontal"
    elif ratio < r_tall:
        direction = "vertical"
    else:
        direction = "square"

    return propagate(depth, mask, direction)
