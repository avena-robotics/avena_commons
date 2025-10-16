import cv2


def find_contours(mask):  # MARK: FIND CONTOURS
    """Znajduje kontury w binarnym obrazie maski.

    Funkcja wykorzystuje algorytm findContours z OpenCV do wykrycia zewnętrznych
    konturów w obrazie binarnym.

    Args:
        mask: Binarny obraz maski (0 lub 255)

    Returns:
        list: Lista konturów znalezionych w obrazie

    Example:
        >>> mask = cv2.inRange(image, lower, upper)
        >>> contours = find_contours(mask)
        >>> for cnt in contours:
        ...     cv2.drawContours(image, [cnt], -1, (0, 255, 0), 2)
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contours
