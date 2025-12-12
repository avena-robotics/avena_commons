"""Universal IO utilities for robot tool communication.

Provides unified interface for robot tool IO operations (Digital/Analog In/Out)
with consistent error handling, logging, and validation.
"""

from .tool_io import ToolIO, ToolIOError

__all__ = ["ToolIO", "ToolIOError"]
