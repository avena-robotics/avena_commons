import cv2


def create_box_color_mask(color_image, config):  # MARK: CREATE BOX COLOR MASK
    """
    Creates a color mask for box detection using HSV color space.

    :param color_image: BGR color image
    :param config: Dictionary containing HSV threshold parameters:
                    - hsv_h_min/max: Hue range
                    - hsv_s_min/max: Saturation range
                    - hsv_v_min/max: Value range
    :return: Binary mask based on HSV thresholds
    """
    hsv_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv_image)

    mask_h = cv2.inRange(h, config["hsv_h_min"], config["hsv_h_max"])
    mask_s = cv2.inRange(s, config["hsv_s_min"], config["hsv_s_max"])
    mask_v = cv2.inRange(v, config["hsv_v_min"], config["hsv_v_max"])

    mask = mask_h & mask_s & mask_v
    return mask
