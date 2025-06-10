import threading
import time

from avena_commons.io.device import modbus_check_device_connection
from avena_commons.util.logger import MessageLogger, error, info, warning


class AS228P:
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
        with self.__lock:
            self.bus.write_holding_register(address=self.address, register=10, value=7)

    def _encoder_thread(self):
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
        with self.__lock:
            return self.encoder_1

    def read_encoder_2(self):
        with self.__lock:
            return self.encoder_2

    def read_encoder_3(self):
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
