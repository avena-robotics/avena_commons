from avena_commons.util.logger import MessageLogger, debug

from .EtherCatSlave import EtherCatDevice, EtherCatSlave


# TODO: CHECK IF THIS IS CORRECT
class R3_Slave(EtherCatSlave):
    """Slave R3 dla EtherCAT: 16 wejść i 16 wyjść cyfrowych.

    Args:
        master: Obiekt mastera EtherCAT.
        address: Adres slave'a w sieci.
        message_logger (MessageLogger | None): Logger wiadomości.
        debug (bool): Flaga debugowania.
    """

    def __init__(
        self, master, address, message_logger: MessageLogger | None = None, debug=True
    ):
        super().__init__(master, address, message_logger, debug)
        self.inputs_ports = [0 for _ in range(16)]
        self.outputs_ports = [0 for _ in range(16)]

    def _config_function(self, slave_pos):
        """Ustawienia konfiguracyjne wykonywane przez mastera EtherCAT."""
        debug(
            f"Configuring {self.address} {slave_pos}",
            message_logger=self.message_logger,
        )

    def _read_pdo(self):
        """Odczytuje wejścia cyfrowe z PDO i aktualizuje `inputs_ports`."""
        # Get the input bytes from the slave
        input_bytes = self.master.slaves[self.address].input

        # Convert the 2 bytes into a 16-bit integer
        input_value = int.from_bytes(input_bytes, byteorder="little")

        # Convert each bit into a boolean value (0 or 1)
        for i in range(16):
            self.inputs_ports[i] = (input_value >> i) & 1

    def _write_pdo(self):
        """Zapisuje wyjścia cyfrowe do PDO na podstawie `outputs_ports`."""
        output_bytes = bytes([self.outputs_ports[i] for i in range(16)])
        self.master.slaves[self.address].output = output_bytes

    def _process(self):
        """Miejsce na logikę przetwarzania wejść/wyjść (do rozszerzenia)."""
        pass

    def read_input(self, port: int):
        """Zwraca stan wejścia cyfrowego o podanym porcie 0..15."""
        return self.inputs_ports[port]

    def write_output(self, port: int, value: bool):
        """Ustawia stan wyjścia cyfrowego w buforze dla portu 0..15."""
        self.outputs_ports[port] = value

    def __str__(self) -> str:
        """Reprezentacja slave'a R3"""
        try:
            return (
                f"R3_Slave(addr={self.address}, "
                f"DI={bin(sum(self.inputs_ports[i] << i for i in range(16)))}, "
                f"DO={bin(sum(self.outputs_ports[i] << i for i in range(16)))})"
            )
        except Exception as e:
            return f"R3_Slave(addr={getattr(self, 'address', 'unknown')}, error='{str(e)}')"

    def __repr__(self) -> str:
        """Szczegółowa reprezentacja dla developerów"""
        try:
            return (
                f"R3_Slave(address={self.address}, "
                f"debug={self.debug}, "
                f"inputs_ports={self.inputs_ports}, "
                f"outputs_ports={self.outputs_ports})"
            )
        except Exception as e:
            return f"R3_Slave(address={getattr(self, 'address', 'unknown')}, error='{str(e)}')"

    def to_dict(self) -> dict:
        """Słownikowa reprezentacja R3_Slave"""
        result = {
            "type": "R3_Slave",
            "address": getattr(self, "address", None),
            "debug": getattr(self, "debug", None),
        }

        try:
            # Stany portów I/O
            result["inputs_ports"] = self.inputs_ports.copy()
            result["outputs_ports"] = self.outputs_ports.copy()

            # Wartości binarne
            result["inputs_binary"] = bin(
                sum(self.inputs_ports[i] << i for i in range(16))
            )
            result["outputs_binary"] = bin(
                sum(self.outputs_ports[i] << i for i in range(16))
            )

        except Exception as e:
            result["error"] = str(e)

        return result


class R3(EtherCatDevice):
    """Urządzenie R3 na warstwie logiki: 16 DI/16 DO.

    Args:
        bus: Magistrala EtherCAT.
        address: Adres slave'a.
        message_logger (MessageLogger | None): Logger wiadomości.
        debug (bool): Flaga debugowania.
        max_consecutive_errors (int): Maksymalna liczba kolejnych błędów przed FAULT.
    """

    def __init__(
        self,
        bus,
        address,
        message_logger: MessageLogger | None = None,
        debug=True,
        max_consecutive_errors: int = 3,
    ):
        product_code = 4353  # TODO: CHANGE THIS
        vendor_code = 2965  # TODO: CHANGE THIS
        # Minimalna konfiguracja z device_name
        configuration = {"device_name": f"R3_{address}"}
        super().__init__(
            bus,
            vendor_code,
            product_code,
            address,
            configuration,
            message_logger,
            debug,
            max_consecutive_errors,
        )
        self.inputs_ports = [0 for _ in range(16)]
        self.outputs_ports = [0 for _ in range(16)]

    def read_input(self, port: int):
        self.inputs_ports[port] = self.bus.read_input(self.address, port)
        return self.inputs_ports[port]

    def read_output(self, port: int):
        """Zwraca stan wyjścia cyfrowego z lokalnego bufora."""
        print(f"read_output {port}")
        return self.outputs_ports[port]

    def write_output(self, port: int, value: bool):
        self.outputs_ports[port] = value
        self.bus.write_output(self.address, port, value)

    def __str__(self) -> str:
        """Reprezentacja urządzenia R3"""
        try:
            connection_status = (
                "connected"  # R3 zawsze zwraca True dla check_device_connection
            )

            return (
                f"R3(addr={self.address}, "
                f"status={connection_status}, "
                f"DI={bin(sum(self.inputs_ports[i] << i for i in range(16)))}, "
                f"DO={bin(sum(self.outputs_ports[i] << i for i in range(16)))})"
            )
        except Exception as e:
            return f"R3(addr={getattr(self, 'address', 'unknown')}, error='{str(e)}')"

    def __repr__(self) -> str:
        """Szczegółowa reprezentacja dla developerów"""
        try:
            return (
                f"R3(address={self.address}, "
                f"vendor_code={self.vendor_code}, "
                f"product_code={self.product_code}, "
                f"debug={self.debug}, "
                f"inputs_ports={self.inputs_ports}, "
                f"outputs_ports={self.outputs_ports})"
            )
        except Exception as e:
            return (
                f"R3(address={getattr(self, 'address', 'unknown')}, error='{str(e)}')"
            )

    def to_dict(self) -> dict:
        """Słownikowa reprezentacja R3"""
        result = {
            "type": "R3",
            "address": getattr(self, "address", None),
            "vendor_code": getattr(self, "vendor_code", None),
            "product_code": getattr(self, "product_code", None),
            "debug": getattr(self, "debug", None),
        }

        try:
            # Stany portów I/O
            result["inputs_ports"] = self.inputs_ports.copy()
            result["outputs_ports"] = self.outputs_ports.copy()

            # Wartości binarne
            result["inputs_binary"] = bin(
                sum(self.inputs_ports[i] << i for i in range(16))
            )
            result["outputs_binary"] = bin(
                sum(self.outputs_ports[i] << i for i in range(16))
            )

            # Status połączenia (R3 nie ma implementacji check_device_connection)
            result["connection_status"] = True

        except Exception as e:
            result["error"] = str(e)

        return result
