import argparse
import asyncio
import concurrent.futures
import json
import multiprocessing as mp

# import logging
import os
import pickle
import random
import signal
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from pupil_apriltags import Detector

from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import (
    LoggerPolicyPeriod,
    MessageLogger,
    debug,
    error,
    info,
    warning,
)
from avena_commons.vision.detector import box_detector
from avena_commons.vision.old import ObjectDetector

# Globalny worker pool - będzie utworzony raz na początku programu
_worker_pool = None


def init_worker_pool(num_workers=2, use_concurrent_futures=False):
    """Inicjalizuj globalny worker pool"""
    global _worker_pool
    if _worker_pool is None:
        if use_concurrent_futures:
            _worker_pool = concurrent.futures.ProcessPoolExecutor(
                max_workers=num_workers
            )
        else:
            _worker_pool = mp.Pool(processes=num_workers)
    return _worker_pool


def cleanup_worker_pool():
    """Zamknij globalny worker pool"""
    global _worker_pool
    if _worker_pool is not None:
        if isinstance(_worker_pool, concurrent.futures.ProcessPoolExecutor):
            _worker_pool.shutdown(wait=True)
        else:
            _worker_pool.close()
            _worker_pool.join()
        _worker_pool = None


def run_box_detector_worker(args):
    """Worker function for multiprocessing"""
    (
        config_name,
        config_value,
        png_image,
        pkl_data,
        camera_params,
        distortion_coefficients,
    ) = args

    try:
        # Sprawdź na jakim rdzeniu działa proces
        import os

        pid = os.getpid()
        print(f"{config_name} działa na PID: {pid}")

        with Catchtime() as t:
            result = box_detector(
                color_image=png_image,
                depth_image=pkl_data,
                camera_params=camera_params,
                distortion_coefficients=distortion_coefficients,
                configs=[config_value],
            )
        return config_name, result, t.t, None
    except Exception as e:
        return config_name, None, 0, str(e)


def run_parallel_detectors_advanced(
    config, png_image, pkl_data, camera_params, distortion_coefficients
):
    """Run box detectors in parallel using persistent worker pool"""
    global _worker_pool

    # Upewnij się, że worker pool jest zainicjalizowany
    if _worker_pool is None:
        init_worker_pool()

    configs_to_test = [
        ("config_a", config),
        ("config_b", config),
        ("config_c", config),
    ]

    # Przygotuj argumenty dla każdego procesu
    args_list = [
        (
            name,
            config_value,
            png_image,
            pkl_data,
            camera_params,
            distortion_coefficients,
        )
        for name, config_value in configs_to_test
    ]

    # Sprawdź rozmiar danych wysyłanych do procesów
    import sys

    sample_args = args_list[0]
    try:
        # Przybliżony rozmiar danych (pickle może być inny)
        data_size = (
            sys.getsizeof(sample_args[1])  # config
            + sys.getsizeof(sample_args[2])  # png_image
            + sys.getsizeof(sample_args[3])  # pkl_data
            + sys.getsizeof(sample_args[4])  # camera_params
            + sys.getsizeof(sample_args[5])  # distortion_coefficients
        )
        print(f"Przybliżony rozmiar danych na proces: {data_size / 1024 / 1024:.2f} MB")
    except:
        print("Nie można obliczyć rozmiaru danych")

    # Pomiar czasu wysyłania danych do procesów
    if isinstance(_worker_pool, concurrent.futures.ProcessPoolExecutor):
        # Użyj concurrent.futures
        with Catchtime() as t_submit:
            futures = [
                _worker_pool.submit(run_box_detector_worker, args) for args in args_list
            ]
        print(f"Czas wysyłania zadań: {t_submit.t:.3f}s")

        with Catchtime() as t_execute:
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]
        print(f"Czas wykonania + odbierania wyników: {t_execute.t:.3f}s")
    else:
        # Użyj multiprocessing.Pool
        with Catchtime() as t_map:
            results = _worker_pool.map(run_box_detector_worker, args_list)
        print(f"Czas map (wysyłanie + wykonanie + odbieranie): {t_map.t:.3f}s")

    # Wyniki będą w formacie [(config_name, result, elapsed_time, error), ...]
    results_dict = {}
    for config_name, result, elapsed, error in results:
        if error:
            print(f"Błąd w {config_name}: {error}")
        else:
            results_dict[config_name] = result
            print(f"{config_name}: {elapsed:.3f}s")

    return results_dict


if __name__ == "__main__":
    # Inicjalizuj worker pool na początku programu
    # Spróbuj z 2 workerami - może 3 to za dużo dla tego systemu
    # Możesz przetestować obie implementacje:
    # init_worker_pool(num_workers=2, use_concurrent_futures=False)  # multiprocessing.Pool
    # init_worker_pool(num_workers=2, use_concurrent_futures=True)   # concurrent.futures.ProcessPoolExecutor

    init_worker_pool(num_workers=2, use_concurrent_futures=True)

    path = "C:/Users/lukasz.lecki/Documents/APS/challenging-3d-samples/dataset/box"

    parser = argparse.ArgumentParser(description="test_vision_detect_box")
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
    detector = ObjectDetector()
    config = {
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
            "depth": {
                "min_non_zero_percentage": 0.3,
                "center_size": 100,
                "depth_range": 35,
                "depth_bias": 44,
            },
            "hsv": {
                "hsv_h_min": 70,
                "hsv_h_max": 105,
                "hsv_s_min": 10,
                "hsv_s_max": 255,
                "hsv_v_min": 120,
                "hsv_v_max": 255,
            },
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
            "rect_validation": {
                "max_angle": 20,
                "box_ratio_range": [1.293, 1.387],
                "max_distance": 150,
            },
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
            "depth": {
                "min_non_zero_percentage": 0.3,
                "center_size": 100,
                "depth_range": 35,
                "depth_bias": 44,
            },
            "hsv": {
                "hsv_h_min": 70,
                "hsv_h_max": 105,
                "hsv_s_min": 10,
                "hsv_s_max": 255,
                "hsv_v_min": 100,
                "hsv_v_max": 255,
            },
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
            "rect_validation": {
                "max_angle": 20,
                "box_ratio_range": [1.293, 1.387],
                "max_distance": 150,
            },
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
                "depth_bias": 44,
            },
            "hsv": {
                "hsv_h_min": 70,
                "hsv_h_max": 105,
                "hsv_s_min": 50,
                "hsv_s_max": 255,
                "hsv_v_min": 120,
                "hsv_v_max": 255,
            },
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
            "rect_validation": {
                "max_angle": 20,
                "box_ratio_range": [1.295, 1.385],  # 1.29, 1.39
                "max_distance": 150,  # 300
            },
        },
    }
    # config = {
    #     "box_config_a": {
    #         "center_point": [1050, 550],
    #         "fix_depth_on": True,
    #         "fix_depth_config": {
    #             "closing_mask": {
    #                 "kernel_size": 10,
    #                 "iterations": 2,
    #             },
    #             "zero_mask": {
    #                 "kernel_size": 10,
    #                 "iterations": 2,
    #             },
    #             "r_wide": 2.0,
    #             "r_tall": 0.5,
    #             "final_closing_mask": {
    #                 "kernel_size": 10,
    #                 "iterations": 2,
    #             },
    #         },
    #         "depth": {
    #             "min_non_zero_percentage": 0.3,
    #             "center_size": 100,
    #             "depth_range": 35,
    #             "depth_bias": 44,
    #         },
    #         "hsv": {
    #             "hsv_h_min": 70,
    #             "hsv_h_max": 105,
    #             "hsv_s_min": 10,
    #             "hsv_s_max": 255,
    #             "hsv_v_min": 120,
    #             "hsv_v_max": 255,
    #         },
    #         "preprocess": {
    #             "blur_size": 15,
    #             "opened_kernel_type": cv2.MORPH_RECT,
    #             "opened_size": [2, 9],
    #             "opened_iterations": 3,
    #             "closed_size": [1, 9],
    #             "closed_iterations": 3,
    #             "closed_kernel_type": cv2.MORPH_ELLIPSE,
    #         },
    #         "remove_cnts": {"expected_width": 1150, "expected_height": 850},
    #         "edge_removal": {"edge_margin": 35},
    #         "hit_contours": {"angle_step": 10, "step_size": 1},
    #         "rect_validation": {
    #             "max_angle": 20,
    #             "box_ratio_range": [1.293, 1.387],
    #             "max_distance": 150,
    #         },
    #     },
    #     "box_config_b": {
    #         "center_point": [1050, 550],
    #         "fix_depth_on": True,
    #         "fix_depth_config": {
    #             "closing_mask": {
    #                 "kernel_size": 10,
    #                 "iterations": 2,
    #             },
    #             "zero_mask": {
    #                 "kernel_size": 10,
    #                 "iterations": 2,
    #             },
    #             "r_wide": 2.0,
    #             "r_tall": 0.5,
    #             "final_closing_mask": {
    #                 "kernel_size": 10,
    #                 "iterations": 2,
    #             },
    #         },
    #         "depth": {
    #             "min_non_zero_percentage": 0.3,
    #             "center_size": 100,
    #             "depth_range": 35,
    #             "depth_bias": 44,
    #         },
    #         "hsv": {
    #             "hsv_h_min": 70,
    #             "hsv_h_max": 105,
    #             "hsv_s_min": 10,
    #             "hsv_s_max": 255,
    #             "hsv_v_min": 100,
    #             "hsv_v_max": 255,
    #         },
    #         "preprocess": {
    #             "blur_size": 15,
    #             "opened_kernel_type": cv2.MORPH_RECT,
    #             "opened_size": [2, 9],
    #             "opened_iterations": 3,
    #             "closed_size": [1, 9],
    #             "closed_iterations": 6,
    #             "closed_kernel_type": cv2.MORPH_ELLIPSE,
    #         },
    #         "remove_cnts": {"expected_width": 1150, "expected_height": 850},
    #         "edge_removal": {"edge_margin": 50},
    #         "hit_contours": {"angle_step": 10, "step_size": 1},
    #         "rect_validation": {
    #             "max_angle": 20,
    #             "box_ratio_range": [1.293, 1.387],
    #             "max_distance": 150,
    #         },
    #     },
    #     "box_config_c": {
    #         "center_point": [1050, 550],
    #         "fix_depth_on": True,
    #         "fix_depth_config": {
    #             "closing_mask": {
    #                 "kernel_size": 10,
    #                 "iterations": 2,
    #             },
    #             "zero_mask": {
    #                 "kernel_size": 10,
    #                 "iterations": 2,
    #             },
    #             "r_wide": 2.0,
    #             "r_tall": 0.5,
    #             "final_closing_mask": {
    #                 "kernel_size": 10,
    #                 "iterations": 2,
    #             },
    #         },
    #         "depth": {
    #             "min_non_zero_percentage": 0.3,
    #             "center_size": 100,
    #             "depth_range": 35,
    #             "depth_bias": 44,
    #         },
    #         "hsv": {
    #             "hsv_h_min": 70,
    #             "hsv_h_max": 105,
    #             "hsv_s_min": 50,
    #             "hsv_s_max": 255,
    #             "hsv_v_min": 120,
    #             "hsv_v_max": 255,
    #         },
    #         "preprocess": {
    #             "blur_size": 15,
    #             "opened_kernel_type": cv2.MORPH_RECT,
    #             "opened_size": [2, 9],
    #             "opened_iterations": 3,
    #             "closed_size": [1, 9],
    #             "closed_iterations": 3,
    #             "closed_kernel_type": cv2.MORPH_ELLIPSE,
    #         },
    #         "remove_cnts": {"expected_width": 1150, "expected_height": 850},
    #         "edge_removal": {"edge_margin": 35},
    #         "hit_contours": {"angle_step": 10, "step_size": 1},
    #         "rect_validation": {
    #             "max_angle": 20,
    #             "box_ratio_range": [1.295, 1.385],  # 1.29, 1.39
    #             "max_distance": 150,  # 300
    #         },
    #     },
    # }
    args = parser.parse_args()

    temp_path = os.path.abspath("temp")
    os.makedirs(temp_path, exist_ok=True)

    message_logger = None

    try:
        json_files = sorted(Path(path).glob("*.json"))
        # for set in os.listdir(path):
        for json_file in json_files:
            base_name = json_file.stem  # np. "0001" z "0001.json"
            parent_dir = json_file.parent
            pkl_file = parent_dir / f"{base_name}.pkl"
            png_file = parent_dir / f"{base_name}.png"
            if not pkl_file.exists() or not png_file.exists():
                error(f"File does not exist: {pkl_file} or {png_file}")
                continue

            # wczytanie plików
            with open(json_file, "r") as f:
                json_data = json.load(f)
            with open(pkl_file, "rb") as f:  # zaladuj numpy array
                pkl_data = np.array(pickle.load(f))
            png_image = cv2.imread(png_file)

            # Uruchom równoległe detektory
            # with Catchtime() as t1:
            #     results = run_parallel_detectors_advanced(
            #         config,
            #         png_image,
            #         pkl_data,
            #         camera_params,
            #         distortion_coefficients,
            #     )
            # print(t1)
            # # Teraz możesz użyć wyników - każdy config ma swój result
            # result_a = results.get("config_a")
            # result_b = results.get("config_b")
            # result_c = results.get("config_c")

            # # Możesz dodać asercje lub dalsze testy na podstawie wyników
            # assert result_a is not None, "Config A nie zwrócił wyniku"
            # assert result_b is not None, "Config B nie zwrócił wyniku"
            # assert result_c is not None, "Config C nie zwrócił wyniku"
            with Catchtime() as t4:
                result = box_detector(
                    color_image=png_image,
                    depth_image=pkl_data,
                    camera_params=camera_params,
                    distortion_coefficients=distortion_coefficients,
                    config=config["box_config_a"],
                )
            # with Catchtime() as t5:
            #     result = detector.box_detector_sequential(
            #         color_image=png_image,
            #         depth_image=pkl_data,
            #         camera_params=camera_params,
            #         dist=distortion_coefficients,
            #         configs=[config["box_config_b"]],
            #     )
            # with Catchtime() as t6:
            #     result = detector.box_detector_sequential(
            #         color_image=png_image,
            #         depth_image=pkl_data,
            #         camera_params=camera_params,
            #         dist=distortion_coefficients,
            #         configs=[config["box_config_c"]],
            #     )

            # Czasy z multiprocessing są już wyświetlane w run_parallel_detectors_advanced
            print(t4)
            #     print(t5)
            # print(t6)
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
        # Zawsze zamknij worker pool na końcu
        cleanup_worker_pool()
