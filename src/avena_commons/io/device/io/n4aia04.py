import threading
import time
import traceback

from avena_commons.util.logger import MessageLogger, debug, error, info, warning

from ...device import modbus_check_device_connection


class N4AIA04:
    def __init__(
        self,
        device_name: str,
        bus=None,
        address=None,
        offset=0,
        period: float = 0.05,
        message_logger: MessageLogger | None = None,
        debug=True,
    ):
        try:
            self.device_name = device_name
            info(
                f"{self.device_name} - Initializing at address {address}",
                message_logger=message_logger,
            )
            self.bus = bus
            self.address = address
            self.offset = offset  # atrybut do ogarniania roznicy pomiedzy wewnetrzna numeracja p7674 a numerami IO napisanymi na PCB
            self.period: float = period  # Period for analog reading thread
            self.message_logger = message_logger
            self.__debug = debug

            # Raw analog values with thread safety
            self.__lock: threading.Lock = threading.Lock()
            self.raw_values: list = [
                0,
                0,
                0,
                0,
            ]  # Raw values from registers 0x0000-0x0003

            # Analog reading thread properties
            self._analog_thread: threading.Thread | None = None
            self._analog_stop_event: threading.Event = threading.Event()

            self.__setup()
            self.check_device_connection()

        except Exception as e:
            error(
                f"{self.device_name} - Error initializing: {str(e)}",
                message_logger=message_logger,
            )
            error(traceback.format_exc(), message_logger=message_logger)

    def __setup(self):
        """Initialize and start the analog reading thread"""
        try:
            # Start analog reading thread
            if self._analog_thread is None or not self._analog_thread.is_alive():
                self._analog_stop_event.clear()
                self._analog_thread = threading.Thread(
                    target=self._analog_thread_worker
                )
                self._analog_thread.daemon = True
                self._analog_thread.start()
                info(
                    f"{self.device_name} - Analog monitoring thread started",
                    message_logger=self.message_logger,
                )

        except Exception as e:
            error(
                f"{self.device_name} - Error starting analog thread: {e}",
                message_logger=self.message_logger,
            )

    def _analog_thread_worker(self):
        """Background thread that periodically reads raw values from Modbus holding registers"""
        while not self._analog_stop_event.is_set():
            now = time.time()

            try:
                # Read voltage and current registers
                # Register 0x0000: CH1 V1 voltage (scale: 0.01V)
                # Register 0x0001: CH2 V2 voltage (scale: 0.01V)
                # Register 0x0002: CH3 C1 current (scale: 0.1mA)
                # Register 0x0003: CH4 C2 current (scale: 0.1mA)

                # Read all 4 holding registers at once (0x0000-0x0003)
                raw_data = self.bus.read_holding_registers(
                    address=self.address, register=0x0000, count=4
                )

                if raw_data is not None and len(raw_data) == 4:
                    # Update raw values
                    with self.__lock:
                        self.raw_values = raw_data.copy()

                    if self.__debug:
                        # Calculate scaled values for debug display
                        v1 = raw_data[0] * 0.01
                        v2 = raw_data[1] * 0.01
                        c1 = raw_data[2] * 0.1
                        c2 = raw_data[3] * 0.1
                        debug(
                            f"{self.device_name} - Raw values updated: {raw_data} -> V1={v1:.2f}V, V2={v2:.2f}V, C1={c1:.1f}mA, C2={c2:.1f}mA",
                            message_logger=self.message_logger,
                        )
                else:
                    warning(
                        f"{self.device_name} - Unable to read holding registers 0x0000-0x0003",
                        message_logger=self.message_logger,
                    )

            except Exception as e:
                error(
                    f"{self.device_name} - Error reading analog values: {e}",
                    message_logger=self.message_logger,
                )

            time.sleep(max(0, self.period - (time.time() - now)))

    def get_voltage_1(self) -> float:
        """Get CH1 V1 voltage value in Volts"""
        with self.__lock:
            return self.raw_values[0] * 0.01  # Convert raw value to Volts

    def get_voltage_2(self) -> float:
        """Get CH2 V2 voltage value in Volts"""
        with self.__lock:
            return self.raw_values[1] * 0.01  # Convert raw value to Volts

    def get_current_1(self) -> float:
        """Get CH3 C1 current value in mA"""
        with self.__lock:
            return self.raw_values[2] * 0.1  # Convert raw value to mA

    def get_current_2(self) -> float:
        """Get CH4 C2 current value in mA"""
        with self.__lock:
            return self.raw_values[3] * 0.1  # Convert raw value to mA

    def get_all_values(self) -> dict:
        """Get all analog values as a dictionary"""
        with self.__lock:
            return {
                "voltage_1": self.raw_values[0] * 0.01,
                "voltage_2": self.raw_values[1] * 0.01,
                "current_1": self.raw_values[2] * 0.1,
                "current_2": self.raw_values[3] * 0.1,
            }

    def get_raw_values(self) -> list:
        """Get raw values from registers as list [V1_raw, V2_raw, C1_raw, C2_raw]"""
        with self.__lock:
            return self.raw_values.copy()

    def __del__(self):
        """Cleanup when object is destroyed"""
        try:
            # Stop analog reading thread
            if (
                hasattr(self, "_analog_thread")
                and self._analog_thread is not None
                and self._analog_thread.is_alive()
            ):
                self._analog_stop_event.set()
                time.sleep(0.1)
                self._analog_thread.join()
                self._analog_thread = None
                info(
                    f"{self.device_name} - Analog monitoring thread stopped",
                    message_logger=self.message_logger,
                )
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
