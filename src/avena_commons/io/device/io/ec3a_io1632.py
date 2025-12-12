import time
from enum import Enum

from avena_commons.util.logger import MessageLogger, debug, error, info

from ..io_utils import init_device_di, init_device_do
from .EtherCatSlave import EtherCatDevice, EtherCatSlave


class ImpulseFSM(Enum):
    """Enum stanów wewnętrznego FSM osi impulsowej."""

    IDLE = 0
    POS_PROFILE_START = 1
    POS_PROFILE_RUN = 2
    VEL_PROFILE_START = 3
    VEL_PROFILE_RUN = 4
    STOP = 5

class MotorWithEndstopsFSM(Enum):
    """Enum stanów wewnętrznego FSM osi z krańcówkami."""

    IDLE = 0
    MOVING_UP = 1
    MOVING_DOWN = 2
    STOPPING = 3

class MotorWithEndstopsAxis:
    def __init__(self):
        self.direction_output_port = 0
        self.power_output_port = 1
        self.up_endstop_input_port = 0
        self.down_endstop_input_port = 1
        
        self.fsm = MotorWithEndstopsFSM.IDLE
        self.power_output_state = False
        self.direction_output_state = False
    
    def process(self, up_endstop_state: bool, down_endstop_state: bool):
        match self.fsm:
            case MotorWithEndstopsFSM.IDLE:
                self.power_output_state = False
                self.direction_output_state = False
            case MotorWithEndstopsFSM.MOVING_UP:
                self.power_output_state = True
                self.direction_output_state = True

                if up_endstop_state:
                    self.power_output_port = False
                    self.fsm = MotorWithEndstopsFSM.IDLE
            case MotorWithEndstopsFSM.MOVING_DOWN:
                self.power_output_state = True
                self.direction_output_state = False

                if down_endstop_state:
                    self.power_output_port = False
                    self.fsm = MotorWithEndstopsFSM.IDLE
    
        return self.power_output_state, self.direction_output_state
    
    def move_up(self):
        self.fsm = MotorWithEndstopsFSM.MOVING_UP
    
    def move_down(self):
        self.fsm = MotorWithEndstopsFSM.MOVING_DOWN
    
    def stop(self):
        self.fsm = MotorWithEndstopsFSM.IDLE
    

class ImpulseAxis:
    """Symulator osi impulsowej generującej sygnały PULSE/DIR.

    Args:
        device_name (str): Nazwa urządzenia (do logowania).
        pulse_port (int): Numer portu wyjściowego dla impulsów.
        direction_port (int): Numer portu wyjściowego dla kierunku.
        message_logger (MessageLogger | None): Logger wiadomości.
    """

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
        """Przetwarza jeden krok FSM osi i wylicza stany PULSE/DIR.

        Returns:
            tuple[bool, bool]: Krotka (pulse_state, direction_state).
        """
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
        """Rozpoczyna profil pozycyjny.

        Args:
            pos (int): Docelowa liczba impulsów.
            vel (int): Prędkość (imp/s).
            direction (bool): Kierunek ruchu.
        """
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
        """Rozpoczyna profil prędkościowy.

        Args:
            vel (int): Prędkość (imp/s).
            direction (bool): Kierunek ruchu.
        """
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
        """Zatrzymuje oś (przejście do STOP)."""
        self.ImpulseFSM = ImpulseFSM.STOP

    def _vel_profile_start(self):
        """Inicjuje parametry profilu prędkościowego i przechodzi do RUN."""
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
        """Inicjuje parametry profilu pozycyjnego i przechodzi do RUN."""
        self.pulse_counter = 0
        self.output_change_time = (
            1 / self.velocity
        ) / 2  # TODO: Check if this is correct
        self.ImpulseFSM = ImpulseFSM.POS_PROFILE_RUN

    def _pos_profile_run(self):
        """Główna logika generacji impulsów dla profilu pozycyjnego."""
        current_time = time.time()
        if current_time - self.last_pulse_time >= self.output_change_time:
            self.pulse_state = not self.pulse_state
            if self.pulse_state:
                self.pulse_counter = self.pulse_counter + 1
            self.last_pulse_time = current_time

        if self.pulse_counter >= self.position:
            self.ImpulseFSM = ImpulseFSM.STOP

    def _vel_profile_run(self):
        """Główna logika generacji impulsów dla profilu prędkościowego."""
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
        """Czyści stany i ustawia FSM na IDLE."""
        self.ImpulseFSM = ImpulseFSM.IDLE
        self.pulse_state = False
        self.direction_state = False


class EC3A_IO1632_Slave(EtherCatSlave):
    """Slave EC3A IO 16xDI/16xDO z obsługą osi impulsowych.

    Args:
        device_name (str): Nazwa urządzenia.
        master: Obiekt mastera EtherCAT.
        address: Adres slave'a.
        config (dict): Konfiguracja zawierająca listę osi.
        message_logger (MessageLogger | None): Logger wiadomości.
        debug (bool): Flaga debugowania.
    """

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
        motor_with_endstops_axis_list = config.get("motor_with_endstops_axis", [])
        self.axis = []
        self.motor_with_endstops_axis = []
        for axis in axis_list:
            self.axis.append(    
                ImpulseAxis(
                    device_name,
                    axis["pulse_port"],
                    axis["direction_port"],
                    self.message_logger,
                )
            )
        for axis in motor_with_endstops_axis_list:
            self.motor_with_endstops_axis.append(
                MotorWithEndstopsAxis(
                    device_name,
                    axis["power_output_port"],
                    axis["direction_output_port"],
                    axis["up_endstop_input_port"],
                    axis["down_endstop_input_port"],
                    self.message_logger
                )
            )

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
        """Odczytuje wejścia cyfrowe z PDO i aktualizuje `inputs_ports`."""
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
        """Zapisuje wyjścia cyfrowe do PDO na podstawie `outputs_ports`."""
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
        """Aktualizuje stany wyjść na podstawie przetwarzania wszystkich osi."""
        for axis in self.axis:
            output_state, direction_state = axis.process()

            self.outputs_ports[axis.pulse_port] = output_state
            self.outputs_ports[axis.direction_port] = direction_state
        
        for axis in self.motor_with_endstops_axis:
            up_endstop_state = self.inputs_ports[axis.up_endstop_input_port]
            down_endstop_state = self.inputs_ports[axis.down_endstop_input_port]
            power_output_state, direction_output_state = axis.process(up_endstop_state, down_endstop_state)

            self.outputs_ports[axis.power_output_port] = power_output_state
            self.outputs_ports[axis.direction_output_port] = direction_output_state

    def _process(self):
        """Główna pętla przetwarzania urządzenia (wywoływana cyklicznie)."""
        # info(f"Processing {self.address}", message_logger=self.message_logger)
        self.axis_process()

    def read_input(self, port: int):
        """Zwraca stan wejścia cyfrowego.

        Args:
            port (int): Numer portu 0..15.
        """
        return self.inputs_ports[port]

    def write_output(self, port: int, value: bool):
        """Ustawia stan wyjścia cyfrowego w buforze.

        Args:
            port (int): Numer portu 0..15.
            value (bool): Wartość do ustawienia.
        """
        self.outputs_ports[port] = value

    def start_axis_pos_profile(self, axis: int, pos: int, vel: int, direction: bool):
        """Rozpoczyna profil pozycyjny na wskazanej osi."""
        print(f"Starting axis {axis} pos profile {pos} {vel} {direction}")
        self.axis[axis].start_pos_profile(pos, vel, direction)

    def start_axis_vel_profile(self, axis: int, vel: int, direction: bool):
        """Rozpoczyna profil prędkościowy na wskazanej osi."""
        print(f"Starting axis {axis} vel profile {vel} {direction}")
        self.axis[axis].start_vel_profile(vel, direction)

    def stop_axis(self, axis: int):
        """Zatrzymuje wskazaną oś."""
        print(f"Stopping axis {axis}")
        self.axis[axis].stop()

    def in_move(self, axis: int):
        """Informuje, czy wskazana oś jest w ruchu (w trakcie profilu)."""
        if (
            self.axis[axis].ImpulseFSM == ImpulseFSM.POS_PROFILE_RUN
            or self.axis[axis].ImpulseFSM == ImpulseFSM.VEL_PROFILE_RUN
        ):
            return True
        else:
            return False

    def __str__(self) -> str:
        """Reprezentacja slave'a EC3A_IO1632"""
        try:
            # Określenie stanu osi
            active_axes = sum(
                1 for axis in self.axis if axis.ImpulseFSM != ImpulseFSM.IDLE
            )

            return (
                f"EC3A_IO1632_Slave(name='{self.device_name}', "
                f"addr={self.address}, "
                f"axes={len(self.axis)}, "
                f"active_axes={active_axes}, "
                f"DI={bin(sum(self.inputs_ports[i] << i for i in range(16)))}, "
                f"DO={bin(sum(self.outputs_ports[i] << i for i in range(16)))})"
            )
        except Exception as e:
            return f"EC3A_IO1632_Slave(name='{self.device_name}', error='{str(e)}')"

    def __repr__(self) -> str:
        """Szczegółowa reprezentacja dla developerów"""
        try:
            axis_states = [axis.ImpulseFSM.name for axis in self.axis]
            return (
                f"EC3A_IO1632_Slave(device_name='{self.device_name}', "
                f"address={self.address}, "
                f"debug={self.debug}, "
                f"axis_count={len(self.axis)}, "
                f"axis_states={axis_states}, "
                f"inputs_ports={self.inputs_ports}, "
                f"outputs_ports={self.outputs_ports})"
            )
        except Exception as e:
            return (
                f"EC3A_IO1632_Slave(device_name='{self.device_name}', error='{str(e)}')"
            )

    def to_dict(self) -> dict:
        """Słownikowa reprezentacja EC3A_IO1632_Slave"""
        result = {
            "type": "EC3A_IO1632_Slave",
            "device_name": self.device_name,
            "address": self.address,
        }

        try:
            # Stany portów I/O
            result["inputs_ports"] = self.inputs_ports.copy()
            result["outputs_ports"] = self.outputs_ports.copy()

            # Wartości binarne dla łatwego odczytu
            result["inputs_binary"] = bin(
                sum(self.inputs_ports[i] << i for i in range(16))
            )
            result["outputs_binary"] = bin(
                sum(self.outputs_ports[i] << i for i in range(16))
            )

        except Exception as e:
            result["error"] = str(e)

        return result


class EC3A_IO1632(EtherCatDevice):
    """Abstrakcja urządzenia EC3A_IO1632 na poziomie logiki magistrali.

    Args:
        device_name (str): Nazwa urządzenia.
        bus: Obiekt magistrali EtherCAT.
        address: Adres slave'a.
        axis (list): Konfiguracja osi.
        message_logger (MessageLogger | None): Logger wiadomości.
        debug (bool): Flaga debugowania.
    """

    def __init__(
        self,
        device_name: str,
        bus,
        address,
        axis=list,
        motor_with_endstops_axis=list,
        message_logger: MessageLogger | None = None,
        debug=True,
    ):
        self.device_name = device_name
        product_code = 4353
        vendor_code = 2965
        info(f"{self.device_name} - Axis config: {axis}", message_logger=message_logger)
        self.number_of_axis = len(axis)
        configuration = {"axis": axis, "motor_with_endstops_axis": motor_with_endstops_axis}
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
        """Odczytuje stan wejścia cyfrowego z urządzenia przez magistralę."""
        self.inputs_ports[port] = self.bus.read_input(self.address, port)
        return self.inputs_ports[port]

    def _read_output(self, port: int):
        """Zwraca stan bufora wyjścia cyfrowego."""
        return self.outputs_ports[port]

    def _write_output(self, port: int, value: bool):
        """Ustawia wyjście cyfrowe w urządzeniu przez magistralę i aktualizuje bufor."""
        self.outputs_ports[port] = value
        # debug(f"{self.device_name} - Writing output {port} to {value}", message_logger=self.message_logger)
        self.bus.write_output(self.address, port, value)

    def _start_axis_pos_profile(
        self, axis: int, position: int, velocity: int, direction: bool
    ):
        """Rozpoczyna profil pozycyjny na wskazanej osi (wywołanie do magistrali)."""
        debug(
            f"{self.device_name}: Axis={axis}, start_axis_pos, position={position}, velocity={velocity}, direction={direction}",
            message_logger=self.message_logger,
        )
        self.bus.start_axis_pos_profile(
            self.address, axis, position, velocity, direction
        )

    def _start_axis_vel_profile(self, axis: int, velocity: int, direction: bool):
        """Rozpoczyna profil prędkościowy na wskazanej osi (wywołanie do magistrali)."""
        debug(
            f"{self.device_name}: Axis={axis}, start_axis_pos, velocity={velocity}, direction={direction}",
            message_logger=self.message_logger,
        )
        self.bus.start_axis_vel_profile(self.address, axis, velocity, direction)

    def _stop_axis(self, axis: int):
        """Zatrzymuje wskazaną oś (wywołanie do magistrali)."""
        self.bus.stop_axis(self.address, axis)
        debug(
            f"{self.device_name}: Axis={axis}, stop_axis",
            message_logger=self.message_logger,
        )

    def _axis_in_move(self, axis: int):
        """Zwraca informację o ruchu osi (zapytanie do magistrali)."""
        return self.bus.axis_in_move(self.address, axis)

    def _motor_with_endstops_move_up(self, axis: int):
        """Rozpoczyna ruch w górę osi z krańcówkami (wywołanie do magistrali)."""
        self.bus.motor_with_endstops_move_up(self.address, axis)
        
    def _motor_with_endstops_move_down(self, axis: int):
        """Rozpoczyna ruch w dół osi z krańcówkami (wywołanie do magistrali)."""
        self.bus.motor_with_endstops_move_down(self.address, axis)
        
    def _motor_with_endstops_stop(self, axis: int):
        """Zatrzymuje oś z krańcówkami (wywołanie do magistrali)."""
        self.bus.motor_with_endstops_stop(self.address, axis)

    def di(self, index: int):
        """Zwraca stan wejścia cyfrowego (skrót do `_read_input`)."""
        return self._read_input(index)

    def do(self, index: int, value: bool = None):
        """Ustawia lub zwraca stan wyjścia cyfrowego.

        Args:
            index (int): Port wyjściowy.
            value (bool | None): Wartość do ustawienia; gdy None, zwraca bieżący stan.
        """
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
    
    def motor_with_endstops_move_up_0(self):
        return self._motor_with_endstops_move_up(0)
    
    def motor_with_endstops_move_up_1(self):
        return self._motor_with_endstops_move_up(1)
    
    def motor_with_endstops_move_up_2(self):
        return self._motor_with_endstops_move_up(2)
    
    def motor_with_endstops_move_up_3(self):
        return self._motor_with_endstops_move_up(3)
    
    def motor_with_endstops_move_up_4(self):
        return self._motor_with_endstops_move_up(4)
    
    def motor_with_endstops_move_up_5(self):
        return self._motor_with_endstops_move_up(5)
    
    def motor_with_endstops_move_up_6(self):
        return self._motor_with_endstops_move_up(6)
    
    def motor_with_endstops_move_down_0(self):
        return self._motor_with_endstops_move_down(0)
    
    def motor_with_endstops_move_down_1(self):
        return self._motor_with_endstops_move_down(1)
    
    def motor_with_endstops_move_down_2(self):
        return self._motor_with_endstops_move_down(2)
    
    def motor_with_endstops_move_down_3(self):
        return self._motor_with_endstops_move_down(3)
    
    def motor_with_endstops_move_down_4(self):
        return self._motor_with_endstops_move_down(4)
    
    def motor_with_endstops_move_down_5(self):
        return self._motor_with_endstops_move_down(5)
    
    def motor_with_endstops_move_down_6(self):
        return self._motor_with_endstops_move_down(6)
    
    def motor_with_endstops_stop_0(self):
        return self._motor_with_endstops_stop(0)
    
    def motor_with_endstops_stop_1(self):
        return self._motor_with_endstops_stop(1)
    
    def motor_with_endstops_stop_2(self):
        return self._motor_with_endstops_stop(2)
    
    def motor_with_endstops_stop_3(self):
        return self._motor_with_endstops_stop(3)
    
    def motor_with_endstops_stop_4(self):
        return self._motor_with_endstops_stop(4)
    
    def motor_with_endstops_stop_5(self):
        return self._motor_with_endstops_stop(5)
    
    def motor_with_endstops_stop_6(self):
        return self._motor_with_endstops_stop(6)
    

    def check_device_connection(self) -> bool:
        return True

    def __str__(self) -> str:
        """Reprezentacja urządzenia EC3A_IO1632"""
        try:
            connection_status = (
                "connected" if self.check_device_connection() else "disconnected"
            )

            return (
                f"EC3A_IO1632(name='{self.device_name}', "
                f"addr={self.address}, "
                f"axes={self.number_of_axis}, "
                f"status={connection_status}, "
                f"DI={bin(sum(self.inputs_ports[i] << i for i in range(16)))}, "
                f"DO={bin(sum(self.outputs_ports[i] << i for i in range(16)))})"
            )
        except Exception as e:
            return f"EC3A_IO1632(name='{self.device_name}', error='{str(e)}')"

    def __repr__(self) -> str:
        """Szczegółowa reprezentacja dla developerów"""
        try:
            return (
                f"EC3A_IO1632(device_name='{self.device_name}', "
                f"address={self.address}, "
                f"number_of_axis={self.number_of_axis}, "
                f"vendor_code={self.vendor_code}, "
                f"product_code={self.product_code}, "
                f"inputs_ports={self.inputs_ports}, "
                f"outputs_ports={self.outputs_ports})"
            )
        except Exception as e:
            return f"EC3A_IO1632(device_name='{self.device_name}', error='{str(e)}')"

    def to_dict(self) -> dict:
        """Słownikowa reprezentacja EC3A_IO1632"""
        result = {
            "type": "EC3A_IO1632",
            "device_name": self.device_name,
            "address": self.address,
            "number_of_axis": self.number_of_axis,
            "vendor_code": self.vendor_code,
            "product_code": self.product_code,
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

            # Status połączenia
            result["connection_status"] = self.check_device_connection()

        except Exception as e:
            result["error"] = str(e)

        return result


init_device_di(EC3A_IO1632, first_index=0, count=16)
init_device_do(EC3A_IO1632, first_index=0, count=16)
