import cv2
import numpy as np


def blend(
    image1: np.ndarray, image2: np.ndarray, merge_image_weight: float
) -> np.ndarray:
    blended_image = cv2.addWeighted(
        image1,
        merge_image_weight,
        image2,
        1 - merge_image_weight,
        0,
    )
    return blended_image
