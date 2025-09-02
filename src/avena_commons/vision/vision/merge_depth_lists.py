import numpy as np


def merge_depth_lists(original_depth, painted_layers, masks=None):
    """Łączy listę warstw głębi z oryginalnym obrazem głębi.

    Funkcja łączy wiele warstw uzupełnionej głębi z oryginalnym obrazem głębi,
    używając opcjonalnych masek do określenia obszarów do zastąpienia.

    Args:
        original_depth: Oryginalny obraz głębi
        painted_layers: Pojedyncza warstwa lub lista warstw uzupełnionej głębi
        masks: Opcjonalna maska lub lista masek określających obszary do zastąpienia

    Returns:
        np.ndarray: Połączony obraz głębi z uzupełnionymi obszarami

    Raises:
        ValueError: Jeśli długość masek nie odpowiada długości warstw

    Example:
        >>> original = np.array([[100, 0, 200], [0, 0, 0], [300, 0, 400]])
        >>> layers = [np.array([[0, 150, 0], [0, 0, 0], [0, 0, 0]])]
        >>> masks = [np.array([[0, 255, 0], [0, 0, 0], [0, 0, 0]])]
        >>> merged = merge_depth_lists(original, layers, masks)
    """
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
