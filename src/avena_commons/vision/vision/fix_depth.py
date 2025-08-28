import cv2
import numpy as np

from avena_commons.vision.vision.merge_depth_lists import merge_depth_lists
from avena_commons.vision.vision.propagate_by_shape import propagate_by_shape


def fix_depth(depth_image, config, debug: bool = False):
    """
    Example config:
    fix_depth_config = {
        "closing_mask": {
            "kernel_size": 10,
            "iterations": 2,
        },
        "zero_mask": {
            "kernel_size": 10,
            "iterations": 2,
        },
        "r_wide": 2.0,
        "r_tall": 0.5,
        "final_closing_mask": {
            "kernel_size": 10,
            "iterations": 2,
        },
    }
    """

    debug_dict = {}

    # STEP 1: CLOSE DEPTH IMAGE
    kernel = np.ones(
        (config["closing_mask"]["kernel_size"], config["closing_mask"]["kernel_size"]),
        np.uint8,
    )
    closed_depth_image = cv2.morphologyEx(
        depth_image,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=config["closing_mask"]["iterations"],
    )

    if debug:
        debug_dict["closed_depth_image"] = closed_depth_image

    # STEP 2: CREATE ZERO DEPTH MASK
    zero_depth_mask = closed_depth_image == 0
    zero_depth_mask = zero_depth_mask.astype(np.uint8) * 255
    kernel = np.ones(
        (config["zero_mask"]["kernel_size"], config["zero_mask"]["kernel_size"]),
        np.uint8,
    )
    closed_zero_mask = cv2.morphologyEx(
        zero_depth_mask,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=config["zero_mask"]["iterations"],
    )

    if debug:
        debug_dict["zero_depth_mask"] = zero_depth_mask
        debug_dict["closed_zero_mask"] = closed_zero_mask

    # STEP 3: SPLIT ZERO DEPTH NASJ
    zero_depth_mask_list = []
    n, labels = cv2.connectedComponents(closed_zero_mask, connectivity=8)
    for i in range(1, n):
        mask = np.zeros_like(closed_zero_mask)
        mask[labels == i] = 255
        zero_depth_mask_list.append(mask)

    if debug:
        debug_dict["zero_depth_mask_list"] = zero_depth_mask_list

    # STEP 4: PROPAGATE ZERO DEPTH MASK
    inpainted_depth_list = []
    for mask in zero_depth_mask_list:
        inpainted_depth = propagate_by_shape(
            closed_depth_image, mask, config["r_wide"], config["r_tall"]
        )
        inpainted_depth_list.append(inpainted_depth)
    if debug:
        debug_dict["inpainted_depth_list"] = inpainted_depth_list

    # STEP 5: MERGE INPAINTED DEPTH
    depth_merged = merge_depth_lists(
        closed_depth_image, inpainted_depth_list, zero_depth_mask_list
    )
    kernel = np.ones(
        (
            config["final_closing_mask"]["kernel_size"],
            config["final_closing_mask"]["kernel_size"],
        ),
        np.uint8,
    )
    depth_merged_closed = cv2.morphologyEx(
        depth_merged,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=config["final_closing_mask"]["iterations"],
    )

    return depth_merged_closed, debug_dict
