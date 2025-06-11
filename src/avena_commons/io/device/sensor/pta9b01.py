import threading

from avena_commons.io.device import modbus_check_device_connection
from avena_commons.util.control_loop import ControlLoop
from avena_commons.util.logger import MessageLogger, error, info


class PTA9B01:
    def __init__(
        self,
        device_name: str,
        bus,
        address,
        loop_temperature_read_frequency: int = 5,
        message_logger: MessageLogger | None = None,
    ):
        self.bus = bus
        self.device_name = device_name
        self.address = address
        self.message_logger = message_logger
        self.temperature: float = 0.0
        self.__loop_temperature_read_frequency: int = loop_temperature_read_frequency
        self.__new_temperature: float = 0.0
        self._thread = None
        self._stop_event = threading.Event()
        self.__setup()
        self.check_device_connection()

    def __setup(self):
        try:
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(target=self._temperature_thread)
                self._thread.daemon = True
                self._thread.start()
                info(
                    "Temperature monitoring thread started",
                    message_logger=self.message_logger,
                )

        except Exception as e:
            error(f"Error writing to device: {e}", message_logger=self.message_logger)
            return None

    def __read_temperature(self):
        """
        Read temperature from device

        Args:

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # read temperature (address 0x00)
            response1 = self.bus.read_holding_register(register=0, address=self.address)

            # Check if any operation failed
            if not (response1):
                error("Error reading register 0", message_logger=self.message_logger)
                return False

            self.__new_temperature = response1 / 10.0
            # debug(f"Temperature read: {self.__new_temperature}", message_logger=self.message_logger)
            return True

        except Exception as e:
            error(f"Error reading register 0: {e}", message_logger=self.message_logger)
            return False

    def _temperature_thread(self):
        loop = ControlLoop(
            name="temperature_thread",
            period=1 / self.__loop_temperature_read_frequency,
            warning_printer=False,
        )
        while not self._stop_event.is_set():
            loop.loop_begin()
            ok = self.__read_temperature()
            if ok:
                self.temperature = self.__new_temperature
            else:
                error("Error reading temperature", message_logger=self.message_logger)
            loop.loop_end()

    def read_temperature(self):
        return self.temperature

    # def __del__(self):
    #     if self._thread is not None and self._thread.is_alive():
    #         self._stop_event.set()
    #         self._thread.join()
    #         self._thread = None
    #         info("Temperature monitoring thread stopped", message_logger=self.message_logger)

    def __del__(self):
        self.message_logger = None
        try:
            if (
                hasattr(self, "_thread")
                and self._thread is not None
                and self._thread.is_alive()
            ):
                self._stop_event.set()
                self._thread.join()
                self._thread = None
                info(
                    "Temperature monitoring thread stopped",
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
