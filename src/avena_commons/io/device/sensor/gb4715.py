import threading
import time

from avena_commons.io.device import modbus_check_device_connection
from avena_commons.util.logger import MessageLogger, debug, error, info


class GB4715:
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
        self.period: float = period
        self.cache_time: float = (
            cache_time  # Store cache_time parameter for cache timeout
        )
        self.message_logger: MessageLogger | None = message_logger
        self.alarm_status: int = 0
        self.__lock: threading.Lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()

        # Add alarm status read cache properties (similar to p7674.py DI cache)
        self.alarm_cache: int | None = None
        self.alarm_cache_time: float = 0
        self.alarm_cache_lock: threading.Lock = threading.Lock()

        self.__setup()
        self.check_device_connection()

    def __setup(self):
        try:
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(target=self._alarm_monitor_thread)
                self._thread.daemon = True
                self._thread.start()
                info(
                    f"{self.device_name} - Alarm monitoring thread started",
                    message_logger=self.message_logger,
                )

        except Exception as e:
            error(
                f"{self.device_name} - Error setting up device: {e}",
                message_logger=self.message_logger,
            )
            return None

    def _alarm_monitor_thread(self):
        while not self._stop_event.is_set():
            now = time.time()
            with self.__lock:
                self.alarm_status = self.read_alarm_status()
            time.sleep(max(0, self.period - (time.time() - now)))

    def read_alarm_status(self):
        """Read alarm status from address 0x003
        Returns:
            0: OK
            1: Alarm
            None: Error reading
        """
        with self.alarm_cache_lock:
            current_time = time.time()
            # Check if cache is valid (similar to p7674.py DI cache implementation)
            if (
                self.alarm_cache is not None
                and (current_time - self.alarm_cache_time) < self.cache_time
            ):
                # Use cached value
                debug(
                    f"{self.device_name} - Using cached alarm status value: {self.alarm_cache}",
                    message_logger=self.message_logger,
                )
                return self.alarm_cache

            # Cache expired or not set, perform actual read
            try:
                result = self.bus.read_holding_registers(
                    address=self.address, first_register=3, count=1
                )
                if result and len(result) == 1:
                    status = result[0]
                    # Update cache
                    self.alarm_cache = status
                    self.alarm_cache_time = current_time
                    debug(
                        f"{self.device_name} - Updated alarm cache with value: {status}",
                        message_logger=self.message_logger,
                    )
                    return status
                else:
                    error(
                        f"{self.device_name} Error reading alarm status",
                        message_logger=self.message_logger,
                    )
                    return None
            except Exception as e:
                error(
                    f"{self.device_name} Error reading alarm status exception: {e}",
                    message_logger=self.message_logger,
                )
                return None

    def set_alarm_delay(self, delay):
        """Set alarm delay at address 0x0033"""
        try:
            with self.__lock:
                result = self.bus.write_holding_register(
                    address=self.address, register=0x0033, value=delay
                )
                return result
        except Exception as e:
            error(
                f"{self.device_name} Failed to set alarm delay: {e}",
                message_logger=self.message_logger,
            )
            return False

    def get_current_alarm_status(self):
        with self.__lock:
            return self.alarm_status

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
                    f"{self.device_name} - Alarm monitoring thread stopped",
                    message_logger=self.message_logger,
                )
        except Exception:
            pass  # nie loguj tutaj!

    def check_device_connection(self) -> bool:
        return modbus_check_device_connection(
            device_name=self.device_name,
            bus=self.bus,
            address=self.address,
            register=3,
            message_logger=self.message_logger,
        )
