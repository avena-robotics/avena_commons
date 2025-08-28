import cv2
import numpy as np


def create_box_depth_mask(depth_image, config):  # MARK: CREATE BOX DEPTH MASK
    """
    Creates a depth mask for box detection.

    :param depth_image: Depth image from the camera
    :param config: Dictionary containing mask configuration parameters:
                    - center_size: Size of the center region to calculate median depth
                    - depth_range: Range of acceptable depth values
                    - depth_bias: Bias adjustment for depth calculation
    :return: Binary mask based on depth thresholds
    """
    center_of_the_image = config["center_point"]
    center_size = config["center_size"]

    depth_image_cropped = depth_image[
        center_of_the_image[1] - center_size : center_of_the_image[1] + center_size,
        center_of_the_image[0] - center_size : center_of_the_image[0] + center_size,
    ]

    depth_image_cropped_0 = depth_image_cropped[depth_image_cropped == 0].flatten()
    depth_image_cropped_non_0 = depth_image_cropped[depth_image_cropped != 0].flatten()

    non_zero_percentage = len(depth_image_cropped_non_0) / (
        len(depth_image_cropped_0) + len(depth_image_cropped_non_0)
    )

    if non_zero_percentage < config["min_non_zero_percentage"]:
        return None

    median_depth = np.median(depth_image_cropped_non_0)

    depth_range = [
        int(median_depth - config["depth_range"] - config["depth_bias"]),
        int(median_depth - config["depth_bias"]),
    ]

    return cv2.inRange(depth_image, depth_range[0], depth_range[1])
