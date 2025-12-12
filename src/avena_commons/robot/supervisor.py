"""Warstwa zdarzeniowa nad `Supervisor` dla sterowania robotem w modelu event-driven.

Zapewnia analizę zdarzeń domenowych i delegację do operacji ruchu, chwytaka i kamery.
Dokumentacja w stylu Google, w języku polskim.
"""

import os

from dotenv import load_dotenv

from avena_commons.event_listener import (
    Event,
    EventListener,
    EventListenerState,
    Result,
)
from avena_commons.event_listener.types import (
    SupervisorGripperAction,
    SupervisorMoveAction,
    Waypoint,
)
from avena_commons.util.logger import debug, error, info, warning

from .controller.enum import RobotControllerState
from .controller.robot_controller import RobotController
from .controller.types import SupervisorModel
from .grippers.base import IOMapping

load_dotenv(override=True)


class Supervisor(EventListener):
    """
    Warstwa zdarzeniowa dla klasy Supervisor obsługująca operacje sterowania robotem.

    Ta klasa służy jako interfejs między systemem zdarzeń a fizycznym kontrolerem robota.
    Przetwarza zdarzenia związane z ruchem i operacjami chwytaka.

    Attributes:
        check_local_data_frequency (int): Częstotliwość sprawdzania stanu supervisora
        _debug (bool): Włączenie/wyłączenie logowania debug
        _supervisor (Supervisor): Instancja supervisora robota
    """

    def __init__(
        self,
        name: str,
        suffix=1,
        message_logger=None,
        loop_synchronization=False,
        debug=False,
        load_state: bool = False,
    ):
        """Inicjalizuje `Supervisor`.

        Args:
            name (str): Nazwa instancji listenera.
            suffix (int): Sufiks identyfikujący instancję robota.
            message_logger: Logger do śledzenia komunikatów.
            debug (bool): Czy włączyć tryb debug.
            load_state (bool): Czy wczytać stan z trwałego magazynu.

        Raises:
            RuntimeError: Gdy pozycja startowa nie jest poprawnie skonfigurowana.
        """
        # Store basic configuration for later initialization
        self._message_logger = message_logger
        self._suffix = suffix
        self._gripper = None  # Will be created in on_initializing based on config
        self._state_model = SupervisorModel(id=self._suffix)
        self._load_state: bool = load_state
        self.check_local_data_frequency: int = 10

        # Default configuration - will be used in on_initialize()
        self._default_configuration = {
            "network": {"ip_address": "192.168.57.2", "port": 8003},
            "frequencies": {"supervisor": 50},
            # General Settings
            "general": {
                "send_requests_retries": 3,
                "start_position_distance": 200,
                "post_collision_safe_timeout_s": 2.0,
            },
            # Robot Collision Levels
            "collision_levels": {
                "j1": 10,
                "j2": 8,
                "j3": 10,
                "j4": 5,
                "j5": 3,
                "j6": 100,
            },
            "start_position": {
                "pos1": 177.5,
                "pos2": -780.0,
                "pos3": 510.0,
                "pos4": 180.0,
                "pos5": 0.0,
                "pos6": 180.0,
            },
            # Gripper Configuration, default NONE
        }

        # Initialize supervisor to None - will be created in on_initialized()
        self._robot_controller = None
        self._error_read = False
        self._error = None
        self._temp_local_counter = 0

        # Call parent constructor
        super().__init__(
            name=name,
            port=os.getenv(f"SUPERVISOR_{suffix}_LISTENER_PORT"),
            load_state=load_state,
            loop_synchronization=loop_synchronization,
            message_logger=message_logger,
        )

    def _create_gripper_instance(
        self, gripper_type: str, gripper_config_dict: dict, robot
    ):
        """Create gripper instance dynamically from configuration.

        Attempts to import gripper class from local lib.robot.grippers first,
        then falls back to avena_commons.robot.grippers.

        Args:
            gripper_type: Name of gripper class (e.g., "VacuumGripper")
            gripper_config_dict: Configuration dictionary for gripper
            robot: Robot instance to pass to gripper

        Returns:
            Gripper instance

        Raises:
            ImportError: If gripper class cannot be found
            ValueError: If gripper configuration is invalid
        """
        import importlib
        import sys
        from pathlib import Path

        # Convert io_mapping dict to IOMapping object if present
        if "io_mapping" in gripper_config_dict and isinstance(
            gripper_config_dict["io_mapping"], dict
        ):
            gripper_config_dict["io_mapping"] = IOMapping(
                **gripper_config_dict["io_mapping"]
            )

        # Try local lib.robot.grippers first
        gripper_class = None
        gripper_config_class = None

        # Check if local lib exists
        local_lib_path = Path.cwd() / "lib" / "robot" / "grippers"
        if local_lib_path.exists():
            try:
                debug(
                    f"Attempting to load {gripper_type} from local lib.robot.grippers",
                    self._message_logger,
                )
                # Add lib to path if not already there
                lib_path_str = str(Path.cwd() / "lib")
                if lib_path_str not in sys.path:
                    sys.path.insert(0, lib_path_str)

                # Import from local lib
                module_name = f"robot.grippers.{self._to_snake_case(gripper_type)}"
                module = importlib.import_module(module_name)
                gripper_class = getattr(module, gripper_type)
                gripper_config_class = getattr(module, f"{gripper_type}Config")

                info(
                    f"Loaded {gripper_type} from local lib.robot.grippers",
                    self._message_logger,
                )
            except (ImportError, AttributeError) as e:
                debug(
                    f"Local gripper not found: {e}, falling back to avena_commons",
                    self._message_logger,
                )

        # Fallback to avena_commons.robot.grippers
        if gripper_class is None:
            try:
                debug(
                    f"Loading {gripper_type} from avena_commons.robot.grippers",
                    self._message_logger,
                )
                module_name = (
                    f"avena_commons.robot.grippers.{self._to_snake_case(gripper_type)}"
                )
                module = importlib.import_module(module_name)
                gripper_class = getattr(module, gripper_type)
                gripper_config_class = getattr(module, f"{gripper_type}Config")

                info(
                    f"Loaded {gripper_type} from avena_commons.robot.grippers",
                    self._message_logger,
                )
            except (ImportError, AttributeError) as e:
                error(f"Failed to import {gripper_type}: {e}", self._message_logger)
                raise ImportError(
                    f"Cannot find gripper class '{gripper_type}'. "
                    f"Tried: lib.robot.grippers and avena_commons.robot.grippers"
                )

        # Create config instance
        try:
            gripper_config = gripper_config_class(**gripper_config_dict)
        except Exception as e:
            error(f"Failed to create {gripper_type}Config: {e}", self._message_logger)
            raise ValueError(f"Invalid gripper configuration: {e}")

        # Create gripper instance
        try:
            gripper = gripper_class(
                robot=robot, config=gripper_config, message_logger=self._message_logger
            )
            return gripper
        except Exception as e:
            error(
                f"Failed to create {gripper_type} instance: {e}", self._message_logger
            )
            raise

    @staticmethod
    def _to_snake_case(name: str) -> str:
        """Convert CamelCase to snake_case.

        Args:
            name: CamelCase string (e.g., "VacuumGripper")

        Returns:
            snake_case string (e.g., "vacuum_gripper")
        """
        import re

        # Insert underscore before uppercase letters and convert to lowercase
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    # FSM Callback Methods
    async def on_initializing(self):
        """
        Callback FSM: STOPPED → INITIALIZED
        Inicjalizuje obiekt Supervisor i konfiguruje stan (robot pozostaje DISABLED)
        """
        debug(
            f"FSM: Initializing supervisor with suffix {self._suffix}",
            self._message_logger,
        )

        # Initialize state from load_state or default
        if not self._load_state:
            self._state = self._state_model
            self._state.path_execution_state.start_position = [
                self._default_configuration["start_position"]["pos1"],
                self._default_configuration["start_position"]["pos2"],
                self._default_configuration["start_position"]["pos3"],
                self._default_configuration["start_position"]["pos4"],
                self._default_configuration["start_position"]["pos5"],
                self._default_configuration["start_position"]["pos6"],
            ]
        else:
            # Load state from persistent storage and validate
            self._state["path_execution_state"]["start_position"] = self._state[
                "robot_state"
            ]["current_position"]
            self._state = self._state_model.model_validate(self._state)

        debug("Creating robot controller", self._message_logger)
        # Create RobotController without gripper first
        self._robot_controller = RobotController(
            suffix=self._suffix,
            message_logger=self._message_logger,
            debug=debug,
            configuration=self._configuration,
            gripper=None,  # Will be set after creation
        )
        debug("Robot controller created", self._message_logger)

        # Create gripper from configuration if specified
        if "gripper" in self._configuration and self._configuration["gripper"]:
            debug("Creating gripper from configuration", self._message_logger)
            gripper_type = self._configuration["gripper"]["type"]
            gripper_config_dict = self._configuration["gripper"]["config"]

            # Dynamically import gripper class
            self._gripper = self._create_gripper_instance(
                gripper_type, gripper_config_dict, self._robot_controller.robot
            )

            # Assign gripper to robot controller
            self._robot_controller._gripper = self._gripper

            # Initialize gripper systems (sets tool coords, weight, etc.)
            self._robot_controller._initialize_gripper_systems()

            debug(
                f"Gripper {gripper_type} created and initialized", self._message_logger
            )
        else:
            debug("No gripper configured", self._message_logger)

        # Configure start position
        start_position_distance = self._configuration["general"][
            "start_position_distance"
        ]
        if self._state.path_execution_state.start_position is None:
            raise RuntimeError("Start position not provided")
        self._robot_controller.save_start_position(
            self._state.path_execution_state.start_position, start_position_distance
        )

        # Configure collision levels
        self._robot_controller.change_anticollision_settings(
            j1=self._state.robot_state.collision_levels.j1,
            j2=self._state.robot_state.collision_levels.j2,
            j3=self._state.robot_state.collision_levels.j3,
            j4=self._state.robot_state.collision_levels.j4,
            j5=self._state.robot_state.collision_levels.j5,
            j6=self._state.robot_state.collision_levels.j6,
        )

        debug(
            "FSM: Supervisor initialized successfully (robot DISABLED)",
            self._message_logger,
        )

    async def on_run(self):
        """Metoda wywoływana podczas przejścia w stan RUN.
        Tu komponent rozpoczyna swoje główne zadania operacyjne."""
        pass

    async def on_pause(self):
        """Metoda wywoływana podczas przejścia w stan PAUSE.
        Tu komponent jest wstrzymany ale gotowy do wznowienia."""
        pass

    async def on_stopping(self):
        """
        FSM Callback: RUN → auto PAUSE → STOPPED
        Czyszczenie przetwarzanych zdarzeń i wyłączenie robota
        """
        debug("FSM: Stopping supervisor operations", self._message_logger)

        if self._robot_controller:
            if hasattr(self._robot_controller, "robot"):
                self._robot_controller.robotDisable()

            self._robot_controller.exit()

        self._robot_controller = None
        self._error_read = False
        self._temp_local_counter = 0

        debug("FSM: Supervisor stopped and cleaned up", self._message_logger)

    async def on_stopped(self):
        """Metoda wywoływana po przejściu w stan STOPPED.
        Tu komponent jest całkowicie zatrzymany i wyczyszczony."""
        pass

    async def on_ack(self):
        """
        Callback FSM: FAULT → STOPPED
        Potwierdzenie błędu i reset managera błędów
        """
        debug("FSM: Acknowledging fault", self._message_logger)

        if self._robot_controller:
            if hasattr(self._robot_controller, "robot"):
                self._robot_controller.robot.ResetAllError()
                info("FSM: Robot internal error reset", self._message_logger)

        self._state.current_error = ""

        debug("FSM: Fault acknowledged", self._message_logger)

    async def on_error(self):
        """Metoda wywoływana podczas przejścia w stan ON_ERROR.
        Tu komponent przechodzi w stan błędu i oczekuje na ACK operatora."""
        error(f"FSM: Entering error state", self._message_logger)

    async def on_fault(self):
        """Metoda wywoływana podczas przejścia w stan FAULT.
        Tu komponent przechodzi w stan błędu i oczekuje na ACK operatora."""
        pass

    async def on_starting(self):
        """
        Callback FSM: INITIALIZED → RUN
        Włącza robota i aktywuje wszystkie moduły
        """
        debug("FSM: Enabling robot and activating modules", self._message_logger)

        # Robot → ENABLED mode (FSM handler will start local_check automatically)
        if self._robot_controller and hasattr(self._robot_controller, "robot"):
            try:
                # Enable robot for full operation
                self._robot_controller.robotEnable()
                debug("FSM: Robot enabled successfully", self._message_logger)
            except Exception as e:
                error(f"FSM: Failed to enable robot: {e}", self._message_logger)
                raise

    async def on_pausing(self):
        """
        Callback FSM: RUN → PAUSE
        Zatrzymuje bieżący ruch, wyłącza światło chwytaka, zachowuje przetwarzane zdarzenia
        """
        debug("FSM: Pausing supervisor operations", self._message_logger)

        if self._robot_controller:
            # Stop current motion
            if hasattr(self._robot_controller, "robot"):
                self._robot_controller.robot.StopMotion()

        debug(
            "FSM: Supervisor paused, processing events preserved", self._message_logger
        )

    async def on_resuming(self):
        """
        Callback FSM: PAUSE → RUN
        Ponowne włącza robota i przygotowuje się do ukończenia zachowanych zdarzeń
        """
        debug("FSM: Resuming supervisor operations", self._message_logger)
        # TODO: Implement

    async def on_soft_stopping(self):
        """
        Callback FSM: RUN → INITIALIZED (graceful)
        Zatrzymuje przyjmowanie nowych zdarzeń, czeka na ukończenie bieżących operacji naturalnie
        """
        debug(
            "FSM: Soft stopping - waiting for operations to complete",
            self._message_logger,
        )

        # NIE robimy StopMotion - pozwalamy dokończyć eventy normalnie
        # System will wait for RobotControllerState == IDLE automatically
        # FSM handler will transition to INITIALIZED when ready

    async def on_hard_stopping(self):
        """
        Callback FSM: RUN → auto PAUSE → STOPPED
        Czyszczenie przetwarzanych zdarzeń i wyłączenie robota
        """
        debug("FSM: Stopping supervisor operations", self._message_logger)

        # Disable robot and cleanup resources
        if self._robot_controller:
            if hasattr(self._robot_controller, "robot"):
                self._robot_controller.robotDisable()

            self._robot_controller.exit()

            debug("FSM: Supervisor stopped and cleaned up", self._message_logger)

    async def _analyze_event(self, event: Event) -> bool:
        """
        Analizuje i kieruje przychodzące zdarzenia do odpowiednich obsługi.

        Args:
            event (Event): Przychodzące zdarzenie do przetworzenia
            source_queue (list[Event]): Kolejka oczekujących zdarzeń

        Returns:
            bool: True jeśli zdarzenie zostało pomyślnie przetworzone

        """
        debug(
            f"Analyzing event {event.event_type} from {event.source}",
            self._message_logger,
        )

        # Defensive guard: supervisor may not be initialized yet if FSM commands were not sent
        if self._robot_controller is None:
            event.result = Result(
                result="error",
                error_message="Supervisor not initialized. Send CMD_INITIALIZED and CMD_RUN before business events.",
            )
            error(
                f"Supervisor not initialized. Send CMD_INITIALIZED and CMD_RUN before business events.",
                self._message_logger,
            )
            await self._reply(event)
            return True

        self._state.state = self._robot_controller.state
        if self._state.state in [
            RobotControllerState.IN_MOVE,
            RobotControllerState.MOVEMENT_FINISHED,
        ]:
            event.result = Result(
                result="failure", error_code=1, error_message="Supervisor is busy"
            )
            await self._reply(event)
            return False

        # Pre-validation: Check if gripper can handle this event
        if self._gripper and self._gripper.validate_event(event):
            # Gripper claims this event - let it process
            result = self._gripper.process_event(event)
            if not result.result == "success":
                error(
                    f"Gripper event processing failed: {result.error_message}",
                    self._message_logger,
                )
                event.result = Result(
                    result="failure", error_message=result.error_message
                )
                await self._reply(event)
                return False

            # Success - check if async completion needed
            add_to_processing = result.data.get("add_to_processing", False)
        else:
            # Not a gripper event - route to robot controller handlers
            action_type = event.event_type
            add_to_processing = await self.action_selector(action_type, event)
        if add_to_processing:
            self._current_event = event
            self._add_to_processing(event)

        debug(f"Event {event.event_type} analyzed", self._message_logger)

        return True

    async def action_selector(
        self, action_type: str, event: Event
    ):  # MARK: ACTION SELECTOR
        """
        Kieruje akcje do odpowiednich obsługi RobotController.

        Obsługuje tylko built-in akcje kontrolera robota:
        - move_j, move_l (ruchy)
        - current_position (odczyt pozycji)

        Eventy grippera są już obsłużone w _analyze_event() przez validate_event().

        Args:
            action_type (str): Typ akcji do wykonania
            event (Event): Zdarzenie zawierające parametry akcji i dane

        Returns:
            bool: True jeśli event ma być dodany do processing, False w przeciwnym razie
        """
        # Robot controller built-in actions only
        if action_type in ["move_j", "move_l"]:
            move_to_processing = await self._movement_actions(action_type, event)
        elif action_type == "current_position":
            move_to_processing = await self._current_position_actions(event)
        else:
            # Unknown event type - not robot action and gripper didn't claim it
            raise ValueError(
                f"Unknown event type '{action_type}' - not a robot action and not handled by gripper"
            )

        return move_to_processing

    async def _movement_actions(self, action_type: str, event: Event):
        """
        Obsługuje operacje ruchu robota, w tym ruchy liniowe i przegubowe.

        Przetwarza polecenia ruchu z opcjonalnym mieszaniem ścieżek dla płynniejszego ruchu.
        Dla ruchów liniowych (move_l), mieszanie jest obsługiwane gdy podano wiele punktów waypoint.
        Dla ruchów przegubowych (move_j), obecnie obsługiwane są tylko ruchy z pojedynczym punktem waypoint.

        Args:
            action_type (str): Typ ruchu ('move_j' dla ruchu przegubowego lub 'move_l' dla ruchu liniowego)
            event (Event): Zdarzenie zawierające parametry ruchu, w tym ścieżkę i ustawienia prędkości

        Raises:
            ValueError: Jeśli ścieżka lub punkty waypoint są brakujące w danych zdarzenia
            NotImplementedError: Jeśli próbuje się użyć mieszania z ruchem przegubowym (move_j)
        """
        debug(f"Handling movement action: {action_type}", self._message_logger)

        move_action = SupervisorMoveAction(**event.data)
        blending = False

        debug(
            f"Move action: {move_action},  max_speed: {move_action.max_speed}",
            self._message_logger,
        )

        if move_action.path is None:
            raise ValueError("Path not provided")
        elif len(move_action.path.waypoints) == 0:
            raise ValueError("No waypoints provided")
        elif len(move_action.path.waypoints) > 1:
            blending = True

        if move_action.path.collision_override:
            # Override collision settings for the path
            debug(
                "Setting collision override to [100, 100, 100, 100, 100, 100]",
                self._message_logger,
            )
            self._robot_controller.change_anticollision_settings(
                j1=100, j2=100, j3=100, j4=100, j5=100, j6=100
            )
        else:
            collision_levels = self._default_configuration["collision_levels"]
            debug(
                f"Setting default collision levels: {collision_levels}",
                self._message_logger,
            )
            self._robot_controller.change_anticollision_settings(
                j1=collision_levels["j1"],
                j2=collision_levels["j2"],
                j3=collision_levels["j3"],
                j4=collision_levels["j4"],
                j5=collision_levels["j5"],
                j6=collision_levels["j6"],
            )

        move_action.path.max_speed = move_action.max_speed
        match action_type:
            case "move_j":
                if blending:
                    raise NotImplementedError(
                        "Blending not supported for move_j. For now..."
                    )
                self._robot_controller.MoveJ(move_action.path)

            case "move_l":
                if blending:
                    self._robot_controller.MoveL_with_blend(move_action.path)
                else:
                    self._robot_controller.MoveL(move_action.path)
        debug("Movement action finished", self._message_logger)

        return True

    async def _current_position_actions(self, event: Event):
        """
        Obsługuje operację odczytu bieżącej pozycji robota.

        Zwraca aktualną pozycję robota jako natychmiastową odpowiedź.

        Args:
            event (Event): Zdarzenie żądające aktualnej pozycji robota
        """
        debug("Handling current position request", self._message_logger)
        debug(
            f"Current robot position: {self._state.robot_state.current_position}",
            self._message_logger,
        )

        # Przygotuj odpowiedź z aktualną pozycją
        result = Result(result="success")
        event.result = result
        event.data = {"current_position": self._state.robot_state.current_position}

        # Wyślij natychmiastową odpowiedź
        await self._reply(event)

        debug("Current position response sent", self._message_logger)

        # Zwróć False - nie dodawaj do przetwarzania, operacja zakończona natychmiast
        return False

    def _utility_actions(self, action_type: str, event: Event):
        """
        Obsługuje operacje narzędziowe (utility) dla supervisora robota.

        Zapewnia operacje narzędziowe, takie jak sprawdzanie aktualnej pozycji robota.

        Argumenty:
            action_type (str): Typ operacji narzędziowej (np. 'check_start_position')
            event (Event): Zdarzenie zawierające parametry operacji narzędziowej
        """
        debug(f"Handling utility action: {action_type}", self._message_logger)
        # Not implemented yet
        return False

    async def get_status_update(self):
        """Update state from supervisor if available"""
        if self._robot_controller is None:
            return  # Supervisor not initialized yet

        try:
            self._robot_controller.get_status_update()

            # Handle case when robot_controller returns None (error occurred)
            if self._robot_controller.status is None:
                warning(
                    "RobotController.get_status_update() returned None - controller in ERROR state",
                    self._message_logger,
                )
                return

            # Update state from supervisor (includes gripper_state from robot controller)
            self._state = self._state_model.model_validate(
                self._robot_controller.status
            )
        except Exception as e:
            error(f"Error updating supervisor status: {e}", self._message_logger)

    async def _handle_event(self, action_types: tuple, waypoint_data=None):
        if self._robot_controller:
            self._robot_controller.state = RobotControllerState.IDLE

        for action_type in action_types:
            event: Event = self._find_and_remove_processing_event(
                event=self._current_event
            )

            if event is not None:
                state_specific_error = self._get_state_specific_error(event)
                if state_specific_error is not None:
                    status, code, error_message = state_specific_error

                    self._error = True
                    self._error_code = code
                    self._error_message = error_message

                    result = Result(
                        result=status, error_code=code, error_message=error_message
                    )

                    if status == "test_failed":
                        # For test_failed, we do not change to error state
                        self._error = False

                elif self._state.current_error:
                    self._error = True
                    self._error_code = 1  # default error code
                    self._error_message = str(self._state.current_error)

                    result = Result(
                        result=self._error_message,
                        error_code=self._error_code,
                        error_message=self._error_message,
                    )

                else:
                    result = Result(result="success")
                    if waypoint_data:
                        corrected_waypoint = Waypoint(
                            waypoint_name="Photo_waypoint",
                            waypoint=waypoint_data,
                        )
                        event.data = SupervisorGripperAction(
                            waypoint=corrected_waypoint
                        ).model_dump()

                # Reset error read flag on success
                self._error_read = False

                event.result = result
                debug(f"Replying with result: {result}", self._message_logger)
                await self._reply(event)

                if self._error:
                    self._change_fsm_state(EventListenerState.ON_ERROR)

                break  # skip if this was first action type
            else:
                debug(
                    f"No event found for action_type: {action_type}",
                    self._message_logger,
                )

    async def _check_local_data(self):  # MARK: CHECK LOCAL DATA
        """
        Monitoruje stan supervisora i zarządza zakończeniem zdarzeń.

        Okresowo sprawdza stan robota i obsługuje:
        - Wykrywanie i raportowanie błędów
        - Status zakończenia ruchu
        - Zakończenie operacji chwytaka
        - Zakończenie operacji kamery
        - Generowanie i wysyłanie odpowiedzi do źródeł zdarzeń
        - Implementację punktów korekcyjnych (waypoint) dla wybranych operacji
        - Zarządzanie maszyną stanów supervisora

        Metoda implementuje maszynę stanów, która przetwarza różne typy operacji
        i generuje odpowiednie odpowiedzi w zależności od wyników operacji oraz stanów błędów.
        """
        # Skip if supervisor not initialized
        if self._robot_controller is None:
            return

        self._temp_local_counter += 1

        # Update status from supervisor
        await self.get_status_update()

        # Skip processing if supervisor is idle
        if self._state.state == RobotControllerState.IDLE:
            return

        # Error handling (only if supervisor is available)
        if (
            self._robot_controller
            and (
                self._state.state == RobotControllerState.ERROR
                or self._state.state == RobotControllerState.WATCHDOG_ERROR
            )
            and not self._error_read
        ):
            self._error_read = True

            if self._state.state == RobotControllerState.WATCHDOG_ERROR:
                self._state.pump_watchdog_failure = True  # For Handling event failure with new error code and status return to munchies

            # else:
            warning(f"Supervisor state: {self._state.state}", self._message_logger)
            warning(
                f"Supervisor current error: {self._state.current_error}",
                self._message_logger,
            )

            self._robot_controller.state = RobotControllerState.MOVEMENT_FINISHED

        # State-based event completion
        match self._state.state:
            case RobotControllerState.MOVEMENT_FINISHED:
                await self._handle_event(("move_l", "move_j"))

            case RobotControllerState.GRIPPER_FINISHED:
                # Handle any gripper event completion - check if current event is gripper event
                if (
                    self._gripper
                    and hasattr(self, "_current_event")
                    and self._current_event
                ):
                    if self._gripper.validate_event(self._current_event):
                        # Current event is a gripper event - handle its completion
                        await self._handle_event((self._current_event.event_type,))
                    else:
                        # Should not happen - GRIPPER_FINISHED without gripper event
                        warning(
                            f"GRIPPER_FINISHED state but current event {self._current_event.event_type} is not a gripper event",
                            self._message_logger,
                        )

    def _get_state_specific_error(self, event: Event) -> str | None:
        """
        Generuje komunikaty o błędach specyficzne dla danego stanu supervisora.

        Argumenty:
            state (RobotControllerState): Aktualny stan supervisora

        Zwraca:
            tuple[str, str] | None: Krotka zawierająca (status, komunikat_błędu) jeśli wystąpił błąd,
            lub None jeśli nie ma błędu. Status może być 'failure' lub 'test_failed'.
        """
        match self._state.state:
            case RobotControllerState.MOVEMENT_FINISHED:
                # if event.data.get("path") and event.data["path"].get("testing_move", False):
                move_data = SupervisorMoveAction(**event.data)
                if move_data.path and move_data.path.testing_move:
                    if not self._state.path_execution_state.testing_move_check:
                        status = "test_failed"
                        code = 1
                        self._state.path_execution_state.testing_move_check = True
                        return status, code, "Move check failed: move test_failed."

                if self._state.pump_watchdog_failure:
                    status = "failure"
                    code = 2
                    self._state.pump_watchdog_failure = False
                    return status, code, "Pump watchdog failure detected"

            case RobotControllerState.GRIPPER_FINISHED:
                # Delegate error checking to gripper
                if self._gripper:
                    # Get current path flags for error context
                    path_flags = {}
                    if (
                        hasattr(self._state, "path_execution_state")
                        and self._state.path_execution_state
                    ):
                        path_flags = {
                            "testing_move": getattr(
                                self._state.path_execution_state, "testing_move", False
                            )
                        }

                    # Check for gripper-specific errors
                    gripper_error = self._gripper.check_errors(path_flags)
                    if gripper_error:
                        status = "failure"
                        code = 3
                        return status, code, gripper_error.message

        return None

    def cleanup(self):
        """
        Wykonuje operacje porządkowe przed zamknięciem.

        Zapewnia prawidłowe zwolnienie zasobów i zamknięcie supervisora.
        """
        self._message_logger = None
        if self._robot_controller:
            self._robot_controller.exit()
            self._robot_controller = None
        self._message_logger = None

    def __del__(self):
        """
        Destruktor do zapewnienia prawidłowego czyszczenia.

        Wywołuje destruktor klasy nadrzędnej dla dodatkowego czyszczenia.
        """
        self.cleanup()
        super().__del__()
