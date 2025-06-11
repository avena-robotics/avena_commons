import math

import cv2
import numpy as np
from scipy.spatial.transform import Rotation


def interpolate(x, y, new_x):
    """
    Interpolates the value of y for a given x using linear interpolation.

    :param x: list of x values
    :param y: list of y values
    :param new_x: new x value for which to interpolate y
    :return: interpolated y value"""
    # Znalezienie indeksów dwóch najbliższych znaczników czasu
    idx = np.searchsorted(x, new_x)
    if idx == 0:
        return y[0]
    if idx == len(x):
        return y[idx - 1]

    # Znalezienie dwóch najbliższych znaczników czasu i ich wartości przyspieszeń
    x1, x2 = x[idx - 1], x[idx]
    y1, y2 = y[idx - 1], y[idx]

    # Obliczenie współczynników dla interpolacji liniowej
    fraction = (new_x - x1) / (x2 - x1)

    # Wygenerowanie interpolowanych wartości przyspieszeń
    interpolated = y1 + fraction * (y2 - y1)

    # return y1 + (y2 - y1) * ((x - x1) / (x2 - x1))
    return interpolated


def moving_average_filter(data, window_size):
    """
    Apply a moving average filter to smooth data.

    :param data: data to be smoothed
    :param window_size: size of the moving average window
    :return: moving average smoothed data
    """
    # Wypełnij dane lustrzanym odbiciem na początku i na końcu
    pad_size = window_size // 2
    padded_data = np.pad(data, (pad_size, pad_size), mode="reflect")

    # Oblicz średnią ruchomą
    cumsum_vec = np.cumsum(np.insert(padded_data, 0, 0))
    ma_vec = (cumsum_vec[window_size:] - cumsum_vec[:-window_size]) / window_size

    return ma_vec


def ramp_smoothing(data, alpha):
    """
    Smooth data by applying a ramp constraint.
    Iterates from left to right and then from right to left.
    If the difference between the current and previous point exceeds alpha, adjust it.

    :param data: data to be smoothed
    :param alpha: maximum difference between two adjacent points
    :return: smoothed data
    """
    smoothed_data = np.copy(data)

    # Left to right iteration
    for i in range(1, len(data)):
        if (smoothed_data[i] - smoothed_data[i - 1]) > alpha:
            smoothed_data[i] = (
                smoothed_data[i - 1]
                + np.sign(smoothed_data[i] - smoothed_data[i - 1]) * alpha
            )

    # Right to left iteration
    for i in range(len(data) - 2, -1, -1):
        if (smoothed_data[i] - smoothed_data[i + 1]) > alpha:
            smoothed_data[i] = (
                smoothed_data[i + 1]
                + np.sign(smoothed_data[i] - smoothed_data[i + 1]) * alpha
            )

    return smoothed_data


def interpolate_rconfigs(times, rconfigs, factors, dt):
    """
    Interpolates between robot configurations.

    :param times: list of times
    :param rconfigs: list of robot configurations
    :param factors: list of factors
    :param dt: time step
    :return: o_times, o_rconfigs: interpolated times and robot configurations
    """
    duration = dt * len(rconfigs)
    _current_time = 0.0
    o_times = np.empty(shape=[0, 1], dtype=np.float64)
    o_rconfigs = np.empty(shape=[0, 6], dtype=np.float64)  # konfiguracja jointow
    while duration > _current_time:
        # if duration > _current_time: break
        _rconfig = interpolate(times, rconfigs, _current_time)
        o_rconfigs = np.append(o_rconfigs, [_rconfig], axis=0)
        o_times = np.append(o_times, len(o_times) * dt)
        _factor = interpolate(times, factors, _current_time)
        _current_time = _current_time + dt * _factor
    del _rconfig
    return o_times, o_rconfigs


def calculate_factor(x, y, new_x, limit, power):
    """
    Calculate a factor for scaling or normalization.

    :param x: list of x values
    :param y: list of y values
    :param new_x: new x value for which to calculate the factor
    :param limit: limit value
    :param power: power value
    :return: calculated factor
    """
    _interpolate = interpolate(x, y, new_x)  # wyznaczenie mnoznika
    _abs = np.abs(_interpolate)
    _max_abs = np.max(_abs)
    _factor = (
        1.0 if _max_abs == 0 else limit / _max_abs
    ) ** power  # mnoznik przekroczenia prędkości
    return _factor


def calculate_factors(times, data, dt, limit, power):
    """
    Calculate factors for scaling or normalization.

    :param times: list of times
    :param data: list of data
    :param dt: time step
    :param limit: limit value
    :param power: power value
    :return: calculated factors
    """
    _time = times[-1] - times[0]
    _begin = times[0]
    _current_time = _begin

    _factors = np.empty(shape=[0, 1], dtype=np.float64)
    while _begin + _time > _current_time:
        if times[-1] < _current_time:
            break

        _factor_2 = calculate_factor(times, data, _current_time, limit, power)
        _factor = min(1.0, _factor_2)
        _current_time += dt

        _factors = np.append(_factors, _factor)

    return _factors


def limit_acc(times, rconfigs, ang_acc, dt, acc_limit):
    """
    Limit acceleration to a certain threshold.

    :param times: list of times
    :param rconfigs: list of robot configurations
    :param ang_acc: list of angular accelerations
    :param dt: time step
    :param acc_limit: acceleration limit
    :return: times_1, rconfigs_1, ang_vel_1, ang_acc_1: limited times, robot configurations, angular velocities, and angular accelerations
    """
    # f_a = calculate_factors_acc(times, ang_acc, dt, acc_limit)
    f_a = calculate_factors(times, ang_acc, dt, acc_limit, 1 / 2)
    f_ramp_a = ramp_smoothing(f_a, 0.005)
    f_ramp_a = np.append(f_ramp_a, 1.0)
    # print(len(f_a))
    # print(len(f_ramp_a))
    # print(len(times))
    times_1, rconfigs_1 = interpolate_rconfigs(times, rconfigs, f_ramp_a, dt)
    ang_vel_1 = calculate_derivative(rconfigs_1, dt)
    ang_acc_1 = calculate_derivative(ang_vel_1, dt)
    return times_1, rconfigs_1, ang_vel_1, ang_acc_1


def limit_vel(times, rconfigs, ang_vel, dt, vel_limit):
    """
    Limit velocity to a certain threshold.

    :param times: list of times
    :param rconfigs: list of robot configurations
    :param ang_vel: list of angular velocities
    :param dt: time step
    :param vel_limit: velocity limit
    :return: times_1, rconfigs_1, ang_vel_1, ang_acc_1: limited times, robot configurations, angular velocities, and angular accelerations
    """
    # f_v = calculate_factors_acc(times, ang_vel, dt, vel_limit)
    f_v = calculate_factors(times, ang_vel, dt, vel_limit, 1)
    f_ramp_v = ramp_smoothing(f_v, 0.005)
    f_ramp_v = np.append(f_ramp_v, 1.0)
    times_1, rconfigs_1 = interpolate_rconfigs(times, rconfigs, f_ramp_v, dt)
    ang_vel_1 = calculate_derivative(rconfigs_1, dt)
    ang_acc_1 = calculate_derivative(ang_vel_1, dt)
    return times_1, rconfigs_1, ang_vel_1, ang_acc_1


def calculate_derivative(arguments, dt):
    """
    Calculate the derivative of a function or data set.

    :param arguments: list of arguments
    :param dt: time step
    :return: derivatives: list of derivatives
    """
    derivatives = np.zeros_like(
        arguments
    )  # Macierz wyników o tym samym kształcie co rconfigs

    # Zakładamy, że times i rconfigs są wektorami o tej samej długości
    for i in range(1, len(arguments) - 1):
        derivatives[i] = (arguments[i + 1] - arguments[i - 1]) / (2 * dt)

    # Opcjonalnie: Obsługa krańców przedziałów
    # Przykładowo, można użyć różnic do przodu i do tyłu
    if len(arguments) > 1:
        derivatives[0] = (
            arguments[1] - arguments[0]
        ) / dt  # Różnica do przodu dla pierwszego elementu
        derivatives[-1] = (
            arguments[-1] - arguments[-2]
        ) / dt  # Różnica do tyłu dla ostatniego elementu

    return derivatives


def find_closest_pose(searched_pose, poses):
    """
    Find the closest pose to a given target pose.

    :param searched_pose: target pose (x, y, z, qx, qy, qz, qw)
    :param poses: list of poses
    :return: closest_pose: closest pose
    """
    # Ustaw początkową minimalną odległość na bardzo dużą wartość
    min_distance = float("inf")

    for step, pose in enumerate(poses):
        # Oblicz odległość Euklidesową między punktem odniesienia a aktualnym punktem
        distance = (
            (searched_pose[0] - pose[0]) ** 2
            + (searched_pose[1] - pose[1]) ** 2
            + (searched_pose[2] - pose[2]) ** 2
        ) ** 0.5

        # Aktualizuj najbliższy punkt i minimalną odległość, jeśli to konieczne
        if distance < min_distance:
            min_distance = distance
            closest_pose = pose
            closest_step = step

    # return closest_pose
    return closest_pose, closest_step


def clip_goal_position(value):
    """
    Clip the goal_position to a certain range.

    :param value: goal_position
    :return: clipped_value: clipped
    """
    max_limit = 2.95
    min_limit = -max_limit
    # Ogranicza goal_position do zakresu od min_limit do max_limit
    clipped_value = max(min_limit, min(max_limit, value))
    return clipped_value


def check_distance(current, target, fksolver=None):
    """
    Function to check the distance between two configurations. If fksolver is provided, the distance is calculated between two configurations. If fksolver is None, the distance is calculated between two poses.

    :param current: current configuration/pose
    :param target: target configuration/pose
    :param fksolver: forward kinematics solver
    :return: distance between two configurations in meters
    """
    if fksolver is None:
        pose1 = target
        pose2 = current
    elif len(current) < 6:
        diff = [target[i] - current[i] for i in range(len(current))]
        return max(diff)

    diff = [pose1[i] - pose2[i] for i in range(3)]
    distance = round(np.linalg.norm(diff), 6)  # meters
    return distance


def update_similar_attr(source, target, read_only=False):  # -> Any:
    """
    Update similar attributes of two objects.

    :param source: source object
    :param target: target object
    :param read_only: read-only flag, if True, the function will update similar attributes with the same name, but without the leading underscore
    :return: updated target object
    """
    for key in target.__dict__.keys():
        if key in source.__dict__:
            try:
                setattr(target, key, getattr(source, key))
            except ValueError as e:
                raise ValueError(f"Error while updating similar attributes: {e}")
        # Jeśli atrybut zaczyna się od podkreślenia, sprawdź, czy atrybut bez podkreślenia istnieje w źródle
        elif read_only and key.startswith("_") and key[1:] in source.__dict__:
            try:
                setattr(target, key, getattr(source, key[1:]))
            except ValueError as e:
                raise ValueError(f"Error while updating similar attributes: {e}")
    return target


def get_quaternion_from_euler(roll, pitch, yaw):
    """
    Convert Euler angles to a quaternion.

    :param roll: rotation around x in degrees (counterclockwise)
    :param pitch: rotation around y in degrees (counterclockwise)
    :param yaw: rotation around z in degrees (counterclockwise)
    :return: quaternion
    """
    # Create a rotation object from Euler angles specifying axes of rotation
    rot = Rotation.from_euler("xyz", [roll, pitch, yaw], degrees=True)
    # Convert to quaternions
    rot_quat = rot.as_quat()
    return rot_quat


def euler_from_quaternion(x, y, z, w):
    """
    Convert a quaternion to Euler angles.

    :param x: x component of the quaternion
    :param y: y component of the quaternion
    :param z: z component of the quaternion
    :param w: w component of the quaternion
    :return: list of Euler angles (roll, pitch, yaw) in degrees
    """
    t0 = +2.0 * (w * x + y * z)
    t1 = +1.0 - 2.0 * (x * x + y * y)
    roll_x = math.atan2(t0, t1)

    t2 = +2.0 * (w * y - z * x)
    t2 = +1.0 if t2 > +1.0 else t2
    t2 = -1.0 if t2 < -1.0 else t2
    pitch_y = math.asin(t2)

    t3 = +2.0 * (w * z + x * y)
    t4 = +1.0 - 2.0 * (y * y + z * z)
    yaw_z = math.atan2(t3, t4)

    roll_x = radians_to_degrees(roll_x)
    pitch_y = radians_to_degrees(pitch_y)
    yaw_z = radians_to_degrees(yaw_z)

    return [roll_x, pitch_y, yaw_z]  # in degrees


def degrees_to_radians(deg):
    """
    Convert degrees to radians.

    :param deg: angle in degrees
    :return: angle in radians
    """
    return deg * np.pi / 180.0


def radians_to_degrees(rad):
    """
    Convert radians to degrees.

    :param rad: angle in radians
    :return: angle in degrees
    """
    return rad * 180.0 / np.pi


def rotate_vector_by_euler(vector, roll, pitch, yaw):
    """
    Rotate a vector by Euler angles.

    :param vector: vector to be rotated
    :param roll: rotation around x in degrees (counterclockwise)
    :param pitch: rotation around y in degrees (counterclockwise)
    :param yaw: rotation around z in degrees (counterclockwise)
    :return: rotated vector
    """
    # Konwersja kątów z stopni na radiany
    roll = np.radians(roll)
    pitch = np.radians(pitch)
    yaw = np.radians(yaw)
    # Macierz rotacji dla roll (wokół osi X)
    R_x = np.array([
        [1, 0, 0],
        [0, np.cos(roll), -np.sin(roll)],
        [0, np.sin(roll), np.cos(roll)],
    ])
    # Macierz rotacji dla pitch (wokół osi Y)
    R_y = np.array([
        [np.cos(pitch), 0, np.sin(pitch)],
        [0, 1, 0],
        [-np.sin(pitch), 0, np.cos(pitch)],
    ])
    # Macierz rotacji dla yaw (wokół osi Z)
    R_z = np.array([
        [np.cos(yaw), -np.sin(yaw), 0],
        [np.sin(yaw), np.cos(yaw), 0],
        [0, 0, 1],
    ])
    # Złożona macierz rotacji R (kolejność ZYX)
    R = np.dot(R_x, np.dot(R_y, R_z))
    # Obróć wektor
    rotated_vector = np.dot(R, vector)
    return rotated_vector


def create_transformation_matrix(pose_quat):
    """
    Create a 4x4 transformation matrix from a pose in quaternion format.

    :param pose_quat: pose in quaternion format [x, y, z, qx, qy, qz, qw]
    :return: 4x4 transformation matrix
    """
    x, y, z, qx, qy, qz, qw = pose_quat
    # Normalize quaternion to avoid numerical instability
    norm = np.linalg.norm([qx, qy, qz, qw])
    qx, qy, qz, qw = qx / norm, qy / norm, qz / norm, qw / norm

    rotation_matrix = Rotation.from_quat([qx, qy, qz, qw]).as_matrix()
    transformation_matrix = np.eye(4)
    transformation_matrix[:3, :3] = rotation_matrix
    transformation_matrix[:3, 3] = [x, y, z]
    return transformation_matrix


def rotate_transformation_matrix(transformation_matrix, angle_degrees, axis):
    """
    Rotate the transformation matrix by a given angle around a given axis.

    :param transformation_matrix: 4x4 transformation matrix
    :param angle_degrees: rotation angle in degrees
    :param axis: axis of rotation (string 'x', 'y', or 'z' or a 3-element list/array)
    :return: new 4x4 transformation matrix after rotation
    """
    if isinstance(axis, str):
        rotation_axis = Rotation.from_euler(
            axis, angle_degrees, degrees=True
        ).as_matrix()
    else:
        # Normalize the axis vector
        axis = np.array(axis) / np.linalg.norm(axis)
        rotation_axis = Rotation.from_rotvec(
            np.radians(angle_degrees) * axis
        ).as_matrix()

    # Expand rotation matrix to 4x4
    rotation_matrix_4x4 = np.eye(4)
    rotation_matrix_4x4[:3, :3] = rotation_axis

    # Multiply the rotation matrix with the transformation matrix
    new_transformation_matrix = np.dot(rotation_matrix_4x4, transformation_matrix)
    return new_transformation_matrix


def pose_from_transformation_matrix(matrix):
    """
    Extract pose in quaternion format from a 4x4 transformation matrix.

    :param matrix: 4x4 transformation matrix
    :return: pose in quaternion format [x, y, z, qx, qy, qz, qw]
    """
    x, y, z = matrix[:3, 3]
    rotation_matrix = matrix[:3, :3]
    quaternion = Rotation.from_matrix(rotation_matrix).as_quat()
    return [x, y, z, quaternion[0], quaternion[1], quaternion[2], quaternion[3]]


def rotate_pose(pose_quat, angle_degrees, axis="z"):
    """
    Rotate a pose by a given angle around a given axis.

    :param pose_quat: pose in quaternion format [x, y, z, qx, qy, qz, qw]
    :param angle_degrees: rotation angle in degrees
    :param axis: axis around which to rotate ('x', 'y', 'z' or a 3-element list/array)
    :return: rotated pose in quaternion format
    """
    transformation_matrix = create_transformation_matrix(pose_quat)
    new_transformation_matrix = rotate_transformation_matrix(
        transformation_matrix, angle_degrees, axis
    )
    return pose_from_transformation_matrix(new_transformation_matrix)


def quaternion_angle_diff(q1, q2):
    """
    Calculate the angle between two quaternions.

    :param q1: first quaternion
    :param q2: second quaternion
    :return: angle in radians
    """
    # Normalizacja pierwszego kwaternionu, aby był kwaternionem jednostkowym
    q1 /= np.linalg.norm(q1)

    # Normalizacja drugiego kwaternionu, aby był kwaternionem jednostkowym
    q2 /= np.linalg.norm(q2)

    # Obliczenie iloczynu skalarnego dwóch jednostkowych kwaternionów.
    # Iloczyn skalarny mierzy cosinus kąta między wektorami 4D
    # reprezentowanymi przez kwaterniony, gdy oba są kwaternionami jednostkowymi.
    dot_product = np.dot(q1, q2)

    # Przytnij iloczyn skalarny do zakresu od -1 do 1.
    # Ten krok jest kluczowy, ponieważ niedokładności numeryczne mogą spowodować,
    # że iloczyn skalarny wykracza nieco poza ten zakres, prowadząc do błędów
    # w następnym kroku obliczania arcus cosinus.
    dot_product = np.clip(dot_product, -1.0, 1.0)

    # Obliczenie kąta między dwoma kwaternionami.
    # Funkcja arccos zwraca kąt w radianach między dwoma wektorami
    # reprezentowanymi przez kwaterniony. Ponieważ faktyczny kąt obrotu to kąt,
    # o jaki jeden kwaternion musi zostać obrócony, aby zgodzić się z drugim,
    # używamy wartości bezwzględnej iloczynu skalarnego, aby rozważyć tylko najmniejszy obrót (ignorując kierunek).
    # Mnożenie przez 2 daje pełny kąt obrotu od jednego kwaternionu do drugiego.
    return 2 * np.arccos(abs(dot_product))


def calculate_rms(differences):
    """Calculate the Root Mean Square (RMS) of a list of differences using numpy for efficiency.

    :param differences: list of differences
    :return: RMS value
    """
    return np.sqrt(np.mean(np.square(differences)))


def angle_axis_to_quaternion(correction_angle: float = 0.0):
    """
    Convert an angle-axis representation to a quaternion.

    :param correction_angle: correction angle in degrees
    :return: quaternion (qx, qy, qz, qw)
    """
    theta = correction_angle * (math.pi / 180)

    qw = math.cos(theta / 2)
    # qw = 1
    qx = 0
    qy = 0
    qz = math.sin(theta / 2)
    # qz = 0
    return qx, qy, qz, qw


def joints_set_current_position_to_goal_position(joints):
    """
    Utility function to set the current position of joints to the goal position.

    :param joints: list of joints
    """
    for joint in joints[:6]:
        joint.goal_position = joint.current_position


def string_to_float_list(value: str) -> list:
    """
    Convert a string representation of numbers into a list of floats.

    :param value: string representation of numbers
    :return: list of floats
    """
    value = value.strip("[]")
    float_values = []
    for v in value.split(","):
        try:
            float_values.append(float(v.strip()))
        except ValueError:
            raise ValueError(f"Cannot transform value '{v}' to float.")
    return float_values


def rotate_points_around_center(points, center, angle):
    """
    Rotate a list of points around a center point by a given angle.

    :param points: list of points [(x1, y1), (x2, y2), ...]
    :param center: center point (x, y)
    :param angle: rotation angle in degrees
    :return: rotated points [(x1, y1), (x2, y2), ...]
    """
    # Przelicz kąt na radiany
    angle_rad = np.deg2rad(angle)

    # Macierz obrotu
    rotation_matrix = np.array([
        [np.cos(angle_rad), -np.sin(angle_rad)],
        [np.sin(angle_rad), np.cos(angle_rad)],
    ])

    # Nowa lista na obrocone punkty
    rotated_points = []

    # Obrót każdego punktu
    for x, y in points:
        # Przesunięcie punktów tak, by środek obrotu był w (0,0)
        translated_point = np.array([x - center[0], y - center[1]])

        # Obrót punktu
        rotated_point = rotation_matrix @ translated_point

        # Przesunięcie punktów z powrotem
        rotated_point += center

        # Dodanie obroconego punktu do listy
        rotated_points.append((rotated_point[0], rotated_point[1]))

    # print(f'Rotated points: {rotated_points}')

    return rotated_points


def rotate_quat_in_euler(quaternion, euler, clear_rp=False):
    """
    Rotate a quaternion using Euler angles.

    :param quaternion: quaternion to be rotated
    :param euler: Euler angles (roll, pitch, yaw) in degrees
    :param clear_rp: clear roll and pitch angles
    :return: rotated quaternion
    """
    rpy = Rotation.from_quat(quaternion).as_euler("xyz", degrees=True)
    for i in range(3):
        rpy[i] += euler[i]
    # normalize angles
    for i in range(3):
        rpy[i] = rpy[i] % 360
    if clear_rp:
        rpy[0] = 0
        rpy[1] = 0
    rotated_quat = Rotation.from_euler("xyz", rpy, degrees=True).as_quat()
    return rotated_quat


def rotation_matrix_to_euler_angles(R):
    """
    Convert a rotation matrix to Euler angles.

    :param R: rotation matrix
    :return: Euler angles (roll, pitch, yaw) in radians
    """
    sy = np.sqrt(R[0, 0] * R[0, 0] + R[1, 0] * R[1, 0])
    singular = sy < 1e-6
    if not singular:
        x = np.arctan2(R[2, 1], R[2, 2])
        y = np.arctan2(-R[2, 0], sy)
        z = np.arctan2(R[1, 0], R[0, 0])
    else:
        x = np.arctan2(-R[1, 2], R[1, 1])
        y = np.arctan2(-R[2, 0], sy)
        z = 0

    return np.array([x, y, z])


def rotation_matrix_to_rvec(R):
    """
    Convert a rotation matrix to a Rodrigues vector.

    :param R: rotation matrix
    :return: Rodrigues vector
    """
    rvec, _ = cv2.Rodrigues(R)
    return rvec


def euler_to_rotation_matrix(x, y, z):
    """
    Convert Euler angles to a rotation matrix.

    :param x: rotation around x in radians
    :param y: rotation around y in radians
    :param z: rotation around z in radians
    :return: rotation matrix
    """
    # Tworzenie macierzy rotacji z kątów Eulera (zakładając rotację w kolejności XYZ)
    Rx = np.array([[1, 0, 0], [0, np.cos(x), -np.sin(x)], [0, np.sin(x), np.cos(x)]])
    Ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    Rz = np.array([[np.cos(z), -np.sin(z), 0], [np.sin(z), np.cos(z), 0], [0, 0, 1]])
    R = Rz @ Ry @ Rx
    return R
