import threading
import time

from avena_commons.io.device import modbus_check_device_connection
from avena_commons.util.logger import MessageLogger, error, info, warning


class AS228P:
    """Czujnik/enkoder AS228P odczytywany przez Modbus z wątkiem monitorującym.

    Args:
        device_name (str): Nazwa urządzenia.
        bus: Magistrala Modbus/komunikacyjna.
        address: Adres urządzenia.
        period (float): Okres odczytu rejestrów (s).
        message_logger (MessageLogger | None): Logger wiadomości.
    """

    def __init__(
        self,
        device_name: str,
        bus,
        address,
        period: float = 0.025,
        message_logger: MessageLogger | None = None,
    ):
        self.device_name = device_name
        self.bus = bus
        self.address = address
        self.period: float = period
        self.message_logger: MessageLogger | None = message_logger
        self.encoder_1: int = 0
        self.encoder_2: int = 0
        self.encoder_3: int = 0
        self.__lock: threading.Lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()
        self.__setup()
        self.__reset()
        self.check_device_connection()

    def __setup(self):
        """Inicjalizuje i uruchamia wątek monitorujący enkodery."""
        try:
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(target=self._encoder_thread)
                self._thread.daemon = True
                self._thread.start()
                info(
                    f"{self.device_name} Encoder monitoring thread started",
                    message_logger=self.message_logger,
                )

        except Exception as e:
            error(
                f"{self.device_name} Error writing to device: {e}",
                message_logger=self.message_logger,
            )
            return None

    def __reset(self):
        """Resetuje enkodery w urządzeniu (zapis do odpowiedniego rejestru)."""
        with self.__lock:
            self.bus.write_holding_register(address=self.address, register=10, value=7)

    def _encoder_thread(self):
        """Wątek cyklicznie odczytujący trzy wartości enkoderów i aktualizujący cache."""
        while not self._stop_event.is_set():
            now = time.time()

            try:
                # Read 6 registers (3 pairs) starting from address 0
                registers = self.bus.read_holding_registers(
                    address=self.address, first_register=0, count=6
                )

                if registers is not None and len(registers) >= 6:
                    with self.__lock:
                        # For each encoder pair:
                        # If odd register (sign register) is 0, value is positive in even register
                        # If odd register is 0xFFFF (65535), value is negative, combine using bit operations
                        self.encoder_1 = (
                            registers[0]
                            if registers[1] == 0
                            else ((registers[1] << 16) | registers[0]) - 0x100000000
                        )
                        self.encoder_2 = (
                            registers[2]
                            if registers[3] == 0
                            else ((registers[3] << 16) | registers[2]) - 0x100000000
                        )
                        self.encoder_3 = (
                            registers[4]
                            if registers[5] == 0
                            else ((registers[5] << 16) | registers[4]) - 0x100000000
                        )
                else:
                    warning(
                        f"{self.device_name} Unable to read encoder registers",
                        message_logger=self.message_logger,
                    )

            except Exception as e:
                error(
                    f"{self.device_name} Error reading encoders: {e}",
                    message_logger=self.message_logger,
                )

            time.sleep(max(0, self.period - (time.time() - now)))

    def read_encoder_1(self):
        """Zwraca bieżącą wartość enkodera 1."""
        with self.__lock:
            return self.encoder_1

    def read_encoder_2(self):
        """Zwraca bieżącą wartość enkodera 2."""
        with self.__lock:
            return self.encoder_2

    def read_encoder_3(self):
        """Zwraca bieżącą wartość enkodera 3."""
        with self.__lock:
            return self.encoder_3

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
                    f"{self.device_name} - Encoder monitoring thread stopped",
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

    def __str__(self) -> str:
        """
        Zwraca czytelną reprezentację urządzenia AS228P w formie stringa.
        Używane przy printowaniu urządzenia.

        Returns:
            str: Czytelna reprezentacja urządzenia zawierająca nazwę i wartości enkoderów
        """
        try:
            with self.__lock:
                encoder_1_val = self.encoder_1
                encoder_2_val = self.encoder_2
                encoder_3_val = self.encoder_3

            # Określenie głównego stanu urządzenia na podstawie aktywności enkoderów
            if encoder_1_val != 0 or encoder_2_val != 0 or encoder_3_val != 0:
                main_state = "ACTIVE"
            else:
                main_state = "IDLE"

            return f"AS228P(name='{self.device_name}', state={main_state}, encoder_1={encoder_1_val}, encoder_2={encoder_2_val}, encoder_3={encoder_3_val})"

        except Exception as e:
            # Fallback w przypadku błędu - pokazujemy podstawowe informacje
            return f"AS228P(name='{self.device_name}', state=ERROR, error='{str(e)}')"

    def __repr__(self) -> str:
        """
        Zwraca reprezentację urządzenia AS228P dla developerów.
        Pokazuje więcej szczegółów technicznych.

        Returns:
            str: Szczegółowa reprezentacja urządzenia
        """
        try:
            with self.__lock:
                encoder_1_val = self.encoder_1
                encoder_2_val = self.encoder_2
                encoder_3_val = self.encoder_3

            return (
                f"AS228P(device_name='{self.device_name}', "
                f"address={self.address}, "
                f"period={self.period}, "
                f"encoder_1={encoder_1_val}, "
                f"encoder_2={encoder_2_val}, "
                f"encoder_3={encoder_3_val})"
            )
        except Exception as e:
            return f"AS228P(device_name='{self.device_name}', error='{str(e)}')"

    def to_dict(self) -> dict:
        """
        Zwraca słownikową reprezentację urządzenia AS228P.
        Używane do zapisywania stanu urządzenia w strukturach danych.

        Returns:
            dict: Słownik zawierający:
                - name: nazwa urządzenia
                - address: adres Modbus urządzenia
                - period: okres odczytu enkoderów
                - encoder_1: wartość enkodera 1
                - encoder_2: wartość enkodera 2
                - encoder_3: wartość enkodera 3
                - main_state: główny stan urządzenia
                - error: informacja o błędzie (jeśli wystąpił)
        """
        result = {
            "name": self.device_name,
            "address": self.address,
            "period": self.period,
        }

        try:
            # Bezpieczne pobranie wartości enkoderów
            with self.__lock:
                encoder_1_val = self.encoder_1
                encoder_2_val = self.encoder_2
                encoder_3_val = self.encoder_3

            # Dodanie wartości enkoderów
            result["encoder_1"] = encoder_1_val
            result["encoder_2"] = encoder_2_val
            result["encoder_3"] = encoder_3_val

            # Dodanie głównego stanu urządzenia
            if encoder_1_val != 0 or encoder_2_val != 0 or encoder_3_val != 0:
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
