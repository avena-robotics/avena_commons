import threading
import time
import traceback

from avena_commons.util.logger import MessageLogger, debug, error, info, warning

from ...device import modbus_check_device_connection


class P7674:
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
            self.period: float = (
                period  # Period for DI reading thread and DO writing thread
            )
            self.message_logger = message_logger

            self.__debug = debug

            # DI reading thread properties
            self.di_value: int = 0
            self.__lock: threading.Lock = threading.Lock()
            self._di_thread: threading.Thread | None = None
            self._di_stop_event: threading.Event = threading.Event()

            # DO writing thread properties
            self.coil_state: list = [
                0
            ] * 16  # Track current state of all coils - used as buffer
            self.__previous_coil_state: list = [
                0
            ] * 16  # Track previous state to detect changes
            self._do_thread: threading.Thread | None = None
            self._do_stop_event: threading.Event = threading.Event()
            self._coil_state_changed: bool = False  # Flag to indicate buffer changes

            self.__setup()
            # self.__reset_all_coils()
            self.check_device_connection()
        except Exception as e:
            error(
                f"{self.device_name} - Error initializing: {str(e)}",
                message_logger=message_logger,
            )
            error(traceback.format_exc(), message_logger=message_logger)

    def __setup(self):
        try:
            # Start DI reading thread
            if self._di_thread is None or not self._di_thread.is_alive():
                self._di_stop_event.clear()
                self._di_thread = threading.Thread(target=self._di_thread_worker)
                self._di_thread.daemon = True
                self._di_thread.start()
                info(
                    f"{self.device_name} - DI monitoring thread started",
                    message_logger=self.message_logger,
                )

            # Start DO writing thread
            if self._do_thread is None or not self._do_thread.is_alive():
                self._do_stop_event.clear()
                self._do_thread = threading.Thread(target=self._do_thread_worker)
                self._do_thread.daemon = True
                self._do_thread.start()
                info(
                    f"{self.device_name} - DO writing thread started",
                    message_logger=self.message_logger,
                )

        except Exception as e:
            error(
                f"{self.device_name} - Error starting threads: {e}",
                message_logger=self.message_logger,
            )

    def _di_thread_worker(self):
        """Background thread that periodically reads DI values"""
        while not self._di_stop_event.is_set():
            now = time.time()

            try:
                # Read DI register
                response = self.bus.read_holding_register(
                    address=self.address, register=4
                )

                if response is not None:
                    with self.__lock:
                        self.di_value = response
                        if self.__debug:
                            debug(
                                f"{self.device_name} - DI value updated: {bin(response)}",
                                message_logger=self.message_logger,
                            )
                else:
                    warning(
                        f"{self.device_name} - Unable to read DI register",
                        message_logger=self.message_logger,
                    )

            except Exception as e:
                error(
                    f"{self.device_name} - Error reading DI: {e}",
                    message_logger=self.message_logger,
                )

            time.sleep(max(0, self.period - (time.time() - now)))

    def _do_thread_worker(self):
        """Background thread that periodically writes DO values from buffer"""
        while not self._do_stop_event.is_set():
            now = time.time()

            try:
                # Check if coil state has changed
                with self.__lock:
                    if (
                        self._coil_state_changed
                        or self.coil_state != self.__previous_coil_state
                    ):
                        current_state = self.coil_state.copy()
                        self._coil_state_changed = False
                        self.__previous_coil_state = current_state.copy()
                        write_needed = True
                    else:
                        write_needed = False

                # Write to device if needed (outside of lock to avoid blocking)
                if write_needed:
                    try:
                        self.bus.write_coils(
                            address=self.address, register=0, values=current_state
                        )
                        if self.__debug:
                            debug(
                                f"{self.device_name} - DO write successful: {current_state}",
                                message_logger=self.message_logger,
                            )
                    except Exception as e:
                        error(
                            f"{self.device_name} - Error writing DO: {str(e)}",
                            message_logger=self.message_logger,
                        )

            except Exception as e:
                error(
                    f"{self.device_name} - Error in DO thread: {e}",
                    message_logger=self.message_logger,
                )

            time.sleep(max(0, self.period - (time.time() - now)))

    def __reset_all_coils(self):
        """Reset all coils to OFF (0)"""
        try:
            with self.__lock:
                self.coil_state = [0] * 16  # Update buffer
                self.__previous_coil_state = [0] * 16
                self._coil_state_changed = True  # Force immediate write
            if self.__debug:
                debug(
                    f"{self.device_name} - All coils reset in buffer",
                    message_logger=self.message_logger,
                )
        except Exception as e:
            error(
                f"{self.device_name} - Error resetting coils: {str(e)}",
                message_logger=self.message_logger,
            )
            raise

    def di(self, index: int):
        """Read DI value from cached data"""
        with self.__lock:
            result = 1 if (self.di_value & (1 << index - self.offset)) else 0
            # if self.__debug:
            #     debug(f"{self.device_name} - DI{index} value: {result}", message_logger=self.message_logger)
            return result

    def do(self, index: int, value: bool = None):
        """Set or get DO value - buffered write via thread"""
        if value is None:
            # Return current state of the specified DO from buffer
            with self.__lock:
                return self.coil_state[index - self.offset]
        else:
            # Update buffer - actual write will be handled by DO thread
            with self.__lock:
                self.coil_state[index - self.offset] = 1 if value else 0
                self._coil_state_changed = True  # Signal that buffer has changed
            if self.__debug:
                debug(
                    f"{self.device_name} - DO{index} buffered to: {value}, current buffer: {self.coil_state}",
                    message_logger=self.message_logger,
                )
            return None

    def __del__(self):
        """Cleanup when object is destroyed"""
        self.message_logger = None
        try:
            # Stop DI thread
            if (
                hasattr(self, "_di_thread")
                and self._di_thread is not None
                and self._di_thread.is_alive()
            ):
                self._di_stop_event.set()
                time.sleep(0.1)
                self._di_thread.join()
                self._di_thread = None
                info(
                    f"{self.device_name} - DI monitoring thread stopped",
                    message_logger=self.message_logger,
                )

            # Stop DO thread
            if (
                hasattr(self, "_do_thread")
                and self._do_thread is not None
                and self._do_thread.is_alive()
            ):
                self._do_stop_event.set()
                time.sleep(0.1)
                self._do_thread.join()
                self._do_thread = None
                info(
                    f"{self.device_name} - DO writing thread stopped",
                    message_logger=self.message_logger,
                )
        except Exception:
            pass  # nie loguj tutaj!

    def check_device_connection(self) -> bool:
        return modbus_check_device_connection(
            device_name=self.device_name,
            bus=self.bus,
            address=self.address,
            register=4,
            message_logger=self.message_logger,
        )

    def __str__(self) -> str:
        """
        Zwraca czytelną reprezentację urządzenia P7674 w formie stringa.
        Używane przy printowaniu urządzenia.

        Returns:
            str: Czytelna reprezentacja urządzenia zawierająca nazwę, stan DI i DO
        """
        try:
            # Sprawdzenie czy są aktywne jakieś wejścia cyfrowe
            active_di_count = bin(self.di_value).count("1")

            # Sprawdzenie czy są aktywne jakieś wyjścia cyfrowe
            active_do_count = sum(self.coil_state)

            # Określenie głównego stanu urządzenia
            if active_di_count > 0 or active_do_count > 0:
                main_state = "ACTIVE"
            else:
                main_state = "IDLE"

            return f"P7674(name='{self.device_name}', state={main_state}, DI={bin(self.di_value)}, DO={self.coil_state})"

        except Exception as e:
            # Fallback w przypadku błędu - pokazujemy podstawowe informacje
            return f"P7674(name='{self.device_name}', state=ERROR, error='{str(e)}')"

    def __repr__(self) -> str:
        """
        Zwraca reprezentację urządzenia P7674 dla developerów.
        Pokazuje więcej szczegółów technicznych.

        Returns:
            str: Szczegółowa reprezentacja urządzenia
        """
        try:
            return (
                f"P7674(device_name='{self.device_name}', "
                f"address={self.address}, "
                f"offset={self.offset}, "
                f"period={self.period}, "
                f"di_value={self.di_value}, "
                f"coil_state={self.coil_state})"
            )
        except Exception as e:
            return f"P7674(device_name='{self.device_name}', error='{str(e)}')"

    def to_dict(self) -> dict:
        """
        Zwraca słownikową reprezentację urządzenia P7674.
        Używane do zapisywania stanu urządzenia w strukturach danych.

        Returns:
            dict: Słownik zawierający:
                - name: nazwa urządzenia
                - address: adres Modbus urządzenia
                - offset: przesunięcie numeracji
                - period: okres odczytu/zapisu
                - di_value: wartość wejść cyfrowych
                - coil_state: aktualny stan wyjść cyfrowych
                - active_di_count: liczba aktywnych wejść
                - active_do_count: liczba aktywnych wyjść
                - main_state: główny stan urządzenia
                - error: informacja o błędzie (jeśli wystąpił)
        """
        result = {
            "name": self.device_name,
            "address": self.address,
            "offset": self.offset,
            "period": self.period,
        }

        try:
            # Dodanie stanu DI/DO
            result["di_value"] = self.di_value
            result["coil_state"] = self.coil_state.copy()

            # Obliczenie liczby aktywnych I/O
            result["active_di_count"] = bin(self.di_value).count("1")
            result["active_do_count"] = sum(self.coil_state)

            # Dodanie głównego stanu urządzenia
            if result["active_di_count"] > 0 or result["active_do_count"] > 0:
                result["main_state"] = "ACTIVE"
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
