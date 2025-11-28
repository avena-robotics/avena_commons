import threading
import time
import traceback

from avena_commons.util.logger import MessageLogger, debug, error, info, warning

from .. import modbus_check_device_connection
from ..physical_device_base import PhysicalDeviceBase, PhysicalDeviceState


class N4AIA04(PhysicalDeviceBase):
    """Moduł 2x napięcie (V) i 2x prąd (mA) czytany przez Modbus Holding Registers.

    Args:
        device_name (str): Nazwa urządzenia.
        bus: Magistrala Modbus/komunikacyjna.
        address (int | None): Adres urządzenia.
        offset (int): Przesunięcie indeksów (rezerwowane).
        period (float): Okres odczytu rejestrów (s).
        message_logger (MessageLogger | None): Logger wiadomości.
        debug (bool): Włącza logi debug.
        max_consecutive_errors (int): Próg błędów przed FAULT.
    """

    def __init__(
        self,
        device_name: str,
        bus=None,
        address: int | None = None,
        offset=0,
        period: float = 0.05,
        message_logger: MessageLogger | None = None,
        debug=True,
        max_consecutive_errors: int = 3,
    ):
        try:
            super().__init__(
                device_name=device_name,
                max_consecutive_errors=max_consecutive_errors,
                message_logger=message_logger,
            )
            info(
                f"{self.device_name} - Initializing at address {address}",
                message_logger=message_logger,
            )
            self.bus = bus
            self.address = address
            self.offset = offset  # atrybut do ogarniania roznicy pomiedzy wewnetrzna numeracja p7674 a numerami IO napisanymi na PCB
            self.period: float = period  # Period for analog reading thread
            self.__debug = debug

            # Raw analog values with thread safety
            self.__lock: threading.Lock = threading.Lock()
            self.raw_values: list = [
                0,
                0,
                0,
                0,
            ]  # Raw values from registers 0x0000-0x0003

            # Analog reading thread properties
            self._analog_thread: threading.Thread | None = None
            self._analog_stop_event: threading.Event = threading.Event()

            self.__setup()
            self.check_device_connection()

        except Exception as e:
            error(
                f"{self.device_name} - Error initializing: {str(e)}",
                message_logger=message_logger,
            )
            error(traceback.format_exc(), message_logger=message_logger)

    def __setup(self):
        """Inicjalizuje i uruchamia wątek odczytu wartości analogowych."""
        try:
            # Start analog reading thread
            if self._analog_thread is None or not self._analog_thread.is_alive():
                self._analog_stop_event.clear()
                self._analog_thread = threading.Thread(
                    target=self._analog_thread_worker
                )
                self._analog_thread.daemon = True
                self._analog_thread.start()
                info(
                    f"{self.device_name} - Analog monitoring thread started",
                    message_logger=self.message_logger,
                )

        except Exception as e:
            error(
                f"{self.device_name} - Error starting analog thread: {e}",
                message_logger=self.message_logger,
            )

    def _analog_thread_worker(self):
        """Wątek cyklicznie odczytujący surowe wartości z rejestrów Holding."""
        while not self._analog_stop_event.is_set():
            now = time.time()

            try:
                # Read voltage and current registers
                # Register 0x0000: CH1 V1 voltage (scale: 0.01V)
                # Register 0x0001: CH2 V2 voltage (scale: 0.01V)
                # Register 0x0002: CH3 C1 current (scale: 0.1mA)
                # Register 0x0003: CH4 C2 current (scale: 0.1mA)

                # Read all 4 holding registers at once (0x0000-0x0003)
                raw_data = self.bus.read_holding_registers(
                    address=self.address, first_register=0x0000, count=4
                )

                if raw_data is not None and len(raw_data) == 4:
                    # Update raw values
                    with self.__lock:
                        self.raw_values = raw_data.copy()

                    if self.__debug:
                        # Calculate scaled values for debug display
                        v1 = raw_data[0] * 0.01
                        v2 = raw_data[1] * 0.01
                        c1 = raw_data[2] * 0.1
                        c2 = raw_data[3] * 0.1
                        if self.message_logger:
                            debug(
                                f"{self.device_name} - Raw values updated: {raw_data} -> V1={v1:.2f}V, V2={v2:.2f}V, C1={c1:.1f}mA, C2={c2:.1f}mA",
                                message_logger=self.message_logger,
                            )
                else:
                    if self.message_logger:
                        warning(
                            f"{self.device_name} - Unable to read holding registers 0x0000-0x0003",
                            message_logger=self.message_logger,
                        )

            except Exception as e:
                error(
                    f"{self.device_name} - Error reading analog values: {e}",
                    message_logger=self.message_logger,
                )

            time.sleep(max(0, self.period - (time.time() - now)))

    def get_voltage_1(self) -> float:
        """Zwraca napięcie CH1 V1 w Voltach."""
        with self.__lock:
            return self.raw_values[0] * 0.01  # Convert raw value to Volts

    def get_voltage_2(self) -> float:
        """Zwraca napięcie CH2 V2 w Voltach."""
        with self.__lock:
            return self.raw_values[1] * 0.01  # Convert raw value to Volts

    def get_current_1(self) -> float:
        """Zwraca prąd CH3 C1 w mA."""
        with self.__lock:
            return self.raw_values[2] * 0.1  # Convert raw value to mA

    def get_current_2(self) -> float:
        """Zwraca prąd CH4 C2 w mA."""
        with self.__lock:
            return self.raw_values[3] * 0.1  # Convert raw value to mA

    def get_all_values(self) -> dict:
        """Zwraca wszystkie wartości analogowe w słowniku."""
        with self.__lock:
            return {
                "voltage_1": self.raw_values[0] * 0.01,
                "voltage_2": self.raw_values[1] * 0.01,
                "current_1": self.raw_values[2] * 0.1,
                "current_2": self.raw_values[3] * 0.1,
            }

    def get_raw_values(self) -> list:
        """Zwraca surowe wartości jako listę [V1_raw, V2_raw, C1_raw, C2_raw]."""
        with self.__lock:
            return self.raw_values.copy()

    def __str__(self) -> str:
        """
        Zwraca czytelną reprezentację urządzenia N4AIA04 w formie stringa.
        Używane przy printowaniu urządzenia.

        Returns:
            str: Czytelna reprezentacja urządzenia zawierająca nazwę i aktualne wartości analogowe
        """
        try:
            values = self.get_all_values()

            return (
                f"N4AIA04(name='{self.device_name}', "
                f"V1={values['voltage_1']:.2f}V, V2={values['voltage_2']:.2f}V, "
                f"C1={values['current_1']:.1f}mA, C2={values['current_2']:.1f}mA)"
            )

        except Exception as e:
            # Fallback w przypadku błędu - pokazujemy podstawowe informacje
            return f"N4AIA04(name='{self.device_name}', state=ERROR, error='{str(e)}')"

    def __repr__(self) -> str:
        """
        Zwraca reprezentację urządzenia N4AIA04 dla developerów.
        Pokazuje więcej szczegółów technicznych.

        Returns:
            str: Szczegółowa reprezentacja urządzenia
        """
        try:
            values = self.get_all_values()
            raw_values = self.get_raw_values()

            return (
                f"N4AIA04(device_name='{self.device_name}', "
                f"address={self.address}, "
                f"offset={self.offset}, "
                f"period={self.period}, "
                f"raw_values={raw_values}, "
                f"voltage_1={values['voltage_1']:.2f}V, "
                f"voltage_2={values['voltage_2']:.2f}V, "
                f"current_1={values['current_1']:.1f}mA, "
                f"current_2={values['current_2']:.1f}mA)"
            )

        except Exception as e:
            return f"N4AIA04(device_name='{self.device_name}', error='{str(e)}')"

    def to_dict(self) -> dict:
        """
        Zwraca słownikową reprezentację urządzenia N4AIA04.
        Używane do zapisywania stanu urządzenia w strukturach danych.

        Returns:
            dict: Słownik zawierający:
                - name: nazwa urządzenia
                - address: adres Modbus urządzenia
                - offset: offset dla numeracji
                - period: okres odczytu danych
                - raw_values: surowe wartości z rejestrów
                - values: przeliczone wartości analogowe (napięcia i prądy)
                - error: informacja o błędzie (jeśli wystąpił)
        """
        result = {
            "name": self.device_name,
            "address": self.address,
            "offset": self.offset,
            "period": self.period,
        }

        try:
            # Dodanie surowych wartości
            result["raw_values"] = self.get_raw_values()

            # Dodanie przeliczonych wartości
            result["values"] = self.get_all_values()

        except Exception as e:
            # W przypadku błędu dodajemy informację o błędzie
            result["error"] = str(e)

            if self.message_logger:
                error(
                    f"{self.device_name} - Error creating dict representation: {e}",
                    message_logger=self.message_logger,
                )

        return result

    def __del__(self):
        """Zamyka wątek odczytu analogów podczas niszczenia obiektu."""
        try:
            # Stop analog reading thread
            if (
                hasattr(self, "_analog_thread")
                and self._analog_thread is not None
                and self._analog_thread.is_alive()
            ):
                self._analog_stop_event.set()
                time.sleep(0.1)
                self._analog_thread.join()
                self._analog_thread = None
                info(
                    f"{self.device_name} - Analog monitoring thread stopped",
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
            register=0,
            message_logger=self.message_logger,
        )
