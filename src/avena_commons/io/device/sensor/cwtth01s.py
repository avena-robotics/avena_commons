import threading
import time

from avena_commons.io.device import modbus_check_device_connection
from avena_commons.util.logger import MessageLogger, debug, error, info

from ..physical_device_base import PhysicalDeviceBase, PhysicalDeviceState


class CWTTH01S(PhysicalDeviceBase):
    """Czujnik temperatury i wilgotności z buforowaniem odczytów i wątkiem monitorującym.

    Args:
        device_name (str): Nazwa urządzenia.
        bus: Magistrala Modbus/komunikacyjna.
        address: Adres urządzenia.
        period (float): Okres odczytu danych (s).
        cache_time (float): Czas ważności cache (s).
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
        self.period = period
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
        """Inicjalizuje i uruchamia wątek cyklicznych odczytów."""
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
        """Wątek cyklicznie odczytujący i aktualizujący temperaturę oraz wilgotność."""
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
        """Odczytuje wilgotność z sensora.

        Zwraca:
            float: Wilgotność w %RH lub None w przypadku niepowodzenia.
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
        """Odczytuje temperaturę z sensora.

        Zwraca:
            float: Temperatura w °C lub None w przypadku niepowodzenia.
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
        """Zwraca bieżącą wartość wilgotności.

        Zwraca:
            float: Wilgotność w %RH lub None, jeśli niedostępna.
        """
        with self.__lock:
            return self.humidity

    def read_temperature(self):
        """Zwraca bieżącą wartość temperatury.

        Zwraca:
            float: Temperatura w °C lub None, jeśli niedostępna.
        """
        with self.__lock:
            return self.temperature

    def read_temp_calibration(self):
        """Odczytuje wartość kalibracji temperatury.

        Zwraca:
            float: Wartość kalibracji temperatury w °C lub None w przypadku błędu.
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
        """Odczytuje wartość kalibracji wilgotności.

        Zwraca:
            float: Wartość kalibracji wilgotności w %RH lub None w przypadku błędu.
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
        """Zapisuje wartość kalibracji temperatury.

        Argumenty:
            cal_value (float): Wartość kalibracji temperatury w °C.

        Zwraca:
            bool: True w przypadku powodzenia, False w przeciwnym razie.
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
        """Zapisuje wartość kalibracji wilgotności.

        Argumenty:
            cal_value (float): Wartość kalibracji wilgotności w %RH.

        Zwraca:
            bool: True w przypadku powodzenia, False w przeciwnym razie.
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

    def __str__(self) -> str:
        """
        Zwraca czytelną reprezentację sensora CWTTH01S w formie stringa.
        Używane przy printowaniu urządzenia.

        Returns:
            str: Czytelna reprezentacja sensora zawierająca nazwę, temperaturę i wilgotność
        """
        try:
            # Formatowanie wartości temperatury i wilgotności
            temp_str = (
                f"{self.temperature:.1f}°C" if self.temperature is not None else "N/A"
            )
            hum_str = f"{self.humidity:.1f}%RH" if self.humidity is not None else "N/A"

            # Określenie głównego stanu sensora
            if self.temperature is None and self.humidity is None:
                main_state = "NO_DATA"
            elif self.temperature is None or self.humidity is None:
                main_state = "PARTIAL_DATA"
            else:
                main_state = "ACTIVE"

            return f"CWTTH01S(name='{self.device_name}', state={main_state}, temp={temp_str}, humidity={hum_str})"

        except Exception as e:
            # Fallback w przypadku błędu - pokazujemy podstawowe informacje
            return f"CWTTH01S(name='{self.device_name}', state=ERROR, error='{str(e)}')"

    def __repr__(self) -> str:
        """
        Zwraca reprezentację sensora CWTTH01S dla developerów.
        Pokazuje więcej szczegółów technicznych.

        Returns:
            str: Szczegółowa reprezentacja sensora
        """
        try:
            return (
                f"CWTTH01S(device_name='{self.device_name}', "
                f"address={self.address}, "
                f"period={self.period}, "
                f"temperature={self.temperature}, "
                f"humidity={self.humidity})"
            )
        except Exception as e:
            return f"CWTTH01S(device_name='{self.device_name}', error='{str(e)}')"

    def to_dict(self) -> dict:
        """
        Zwraca słownikową reprezentację sensora CWTTH01S.
        Używane do zapisywania stanu sensora w strukturach danych.

        Returns:
            dict: Słownik zawierający:
                - name: nazwa urządzenia
                - address: adres Modbus urządzenia
                - period: okres odczytu
                - temperature: aktualna temperatura
                - humidity: aktualna wilgotność
                - main_state: główny stan sensora
                - error: informacja o błędzie (jeśli wystąpił)
        """
        result = {
            "name": self.device_name,
            "address": self.address,
            "period": self.period,
        }

        try:
            # Dodanie wartości pomiarowych
            result["temperature"] = self.temperature
            result["humidity"] = self.humidity

            # Określenie głównego stanu sensora
            if self.temperature is None and self.humidity is None:
                result["main_state"] = "NO_DATA"
            elif self.temperature is None or self.humidity is None:
                result["main_state"] = "PARTIAL_DATA"
            else:
                result["main_state"] = "ACTIVE"

            # Dodanie informacji o jakości danych
            result["data_quality"] = {
                "temperature_available": self.temperature is not None,
                "humidity_available": self.humidity is not None,
            }

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

    def __del__(self):
        """Zatrzymuje wątek sensora i czyści referencje loggera przy usuwaniu obiektu."""
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
                # Nie logujemy tutaj ponieważ message_logger jest już None
        except Exception:
            pass  # nie loguj tutaj!

    def check_device_connection(self) -> bool:
        """Sprawdza połączenie z urządzeniem poprzez odczyt rejestru kontrolnego.

        Zwraca:
            bool: True jeśli urządzenie odpowiada, w przeciwnym razie False.
        """
        if not self.check_health():
            return False
        return modbus_check_device_connection(
            device_name=self.device_name,
            bus=self.bus,
            address=self.address,
            register=0,
            message_logger=self.message_logger,
        )
