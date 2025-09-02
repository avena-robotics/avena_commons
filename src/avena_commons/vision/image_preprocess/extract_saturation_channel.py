import cv2


def extract_saturation_channel(image):
    """Ekstrahuje kanał nasycenia (S) z obrazu HSV i inwertuje go.

    Funkcja konwertuje obraz z przestrzeni barw BGR na HSV, ekstrahuje
    kanał nasycenia (S) i inwertuje go (255 - S). Inwersja kanału
    nasycenia jest przydatna w detekcji obiektów o niskim nasyceniu
    kolorów, takich jak białe lub szare elementy.

    Args:
        image: Obraz wejściowy w formacie BGR (numpy.ndarray)

    Returns:
        numpy.ndarray: Kanał nasycenia po inwersji (255 - S) jako obraz w skali szarości

    Example:
        >>> bgr_image = cv2.imread('colorful_image.jpg')
        >>> saturation_inverted = extract_saturation_channel(bgr_image)
        >>> cv2.imshow('Saturation Inverted', saturation_inverted)
    """
    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation_channel = hsv_image[:, :, 1]
    return 255 - saturation_channel
