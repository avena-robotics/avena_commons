import cv2
import numpy as np


def rectangle_from_contours(cnts):
    combined_points = np.vstack([cnt.reshape(-1, 2) for cnt in cnts])
    rect = cv2.minAreaRect(combined_points)
    box = cv2.boxPoints(rect).tolist()
    return rect, box
