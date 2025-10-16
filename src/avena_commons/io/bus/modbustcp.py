import threading

from avena_commons.util.control_loop import ControlLoop

# from pymodbus.client import ModbusTcpClient
from avena_commons.util.logger import debug, error, info
from avena_commons.util.worker import Connector, Worker


class ModbusTCPWorker(Worker):
    """Worker do obsługi (przykładowej) komunikacji Modbus TCP.

    Args:
        host (str): Adres hosta urządzenia Modbus TCP.
        message_logger: Logger wiadomości.
    """

    def __init__(self, host: str, message_logger=None):
        self.__lock = threading.Lock()
        self._period = 0.002
        self._message_logger = message_logger
        super().__init__()
        # Inicjalizujemy klienta Modbus tylko z niezbędnymi parametrami
        # self._client = ModbusTcpClient(host=host)
        # self._client.connect()
        # debug("ModbusTCP Worker initialized", message_logger=self._message_logger)

    def __trace_connection(self):
        """Loguje wynik próby połączenia (gdy klient dostępny)."""
        debug(
            f"Connection: {self._client.connect()}", message_logger=self._message_logger
        )

    def __trace_packet(self, is_sending: bool, packet: bytes) -> bytes:
        """Loguje pakiet wysyłany/odbierany w formacie hex."""
        debug(
            f"Packet {'OUT' if is_sending else ' IN'}: [{' '.join(f'{b:02X}' for b in packet)}]",
            message_logger=self._message_logger,
        )
        return packet

    def __trace_pdu(self, is_sending: bool, pdu) -> object:
        """Loguje PDU wysyłane/odbierane (gdy klient dostępny)."""
        debug(
            f"PDU {'OUT' if is_sending else ' IN'}: {pdu}",
            message_logger=self._message_logger,
        )
        return pdu

    def _run(self, pipe_in):
        """Pętla robocza przetwarzająca komendy przychodzące przez pipe."""
        cl = ControlLoop(
            "control_loop_modbus_rtu",
            period=self._period,
            message_logger=None,
            warning_printer=False,
        )

        try:
            while True:
                cl.loop_begin()

                if pipe_in.poll(0.0005):
                    data = pipe_in.recv()
                    match data[0]:
                        case "STOP":
                            info(
                                "Stopping control_loop_modbus_rtu subprocess",
                                message_logger=self._message_logger,
                            )
                            break

                        case _:
                            match data[0]:
                                case "READ_COILS":
                                    with self.__lock:
                                        try:
                                            response = self._client.read_coils(
                                                slave=data[1],
                                                address=data[2],
                                                count=data[3],
                                            )
                                            pipe_in.send(response.registers[0])
                                        except Exception as e:
                                            error(
                                                f"Error reading coils: {e}",
                                                self._message_logger,
                                            )
                                            pipe_in.send(False)

                                case "WRITE_COILS":
                                    with self.__lock:
                                        try:
                                            response = self._client.write_coils(
                                                slave=data[1],
                                                address=data[2],
                                                values=data[3],
                                            )
                                            pipe_in.send(response.registers)
                                        except Exception as e:
                                            error(
                                                f"Error writing coils: {e}",
                                                self._message_logger,
                                            )
                                            pipe_in.send(False)

                                case "READ_HOLDING_REGISTER":
                                    with self.__lock:
                                        try:
                                            response = (
                                                self._client.read_holding_registers(
                                                    slave=data[1],
                                                    address=data[2],
                                                    count=1,
                                                )
                                            )
                                            pipe_in.send(response.registers[0])
                                        except Exception as e:
                                            error(
                                                f"Error reading holding register: {e}",
                                                self._message_logger,
                                            )
                                            pipe_in.send(False)

                                case "READ_HOLDING_REGISTERS":
                                    with self.__lock:
                                        try:
                                            response = (
                                                self._client.read_holding_registers(
                                                    slave=data[1],
                                                    address=data[2],
                                                    count=data[3],
                                                )
                                            )
                                            pipe_in.send(response.registers)
                                        except Exception as e:
                                            error(
                                                f"Error reading holding registers: {e}",
                                                self._message_logger,
                                            )
                                            pipe_in.send(False)

                                case "WRITE_HOLDING_REGISTER":
                                    with self.__lock:
                                        response = None
                                        try:
                                            response = self._client.write_register(
                                                slave=data[1],
                                                address=data[2],
                                                value=data[3],
                                            )
                                            if response and not response.isError():
                                                pipe_in.send(True)
                                            else:
                                                error_msg = (
                                                    f"Error writing holding register: {response}"
                                                    if response
                                                    else "Error writing holding register: No valid response received (None)"
                                                )
                                                error(error_msg, self._message_logger)
                                                pipe_in.send(False)
                                        except Exception as e:
                                            error(
                                                f"Exception during writing holding register: {e}",
                                                self._message_logger,
                                            )
                                            if response is not None:
                                                error(
                                                    f"Response object before exception: {response}",
                                                    self._message_logger,
                                                )
                                            pipe_in.send(False)

                                case "WRITE_HOLDING_REGISTERS":
                                    with self.__lock:
                                        response = None
                                        try:
                                            response = self._client.write_registers(
                                                slave=data[1],
                                                address=data[2],
                                                values=data[3],
                                            )
                                            if response and not response.isError():
                                                pipe_in.send(True)
                                            else:
                                                error_msg = (
                                                    f"Error writing holding registers: {response}"
                                                    if response
                                                    else "Error writing holding registers: No valid response received (None)"
                                                )
                                                error(error_msg, self._message_logger)
                                                pipe_in.send(False)
                                        except Exception as e:
                                            error(
                                                f"Exception during writing holding registers: {e}",
                                                self._message_logger,
                                            )
                                            if response is not None:
                                                error(
                                                    f"Response object before exception: {response}",
                                                    self._message_logger,
                                                )
                                            pipe_in.send(False)

                                case _:
                                    error(
                                        f"Unknown command: {data[0]}",
                                        self._message_logger,
                                    )

                cl.loop_end()
        except KeyboardInterrupt:
            pass


class ModbusTCP(Connector):
    """Konektor Modbus TCP uruchamiany w procesie potomnym.

    Args:
        host (str): Adres hosta urządzenia.
        message_logger: Logger wiadomości.
    """

    def __init__(self, host: str, message_logger=None):
        self._host = host
        self.message_logger = message_logger
        self._state = None
        super().__init__(message_logger=self.message_logger)
        super()._connect()
        self.__lock = threading.Lock()
        debug(
            f"ModbusTCP Connector initialized on: {self._host}",
            message_logger=self.message_logger,
        )

    def __getstate__(self):
        """Serializuje stan obiektu (dla picklingu procesu)."""
        state = self.__dict__.copy()
        return state

    def __setstate__(self, state):
        """Przywraca stan obiektu (dla picklingu procesu)."""
        self.__dict__.update(state)

    def _run(self, pipe_in):
        """Wejście procesu potomnego: uruchamia `ModbusTCPWorker`."""
        self.__lock = threading.Lock()
        debug(
            f"Starting {self.__class__.__name__} subprocess: {self._host}",
            message_logger=self.message_logger,
        )
        worker = ModbusTCPWorker(host=self._host, message_logger=self.message_logger)
        worker._run(pipe_in)

    @property
    def host(self):
        """Zwraca skonfigurowany adres hosta."""
        return self._host

    def configure(self):
        """Konfiguracja urządzeń (placeholder)."""
        pass

    def read_coils(self, address: int, register: int, count: int):
        """Czyta rejestry Coils z urządzenia.

        Returns:
            Any: Odpowiedź z procesu worker'a.
        """
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out, ["READ_COILS", address, register, count]
            )
            return value

    def write_coils(self, address: int, register: int, values: list):
        """Zapisuje wartości do rejestrów Coils."""
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out, ["WRITE_COILS", address, register, values]
            )
            return value

    def read_holding_register(self, address: int, register: int):
        """Czyta pojedynczy rejestr Holding Register."""
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out, ["READ_HOLDING_REGISTER", address, register]
            )
            return value

    def write_holding_register(self, address: int, register: int, value: int):
        """Zapisuje wartość do pojedynczego rejestru Holding Register."""
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out, ["WRITE_HOLDING_REGISTER", address, register, value]
            )
            return value

    def read_holding_registers(self, address: int, first_register: int, count: int):
        """Czyta wiele rejestrów Holding Registers."""
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out,
                ["READ_HOLDING_REGISTERS", address, first_register, count],
            )
            return value

    def write_holding_registers(self, address: int, first_register: int, values: list):
        """Zapisuje wiele rejestrów Holding Registers."""
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out,
                ["WRITE_HOLDING_REGISTERS", address, first_register, values],
            )
            return value
