from avena_commons.util.logger import MessageLogger, debug, error, info
import threading
from enum import Enum
import time


class WorkingMode(Enum):
    AB_ENCODER = 0
    INDEPENDENT_COUNTERS = 1


class WJ150:
    def __init__(
        self,
        device_name: str,
        bus,
        address,
        working_mode: WorkingMode = WorkingMode.AB_ENCODER,
        period: float = 0.025,
        message_logger: MessageLogger | None = None,
    ):
        self.device_name = device_name
        self.bus = bus
        self.address = address
        self.working_mode: WorkingMode = working_mode
        self.period: float = period
        self.message_logger: MessageLogger | None = message_logger
        self.encoder: int = 0
        self.counter_1: int = 0
        self.counter_2: int = 0
        self.__lock: threading.Lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()
        self.__setup()
        self.__reset()

    def __setup(self):
        try:
            if self.working_mode == WorkingMode.AB_ENCODER:
                with self.__lock:
                    self.bus.write_holding_register(
                        address=self.address, register=0, value=0
                    )
            else:
                with self.__lock:
                    self.bus.write_holding_register(
                        address=self.address, register=0, value=1
                    )

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
        with self.__lock:
            self.bus.write_holding_registers(
                address=self.address, first_register=16, values=[0, 0]
            )
            self.bus.write_holding_registers(
                address=self.address, first_register=32, values=[0, 0, 0, 0]
            )

    def _encoder_thread(self):
        while not self._stop_event.is_set():
            now = time.time()
            match self.working_mode:
                case WorkingMode.AB_ENCODER:
                    with self.__lock:
                        response = self.bus.read_holding_registers(
                            address=self.address, first_register=16, count=2
                        )
                        # debug(f"{self.device_name} - response: {response}", message_logger=self.message_logger)
                        if response and len(response) == 2:
                            # Register 16 (response[0]) contains lower 16 bits
                            # Register 17 (response[1]) contains upper 16 bits
                            value = (response[1] << 16) | response[0]
                            if response[1] & 0x8000:
                                self.encoder = value - (1 << 32)
                            else:
                                self.encoder = value
                            debug(
                                f"{self.device_name} - Response: {response} value: {self.encoder}",
                                message_logger=self.message_logger,
                            )
                        else:
                            error(
                                f"{self.device_name} {self.bus.serial_port} addr[{self.address}]: Error reading encoder or invalid response format",
                                message_logger=self.message_logger,
                            )
                case WorkingMode.INDEPENDENT_COUNTERS:
                    with self.__lock:
                        response = self.bus.read_holding_registers(
                            address=self.address, first_register=32, count=4
                        )
                        if response and len(response) == 4:
                            # Zakładamy, że liczniki są 32-bitowe unsigned int i każdy zajmuje 2 rejestry
                            # Counter 1: response[0] (high), response[1] (low)
                            # Counter 2: response[2] (high), response[3] (low)

                            # Counter 1 (uint32)
                            self.counter_1 = (response[0] << 16) | response[1]

                            # Counter 2 (uint32)
                            self.counter_2 = (response[2] << 16) | response[3]
                        else:
                            error(
                                f"{self.device_name} Error reading independent counters or invalid response format",
                                message_logger=self.message_logger,
                            )
                case _:
                    error(
                        f"{self.device_name} Invalid working mode",
                        message_logger=self.message_logger,
                    )
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

    # def __del__(self):
    #     if hasattr(self, '_thread') and self._thread is not None and self._thread.is_alive():
    #         self._stop_event.set()
    #         self._thread.join()
    #         self._thread = None
    #         info(f"{self.device_name} Encoder monitoring thread stopped", message_logger=self.message_logger)

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
