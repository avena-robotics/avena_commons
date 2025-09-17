import numpy as np

import avena_commons.vision.camera as camera
import avena_commons.vision.image_preprocess as preprocess
import avena_commons.vision.validation as validation
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import debug
from avena_commons.vision.vision import (
    create_box_color_mask,
    create_box_depth_mask,
    find_contours,
    fix_depth,
    get_hit_contours,
    merge_masks,
    prepare_box_output,
    prepare_image_output,
    preprocess_mask,
    rectangle_from_contours,
    remove_contours_outside_box,
    remove_edge_contours,
)


def box_detector(*, frame, camera_config, config):
    color_image = frame["color"]
    depth_image = frame["depth"]

    debug_data = {}
    with Catchtime() as t1:
        camera_matrix = camera.create_camera_matrix(camera_config["camera_params"])
        camera_distortion = camera.create_camera_distortion(
            camera_config["distortion_coefficients"]
        )

    with Catchtime() as t2:
        if config.get("fix_depth_on", False):
            depth_image = fix_depth(depth_image, config["fix_depth_config"])
            debug_data["box_depth_image_fixed"] = depth_image

    # create box depth mask
    with Catchtime() as t3:
        depth_mask = create_box_depth_mask(
            depth_image, {**config["depth"], "center_point": config["center_point"]}
        )
        debug_data["box_depth_mask"] = depth_mask

    # create box color mask
    with Catchtime() as t4:
        color_mask = create_box_color_mask(
            color_image, {**config["hsv"], "center_point": config["center_point"]}
        )
        debug_data["box_color_mask"] = color_mask

    # combine masks
    with Catchtime() as t5:
        mask_combined = merge_masks([depth_mask, color_mask])
        debug_data["box_mask_combined"] = mask_combined

    if np.max(mask_combined) <= 0:
        detect_image = mask_combined
        return None, None, None, None, detect_image

    with Catchtime() as t6:
        mask_preprocessed = preprocess_mask(mask_combined, config["preprocess"])
        debug_data["box_mask_preprocessed"] = mask_preprocessed

    with Catchtime() as t7:
        mask_undistorted = preprocess.undistort(
            mask_preprocessed, camera_matrix, camera_distortion
        )
        debug_data["box_mask_undistorted"] = mask_undistorted

    with Catchtime() as t8:
        contours = find_contours(mask_undistorted)
        debug_data["box_contours"] = contours

    with Catchtime() as t9:
        box_contours = remove_contours_outside_box(
            contours, {**config["remove_cnts"], "center_point": config["center_point"]}
        )
        debug_data["box_box_contours"] = box_contours

    with Catchtime() as t10:
        filtered_contours = remove_edge_contours(
            contours,  # FIXME contours czy to nie powinno być box_contours?
            mask_undistorted.shape,
            config.get("edge_removal", {"edge_margin": 50}),
        )
        debug_data["box_filtered_contours"] = filtered_contours

    with Catchtime() as t11:
        hit_contours, labeled_mask = get_hit_contours(
            mask_undistorted,
            filtered_contours,
            {**config["hit_contours"], "center_point": config["center_point"]},
        )
        debug_data["box_hit_contours"] = hit_contours
        debug_data["box_labeled_mask"] = labeled_mask

    if len(hit_contours) == 0:
        detect_image = mask_combined
        return None, None, None, None, detect_image

    with Catchtime() as t12:
        rect, box = rectangle_from_contours(hit_contours)
        debug_data["box_rect"] = rect
        debug_data["box_box"] = box

    with Catchtime() as t13:
        valid = validation.validate_rectangle(
            rect,
            box,
            color_image,
            {**config["rect_validation"], "center_point": config["center_point"]},
        )
        debug_data["box_valid"] = valid

    with Catchtime() as t14:  # debug
        detect_image = prepare_image_output(color_image, box_contours, rect, box)
        debug_data["box_detect_image"] = detect_image

    if not valid:
        return None, None, None, None, detect_image

    with Catchtime() as t15:
        center, sorted_corners, angle, z = prepare_box_output(  # wynik glowny
            rect,
            box,
            depth_image,
            {**config["depth"], "center_point": config["center_point"]},
        )
        debug_data["box_center"] = center
        debug_data["box_sorted_corners"] = sorted_corners
        debug_data["box_angle"] = angle
        debug_data["box_z"] = z

    # debug(
    #     f"t1: {t1.t * 1_000:.1f}ms t2: {t2.t * 1_000:.1f}ms t3: {t3.t * 1_000:.1f}ms t4: {t4.t * 1_000:.1f}ms t5: {t5.t * 1_000:.1f}ms t6: {t6.t * 1_000:.1f}ms t7: {t7.t * 1_000:.1f}ms t8: {t8.t * 1_000:.1f}ms t9: {t9.t * 1_000:.1f}ms t10: {t10.t * 1_000:.1f}ms t11: {t11.t * 1_000:.1f}ms t12: {t12.t * 1_000:.1f}ms t13: {t13.t * 1_000:.1f}ms t14: {t14.t * 1_000:.1f}ms t15: {t15.t * 1_000:.1f}ms"
    # )
    return center, sorted_corners, angle, z, detect_image, debug_data
