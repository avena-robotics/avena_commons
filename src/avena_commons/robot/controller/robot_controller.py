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

from avena_commons.event_listener.types import Path, Waypoint
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
from .utils import PressureCalculator

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
    ) -> None:
        """Inicjalizuje `Supervisor` zarządzający robotem i peryferiami.

        Args:
            suffix (int): Sufiks instancji (wpływa m.in. na porty klientów).
            message_logger: Logger do zapisu komunikatów.
            configuration (dict): Konfiguracja połączeń i parametrów pracy (wymagana).
            debug (bool): Czy włączyć tryb debug.

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
        self.__gripper_enabled = self.__configuration["gripper"]["enabled"]
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
        self.__pressure_calculator = PressureCalculator()
        
        self._initialize_robot(self.__configuration["network"]["ip_address"])

        # Initialize collision handler
        self.robot_error_and_collision_handler = CollisionAndErrorHandler(
            self._robot, message_logger=self._message_logger, debug=self._debug
        )
        # self.is_rotation = False
        self._start_position = None
        # self._camera_data = None
        self._gripper_check = False
        self._interrupt = False
        self._testing_move_check = True
        self._gripper_watchdog_override = False
        self._last_waypoint = None

        self._robot_current_position = None
        self._current_waypoint = None
        self._current_path = None
        self._remaining_waypoints = []

        # Add state transition tracking for gripper
        self._gripper_pump_on = False
        self._pump_holding = False  # supervisor
        self._pump_holding_timer = None
        self._gripper_pressure = 0.0  # Current gripper pressure in kPa
        self._gripper_pump_holding = self.__configuration["gripper"][
            "pump_holding"
        ]  # gripper
        self._pump_pressure_threshold = self.__configuration["gripper"][
            "pressure_threshold"
        ]
        self._pump_hold_threshold_ms = self.__configuration["gripper"][
            "hold_threshold_ms"
        ]  # Wait 250ms to confirm state change
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

    @handle_errors()
    def get_status_update(self):
        """
        Pobiera aktualny status supervisora.

        Returns:
            dict: Status supervisora.
        """
        main_code = self.robot.robot_state_pkg.main_code
        sub_code = self.robot.robot_state_pkg.sub_code
        joint_current_torque = list(self.robot.robot_state_pkg.jt_cur_tor)
        self._robot_current_position = self.cartesian_position

        return {
            "state": self.state,
            "current_error": self._error_message,
            "robot_state": {
                "error_name": FAIRINO_ERROR_CODES[main_code]["name"],
                "error_description": FAIRINO_ERROR_CODES[main_code]["sub_codes"][
                    sub_code
                ],
                "enable_state": self.robot.robot_state_pkg.rbtEnableState,
                "mode_state": self.robot.robot_state_pkg.robot_mode,
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
                "watchdog_override": self._gripper_watchdog_override,
            },
        }

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
    def gripper_check(self):
        """
        Pobiera status sprawdzania chwytaka.

        Returns:
            bool: Status sprawdzania chwytaka.
        """
        return self._gripper_check

    @gripper_check.setter
    @Connector._read_only_property("gripper_check")
    def gripper_check(self, *args):
        pass

    @property
    def pump_hold_threshold_ms(self):
        """
        Pobiera próg trzymania pompy w milisekundach.

        Returns:
            int: Próg trzymania pompy w milisekundach.
        """
        return self._pump_hold_threshold_ms

    @pump_hold_threshold_ms.setter
    def pump_hold_threshold_ms(self, value: int):
        """
        Ustawia próg trzymania pompy w milisekundach.

        Args:
            value (int): Nowy próg trzymania pompy w milisekundach.
        """
        if not isinstance(value, (int, float)):
            raise ValueError(
                f"Pump hold threshold must be an integer or float: {value} type: {type(value)}"
            )
        if value < 0:
            raise ValueError("Pump hold threshold must be non-negative")
        self._pump_hold_threshold_ms = value

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

    def gripper_pressure(self) -> float:
        """
        Pobiera aktualne ciśnienie w chwytaku.

        Returns:
            float: Aktualne ciśnienie w chwytaku w kPa.
        """
        error, current_pressure_voltage = self._robot_tool_io(
            io_type="AI", operation="get", id=self.__configuration["gripper"]["pump_AI"]
        )
        self._gripper_pressure = self.__pressure_calculator.calculate_pressure(
            voltage_in=current_pressure_voltage
        )
        return self._gripper_pressure

    def decode_tool_do_status(self, status: int) -> dict[str, bool]:
        """Dekoduje status DO narzędzia z wartości bitowej.

        Args:
            status: Status DO jako liczba całkowita (wartość bitowa).

        Returns:
            dict[str, bool]: Słownik ze statusem każdego DO (DO0, DO1, itd.).

        Example:
            >>> decode_tool_do_status(9)
            {'DO0': True, 'DO1': False, 'DO2': False, 'DO3': True}
        """
        result = {}
        for i in range(8):  # Zakładając maksymalnie 8 DO
            bit_value = (status >> i) & 1
            result[f"DO{i}"] = bool(bit_value)
        return result

    def is_do_active(self, status: int, do_number: int) -> bool:
        """Sprawdza czy określony DO jest aktywny.

        Args:
            status: Status DO jako liczba całkowita.
            do_number: Numer DO do sprawdzenia (0-7).

        Returns:
            bool: True jeśli DO jest aktywny, False w przeciwnym razie.
        """
        return bool((status >> do_number) & 1)

    def _robot_tool_io(self, io_type: str, operation: str, **kwargs):
        """
        Uniwersalna metoda obsługi Digital Output (DO), Analog Output (AO) i Digital Input (DI) narzędzia robota.

        Args:
            io_type (str): Typ IO - 'DO', 'AO' lub 'DI'.
            operation (str): Operacja - 'get' lub 'set' (tylko dla DO i AO).
            **kwargs: Parametry specyficzne dla operacji (id, status, value, smooth, block).

        Returns:
            tuple: (error, value) dla operacji 'get', None dla 'set'.

        Raises:
            ValueError: Przy nieprawidłowych parametrach.
            Exception: Przy błędach komunikacji z robotem.
        """
        if io_type == "DO":
            if operation == "get":
                error, status = self._robot.GetToolDO()
                if error == 0:
                    if not kwargs["id"] in [0, 1]:
                        raise ValueError(
                            f"Invalid DO id: {kwargs['id']}. Must be 0 or 1."
                        )
                    if self.is_do_active(status, kwargs["id"]):
                        # debug(f"Get Tool DO{kwargs['id']} status: {True}", self._message_logger)
                        return error, True
                    # debug(f"Get Tool DO{kwargs['id']} status: {False}", self._message_logger)
                    return error, False
                else:
                    raise Exception("Error while getting Tool DO status")

            elif operation == "set":
                id, status = kwargs["id"], kwargs["status"]
                smooth, block = kwargs.get("smooth", 0), kwargs.get("block", 1)

                if (
                    not (0 <= id <= 1)
                    or status not in [0, 1]
                    or smooth not in [0, 1]
                    or block not in [0, 1]
                ):
                    raise ValueError(
                        f"Invalid DO parameters: id={id}, status={status}, smooth={smooth}, block={block}"
                    )

                error = self._robot.SetToolDO(id, status, smooth=smooth, block=block)
                if error != 0:
                    raise Exception(f"Error setting Tool DO{id} to {status}")
                # debug(f"Set Tool DO{id} to {status}", self._message_logger)

        elif io_type == "AO":
            if operation == "get":
                error, value = self._robot.GetToolAO(0)
                if error == 0:
                    # debug(f"Get Tool AO value: {value}", self._message_logger)
                    return error, value
                else:
                    raise Exception("Error while getting Tool AO value")

            elif operation == "set":
                id, value = kwargs.get("id", 0), kwargs["value"]
                block = kwargs.get("block", 1)

                if id != 0 or not (0 <= value <= 100) or block not in [0, 1]:
                    raise ValueError(
                        f"Invalid AO parameters: id={id}, value={value}, block={block}"
                    )

                error = self._robot.SetToolAO(id, value, block=block)
                if error != 0:
                    raise Exception(f"Error setting Tool AO{id} to {value}")
                # debug(f"Set Tool AO{id} to {round((value / 10), 1)}V", self._message_logger)

        elif io_type == "DI":
            if operation == "get":
                id = kwargs["id"]
                block = kwargs.get("block", 0)
                if not (0 <= id <= 1) or block not in [0, 1]:
                    raise ValueError(f"Invalid AI parameters: id={id}, block={block}")

                error, status = self._robot.GetToolDI(id, block=block)
                if error == 0:
                    if self.is_do_active(status, kwargs["id"]):
                        # debug(f"Get Tool DI{kwargs['id']} status: {True}", self._message_logger)
                        return error, True
                    # debug(f"Get Tool DI{kwargs['id']} status: {False}", self._message_logger)
                    return error, False
                else:
                    raise Exception(f"Error while getting Tool DI status")

            elif operation == "set":
                raise ValueError("DI (Digital Input) does not support 'set' operation")

        elif io_type == "AI":
            if operation == "get":
                id = kwargs["id"]
                block = kwargs.get("block", 0)

                if not (0 <= id <= 1) or block not in [0, 1]:
                    raise ValueError(f"Invalid AI parameters: id={id}, block={block}")

                error, ai_value = self._robot.GetToolAI(id, block=block)
                if error == 0:
                    # debug(f"Get Tool AI{id} value: {ai_value}", self._message_logger)
                    return error, ai_value
                else:
                    raise Exception(f"Error while getting Tool AI{id} value")

            elif operation == "set":
                raise ValueError("AI (Analog Input) does not support 'set' operation")

        else:
            raise ValueError(
                f"Unsupported IO type: {io_type}. Must be 'DO', 'AO', or 'AI'"
            )

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
        self.gripperEnableLightControl(True)  # Enable gripper light Control

    @handle_errors()
    def robotDisable(self):
        """
        Wyłącza robota.

        Wysyła żądanie do robota o jego wyłączenie. -> RobotEnable(state=0)
        """
        self.gripperLightOff()  # Turn off gripper light if on
        self.gripperEnableLightControl(False)  # Disable gripper light control

        errors = self._robot.RobotEnable(state=0)
        if errors == 0:
            info("Robot disabled", self._message_logger)
        else:
            info(f"Robot failed to disable: {errors}", self._message_logger)
            raise Exception(
                f"Error while disabling robot: {errors}",
            )

    def gripperCheckConnection(self):
        """
        Sprawdza połączenie z chwytakiem.
        Wysyła sygnał do chwytaka i oczekuje na odpowiedź, aby potwierdzić, że chwytak jest poprawnie podłączony.
        """
        # Sprawdzenie, czy gripper działa jeśli uruchomiony, wyślij DO0 true, sprawdź pozytyw w czasie 200ms, DO0 na false
        if self.__gripper_enabled:
            self.gripperPumpOn()  # Set DO0 to True

            time.sleep(1.0)  # wait 1000ms
            error, tool_do_state = self._robot_tool_io(
                io_type="DI",
                operation="get",
                id=self.__configuration["gripper"]["pump_DI"],
            )  # Read DI0

            self.gripperPumpOff()  # Set DO0 to False

            if tool_do_state:  # If DO0 is True
                info("Gripper connection successful", self._message_logger)
            else:
                warning("Gripper connection failed", self._message_logger)
                raise RuntimeError("Gripper connection failed")

    def gripperPumpOn(self):
        """
        Włącza pompę chwytaka.

        Ustawia chwytak w tryb aktywny.
        """
        if self.__gripper_enabled:
            self._robot_tool_io(
                io_type="DO",
                operation="set",
                id=self.__configuration["gripper"]["pump_DO"],
                status=1,
            )  # Set DO0 to True
            self._gripper_pump_on = True

    def gripperPumpOff(self):
        """
        Wyłącza pompę chwytaka.

        Ustawia chwytak w tryb nieaktywny.
        """
        if self.__gripper_enabled:
            self.__pressure_calculator.reset()  # Reset pressure buffer to avoid false readings on next use
            self._robot_tool_io(
                io_type="DO",
                operation="set",
                id=self.__configuration["gripper"]["pump_DO"],
                status=0,
            )  # Set DO0 to False
            self._gripper_pump_on = False

    def gripperEnableLightControl(self, enable: bool = True):
        """
        Włącza lub wyłącza kontrolę światła chwytaka.

        Args:
            enable (bool): True aby włączyć kontrolę światła, False aby wyłączyć.
        """
        if self.__gripper_enabled:
            if enable:
                self._robot_tool_io(
                    io_type="DO",
                    operation="set",
                    id=self.__configuration["gripper"]["light_DO"],
                    status=1,
                )  # Enable gripper light Control
            else:
                self._robot_tool_io(
                    io_type="DO",
                    operation="set",
                    id=self.__configuration["gripper"]["light_DO"],
                    status=0,
                )  # Disable gripper light Control

    def gripperLightOn(self, value: int = 100):
        """
        Włącza światło chwytaka.

        Ustawia wartość jasności światła chwytaka.
        """
        if self.__gripper_enabled:
            if not (0 <= value <= 100):
                raise ValueError(
                    f"Gripper, wartość dla światła między 0 a 100: {value}"
                )
            # Sprawdzenie, jakie wartości min-max ma ustawione gripper, wysłanie przekalkulowanej wartości procentowej zaorkąglonej do 1.
            if value == 0:
                value = self.__configuration["gripper"][
                    "light_min"
                ]  # Wartości 0.0 to max , a 43 to min. 4,3V to brak światła.
            elif value == 100:
                value = self.__configuration["gripper"]["light_max"]
            else:
                value = int(
                    round(
                        self.__configuration["gripper"]["light_min"]
                        - (value / 100)
                        * (
                            self.__configuration["gripper"]["light_min"]
                            - self.__configuration["gripper"]["light_max"]
                        ),
                        0,
                    )
                )
            self._robot_tool_io(
                io_type="AO",
                operation="set",
                id=self.__configuration["gripper"]["light_AO"],
                value=value,
            )  # Set AO0 to value

    def gripperLightOff(self):
        """
        Wyłącza światło chwytaka.

        Ustawia wartość jasności światła chwytaka na 0.
        """
        if self.__gripper_enabled:
            self._robot_tool_io(
                io_type="AO",
                operation="set",
                id=self.__configuration["gripper"]["light_AO"],
                value=self.__configuration["gripper"]["light_min"],
            )  # Set AO0 to min value (light off)

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

            # TODO: Ustawianie konkretnego chwytaka podłączonego do robota, wynikające z konfiguracji
            # id: coordinate system number, range [1~15];
            # t_coord: Position of the tool center point relative to the center of the end flange in [mm][°];
            # type: 0 - tool coordinate system, 1 - sensor coordinate system;
            # install: installation position, 0 - robot end, 1 - robot exterior
            # toolID: tool ID
            # loadNum: load number

            if self.__gripper_enabled:
                self.gripperCheckConnection()  # Check gripper connection
                self.gripperLightOff()  # Turn off gripper light if on

                # Set tool coordinate system of gripper
                self._robot.SetToolCoord(
                    self.__configuration["gripper"]["id"],
                    self.__configuration["gripper"]["tool_coordinates"],
                    self.__configuration["gripper"]["tool_type"],
                    self.__configuration["gripper"]["tool_installation"],
                    self.__configuration["gripper"]["tool_id"],  # toolID
                    0,  # loadNum
                )
                self._tool = self.__configuration["gripper"][
                    "tool_id"
                ]  # Set the tool id of gripper
                self.update_payload(
                    weight=0.0,
                    tool_weight=self.__configuration["gripper"]["weight"],
                    tool_mass_coord=self.__configuration["gripper"]["mass_coord"],
                )  # Set the tool weight of gripper
                # Check gripper connection

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

            if self.__gripper_enabled:
                self.__check_gripper_status()

            self._state = RobotControllerState.IN_MOVE
            robot_connection_check = 1

            self._current_path = path  # Save current path for tracking
            # Create a list of all waypoints from the path for tracking and checkpoint functionality
            # This could be used later to implement progress tracking or on_point callbacks
            self._remaining_waypoints = []
            for waypoint in path.waypoints:
                self._remaining_waypoints.append(waypoint)

            if path.testing_move:
                self._gripper_watchdog_override = (
                    True  # OVERRIDE GRIPPER WATCHDOG ERROR FOR TESTING MOVES ONLY
                )
            else:
                self._gripper_watchdog_override = False

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

                # Check Gripper Status
                with Catchtime() as ct1:
                    if self.__gripper_enabled:
                        self.__check_gripper_status()
                self.__supervisor_overtime_info["gripper_status1"] = round(
                    ct1.t * 1000, 4
                )  # in ms

                previous_position = self._robot_current_position
                local_loop.loop_end()

            # # Check Gripper Status after robot finished movement
            if self.__gripper_enabled:
                self.__check_gripper_status()

            # Check if we are in testing move and pump is holding
            if path.testing_move and not self._pump_holding:
                self._testing_move_check = False
                if self._debug:
                    warning(
                        f"Testing move finished with: {self._testing_move_check}",
                        self._message_logger,
                    )
            elif path.testing_move and self._pump_holding:
                if self._debug:
                    info(
                        f"Testing move finished with: {self._testing_move_check}",
                        self._message_logger,
                    )

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

    def __check_gripper_status(self):
        """
        Sprawdza status chwytaka i obsługuje trzymanie pompy oraz warunki watchdog.

        Funkcja monitoruje stan pompy chwytaka i realizuje:
        1. Wykrywanie zmiany stanu trzymania pompy z potwierdzeniem czasowym.
        2. Obsługę scenariuszy z nadpisaniem watchdog (watchdog override).
        3. Zatrzymanie ruchu robota, jeśli wymagane przez warunki pompy.
        4. Aktualizację ostatniego waypointu przy przerwaniach i potwierdzeniu chwytu.

        Raises:
            Exception: Gdy watchdog pompy wykryje utratę podciśnienia podczas trzymania
            i nadpisanie watchdog nie jest aktywne.
        """
        if not self.__gripper_enabled:
            return

        if self._gripper_pump_on:
            # Sprawdz stan podciśnienie
            self.gripper_pressure()

            if self._gripper_pressure < 0:
                debug(
                    f"Podciśnienie chwytaka: {self._gripper_pressure:.2f} kPa",
                    self._message_logger,
                )
            # Sprawdz czy podciśnienie jest poniżej progu
            if self._gripper_pressure < self._pump_pressure_threshold:
                pressure_ok = True
            else:
                pressure_ok = False
            # Ustaw trzymanie jeśli podciśnienie jest poprawne
            if not self._gripper_pump_holding and pressure_ok:
                self._gripper_pump_holding = True
            # Resetuj trzymanie jeśli podciśnienie jest niepoprawne
            elif self._gripper_pump_holding and not pressure_ok:
                self._gripper_pump_holding = False
        else:
            self._gripper_pump_holding = False

        # Case 1: Pump was turned off - reset holding state
        if not self._gripper_pump_on and self._pump_holding:
            self._pump_holding = False
            self._pump_holding_timer = None
            if self._debug:
                debug("Pump turned off, reset holding state", self._message_logger)

        # Case 2: Pump holding with watchdog override active
        elif (
            self._gripper_watchdog_override
            and self._pump_holding
            and not self._gripper_pump_holding
        ):
            self._pump_holding = False
            self._pump_holding_timer = None

            if not self._current_path.testing_move:
                # self._last_waypoint.waypoint = self.cartesian_position #FIXME: CHECK new status callback for current position
                self._last_waypoint.waypoint = list(
                    self.robot.robot_state_pkg.tl_cur_pos
                )
                self._robot.StopMotion()
                if self._debug:
                    debug(
                        "Pump lost vacuum but watchdog override active not in testing move, stopping robot and updating last waypoint",
                        self._message_logger,
                    )
            if self._debug:
                debug(
                    "Gripper watchdog override active, ignoring non-holding state",
                    self._message_logger,
                )

        # Case 3: Pump should be holding but isn't (watchdog error)
        elif (
            not self._gripper_watchdog_override
            and self._pump_holding
            and not self._gripper_pump_holding
        ):
            self._pump_holding_timer = None
            self._pump_holding = False
            self._robot.StopMotion()  # Stop the robot if pump lost vacuum while holding
            self._state = RobotControllerState.WATCHDOG_ERROR
            raise Exception(
                f"Pump lost vacuum while holding! Current pressure: {self._gripper_pressure}",
            )

        # Case 4: State transition handling - pump just started or stopped holding
        elif self._gripper_pump_holding and not self._pump_holding:
            current_time = time.perf_counter() * 1000  # Current time in milliseconds

            # Begin timer if this is the first detection of a potential state change
            if self._pump_holding_timer is None:
                self._robot.StopMotion()  # Stop the robot when pump starts holding
                if self._debug:
                    debug(
                        f"Pump is reading pressure change, stopping the robot",
                        self._message_logger,
                    )
                self._pump_holding_timer = current_time
                if self._debug:
                    debug(
                        f"Potential pump state change detected: holding={self._gripper_pump_holding}, pressure={self._gripper_pressure}",
                        self._message_logger,
                    )
            # Check if state has been stable for threshold period
            elif (
                current_time - self._pump_holding_timer
            ) >= self._pump_hold_threshold_ms:
                if self._gripper_pump_holding:
                    # Confirmed pump is now holding
                    self._pump_holding = True

                    # Save current position as last waypoint
                    try:
                        self._last_waypoint.waypoint = self.cartesian_position
                    except AttributeError:
                        self._last_waypoint = Waypoint(
                            waypoint=self.cartesian_position
                        )

                    if self._debug:
                        debug(
                            f"Pump state change confirmed - now holding with pressure: {self._gripper_pressure}",
                            self._message_logger,
                        )
                else:
                    # Confirmed pump is no longer holding
                    self._pump_holding = False
                    if self._debug:
                        debug(
                            f"Pump state change confirmed - no longer holding, pressure: {self._gripper_pressure}",
                            self._message_logger,
                        )

                self._pump_holding_timer = None
        else:
            # Reset timer if state matches again before threshold
            self._pump_holding_timer = None

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

            if self._current_waypoint.watchdog_override:
                self._gripper_watchdog_override = True  # OVERRIDE GRIPPER WATCHDOG ERROR STARTING FROM SPECIFIC WAYPOINT

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

        if self.__gripper_enabled and self._tool_weight == 0:
            if tool_weight == 0:
                raise Exception(
                    f"Tool weight must be provided when changing the payload for the first time",
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
        if not self.__gripper_enabled:
            raise Exception(f"Gripper not enabled")

        self._state = RobotControllerState.WAITING_FOR_GRIPPER_INFO
        self._gripper_check = False
        # Start the thread with the gripper task
        threading.Thread(
            target=self.__check_gripper_status_task, args=(pump_on,)
        ).start()

    def __check_gripper_status_task(self, pump_on):
        """
        Monitoruje stan chwytaka do momentu osiągnięcia żądanego stanu pompy lub upłynięcia limitu czasu.

        Args:
            pump_on (bool): Docelowy stan pompy — True oznacza włączenie, False wyłączenie.

        Returns:
            None: Metoda nie zwraca wartości; ustawia flagę self._gripper_check oraz zmienia stan supervisora.

        Raises:
            Exception: W przypadku błędów komunikacji lub problemów podczas odczytu statusu chwytaka.
        """
        loop = ControlLoop(
            "Gripper Status",
            period=1 / self.__supervisor_frequency,
            warning_printer=False,
        )
        timeout = time.time() + 1.0  # Set timeout to 1.0 second
        while True:
            loop.loop_begin()
            if time.time() > timeout:
                break

            error, status = self._robot_tool_io(
                io_type="DO",
                operation="get",
                id=self.__configuration["gripper"]["pump_DO"],
            )  # Sprawdzanie stanu chwycenia przez gripper, supervisor check
            if status and pump_on or not status and not pump_on:
                self._gripper_check = True
                break

            loop.loop_end()

        self._state = RobotControllerState.GRIPPER_FINISHED
        return

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
