import numpy as np

from avena_commons.vision.vision.propagate import propagate


def propagate_by_shape(depth, mask, r_wide=2.0, r_tall=0.5):
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
