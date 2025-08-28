import numpy as np


def create_camera_distortion(distortion_coefficients):
    camera_distortion = np.array(distortion_coefficients, dtype=np.float32)

    return camera_distortion
