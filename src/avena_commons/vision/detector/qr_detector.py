import traceback

import cv2
import pkg_resources

import avena_commons.vision.camera as camera
import avena_commons.vision.preprocess as preprocess
import avena_commons.vision.tag_reconstruction as tag_reconstruction
import avena_commons.vision.vision as vision
from avena_commons.util.logger import error


def qr_detector(*, detector, qr_image, camera_params, distortion_coefficients, config):
    debug_data = {}

    camera_matrix = camera.create_camera_matrix(camera_params)
    camera_distortion = camera.create_camera_distortion(distortion_coefficients)
    qr_image_undistorted = preprocess.undistort(
        qr_image, camera_matrix, camera_distortion
    )
    debug_data["qr_image_undistorted"] = qr_image_undistorted

    qr_image_undistorted_darkened = preprocess.darken_sides(
        qr_image_undistorted,
        top=0.0,
        bottom=0.0,
        left=0.3,
        right=0.3,
        darkness_factor=0.0,
    )
    debug_data["qr_image_undistorted_darkened"] = qr_image_undistorted_darkened

    detections = None
    match config["mode"]:
        case "gray":
            gray_image = preprocess.to_gray(qr_image_undistorted_darkened)
            # CLAHE
            image_clahe = preprocess.clahe(
                gray_image,
                clip_limit=config["clahe"]["clip_limit"],
                grid_size=config["clahe"]["grid_size"],
            )

            detections = detector.detect(  # apriltag detect
                image_clahe, True, camera_params, config["qr_size"]
            )

        case "gray_with_binarization":
            gray_image = preprocess.to_gray(qr_image_undistorted_darkened)
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

            detections = detector.detect(  # apriltag detect
                preprocessed_image, True, camera_params, config["qr_size"]
            )

        case "saturation":
            gray_image = preprocess.extract_saturation_channel(
                qr_image_undistorted_darkened
            )
            # CLAHE
            image_clahe = preprocess.clahe(
                gray_image,
                clip_limit=config["clahe"]["clip_limit"],
                grid_size=config["clahe"]["grid_size"],
            )

            detections = detector.detect(  # apriltag detect
                image_clahe, True, camera_params, config["qr_size"]
            )

        case "saturation_with_binarization":
            gray_image = preprocess.extract_saturation_channel(
                qr_image_undistorted_darkened
            )
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

            detections = detector.detect(  # apriltag detect
                preprocessed_image, True, camera_params, config["qr_size"]
            )

        case "tag_reconstruction":
            try:
                tag_path = pkg_resources.resource_filename(
                    "avena_commons.vision.data", "tag36h11-0.png"
                )
                tag_image = cv2.imread(tag_path)
                merged_image = tag_reconstruction.reconstruct_tags(
                    qr_image_undistorted_darkened,
                    tag_image,
                    config["tag_reconstruction"],
                )
                gray_image = preprocess.to_gray(merged_image)
                detections = detector.detect(
                    gray_image, True, camera_params, config["qr_size"]
                )
            except Exception as e:
                error(
                    f"OBJECT DETECTOR: tag reconstruction error: {e} traceback: {traceback.format_exc()}",
                )

        case _:
            raise ValueError(f"Invalid mode: {config['mode']}")

    return detections, debug_data
