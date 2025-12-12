"""Universal robot tool IO operations.

Provides unified interface for Digital Output (DO), Digital Input (DI),
Analog Output (AO), and Analog Input (AI) operations with consistent
error handling and validation.
"""


class ToolIOError(Exception):
    """Exception for tool IO operation errors."""

    def __init__(self, io_type: str, operation: str, message: str):
        """Initialize tool IO error.

        Args:
            io_type: Type of IO (DO, DI, AO, AI).
            operation: Operation that failed (get, set).
            message: Error message.
        """
        self.io_type = io_type
        self.operation = operation
        super().__init__(f"Tool {io_type} {operation} failed: {message}")


class ToolIO:
    """Universal interface for robot tool IO operations.

    Provides unified error handling, validation, and logging for all
    robot tool IO operations. Can be used directly or wrapped by
    higher-level managers (like IOManager with name mapping).

    Attributes:
        _robot: Robot instance with tool IO methods.
        _message_logger: Logger for IO operations.
    """

    def __init__(self, robot, message_logger=None):
        """Initialize tool IO manager.

        Args:
            robot: Robot instance with GetToolDO/SetToolDO/etc methods.
            message_logger: Optional logger for operations.
        """
        self._robot = robot
        self._message_logger = message_logger

    @staticmethod
    def is_bit_set(value: int, bit_position: int) -> bool:
        """Check if specific bit is set in integer value.

        Args:
            value: Integer value to check.
            bit_position: Bit position (0-based).

        Returns:
            True if bit is set, False otherwise.
        """
        return bool((value >> bit_position) & 1)

    def get_do(self, pin: int, io_state: dict, block: int = 0, tool: bool = False) -> bool:
        """Get digital output status by pin number.

        Reads from io_state dict containing robot_state_pkg snapshot.

        Args:
            pin: DO pin number (0-based).
            io_state: Dict with IO state from robot_state_pkg (keys: c/tl_dgt_output_l, c/tl_dgt_input_l, c/tl_anglog_input).
            block: Blocking mode (0=non-blocking, 1=blocking) - ignored, uses state dict.

        Returns:
            True if DO is high, False if low.

        Raises:
            ToolIOError: If operation fails or parameters invalid.
        """
        if tool:
            if not (0 <= pin <= 1):
                raise ToolIOError("DO", "get", f"Invalid tool DO pin {pin}. Must be 0-1.")
        else:
            if not (0 <= pin <= 15):
                raise ToolIOError("DO", "get", f"Invalid pin BOX {pin}. Must be 0-15.")

        try:
            # Read from io_state dict instead of robot_state_pkg
            if tool:
                status = io_state.tl_dgt_output_tool
            else:
                if pin >= 8:
                    status = io_state.cl_dgt_output_h
                else:
                    status = io_state.cl_dgt_output_l
            result = self.is_bit_set(status, pin)
            return result
        except Exception as e:
            raise ToolIOError("DO", "get", str(e))

    def set_do(self, pin: int, value: bool, smooth: int = 0, block: int = 1, tool: bool = False) -> None:
        """Set digital output by pin number.

        Args:
            pin: DO pin number (0-based). Tool: 0-1, Control box: 0-15.
            value: True to set high, False to set low.
            smooth: Smooth transition (0=off, 1=on).
            block: Blocking mode (0=non-blocking, 1=blocking).
            tool: True for tool IO, False for control box IO.

        Raises:
            ToolIOError: If operation fails or parameters invalid.
        """
        if tool:
            if not (0 <= pin <= 1):
                raise ToolIOError("DO", "set", f"Invalid tool DO pin {pin}. Must be 0-1.")
        else:
            if not (0 <= pin <= 15):
                raise ToolIOError("DO", "set", f"Invalid control box DO pin {pin}. Must be 0-15.")

        if smooth not in [0, 1]:
            raise ToolIOError("DO", "set", f"Invalid smooth {smooth}. Must be 0 or 1.")

        if block not in [0, 1]:
            raise ToolIOError("DO", "set", f"Invalid block {block}. Must be 0 or 1.")

        status = 1 if value else 0

        try:
            if tool:
                error_code = self._robot.SetToolDO(pin, status, smooth=smooth, block=block)
            else:
                error_code = self._robot.SetDO(pin, status, smooth=smooth, block=block)
            if error_code != 0:
                raise ToolIOError(
                    "DO", "set", f"Robot returned error code {error_code}"
                )
        except ToolIOError:
            raise
        except Exception as e:
            raise ToolIOError("DO", "set", str(e))

    def get_di(self, pin: int, io_state: dict = None, block: int = 0, tool: bool = False) -> bool:
        """Get digital input status by pin number.

        Args:
            pin: DI pin number (0-based). Tool: 0-1, Control box: 0-15.
            io_state: Dict with IO state from robot_state_pkg (optional, for future use).
            block: Blocking mode (0=non-blocking, 1=blocking).
            tool: True for tool IO, False for control box IO.

        Returns:
            True if DI is high, False if low.

        Raises:
            ToolIOError: If operation fails or parameters invalid.
        """
        if tool:
            if not (0 <= pin <= 1):
                raise ToolIOError("DI", "get", f"Invalid tool DI pin {pin}. Must be 0-1.")
        else:
            if not (0 <= pin <= 15):
                raise ToolIOError("DI", "get", f"Invalid control box DI pin {pin}. Must be 0-15.")

        try:
            if tool:
                error, status = self._robot.GetToolDI(pin, block=block)
            else:
                error, status = self._robot.GetDI(pin, block=block)
            if error != 0:
                raise ToolIOError("DI", "get", f"Robot returned error code {error}")
            return bool(status)
        except ToolIOError:
            raise
        except Exception as e:
            raise ToolIOError("DI", "get", str(e))

    def get_ai(self, pin: int, io_state: dict = None, block: int = 0, tool: bool = False) -> float:
        """Get analog input value by pin number.

        Args:
            pin: AI pin number (0-based). Tool: 0, Control box: 0-2.
            io_state: Dict with IO state from robot_state_pkg (optional, for future use).
            block: Blocking mode (0=non-blocking, 1=blocking).
            tool: True for tool IO, False for control box IO.

        Returns:
            Analog value in percentage (0-100 range).

        Raises:
            ToolIOError: If operation fails or parameters invalid.
        """
        if tool:
            if not (0 <= pin <= 0):
                raise ToolIOError("AI", "get", f"Invalid tool AI pin {pin}. Must be 0.")
        else:
            if not (0 <= pin <= 2):
                raise ToolIOError("AI", "get", f"Invalid control box AI pin {pin}. Must be 0-2.")

        try:
            if tool:
                error, ai_value = self._robot.GetToolAI(pin, block=block)
            else:
                error, ai_value = self._robot.GetAI(pin, block=block)
            if error != 0:
                raise ToolIOError("AI", "get", f"Robot returned error code {error}")
            return float(ai_value)
        except ToolIOError:
            raise
        except Exception as e:
            raise ToolIOError("AI", "get", str(e))

    def set_ao(self, pin: int, value: float, block: int = 1, tool: bool = False) -> None:
        """Set analog output value by pin number.

        Args:
            pin: AO pin number (0-based). Tool: 0, Control box: 0-1.
            value: Analog value (0-100 range, represents 0-10V or 0-20mA).
            block: Blocking mode (0=non-blocking, 1=blocking).
            tool: True for tool IO, False for control box IO.

        Raises:
            ToolIOError: If operation fails or parameters invalid.
        """
        if tool:
            if not (0 <= pin <= 0):
                raise ToolIOError("AO", "set", f"Invalid tool AO pin {pin}. Must be 0.")
        else:
            if not (0 <= pin <= 1):
                raise ToolIOError("AO", "set", f"Invalid control box AO pin {pin}. Must be 0-1.")

        if not (0 <= value <= 100):
            raise ToolIOError("AO", "set", f"Invalid value {value}. Must be 0-100.")

        if block not in [0, 1]:
            raise ToolIOError("AO", "set", f"Invalid block {block}. Must be 0 or 1.")

        try:
            if tool:
                error_code = self._robot.SetToolAO(pin, value, block=block)
            else:
                error_code = self._robot.SetAO(pin, value, block=block)
            if error_code != 0:
                raise ToolIOError(
                    "AO", "set", f"Robot returned error code {error_code}"
                )
        except ToolIOError:
            raise
        except Exception as e:
            raise ToolIOError("AO", "set", str(e))

    def get_do_status(self, io_state: dict) -> int:
        """Get raw status of all digital outputs.

        Reads from io_state dict containing robot_state_pkg snapshot.

        Args:
            io_state: Dict with IO state from robot_state_pkg (keys: tl_dgt_output_l, tl_dgt_input_l, tl_anglog_input).

        Returns:
            Integer with bit flags for all DO pins.

        Raises:
            ToolIOError: If operation fails.
        """
        try:
            # Read from io_state dict instead of robot_state_pkg
            status = io_state.tl_dgt_output_l
            return status
        except Exception as e:
            raise ToolIOError("DO", "get_status", str(e))

    def decode_do_status(self, status: int) -> dict:
        """Decode DO status integer into dictionary.

        Args:
            status: Status integer from get_do_status().

        Returns:
            Dictionary with DO pin states {0: bool, 1: bool, ...}.
        """
        return {i: self.is_bit_set(status, i) for i in range(16)}
