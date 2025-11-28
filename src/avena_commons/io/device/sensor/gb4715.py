import threading
import time

from avena_commons.io.device import modbus_check_device_connection
from avena_commons.util.logger import MessageLogger, debug, error, info

from ..physical_device_base import PhysicalDeviceBase


class GB4715(PhysicalDeviceBase):
    """Czujnik alarmowy GB4715 monitorowany wątkiem z cache odczytu alarmu.

    Args:
        device_name (str): Nazwa urządzenia.
        bus: Magistrala Modbus/komunikacyjna.
        address: Adres urządzenia.
        period (float): Okres odczytu alarmu (s).
        cache_time (float): Czas ważności cache odczytu (s).
        max_consecutive_errors (int): Maksymalna liczba kolejnych błędów przed FAULT.
        message_logger (MessageLogger | None): Logger wiadomości.
    """

    def __init__(
        self,
        device_name: str,
        bus,
        address,
        period: float = 0.025,
        cache_time: float = 1,
        max_consecutive_errors: int = 3,
        message_logger: MessageLogger | None = None,
    ):
        super().__init__(
            device_name=device_name,
            max_consecutive_errors=max_consecutive_errors,
            message_logger=message_logger,
        )
        self.bus = bus
        self.address = address
        self.period: float = period
        self.cache_time: float = (
            cache_time  # Store cache_time parameter for cache timeout
        )
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
        """Inicjalizuje i uruchamia wątek monitorujący stan alarmu."""
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
        """Wątek cyklicznie odczytujący i aktualizujący stan alarmu."""
        while not self._stop_event.is_set():
            now = time.time()
            with self.__lock:
                self.alarm_status = self.read_alarm_status()
            time.sleep(max(0, self.period - (time.time() - now)))

    def read_alarm_status(self):
        """Odczytuje stan alarmu z adresu 0x0033

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
        """Ustawia ouznienie alarmu na adresie 0x0033"""
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
        if not self.check_health():
            return False
        return modbus_check_device_connection(
            device_name=self.device_name,
            bus=self.bus,
            address=self.address,
            register=3,
            message_logger=self.message_logger,
        )

    def __str__(self) -> str:
        """
        Zwraca czytelną reprezentację urządzenia GB4715 w formie stringa.
        Używane przy printowaniu urządzenia.

        Returns:
            str: Czytelna reprezentacja urządzenia zawierająca nazwę i stan alarmu
        """
        try:
            # Określenie głównego stanu urządzenia na podstawie alarm_status
            if self.alarm_status == 1:
                main_state = "ALARM"
            elif self.alarm_status == 0:
                main_state = "OK"
            else:
                main_state = "UNKNOWN"

            return f"GB4715(name='{self.device_name}', state={main_state})"

        except Exception as e:
            # Fallback w przypadku błędu - pokazujemy podstawowe informacje
            return f"GB4715(name='{self.device_name}', state=ERROR, error='{str(e)}')"

    def __repr__(self) -> str:
        """
        Zwraca reprezentację urządzenia GB4715 dla developerów.
        Pokazuje więcej szczegółów technicznych.

        Returns:
            str: Szczegółowa reprezentacja urządzenia
        """
        try:
            return (
                f"GB4715(device_name='{self.device_name}', "
                f"address={self.address}, "
                f"period={self.period}, "
                f"alarm_status={self.alarm_status})"
            )
        except Exception as e:
            return f"GB4715(device_name='{self.device_name}', error='{str(e)}')"

    def to_dict(self) -> dict:
        """
        Zwraca słownikową reprezentację urządzenia GB4715.
        Używane do zapisywania stanu urządzenia w strukturach danych.

        Returns:
            dict: Słownik zawierający:
                - name: nazwa urządzenia
                - address: adres Modbus urządzenia
                - period: okres odczytu alarmu
                - alarm_status: aktualny stan alarmu (0=OK, 1=Alarm)
                - main_state: główny stan urządzenia w postaci tekstowej
                - error: informacja o błędzie (jeśli wystąpił)
        """
        result = {
            "name": self.device_name,
            "address": self.address,
            "period": self.period,
        }

        try:
            # Dodanie stanu alarmu
            result["alarm_status"] = self.alarm_status

            # Dodanie głównego stanu urządzenia w postaci tekstowej
            if self.alarm_status == 1:
                result["main_state"] = "ALARM"
            elif self.alarm_status == 0:
                result["main_state"] = "OK"
            else:
                result["main_state"] = "UNKNOWN"

        except Exception as e:
            # W przypadku błędu dodajemy informację o błędzie
            result["main_state"] = "ERROR"
            result["error"] = str(e)

            if self.message_logger:
                error(
                    f"{self.device_name} - Error creating dict representation: {e}",
                    message_logger=self.message_logger,
                )

        return result
