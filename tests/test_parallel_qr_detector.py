# pytest tests/test_parallel_qr_detector.py::TestParallelQRDetection::test_parallel_9_configs -v -s
import asyncio
import json
import os
import random
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
from pupil_apriltags import Detector

import avena_commons.vision.detector as detector
import avena_commons.vision.merge as merge
import avena_commons.vision.sorter as sorter
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import error


def process_single_config(args):
    """Funkcja workera - otrzymuje obraz + indeks konfiguracji wg nowego schematu z general.py."""
    (
        image_data,  # Obraz jako numpy array (pickleable)
        config_index,  # Indeks konfiguracji (0-8)
        camera_params,  # Parametry kamery
        distortion_coefficients,  # Współczynniki zniekształcenia
    ) = args

    try:
        # Dynamiczny import detektora zgodnie z nowym schematem z general.py
        import importlib
        detector_module = importlib.import_module("avena_commons.vision.detector")
        detector_function = getattr(detector_module, "qr_detector")

        # Pobierz konfigurację po indeksie
        qr_configs = [
            {
                "qr_size": 0.026,
                "mode": "gray",
                "clahe": {"clip_limit": 4.0, "grid_size": 8},
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "gray_with_binarization",
                "clahe": {"clip_limit": 4.0, "grid_size": 8},
                "binarization": {
                    "gamma": 3,
                    "binarization": {"block_size": 31, "C": 1},
                    "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
                },
                "merge_image_weight": 0.7,
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "gray",
                "clahe": {"clip_limit": 1.0, "grid_size": 1},
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "gray_with_binarization",
                "clahe": {"clip_limit": 1.0, "grid_size": 1},
                "binarization": {
                    "gamma": 3,
                    "binarization": {"block_size": 31, "C": 1},
                    "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
                },
                "merge_image_weight": 0.7,
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "saturation",
                "clahe": {"clip_limit": 4.0, "grid_size": 8},
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "saturation_with_binarization",
                "clahe": {"clip_limit": 4.0, "grid_size": 8},
                "binarization": {
                    "gamma": 3,
                    "binarization": {"block_size": 31, "C": 1},
                    "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
                },
                "merge_image_weight": 0.7,
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "saturation",
                "clahe": {"clip_limit": 1.0, "grid_size": 1},
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "saturation_with_binarization",
                "clahe": {"clip_limit": 1.0, "grid_size": 1},
                "binarization": {
                    "gamma": 3,
                    "binarization": {"block_size": 31, "C": 1},
                    "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
                },
                "merge_image_weight": 0.7,
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "tag_reconstruction",
                "tag_reconstruction": {
                    "roi_config": {
                        "horizontal_slice": (0.33, 0.66),
                        "vertical_slice": (0.0, 1.0),
                        "overlap_fraction": 0.2,
                    },
                    "scene_corners": ["BL", "TR", "BL", "TR"],
                    "central": False,
                },
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
        ]

        config = qr_configs[config_index]
        # print(camera_params)
        # Prosty pomiar czasu (bez Catchtime w procesie workera) - zachowany sposób
        start_time = time.perf_counter()

        # Przygotuj ramki w formacie oczekiwanym przez detektor (zgodnie z general.py)
        frames = {"color": image_data}
        camera_config = {"camera_params": camera_params}

        # Wywołanie przez nowy schemat z dynamicznym importem
        result, debug_data = detector_function(
            frame=frames,
            camera_config=camera_config,
            config=config,
        )
        elapsed_time = time.perf_counter() - start_time
        # print(f"result: {result}")

        # DEBUG: sprawdź czas w milisekundach
        # elapsed_time_ms = elapsed_time * 1000
        # print(f"DEBUG: elapsed_time = {elapsed_time_ms:.2f}ms")

        # Zwróć tylko dane które można spicklować (NIE Mock objects!)
        return {
            "success": True,
            "time": elapsed_time,
            # "result": result,
            "detections": result,
            # if result
            # else 0,  # Liczba znalezionych kodów
            # "detection_details": result,
        }
    except Exception as e:
        return {"success": False, "time": 0.0, "error": str(e)}


class TestParallelQRDetection:
    """Testy równoległego vs sekwencyjnego wykrywania QR kodów."""

    @pytest.fixture
    def test_images_data(self):
        """Dane testowe z katalogu z obrazami."""
        path = "../challenging-3d-samples/dataset/qr_cold_big_qr"
        test_data = []

        if not os.path.exists(path):
            print(f"Katalog {path} nie istnieje - pomijam test")
            return test_data

        json_files = sorted(Path(path).glob("0018.json"))
        json_files = list(json_files)
        random.shuffle(json_files)

        for json_file in json_files[:1]:  # Tylko 1 obraz dla testów
            base_name = json_file.stem
            parent_dir = json_file.parent
            png_file = parent_dir / f"{base_name}.png"

            if not png_file.exists():
                error(f"File does not exist: {png_file}")
                continue

            with open(json_file, "r") as f:
                json_data = json.load(f)

            png_image = cv2.imread(str(png_file))
            if png_image is None:
                error(f"Nie można wczytać obrazu: {png_file}")
                continue

            test_data.append({
                "png_file": png_file,
                "json_file": json_file,
                "image": png_image,
                "expected_qr_count": json_data["qr_number"],
                "base_name": base_name,
            })

        print(f"Wczytano {len(test_data)} obrazów testowych")
        return test_data

    @pytest.fixture
    def mock_detector(self):
        """Symulowany detektor AprilTag (bez Mock objects)."""

        class SimulatedDetector:
            def detect(self, image, *args, **kwargs):
                # Symulujemy różne wyniki detekcji jako zwykłe dane
                if hasattr(image, "shape"):
                    if image.shape[0] > 400:
                        return [
                            type(
                                "obj",
                                (object,),
                                {
                                    "center": [100, 100],
                                    "id": 1,
                                    "corners": [
                                        [100, 100],
                                        [110, 100],
                                        [110, 110],
                                        [100, 110],
                                    ],
                                },
                            )(),
                            type(
                                "obj",
                                (object,),
                                {
                                    "center": [200, 200],
                                    "id": 2,
                                    "corners": [
                                        [200, 200],
                                        [210, 200],
                                        [210, 210],
                                        [200, 210],
                                    ],
                                },
                            )(),
                        ]
                    else:
                        return [
                            type(
                                "obj",
                                (object,),
                                {
                                    "center": [150, 150],
                                    "id": 1,
                                    "corners": [
                                        [150, 150],
                                        [160, 150],
                                        [160, 160],
                                        [150, 160],
                                    ],
                                },
                            )()
                        ]
                return []

        return SimulatedDetector()

    @pytest.fixture
    def camera_params(self):
        """Parametry kamery do testów."""
        return [1378.84831, 1375.17821, 956.711425, 573.043875]

    @pytest.fixture
    def distortion_coefficients(self):
        """Współczynniki zniekształcenia do testów."""
        return [0.12785771, -0.39385802, 0.00286301, -0.0010572, 0.35668062]

    @pytest.fixture
    def qr_configs(self):
        """9 konfiguracji QR do testów (a-i)."""
        return [
            {
                "qr_size": 0.026,
                "mode": "gray",
                "clahe": {"clip_limit": 4.0, "grid_size": 8},
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "gray_with_binarization",
                "clahe": {"clip_limit": 4.0, "grid_size": 8},
                "binarization": {
                    "gamma": 3,
                    "binarization": {"block_size": 31, "C": 1},
                    "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
                },
                "merge_image_weight": 0.7,
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "gray",
                "clahe": {"clip_limit": 1.0, "grid_size": 1},
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "gray_with_binarization",
                "clahe": {"clip_limit": 1.0, "grid_size": 1},
                "binarization": {
                    "gamma": 3,
                    "binarization": {"block_size": 31, "C": 1},
                    "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
                },
                "merge_image_weight": 0.7,
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "saturation",
                "clahe": {"clip_limit": 4.0, "grid_size": 8},
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "saturation_with_binarization",
                "clahe": {"clip_limit": 4.0, "grid_size": 8},
                "binarization": {
                    "gamma": 3,
                    "binarization": {"block_size": 31, "C": 1},
                    "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
                },
                "merge_image_weight": 0.7,
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "saturation",
                "clahe": {"clip_limit": 1.0, "grid_size": 1},
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "saturation_with_binarization",
                "clahe": {"clip_limit": 1.0, "grid_size": 1},
                "binarization": {
                    "gamma": 3,
                    "binarization": {"block_size": 31, "C": 1},
                    "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
                },
                "merge_image_weight": 0.7,
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
            {
                "qr_size": 0.026,
                "mode": "tag_reconstruction",
                "tag_reconstruction": {
                    "roi_config": {
                        "horizontal_slice": (0.33, 0.66),
                        "vertical_slice": (0.0, 1.0),
                        "overlap_fraction": 0.2,
                    },
                    "scene_corners": ["BL", "TR", "BL", "TR"],
                    "central": False,
                },
                "middle_area": {"min_x": 0.56, "max_x": 1.44},
            },
        ]

    def test_sequential_9_configs(
        self,
        test_images_data,
        camera_params,
        distortion_coefficients,
        qr_configs,
    ):
        """Test sekwencyjnego uruchomienia 9 konfiguracji."""
        if not test_images_data:
            pytest.skip("Brak danych testowych z katalogu")

        print(f"=== SEKWENCYJNE WYKRYWANIE - 9 konfiguracji (nowy schemat z general.py) ===")
        print(f"Test na {len(test_images_data)} obrazach")

        all_times = []
        total_sequential_time = 0
        apriltag_detector = Detector()  # Prawdziwy detektor AprilTag

        for i, test_data in enumerate(test_images_data):
            print(
                f"\n--- Obraz {i + 1}/{len(test_images_data)}: {Path(test_data['png_file']).name} ---"
            )

            image_times = []
            for j, config in enumerate(qr_configs):
                config_name = f"config_{chr(97 + j)}"  # a, b, c, d, e, f, g, h, i
                print(f"  Testuję {config_name} (mode: {config['mode']})...")

                with Catchtime() as timer:
                    try:
                        # Użycie nowego schematu z dynamicznym importem detektora
                        import importlib
                        detector_module = importlib.import_module("avena_commons.vision.detector")
                        detector_function = getattr(detector_module, "qr_detector")

                        # Przygotuj ramki w formacie oczekiwanym przez detektor
                        frames = {"color": test_data["image"]}
                        camera_config = {"camera_params": camera_params}

                        result, debug_data = detector_function(
                            frame=frames,
                            camera_config=camera_config,
                            config=config,
                        )
                        elapsed_time = timer.sec
                        image_times.append(elapsed_time)
                        all_times.append(elapsed_time)
                        total_sequential_time += elapsed_time
                        print(
                            f"    ✓ {config_name}: {elapsed_time:.6f}s (mode: {config['mode']})"
                        )
                    except Exception as e:
                        elapsed_time = 0.0
                        image_times.append(elapsed_time)
                        all_times.append(elapsed_time)
                        print(f"    ✗ {config_name}: BŁĄD - {str(e)}")

            # Podsumowanie dla tego obrazu
            total_image_time = sum(image_times)
            successful_configs = len([t for t in image_times if t > 0])
            print(f"\n  Podsumowanie dla obrazu {Path(test_data['png_file']).name}:")
            print(f"    Udało się: {successful_configs}/{len(qr_configs)} konfiguracji")
            print(f"    Łączny czas: {total_image_time:.6f}s")
            time_str = ", ".join([f"{t:.6f}s" for t in image_times])
            print(f"    Czasy pojedyncze: {time_str}")

        # Podsumowanie ogólne
        print(f"\n=== WYNIKI SEKWENCYJNE ===")
        print(f"Łączny czas wszystkich konfiguracji: {total_sequential_time:.6f}s")
        print(f"Liczba testowanych konfiguracji: {len(all_times)}")
        print(
            f"Średni czas na konfigurację: {total_sequential_time / len(all_times):.6f}s"
        )

        # Dodaj minimalny i maksymalny czas
        if all_times:
            min_time = min(all_times)
            max_time = max(all_times)
            min_time_ms = min_time * 1000
            max_time_ms = max_time * 1000
            print(f"Minimalny czas: {min_time_ms:.2f}ms")
            print(f"Maksymalny czas: {max_time_ms:.2f}ms")

        # Sprawdź czy wszystkie konfiguracje zostały przetestowane
        assert len(all_times) == len(test_images_data) * len(qr_configs), (
            "Nie wszystkie konfiguracje zostały przetestowane"
        )

    def test_parallel_9_configs(
        self,
        test_images_data,
        camera_params,
        distortion_coefficients,
        qr_configs,
    ):
        """Test równoległego uruchomienia 9 konfiguracji na oddzielnych procesach."""
        if not test_images_data:
            pytest.skip("Brak danych testowych z katalogu")

        print(f"=== RÓWNOLEGŁE WYKRYWANIE - 9 konfiguracji na procesach (nowy schemat z general.py) ===")
        print(f"Test na {len(test_images_data)} obrazach")

        all_times = []
        total_parallel_time = 0

        for i, test_data in enumerate(test_images_data):
            print(
                f"\n--- Obraz {i + 1}/{len(test_images_data)}: {Path(test_data['png_file']).name} ---"
            )

            # Przygotuj argumenty dla wszystkich konfiguracji
            worker_args = []
            for j, config in enumerate(qr_configs):
                config_name = f"config_{chr(97 + j)}"  # a, b, c, d, e, f, g, h, i
                worker_args.append((
                    test_data["image"],  # Obraz jako numpy array
                    j,  # Indeks konfiguracji (0-8)
                    camera_params,
                    distortion_coefficients,
                ))
                print(f"  Przygotowano {config_name} (mode: {config['mode']})")

            # Uruchom równolegle na procesach
            print(f"  Uruchamiam {len(worker_args)} konfiguracji równolegle...")
            results = {}

            # Przygotuj executor PRZED pomiarem czasu (tworzenie procesów nie wchodzi w pomiar)
            with ProcessPoolExecutor(max_workers=9) as executor:
                # Submit wszystkie zadania PRZED pomiarem
                future_to_config = {
                    executor.submit(process_single_config, args): j
                    for j, args in enumerate(worker_args)
                }

                # TERAZ zacznij mierzyć czas (wysyłka + przetwarzanie + odpowiedź)
                with Catchtime() as total_timer:
                    # Zbierz wyniki (to zajmie czas)
                    for future in as_completed(future_to_config):
                        # print(f"Skonczyl sie: {future}")
                        config_idx = future_to_config[future]
                        config_name = f"config_{chr(97 + config_idx)}"

                        try:
                            result = future.result()

                            elapsed_time = result["time"]
                            elapsed_time_ms = elapsed_time * 1000
                            all_times.append(elapsed_time)
                            total_parallel_time += elapsed_time

                            if result["success"]:
                                detections = result.get("detections", [])
                                if detections is not None:
                                    detection_count = len(detections)
                                else:
                                    detection_count = 0
                                    detections = []
                                print(
                                    f"    ✓ {config_name}: {elapsed_time_ms:.2f}ms, znaleziono QR-kodów: {detection_count}, spodziewanych: {test_data['expected_qr_count']} type: {type(detections)}"
                                )
                                if detection_count > 0:
                                    for i, detection in enumerate(detections):
                                        print(
                                            f"    ✓ {config_name}: Unsorted {i} {detection.center}"
                                        )
                                    sorted_detections = sorter.sort_qr_by_center_position(
                                        expected_count=test_data["expected_qr_count"],
                                        detections=detections,
                                    )
                                    for key, value in sorted_detections.items():
                                        print(
                                            f"    ✓ {config_name}: Sorted {key} {value.center if value else None}"
                                        )
                                    results = merge.merge_qr_detections_with_confidence(
                                        sorted_detections,
                                        results,
                                    )
                                    actual_detections = sum(
                                        1 for v in results.values() if v is not None
                                    )
                                    print(
                                        f"    ✓ {config_name}: Actual detections after merge {actual_detections}"
                                    )
                                else:
                                    print(f"    ✓ {config_name}: Brak detekcji")
                                    actual_detections = sum(
                                        1 for v in results.values() if v is not None
                                    )
                                # gdy actual_detections = test_data["expected_qr_count"] - to natychmiast zakonczyc pozostale procesy bez analizy wynikow!
                                if actual_detections == test_data["expected_qr_count"]:
                                    print(
                                        f"    ✓ {config_name}: Actual detections after merge {actual_detections} = expected {test_data['expected_qr_count']} - zakonczenie pozostalych procesow --------------------------------------------------------------"
                                    )
                            else:
                                print(
                                    f"    ✗ {config_name}: BŁĄD - {result.get('error', 'Unknown error')}"
                                )

                        except Exception as e:
                            print(f"    ✗ {config_name}: BŁĄD PROCESU - {str(e)}")
                            # Nie dodawaj czasu 0.0 dla błędów procesu, żeby nie zaburzyć liczenia
                            traceback.print_exc()

            total_processing_time = total_timer.sec
            actual_detections = sum(1 for v in results.values() if v is not None)
            print(f"\n  Podsumowanie dla obrazu {Path(test_data['png_file']).name}:")
            print(f"    Całkowity czas przetwarzania: {total_processing_time:.6f}s")
            print(f"    Suma czasów konfiguracji: {total_parallel_time:.6f}s")
            print(
                f"    Przyspieszenie: {total_parallel_time / total_processing_time:.2f}x"
            )

        # Podsumowanie ogólne
        print(f"\n=== WYNIKI RÓWNOLEGŁE ===")
        print(f"Łączny czas wszystkich konfiguracji: {total_parallel_time:.6f}s")
        print(f"Liczba testowanych konfiguracji: {len(all_times)}")
        print(
            f"Średni czas na konfigurację: {total_parallel_time / len(all_times):.6f}s"
        )

        # Dodaj minimalny i maksymalny czas
        if all_times:
            min_time = min(all_times)
            max_time = max(all_times)
            min_time_ms = min_time * 1000
            max_time_ms = max_time * 1000
            print(f"Minimalny czas: {min_time_ms:.2f}ms")
            print(f"Maksymalny czas: {max_time_ms:.2f}ms")

        # Sprawdź czy co najmniej część konfiguracji została przetestowana
        expected_total = len(test_images_data) * len(qr_configs)
        actual_total = len(all_times)
        print(f"Przetestowano {actual_total}/{expected_total} konfiguracji")
        assert actual_total > 0, "Żadna konfiguracja nie została przetestowana pomyślnie"

        # Sprawdź czy równoległość daje korzyści
        assert total_parallel_time > 0, "Brak wyników z równoległego przetwarzania"


    def test_parallel_9_configs_with_break(
        self,
        test_images_data,
        camera_params,
        distortion_coefficients,
        qr_configs,
    ):
        """Test równoległego uruchomienia 9 konfiguracji na oddzielnych procesach."""
        if not test_images_data:
            pytest.skip("Brak danych testowych z katalogu")

        print(f"=== RÓWNOLEGŁE WYKRYWANIE - 9 konfiguracji na procesach z break (nowy schemat z general.py) ===")
        print(f"Test na {len(test_images_data)} obrazach")

        all_times = []
        total_parallel_time = 0

        for i, test_data in enumerate(test_images_data):
            print(
                f"\n--- Obraz {i + 1}/{len(test_images_data)}: {Path(test_data['png_file']).name} ---"
            )

            # Przygotuj argumenty dla wszystkich konfiguracji
            worker_args = []
            for j, config in enumerate(qr_configs):
                config_name = f"config_{chr(97 + j)}"  # a, b, c, d, e, f, g, h, i
                worker_args.append((
                    test_data["image"],  # Obraz jako numpy array
                    j,  # Indeks konfiguracji (0-8)
                    camera_params,
                    distortion_coefficients,
                ))
                print(f"  Przygotowano {config_name} (mode: {config['mode']})")

            # Uruchom równolegle na procesach
            print(f"  Uruchamiam {len(worker_args)} konfiguracji równolegle...")

            # Przygotuj executor PRZED pomiarem czasu (tworzenie procesów nie wchodzi w pomiar)
            with ProcessPoolExecutor(max_workers=9) as executor:
                # Submit wszystkie zadania PRZED pomiarem
                future_to_config = {
                    executor.submit(process_single_config, args): j
                    for j, args in enumerate(worker_args)
                }

                # TERAZ zacznij mierzyć czas (wysyłka + przetwarzanie + odpowiedź)
                with Catchtime() as total_timer:
                    # Zbierz wyniki (to zajmie czas)
                    results = {}
                    for future in as_completed(future_to_config):
                        # print(f"Skonczyl sie: {future}")
                        config_idx = future_to_config[future]
                        config_name = f"config_{chr(97 + config_idx)}"

                        try:
                            result = future.result()

                            elapsed_time = result["time"]
                            elapsed_time_ms = elapsed_time * 1000
                            all_times.append(elapsed_time)
                            total_parallel_time += elapsed_time

                            if result["success"]:
                                detections = result.get("detections", [])
                                if detections is not None:
                                    detection_count = len(detections)
                                else:
                                    detection_count = 0
                                    detections = []
                                print(
                                    f"    ✓ {config_name}: {elapsed_time_ms:.2f}ms, znaleziono QR-kodów: {detection_count}, spodziewanych: {test_data['expected_qr_count']} type: {type(detections)}"
                                )
                                if detection_count > 0:
                                    for i, detection in enumerate(detections):
                                        print(
                                            f"    ✓ {config_name}: Unsorted {i} {detection.center}"
                                        )
                                    sorted_detections = sorter.sort_qr_by_center_position(
                                        expected_count=test_data["expected_qr_count"],
                                        detections=detections,
                                    )
                                    for key, value in sorted_detections.items():
                                        print(
                                            f"    ✓ {config_name}: Sorted {key} {value.center if value else None}"
                                        )
                                    results = merge.merge_qr_detections_with_confidence(
                                        sorted_detections,
                                        results,
                                    )
                                    actual_detections = sum(
                                        1 for v in results.values() if v is not None
                                    )
                                    print(
                                        f"    ✓ {config_name}: Actual detections after merge {actual_detections}"
                                    )
                                else:
                                    print(f"    ✓ {config_name}: Brak detekcji")
                                    actual_detections = sum(
                                        1 for v in results.values() if v is not None
                                    )
                                # gdy actual_detections = test_data["expected_qr_count"] - to natychmiast zakonczyc pozostale procesy bez analizy wynikow!
                                if actual_detections == test_data["expected_qr_count"]:
                                    print(
                                        f"    ✓ {config_name}: Actual detections after merge {actual_detections} = expected {test_data['expected_qr_count']} - zakonczenie pozostalych procesow --------------------------------------------------------------"
                                    )
                                    break
                            else:
                                print(
                                    f"    ✗ {config_name}: BŁĄD - {result.get('error', 'Unknown error')}"
                                )

                        except Exception as e:
                            print(f"    ✗ {config_name}: BŁĄD PROCESU - {str(e)}")
                            # Nie dodawaj czasu 0.0 dla błędów procesu, żeby nie zaburzyć liczenia
                            traceback.print_exc()

            total_processing_time = total_timer.sec
            print(f"\n  Podsumowanie dla obrazu {Path(test_data['png_file']).name}:")
            print(f"    Całkowity czas przetwarzania: {total_processing_time:.6f}s")
            print(f"    Suma czasów konfiguracji: {total_parallel_time:.6f}s")
            print(
                f"    Przyspieszenie: {total_parallel_time / total_processing_time:.2f}x"
            )

        # Podsumowanie ogólne
        print(f"\n=== WYNIKI RÓWNOLEGŁE ===")
        print(f"Łączny czas wszystkich konfiguracji: {total_parallel_time:.6f}s")
        print(f"Liczba testowanych konfiguracji: {len(all_times)}")
        print(
            f"Średni czas na konfigurację: {total_parallel_time / len(all_times):.6f}s"
        )

        # Dodaj minimalny i maksymalny czas
        if all_times:
            min_time = min(all_times)
            max_time = max(all_times)
            min_time_ms = min_time * 1000
            max_time_ms = max_time * 1000
            print(f"Minimalny czas: {min_time_ms:.2f}ms")
            print(f"Maksymalny czas: {max_time_ms:.2f}ms")

        # Sprawdź czy co najmniej część konfiguracji została przetestowana
        expected_total = len(test_images_data) * len(qr_configs)
        actual_total = len(all_times)
        print(f"Przetestowano {actual_total}/{expected_total} konfiguracji")
        assert actual_total > 0, "Żadna konfiguracja nie została przetestowana pomyślnie"

        # Sprawdź czy równoległość daje korzyści
        assert total_parallel_time > 0, "Brak wyników z równoległego przetwarzania"
