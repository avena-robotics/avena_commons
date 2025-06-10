import threading
import time

from avena_commons.util.logger import MessageLogger, debug, error, info, warning

from ...device import modbus_check_device_connection
from ..io_utils import init_device_di, init_device_do


class DSR:
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

        # Operation status properties (from register 3)
        self.operation_status_out_of_tolerance = False
        self.operation_status_undervoltage = False
        self.operation_status_overvoltage = False
        self.operation_status_overcurrent = False
        self.operation_status_encoder_fault = False
        self.operation_status_overload = False
        self.operation_status_error_bit = False
        self.operation_status_motor_enabling = False
        self.operation_status_homing_completed = False
        self.operation_status_positive_software_limit = False
        self.operation_status_negative_software_limit = False
        self.operation_status_in_place = False

        # Velocity threading control flags
        self._velocity_stop_event = threading.Event()
        self._velocity_run = False
        self._velocity_speed = 0
        self._velocity_accel = 0
        self._velocity_decel = 0
        self._velocity_control_word = 0
        self._velocity_lock = threading.Lock()
        self._velocity_thread = None
        self._velocity_counter = 0

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

        self.__setup()

    def __setup(self):
        try:
            if self.configuration_type == 1:
                # Set DI to do nothing
                self.bus.write_holding_registers(
                    address=self.address, first_register=135, values=[0, 0, 0, 0, 0]
                )

            self.bus.write_holding_register(
                address=self.address, register=98, value=1
            )  # alarm clear
            self.bus.write_holding_register(
                address=self.address, register=105, value=int(self.reverse_direction)
            )  # ustalenie kierunku enkodera

            # Ustawienie portów DO aby działały jak przekaźniki
            self.bus.write_holding_registers(
                address=self.address, first_register=141, values=[9, 10, 11]
            )

            init_device_di(DSR, first_index=0, count=self.di_count)
            init_device_do(DSR, first_index=0, count=self.do_count)

            # Start DI reading thread
            self._start_di_thread()

            # Start DO writing thread
            self._start_do_thread()

            # Start the continuous velocity thread
            self._start_velocity_thread()

        except Exception as e:
            error(
                f"{self.device_name} Error writing to device: {e}",
                message_logger=self.message_logger,
            )
            return None

    def _start_velocity_thread(self):
        """Start the continuous velocity thread"""
        try:
            if self._velocity_thread is None or not self._velocity_thread.is_alive():
                self._velocity_stop_event.clear()
                self._velocity_thread = threading.Thread(
                    target=self.__velocity_thread_worker, daemon=True
                )
                self._velocity_thread.start()
                debug(
                    f"{self.device_name} Velocity thread started",
                    message_logger=self.message_logger,
                )
        except Exception as e:
            error(
                f"{self.device_name} Error starting velocity thread: {e}",
                message_logger=self.message_logger,
            )

    def __velocity_thread_worker(self):
        """Continuous velocity thread worker that sends velocity parameters when enabled"""

        while not self._velocity_stop_event.is_set():
            now = time.time()

            try:
                with self._velocity_lock:
                    current_run = self._velocity_run
                    speed = self._velocity_speed
                    accel = self._velocity_accel
                    decel = self._velocity_decel
                    control_word = self._velocity_control_word
                    velocity_counter = self._velocity_counter

                # Send velocity parameters only once when velocity is enabled, then disable the flag
                if current_run:
                    # Immediately set velocity_enabled to false after sending parameters
                    with self._velocity_lock:
                        # Velocity enabled - send velocity parameters once and disable the flag
                        response = self.__send_velocity_parameters(
                            speed, accel, decel, control_word
                        )
                        if response:
                            self._velocity_run = False
                        else:
                            self._velocity_run = True
                        debug(
                            f"{self.device_name} Velocity parameters sent: speed={speed}, accel={accel}, decel={decel}",
                            message_logger=self.message_logger,
                        )

                with self._velocity_lock:
                    self._velocity_counter = velocity_counter + 1

                # Read operation status every 10 iterations (similar to TLC57R24V08)
                if velocity_counter % 10 == 0:
                    response_status = self.bus.read_holding_registers(
                        address=self.address, first_register=3, count=2
                    )
                    if response_status and len(response_status) >= 1:
                        # Parse system status from register 3
                        status_value = response_status[0]
                        self.operation_status_out_of_tolerance = bool(
                            status_value & (1 << 0)
                        )
                        self.operation_status_undervoltage = bool(
                            status_value & (1 << 1)
                        )
                        self.operation_status_overvoltage = bool(
                            status_value & (1 << 2)
                        )
                        self.operation_status_overcurrent = bool(
                            status_value & (1 << 3)
                        )
                        self.operation_status_encoder_fault = bool(
                            status_value & (1 << 4)
                        )
                        self.operation_status_overload = bool(status_value & (1 << 5))
                        self.operation_status_error_bit = bool(status_value & (1 << 6))
                        self.operation_status_motor_enabling = bool(
                            status_value & (1 << 7)
                        )
                        self.operation_status_homing_completed = bool(
                            status_value & (1 << 8)
                        )
                        self.operation_status_positive_software_limit = bool(
                            status_value & (1 << 9)
                        )
                        self.operation_status_negative_software_limit = bool(
                            status_value & (1 << 10)
                        )
                        self.operation_status_in_place = bool(status_value & (1 << 11))

                        message = f"{self.device_name} Operation status: out_of_tolerance={self.operation_status_out_of_tolerance} undervoltage={self.operation_status_undervoltage} overvoltage={self.operation_status_overvoltage} overcurrent={self.operation_status_overcurrent} encoder_fault={self.operation_status_encoder_fault} overload={self.operation_status_overload} error_bit={self.operation_status_error_bit} motor_enabling={self.operation_status_motor_enabling} homing_completed={self.operation_status_homing_completed} positive_limit={self.operation_status_positive_software_limit} negative_limit={self.operation_status_negative_software_limit} in_place={self.operation_status_in_place}"

                        # Log as error if any error conditions are present
                        if (
                            self.operation_status_error_bit
                            or self.operation_status_overcurrent
                            or self.operation_status_overvoltage
                            or self.operation_status_undervoltage
                            or self.operation_status_encoder_fault
                            or self.operation_status_overload
                        ):
                            error(message, message_logger=self.message_logger)
                        else:
                            debug(message, message_logger=self.message_logger)

                time.sleep(0.005)

            except Exception as e:
                error(
                    f"{self.device_name} Error in velocity thread: {e}",
                    message_logger=self.message_logger,
                )
                time.sleep(0.1)

    def __send_velocity_parameters(
        self, speed: int, accel: int, decel: int, control_word: int
    ):
        """Send velocity parameters to the device via Modbus"""
        try:
            # Set operating mode to velocity mode (3)
            response_mode = self.bus.write_holding_register(
                address=self.address, register=148, value=3
            )

            # Split 32-bit values into high and low 16-bit registers
            # Acceleration time (32-bit split to registers 158-159)
            accel_high = (accel >> 16) & 0xFFFF
            accel_low = accel & 0xFFFF

            # Deceleration time (32-bit split to registers 160-161)
            decel_high = (decel >> 16) & 0xFFFF
            decel_low = decel & 0xFFFF

            # Target velocity (32-bit split to registers 162-163)
            # Handle negative values using two's complement for signed 32-bit
            if speed < 0:
                speed_32bit = (1 << 32) + speed
            else:
                speed_32bit = speed

            speed_high = (speed_32bit >> 16) & 0xFFFF
            speed_low = speed_32bit & 0xFFFF

            # Write all velocity parameters in one operation (registers 158-163)
            velocity_values = [
                accel_high,
                accel_low,
                decel_high,
                decel_low,
                speed_high,
                speed_low,
            ]
            response_velocity = self.bus.write_holding_registers(
                address=self.address, first_register=158, values=velocity_values
            )

            # Set control command with velocity mode enabling (bit 2)
            # control_word should have bit 2 set for velocity mode enabling
            final_control_word = control_word | (
                1 << 2
            )  # Set bit 2 for velocity mode enabling
            response_control = self.bus.write_holding_register(
                address=self.address, register=145, value=final_control_word
            )

            # Check if any operation failed
            if not (response_mode or response_velocity or response_control):
                error(
                    f"{self.device_name} Error setting velocity mode parameters",
                    message_logger=self.message_logger,
                )
                return False

            return True

        except Exception as e:
            error(
                f"{self.device_name} Error sending velocity parameters: {e}",
                message_logger=self.message_logger,
            )
            return False

    def run_velocity(self, speed: int, accel: int = 0, decel: int = 0):
        """
        Enable velocity mode with specified parameters. The velocity thread will handle sending the parameters.

        Args:
            speed (int): Target velocity in rpm (-3000 - 3000)
            accel (int): Acceleration time in ms (0-2000)
            decel (int): Deceleration time in ms (0-2000)
        """
        info(
            f"{self.device_name}.run_velocity(speed={speed}, accel={accel}, decel={decel})",
            message_logger=self.message_logger,
        )

        with self._velocity_lock:
            self._velocity_speed = speed
            self._velocity_accel = accel
            self._velocity_decel = decel
            self._velocity_control_word = (
                0  # Base control word, bit 2 will be set in __send_velocity_parameters
            )
            self._velocity_run = True

    def stop_velocity(self):
        """Stop velocity operation"""
        info(f"{self.device_name}.stop_velocity", message_logger=self.message_logger)

        # Send stop command (bit 8) and emergency stop (bit 9) via control register
        try:
            stop_control_word = (1 << 8) | (
                1 << 9
            )  # Set bit 8 (stop) and bit 9 (emergency stop)
            response = self.bus.write_holding_register(
                address=self.address, register=145, value=stop_control_word
            )

            if not response:
                error(
                    f"{self.device_name} Error sending stop command",
                    message_logger=self.message_logger,
                )

            # Disable velocity mode
            with self._velocity_lock:
                self._velocity_run = True
                self._velocity_speed = 0
                self._velocity_accel = 0
                self._velocity_decel = 0

        except Exception as e:
            error(
                f"{self.device_name} Error stopping velocity: {e}",
                message_logger=self.message_logger,
            )

    def is_motor_running(self):
        """Check if motor is currently running (motor enabling bit)"""
        return self.operation_status_motor_enabling

    def is_failure(self):
        """Check if there are any failure conditions"""
        return (
            self.operation_status_error_bit
            or self.operation_status_overcurrent
            or self.operation_status_overvoltage
            or self.operation_status_undervoltage
            or self.operation_status_encoder_fault
            or self.operation_status_overload
        )

    def is_in_place(self):
        """Check if motor is in place (positioning completed)"""
        return self.operation_status_in_place

    def is_homing_completed(self):
        """Check if homing operation is completed"""
        return self.operation_status_homing_completed

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
                            first_register=140,
                            values=do_current_state,
                        )
                        if self.__debug:
                            debug(
                                f"{self.device_name} - DO values updated: {do_current_state}",
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

            # Stop velocity thread
            if hasattr(self, "_velocity_stop_event"):
                self._velocity_stop_event.set()
            if (
                hasattr(self, "_velocity_thread")
                and self._velocity_thread is not None
                and self._velocity_thread.is_alive()
            ):
                self._velocity_thread.join(timeout=1.0)
                self._velocity_thread = None

        except Exception:
            pass  # nie loguj tutaj!

    def check_device_connection(self) -> bool:
        return modbus_check_device_connection(
            device_name=self.device_name,
            bus=self.bus,
            address=self.address,
            register=0,
            message_logger=self.message_logger,
        )
