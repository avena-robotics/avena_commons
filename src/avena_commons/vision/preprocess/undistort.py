import cv2


def undistort(image, camera_matrix, camera_distortion):  # MARK: UNDISTORT
    """
    Corrects lens distortion in the image.

    :param image: Input distorted image
    :param camera_params: List/array of camera parameters [fx, fy, cx, cy]
                        where fx,fy are focal lengths and cx,cy are principal points
    :param dist: Distortion coefficients
    :return: Undistorted image
    """

    return cv2.undistort(image, camera_matrix, camera_distortion)
