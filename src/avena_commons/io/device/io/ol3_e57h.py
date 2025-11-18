from .EtherCatSlave import EtherCatDevice, EtherCatSlave
import struct
from enum import Enum

from avena_commons.util.logger import MessageLogger, debug, error, info

class cia402_states(Enum):
    NOT_READY_TO_SWITCH_ON = 0
    SWITCH_ON_DISABLED = 1
    READY_TO_SWITCH_ON = 2
    SWITCHED_ON = 3
    OPERATION_ENABLED = 4
    QUICK_STOP_ACTIVE = 5
    FAULT_REACTION_ACTIVE = 6
    FAULT = 7
    UNKNOWN = 8

class OL3_E57H_FSM(Enum):
    IDLE = 0
    STARTING = 1
    OPERATIONAL = 2
    IN_PROFILE_VELOCITY = 3
    STOPPING = 4
    ERROR = 5
    UNKNOWN = 6
    
class OL3_E57H_Slave(EtherCatSlave):
    
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
        
        self.status_word = 0
        self.mode_display = 0
        self.actual_position = 0
        self.actual_velocity = 0
        self.input_values = 0
        
        self.control_word = 0x0080  # 0x80 = Clear Fault
        self.mode = 0
        self.target_pos = 0
        self.target_vel = 0
        self.prof_vel = 0
        self.prof_accel = 0
        self.prof_decel = 0
        
        self.cia402_state = cia402_states.UNKNOWN
        self.fsm  = OL3_E57H_FSM.IDLE
        
        self.init_drive = False
        
        self.save_position = 0
        
    def check_io_config(self):
        print("--- Weryfikacja konfiguracji IO ---")
        for i in range(6):
            index = 0x2510 + i
            # Odczytujemy 1 bajt (B)
            try:
                val_bytes = self.master.slaves[self.address].sdo_read(index, 0)
                val = struct.unpack('<H', val_bytes)[0]
                print(f"DI{i+1} (0x{index:X}) Function: {val}")
            except Exception as e:
                print(f"Błąd odczytu 0x{index:X}: {e}")
                
        # Sprawdźmy też polaryzację (NO/NC)
        try:
            pol_bytes = self.master.slaves[self.address].sdo_read(0x2500, 0)
            pol = struct.unpack('H', pol_bytes)[0] # UINT, 2 bajty
            print(f"Polarity (0x2500): {pol} (Binarnie: {bin(pol)})")
        except Exception as e:
            print(f"Błąd odczytu polaryzacji: {e}")
    
    def _config_function(self, slave_pos):
        #setting io
        self.master.slaves[slave_pos].sdo_write(0x2510, 0, struct.pack('<H', 0))#9))
        self.master.slaves[slave_pos].sdo_write(0x2511, 0, struct.pack('<H', 0))#10))
        self.master.slaves[slave_pos].sdo_write(0x2512, 0, struct.pack('<H', 11))
        self.master.slaves[slave_pos].sdo_write(0x2513, 0, struct.pack('<H', 0))#12))
        self.master.slaves[slave_pos].sdo_write(0x2514, 0, struct.pack('<H', 13))
        self.master.slaves[slave_pos].sdo_write(0x2515, 0, struct.pack('<H', 14))
        
        self.master.slaves[slave_pos].sdo_write(0x2500, 0, struct.pack('<H', 0))
        #PDO Mapping for OL3-E57H
        self.master.slaves[slave_pos].sdo_write(0x1C12, 0, struct.pack('B', 0))
        self.master.slaves[slave_pos].sdo_write(0x1C13, 0, struct.pack('B', 0))
        self.master.slaves[slave_pos].sdo_write(0x1600, 0, struct.pack('B', 0))
        self.master.slaves[slave_pos].sdo_write(0x1A00, 0, struct.pack('B', 0))
        
        rx_entries = [
            {"index": 0x6040, "subindex": 0x00, "bitlength": 0x10},  # Control Word
            {"index": 0x6060, "subindex": 0x00, "bitlength": 0x08},  # Modes of Operation
            {"index": 0x607A, "subindex": 0x00, "bitlength": 0x20},  # Target Position
            {"index": 0x60FF, "subindex": 0x00, "bitlength": 0x20},  # Target Velocity
            {"index": 0x6081, "subindex": 0x00, "bitlength": 0x20},  # Profile Velocity
            {"index": 0x6083, "subindex": 0x00, "bitlength": 0x20},  # Profile Acceleration
            {"index": 0x6084, "subindex": 0x00, "bitlength": 0x20},  # Profile Deceleration
        ]
        
        for subindex, content in enumerate(rx_entries, start=1):
            mapping = (content["index"] << 16) | (content["subindex"] << 8) | content["bitlength"]
            self.master.slaves[slave_pos].sdo_write(0x1600, subindex, struct.pack('I', mapping))
        self.master.slaves[slave_pos].sdo_write(0x1600, 0, struct.pack('B', len(rx_entries)))
        
        tx_entries = [
            {"index": 0x6041, "subindex": 0x00, "bitlength": 0x10},  # Status Word
            {"index": 0x6061, "subindex": 0x00, "bitlength": 0x08},  # Modes of Operation Display
            {"index": 0x6064, "subindex": 0x00, "bitlength": 0x20},  # Position Actual Value
            {"index": 0x606C, "subindex": 0x00, "bitlength": 0x20},  # Velocity Actual Value WAŻNE - sterownik w trybie open_loop nie zwraca prędkości
            {"index": 0x60FD, "subindex": 0x00, "bitlength": 0x20},  # Input Values
        ]
        
        for subindex, content in enumerate(tx_entries, start=1):
            mapping = (content["index"] << 16) | (content["subindex"] << 8) | content["bitlength"]
            self.master.slaves[slave_pos].sdo_write(0x1A00, subindex, struct.pack('I', mapping))
        self.master.slaves[slave_pos].sdo_write(0x1A00, 0, struct.pack('B', len(tx_entries)))
        
        
        self.master.slaves[slave_pos].sdo_write(0x1C12, 1, struct.pack('<H', 0x1600))
        self.master.slaves[slave_pos].sdo_write(0x1C12, 0, struct.pack('B', 1))
        self.master.slaves[slave_pos].sdo_write(0x1C13, 1, struct.pack('<H', 0x1A00))
        self.master.slaves[slave_pos].sdo_write(0x1C13, 0, struct.pack('B', 1))
        
    def _read_pdo(self):
        input_bytes = self.master.slaves[self.address].input

        # Your raw input data from slave.inputs
        input_data = input_bytes
        
        print(f"Reading PDO from OL3-E57H {input_data}")

        # Define the format string based on your TxPDO map
        # < = little-endian
        # H = Status Word (unsigned short, 2 bytes)
        # b = Mode Display (signed char, 1 byte)
        # i = Position (signed int, 4 bytes)
        # i = Velocity (signed int, 4 bytes)
        # H = Input Values (unsigned short, 2 bytes)
        pdo_format = '<Hbiii'

        # Check if data has the expected length before unpacking
        expected_length = struct.calcsize(pdo_format)

        if len(input_data) == expected_length:
            # Unpack the data
            unpacked_data = struct.unpack(pdo_format, input_data)
            
            # Assign to named variables
            self.status_word = unpacked_data[0]
            self.mode_display = unpacked_data[1]
            self.actual_position = unpacked_data[2]
            self.actual_velocity = unpacked_data[3]
            self.input_values = unpacked_data[4]

            # print(f"--- Unpacked PDO Data ---")
            # print(f"Raw: {unpacked_data}")
            # print(f"Status Word: {self.status_word} (Hex: 0x{self.status_word:X})")
            # print(f"Mode Display: {self.mode_display}")
            # print(f"Actual Position: {self.actual_position}")
            # print(f"Actual Velocity: {self.actual_velocity}")
            print(f"Input Values: {self.input_values}")

        else:
            print(f"Error: Input data length ({len(input_data)}) does not match expected ({expected_length})")
        
    
    def _write_pdo(self):
        output_bytes = self.master.slaves[self.address].output
        print(f"Writing PDO to OL3-E57H {output_bytes}")
        
        # self.control_word = 0x0080  # 0x80 = Clear Fault
        # self.mode = 0
        # self.target_pos = 0
        # self.target_vel = 0
        # self.prof_vel = 0
        # self.prof_accel = 0
        # self.prof_decel = 0
        
        pdo_format = '<HbiiIII'


        # print(f"Target Velocity: {self.target_vel}, Profile Velocity: {self.prof_vel}, Profile Accel: {self.prof_accel}, Profile Decel: {self.prof_decel}, control word: {self.control_word}, mode: {self.mode}")
        # print(f"Actual Velocity: {self.actual_velocity}, Actual Position: {self.actual_position}, status word: {self.status_word}, mode display: {self.mode_display}")
        # Pack the data into a 23-byte string
        output_data = struct.pack(
            pdo_format,
            self.control_word,
            self.mode,
            self.target_pos,
            self.target_vel,
            self.prof_vel,
            self.prof_accel,
            self.prof_decel
        )
        
        self.master.slaves[self.address].output = output_data
        
    
    def _process(self):
        self.cia402_state = self.decode_cia402_state(self.status_word)
        # print(f"{self.device_name}: Current CIA402 State: {self.cia402_state.name}")
        
        print(f"{self.device_name}: FSM State: {self.fsm.name}")
        
        match self.fsm:
            case OL3_E57H_FSM.IDLE:
                if self.init_drive:
                    self.fsm = OL3_E57H_FSM.STARTING
                else:
                    self.init_drive_cmd()
            case OL3_E57H_FSM.STARTING:
                self.process_init()
            case OL3_E57H_FSM.OPERATIONAL:
                #pass
                # self.run_jog(speed=-1000, accel=100, decel=100)
                # self.save_position = self.actual_position
                
                    
                # print(self.read_input(port=1))
                # print(self.read_input(port=2))
                # print(self.read_input(port=3))
                # print(self.read_input(port=4))
                # print(self.read_input(port=5))
                # print(self.read_input(port=6))
                pass
                
                
            case OL3_E57H_FSM.IN_PROFILE_VELOCITY:
                # pass
                # self.check_io_config()
                # print(f"{self.device_name}: Running in Profile Velocity Mode at target velocity {self.target_vel}.")
                # ODCZYT DEBUGGERSKI PRZEZ SDO
                # try:
                #     sdo_velocity_bytes = self.master.slaves[self.address].sdo_read(0x2100, 0x00)
                #     sdo_velocity = struct.unpack('<H', sdo_velocity_bytes)[0]
                #     print(f"{self.device_name}: SDO Read - 0x2100: {sdo_velocity}")
                # except Exception as e:
                #     print(f"{self.device_name}: SDO Read Error: {e}")
                
                
                # if abs(self.save_position - self.actual_position) > 5000:
                #     print(f"{self.device_name}: Significant position change detected. Stopping drive.")
                #     self.stop()
                pass
                
            case OL3_E57H_FSM.STOPPING:
                if self.is_stopped():
                    self.fsm = OL3_E57H_FSM.OPERATIONAL
                    print(f"{self.device_name}: Drive stopped successfully.")
            case OL3_E57H_FSM.ERROR:
                pass
            case _:
                pass
    
    def _check_state(self):
        pass
    
    def decode_cia402_state(self, status_word: int) -> str:
        state = cia402_states.UNKNOWN
        
        if (status_word & 0x004F) == 0x0000:
            state = cia402_states.NOT_READY_TO_SWITCH_ON
            print(f"{self.device_name}: State - NOT_READY_TO_SWITCH_ON")
        elif (status_word & 0x004F) == 0x0040:
            state = cia402_states.SWITCH_ON_DISABLED
            print(f"{self.device_name}: State - SWITCH_ON_DISABLED")
        elif (status_word & 0x006F) == 0x0021:
            state = cia402_states.READY_TO_SWITCH_ON
            print(f"{self.device_name}: State - READY_TO_SWITCH_ON")
        elif (status_word & 0x006F) == 0x0023:
            state = cia402_states.SWITCHED_ON
            print(f"{self.device_name}: State - SWITCHED_ON")
        elif (status_word & 0x006F) == 0x0027:
            state = cia402_states.OPERATION_ENABLED
            print(f"{self.device_name}: State - OPERATION_ENABLED")
        elif (status_word & 0x006F) == 0x0007:
            state = cia402_states.QUICK_STOP_ACTIVE
            print(f"{self.device_name}: State - QUICK_STOP_ACTIVE")
        elif (status_word & 0x004F) == 0x000F:
            state = cia402_states.FAULT_REACTION_ACTIVE
            print(f"{self.device_name}: State - FAULT_REACTION_ACTIVE")
        elif (status_word & 0x004F) == 0x0008:
            state = cia402_states.FAULT
            print(f"{self.device_name}: State - FAULT")
        
        return state

    def init_drive_cmd(self):
        self.init_drive = True
        
    def process_init(self):
        match self.cia402_state:
            case cia402_states.SWITCH_ON_DISABLED:
                self.control_word = 0x0006  # Enable Voltage
                print(f"{self.device_name}: Enabling voltage.")
            case cia402_states.READY_TO_SWITCH_ON:
                self.control_word = 0x0007  # Switch On
                print(f"{self.device_name}: Switching on.")
            case cia402_states.SWITCHED_ON:
                self.control_word = 0x000F  # Enable Operation
                print(f"{self.device_name}: Enabling operation.")
            case cia402_states.OPERATION_ENABLED:
                self.fsm = OL3_E57H_FSM.OPERATIONAL
                print(f"{self.device_name}: Drive is now operational.")
                info(f"{self.device_name}: Drive initialized and operational.", self.message_logger)
            case cia402_states.FAULT:
                self.control_word = 0x0080  # Clear Fault
                print(f"{self.device_name}: Clearing fault.")
                error(f"{self.device_name}: Drive in FAULT state. Clearing fault.", self.message_logger)
            case _:
                pass
            
    def is_target_reached(self) -> bool:
        """Sprawdza Bit 10 w Status Word (Target Reached)"""
        # Maska 0x0400 to binarnie ... 0000 0100 0000 0000 (czyli 10. bit)
        return (self.status_word & 0x0400) != 0

    def is_stopped(self) -> bool:
        """
        Zwraca True, jeśli zadana prędkość to 0 i napęd potwierdza wykonanie.
        """
        return self.target_vel == 0 and self.is_target_reached()
            
    def run_jog(self, speed: int, accel: int = 0, decel: int = 0):
        """
        Uruchamia napęd w trybie prędkościowym (Profile Velocity Mode - 3).
        :param speed: Prędkość docelowa (jednostki użytkownika, np. pulses/s)
        :param accel: Przyspieszenie
        :param decel: Hamowanie
        """
        if self.fsm != OL3_E57H_FSM.OPERATIONAL:
            print(f"{self.device_name}: Drive not operational. Cannot run jog.")
            return
        
        # 1. Ustaw tryb Profile Velocity (3)
        self.mode = 3
        
        # 2. Ustaw parametry ruchu
        self.prof_vel = abs(speed)
        self.target_vel = speed
        self.prof_accel = 4*abs(speed) #accel
        self.prof_decel = 4*abs(speed) #decel
        
        # 3. Control Word: Enable Operation (Bit 3=1) + HALT=0 (Bit 8=0)
        # 0x000F = 0000 0000 0000 1111
        self.control_word = 0x000F
        self.fsm = OL3_E57H_FSM.IN_PROFILE_VELOCITY
    
    def stop_motor(self):
        if self.fsm != OL3_E57H_FSM.IN_PROFILE_VELOCITY:
            print(f"{self.device_name}: Drive not operational. Cannot run jog.")
            return
        
        print(f"{self.device_name}: Stopping drive.")
        info(f"{self.device_name}: Stopping drive.", self.message_logger)
        self.target_vel = 0
        self.control_word = 0x010F  # Bit 1=1 (Switch Off), Bit 3=1 (Enable Operation)
        self.fsm = OL3_E57H_FSM.STOPPING
    
    def read_input(self, port):
        io_mapping = {
            1: 17, 
            2: 18,
            3: 20,
            4: 21,
            5: 22,
            6: 23
        }
        
        if port not in io_mapping:
            print(f"Error: Port {port} not mapped.")
            return False
        
        target_bit = io_mapping[port]
        mask = 1 << target_bit
        
        is_active = (self.input_values & mask) != 0
        
        print(f"Input Port {port} (Bit {target_bit}) is {'ACTIVE' if is_active else 'INACTIVE'}.")
        
        return is_active
    
    def is_motor_running(self) -> bool:
        """Sprawdza Bit 0 w Status Word (Switch On Status)"""
        return self.fsm == OL3_E57H_FSM.IN_PROFILE_VELOCITY
        

class OL3_E57H(EtherCatDevice):
    
    def __init__(
        self,
        device_name: str,
        bus,
        address,
        message_logger=None,
        debug=True
    ):
        self.device_name = device_name
        product_code = 8192 #87 # Example product code for OL3-E57H
        vendor_code = 2681 #26 # Example vendor code
        configuration = {}
        super().__init__(
            bus,
            vendor_code,
            product_code,
            address,
            configuration,
            message_logger,
            debug
        )
        
    def run_jog(self, speed: int, accel: int = 0, decel: int = 0):
        self.bus.run_jog(self.address, speed, accel, decel)
        
    def stop(self):
        self.bus.stop_motor(self.address)
        
    def read_input(self, port):
        value = self.bus.read_input(self.address, port)
        return value
    
    @property
    def di1(self):
        value = self.read_input(1)
        return value
    
    @property
    def di2(self):
        value = self.read_input(2)
        return value
    
    @property
    def di3(self):
        value = self.read_input(3)
        return value
    
    @property
    def di4(self):
        value = self.read_input(4)
        return value
    
    @property
    def di5(self):
        value = self.read_input(5)
        return value
    
    @property
    def di6(self):
        value = self.read_input(6)
        return value
    
    @property
    def is_motor_running(self) -> bool:
        result = self.bus.is_motor_running(self.address)
        return result

    @property
    def is_failure(self) -> bool:
        return False
        
        
    
    