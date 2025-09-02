import numpy as np


def merge_masks(masks: list[np.ndarray]):  # MARK: MERGE MASKS
    """Łączy wiele binarnych masek używając operacji bitowej AND.

    Funkcja wykonuje operację bitową AND na wszystkich maskach w liście,
    zwracając maskę zawierającą tylko piksele, które są aktywne we wszystkich maskach.

    Args:
        masks: Lista binarnych masek do połączenia

    Returns:
        np.ndarray: Pojedyncza połączona maska binarna

    Example:
        >>> mask1 = np.array([[255, 0], [255, 0]])
        >>> mask2 = np.array([[255, 255], [0, 0]])
        >>> combined = merge_masks([mask1, mask2])
        >>> print(combined)  # [[255, 0], [0, 0]]
    """
    return np.bitwise_and.reduce(masks)
