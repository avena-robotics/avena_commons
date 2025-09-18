import asyncio
import threading
import time
import traceback

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.pdu import ModbusPDU

from avena_commons.util.logger import debug, error, info, warning
from avena_commons.util.worker import Connector, Worker


class ModbusRTUWorker(Worker):
    """Worker asynchroniczny obsługujący klienta Modbus RTU.

    Args:
        device_name (str): Nazwa urządzenia.
        serial_port (str): Port szeregowy (np. "/dev/ttyUSB0").
        baudrate (int): Prędkość transmisji.
        timeout_ms (int): Czas oczekiwania (ms).
        trace_connect (bool): Włącza log śledzenia połączenia.
        trace_packet (bool): Włącza logowanie pakietów (hex).
        trace_pdu (bool): Włącza logowanie PDU.
        retry (int): Liczba ponowień żądania.
        message_logger: Logger wiadomości.
    """

    def __init__(
        self,
        device_name: str,
        serial_port: str,
        baudrate: int = 115200,
        timeout_ms: int = 30,
        trace_connect: bool = False,
        trace_packet: bool = False,
        trace_pdu: bool = False,
        retry: int = 3,
        message_logger=None,
    ):
        self.device_name = device_name
        info(
            f"ModbusRTUWorker init {serial_port} {baudrate}bps {timeout_ms}ms",
            message_logger=message_logger,
        )
        self.__trace_connect_enable: bool = trace_connect
        self.__trace_packet_enable: bool = trace_packet
        self.__trace_pdu_enable: bool = trace_pdu
        self._message_logger = message_logger
        self._serial_port = serial_port
        self._baudrate = baudrate
        self.timeout_ms = timeout_ms
        self.request_success_counter = 0
        self.request_error_counter = 0
        self.retry = retry
        self._client = None
        self.__last_pdu = None
        self.__last_packet_time = None
        super().__init__(message_logger=self._message_logger)

    async def init(self):
        """Tworzy i łączy klienta `AsyncModbusSerialClient`. Zwraca self po sukcesie."""
        self._client = AsyncModbusSerialClient(
            port=self._serial_port,
            baudrate=self._baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            trace_connect=self.__trace_connect if self.__trace_connect_enable else None,
            trace_packet=self.__trace_packet if self.__trace_packet_enable else None,
            trace_pdu=self.__trace_pdu if self.__trace_pdu_enable else None,
            timeout=self.timeout_ms / 1000,
            retries=self.retry,
        )

        test = await self._client.connect()
        if test:
            info(
                f"{self.device_name} - ModbusRTU client is connected.",
                message_logger=self._message_logger,
            )
            return self
        else:
            error(
                f"{self.device_name} - ModbusRTU client is not connected.",
                message_logger=self._message_logger,
            )
            raise Exception(f"{self.device_name} - ModbusRTU client is not connected.")

    def __trace_connect(self):
        """Loguje stan połączenia klienta (gdy śledzenie włączone)."""
        debug(
            f"{self.device_name} Connection: {self._client.connect()}",
            message_logger=self._message_logger,
        )

    def __trace_packet(self, is_sending: bool, packet: bytes) -> bytes:
        """Loguje pakiet wyjściowy/wejściowy (hex) oraz czas przejścia OUT→IN."""
        current_time = time.time()
        debug(
            f"{self.device_name} Packet {'OUT' if is_sending else ' IN'}: [{' '.join(f'{b:02X}' for b in packet)}]",
            message_logger=self._message_logger,
        )
        if is_sending:
            self.__last_packet_time = current_time
        else:
            if self.__last_packet_time is not None:
                packet_time = (current_time - self.__last_packet_time) * 1000
                debug(
                    f"{self.device_name} Packet timing: OUT->IN time={packet_time:.2f}ms, baudrate={self._baudrate}, bytes={len(packet)}",
                    message_logger=self._message_logger,
                )
                # Sprawdzenie, czy czas jest fizycznie możliwy
                min_time = (len(packet) * 10) / (
                    self._baudrate / 1000
                )  # 10 bitów na bajt (8 + start + stop)
                if packet_time < min_time:
                    warning(
                        f"{self.device_name} - Suspiciously fast packet timing: measured={packet_time:.2f}ms, minimum={min_time:.2f}ms",
                        message_logger=self._message_logger,
                    )

        return packet

    def __trace_pdu(self, is_sending: bool, pdu) -> object:
        """Loguje PDU wysłane i odebrane (gdy śledzenie włączone)."""
        if is_sending:
            self.__last_pdu = pdu
        else:
            debug(
                f"{self.device_name} pdu: 'OUT' {self.__last_pdu} -> 'IN' {pdu}",
                message_logger=self._message_logger,
            )
        return pdu

    async def _run(self, pipe_in):
        """Pętla główna worker'a obsługująca komendy przychodzące przez pipe."""
        try:
            await self.init()
            last_debug_time = time.time()

            # Set up cancellation handling
            loop = asyncio.get_running_loop()

            while True:
                if pipe_in.poll(0.0005):
                    data = pipe_in.recv()
                    response = None
                    match data[0]:
                        case "STOP":
                            info(
                                f"{self.device_name} - Stopping control_loop_modbus_rtu subprocess",
                                message_logger=self._message_logger,
                            )
                            break

                        case "READ_DISCRETE_INPUTS":
                            try:
                                response: ModbusPDU = (
                                    await self._client.read_discrete_inputs(
                                        slave=data[1], address=data[2], count=data[3]
                                    )
                                )
                                self.request_success_counter += 1
                                pipe_in.send(response)
                            except Exception as e:
                                error(
                                    f"{self.device_name} addr={data[1]} Error reading discrete inputs: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(response)

                        case "READ_COILS":
                            try:
                                response: ModbusPDU = await self._client.read_coils(
                                    slave=data[1], address=data[2], count=data[3]
                                )
                                self.request_success_counter += 1
                                pipe_in.send(response)
                            except Exception as e:
                                error(
                                    f"{self.device_name} addr={data[1]} Error reading coils: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(response)

                        case "WRITE_COILS":
                            try:
                                response: ModbusPDU = await self._client.write_coils(
                                    slave=data[1], address=data[2], values=data[3]
                                )
                                if response and not response.isError():
                                    self.request_success_counter += 1
                                    pipe_in.send(response)
                                else:
                                    error(
                                        f"{self.device_name} Error writing coils: {response}",
                                        message_logger=self._message_logger,
                                    )
                                    self.request_error_counter += 1
                                    pipe_in.send(response)
                            except Exception as e:
                                error(
                                    f"{self.device_name} addr={data[1]} Error writing coils: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(response)

                        case "READ_HOLDING_REGISTER":
                            try:
                                response: ModbusPDU = (
                                    await self._client.read_holding_registers(
                                        slave=data[1], address=data[2], count=1
                                    )
                                )
                                self.request_success_counter += 1
                                pipe_in.send(response)

                            except Exception as e:
                                error(
                                    f"{self.device_name} addr={data[1]} Error reading holding register: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(response)

                        case "READ_HOLDING_REGISTERS":
                            try:
                                response: ModbusPDU = (
                                    await self._client.read_holding_registers(
                                        slave=data[1], address=data[2], count=data[3]
                                    )
                                )
                                self.request_success_counter += 1
                                pipe_in.send(response)
                            except Exception as e:
                                error(
                                    f"{self.device_name} addr={data[1]} Error reading holding registers: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(response)

                        case "READ_INPUT_REGISTERS":
                            try:
                                response: ModbusPDU = (
                                    await self._client.read_input_registers(
                                        slave=data[1], address=data[2], count=data[3]
                                    )
                                )
                                self.request_success_counter += 1
                                pipe_in.send(response)
                            except Exception as e:
                                error(
                                    f"{self.device_name} addr={data[1]} Error reading input registers: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(response)

                        case "WRITE_HOLDING_REGISTER":
                            try:
                                response: ModbusPDU = await self._client.write_register(
                                    slave=data[1], address=data[2], value=data[3]
                                )
                                if response and not response.isError():
                                    self.request_success_counter += 1
                                    pipe_in.send(response)
                                else:
                                    error_msg = (
                                        f"{self._serial_port} Error writing holding register: {response}"
                                        if response
                                        else "Error writing holding register: No valid response received (None)"
                                    )
                                    error(
                                        error_msg, message_logger=self._message_logger
                                    )
                                    self.request_error_counter += 1
                                    pipe_in.send(False)
                            except Exception as e:
                                error(
                                    f"{self.device_name} addr={data[1]} Exception during writing holding register: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(response)

                        case "WRITE_HOLDING_REGISTERS":
                            try:
                                response: ModbusPDU = (
                                    await self._client.write_registers(
                                        slave=data[1], address=data[2], values=data[3]
                                    )
                                )
                                if response and not response.isError():
                                    self.request_success_counter += 1
                                    pipe_in.send(response)
                                else:
                                    error_msg = (
                                        f"{self.device_name} Error writing holding registers: {response}"
                                        if response
                                        else "Error writing holding registers: No valid response received (None)"
                                    )
                                    error(
                                        error_msg, message_logger=self._message_logger
                                    )
                                    self.request_error_counter += 1
                                    pipe_in.send(False)
                            except Exception as e:
                                error(
                                    f"{self.device_name} addr={data[1]} Exception during writing holding registers: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(response)

                        case _:
                            error(
                                f"{self.device_name} Unknown command: {data[0]}",
                                message_logger=self._message_logger,
                            )

                if time.time() - last_debug_time > 1:
                    debug(
                        f"{self.device_name} - Request success counter: {self.request_success_counter} Request error counter: {self.request_error_counter}",
                        message_logger=self._message_logger,
                    )
                    last_debug_time = time.time()

        except asyncio.CancelledError:
            info(
                f"{self.device_name} - Task was cancelled",
                message_logger=self._message_logger,
            )
        except Exception as e:
            error(f"Error in ModbusRTUWorker: {e}", message_logger=self._message_logger)
            error(
                f"Traceback:\n{traceback.format_exc()}",
                message_logger=self._message_logger,
            )
        finally:
            # Clean up resources
            if self._client and self._client.connected:
                await self._client.close()
            info(
                f"{self.device_name} - Worker has shut down",
                message_logger=self._message_logger,
            )


class ModbusRTU(Connector):
    """Konektor Modbus RTU uruchamiany w procesie potomnym.

    Args:
        device_name (str): Nazwa urządzenia.
        serial_port (str): Port szeregowy.
        baudrate (int): Prędkość transmisji.
        timeout_ms (int): Czas oczekiwania (ms).
        trace_connect (bool): Włącza śledzenie connect.
        trace_packet (bool): Włącza śledzenie pakietów.
        trace_pdu (bool): Włącza śledzenie PDU.
        core (int): Rdzeń CPU dla procesu potomnego.
        retry (int): Liczba ponowień.
        message_logger: Logger wiadomości.
        max_send_failures (int): Limit porażek wysyłki przed eskalacją.
    """

    def __init__(
        self,
        device_name: str,
        serial_port: str,
        baudrate: int,
        timeout_ms: int = 100,
        trace_connect: bool = False,
        trace_packet: bool = False,
        trace_pdu: bool = False,
        core: int = 8,
        retry: int = 3,
        message_logger=None,
        max_send_failures: int = 3,
    ):
        self.device_name = device_name
        self.__trace_connect: bool = trace_connect
        self.__trace_packet: bool = trace_packet
        self.__trace_pdu: bool = trace_pdu
        self._serial_port = serial_port
        self._baudrate = baudrate
        self.timeout_ms = timeout_ms
        self.retry = retry
        self.message_logger = message_logger
        self._state = None
        # Eskalacja błędów do IO/Orchestratora
        self._error: bool = False
        self._error_message: str | None = None
        self._consecutive_send_failures: int = 0
        self._per_slave_failures: dict[int, int] = {}
        self._max_send_failures: int = max(1, int(max_send_failures))
        super().__init__(core=core, message_logger=self.message_logger)
        super()._connect()
        self.__lock = threading.Lock()
        debug(
            f"{self.device_name} - ModbusRTU Connector initialized on: {self._serial_port} {self._baudrate}",
            message_logger=self.message_logger,
        )

    def __getstate__(self):
        """Serializuje stan obiektu (dla picklingu procesu)."""
        state = self.__dict__.copy()
        return state

    def __setstate__(self, state):
        """Przywraca stan obiektu (dla picklingu procesu)."""
        self.__dict__.update(state)

    def _run(self, pipe_in, message_logger):
        """Wejście procesu potomnego: uruchamia `ModbusRTUWorker` w asyncio."""
        self.__lock = threading.Lock()
        debug(
            f"{self.device_name} Starting {self.__class__.__name__} subprocess: {self._serial_port} {self._baudrate}bps {self.timeout_ms}ms",
            message_logger=self.message_logger,
        )
        worker = ModbusRTUWorker(
            device_name=self.device_name,
            serial_port=self._serial_port,
            baudrate=self._baudrate,
            timeout_ms=self.timeout_ms,
            trace_connect=self.__trace_connect,
            trace_packet=self.__trace_packet,
            trace_pdu=self.__trace_pdu,
            retry=self.retry,
            message_logger=self.message_logger,
        )
        try:
            asyncio.run(worker._run(pipe_in), debug=False)
        except KeyboardInterrupt:
            debug(
                f"{self.device_name} KeyboardInterrupt received, shutting down asyncio event loop",
                message_logger=self.message_logger,
            )
        except Exception as e:
            error(
                f"{self.device_name} Error in ModbusRTU process: {e}",
                message_logger=self.message_logger,
            )
        finally:
            # Ensure any remaining resources are cleaned up
            if hasattr(worker, "_client") and worker._client is not None:
                try:
                    # Create a new event loop for cleanup
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    if worker._client.connected:
                        loop.run_until_complete(worker._client.close())
                    loop.close()
                except Exception as e:
                    error(
                        f"{self.device_name} Error during cleanup: {e}",
                        message_logger=self.message_logger,
                    )

    @property
    def serial_port(self):
        """Zwraca skonfigurowany port szeregowy."""
        return self._serial_port

    @property
    def baudrate(self):
        """Zwraca skonfigurowaną prędkość transmisji."""
        return self._baudrate

    def configure(self, physical_devices: dict):
        """Konfiguracja urządzeń fizycznych (placeholder)."""
        pass

    def __execute_command(self, data: list = []):
        """Wysyła komendę do procesu worker'a i obsługuje liczniki błędów/timeouty."""
        start_time = time.time()
        # Wyciągnij adres slave (drugi element danych) jeśli jest liczbą całkowitą
        slave_id = None
        try:
            if isinstance(data, list) and len(data) > 1 and isinstance(data[1], int):
                slave_id = data[1]
        except Exception:
            slave_id = None
        with self.__lock:
            after_lock_time = time.time()
            try:
                response: ModbusPDU = super()._send_thru_pipe(self._pipe_out, data)
            except Exception as e:
                # Nie udało się wysłać komendy do procesu/urządzenia
                self._consecutive_send_failures += 1
                if slave_id is not None:
                    self._per_slave_failures[slave_id] = (
                        self._per_slave_failures.get(slave_id, 0) + 1
                    )
                self._error = True
                self._error_message = (
                    f"{self.device_name} - Nie udało się wykonać polecenia {data[0]}"
                    f"{(f' (slave {slave_id})' if slave_id is not None else '')}: {e}"
                )
                if (
                    slave_id is not None
                    and self._per_slave_failures.get(slave_id, 0)
                    >= self._max_send_failures
                ) or (self._consecutive_send_failures >= self._max_send_failures):
                    error(
                        f"{self.device_name} - Exceeded max_send_failures={self._max_send_failures}: {self._error_message}",
                        message_logger=self.message_logger,
                    )
                return None
        now = time.time()
        locking_time = (after_lock_time - start_time) * 1000
        communication_time = (now - after_lock_time) * 1000
        pipe_time = (now - start_time) * 1000

        # TODO: WHY?????????
        if response is None:
            error(
                f"{self.device_name} - No response received for command: {data[0]}",
                message_logger=self.message_logger,
            )
            # Traktuj jako niepowodzenie wysyłki
            self._consecutive_send_failures += 1
            if slave_id is not None:
                self._per_slave_failures[slave_id] = (
                    self._per_slave_failures.get(slave_id, 0) + 1
                )
            self._error = True
            self._error_message = (
                f"{self.device_name} - Nie otrzymano odpowiedzi na polecenie {data[0]}"
                f"{(f' (slave {slave_id})' if slave_id is not None else '')}"
                f" (failures {self._per_slave_failures.get(slave_id, 0) if slave_id is not None else self._consecutive_send_failures}/{self._max_send_failures})"
            )
            if (
                slave_id is not None
                and self._per_slave_failures.get(slave_id, 0) >= self._max_send_failures
            ) or (self._consecutive_send_failures >= self._max_send_failures):
                error(
                    f"{self.device_name} - Exceeded max_send_failures={self._max_send_failures}: {self._error_message}",
                    message_logger=self.message_logger,
                )
            return ModbusPDU()

        message = f"{self.device_name} - {data[0]} took LOCK:{locking_time:.2f}ms COMM:{communication_time:.2f}ms value:{response.registers} status:{response.status} exception:{response.exception_code} response:{response}"
        if (
            not response
            or response.isError()
            or communication_time > self.timeout_ms * 2
        ):
            error(message, message_logger=self.message_logger)
            # Błąd odpowiedzi/time-out → licznik porażek
            self._consecutive_send_failures += 1
            if slave_id is not None:
                self._per_slave_failures[slave_id] = (
                    self._per_slave_failures.get(slave_id, 0) + 1
                )
            self._error = True
            self._error_message = (
                f"{self.device_name} - Błąd podczas wykonywania polecenia {data[0]}"
                f"{(f' (slave {slave_id})' if slave_id is not None else '')}"
                f" (failures {self._per_slave_failures.get(slave_id, 0) if slave_id is not None else self._consecutive_send_failures}/{self._max_send_failures}), resp={response}"
            )
            if (
                slave_id is not None
                and self._per_slave_failures.get(slave_id, 0) >= self._max_send_failures
            ) or (self._consecutive_send_failures >= self._max_send_failures):
                error(
                    f"{self.device_name} - Exceeded max_send_failures={self._max_send_failures}: {self._error_message}",
                    message_logger=self.message_logger,
                )
        elif locking_time > self.timeout_ms * 2:
            warning(message, message_logger=self.message_logger)
        else:
            debug(message, message_logger=self.message_logger)
            # Sukces → wyczyść stan błędów
            self._consecutive_send_failures = 0
            if slave_id is not None:
                self._per_slave_failures[slave_id] = 0
            # Wyczyść globalny stan błędu tylko, gdy żaden slave nie przekracza limitu
            try:
                any_over = any(
                    v >= self._max_send_failures
                    for v in self._per_slave_failures.values()
                )
            except Exception:
                any_over = False
            if not any_over:
                self._error = False
                self._error_message = None
        return response

    def read_discrete_inputs(self, address: int, register: int, count: int):
        """Czyta rejestry typu Discrete Inputs.

        Returns:
            list[int]: Lista bitów (0/1) odczytanych z urządzenia.
        """
        return (
            self.__execute_command(["READ_DISCRETE_INPUTS", address, register, count])
        ).registers

    def read_coils(self, address: int, register: int, count: int):
        """Czyta rejestry typu Coils.

        Returns:
            list[int]: Lista bitów (0/1) odczytanych z urządzenia.
        """
        return (self.__execute_command(["READ_COILS", address, register, count])).bits

    def write_coils(self, address: int, register: int, values: list):
        """Zapisuje wartości do rejestrów typu Coils.

        Returns:
            bool: True, jeśli operacja zakończyła się powodzeniem.
        """
        return not (
            self.__execute_command(["WRITE_COILS", address, register, values])
        ).isError()

    def read_holding_register(self, address: int, register: int):
        """Czyta pojedynczy rejestr Holding Register."""
        return (
            self.__execute_command(["READ_HOLDING_REGISTER", address, register])
        ).registers[0]

    def write_holding_register(self, address: int, register: int, value: int):
        """Zapisuje wartość do pojedynczego rejestru Holding Register."""
        return not (
            self.__execute_command(["WRITE_HOLDING_REGISTER", address, register, value])
        ).isError()

    def read_holding_registers(self, address: int, first_register: int, count: int):
        """Czyta wiele rejestrów Holding Registers."""
        return (
            self.__execute_command([
                "READ_HOLDING_REGISTERS",
                address,
                first_register,
                count,
            ])
        ).registers

    def read_input_registers(self, address: int, first_register: int, count: int):
        """Czyta wiele rejestrów Input Registers."""
        return (
            self.__execute_command([
                "READ_INPUT_REGISTERS",
                address,
                first_register,
                count,
            ])
        ).registers

    def write_holding_registers(self, address: int, first_register: int, values: list):
        """Zapisuje wiele rejestrów Holding Registers."""
        return not (
            self.__execute_command([
                "WRITE_HOLDING_REGISTERS",
                address,
                first_register,
                values,
            ])
        ).isError()

    def __del__(self):
        """Zamyka proces potomny i kanały IPC przy usuwaniu obiektu."""
        self.__execute_command(["STOP"])
        self.pipe_out.close()
        # self.process.join()
        time.sleep(0.1)  # Allow time for the subprocess to stop
        debug(
            f"{self.device_name} - ModbusRTU Connector subprocess stopped.",
            message_logger=self.message_logger,
        )
        self.message_logger = None

    # === Interfejs dla IO_server (health-check i monitoring) ===
    def check_device_connection(self):
        """
        Lekki health-check procesu i stanu wysyłki.

        - Jeśli proces potomny nie działa → błąd połączenia z portem
        - Jeśli przekroczono max_send_failures → błąd wysyłki pakietów
        """
        try:
            # Sprawdź proces (brak procesu zwykle oznacza brak połączenia/wyjątek inicjalizacji)
            proc = getattr(self, "_process", None)
            if proc is None or (hasattr(proc, "is_alive") and not proc.is_alive()):
                self._error = True
                self._error_message = f"{self.device_name} - ModbusRTU process nie uruchomiony (port={self._serial_port})"
                return False

            # Sprawdź przekroczenie limitu niepowodzeń wysyłki (per-slave priorytetowo)
            for sid, cnt in self._per_slave_failures.items():
                if cnt >= self._max_send_failures:
                    self._error = True
                    self._error_message = f"{self.device_name} - Przekroczono max_send_failures={self._max_send_failures} dla slave {sid}"
                    return False

            # Fallback: globalny licznik
            if self._consecutive_send_failures >= self._max_send_failures:
                self._error = True
                if not self._error_message:
                    self._error_message = f"{self.device_name} - Przekroczono max_send_failures={self._max_send_failures}"
                return False

            return True
        except Exception as e:
            self._error = True
            self._error_message = f"{self.device_name} - Błąd podczas sprawdzania połączenia check_device_connection: {e}"
            return False

    @property
    def is_connected(self) -> bool:
        """Zwraca True, jeśli proces żyje i brak stanu błędu."""
        try:
            proc = getattr(self, "_process", None)
            alive = proc is not None and (
                not hasattr(proc, "is_alive") or proc.is_alive()
            )
            return bool(alive) and not bool(self._error)
        except Exception:
            return False

    def to_dict(self) -> dict:
        """Minimalna reprezentacja stanu busa dla monitoringu IO_server."""
        return {
            "name": self.device_name,
            "type": self.__class__.__name__,
            "serial_port": self._serial_port,
            "baudrate": self._baudrate,
            "timeout_ms": self.timeout_ms,
            "retry": self.retry,
            "error": self._error,
            "error_message": self._error_message,
            "consecutive_send_failures": self._consecutive_send_failures,
            "max_send_failures": self._max_send_failures,
            "per_slave_failures": self._per_slave_failures.copy(),
        }
