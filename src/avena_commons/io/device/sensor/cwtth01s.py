import threading
import time

from avena_commons.io.device import modbus_check_device_connection
from avena_commons.util.logger import MessageLogger, debug, error, info


class CWTTH01S:
    def __init__(
        self,
        device_name: str,
        bus,
        address,
        period: float = 0.025,
        cache_time: float = 1,
        message_logger: MessageLogger | None = None,
    ):
        self.device_name = device_name
        self.bus = bus
        self.address = address
        self.period = period
        self.message_logger = message_logger
        self.humidity = None
        self.temperature = None
        self.__lock = threading.Lock()
        self._thread = None
        self._stop_event = threading.Event()

        # Add caching properties for humidity and temperature reads
        self.humidity_cache = None
        self.humidity_cache_time = 0
        self.temperature_cache = None
        self.temperature_cache_time = 0
        self.cache_timeout = cache_time

        self.__setup()
        self.check_device_connection()

    def __setup(self):
        try:
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(target=self._sensor_thread)
                self._thread.daemon = True
                self._thread.start()
                info(
                    f"{self.device_name} - Sensor monitoring thread started",
                    message_logger=self.message_logger,
                )
        except Exception as e:
            error(
                f"{self.device_name} - Error setting up device: {e}",
                message_logger=self.message_logger,
            )
            return None

    def _sensor_thread(self):
        while not self._stop_event.is_set():
            now = time.time()
            try:
                with self.__lock:
                    self.humidity = self.__read_humidity()
                    self.temperature = self.__read_temperature()
                    debug(
                        f"{self.device_name} - Humidity: {self.humidity}%RH, Temperature: {self.temperature}°C",
                        message_logger=self.message_logger,
                    )
            except Exception as e:
                error(
                    f"{self.device_name} - Error reading sensor: {e}",
                    message_logger=self.message_logger,
                )

            time.sleep(max(0, self.period - (time.time() - now)))

    def __read_humidity(self):
        """Read humidity value from the sensor.

        Returns:
            float: Humidity in %RH or None if failed
        """
        current_time = time.time()
        # Check if cache is valid
        if (
            self.humidity_cache is not None
            and (current_time - self.humidity_cache_time) < self.cache_timeout
        ):
            # Use cached value
            debug(
                f"{self.device_name} - Using cached humidity value: {self.humidity_cache}%RH",
                message_logger=self.message_logger,
            )
            return self.humidity_cache

        # Cache expired or not set, perform actual read
        try:
            result = self.bus.read_holding_registers(
                address=self.address, first_register=0, count=1
            )
            if result and len(result) == 1:
                # Convert the value (0.1%rh resolution)
                humidity_value = result[0] / 10.0

                # Update cache
                self.humidity_cache = humidity_value
                self.humidity_cache_time = current_time
                debug(
                    f"{self.device_name} - Updated humidity cache with value: {humidity_value}%RH",
                    message_logger=self.message_logger,
                )

                return humidity_value
            else:
                error(
                    f"{self.device_name} - Error reading humidity or invalid response format",
                    message_logger=self.message_logger,
                )
                return None
        except Exception as e:
            error(
                f"{self.device_name} - Error reading humidity: {e}",
                message_logger=self.message_logger,
            )
            return None

    def __read_temperature(self):
        """Read temperature value from the sensor.

        Returns:
            float: Temperature in °C or None if failed
        """
        current_time = time.time()
        # Check if cache is valid
        if (
            self.temperature_cache is not None
            and (current_time - self.temperature_cache_time) < self.cache_timeout
        ):
            # Use cached value
            debug(
                f"{self.device_name} - Using cached temperature value: {self.temperature_cache}°C",
                message_logger=self.message_logger,
            )
            return self.temperature_cache

        # Cache expired or not set, perform actual read
        try:
            result = self.bus.read_holding_registers(
                address=self.address, first_register=1, count=1
            )
            if result and len(result) == 1:
                # Get raw register value
                value = result[0]

                # Handle two's complement for negative values
                if value >= 0x8000:  # If the high bit is set (negative number)
                    # Convert from two's complement to negative decimal
                    value = value - 0x10000

                # Convert the value (0.1°C resolution)
                temperature_value = value / 10.0

                # Update cache
                self.temperature_cache = temperature_value
                self.temperature_cache_time = current_time
                debug(
                    f"{self.device_name} - Updated temperature cache with value: {temperature_value}°C",
                    message_logger=self.message_logger,
                )

                return temperature_value
            else:
                error(
                    f"{self.device_name} - Error reading temperature or invalid response format",
                    message_logger=self.message_logger,
                )
                return None
        except Exception as e:
            error(
                f"{self.device_name} - Error reading temperature: {e}",
                message_logger=self.message_logger,
            )
            return None

    def read_humidity(self):
        """Get the current humidity value.

        Returns:
            float: Humidity in %RH or None if not available
        """
        with self.__lock:
            return self.humidity

    def read_temperature(self):
        """Get the current temperature value.

        Returns:
            float: Temperature in °C or None if not available
        """
        with self.__lock:
            return self.temperature

    def read_temp_calibration(self):
        """Read temperature calibration value

        Returns:
            float: Temperature calibration value in °C or None if failed
        """
        try:
            with self.__lock:
                result = self.bus.read_holding_registers(
                    address=self.address, first_register=0x0050, count=1
                )
                if result and len(result) == 1:
                    # Convert the value (0.1°C resolution)
                    return result[0] / 10.0
                else:
                    error(
                        f"{self.device_name} - Error reading temperature calibration or invalid response format",
                        message_logger=self.message_logger,
                    )
                    return None
        except Exception as e:
            error(
                f"{self.device_name} - Error reading temperature calibration: {e}",
                message_logger=self.message_logger,
            )
            return None

    def read_humid_calibration(self):
        """Read humidity calibration value

        Returns:
            float: Humidity calibration value in %RH or None if failed
        """
        try:
            with self.__lock:
                result = self.bus.read_holding_registers(
                    address=self.address, first_register=0x0051, count=1
                )
                if result and len(result) == 1:
                    # Convert the value (0.1%rh resolution)
                    return result[0] / 10.0
                else:
                    error(
                        f"{self.device_name} - Error reading humidity calibration or invalid response format",
                        message_logger=self.message_logger,
                    )
                    return None
        except Exception as e:
            error(
                f"{self.device_name} - Error reading humidity calibration: {e}",
                message_logger=self.message_logger,
            )
            return None

    def write_temp_calibration(self, cal_value):
        """Write temperature calibration value

        Args:
            cal_value (float): Temperature calibration value in °C

        Returns:
            bool: True if successful, False otherwise
        """
        # Convert to register value (0.1°C resolution)
        register_value = int(cal_value * 10)

        try:
            with self.__lock:
                result = self.bus.write_holding_register(
                    address=self.address, register=0x0050, value=register_value
                )
                if result:
                    info(
                        f"{self.device_name} - Temperature calibration updated to {cal_value}°C",
                        message_logger=self.message_logger,
                    )
                    return True
                else:
                    error(
                        f"{self.device_name} - Failed to update temperature calibration",
                        message_logger=self.message_logger,
                    )
                    return False
        except Exception as e:
            error(
                f"{self.device_name} - Error writing temperature calibration: {e}",
                message_logger=self.message_logger,
            )
            return False

    def write_humid_calibration(self, cal_value):
        """Write humidity calibration value

        Args:
            cal_value (float): Humidity calibration value in %RH

        Returns:
            bool: True if successful, False otherwise
        """
        # Convert to register value (0.1%rh resolution)
        register_value = int(cal_value * 10)

        try:
            with self.__lock:
                result = self.bus.write_holding_register(
                    address=self.address, register=0x0051, value=register_value
                )
                if result:
                    info(
                        f"{self.device_name} - Humidity calibration updated to {cal_value}%RH",
                        message_logger=self.message_logger,
                    )
                    return True
                else:
                    error(
                        f"{self.device_name} - Failed to update humidity calibration",
                        message_logger=self.message_logger,
                    )
                    return False
        except Exception as e:
            error(
                f"{self.device_name} - Error writing humidity calibration: {e}",
                message_logger=self.message_logger,
            )
            return False

    def __del__(self):
        self.message_logger = None
        try:
            if (
                hasattr(self, "_thread")
                and self._thread is not None
                and self._thread.is_alive()
            ):
                self._stop_event.set()
                time.sleep(0.1)
                self._thread.join()
                self._thread = None
                info(
                    f"{self.device_name} - Sensor monitoring thread stopped",
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
