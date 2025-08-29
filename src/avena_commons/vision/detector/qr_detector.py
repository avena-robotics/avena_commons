import traceback

import cv2
import pkg_resources

import avena_commons.vision.camera as camera
import avena_commons.vision.preprocess as preprocess
import avena_commons.vision.tag_reconstruction as tag_reconstruction
from avena_commons.util.logger import error


def qr_detector(
    *, detector, qr_image, qr_number, camera_params, distortion_coefficients, config
):
    results_dict = {}

    # match qr_number:
    #     case 0: # na wyjscie pieca
    #         qr_number_func = 1

    #         # TODO: QUICK FIX DO SOMETHING BETTER
    #         for config in configs:
    #             config["middle_area"]["min_x"] = 0.8
    #             config["middle_area"]["max_x"] = 1.4

    #             if config.get("tag_reconstruction", False):
    #                 config["tag_reconstruction_config"]["scene_corners"] = ["BL"]
    #                 config["tag_reconstruction_config"]["central"] = True # na wyjscie pi

    #     case 1: # szukamy 1 wiec maja byc 4
    #         qr_number_func = 4
    #     case 2: # szukamy 2 wiec maja byc 3
    #         qr_number_func = 3
    #     case 3: # szukamy 3 wiec maja byc 2
    #         qr_number_func = 2
    #     case 4: # szukamy 4 wiec maja byc 1
    #         qr_number_func = 1

    middle_point_x = camera_params[2]
    camera_matrix = camera.create_camera_matrix(camera_params)
    camera_distortion = camera.create_camera_distortion(distortion_coefficients)
    qr_image_undistorted = preprocess.undistort(
        qr_image, camera_matrix, camera_distortion
    )

    # config_index = 0

    # output_list = []

    # for idx, config in enumerate(configs):
    #     config_name = f"config_{chr(97 + idx)}"
    #     results_dict[config_name] = {
    #         "clahe_detections": [],
    #         "binary_detections": [],
    #         "reconstructed_detections": [],
    #     }

    detection = None
    match config["mode"]:
        case "gray":
            gray_image = preprocess.to_gray(qr_image_undistorted)
            # CLAHE
            image_clahe = preprocess.clahe(
                gray_image,
                clip_limit=config["clahe"]["clip_limit"],
                grid_size=config["clahe"]["grid_size"],
            )

            detection = detector.detect(  # apriltag detect
                image_clahe, True, camera_params, config["qr_size"]
            )

        case "gray_with_binarization":
            gray_image = preprocess.to_gray(qr_image_undistorted)
            # CLAHE
            image_clahe = preprocess.clahe(
                gray_image,
                clip_limit=config["clahe"]["clip_limit"],
                grid_size=config["clahe"]["grid_size"],
            )

            binary_image = preprocess.binarize_and_clean(
                gray_image, config["binarization"]
            )

            preprocessed_image = preprocess.blend(
                image1=binary_image,
                image2=image_clahe,
                merge_image_weight=config["merge_image_weight"],
            )

            detection = detector.detect(  # apriltag detect
                preprocessed_image, True, camera_params, config["qr_size"]
            )

        case "saturation":
            gray_image = preprocess.extract_saturation_channel(qr_image_undistorted)
            # CLAHE
            image_clahe = preprocess.clahe(
                gray_image,
                clip_limit=config["clahe"]["clip_limit"],
                grid_size=config["clahe"]["grid_size"],
            )

            detection = detector.detect(  # apriltag detect
                image_clahe, True, camera_params, config["qr_size"]
            )

        case "saturation_with_binarization":
            gray_image = preprocess.extract_saturation_channel(qr_image_undistorted)
            # CLAHE
            image_clahe = preprocess.clahe(
                gray_image,
                clip_limit=config["clahe"]["clip_limit"],
                grid_size=config["clahe"]["grid_size"],
            )

            binary_image = preprocess.binarize_and_clean(
                gray_image, config["binarization"]
            )

            preprocessed_image = preprocess.blend(
                image1=binary_image,
                image2=image_clahe,
                merge_image_weight=config["merge_image_weight"],
            )

            detection = detector.detect(  # apriltag detect
                preprocessed_image, True, camera_params, config["qr_size"]
            )

        case "tag_reconstruction":
            try:
                tag_path = pkg_resources.resource_filename(
                    "avena_commons.vision.data", "tag36h11-0.png"
                )
                tag_image = cv2.imread(tag_path)
                # tag_image = cv2.imread(
                #     "lib/supervisor_fairino/module/util/tag36h11-0.png"
                # )
                merged_image = tag_reconstruction.reconstruct_tags(
                    qr_image, tag_image, config["tag_reconstruction"]
                )
                gray_image = preprocess.to_gray(merged_image)
                detection = detector.detect(
                    gray_image, True, camera_params, config["qr_size"]
                )
            except Exception as e:
                error(
                    f"OBJECT DETECTOR: tag reconstruction error: {e} traceback: {traceback.format_exc()}",
                )

        case _:
            raise ValueError(f"Invalid mode: {config['mode']}")

    # for detection in detection_list_clahe:
    #     if detection.center[0] > (
    #         middle_point_x * config["middle_area"]["min_x"]
    #     ) and detection.center[0] < (
    #         middle_point_x * config["middle_area"]["max_x"]
    #     ):
    #         results_dict[config_name]["clahe_detections"].append(detection)
    #         if ObjectDetector._is_unique_detection(detection, output_list):
    #             output_list.append(detection)

    # if len(output_list) >= qr_number_func:
    #     return output_list, results_dict

    # BINARY

    # for detection in detection_list_binary:
    #     if detection.center[0] > (
    #         middle_point_x * config["middle_area"]["min_x"]
    #     ) and detection.center[0] < (
    #         middle_point_x * config["middle_area"]["max_x"]
    #     ):
    #         results_dict[config_name]["binary_detections"].append(detection)

    #         if ObjectDetector._is_unique_detection(detection, output_list):
    #             output_list.append(detection)

    # if len(output_list) >= qr_number_func:
    #     return output_list, results_dict

    # config_index += 1

    # return detection_list_clahe, detection_list_binary
    return detection
