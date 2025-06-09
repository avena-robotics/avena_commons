"""
## Error Level Utility

This module provides a utility for managing error levels and taking actions based on the error group.

# Usage:

1. ErrorManager:
    1.1 Initialization:
        error_manager = ErrorManager(message_logger, suffix)

    1.2 Set error:
        error_manager.set_error(ErrorCodes.CONNECTION_ERROR, "Failed to connect to the server")

    1.3 Acknowledge errors:
        error_manager.ack_errors()

    1.4 Acknowledge specific error:
        error_manager.ack_error(ErrorCodes.SOME_ERROR)

    1.5 Check current group:
        bool(true/false) = error_manager.check_current_group(ErrorGroups.CRITICAL)

    1.6 Check current error:
        bool(true/false) = error_manager.check_current_error(ErrorCodes.CONNECTION_ERROR)

    1.7 Get error history:
        error_history = error_manager.get_error_history()

2. ErrorInfo - every error is stored as an ErrorInfo object:
    2.1 Initialization:
        error = ErrorInfo(ErrorCodes.CONNECTION_ERROR, ErrorGroups.CRITICAL, "Failed to connect to the server")

    2.2 Get error code:
        error_code = error.error_code

    2.3 Get error group:
        error_group = error.error_group

    2.4 Get message:
        message = error.message

3. Error codes and groups:
    Error codes:\n
        CONNECTION_ERROR: Connection error
        RUN_PROGRAM_ERROR: Error while running the program
        INITIALIZATION_ERROR: Initialization error
        START_DISTANCE_ERROR: Error in starting distance
        CONTINUE_WORK_ERROR: Error in continuing work
        PUMP_WATCHDOG_ERROR: Watchdog error
        CAMERA_ERROR: Camera error
        GENERATING_ERROR: Error in generating
        DEVICE_ERROR: Device error
        PUMP_ERROR: Pump error
        DISTANCE_ERROR: Distance error
        TRAJECTORY_LOADING_ERROR: Trajectory loading error
        CHAIN_ERROR: Chain error
        TORQUE_ERROR: Torque error
        TORQUE_THRESHOLD_ERROR: Torque threshold error
        UNKNOWN_ERROR: Unknown error
        COMMON_WARNING: Device warning
        DEVICE_WARNING: Device warning
        QR_WARNING: QR warning
        SEMAPHORE_LOCK_WARNING: Semaphore lock warning
        NO_ERROR: No error

    Error groups:
        CRITICAL: Critical errors
        ERROR: Errors
        WARNING: Warnings
        INFO: Informational messages

4. ErrorCodeException:
    4.1 Custom exception handling:
        try:
            raise ErrorCodeException(ErrorCodes.CONNECTION_ERROR, "Failed to connect to the server")
        except ErrorCodeException as ce:
            error_code = ce.error_code
            error_message = ce.message

## Example of usage:
```python
try:
    error_manager = ErrorManager(message_logger, suffix)

    while True:
        error_manager.set_error(ErrorCodes.CONNECTION_ERROR, "Failed to connect to the server")

        current_error = error_manager.current_error    # => lista [ErrorInfo(ErrorCodes.CONNECTION_ERROR, ErrorGroups.CRITICAL, "Failed to connect to the server", ...])
        if error_manager.check_current_group(ErrorGroups.CRITICAL):
            #Przerwij program
            error_manager.ack_errors()
        elif error_manager.check_current_group(ErrorGroups.ERROR):
            #powtórz program
            error_manager.ack_errors()
        elif error_manager.check_current_group(ErrorGroups.WARNING):
            #kontynuuj program, nic nie rób

        if check_current_error = error_manager.check_current_error(ErrorCodes.CONNECTION_ERROR):
            # do something for this specific error
except KeyboardInterrupt:
    pass
finally:
    error_manager.stop()
```
## Contributors:
- Damian Gawin

"""

import copy
import os
import threading
from enum import Enum, auto

from .control_loop import ControlLoop
from .logger import error, info, warning

# Check if running on Windows
IS_WINDOWS = os.name == "nt"

if not IS_WINDOWS:
    from ..connection.shm import AvenaComm as shm

if IS_WINDOWS:
    warning("ErrorManager is not supported on Windows due to POSIX IPC requirements")

    # Dummy ErrorManager for Windows systems
    class ErrorManager:
        """Dummy ErrorManager for Windows systems - IPC functionality disabled"""

        def __init__(self, suffix, message_logger=None, debug=False):
            warning("ErrorManager is not supported on Windows - using dummy implementation")
            self._message_logger = message_logger

        def set_error(self, error_code, msg=""):
            warning(
                f"Error occurred but not propagated (Windows): {error_code} - {msg}",
                self._message_logger,
            )

        def ack_errors(self):
            pass

        def ack_error(self, error_code):
            pass

        def check_current_group(self, groups):
            return False

        def check_current_error(self, error_code):
            return False

        def get_error_history(self):
            return []

        def stop(self):
            pass

else:
    # Original ErrorManager implementation for POSIX systems
    class ErrorManager:
        """Error manager class.

        :param suffix: Suffix - number for the shared memory
        :param message_logger: Message logger

        :param current_error: Current error
        :type current_error: list
        """

        def __init__(self, suffix, message_logger=None, debug=False):
            self.__message_logger = message_logger

            self.__error_interface = ErrorInterface(log=False)

            self.__comm = shm(
                comm_name=f"error_manager_{suffix}",
                shm_size=100_000,
                semaphore_timeout=0.01,
                data=self.__error_interface,
                message_logger=self.__message_logger,
                debug=debug,
            )

            self.__cl = ControlLoop(
                name="manager_loop",
                warning_printer=False,
                period=1 / 1000,
                message_logger=self.__message_logger,
            )  # 1000hz
            self.__shm_freq = 1000 / 100  # 50hz/100hz

            self.__set_error = False
            self.__ack_errors = False
            self.__ack_error = None

            self.__stop_event = threading.Event()
            self.__connect()
            self.__update_msg_logger()

        def __connect(self):
            self._t1 = threading.Thread(target=self.__run)
            self._t1.start()

        def __run(self):
            os.nice(15)
            try:
                while not self.__stop_event.is_set():
                    self.__cl.loop_begin()  # 1000hz
                    if self.__cl.loop_counter % self.__shm_freq == 0:  # 50hz
                        check, interface = self.__comm.lock_and_read()
                        if check:
                            if self.__set_error:
                                self.__set_error = False
                                try:
                                    interface.set_error(self.__error_interface.current_error.pop())
                                except IndexError:
                                    pass

                            elif self.__ack_errors:
                                self.__ack_errors = False
                                interface.ack_errors()

                            elif self.__ack_error is not None:
                                interface.ack_error(self.__ack_error)
                                self.__ack_error = None

                            self.__comm.save_and_unlock(interface)
                            self.__error_interface = copy.deepcopy(interface)
                            self.__update_msg_logger()

                    self.__cl.loop_end()
            except KeyboardInterrupt:
                pass
            except Exception as e:
                error(
                    f"Error interface loop error: {e}",
                    message_logger=self.__message_logger,
                )
                raise
            finally:
                self.__comm.save_and_unlock(interface)
                # print(f"Closing error manager interface")

        @property
        def current_error(self):
            return self.__error_interface.current_error

        @current_error.setter
        def current_error(self, *args) -> None:
            raise AttributeError("Cannot set current_error attribute")

        def set_error(self, error_code, msg=""):
            self.__error_interface.set_error(error_code, msg)
            self.__set_error = True

        def ack_errors(self):
            self.__ack_errors = True

        def ack_error(self, error_code):
            self.__ack_error = error_code

        def check_current_group(self, group):
            """Check if error group in current error.

            group (ErrorCodes): Error group to check, can be a list of groups

            """
            return self.__error_interface.check_current_group(group)

        def check_current_error(self, error_code):
            """Check if error code in current error.

            error_code (ErrorCodes): Error code to check, can be a list of error codes

            """
            return self.__error_interface.check_current_error(error_code)

        def get_error_history(self):
            return self.__error_interface.get_error_history()

        def __update_msg_logger(self):
            """Because we cant pickle logger"""
            self.__error_interface._log = True
            self.__error_interface._message_logger = self.__message_logger

        def stop(self):
            self.__stop_event.set()
            self._t1.join()


class ErrorCodes(Enum):
    # Defining error codes with auto() for simplicity
    CONNECTION_ERROR = auto()
    RUN_PROGRAM_ERROR = auto()
    INITIALIZATION_ERROR = auto()
    CONTINUE_WORK_ERROR = auto()
    PUMP_WATCHDOG_ERROR = auto()
    CAMERA_ERROR = auto()
    GENERATING_ERROR = auto()
    DEVICE_ERROR = auto()
    PUMP_ERROR = auto()
    INTERRUPT_ERROR = auto()
    DISTANCE_ERROR = auto()
    TRAJECTORY_ERROR = auto()
    TRAJECTORY_LOADING_ERROR = auto()
    CHAIN_ERROR = auto()
    TORQUE_ERROR = auto()
    TORQUE_THRESHOLD_ERROR = auto()
    UNKNOWN_ERROR = auto()
    COMMON_WARNING = auto()
    DEVICE_WARNING = auto()
    QR_WARNING = auto()
    SEMAPHORE_LOCK_WARNING = auto()
    NO_ERROR = auto()


class ErrorGroups(Enum):
    CRITICAL = 0
    ERROR = 1
    WARNING = 2
    INFO = 3
    UNKNOWN = 4


class InvalidError(Exception):
    pass


class ErrorCodeException(Exception):
    """Usage example \n

    attributes:
        - error_code (ErrorCodes): Error code
        - message (str): Custom message if needed

    try:
        raise ErrorCodeException(ErrorCodes.CONNECTION_ERROR, "Failed to connect to the server")
    except ErrorCodeException as ce:
        print(ce)
    """

    def __init__(self, error_code: ErrorCodes, message: str = "An error occurred"):
        self.error_code = error_code
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> tuple[ErrorCodes, str]:
        return f"{self.error_code}, {self.message}"


class ErrorInfo:
    """Class to store error information.

    attributes:
        - error_code (ErrorCodes): Error code
        - error_group (ErrorGroups): Error group
        - message (str): Custom message if needed

    example:
        error_info = ErrorInfo(ErrorCodes.CONNECTION_ERROR, ErrorGroups.CRITICAL, "Failed to connect to the server")
        print(error_info) -> Error: ErrorCodes.CONNECTION_ERROR, Group: ErrorGroups.CRITICAL, Message: "Failed to connect to the server"
        print(error_info.error_code) -> ErrorCodes.CONNECTION_ERROR
        print(error_info.error_group) -> ErrorGroups.CRITICAL
        print(error_info.message) -> "Failed to connect to the server"
    """

    def __init__(self, error_code, error_group, message):
        self.error_code = error_code
        self.error_group = error_group
        self.message = message

    def __str__(self) -> str:
        return f"Error: {self.error_code.name}, Group: {self.error_group.name}, Message: {self.message}"

    def __repr__(self) -> str:
        return f"Error: {self.error_code.name}, Group: {self.error_group.name}, Message: {self.message}"


class ErrorInterface:
    """Class to manage errors and take actions based on the error group.

    attributes:
        - current_error
    methods:
        - set_error(error_code, msg='')
        - ack_errors()
        - get_error_history()
    """

    def __init__(self, log=True):
        self._message_logger = None
        self._log = log
        self.__error_groups = {
            ErrorCodes.CONNECTION_ERROR: ErrorGroups.CRITICAL,
            ErrorCodes.RUN_PROGRAM_ERROR: ErrorGroups.CRITICAL,
            ErrorCodes.INITIALIZATION_ERROR: ErrorGroups.CRITICAL,
            ErrorCodes.CONTINUE_WORK_ERROR: ErrorGroups.CRITICAL,
            ErrorCodes.TORQUE_THRESHOLD_ERROR: ErrorGroups.CRITICAL,
            ErrorCodes.PUMP_WATCHDOG_ERROR: ErrorGroups.ERROR,
            ErrorCodes.CAMERA_ERROR: ErrorGroups.ERROR,
            ErrorCodes.GENERATING_ERROR: ErrorGroups.ERROR,
            ErrorCodes.DEVICE_ERROR: ErrorGroups.ERROR,
            ErrorCodes.PUMP_ERROR: ErrorGroups.ERROR,
            ErrorCodes.INTERRUPT_ERROR: ErrorGroups.ERROR,
            ErrorCodes.DISTANCE_ERROR: ErrorGroups.ERROR,
            ErrorCodes.TRAJECTORY_LOADING_ERROR: ErrorGroups.ERROR,
            ErrorCodes.TRAJECTORY_ERROR: ErrorGroups.ERROR,
            ErrorCodes.CHAIN_ERROR: ErrorGroups.ERROR,
            ErrorCodes.TORQUE_ERROR: ErrorGroups.ERROR,
            ErrorCodes.UNKNOWN_ERROR: ErrorGroups.ERROR,
            ErrorCodes.COMMON_WARNING: ErrorGroups.WARNING,
            ErrorCodes.DEVICE_WARNING: ErrorGroups.WARNING,
            ErrorCodes.QR_WARNING: ErrorGroups.WARNING,
            ErrorCodes.SEMAPHORE_LOCK_WARNING: ErrorGroups.WARNING,
            ErrorCodes.NO_ERROR: ErrorGroups.INFO,
        }
        self.__error_actions = {
            ErrorGroups.CRITICAL: [],
            ErrorGroups.ERROR: [],
            ErrorGroups.WARNING: [],
            ErrorCodes.NO_ERROR: [],
        }
        self.__current_error = []
        self.__error_history = []

    @property
    def current_error(self):
        """Get the current error, its group and message.

        Returns:
            ErrorInfo: ErrorInfo object containing error code, group, and message
        """
        return self.__current_error

    @current_error.setter
    def current_error(self, *args):
        pass

    @property
    def error_groups(self):
        return self.__error_groups

    @error_groups.setter
    def error_groups(self, *args):
        raise AttributeError("Cannot set error_groups attribute")

    def set_error(self, error_code, msg=""):
        """Set an error and take action based on the error group.

        Args:
            error_code (ErrorCodes): Error code to set
            msg (str, optional): Custom message if needed. Defaults to ''.
            message_logger (_type_, optional): Message_logger. Defaults to None.

        Raises:
            InvalidError: If an invalid error code is provided
        """
        new_current_error = None

        if isinstance(error_code, ErrorInfo):
            new_current_error = error_code
            msg = error_code.message
        elif isinstance(error_code, str):
            try:
                error_code = ErrorCodes[error_code]
                new_current_error = ErrorInfo(error_code, self.get_group(error_code), msg)
            except KeyError:
                raise InvalidError("Invalid error code provided")
        elif isinstance(error_code, int):
            try:
                error_code = ErrorCodes(error_code)
                new_current_error = ErrorInfo(error_code, self.get_group(error_code), msg)
            except ValueError:
                raise InvalidError("Invalid error code provided")
        else:
            try:
                new_current_error = ErrorInfo(error_code, self.get_group(error_code), msg)
            except Exception as e:
                raise InvalidError(f"Invalid error code provided: {e}")

        self.__error_history.append(new_current_error)
        if self.__current_error:
            for i, current in enumerate(self.__current_error):
                if current.error_code == new_current_error.error_code:
                    return
                else:
                    if i == len(self.__current_error) - 1:
                        self.__current_error.append(new_current_error)
        else:
            self.__current_error.append(new_current_error)

        if self._log:
            self.__log_error(new_current_error)
        # self._take_action() # will do every registered action for that group

    def ack_errors(self):
        """Acknowledge errors and clear the error history."""
        self.__error_history.clear()
        self.__current_error = []  # Reset current error when acknowledging errors
        self._current_message = ""

    def ack_error(self, error_code):
        """Acknowledge specific error. Which can be a list or a single error code."""
        if not isinstance(error_code, list):
            error_code = [error_code]
        for code in error_code:
            for i, error in enumerate(self.__current_error):
                if error.error_code == code:
                    self.__current_error.pop(i)
        return

    def get_error_history(self):
        """Get the error history.

        Returns:
            list: List of tuples containing error code, group, and message
        """
        return self.__error_history

    def check_current_group(self, groups):
        """Check if error group(s) in current error."""
        if not isinstance(groups, list):
            groups = [groups]
        for group in groups:
            for error in self.__current_error:
                if error.error_group == group:
                    return True
        return False

    def check_current_error(self, error_code):
        """Check if error code in current error."""
        if not isinstance(error_code, list):
            error_code = [error_code]
        for code in error_code:
            for error in self.__current_error:
                if error.error_code == code:
                    return True
        return False

    def get_group(self, error_code):
        return self.__error_groups.get(error_code, ErrorGroups.UNKNOWN)

    def __log_error(self, new_error):
        group = new_error.error_group
        error_message = f"Error: {new_error.error_code.name}, Group: {new_error.error_group.name}"
        if new_error.message:
            error_message += f", Message: {new_error.message}"

        if group == ErrorGroups.CRITICAL:
            error(error_message, message_logger=self._message_logger)
        elif group == ErrorGroups.ERROR:
            error(error_message, message_logger=self._message_logger)
        elif group == ErrorGroups.WARNING:
            warning(error_message, message_logger=self._message_logger)
        else:
            info(error_message, message_logger=self._message_logger)

    # def register_action(self, group, action):
    #     """Register an action to be taken when an error of the specified group is set.

    #     Args:
    #         group (ErrorGroups): Error group
    #         action (Object action): Action to be taken
    #     """
    #     if group in self.__error_actions:
    #         self.__error_actions[group].append(action)
    #     else:
    #         self.__error_actions[group] = [action]

    # def remove_action(self, group, action):
    #     """Remove an action from the list of actions to be taken when an error of the specified group is set.

    #     Args:
    #         group (ErrorGroups): Error group
    #         action (Object action): Action to be removed
    #     """
    #     if group in self.__error_actions:
    #         self.__error_actions[group].remove(action)

    # def remove_all_actions(self):
    #     """Remove all actions from the list of actions to be taken when an error of the specified group is set.
    #     """
    #     self.__error_actions.clear()

    # def _take_action(self):
    #     group = self.__current_error.error_group
    #     actions = self.__error_actions.get(group, [])
    #     for action in actions:
    #         action()  # Wywołanie każdej zarejestrowanej akcji
    #     if self._log:
    #         debug(f"{group} action taken: {[action.__name__ for action in actions]}", self._message_logger)
