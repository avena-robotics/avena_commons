import threading
import time

from avena_commons.io.device import modbus_check_device_connection
from avena_commons.util.logger import MessageLogger, debug, error, info


class TLC57R24V08:
    def __init__(
        self,
        device_name: str,
        bus,
        address,
        configuration_type,
        reverse_direction: bool = False,
        period: float = 0.05,
        message_logger: MessageLogger | None = None,
    ):
        self.device_name = device_name
        self.bus = bus
        self.address = address
        self.configuration_type = configuration_type
        self.reverse_direction = reverse_direction
        self.period: float = period
        self.message_logger = message_logger
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

        self.__setup()

    def __setup(self):
        try:
            if self.configuration_type == 1:  # komora odbiorcza
                # komora odbiorcza
                self.bus.write_holding_register(
                    address=self.address, register=17, value=3
                )
                self.bus.write_holding_register(
                    address=self.address, register=18, value=2
                )
                self.bus.write_holding_register(
                    address=self.address, register=19, value=0
                )
                self.bus.write_holding_register(
                    address=self.address, register=20, value=0
                )
                self.bus.write_holding_register(
                    address=self.address, register=21, value=0
                )
            elif self.configuration_type == 2:  # feeder
                # feeder
                self.bus.write_holding_register(
                    address=self.address, register=17, value=0
                )
                self.bus.write_holding_register(
                    address=self.address, register=18, value=0
                )
                self.bus.write_holding_register(
                    address=self.address, register=19, value=0
                )
                self.bus.write_holding_register(
                    address=self.address, register=20, value=0
                )
                self.bus.write_holding_register(
                    address=self.address, register=21, value=0
                )
            # pass

            self.bus.write_holding_register(
                address=self.address, register=79, value=0x0300
            )
            self.bus.write_holding_register(
                address=self.address, register=34, value=int(self.reverse_direction)
            )  # ustalenie kierunku enkodera

            # Start the continuous jog thread
            self._start_jog_thread()

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
        """Continuous jog thread worker that sends jog parameters when enabled"""

        while not self._stop_event.is_set():
            now = time.time()

            try:
                with self._jog_lock:
                    current_run = self._run
                    speed = self._jog_speed
                    accel = self._jog_accel
                    decel = self._jog_decel
                    control_word = self._jog_control_word
                    jog_counter = self._jog_counter

                # Send jog parameters only once when jog is enabled, then disable the flag
                if current_run:
                    # Immediately set jog_enabled to false after sending parameters
                    with self._jog_lock:
                        # Jog enabled - send jog parameters once and disable the flag
                        response = self.__send_jog_parameters(
                            speed, accel, decel, control_word
                        )  # FIXME TUTAJ NORBERT - jak sie nie powiedzie to nie resetujemy flagi i ponowimy w kolejnym kroku
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

    def __run_position(
        self,
        position: int = 0,
        speed: int = 0,
        accel: int = 0,
        decel: int = 0,
        start_speed: int = 0,
        control_word: int = 1,
    ):
        """
        Set parameters for positioning mode and execute

        Args:
            position (int): Target position in pulses (-2147483648~2147483647)
            speed (int): Positioning speed in r/min (0-3000)
            accel (int): Positioning acceleration time in ms (0-2000)
            decel (int): Positioning deceleration time in ms (0-2000)
            start_speed (int): Positioning start speed in r/min (0-3000)
            control_word (int): Control word (0-127)

        Returns:
            bool: True if successful, False otherwise
        """
        # if not self.connected:
        #     error("Not connected to device", message_logger=self.message_logger)
        #     return False

        try:
            # Set start speed (address 51)
            response1 = self.bus.write_holding_register(
                register=51, value=start_speed, address=self.address
            )

            # Set acceleration time (address 52)
            response2 = self.bus.write_holding_register(
                register=52, value=accel, address=self.address
            )

            # Set deceleration time (address 53)
            response3 = self.bus.write_holding_register(
                register=53, value=decel, address=self.address
            )

            # Set positioning speed (address 54)
            response4 = self.bus.write_holding_register(
                register=54, value=speed, address=self.address
            )

            # Set target position (addresses 55-56) - 32-bit value
            # Split 32-bit value into high and low 16-bit registers
            high_word = (position >> 16) & 0xFFFF
            low_word = position & 0xFFFF

            response5 = self.bus.write_holding_registers(
                first_register=55, values=[high_word, low_word], address=self.address
            )

            # Set control word (address 78)
            response6 = self.bus.write_holding_register(
                register=78, value=control_word, address=self.address
            )

            # Check if any operation failed
            if not (
                response1
                or response2
                or response3
                or response4
                or response5
                or response6
            ):
                error(
                    f"{self.device_name} Error setting position mode parameters",
                    message_logger=self.message_logger,
                )
                return False

            self.__run_operation_status_read()
            info(
                f"{self.device_name} Successfully set position mode: position={position}, speed={speed}, accel={accel}, decel={decel}",
                message_logger=self.message_logger,
            )
            return True

        except Exception as e:
            error(
                f"{self.device_name} Error setting position mode: {e}",
                message_logger=self.message_logger,
            )
            return False

    def __run_jog(
        self, speed: int = 0, accel: int = 0, decel: int = 0, control_word: int = 8
    ):
        """
        Set parameters for positioning mode and execute

        Args:
            speed (int): Positioning speed in r/min (-3000 - 3000)
            accel (int): Positioning acceleration time in ms (0-2000)
            decel (int): Positioning deceleration time in ms (0-2000)
            control_word (int): Control word (0-127)

        Returns:
            bool: True if successful, False otherwise
        """
        # if not self.connected:
        #     error("Not connected to device", message_logger=self.message_logger)
        #     return False

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

            # # Set acceleration time (address 49)
            # response2 = self.bus.write_holding_register(register=49, value=accel, address=self.address)

            # # Set deceleration time (address 50)
            # response3 = self.bus.write_holding_register(register=50, value=decel, address=self.address)

            # # Set speed (address 48)
            # response4 = self.bus.write_holding_register(register=48, value=self.ujemna_na_uzupelnienie_do_dwoch(speed), address=self.address)

            # # Set control word (address 78)
            # response6 = self.bus.write_holding_register(register=78, value=control_word, address=self.address)

            # # debug(f"response2: {response2.isError()}{response2}, response3: {response3.isError()}{response3}, response4: {response4.isError()}{response4}, response6: {response6.isError()}{response6}", message_logger=self.message_logger)
            # # Check if any operation failed
            # if not (response2 or response3 or response4 or response6):
            #     error("Error setting position mode parameters", message_logger=self.message_logger)
            #     return False

            self.__run_operation_status_read()
            info(
                f"{self.device_name} Successfully set jog mode: speed={speed}, accel={accel}, decel={decel}",
                message_logger=self.message_logger,
            )
            return True

        except Exception as e:
            error(
                f"{self.device_name} Error setting position mode: {e}",
                message_logger=self.message_logger,
            )
            return False

    def is_motor_running(self):
        return self.operation_status_motor_running

    def is_failure(self):
        return self.operation_status_failure

    def __get_digital_inputs(self):
        """Read the status of the servo"""
        # if not self.connected:
        #     logger.error("Not connected to device")
        #     return None

        try:
            response = self.bus.read_holding_register(address=self.address, register=6)
            # print(response)
            # print(type(response))

            if type(response) == int:
                info(
                    f"{self.device_name} Digital inputs: {response}",
                    message_logger=self.message_logger,
                )
                return response
            else:
                error(
                    f"{self.device_name} __get_digital_inputs: Error reading status: {response}",
                    message_logger=self.message_logger,
                )
                return None
        except Exception as e:
            error(
                f"{self.device_name} Exception:Error reading status: {e}",
                message_logger=self.message_logger,
            )
            return None

    def __get_digital_input(self, input_number: int):
        """Read the status of the servo"""
        digital_inputs = self.__get_digital_inputs()
        if digital_inputs is None:
            # error(f"Error reading status: {digital_inputs}", message_logger=self.message_logger)
            return None
        debug(
            f"{self.device_name} Digital inputs value: {bool(digital_inputs & (1 << input_number))}",
            message_logger=self.message_logger,
        )
        return bool(digital_inputs & (1 << input_number))

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
        info(
            f"{self.device_name}.run_position(position={position}, speed={speed}, accel={accel}, decel={decel}, start_speed={start_speed})",
            message_logger=self.message_logger,
        )
        self.__run_position(
            position=position,
            speed=speed,
            accel=accel,
            decel=decel,
            start_speed=start_speed,
            control_word=1,
        )

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
            self._jog_speed = 0
            self._jog_accel = 0
            self._jog_decel = 0
            self._jog_control_word = 32

        info(f"{self.device_name}.stop", message_logger=self.message_logger)
        # The jog thread will handle sending the stop command when jog is disabled

    def di0(self):
        info(f"{self.device_name}.di0", message_logger=self.message_logger)
        return self.__get_digital_input(input_number=0)

    def di1(self):
        info(f"{self.device_name}.di1", message_logger=self.message_logger)
        return self.__get_digital_input(input_number=1)

    def di2(self):
        info(f"{self.device_name}.di2", message_logger=self.message_logger)
        return self.__get_digital_input(input_number=2)

    def di3(self):
        info(f"{self.device_name}.di3", message_logger=self.message_logger)
        return self.__get_digital_input(input_number=3)

    def di4(self):
        info(f"{self.device_name}.di4", message_logger=self.message_logger)
        return self.__get_digital_input(input_number=4)

    def di5(self):
        info(f"{self.device_name}.di5", message_logger=self.message_logger)
        return self.__get_digital_input(input_number=5)

    def do0(self):
        info(f"{self.device_name}.do0", message_logger=self.message_logger)
        return 1

    def do1(self):
        info(f"{self.device_name}.do1", message_logger=self.message_logger)
        return 1

    def read(self, register):
        pass

    def check_device_connection(self) -> bool:
        return modbus_check_device_connection(
            device_name=self.device_name,
            bus=self.bus,
            address=self.address,
            register=6,
            message_logger=self.message_logger,
        )

    # def __del__(self):
    #     # self._message_logger = None
    #     self.stop()
    #     time.sleep(0.1)
    #     self._status_thread.join()
    #     time.sleep(0.1)

    def __del__(self):
        try:
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
