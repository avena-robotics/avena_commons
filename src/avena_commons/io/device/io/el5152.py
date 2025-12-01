from .EtherCatSlave import EtherCatDevice, EtherCatSlave
import time
import struct

from enum import Enum

from avena_commons.util.logger import MessageLogger, debug, error, info

# TODO: dodanie danych status, obsługi błędów i możliwości setowania licznika

class EL5152_Slave(EtherCatSlave):
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
        input_data = self.master.slaves[self.address].input
        
        pdo_format = "<xBIIxBII"
        expected_length = struct.calcsize(pdo_format)
        
        if len(input_data) == expected_length:
            unpacked_data = struct.unpack(pdo_format, input_data)
            
            # --- CHANNEL 1 ---
            status_byte_1 = unpacked_data[0]
            counter_1 = unpacked_data[1]
            period_1 = unpacked_data[2]
            
            # Extract Bits for Channel 1
            # Note: verify the bit order (0-5) matches your specific documentation
            ch1_status = {
                "set_done":            bool((status_byte_1 >> 0) & 1),
                "extrapolation_stall": bool((status_byte_1 >> 3) & 1),
                "input_A":             bool((status_byte_1 >> 4) & 1),
                "input_B":             bool((status_byte_1 >> 5) & 1),
                "sync_error":          bool((status_byte_1 >> 6) & 1),
                "txPdo_toggle":        bool((status_byte_1 >> 7) & 1)
            }

            # --- CHANNEL 2 ---
            status_byte_2 = unpacked_data[3]
            counter_2 = unpacked_data[4]
            period_2 = unpacked_data[5]
            
            # Extract Bits for Channel 2
            ch2_status = {
                "set_done":            bool((status_byte_2 >> 0) & 1),
                "extrapolation_stall": bool((status_byte_2 >> 3) & 1),
                "input_A":             bool((status_byte_2 >> 4) & 1),
                "input_B":             bool((status_byte_2 >> 5) & 1),
                "sync_error":          bool((status_byte_2 >> 6) & 1),
                "txPdo_toggle":        bool((status_byte_2 >> 7) & 1)
            }

            # print(f"Ch1 Counter: {counter_1}, Period: {period_1}")
            # print(f"Ch1 Status: {ch1_status}")
            # print(f"Ch2 Counter: {counter_2}, Period: {period_2}")
            # print(f"Ch2 Status: {ch2_status}")
            
            self.counter_ports[0] = counter_1
            self.counter_ports[1] = counter_2
            
        else:
            print(f"Error: Input data length ({len(input_data)}) does not match expected ({expected_length})")
            print(input_data)
    
    def _write_pdo(self):
        pass
    
    def read_counter(self, port:int):
        return self.counter_ports[port]
    
    def _check_state(self):
        pass

    def __str__(self) -> str:
        """Reprezentacja slave'a Beckhoff EL5152"""
        try:
            # Określenie stanu osi

            return (
                f"EBeckhoff EL5152_Slave(name='{self.device_name}', "
                f"addr={self.address}, "
                f"Counter={bin(sum(self.counter_ports[i] << i for i in range(2)))}, "
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
                f"axis_states={axis_states}, "
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

        try:
            # Stany portów I/O
            result["counter_ports"] = self.counter_ports.copy()

        except Exception as e:
            result["error"] = str(e)

        return result

class el5152(EtherCatDevice):
    def __init__(
        self,         
        device_name: str,
        bus,
        address,
        message_logger: MessageLogger | None = None,
        debug=True):
        
        self.device_name = device_name
        product_code = 337653842
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
        
        self.counter_ports = [0, 0]
        
    def _read_counter(self, port: int):
        self.counter_ports[port] = self.bus.read_counter(self.address, port)
        return self.counter_ports[port]
    
    def check_device_connection(self) -> bool:
        return True
    
    @property
    def cnt1(self):
        print("in property")
        value = self._read_counter(0)
        return value
    
    @property
    def cnt2(self):
        value = self._read_counter(1)
        return value

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
            # Stany portów I/O
            result["counter"] = self.counter_ports.copy()
            
            # Status połączenia
            result["connection_status"] = self.check_device_connection()

        except Exception as e:
            result["error"] = str(e)

        return result