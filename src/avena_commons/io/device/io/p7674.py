import threading
import time
import traceback

from avena_commons.util.logger import MessageLogger, debug, error, info, warning

from .. import modbus_check_device_connection
from ..physical_device_base import PhysicalDeviceBase, PhysicalDeviceState


class P7674(PhysicalDeviceBase):
    """Sterownik modułu P7674 z buforowanym odczytem DI i zapisem DO w wątkach.

    Args:
        device_name (str): Nazwa urządzenia.
        bus: Magistrala Modbus/komunikacji.
        address: Adres urządzenia.
        offset (int): Przesunięcie indeksów I/O względem PCB.
        period (float): Okres cyklu wątków (s).
        message_logger (MessageLogger | None): Logger wiadomości.
        debug (bool): Włącza logi debug.
    """

    def __init__(
        self,
        device_name: str,
        bus=None,
        address=None,
        offset=0,
        period: float = 0.05,
        message_logger: MessageLogger | None = None,
        debug=True,
        max_consecutive_errors: int = 3,
    ):
        try:
            # Initialize PhysicalDeviceBase first
            super().__init__(
                device_name=device_name,
                max_consecutive_errors=max_consecutive_errors,
                message_logger=message_logger,
            )

            self.set_state(PhysicalDeviceState.INITIALIZING)

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
            if self.check_device_connection():
                self.set_state(PhysicalDeviceState.WORKING)
            else:
                self.set_error(f"Initial connection check failed at address {address}")
        except Exception as e:
            error(
                f"{self.device_name} - Error initializing: {str(e)}",
                message_logger=message_logger,
            )
            error(traceback.format_exc(), message_logger=message_logger)
            self.set_error(f"Initialization exception: {str(e)}")

    def __setup(self):
        """Uruchamia wątki odczytu DI i zapisu DO (jeśli nie działają)."""
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
        """Wątek cyklicznie czytający wartości DI do bufora."""
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
                    # Clear error on successful read
                    self.clear_error()
                else:
                    warning(
                        f"{self.device_name} - Unable to read DI register",
                        message_logger=self.message_logger,
                    )
                    self.set_error("Unable to read DI register")

            except Exception as e:
                self.set_error(f"Error reading DI: {e}")

            time.sleep(max(0, self.period - (time.time() - now)))

    def _do_thread_worker(self):
        """Wątek cyklicznie zapisujący DO z bufora na urządzenie."""
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
                        # Clear error on successful write
                        self.clear_error()
                    except Exception as e:
                        self.set_error(f"Error writing DO: {str(e)}")

            except Exception as e:
                self.set_error(f"Error in DO thread: {e}")

            time.sleep(max(0, self.period - (time.time() - now)))

    def __reset_all_coils(self):
        """Resetuje wszystkie cewki (DO) do OFF (0) w buforze i wymusza zapis."""
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
        """Zwraca wartość DI z bufora (bitowo)."""
        with self.__lock:
            result = 1 if (self.di_value & (1 << index - self.offset)) else 0
            # if self.__debug:
            #     debug(f"{self.device_name} - DI{index} value: {result}", message_logger=self.message_logger)
            return result

    def do(self, index: int, value: bool = None):
        """Ustawia lub zwraca wartość DO; zapis wykonywany asynchronicznie przez wątek."""
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
        """Zamyka wątki DI/DO przy niszczeniu obiektu."""
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
        """Sprawdza połączenie urządzenia i status FSM.

        Returns:
            bool: True jeśli urządzenie nie jest w FAULT i połączenie działa.
        """
        # First check FSM health
        if not self.check_health():
            return False

        # Then check Modbus connection
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
                - (z PhysicalDeviceBase): state, state_name, consecutive_errors, etc.
        """
        # Get base class state
        result = super().to_dict()

        # Add P7674-specific fields
        result["address"] = self.address
        result["offset"] = self.offset
        result["period"] = self.period

        try:
            # Dodanie stanu DI/DO
            result["di_value"] = self.di_value
            result["coil_state"] = self.coil_state.copy()

            # Obliczenie liczby aktywnych I/O
            result["active_di_count"] = bin(self.di_value).count("1")
            result["active_do_count"] = sum(self.coil_state)

            # Dodanie głównego stanu urządzenia (legacy compatibility)
            if result["active_di_count"] > 0 or result["active_do_count"] > 0:
                result["main_state"] = "ACTIVE"
            else:
                result["main_state"] = "IDLE"

        except Exception as e:
            # W przypadku błędu dodajemy informację o błędzie
            result["main_state"] = "ERROR"
            if "error_message" not in result or not result["error_message"]:
                result["error_message"] = str(e)

            if self.message_logger:
                error(
                    f"{self.device_name} - Error creating dict representation: {e}",
                    message_logger=self.message_logger,
                )

        return result
