import json
import time

import numpy as np

from .search_functions import (
    add_nozzle_masks,
    create_outer_overflow_mask,
    create_overflow_mask,
    depth_measurement_zones,
    hole_detection,
    pepper_presence_from_depth,
    split_nozzle_mask,
)
from .search_functions import pepper_mask as pepper_mask_search
from .utils_functions import (
    add_exclusion_masks,
    create_seed_masks,
    filter_exclusion_mask,
)


# MARK: CONFIG
def config(
    nozzle_mask, section, pepper_type="big_pepper", reflective_nozzle=False
):  # small_prime, big_pepper
    # json_path = "/home/avena/system_perla/resources/pepper_vision/masks.json"

    # with open(json_path, "r") as file:
    #     data = json.load(file)

    data = {
        "bottom_left": [0.45587738870296174, 0.8900425868852393],
        "bottom_right": [-0.3252092125871874, 0.9456420929973568],
        "top_left": [-0.43164724377238617, 0.9020424917617252],
        "top_right": [0.4059873766996334, 0.9138786844874707],
    }

    match section:
        case "bottom_right":
            vectors = (data["bottom_right"][0], data["bottom_right"][1])
        case "bottom_left":
            vectors = (data["bottom_left"][0], data["bottom_left"][1])
        case "top_right":
            vectors = (data["top_right"][0], data["top_right"][1])
        case "top_left":
            vectors = (data["top_left"][0], data["top_left"][1])

    # TODO: form json
    # match section:
    #     case "top_left":
    #         vectors = (-0.4279989873279, 0.9037792135506836)
    #     case "top_right":
    #         vectors = (0.38107893052152586, 0.9245425077910534)
    #     case "bottom_right":
    #         vectors = (-0.3124139550973251, 0.9499460619742821)
    #     case "bottom_left":
    #         vectors = (0.4889248257678126, 0.8723259223179798)
    #

    image_center = (nozzle_mask.shape[1] // 2, nozzle_mask.shape[0] // 2)

    # DEFAULT
    config_dict = {}
    config_dict["nozzle_vectors"] = vectors
    config_dict["image_center"] = image_center
    config_dict["section"] = section
    config_dict["reflective_nozzle"] = reflective_nozzle

    # PEPPER MASK
    pepper_mask_dict = {}
    pepper_mask_dict["red_bottom_range"] = [[0, 140, 50], [30, 255, 255]]
    pepper_mask_dict["red_top_range"] = [[150, 140, 50], [180, 255, 255]]
    pepper_mask_dict["mask_de_noise_open_params"] = {"kernel": (5, 5), "iterations": 1}
    pepper_mask_dict["mask_de_noise_close_params"] = {
        "kernel": (10, 10),
        "iterations": 1,
    }
    pepper_mask_dict["min_mask_area"] = 100

    config_dict["pepper_mask_config"] = pepper_mask_dict

    # PEPPER_PRESENCE
    config_dict["pepper_presence_max_depth"] = 245

    # HOLE DETECTION
    hole_detection_dict = {}
    hole_detection_dict["gauss_blur_kernel_size"] = (3, 3)
    hole_detection_dict["clahe_params"] = {"clipLimit": 2.0, "tileGridSize": (8, 8)}
    hole_detection_dict["threshold_param"] = 0.5
    hole_detection_dict["open_on_l_params"] = {"kernel": (5, 5), "iterations": 1}
    hole_detection_dict["open_on_center_params"] = {"kernel": (5, 5), "iterations": 2}
    hole_detection_dict["open_on_center_raw_params"] = {
        "kernel": (2, 2),
        "iterations": 1,
    }
    hole_detection_dict["max_distance_from_center"] = 30
    hole_detection_dict["close_params"] = {"kernel": (5, 5), "iterations": 1}
    hole_detection_dict["min_hole_area"] = 30

    config_dict["hole_detection_config"] = hole_detection_dict

    # SEEDS REMOVAL
    seed_removal_dict = {}
    seed_removal_dict["hsv_range"] = [[10, 141, 136], [14, 237, 186]]
    seed_removal_dict["rgb_range"] = [[151, 104, 14], [209, 164, 87]]
    seed_removal_dict["hsv_close_1_params"] = {"kernel": (5, 5), "iterations": 1}
    seed_removal_dict["hsv_dilate_params"] = {"kernel": (3, 3), "iterations": 1}
    seed_removal_dict["hsv_open_params"] = {"kernel": (5, 5), "iterations": 1}
    seed_removal_dict["hsv_close_2_params"] = {"kernel": (2, 2), "iterations": 1}
    seed_removal_dict["rgb_dilate_params"] = {"kernel": (3, 3), "iterations": 1}
    seed_removal_dict["rgb_close_1_params"] = {"kernel": (7, 7), "iterations": 1}
    seed_removal_dict["rgb_close_2_params"] = {"kernel": (9, 9), "iterations": 1}
    seed_removal_dict["rgb_close_3_params"] = {"kernel": (2, 2), "iterations": 1}

    config_dict["seed_removal_config"] = seed_removal_dict

    # SPLITING MASKS
    # TODO: NOT USED RIGHT NOW - MAYBE IN FUTURE

    # DEPTH MEASURMENT ZONES
    depth_measurement_zones_dict = {}
    depth_measurement_zones_dict["line_width"] = 50
    depth_measurement_zones_dict["nozzle_mask_de_noise_open_params"] = {
        "kernel": (5, 5),
        "iterations": 1,
    }
    depth_measurement_zones_dict["outer_mask_dilate_params"] = {
        "kernel": (3, 3),
        "near_iterations": 1,
        "far_iterations": 14,
    }
    depth_measurement_zones_dict["nozzle_mask_extended_outer_dilate_params"] = {
        "kernel": (5, 5),
        "iterations": 4,
    }
    depth_measurement_zones_dict["nozzle_mask_extended_inner_dilate_params"] = {
        "kernel": (4, 4),
        "iterations": 2,
    }
    depth_measurement_zones_dict["inner_zone_erode_params"] = {
        "kernel": (3, 3),
        "iterations": 2,
    }

    config_dict["depth_measurement_zones_config"] = depth_measurement_zones_dict

    # OVERFLOW MASK
    overflow_mask_dict = {}
    overflow_mask_dict["kernel"] = (8, 8)
    overflow_mask_dict["erode_iter"] = 3
    overflow_mask_dict["dilate_iter"] = 4

    config_dict["overflow_mask_config"] = overflow_mask_dict

    # OUTER OVERFLOW MASK
    outer_overflow_mask_dict = {}
    outer_overflow_mask_dict["erode_params"] = {"kernel": (5, 5), "iterations": 1}

    config_dict["outer_overflow_mask_config"] = outer_overflow_mask_dict

    # MIN MASK SIZE
    min_mask_size_dict = {}
    min_mask_size_dict["inner_zone_mask"] = 50
    min_mask_size_dict["outer_zone_mask"] = 50
    min_mask_size_dict["overflow_mask"] = 50
    min_mask_size_dict["inner_zone_for_color"] = 50

    config_dict["min_mask_size_config"] = min_mask_size_dict

    # IF PEPPER IS FILLED
    if_pepper_is_filled_dict = {}
    if_pepper_is_filled_dict["max_outer_diff"] = 10
    if_pepper_is_filled_dict["min_inner_zone_non_zero_perc"] = 0.5
    if_pepper_is_filled_dict["min_inner_to_outer_diff"] = 0

    config_dict["if_pepper_is_filled_config"] = if_pepper_is_filled_dict

    # IF PEPPER MASK IS WHITE
    if_pepper_mask_is_white_dict = {}
    if_pepper_mask_is_white_dict["min_white_perc"] = 0.65
    if_pepper_mask_is_white_dict["hsv_white_range"] = [[0, 0, 150], [180, 75, 255]]

    config_dict["if_pepper_mask_is_white_config"] = if_pepper_mask_is_white_dict

    # OVERFLOW DETECTION
    overflow_detection_dict = {}
    overflow_detection_dict["inner_overflow_max_perc"] = 0.05
    overflow_detection_dict["outer_overflow_max_perc"] = 0.05

    config_dict["overflow_detection_config"] = overflow_detection_dict

    # SMALL PRIME
    if pepper_type == "small_prime":
        config_dict["pepper_mask_config"]["red_bottom_range"] = [
            [0, 100, 20],
            [30, 255, 255],
        ]
        config_dict["pepper_mask_config"]["red_top_range"] = [
            [150, 100, 20],
            [180, 255, 255],
        ]
        # config_dict["pepper_mask_config"]["mask_de_noise_open_params"] = {"kernel": (50,50), "iterations": 6}
        config_dict["hole_detection_config"]["threshold_param"] = 1
        config_dict["hole_detection_config"]["max_distance_from_center"] = 20

        config_dict["overflow_mask_config"]["kernel"] = (4, 4)
        config_dict["overflow_mask_config"]["erode_iter"] = 3
        config_dict["overflow_mask_config"]["dilate_iter"] = 7

    elif pepper_type == "big_pepper":
        pass

    return config_dict


# MARK: CREATE MASKS
def create_masks(rgb, depth, nozzle_mask, params):
    debug = {}

    pepper_mask, debug_mask_search = pepper_mask_search(rgb, nozzle_mask, params)

    pepper_presence, debug_presence = pepper_presence_from_depth(
        depth, pepper_mask, params
    )

    debug["pepper_mask"] = pepper_mask
    debug["pepper_presence"] = pepper_presence
    debug["depth_mean"] = debug_presence["depth_mask_mean"]
    debug["debug_mask_search"] = debug_mask_search

    if not pepper_presence:
        zero_mask = np.zeros_like(nozzle_mask)
        return (
            False,
            zero_mask,
            zero_mask,
            zero_mask,
            zero_mask,
            zero_mask,
            zero_mask,
            debug,
        )

    hole_mask, hole_mask_founded, debug_hole_detection = hole_detection(
        rgb, pepper_mask, params
    )
    # _, excluded_mask_from_depth, debug_exclude_from_depth = refine_hole_mask_with_depth(hole_mask, pepper_mask, depth)
    excluded_mask_seed, debug_seed = create_seed_masks(rgb, params)

    debug["excluded_mask_seed"] = excluded_mask_seed
    debug["debug_seed"] = debug_seed

    debug["hole_mask"] = hole_mask
    # debug["excluded_mask_from_depth"] = excluded_mask_from_depth
    debug["excluded_mask_from_depth"] = np.zeros_like(hole_mask)
    debug["debug_hole_detection"] = debug_hole_detection
    # debug["debug_exclude_from_depth"] = debug_exclude_from_depth

    if not hole_mask_founded:
        zero_mask = np.zeros_like(nozzle_mask)
        return (
            False,
            zero_mask,
            zero_mask,
            zero_mask,
            zero_mask,
            zero_mask,
            zero_mask,
            debug,
        )

    nozzle_in_pepper, nozzle_in_hole, nozzle_outside, debug_split_nozzle = (
        split_nozzle_mask(
            nozzle_mask,
            hole_mask,
            pepper_mask,
            params["nozzle_vectors"],
            params["section"],
        )
    )
    inner_zone_mask, outer_zone_mask, debug_zones = depth_measurement_zones(
        hole_mask, pepper_mask, nozzle_in_hole, nozzle_in_pepper, nozzle_mask, params
    )

    debug["debug_zones"] = debug_zones

    overflow_mask, debug_overflow = create_overflow_mask(pepper_mask, hole_mask, params)
    outer_overflow_mask, _ = create_outer_overflow_mask(pepper_mask, hole_mask, params)
    debug["outer_overflow_mask"] = outer_overflow_mask

    debug["overflow_mask"] = overflow_mask

    inner_zone_for_color, overflow_mask, debug_add_nozzles = add_nozzle_masks(
        inner_zone_mask, overflow_mask, nozzle_in_hole, nozzle_outside
    )

    # exclusion_mask = add_exclusion_masks([excluded_mask_from_depth, excluded_mask_seed])
    exclusion_mask = add_exclusion_masks([excluded_mask_seed])

    debug["nozzle_in_pepper"] = nozzle_in_pepper
    debug["nozzle_in_hole"] = nozzle_in_hole
    debug["nozzle_outside"] = nozzle_outside

    debug["debug_split_nozzle"] = debug_split_nozzle
    debug["debug_zones"] = debug_zones
    debug["debug_overflow"] = debug_overflow
    debug["debug_add_nozzles"] = debug_add_nozzles

    return (
        True,
        inner_zone_mask,
        outer_zone_mask,
        overflow_mask,
        outer_overflow_mask,
        inner_zone_for_color,
        exclusion_mask,
        debug,
    )


# MARK: EXCLUDE MASKS
def exclude_masks(masks, exclusion_mask):
    ret_masks = []

    for mask in masks:
        ret_masks.append(filter_exclusion_mask(mask, exclusion_mask))

    return ret_masks
