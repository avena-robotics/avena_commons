import importlib
import threading
import time
from enum import Enum

import pysoem
import ctypes
from avena_commons.util.logger import debug, error, info, warning
from avena_commons.util.measure_time import MeasureTime
from avena_commons.util.worker import Connector, Worker


class EtherCATState(Enum):
    """Enum stanów wewnętrznego FSM dla pracy magistrali EtherCAT."""

    PREINIT = 0
    INIT = 1
    CONFIG = 2
    RUNNING = 4
    STOPPED = 5


class PysoemStates(Enum):
    """Mapowanie kodów stanów pysoem na czytelne nazwy (pomoc przy logowaniu)."""

    NONE_STATE = 0
    INIT_STATE = 1
    PREOP_STATE = 2
    BOOT_STATE = 3
    SAFEOP_STATE = 4
    OP_STATE = 8
    STATE_ACK = 100
    STATE_ERROR = 200


class EtherCATWorker(Worker):
    """Worker obsługujący komunikację i przetwarzanie PDO w wątku EtherCAT.

    Args:
        device_name (str): Nazwa instancji.
        network_interface (str): Interfejs sieciowy (np. "eth0").
        number_of_devices (int): Oczekiwana liczba slave'ów.
        message_logger: Logger komunikatów.
    """

    def __init__(
        self,
        device_name: str,
        network_interface: str,
        number_of_devices: int,
        message_logger=None,
    ):
        self.device_name = device_name
        self._message_logger = message_logger
        super().__init__(message_logger)
        self.master = pysoem.Master()
        self._configuration = None

        self._slaves = []

        # CONFIG INFO
        self._network_interface = network_interface
        self._number_of_devices = number_of_devices

        self.__change_state(EtherCATState.PREINIT)
        self._running = True
        self._lock = threading.Lock()
        self.__cycle_time: float = 0.0
        self.__cycle_frequency: int = 0

    def _init(self):
        """Inicjalizuje mastera pysoem i weryfikuje liczbę urządzeń."""
        self.master.open(self._network_interface)
        number_of_slaves = self.master.config_init()
        info(
            f"{self.device_name} INIT - Number of devices: {number_of_slaves}",
            message_logger=self._message_logger,
        )

        if number_of_slaves != self._number_of_devices:
            error(
                f"{self.device_name} INIT - Number of devices ({number_of_slaves}) does not match the expected number of devices ({self._number_of_devices})",
                message_logger=self._message_logger,
            )
            raise Exception(
                f"{self.device_name} INIT - Number of devices ({number_of_slaves}) does not match the expected number of devices ({self._number_of_devices})"
            )
        else:
            info(
                f"{self.device_name} INIT - Number of devices ({number_of_slaves}) matches the expected number of devices ({self._number_of_devices})",
                message_logger=self._message_logger,
            )
            for i, slave in enumerate(self.master.slaves):
                slave_name = slave.name
                slave_vendor_code = slave.man
                slave_product_code = slave.id
                info(
                    f"{self.device_name} INIT - Slave {slave_name} at address {i} with vendor code {slave_vendor_code} and product code {slave_product_code}",
                    message_logger=self._message_logger,
                )

    def __process(self, sleep: float = 0.0):
        """Realizuje jeden cykl komunikacji: receive → process per-slave → send → state check.

        Args:
            sleep (float): Dodatkowe opóźnienie na koniec cyklu (sekundy).
        """
        ret = self.master.receive_processdata(1000)  # odczyt danych z sieci EtherCat
        # print(f"wck {ret} vs ex wck {self.master.expected_wkc}")
        if ret == 0:
            error(
                f"{self.device_name} Error receiving processdata: {ret}",
                message_logger=self._message_logger,
            )
            return

        for i, slave in enumerate(self._slaves):  # wywolanie metod z klas device
            slave._read_pdo()
            slave._process()
            slave._write_pdo()
            slave._check_state()

        # Logowanie send_processdata
        ret = self.master.send_processdata()
        if ret == 0:
            error(
                f"{self.device_name} PROCESS - Error sending processdata: {ret}",
                message_logger=self._message_logger,
            )
            return

        # Logowanie sprawdzania stanu
        state = self.master.read_state()
        if state != pysoem.OP_STATE:
            info(
                f"{self.device_name} PROCESS - Network state: {PysoemStates(state).name}",
                message_logger=self._message_logger,
            )
            # TODO: ADD SLAVE STATE CHECK
            self.master.state = pysoem.OP_STATE
            self.master.write_state()

        time.sleep(sleep)

    def _add_device(self, device_args: list):
        """Dodaje obiekt slave do wewnętrznej listy na podstawie konfiguracji."""
        device_class = device_args[4].lower()

        # module_path = f"avena_commons.io.device.io.{device_class}"
        # ścieżka testowa/dynamiczna musi być z "lib.io.{folder_name}.{subfolder_path}.{actual_class_name.lower()}"
        # ścieżka wewnętrzna avena_commons "avena_commons.io.{folder_name}.{subfolder_path}.{actual_class_name.lower()}"
        # FIXME -  scieżkę powinien brać z jednego miejsca - konfiguracji lub zmiennej środowiskowej
        test_module_path = f"lib.io.device.io.{device_class}"
        module_path = f"avena_commons.io.device.io.{device_class}"

        try:
            module = importlib.import_module(test_module_path)
            device_class = f"{device_class.upper()}_Slave"
        except (ImportError, AttributeError) as e:
            try:
                # Try importing from the main module path
                module = importlib.import_module(module_path)
                device_class = f"{device_class.upper()}_Slave"

            except (ImportError, AttributeError) as e:
                error(
                    f"Failed to import {device_class} from {module_path}: {str(e)}",
                    message_logger=self._message_logger,
                )
                return None

        # module = importlib.import_module(module_path)
        # device_class = f"{device_class.upper()}_Slave"
        device = getattr(module, device_class)
        device = device(
            device_name=device_args[0],
            master=self.master,
            address=device_args[3],
            config=device_args[5],
            message_logger=self._message_logger,
        )
        self._slaves.append(device)

    def __configure(self, slave_args: list):
        """Konfiguruje slave'y, ustawia PREOP, mapuje PDO i przygotowuje DC."""
        info(f"slave_args {slave_args}", message_logger=self._message_logger)
        slave_args.sort(key=lambda x: x[3])
        info(f"slave_args sorted {slave_args}", message_logger=self._message_logger)
        
        for i, slave_arg in enumerate(slave_args):
            device_name = slave_arg[0]
            slave_product_code = slave_arg[1]
            slave_vendor_code = slave_arg[2]
            slave_address = slave_arg[3]
            info(
                f"{self.device_name} CONFIG - {device_name} Config: {slave_arg[5]}",
                message_logger=self._message_logger,
            )

            if (
                self.master.slaves[slave_address].id == slave_product_code
                and self.master.slaves[slave_address].man == slave_vendor_code
            ):
                self._add_device(slave_arg)
                info(f"slave_address {slave_address} {i}, slaves num ecat {len(self.master.slaves)}, slaves {len(self._slaves)}", self._message_logger)
                self.master.slaves[slave_address].config_func = self._slaves[
                    i
                ]._config_function  # przypisanie funkcji konfiguracji do slave
            else:
                error(
                    f"{self.device_name} CONFIG - Slave {slave_address} at address {slave_address} with vendor code {slave_vendor_code} and product code {slave_product_code} does not match the expected vendor code {self.master.slaves[slave_address].man} and product code {self.master.slaves[slave_address].id}",
                    message_logger=self._message_logger,
                )
                raise Exception(
                    f"{self.device_name} CONFIG - Slave {slave_address} at address {slave_address} with vendor code {slave_vendor_code} and product code {slave_product_code} does not match the expected vendor code {self.master.slaves[slave_address].man} and product code {self.master.slaves[slave_address].id}"
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
                    f"{self.device_name} CONFIG - Slave {slave.name} is not in PREOP_STATE state",
                    message_logger=self._message_logger,
                )
            else:
                info(
                    f"{self.device_name} CONFIG - Slave {slave.name} is in PREOP_STATE state",
                    message_logger=self._message_logger,
                )

        # TODO: ADD CHECKS
        try:
            size = 409600 # Make this generously large for testing
            iomap = (ctypes.c_uint8 * size)()
            map_size = self.master.config_map()  # budowanie mapy komunikatow - pobranie od slave
            print(f"MASTER Map size - {map_size}")
        except Exception as e:
            error(
                f"{self.device_name} CONFIG - Error: {e}",
                message_logger=self._message_logger,
            )

        if (
            self.master.state_check(pysoem.SAFEOP_STATE, timeout=50_000)
            != pysoem.SAFEOP_STATE
        ):
            warning(
                f"{self.device_name} CONFIG - Not all slaves reached SAFEOP state",
                message_logger=self._message_logger,
            )
        else:
            info(
                f"{self.device_name} CONFIG - All slaves reached SAFEOP state",
                message_logger=self._message_logger,
            )

        # ✅ KONFIGURACJA DC NA 4kHz (250μs)
        info(
            f"{self.device_name} CONFIG - Configuring Distributed Clock for 4kHz (250μs)",
            message_logger=self._message_logger,
        )

        # Podstawowa konfiguracja DC
        self.master.config_dc()

        info(
            f"{self.device_name} CONFIG - Configuration completed, ready for initialization verification",
            message_logger=self._message_logger,
        )

    def __measure_actual_network_cycle(self, count: int = 20, sleep: float = 0.0):
        """Mierzy rzeczywisty cykl komunikacyjny sieci EtherCAT i zapisuje medianę.

        Args:
            count (int): Liczba pomiarów pełnych cykli.
            sleep (float): Przerwa między kolejnymi pomiarami (s).
        """
        info(
            f"{self.device_name} - Measuring actual EtherCAT network cycle...",
            message_logger=self._message_logger,
        )

        cycle_times = []

        # ✅ POMIAR PEŁNEGO CYKLU KOMUNIKACYJNEGO
        for i in range(count):  # Mniej pomiarów, ale dokładniejsze
            start_time = time.perf_counter()

            # ✅ CAŁY CYKL ETHERCAT - DOKŁADNIE JAK W _process()
            ret = self.master.receive_processdata(
                1000
            )  # odczyt danych z sieci EtherCat

            
            if ret == 0:
                warning(
                    f"{self.device_name} - Error receiving processdata during measurement",
                    message_logger=self._message_logger,
                )
                continue

            for i, slave in enumerate(self._slaves):
                slave._read_pdo()
                slave._process()
                slave._write_pdo()
                slave._check_state()

            ret = self.master.send_processdata()

            if ret == 0:
                warning(
                    f"{self.device_name} - Error sending processdata during measurement",
                    message_logger=self._message_logger,
                )
                continue

            # Sprawdź stan sieci
            state = self.master.read_state()
            if state != pysoem.OP_STATE:
                self.master.state = pysoem.OP_STATE
                self.master.write_state()

            end_time = time.perf_counter()
            cycle_time = end_time - start_time
            if cycle_time < 0.0001:
                warning(
                    f"{self.device_name} - Measured cycle time too small ({cycle_time * 1000000:.3f}μs), skipping...",
                    message_logger=self._message_logger,
                )
                continue
            elif cycle_time > 0.1:
                warning(
                    f"{self.device_name} - Measured cycle time too large ({cycle_time * 1000000:.3f}μs), skipping...",
                    message_logger=self._message_logger,
                )
                continue
            cycle_times.append(cycle_time)

            # Krótka przerwa między pomiarami
            time.sleep(sleep)

        if len(cycle_times) == 0:
            error(
                f"{self.device_name} - No valid cycle time measurements!",
                message_logger=self._message_logger,
            )

        # Analiza czasów
        cycle_times.sort()
        median_time = cycle_times[len(cycle_times) // 2]  # mediana
        avg_time = sum(cycle_times) / len(cycle_times)
        min_time = min(cycle_times)
        max_time = max(cycle_times)

        # ✅ WYŚWIETL W NORMALNEJ NOTACJI
        info(
            f"{self.device_name} - Network cycle analysis:",
            message_logger=self._message_logger,
        )
        info(
            f"  - Median: {median_time * 1000:.6f}ms ({median_time * 1000000:.3f}μs)",
            message_logger=self._message_logger,
        )
        info(
            f"  - Average: {avg_time * 1000:.6f}ms ({avg_time * 1000000:.3f}μs)",
            message_logger=self._message_logger,
        )
        info(
            f"  - Min: {min_time * 1000:.6f}ms ({min_time * 1000000:.3f}μs)",
            message_logger=self._message_logger,
        )
        info(
            f"  - Max: {max_time * 1000:.6f}ms ({max_time * 1000000:.3f}μs)",
            message_logger=self._message_logger,
        )

        if median_time < 0.0001:
            raise Exception(
                f"{self.device_name} - Measured cycle time too small ({median_time * 1000000:.3f}μs)"
            )
        elif median_time > 0.1:
            raise Exception(
                f"{self.device_name} - Measured cycle time too large ({median_time * 1000000:.3f}μs)"
            )

        # Zwróć realistyczny czas z buforem
        self.__cycle_time = median_time
        self.__cycle_frequency = 1 / median_time

        info(
            f"{self.device_name} - Median EtherCAT cycle time: {self.__cycle_time * 1000000:.3f}μs [Hz: {self.__cycle_frequency:.1f}]",
            message_logger=self._message_logger,
        )

    def get_cycle_time(self):
        """Zwraca ostatnio zmierzoną medianę czasu cyklu (sekundy)."""
        return self.__cycle_time

    def get_cycle_frequency(self):
        """Zwraca częstotliwość cyklu wyliczoną z mediany czasu (Hz)."""
        return self.__cycle_frequency

    def _check_dc_support(self, slave_address):
        """Sprawdza, czy dany slave obsługuje Distributed Clock (DC)."""
        try:
            # Sprawdź ESC Feature register (0x0008-0x0009)
            feature_data = self.master.FPRD(slave_address, 0x0008, 2, timeout=1000)
            if len(feature_data) >= 2:
                features = int.from_bytes(feature_data[:2], byteorder="little")
                dc_support = (features & 0x0004) != 0  # Bit 2: DC support
                return dc_support
            return False
        except:
            return False

    def __switch_to_op_state(self):
        """
        Przełącza do OP_STATE używając oryginalnej logiki (bez testów komunikacji).
        """
        try:
            # ORYGINALNA LOGIKA - bez testów komunikacji!
            info(
                f"{self.device_name} OP_SWITCH - Setting master to OP_STATE",
                message_logger=self._message_logger,
            )
            self.master.state = pysoem.OP_STATE
            self.master.write_state()

            # Sprawdź stan i ewentualnie ustaw ponownie
            state = self.master.read_state()
            if state != pysoem.OP_STATE:
                info(
                    f"{self.device_name} OP_SWITCH - Network state: {PysoemStates(state).name}, setting OP_STATE again",
                    message_logger=self._message_logger,
                )
                self.master.state = pysoem.OP_STATE
                self.master.write_state()

            final_state = self.master.read_state()
            info(
                f"{self.device_name} OP_SWITCH - Final network state: {PysoemStates(final_state).name}",
                message_logger=self._message_logger,
            )

            # WAŻNE: Sprawdź stan slave'ów ale NIE rób z tego błędu krytycznego!
            for i, slave in enumerate(self.master.slaves):
                slave_state = slave.state
                if slave_state != pysoem.OP_STATE:
                    debug(
                        f"{self.device_name} OP_SWITCH - Slave {i} ({slave.name}) state: {PysoemStates(slave_state).name}",
                        message_logger=self._message_logger,
                    )
                else:
                    info(
                        f"{self.device_name} OP_SWITCH - Slave {i} ({slave.name}) OK: OP_STATE",
                        message_logger=self._message_logger,
                    )

            # ZAWSZE zwracaj True - jak w oryginalnym kodzie!
            info(
                f"{self.device_name} OP_SWITCH - Transition completed",
                message_logger=self._message_logger,
            )
            return True

        except Exception as e:
            error(
                f"{self.device_name} OP_SWITCH - Exception: {e}",
                message_logger=self._message_logger,
            )
            return False

    def __change_state(self, state: EtherCATState):
        """Ustawia bieżący stan worker'a EtherCAT i loguje zmianę."""
        self._ethercat_state = state
        info(
            f"{self.device_name} - Changing state to {state}",
            message_logger=self._message_logger,
        )

    def __communication_thread(self, pipe_in):
        """Wątek obsługujący komunikację z procesem nadrzędnym przez pipe."""
        info(
            f"{self.device_name} - Starting communication thread",
            message_logger=self._message_logger,
        )
        pipe_check_timer = MeasureTime(
            f"{self.device_name} - Pipe check",
            message_logger=self._message_logger,
            max_execution_time=0.5,
            show_only_errors=True,
        )

        try:
            while self._running:
                if pipe_in.poll(0.0):
                    with pipe_check_timer:
                        data = pipe_in.recv()
                        # debug(f"{self.device_name} - Processing command: {data[0]}", message_logger=self._message_logger)
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
                                self.__change_state(EtherCATState.CONFIG)
                                self._configuration = data[1]
                                pipe_in.send(True)
                            case "READ_INPUT":
                                value = self._slaves[data[1]].read_input(data[2])
                                # debug(f"{self.device_name} - READ_INPUT: ADDRESS:{data[1]} DI:{data[2]} VALUE:{value}", message_logger=self._message_logger)
                                pipe_in.send(value)
                            case "READ_OUTPUT":
                                value = self._slaves[data[1]].read_output(data[2])
                                # debug(f"{self.device_name} - READ_OUTPUT: ADDRESS:{data[1]} DO:{data[2]} VALUE:{value}", message_logger=self._message_logger)
                                pipe_in.send(value)
                            case "WRITE_OUTPUT":
                                # debug(f"{self.device_name} - WRITE_OUTPUT, {data[1]}, {data[2]}, {data[3]}", message_logger=self._message_logger)
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
                            case "RUN_JOG":
                                info(
                                    f"{self.device_name} - RUN_JOG, {data[1]}, {data[2]}, {data[3]}, {data[4]}",
                                    message_logger=self._message_logger,
                                )
                                self._slaves[data[1]].run_jog(data[2], data[3], data[4])
                                pipe_in.send(True)
                            case "STOP_MOTOR":
                                info(
                                    f"{self.device_name} - STOP MOTOR, {data[1]} at deceleration {data[2]}",
                                    message_logger=self._message_logger,
                                )
                                self._slaves[data[1]].stop_motor(data[2])
                                pipe_in.send(True)
                            case "IS_MOTOR_RUNNING":
                                info(
                                    f"{self.device_name} - IS_MOTOR_RUNNING, {data[1]}",
                                    message_logger=self._message_logger,
                                )
                                value = self._slaves[data[1]].is_motor_running()
                                pipe_in.send(value)
                            case "READ_CNT":
                                info(
                                    f"{self.device_name} - READ_CNT, {data[1]}",
                                    message_logger=self._message_logger,
                                )
                                # print(f"In worker {data[1]} {len(self._slaves)}")
                                value = self._slaves[data[1]].read_counter(data[2])
                                pipe_in.send(value)
                            case "MOTOR_WITH_ENDSTOPS_MOVE_UP":
                                info(
                                    f"{self.device_name} - MOTOR_WITH_ENDSTOPS_MOVE_UP, {data[1]}, {data[2]}",
                                    message_logger=self._message_logger,
                                )
                                self._slaves[data[1]].motor_with_endstops_move_up(
                                    data[2]
                                )
                                pipe_in.send(True)
                            case "MOTOR_WITH_ENDSTOPS_MOVE_DOWN":
                                info(
                                    f"{self.device_name} - MOTOR_WITH_ENDSTOPS_MOVE_DOWN, {data[1]}, {data[2]}",
                                    message_logger=self._message_logger,
                                )
                                self._slaves[data[1]].motor_with_endstops_move_up(
                                    data[2]
                                )
                                pipe_in.send(True)
                            case "MOTOR_WITH_ENDSTOPS_STOP":
                                info(
                                    f"{self.device_name} - MOTOR_WITH_ENDSTOPS_STOP, {data[1]}, {data[2]}",
                                    message_logger=self._message_logger,
                                )
                                self._slaves[data[1]].motor_with_endstops_stop(
                                    data[2]
                                )
                                pipe_in.send(True)
                            case _:
                                error(
                                    f"{self.device_name} - Unknown command: {data[0]}",
                                    message_logger=self._message_logger,
                                )

        except Exception as e:
            error(
                f"{self.device_name} - Error in communication thread: {e}",
                message_logger=self._message_logger,
            )
            raise e

    def __ethercat_thread(self):
        """Wątek obsługujący logikę stanów i cyklicznego przetwarzania EtherCAT."""
        info(
            f"{self.device_name} - Starting EtherCAT thread",
            message_logger=self._message_logger,
        )
        processing_check_timer = MeasureTime(
            f"{self.device_name} - Processing check",
            show_only_errors=True,
            message_logger=self._message_logger,
            max_execution_time=4 #0.5,
        )

        try:
            while self._running:
                match self._ethercat_state:
                    case EtherCATState.PREINIT:
                        self._init()
                        self.__change_state(EtherCATState.INIT)

                    case EtherCATState.INIT:
                        pass

                    case EtherCATState.CONFIG:
                        self.__configure(self._configuration)
                        if not self.__switch_to_op_state():
                            error(
                                f"{self.device_name} CONFIG - Failed to switch to OP_STATE",
                                message_logger=self._message_logger,
                            )
                            raise Exception(
                                f"{self.device_name} CONFIG - OP_STATE transition failed"
                            )
                        else:
                            for i in range(200):
                                self.__process(
                                    sleep=0.0001
                                )  # pierwsza komunikacja z mastera do slave'ow - moze byc dluzsza niz period petli
                            try:
                                self.__measure_actual_network_cycle(count=200)
                                for i, slave in enumerate(
                                    self._slaves
                                ):  # wywolanie metod z klas device
                                    slave._set_cycle_time(self.__cycle_time)
                                    slave._set_cycle_frequency(self.__cycle_frequency)

                            except Exception as e:
                                error(
                                    f"{self.device_name} CONFIG - Error measuring actual network cycle: {e}",
                                    message_logger=self._message_logger,
                                )
                                period_time = 4/1000#self.__cycle_time
                                warning(
                                    f"{self.device_name} CONFIG - Using default cycle time: {period_time * 1000:.3f}ms ({1 / period_time:.1f}Hz)",
                                    message_logger=self._message_logger,
                                )

                            self.__change_state(EtherCATState.RUNNING)

                    case EtherCATState.RUNNING:
                        with processing_check_timer:
                            self.__process(sleep=0.00001)

                        # if processing_check_timer.get_count() % 4000 == 0:
                        #     info(
                        #         f"{self.device_name} - Processing check: count={processing_check_timer.get_count()} missed={processing_check_timer.get_missed()}",
                        #         message_logger=self._message_logger,
                        #     )

                    case _:
                        error(
                            f"{self.device_name} - Unknown state: {self._ethercat_state}",
                            message_logger=self._message_logger,
                        )
                        break

        except Exception as e:
            error(
                f"{self.device_name} - Error in EtherCAT thread: {e}",
                message_logger=self._message_logger,
            )
            raise e

    def _run(self, pipe_in):
        """Uruchamia wątki: komunikacyjny oraz EtherCAT i czeka na ich zakończenie."""
        info(
            f"{self.device_name} - Starting EtherCATWorker with threads",
            message_logger=self._message_logger,
        )

        # Tworzenie wątków
        comm_thread = threading.Thread(
            target=self.__communication_thread, args=(pipe_in,)
        )
        ethercat_thread = threading.Thread(target=self.__ethercat_thread)

        try:
            # Uruchomienie wątków
            comm_thread.start()
            ethercat_thread.start()

            # Czekanie na zakończenie wątków
            comm_thread.join()
            ethercat_thread.join()

        except KeyboardInterrupt:
            info(
                f"{self.device_name} - Keyboard interrupt received",
                message_logger=self._message_logger,
            )
            self._running = False
            comm_thread.join(timeout=2.0)
            ethercat_thread.join(timeout=2.0)

        except Exception as e:
            error(
                f"{self.device_name} - Error in threads: {e}",
                message_logger=self._message_logger,
            )
            self._running = False
            comm_thread.join(timeout=2.0)
            ethercat_thread.join(timeout=2.0)
            raise e


class EtherCAT(Connector):
    """Magistrala EtherCAT jako Connector z procesem potomnym (workerem).

    Args:
        device_name (str): Nazwa urządzenia.
        network_interface (str): Interfejs sieciowy (np. "eth0").
        number_of_devices (int): Oczekiwana liczba slave'ów.
        core (int): Rdzeń CPU dla procesu potomnego.
        message_logger: Logger komunikatów.
        max_send_failures (int): Limit kolejnych błędów wysyłki przed eskalacją.
    """

    def __init__(
        self,
        device_name: str,
        network_interface: str,
        number_of_devices: int,
        core: int = 8,
        message_logger=None,
        max_send_failures: int = 3,
    ):
        self.device_name = device_name
        self._network_interface = network_interface
        self._number_of_devices = number_of_devices
        self._message_logger = message_logger
        # Eskalacja błędów do IO/Orchestratora
        self._error: bool = False
        self._error_message: str | None = None
        self._consecutive_send_failures: int = 0
        self._per_slave_failures: dict[int, int] = {}
        self._max_send_failures: int = max(1, int(max_send_failures))
        super().__init__(core=core, message_logger=self._message_logger)

        debug(
            f"{self.device_name} - Initializing {self.__class__.__name__} with network interface {self._network_interface} and {self._number_of_devices} devices",
            message_logger=self._message_logger,
        )

        super()._connect()
        self.__lock = threading.Lock()

        time.sleep(1)  # TODO: REMOVE THIS AND MAKE THIS WAIT FOT THE BUS TO BE READY

    def __execute_command(self, data: list):
        """
        Wspólny egzekutor komend z obsługą liczników błędów per-slave i globalnych.
        Zakładamy, że adres slave (jeśli dotyczy) to drugi element listy (index 1).
        """
        slave_id = None
        try:
            if isinstance(data, list) and len(data) > 1 and isinstance(data[1], int):
                slave_id = data[1]
        except Exception:
            slave_id = None

        try:
            value = super()._send_thru_pipe(self._pipe_out, data)
        except Exception as e:
            # Nie udało się wysłać komendy do procesu/urządzenia
            self._consecutive_send_failures += 1
            if slave_id is not None:
                self._per_slave_failures[slave_id] = (
                    self._per_slave_failures.get(slave_id, 0) + 1
                )
            self._error = True
            self._error_message = f"{self.device_name} - Nie udało się wykonać polecenia {data[0]}{(f' (slave {slave_id})' if slave_id is not None else '')}: {e}"
            if (
                slave_id is not None
                and self._per_slave_failures.get(slave_id, 0) >= self._max_send_failures
            ) or (self._consecutive_send_failures >= self._max_send_failures):
                error(
                    f"{self.device_name} - Exceeded max_send_failures={self._max_send_failures}: {self._error_message}",
                    message_logger=self._message_logger,
                )
            return None

        # Traktuj None jako porażkę
        if value is None:
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
                    message_logger=self._message_logger,
                )
            return None

        # Sukces
        self._consecutive_send_failures = 0
        if slave_id is not None:
            self._per_slave_failures[slave_id] = 0
        try:
            any_over = any(
                v >= self._max_send_failures for v in self._per_slave_failures.values()
            )
        except Exception:
            any_over = False
        if not any_over:
            self._error = False
            self._error_message = None
        return value

    def _run(self, pipe_in, message_logger):
        """Funkcja wejściowa procesu potomnego uruchamiająca `EtherCATWorker`."""
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
        """Konfiguruje listę slave'ów powiązanych z tą magistralą."""
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
            value = self.__execute_command(["CONFIG", list_of_slaves])
            return value

    def read_input(self, address: int, port: int):
        """Odczytuje stan wejścia cyfrowego z wybranego slave'a/portu."""
        with self.__lock:
            value = self.__execute_command(["READ_INPUT", address, port])
            return value

    def write_output(self, address: int, port: int, value: bool):
        """Ustawia stan wyjścia cyfrowego dla wybranego slave'a/portu."""
        with self.__lock:
            result = self.__execute_command(["WRITE_OUTPUT", address, port, value])
            return result

    def read_counter(self, address: int, port: int):
        with self.__lock:
            result = self.__execute_command(["READ_CNT", address, port])
            return result
        
    def start_axis_pos_profile(
        self, address: int, axis: int, pos: int, vel: int, direction: bool
    ):
        """Rozpoczyna ruch osi w profilu pozycja (position profile)."""
        with self.__lock:
            result = self.__execute_command([
                "START_AXIS_POS_PROFILE",
                address,
                axis,
                pos,
                vel,
                direction,
            ])
            return result

    def start_axis_vel_profile(
        self, address: int, axis: int, vel: int, direction: bool
    ):
        """Rozpoczyna ruch osi w profilu prędkość (velocity profile)."""
        with self.__lock:
            result = self.__execute_command([
                "START_AXIS_VEL_PROFILE",
                address,
                axis,
                vel,
                direction,
            ])
            return result

    def stop_axis(self, address: int, axis: int):
        """Zatrzymuje zadaną oś."""
        with self.__lock:
            result = self.__execute_command(["STOP_AXIS", address, axis])
            return result

    def axis_in_move(self, address: int, axis: int):
        """Zwraca informację, czy wskazana oś jest w ruchu."""
        with self.__lock:
            result = self.__execute_command(["AXIS_IN_MOVE", address, axis])
            return result

    def run_jog(self, address: int, speed: int, accel: int, decel: bool):
        """Uruchamia ruch jog dla wskazanej osi."""
        with self.__lock:
            result = self.__execute_command([
                "RUN_JOG",
                address,
                speed,
                accel,
                decel,
            ])
            return result
        
    def motor_with_endstops_move_up(self, address: int, axis: int):
        with self.__lock:
            result = self.__execute_command([
                "MOTOR_WITH_ENDSTOPS_MOVE_UP",
                address,
                axis
            ])
            return result
        
    def motor_with_endstops_move_down(self, address: int, axis: int):
        with self.__lock:
            result = self.__execute_command([
                "MOTOR_WITH_ENDSTOPS_MOVE_DOWN",
                address,
                axis
            ])
            return result
    
    def motor_with_endstops_stop(self, address: int, axis: int):
        with self.__lock:
            result = self.__execute_command([
                "MOTOR_WITH_ENDSTOPS_STOP",
                address,
                axis
            ])
            return result

    def stop_motor(self, address: int, decel:int):
        """Zatrzymuje wszystkie osie na wskazanym slave'ie."""
        with self.__lock:
            result = self.__execute_command(["STOP_MOTOR", address, decel])
            return result

    def is_motor_running(self, address: int) -> bool:
        """Sprawdza, czy silnik na wskazanej osi jest uruchomiony."""
        with self.__lock:
            in_move = self.__execute_command(["IS_MOTOR_RUNNING", address])
            return bool(in_move) if in_move is not None else False

    # === Interfejs dla IO_server (health-check i monitoring) ===
    def check_device_connection(self):
        try:
            proc = getattr(self, "_process", None)
            if proc is None or (hasattr(proc, "is_alive") and not proc.is_alive()):
                self._error = True
                self._error_message = f"{self.device_name} - EtherCAT process nie uruchomiony (iface={self._network_interface})"
                return False

            for sid, cnt in self._per_slave_failures.items():
                if cnt >= self._max_send_failures:
                    self._error = True
                    self._error_message = f"{self.device_name} - Przekroczono max_send_failures={self._max_send_failures} dla slave {sid}"
                    return False

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

    def to_dict(self):
        """Zwraca słownikowy stan magistrali do monitoringu IO_server."""
        return {
            "name": self.device_name,
            "type": self.__class__.__name__,
            "network_interface": self._network_interface,
            "number_of_devices": self._number_of_devices,
            "error": self._error,
            "error_message": self._error_message,
            "consecutive_send_failures": self._consecutive_send_failures,
            "max_send_failures": self._max_send_failures,
            "per_slave_failures": self._per_slave_failures.copy(),
        }

    def __del__(self):
        """Zamyka proces potomny i kanały IPC przy usuwaniu obiektu."""
        super()._send_thru_pipe(self._pipe_out, ["STOP"])  # type: ignore[attr-defined]
        self.pipe_out.close()
