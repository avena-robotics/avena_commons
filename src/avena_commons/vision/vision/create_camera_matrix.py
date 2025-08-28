import numpy as np


def create_camera_matrix(camera_params):
    return np.array(
        [
            [camera_params[0], 0, camera_params[2]],
            [0, camera_params[1], camera_params[3]],
            [0, 0, 1],
        ],
        dtype=np.float32,
    )
