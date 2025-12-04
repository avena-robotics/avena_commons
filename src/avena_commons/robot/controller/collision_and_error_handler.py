"""Obsługa kolizji i błędów dla nadzorcy robota.

Zapewnia wykrywanie kolizji, resetowanie błędów, ograniczoną liczbę prób odzyskania ruchu
i weryfikację „bezpiecznego” przesunięcia po kolizji. Styl Google, język polski.
"""

import time

from avena_commons.util.logger import debug


class CollisionAndErrorHandler:
    """
    Handles collision detection, recovery, and tracking for robot supervisor.

    This class encapsulates the logic for detecting collisions, handling recovery attempts,
    and tracking safe movement after collisions.
    """

    def __init__(self, robot, message_logger=None, debug=False):
        """
        Initialize the CollisionAndErrorHandler.

        Args:
            robot: Robot controller object with access to status and error info
            message_logger: Logger for writing messages
            debug (bool): Whether to output debug information
        """
        self._robot = robot
        self._message_logger = message_logger
        self._debug = debug
        self._last_collision_position = None
        self._recovery_attempts = 0
        self._max_recovery_attempts = 3
        self._safe_movement_distance = 100  # mm of safe movement to reset collision recovery

    def detect_errors(self):
        """
        Check robot status to detect if a collision has occurred.

        Returns:
            bool: True if collision was detected, False otherwise

        Raises:
            Exception: If robot reports non-collision errors or reset fails
        """
        main_code = self._robot.robot_state_pkg.main_code
        sub_code = self._robot.robot_state_pkg.sub_code

        if main_code == 0 and sub_code == 0:
            return False  # No errors detected

        # Get error description if available from error codes
        try:
            from .error_codes import FAIRINO_ERROR_CODES

            error_name = FAIRINO_ERROR_CODES[main_code]["name"]
            error_description = FAIRINO_ERROR_CODES[main_code]["sub_codes"][sub_code]
        except (KeyError, ImportError):
            error_name = f"Unknown error {main_code}"
            error_description = f"Unknown subcode {sub_code}"

        # Handle collision fault specially
        if error_name == "collision fault":
            if self._debug:
                debug(f"Collision detected: {main_code}.{sub_code}: {error_description}", self._message_logger)

            # Reset the error
            reset_result = self._robot.ResetAllError()
            if self._debug:
                debug(f"Reset result: {main_code}.{sub_code}", self._message_logger)
            time.sleep(1.0)  # Short delay to allow robot status to update
            # Resume motion after reset
            resume_result = self._robot.ResumeMotion()

            if reset_result != 0 or resume_result != 0:
                # If error can't be reset, we need to raise exception
                raise Exception(f"Failed to reset collision error: {reset_result}")
            return True  # Signal that a collision was detected and handled

        # For non-collision errors, raise exception
        raise Exception(f"Robot current errors {main_code}.{sub_code}: {error_name} => {error_description}")
    
    def handle_recovery(self, robot, current_position, send_move_commands_fn, movetype, waypoints, max_speed=None):
        """
        Handle collision recovery by incrementing attempts and sending commands.

        Args:
            current_position: Current robot position for tracking
            send_move_commands_fn: Function to send move commands to robot
            movetype: Type of movement to execute
            waypoints: List of waypoints to send
            max_speed: Maximum speed limit

        Returns:
            bool: True if recovery was successful, False if max attempts exceeded

        Raises:
            Exception: If maximum recovery attempts are exceeded
        """
        # Record collision position if this is a new collision sequence
        if self._recovery_attempts == 0:
            self._last_collision_position = current_position

        # Increment recovery counter
        self._recovery_attempts += 1

        # Check if we've exceeded maximum attempts
        if self._recovery_attempts > self._max_recovery_attempts:
            self._robot.StopMotion()
            raise Exception(f"Too many collision recovery attempts: {self._recovery_attempts}")

        # Log and add delay before retry
        if self._debug:
            debug(
                f"Continuing after collision ({self._recovery_attempts}/{self._max_recovery_attempts}). Remaining waypoints: {len(waypoints)}",
                self._message_logger,
            )
        # Disable robot temporarily to allow it to reset waypoints stored in it's memory
        robot.RobotEnable(state=0)
        time.sleep(2.0)  # Wait before retry
        debug("Robot disabled for collision recovery", self._message_logger)

        # Re-enable robot
        robot.RobotEnable(state=1)
        time.sleep(2.0)  # Wait before retry
        debug("Robot re-enabled for collision recovery", self._message_logger)
        # Send remaining waypoints to robot
        send_move_commands_fn(movetype, waypoints, max_speed=max_speed)

        return True

    def check_safe_movement(self, calculate_distance_fn, current_position):
        """
        Check if robot has moved a safe distance since the last collision.

        Args:
            calculate_distance_fn: Function to calculate distance between positions
            current_position: Current robot position

        Returns:
            bool: True if safe distance moved and recovery counters should be reset
        """
        # If no recovery attempts active, nothing to check
        if self._recovery_attempts == 0 or self._last_collision_position is None:
            return False

        # Calculate distance moved since collision
        distance = calculate_distance_fn(self._last_collision_position, current_position)

        # If we've moved a safe distance, reset recovery counters
        if distance > self._safe_movement_distance:
            if self._debug:
                debug(
                    f"Robot moved {distance:.2f}mm safely after collision, resetting recovery counter",
                    self._message_logger,
                )
            self.reset()
            return True

        return False

    def reset(self):
        """Reset all collision tracking and recovery counters."""
        self._recovery_attempts = 0
        self._last_collision_position = None

    @property
    def recovery_attempts(self):
        """Get the current number of recovery attempts."""
        return self._recovery_attempts

    @property
    def max_recovery_attempts(self):
        """Get the maximum allowed recovery attempts."""
        return self._max_recovery_attempts

    @max_recovery_attempts.setter
    def max_recovery_attempts(self, value):
        """Set the maximum allowed recovery attempts."""
        if not isinstance(value, int) or value < 1:
            raise ValueError("Max recovery attempts must be a positive integer")
        self._max_recovery_attempts = value
