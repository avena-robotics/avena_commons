import numpy as np


def merge_masks(masks: list[np.ndarray]):  # MARK: MERGE MASKS
    """
    Combines multiple binary masks using bitwise AND operation.

    :param masks: List of binary masks to be combined
    :return: Single combined binary mask
    """
    return np.bitwise_and.reduce(masks)
