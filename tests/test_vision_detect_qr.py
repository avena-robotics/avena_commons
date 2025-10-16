import argparse
import json
import os
import random
from pathlib import Path

import cv2
import numpy as np
from pupil_apriltags import Detector

from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import debug, error
from avena_commons.vision.detector import qr_detector

if __name__ == "__main__":
    path = "../challenging-3d-samples/dataset/qr_cold"

    parser = argparse.ArgumentParser(description="test_vision_detect_qr")
    parser.add_argument(
        "-c",
        "--clients",
        type=int,
        default=3,
        help="test clients number (default: 3)",
    )
    camera_params = [1378.84831, 1375.17821, 956.711425, 573.043875]
    distortion_coefficients = [
        0.12785771,
        -0.39385802,
        0.00286301,
        -0.0010572,
        0.35668062,
    ]
    config_detector = {
        "quad_decimate": 1.5,
        "quad_sigma": 1.5,
        "refine_edges": 1,
        "decode_sharpening": 0,
    }
    detector = Detector(**config_detector)

    qr_config_a = {
        "qr_size": 0.026,  # 0.026 #TODO: było 0.02 - małe tacki
        "mode": "gray",
        "clahe": {"clip_limit": 4.0, "grid_size": 8},
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    }
    qr_config_b = {
        "qr_size": 0.026,  # 0.026 #TODO: było 0.02 - małe tacki
        "mode": "gray_with_binarization",
        "clahe": {"clip_limit": 4.0, "grid_size": 8},
        "binarization": {
            "gamma": 3,
            "binarization": {"block_size": 31, "C": 1},
            "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
        },
        "merge_image_weight": 0.7,
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    }
    qr_config_c = {
        "qr_size": 0.026,  # 0.026 #TODO: było 0.02 - małe tacki
        "mode": "gray",
        "clahe": {"clip_limit": 1.0, "grid_size": 1},
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    }
    qr_config_d = {
        "qr_size": 0.026,  # 0.026 #TODO: było 0.02 - małe tacki
        "mode": "gray_with_binarization",
        "clahe": {"clip_limit": 1.0, "grid_size": 1},
        "binarization": {
            "gamma": 3,
            "binarization": {"block_size": 31, "C": 1},
            "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
        },
        "merge_image_weight": 0.7,
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    }
    qr_config_e = {
        "qr_size": 0.026,  # 0.026 #TODO: było 0.02 - małe tacki
        "mode": "saturation",
        "clahe": {"clip_limit": 4.0, "grid_size": 8},
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    }
    qr_config_f = {
        "qr_size": 0.026,  # 0.026 #TODO: było 0.02 - małe tacki
        "mode": "saturation_with_binarization",
        "clahe": {"clip_limit": 4.0, "grid_size": 8},
        "binarization": {
            "gamma": 3,
            "binarization": {"block_size": 31, "C": 1},
            "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
        },
        "merge_image_weight": 0.7,
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    }
    qr_config_g = {
        "qr_size": 0.026,  # 0.026 #TODO: było 0.02 - małe tacki
        "mode": "saturation",
        "clahe": {"clip_limit": 1.0, "grid_size": 1},
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    }
    qr_config_h = {
        "qr_size": 0.026,  # 0.026 #TODO: było 0.02 - małe tacki
        "mode": "saturation_with_binarization",
        "clahe": {"clip_limit": 1.0, "grid_size": 1},
        "binarization": {
            "gamma": 3,
            "binarization": {"block_size": 31, "C": 1},
            "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
        },
        "merge_image_weight": 0.7,
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    }
    qr_config_i = {
        "qr_size": 0.026,  # 0.026 #TODO: było 0.02 - małe tacki
        "mode": "tag_reconstruction",  # "tag_reconstruction", "saturation", "gray", "gray_with_binarization", "saturation_with_binarization"
        "tag_reconstruction": {
            "roi_config": {
                "horizontal_slice": (0.33, 0.66),
                "vertical_slice": (0.0, 1.0),  # Cała wysokość
                "overlap_fraction": 0.2,
            },
            "scene_corners": ["BL", "TR", "BL", "TR"],
            "central": False,
        },
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    }
    configs = [
        qr_config_a,
        qr_config_b,
        qr_config_c,
        qr_config_d,
        qr_config_e,
        qr_config_f,
        qr_config_g,
        qr_config_h,
        qr_config_i,
    ]

    args = parser.parse_args()

    temp_path = os.path.abspath("temp")
    os.makedirs(temp_path, exist_ok=True)

    message_logger = None

    try:
        json_files = sorted(Path(path).glob("*.json"))
        json_files = list(json_files)  # Konwersja Path objects na listę
        random.shuffle(json_files)  # Tasuje listę w miejscu

        # for set in os.listdir(path):
        for json_file in json_files:
            base_name = json_file.stem  # np. "0001" z "0001.json"
            parent_dir = json_file.parent
            png_file = parent_dir / f"{base_name}.png"
            if not png_file.exists():
                error(f"File does not exist: {png_file}")
                continue

            # wczytanie plików
            with open(json_file, "r") as f:
                json_data = json.load(f)
            png_image = cv2.imread(png_file)
            oczekiwana_ilosc_kodow = json_data["qr_number"]
            debug(f"Oczekuje na wynik: {oczekiwana_ilosc_kodow} kodów QR")

            with Catchtime() as t1:
                result1 = qr_detector(
                    qr_image=png_image,
                    qr_number=oczekiwana_ilosc_kodow,
                    detector=detector,
                    camera_params=camera_params,
                    distortion_coefficients=distortion_coefficients,
                    config=qr_config_a,
                )
            with Catchtime() as t2:
                result2 = qr_detector(
                    qr_image=png_image,
                    qr_number=oczekiwana_ilosc_kodow,
                    detector=detector,
                    camera_params=camera_params,
                    distortion_coefficients=distortion_coefficients,
                    config=qr_config_b,
                )
            with Catchtime() as t3:
                result3 = qr_detector(
                    qr_image=png_image,
                    qr_number=oczekiwana_ilosc_kodow,
                    detector=detector,
                    camera_params=camera_params,
                    distortion_coefficients=distortion_coefficients,
                    config=qr_config_c,
                )
            with Catchtime() as t4:
                result4 = qr_detector(
                    qr_image=png_image,
                    qr_number=oczekiwana_ilosc_kodow,
                    detector=detector,
                    camera_params=camera_params,
                    distortion_coefficients=distortion_coefficients,
                    config=qr_config_d,
                )
            with Catchtime() as t5:
                result5 = qr_detector(
                    qr_image=png_image,
                    qr_number=oczekiwana_ilosc_kodow,
                    detector=detector,
                    camera_params=camera_params,
                    distortion_coefficients=distortion_coefficients,
                    config=qr_config_e,
                )
            with Catchtime() as t6:
                result6 = qr_detector(
                    qr_image=png_image,
                    qr_number=oczekiwana_ilosc_kodow,
                    detector=detector,
                    camera_params=camera_params,
                    distortion_coefficients=distortion_coefficients,
                    config=qr_config_f,
                )
            with Catchtime() as t7:
                result7 = qr_detector(
                    qr_image=png_image,
                    qr_number=oczekiwana_ilosc_kodow,
                    detector=detector,
                    camera_params=camera_params,
                    distortion_coefficients=distortion_coefficients,
                    config=qr_config_g,
                )
            with Catchtime() as t8:
                result8 = qr_detector(
                    qr_image=png_image,
                    qr_number=0,
                    detector=detector,
                    camera_params=camera_params,
                    distortion_coefficients=distortion_coefficients,
                    config=qr_config_h,
                )
            with Catchtime() as t9:
                result9 = qr_detector(
                    qr_image=png_image,
                    qr_number=oczekiwana_ilosc_kodow,
                    detector=detector,
                    camera_params=camera_params,
                    distortion_coefficients=distortion_coefficients,
                    config=qr_config_i,
                )
            print(t1)
            print(t2)
            print(t3)
            print(t4)
            print(t5)
            print(t6)
            print(t7)
            print(t8)
            print(t9)
            print(
                f"result1: {len(result1)} {'sukces' if len(result1) == oczekiwana_ilosc_kodow else 'niepowodzenie'}"
            )
            print(
                f"result2: {len(result2)} {'sukces' if len(result2) == oczekiwana_ilosc_kodow else 'niepowodzenie'}"
            )
            print(
                f"result3: {len(result3)} {'sukces' if len(result3) == oczekiwana_ilosc_kodow else 'niepowodzenie'}"
            )
            print(
                f"result4: {len(result4)} {'sukces' if len(result4) == oczekiwana_ilosc_kodow else 'niepowodzenie'}"
            )
            print(
                f"result5: {len(result5)} {'sukces' if len(result5) == oczekiwana_ilosc_kodow else 'niepowodzenie'}"
            )
            print(
                f"result6: {len(result6)} {'sukces' if len(result6) == oczekiwana_ilosc_kodow else 'niepowodzenie'}"
            )
            print(
                f"result7: {len(result7)} {'sukces' if len(result7) == oczekiwana_ilosc_kodow else 'niepowodzenie'}"
            )
            print(
                f"result8: {len(result8)} {'sukces' if len(result8) == oczekiwana_ilosc_kodow else 'niepowodzenie'}"
            )
            print(
                f"result9: {len(result9)} {'sukces' if len(result9) == oczekiwana_ilosc_kodow else 'niepowodzenie'}"
            )
            # print(result)
            break
    except KeyboardInterrupt:
        pass
    except Exception as e:
        error(
            f"Nieoczekiwany błąd w głównym wątku: {e}",
            message_logger=message_logger,
        )
        raise e
        # signal_handler_processes(signal.SIGTERM, None, message_logger)
    finally:
        pass
