import numpy as np

from avena_commons.vision.vision.propagate import propagate


def propagate_by_shape(depth, mask, r_wide=2.0, r_tall=0.5):
    """Propaguje wartości głębi na podstawie kształtu obszaru dziury.

    Funkcja analizuje kształt obszaru dziury (stosunek szerokości do wysokości)
    i wybiera odpowiedni kierunek propagacji dla optymalnego wypełnienia.
    Optymalizowana wersja z wczesnym sprawdzeniem dziur i efektywnym obliczaniem boundingu box.

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
    # Wczesne sprawdzenie czy są w ogóle dziury do wypełnienia
    if not np.any(mask == 255):
        return depth.copy()

    # Efektywne obliczanie bounding box bez np.where
    # Znajdź rzędy i kolumny zawierające dziury
    rows_with_holes = np.any(mask == 255, axis=1)
    cols_with_holes = np.any(mask == 255, axis=0)

    # Jeśli nie ma dziur, zwróć kopię
    if not np.any(rows_with_holes) or not np.any(cols_with_holes):
        return depth.copy()

    # Znajdź granice bounding box
    y_indices = np.where(rows_with_holes)[0]
    x_indices = np.where(cols_with_holes)[0]

    y_min, y_max = y_indices[0], y_indices[-1]
    x_min, x_max = x_indices[0], x_indices[-1]

    h = y_max - y_min + 1
    w = x_max - x_min + 1
    ratio = w / h

    if ratio > r_wide:
        direction = "horizontal"
    elif ratio < r_tall:
        direction = "vertical"
    else:
        direction = "square"

    return propagate(depth, mask, direction)
