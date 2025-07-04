"""
#### Utility Module

Moduł zawierający narzędzia matematyczne i pomocnicze funkcje do obliczeń 3D, robotyki i analizy danych.

#### Główne komponenty:
- `MeasureTime`: Klasa do pomiaru czasu wykonania kodu (dekorator/context manager)
- `ControlLoop`: Pętla kontrolna
- `Connector`/`Worker`: Asynchroniczne połączenia i przetwarzanie
- `Catchtime`: Narzędzie do pomiaru czasu wykonania kodu
- `logger`: Polityka logowania i logger wiadomości lub danych
- `utils`: Funkcje matematyczne do transformacji 3D, interpolacji i obliczeń robotycznych

#### Funkcjonalności matematyczne:
- Konwersje między kwaternionami, macierzami rotacji i kątami Eulera
- Interpolacja liniowa i smooth ramp
- Obliczenia kinematyki robotycznej
- Filtrowanie sygnałów (moving average, RMS)
- Operacje na pozach i transformacjach 3D
```
"""

from .utils import (
    angle_axis_to_quaternion,
    calculate_derivative,
    calculate_factor,
    calculate_factors,
    calculate_rms,
    check_distance,
    clip_goal_position,
    create_transformation_matrix,
    degrees_to_radians,
    euler_from_quaternion,
    euler_to_rotation_matrix,
    find_closest_pose,
    get_quaternion_from_euler,
    interpolate,
    interpolate_rconfigs,
    joints_set_current_position_to_goal_position,
    limit_acc,
    limit_vel,
    moving_average_filter,
    pose_from_transformation_matrix,
    quaternion_angle_diff,
    radians_to_degrees,
    ramp_smoothing,
    rotate_points_around_center,
    rotate_pose,
    rotate_quat_in_euler,
    rotate_transformation_matrix,
    rotate_vector_by_euler,
    rotation_matrix_to_euler_angles,
    rotation_matrix_to_rvec,
    string_to_float_list,
    update_similar_attr,
)

__all__ = [
    "angle_axis_to_quaternion",
    "calculate_derivative",
    "calculate_factor",
    "calculate_factors",
    "calculate_rms",
    "check_distance",
    "clip_goal_position",
    "create_transformation_matrix",
    "degrees_to_radians",
    "euler_from_quaternion",
    "euler_to_rotation_matrix",
    "find_closest_pose",
    "get_quaternion_from_euler",
    "interpolate",
    "interpolate_rconfigs",
    "joints_set_current_position_to_goal_position",
    "limit_acc",
    "limit_vel",
    "moving_average_filter",
    "pose_from_transformation_matrix",
    "quaternion_angle_diff",
    "radians_to_degrees",
    "ramp_smoothing",
    "rotate_points_around_center",
    "rotate_pose",
    "rotate_quat_in_euler",
    "rotate_transformation_matrix",
    "rotate_vector_by_euler",
    "rotation_matrix_to_euler_angles",
    "rotation_matrix_to_rvec",
    "string_to_float_list",
    "update_similar_attr",
]
