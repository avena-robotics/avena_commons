from avena_commons.util.logger import MessageLogger

from ..physical_device_base import PhysicalDeviceBase, PhysicalDeviceState


class EtherCatSlave:
    """Bazowa klasa reprezentująca urządzenie podrzędne (slave) EtherCAT.

    Ustawia funkcję konfiguracyjną w masterze oraz dostarcza szkielety metod
    do odczytu/zapisu PDO i przetwarzania logiki urządzenia.

    Args:
        master: Obiekt mastera EtherCAT (pysoem.Master).
        address: Adres urządzenia w sieci EtherCAT.
        message_logger (MessageLogger | None): Logger wiadomości.
        debug (bool): Flaga debugowania.
    """

    def __init__(
        self, master, address, message_logger: MessageLogger | None = None, debug=True
    ):
        self.address = address
        self.message_logger = message_logger
        self.debug = debug
        self.master = master
        self.master.slaves[self.address].config_func = self._config_function

    def _config_function(self, slave_pos):
        """Funkcja konfiguracyjna wywoływana przez mastera dla tego slave'a."""
        pass

    def _read_pdo(self):
        """Odczytuje dane procesu (PDO) z urządzenia (do nadpisania w klasach potomnych)."""
        pass

    def _write_pdo(self):
        """Zapisuje dane procesu (PDO) do urządzenia (do nadpisania w klasach potomnych)."""
        pass

    def _process(self):
        """Główna logika przetwarzania urządzenia (do nadpisania w klasach potomnych)."""
        pass

    def __str__(self) -> str:
        """Podstawowa reprezentacja dla slave'a EtherCat"""
        try:
            return f"EtherCatSlave(address={self.address}, debug={self.debug})"
        except Exception as e:
            return f"EtherCatSlave(address={getattr(self, 'address', 'unknown')}, error='{str(e)}')"

    def __repr__(self) -> str:
        """Szczegółowa reprezentacja dla developerów"""
        try:
            return (
                f"EtherCatSlave(address={self.address}, "
                f"debug={self.debug}, "
                f"master={type(self.master).__name__})"
            )
        except Exception as e:
            return f"EtherCatSlave(error='{str(e)}')"

    def to_dict(self) -> dict:
        """Słownikowa reprezentacja bazowego slave'a"""
        result = {
            "type": self.__class__.__name__,
            "address": getattr(self, "address", None),
            "debug": getattr(self, "debug", None),
        }

        try:
            # Dodanie podstawowych informacji o master
            result["master_type"] = (
                type(self.master).__name__ if hasattr(self, "master") else None
            )
        except Exception as e:
            result["error"] = str(e)

        return result


class EtherCatDevice(PhysicalDeviceBase):
    """Reprezentacja urządzenia EtherCAT skojarzonego z magistralą i konfiguracją.

    Args:
        bus: Magistrala (obiekt konektora) do której podłączone jest urządzenie.
        vendor_code: Kod producenta urządzenia.
        product_code: Kod produktu urządzenia.
        address: Adres urządzenia w sieci EtherCAT.
        configuration: Słownik konfiguracji urządzenia.
        message_logger (MessageLogger | None): Logger wiadomości.
        debug (bool): Flaga debugowania.
        max_consecutive_errors (int): Maksymalna liczba kolejnych błędów przed FAULT.
    """

    def __init__(
        self,
        bus,
        vendor_code,
        product_code,
        address,
        configuration,
        message_logger: MessageLogger | None = None,
        debug=True,
        max_consecutive_errors: int = 3,
    ):
        # Pobierz device_name z konfiguracji lub użyj domyślnej nazwy
        device_name = configuration.get("device_name", f"EtherCAT_Addr{address}")
        
        super().__init__(
            device_name=device_name,
            max_consecutive_errors=max_consecutive_errors,
            message_logger=message_logger,
        )
        
        self.bus = bus
        self.vendor_code = vendor_code
        self.product_code = product_code
        self.address = address
        self.debug = debug
        self.configuration = configuration
        
    def check_device_connection(self) -> bool:
        """Sprawdza połączenie z urządzeniem EtherCAT.
        
        Weryfikuje:
        1. Stan zdrowia urządzenia (PhysicalDeviceBase.check_health)
        2. Stan magistrali EtherCAT (jeśli dostępne)
        
        Returns:
            bool: True jeśli urządzenie jest dostępne i zdrowe.
        """
        if not self.check_health():
            return False
        
        # Sprawdź czy magistrala EtherCAT jest dostępna
        if hasattr(self.bus, 'check_device_connection'):
            try:
                return self.bus.check_device_connection()
            except Exception as e:
                self.set_error(f"Bus connection check failed: {e}")
                return False
        
        # Fallback: zakładamy że EtherCAT jest OK jeśli proces żyje
        return True
