import numpy as np

from .utils_functions import get_white_percentage_in_mask


# MARK: DEPTH MEASURMENT IN MASK
def depth_measurement_in_mask(depth, mask):
    debug = {}

    depth_flat = depth.flatten()
    mask_flat = mask.flatten()

    mask_depth_vals = depth_flat[mask_flat == 255]
    non_zero_mask_depth_vals = mask_depth_vals[mask_depth_vals != 0]

    if non_zero_mask_depth_vals.size == 0:
        return 0, 0, debug

    debug["mask_depth_vals"] = non_zero_mask_depth_vals

    depth_median = np.median(non_zero_mask_depth_vals)
    non_zero_percentage = len(non_zero_mask_depth_vals) / len(mask_depth_vals)

    return depth_median, non_zero_percentage, debug


# MARK: IS PEPPER FILLED


def if_pepper_is_filled(
    inner_zone_median,
    inner_zone_non_zero_perc,
    outer_zone_median,
    outer_zone_median_start,
    params,
):
    debug = {}

    func_params = params["if_pepper_is_filled_config"]

    debug["diff"] = (
        inner_zone_median - (outer_zone_median_start + outer_zone_median) / 2
    )

    if (
        abs(outer_zone_median - outer_zone_median_start)
        >= func_params["max_outer_diff"]
    ):  # TODO: param
        # print("becouse diff outer", outer_zone_median - outer_zone_median_start)
        return True, debug

    if (
        inner_zone_non_zero_perc <= func_params["min_inner_zone_non_zero_perc"]
    ):  # TODO: param
        return False, debug

    if (
        inner_zone_median - (outer_zone_median_start + outer_zone_median) / 2
        <= func_params["min_inner_to_outer_diff"]
    ):  # TODO: param
        # print("becouse diff", inner_zone_median - outer_zone_median)
        return True, debug

    return False, debug


# MARK: IS MASK WHITE


def if_pepper_mask_is_white(rgb, mask, params):
    debug = {}

    hsv_range = params["if_pepper_mask_is_white_config"]["hsv_white_range"]
    min_white_perc = params["if_pepper_mask_is_white_config"]["min_white_perc"]

    white_percentage, _ = get_white_percentage_in_mask(rgb, mask, hsv_range)
    # print(white_percentage)
    debug["mask_in_range_perc"] = white_percentage

    if white_percentage >= min_white_perc:
        return True, debug
    else:
        return False, debug  # TODO: param


# MARK: OVERFLOW DETECTION


def overflow_detection(rgb, overflow_mask, hsv_range, max_value, bias=0):
    debug = {}

    white_percentage, debug_mask = get_white_percentage_in_mask(
        rgb, overflow_mask, hsv_range
    )
    debug["hsv"] = debug_mask["hsv"]
    debug["mask_in_range"] = debug_mask["mask_in_range"]
    debug["mask_perc"] = white_percentage

    # TODO: Add analysis of vicinity of pepper mask

    if white_percentage >= (0.05 + bias):
        return True, debug  # TODO: param
    return False, debug
