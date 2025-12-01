from .EtherCatSlave import EtherCatDevice, EtherCatSlave
import time
import struct

from enum import Enum

from avena_commons.util.logger import MessageLogger, debug, error, info

# TODO: dodanie danych status, obsługi błędów i możliwości setowania licznika

class EK1100_Slave(EtherCatSlave):
    def __init__(
        self,
        device_name: str,
        master,
        address,
        config,
        message_logger: MessageLogger | None = None,
        debug=True
        ):
        super().__init__(master, address, message_logger, debug)
        self.device_name = device_name
        self.counter_ports = [0, 0]
        
    def _config_function(self, slave_pos):
        """Konfiguracja slave'a wywoływana przez mastera.

        Args:
            slave_pos: Pozycja urządzenia w łańcuchu EtherCAT.
        """
        debug(
            f"{self.device_name} - Configuring {self.address} {slave_pos}",
            message_logger=self.message_logger,
        )

    def _read_pdo(self):
        pass
    
    def _write_pdo(self):
        pass
    
    def _check_state(self):
        pass

    def __str__(self) -> str:
        """Reprezentacja slave'a Beckhoff EL5152"""
        try:
            # Określenie stanu osi

            return (
                f"EBeckhoff EL5152_Slave(name='{self.device_name}', "
                f"addr={self.address}, "
            )
        except Exception as e:
            return f"Beckhoff EL5152_Slave(name='{self.device_name}', error='{str(e)}')"

    def __repr__(self) -> str:
        """Szczegółowa reprezentacja dla developerów"""
        try:
            axis_states = [axis.ImpulseFSM.name for axis in self.axis]
            return (
                f"Beckhoff EL5152_Slave(device_name='{self.device_name}', "
                f"address={self.address}, "
                f"debug={self.debug}, "
                f"counter_ports={self.counter_ports}, "
            )
        except Exception as e:
            return (
                f"Beckhoff EL5152_Slave(device_name='{self.device_name}', error='{str(e)}')"
            )

    def to_dict(self) -> dict:
        """Słownikowa reprezentacja Beckhoff EL5152_Slave"""
        result = {
            "type": "Beckhoff EL5152_Slave",
            "device_name": self.device_name,
            "address": self.address,
        }

        return result

class ek1100(EtherCatDevice):
    def __init__(
        self,         
        device_name: str,
        bus,
        address,
        message_logger: MessageLogger | None = None,
        debug=True):
        
        self.device_name = device_name
        product_code = 72100946
        vendor_code = 2
        configuration = {}
        super().__init__(
            bus,
            vendor_code,
            product_code,
            address,
            configuration,
            message_logger,
            debug,
        )
        

    def check_device_connection(self) -> bool:
        return True
    
    def __str__(self) -> str:
        """Reprezentacja urządzenia EC3A_IO1632"""
        try:
            connection_status = (
                "connected" if self.check_device_connection() else "disconnected"
            )

            return (
                f"Beckhoff EL5152(name='{self.device_name}', "
                f"addr={self.address}, "
                f"status={connection_status}, "
                f"counter={bin(sum(self.counter_ports[i] << i for i in range(2)))}, "
            )
        except Exception as e:
            return f"Beckhoff EL5152(name='{self.device_name}', error='{str(e)}')"

    def __repr__(self) -> str:
        """Szczegółowa reprezentacja dla developerów"""
        try:
            return (
                f"Beckhoff EL5152(device_name='{self.device_name}', "
                f"address={self.address}, "
                f"vendor_code={self.vendor_code}, "
                f"product_code={self.product_code}, "
                f"counter_ports={self.counter_ports}, "
            )
        except Exception as e:
            return f"Beckhoff EL5152(device_name='{self.device_name}', error='{str(e)}')"

    def to_dict(self) -> dict:
        """Słownikowa reprezentacja EC3A_IO1632"""
        result = {
            "type": "Beckhoff EL5152",
            "device_name": self.device_name,
            "address": self.address,
            "vendor_code": self.vendor_code,
            "product_code": self.product_code,
        }

        try:
            # Status połączenia
            result["connection_status"] = self.check_device_connection()

        except Exception as e:
            result["error"] = str(e)

        return result