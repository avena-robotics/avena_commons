"""GPU acceleration utilities for pepper vision processing.

Provides batch GPU operations using OpenCV CUDA and CuPy for efficient
image processing on GPU. Designed for batch processing of multiple fragments
simultaneously to maximize GPU utilization.

Features:
- Batch color space conversions (BGR→HSV, BGR→LAB)
- Batch morphological operations
- Batch thresholding and masking
- CUDA stream management for parallel operations
- Automatic fallback to CPU if GPU unavailable

Requires:
- OpenCV with CUDA support (cv2.cuda)
- CuPy for advanced GPU array operations

Exposes:
- Class `GPUBatchProcessor` (main GPU processing interface)
- Function `check_gpu_available()` (GPU capability check)
"""

import warnings
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

try:
    import cupy as cp
    CUPY_AVAILABLE = True
except ImportError:
    CUPY_AVAILABLE = False
    warnings.warn("CuPy not available - some GPU operations will be limited")


def check_gpu_available(init_device: bool = False) -> Tuple[bool, str]:
    """Check if GPU acceleration is available.
    
    IMPORTANT: By default, this function does NOT initialize CUDA (safe for multiprocessing).
    Only checks device count without calling getDevice() which would initialize CUDA context.
    
    Args:
        init_device (bool): If True, also initialize device (NOT safe before fork!)
    
    Returns:
        Tuple[bool, str]: (is_available, info_message)
    """
    try:
        cuda_count = cv2.cuda.getCudaEnabledDeviceCount()
        if cuda_count > 0:
            if init_device:
                # Only call getDevice() if explicitly requested (e.g. in worker process)
                device_name = cv2.cuda.getDevice()
                return True, f"CUDA available: {cuda_count} device(s), using device {device_name}"
            else:
                # Safe check - don't initialize CUDA (for parent process before fork)
                return True, f"CUDA available: {cuda_count} device(s)"
        else:
            return False, "No CUDA-enabled devices found"
    except Exception as e:
        return False, f"CUDA check failed: {e}"


def _apply_clahe_robust(clahe_filter, gpu_img, stream):
    """Apply CLAHE robustly across OpenCV build variants.
    
    OpenCV has two different signatures for CLAHE apply():
    - Variant A: apply(src[, stream]) -> dst (returns new GpuMat)
    - Variant B: apply(src, dst[, stream]) -> None (requires dst)
    
    This function tries Variant A first, then falls back to Variant B.
    
    Args:
        clahe_filter: CUDA CLAHE filter object
        gpu_img: Input GpuMat (must be CV_8UC1)
        stream: CUDA stream or None
        
    Returns:
        cv2.cuda_GpuMat: Result of CLAHE operation
    """
    # Ensure CV_8UC1 (CLAHE requirement)
    if gpu_img.type() != cv2.CV_8UC1:
        # Convert to grayscale if multi-channel
        if gpu_img.channels() > 1:
            gpu_img = cv2.cuda.cvtColor(gpu_img, cv2.COLOR_BGR2GRAY, stream=stream)
    
    # Try Variant A first (shorter signature, returns dst)
    try:
        if stream is not None:
            return clahe_filter.apply(gpu_img, stream)  # Positional stream
        else:
            return clahe_filter.apply(gpu_img)
    except (cv2.error, TypeError):
        # Fallback to Variant B (requires dst parameter)
        # Use size() instead of rows/cols - GpuMat doesn't have rows/cols attributes
        dst = cv2.cuda_GpuMat(gpu_img.size(), gpu_img.type())
        if stream is not None:
            clahe_filter.apply(gpu_img, dst, stream)  # Positional stream
        else:
            clahe_filter.apply(gpu_img, dst)
        return dst


def _apply_gaussian_robust(gaussian_filter, gpu_img, stream):
    """Apply Gaussian blur robustly across OpenCV build variants.
    
    Similar to CLAHE, Gaussian filter may have different signatures:
    - Variant A: apply(src[, stream]) -> dst
    - Variant B: apply(src, dst[, stream]) -> None
    
    Args:
        gaussian_filter: CUDA Gaussian filter object
        gpu_img: Input GpuMat
        stream: CUDA stream or None
        
    Returns:
        cv2.cuda_GpuMat: Result of Gaussian blur
    """
    # Try Variant A first
    try:
        if stream is not None:
            return gaussian_filter.apply(gpu_img, stream)  # Positional stream
        else:
            return gaussian_filter.apply(gpu_img)
    except (cv2.error, TypeError):
        # Fallback to Variant B
        # Use size() instead of rows/cols - GpuMat doesn't have rows/cols attributes
        dst = cv2.cuda_GpuMat(gpu_img.size(), gpu_img.type())
        if stream is not None:
            gaussian_filter.apply(gpu_img, dst, stream)  # Positional stream
        else:
            gaussian_filter.apply(gpu_img, dst)
        return dst


class GPUBatchProcessor:
    """Batch GPU processor for pepper vision operations.
    
    Handles batch processing of multiple image fragments on GPU for optimal
    performance. Uses CUDA streams for parallel execution when possible.
    
    Attributes:
        cuda_available (bool): Whether CUDA is available
        cupy_available (bool): Whether CuPy is available
        num_streams (int): Number of CUDA streams for parallel processing
        streams (list): List of CUDA stream objects
    """
    
    def __init__(self, num_streams: int = 4, use_cupy: bool = True):
        """Initialize GPU batch processor.
        
        Args:
            num_streams (int): Number of CUDA streams for parallel processing
            use_cupy (bool): Whether to use CuPy for advanced operations
        """
        self.cuda_available = cv2.cuda.getCudaEnabledDeviceCount() > 0
        self.cupy_available = CUPY_AVAILABLE and use_cupy
        self.num_streams = num_streams
        self.streams = []
        
        if self.cuda_available:
            # Create CUDA streams for parallel processing
            for _ in range(num_streams):
                stream = cv2.cuda.Stream()
                self.streams.append(stream)
        
        # Cache for GPU filters/operations
        self._morphology_filters = {}
        self._clahe_filters = {}
    
    def upload_to_gpu(self, images: List[np.ndarray]) -> List[cv2.cuda.GpuMat]:
        """Upload batch of images to GPU memory.
        
        Args:
            images (List[np.ndarray]): List of numpy arrays to upload
            
        Returns:
            List[cv2.cuda.GpuMat]: List of GPU matrices
        """
        if not self.cuda_available:
            return images  # Return CPU arrays if no GPU
        
        gpu_images = []
        for img in images:
            gpu_mat = cv2.cuda.GpuMat()
            gpu_mat.upload(img)
            gpu_images.append(gpu_mat)
        
        return gpu_images
    
    def download_from_gpu(self, gpu_images: List[cv2.cuda.GpuMat]) -> List[np.ndarray]:
        """Download batch of images from GPU memory.
        
        Args:
            gpu_images (List[cv2.cuda.GpuMat]): List of GPU matrices
            
        Returns:
            List[np.ndarray]: List of numpy arrays
        """
        if not self.cuda_available:
            return gpu_images  # Already CPU arrays
        
        cpu_images = []
        for gpu_img in gpu_images:
            if isinstance(gpu_img, cv2.cuda.GpuMat):
                cpu_img = gpu_img.download()
                cpu_images.append(cpu_img)
            else:
                cpu_images.append(gpu_img)
        
        return cpu_images
    
    def batch_color_convert(
        self,
        gpu_images: List[cv2.cuda.GpuMat],
        conversion_code: int,
        use_streams: bool = True
    ) -> List[cv2.cuda.GpuMat]:
        """Batch color space conversion on GPU.
        
        Args:
            gpu_images (List[cv2.cuda.GpuMat]): Input images on GPU
            conversion_code (int): OpenCV color conversion code (e.g., cv2.COLOR_BGR2HSV)
            use_streams (bool): Whether to use parallel CUDA streams
            
        Returns:
            List[cv2.cuda.GpuMat]: Converted images on GPU
        """
        if not self.cuda_available:
            # CPU fallback
            cpu_images = [img if isinstance(img, np.ndarray) else img.download() 
                          for img in gpu_images]
            return [cv2.cvtColor(img, conversion_code) for img in cpu_images]
        
        converted = []
        for idx, gpu_img in enumerate(gpu_images):
            stream = self.streams[idx % len(self.streams)] if use_streams and self.streams else None
            
            converted_img = cv2.cuda.cvtColor(gpu_img, conversion_code, stream=stream)
            converted.append(converted_img)
        
        # NOTE: Removed stream synchronization here - caller should sync once at end of entire pipeline
        # This allows true parallel execution across multiple batch operations
        
        return converted
    
    def batch_inrange(
        self,
        gpu_images: List[cv2.cuda.GpuMat],
        lower_bounds: List[Tuple[int, int, int]],
        upper_bounds: List[Tuple[int, int, int]],
        use_streams: bool = True
    ) -> List[cv2.cuda.GpuMat]:
        """Batch color range thresholding on GPU.
        
        Args:
            gpu_images (List[cv2.cuda.GpuMat]): Input images on GPU
            lower_bounds (List[Tuple]): Lower color bounds for each image
            upper_bounds (List[Tuple]): Upper color bounds for each image
            use_streams (bool): Whether to use parallel CUDA streams
            
        Returns:
            List[cv2.cuda.GpuMat]: Binary masks on GPU
        """
        if not self.cuda_available:
            # CPU fallback
            cpu_images = [img if isinstance(img, np.ndarray) else img.download() 
                          for img in gpu_images]
            return [cv2.inRange(img, np.array(lower), np.array(upper))
                    for img, lower, upper in zip(cpu_images, lower_bounds, upper_bounds)]
        
        masks = []
        for idx, (gpu_img, lower, upper) in enumerate(zip(gpu_images, lower_bounds, upper_bounds)):
            stream = self.streams[idx % len(self.streams)] if use_streams and self.streams else None
            
            # OpenCV Python CUDA inRange accepts tuples directly
            # Ensure they are tuples (not lists) for consistency
            lower_tuple = tuple(lower) if not isinstance(lower, tuple) else lower
            upper_tuple = tuple(upper) if not isinstance(upper, tuple) else upper
            
            # CRITICAL: Pre-allocate mask with correct size/type (single channel grayscale)
            # Empty GpuMat() may not be allocated properly by inRange, causing NULL pointer errors downstream
            mask = cv2.cuda.GpuMat(gpu_img.size(), cv2.CV_8UC1)
            cv2.cuda.inRange(gpu_img, lower_tuple, upper_tuple, mask, stream=stream)
            masks.append(mask)
        
        # NOTE: Removed stream synchronization here - caller should sync once at end of entire pipeline
        
        return masks
    
    def batch_morphology(
        self,
        gpu_images: List[cv2.cuda.GpuMat],
        operation: int,
        kernel_size: Tuple[int, int],
        iterations: int = 1,
        use_streams: bool = True
    ) -> List[cv2.cuda.GpuMat]:
        """Batch morphological operations on GPU.
        
        Args:
            gpu_images (List[cv2.cuda.GpuMat]): Input images/masks on GPU
            operation (int): Morphology operation (cv2.MORPH_OPEN, CLOSE, ERODE, DILATE)
            kernel_size (Tuple[int, int]): Kernel size for operation
            iterations (int): Number of iterations
            use_streams (bool): Whether to use parallel CUDA streams
            
        Returns:
            List[cv2.cuda.GpuMat]: Processed images on GPU
        """
        if not self.cuda_available:
            # CPU fallback
            cpu_images = [img if isinstance(img, np.ndarray) else img.download() 
                          for img in gpu_images]
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, kernel_size)
            return [cv2.morphologyEx(img, operation, kernel, iterations=iterations)
                    for img in cpu_images]
        
        # Create or get cached morphology filter
        filter_key = (operation, kernel_size)
        if filter_key not in self._morphology_filters:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, kernel_size)
            self._morphology_filters[filter_key] = cv2.cuda.createMorphologyFilter(
                operation, cv2.CV_8U, kernel
            )
        
        morph_filter = self._morphology_filters[filter_key]
        
        processed = []
        for idx, gpu_img in enumerate(gpu_images):
            stream = self.streams[idx % len(self.streams)] if use_streams and self.streams else None
            
            # Handle iterations properly - use gpu_img as source for first iteration,
            # then use result as both source and destination for subsequent iterations
            if iterations == 0:
                processed.append(gpu_img.clone())
                continue
            
            # CRITICAL: Pre-allocate result buffer with same size/type as input
            # Empty GpuMat() has no memory allocated and causes NPP_NULL_POINTER_ERROR
            result = cv2.cuda.GpuMat(gpu_img.size(), gpu_img.type())
            
            for iteration_idx in range(iterations):
                # First iteration: use original image as source
                # Subsequent iterations: use result as source (in-place operation)
                source = gpu_img if iteration_idx == 0 else result
                morph_filter.apply(source, result, stream=stream)
            
            processed.append(result)
        
        # NOTE: Removed stream synchronization here - caller should sync once at end of entire pipeline
        
        return processed
    
    def batch_clahe(
        self,
        gpu_images: List[cv2.cuda.GpuMat],
        clip_limit: float = 2.0,
        tile_grid_size: Tuple[int, int] = (8, 8),
        use_streams: bool = True
    ) -> List[cv2.cuda.GpuMat]:
        """Batch CLAHE (Contrast Limited Adaptive Histogram Equalization) on GPU.
        
        Args:
            gpu_images (List[cv2.cuda.GpuMat]): Input grayscale images on GPU
            clip_limit (float): Contrast clipping limit
            tile_grid_size (Tuple[int, int]): Grid size for tiles
            use_streams (bool): Whether to use parallel CUDA streams
            
        Returns:
            List[cv2.cuda.GpuMat]: Enhanced images on GPU
        """
        if not self.cuda_available:
            # CPU fallback
            cpu_images = [img if isinstance(img, np.ndarray) else img.download() 
                          for img in gpu_images]
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
            return [clahe.apply(img) for img in cpu_images]
        
        # Create or get cached CLAHE filter
        filter_key = (clip_limit, tile_grid_size)
        if filter_key not in self._clahe_filters:
            self._clahe_filters[filter_key] = cv2.cuda.createCLAHE(
                clipLimit=clip_limit,
                tileGridSize=tile_grid_size
            )
        
        clahe_filter = self._clahe_filters[filter_key]
        
        enhanced = []
        for idx, gpu_img in enumerate(gpu_images):
            stream = self.streams[idx % len(self.streams)] if use_streams and self.streams else None
            
            # Use robust apply wrapper to handle different OpenCV build variants
            result = _apply_clahe_robust(clahe_filter, gpu_img, stream)
            enhanced.append(result)
        
        # NOTE: Removed stream synchronization here - caller should sync once at end of entire pipeline
        
        return enhanced
    
    def batch_threshold(
        self,
        gpu_images: List[cv2.cuda.GpuMat],
        thresholds: List[float],
        max_values: List[float],
        threshold_type: int = cv2.THRESH_BINARY,
        use_streams: bool = True
    ) -> List[cv2.cuda.GpuMat]:
        """Batch thresholding on GPU.
        
        Args:
            gpu_images (List[cv2.cuda.GpuMat]): Input grayscale images on GPU
            thresholds (List[float]): Threshold values for each image
            max_values (List[float]): Maximum values for each image
            threshold_type (int): Threshold type (cv2.THRESH_BINARY, etc.)
            use_streams (bool): Whether to use parallel CUDA streams
            
        Returns:
            List[cv2.cuda.GpuMat]: Thresholded images on GPU
        """
        if not self.cuda_available:
            # CPU fallback
            cpu_images = [img if isinstance(img, np.ndarray) else img.download() 
                          for img in gpu_images]
            return [cv2.threshold(img, thresh, maxval, threshold_type)[1]
                    for img, thresh, maxval in zip(cpu_images, thresholds, max_values)]
        
        thresholded = []
        for idx, (gpu_img, thresh, maxval) in enumerate(zip(gpu_images, thresholds, max_values)):
            stream = self.streams[idx % len(self.streams)] if use_streams and self.streams else None
            
            result = cv2.cuda.GpuMat()
            cv2.cuda.threshold(gpu_img, thresh, maxval, threshold_type, result, stream=stream)
            thresholded.append(result)
        
        # NOTE: Removed stream synchronization here - caller should sync once at end of entire pipeline
        
        return thresholded
    
    def batch_gaussian_blur(
        self,
        gpu_images: List[cv2.cuda.GpuMat],
        kernel_size: Tuple[int, int],
        sigma: float = 0,
        use_streams: bool = True
    ) -> List[cv2.cuda.GpuMat]:
        """Batch Gaussian blur on GPU.
        
        Args:
            gpu_images (List[cv2.cuda.GpuMat]): Input images on GPU
            kernel_size (Tuple[int, int]): Gaussian kernel size
            sigma (float): Gaussian standard deviation (0 = auto-calculate)
            use_streams (bool): Whether to use parallel CUDA streams
            
        Returns:
            List[cv2.cuda.GpuMat]: Blurred images on GPU
        """
        if not self.cuda_available:
            # CPU fallback
            cpu_images = [img if isinstance(img, np.ndarray) else img.download() 
                          for img in gpu_images]
            return [cv2.GaussianBlur(img, kernel_size, sigma) for img in cpu_images]
        
        # Create Gaussian filter
        gaussian_filter = cv2.cuda.createGaussianFilter(
            cv2.CV_8U, cv2.CV_8U, kernel_size, sigma
        )
        
        blurred = []
        for idx, gpu_img in enumerate(gpu_images):
            stream = self.streams[idx % len(self.streams)] if use_streams and self.streams else None
            
            # Use robust apply wrapper to handle different OpenCV build variants
            result = _apply_gaussian_robust(gaussian_filter, gpu_img, stream)
            blurred.append(result)
        
        # NOTE: Removed stream synchronization here - caller should sync once at end of entire pipeline
        
        return blurred
    
    def cleanup(self):
        """Clean up GPU resources and cached filters."""
        try:
            self._morphology_filters.clear()
            self._clahe_filters.clear()
            
            if self.streams:
                for stream in self.streams:
                    try:
                        stream.waitForCompletion()
                    except Exception:
                        pass  # Ignore errors during cleanup
                self.streams.clear()
        except Exception:
            pass  # Ensure cleanup never raises
    
    def reset_after_error(self):
        """Reset GPU processor state after CUDA error.
        
        Called when CUDA operations fail to clean up potentially corrupted state.
        Clears cached filters and recreates streams.
        """
        try:
            # Clear all cached filters
            self._morphology_filters.clear()
            self._clahe_filters.clear()
            
            # Wait for and clear existing streams
            if self.streams:
                for stream in self.streams:
                    try:
                        stream.waitForCompletion()
                    except Exception:
                        pass
                self.streams.clear()
            
            # Recreate streams if CUDA is still available
            if self.cuda_available:
                try:
                    for _ in range(self.num_streams):
                        stream = cv2.cuda.Stream()
                        self.streams.append(stream)
                except Exception:
                    # If stream creation fails, CUDA is likely broken
                    self.cuda_available = False
                    self.streams.clear()
        except Exception:
            # Last resort: disable GPU
            self.cuda_available = False
            self.streams.clear()
