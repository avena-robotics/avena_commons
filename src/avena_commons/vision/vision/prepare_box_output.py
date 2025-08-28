import numpy as np


def prepare_box_output(rect, box, depth_image, config):
    center = rect[0]
    angle = rect[2]

    sorted_corners = sorted(box, key=lambda point: (point[0]))
    left = sorted_corners[0:2]
    right = sorted_corners[2:4]
    left_y = sorted(left, key=lambda point: (point[1]))
    right_y = sorted(right, key=lambda point: (point[1]))
    sorted_corners = [left_y[1], right_y[1], right_y[0], left_y[0]]

    z = (
        np.median(
            depth_image[
                int(center[1]) - config["center_size"] : int(center[1])
                + config["center_size"],
                int(center[0]) - config["center_size"] : int(center[0])
                + config["center_size"],
            ]
        )
    ) / 1000
    return center, sorted_corners, angle, z
