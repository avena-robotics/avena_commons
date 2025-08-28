import numpy as np

from avena_commons.vision.vision import (
    create_box_color_mask,
    create_box_depth_mask,
    create_camera_distortion,
    create_camera_matrix,
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
    undistort,
    validate_rectangle,
)

"""
"box_config_a": {
  "center_point": [1050, 550],
  "fix_depth_on": True,
  "fix_depth_config": {
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
  },
  "depth": {"min_non_zero_percentage": 0.3, "center_size": 100, "depth_range": 35, "depth_bias": 44},
  "hsv": {"hsv_h_min": 70, "hsv_h_max": 105, "hsv_s_min": 10, "hsv_s_max": 255, "hsv_v_min": 120, "hsv_v_max": 255},
  "preprocess": {
      "blur_size": 15,
      "opened_kernel_type": cv2.MORPH_RECT,
      "opened_size": [2, 9],
      "opened_iterations": 3,
      "closed_size": [1, 9],
      "closed_iterations": 3,
      "closed_kernel_type": cv2.MORPH_ELLIPSE,
  },
  "remove_cnts": {"expected_width": 1150, "expected_height": 850},
  "edge_removal": {"edge_margin": 35},
  "hit_contours": {"angle_step": 10, "step_size": 1},
  "rect_validation": {"max_angle": 20, "box_ratio_range": [1.293, 1.387], "max_distance": 150},
},
"box_config_b": {
  "center_point": [1050, 550],
  "fix_depth_on": True,
  "fix_depth_config": {
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
  },
  "depth": {"min_non_zero_percentage": 0.3, "center_size": 100, "depth_range": 35, "depth_bias": 44},
  "hsv": {"hsv_h_min": 70, "hsv_h_max": 105, "hsv_s_min": 10, "hsv_s_max": 255, "hsv_v_min": 100, "hsv_v_max": 255},
  "preprocess": {
      "blur_size": 15,
      "opened_kernel_type": cv2.MORPH_RECT,
      "opened_size": [2, 9],
      "opened_iterations": 3,
      "closed_size": [1, 9],
      "closed_iterations": 6,
      "closed_kernel_type": cv2.MORPH_ELLIPSE,
  },
  "remove_cnts": {"expected_width": 1150, "expected_height": 850},
  "edge_removal": {"edge_margin": 50},
  "hit_contours": {"angle_step": 10, "step_size": 1},
  "rect_validation": {"max_angle": 20, "box_ratio_range": [1.293, 1.387], "max_distance": 150},
},
"box_config_c": {
  "center_point": [1050, 550],
  "fix_depth_on": True,
  "fix_depth_config": {
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
  },
  "depth": {
      "min_non_zero_percentage": 0.3,
      "center_size": 100,
      "depth_range": 35, 
      "depth_bias": 44
  },
  "hsv": {
      "hsv_h_min": 70, 
      "hsv_h_max": 105, 
      "hsv_s_min": 50, 
      "hsv_s_max": 255,
      "hsv_v_min": 120, 
      "hsv_v_max": 255
  },
  "preprocess": {
      "blur_size": 15,
      "opened_kernel_type": cv2.MORPH_RECT,
      "opened_size": [2, 9],
      "opened_iterations": 3,
      "closed_size": [1, 9],
      "closed_iterations": 3,
      "closed_kernel_type": cv2.MORPH_ELLIPSE
  },
  "remove_cnts": {
      "expected_width": 1150,
      "expected_height": 850
  },
  "edge_removal": {
      "edge_margin": 35
  },
  "hit_contours": {
      "angle_step": 10,
      "step_size": 1
  },
  "rect_validation": {
      "max_angle": 20,
      "box_ratio_range": [1.295, 1.385], #1.29, 1.39
      "max_distance": 150 #300
  }
}
"""


def box_detector(
    *, color_image, depth_image, camera_params, distortion_coefficients, configs
):
    camera_matrix = create_camera_matrix(camera_params)  # utworzenie macierzy kamery
    camera_distortion = create_camera_distortion(distortion_coefficients)

    for config in configs:
        # fix depth
        if config.get("fix_depth_on", False):
            depth_image, _ = fix_depth(depth_image, config["fix_depth_config"])

        # create box depth mask
        depth_mask = create_box_depth_mask(
            depth_image, {**config["depth"], "center_point": config["center_point"]}
        )

        # create box color mask
        color_mask = create_box_color_mask(
            color_image, {**config["hsv"], "center_point": config["center_point"]}
        )

        # combine masks
        mask_combined = merge_masks([depth_mask, color_mask])

        if np.max(mask_combined) <= 0:
            detect_image = mask_combined
            continue

        mask_preprocessed = preprocess_mask(mask_combined, config["preprocess"])
        mask_undistorted = undistort(
            mask_preprocessed, camera_matrix, camera_distortion
        )
        contours = find_contours(mask_undistorted)

        box_contours = remove_contours_outside_box(
            contours, {**config["remove_cnts"], "center_point": config["center_point"]}
        )
        filtered_contours = remove_edge_contours(
            contours,  # FIXME contours czy to nie powinno być box_contours?
            mask_undistorted.shape,
            config.get("edge_removal", {"edge_margin": 50}),
        )

        hit_contours, labeled_mask = get_hit_contours(
            mask_undistorted,
            filtered_contours,
            {**config["hit_contours"], "center_point": config["center_point"]},
        )

        if len(hit_contours) == 0:
            detect_image = mask_combined
            continue

        rect, box = rectangle_from_contours(hit_contours)

        valid = validate_rectangle(
            rect,
            box,
            color_image,
            {**config["rect_validation"], "center_point": config["center_point"]},
        )

        if not valid:
            continue

        detect_image = prepare_image_output(color_image, box_contours, rect, box)

        center, sorted_corners, angle, z = prepare_box_output(
            rect,
            box,
            depth_image,
            {**config["depth"], "center_point": config["center_point"]},
        )

        return center, sorted_corners, angle, z, detect_image

    return None, None, None, None, detect_image
