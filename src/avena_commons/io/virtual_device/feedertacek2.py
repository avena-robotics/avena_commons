from enum import Enum

from avena_commons.event_listener import Event
from avena_commons.io import VirtualDevice, VirtualDeviceState
from avena_commons.io.virtual_device.sensor_watchdog import SensorTimerTask
from avena_commons.util.logger import debug, error, warning


class FeederTacek2State(Enum):
    IDLE = 0
    RUNNING_FORWARD = 1
    STOP_1 = 2
    RUNNING_BACK = 3
    STOP_2 = 4
    ENABLING_MAINTENANCE = 199
    MAINTENANCE = 200
    DISABLING_MAINTENANCE = 201
    ERROR = 255


class FeederTacek2(VirtualDevice):
    def __init__(self, timeouts: dict | None = None, **kwargs):
        super().__init__(**kwargs)
        self.__fsm = FeederTacek2State.IDLE
        self.set_state(VirtualDeviceState.INITIALIZING)
        # Track DI inputs similar to Oven: store latest states of sensors
        self.__di_sensors = {
            "sensors": [False, False, False, False],  # sensor_1, sensor_2, sensor
        }

        # Konfigurowalne timeouty i opisy (ładowane z configuration w JSON)
        # Domyślne wartości zgodne z dotychczasową logiką
        self.__timeouts = {
            "running_s1_high": 6.0,
            "running_s2_high": 7.0,
            "running_s3_high": 6.0,
            "running_s4_high": 7.0,
            "correction_s2_low": 7.0,
            "correction_s4_low": 7.0,
            "stopping": 1.0,
            "running_forward": 6.0,
            "running_back": 6.0,
        }

        if isinstance(timeouts, dict):
            try:
                self.__timeouts.update({k: float(v) for k, v in timeouts.items()})
            except Exception:
                # Jeśli wartości nie są numeryczne, pozostaw domyślne i zaloguj ostrzeżenie
                warning(
                    f"{self.device_name} - Nieprawidłowe wartości w 'timeouts' konfiguracji, używam domyślnych",
                    message_logger=self._message_logger,
                )

    def __run_jog(self, speed: int, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])(speed=speed)

    def __read_sensor_1(self, **kwargs):
        # debug(f"READ SENSOR 1 {self.device_name} - {self.devices[kwargs['device']]} - reading sensor 1", message_logger=self._message_logger)
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        self.__di_sensors["sensors"][0] = value
        return value

    def __read_sensor_2(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        self.__di_sensors["sensors"][1] = value
        return value

    def __read_sensor_3(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        self.__di_sensors["sensors"][2] = value
        return value

    def __read_sensor_4(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        self.__di_sensors["sensors"][3] = value
        return value

    def __is_motor_running(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])()
        return value

    def __is_failure(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])()
        return value

    def __stop(self, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])()

    def _instant_execute_event(self, event: Event) -> Event:  # FIXME tylko zwracamy?
        return event

    def get_current_state(self):
        return self._state

    def _on_sensor_timeout(self, task: SensorTimerTask) -> None:
        error(f"{self.device_name} - Sensor timeout: {task.description}", message_logger=self._message_logger)
        self.__stop(**self.methods["stop"])
        self._move_event_to_finished(event_type="feeder_place_tray", result="error")

    def get_sensor_state(self, sensor_number: int) -> bool:
        """
        Zwraca stan czujnika (True/False) na podstawie jego numeru.

        sensor_number: 1 dla sensor_1, 2 dla sensor_2.
        """
        try:
            return bool(self.__di_sensors["sensors"][sensor_number - 1])
        except Exception:
            warning(
                f"{self.device_name} - Nieprawidłowy numer sensora: {sensor_number}",
                message_logger=self._message_logger,
            )
            return False

    def tick(self):
        sensor_1 = self.__read_sensor_1(**self.methods["read_sensor_1"])
        sensor_2 = self.__read_sensor_2(**self.methods["read_sensor_2"])
        sensor_3 = self.__read_sensor_3(**self.methods["read_sensor_3"])
        sensor_4 = self.__read_sensor_4(**self.methods["read_sensor_4"])
        running = self.__is_motor_running(**self.methods["is_motor_running"])
        is_failure = self.__is_failure(**self.methods["is_failure"])
        # debug(f"{self.device_name} ---     is_failure: {type(is_failure)} {is_failure} {type(running)} {running} {type(sensor_1)}", message_logger=self._message_logger)

        # if self._state == VirtualDeviceState.ERROR:
        # FIXME is_failure zwraca is_failure: <bound method TLC57R24V08.is_failure of TLC57R24V08(device_name='TLC57R24V08_feedertacek_1', address=13, config_type=2, reverse_direction=False, operation_status={in_place=True, homing_completed=False, motor_running=False, failure=False, motor_enabling=False, positive_limit=False, negative_limit=False}, current_alarms={overcurrent=False, overvoltage=False, undervoltage=False}, di_value=5, do_current_state=[0, 0, 0])>
        if self._state == VirtualDeviceState.ERROR or bool(is_failure):
            self.__fsm = FeederTacek2State.ERROR

        match self.__fsm:
            case FeederTacek2State.IDLE:
                if self._state == VirtualDeviceState.INITIALIZING:
                    self.set_state(VirtualDeviceState.WORKING)
                if self._processing_events.get("feeder_place_tray"):
                    if sensor_1:
                        # error(
                        #     f"{self.device_name} - Próba wydania tacki gdy poprzednia zaslania sensor 1",
                        #     message_logger=self._message_logger,
                        # )
                        self._error_message = f"{self.device_name} - Próba wydania tacki gdy poprzednia zaslania sensor 1"  # Musi być error message, inaczej system nie wie dlaczego błąd i jest pełna Awaria APS
                        self.__fsm = FeederTacek2State.ERROR
                        self.set_state(VirtualDeviceState.ERROR)
                        return

                    debug(f"{self.device_name} - Place tray - start feeding", message_logger=self._message_logger)
                    self.__run_jog(speed=8000, **self.methods["run_jog"])  # start 1 ruchu og speed -80
                    self.add_sensor_timeout(
                        condition=lambda: self.get_sensor_state(2),
                        timeout_s=self.__timeouts["running_s2_high"],
                        description="tacka się nie wysuneła: sensor 2 nie został aktywowany",
                        metadata={"device": self.device_name},
                    )
                    self.add_sensor_timeout(
                        condition=lambda: self.get_sensor_state(4),
                        timeout_s=self.__timeouts["running_s4_high"],
                        description="tacka się nie wysuneła: sensor 4 nie został aktywowany",
                        metadata={"device": self.device_name},
                    )
                    self.add_sensor_timeout(
                        condition=lambda: self.get_sensor_state(3),
                        timeout_s=self.__timeouts["running_s3_high"],
                        description="tacka się nie wysuneła: sensor 3 nie został aktywowany",
                        metadata={"device": self.device_name},
                    )
                    self.add_sensor_timeout(
                        condition=lambda: self.get_sensor_state(1),
                        timeout_s=self.__timeouts["running_s1_high"],
                        description="tacka nie została wydana",
                        metadata={"device": self.device_name},
                    )
                    self.__fsm = FeederTacek2State.RUNNING_FORWARD
                    debug(f"{self.device_name} - Place tray - {self.__fsm.name}", message_logger=self._message_logger)

            case FeederTacek2State.RUNNING_FORWARD:
                debug(f"{self.device_name} - Sensor 1: {sensor_1}", message_logger=self._message_logger)
                debug(f"{self.device_name} - Sensor 2: {sensor_2}", message_logger=self._message_logger)
                debug(f"{self.device_name} - Sensor 3: {sensor_3}", message_logger=self._message_logger)
                debug(f"{self.device_name} - Sensor 4: {sensor_4}", message_logger=self._message_logger)

                if sensor_1:
                    self.__stop(**self.methods["stop"])  # zatrzymanie ruchu
                    self.__fsm = FeederTacek2State.STOP_1
                    self.add_sensor_timeout(
                        condition=lambda: not bool(self.__is_motor_running(**self.methods["is_motor_running"])),
                        timeout_s=self.__timeouts["stopping"],
                        description="silnik sie nie zatrzymał po wydaniu polecenia stop",
                        metadata={"device": self.device_name, "fsm_state": self.__fsm.name},
                    )
                    debug(f"{self.device_name} - Place tray - {self.__fsm.name}", message_logger=self._message_logger)

            case FeederTacek2State.STOP_1:
                if not running:
                    self.__run_jog(speed=-4000, **self.methods["run_jog"])  # start 2 ruchu og speed 40
                    self.add_sensor_timeout(
                        condition=lambda: not self.get_sensor_state(2),
                        timeout_s=self.__timeouts["correction_s2_low"],
                        description="tacka nie została schowana/brak przerwy między tackami - sensor 2",
                        metadata={"device": self.device_name},
                    )
                    self.add_sensor_timeout(
                        condition=lambda: not self.get_sensor_state(4),
                        timeout_s=self.__timeouts["correction_s4_low"],
                        description="tacka nie została schowana/brak przerwy między tackami - sensor 4",
                        metadata={"device": self.device_name},
                    )
                    self.__fsm = FeederTacek2State.RUNNING_BACK
                    debug(f"{self.device_name} - Place tray - {self.__fsm.name}", message_logger=self._message_logger)

            case FeederTacek2State.RUNNING_BACK:
                if not sensor_2 and not sensor_4:
                    self.__stop(**self.methods["stop"])  # zatrzymanie ruchu
                    self.__fsm = FeederTacek2State.STOP_2
                    self.add_sensor_timeout(
                        condition=lambda: not bool(self.__is_motor_running(**self.methods["is_motor_running"])),
                        timeout_s=self.__timeouts["stopping"],
                        description="silnik sie nie zatrzymał po wydaniu polecenia stop",
                        metadata={"device": self.device_name, "fsm_state": self.__fsm.name},
                    )
                    debug(f"{self.device_name} - Place tray - {self.__fsm.name}", message_logger=self._message_logger)

            case FeederTacek2State.STOP_2:
                if not running:
                    self._move_event_to_finished(event_type="feeder_place_tray", result="success")
                    self.__fsm = FeederTacek2State.IDLE
                    debug(f"{self.device_name} - Place tray - {self.__fsm.name}", message_logger=self._message_logger)

            case FeederTacek2State.ERROR:
                warning(f"{self.device_name} - Feeder in ERROR state", message_logger=self._message_logger)
                warning(f"{self.device_name} ---     is_failure: {bool(is_failure)}", message_logger=self._message_logger)
                warning(f"{self.device_name} ---     self._state: {self._state}", message_logger=self._message_logger)
                self._move_event_to_finished(event_type="feeder_place_tray", result="failure")
