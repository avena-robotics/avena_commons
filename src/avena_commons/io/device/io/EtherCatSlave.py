from avena_commons.util.logger import MessageLogger


class EtherCatSlave:
    def __init__(
        self, master, address, message_logger: MessageLogger | None = None, debug=True
    ):
        self.address = address
        self.message_logger = message_logger
        self.debug = debug
        self.master = master
        self.master.slaves[self.address].config_func = self._config_function

    def _config_function(self, slave_pos):
        pass

    def _read_pdo(self):
        pass

    def _write_pdo(self):
        pass

    def _process(self):
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
            "address": getattr(self, 'address', None),
            "debug": getattr(self, 'debug', None),
        }
        
        try:
            # Dodanie podstawowych informacji o master
            result["master_type"] = type(self.master).__name__ if hasattr(self, 'master') else None
        except Exception as e:
            result["error"] = str(e)
        
        return result

class EtherCatDevice:
    def __init__(
        self,
        bus,
        vendor_code,
        product_code,
        address,
        configuration,
        message_logger: MessageLogger | None = None,
        debug=True,
    ):
        self.bus = bus
        self.vendor_code = vendor_code
        self.product_code = product_code
        self.address = address
        self.message_logger = message_logger
        self.debug = debug
        self.configuration = configuration
