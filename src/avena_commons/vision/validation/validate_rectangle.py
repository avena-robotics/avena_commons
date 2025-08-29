import math


def validate_rectangle(rect, box, image, config):  # MARK: VALIDATE RECT
    if rect[1][0] > rect[1][1]:
        long = rect[1][0]
        short = rect[1][1]
    else:
        long = rect[1][1]
        short = rect[1][0]

    # 0. check if box is not too small or too big
    if long < 800 or long > 1050 or short < 500 or short > 800:
        return False

    ratio = long / short
    if ratio > config["box_ratio_range"][1] or ratio < config["box_ratio_range"][0]:
        return False

    # 2. check distance between center of the rect and assumed center of the box
    center_rect = rect[0]
    center_box = config["center_point"]
    distance = math.sqrt(
        (center_rect[0] - center_box[0]) ** 2 + (center_rect[1] - center_box[1]) ** 2
    )
    if distance > config["max_distance"]:
        return (False,)

    # 3. check box angle
    angle = rect[2]
    if angle == 45:
        return False
    if angle < 45 and angle > config["max_angle"]:
        return False
    if angle > 45 and angle < 90 - config["max_angle"]:
        return False

    # 4. check if box corner is not near the edge of the image
    for corner in box:
        if (
            corner[0] < 0
            or corner[0] > image.shape[1]
            or corner[1] < 0
            or corner[1] > image.shape[0]
        ):
            return False

    return True
