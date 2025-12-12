"""Base classes and models for gripper implementations.

Defines abstract BaseGripper class and common Pydantic models used across
all gripper implementations. Grippers process events and monitor their own
state using robot_state_pkg.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from avena_commons.event_listener import Result
from pydantic import BaseModel, Field
from avena_commons.robot.io import ToolIO, ToolIOError


class RobotToolConfig(BaseModel):
    """Configuration for robot tool coordinate system and physical properties.

    Attributes:
        tool_id: Tool identifier (1-15).
        tool_coordinates: TCP offset [x, y, z, rx, ry, rz] in mm and degrees.
        tool_type: 0=tool coordinate system, 1=sensor coordinate system.
        tool_installation: 0=robot end, 1=robot exterior.
        weight: Tool weight in kg.
        mass_coord: Center of mass [x, y, z] in mm relative to flange.
    """

    tool_id: int = Field(ge=1, le=15)
    tool_coordinates: List[float] = Field(min_length=6, max_length=6)
    tool_type: int = Field(ge=0, le=1)
    tool_installation: int = Field(ge=0, le=1)
    weight: float = Field(ge=0)
    mass_coord: List[float] = Field(min_length=3, max_length=3)


class EventResult(Result):
    """Result of event processing by gripper.

    Attributes:
        result(str): Whether the event was processed successfully.
        error_code(int): Error code if failure.
        error_message: Error message if failure.
        data(dict): Additional data from event processing.
    """


class GripperError(Exception):
    """Base exception for gripper-related errors.

    Attributes:
        error_type: Type of error (e.g., "watchdog_error", "connection_error").
        message: Human-readable error message.
        recoverable: Whether the error can be recovered from.
    """

    def __init__(self, error_type: str, message: str, recoverable: bool = False):
        """Initialize gripper error.

        Args:
            error_type: Type of error for categorization.
            message: Detailed error message.
            recoverable: Whether the robot can continue after this error.
        """
        self.error_type = error_type
        self.message = message
        self.recoverable = recoverable
        super().__init__(f"[{error_type}] {message}")


class IOMapping(BaseModel):
    """Mapping of logical gripper IO names to physical pin numbers.

    Attributes:
        digital_outputs: Map of logical names to DO pin numbers (e.g., {"pump": 1}).
        digital_inputs: Map of logical names to DI pin numbers (e.g., {"pump_feedback": 0}).
        analog_inputs: Map of logical names to AI pin numbers (e.g., {"pressure_sensor": 0}).
        analog_outputs: Map of logical names to AO pin numbers (e.g., {"light": 0}).
    """
    tool_do: Dict[str, int] = Field(default_factory=dict)
    tool_di: Dict[str, int] = Field(default_factory=dict)
    tool_ai: Dict[str, float] = Field(default_factory=dict)
    tool_ao: Dict[str, float] = Field(default_factory=dict)
    box_do: Dict[str, int] = Field(default_factory=dict)
    box_di: Dict[str, int] = Field(default_factory=dict)
    box_ai: Dict[str, float] = Field(default_factory=dict)
    box_ao: Dict[str, float] = Field(default_factory=dict)


class GripperIOError(GripperError):
    """Exception for IO operation errors.

    Extends GripperError with IO-specific context.
    """

    def __init__(self, operation: str, pin_name: str, original_error: Exception):
        """Initialize IO error.

        Args:
            operation: IO operation that failed (e.g., "set_do", "get_ai").
            pin_name: Logical name of the pin that caused the error.
            original_error: Original exception from IO operation.
        """
        self.operation = operation
        self.pin_name = pin_name
        self.original_error = original_error

        message = f"IO operation '{operation}' failed on pin '{pin_name}': {str(original_error)}"
        super().__init__(error_type="io_error", message=message, recoverable=False)


class IOManager:
    """Manages gripper IO operations with logical name to pin translation.

    Wraps universal ToolIO and provides name-based interface using IOMapping.
    Translates logical pin names to physical pin numbers.

    Attributes:
        _tool_io: Universal ToolIO instance for hardware operations.
        _io_mapping: Mapping of logical names to physical pins.
        _message_logger: Logger for IO operations.
    """

    def __init__(self, robot, io_mapping: IOMapping, message_logger=None):
        """Initialize IO manager.

        Args:
            robot: Robot instance with tool IO methods.
            io_mapping: Mapping configuration for this gripper.
            message_logger: Logger for IO operations.
        """
        self._tool_io = ToolIO(robot, message_logger)
        self._io_mapping = io_mapping
        self._message_logger = message_logger
        self._io_state: dict = {}  # Stores latest IO state from robot_state_pkg

    def update_io_state(self, io_state: dict) -> None:
        """Update internal IO state snapshot from robot_state_pkg.

        Called by gripper's update_io_state() with fresh data from RobotController.

        Args:
            io_state: Dict with IO fields from robot_state_pkg (tl_dgt_output_l, tl_dgt_input_l, tl_anglog_input).
        """
        self._io_state = io_state

    def set_do(self, name: str, value: bool, smooth: int = 0, block: int = 1) -> None:
        """Set digital output by logical name.

        Args:
            name: Logical name from io_mapping.digital_outputs.
            value: True to set high, False to set low.
            smooth: Smooth transition (0=off, 1=on).
            block: Blocking mode (0=non-blocking, 1=blocking).

        Raises:
            GripperIOError: If pin name not found or IO operation fails.
        """
        if name in self._io_mapping.tool_do:
            tool = True
            pin_id = self._io_mapping.tool_do[name]
        elif name in self._io_mapping.box_do:
            tool = False
            pin_id = self._io_mapping.box_do[name]
        else:
            raise GripperIOError(
                operation="set_do",
                pin_name=name,
                original_error=ValueError(
                    f"Digital output '{name}' not found in IO mapping"
                ),
            )

        try:
            self._tool_io.set_do(pin_id, value, smooth=smooth, block=block, tool=tool)
        except ToolIOError as e:
            raise GripperIOError(operation="set_do", pin_name=name, original_error=e)

    def get_di(self, name: str, block: int = 0) -> bool:
        """Get digital input by logical name.

        Args:
            name: Logical name from io_mapping.digital_inputs.
            block: Blocking mode (0=non-blocking, 1=blocking).

        Returns:
            True if input is high, False if low.

        Raises:
            GripperIOError: If pin name not found or IO operation fails.
        """
        if name in self._io_mapping.tool_di:
            tool = True
            pin_id = self._io_mapping.tool_di[name]
        elif name in self._io_mapping.box_di:
            tool = False
            pin_id = self._io_mapping.box_di[name]
        else:
            raise GripperIOError(
                operation="get_di",
                pin_name=name,
                original_error=ValueError(
                    f"Digital input '{name}' not found in IO mapping"
                ),
            )

        try:
            return self._tool_io.get_di(pin_id, self._io_state, block=block, tool=tool)
        except ToolIOError as e:
            raise GripperIOError(operation="get_di", pin_name=name, original_error=e)

    def get_ai(self, name: str, block: int = 0) -> float:
        """Get analog input by logical name.

        Args:
            name: Logical name from io_mapping.analog_inputs.
            block: Blocking mode (0=non-blocking, 1=blocking).

        Returns:
            Analog value in volts (0-10V range).

        Raises:
            GripperIOError: If pin name not found or IO operation fails.
        """
        if name in self._io_mapping.tool_ai:
            tool = True
            pin_id = self._io_mapping.tool_ai[name]
        elif name in self._io_mapping.box_ai:
            tool = False
            pin_id = self._io_mapping.box_ai[name]
        else:
            raise GripperIOError(
                operation="get_ai",
                pin_name=name,
                original_error=ValueError(
                    f"Analog input '{name}' not found in IO mapping"
                ),
            )
        
        try:
            return self._tool_io.get_ai(pin_id, self._io_state, block=block, tool=tool)
        except ToolIOError as e:
            raise GripperIOError(operation="get_ai", pin_name=name, original_error=e)

    def set_ao(self, name: str, value: float, block: int = 0) -> None:
        """Set analog output by logical name.

        Args:
            name: Logical name from io_mapping.analog_outputs.
            value: Analog value to set (0-100 range, represents 0-10V or custom range).
            block: Blocking mode (0=non-blocking, 1=blocking).

        Raises:
            GripperIOError: If pin name not found or IO operation fails.
        """
        if name in self._io_mapping.tool_ao:
            tool = True
            pin_id = self._io_mapping.tool_ao[name]
        elif name in self._io_mapping.box_ao:
            tool = False
            pin_id = self._io_mapping.box_ao[name]
        else:
            raise GripperIOError(
                operation="set_ao",
                pin_name=name,
                original_error=ValueError(
                    f"Analog output '{name}' not found in IO mapping"
                ),
            )

        try:
            self._tool_io.set_ao(pin_id, value, block=block, tool=tool)
        except ToolIOError as e:
            raise GripperIOError(operation="set_ao", pin_name=name, original_error=e)

    def get_do_status(self) -> int:
        """Get raw status of all digital outputs.

        Returns:
            Integer with bit flags for all DO pins.

        Raises:
            GripperIOError: If IO operation fails.
        """
        try:
            return self._tool_io.get_do_status(self._io_state)
        except ToolIOError as e:
            raise GripperIOError(
                operation="get_do_status", pin_name="all", original_error=e
            )


class BaseGripper(ABC):
    """Abstract base class for robot grippers.

    All gripper implementations must inherit from this class and implement
    the abstract methods. Grippers have direct access to robot instance
    for reading robot_state_pkg and performing IO operations.

    Attributes:
        _robot: Robot instance for accessing robot_state_pkg and IO.
        _message_logger: Logger for gripper messages.
    """

    def __init__(self, robot, config, message_logger=None):
        """Initialize base gripper.

        Args:
            robot: Robot instance with robot_state_pkg access.
            config: Configuration object with IO mapping.
            message_logger: Logger for gripper operations.
        """
        self._robot = robot
        self._config = config
        self._message_logger = message_logger
        self._io_manager = IOManager(
            self._robot, self._config.io_mapping, self._message_logger
        )

    @abstractmethod
    def get_robot_config(self) -> RobotToolConfig:
        """Get robot tool configuration for this gripper.

        Returns:
            RobotToolConfig with tool coordinates, weight, etc.
        """
        pass

    @abstractmethod
    def get_io_mapping(self) -> IOMapping:
        """Get IO pin mapping for this gripper.

        Returns:
            IOMapping with logical names mapped to physical pins.
        """
        pass

    @abstractmethod
    def process_event(self, event) -> EventResult:
        """Process an event directed at this gripper.

        This method should execute IO operations and return the result.
        It should NOT include watchdog logic - only IO actions.

        Args:
            event: Event object with event_type and parameters.

        Returns:
            EventResult indicating success/failure and any data.
        """
        pass

    @abstractmethod
    def update_io_state(self, io_state: dict) -> None:
        """Update gripper internal state from robot IO state dict.

        Called at supervisor_frequency (10 Hz in movement loop, 1 Hz in get_status_update).
        Gripper decides which fields to read and process from io_state dict.

        Args:
            io_state: Dict with IO fields from robot_state_pkg.
                Standard keys: tl_dgt_output_l, tl_dgt_input_l, tl_anglog_input.
                Gripper can use any subset of these fields as needed.

        Note:
            This is the ONLY place where gripper reads IO state.
            get_state() and check_errors() use data updated by this method.
        """
        pass

    @abstractmethod
    def get_state(self) -> Dict[str, Any]:
        """Get current gripper state from last update_io_state() call.

        Returns processed state without reading IO hardware.
        Uses data updated by most recent update_io_state() call.

        Returns:
            Dictionary with gripper-specific state (e.g., {"holding": bool, "pressure_kpa": float}).
        """
        pass

    @abstractmethod
    def check_errors(self) -> Optional[GripperError]:
        """Check for gripper errors based on current internal state.

        This method implements gripper-specific error detection logic
        (e.g., watchdog monitoring). Gripper tracks its own context
        internally via lifecycle callbacks.

        Returns:
            GripperError if an error is detected, None otherwise.
        """
        pass

    def on_initialize(self) -> None:
        """Called when robot controller initializes gripper tool configuration.

        Gripper can perform initialization tasks like:
        - Reset internal state
        - Validate hardware connections
        - Initialize timers or buffers

        Note:
            Override this method if gripper needs initialization logic.
            Default implementation does nothing.
        """
        pass

    def on_enable(self) -> None:
        """Called when robot controller initializes gripper systems.

        Gripper can perform initialization tasks like:
        - Reset internal state
        - Validate hardware connections
        - Initialize timers or buffers

        Note:
            Override this method if gripper needs initialization logic.
            Default implementation does nothing.
        """
        pass

    def on_disable(self) -> None:
        """Called when robot controller shuts down.

        Gripper can perform cleanup tasks like:
        - Turn off actuators
        - Save state
        - Release resources

        Note:
            Override this method if gripper needs cleanup logic.
            Default implementation does nothing.
        """
        pass

    def on_path_start(self, path) -> None:
        """Called when robot starts executing a path.

        Gripper can:
        - Read path.testing_move and adjust internal behavior
        - Prepare for movement (e.g., adjust watchdog timeouts)
        - Log path parameters for context

        Args:
            path: Path object with waypoints and execution parameters.

        Note:
            Override this method if gripper needs path start logic.
            Default implementation does nothing.
        """
        pass

    def on_waypoint_reached(self, waypoint) -> None:
        """Called when robot reaches a waypoint during movement.

        Gripper can:
        - Trigger waypoint-specific actions
        - Update internal timers or state
        - Read waypoint parameters (e.g., watchdog_override)

        Args:
            waypoint: Waypoint object that was just reached.

        Note:
            Override this method if gripper needs waypoint logic.
            Default implementation does nothing.
        """
        pass

    def on_path_end(self, path) -> None:
        """Called when robot finishes path execution.

        Gripper can:
        - Reset path-specific state
        - Log completion
        - Prepare for next operation

        Args:
            path: Path object that just completed.

        Note:
            Override this method if gripper needs path end logic.
            Default implementation does nothing.
        """
        pass

    def validate_path_completion(self, path) -> bool:
        """Validate gripper state after path completes.

        For testing_move paths, gripper validates its own success criteria.
        Each gripper type defines what constitutes successful completion.

        Args:
            path: Path object to validate against.

        Returns:
            bool: True if gripper state is valid, False otherwise.

        Note:
            Override this method to implement gripper-specific validation.
            Default implementation always returns success.
        """
        return True

    def get_supported_events(self) -> set:
        """Get set of event types supported by this gripper.

        Returns:
            Set of event event_type strings (e.g., {"pump_on", "pump_off"}).

        Note:
            Override this method to define gripper-specific events.
            Default implementation returns empty set.
        """
        return set()

    def validate_event(self, event) -> bool:
        """Validate whether this gripper can handle the given event.

        Args:
            event: Event object with event_type to validate.

        Returns:
            True if event.event_type is in supported events, False otherwise.
        """
        return event.event_type in self.get_supported_events()
