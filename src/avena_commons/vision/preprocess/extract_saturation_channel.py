import cv2


def extract_saturation_channel(image):
    """Ekstrahuje kanał nasycenia (S) z obrazu HSV i inwertuje go.

    Args:
        image: Obraz w formacie BGR

    Returns:
        numpy.ndarray: Kanał S po inwersji (255 - S)
    """
    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation_channel = hsv_image[:, :, 1]
    return 255 - saturation_channel
