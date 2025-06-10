import threading
import time

from avena_commons.io.device import modbus_check_device_connection
from avena_commons.util.logger import MessageLogger, debug, error, info

from ..io_utils import init_device_di, init_device_do


class TLC57R24V08:
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
        message_logger: MessageLogger | None = None,
        debug: bool = True,
    ):
        self.device_name = device_name
        self.bus = bus
        self.address = address
        self.configuration_type = configuration_type
        self.reverse_direction = reverse_direction
        self.period: float = period
        self.do_count = do_count
        self.di_count = di_count
        self.message_logger = message_logger
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
        # TODO: implement DO writing thread
        self.do_current_state: list[int] = [0] * self.do_count
        self.do_state_changed: bool = False
        self.do_previous_state: list[int] = [0] * self.do_count
        self.__do_lock: threading.Lock = threading.Lock()
        self._do_thread: threading.Thread | None = None
        self._do_stop_event: threading.Event = threading.Event()

        self.__setup()

    def __setup(self):
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
            )
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
        """Start the continuous jog thread"""
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
        """Continuous jog thread worker that sends jog or position parameters when enabled"""

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
                    if response_status in [0, 1]:
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
        """Send jog parameters to the device via Modbus"""
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
        """Send position parameters to the device via Modbus"""
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
        self.__motor_running = True
        self._status_thread = threading.Thread(target=self.__operation_status_thread)
        self._status_thread.start()

    def is_motor_running(self):
        return self.operation_status_motor_running

    def is_failure(self):
        return self.operation_status_failure

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
        """
        Enable position mode with specified parameters. The jog thread will handle sending the parameters.

        Args:
            position (int): Target position in pulses (-2147483648~2147483647)
            speed (int): Positioning speed in r/min (0-3000)
            accel (int): Positioning acceleration time in ms (0-2000)
            decel (int): Positioning deceleration time in ms (0-2000)
            start_speed (int): Positioning start speed in r/min (0-3000)
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

    def run_jog(self, speed: int, accel: int = 0, decel: int = 0):
        """
        Enable jog mode with specified parameters. The jog thread will handle sending the parameters.

        Args:
            speed (int): Positioning speed in r/min (-3000 - 3000)
            accel (int): Positioning acceleration time in ms (0-2000)
            decel (int): Positioning deceleration time in ms (0-2000)
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

    def stop(self):
        """Stop motor operation and disable jog mode"""
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
                else:
                    if self.__debug:
                        warning(
                            f"{self.device_name} - Unable to read DI register",
                            message_logger=self.message_logger,
                        )

            except Exception as e:
                error(
                    f"{self.device_name} - Error reading DI: {e}",
                    message_logger=self.message_logger,
                )

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
                    except Exception as e:
                        error(
                            f"{self.device_name} - Error writing DO: {str(e)}",
                            message_logger=self.message_logger,
                        )

            except Exception as e:
                error(
                    f"{self.device_name} - Error in DO thread: {e}",
                    message_logger=self.message_logger,
                )

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
