import math
import traceback

import cv2
import numpy as np
from avena_commons.util import (
    euler_to_rotation_matrix,
    rotation_matrix_to_euler_angles,
    rotation_matrix_to_rvec,
)
from avena_commons.util.logger import MessageLogger, debug, error, info, warning
from scipy.spatial.transform import Rotation as R

from .tag_reconstruction import TagReconstuction
from .vision import Vision


class ObjectDetector:
    """Class for detecting and analyzing objects in images using various computer vision techniques."""

    def __init__(self):
        """Initialize detector with default HSV and depth configuration parameters."""
        self.config_hsv = {
            "hsv_h_min": 100,
            "hsv_h_max": 105,
            "hsv_s_min": 100,
            "hsv_s_max": 255,
            "hsv_v_min": 65,
            "hsv_v_max": 255,
        }
        self.config_depth = {"center_size": 100, "depth_range": 35, "depth_bias": 44}

    # MARK: BOX DETECTION
    def box_detector(self, color_image, depth_image, camera_params, dist):
        """
        Detect boxes in color and depth images using combined color and depth segmentation.

        Args:
            color_image: RGB image array
            depth_image: Depth image array
            camera_params: Camera intrinsic parameters [fx, fy, cx, cy]
            dist: Camera distortion coefficients

        Returns:
            tuple: (center, sorted_corners, angle, z, image) where:
                - center: (x,y) coordinates of box center
                - sorted_corners: List of 4 corner points in clockwise order
                - angle: Rotation angle of box in degrees
                - z: Depth value at box center
                - image: Processed image with detected box
            None if no box detected
        """

        # FIXME: TO ENV
        center_point = (1050, 550)
        config_depth = {"center_size": 100, "depth_range": 35, "depth_bias": 44, "center_point": center_point}

        config_hsv = {"hsv_h_min": 85, "hsv_h_max": 105, "hsv_s_min": 50, "hsv_s_max": 255, "hsv_v_min": 65, "hsv_v_max": 255}

        config_preprocess = {"blur_size": 15, "morph_size": 9, "morph_iterations": 3}
        config_remove_cnts = {"expected_width": 1150, "expected_height": 850}
        config_hit_contours = {"angle_step": 2, "step_size": 1, "center_point": center_point}
        config_rect_validation = {"center_point": center_point, "max_angle": 20, "box_ratio_range": [1.29, 1.39], "max_distance": 300}

        depth_mask = Vision.create_box_depth_mask(depth_image, config_depth)
        color_mask = Vision.create_box_color_mask(color_image, config_hsv)
        mask_combined = Vision.merge_masks([depth_mask, color_mask])

        if np.max(mask_combined) <= 0:
            return None, None, None, None, mask_combined

        mask_preprocessed, _, _, _ = Vision.preprocess_mask(mask_combined, config_preprocess)
        mask_undistorted = Vision.undistort_image(mask_preprocessed, camera_params, dist)
        cnts = Vision.find_cnts(mask_undistorted)
        box_cnts = Vision.remove_cnts_outside_expected_bbox(cnts, center_point, config_remove_cnts)
        hit_contours, _ = Vision.get_hit_contours(mask_undistorted, box_cnts, config_hit_contours)
        rect, box = Vision.rect_from_cnts(hit_contours)

        image = Vision.prepare_image_output(color_image, hit_contours, rect, box)

        value = Vision.rect_validation(rect, config_rect_validation)

        if value:
            center, sorted_corners, angle, z, image = Vision.prepare_box_output(rect, box, depth_image, image, config_depth)
            return center, sorted_corners, angle, z, image

        return None, None, None, None, image

    # MARK: BOX DETECTION SEQUENTIAL
    @staticmethod
    def box_detector_sequential(color_image, depth_image, camera_params, dist, configs):
        camera_matrix = np.array(
            [
                [camera_params[0], 0, camera_params[2]],
                [0, camera_params[1], camera_params[3]],
                [0, 0, 1],
            ],
            dtype=np.float32,
        )
        dist = np.array(dist, dtype=np.float32)

        for config in configs:
            if config.get("fix_depth_on", False):
                depth_image, _ = Vision.fix_depth_img(depth_image, config["fix_depth_config"])

            depth_mask = Vision.create_box_depth_mask(depth_image, {**config["depth"], "center_point": config["center_point"]})
            color_mask = Vision.create_box_color_mask(color_image, {**config["hsv"], "center_point": config["center_point"]})
            mask_combined = Vision.merge_masks([depth_mask, color_mask])

            if np.max(mask_combined) <= 0:
                detect_image = mask_combined
                continue

            mask_preprocessed = Vision.preprocess_mask(mask_combined, config["preprocess"])
            mask_undistorted = cv2.undistort(mask_preprocessed, camera_matrix, dist)
            cnts, _ = cv2.findContours(mask_undistorted, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            box_cnts = Vision.remove_cnts_outside_expected_bbox(cnts, {**config["remove_cnts"], "center_point": config["center_point"]})
            filtered_cnts = Vision.remove_edge_contours(box_cnts, mask_undistorted.shape, config.get("edge_removal", {"edge_margin": 50}))

            hit_contours, labeled_mask = Vision.get_hit_contours(mask_undistorted, filtered_cnts, {**config["hit_contours"], "center_point": config["center_point"]})

            if len(hit_contours) == 0:
                detect_image = mask_combined
                continue

            rect, box = Vision.rect_from_cnts(hit_contours)

            detect_image = Vision.prepare_image_output(color_image, box_cnts, rect, box)

            valid = Vision.rect_validation(rect, box, detect_image, {**config["rect_validation"], "center_point": config["center_point"]})

            if not valid:
                continue

            center, sorted_corners, angle, z = Vision.prepare_box_output(rect, box, depth_image, {**config["depth"], "center_point": config["center_point"]})

            return center, sorted_corners, angle, z, detect_image

        return None, None, None, None, detect_image

    # MARK: QR DETECTION
    @staticmethod
    def qr_detector_pnp_test(detector, image, depth_original):
        """
        Test function for QR code detection and pose estimation.

        Args:
            detector: QR code detector instance
            image: RGB image array
            depth_original: Original depth image array

        Returns:
            tuple: (sorted_centers2, gray_to_draw) where:
                - sorted_centers2: Dictionary mapping QR code indices to their detected positions
                - gray_to_draw: Grayscale image with detected QR codes marked
        """
        # Przekształcenie obrazu na skalę szarości
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        detection_list = detector.detect(gray_image)
        gray_to_draw = gray_image.copy()

        a = []
        for detection in detection_list:
            # if detection.center[0] > 430 and detection.center[0] < 850:
            # Liczenie pozy QR kodu
            # print(detection)
            # Rotation = R.from_matrix(detection.pose_R)
            # carthesian = Rotation.as_euler('xyz', degrees=True)
            # carthesian = carthesian.tolist()
            # copy = carthesian.copy()
            # quaternion = get_quaternion_from_euler(carthesian[0], carthesian[1], carthesian[2])
            # pose_t_flat = detection.pose_t.flatten()
            # pose = np.concatenate((pose_t_flat, quaternion))

            # liczenie mediany głębii
            min_x, min_y = (
                int(np.min(detection.corners[:, 0], axis=0)),
                int(np.min(detection.corners[:, 1], axis=0)),
            )
            max_x, max_y = (
                int(np.max(detection.corners[:, 0], axis=0)),
                int(np.max(detection.corners[:, 1], axis=0)),
            )
            cropped_depth_array = depth_original[min_y:max_y, min_x:max_x]
            z = np.median(cropped_depth_array) / 1000
            # pose[2] = z

            corners = detection.corners.tolist()

            detected = {"center": (detection.center), "corners": (corners), "z": z}
            a.append(detected)

        centers = []
        sorted_centers2 = {}

        for qr in a:
            x, y = qr["center"][0], qr["center"][1]
            centers.append([x, y, qr["corners"], qr["z"]])
            for corner in qr["corners"]:
                cv2.circle(gray_to_draw, (int(corner[0]), int(corner[1])), 1, (0, 255, 0), -1)
        if len(centers) == 0:
            pass
            # raise Exception("No QR codes detected")
        # Sortowanie punktów najpierw wzdłuż osi x, a następnie wzdłuż osi y
        # Punkty mają być posortowane tak, aby pierwszy punkt był lewym górnym, drugi lewym dolnym, trzeci prawym górnym, a czwarty prawym dolnym
        sorted_centers = sorted(centers, key=lambda point: (point[0]))

        if len(sorted_centers) == 4:
            left = sorted_centers[0:2]
            right = sorted_centers[2:4]

            left_y = sorted(left, key=lambda point: (point[1]))
            right_y = sorted(right, key=lambda point: (point[1]))

            sorted_centers2 = {1: left_y[0], 2: left_y[1], 3: right_y[0], 4: right_y[1]}

        elif len(sorted_centers) == 3:
            # return {1: left[0], 2: left[1], 3: right_y[0], 4: None}
            if abs(sorted_centers[0][0] - sorted_centers[1][0]) > abs(sorted_centers[1][0] - sorted_centers[2][0]):
                left = sorted_centers[0]
                right = sorted_centers[1:3]

                right_y = sorted(right, key=lambda point: (point[1]))

                if abs(right_y[0][1] - left[1]) > abs(right_y[1][1] - left[1]):
                    sorted_centers2 = {1: None, 2: left, 3: right_y[0], 4: right_y[1]}
                else:
                    sorted_centers2 = {1: left, 2: None, 3: right_y[0], 4: right_y[1]}

            else:
                left = sorted_centers[0:2]
                right = sorted_centers[2]

                left_y = sorted(left, key=lambda point: (point[1]))

                if abs(left_y[0][1] - right[1]) > abs(left_y[1][1] - right[1]):
                    sorted_centers2 = {1: left_y[0], 2: left_y[1], 3: None, 4: right}
                else:
                    sorted_centers2 = {1: left_y[0], 2: left_y[1], 3: right, 4: None}

        elif len(sorted_centers) == 2:
            if sorted_centers[0][1] > sorted_centers[1][1]:
                upper = sorted_centers[1]
                lower = sorted_centers[0]
            else:
                upper = sorted_centers[0]
                lower = sorted_centers[1]

            return {1: None, 2: None, 3: upper, 4: lower}

            # print(sorted_centers)
            # left, right = [], []
            # for center in sorted_centers:
            #     if center[2] < 0:
            #         left.append(center)
            #     else:
            #         right.append(center)

            # if len(left) == 2:
            #     left_y = sorted(left, key=lambda point: (point[1]))
            #     sorted_centers2 = {1: left_y[0], 2: left_y[1], 3: None, 4: None}
            # elif len(right) == 2:
            #     right_y = sorted(right, key=lambda point: (point[1]))
            #     sorted_centers2 = {1: None, 2: None, 3: right_y[0], 4: right_y[1]}
            # else:
            #     if left[0][1] > 360:
            #         second = left[0]
            #         first = None
            #     else:
            #         first = left[0]
            #         second = None
            #     if right[0][1] > 360:
            #         fourth = right[0]
            #         third = None
            #     else:
            #         third = right[0]
            #         fourth = None

        elif len(sorted_centers) == 1:
            sorted_centers2 = {1: None, 2: None, 3: None, 4: sorted_centers[0]}
            # if sorted_centers[0][2] < 0:
            #     if sorted_centers[0][1] > 360:
            #         sorted_centers2 = {1: None, 2: sorted_centers[0], 3: None, 4: None}
            #     else:
            #         sorted_centers2 = {1: sorted_centers[0], 2: None, 3: None, 4: None}
            # elif sorted_centers[0][2] >= 0:
            #     if sorted_centers[0][1] > 360:
            #         sorted_centers2 = {1: None, 2: None, 3: None, 4: sorted_centers[0]}
            #     else:
            #         sorted_centers2 = {1: None, 2: None, 3: sorted_centers[0], 4: None}

        elif len(sorted_centers) == 9:
            left = sorted_centers[0:3]
            middle = sorted_centers[3:6]
            right = sorted_centers[6:9]

            left_y = sorted(left, key=lambda point: (point[1]))
            middle_y = sorted(middle, key=lambda point: (point[1]))
            right_y = sorted(right, key=lambda point: (point[1]))

            sorted_centers2 = {
                1: left_y[0],
                2: left_y[1],
                3: left_y[2],
                4: middle_y[0],
                5: middle_y[1],
                6: middle_y[2],
                7: right_y[0],
                8: right_y[1],
                9: right_y[2],
            }

        elif len(sorted_centers) > 9:
            cols_count = 0
            current_center = None
            for center in sorted_centers:
                if current_center is None:
                    current_center = center
                    cols_count += 1
                else:
                    if center[0] > current_center[0] + 70:
                        current_center = center
                        cols_count += 1
            if len(sorted_centers) % cols_count != 0:
                raise Exception(f"Wrong number of QR codes detected. Detected {len(sorted_centers)} QR codes, but it should be a multiple of {cols_count}")
            else:
                rows_count = len(sorted_centers) / cols_count
                cols = []
                for i in range(cols_count):
                    col_centers = sorted_centers[int(i * rows_count) : int((i + 1) * rows_count)]
                    col_centers_y = sorted(col_centers, key=lambda point: (point[1]))
                    for center in col_centers_y:
                        cols.append(center)

            for i in range(len(cols)):
                sorted_centers2[i + 1] = cols[i]

        return sorted_centers2, gray_to_draw

    @staticmethod
    def qr_detector_pnp(detector, image, depth_original, camera_params, dist):
        """
        Detect QR codes and estimate their 3D poses using PnP algorithm.

        Args:
            detector: QR code detector instance
            image: RGB image array
            depth_original: Original depth image array
            camera_params: Camera intrinsic parameters [fx, fy, cx, cy]
            dist: Camera distortion coefficients

        Returns:
            dict: Mapping of QR code indices (1-4) to their detected positions and pose data
        """
        # Przekształcenie obrazu na skalę szarości

        middle_point_x = camera_params[2]

        camera_matrix = np.array(
            [
                [camera_params[0], 0, camera_params[2]],
                [0, camera_params[1], camera_params[3]],
                [0, 0, 1],
            ],
            dtype=np.float32,
        )

        dist = np.array(dist, dtype=np.float32)

        # TODO: SPRAWDZIĆ CZY TO NA 100 % ROBI LEPIEJ
        config = {
            "clahe": {
                "clip_limit": 4.0,
                "grid_size": 8,
            },
            "glare": {"threshold": 200, "kernel_size": 5, "iter": 2},
            "border_size": 20,
            "gamma": 3,
            "binarization": {"block_size": 31, "C": 1},
            "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
            "merge": {"cropped_weight": 0.7, "image_weight": 0.7},
        }

        gray_image = Vision.qr_preprocess(image, config)
        # gray_image = Vision.qr_preprocess_b(image, config)
        # gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        undistorted = cv2.undistort(gray_image, camera_matrix, dist)
        detection_list = detector.detect(undistorted, True, camera_params, 0.02)
        # image_c = image.copy()

        centers = []
        print(f"Detection list: {len(detection_list)}")
        for detection in detection_list:
            if detection.center[0] > (middle_point_x * 3.3) / 5 and detection.center[0] < (middle_point_x * 6.7) / 5:
                print(f"Detection center: {detection.center}")
                # liczenie mediany głębii
                min_x, min_y = (
                    int(np.min(detection.corners[:, 0], axis=0)),
                    int(np.min(detection.corners[:, 1], axis=0)),
                )
                max_x, max_y = (
                    int(np.max(detection.corners[:, 0], axis=0)),
                    int(np.max(detection.corners[:, 1], axis=0)),
                )
                cropped_depth_array = depth_original[min_y:max_y, min_x:max_x]
                z = np.median(cropped_depth_array) / 1000

                corners = detection.corners.tolist()

                detected = [
                    detection.center[0],
                    detection.center[1],
                    corners,
                    z,
                    detection.pose_t,
                    rotation_matrix_to_rvec(euler_to_rotation_matrix(0, 0, rotation_matrix_to_euler_angles(detection.pose_R)[2])),
                ]
                centers.append(detected)

            # for corner in corners:
            #     cv2.circle(image_c, (int(corner[0]), int(corner[1])), 1, (0, 255, 0), -1)
            # path = os.path.expanduser('~') + '/controller/resources/photos'
            # cv2.imwrite(f'{path}/qr_ver/color_photo.png', image_c)
            # cv2.imwrite(f'{path}/qr_ver/gray_photo.png', gray_image)

            else:
                print(f"QR code out of range: {detection.center}")

        print(f"Centers: {centers}")
        sorted_centers2 = {}

        if len(centers) == 0:
            pass

        # Punkty mają być posortowane tak, aby pierwszy punkt był lewym górnym, drugi lewym dolnym, trzeci prawym górnym, a czwarty prawym dolnym
        sorted_centers = sorted(centers, key=lambda point: (point[0]))

        print(f"Sorted centers: {sorted_centers}")

        if len(sorted_centers) == 4:
            left = sorted_centers[0:2]
            right = sorted_centers[2:4]

            left_y = sorted(left, key=lambda point: (point[1]))
            right_y = sorted(right, key=lambda point: (point[1]))

            sorted_centers2 = {1: left_y[0], 2: left_y[1], 3: right_y[0], 4: right_y[1]}

        elif len(sorted_centers) == 3:
            if abs(sorted_centers[0][0] - sorted_centers[1][0]) > abs(sorted_centers[1][0] - sorted_centers[2][0]):
                left = sorted_centers[0]
                right = sorted_centers[1:3]

                right_y = sorted(right, key=lambda point: (point[1]))

                if abs(right_y[0][1] - left[1]) > abs(right_y[1][1] - left[1]):
                    sorted_centers2 = {1: None, 2: left, 3: right_y[0], 4: right_y[1]}
                else:
                    sorted_centers2 = {1: left, 2: None, 3: right_y[0], 4: right_y[1]}

            else:
                left = sorted_centers[0:2]
                right = sorted_centers[2]

                left_y = sorted(left, key=lambda point: (point[1]))

                if abs(left_y[0][1] - right[1]) > abs(left_y[1][1] - right[1]):
                    sorted_centers2 = {1: left_y[0], 2: left_y[1], 3: None, 4: right}
                else:
                    sorted_centers2 = {1: left_y[0], 2: left_y[1], 3: right, 4: None}

        elif len(sorted_centers) == 2:
            if abs(sorted_centers[0][0] - sorted_centers[1][0]) < 150:
                if sorted_centers[0][1] > sorted_centers[1][1]:
                    upper = sorted_centers[1]
                    lower = sorted_centers[0]
                else:
                    upper = sorted_centers[0]
                    lower = sorted_centers[1]
            else:
                upper = None
                lower = None

            print(f"Upper: {upper}, Lower: {lower}")
            return {1: None, 2: None, 3: upper, 4: lower}

        elif len(sorted_centers) == 1:
            if sorted_centers[0][1] > 540:
                sorted_centers2 = {1: None, 2: None, 3: None, 4: sorted_centers[0]}
            else:
                sorted_centers2 = {1: None, 2: None, 3: sorted_centers[0], 4: None}

        print(f"Sorted centers 2: {sorted_centers2}")

        return sorted_centers2

    @staticmethod
    def qr_detect_sequencial(detector, qr_image, qr_number, camera_params, dist, configs, message_logger):
        results_dict = {}

        match qr_number:
            case 0:
                qr_number_func = 1

                # TODO: QUICK FIX DO SOMETHING BETTER
                for config in configs:
                    config["middle_area"]["min_x"] = 0.8
                    config["middle_area"]["max_x"] = 1.4

                    if config.get("tag_reconstruction", False):
                        config["tag_reconstruction_config"]["scene_corners"] = ["BL"]
                        config["tag_reconstruction_config"]["central"] = True

            case 1:
                qr_number_func = 4
            case 2:
                qr_number_func = 3
            case 3:
                qr_number_func = 2
            case 4:
                qr_number_func = 1

        middle_point_x = camera_params[2]
        camera_matrix = np.array(
            [
                [camera_params[0], 0, camera_params[2]],
                [0, camera_params[1], camera_params[3]],
                [0, 0, 1],
            ],
            dtype=np.float32,
        )
        dist = np.array(dist, dtype=np.float32)

        config_index = 0

        output_list = []

        for idx, config in enumerate(configs):
            config_name = f"config_{chr(97 + idx)}"
            results_dict[config_name] = {
                "clahe_detections": [],
                "binary_detections": [],
                "reconstructed_detections": [],
            }

            if config.get("tag_reconstruction", False) == True:  # MARK: TAG RECONSTRUCTION USE HERE
                try:
                    tag_image = cv2.imread("lib/supervisor_fairino/module/util/tag36h11-0.png")
                    merged_image = TagReconstuction.reconsturct_tags_on_image(qr_image, tag_image, config["tag_reconstruction_config"])
                    gray_image = cv2.cvtColor(merged_image, cv2.COLOR_BGR2GRAY)
                    detection_list_reconstructed = detector.detect(gray_image, True, camera_params, config["qr_size"])
                    for detection in detection_list_reconstructed:
                        if detection.center[0] > (middle_point_x * config["middle_area"]["min_x"]) and detection.center[0] < (middle_point_x * config["middle_area"]["max_x"]):
                            results_dict[config_name]["reconstructed_detections"].append(detection)
                            if ObjectDetector._is_unique_detection(detection, output_list):
                                output_list.append(detection)
                except Exception as e:
                    error(f"OBJECT DETECTOR: tag reconstruction error: {e} traceback: {traceback.format_exc()}", message_logger)

                if len(output_list) >= qr_number_func:
                    return output_list, results_dict
                continue

            if config["gray_image_type"] == "gray":
                gray_image = cv2.cvtColor(qr_image, cv2.COLOR_BGR2GRAY)
            elif config["gray_image_type"] == "saturation":
                gray_image = 255 - cv2.cvtColor(qr_image, cv2.COLOR_BGR2HSV)[:, :, 1]

            # CLAHE
            image_clahe = cv2.createCLAHE(clipLimit=config["clahe"]["clip_limit"], tileGridSize=(config["clahe"]["grid_size"], config["clahe"]["grid_size"])).apply(gray_image)

            undistorted_clahe = cv2.undistort(image_clahe, camera_matrix, dist)

            detection_list_clahe = detector.detect(undistorted_clahe, True, camera_params, config["qr_size"])

            for detection in detection_list_clahe:
                if detection.center[0] > (middle_point_x * config["middle_area"]["min_x"]) and detection.center[0] < (middle_point_x * config["middle_area"]["max_x"]):
                    results_dict[config_name]["clahe_detections"].append(detection)
                    if ObjectDetector._is_unique_detection(detection, output_list):
                        output_list.append(detection)

            if len(output_list) >= qr_number_func:
                return output_list, results_dict

            # BINARY
            binary_image = Vision.crop_image_process(gray_image, config["binarization"])

            preprocessed_image = cv2.addWeighted(binary_image, config["merge_image_weight"], image_clahe, 1 - config["merge_image_weight"], 0)

            undistorted_binary = cv2.undistort(preprocessed_image, camera_matrix, dist)

            detection_list_binary = detector.detect(undistorted_binary, True, camera_params, config["qr_size"])

            for detection in detection_list_binary:
                if detection.center[0] > (middle_point_x * config["middle_area"]["min_x"]) and detection.center[0] < (middle_point_x * config["middle_area"]["max_x"]):
                    results_dict[config_name]["binary_detections"].append(detection)

                    if ObjectDetector._is_unique_detection(detection, output_list):
                        output_list.append(detection)

            if len(output_list) >= qr_number_func:
                return output_list, results_dict

            config_index += 1

        return output_list, results_dict

    @staticmethod
    def _is_unique_detection(detection, existing_detections, threshold_x=100, threshold_y=500):
        """
        Check if a detection is unique compared to existing detections.

        Args:
            detection: Current detection to check
            existing_detections: List of existing detections
            threshold: Distance threshold for considering detections as duplicates

        Returns:
            bool: True if detection is unique, False otherwise
        """
        for existing_detection in existing_detections:
            distance_x = abs(detection.center[0] - existing_detection.center[0])
            distance_y = abs(detection.center[1] - existing_detection.center[1])
            if distance_x < threshold_x and distance_y < threshold_y:
                return False
        return True
            

    @staticmethod
    def qr_output_process(detection_list, depth_original, message_logger, middle_point_y = 540):
        if detection_list is None or len(detection_list) == 0:
            return {1: None, 2: None, 3: None, 4: None}

        centers = []
        for detection in detection_list:
            min_x, min_y = (
                int(np.min(detection.corners[:, 0], axis=0)),
                int(np.min(detection.corners[:, 1], axis=0)),
            )
            max_x, max_y = (
                int(np.max(detection.corners[:, 0], axis=0)),
                int(np.max(detection.corners[:, 1], axis=0)),
            )
            cropped_depth_array = depth_original[min_y:max_y, min_x:max_x]
            z = np.median(cropped_depth_array) / 1000

            corners = detection.corners.tolist()

            detected = [
                detection.center[0],
                detection.center[1],
                corners,
                z,
                detection.pose_t,
                rotation_matrix_to_rvec(euler_to_rotation_matrix(0, 0, rotation_matrix_to_euler_angles(detection.pose_R)[2])),
            ]
            centers.append(detected)

        result = {1: None, 2: None, 3: None, 4: None}

        #TODO: ROTATION VERIFICATION - Potrzeba zdjęcia krzywego stosu QR
        
        for c in centers:
            y = c[1]
            rot_z = c[5][2]

            if y < middle_point_y:
                # Top row
                if rot_z < 0:
                    result[1] = c  # Top-left
                else:
                    result[3] = c  # Top-right
            else:
                # Bottom row
                if rot_z < 0:
                    result[2] = c  # Bottom-left
                else:
                    result[4] = c  # Bottom-right

        if result[1] is None and result[2] is None and result[3] is None and result[4] is None:
            error(f"OBJECT DETECTOR: no qr detected", message_logger)
            return {1: None, 2: None, 3: None, 4: None}

        return result
    

        # sorted_centers2 = {}

        # sorted_centers = sorted(centers, key=lambda point: (point[0]))

        # if len(sorted_centers) == 4:
        #     left = sorted_centers[0:2]
        #     right = sorted_centers[2:4]

        #     left_y = sorted(left, key=lambda point: (point[1]))
        #     right_y = sorted(right, key=lambda point: (point[1]))

        #     sorted_centers2 = {1: left_y[0], 2: left_y[1], 3: right_y[0], 4: right_y[1]}

        # elif len(sorted_centers) == 3:
        #     if abs(sorted_centers[0][0] - sorted_centers[1][0]) > abs(sorted_centers[1][0] - sorted_centers[2][0]):
        #         left = sorted_centers[0]
        #         right = sorted_centers[1:3]

        #         right_y = sorted(right, key=lambda point: (point[1]))

        #         if abs(right_y[0][1] - left[1]) > abs(right_y[1][1] - left[1]):
        #             sorted_centers2 = {1: None, 2: left, 3: right_y[0], 4: right_y[1]}
        #         else:
        #             sorted_centers2 = {1: left, 2: None, 3: right_y[0], 4: right_y[1]}

        #     else:
        #         left = sorted_centers[0:2]
        #         right = sorted_centers[2]

        #         left_y = sorted(left, key=lambda point: (point[1]))

        #         if abs(left_y[0][1] - right[1]) > abs(left_y[1][1] - right[1]):
        #             sorted_centers2 = {1: left_y[0], 2: left_y[1], 3: None, 4: right}
        #         else:
        #             sorted_centers2 = {1: left_y[0], 2: left_y[1], 3: right, 4: None}

        # elif len(sorted_centers) == 2:
        #     if abs(sorted_centers[0][0] - sorted_centers[1][0]) < 150:
        #         if sorted_centers[0][1] > sorted_centers[1][1]:
        #             upper = sorted_centers[1]
        #             lower = sorted_centers[0]
        #         else:
        #             upper = sorted_centers[0]
        #             lower = sorted_centers[1]
        #     else:
        #         upper = None
        #         lower = None

        #     return {1: None, 2: None, 3: upper, 4: lower}

        # elif len(sorted_centers) == 1:
        #     if sorted_centers[0][1] > 540:
        #         sorted_centers2 = {1: None, 2: None, 3: None, 4: sorted_centers[0]}
        #     else:
        #         sorted_centers2 = {1: None, 2: None, 3: sorted_centers[0], 4: None}

        # if sorted_centers2 == {}:
        #     error(f"OBJECT DETECTOR: no qr detected", message_logger)
        #     return {1: None, 2: None, 3: None, 4: None}

        # return sorted_centers2

    def calculate_3d_pose(focal_lengthx, focal_lengthy, ppx, ppy, x, y, z):
        """
        Calculate 3D world coordinates from 2D image coordinates and depth.

        Args:
            focal_lengthx: Focal length in x direction
            focal_lengthy: Focal length in y direction
            ppx: Principal point x coordinate
            ppy: Principal point y coordinate
            x: Image x coordinate
            y: Image y coordinate
            z: Depth value

        Returns:
            list: [X, Y, Z] coordinates in world space
        """
        # Przykładowe wartości
        camera_matrix = np.array([
            [focal_lengthx, 0, ppx, 0],
            [0, focal_lengthy, ppy, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ])

        # Odwróć macierz kamery, aby uzyskać transformację z przestrzeni obrazu do przestrzeni świata
        inv_camera_matrix = np.linalg.inv(camera_matrix)

        # Utwórz wektor współrzędnych pikseli z głębokością
        pixel_coordinates = np.array([x * z, y * z, z, 1])
        # Przemnóż wektor współrzędnych pikseli przez odwróconą macierz kamery, aby uzyskać współrzędne w przestrzeni
        world_coordinates = inv_camera_matrix.dot(pixel_coordinates)

        # Znormalizuj, aby ostatnia współrzędna była równa 1
        world_coordinates = world_coordinates / world_coordinates[-1]

        return world_coordinates[:3].tolist()

    def calculate_pose_pnp(
        corners,
        a,
        b,
        camera_params,
        z,
        dist_coeffs,
        tvec_initial=[],
        rvec_initial=[],
        test=False,
        offset=0,
        message_logger=None,
    ):
        """
        Calculate object pose using PnP algorithm.

        Args:
            corners: List of 4 corner points in image coordinates
            a: Object width
            b: Object height
            camera_params: Camera intrinsic parameters [fx, fy, cx, cy]
            z: Depth value
            dist_coeffs: Distortion coefficients
            tvec_initial: Initial translation vector (optional)
            rvec_initial: Initial rotation vector (optional)
            test: Boolean flag for test mode

        Returns:
            tuple: (tx, ty, tz, rx, ry, rz) containing translation and rotation
            If test=True: also returns reprojection error
        """
        camera_matrix = np.array(
            [
                [camera_params[0], 0, camera_params[2]],
                [0, camera_params[1], camera_params[3]],
                [0, 0, 1],
            ],
            dtype=np.float32,
        )
        dist = np.array([0, 0, 0, 0, 0], dtype=np.float32)

        # if len(rvec_initial) != 0 and len(tvec_initial) != 0:
        #     points_3d = np.array([
        #         [-a / 2, b / 2, 0],  # Dolny lewy róg
        #         [a / 2, b / 2, 0],   # Dolny prawy róg
        #         [a / 2, -b / 2, 0],  # Górny prawy róg
        #         [-a / 2, -b / 2, 0], # Górny lewy róg
        #         [0.0, 0.0, 0.0],    # Górny lewy róg
        #         [0.0, b, 0.0], # dół
        #         [a, 0.0, 0.0], # prawo
        #         [0.0, -b, 0.0], # góra
        #         [-a, 0.0, 0.0], # lewo
        #         ], dtype=np.float32)
        #     print(corners[0], corners[1], corners[2], corners[3])
        #     midpoints = np.array([(np.array(corners[0]) + np.array(corners[1])) / 2,
        #                         (np.array(corners[1]) + np.array(corners[2])) / 2,
        #                         (np.array(corners[2]) + np.array(corners[3])) / 2,
        #                         (np.array(corners[3]) + np.array(corners[0])) / 2], dtype=np.float32)
        #     base = np.array(corners, dtype=np.float32)
        #     corners = np.vstack((base, midpoints))

        # _, rot_vec, trans_vec = cv2.solvePnP(points_3d, corners, camera_matrix, dist, flags=cv2.SOLVEPNP_ITERATIVE, rvec=rvec_initial, tvec=tvec_initial, useExtrinsicGuess=True)

        # for i, point in enumerate(points_3d):
        #     points_3d[i] = point * zs
        # if tvec_initial == [] and rvec_initial == []:
        points_3d = np.array(
            [
                [-a / 2, b / 2, 0],  # Dolny lewy róg
                [a / 2, b / 2, 0],  # Dolny prawy róg
                [a / 2, -b / 2, 0],  # Górny prawy róg
                [-a / 2, -b / 2, 0],  # Górny lewy róg
                [0.0, 0.0, 0.0],  # Górny lewy róg
            ],
            dtype=np.float32,
        )
        corners = np.array(corners, dtype=np.float32)

        # print(f"Points 3d: {points_3d}")
        # print(f"Corners: {corners}")

        _, rot_vec, trans_vec = cv2.solvePnP(points_3d, corners, camera_matrix, dist, flags=cv2.SOLVEPNP_ITERATIVE)
        translation = trans_vec.flatten().tolist()
        rot_vec_flat = np.array([rot_vec]).flatten()  # Upewnij się, że rot_vec jest jednowymiarowy
        rotation = R.from_rotvec(rot_vec_flat)
        euler_angles = rotation.as_euler("xyz", degrees=True)
        # quat_modified = R.from_euler('xyz', (0.0, 0.0, euler_angles[2]-180), True).as_quat()

        # quaternion = rotation.as_quat()

        # BADANIE BŁĘDU REPROJEKCJI
        # imgpoints2, _ = cv2.projectPoints(points_3d, rot_vec, trans_vec, camera_matrix, dist)
        # reprojected_points = reprojected_points.squeeze()
        # error = cv2.norm(np.array(corners), imgpoints2, cv2.NORM_L2)/len(imgpoints2)
        # mean_error += error
        # print(error)

        # print(f'trans: {a}')
        # print(f'rot: {euler_angles}')

        if test is True:
            imgpoints2, _ = cv2.projectPoints(points_3d, rot_vec, trans_vec, camera_matrix, dist)
            imgpoints2 = imgpoints2.squeeze()
            error = cv2.norm(corners, imgpoints2, cv2.NORM_L2) / len(imgpoints2)

            # return (
            #     translation[0],
            #     translation[1],
            #     translation[2],
            #     quaternion[0],
            #     quaternion[1],
            #     quaternion[2],
            #     quaternion[3],
            #     error,
            # )
            return (
                translation[0],
                translation[1],
                translation[2],
                euler_angles[0],
                euler_angles[1],
                euler_angles[2],
                error,
            )

        else:
            if z is not None:
                debug(f"CAMERA CONTROLLER CALCULATE POSE: z from depth: {z} || From translation: {translation[2]}", message_logger=message_logger)
                return (
                    translation[0],
                    translation[1],
                    z * 1000,  # translation[2],
                    0.0,
                    0.0,
                    euler_angles[2],
                )
            else:
                debug(f"CAMERA CONTROLLER CALCULATE POSE: z from translation: {translation[2]} || From depth: None", message_logger=message_logger)
                return (
                    translation[0],
                    translation[1],
                    translation[2] + offset,
                    0.0,
                    0.0,
                    euler_angles[2],
                )

    def calibration_detector(self, image):
        """
        Detect calibration markers and sort them in specific order.

        Args:
            detector: Marker detector instance
            image: RGB image array

        Returns:
            list: Ordered list of 4 marker centers [top_left, top_right, bottom_right, bottom_left]
        """
        # Przekształcenie obrazu na skalę szarości
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        detection_list = detector.detect(gray_image)
        a = []
        for detection in detection_list:
            detected = {
                "tag_family": (str(detection.tag_family)),
                "tag_id": (detection.tag_id),
                "decision_margin": (detection.decision_margin),
                "center": (detection.center),
                "corners": (detection.corners),
            }
            a.append(detected)

        centers = []

        for qr in a:
            x, y = qr["center"][0], qr["center"][1]
            centers.append([x, y])

        # Sortowanie środków od lewej do prawej (według współrzędnej x)
        x_sorted_centers = sorted(centers, key=lambda x: x[0])

        left = x_sorted_centers[0:2]
        right = x_sorted_centers[2:4]

        if left[0][1] > left[1][1]:
            left[0], left[1] = left[1], left[0]

        if right[0][1] > right[1][1]:
            right[0], right[1] = right[1], right[0]

        order = [left[0], right[0], right[1], left[1]]

        return order

    def segment_box_hsv(self, color_image, config):
        """
        Segment box in image using HSV color thresholding.

        Args:
            color_image: RGB image array
            config: Dictionary with HSV threshold parameters

        Returns:
            tuple: (mask, debug) where:
                - mask: Binary mask of segmented box
                - debug: Dictionary with intermediate masks for debugging
        """
        debug = {}
        hsv_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv_image)

        mask_h = cv2.inRange(h, config["hsv_h_min"], config["hsv_h_max"])
        mask_s = cv2.inRange(s, config["hsv_s_min"], config["hsv_s_max"])
        mask_v = cv2.inRange(v, config["hsv_v_min"], config["hsv_v_max"])

        mask = mask_h & mask_s & mask_v
        debug["mask_h"] = mask_h
        debug["mask_s"] = mask_s
        debug["mask_v"] = mask_v

        return mask, debug

    def center_based_clipping(self, depth, config):
        """
        Calculate depth range for clipping based on center region of depth image.

        Args:
            depth: Depth image array
            config: Dictionary with clipping parameters

        Returns:
            list: [min_depth, max_depth] range for depth thresholding
        """
        center = (depth.shape[1] // 2, depth.shape[0] // 2)
        center_size = config["center_size"]

        median_depth = np.median(
            depth[
                center[1] - center_size : center[1] + center_size,
                center[0] - center_size : center[0] + center_size,
            ]
        )
        depth_range = [
            int(median_depth - config["depth_range"] - config["depth_bias"]),
            int(median_depth - config["depth_bias"]),
        ]

        return depth_range

    def depth_masking(self, depth, depth_range):
        """
        Create binary mask from depth image using threshold range.

        Args:
            depth: Depth image array
            depth_range: List of [min_depth, max_depth] values

        Returns:
            ndarray: Binary mask where depth values are within specified range
        """
        mask = cv2.inRange(depth, depth_range[0], depth_range[1])
        return mask
