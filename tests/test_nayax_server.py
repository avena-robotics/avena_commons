import argparse
from enum import Enum
import os
import sys
import traceback
import time
import threading
import serial

from unittest import case 
from decimal import Decimal

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from avena_commons.util.control_loop import ControlLoop
from avena_commons.nayax.nayax import NayaxConnector
from avena_commons.event_listener import EventListener, Event
from avena_commons.util.logger import (
    # LoggerPolicyPeriod,
    # MessageLogger,
    debug,
    info,
    warning,
    error,
)
from avena_commons.nayax.enums import MdbStatus, MdbTransactionResult

# from avena_commons.util.worker import Worker, Connector


# def _format_loop_info(cl: ControlLoop) -> str:
#     def fmt(value):
#         return f"{value * 1000:.5}ms" if value is not None else "n/a"

#     return (
#         f"{cl.name.upper()}, loops: {cl.loop_counter}, "
#         f"overtime: {cl.overtime_counter}, "
#         f"min: {fmt(cl.min_period)}, "
#         f"max: {fmt(cl.max_period)}, "
#         f"avg: {fmt(cl.avg_period)}"
#     )


# class NayaxCommand(Enum):
#     REQUEST_DISABLE_CASHLESS = "D,0" # Disable cashless
#     REQUEST_DEVICE_STATUS1 = "D,1" # Device status
#     REQUEST_DEVICE_STATUS = "D,2" # Device status
#     REQUEST_ENABLE_DEVICE = "D,READER,1" # Enable Device
#     REQUEST_CHARGE = "D,REQ," # Charge FORMAT: D,REQ,1.20,10
#     REQUEST_GET_STATUS = "D,STATUS"
# # 
# class NayaxResponse(Enum):
#     RESPONSE_CASHLESS_ERROR = str('D,ERR,"cashless master is on"') # Cashless error response - nalezy wylaczyc
#     RESPONSE_ERROR_MASTER_IS_OFF = str('D,ERR,"cashless master is off"') # Cashless error response - nalezy wylaczyc
#     RESPONSE_DEVICE_STATUS_RESET = str("d,STATUS,RESET")
#     RESPONSE_DEVICE_STATUS_VEND = str("d,STATUS,VEND")
#     RESPONSE_DEVICE_STATUS_RESULT = str("d,STATUS,RESULT")
#     # RESPONSE_DEVICE_STATUS_RESULT = str("d,STATUS,RESULT,-1")
#     RESPONSE_DEVICE_STATUS_OFF = str("d,STATUS,OFF")
#     RESPONSE_DEVICE_STATUS_INITIALIZED = str("d,STATUS,INIT,1")
#     RESPONSE_DEVICE_STATUS_IDLE = str("d,STATUS,IDLE")

# class MdbStatus(Enum):
#     """Status states for MDB service"""

#     DISCONNECTED = "disconnected"
#     OPENING_PORT = "opening_port"
#     CONNECTING = "connecting"
#     RESTARTING_CASHLESS = "restarting_cashless"
#     INITIALIZING = "initializing"
#     STARTING = "starting"
#     IDLE = "idle"
#     PROCESSING_SEND_COMMAND = "processing_send_command"
#     PROCESSING_WAIT_STATUS_VEND = "processing_wait_status_vend"
#     PROCESSING_WAIT_STATUS_RESULT = "processing_wait_status_result"
#     # RESTARTING_AFTER_FAILURE = "restarting_after_failure"
#     WAITING_AFTER_SUCCESS = "waiting_after_success"
#     WAITING_AFTER_FAILURE = "waiting_after_failure"
#     ERROR = "error"
#     SHUTDOWN = "shutdown"

# class MdbError(Exception):
#     """Custom exception for MDB service errors"""

#     pass

# class MdbTransactionResult(Enum):
#     """Transaction result states"""

#     NONE = "none"
#     SUCCESS = "success"
#     FAILED = "failed"
#     TIMEOUT = "timeout"
#     CANCELLED = "cancelled"

# class MdbResult:
#     """Transaction result object"""

#     def __init__(self, status, message=None, amount=None, product=None):
#         self.status = status
#         self.message = message
#         self.amount = amount
#         self.product = product
#         self.timestamp = time.time()

#     def __str__(self):
#         return f"MdbResult: {self.status.value} - {self.message}"

# class NayaxWorker(Worker):

#     def __init__(self, serial: str, message_logger=None):
#         super().__init__(message_logger=message_logger)
#         self._serial_name = serial
#         self._serial = None
#         self._pipe_loop_freq = 5  # Hz
#         self._status = MdbStatus.DISCONNECTED
#         self._rx_buffer = bytearray()
#         self.__start_time_after_success = None
#         self.__wait_after_success_duration = 15  # seconds
#         self.__start_time_after_failure = None
#         self.__wait_after_failure_duration = 20  # seconds
#         self.__charge_amount = Decimal(0)
#         self.__last_payment_result: MdbTransactionResult = MdbTransactionResult.NONE

#     @property
#     def status(self) -> MdbStatus:
#         return self._status

#     @status.setter
#     def status(self, value: MdbStatus):
#         debug(f"NayaxWorker status changed from `{self.status}` to `{value}`", message_logger=self._message_logger)
#         self._status = value

#     def _connect_serial(self):
#         """Connect to the serial port"""
#         try:
#             self._serial = serial.Serial()
#             self._serial.baudrate = 115200
#             self._serial.timeout = 1
#             self._serial.port = self._serial_name
#             self._serial.open()
#             self._serial.reset_input_buffer()
#             self._serial.reset_output_buffer()
#             self._rx_buffer.clear()

#             error(f"Serial port {self._serial_name} opened", message_logger=self._message_logger)

#             # Wait for connection to establish
#             # time.sleep(1)

#             # info(f"Serial connection established on port: {self._serial_name}", message_logger=self._message_logger)
#             return True
#         except Exception as e:
#             self.last_error = str(e)
#             error(f"Serial connection error: {e}", message_logger=self._message_logger)
#             return False

#     def _write_to_serial(self, message):
#         """Send a message to the serial port"""
#         # if not self._serial or not self._serial.is_open:
#         #     raise MdbError("Serial port not connected")

#         payload = (message + "\n").encode("ascii")
#         self._serial.write(payload)
#         self._serial.flush()

#         # if self.debug:
#         debug(f"Sent: '{message}'", message_logger=self._message_logger)

#     def _read_response(self):
#         """Read response from serial port"""
#         # if not self._serial or not self._serial.is_open:
#         #     raise MdbError("Serial port not connected")

#         deadline = time.time() + 0.1  # 100 ms timeout

#         while time.time() < deadline:
#             newline_index = self._rx_buffer.find(b"\n")
#             if newline_index != -1:
#                 line = self._rx_buffer[: newline_index + 1]
#                 del self._rx_buffer[: newline_index + 1]
#                 text = line.decode("ascii", errors="ignore")
#                 debug(f"Received: {len(text)} [{text.strip()}]", message_logger=self._message_logger)
#                 return text.strip()

#             waiting = self._serial.in_waiting
#             if waiting:
#                 chunk = self._serial.read(waiting)
#                 if chunk:
#                     self._rx_buffer.extend(chunk)
#                     continue

#             time.sleep(0.05)

#         if self._rx_buffer:
#             text = self._rx_buffer.decode("ascii", errors="ignore")
#             self._rx_buffer.clear()
#             # if self.debug:
#             debug(f"Received partial: {len(text)} [{text.strip()}]", message_logger=self._message_logger)
#             return text

#         return ""

#     def _run(self, pipe_in) -> None:
#         debug(f"Starting NayaxWorker subprocess", message_logger=self._message_logger)
#         try:
#             cl = ControlLoop(
#                 "NayaxWorker_Loop",
#                 period=1 / self._pipe_loop_freq,
#                 message_logger=self._message_logger, 
#                 warning_printer=False,
#             )

#             # self.state = "Worker New state"

#             while True:
#                 cl.loop_begin()
#                 if pipe_in.poll(0.0001):  # default is 0.001
#                     # info(f"Received data from pipe")
#                     data = pipe_in.recv()
#                     match data[0]:
#                         case "STOP":
#                             debug(
#                                 f"Stopping worker", message_logger=self._message_logger
#                             )
#                             pipe_in.send(True)
#                             break

#                         # GETTERS
#                         case "GET_STATE":
#                             pipe_in.send(self.status)

#                         case "GET_LAST_PAYMENT_RESULT":
#                             pipe_in.send(self.__last_payment_result)

#                         # SETTERS
#                         case "SET_CHARGE":
#                             # w zaleznosci od stanu urzadzenia
#                             if self.status == MdbStatus.IDLE:
#                                 info(f"SET_CHARGE({data[1]:.2f}): returning True", message_logger=self._message_logger)
#                                 self.__last_payment_result = MdbTransactionResult.NONE
#                                 self.__charge_amount = Decimal(data[1])
#                                 self.status = MdbStatus.PROCESSING_SEND_COMMAND
#                                 pipe_in.send(True)
#                             else:
#                                 error(f"SET_CHARGE({data[1]:.2f}): returning False, device busy", message_logger=self._message_logger)
#                                 pipe_in.send(False)

#                         # if unknown message
#                         case _:
#                             warning(
#                                 f"Received unknown message: {data}",
#                                 message_logger=self._message_logger,
#                             )
#                             pipe_in.send(False)


#                 # MARK: SEND COMMAND
#                 # periodic tasks
#                 match self.status:
#                     case MdbStatus.DISCONNECTED:
#                         if self._serial is None or not self._serial.is_open:
#                             self._connect_serial()
#                             self.status = MdbStatus.OPENING_PORT
#                         pass
#                     case MdbStatus.OPENING_PORT:
#                         if self._serial.is_open:
#                             self.status = MdbStatus.CONNECTING

#                     case MdbStatus.CONNECTING:
#                         self._write_to_serial(NayaxCommand.REQUEST_DEVICE_STATUS.value)

#                     case MdbStatus.RESTARTING_CASHLESS:
#                         self._write_to_serial(NayaxCommand.REQUEST_DISABLE_CASHLESS.value)
#                         self._write_to_serial(NayaxCommand.REQUEST_DEVICE_STATUS.value)

#                     case MdbStatus.INITIALIZING:
#                         # self._write_to_serial(NayaxCommand.REQUEST_DEVICE_STATUS.value)
#                         pass

#                     case MdbStatus.STARTING:
#                         self._write_to_serial(NayaxCommand.REQUEST_ENABLE_DEVICE.value)
#                         pass

#                     case MdbStatus.IDLE:                        
#                         pass

#                     case MdbStatus.PROCESSING_SEND_COMMAND:
#                         self._write_to_serial(NayaxCommand.REQUEST_CHARGE.value + f"{self.__charge_amount:.2f},10")
#                         self.status = MdbStatus.PROCESSING_WAIT_STATUS_VEND
#                         continue
#                         pass

#                     case MdbStatus.PROCESSING_WAIT_STATUS_VEND:
#                         pass
                    
#                     case MdbStatus.PROCESSING_WAIT_STATUS_RESULT:
#                         pass

#                     case MdbStatus.WAITING_AFTER_SUCCESS:
#                         if self.__start_time_after_success is not None:
#                             elapsed = time.time() - self.__start_time_after_success
#                             if elapsed >= self.__wait_after_success_duration:
#                                 self.status = MdbStatus.IDLE
#                                 self.__start_time_after_success = None
#                         pass

#                     case MdbStatus.WAITING_AFTER_FAILURE:
#                         if self.__start_time_after_failure is not None:
#                             elapsed = time.time() - self.__start_time_after_failure
#                             if elapsed >= self.__wait_after_failure_duration:
#                                 self.status = MdbStatus.IDLE
#                                 self.__start_time_after_failure = None
#                         pass


#                     # case MdbStatus.RESTARTING_AFTER_FAILURE:
#                     #     self._write_to_serial(NayaxCommand.REQUEST_GET_STATUS.value)
#                     #     pass

#                     case MdbStatus.ERROR:
#                         pass

#                     case MdbStatus.SHUTDOWN:
#                         pass


#                 # MARK: HANDLE RESPONSE
#                 try:
#                     if self._serial and self._serial.is_open:
#                         response = self._read_response()
#                         if len(response) > 0:
#                             match self.status:
#                                 case MdbStatus.CONNECTING:
#                                     match response:  # remove newline
#                                         case NayaxResponse.RESPONSE_CASHLESS_ERROR.value:
#                                             self.status = MdbStatus.RESTARTING_CASHLESS
#                                         case _:
#                                             error(f"Unexpected response while  [{self.status}] [{response}]", message_logger=self._message_logger)

#                                 case MdbStatus.RESTARTING_CASHLESS:
#                                     match response:  # remove newline
#                                         case NayaxResponse.RESPONSE_DEVICE_STATUS_OFF.value:
#                                             self.status = MdbStatus.INITIALIZING
#                                         case _:
#                                             error(f"Unexpected response while  [{self.status}] [{response}]", message_logger=self._message_logger)

#                                 case MdbStatus.INITIALIZING:
#                                     match response:  # remove newline
#                                         case NayaxResponse.RESPONSE_DEVICE_STATUS_INITIALIZED.value:
#                                             self.status = MdbStatus.STARTING
#                                         case _:
#                                             error(f"Unexpected response while  [{self.status}] [{response}]", message_logger=self._message_logger)

#                                 case MdbStatus.STARTING:
#                                     match response:  # remove newline
#                                         case NayaxResponse.RESPONSE_DEVICE_STATUS_IDLE.value:
#                                             self.status = MdbStatus.IDLE
#                                         case _:
#                                             error(f"Unexpected response while  [{self.status}] [{response}]", message_logger=self._message_logger)
#                                     pass

#                                 case MdbStatus.IDLE:
#                                     if NayaxResponse.RESPONSE_DEVICE_STATUS_IDLE.value in response:
#                                         pass
#                                     else:
#                                         error(f"Unexpected response while  [{self.status}] [{response}]", message_logger=self._message_logger)

#                                 case MdbStatus.PROCESSING_SEND_COMMAND:
#                                     pass

#                                 case MdbStatus.PROCESSING_WAIT_STATUS_VEND:
#                                     match response:  # remove newline
#                                         case NayaxResponse.RESPONSE_DEVICE_STATUS_VEND.value:
#                                             self.status = MdbStatus.PROCESSING_WAIT_STATUS_RESULT
#                                         case _:
#                                             error(f"Unexpected response while  [{self.status}] [{response}]", message_logger=self._message_logger)
                                
#                                 case MdbStatus.PROCESSING_WAIT_STATUS_RESULT: 
#                                     if NayaxResponse.RESPONSE_DEVICE_STATUS_RESULT.value in response:
#                                         if ",-1" in response:
#                                             # failure
#                                             self.status = MdbStatus.WAITING_AFTER_FAILURE
#                                             self.__last_payment_result = MdbTransactionResult.FAILED
#                                             self.__start_time_after_failure = time.time()
#                                             pass
#                                         elif f",1,{self.__charge_amount:.2f}" in response:
#                                             # success
#                                             pass
#                                         else:
#                                             error(f"Unexpected amount in response while  [{self.status}] [{response}]", message_logger=self._message_logger)
#                                     elif NayaxResponse.RESPONSE_DEVICE_STATUS_IDLE.value in response:
#                                         # success
#                                         self.__last_payment_result = MdbTransactionResult.SUCCESS
#                                         self.status = MdbStatus.WAITING_AFTER_SUCCESS
#                                         self.__start_time_after_success = time.time()
#                                         pass
#                                     else:
#                                         error(f"Unexpected response while  [{self.status}] [{response}]", message_logger=self._message_logger)

#                                 case _:
#                                     error(f"Unhandled state while reading response: [{self.status}] [{response}] [{NayaxResponse.RESPONSE_DEVICE_STATUS_OFF.value}]", message_logger=self._message_logger)
#                             # debug(f"{len(self._rx_buffer)} '{response}'", message_logger=self._message_logger)
#                 except MdbError as e:
#                     warning(f"MdbError while reading response: {e}", message_logger=self._message_logger)
#                     self.status = MdbStatus.DISCONNECTED
#                 except Exception as e:
#                     warning(f"Exception while reading response: {e}", message_logger=self._message_logger)
#                     self.status = MdbStatus.DISCONNECTED

#                 cl.loop_end()

#         except KeyboardInterrupt:
#             pass
#         except Exception as e:
#             warning(f"Exception in worker: {e}", message_logger=self._message_logger)
#             traceback.print_exception(e)
#         finally:
#             debug(f"Exiting NayaxConnector subprocess", message_logger=self._message_logger)

# class NayaxConnector(Connector):
#     def __init__(self, serial: str, core:int, message_logger=None):
#         super().__init__(core=core, message_logger=message_logger)
#         self.serial = serial
#         self.__lock = threading.Lock()
#         # self._state
#         debug(f"Initialized NayaxConnector with serial: {self.serial}", message_logger=message_logger)

#     # PROPERTIES
#     @property
#     def state(self) -> bool:
#         with self.__lock:
#             state = super()._send_thru_pipe(self._pipe_out, ["GET_STATE"])
#             self._state = state if state != None else self._state
#             return self._state

#     @state.setter
#     @Connector._read_only_property("state")
#     def state(self, *args):
#         pass

#     @property
#     def last_payment_result(self) -> MdbTransactionResult:
#         with self.__lock:
#             last_payment_result = super()._send_thru_pipe(self._pipe_out, ["GET_LAST_PAYMENT_RESULT"])
#             return last_payment_result

#     @last_payment_result.setter
#     @Connector._read_only_property("last_payment_result")
#     def last_payment_result(self, *args):
#         pass

#     def charge(self, amount: Decimal) -> bool:
#         with self.__lock:
#             cmd_accepted = super()._send_thru_pipe(self._pipe_out, ["SET_CHARGE", amount])
#             return cmd_accepted

#     def _run(self, pipe_in, message_logger) -> None:
#         info(f"Starting run_connector()", message_logger=message_logger)
#         worker = NayaxWorker(
#             serial=self.serial,
#             message_logger=message_logger,

#         )
#         worker._run(pipe_in)

class TestNayaxServer(EventListener):
    def __init__(
        self,
        name: str,
        port: int,
        address: str,
        serial: str,
        message_logger=None,
    ):
        self.serial = serial
        self.check_local_data_frequency = 1
        super().__init__(
            name=name,
            address=address,
            port=port,
            message_logger=message_logger,
        )
        self._nayax_connector = NayaxConnector(core=3, serial=self.serial, message_logger=message_logger)
        self._nayax_connector._connect()
        self.start()

    async def on_start(self):
        pass

    async def _check_local_data(self):  # MARK: CHECK LOCAL DATA
        info(f"NAYAX STATUS: {self._nayax_connector.state} {self._nayax_connector.last_payment_result}", message_logger=self._message_logger)
        if self._nayax_connector.state == MdbStatus.IDLE:
            # warning(f"NAYAX in ERROR state, reconnecting...", message_logger=self._message_logger)
            self._nayax_connector.charge(0.09)

    async def _analyze_event(self, event: Event) -> bool:
        """
        Analizuje i obsługuje zdarzenia przychodzące do Orchestratora.

        Obsługuje m.in. aktualizację stanów klientów dla zdarzeń
        `CMD_GET_STATE` i `CMD_HEALTH_CHECK` oraz porządkuje listę
        przetwarzanych zdarzeń.

        Args:
            event (Event): Otrzymane zdarzenie.

        Returns:
            bool: Zawsze True (zdarzenie zostało obsłużone).
        """
        match event.event_type:
            case "nayax_charge":
                self._add_to_processing(event)
                self._nayax_connector.charge(Decimal(event.data["charge"]))
                pass

            case _:
                pass
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="supervisor server")
    temp_path = os.path.abspath("temp")
    # message_logger = MessageLogger(
    #     filename=f"{temp_path}/test_nayax_server.log",
    #     period=LoggerPolicyPeriod.LAST_15_MINUTES,
    #     core=3,
    # )
    message_logger = None
    try:
        app = TestNayaxServer(
            name=f"io",
            address="127.0.0.1",
            port=8001,
            message_logger=message_logger,
            serial='/dev/ttyS0',  )

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
    finally:
        try:
            # supervisor.cleanup()
            pass
        except NameError:
            pass
