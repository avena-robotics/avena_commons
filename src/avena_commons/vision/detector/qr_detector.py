import traceback
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np
import pkg_resources

import avena_commons.vision.camera as camera
import avena_commons.vision.image_preprocess as preprocess
import avena_commons.vision.tag_reconstruction as tag_reconstruction
import avena_commons.vision.vision as vision
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import debug, error

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
        debug("QR DETECTOR: Detector initialized successfully")
        return _DETECTOR_CACHE
        
    except Exception as e:
        error(f"QR DETECTOR: Failed to initialize detector: {e}")
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
            
        debug("QR DETECTOR: Tag image loaded successfully")
        return _TAG_IMAGE_CACHE
        
    except Exception as e:
        error(f"QR DETECTOR: Failed to load tag image: {e}")
        return None


def qr_detector(*, frame: Dict[str, Any], camera_config: Dict[str, Any], config: Dict[str, Any]) -> Tuple[Optional[Any], Dict[str, Any]]:
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
    
    try:
        # Walidacja wejść
        if not frame or 'color' not in frame:
            error("QR DETECTOR: Invalid frame data - missing 'color' key")
            return None, debug_data
            
        if not camera_config or 'camera_params' not in camera_config:
            error("QR DETECTOR: Invalid camera_config - missing 'camera_params'")
            return None, debug_data
            
        if not config or 'mode' not in config:
            error("QR DETECTOR: Invalid config - missing 'mode'")
            return None, debug_data
        
        # Bezpieczna inicjalizacja detectora
        with Catchtime() as t:
            detector = _initialize_detector_safely()
            if detector is None:
                error("QR DETECTOR: Failed to initialize detector")
                return None, debug_data
                
        debug(f"QR DETECTOR: Detector ready in {t.ms:.4f} ms")
        
        # Przygotowanie parametrów kamery
        try:
            camera_params = (
                camera_config["camera_params"][0],
                camera_config["camera_params"][1],
                camera_config["camera_params"][2],
                camera_config["camera_params"][3],
            )
            
            camera_matrix = camera.create_camera_matrix(camera_config["camera_params"])
            camera_distortion = camera.create_camera_distortion(
                camera_config["distortion_coefficients"]
            )
        except (KeyError, IndexError, TypeError) as e:
            error(f"QR DETECTOR: Invalid camera parameters: {e}")
            return None, debug_data
        
        # Preprocessing obrazu
        try:
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
            debug_data["qr_image_undistorted_darkened"] = qr_image_undistorted_darkened
            
        except Exception as e:
            error(f"QR DETECTOR: Image preprocessing failed: {e}")
            return None, debug_data
        
        # Wykrywanie według trybu
        detections = None
        mode = config.get("mode", "unknown")
        
        try:
            if mode == "gray":
                detections = _process_gray_mode(
                    qr_image_undistorted_darkened, detector, camera_params, config, debug_data
                )
                
            elif mode == "gray_with_binarization":
                detections = _process_gray_with_binarization_mode(
                    qr_image_undistorted_darkened, detector, camera_params, config, debug_data
                )
                
            elif mode == "saturation":
                detections = _process_saturation_mode(
                    qr_image_undistorted_darkened, detector, camera_params, config, debug_data
                )
                
            elif mode == "saturation_with_binarization":
                detections = _process_saturation_with_binarization_mode(
                    qr_image_undistorted_darkened, detector, camera_params, config, debug_data
                )
                
            elif mode == "tag_reconstruction":
                detections = _process_tag_reconstruction_mode(
                    qr_image_undistorted_darkened, detector, camera_params, config, debug_data
                )
                
            else:
                error(f"QR DETECTOR: Invalid mode: {mode}")
                return None, debug_data
                
        except Exception as e:
            error(f"QR DETECTOR: Detection failed in mode '{mode}': {e}")
            return None, debug_data
        
        debug(f"QR DETECTOR: Successfully processed mode '{mode}', found {len(detections) if detections else 0} detections")
        return detections, debug_data
        
    except Exception as e:
        error(f"QR DETECTOR: Unexpected error: {e}")
        error(f"QR DETECTOR: Traceback: {traceback.format_exc()}")
        return None, debug_data


def _process_gray_mode(image: np.ndarray, detector: Any, camera_params: Tuple, config: Dict, debug_data: Dict) -> Optional[Any]:
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
        error(f"QR DETECTOR: Gray mode processing failed: {e}")
        return None


def _process_gray_with_binarization_mode(image: np.ndarray, detector: Any, camera_params: Tuple, config: Dict, debug_data: Dict) -> Optional[Any]:
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
        error(f"QR DETECTOR: Gray with binarization mode processing failed: {e}")
        return None


def _process_saturation_mode(image: np.ndarray, detector: Any, camera_params: Tuple, config: Dict, debug_data: Dict) -> Optional[Any]:
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
        error(f"QR DETECTOR: Saturation mode processing failed: {e}")
        return None


def _process_saturation_with_binarization_mode(image: np.ndarray, detector: Any, camera_params: Tuple, config: Dict, debug_data: Dict) -> Optional[Any]:
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
        error(f"QR DETECTOR: Saturation with binarization mode processing failed: {e}")
        return None


def _process_tag_reconstruction_mode(image: np.ndarray, detector: Any, camera_params: Tuple, config: Dict, debug_data: Dict) -> Optional[Any]:
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
            error("QR DETECTOR: Failed to load tag image for reconstruction")
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
        error(f"QR DETECTOR: Tag reconstruction mode processing failed: {e}")
        error(f"QR DETECTOR: Tag reconstruction traceback: {traceback.format_exc()}")
        return None
