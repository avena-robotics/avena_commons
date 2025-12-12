"""Gripper modules for robot end-effectors.

This package provides abstract base classes and concrete implementations
for various gripper types (vacuum, mechanical, etc.) that can be attached
to the robot.
"""

from .base import BaseGripper, EventResult, GripperError, IOMapping, RobotToolConfig
from .vacuum_gripper import VacuumGripper, VacuumGripperConfig

__all__ = [
    "BaseGripper",
    "EventResult",
    "GripperError",
    "RobotToolConfig",
    "VacuumGripper",
    "VacuumGripperConfig",
]
