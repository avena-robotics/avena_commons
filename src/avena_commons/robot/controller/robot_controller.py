"""Nadzorca robota Fairino: inicjalizacja, ruchy, integracja z chwytakiem i kamerą.

Udostępnia stany, sterowanie antykolizją, obsługę błędów oraz asynchroniczne oczekiwanie na
urządzenia. Dokumentacja w stylu Google, w języku polskim.
"""

import http.client
import math

# import sys
import threading
import time

try:
    import Robot
except ImportError:
    from avena_commons.util.logger import error

    error("Cannot import Robot module. Make sure the Fairino SDK is installed.")

from dotenv import load_dotenv

from avena_commons.event_listener.types import Path
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.control_loop import ControlLoop
from avena_commons.util.logger import (
    debug,
    error,
    info,
    warning,
)
from avena_commons.util.worker import Connector

from .collision_and_error_handler import CollisionAndErrorHandler
from .enum import MoveType, PostCollisionStrategy, RobotControllerState
from .error_codes import FAIRINO_ERROR_CODES
from .error_handler import handle_errors

try:
    from ..grippers.base import BaseGripper
except ImportError:
    BaseGripper = None

load_dotenv(override=True)


class RobotController(Connector):
    """
    Klasa Supervisor zarządza operacjami robota oraz jego stanem.

    Attributes:
        _state (RobotControllerState): Aktualny stan supervisora.
        _start_position: Referencja do pozycji startowej.
        _stop_event (threading.Event): Zdarzenie służące do zatrzymywania operacji.

    Description:
        Klasa odpowiedzialna za kontrolę cyklu życia robota, obsługę stanów oraz zarządzanie operacjami ruchu i peryferiami.
        Pozwala na inicjalizację, zatrzymywanie oraz monitorowanie pracy robota.
    """

    def __init__(
        self,
        suffix=1,
        message_logger=None,
        configuration=None,
        debug=False,
        gripper=None,
    ) -> None:
        """Inicjalizuje `Supervisor` zarządzający robotem i peryferiami.

        Args:
            suffix (int): Sufiks instancji (wpływa m.in. na porty klientów).
            message_logger: Logger do zapisu komunikatów.
            configuration (dict): Konfiguracja połączeń i parametrów pracy (wymagana).
            debug (bool): Czy włączyć tryb debug.
            gripper (Optional[BaseGripper]): Gripper instance for tool management.

        Raises:
            Exception: Gdy `configuration` nie została przekazana lub wystąpi błąd inicjalizacji.
        """

        if configuration is None:
            self._state = RobotControllerState.ERROR
            self._error_message = (f"{__name__}: Configuration must be provided",)
            return

        self.__configuration = configuration
        # self.__gripper_state = gripper_state
        self.__suffix = suffix
        self.__supervisor_frequency = self.__configuration["frequencies"]["supervisor"]
        self._gripper = gripper  # Modular gripper instance (optional)
        # self.__camera_enabled = self.__configuration["camera"]["enabled"]
        self._can_you_run_it = False
        self._start_max_distance = self.__configuration["general"][
            "start_position_distance"
        ]
        self._debug = debug

        self.__supervisor_overtime_info = {}

        self._message_logger = message_logger
        super().__init__(message_logger=message_logger)

        self._tool = 0  # tool coordinate system number for flange
        self._tool_weight = 0  # tool weight

        self._error_message = ""

        self._state = RobotControllerState.STOPPED
        self._status = {}
        # self.is_rotation = False
        self._start_position = None
        # self._camera_data = None
        self._interrupt = False
        self._testing_move_check = True
        self._last_waypoint = None

        self._robot_current_position = None
        self._current_waypoint = None
        self._current_path = None
        self._remaining_waypoints = []
        # Set the move distance threshold for checking if the robot is moving
        self._move_distance_counter = int(
            0.3 * self.__supervisor_frequency
        )  # 300ms to make sure we are not moving TODO: make it configurable .env
        self._move_distance = 0.1  # (mm) TODO: make it configurable .env

        self._post_collision_safe_timeout_s = float(
            self.__configuration["general"].get("post_collision_safe_timeout_s", 2.0)
        )
        self._sendRequests_retries = self.__configuration["general"][
            "send_requests_retries"
        ]  # Number of retries for sending requests

        self.max_distance_check = 0

        self._initialize_robot(self.__configuration["network"]["ip_address"])

        # Initialize collision handler
        self.robot_error_and_collision_handler = CollisionAndErrorHandler(
            self._robot, message_logger=self._message_logger, debug=self._debug
        )
        self._stop_event = threading.Event()

    @property
    def threads(self) -> int:
        """
        Zwraca liczbę aktywnych wątków.

        Returns:
            int: Liczba aktywnych wątków.
        """
        return threading.active_count()

    def _run(self, pipe_in):
        """
        Wewnętrzna metoda uruchamiająca główną pętlę Supervisora.

        Args:
            pipe_in (multiprocessing.Pipe): Rurka wejściowa do komunikacji z innymi procesami.
        """
        pass

    @property
    def status(self) -> dict:
        """
        Pobiera aktualny status supervisora.

        Returns:
            dict: Status supervisora.
        """
        return self._status

    @status.setter
    @Connector._read_only_property("status")
    def status(self, *args):
        pass

    @handle_errors()
    def get_status_update(self):
        """
        Pobiera aktualny status supervisora.

        Returns:
            dict: Status supervisora.
        """
        new_state_pkg = self.robot.robot_state_pkg

        main_code = new_state_pkg.main_code
        sub_code = new_state_pkg.sub_code
        joint_current_torque = list(new_state_pkg.jt_cur_tor)
        self._robot_current_position = self.cartesian_position

        # Get gripper state if gripper is configured
        gripper_state = {}
        gripper_type = None
        if self._gripper:
            gripper_type = type(self._gripper).__name__
            try:
                # Update gripper with full robot state snapshot
                self._gripper.update_io_state(new_state_pkg)
                info(f"Gripper IO state updated: CLDO{new_state_pkg.cl_dgt_output_l}, CLDI{new_state_pkg.cl_dgt_input_l}", self._message_logger)
                gripper_state = self._gripper.get_state()
            except Exception as e:
                gripper_state = {"error": str(e)}

        # Handle unknown error codes defensively
        try:
            error_name = FAIRINO_ERROR_CODES[main_code]["name"]
            error_description = FAIRINO_ERROR_CODES[main_code]["sub_codes"][sub_code]
        except (KeyError, TypeError):
            error_name = f"Unknown error {main_code}"
            error_description = f"Unknown subcode {sub_code}"
            warning(
                f"Unknown error code encountered: main_code={main_code}, sub_code={sub_code}",
                self._message_logger,
            )

        self._status.update({
            "state": self.state,
            "current_error": self._error_message,
            "robot_state": {
                "error_name": error_name,
                "error_description": error_description,
                "enable_state": new_state_pkg.rbtEnableState,
                "mode_state": new_state_pkg.robot_mode,
                "current_position": self._robot_current_position,
                "joint_current_torque": joint_current_torque,
            },
            "path_execution_state": {
                "start_position": self._start_position,
                "remaining_waypoints": self._remaining_waypoints,
                "current_waypoint": self._current_waypoint,
                "current_path": self._current_path,
                "interrupt": self._interrupt,
                "testing_move_check": self._testing_move_check,
            },
            "gripper_state": {
                "type": gripper_type,
                "state": gripper_state,
            },
        })

    @property
    def robot(self):
        """
        Pobiera obiekt Robot.

        Returns:
            object: Obiekt Robot.
        """
        return self._robot

    @robot.setter
    @Connector._read_only_property("robot")
    def robot(self, *args):
        pass

    @property
    @handle_errors()
    def joint_position(self):
        """
        Pobiera konfigurację zespołów robota.

        Returns:
            list: Konfiguracja zespołów robota w stopniach.
        """
        error, rconfig = self._robot.GetActualJointPosDegree(flag=1)
        if error == 0:
            return rconfig
        else:
            raise Exception(f"Error getting joint position: {error}")

    @joint_position.setter
    @Connector._read_only_property("joint_position")
    def joint_position(self, *args):
        pass

    @property
    @handle_errors()
    def cartesian_position(self):
        """
        Pobiera pozycję robota w układzie kartezjańskim.

        Returns:
            list: Pozycja robota w układzie kartezjańskim.
        """
        try:
            # error, pose = self._robot.GetActualTCPPose(flag=1)
            current_pose_from_state_pkg = list(self.robot.robot_state_pkg.tl_cur_pos)
        except http.client.CannotSendRequest as e:
            error(
                f"CannotSendRequest Error getting TCP pose: {e}", self._message_logger
            )
            raise e

        return current_pose_from_state_pkg

    @cartesian_position.setter
    @Connector._read_only_property("cartesian_position")
    def cartesian_position(self, *args):
        pass

    @property
    def can_you_run_it(self):
        """
        Sprawdza, czy robot może się poruszać.

        Returns:
            bool: True jeśli robot może się poruszać.
        """
        return self._can_you_run_it

    @can_you_run_it.setter
    def can_you_run_it(self, value: bool = False):
        """
        Ustawia flagę można uruchomić.

        Args:
            value (bool): Nowa wartość flagi można uruchomić.
        """
        self._can_you_run_it = value

    @property
    def state(self) -> RobotControllerState:
        """
        Pobiera aktualny stan supervisora.

        Returns:
            RobotControllerState: Aktualny stan supervisora.
        """
        return self._state

    @state.setter
    def state(self, state: RobotControllerState):
        """
        Ustawia stan supervisora.

        Args:
            state (RobotControllerState): Nowy stan supervisora.
        """
        self._state = state

    def change_anticollision_settings(
        self,
        j1: int | None = None,
        j2: int | None = None,
        j3: int | None = None,
        j4: int | None = None,
        j5: int | None = None,
        j6: int | None = None,
    ):
        """
        Zmienia ustawienia antykolizji robota. 1-100.

        Args:
            j1 (int): Poziom antykolizji dla stawu 1.
            j2 (int): Poziom antykolizji dla stawu 2.
            j3 (int): Poziom antykolizji dla stawu 3.
            j4 (int): Poziom antykolizji dla stawu 4.
            j5 (int): Poziom antykolizji dla stawu 5.
            j6 (int): Poziom antykolizji dla stawu 6.
        """
        if j1 is None:
            j1 = self.__configuration["collision_levels"]["j1"]
        else:
            if not (1 <= j1 <= 100):
                raise ValueError(
                    f"Joint 1 anticollision level must be between 1 and 100: {j1}"
                )
            else:
                self.__configuration["collision_levels"]["j1"] = (
                    j1  # Update state config
                )
        if j2 is None:
            j2 = self.__configuration["collision_levels"]["j2"]
        else:
            if not (1 <= j2 <= 100):
                raise ValueError(
                    f"Joint 2 anticollision level must be between 1 and 100: {j2}"
                )
            else:
                self.__configuration["collision_levels"]["j2"] = (
                    j2  # Update state config
                )
        if j3 is None:
            j3 = self.__configuration["collision_levels"]["j3"]
        else:
            if not (1 <= j3 <= 100):
                raise ValueError(
                    f"Joint 3 anticollision level must be between 1 and 100: {j3}"
                )
            else:
                self.__configuration["collision_levels"]["j3"] = (
                    j3  # Update state config
                )
        if j4 is None:
            j4 = self.__configuration["collision_levels"]["j4"]
        else:
            if not (1 <= j4 <= 100):
                raise ValueError(
                    f"Joint 4 anticollision level must be between 1 and 100: {j4}"
                )
            else:
                self.__configuration["collision_levels"]["j4"] = (
                    j4  # Update state config
                )
        if j5 is None:
            j5 = self.__configuration["collision_levels"]["j5"]
        else:
            if not (1 <= j5 <= 100):
                raise ValueError(
                    f"Joint 5 anticollision level must be between 1 and 100: {j5}"
                )
            else:
                self.__configuration["collision_levels"]["j5"] = (
                    j5  # Update state config
                )
        if j6 is None:
            j6 = self.__configuration["collision_levels"]["j6"]
        else:
            if not (1 <= j6 <= 100):
                raise ValueError(
                    f"Joint 6 anticollision level must be between 1 and 100: {j6}"
                )
            else:
                self.__configuration["collision_levels"]["j6"] = (
                    j6  # Update state config
                )
        anticollision = [
            j1,
            j2,
            j3,
            j4,
            j5,
            j6,
        ]
        errors = self._robot.SetAnticollision(
            0,  # MODE 0 - LEVEL, 1 - PERCENTAGE
            anticollision,
            0,  # 0 - do not update configuration file, 1 - update configuration file
        )
        if errors == 0:
            info(f"Anticollision level set to {anticollision}", self._message_logger)
        else:
            info(
                f"Anticollision level failed to set to {anticollision}: {errors}",
                self._message_logger,
            )
            raise Exception(f"Error while setting anticollision level: {errors}")

    @handle_errors()
    def robotEnable(self):
        """
        Włącza robota.

        Wysyła żądanie do robota o jego włączenie. -> RobotEnable(state=1)
        Ustawia robota w tryb automatyczny. -> Mode(0) -> tryb 0 -> auto, tryb 1 -> manual
        """
        errors = self._robot.RobotEnable(state=1)
        if errors == 0:
            info("Robot enabled", self._message_logger)
        else:
            info(f"Robot failed to enable: {errors}", self._message_logger)
            raise Exception(
                f"Error while enabling robot",
            )
        # SET AUTO MODE -> Mode(0) -> mode 0 -> auto, mode 1 -> manual
        errors = self._robot.Mode(0)
        if errors == 0:
            info("Robot set to Auto Mode", self._message_logger)
        else:
            info(f"Robot failed to set to Auto Mode: {errors}", self._message_logger)
            raise Exception(
                f"Error while setting robot to Auto Mode",
            )

        if self._gripper:
            self._gripper.on_enable()

    @handle_errors()
    def robotDisable(self):
        """
        Wyłącza robota.

        Wysyła żądanie do robota o jego wyłączenie. -> RobotEnable(state=0)
        """
        # Gripper enable callback - let gripper handle its own initialization
        if self._gripper:
            self._gripper.on_disable()

        errors = self._robot.RobotEnable(state=0)
        if errors == 0:
            info("Robot disabled", self._message_logger)
        else:
            info(f"Robot failed to disable: {errors}", self._message_logger)
            raise Exception(
                f"Error while disabling robot: {errors}",
            )

    def _initialize_gripper_systems(self):
        """Initialize gripper tool configuration and validate connection.

        Sets tool coordinate system and payload based on gripper configuration.
        Validates gripper hardware connection if test sequence is configured.

        Raises:
            GripperError: If gripper connection validation fails.
        """
        if not self._gripper:
            return

        # Get gripper configuration
        robot_config = self._gripper.get_robot_config()

        # Set tool coordinate system of gripper
        self._robot.SetToolCoord(
            robot_config.tool_id,  # id
            robot_config.tool_coordinates,  # t_coord
            robot_config.tool_type,  # type
            robot_config.tool_installation,  # install
            robot_config.tool_id,  # toolID
            0,  # loadNum
        )

        self._tool = robot_config.tool_id

        # Update payload with gripper weight
        self.update_payload(
            weight=0.0,
            tool_weight=robot_config.weight,
            tool_mass_coord=robot_config.mass_coord,
        )

        self._gripper.on_initialize()
        info("Gripper tool configuration set successfully", self._message_logger)

    @handle_errors()
    def _initialize_robot(self, robot_ip_address):
        """Inicjalizuje połączenie z robotem i konfiguruje podstawowe ustawienia.

        Args:
            robot_ip_address (str): Adres IP robota, z którym należy się połączyć.

        Raises:
            Exception: Jeśli wystąpią błędy podczas inicjalizacji robota, włączania,
                ustawiania trybu lub prędkości.
        """
        self._robot = Robot.RPC(robot_ip_address)
        if self._robot.is_conect:
            self._robot.ResetAllError()  # reset all errors of robot if possible
            time.sleep(1.0)
            info(
                "========================================================",
                self._message_logger,
            )
            info("Robot Connection successful", self._message_logger)
            errors, sdk = self._robot.GetSDKVersion()
            if errors == 0:
                info(f"Robot SDK Version: {sdk}", self._message_logger)
            # SET GLOBAL SPEED
            errors = self._robot.SetSpeed(100)  # set global speed to 100%
            if errors == 0:
                info("Global speed set to 100%", self._message_logger)
            else:
                info(
                    f"Global speed failed to set to 100%: {errors}",
                    self._message_logger,
                )
                raise Exception(f"Error while setting global speed to 100%: {errors}")
            # SET DEFAULT ANTICOLLISION LEVEL
            anticollision = [
                self.__configuration["collision_levels"]["j1"],
                self.__configuration["collision_levels"]["j2"],
                self.__configuration["collision_levels"]["j3"],
                self.__configuration["collision_levels"]["j4"],
                self.__configuration["collision_levels"]["j5"],
                self.__configuration["collision_levels"]["j6"],
            ]
            # SET DEFAULT POST - COLLISION STRATEGY
            post_collision_strategy = PostCollisionStrategy.REPORT_ERROR_AND_PAUSE
            errors = self._robot.SetCollisionStrategy(
                strategy=post_collision_strategy.value
            )
            if errors == 0:
                info(
                    f"Post-collision strategy set to {post_collision_strategy.name}",
                    self._message_logger,
                )
            else:
                info(
                    f"Post-collision strategy failed to set to {post_collision_strategy.name}: {errors}",
                    self._message_logger,
                )
                raise Exception(
                    f"Error while setting post-collision strategy: {errors}"
                )
            info(
                "========================================================",
                self._message_logger,
            )

            self.get_status_update()  # Initial status update
            # Gripper enable callback - let gripper handle its own initialization
            if self._gripper:
                self._initialize_gripper_systems()

            self._state = RobotControllerState.IDLE
            # save current position
            self._robot_current_position = self.cartesian_position
        else:
            error("Robot Connection failed", self._message_logger)
            raise Exception(
                f"Error while Connecting to robot: {errors}",
            )

    @handle_errors()
    def save_start_position(self, position, distance):
        """
        Zapisuje pozycję startową i maksymalną dopuszczalną odległość dla sprawdzenia programu.

        Args:
            position (list): Pozycja startowa w układzie kartezjańskim [x, y, z, rx, ry, rz].
            distance (float): Maksymalna dopuszczalna odległość w milimetrach od pozycji startowej.

        Returns:
            bool: True jeśli pozycja startowa została zapisana pomyślnie.

        Raises:
            Exception: Jeśli wystąpi błąd podczas zapisywania pozycji startowej.
        """
        if not self._can_you_run_it:
            self._start_position = position
            self._start_max_distance = distance

            if self._debug:
                debug(
                    f"Start position saved: {position}, Max distance: {distance}",
                    self._message_logger,
                )
        return True

    def __calculate_joint_distance(self, config1, config2):
        """
        Oblicza odległość euklidesową między dwoma konfiguracjami stawów.

        Args:
            config1 (list): First joint configuration.
            config2 (list): Second joint configuration.

        Returns:
            float: The Euclidean distance between the joint configurations.

        Raises:
            ValueError: If the joint configurations have different lengths.
        """
        if len(config1) != len(config2):
            raise ValueError("Joint configurations must have same length")

        # Calculate sum of squared differences for each joint
        squared_diff_sum = sum((a - b) ** 2 for a, b in zip(config1, config2))
        return math.sqrt(squared_diff_sum)

    def __calculate_pose_distance(self, pose1, pose2):
        """
        Oblicz ważoną odległość między dwoma pozami (pozycja + orientacja).

        Args:
            pose1 (list): Pierwsza poza [x, y, z, rx, ry, rz].
            pose2 (list): Druga poza [x, y, z, rx, ry, rz].

        Returns:
            float: Ważona odległość między pozami.
            Odległość pozycyjna jest w milimetrach (mm), a odległość kątowa
            przyczynia się do ostatecznego wyniku na podstawie stopni przelicanych na radiany.

        Raises:
            ValueError: Jeśli pozycje nie mają dokładnie 6 komponentów.
        """
        if len(pose1) != 6 or len(pose2) != 6:
            raise ValueError("Poses must have 6 components [x,y,z,rx,ry,rz]")

        # Position distance (xyz)
        pos_dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(pose1[:3], pose2[:3])))

        # Angular distance (euler angles)
        # Convert to radians for calculation
        ang_dist = math.sqrt(
            sum((math.radians(a - b) ** 2) for a, b in zip(pose1[3:], pose2[3:]))
        )

        # Weight factors (can be adjusted)
        pos_weight = 1.0
        ang_weight = 0.3

        return pos_weight * pos_dist + ang_weight * ang_dist

    def __check_start_distance(self):
        """
        Sprawdza, czy bieżąca pozycja jest w dozwolonej odległości od zapisanej pozycji startowej.

        Returns:
            bool: True jeśli kontrola odległości zakończyła się pomyślnie.

        Raises:
            RuntimeError: Jeśli pozycja startowa nie została zapisana lub odległość przekracza dozwolony limit.
            ValueError: Jeśli bieżąca pozycja ma nieprawidłowy format.
        """
        # Retry logic for Current Position
        max_retries = self._sendRequests_retries
        for attempt in range(1, max_retries + 1):
            try:
                self._robot_current_position = self.cartesian_position
                break
            except http.client.CannotSendRequest as e:
                if attempt == max_retries:
                    error(
                        f"Current position reading (attempt {attempt}/{max_retries}): {e}",
                        self._message_logger,
                    )
                    raise
                else:
                    warning(
                        f"Current position reading (attempt {attempt}/{max_retries}): {e}. Retrying...",
                        self._message_logger,
                    )
                    time.sleep(0.025)
                    continue

        if self._start_position is None:
            raise RuntimeError("Start position not saved")
        if len(self._robot_current_position) != 6:
            raise ValueError("Invalid pose length - expected [x,y,z,rx,ry,rz]")

        distance = self.__calculate_pose_distance(
            self._start_position, self._robot_current_position
        )

        if self._debug:
            debug(f"Distance from start position: {distance:.2f}", self._message_logger)

        if distance > self._start_max_distance:
            raise RuntimeError(
                f"Distance {distance:.2f} exceeds maximum allowed {self._start_max_distance:.2f}"
            )
        return True

    def _overtime_info_callback(self):
        """
        Callback wywoływany przez ControlLoop przy przekroczeniu czasu wykonania (overtime).

        Funkcja zwraca łańcuch znaków zawierający informacje zebrane w momencie wystąpienia overtime,
        przydatne do debugowania i monitorowania stanu Supervisora. Dane te powinny pochodzić z atrybutu
        __supervisor_overtime_info oraz dodatkowego stanu robota uzyskanego przez get_status().

        Returns:
            str: Tekst opisujący stan Supervisora w chwili overtime.
        """
        try:
            status = self.get_status_update()
        except Exception as e:
            status = f"Error getting status: {e}"
        return f"Supervisor Overtime Info: {self.__supervisor_overtime_info},\nRobot Get Status: {status}"

    # region RUN
    @handle_errors()
    def _movement_task(self, movetype, path: Path, on_start=None, on_end=None):
        """
        Wykonuje zadanie ruchu o określonym typie i ścieżce.

        Args:
            movetype (MoveType): Typ ruchu (MOVEJ, MOVEL, MOVEL_WITH_BLEND).
            path (Path): Obiekt Path zawierający waypointy i parametry ruchu.
            on_start (callable, optional): Funkcja wywoływana przed rozpoczęciem ruchu.
            on_end (callable, optional): Funkcja wywoływana po zakończeniu ruchu.

        Raises:
            Exception: Jeśli wystąpią błędy podczas wykonywania ruchu lub pojawi się błąd krytyczny.
        """
        try:
            if on_start:
                on_start()  # Execute start callback

            local_loop = ControlLoop(
                "_movement_task",
                period=1 / self.__supervisor_frequency,
                warning_printer=False,
                overtime_info_callback=self._overtime_info_callback,
            )
            if path.start_position is not None:
                self._can_you_run_it = False  # If we specify starting position in Path, then check before movement
                self.save_start_position(
                    path.start_position.waypoint, self._start_max_distance
                )

                if self._debug:
                    debug(
                        f"Start position: {path.start_position.waypoint}",
                        self._message_logger,
                    )

            self._testing_move_check = True
            if not self._can_you_run_it:
                self._can_you_run_it = self.__check_start_distance()

                if self._debug:
                    debug(
                        f"Can you run it: {self._can_you_run_it}", self._message_logger
                    )

            # Check gripper status before starting movement
            if self._gripper:
                gripper_error = self._gripper.check_errors()
                if gripper_error and not gripper_error.recoverable:
                    self._state = RobotControllerState.WATCHDOG_ERROR
                    raise gripper_error

            self._state = RobotControllerState.IN_MOVE
            robot_connection_check = 1

            self._current_path = path  # Save current path for tracking
            # Create a list of all waypoints from the path for tracking and checkpoint functionality
            # This could be used later to implement progress tracking or on_point callbacks
            self._remaining_waypoints = []
            for waypoint in path.waypoints:
                self._remaining_waypoints.append(waypoint)

            # Save last waypoint for position check after movement
            self._last_waypoint = path.waypoints[-1]

            # Retry logic for Current Position
            max_retries = self._sendRequests_retries
            for attempt in range(1, max_retries + 1):
                try:
                    self._robot_current_position = previous_position = (
                        self.cartesian_position
                    )
                    break
                except http.client.CannotSendRequest as e:
                    if attempt == max_retries:
                        error(
                            f"Current position reading (attempt {attempt}/{max_retries}): {e}",
                            self._message_logger,
                        )
                        raise
                    else:
                        warning(
                            f"Current position reading (attempt {attempt}/{max_retries}): {e}. Retrying...",
                            self._message_logger,
                        )
                        time.sleep(0.025)
                        continue

            move_distance_check = (
                0  # How many times distance was under move_distance, not moving
            )
            distance_values_list = []

            finish_distance = 10  # 10mm

            if self._debug:
                debug(
                    f"Robot move start position: {self._robot_current_position}",
                    self._message_logger,
                )
                debug(
                    f"Robot move end position: {self._last_waypoint.waypoint_name} - {self._last_waypoint.waypoint}",
                    self._message_logger,
                )

            if path.interruption_move:
                # Check if movement should be interrupted
                self._interrupt = True

            if path.interruption_duration is not None:
                # Set the pump hold threshold for interruption
                self.pump_hold_threshold_ms = path.interruption_duration
                if self._debug:
                    debug(
                        f"Interruption duration set to: {path.interruption_duration}",
                        self._message_logger,
                    )

            # Load waypoints and execute initial movement
            self._send_move_commands(
                movetype, self._remaining_waypoints, max_speed=path.max_speed
            )

            # Configure collision handler for this movement task
            self.robot_error_and_collision_handler.max_recovery_attempts = (
                3  # Set maximum recovery attempts # TODO: make it configurable .env
            )

            # Reset the collision handler for this new movement task
            self.robot_error_and_collision_handler.reset()

            collision_detected = False
            awaiting_safe_result = (
                False  # Oczekiwanie na potwierdzenie bezpiecznego ruchu po kolizji
            )
            safe_wait_ticks = 0
            safe_wait_limit_ticks = int(
                self.__supervisor_frequency * self._post_collision_safe_timeout_s
            )

            while not self._stop_event.is_set():
                local_loop.loop_begin()
                self.get_status_update()  # Update status in each loop

                # Robot current position
                with Catchtime() as ct2:
                    try:
                        self._robot_current_position = self.cartesian_position
                    except http.client.CannotSendRequest as e:
                        # Position reading check, possible connection error:
                        error(
                            f"Error getting current position, check number: {robot_connection_check}"
                        )
                        if robot_connection_check > self._sendRequests_retries:
                            raise e
                        else:
                            robot_connection_check += 1
                self.__supervisor_overtime_info["robot_current_position"] = round(
                    ct2.t * 1000, 4
                )  # in ms

                # Check robot movement status
                with Catchtime() as ct3:
                    distance_check = self.__calculate_pose_distance(
                        previous_position, self._robot_current_position
                    )
                    self.max_distance_check = max(
                        self.max_distance_check, distance_check
                    )

                    moved_enough = distance_check >= self._move_distance
                self.__supervisor_overtime_info["move_distance_check"] = round(
                    ct3.t * 1000, 4
                )  # in ms

                # Jeżeli czekamy na bezpieczny ruch, sprawdzaj w każdej iteracji, niezależnie od dystansu
                with Catchtime() as ct4:
                    if awaiting_safe_result:
                        try:
                            if self.robot_error_and_collision_handler.check_safe_movement(
                                self.__calculate_pose_distance,
                                self._robot_current_position,
                            ):
                                awaiting_safe_result = False
                                move_distance_check = 0
                                safe_wait_ticks = 0
                                if self._debug:
                                    info(
                                        "Safe movement confirmed after collision.",
                                        self._message_logger,
                                    )
                            else:
                                safe_wait_ticks += 1
                                if safe_wait_ticks > safe_wait_limit_ticks:
                                    robot_collision_detected = True  # Ponawiamy próbę ruchu po kolizji, ponieważ aktualna nie została poprawnie wykonana.
                                    warning(
                                        f"Post-collision safe movement timeout ({self._post_collision_safe_timeout_s:.2f}s) with no sufficient movement, retrying. Supervisor Status: {self.get_status_update()}",
                                    )
                        except Exception as e:
                            self._state = RobotControllerState.STOPPED
                            raise e

                self.__supervisor_overtime_info["safe_wait_collision_check"] = (
                    safe_wait_ticks
                )

                # Standardowe śledzenie bezruchu tylko gdy nie czekamy na safe result
                with Catchtime() as ct5:
                    if not awaiting_safe_result:
                        if not moved_enough:
                            move_distance_check += 1
                            distance_values_list.append(distance_check)
                            if self._debug:
                                debug(
                                    f"Robot not moving, distance check: {distance_check:.2f}, "
                                    f"avg: {(sum(distance_values_list) / len(distance_values_list)):.4f}, "
                                    f"threshold: {self._move_distance}, "
                                    f"counter: {move_distance_check}/{self._move_distance_counter}, "
                                    f"max: {self.max_distance_check:.5f}",
                                    self._message_logger,
                                )
                    self.__supervisor_overtime_info["idle_movement_check"] = round(
                        ct5.t * 1000, 4
                    )  # in ms

                # Only check for new collisions if we're not already handling one
                with Catchtime() as ct6:
                    robot_collision_detected = (
                        self.robot_error_and_collision_handler.detect_errors()
                    )
                    if not collision_detected:
                        try:
                            if robot_collision_detected:
                                collision_detected = True
                                awaiting_safe_result = True
                                safe_wait_ticks = 0
                                move_distance_check = 0
                                if self._debug:
                                    warning(
                                        "Collision detected. Awaiting safe movement.",
                                        self._message_logger,
                                    )
                        except Exception as e:
                            self._state = RobotControllerState.STOPPED
                            raise e
                self.__supervisor_overtime_info["collision_check"] = round(
                    ct6.t * 1000, 4
                )  # in ms

                # Handle collision recovery if needed
                with Catchtime() as ct7:
                    if collision_detected and self._remaining_waypoints:
                        collision_detected = False
                        awaiting_safe_result = True
                        safe_wait_ticks = 0
                        try:
                            self.robot_error_and_collision_handler.handle_recovery(
                                self.robot,
                                self._robot_current_position,
                                self._send_move_commands,
                                movetype,
                                self._remaining_waypoints,
                                path.max_speed,
                            )
                            if self._debug:
                                info(
                                    "Recovery executed. Awaiting safe movement.",
                                    self._message_logger,
                                )
                        except Exception as e:
                            self._state = RobotControllerState.STOPPED
                            raise e
                self.__supervisor_overtime_info["recovery_check"] = round(
                    ct7.t * 1000, 4
                )  # in ms

                # nie kończ pętli z powodu bezruchu, gdy jesteśmy po kolizji / czekamy na safe result
                if (
                    (not collision_detected)
                    and (not awaiting_safe_result)
                    and (move_distance_check > self._move_distance_counter)
                ):
                    local_loop.loop_end()  # Dodałem dla pewności, że poprawnie kończymy pętle.
                    break

                # Check waypoint reached, do something if needed
                with Catchtime() as ct8:
                    self._remaining_waypoints = self.__check_waypoint_reached(
                        previous_position, self._remaining_waypoints
                    )
                self.__supervisor_overtime_info["waypoint_check"] = round(
                    ct8.t * 1000, 4
                )  # in ms

                # Check Gripper Status during movement
                with Catchtime() as ct1:
                    if self._gripper:
                        gripper_error = self._gripper.check_errors()
                        if gripper_error and not gripper_error.recoverable:
                            self._robot.StopMotion()
                            self._state = RobotControllerState.WATCHDOG_ERROR
                            raise gripper_error
                self.__supervisor_overtime_info["gripper_status1"] = round(
                    ct1.t * 1000, 4
                )  # in ms

                previous_position = self._robot_current_position
                local_loop.loop_end()

            # Check Gripper Status after robot finished movement
            if self._gripper:
                gripper_error = self._gripper.check_errors()
                if gripper_error and not gripper_error.recoverable:
                    self._state = RobotControllerState.WATCHDOG_ERROR
                    raise gripper_error

            # Validate path completion for testing moves
            if path.testing_move:
                if self._gripper:
                    result = self._gripper.validate_path_completion(path)
                    if not result:
                        self._testing_move_check = False
                        if self._debug:
                            warning(
                                f"Testing move validation failed by gripper",
                                self._message_logger,
                            )
                    else:
                        self._testing_move_check = True
                        if self._debug:
                            debug(
                                "Testing move validation successful",
                                self._message_logger,
                            )

            # Notify gripper that path has ended
            if self._gripper:
                self._gripper.on_path_end(path)

            for _ in range(4):  # FIXME: po zakonczeniu testów state_pkg pose
                self._robot_current_position = self.cartesian_position
                debug(
                    f"Robot current position: {self._robot_current_position}",
                    message_logger=self._message_logger,
                )
                time.sleep(0.02)

            if not path.testing_move:
                # Check if we finished movement in the right position
                last_pose_distance_value = self.__calculate_pose_distance(
                    self._last_waypoint.waypoint, self._robot_current_position
                )
                if last_pose_distance_value < finish_distance:
                    self._state = (
                        RobotControllerState.MOVEMENT_FINISHED
                    )  # Set state to MOVEMENT_FINISHED after movement
                else:
                    self._state = RobotControllerState.STOPPED
                    raise Exception(
                        f"Robot movement failed to reach position. Current: {[f'{x:.3f}' for x in self._robot_current_position]}, Last: {[f'{x:.3f}' for x in self._last_waypoint.waypoint]}, Distance: {last_pose_distance_value:.3f}",
                    )

            self._state = (
                RobotControllerState.MOVEMENT_FINISHED
            )  # Set state to MOVEMENT_FINISHED after movement

        except ConnectionRefusedError:
            pass
        finally:
            self._stop_event.clear()
            if on_end:
                on_end()  # Execute end callback

    def __check_waypoint_reached(self, previous_position, list_of_waypoints):
        """
        Sprawdza, czy osiągnięto następny waypoint i obsługuje ustawienia specyficzne dla waypointu.

        Args:
            previous_position (list): Bieżąca pozycja robota [x, y, z, rx, ry, rz].
            list_of_waypoints (list[Waypoint]): Lista pozostałych waypointów do przetworzenia.

        Returns:
            list[Waypoint]: Zaktualizowana lista waypointów z usuniętymi osiągniętymi punktami.
        """
        if not list_of_waypoints:  # Check if there are any waypoints left
            return list_of_waypoints

        distance_to_next_waypoint = self.__calculate_pose_distance(
            pose1=previous_position,
            pose2=list_of_waypoints[0].waypoint,
        )
        if distance_to_next_waypoint < 100:  # 100mm threshold
            self._current_waypoint = list_of_waypoints.pop(
                0
            )  # Remove the waypoint from the list

            # Notify gripper that waypoint was reached
            if self._gripper:
                self._gripper.on_waypoint_reached(self._current_waypoint)

        return list_of_waypoints

    def _send_move_commands(self, movetype, waypoints, max_speed=None):
        """
        Wyślij komendy ruchu do robota dla listy waypointów.

        Args:
            movetype (MoveType): Typ ruchu (MOVEJ, MOVEL, MOVEL_WITH_BLEND).
            waypoints (list[Waypoint]): Lista obiektów Waypoint do wykonania.
            max_speed (int, optional): Maksymalne ograniczenie prędkości w procentach. Domyślnie None.

        Returns:
            bool: True jeśli wszystkie komendy zostały wysłane pomyślnie.

        Raises:
            Exception: Jeśli podczas wysyłania komend wystąpiły błędy.
        """
        for waypoint in waypoints:
            joint_position = [0, 0, 0, 0, 0, 0]
            try:
                inv_error, new_joint_pos = self._robot.GetInverseKin(
                    0, waypoint.waypoint, 2
                )
                if inv_error != 0 or new_joint_pos is None:
                    info(
                        f"GetInverseKin error: {inv_error}, joint_position {new_joint_pos}",
                        self._message_logger,
                    )
                    joint_position = [0, 0, 0, 0, 0, 0]
                else:
                    joint_position = new_joint_pos
            except Exception as e:
                error(f"error GetInverseKin: {e}", self._message_logger)

            blend_radius = (
                waypoint.blend_radius if waypoint.blend_radius is not None else 100
            )
            speed = waypoint.speed if waypoint.speed is not None else 100

            if max_speed is not None:
                speed = min(speed, max_speed)

            info(
                f"Sending move command: {waypoint.waypoint_name} - {waypoint.waypoint}",
                self._message_logger,
            )

            # Retry logic for Move commands
            max_retries = self._sendRequests_retries
            for attempt in range(1, max_retries + 1):
                try:
                    match movetype:
                        case MoveType.MOVEJ:
                            move_error = self._robot.MoveJ(
                                waypoint.waypoint,
                                tool=self._tool,
                                user=0,
                                blendT=blend_radius,
                                vel=speed,
                            )
                        case MoveType.MOVEL:
                            move_error = self._robot.MoveL(
                                waypoint.waypoint,
                                joint_pos=joint_position,
                                tool=self._tool,
                                user=0,
                                blendR=blend_radius,
                                vel=speed,
                                overSpeedStrategy=0,  # strategy off, 1 - standard, 2 - stop on error, 3 - adaptive speed reduc. blocking
                            )
                        case MoveType.MOVEL_WITH_BLEND:
                            move_error = self._robot.MoveL(
                                waypoint.waypoint,
                                joint_pos=joint_position,
                                tool=self._tool,
                                user=0,
                                blendR=blend_radius,
                                blendMode=1,
                                vel=speed,
                                overSpeedStrategy=0,  # strategy off, 1 - standard, 2 - stop on error, 3 - adaptive speed reduc. blocking
                            )
                    # If no exception, check move_error
                    if move_error != 0:
                        error_message = FAIRINO_ERROR_CODES.get(move_error)
                        if error_message is None:
                            error_message = f"Unknown error code: {move_error}"
                        raise Exception(
                            f"Robot move failed with error: {error_message}"
                        )
                    break  # Success, exit retry loop

                except http.client.CannotSendRequest as e:
                    if attempt == max_retries:
                        error(
                            f"Move command exception (attempt {attempt}/{max_retries}): {e}",
                            self._message_logger,
                        )
                        raise
                    else:
                        warning(
                            f"Move command exception (attempt {attempt}/{max_retries}): {e}. Retrying...",
                            self._message_logger,
                        )
                        time.sleep(0.025)
                        continue

        return True

    def _start_move(self, movetype, path: Path):
        """
        Rozpoczyna operację ruchu w osobnym wątku.

        Args:
            movetype (MoveType): Typ wykonywanego ruchu.
            path (Path): Obiekt Path zawierający waypointy i parametry ruchu.

        Raises:
            Exception: Jeśli supervisor nie jest w stanie IDLE lub występują krytyczne błędy uniemożliwiające rozpoczęcie ruchu.
        """

        if self._state != RobotControllerState.IDLE:
            raise Exception(
                f"Cannot start move, supervisor is in state: {self._state}",
            )

        # Notify gripper that path is starting
        if self._gripper:
            self._gripper.on_path_start(path)

        # Start movement in a separate thread with callbacks
        threading.Thread(
            target=self._movement_task,
            args=(movetype, path),
            kwargs={
                "on_start": lambda: info(
                    f"{movetype.name} started", self._message_logger
                ),
                "on_end": lambda: info(
                    f"{movetype.name} finished", self._message_logger
                ),
            },
        ).start()

    @handle_errors()
    def update_payload(self, weight, tool_weight=0, tool_mass_coord=[0, 0, 0]):
        """
        Aktualizuje ładunek (payload) robota.

        Args:
            weight (float): Nowa wartość ładunku robota w kilogramach.
            tool_weight (float, optional): Waga narzędzia (chwytnika) w kilogramach. Używać przy zmianie narzędzia lub
            przy pierwszej inicjalizacji. Domyślnie 0.
            tool_mass_coord (list[float], optional): Współrzędne środka masy narzędzia [x, y, z] (mm). Domyślnie [0, 0, 0].

        Note:
            Domyślny payload to 0 kg. Jeśli chwytak jest włączony, początkowa wartość ładunku może zostać pobrana z
            chwytaka. Po pierwszym ustawieniu kolejna aktualizacja payload będzie uwzględniać wagę narzędzia jako offset.

        Returns:
            None

        Raises:
            Exception: Gdy wartości nie mogą zostać skonwertowane na float lub gdy ustawienie wagi/środka masy
            na robocie zakończy się niepowodzeniem.
        """
        try:
            weight = float(weight)
            tool_weight = float(tool_weight)
        except Exception:
            raise Exception(
                f"Payload is not a float",
            )

        if self._gripper and self._tool_weight == 0:
            if tool_weight == 0:
                warning(
                    f"Tool weight is 0.0. No error will be raised, but make sure this is intended behavior.",
                    self._message_logger,
                )
            self._tool_weight = tool_weight

        total_weight = weight + float(self._tool_weight)
        error = self._robot.SetLoadWeight(1, total_weight)
        if error != 0:
            raise Exception(
                f"Error while setting payload: {error}",
            )
        error = self._robot.SetLoadCoord(
            *tool_mass_coord
        )  #!!! Load center of mass should be set to match the actual (incorrect load center of mass settings can lead to loss of robot control in drag mode)
        if error != 0:
            raise Exception(
                f"Error while setting payload: {error}",
            )
        if self._debug:
            debug(
                f"Payload updated to {weight} plus tool weight: {self._tool_weight}",
                self._message_logger,
            )

    @handle_errors()
    def MoveJ(self, path: Path):
        """
        Wykonuje ruch stawowy (MoveJ).

        Args:
            path (Path): Obiekt Path zawierający waypointy i parametry ruchu.

        Note:
            rconfig (list): Konfiguracja stawów (w radianach).
            speed (int): Prędkość robota w procentach.
            blendT (int): Czas wygładzania (smoothing time) w milisekundach — powoduje, że ruch jest nieblokujący.
            interrupt (bool): Flaga przerywania ruchu. Domyślnie False.

        Returns:
            None

        Raises:
            Exception: Gdy wystąpi błąd podczas przygotowania lub uruchamiania ruchu.
        """
        self._start_move(MoveType.MOVEJ, path=path)

    @handle_errors()
    def MoveL(self, path: Path):
        """
        Wykonuje ruch liniowy (MoveL).

        Args:
            path (Path): Obiekt Path zawierający listę waypointów oraz parametry ruchu.

        Note:
            pose (list): docelowa pozycja w układzie kartezjańskim [mm][°].
            speed (int): docelowa prędkość robota w procentach.
            blendR (int): promień wygładzania (blend radius) w mm — powoduje, że ruch jest nieblokujący.
            interrupt (bool): Flaga przerywania ruchu. Domyślnie False.
        """
        self._start_move(MoveType.MOVEL, path=path)

    @handle_errors()
    def MoveL_with_blend(self, path: Path):
        """Wykonuje ruch liniowy z mieszaniem (blend).

        Args:
            path (Path): Obiekt Path zawierający listę waypointów oraz parametry ruchu.

        Note:
            path: Path

            pose (list): docelowa pozycja w układzie kartezjańskim [mm][°].
            speed (int): docelowa prędkość robota w procentach.
            blendR (int): promień wygładzania (blend radius) w mm — powoduje, że ruch jest nieblokujący.
            interrupt (bool): Flaga przerywania ruchu. Domyślnie False.
        """
        self._start_move(MoveType.MOVEL_WITH_BLEND, path=path)

    @handle_errors()
    def wait_for_gripper(self, pump_on=True):
        """
        Oczekuje na informacje od chwytaka i ustawia stan na WAITING_FOR_GRIPPER_INFO.

        Funkcja uruchamia proces oczekiwania na potwierdzenie stanu pompy chwytaka (włączona/wyłączona).
        Zmienia stan supervisora na WAITING_FOR_GRIPPER_INFO i resetuje znacznik _gripper_check.

        Args:
            pump_on (bool): Docelowy stan pompy (True — włączona, False — wyłączona).

        Returns:
            None

        Raises:
            Exception: Jeśli chwytak nie jest włączony lub wystąpi błąd podczas oczekiwania.
        """
        if not self._gripper:
            raise Exception(f"Gripper not configured")

        self._state = RobotControllerState.WAITING_FOR_GRIPPER_INFO
        # Note: This method needs to be refactored to use modular gripper architecture
        # For now, raising not implemented error
        raise NotImplementedError("Gripper check now handled by gripper module")

    @handle_errors()
    def wait(self, wait_time):
        """
        Wykonuje polecenie oczekiwania.

        Args:
            wait_time (float): Czas oczekiwania w sekundach.
        """
        self._state = RobotControllerState.WAITING

        def wait_task():
            # Execute the start callback
            if self._debug:
                debug(f"Waiting for {wait_time} seconds", self._message_logger)
            # Perform the actual wait
            # self._robot.WaitMs(wait_time * 1000)
            time.sleep(wait_time)
            # Execute the end callback
            self._state = RobotControllerState.IDLE

        # Start the thread with the wait task
        threading.Thread(target=wait_task).start()

    def _send_thru_pipe(self):
        try:
            raise NotImplementedError(
                f"Not implemented: {self._send_thru_pipe.__name__}"
            )
        except NotImplementedError as e:
            error(f"error _send_thru_pipe: {e}", self._message_logger)
            raise

    def exit(self):
        """
        Zamyka Supervisora i zwalnia zasoby.

        Zatrzymuje ruch robota, ustawia zdarzenie zatrzymania, zatrzymuje menedżera błędów
        oraz czyści kontrolery chwytaka i kamery. Na końcu zamyka połączenie RPC z robotem.

        Args:
            None

        Returns:
            None

        Raises:
            None
        """

        if self._robot:
            self._robot.StopMotion()
            time.sleep(0.1)
            self._robot_current_position = self.cartesian_position
            time.sleep(0.1)  # FIXME

        self._stop_event.set()

        if self._robot:
            self._robot.CloseRPC()
            self._robot = None

        print("Supervisor closed")
