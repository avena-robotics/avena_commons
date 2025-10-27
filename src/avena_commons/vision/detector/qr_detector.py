from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np
import pkg_resources
import os
from datetime import datetime

import avena_commons.vision.camera as camera
import avena_commons.vision.image_preprocess as preprocess
import avena_commons.vision.tag_reconstruction as tag_reconstruction
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import error

# Global detector cache dla optymalizacji
_DETECTOR_CACHE = None
_TAG_IMAGE_CACHE = None


def _initialize_detector_safely() -> Optional[Any]:
    """Bezpieczna inicjalizacja detectora z obsługą błędów.

    Returns:
        Optional[Any]: Instancja detectora lub None przy błędzie.

    Raises:
        Exception: Obsłużone wewnętrznie, logowane jako error.
    """
    global _DETECTOR_CACHE

    if _DETECTOR_CACHE is not None:
        return _DETECTOR_CACHE

    try:
        from pupil_apriltags import Detector

        config_detector = {
            "quad_decimate": 1.5,
            "quad_sigma": 1.5,
            "refine_edges": 1,
            "decode_sharpening": 0,
        }

        _DETECTOR_CACHE = Detector(families="tag36h11", **config_detector)
        # debug("QR DETECTOR: Detector initialized successfully")
        return _DETECTOR_CACHE

    except Exception as e:
        # error(f"QR DETECTOR: Failed to initialize detector: {e}")
        return None


def _load_tag_image_safely() -> Optional[np.ndarray]:
    """Bezpieczne ładowanie obrazu tagu z cache.

    Returns:
        Optional[np.ndarray]: Obraz tagu lub None przy błędzie.

    Raises:
        Exception: Obsłużone wewnętrznie, logowane jako error.
    """
    global _TAG_IMAGE_CACHE

    if _TAG_IMAGE_CACHE is not None:
        return _TAG_IMAGE_CACHE

    try:
        tag_path = pkg_resources.resource_filename(
            "avena_commons.vision.data", "tag36h11-0.png"
        )
        _TAG_IMAGE_CACHE = cv2.imread(tag_path)

        if _TAG_IMAGE_CACHE is None:
            raise ValueError(f"Failed to load tag image from {tag_path}")

        # debug("QR DETECTOR: Tag image loaded successfully")
        return _TAG_IMAGE_CACHE

    except Exception as e:
        # error(f"QR DETECTOR: Failed to load tag image: {e}")
        return None


def qr_detector(
    *, frame: Dict[str, Any], camera_config: Dict[str, Any], config: Dict[str, Any]
) -> Tuple[Optional[Any], Dict[str, Any]]:
    """Wykryj QR/AprilTag w obrazie z robust error handling.

    Funkcja przetwarza obraz kamery w celu wykrycia tagów AprilTag
    z wykorzystaniem różnych trybów preprocessingu.

    Args:
        frame: Słownik z kluczami 'color', 'depth' zawierający ramki obrazu.
        camera_config: Konfiguracja kamery z parametrami kalibracji.
        config: Konfiguracja detectora z trybem przetwarzania.

    Returns:
        Tuple[Optional[Any], Dict[str, Any]]: Krotka (detections, debug_data).
        - detections: Lista wykrytych tagów lub None przy błędzie
        - debug_data: Słownik obrazów debug lub pusty przy błędzie

    Raises:
        Exception: Wszystkie wyjątki są przechwytywane i logowane.
    """
    debug_data = {}

    with Catchtime() as total_time:
        try:
            # Walidacja wejść
            if not frame or "color" not in frame:
                # error("QR DETECTOR: Invalid frame data - missing 'color' key")
                return None, debug_data

            if not camera_config or "camera_params" not in camera_config:
                # error("QR DETECTOR: Invalid camera_config - missing 'camera_params'")
                return None, debug_data

            if not config or "mode" not in config:
                # error("QR DETECTOR: Invalid config - missing 'mode'")
                return None, debug_data

            # Bezpieczna inicjalizacja detectora
            with Catchtime() as t:
                detector = _initialize_detector_safely()
                if detector is None:
                    # error("QR DETECTOR: Failed to initialize detector")
                    return None, debug_data

            # debug(f"QR DETECTOR: Detector ready in {t.ms:.4f} ms")

            # Przygotowanie parametrów kamery
            try:
                camera_params = (
                    camera_config["camera_params"][0],
                    camera_config["camera_params"][1],
                    camera_config["camera_params"][2],
                    camera_config["camera_params"][3],
                )

                camera_matrix = camera.create_camera_matrix(
                    camera_config["camera_params"]
                )
                camera_distortion = camera.create_camera_distortion(
                    camera_config["distortion_coefficients"]
                )
            except (KeyError, IndexError, TypeError) as e:
                # error(f"QR DETECTOR: Invalid camera parameters: {e}")
                return None, debug_data

            # Preprocessing obrazu
            try:
                with Catchtime() as preprocess_time:
                    qr_image_undistorted = preprocess.undistort(
                        frame["color"], camera_matrix, camera_distortion
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
                    debug_data["qr_image_undistorted_darkened"] = (
                        qr_image_undistorted_darkened
                    )

            except Exception as e:
                # error(f"QR DETECTOR: Image preprocessing failed: {e}")
                return None, debug_data

            # Wykrywanie według trybu
            detections = None
            mode = config.get("mode", "unknown")

            try:
                with Catchtime() as detection_time:
                    if mode == "gray":
                        detections = _process_gray_mode(
                            qr_image_undistorted_darkened,
                            detector,
                            camera_params,
                            config,
                            debug_data,
                        )

                    elif mode == "gray_with_binarization":
                        detections = _process_gray_with_binarization_mode(
                            qr_image_undistorted_darkened,
                            detector,
                            camera_params,
                            config,
                            debug_data,
                        )

                    elif mode == "saturation":
                        detections = _process_saturation_mode(
                            qr_image_undistorted_darkened,
                            detector,
                            camera_params,
                            config,
                            debug_data,
                        )

                    elif mode == "saturation_with_binarization":
                        detections = _process_saturation_with_binarization_mode(
                            qr_image_undistorted_darkened,
                            detector,
                            camera_params,
                            config,
                            debug_data,
                        )

                    elif mode == "tag_reconstruction":
                        detections = _process_tag_reconstruction_mode(
                            qr_image_undistorted_darkened,
                            detector,
                            camera_params,
                            config,
                            debug_data,
                        )

                    else:
                        # error(f"QR DETECTOR: Invalid mode: {mode}")
                        return None, debug_data

            except Exception as e:
                # error(f"QR DETECTOR: Detection failed in mode '{mode}': {e}")
                return None, debug_data

            # Dodaj pole z (głębia) do wykrytych tagów
            if detections and len(detections) > 0 and "depth" in frame:
                try:
                    depth_original = frame["depth"]
                    for detection in detections:
                        min_x, min_y = (
                            int(np.min(detection.corners[:, 0], axis=0)),
                            int(np.min(detection.corners[:, 1], axis=0)),
                        )
                        max_x, max_y = (
                            int(np.max(detection.corners[:, 0], axis=0)),
                            int(np.max(detection.corners[:, 1], axis=0)),
                        )

                        # Sprawdź czy współrzędne są w granicach obrazu
                        height, width = depth_original.shape[:2]
                        min_x = max(0, min_x)
                        min_y = max(0, min_y)
                        max_x = min(width, max_x)
                        max_y = min(height, max_y)

                        if max_x > min_x and max_y > min_y:
                            cropped_depth_array = depth_original[
                                min_y:max_y, min_x:max_x
                            ]
                            # Usuń wartości zerowe z macierzy głębi przed obliczeniem mediany
                            valid_depths = cropped_depth_array[cropped_depth_array > 0]
                            if len(valid_depths) > 0:
                                z = np.median(valid_depths) / 1000
                            else:
                                z = 0.0
                        else:
                            z = 0.0

                        # Dodaj pole z do obiektu detection
                        detection.z = z

                except Exception as depth_error:
                    error(f"QR DETECTOR: Błąd podczas obliczania głębi: {depth_error}")
                    # Ustaw z = 0.0 dla wszystkich wykryć w przypadku błędu
                    for detection in detections:
                        detection.z = 0.0
            # Stwórz wizualizację wykrytych tagów

            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                debug_dir = "temp/debug_frames_qr"
                os.makedirs(debug_dir, exist_ok=True)

                # if detections and len(detections) > 0:
                detection_visualization = create_qr_detection_visualization(
                    frame["color"], detections, timestamp, debug_dir
                )
                debug_data["qr_detection_visualization"] = detection_visualization
                # print(f"DEBUG: Stworzono wizualizację dla {len(detections)} tagów")
                # else:
                # print("DEBUG: Brak tagów do wizualizacji")

            except Exception as viz_error:
                error(f"DEBUG: Błąd podczas tworzenia wizualizacji: {viz_error}")

            debug(
                f"QR DETECTOR: Successfully processed mode '{mode}', found {len(detections) if detections else 0} detections"
            )
            return detections, debug_data

        except Exception as e:
            # error(f"QR DETECTOR: Unexpected error: {e}")
            # error(f"QR DETECTOR: Traceback: {traceback.format_exc()}")
            return None, debug_data


def _process_gray_mode(
    image: np.ndarray,
    detector: Any,
    camera_params: Tuple,
    config: Dict,
    debug_data: Dict,
) -> Optional[Any]:
    """Przetwórz obraz w trybie gray.

    Args:
        image: Obraz wejściowy.
        detector: Instancja detectora.
        camera_params: Parametry kamery.
        config: Konfiguracja.
        debug_data: Słownik do zapisywania obrazów debug.

    Returns:
        Optional[Any]: Wykrycia lub None przy błędzie.
    """
    try:
        gray_image = preprocess.to_gray(image)

        # CLAHE z walidacją parametrów
        clahe_config = config.get("clahe", {})
        image_clahe = preprocess.clahe(
            gray_image,
            clip_limit=clahe_config.get("clip_limit", 2.0),
            grid_size=clahe_config.get("grid_size", (8, 8)),
        )
        debug_data["image_clahe"] = image_clahe

        qr_size = config.get("qr_size", 0.1)
        return detector.detect(image_clahe, True, camera_params, qr_size)

    except Exception as e:
        # error(f"QR DETECTOR: Gray mode processing failed: {e}")
        return None


def _process_gray_with_binarization_mode(
    image: np.ndarray,
    detector: Any,
    camera_params: Tuple,
    config: Dict,
    debug_data: Dict,
) -> Optional[Any]:
    """Przetwórz obraz w trybie gray z binaryzacją.

    Args:
        image: Obraz wejściowy.
        detector: Instancja detectora.
        camera_params: Parametry kamery.
        config: Konfiguracja.
        debug_data: Słownik do zapisywania obrazów debug.

    Returns:
        Optional[Any]: Wykrycia lub None przy błędzie.
    """
    try:
        gray_image = preprocess.to_gray(image)

        # CLAHE
        clahe_config = config.get("clahe", {})
        image_clahe = preprocess.clahe(
            gray_image,
            clip_limit=clahe_config.get("clip_limit", 2.0),
            grid_size=clahe_config.get("grid_size", (8, 8)),
        )
        debug_data["image_clahe"] = image_clahe

        # Binaryzacja
        binary_config = config.get("binarization", {})
        binary_image = preprocess.binarize_and_clean(gray_image, binary_config)
        debug_data["binary_image"] = binary_image

        # Blending
        merge_weight = config.get("merge_image_weight", 0.5)
        blended_image = preprocess.blend(
            image1=binary_image,
            image2=image_clahe,
            merge_image_weight=merge_weight,
        )
        debug_data["blended_image"] = blended_image

        qr_size = config.get("qr_size", 0.1)
        return detector.detect(blended_image, True, camera_params, qr_size)

    except Exception as e:
        # error(f"QR DETECTOR: Gray with binarization mode processing failed: {e}")
        return None


def _process_saturation_mode(
    image: np.ndarray,
    detector: Any,
    camera_params: Tuple,
    config: Dict,
    debug_data: Dict,
) -> Optional[Any]:
    """Przetwórz obraz w trybie saturation.

    Args:
        image: Obraz wejściowy.
        detector: Instancja detectora.
        camera_params: Parametry kamery.
        config: Konfiguracja.
        debug_data: Słownik do zapisywania obrazów debug.

    Returns:
        Optional[Any]: Wykrycia lub None przy błędzie.
    """
    try:
        gray_image = preprocess.extract_saturation_channel(image)

        # CLAHE
        clahe_config = config.get("clahe", {})
        image_clahe = preprocess.clahe(
            gray_image,
            clip_limit=clahe_config.get("clip_limit", 2.0),
            grid_size=clahe_config.get("grid_size", (8, 8)),
        )
        debug_data["image_clahe"] = image_clahe

        qr_size = config.get("qr_size", 0.1)
        return detector.detect(image_clahe, True, camera_params, qr_size)

    except Exception as e:
        # error(f"QR DETECTOR: Saturation mode processing failed: {e}")
        return None


def _process_saturation_with_binarization_mode(
    image: np.ndarray,
    detector: Any,
    camera_params: Tuple,
    config: Dict,
    debug_data: Dict,
) -> Optional[Any]:
    """Przetwórz obraz w trybie saturation z binaryzacją.

    Args:
        image: Obraz wejściowy.
        detector: Instancja detectora.
        camera_params: Parametry kamery.
        config: Konfiguracja.
        debug_data: Słownik do zapisywania obrazów debug.

    Returns:
        Optional[Any]: Wykrycia lub None przy błędzie.
    """
    try:
        gray_image = preprocess.extract_saturation_channel(image)

        # CLAHE
        clahe_config = config.get("clahe", {})
        image_clahe = preprocess.clahe(
            gray_image,
            clip_limit=clahe_config.get("clip_limit", 2.0),
            grid_size=clahe_config.get("grid_size", (8, 8)),
        )
        debug_data["image_clahe"] = image_clahe

        # Binaryzacja
        binary_config = config.get("binarization", {})
        binary_image = preprocess.binarize_and_clean(gray_image, binary_config)
        debug_data["binary_image"] = binary_image

        # Blending
        merge_weight = config.get("merge_image_weight", 0.5)
        preprocessed_image = preprocess.blend(
            image1=binary_image,
            image2=image_clahe,
            merge_image_weight=merge_weight,
        )
        debug_data["preprocessed_image"] = preprocessed_image

        qr_size = config.get("qr_size", 0.1)
        return detector.detect(preprocessed_image, True, camera_params, qr_size)

    except Exception as e:
        # error(f"QR DETECTOR: Saturation with binarization mode processing failed: {e}")
        return None


def _process_tag_reconstruction_mode(
    image: np.ndarray,
    detector: Any,
    camera_params: Tuple,
    config: Dict,
    debug_data: Dict,
) -> Optional[Any]:
    """Przetwórz obraz w trybie tag reconstruction.

    Args:
        image: Obraz wejściowy.
        detector: Instancja detectora.
        camera_params: Parametry kamery.
        config: Konfiguracja.
        debug_data: Słownik do zapisywania obrazów debug.

    Returns:
        Optional[Any]: Wykrycia lub None przy błędzie.
    """
    try:
        # Bezpieczne załadowanie obrazu tagu
        tag_image = _load_tag_image_safely()
        if tag_image is None:
            # error("QR DETECTOR: Failed to load tag image for reconstruction")
            return None

        # Tag reconstruction
        reconstruction_config = config.get("tag_reconstruction", {})
        merged_image = tag_reconstruction.reconstruct_tags(
            image, tag_image, reconstruction_config
        )
        debug_data["merged_image"] = merged_image

        # Konwersja na grayscale i detekcja
        gray_image = preprocess.to_gray(merged_image)
        qr_size = config.get("qr_size", 0.1)
        return detector.detect(gray_image, True, camera_params, qr_size)

    except Exception as e:
        # error(f"QR DETECTOR: Tag reconstruction mode processing failed: {e}")
        # error(f"QR DETECTOR: Tag reconstruction traceback: {traceback.format_exc()}")
        return None


def create_qr_detection_visualization(color_image, detections, timestamp, debug_dir):
    """Tworzy wizualizację wykrytych QR/AprilTag z numerami pozycji w siatce.

    Rysuje krawędzie wykrytych tagów i ich numery pozycji w siatce sortującej.

    Args:
        color_image: Obraz kolorowy z kamery
        detections: Lista wykrytych tagów AprilTag
        timestamp: Znacznik czasu dla nazwy pliku
        debug_dir: Katalog do zapisu plików debug

    Returns:
        numpy.ndarray: Obraz z naniesioną wizualizacją zawierającą:
            - Krawędzie tagów (niebieskie linie)
            - Centrum tagów (czerwone kółko)
            - Numery pozycji w siatce (zielony tekst)
    """
    # Import funkcji sortującej
    from avena_commons.vision.sorter import sort_qr_by_center_position

    # Skopiuj obraz kolorowy aby nie modyfikować oryginału
    vis_image = color_image.copy()

    if not detections:
        print("DEBUG: Brak wykrytych tagów do wizualizacji")
        return vis_image

    print(f"DEBUG: Wizualizacja {len(detections)} wykrytych tagów")

    # Posortuj wykrycia według pozycji w siatce
    sorted_detections = sort_qr_by_center_position(4, detections)

    # Stwórz mapę detection -> pozycja dla łatwiejszego wyszukiwania
    detection_to_position = {}
    for position, detection in sorted_detections.items():
        if detection is not None:
            detection_to_position[id(detection)] = position

    # Kolory dla wizualizacji (BGR format dla OpenCV)
    line_color = (255, 0, 0)  # Niebieski dla linii krawędzi
    center_color = (0, 0, 255)  # Czerwony dla centrum
    text_color = (0, 255, 0)  # Zielony dla tekstu pozycji

    for detection in detections:
        # Pobierz dane z wykrycia
        center = detection.center
        corners = detection.corners

        # Konwertuj do int
        center_int = (int(center[0]), int(center[1]))
        corners_int = [(int(corner[0]), int(corner[1])) for corner in corners]

        # Znajdź pozycję tego wykrycia w siatce
        position = detection_to_position.get(id(detection), "?")

        print(
            f"DEBUG: Tag {detection.tag_id} - Center: {center_int}, Pozycja: {position}, Corners: {corners_int}"
        )

        # Narysuj centrum jako wypełnione koło
        cv2.circle(vis_image, center_int, 5, center_color, -1)

        # Połącz corners liniami aby stworzyć prostokąt
        for i in range(len(corners_int)):
            start_point = corners_int[i]
            end_point = corners_int[
                (i + 1) % len(corners_int)
            ]  # Następny punkt (z wraparound)
            cv2.line(vis_image, start_point, end_point, line_color, 2)

        # Dodaj numer pozycji w siatce obok centrum
        text_position = (center_int[0] + 15, center_int[1] - 15)
        cv2.putText(
            vis_image,
            str(position),
            text_position,
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,  # Rozmiar czcionki
            text_color,
            3,  # Grubość
            cv2.LINE_AA,
        )

    # Zapisz wizualizację
    vis_filename = f"{debug_dir}/qr_detection_visualization_{timestamp}.jpg"
    cv2.imwrite(vis_filename, vis_image)

    print(f"DEBUG: Wizualizacja QR z numerami pozycji zapisana do {vis_filename}")

    return vis_image
