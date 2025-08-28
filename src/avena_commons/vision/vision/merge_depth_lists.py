import numpy as np


def merge_depth_lists(original_depth, painted_layers, masks=None):
    merged = original_depth.astype(np.float32).copy()

    # normalise inputs to lists so we can loop uniformly
    if not isinstance(painted_layers, (list, tuple)):
        painted_layers = [painted_layers]

    if masks is None:
        masks = [None] * len(painted_layers)
    elif not isinstance(masks, (list, tuple)):
        masks = [masks] * len(painted_layers)

    if len(masks) != len(painted_layers):
        raise ValueError(
            "`masks` must be None, a single array, "
            "or a list the same length as `painted_layers`"
        )

    # ------------------------------------------------------------
    for layer, mask in zip(painted_layers, masks):
        if mask is None:
            sel = layer != 0  # write wherever layer has data
        else:
            sel = mask == 255  # obey supplied mask

        merged[sel] = layer[sel]

    return merged
