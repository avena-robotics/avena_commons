import threading
import time
import traceback

from avena_commons.util.logger import MessageLogger, debug, error, info


class MA01:
    def __init__(
        self,
        device_name: str,
        bus,
        address,
        message_logger: MessageLogger | None = None,
        debug=True,
    ):
        try:
            self.device_name = device_name
            info(
                f"Initializing MA01 at address {address}", message_logger=message_logger
            )
            self.bus = bus
            self.address = address
            self.message_logger = message_logger

            self.__debug = debug
            self.coil_buffer = [0, 0]  # Only 2 coils
            self.last_write_time = 0
            self.buffer_timeout = 0.1  # 0.1 seconds timeout
            self.buffer_lock = threading.Lock()
            self.buffer_modified = False
            self.buffer_timer = None
            self.new_buffer_cycle = (
                True  # Flag to track if we're starting a new buffer cycle
            )

            # Add DI read buffering properties
            self.di_cache = 0
            self.di_cache_time = 0
            self.di_cache_timeout = 0.05  # 50ms timeout for DI reads
            self.di_lock = threading.Lock()

            self.__setup()
        except Exception as e:
            error(f"Error initializing MA01: {str(e)}", message_logger=message_logger)
            error(traceback.format_exc(), message_logger=message_logger)

    def __setup(self):
        self.__reset_all_coils()
        self.coil_buffer = [0, 0]  # Only 2 coils
        self.last_write_time = time.time()
        self.buffer_modified = False
        self.new_buffer_cycle = True

    def __read_di(self):
        with self.di_lock:
            current_time = time.time()
            # Check if cache is valid
            if (
                self.di_cache is not None
                and (current_time - self.di_cache_time) < self.di_cache_timeout
            ):
                # Use cached value
                return self.di_cache

            # Cache expired or not set, perform actual read
            response = self.bus.read_discrete_inputs(address=self.address, register=0)
            if self.__debug:
                debug(
                    f"{self.device_name} - Updated DI cache with value: {bin(response)}",
                    message_logger=self.message_logger,
                )
            if not response:
                return 0

            # Update cache
            self.di_cache = response
            self.di_cache_time = current_time
            return response

    def __write_do(self, values: list):
        try:
            self.bus.write_coils(address=self.address, register=0, values=values)
            self.last_write_time = time.time()
            self.buffer_modified = False
            if self.__debug:
                debug(f"DO write successful", message_logger=self.message_logger)
        except Exception as e:
            error(f"Error writing DO: {str(e)}", message_logger=self.message_logger)
            raise

    def __reset_all_coils(self):
        """Reset all coils to OFF (0)"""
        try:
            self.bus.write_coils(address=self.address, register=0, values=[0, 0])
            self.coil_buffer = [0, 0]
            self.last_write_time = time.time()
            self.buffer_modified = False
            if self.__debug:
                debug(
                    f"All coils reset successfully", message_logger=self.message_logger
                )
        except Exception as e:
            error(
                f"Error resetting coils: {str(e)}", message_logger=self.message_logger
            )
            raise

    def __buffer_write(self, index: int, value: bool):
        if self.__debug:
            debug(
                f"Buffer write: index={index}, value={value}",
                message_logger=self.message_logger,
            )
        with self.buffer_lock:
            current_time = time.time()
            time_since_last_write = current_time - self.last_write_time

            # Check if we're starting a new buffer cycle (more than buffer_timeout since last write)
            if time_since_last_write > self.buffer_timeout:
                if self.new_buffer_cycle:
                    # If starting a new buffer cycle, reset all coils first
                    if self.__debug:
                        debug(
                            f"Starting new buffer cycle",
                            message_logger=self.message_logger,
                        )
                    # MARK: If you want to disable the already on coils automatically, uncomment the following line. If you want to disable them manually, comment it.
                    # self.coil_buffer = [0, 0]
                    self.new_buffer_cycle = False

                # Start a new timer for buffer timeout
                if self.buffer_timer:
                    if self.__debug:
                        debug(
                            f"Cancelling existing buffer timer",
                            message_logger=self.message_logger,
                        )
                    self.buffer_timer.cancel()

                # Set the current coil and mark buffer as modified
                self.coil_buffer[index] = 1 if value else 0
                self.buffer_modified = True

                # Start a timer to send the buffered command after buffer_timeout
                if self.__debug:
                    debug(
                        f"Starting new buffer timer with timeout {self.buffer_timeout}s",
                        message_logger=self.message_logger,
                    )
                self.buffer_timer = threading.Timer(
                    self.buffer_timeout, self.__flush_timer_callback
                )
                self.buffer_timer.daemon = True
                self.buffer_timer.start()

            else:
                # We're within an active buffer cycle, just add to existing buffer
                if self.__debug:
                    debug(
                        f"Adding to existing buffer cycle",
                        message_logger=self.message_logger,
                    )
                self.coil_buffer[index] = 1 if value else 0
                self.buffer_modified = True

                # If no timer is running, start one for the remaining time
                if not self.buffer_timer:
                    remaining_time = self.buffer_timeout - time_since_last_write
                    if self.__debug:
                        debug(
                            f"Starting new buffer timer with remaining time {remaining_time:.4f}s",
                            message_logger=self.message_logger,
                        )
                    self.buffer_timer = threading.Timer(
                        remaining_time, self.__flush_timer_callback
                    )
                    self.buffer_timer.daemon = True
                    self.buffer_timer.start()

    def __flush_timer_callback(self):
        """Callback for the timer to flush the buffer"""
        if self.__debug:
            debug(f"Flush timer callback triggered", message_logger=self.message_logger)
        with self.buffer_lock:
            if self.buffer_modified:
                if self.__debug:
                    debug(
                        f"Flushing modified buffer: {self.coil_buffer}",
                        message_logger=self.message_logger,
                    )
                self.__write_do(self.coil_buffer.copy())
            else:
                if self.__debug:
                    debug(
                        f"Buffer not modified, skipping flush",
                        message_logger=self.message_logger,
                    )
            self.buffer_timer = None
            self.new_buffer_cycle = (
                True  # Mark that the next command will start a new cycle
            )

    def flush_buffer(self):
        """Force write any pending values in the buffer"""
        if self.__debug:
            debug(f"Manual flush buffer requested", message_logger=self.message_logger)
        with self.buffer_lock:
            if self.buffer_modified:
                if self.__debug:
                    debug(
                        f"Flushing modified buffer: {self.coil_buffer}",
                        message_logger=self.message_logger,
                    )
                self.__write_do(self.coil_buffer.copy())
                if self.buffer_timer:
                    if self.__debug:
                        debug(
                            f"Cancelling buffer timer during manual flush",
                            message_logger=self.message_logger,
                        )
                    self.buffer_timer.cancel()
                    self.buffer_timer = None
                self.new_buffer_cycle = (
                    True  # Mark that the next command will start a new cycle
                )
                if self.__debug:
                    debug(f"Manual flush completed", message_logger=self.message_logger)
            else:
                if self.__debug:
                    debug(
                        f"Buffer not modified, skipping manual flush",
                        message_logger=self.message_logger,
                    )

    def di(self, index: int):
        result = 1 if (self.__read_di() & (1 << index)) else 0
        return result

    def do0(self, value: bool):
        if self.__debug:
            debug(
                f"{self.__class__.__name__} Setting DO0 to {value}",
                message_logger=self.message_logger,
            )
        self.__buffer_write(0, value)
        return value

    def do1(self, value: bool):
        if self.__debug:
            debug(
                f"{self.__class__.__name__} Setting DO1 to {value}",
                message_logger=self.message_logger,
            )
        self.__buffer_write(1, value)
        return value

    def __str__(self) -> str:
        """
        Zwraca czytelną reprezentację urządzenia MA01 w formie stringa.
        Używane przy printowaniu urządzenia.

        Returns:
            str: Czytelna reprezentacja urządzenia zawierająca nazwę, stan cewek i wejść cyfrowych
        """
        try:
            # Określenie głównego stanu urządzenia
            if self.buffer_modified:
                main_state = "BUFFER_MODIFIED"
            elif any(self.coil_buffer):
                main_state = "COILS_ACTIVE"
            else:
                main_state = "IDLE"

            # Formatowanie stanu cewek
            coil_states = [f"DO{i}={self.coil_buffer[i]}" for i in range(len(self.coil_buffer))]
            coil_info = ", ".join(coil_states)

            # Formatowanie stanu wejść cyfrowych
            di_info = f"DI={bin(self.di_cache)}"

            # Informacja o stanie bufora
            buffer_info = f", buffer_cycle={'new' if self.new_buffer_cycle else 'active'}"

            return f"MA01(name='{self.device_name}', state={main_state}, {coil_info}, {di_info}{buffer_info})"
        
        except Exception as e:
            # Fallback w przypadku błędu - pokazujemy podstawowe informacje
            return f"MA01(name='{self.device_name}', state=ERROR, error='{str(e)}')"

    def __repr__(self) -> str:
        """
        Zwraca reprezentację urządzenia MA01 dla developerów.
        Pokazuje więcej szczegółów technicznych.

        Returns:
            str: Szczegółowa reprezentacja urządzenia
        """
        try:
            import time
            cache_age = time.time() - self.di_cache_time
            
            return (
                f"MA01(device_name='{self.device_name}', "
                f"address={self.address}, "
                f"coil_buffer={self.coil_buffer}, "
                f"di_cache={self.di_cache})"
            )
        except Exception as e:
            return f"MA01(device_name='{self.device_name}', error='{str(e)}')"

    def to_dict(self) -> dict:
        """
        Zwraca słownikową reprezentację urządzenia MA01.
        Używane do zapisywania stanu urządzenia w strukturach danych.

        Returns:
            dict: Słownik zawierający:
                - name: nazwa urządzenia
                - address: adres Modbus urządzenia
                - coil_buffer: aktualny stan cewek
                - di_cache: cache wartości wejść cyfrowych
                - di_cache_time: czas ostatniego odczytu DI
                - buffer_modified: czy buffer został zmodyfikowany
                - new_buffer_cycle: czy rozpoczynamy nowy cykl bufora
                - buffer_timeout: timeout bufora
                - di_cache_timeout: timeout cache wejść cyfrowych
                - main_state: główny stan urządzenia
                - error: informacja o błędzie (jeśli wystąpił)
        """
        result = {
            "name": self.device_name,
            "address": self.address,
        }

        try:            
            # Dodanie stanu cewek
            result["coil_buffer"] = self.coil_buffer.copy()
            
            # Dodanie stanu wejść cyfrowych
            result["di_cache"] = self.di_cache

            # Dodanie informacji o aktywnych cewkach
            result["active_coils"] = [i for i, value in enumerate(self.coil_buffer) if value]
            
            # Dodanie stanu poszczególnych wejść cyfrowych
            result["di_states"] = {}
            for i in range(8):  # Zakładamy maksymalnie 8 wejść cyfrowych
                result["di_states"][f"DI{i}"] = 1 if (self.di_cache & (1 << i)) else 0

            # Określenie głównego stanu urządzenia
            if self.buffer_modified:
                result["main_state"] = "BUFFER_MODIFIED"
            elif any(self.coil_buffer):
                result["main_state"] = "COILS_ACTIVE"
            else:
                result["main_state"] = "IDLE"

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
