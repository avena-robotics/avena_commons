import cv2


def find_contours(mask):  # MARK: FIND CONTOURS
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contours
