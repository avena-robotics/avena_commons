import importlib
import threading
import time
from enum import Enum

try:
    import pysoem
except ImportError as e:
    print(f"Failed to import pysoem: {e}")


from avena_commons.util.control_loop import ControlLoop
from avena_commons.util.logger import debug, error, info, warning
from avena_commons.util.worker import Connector, Worker


class EtherCATState(Enum):
    PREINIT = 0
    INIT = 1
    CONFIG = 2
    RUNNING = 3
    STOPPED = 4


class PysoemStates(Enum):
    NONE_STATE = 0
    INIT_STATE = 1
    PREOP_STATE = 2
    BOOT_STATE = 3
    SAFEOP_STATE = 4
    OP_STATE = 8
    STATE_ACK = 100
    STATE_ERROR = 200


class EtherCATWorker(Worker):
    def __init__(
        self,
        device_name: str,
        network_interface: str,
        number_of_devices: int,
        message_logger=None,
    ):
        self.device_name = device_name
        self._period = 1 / 2000
        self._message_logger = message_logger
        super().__init__(message_logger)
        self.master = pysoem.Master()

        self._slaves = []

        # CONFIG INFO
        self._network_interface = network_interface
        self._number_of_devices = number_of_devices

        self._ethercat_state = EtherCATState.PREINIT

    def _init(self):
        self.master.open(self._network_interface)
        number_of_slaves = self.master.config_init()
        info(
            f"{self.device_name} - odpytanie ile urzadzen jest w sieci: {number_of_slaves}",
            message_logger=self._message_logger,
        )

        if number_of_slaves != self._number_of_devices:
            error(
                f"{self.device_name} - Number of devices ({number_of_slaves}) does not match the expected number of devices ({self._number_of_devices})",
                message_logger=self._message_logger,
            )
            raise Exception(
                f"{self.device_name} - Number of devices ({number_of_slaves}) does not match the expected number of devices ({self._number_of_devices})"
            )
        else:
            info(
                f"{self.device_name} - Number of devices ({number_of_slaves}) matches the expected number of devices ({self._number_of_devices})",
                message_logger=self._message_logger,
            )
            for i, slave in enumerate(self.master.slaves):
                slave_name = slave.name
                slave_vendor_code = slave.man
                slave_product_code = slave.id
                info(
                    f"Slave {slave_name} at address {i} with vendor code {slave_vendor_code} and product code {slave_product_code}",
                    message_logger=self._message_logger,
                )

    def _process(self):
        ret = self.master.receive_processdata(10000)
        # info(f"Receive processdata: {ret}", message_logger=self._message_logger)
        if ret == 0:
            error(
                f"Error receiving processdata: {ret}",
                message_logger=self._message_logger,
            )
            return

        for slave in self._slaves:
            slave._read_pdo()
            slave._process()
            slave._write_pdo()
        # self._slaves[0]._read_pdo()
        # self._slaves[0]._process()
        # self._slaves[0]._write_pdo()

        ret = self.master.send_processdata()
        # info(f"Send processdata: {ret}", message_logger=self._message_logger)
        if ret == 0:
            error(
                f"Error sending processdata: {ret}", message_logger=self._message_logger
            )
            return
        state = self.master.read_state()
        if state != pysoem.OP_STATE:
            warning(
                f"Network state: {PysoemStates(state).name}",
                message_logger=self._message_logger,
            )
            self.master.state = pysoem.OP_STATE
            self.master.write_state()
        else:
            # info(f"Network state: {PysoemStates(state).name}", message_logger=self._message_logger)
            pass

    def _add_device(self, device_args: list):
        device_class = device_args[4].lower()
        module_path = f"avena_commons.io.device.io.{device_class}"
        module = importlib.import_module(module_path)
        device_class = f"{device_class.upper()}_Slave"
        device = getattr(module, device_class)
        device = device(
            device_name=device_args[0],
            master=self.master,
            address=device_args[3],
            config=device_args[5],
            message_logger=self._message_logger,
        )
        self._slaves.append(device)

    def _configure(self, slave_args: list):
        for slave_arg in slave_args:
            device_name = slave_arg[0]
            slave_product_code = slave_arg[1]
            slave_vendor_code = slave_arg[2]
            slave_address = slave_arg[3]
            info(f"Slave Config: {slave_arg[5]}", message_logger=self._message_logger)

            if (
                self.master.slaves[slave_address].id == slave_product_code
                and self.master.slaves[slave_address].man == slave_vendor_code
            ):
                self._add_device(slave_arg)
                self.master.slaves[slave_address].config_func = self._slaves[
                    slave_address
                ]._config_function  # przypisanie funkcji konfiguracji do slave
            else:
                error(
                    f"Slave {slave_address} at address {slave_address} with vendor code {slave_vendor_code} and product code {slave_product_code} does not match the expected vendor code {self._master.slaves[slave_address].man} and product code {self._master.slaves[slave_address].id}",
                    message_logger=self._message_logger,
                )
                raise Exception(
                    f"Slave {slave_address} at address {slave_address} with vendor code {slave_vendor_code} and product code {slave_product_code} does not match the expected vendor code {self._master.slaves[slave_address].man} and product code {self._master.slaves[slave_address].id}"
                )

        for (
            slave
        ) in self.master.slaves:  # zmiana trybu slave na mozliwe do konfiguracji
            slave.state = pysoem.PREOP_STATE
            slave.write_state()

        for (
            slave
        ) in self.master.slaves:  # zmiana trybu slave na mozliwe do konfiguracji
            if slave.state != pysoem.PREOP_STATE:
                info(
                    f"Slave {slave.name} is not in PREOP_STATE state",
                    message_logger=self._message_logger,
                )
            else:
                info(
                    f"Slave {slave.name} is in PREOP_STATE state",
                    message_logger=self._message_logger,
                )

        # TODO: ADD CHECKS
        # ret = self.master.config_map()
        # info(f"Configuring devices: {ret}", message_logger=self._message_logger)
        try:
            self.master.config_map()  # budowanie mapy komunikatow - pobranie od slave
        except Exception as e:
            error(f"Error: {e}", message_logger=self._message_logger)

        if (
            self.master.state_check(pysoem.SAFEOP_STATE, timeout=50_000)
            != pysoem.SAFEOP_STATE
        ):
            info(
                "Not all slaves reached SAFEOP state",
                message_logger=self._message_logger,
            )
        else:
            info("All slaves reached SAFEOP state", message_logger=self._message_logger)
        self.master.config_dc()
        # info("Configuring dc", message_logger=self._message_logger)
        self.master.state = pysoem.OP_STATE
        self.master.write_state()

        state = self.master.read_state()
        if state != pysoem.OP_STATE:
            self.master.state = pysoem.OP_STATE
            self.master.write_state()
        info(
            f"Network state: {PysoemStates(state).name}",
            message_logger=self._message_logger,
        )

        self._ethercat_state = EtherCATState.RUNNING
        info(f"Read initializes state", message_logger=self._message_logger)
        self._process()
        info(f"End of configure", message_logger=self._message_logger)

    def _run(self, pipe_in):
        info(
            f"{self.device_name} - Starting EtherCATWorker {self._period}",
            message_logger=self._message_logger,
        )
        cl = ControlLoop(
            "control_loop_ethercat",
            period=self._period,
            message_logger=self._message_logger,
            warning_printer=False,
        )

        self._init()

        try:
            while True:
                cl.loop_begin()

                if pipe_in.poll(0.00005):
                    data = pipe_in.recv()
                    match data[0]:
                        case "STOP":
                            self.master.close()
                            info(
                                f"{self.device_name} - Stopping control_loop_ethercat subprocess",
                                message_logger=self._message_logger,
                            )
                            break
                        case "CONFIG":
                            info(
                                f"{self.device_name} - CONFIG: ADDRESS:{data[1]}",
                                message_logger=self._message_logger,
                            )
                            self._ethercat_state = EtherCATState.CONFIG
                            self._configure(data[1])
                            pipe_in.send(True)
                        case "READ_INPUT":
                            value = self._slaves[data[1]].read_input(data[2])
                            info(
                                f"{self.device_name} - READ_INPUT: ADDRESS:{data[1]} DI:{data[2]} VALUE:{value}",
                                message_logger=self._message_logger,
                            )
                            pipe_in.send(value)
                        case "READ_OUTPUT":
                            value = self._slaves[data[1]].read_output(data[2])
                            info(
                                f"{self.device_name} - READ_OUTPUT: ADDRESS:{data[1]} DO:{data[2]} VALUE:{value}",
                                message_logger=self._message_logger,
                            )
                            pipe_in.send(value)
                        case "WRITE_OUTPUT":
                            # info(f"{self.device_name} - WRITE_OUTPUT, {data[1]}, {data[2]}, {data[3]}", message_logger=self._message_logger)
                            self._slaves[data[1]].write_output(data[2], data[3])
                            pipe_in.send(True)
                        case "START_AXIS_POS_PROFILE":
                            info(
                                f"{self.device_name} - START_AXIS_POS_PROFILE, {data[1]}, {data[2]}, {data[3]}, {data[4]}, {data[5]}",
                                message_logger=self._message_logger,
                            )
                            self._slaves[data[1]].start_axis_pos_profile(
                                data[2], data[3], data[4], data[5]
                            )
                            pipe_in.send(True)
                        case "START_AXIS_VEL_PROFILE":
                            info(
                                f"{self.device_name} - START_AXIS_VEL_PROFILE, {data[1]}, {data[2]}, {data[3]}, {data[4]}",
                                message_logger=self._message_logger,
                            )
                            self._slaves[data[1]].start_axis_vel_profile(
                                data[2], data[3], data[4]
                            )
                            pipe_in.send(True)
                        case "STOP_AXIS":
                            info(
                                f"{self.device_name} - STOP_AXIS, {data[1]}, {data[2]}",
                                message_logger=self._message_logger,
                            )
                            self._slaves[data[1]].stop_axis(data[2])
                            pipe_in.send(True)
                        case "AXIS_IN_MOVE":
                            info(
                                f"{self.device_name} - AXIS_IN_MOVE, {data[1]}, {data[2]}",
                                message_logger=self._message_logger,
                            )
                            value = self._slaves[data[1]].in_move(data[2])
                            pipe_in.send(value)
                        case _:
                            error(
                                f"{self.device_name} - Unknown command: {data[0]}",
                                message_logger=self._message_logger,
                            )

                if self._ethercat_state == EtherCATState.RUNNING:
                    self._process()

                    if cl.loop_counter % 1000 == 0:
                        debug(
                            f"SLAVE 0: INPUT {self.master.slaves[0].input} || OUTPUT {self.master.slaves[0].output}",
                            message_logger=self._message_logger,
                        )
                        debug(
                            f"SLAVE 1: INPUT {self.master.slaves[1].input} || OUTPUT {self.master.slaves[1].output}",
                            message_logger=self._message_logger,
                        )

                cl.loop_end()

        except Exception as e:
            error(
                f"{self.device_name} - Error in EtherCATWorker: {e}",
                message_logger=self._message_logger,
            )
            raise e


class EtherCAT(Connector):
    def __init__(
        self,
        device_name: str,
        network_interface: str,
        number_of_devices: int,
        message_logger=None,
    ):
        self.device_name = device_name
        self._network_interface = network_interface
        self._number_of_devices = number_of_devices
        self._message_logger = message_logger
        super().__init__(message_logger=self._message_logger)

        debug(
            f"{self.device_name} - Initializing {self.__class__.__name__} with network interface {self._network_interface} and {self._number_of_devices} devices",
            message_logger=self._message_logger,
        )

        super()._connect()
        self.__lock = threading.Lock()

        time.sleep(1)  # TODO: REMOVE THIS AND MAKE THIS WAIT FOT THE BUS TO BE READY

    def _run(self, pipe_in, message_logger):
        self.__lock = threading.Lock()
        debug(
            f"{self.device_name} - Starting {self.__class__.__name__} subprocess",
            message_logger=message_logger,
        )
        worker = EtherCATWorker(
            device_name=self.device_name,
            network_interface=self._network_interface,
            number_of_devices=self._number_of_devices,
            message_logger=message_logger,
        )
        try:
            worker._run(pipe_in)
        except KeyboardInterrupt:
            pass

    def configure(self, dict_of_slaves: dict):
        list_of_slaves = []
        for slave_name in dict_of_slaves:
            if (
                dict_of_slaves[slave_name].bus.__class__.__name__
                == self.__class__.__name__
            ):
                slave_product_code = dict_of_slaves[slave_name].product_code
                slave_vendor_code = dict_of_slaves[slave_name].vendor_code
                slave_address = dict_of_slaves[slave_name].address
                slave_class = dict_of_slaves[slave_name].__class__.__name__
                slave_config = dict_of_slaves[slave_name].configuration
                list_of_slaves.append([
                    slave_name,
                    slave_product_code,
                    slave_vendor_code,
                    slave_address,
                    slave_class,
                    slave_config,
                ])
        debug(
            f"{self.device_name} - Configuring {self.__class__.__name__} with {len(list_of_slaves)} slaves",
            message_logger=self._message_logger,
        )

        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["CONFIG", list_of_slaves])
            return value

    def read_input(self, address: int, port: int):
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out, ["READ_INPUT", address, port]
            )
            return value

    def write_output(self, address: int, port: int, value: bool):
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out, ["WRITE_OUTPUT", address, port, value]
            )
            return value

    def start_axis_pos_profile(
        self, address: int, axis: int, pos: int, vel: int, direction: bool
    ):
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out,
                ["START_AXIS_POS_PROFILE", address, axis, pos, vel, direction],
            )
            return value

    def start_axis_vel_profile(
        self, address: int, axis: int, vel: int, direction: bool
    ):
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out,
                ["START_AXIS_VEL_PROFILE", address, axis, vel, direction],
            )
            return value

    def stop_axis(self, address: int, axis: int):
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out, ["STOP_AXIS", address, axis]
            )
            return value

    def axis_in_move(self, address: int, axis: int):
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out, ["AXIS_IN_MOVE", address, axis]
            )
            return value
