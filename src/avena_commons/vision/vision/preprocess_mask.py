import cv2


def preprocess_mask(mask, config):  # MARK: PREPROCESS MASK
    """Przetwarza maskę binarną używając operacji morfologicznych.

    Funkcja wykonuje serię operacji na masce: rozmycie Gaussa, progowanie OTSU,
    otwarcie morfologiczne i zamknięcie morfologiczne w celu wygładzenia i oczyszczenia maski.

    Args:
        mask: Binarna maska wejściowa
        config: Słownik zawierający parametry przetwarzania:
            - blur_size: Rozmiar jądra rozmycia Gaussa
            - opened_size: Rozmiar jądra dla operacji otwarcia [width, height]
            - opened_iterations: Liczba iteracji operacji otwarcia
            - closed_size: Rozmiar jądra dla operacji zamknięcia [width, height]
            - closed_iterations: Liczba iteracji operacji zamknięcia
            - opened_kernel_type: Typ jądra dla otwarcia (np. cv2.MORPH_RECT)
            - closed_kernel_type: Typ jądra dla zamknięcia (np. cv2.MORPH_RECT)

    Returns:
        np.ndarray: Przetworzona maska binarna

    Example:
        >>> config = {
        ...     "blur_size": 5,
        ...     "opened_size": [3, 3],
        ...     "opened_iterations": 1,
        ...     "closed_size": [5, 5],
        ...     "closed_iterations": 2,
        ...     "opened_kernel_type": cv2.MORPH_RECT,
        ...     "closed_kernel_type": cv2.MORPH_RECT
        ... }
        >>> processed_mask = preprocess_mask(mask, config)
    """
    blur_size = config["blur_size"]
    opened_size = config["opened_size"]
    opened_iterations = config["opened_iterations"]
    closed_size = config["closed_size"]
    closed_iterations = config["closed_iterations"]
    opened_kernel_type = config["opened_kernel_type"]
    closed_kernel_type = config["closed_kernel_type"]

    if blur_size % 2 == 0:
        blur_size += 1

    blurred = cv2.GaussianBlur(mask, (blur_size, blur_size), 0)
    _, mask_smoothed = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    kernel_opened = cv2.getStructuringElement(
        opened_kernel_type, (opened_size[0], opened_size[1])
    )
    mask_opened = cv2.morphologyEx(
        mask_smoothed, cv2.MORPH_OPEN, kernel_opened, iterations=opened_iterations
    )
    kernel_closed = cv2.getStructuringElement(
        closed_kernel_type, (closed_size[0], closed_size[1])
    )
    mask_closed = cv2.morphologyEx(
        mask_opened, cv2.MORPH_CLOSE, kernel_closed, iterations=closed_iterations
    )

    return mask_closed
