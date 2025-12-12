import time
from enum import Enum

from avena_commons.event_listener import Event, Result
from avena_commons.io import VirtualDevice, VirtualDeviceState
from avena_commons.io.virtual_device.sensor_watchdog import SensorTimerTask
from avena_commons.util.logger import MessageLogger, debug, error, info, warning


class WydawkaState(Enum):
    IDLE = 0
    RUNNING = 1
    STOPPING = 2
    BACK = 4
    ENABLING_MAINTENANCE = 199
    MAINTENANCE = 200
    DISABLING_MAINTENANCE = 201
    ERROR = 255


class Wydawka(VirtualDevice):
    def __init__(
        self,
        steps: int = 539,
        external_encoder_reverse_direction: bool = True,
        max_velocity=90,
        veloctiy_segments=[[0.0, 1.0], [0.55, 0.5], [0.90, 0.35], [0.95, 0.1]],
        max_correction_steps: int = 100,
        timeouts: dict | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.__fsm = WydawkaState.IDLE
        self.set_state(VirtualDeviceState.INITIALIZING)
        # Apply compensation factor to account for consistent overshooting (~14%)
        self.steps = steps
        self.__external_encoder_reverse_direction = external_encoder_reverse_direction
        self.__starting_position: int = 0
        self.__encoder_correct: int = 0
        self.__target_steps: int = 0
        self.__debug = True
        self.__max_correction_steps = max_correction_steps

        self.__veloctiy_segments = veloctiy_segments
        self.__veloctiy_segments_index = 0
        self.__max_velocity = max_velocity

        # Przechowywanie bieżącego i poprzedniego odczytu enkodera oraz flagi zmiany,
        # chcemy mieć prosty słownik ze stanem,
        # aby w warunku timeoutu można było łatwo sprawdzać zmianę wartości.
        self.__encoder_state = {
            "last": 0,
            "current": 0,
            "changed": False,
        }
        self.__encoder_initialized = False

        # Konfigurowalne timeouty (ładowane z configuration w JSON)
        # Domyślne wartości pozostają jak dotychczas: 5s na wystartowanie i zatrzymanie
        self.__timeouts = {
            "start_encoder_change": 3.0,  # Oczekiwanie na zmianę enkodera po starcie
            "stop_encoder_no_change": 3.0,  # Oczekiwanie na brak zmian enkodera po zatrzymaniu
            # "start_move_delay": 0.2,  # Opóźnienie przed rozpoczęciem ruchu po wywołaniu komendy
        }
        if isinstance(timeouts, dict):
            try:
                self.__timeouts.update({k: float(v) for k, v in timeouts.items()})
            except Exception:
                warning(
                    f"{self.device_name} - Nieprawidłowe wartości w 'timeouts' konfiguracji, używam domyślnych",
                    message_logger=self._message_logger,
                )

    def __move_forward(self, **kwargs):
        # start_time = time.time()
        # while time.time() - start_time < self.__timeouts["start_move_delay"]:
        #     continue
        return getattr(self.devices[kwargs["device"]], kwargs["method"])(speed=kwargs["speed"])

    def __stop(self, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])()

    def __read_encoder(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])()
        if not self.__encoder_initialized:
            # Pierwsza inicjalizacja - brak sztucznego zgłoszenia zmiany
            self.__encoder_state["last"] = value
            self.__encoder_state["current"] = value
            self.__encoder_state["changed"] = False
            self.__encoder_initialized = True
        else:
            self.__encoder_state["last"] = self.__encoder_state["current"]
            self.__encoder_state["current"] = value
            self.__encoder_state["changed"] = self.__encoder_state["current"] != self.__encoder_state["last"]
        return value

    def get_encoder_changed(self) -> bool:
        """
        Zwraca informację czy wartość enkodera uległa zmianie od ostatniego odczytu.

        Może być użyte bezpośrednio w warunku timeoutu, np. w `add_sensor_timeout`:
        `condition=lambda: self.get_encoder_changed()`.
        """
        try:
            return bool(self.__encoder_state["changed"])
        except Exception:
            return False

    def _on_encoder_timeout(self, task: SensorTimerTask) -> None:
        error(f"{self.device_name} - Encoder timeout: {task.description}", message_logger=self._message_logger)
        if self.__fsm == WydawkaState.RUNNING:
            self.__stop(**self.methods["stop"])
            self._move_event_to_finished(event_type="wydawka_move", result="error")

    def __is_motor_running(self, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])()

    def __is_failure(self, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])()

    def _instant_execute_event(self, event: Event) -> Event:
        return event

    def get_current_state(self):
        return self._state

    def tick(self):
        # należy przejąć event niewazne w jakim stanie bedzie wydawka:
        if self._processing_events.get("wydawka_maintenance_enable"):
            self.__fsm = WydawkaState.ENABLING_MAINTENANCE

        # normalna praca wydawki:
        encoder_position = (-1 if self.__external_encoder_reverse_direction else 1) * self.__read_encoder(**self.methods["read_encoder"])
        match self.__fsm:
            case WydawkaState.IDLE:
                if self._state == VirtualDeviceState.INITIALIZING:
                    self.set_state(VirtualDeviceState.WORKING)
                if self._processing_events.get("wydawka_move"):
                    if self.__debug:
                        debug(f"{self.device_name} - start przesuwania, pozycja enkodera: {encoder_position}", message_logger=self._message_logger)
                    self.__starting_position = encoder_position
                    if self.__debug:
                        debug(f"{self.device_name} - Start position: {self.__starting_position} encoder correct: {self.__encoder_correct}", message_logger=self._message_logger)

                    self.__move_forward(speed=int(self.__max_velocity * self.__veloctiy_segments[0][1]), **self.methods["move_forward"])
                    self.add_sensor_timeout(
                        condition=lambda: self.get_encoder_changed(), timeout_s=self.__timeouts["start_encoder_change"], description="Silnik się nie ruszył"
                    )
                    self.__fsm = WydawkaState.RUNNING
                    self.__target_steps = self.steps - self.__encoder_correct
                    # self.__target_steps = 560
                    self.__veloctiy_segments_index = 0

            case WydawkaState.RUNNING:
                is_motor_running = self.__is_motor_running(**self.methods["is_motor_running"])
                is_failure = self.__is_failure(**self.methods["is_failure"])
                debug(f"{self.device_name} - encoder: {encoder_position} is_motor_running: {is_motor_running}, is_failure: {is_failure}", message_logger=self._message_logger)

                debug(f"{self.device_name} - RUNNING {encoder_position - self.__starting_position} > {self.__target_steps}", message_logger=self._message_logger)
                if encoder_position - self.__starting_position >= self.__target_steps:
                    if self.__debug:
                        debug(
                            f"{self.device_name} - stop przesuwania, pozycja: {encoder_position - self.__starting_position}, docelowa pozycja: {self.__target_steps}",
                            message_logger=self._message_logger,
                        )
                    self.__stop(**self.methods["stop"])
                    self.add_sensor_timeout(
                        condition=lambda: not self.get_encoder_changed(), timeout_s=self.__timeouts["stop_encoder_no_change"], description="Silnik się nie zatrzymał"
                    )
                    self.__fsm = WydawkaState.STOPPING
                    self._move_event_to_finished(event_type="wydawka_move", result="success")

                else:
                    match self.__veloctiy_segments_index:
                        case 0:
                            if self.__starting_position - encoder_position >= self.__target_steps * self.__veloctiy_segments[1][0]:
                                self.__veloctiy_segments_index = 1
                                self.__stop(**self.methods["stop"])
                                self.__move_forward(speed=int(90 * self.__veloctiy_segments[1][1]), **self.methods["move_forward"])
                                if self.__debug:
                                    debug(f"{self.device_name} - zmiana prędkości na {self.__veloctiy_segments[1][1]}", message_logger=self._message_logger)
                        case 1:
                            if self.__starting_position - encoder_position >= self.__target_steps * self.__veloctiy_segments[2][0]:
                                self.__veloctiy_segments_index = 2
                                self.__stop(**self.methods["stop"])
                                self.__move_forward(speed=int(90 * self.__veloctiy_segments[2][1]), **self.methods["move_forward"])
                                if self.__debug:
                                    debug(f"{self.device_name} - zmiana prędkości na {self.__veloctiy_segments[2][1]}", message_logger=self._message_logger)
                        case 2:
                            if self.__starting_position - encoder_position >= self.__target_steps * self.__veloctiy_segments[3][0]:
                                self.__veloctiy_segments_index = 3
                                self.__stop(**self.methods["stop"])
                                self.__move_forward(speed=int(90 * self.__veloctiy_segments[3][1]), **self.methods["move_forward"])
                                if self.__debug:
                                    debug(f"{self.device_name} - zmiana prędkości na {self.__veloctiy_segments[3][1]}", message_logger=self._message_logger)
            case WydawkaState.STOPPING:
                is_motor_running = self.__is_motor_running(**self.methods["is_motor_running"])
                if not is_motor_running:
                    # Calculate correction based on actual traveled distance vs target
                    actual_distance = encoder_position - self.__starting_position
                    self.__encoder_correct = actual_distance - self.__target_steps  # Target_steps bug fix
                    if self.__debug:
                        debug(
                            f"{self.device_name} STOP Pozycją końcowa: {encoder_position}, dystans przebyty: {actual_distance}, docelowy dystans: {self.__target_steps}, korekta krokow bazowana z {self.__encoder_correct}",
                            message_logger=self._message_logger,
                        )
                    # if self.__encoder_correct > self.__max_correction_steps:
                    #     self.__fsm = WydawkaState.BACK
                    # else:
                    self.__fsm = WydawkaState.IDLE

            case WydawkaState.BACK:
                self.__move_forward(speed=-10, **self.methods["move_forward"])  # FIXME
                actual_distance = encoder_position - self.__starting_position
                self.__encoder_correct = actual_distance - self.__target_steps  # Target_steps bug fix
                if self.__encoder_correct < 10:
                    self.__stop(**self.methods["stop"])
                    self.__fsm = WydawkaState.STOPPING
                    if self.__debug:
                        debug(
                            f"{self.device_name} ruch w tył: {encoder_position}, dystans przebyty: {actual_distance}, docelowy dystans: {self.__target_steps}, korekta krokow bazowana z {self.__encoder_correct}",
                            message_logger=self._message_logger,
                        )

            case WydawkaState.ENABLING_MAINTENANCE:
                # tryb serwisowy, czekanie na wyjscie z trybu serwisowego przez event
                if self._processing_events.get("wydawka_maintenance_enable"):
                    info(f"{self.device_name} - Wydawka w trybie serwisowym - ciągły ruch", message_logger=self._message_logger)
                    self.__move_forward(speed=int(self.__max_velocity * self.__veloctiy_segments[0][1]), **self.methods["move_forward"])
                    self._move_event_to_finished(event_type="wydawka_maintenance_enable", result="success")
                    self.__fsm = WydawkaState.MAINTENANCE

            case WydawkaState.MAINTENANCE:
                #
                if self._processing_events.get("wydawka_maintenance_disable"):
                    info(f"{self.device_name} - Wydawka w trybie serwisowym - zatrzymanie", message_logger=self._message_logger)
                    self._move_event_to_finished(event_type="wydawka_maintenance_disable", result="success")
                    self.__stop(**self.methods["stop"])  # polecenie stopu silnika
                    self.__fsm = WydawkaState.DISABLING_MAINTENANCE

            case WydawkaState.DISABLING_MAINTENANCE:
                info(f"{self.device_name} - Wydawka wyszła z trybu serwisowego. Przejście do IDLE", message_logger=self._message_logger)
                self.__fsm = WydawkaState.IDLE

            case WydawkaState.ERROR:
                error(f"{self.device_name} - Wydawka w stanie ERROR", message_logger=self._message_logger)
                pass
