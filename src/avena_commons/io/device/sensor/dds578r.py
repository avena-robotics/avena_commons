import struct
import threading
import time

from avena_commons.io.device import modbus_check_device_connection
from avena_commons.util.logger import MessageLogger, error, info


class DDS578R:
    """Licznik parametrów elektrycznych z mechanizmem cache i wątkiem monitorującym.

    Urządzenie cyklicznie odczytuje podstawowe parametry elektryczne (napięcia fazowe,
    prądy liniowe, moce czynne/bierne, współczynniki mocy, częstotliwość oraz sumaryczne
    energie) z magistrali i udostępnia je w bezpieczny wątkowo sposób. Publiczne metody
    posiadają krótki cache ograniczający koszt odczytów.

    Argumenty:
        device_name (str): Nazwa urządzenia.
        bus: Magistrala Modbus/komunikacyjna.
        address (int): Adres slave (1-247).
        period (float): Okres odczytu w sekundach.
        cache_time (float): Czas ważności cache w sekundach.
        message_logger (MessageLogger | None): Logger wiadomości.
    """

    def __init__(
        self,
        device_name: str,
        bus,
        address,
        period: float = 0.1,
        cache_time: float = 1,
        message_logger: MessageLogger | None = None,
    ):
        """Initialize the electrical meter client.

        Args:
            device_name (str): Name of the device
            bus: Modbus bus interface
            address (int): Slave ID (1-247)
            period (float): Polling period in seconds
            message_logger: Logger instance
        """
        self.device_name = device_name
        self.bus = bus
        self.address = address
        self.period = period
        self.message_logger = message_logger

        # Electrical parameters
        self.phase_voltages = {"A": 0.0, "B": 0.0, "C": 0.0}
        self.line_currents = {"A": 0.0, "B": 0.0, "C": 0.0}
        self.active_power = {"total": 0.0, "A": 0.0, "B": 0.0, "C": 0.0}
        self.reactive_power = {"total": 0.0, "A": 0.0, "B": 0.0, "C": 0.0}
        self.power_factors = {"A": 0.0, "B": 0.0, "C": 0.0}
        self.frequency = 0.0
        self.total_active_electricity = 0.0
        self.total_reactive_electricity = 0.0

        # Cache properties for read functions - similar to p7674.py DI cache mechanism
        self.cache_timeout = cache_time
        self.cache_lock = threading.Lock()

        # Individual caches for each parameter type
        self.phase_voltages_cache = None
        self.phase_voltages_cache_time = 0

        self.line_currents_cache = None
        self.line_currents_cache_time = 0

        self.active_power_cache = None
        self.active_power_cache_time = 0

        self.reactive_power_cache = None
        self.reactive_power_cache_time = 0

        self.power_factors_cache = None
        self.power_factors_cache_time = 0

        self.frequency_cache = None
        self.frequency_cache_time = 0

        self.total_active_electricity_cache = None
        self.total_active_electricity_cache_time = 0

        self.total_reactive_electricity_cache = None
        self.total_reactive_electricity_cache_time = 0

        # Thread control
        self.__lock = threading.Lock()
        self._thread = None
        self._stop_event = threading.Event()

        # Start monitoring thread
        self.__setup()
        self.check_device_connection()

    def __setup(self):
        """Inicjalizuje i uruchamia wątek monitorujący parametry elektryczne."""
        try:
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(target=self._monitoring_thread)
                self._thread.daemon = True
                self._thread.start()
                info(
                    f"{self.device_name} Electrical meter monitoring thread started",
                    message_logger=self.message_logger,
                )
        except Exception as e:
            error(
                f"{self.device_name} Error setting up device: {e}",
                message_logger=self.message_logger,
            )

    def _decode_float(self, registers, register_index=0):
        """Dekoduje wartość typu float z pary 16‑bitowych rejestrów.

        Argumenty:
            registers (list[int]): Lista rejestrów wejściowych.
            register_index (int): Indeks pierwszego rejestru z pary.

        Zwraca:
            float | None: Zdekodowana wartość lub None, gdy wejście niekompletne.
        """
        if not registers or len(registers) < register_index + 2:
            return None

        # Get the two registers and convert to a 32-bit float
        reg_1 = registers[register_index]
        reg_2 = registers[register_index + 1]
        combined = (reg_1 << 16) | reg_2

        # Use struct to unpack the float
        return struct.unpack(">f", struct.pack(">I", combined))[0]

    def _encode_float(self, value):
        """Koduje wartość typu float do dwóch 16‑bitowych rejestrów.

        Argumenty:
            value (float): Wartość do zakodowania.

        Zwraca:
            list[int]: Dwa rejestry reprezentujące wartość w formacie big‑endian.
        """
        # Pack the float into a 32-bit value
        packed = struct.pack(">f", float(value))

        # Unpack as 32-bit integer
        combined = struct.unpack(">I", packed)[0]

        # Split into two 16-bit registers
        reg_1 = (combined >> 16) & 0xFFFF
        reg_2 = combined & 0xFFFF

        return [reg_1, reg_2]

    def _monitoring_thread(self):
        """Wątek cyklicznie odczytujący parametry elektryczne z urządzenia."""
        while not self._stop_event.is_set():
            now = time.time()

            try:
                # Read phase voltages
                response = self.bus.read_input_registers(
                    address=self.address, first_register=0x0000, count=6
                )
                if response and len(response) >= 6:
                    with self.__lock:
                        self.phase_voltages["A"] = self._decode_float(response, 0)
                        self.phase_voltages["B"] = self._decode_float(response, 2)
                        self.phase_voltages["C"] = self._decode_float(response, 4)

                # Read line currents
                response = self.bus.read_input_registers(
                    address=self.address, first_register=0x0008, count=6
                )
                if response and len(response) >= 6:
                    with self.__lock:
                        self.line_currents["A"] = self._decode_float(response, 0)
                        self.line_currents["B"] = self._decode_float(response, 2)
                        self.line_currents["C"] = self._decode_float(response, 4)

                # Read active power
                response = self.bus.read_input_registers(
                    address=self.address, first_register=0x0010, count=8
                )
                if response and len(response) >= 8:
                    with self.__lock:
                        self.active_power["total"] = self._decode_float(response, 0)
                        self.active_power["A"] = self._decode_float(response, 2)
                        self.active_power["B"] = self._decode_float(response, 4)
                        self.active_power["C"] = self._decode_float(response, 6)

                # Read reactive power
                response = self.bus.read_input_registers(
                    address=self.address, first_register=0x0018, count=8
                )
                if response and len(response) >= 8:
                    with self.__lock:
                        self.reactive_power["total"] = self._decode_float(response, 0)
                        self.reactive_power["A"] = self._decode_float(response, 2)
                        self.reactive_power["B"] = self._decode_float(response, 4)
                        self.reactive_power["C"] = self._decode_float(response, 6)

                # Read power factors
                response = self.bus.read_input_registers(
                    address=self.address, first_register=0x002A, count=6
                )
                if response and len(response) >= 6:
                    with self.__lock:
                        self.power_factors["A"] = self._decode_float(response, 0)
                        self.power_factors["B"] = self._decode_float(response, 2)
                        self.power_factors["C"] = self._decode_float(response, 4)

                # Read frequency
                response = self.bus.read_input_registers(
                    address=self.address, first_register=0x0036, count=2
                )
                if response and len(response) >= 2:
                    with self.__lock:
                        self.frequency = self._decode_float(response, 0)

                # Read total active electricity
                response = self.bus.read_input_registers(
                    address=self.address, first_register=0x0100, count=2
                )
                if response and len(response) >= 2:
                    with self.__lock:
                        self.total_active_electricity = self._decode_float(response, 0)

                # Read total reactive electricity
                response = self.bus.read_input_registers(
                    address=self.address, first_register=0x0400, count=2
                )
                if response and len(response) >= 2:
                    with self.__lock:
                        self.total_reactive_electricity = self._decode_float(
                            response, 0
                        )

            except Exception as e:
                error(
                    f"{self.device_name} Error reading electrical parameters: {e}",
                    message_logger=self.message_logger,
                )

            # Sleep for the remainder of the period
            time.sleep(max(0, self.period - (time.time() - now)))

    # Public methods to read electrical parameters with caching mechanism similar to p7674.py

    def read_phase_voltages(self):
        """Zwraca napięcia fazowe A, B, C z mechanizmem cache."""
        with self.cache_lock:
            current_time = time.time()
            # Check if cache is valid
            if (
                self.phase_voltages_cache is not None
                and (current_time - self.phase_voltages_cache_time) < self.cache_timeout
            ):
                # Use cached value
                return self.phase_voltages_cache

            # Cache expired or not set, get current value from monitoring thread
            with self.__lock:
                fresh_value = self.phase_voltages.copy()

            # Update cache
            self.phase_voltages_cache = fresh_value
            self.phase_voltages_cache_time = current_time
            return fresh_value

    def read_line_currents(self):
        """Zwraca prądy liniowe A, B, C z mechanizmem cache."""
        with self.cache_lock:
            current_time = time.time()
            # Check if cache is valid
            if (
                self.line_currents_cache is not None
                and (current_time - self.line_currents_cache_time) < self.cache_timeout
            ):
                # Use cached value
                return self.line_currents_cache

            # Cache expired or not set, get current value from monitoring thread
            with self.__lock:
                fresh_value = self.line_currents.copy()

            # Update cache
            self.line_currents_cache = fresh_value
            self.line_currents_cache_time = current_time
            return fresh_value

    def read_active_power(self):
        """Zwraca moc czynną (całkowitą i na fazach) z mechanizmem cache."""
        with self.cache_lock:
            current_time = time.time()
            # Check if cache is valid
            if (
                self.active_power_cache is not None
                and (current_time - self.active_power_cache_time) < self.cache_timeout
            ):
                # Use cached value
                return self.active_power_cache

            # Cache expired or not set, get current value from monitoring thread
            with self.__lock:
                fresh_value = self.active_power.copy()

            # Update cache
            self.active_power_cache = fresh_value
            self.active_power_cache_time = current_time
            return fresh_value

    def read_reactive_power(self):
        """Zwraca moc bierną (całkowitą i na fazach) z mechanizmem cache."""
        with self.cache_lock:
            current_time = time.time()
            # Check if cache is valid
            if (
                self.reactive_power_cache is not None
                and (current_time - self.reactive_power_cache_time) < self.cache_timeout
            ):
                # Use cached value
                return self.reactive_power_cache

            # Cache expired or not set, get current value from monitoring thread
            with self.__lock:
                fresh_value = self.reactive_power.copy()

            # Update cache
            self.reactive_power_cache = fresh_value
            self.reactive_power_cache_time = current_time
            return fresh_value

    def read_power_factors(self):
        """Zwraca współczynniki mocy faz A, B, C z mechanizmem cache."""
        with self.cache_lock:
            current_time = time.time()
            # Check if cache is valid
            if (
                self.power_factors_cache is not None
                and (current_time - self.power_factors_cache_time) < self.cache_timeout
            ):
                # Use cached value
                return self.power_factors_cache

            # Cache expired or not set, get current value from monitoring thread
            with self.__lock:
                fresh_value = self.power_factors.copy()

            # Update cache
            self.power_factors_cache = fresh_value
            self.power_factors_cache_time = current_time
            return fresh_value

    def read_frequency(self):
        """Zwraca częstotliwość z mechanizmem cache."""
        with self.cache_lock:
            current_time = time.time()
            # Check if cache is valid
            if (
                self.frequency_cache is not None
                and (current_time - self.frequency_cache_time) < self.cache_timeout
            ):
                # Use cached value
                return self.frequency_cache

            # Cache expired or not set, get current value from monitoring thread
            with self.__lock:
                fresh_value = self.frequency

            # Update cache
            self.frequency_cache = fresh_value
            self.frequency_cache_time = current_time
            return fresh_value

    def read_total_active_electricity(self):
        """Zwraca całkowitą energię czynną z mechanizmem cache."""
        with self.cache_lock:
            current_time = time.time()
            # Check if cache is valid
            if (
                self.total_active_electricity_cache is not None
                and (current_time - self.total_active_electricity_cache_time)
                < self.cache_timeout
            ):
                # Use cached value
                return self.total_active_electricity_cache

            # Cache expired or not set, get current value from monitoring thread
            with self.__lock:
                fresh_value = self.total_active_electricity

            # Update cache
            self.total_active_electricity_cache = fresh_value
            self.total_active_electricity_cache_time = current_time
            return fresh_value

    def read_total_reactive_electricity(self):
        """Zwraca całkowitą energię bierną z mechanizmem cache."""
        with self.cache_lock:
            current_time = time.time()
            # Check if cache is valid
            if (
                self.total_reactive_electricity_cache is not None
                and (current_time - self.total_reactive_electricity_cache_time)
                < self.cache_timeout
            ):
                # Use cached value
                return self.total_reactive_electricity_cache

            # Cache expired or not set, get current value from monitoring thread
            with self.__lock:
                fresh_value = self.total_reactive_electricity

            # Update cache
            self.total_reactive_electricity_cache = fresh_value
            self.total_reactive_electricity_cache_time = current_time
            return fresh_value

    def check_device_connection(self) -> bool:
        """Sprawdza połączenie z urządzeniem poprzez odczyt rejestru kontrolnego.

        Zwraca:
            bool: True jeśli urządzenie odpowiada, w przeciwnym razie False.
        """
        return modbus_check_device_connection(
            device_name=self.device_name,
            bus=self.bus,
            address=self.address,
            register=0,
            message_logger=self.message_logger,
        )

    def __str__(self) -> str:
        """Zwraca czytelną reprezentację urządzenia w formie tekstu do debugowania.

        Zwraca:
            str: Nazwa i podstawowe parametry (napięcia, prądy, moce, częstotliwość).
        """
        try:
            # Pobieranie aktualnych wartości z zabezpieczeniem przed błędami
            with self.__lock:
                voltages = self.phase_voltages.copy()
                currents = self.line_currents.copy()
                freq = self.frequency
                active_total = self.active_power.get("total", 0.0)
                reactive_total = self.reactive_power.get("total", 0.0)

            # Formatowanie napięć fazowych
            voltage_str = f"V_A:{voltages['A']:.1f}V, V_B:{voltages['B']:.1f}V, V_C:{voltages['C']:.1f}V"

            # Formatowanie prądów liniowych
            current_str = f"I_A:{currents['A']:.2f}A, I_B:{currents['B']:.2f}A, I_C:{currents['C']:.2f}A"

            # Formatowanie mocy
            power_str = f"P:{active_total:.1f}W, Q:{reactive_total:.1f}VAR"

            return f"DDS578R(name='{self.device_name}', freq={freq:.1f}Hz, {voltage_str}, {current_str}, {power_str})"

        except Exception as e:
            # Fallback w przypadku błędu - pokazujemy podstawowe informacje
            return f"DDS578R(name='{self.device_name}', state=ERROR, error='{str(e)}')"

    def __repr__(self) -> str:
        """Zwraca szczegółową reprezentację obiektu dla programistów.

        Zwraca:
            str: Reprezentacja z technicznymi polami wewnętrznymi.
        """
        try:
            with self.__lock:
                return (
                    f"DDS578R(device_name='{self.device_name}', "
                    f"address={self.address}, "
                    f"period={self.period}, "
                    f"phase_voltages={self.phase_voltages}, "
                    f"line_currents={self.line_currents}, "
                    f"active_power={self.active_power}, "
                    f"reactive_power={self.reactive_power}, "
                    f"power_factors={self.power_factors}, "
                    f"frequency={self.frequency}, "
                    f"total_active_electricity={self.total_active_electricity}, "
                    f"total_reactive_electricity={self.total_reactive_electricity})"
                )
        except Exception as e:
            return f"DDS578R(device_name='{self.device_name}', error='{str(e)}')"

    def to_dict(self) -> dict:
        """Zwraca słownikową reprezentację bieżącego stanu urządzenia.

        Zwraca:
            dict: Dane adresowe/okres oraz bieżące parametry i podsumowanie.
        """
        result = {
            "name": self.device_name,
            "address": self.address,
            "period": self.period,
        }

        try:
            # Dodanie wszystkich parametrów elektrycznych
            with self.__lock:
                result["phase_voltages"] = self.phase_voltages.copy()
                result["line_currents"] = self.line_currents.copy()
                result["active_power"] = self.active_power.copy()
                result["reactive_power"] = self.reactive_power.copy()
                result["power_factors"] = self.power_factors.copy()
                result["frequency"] = self.frequency
                result["total_active_electricity"] = self.total_active_electricity
                result["total_reactive_electricity"] = self.total_reactive_electricity

            # Dodanie podsumowania stanu
            result["summary"] = {
                "voltage_avg": sum(result["phase_voltages"].values()) / 3,
                "current_avg": sum(result["line_currents"].values()) / 3,
                "active_power_total": result["active_power"]["total"],
                "reactive_power_total": result["reactive_power"]["total"],
                "power_factor_avg": sum(result["power_factors"].values()) / 3,
                "frequency": result["frequency"],
                "status": "OK",
            }

        except Exception as e:
            # W przypadku błędu dodajemy informację o błędzie
            result["summary"] = {"status": "ERROR", "error_message": str(e)}
            result["error"] = str(e)

            if self.message_logger:
                error(
                    f"{self.device_name} - Error creating dict representation: {e}",
                    message_logger=self.message_logger,
                )

        return result

    def __del__(self):
        """Zatrzymuje wątek monitorujący i czyści referencje loggera przy usuwaniu."""
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
                    f"{self.device_name} - Electrical meter monitoring thread stopped",
                    message_logger=self.message_logger,
                )
        except Exception:
            pass  # nie loguj tutaj!
