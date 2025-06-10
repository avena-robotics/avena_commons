import time
from enum import Enum

from avena_commons.util.logger import MessageLogger, debug, error, info

from .EtherCatSlave import EtherCatDevice, EtherCatSlave
from .io_utils import init_device_di, init_device_do


class ImpulseFSM(Enum):
    IDLE = 0
    POS_PROFILE_START = 1
    POS_PROFILE_RUN = 2
    VEL_PROFILE_START = 3
    VEL_PROFILE_RUN = 4
    STOP = 5


class ImpulseAxis:
    def __init__(
        self,
        device_name: str,
        pulse_port: int,
        direction_port: int,
        message_logger: MessageLogger | None = None,
    ):
        self.device_name = device_name
        self.pulse_port = pulse_port
        self.direction_port = direction_port
        self.ImpulseFSM = ImpulseFSM.IDLE
        self.message_logger = message_logger

        self.pulse_counter = 0
        self.velocity = 0  # pulse/sec
        self.last_pulse_time = 0
        self.pulse_state = False
        self.direction_state = False

    def process(self):
        match self.ImpulseFSM:
            case ImpulseFSM.IDLE:
                pass
            case ImpulseFSM.VEL_PROFILE_START:
                self._vel_profile_start()
            case ImpulseFSM.POS_PROFILE_START:
                self._pos_profile_start()
            case ImpulseFSM.VEL_PROFILE_RUN:
                self._vel_profile_run()
            case ImpulseFSM.POS_PROFILE_RUN:
                self._pos_profile_run()
            case ImpulseFSM.STOP:
                self._stop()

        return self.pulse_state, self.direction_state

    def start_pos_profile(self, pos, vel, direction):
        if self.ImpulseFSM == ImpulseFSM.IDLE:
            self.ImpulseFSM = ImpulseFSM.POS_PROFILE_START
            self.velocity = vel
            self.position = pos
            self.direction_state = direction
        else:
            error(
                f"{self.device_name} - ImpulseAxis {self.pulse_port} is not idle",
                message_logger=self.message_logger,
            )

    def start_vel_profile(self, vel, direction):
        if self.ImpulseFSM == ImpulseFSM.IDLE:
            self.ImpulseFSM = ImpulseFSM.VEL_PROFILE_START
            self.velocity = vel
            self.direction_state = direction
        else:
            error(
                f"{self.device_name} - ImpulseAxis {self.pulse_port} is not idle",
                message_logger=self.message_logger,
            )

    def stop(self):
        self.ImpulseFSM = ImpulseFSM.STOP

    def _vel_profile_start(self):
        self.pulse_counter = 0
        self.output_change_time = (
            1 / self.velocity
        ) / 2  # TODO: Check if this is correct
        info(
            f"{self.device_name} - output_change_time: {self.output_change_time}",
            message_logger=self.message_logger,
        )
        self.ImpulseFSM = ImpulseFSM.VEL_PROFILE_RUN

    def _pos_profile_start(self):
        self.pulse_counter = 0
        self.output_change_time = (
            1 / self.velocity
        ) / 2  # TODO: Check if this is correct
        self.ImpulseFSM = ImpulseFSM.POS_PROFILE_RUN

    def _pos_profile_run(self):
        current_time = time.time()
        if current_time - self.last_pulse_time >= self.output_change_time:
            self.pulse_state = not self.pulse_state
            if self.pulse_state:
                self.pulse_counter = self.pulse_counter + 1
            self.last_pulse_time = current_time

        if self.pulse_counter >= self.position:
            self.ImpulseFSM = ImpulseFSM.STOP

    def _vel_profile_run(self):
        current_time = time.time()
        info(
            f"{self.device_name} - time_change {current_time - self.last_pulse_time} output_change_time: {self.output_change_time}",
            message_logger=self.message_logger,
        )
        if current_time - self.last_pulse_time >= self.output_change_time:
            info(
                f"{self.device_name} - PULSE CHANGE", message_logger=self.message_logger
            )
            self.pulse_state = not self.pulse_state
            if self.pulse_state:
                self.pulse_counter = self.pulse_counter + 1
            self.last_pulse_time = current_time

    def _stop(self):
        self.ImpulseFSM = ImpulseFSM.IDLE
        self.pulse_state = False
        self.direction_state = False


class EC3A_IO1632_Slave(EtherCatSlave):
    def __init__(
        self,
        device_name: str,
        master,
        address,
        config,
        message_logger: MessageLogger | None = None,
        debug=True,
    ):
        super().__init__(master, address, message_logger, debug)
        self.device_name = device_name
        self.inputs_ports = [0 for _ in range(16)]
        self.outputs_ports = [0 for _ in range(16)]
        self.previous_outputs = [0 for _ in range(16)]
        axis_list = config["axis"]
        self.axis = []
        for axis in axis_list:
            self.axis.append(
                ImpulseAxis(
                    device_name,
                    axis["pulse_port"],
                    axis["direction_port"],
                    self.message_logger,
                )
            )

    def _config_function(self, slave_pos):
        debug(
            f"{self.device_name} - Configuring {self.address} {slave_pos}",
            message_logger=self.message_logger,
        )

    def _read_pdo(self):
        # info(f"Reading PDO {self.address}", message_logger=self.message_logger)
        input_bytes = self.master.slaves[self.address].input
        input_value = int.from_bytes(input_bytes, byteorder="little")

        for i in range(16):
            value = (input_value >> i) & 1
            if value != self.inputs_ports[i]:
                self.inputs_ports[i] = value
                info(
                    f"{self.device_name} - read input port ADDR: {self.address} PORT: {i} changed to {int(value)}",
                    message_logger=self.message_logger,
                )

    def _write_pdo(self):
        # output_bytes = self.master.slaves[self.address].output
        # info(f"output_bytes: {output_bytes}", message_logger=self.message_logger)
        # output_value = int.from_bytes(output_bytes, byteorder='little')
        # output_value = output_value + 1
        # if output_value > 65535:
        #     output_value = 0
        # output_bytes = output_value.to_bytes(2, byteorder='little')
        # self.master.slaves[self.address].output = output_bytes

        # info(f"Writing PDO {self.address}", message_logger=self.message_logger)
        # Convert first 8 bits (0-7) to first byte
        first_byte = 0
        for i in range(8):
            if self.outputs_ports[i]:
                first_byte |= 1 << i

        # Convert second 8 bits (8-15) to second byte
        second_byte = 0
        for i in range(8):
            if self.outputs_ports[i + 8]:
                second_byte |= 1 << i

        output_bytes = bytes([first_byte, second_byte])
        # info(f"{self.device_name} - output_regs: {self.outputs_ports}", message_logger=self.message_logger)
        # info(f"{self.device_name} - output_bytes: {output_bytes}", message_logger=self.message_logger)
        if output_bytes != self.master.slaves[self.address].output:
            self.master.slaves[self.address].output = output_bytes
            for i in range(16):
                if self.outputs_ports[i] != self.previous_outputs[i]:
                    info(
                        f"{self.device_name} - write output port ADDR: {self.address} PORT: {i} changed to {int(self.outputs_ports[i])} ",
                        message_logger=self.message_logger,
                    )
                    self.previous_outputs[i] = self.outputs_ports[i]

    def axis_process(self):
        for axis in self.axis:
            output_state, direction_state = axis.process()

            self.outputs_ports[axis.pulse_port] = output_state
            self.outputs_ports[axis.direction_port] = direction_state

    def _process(self):
        # info(f"Processing {self.address}", message_logger=self.message_logger)
        self.axis_process()

    def read_input(self, port: int):
        return self.inputs_ports[port]

    def write_output(self, port: int, value: bool):
        self.outputs_ports[port] = value

    def start_axis_pos_profile(self, axis: int, pos: int, vel: int, direction: bool):
        print(f"Starting axis {axis} pos profile {pos} {vel} {direction}")
        self.axis[axis].start_pos_profile(pos, vel, direction)

    def start_axis_vel_profile(self, axis: int, vel: int, direction: bool):
        print(f"Starting axis {axis} vel profile {vel} {direction}")
        self.axis[axis].start_vel_profile(vel, direction)

    def stop_axis(self, axis: int):
        print(f"Stopping axis {axis}")
        self.axis[axis].stop()

    def in_move(self, axis: int):
        if (
            self.axis[axis].ImpulseFSM == ImpulseFSM.POS_PROFILE_RUN
            or self.axis[axis].ImpulseFSM == ImpulseFSM.VEL_PROFILE_RUN
        ):
            return True
        else:
            return False


class EC3A_IO1632(EtherCatDevice):
    def __init__(
        self,
        device_name: str,
        bus,
        address,
        axis=list,
        message_logger: MessageLogger | None = None,
        debug=True,
    ):
        self.device_name = device_name
        product_code = 4353
        vendor_code = 2965
        info(f"{self.device_name} - Axis config: {axis}", message_logger=message_logger)
        self.number_of_axis = len(axis)
        configuration = {"axis": axis}
        super().__init__(
            bus,
            vendor_code,
            product_code,
            address,
            configuration,
            message_logger,
            debug,
        )
        self.inputs_ports = [0 for _ in range(16)]
        self.outputs_ports = [0 for _ in range(16)]
        # init_device_di(self, 16)
        # init_device_do(self, 16)

    def _read_input(self, port: int):
        self.inputs_ports[port] = self.bus.read_input(self.address, port)
        return self.inputs_ports[port]

    def _read_output(self, port: int):
        return self.outputs_ports[port]

    def _write_output(self, port: int, value: bool):
        self.outputs_ports[port] = value
        # debug(f"{self.device_name} - Writing output {port} to {value}", message_logger=self.message_logger)
        self.bus.write_output(self.address, port, value)

    def _start_axis_pos_profile(
        self, axis: int, position: int, velocity: int, direction: bool
    ):
        debug(
            f"{self.device_name}: Axis={axis}, start_axis_pos, position={position}, velocity={velocity}, direction={direction}",
            message_logger=self.message_logger,
        )
        self.bus.start_axis_pos_profile(
            self.address, axis, position, velocity, direction
        )

    def _start_axis_vel_profile(self, axis: int, velocity: int, direction: bool):
        debug(
            f"{self.device_name}: Axis={axis}, start_axis_pos, velocity={velocity}, direction={direction}",
            message_logger=self.message_logger,
        )
        self.bus.start_axis_vel_profile(self.address, axis, velocity, direction)

    def _stop_axis(self, axis: int):
        self.bus.stop_axis(self.address, axis)
        debug(
            f"{self.device_name}: Axis={axis}, stop_axis",
            message_logger=self.message_logger,
        )

    def _axis_in_move(self, axis: int):
        return self.bus.axis_in_move(self.address, axis)

    def di(self, index: int):
        return self._read_input(index)

    def do(self, index: int, value: bool = None):
        if value is None:
            return self._read_output(index)
        else:
            return self._write_output(index, value)

    def start_axis_pos_profile_0(self, position: int, velocity: int, direction: bool):
        return self._start_axis_pos_profile(0, position, velocity, direction)

    def start_axis_pos_profile_1(self, position: int, velocity: int, direction: bool):
        return self._start_axis_pos_profile(1, position, velocity, direction)

    def start_axis_pos_profile_2(self, position: int, velocity: int, direction: bool):
        return self._start_axis_pos_profile(2, position, velocity, direction)

    def start_axis_pos_profile_3(self, position: int, velocity: int, direction: bool):
        return self._start_axis_pos_profile(3, position, velocity, direction)

    def start_axis_pos_profile_4(self, position: int, velocity: int, direction: bool):
        return self._start_axis_pos_profile(4, position, velocity, direction)

    def start_axis_pos_profile_5(self, position: int, velocity: int, direction: bool):
        return self._start_axis_pos_profile(5, position, velocity, direction)

    def start_axis_pos_profile_6(self, position: int, velocity: int, direction: bool):
        return self._start_axis_pos_profile(6, position, velocity, direction)

    def start_axis_pos_profile_7(self, position: int, velocity: int, direction: bool):
        return self._start_axis_pos_profile(7, position, velocity, direction)

    def start_axis_vel_profile_0(self, velocity: int, direction: bool):
        return self._start_axis_vel_profile(0, velocity, direction)

    def start_axis_vel_profile_1(self, velocity: int, direction: bool):
        return self._start_axis_vel_profile(1, velocity, direction)

    def start_axis_vel_profile_2(self, velocity: int, direction: bool):
        return self._start_axis_vel_profile(2, velocity, direction)

    def start_axis_vel_profile_3(self, velocity: int, direction: bool):
        return self._start_axis_vel_profile(3, velocity, direction)

    def start_axis_vel_profile_4(self, velocity: int, direction: bool):
        return self._start_axis_vel_profile(4, velocity, direction)

    def start_axis_vel_profile_5(self, velocity: int, direction: bool):
        return self._start_axis_vel_profile(5, velocity, direction)

    def start_axis_vel_profile_6(self, velocity: int, direction: bool):
        return self._start_axis_vel_profile(6, velocity, direction)

    def start_axis_vel_profile_7(self, velocity: int, direction: bool):
        return self._start_axis_vel_profile(7, velocity, direction)

    def stop_axis_0(self):
        return self._stop_axis(0)

    def stop_axis_1(self):
        return self._stop_axis(1)

    def stop_axis_2(self):
        return self._stop_axis(2)

    def stop_axis_3(self):
        return self._stop_axis(3)

    def stop_axis_4(self):
        return self._stop_axis(4)

    def stop_axis_5(self):
        return self._stop_axis(5)

    def stop_axis_6(self):
        return self._stop_axis(6)

    def stop_axis_7(self):
        return self._stop_axis(7)

    def axis_in_move_0(self):
        return self._axis_in_move(0)

    def axis_in_move_1(self):
        return self._axis_in_move(1)

    def axis_in_move_2(self):
        return self._axis_in_move(2)

    def axis_in_move_3(self):
        return self._axis_in_move(3)

    def axis_in_move_4(self):
        return self._axis_in_move(4)

    def axis_in_move_5(self):
        return self._axis_in_move(5)

    def axis_in_move_6(self):
        return self._axis_in_move(6)

    def axis_in_move_7(self):
        return self._axis_in_move(7)

    def check_device_connection(self) -> bool:
        return True


init_device_di(EC3A_IO1632, first_index=0, count=16)
init_device_do(EC3A_IO1632, first_index=0, count=16)
