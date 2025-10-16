import cv2
import numpy as np
from math import atan2, degrees

from .utils_functions import (
    pepper_mask_refinement,
    convex_hull_mask,
    get_mask_edge_area,
    convex_hull_joined_masks,
    nozzle_in_pepper_mask,
)

# MARK: PEPPER PRESENCE

from .catchtime import Catchtime


def pepper_presence(rgb, nozzle_mask, section="top_left"):
    # TODO: podzielić na dwie funkcje: pepper_presence i pepper_mask
    debug = {}

    hsv_color = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV)
    lower_range_bottom = np.array([0, 140, 50])  # TODO: param
    upper_range_bottom = np.array([30, 255, 255])  # TODO: param

    lower_range_top = np.array([150, 140, 50])  # TODO: param
    upper_range_top = np.array([180, 255, 255])  # TODO: param

    mask_bottom = cv2.inRange(hsv_color, lower_range_bottom, upper_range_bottom)
    mask_top = cv2.inRange(hsv_color, lower_range_top, upper_range_top)
    mask = cv2.bitwise_or(mask_bottom, mask_top)

    debug["mask"] = mask
    mask, refinement_debug = pepper_mask_refinement(mask, nozzle_mask)
    debug["refinement_debug"] = refinement_debug

    error_count = 0

    d = 3  # TODO: param

    match section:
        case "top_left":
            messurment_points = [(75, 140), (100, 140), (50, 90)]  # TODO: param
        case "top_right":
            messurment_points = [(60, 100), (120, 110), (60, 80)]  # TODO: param
        case "bottom_left":
            messurment_points = [(75, 140), (100, 140), (100, 90)]  # TODO: param
        case "bottom_right":
            messurment_points = [(60, 60), (100, 100), (100, 60)]  # TODO: param
        case _:
            messurment_points = [(75, 140), (100, 140), (100, 90)]  # TODO: param

    debug["messurment_points"] = messurment_points

    for point in messurment_points:
        point_crop = mask[point[0] - d : point[0] + d, point[1] - d : point[1] + d]

        mask_sum = (np.sum(point_crop[point_crop > 0])) / 255

        if mask_sum < 10:
            error_count += 1  # TODO: param

    if error_count > 1:
        pepper_presence = False
        mask = None
        nozzle_in_pepper_mask = None
    else:
        pepper_presence = True

    return pepper_presence, mask, debug


# MARK: PEPPER MASK
def pepper_mask(rgb, nozzle_mask, params):
    debug = {}

    pepper_mask_config = params["pepper_mask_config"]
    red_bottom_range = pepper_mask_config["red_bottom_range"]
    red_top_range = pepper_mask_config["red_top_range"]

    # 🔍 DEBUG: Informacje o tworzeniu pepper mask
    print(f"🌶️ PEPPER_MASK DEBUG:")
    print(f"   RGB shape: {rgb.shape}")
    print(f"   Red bottom range: {red_bottom_range}")
    print(f"   Red top range: {red_top_range}")

    hsv_color = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV)

    # Sprawdź statystyki HSV
    hsv_mean = np.mean(hsv_color, axis=(0, 1))
    hsv_min = np.min(hsv_color, axis=(0, 1))
    hsv_max = np.max(hsv_color, axis=(0, 1))
    print(f"   HSV stats - Mean: {hsv_mean}, Min: {hsv_min}, Max: {hsv_max}")

    lower_range_bottom = np.array(red_bottom_range[0])
    upper_range_bottom = np.array(red_bottom_range[1])

    lower_range_top = np.array(red_top_range[0])
    upper_range_top = np.array(red_top_range[1])

    mask_bottom = cv2.inRange(hsv_color, lower_range_bottom, upper_range_bottom)
    mask_top = cv2.inRange(hsv_color, lower_range_top, upper_range_top)

    print(f"   Bottom mask pixels: {np.count_nonzero(mask_bottom)}")
    print(f"   Top mask pixels: {np.count_nonzero(mask_top)}")

    mask = cv2.bitwise_or(mask_bottom, mask_top)

    print(f"   Combined raw mask pixels: {np.count_nonzero(mask)}")

    debug["mask"] = mask
    mask, refinement_debug = pepper_mask_refinement(mask, pepper_mask_config)
    debug["refinement_debug"] = refinement_debug

    print(f"   After refinement mask pixels: {np.count_nonzero(mask)}")
    print(f"🌶️ PEPPER_MASK DEBUG END\n")

    if params["reflective_nozzle"] == True:
        print(
            f"🔧 PEPPER_MASK: reflective_nozzle=True, wywołuję nozzle_in_pepper_mask dla sekcji '{params['section']}'"
        )
        nozzle_in_pepper_mask_var = nozzle_in_pepper_mask(
            rgb, nozzle_mask, mask, params["section"]
        )
        if (
            nozzle_in_pepper_mask_var is not None
            and np.max(nozzle_in_pepper_mask_var) > 0
        ):
            print(
                f"🔧 PEPPER_MASK: nozzle_in_pepper_mask zwrócił maskę z {np.count_nonzero(nozzle_in_pepper_mask_var)} pikselami"
            )
            debug["nozzle_in_pepper_mask"] = nozzle_in_pepper_mask_var
            # print(mask.dtype, mask.shape, nozzle_in_pepper_mask_var.dtype, nozzle_in_pepper_mask_var.shape)
            nozzle_outside_pepper = nozzle_mask - cv2.bitwise_and(
                nozzle_mask, nozzle_in_pepper_mask_var
            )
            mask = mask - cv2.bitwise_and(mask, nozzle_outside_pepper)
        else:
            print(f"🔧 PEPPER_MASK: nozzle_in_pepper_mask zwrócił pustą maskę")

    return mask, debug


# MARK: PEPPER PRESENCE FROM DEPTH
def pepper_presence_from_depth(depth, pepper_mask, params):
    debug = {}

    max_depth = params["pepper_presence_max_depth"]

    if pepper_mask is None or np.max(pepper_mask) == 0:
        debug["depth_mask_mean"] = 0
        return False, debug

    depth_mask = depth[pepper_mask == 255]
    depth_mask = depth_mask[depth_mask > 0]

    if len(depth_mask) == 0:
        debug["depth_mask_mean"] = 0
        return False, debug

    # max_pepper_depth
    depth_mask_mean = np.mean(depth_mask)
    debug["depth_mask_mean"] = depth_mask_mean
    return depth_mask_mean < max_depth, debug


# MARK: HOLE DETECTING
def hole_detection(rgb, pepper_mask, params):
    # TODO: add hull and remove nozzle mask
    # TODO: dodoawanie kilku mask obok siebie

    # TODO: ADD SPLITED MASKS

    debug = {}

    hole_detection_config = params["hole_detection_config"]
    gauss_blur_kernel_size = hole_detection_config["gauss_blur_kernel_size"]
    clahe_params = hole_detection_config["clahe_params"]
    threshold_param = hole_detection_config["threshold_param"]
    open_on_l_params = hole_detection_config["open_on_l_params"]
    open_on_center_params = hole_detection_config["open_on_center_params"]
    open_on_center_raw_params = hole_detection_config["open_on_center_raw_params"]
    max_distance_from_center = hole_detection_config["max_distance_from_center"]
    close_params = hole_detection_config["close_params"]
    min_hole_area = hole_detection_config["min_hole_area"]

    image_center = params["image_center"]

    # DATA PREPARATION
    rgb_on_pepper = cv2.bitwise_and(rgb, rgb, mask=pepper_mask)

    lab_image = cv2.cvtColor(rgb_on_pepper, cv2.COLOR_BGR2HLS)

    _, l, _ = cv2.split(lab_image)
    debug["l"] = l

    # PREPROCESING
    l_gauss = cv2.GaussianBlur(l, gauss_blur_kernel_size, 0)  # TODO: param
    l_equHist = cv2.equalizeHist(l_gauss)
    clahe = cv2.createCLAHE(
        clipLimit=clahe_params["clipLimit"], tileGridSize=clahe_params["tileGridSize"]
    )
    l_clahe = clahe.apply(np.uint8(l_equHist))
    l_clahe[pepper_mask == 0] = 0

    debug["l_preprocess"] = l_clahe

    # THRESHOLDING
    l_non_zero = l_clahe[l_clahe > 0]
    l_non_zero_normalized = cv2.normalize(l_non_zero, None, 0, 255, cv2.NORM_MINMAX)
    threshold_param_value = (
        ((np.median(l_non_zero_normalized) * threshold_param) / 255)
        * np.max(l_non_zero)
    ) + np.min(l_non_zero)
    debug["threshold_param"] = threshold_param_value
    l_threshold = cv2.threshold(l_clahe, threshold_param_value, 255, cv2.THRESH_BINARY)[
        1
    ]

    debug["l_threshold"] = l_threshold

    # THRESHOLD POSTPROCESSING
    l_hull = convex_hull_mask(l_threshold)
    debug["l_hull"] = l_hull

    l_threshold_morph = cv2.morphologyEx(
        l_threshold,
        cv2.MORPH_OPEN,
        np.ones(open_on_l_params["kernel"], np.uint8),
        iterations=open_on_l_params["iterations"],
    )
    debug["l_threshold_morph"] = l_threshold_morph

    hole_mask_raw = pepper_mask - l_threshold_morph
    debug["hole_mask_raw"] = hole_mask_raw

    center_area = l_hull - l_threshold_morph
    debug["center_area"] = center_area

    center_area_morph = cv2.morphologyEx(
        center_area,
        cv2.MORPH_OPEN,
        np.ones(open_on_center_params["kernel"], np.uint8),
        iterations=open_on_center_params["iterations"],
    )
    debug["center_area_morph"] = center_area_morph

    hole_mask_raw_center = np.bitwise_and(hole_mask_raw, center_area_morph)
    debug["hole_mask_raw_center"] = hole_mask_raw_center

    hole_mask_raw_center_morph = cv2.morphologyEx(
        hole_mask_raw_center,
        cv2.MORPH_OPEN,
        np.ones(open_on_center_raw_params["kernel"], np.uint8),
        iterations=open_on_center_raw_params["iterations"],
    )
    debug["hole_mask_raw_center_morph"] = hole_mask_raw_center_morph

    # TODO: Filter to keep only close to center
    good_contours = []
    hole_contours, _ = cv2.findContours(
        hole_mask_raw_center_morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    if len(hole_contours) > 0:
        for cnt in hole_contours:
            result = cv2.pointPolygonTest(cnt, image_center, True)
            # print(result)
            if abs(result) < max_distance_from_center:
                good_contours.append(cnt)

    # countours to mask
    hole_mask_raw_center_morph = np.zeros_like(hole_mask_raw_center_morph)
    cv2.fillPoly(hole_mask_raw_center_morph, good_contours, 255)

    hole_mask_after_morph = cv2.morphologyEx(
        hole_mask_raw_center_morph,
        cv2.MORPH_CLOSE,
        np.ones(close_params["kernel"], np.uint8),
        iterations=close_params["iterations"],
    )
    debug["hole_mask_after_morph"] = hole_mask_after_morph

    # CONTOURS FINDING
    hole_contours, _ = cv2.findContours(
        hole_mask_after_morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    debug["hole_contours"] = hole_contours

    hole_contour = []
    if len(hole_contours) > 0:
        min_result = max_distance_from_center
        for cnt in hole_contours:
            # print(cv2.contourArea(cnt))
            if cv2.contourArea(cnt) > min_hole_area:
                result = cv2.pointPolygonTest(cnt, image_center, True)
                # print(result)
                if abs(result) < abs(min_result):
                    hole_contour.append(cnt)

    hole_mask = np.zeros_like(hole_mask_after_morph)
    if len(hole_contour) > 0:
        cv2.fillPoly(hole_mask, hole_contour, 255)
    mask_founded = True if len(hole_contour) > 0 else False

    debug["hole_mask"] = hole_mask

    return hole_mask, mask_founded, debug


# MARK: SPLIT NOZZLE MASK
def split_nozzle_mask(
    nozzle_mask, hole_mask, pepper_mask, vectors, section="top_right"
):
    debug = {}

    raw_nozzle_in_pepper_mask = cv2.bitwise_and(nozzle_mask, pepper_mask)
    nozzle_in_pepper_mask = cv2.morphologyEx(
        raw_nozzle_in_pepper_mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)
    )  # TODO: param

    nozzle_mask = nozzle_mask - np.bitwise_and(nozzle_in_pepper_mask, nozzle_mask)

    # Nozzle in pepper mask
    hole_mask_hull = convex_hull_mask(hole_mask)
    pepper_mask_hull = convex_hull_mask(pepper_mask)

    # Nozzle in hole mask
    nozzle_in_hole_mask = cv2.bitwise_and(hole_mask_hull, nozzle_mask)

    contours, _ = cv2.findContours(
        nozzle_in_hole_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    if contours:
        # Assuming the largest contour corresponds to the mask of interest
        cnt = max(contours, key=cv2.contourArea)

        if cv2.contourArea(cnt) < 100:
            nozzle_in_hole_mask = np.zeros_like(nozzle_mask)
            nozzle_outside_mask = np.zeros_like(nozzle_mask)

            return (
                nozzle_in_pepper_mask,
                nozzle_in_hole_mask,
                nozzle_outside_mask,
                debug,
            )

        # Calculate the center of the mask
        M = cv2.moments(cnt)
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])

        vector_x, vector_y = vectors

        # VISU START
        scale_factor = 100  # Adjust this factor as needed
        end_x = int(cx + vector_x * scale_factor)
        end_y = int(cy + vector_y * scale_factor)

        # Create a blank image to draw the split line
        split_line_img = np.zeros_like(nozzle_in_hole_mask)
        cv2.arrowedLine(split_line_img, (cx, cy), (end_x, end_y), (255, 0, 0), 2)

        # Draw the line
        debug["line"] = split_line_img
        # VISU END

        # TODO: Split based on the static vector

        # Calculate the angle of the new vector
        angle = degrees(atan2(vector_y, vector_x)) - 90

        # Rotate the mask to align the new vector with the horizontal axis
        center = (nozzle_in_hole_mask.shape[1] // 2, nozzle_in_hole_mask.shape[0] // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated_mask = cv2.warpAffine(
            nozzle_in_hole_mask,
            M,
            (nozzle_in_hole_mask.shape[1], nozzle_in_hole_mask.shape[0]),
        )

        # Split the rotated mask
        midpoint = rotated_mask.shape[1] // 2
        left_split = rotated_mask[:, :midpoint]
        left_split_zeros = np.zeros_like(left_split)

        right_split = rotated_mask[:, midpoint:]
        right_split_zeros = np.zeros_like(right_split)

        left_split = np.hstack((left_split, right_split_zeros))
        right_split = np.hstack((left_split_zeros, right_split))

        # Rotate the split masks back to their original orientation
        M_inverse = cv2.getRotationMatrix2D(center, -angle, 1.0)
        left_split_original = cv2.warpAffine(
            left_split, M_inverse, (left_split.shape[1], left_split.shape[0])
        )
        right_split_original = cv2.warpAffine(
            right_split, M_inverse, (right_split.shape[1], right_split.shape[0])
        )
        debug["left_split_original"] = left_split_original
        debug["right_split_original"] = right_split_original

        # TODO: Split this mask and add to outside mask

        # Nozzle outside mask
        nozzle_outside_mask = cv2.bitwise_and(
            nozzle_mask, pepper_mask_hull
        ) - cv2.bitwise_and(nozzle_in_hole_mask, nozzle_mask)
        nozzle_outside_mask = nozzle_outside_mask - cv2.bitwise_and(
            nozzle_in_pepper_mask, nozzle_outside_mask
        )

        nozzle_outside_mask = cv2.morphologyEx(
            nozzle_outside_mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)
        )  # TODO: param

        match section:
            case "top_left" | "bottom_left":
                if left_split_original is not None:
                    nozzle_in_hole_mask = nozzle_in_hole_mask - cv2.bitwise_and(
                        nozzle_in_hole_mask, left_split_original
                    )
                    nozzle_outside_mask = nozzle_outside_mask + left_split_original
            case "top_right" | "bottom_right":
                if right_split_original is not None:
                    nozzle_in_hole_mask = nozzle_in_hole_mask - cv2.bitwise_and(
                        nozzle_in_hole_mask, right_split_original
                    )
                    nozzle_outside_mask = nozzle_outside_mask + right_split_original
            case _:
                pass

        nozzle_in_hole_mask = cv2.morphologyEx(
            nozzle_in_hole_mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)
        )  # TODO: param
    else:
        nozzle_in_hole_mask = np.zeros_like(nozzle_mask)
        nozzle_outside_mask = np.zeros_like(nozzle_mask)

    # TODO: zrobienie żeby kod był ładny !!!!!!
    return nozzle_in_pepper_mask, nozzle_in_hole_mask, nozzle_outside_mask, debug


# MARK: DEPTH MEASURMENT ZONES


def depth_measurement_zones(
    hole_mask,
    pepper_mask,
    nozzle_in_hole_mask,
    nozzle_in_pepper,
    og_nozzle_mask,
    params,
):
    debug = {}

    line_mask = np.zeros_like(hole_mask)

    # TODO: param
    section = params["section"]
    depth_measurement_config = params["depth_measurement_zones_config"]
    line_width = depth_measurement_config["line_width"]
    nozzle_mask_de_noise_open_params = depth_measurement_config[
        "nozzle_mask_de_noise_open_params"
    ]
    outer_mask_dilate_params = depth_measurement_config["outer_mask_dilate_params"]
    nozzle_mask_extended_outer_dilate_params = depth_measurement_config[
        "nozzle_mask_extended_outer_dilate_params"
    ]
    nozzle_mask_extended_inner_dilate_params = depth_measurement_config[
        "nozzle_mask_extended_inner_dilate_params"
    ]
    inner_zone_erode_params = depth_measurement_config["inner_zone_erode_params"]

    # TODO: in param dict
    match section:
        case "top_left":
            center = (100, 100)
            cv2.line(
                line_mask,
                (center[0] - 100, center[1] + 100),
                (center[0] + 100, center[1] - 100),
                255,
                line_width,
            )  # TODO: param width
        case "top_right":
            center = (100, 100)
            cv2.line(
                line_mask,
                (center[0] - 100, center[1] - 100),
                (center[0] + 100, center[1] + 100),
                255,
                line_width,
            )  # TODO: param width
        case "bottom_left":
            center = (140, 100)
            cv2.line(
                line_mask,
                (center[0] - 100, center[1] - 100),
                (center[0] + 100, center[1] + 100),
                255,
                line_width,
            )  # TODO: param width
        case "bottom_right":
            center = (60, 100)
            cv2.line(
                line_mask,
                (center[0] - 100, center[1] + 100),
                (center[0] + 100, center[1] - 100),
                255,
                line_width,
            )  # TODO: param width
        case _:
            cv2.line(
                line_mask,
                (center[0] - 100, center[1] + 100),
                (center[0] + 100, center[1] - 100),
                255,
                line_width,
            )  # TODO: param width

    debug["line_mask"] = line_mask

    nozzle_mask = og_nozzle_mask - cv2.bitwise_and(og_nozzle_mask, nozzle_in_pepper)
    nozzle_mask = cv2.morphologyEx(
        nozzle_mask,
        cv2.MORPH_OPEN,
        np.ones(nozzle_mask_de_noise_open_params["kernel"], np.uint8),
        iterations=nozzle_mask_de_noise_open_params["iterations"],
    )  # TODO: param

    debug["nozzle_mask"] = nozzle_mask
    # if np.max(nozzle_in_hole_mask) == 0 or np.max(nozzle_outside_mask) == 0:
    #     nozzle_mask = og_nozzle_mask
    # else:
    #     nozzle_mask = cv2.bitwise_or(nozzle_in_hole_mask, nozzle_outside_mask)

    # OUTER ZONE MASK

    nozzle_line_mask = cv2.bitwise_and(nozzle_mask, line_mask)
    nozzle_hole_mask = convex_hull_joined_masks(nozzle_line_mask, hole_mask)
    if nozzle_hole_mask is None:
        nozzle_hole_mask = np.zeros_like(nozzle_mask)
    nozzle_hole_mask = cv2.bitwise_and(nozzle_hole_mask, line_mask)

    kernel_outer_mask = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, outer_mask_dilate_params["kernel"]
    )  # TODO: param
    near_outer_zone_mask = cv2.dilate(
        nozzle_hole_mask,
        kernel_outer_mask,
        iterations=outer_mask_dilate_params["near_iterations"],
    )  # TODO: param
    far_outer_zone_mask = cv2.dilate(
        nozzle_hole_mask,
        kernel_outer_mask,
        iterations=outer_mask_dilate_params["far_iterations"],
    )  # TODO: param

    outer_zone_mask_raw = far_outer_zone_mask - cv2.bitwise_and(
        near_outer_zone_mask, far_outer_zone_mask
    )

    kernel_nozzle = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, nozzle_mask_extended_outer_dilate_params["kernel"]
    )  # TODO: param
    nozzle_mask_extended_outer = cv2.dilate(
        nozzle_mask,
        kernel_nozzle,
        iterations=nozzle_mask_extended_outer_dilate_params["iterations"],
    )  # TODO: param

    kernel_nozzle = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, nozzle_mask_extended_inner_dilate_params["kernel"]
    )  # TODO: param
    nozzle_mask_extended_inner = cv2.dilate(
        nozzle_mask,
        kernel_nozzle,
        iterations=nozzle_mask_extended_inner_dilate_params["iterations"],
    )  # TODO: param

    debug["nozzle_mask_extended_inner"] = nozzle_mask_extended_inner

    outer_zone_mask = outer_zone_mask_raw - cv2.bitwise_and(
        outer_zone_mask_raw, nozzle_mask_extended_outer
    )
    outer_zone_mask = outer_zone_mask - cv2.bitwise_and(
        outer_zone_mask, np.invert(pepper_mask)
    )
    outer_zone_mask = outer_zone_mask - cv2.bitwise_and(
        outer_zone_mask, get_mask_edge_area(convex_hull_mask(pepper_mask))
    )  # TODO: WHY?
    outer_zone_mask = cv2.bitwise_and(outer_zone_mask, line_mask)

    # INNER ZONE MASK

    # TODO: nie ruszać tej części krawędzi przy brzegu dyszy
    inner_zone_mask = cv2.bitwise_or(hole_mask, nozzle_in_hole_mask)

    debug["inner_zone_mask_with_nozzle"] = inner_zone_mask

    kernel_inner_mask = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, inner_zone_erode_params["kernel"]
    )  # TODO: param
    inner_zone_mask = cv2.erode(
        inner_zone_mask,
        kernel_inner_mask,
        iterations=inner_zone_erode_params["iterations"],
    )  # TODO: param iters

    debug["inner_mask_after_erode"] = inner_zone_mask

    inner_zone_mask = convex_hull_mask(inner_zone_mask)

    debug["inner_mask_after_convex"] = inner_zone_mask

    # Excluding nozzle from inner zone and outer zone
    if inner_zone_mask is not None:
        inner_zone_mask = inner_zone_mask - cv2.bitwise_and(
            inner_zone_mask, nozzle_mask
        )
    else:
        inner_zone_mask = np.zeros_like(nozzle_mask)

    if outer_zone_mask is not None:
        outer_zone_mask = outer_zone_mask - cv2.bitwise_and(
            outer_zone_mask, nozzle_mask
        )
    else:
        outer_zone_mask = np.zeros_like(nozzle_mask)

    return inner_zone_mask, outer_zone_mask, debug


# MARK: CREATE OVERFLOW MASK
def create_overflow_mask(pepper_mask, hole_mask, params):
    debug = {}

    overflow_config = params["overflow_mask_config"]
    kernel = overflow_config["kernel"]
    erode_iterations = overflow_config["erode_iter"]
    dilate_iterations = overflow_config["dilate_iter"]

    outside_of_pepper_mask = cv2.bitwise_and(
        pepper_mask, np.invert(convex_hull_mask(hole_mask))
    )
    debug["outside_of_pepper_mask_init"] = outside_of_pepper_mask

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, kernel)
    overflow_mask = cv2.erode(
        outside_of_pepper_mask, kernel, iterations=erode_iterations
    )
    debug["near_erode"] = overflow_mask
    far_hole_mask = cv2.dilate(hole_mask, kernel, iterations=dilate_iterations)
    debug["far_dilate"] = far_hole_mask

    overflow_mask = cv2.bitwise_and(overflow_mask, far_hole_mask)

    # TODO: Stała grubość paska overflow

    return overflow_mask, debug


# MARK: CREATE OUTER OVERFLOW MASK
def create_outer_overflow_mask(pepper_mask, hole_mask, params):
    debug = {}

    kernel = params["outer_overflow_mask_config"]["erode_params"]["kernel"]
    iter = params["outer_overflow_mask_config"]["erode_params"]["iterations"]

    pepper_mask_hull = convex_hull_mask(pepper_mask)

    pepper_mask_hull_erode = cv2.erode(
        pepper_mask_hull, np.ones(kernel, np.uint8), iterations=iter
    )  # TODO: param

    outer_pepper_mask = pepper_mask - np.bitwise_and(
        pepper_mask, pepper_mask_hull_erode
    )
    hole_mask_hull = convex_hull_mask(hole_mask)
    outer_pepper_mask = outer_pepper_mask - np.bitwise_and(
        outer_pepper_mask, hole_mask_hull
    )

    return outer_pepper_mask, debug


# MARK: ADD NOZZLE MASKS
def add_nozzle_masks(
    inner_zone_mask, overflow_mask, nozzle_in_hole_mask, nozzle_outside_mask
):
    debug = {}

    inner_zone_color = np.bitwise_or(
        inner_zone_mask, nozzle_in_hole_mask
    ) - np.bitwise_and(inner_zone_mask, nozzle_outside_mask)
    overflow_mask_color = overflow_mask  # np.bitwise_or(overflow_mask, nozzle_outside_mask) - np.bitwise_and(overflow_mask, nozzle_in_hole_mask)

    return inner_zone_color, overflow_mask_color, debug


# MARK: CHECK MASK SIZE
def check_mask_size(mask, min_size):
    return cv2.countNonZero(mask) < min_size
