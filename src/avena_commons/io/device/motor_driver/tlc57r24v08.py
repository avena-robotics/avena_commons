import threading
import time

from avena_commons.io.device import modbus_check_device_connection
from avena_commons.util.logger import MessageLogger, debug, error, info, warning

from ..io_utils import init_device_di, init_device_do
from ..physical_device_base import PhysicalDeviceBase


class TLC57R24V08(PhysicalDeviceBase):
    """Sterownik TLC57R24V08 z trybem jog/pozycja, wątkami DI/DO i obsługą błędów.

    Args:
        device_name (str): Nazwa urządzenia.
        bus: Magistrala Modbus/komunikacyjna.
        address: Adres urządzenia.
        configuration_type: Typ konfiguracji urządzenia (mapowanie wejść/wyjść).
        reverse_direction (bool): Odwrócenie kierunku enkodera.
        period (float): Okres pętli wątków (s).
        do_count (int): Liczba linii DO.
        di_count (int): Liczba linii DI.
        movement_retry_attempts (int): Maks. próby ponawiania ruchu przy błędzie.
        movement_retry_delay (float): Opóźnienie między próbami (s).
        message_logger (MessageLogger | None): Logger wiadomości.
        debug (bool): Włącza logi debug.
        command_send_retry_attempts (int): Próby ponownego wysłania komendy (niezależnie od retry ruchu).
        max_consecutive_errors (int): Próg błędów przed FAULT.
    """

    def __init__(
        self,
        device_name: str,
        bus,
        address,
        configuration_type,
        reverse_direction: bool = False,
        period: float = 0.05,
        do_count: int = 3,
        di_count: int = 5,
        movement_retry_attempts: int = 3,
        movement_retry_delay: float = 0.2,
        message_logger: MessageLogger | None = None,
        debug: bool = True,
        command_send_retry_attempts: int = 3,
        max_consecutive_errors: int = 3,
    ):
        super().__init__(
            device_name=device_name,
            max_consecutive_errors=max_consecutive_errors,
            message_logger=message_logger,
        )
        self.bus = bus
        self.address = address
        self.configuration_type = configuration_type
        self.reverse_direction = reverse_direction
        self.period: float = period
        self.do_count = do_count
        self.di_count = di_count
        self.__debug = debug
        self.operation_status_in_place = False
        self.operation_status_homing_completed = False
        self.operation_status_motor_running = False
        self.operation_status_failure = False
        self.operation_status_motor_enabling = False
        self.operation_status_positive_software_limit = False
        self.operation_status_negative_software_limit = False
        self.current_alarm_overcurrent = False
        self.current_alarm_overvoltage = False
        self.current_alarm_undervoltage = False
        self.__motor_running = False

        # Jog threading control flags
        self._stop_event = threading.Event()
        self._run = False
        self._jog_speed = 0
        self._jog_accel = 0
        self._jog_decel = 0
        self._jog_control_word = 8
        self._jog_lock = threading.Lock()
        self._jog_thread = None
        self._jog_counter = 0

        # Position mode variables
        self._position_mode = False  # True for position mode, False for jog mode
        self._position_target = 0
        self._position_speed = 0
        self._position_accel = 0
        self._position_decel = 0
        self._position_start_speed = 0
        self._position_control_word = 1

        # DI reading thread properties
        self.di_value: int = 0
        self.__di_lock: threading.Lock = threading.Lock()
        self._di_thread: threading.Thread | None = None
        self._di_stop_event: threading.Event = threading.Event()

        # DO writing thread properties
        self.do_current_state: list[int] = [0] * self.do_count
        self.do_state_changed: bool = False
        self.do_previous_state: list[int] = [0] * self.do_count
        self.__do_lock: threading.Lock = threading.Lock()
        self._do_thread: threading.Thread | None = None
        self._do_stop_event: threading.Event = threading.Event()

        # Error propagation fields (for IO_server escalation)
        self._error: bool = False
        self._error_message: str | None = None

        # Movement retry configuration/state
        self._move_retry_attempts: int = (
            int(movement_retry_attempts) if movement_retry_attempts is not None else 0
        )
        self._move_retry_delay: float = (
            float(movement_retry_delay) if movement_retry_delay is not None else 0.0
        )
        self._move_in_progress: bool = False
        self._move_attempts_made: int = 0
        self._last_command_type: str | None = None  # 'jog' | 'position' | None
        self._waiting_for_failure_clear: bool = False

        # Command send retry configuration/state (independent from movement retries)
        self._command_send_retry_attempts: int = (
            int(command_send_retry_attempts)
            if command_send_retry_attempts is not None
            else 0
        )
        self._command_send_attempts_made: int = 0

        self.__setup()

    def __setup(self):
        """Konfiguruje rejestry sterownika, uruchamia wątki jog/DI/DO."""
        try:
            if self.configuration_type == 1:  # komora odbiorcza
                # komora odbiorcza
                self.bus.write_holding_registers(
                    address=self.address, first_register=17, values=[3, 2, 0, 0, 0]
                )
            elif self.configuration_type == 2:  # feeder
                # feeder
                self.bus.write_holding_registers(
                    address=self.address, first_register=17, values=[0, 0, 0, 0, 0]
                )
            # pass

            self.bus.write_holding_register(
                address=self.address, register=79, value=0x0300
            )  # reset błędów

            self.bus.write_holding_register(
                address=self.address, register=34, value=int(self.reverse_direction)
            )  # ustalenie kierunku enkodera

            # Ustawienie portów DO aby działały jak przekaźniki
            self.bus.write_holding_registers(
                address=self.address, first_register=28, values=[9, 10, 11]
            )

            init_device_di(TLC57R24V08, first_index=0, count=self.di_count)
            init_device_do(TLC57R24V08, first_index=0, count=self.do_count)

            # Start the continuous jog thread
            self._start_jog_thread()

            # Start DI reading thread
            self._start_di_thread()

            # Start DO writing thread
            self._start_do_thread()

        except Exception as e:
            error(
                f"{self.device_name} Error writing to device: {e}",
                message_logger=self.message_logger,
            )
            return None

    def _start_jog_thread(self):
        """Uruchamia wątek sterowania jog, jeśli nie działa."""
        try:
            if self._jog_thread is None or not self._jog_thread.is_alive():
                self._stop_event.clear()
                self._jog_thread = threading.Thread(
                    target=self.__jog_thread_worker, daemon=True
                )
                self._jog_thread.start()
                debug(
                    f"{self.device_name} Jog thread started",
                    message_logger=self.message_logger,
                )
        except Exception as e:
            error(
                f"{self.device_name} Error starting jog thread: {e}",
                message_logger=self.message_logger,
            )

    def __jog_thread_worker(self):
        """Wątek: wysyła parametry jog/pozycja po ustawieniu flagi run, z obsługą retry."""

        while not self._stop_event.is_set():
            now = time.time()

            try:
                with self._jog_lock:
                    current_run = self._run
                    position_mode = self._position_mode

                    if position_mode:
                        # Position mode parameters
                        target = self._position_target
                        speed = self._position_speed
                        accel = self._position_accel
                        decel = self._position_decel
                        start_speed = self._position_start_speed
                        control_word = self._position_control_word
                    else:
                        # Jog mode parameters
                        speed = self._jog_speed
                        accel = self._jog_accel
                        decel = self._jog_decel
                        control_word = self._jog_control_word

                    jog_counter = self._jog_counter

                # Send parameters only once when enabled, then disable the flag
                if current_run:
                    # Immediately set run to false after sending parameters
                    with self._jog_lock:
                        if position_mode:
                            # Position enabled - send position parameters once and disable the flag
                            response = self.__send_position_parameters(
                                target, speed, accel, decel, start_speed, control_word
                            )
                            if response:
                                self._run = False
                                self._command_send_attempts_made = 0
                            else:
                                self._command_send_attempts_made += 1
                                if (
                                    self._command_send_retry_attempts > 0
                                    and self._command_send_attempts_made
                                    >= self._command_send_retry_attempts
                                ):
                                    self._error = True
                                    self._error_message = (
                                        f"{self.device_name} - Wysyłanie parametrów pozycji: "
                                        f"przekroczono liczbę prób ("
                                        f"{self._command_send_attempts_made}/"
                                        f"{self._command_send_retry_attempts})"
                                    )
                                    error(
                                        self._error_message,
                                        message_logger=self.message_logger,
                                    )
                                    self._move_in_progress = False
                                    self._last_command_type = None
                                    self._run = False
                                else:
                                    self._run = True
                            debug(
                                f"{self.device_name} Position parameters sent: target={target}, speed={speed}, accel={accel}, decel={decel}",
                                message_logger=self.message_logger,
                            )
                        else:
                            # Jog enabled - send jog parameters once and disable the flag
                            response = self.__send_jog_parameters(
                                speed, accel, decel, control_word
                            )
                            if response:
                                self._run = False
                                self._command_send_attempts_made = 0
                            else:
                                self._command_send_attempts_made += 1
                                if (
                                    self._command_send_retry_attempts > 0
                                    and self._command_send_attempts_made
                                    >= self._command_send_retry_attempts
                                ):
                                    self._error = True
                                    self._error_message = (
                                        f"{self.device_name} - Wysyłanie parametrów ruchu: "
                                        f"przekroczono liczbę prób ("
                                        f"{self._command_send_attempts_made}/"
                                        f"{self._command_send_retry_attempts})"
                                    )
                                    error(
                                        self._error_message,
                                        message_logger=self.message_logger,
                                    )
                                    self._move_in_progress = False
                                    self._last_command_type = None
                                    self._run = False
                                else:
                                    self._run = True
                            debug(
                                f"{self.device_name} Jog parameters sent: speed={speed}, accel={accel}, decel={decel}",
                                message_logger=self.message_logger,
                            )

                # time.sleep(max(0, self.period - (time.time() - now)))
                # co 10 raz wykonac to:
                if jog_counter % 10 == 0:
                    response_status = self.bus.read_holding_registers(
                        address=self.address, first_register=4, count=2
                    )
                    if response_status and len(response_status) == 2:
                        # status_value = response_status[0] if isinstance(response_status, list) else response_status
                        status_value = response_status[0]
                        self.operation_status_in_place = bool(status_value & 1)
                        self.operation_status_homing_completed = bool(
                            status_value >> 1 & 1
                        )
                        self.operation_status_motor_running = bool(
                            status_value >> 2 & 1
                        )
                        self.operation_status_failure = bool(status_value >> 3 & 1)
                        self.operation_status_motor_enabling = bool(
                            status_value >> 4 & 1
                        )
                        self.operation_status_positive_software_limit = bool(
                            status_value >> 5 & 1
                        )
                        self.operation_status_negative_software_limit = bool(
                            status_value >> 6 & 1
                        )

                        current_alarm = response_status[1]
                        self.current_alarm_overcurrent = (
                            True if current_alarm == 1 else False
                        )
                        self.current_alarm_overvoltage = (
                            True if current_alarm == 2 else False
                        )
                        self.current_alarm_undervoltage = (
                            True if current_alarm == 3 else False
                        )

                        message = f"{self.device_name} Operation status: in_place={self.operation_status_in_place} homing_completed={self.operation_status_homing_completed} motor_running={self.operation_status_motor_running} failure={self.operation_status_failure} motor_enabling={self.operation_status_motor_enabling} positive_limit={self.operation_status_positive_software_limit} negative_limit={self.operation_status_negative_software_limit} overcurrent={self.current_alarm_overcurrent} overvoltage={self.current_alarm_overvoltage} undervoltage={self.current_alarm_undervoltage}"
                        if self.operation_status_failure:
                            error(message, message_logger=self.message_logger)
                        else:
                            debug(message, message_logger=self.message_logger)

                        # Movement error handling with retry and reset
                        try:
                            if self.operation_status_failure:
                                # Avoid hammering retry while failure bit still set
                                if not self._waiting_for_failure_clear:
                                    # Reset error at drive and schedule retry or escalate
                                    try:
                                        self.reset_error()
                                    except Exception as _e:
                                        error(
                                            f"{self.device_name} - Reset error failed: {_e}",
                                            message_logger=self.message_logger,
                                        )

                                    self._move_attempts_made += 1
                                    if (
                                        self._move_in_progress
                                        and self._move_attempts_made
                                        <= self._move_retry_attempts
                                    ):
                                        # Re-send the last command by toggling _run
                                        with self._jog_lock:
                                            self._run = True
                                        if self._move_retry_delay > 0:
                                            time.sleep(self._move_retry_delay)
                                    else:
                                        # Exceeded retry attempts → escalate error
                                        self._error = True
                                        self._error_message = (
                                            f"{self.device_name} - Błąd ruchu podczas {self._last_command_type or 'unknown'}: "
                                            f"przekroczono liczbę prób ({self._move_attempts_made}/{self._move_retry_attempts})"
                                        )
                                        error(
                                            self._error_message,
                                            message_logger=self.message_logger,
                                        )
                                        # Stop trying further
                                        self._move_in_progress = False
                                        self._last_command_type = None

                                    # From now wait until failure bit clears to avoid repeated retries in tight loop
                                    self._waiting_for_failure_clear = True
                            else:
                                # Failure bit cleared → allow next detection
                                if self._waiting_for_failure_clear:
                                    self._waiting_for_failure_clear = False

                                # Detect success and clear in-progress flags
                                if self._move_in_progress:
                                    if (
                                        self.operation_status_in_place
                                        or self.operation_status_motor_running
                                    ):
                                        self._move_in_progress = False
                                        self._last_command_type = None
                                        self._move_attempts_made = 0
                        except Exception as _eh:
                            error(
                                f"{self.device_name} - Error in movement retry handler: {_eh}",
                                message_logger=self.message_logger,
                            )

                with self._jog_lock:
                    self._jog_counter = jog_counter + 1

                time.sleep(0.005)

            except Exception as e:
                error(
                    f"{self.device_name} Error in jog thread: {e}",
                    message_logger=self.message_logger,
                )
                time.sleep(0.1)

    def __send_jog_parameters(
        self, speed: int, accel: int, decel: int, control_word: int
    ):
        """Wysyła do urządzenia parametry trybu jog przez Modbus."""
        try:
            response_setup = self.bus.write_holding_registers(
                address=self.address,
                first_register=48,
                values=[self.ujemna_na_uzupelnienie_do_dwoch(speed), accel, decel],
            )
            response_control_word = self.bus.write_holding_register(
                register=78, value=control_word, address=self.address
            )

            if not (response_setup or response_control_word):
                error(
                    f"{self.device_name} Error setting jog mode parameters",
                    message_logger=self.message_logger,
                )
                return False

            return True

        except Exception as e:
            error(
                f"{self.device_name} Error sending jog parameters: {e}",
                message_logger=self.message_logger,
            )
            return False

    def __send_position_parameters(
        self,
        position: int,
        speed: int,
        accel: int,
        decel: int,
        start_speed: int,
        control_word: int,
    ):
        """Wysyła do urządzenia parametry trybu pozycja przez Modbus."""
        try:
            high_word = (position >> 16) & 0xFFFF
            low_word = position & 0xFFFF

            response_setup = self.bus.write_holding_registers(
                address=self.address,
                first_register=51,
                values=[start_speed, accel, decel, speed, high_word, low_word],
            )
            response_control_word = self.bus.write_holding_register(
                register=78, value=control_word, address=self.address
            )

            if not (response_setup or response_control_word):
                error(
                    f"{self.device_name} Error setting position mode parameters",
                    message_logger=self.message_logger,
                )
                return False

            return True

        except Exception as e:
            error(
                f"{self.device_name} Error sending position parameters: {e}",
                message_logger=self.message_logger,
            )
            return False

    def __operation_status_thread(self):
        """Wątek śledzący status operacyjny podczas pracy silnika."""
        while self.__motor_running:
            response_status = self.bus.read_holding_registers(
                address=self.address, first_register=4, count=2
            )
            # status_value = response_status[0] if isinstance(response_status, list) else response_status
            status_value = response_status[0]
            self.operation_status_in_place = bool(status_value & 1)
            self.operation_status_homing_completed = bool(status_value >> 1 & 1)
            self.operation_status_motor_running = bool(status_value >> 2 & 1)
            self.operation_status_failure = bool(status_value >> 3 & 1)
            self.operation_status_motor_enabling = bool(status_value >> 4 & 1)
            self.operation_status_positive_software_limit = bool(status_value >> 5 & 1)
            self.operation_status_negative_software_limit = bool(status_value >> 6 & 1)

            current_alarm = response_status[1]
            self.current_alarm_overcurrent = True if current_alarm == 1 else False
            self.current_alarm_overvoltage = True if current_alarm == 2 else False
            self.current_alarm_undervoltage = True if current_alarm == 3 else False

            message = f"{self.device_name} Operation status: in_place={self.operation_status_in_place} homing_completed={self.operation_status_homing_completed} motor_running={self.operation_status_motor_running} failure={self.operation_status_failure} motor_enabling={self.operation_status_motor_enabling} positive_limit={self.operation_status_positive_software_limit} negative_limit={self.operation_status_negative_software_limit} overcurrent={self.current_alarm_overcurrent} overvoltage={self.current_alarm_overvoltage} undervoltage={self.current_alarm_undervoltage}"
            if self.operation_status_failure:
                error(message, message_logger=self.message_logger)
            else:
                debug(message, message_logger=self.message_logger)
            time.sleep(0.1)

    def __run_operation_status_read(self):
        """Uruchamia wątek odczytu statusu operacyjnego."""
        self.__motor_running = True
        self._status_thread = threading.Thread(target=self.__operation_status_thread)
        self._status_thread.start()

    def is_motor_running(self):
        """Zwraca True, jeśli silnik jest uruchomiony (bit motor_running)."""
        return self.operation_status_motor_running

    def is_failure(self):
        """Zwraca True, jeśli występuje stan awarii (failure)."""
        return self.operation_status_failure

    def reset_error(self):
        """Resetuje błąd w urządzeniu (zapis do rejestru resetu błędów)."""
        self.bus.write_holding_register(address=self.address, register=79, value=0x0300)
        debug(
            f"{self.device_name} - Reset po byciu w stanie failure",
            message_logger=self.message_logger,
        )

    def ujemna_na_uzupelnienie_do_dwoch(self, wartosc: int, bity: int = 16):
        if wartosc < 0:
            # Wartość maskujemy na określoną liczbę bitów
            return (1 << bity) + wartosc
        return wartosc

    def run_position(
        self,
        position: int,
        speed: int,
        accel: int = 1,
        decel: int = 1,
        start_speed: int = 0,
    ):
        """Włącza tryb pozycja z podanymi parametrami (wysyłką zajmuje się wątek jog).

        Args:
            position (int): Docelowa pozycja w impulsach (-2147483648..2147483647).
            speed (int): Prędkość pozycjonowania w r/min (0..3000).
            accel (int): Czas narastania prędkości w ms (0..2000).
            decel (int): Czas opadania prędkości w ms (0..2000).
            start_speed (int): Prędkość startowa w r/min (0..3000).
        """
        info(
            f"{self.device_name}.run_position(position={position}, speed={speed}, accel={accel}, decel={decel}, start_speed={start_speed})",
            message_logger=self.message_logger,
        )

        with self._jog_lock:
            self._position_mode = True
            self._position_target = position
            self._position_speed = speed
            self._position_accel = accel
            self._position_decel = decel
            self._position_start_speed = start_speed
            self._position_control_word = 1
            self._run = True
        # Initialize movement tracking
        self._move_in_progress = True
        self._last_command_type = "position"
        self._move_attempts_made = 0
        self._error = False
        self._error_message = None
        self._command_send_attempts_made = 0

    def run_jog(self, speed: int, accel: int = 0, decel: int = 0):
        """Włącza tryb jog z podanymi parametrami (wysyłką zajmuje się wątek jog).

        Args:
            speed (int): Prędkość w r/min (-3000..3000).
            accel (int): Czas narastania w ms (0..2000).
            decel (int): Czas opadania w ms (0..2000).
        """
        info(
            f"{self.device_name}.run_jog(speed={speed}, accel={accel}, decel={decel})",
            message_logger=self.message_logger,
        )

        with self._jog_lock:
            self._position_mode = False
            self._jog_speed = speed
            self._jog_accel = accel
            self._jog_decel = decel
            self._jog_control_word = 8
            self._run = True
        # Initialize movement tracking
        self._move_in_progress = True
        self._last_command_type = "jog"
        self._move_attempts_made = 0
        self._error = False
        self._error_message = None
        self._command_send_attempts_made = 0

    def stop(self):
        """Zatrzymuje silnik i wyłącza tryb jog."""
        self.__motor_running = False

        # Disable jog mode
        with self._jog_lock:
            self._run = True
            self._position_mode = False  # Reset to jog mode
            self._jog_speed = 0
            self._jog_accel = 0
            self._jog_decel = 0
            self._jog_control_word = 32

        info(f"{self.device_name}.stop", message_logger=self.message_logger)
        # The jog thread will handle sending the stop command when jog is disabled
        # Clear movement tracking (stop requested)
        self._move_in_progress = False
        self._last_command_type = None
        self._command_send_attempts_made = 0

    def di(self, index: int):
        """Read DI value from cached data"""
        with self.__di_lock:
            result = 1 if (self.di_value & (1 << index)) else 0
            if self.__debug:
                debug(
                    f"{self.device_name} - DI{index} value: {result}",
                    message_logger=self.message_logger,
                )
            return result

    def do(self, index: int, value: bool = None):
        """Set or get DO value - buffered write via thread"""
        if value is None:
            # Return current state of the specified DO from buffer
            with self.__do_lock:
                return self.do_current_state[index]
        else:
            # Update buffer - actual write will be handled by DO thread
            with self.__do_lock:
                self.do_current_state[index] = 1 if value else 0
                self.do_state_changed = True
            if self.__debug:
                debug(
                    f"{self.device_name} - DO{index} buffered to: {value}",
                    message_logger=self.message_logger,
                )
            return None

    def check_device_connection(self) -> bool:
        """Sprawdza połączenie urządzenia i status FSM.

        Returns:
            bool: True jeśli urządzenie nie jest w FAULT i połączenie działa.
        """
        # First check FSM health
        if not self.check_health():
            return False

        # Then check Modbus connection
        return modbus_check_device_connection(
            device_name=self.device_name,
            bus=self.bus,
            address=self.address,
            register=6,
            message_logger=self.message_logger,
        )

    def _start_di_thread(self):
        """Start the DI reading thread"""
        try:
            if self._di_thread is None or not self._di_thread.is_alive():
                self._di_stop_event.clear()
                self._di_thread = threading.Thread(
                    target=self._di_thread_worker, daemon=True
                )
                self._di_thread.start()
                if self.__debug:
                    debug(
                        f"{self.device_name} DI monitoring thread started",
                        message_logger=self.message_logger,
                    )
        except Exception as e:
            error(
                f"{self.device_name} Error starting DI thread: {e}",
                message_logger=self.message_logger,
            )

    def _start_do_thread(self):
        """Start the DO writing thread"""
        try:
            if self._do_thread is None or not self._do_thread.is_alive():
                self._do_stop_event.clear()
                self._do_thread = threading.Thread(
                    target=self._do_thread_worker, daemon=True
                )
                self._do_thread.start()
                if self.__debug:
                    debug(
                        f"{self.device_name} DO writing thread started",
                        message_logger=self.message_logger,
                    )
        except Exception as e:
            error(
                f"{self.device_name} Error starting DO thread: {e}",
                message_logger=self.message_logger,
            )

    def _di_thread_worker(self):
        """Background thread that periodically reads DI values"""
        while not self._di_stop_event.is_set():
            now = time.time()

            try:
                # Read DI register
                response = self.bus.read_holding_register(
                    address=self.address, register=6
                )

                if response is not None and type(response) == int:
                    with self.__di_lock:
                        self.di_value = response
                        if self.__debug:
                            debug(
                                f"{self.device_name} - DI value updated: {bin(response)}",
                                message_logger=self.message_logger,
                            )
                    # Successful read - clear error counter
                    self.clear_error()
                else:
                    if self.__debug:
                        warning(
                            f"{self.device_name} - Unable to read DI register",
                            message_logger=self.message_logger,
                        )
                    self.set_error("Unable to read DI register")

            except Exception as e:
                error(
                    f"{self.device_name} - Error reading DI: {e}",
                    message_logger=self.message_logger,
                )
                self.set_error(f"Error reading DI: {e}")

            time.sleep(max(0, self.period - (time.time() - now)))

    def _do_thread_worker(self):
        """Background thread that periodically writes DO values from buffer"""
        while not self._do_stop_event.is_set():
            now = time.time()

            try:
                with self.__do_lock:
                    if (
                        self.do_state_changed
                        or self.do_current_state != self.do_previous_state
                    ):
                        do_current_state = self.do_current_state.copy()
                        self.do_state_changed = False
                        self.do_previous_state = do_current_state.copy()
                        write_needed = True
                    else:
                        write_needed = False

                if write_needed:
                    try:
                        self.bus.write_holding_registers(
                            address=self.address,
                            first_register=28,
                            values=do_current_state,
                        )
                        if self.__debug:
                            debug(
                                f"{self.device_name} - DO value updated: {bin(do_current_state)}",
                                message_logger=self.message_logger,
                            )
                        # Successful write - clear error counter
                        self.clear_error()
                    except Exception as e:
                        error(
                            f"{self.device_name} - Error writing DO: {str(e)}",
                            message_logger=self.message_logger,
                        )
                        self.set_error(f"Error writing DO: {str(e)}")

            except Exception as e:
                error(
                    f"{self.device_name} - Error in DO thread: {e}",
                    message_logger=self.message_logger,
                )
                self.set_error(f"Error in DO thread: {e}")

            time.sleep(max(0, self.period - (time.time() - now)))

    def __del__(self):
        try:
            # Stop DI thread
            if hasattr(self, "_di_stop_event"):
                self._di_stop_event.set()
            if (
                hasattr(self, "_di_thread")
                and self._di_thread is not None
                and self._di_thread.is_alive()
            ):
                self._di_thread.join(timeout=1.0)
                self._di_thread = None

            # Stop DO thread
            if hasattr(self, "_do_stop_event"):
                self._do_stop_event.set()
            if (
                hasattr(self, "_do_thread")
                and self._do_thread is not None
                and self._do_thread.is_alive()
            ):
                self._do_thread.join(timeout=1.0)
                self._do_thread = None

            # Stop jog thread
            if hasattr(self, "_stop_event"):
                self._stop_event.set()
            if (
                hasattr(self, "_jog_thread")
                and self._jog_thread is not None
                and self._jog_thread.is_alive()
            ):
                self._jog_thread.join(timeout=1.0)
                self._jog_thread = None

            self.stop()
            if hasattr(self, "_status_thread"):
                self._status_thread.join(timeout=1.0)
        except Exception:
            pass  # nie loguj tutaj!

    def __str__(self) -> str:
        """
        Zwraca czytelną reprezentację urządzenia TLC57R24V08 w formie stringa.
        Używane przy printowaniu urządzenia.

        Returns:
            str: Czytelna reprezentacja urządzenia zawierająca nazwę, stan silnika i podstawowe statusy
        """
        try:
            # Określenie głównego stanu urządzenia
            if self.operation_status_failure:
                main_state = "FAILURE"
            elif self.operation_status_motor_running:
                main_state = "RUNNING"
            elif self.operation_status_in_place:
                main_state = "IN_PLACE"
            elif self.operation_status_homing_completed:
                main_state = "HOMED"
            else:
                main_state = "IDLE"

            # Dodaj informacje o alarmach jeśli występują
            alarms = []
            if self.current_alarm_overcurrent:
                alarms.append("OVERCURRENT")
            if self.current_alarm_overvoltage:
                alarms.append("OVERVOLTAGE")
            if self.current_alarm_undervoltage:
                alarms.append("UNDERVOLTAGE")

            alarm_info = f", alarms={alarms}" if alarms else ""

            return f"TLC57R24V08(name='{self.device_name}', state={main_state}, DI={bin(self.di_value)}, DO={self.do_current_state}{alarm_info})"

        except Exception as e:
            # Fallback w przypadku błędu - pokazujemy podstawowe informacje
            return (
                f"TLC57R24V08(name='{self.device_name}', state=ERROR, error='{str(e)}')"
            )

    def __repr__(self) -> str:
        """
        Zwraca reprezentację urządzenia TLC57R24V08 dla developerów.
        Pokazuje więcej szczegółów technicznych.

        Returns:
            str: Szczegółowa reprezentacja urządzenia
        """
        try:
            return (
                f"TLC57R24V08(device_name='{self.device_name}', "
                f"address={self.address}, "
                f"config_type={self.configuration_type}, "
                f"reverse_direction={self.reverse_direction}, "
                f"operation_status={{in_place={self.operation_status_in_place}, "
                f"homing_completed={self.operation_status_homing_completed}, "
                f"motor_running={self.operation_status_motor_running}, "
                f"failure={self.operation_status_failure}, "
                f"motor_enabling={self.operation_status_motor_enabling}, "
                f"positive_limit={self.operation_status_positive_software_limit}, "
                f"negative_limit={self.operation_status_negative_software_limit}}}, "
                f"current_alarms={{overcurrent={self.current_alarm_overcurrent}, "
                f"overvoltage={self.current_alarm_overvoltage}, "
                f"undervoltage={self.current_alarm_undervoltage}}}, "
                f"di_value={self.di_value}, "
                f"do_current_state={self.do_current_state})"
            )
        except Exception as e:
            return f"TLC57R24V08(device_name='{self.device_name}', error='{str(e)}')"

    def to_dict(self) -> dict:
        """
        Zwraca słownikową reprezentację urządzenia TLC57R24V08.
        Używane do zapisywania stanu urządzenia w strukturach danych.

        Returns:
            dict: Słownik zawierający:
                - name: nazwa urządzenia
                - address: adres Modbus urządzenia
                - configuration_type: typ konfiguracji
                - reverse_direction: kierunek obrotu
                - operation_status: słownik ze statusami operacyjnymi
                - current_alarms: słownik z alarmami
                - di_value: wartość wejść cyfrowych
                - do_current_state: aktualny stan wyjść cyfrowych
                - error: informacja o błędzie (jeśli wystąpił)
        """
        result = {
            "name": self.device_name,
            "address": self.address,
            "configuration_type": self.configuration_type,
            "reverse_direction": self.reverse_direction,
        }

        try:
            # Dodanie statusów operacyjnych
            result["operation_status"] = {
                "in_place": self.operation_status_in_place,
                "homing_completed": self.operation_status_homing_completed,
                "motor_running": self.operation_status_motor_running,
                "failure": self.operation_status_failure,
                "motor_enabling": self.operation_status_motor_enabling,
                "positive_software_limit": self.operation_status_positive_software_limit,
                "negative_software_limit": self.operation_status_negative_software_limit,
            }

            # Dodanie alarmów
            result["current_alarms"] = {
                "overcurrent": self.current_alarm_overcurrent,
                "overvoltage": self.current_alarm_overvoltage,
                "undervoltage": self.current_alarm_undervoltage,
            }

            # Dodanie stanu DI/DO
            result["di_value"] = self.di_value
            result["do_current_state"] = self.do_current_state.copy()

            # Eskalacja błędu (dla IO_server i monitoringu)
            result["error"] = self._error
            result["error_message"] = self._error_message

            # Dodanie głównego stanu urządzenia
            if self.operation_status_failure:
                result["main_state"] = "FAILURE"
            elif self.operation_status_motor_running:
                result["main_state"] = "RUNNING"
            elif self.operation_status_in_place:
                result["main_state"] = "IN_PLACE"
            elif self.operation_status_homing_completed:
                result["main_state"] = "HOMED"
            else:
                result["main_state"] = "IDLE"

        except Exception as e:
            # W przypadku błędu dodajemy informację o błędzie
            result["main_state"] = "ERROR"
            result["error"] = str(e)
            result["error_message"] = str(e)

            if self.message_logger:
                error(
                    f"{self.device_name} - Error creating dict representation: {e}",
                    message_logger=self.message_logger,
                )

        return result
