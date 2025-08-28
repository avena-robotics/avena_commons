from copy import deepcopy

import cv2
import numpy as np


def prepare_image_output(image, cnts, rect, box):  # MARK: PREPARE IMAGE OUTPUT
    image_copy = deepcopy(image)
    for cnt in cnts:
        cv2.drawContours(image_copy, [cnt], -1, (0, 255, 0), 2)

    for point in box:
        cv2.circle(image_copy, (int(point[0]), int(point[1])), 10, (0, 0, 255), -1)

    cv2.circle(image_copy, (int(rect[0][0]), int(rect[0][1])), 10, (0, 0, 255), -1)
    box_int = np.intp(box)
    cv2.drawContours(image_copy, [box_int], -1, (0, 255, 0), 2)

    return image_copy
