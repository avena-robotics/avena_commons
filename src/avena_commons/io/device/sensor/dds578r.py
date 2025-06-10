import struct
import threading
import time

from avena_commons.io.device import modbus_check_device_connection
from avena_commons.util.logger import MessageLogger, error, info


class DDS578R:
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
        """Decode a floating point value from registers using struct library."""
        if not registers or len(registers) < register_index + 2:
            return None

        # Get the two registers and convert to a 32-bit float
        reg_1 = registers[register_index]
        reg_2 = registers[register_index + 1]
        combined = (reg_1 << 16) | reg_2

        # Use struct to unpack the float
        return struct.unpack(">f", struct.pack(">I", combined))[0]

    def _encode_float(self, value):
        """Encode a floating point value to registers using struct library."""
        # Pack the float into a 32-bit value
        packed = struct.pack(">f", float(value))

        # Unpack as 32-bit integer
        combined = struct.unpack(">I", packed)[0]

        # Split into two 16-bit registers
        reg_1 = (combined >> 16) & 0xFFFF
        reg_2 = combined & 0xFFFF

        return [reg_1, reg_2]

    def _monitoring_thread(self):
        """Background thread to continuously monitor electrical parameters."""
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
        """Read the A, B, C phase voltages with caching."""
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
        """Read the A, B, C line currents with caching."""
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
        """Read total and phase active power with caching."""
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
        """Read total and phase reactive power with caching."""
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
        """Read the A, B, C phase power factors with caching."""
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
        """Read the frequency with caching."""
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
        """Read the total active electricity power with caching."""
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
        """Read the total reactive electricity power with caching."""
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
                    f"{self.device_name} - Electrical meter monitoring thread stopped",
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
