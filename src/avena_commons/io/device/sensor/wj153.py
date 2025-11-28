import threading
import time

from avena_commons.util.logger import MessageLogger, error, info

from ..physical_device_base import PhysicalDeviceBase


class WJ153(PhysicalDeviceBase):
    """Czujnik/enkoder WJ153 z wątkiem monitorującym wartość enkodera.

    Args:
        device_name (str): Nazwa urządzenia.
        bus: Magistrala Modbus/komunikacyjna.
        address: Adres urządzenia.
        period (float): Okres odczytu (s).
        max_consecutive_errors (int): Maksymalna liczba kolejnych błędów przed FAULT.
        message_logger (MessageLogger | None): Logger wiadomości.
    """

    def __init__(
        self,
        device_name: str,
        bus,
        address,
        period: float = 0.025,
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
        self.encoder: int = 0
        self.counter_1: int = 0
        self.counter_2: int = 0
        self.__lock: threading.Lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()
        self.__setup()
        self.__reset()

    def __setup(self):
        """Inicjalizuje i uruchamia wątek monitorujący odczyt enkodera."""
        try:
            # with self.__lock:
            #     self.bus.write_holding_register(address=self.address, register=0, value=0)

            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(target=self._encoder_thread)
                self._thread.daemon = True
                self._thread.start()
                info(
                    f"{self.device_name} - Encoder monitoring thread started",
                    message_logger=self.message_logger,
                )

        except Exception as e:
            error(
                f"{self.device_name} - Error writing to device: {e}",
                message_logger=self.message_logger,
            )
            return None

    def __reset(self):
        """Resetuje wewnętrzne rejestry odpowiedzialne za licznik/enkoder."""
        with self.__lock:
            self.bus.write_holding_registers(
                address=self.address, first_register=67, values=[10]
            )
            # self.bus.write_holding_registers(address=self.address, first_register=32, values=[0, 0, 0, 0])

    def _encoder_thread(self):
        """Wątek cyklicznie odczytujący wartość enkodera i aktualizujący cache."""
        while not self._stop_event.is_set():
            now = time.time()
            try:
                with self.__lock:
                    response = self.bus.read_holding_registers(
                        address=self.address, first_register=16, count=2
                    )
                    if response and len(response) == 2:
                        # Register 16 (response[0]) contains lower 16 bits
                        # Register 17 (response[1]) contains upper 16 bits
                        value = (response[1] << 16) | response[0]
                        if response[1] & 0x8000:
                            self.encoder = value - (1 << 32)
                        else:
                            self.encoder = value
                        # debug(f"Response: {response} value: {self.encoder}", message_logger=self.message_logger)
                        self.clear_error()
                    else:
                        error(
                            f"{self.device_name} {self.bus.serial_port} addr[{self.address}]: Error reading encoder or invalid response format",
                            message_logger=self.message_logger,
                        )
                        self.set_error("Invalid response reading encoder")
            except Exception as e:
                error(
                    f"{self.device_name} - Exception in encoder thread: {e}",
                    message_logger=self.message_logger,
                )
                self.set_error(f"Exception in encoder thread: {e}")

            time.sleep(max(0, self.period - (time.time() - now)))

    def read_encoder(self):
        with self.__lock:
            return self.encoder

    def read_counter_1(self):
        with self.__lock:
            return self.counter_1

    def read_counter_2(self):
        with self.__lock:
            return self.counter_2

    def __str__(self) -> str:
        """
        Zwraca czytelną reprezentację urządzenia WJ153 w formie stringa.
        Używane przy printowaniu urządzenia.

        Returns:
            str: Czytelna reprezentacja urządzenia zawierająca nazwę i aktualny stan
        """
        try:
            return f"WJ153(name='{self.device_name}', encoder={self.encoder}, counter_1={self.counter_1}, counter_2={self.counter_2})"
        except Exception as e:
            # Fallback w przypadku błędu - pokazujemy podstawowe informacje
            return f"WJ153(name='{self.device_name}', state=ERROR, error='{str(e)}')"

    def __repr__(self) -> str:
        """
        Zwraca reprezentację urządzenia WJ153 dla developerów.
        Pokazuje więcej szczegółów technicznych.

        Returns:
            str: Szczegółowa reprezentacja urządzenia
        """
        try:
            return (
                f"WJ153(device_name='{self.device_name}', "
                f"address={self.address}, "
                f"encoder={self.encoder}, "
                f"counter_1={self.counter_1}, "
                f"counter_2={self.counter_2})"
            )
        except Exception as e:
            return f"WJ153(device_name='{self.device_name}', error='{str(e)}')"

    def to_dict(self) -> dict:
        """
        Zwraca słownikową reprezentację urządzenia WJ153.
        Używane do zapisywania stanu urządzenia w strukturach danych.

        Returns:
            dict: Słownik zawierający:
                - name: nazwa urządzenia
                - address: adres Modbus urządzenia
                - period: okres odczytu
                - encoder: aktualną wartość encodera
                - counter_1: wartość counter_1
                - counter_2: wartość counter_2
                - error: informacja o błędzie (jeśli wystąpił)
        """
        result = {
            "name": self.device_name,
            "address": self.address,
        }

        try:
            # Dodanie aktualnych wartości urządzenia
            result["encoder"] = self.encoder
            result["counter_1"] = self.counter_1
            result["counter_2"] = self.counter_2

            # Określenie głównego stanu urządzenia
            result["main_state"] = "ACTIVE"  # WJ153 jest aktywny gdy thread działa

        except Exception as e:
            # W przypadku błędu dodajemy informację o błędzie
            result["main_state"] = "ERROR"
            result["error"] = str(e)

            if self.message_logger is not None:
                error(
                    f"{self.device_name} - Error creating dict representation: {e}",
                    message_logger=self.message_logger,
                )

        return result

    # def __del__(self):
    #     if hasattr(self, '_thread') and self._thread is not None and self._thread.is_alive():
    #         self._stop_event.set()
    #         self._thread.join()
    #         self._thread = None
    #         info(f"{self.device_name} - Encoder monitoring thread stopped", message_logger=self.message_logger)

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

        except Exception:
            pass  # nie loguj tutaj!
