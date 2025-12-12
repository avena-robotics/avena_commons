import time
from enum import Enum

from avena_commons.event_listener import Event, Result
from avena_commons.event_listener.types import IoSignal
from avena_commons.io import VirtualDevice, VirtualDeviceState
from avena_commons.util.logger import MessageLogger, debug, error, info, warning

from lib.io.virtual_device.enums import KomoraOdbiorczaState

# class GenericState(Enum):
#     IDLE = 0
#     RUNNING = 1
#     ERROR = 255


class KomoraOdbiorczaZamek(Enum):
    ODBLOKOWANY = 1
    ZABLOKOWANY = 0


class KomoraOdbiorcza(VirtualDevice):
    def __init__(self, timeouts: dict | None = None, **kwargs):
        super().__init__(**kwargs)
        self.__fsm = KomoraOdbiorczaState.UNKNOWN
        self.set_state(VirtualDeviceState.UNINITIALIZED)

        # Konfigurowalne timeouty (sekundy)
        self.__timeouts = {
            "partition_open_reached": 10.0,
            "partition_close_reached": 10.0,
            "gate_locked_confirmed": 2.0,
            "gate_unlocked_confirmed": 2.0,
            "gate_closed_confirmed": 180.0,
            # "gate_closed_error": 300.0,
        }
        if isinstance(timeouts, dict):
            try:
                for k, v in timeouts.items():
                    if k in self.__timeouts:
                        self.__timeouts[k] = float(v)
            except Exception:
                warning(
                    f"{self.device_name} - Nieprawidłowe wartości w 'timeouts' konfiguracji, używam domyślnych",
                    message_logger=self._message_logger,
                )

        # Cache stanów DI (aktualizowany w tick())
        self.__di_sensors = {
            "chamber_open": False,
            "partition": {"up": False, "down": False},
            "product": [False, False],  # 1, 2
            "sauce": [False, False, False],  # 1, 2, 3
            "block_state": None,  # surowa wartość z __block_for_client_check (0/1)
            "failure": False,
        }

    # eventy:
    # block_for_client
    # unblock_for_client
    # block_chamber
    # unblock_chamber
    # partition_up
    # partition_down
    # is_product_present
    # is_sauce_present

    @property
    def fsm(self) -> KomoraOdbiorczaState:
        return self.__fsm

    @fsm.setter
    def fsm(self, value: KomoraOdbiorczaState):
        debug(f"{self.device_name} - Setting FSM from {self.__fsm.name} to {value.name}", message_logger=self._message_logger)
        self.__fsm = value

    def __block_for_client(self, **kwargs):  # zalaczenie przekaznika blokady : 1 - zablokowanie, 0 - odblokowanie
        setattr(self.devices[kwargs["device"]], kwargs["method"], kwargs["value"])

    def __block_for_client_check(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        self.__di_sensors["block_state"] = value
        return value

    def __is_chamber_open(self, **kwargs):  # sprawdzenie czy komora jest otwarta przez czujnik krancowy od strony klienta
        value = not getattr(self.devices[kwargs["device"]], kwargs["method"])
        self.__di_sensors["chamber_open"] = bool(value)
        return value

    def __is_sauce_1_sensor(self, **kwargs):  # sprawdzenie czy czujnik sosu 1 jest aktywny
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        self.__di_sensors["sauce"][0] = bool(value)
        return value

    def __is_sauce_2_sensor(self, **kwargs):  # sprawdzenie czy czujnik sosu 2 jest aktywny
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        self.__di_sensors["sauce"][1] = bool(value)
        return value

    def __is_sauce_3_sensor(self, **kwargs):  # sprawdzenie czy czujnik sosu 3 jest aktywny
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        self.__di_sensors["sauce"][2] = bool(value)
        return value

    def __is_product_sensor_1(self, **kwargs):  # sprawdzenie czy czujnik produktu 1 jest aktywny
        debug(f"{self.device_name} - is_product_sensor_1={kwargs}", message_logger=self._message_logger)
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        self.__di_sensors["product"][0] = bool(value)
        return value

    def __is_product_sensor_2(self, **kwargs):  # sprawdzenie czy czujnik produktu 2 jest aktywny
        debug(f"{self.device_name} - is_product_sensor_2={kwargs}", message_logger=self._message_logger)
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        self.__di_sensors["product"][1] = bool(value)
        return value

    def __move_partition(self, **kwargs):  # otwarcie przegrody wewnetrznej : 1 - otwarcie, 0 - zamkniecie
        return getattr(self.devices[kwargs["device"]], kwargs["method"])(speed=kwargs["speed"])

    def __is_failure(self, **kwargs):  # sprawdzenie czy wystąpił błąd w silniku przegrody
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])()
        self.__di_sensors["failure"] = bool(value)
        return value

    def __reset_error(self, **kwargs):  # zresetowanie błędu w silniku przegrody
        return getattr(self.devices[kwargs["device"]], kwargs["method"])()

    def __is_partition_up(self, **kwargs):  # sprawdzenie czy przegroda wewnetrzna jest podniesiona
        result = getattr(self.devices[kwargs["device"]], kwargs["method"])
        self.__di_sensors["partition"]["up"] = bool(result)
        debug(f"{self.device_name} - Is partition up: {result}", message_logger=self._message_logger)
        return result

    def __is_partition_down(self, **kwargs):  # sprawdzenie czy przegroda wewnetrzna jest opuszczona
        result = getattr(self.devices[kwargs["device"]], kwargs["method"])
        self.__di_sensors["partition"]["down"] = bool(result)
        debug(f"{self.device_name} - Is partition down: {result}", message_logger=self._message_logger)
        return result

    def __led_relay_colour(self, **kwargs):  # zalaczenie przekaznika koloru diody : 1 - biała, 0 - czerwony
        # return getattr(self.devices[kwargs["device"]], kwargs["method"])(value=kwargs["value"])
        setattr(self.devices[kwargs["device"]], kwargs["method"], kwargs["value"])

    def __is_sauce_1_init(self, **kwargs):  # sprawdzenie czy czujnik sosu jest zinitowany
        return getattr(self.devices[kwargs["device"]], kwargs["method"])

    def __is_sauce_2_init(self, **kwargs):  # sprawdzenie czy czujnik sosu jest zinitowany
        return getattr(self.devices[kwargs["device"]], kwargs["method"])

    def __is_sauce_3_init(self, **kwargs):  # sprawdzenie czy czujnik sosu jest zinitowany
        return getattr(self.devices[kwargs["device"]], kwargs["method"])

    def __is_product_present(self) -> bool:
        # odczyt aktualizuje cache
        product_sensor_1 = self.__is_product_sensor_1(**self.methods["product_sensor_1"]) if "product_sensor_1" in self.methods else self.__di_sensors["product"][0]
        product_sensor_2 = self.__is_product_sensor_2(**self.methods["product_sensor_2"]) if "product_sensor_2" in self.methods else self.__di_sensors["product"][1]
        is_present = bool(product_sensor_1 or product_sensor_2)
        debug(
            f"{self.device_name} - product_sensor_1: {product_sensor_1}, product_sensor_2: {product_sensor_2}, is_present: {is_present}",
            message_logger=self._message_logger,
        )
        return is_present

    def __is_sauce_present(self) -> bool:
        # odczyty aktualizują cache
        if "sauce_1_sensor" in self.methods:
            self.__is_sauce_1_sensor(**self.methods["sauce_1_sensor"])
        if "sauce_2_sensor" in self.methods:
            self.__is_sauce_2_sensor(**self.methods["sauce_2_sensor"])
        if "sauce_3_sensor" in self.methods:
            self.__is_sauce_3_sensor(**self.methods["sauce_3_sensor"])
        return bool(self.__di_sensors["sauce"][0] or self.__di_sensors["sauce"][1] or self.__di_sensors["sauce"][2])

    def __is_sauce_init(self) -> bool:
        init_sauce_sensor_1 = self.__is_sauce_1_init(**self.methods["sauce_1_init_sensor"])
        init_sauce_sensor_2 = self.__is_sauce_2_init(**self.methods["sauce_2_init_sensor"])
        init_sauce_sensor_3 = self.__is_sauce_3_init(**self.methods["sauce_3_init_sensor"])
        are_inited = init_sauce_sensor_1 and init_sauce_sensor_2 and init_sauce_sensor_3

        return are_inited

    def __check_chamber_open(self):  # sprawdzenie czy komora jest otwarta przez czujnik krancowy od strony klienta
        if self.__is_chamber_open(**self.methods["chamber_open"]):
            # self.fsm = KomoraOdbiorczaState.ERROR
            raise Exception(
                f"{self.device_name} - # sprawdzenie czy komora jest otwarta przez czujnik krancowy od strony klienta: Komora klienta jest otwarta, a powinna byc zamknieta zamkiem!"
            )

    # === Predykaty (True/False) do użycia w add_sensor_timeout ===
    def get_partition_opened(self) -> bool:
        try:
            return bool(self.__di_sensors["partition"]["up"])
        except Exception:
            return False

    def get_partition_closed(self) -> bool:
        try:
            return bool(self.__di_sensors["partition"]["down"])
        except Exception:
            return False

    def get_gate_locked(self) -> bool:
        try:
            chamber_closed = not bool(self.__di_sensors["chamber_open"])  # zamknięta => True
        except Exception:
            chamber_closed = False
        try:
            coil_value = self.__di_sensors["block_state"]
            coil_ok = (coil_value == KomoraOdbiorczaZamek.ZABLOKOWANY.value) if coil_value is not None else True
        except Exception:
            coil_ok = True
        return bool(chamber_closed and coil_ok)

    def get_gate_unlocked(self) -> bool:
        try:
            coil_value = self.__di_sensors["block_state"]
            coil_unlocked = (coil_value == KomoraOdbiorczaZamek.ODBLOKOWANY.value) if coil_value is not None else False
        except Exception:
            coil_unlocked = False
        chamber_open = bool(self.__di_sensors.get("chamber_open", False))
        return bool(coil_unlocked or chamber_open)

    def get_gate_closed(self) -> bool:
        # Brama fizycznie zamknięta wg. czujnika krańcowego od strony klienta
        try:
            return not bool(self.__di_sensors["chamber_open"])  # zamknięta => True
        except Exception:
            return False

    def _instant_execute_event(self, event: Event) -> Event:
        match event.event_type:
            case "chamber_is_product_present":
                event.data["signal_value"] = self.__is_product_present()
            case "chamber_is_chamber_open":
                event.data["signal_value"] = self.__is_chamber_open(**self.methods["chamber_open"])
            case "chamber_is_sauce_present":
                event.data["signal_value"] = self.__is_sauce_present()
            case _:
                event.data["signal_value"] = -1
        return event

    def get_current_state(self):
        return self._state

    def check_if_ethercat_work(self):
        if not self.__block_for_client_check(**self.methods["block_for_client_check"]):
            error(f"{self.device_name} - WTF !!!! FIXME !!!!! Ethercat is not working. Modbus state is not working [ER-C01]", message_logger=self._message_logger)

    def tick(self):
        # debug(f"Komora, aktualny FSM: {self.__fsm.value}", message_logger=self._message_logger)
        # if self._processing_events.get("chamber_initialize") and self.fsm == KomoraOdbiorczaState.UNKNOWN:
        if self.fsm == KomoraOdbiorczaState.UNKNOWN:  # FIXME: PRZENIEŚĆ DO INSTANT EXECUTE EVENT
            self.fsm = KomoraOdbiorczaState.CHAMBER_INITIALIZING

        if self._processing_events.get("chamber_maintenance_enable"):  # jezli jest event wlaczajacy tryb serwisowy odpowiedz o sukcesie
            self.fsm = KomoraOdbiorczaState.ENABLING_MAINTENANCE

        debug(f"{self.device_name} - Komora, aktualny FSM: {self.fsm.name}", message_logger=self._message_logger)

        match self.fsm:
            case KomoraOdbiorczaState.CHAMBER_INITIALIZING:
                if self._state == VirtualDeviceState.UNINITIALIZED:
                    self.set_state(VirtualDeviceState.INITIALIZING)

                if not self.__is_chamber_open(**self.methods["chamber_open"]):  # gdy komora od strony klienta jest zamknieta
                    debug("Initialising Chamber", message_logger=self._message_logger)
                    self.__block_for_client(value=KomoraOdbiorczaZamek.ZABLOKOWANY.value, **self.methods["block_for_client"])  # zablokowanie komory klienta
                    # Timeout: brama powinna zostać zablokowana (potwierdzenie krańcówką i/lub sygnałem blokady)
                    self.add_sensor_timeout(
                        condition=lambda: self.get_gate_locked(),
                        timeout_s=self.__timeouts["gate_locked_confirmed"],
                        description="Komora odbiorcza nie została zablokowana",
                        metadata={"device": self.device_name},
                    )
                else:
                    error(f"{self.device_name} - brama zewnetrzna jest otwarta", message_logger=self._message_logger)
                    warning(f"{self.device_name} - Komora odbiorcza nie moze byc zainicjalizowana. Wylaczenie komory z Munchies Algo!", message_logger=self._message_logger)
                    self.fsm = KomoraOdbiorczaState.CHAMBER_INIT_ERROR
                    return

                if not self.__is_partition_up(**self.methods["partition_up"]):  # gdy przegroda wewnetrzna nie jest otwarta, otworz ja
                    self.__move_partition(speed=-3000, **self.methods["move_partition"])  # otwarcie przegrody wewnetrznej
                    # Timeout: przegroda powinna osiągnąć pozycję GÓRA
                    self.add_sensor_timeout(
                        condition=lambda: self.get_partition_opened(),
                        timeout_s=self.__timeouts["partition_open_reached"],
                        description="Przegroda wewnętrzna nie otworzyła się",
                        metadata={"device": self.device_name},
                    )

                self.fsm = KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_OPENING

            case KomoraOdbiorczaState.RELEASED_FOR_CLIENT_GATE_OPENED:
                # self.check_if_ethercat_work()
                if not self.__is_chamber_open(**self.methods["chamber_open"]):  # gdy komora od strony klienta jest zamknieta
                    self.fsm = KomoraOdbiorczaState.RELEASED_FOR_CLIENT_GATE_CLOSED
                    debug("Chamber is closed by client", message_logger=self._message_logger)

            case KomoraOdbiorczaState.RELEASED_FOR_CLIENT_GATE_CLOSED:
                # self.check_if_ethercat_work()
                warunek = self.__is_chamber_open(**self.methods["chamber_open"])
                debug(f"{self.device_name} - [KomoraOdbiorcza] self.__is_chamber_open(**self.methods['chamber_open']):{warunek}", message_logger=self._message_logger)

                if self.__is_chamber_open(**self.methods["chamber_open"]):  # gdy komora od strony klienta jest zamknieta #tutaj się zatrzymał
                    debug(f"{self.device_name} - Chamber is opened by client", message_logger=self._message_logger)
                    self.fsm = KomoraOdbiorczaState.RELEASED_FOR_CLIENT_GATE_OPENED
                    # Timeout: czujnik powinien potwierdzić zamknięcie bramy
                    self.add_sensor_timeout(
                        condition=lambda: self.get_gate_closed(),
                        timeout_s=self.__timeouts["gate_closed_confirmed"],
                        description="Komora odbiorcza nie została zamknięta",
                        on_timeout=lambda: warning(
                            f"{self.device_name} - Komora odbiorcza nie została zamknięta w wyznaczonym czasie.",
                            message_logger=self._message_logger,
                        ),
                        metadata={"device": self.device_name},
                    )
                    # self._block_for_client_check_time = time.time()
                else:
                    if self._processing_events.get("chamber_block_for_client"):  # sprawdzenie czy jest event blokujacy komore klienta #tutaj zwraca NONE !!! #FIXME
                        self.__block_for_client(value=KomoraOdbiorczaZamek.ZABLOKOWANY.value, **self.methods["block_for_client"])  # blokujemy komore klienta
                        # Timeout: brama powinna zostać zablokowana
                        self.add_sensor_timeout(
                            condition=lambda: self.get_gate_locked(),
                            timeout_s=self.__timeouts["gate_locked_confirmed"],
                            description="Komora odbiorcza nie została zablokowana",
                            metadata={"device": self.device_name},
                        )
                        debug(f"{self.device_name} - Start blocking chamber for client", message_logger=self._message_logger)
                        self.fsm = KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_CLOSED
                        self._move_event_to_finished(event_type="chamber_block_for_client", result="success")

            case KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_OPENED:
                if self._state == VirtualDeviceState.INITIALIZING:
                    self.set_state(VirtualDeviceState.WORKING)
                try:
                    self.__check_chamber_open()  # sprawdzenie krancowki odbiorczej klienta
                except Exception as e:
                    error(f"{self.device_name} - {e}", message_logger=self._message_logger)
                if self._processing_events.get("chamber_initialize"):
                    self._move_event_to_finished(event_type="chamber_initialize", result="success")
                if self._processing_events.get("chamber_block_chamber"):  # sprawdzenie czy jest event blokujacy komora klienta oraz przegrode wewnetrzna
                    debug(f"{self.device_name} - Blocking chamber. Conveyor is moving.", message_logger=self._message_logger)
                    self.fsm = KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_OPEN_CONVEYOR_MOVING
                    self._move_event_to_finished(event_type="chamber_block_chamber", result="success")
                elif self._processing_events.get("chamber_partition_down"):  # sprawdzenie czy jest event odblokowujacy przegrode dal klienta
                    debug(f"{self.device_name} - Closing partition", message_logger=self._message_logger)
                    self.__move_partition(speed=3000, **self.methods["move_partition"])
                    # Timeout: przegroda powinna osiągnąć pozycję DÓŁ
                    self.add_sensor_timeout(
                        condition=lambda: self.get_partition_closed(),
                        timeout_s=self.__timeouts["partition_close_reached"],
                        description="Przegroda wewnętrzna nie zamknęła się",
                        metadata={"device": self.device_name},
                    )
                    self.fsm = KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_CLOSING

            case KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_CLOSED:  # klient zablokowany, komora zamknieta
                try:
                    self.__check_chamber_open()  # sprawdzenie krancowki odbiorczej klienta
                except Exception as e:
                    error(f"{self.device_name} - {e}", message_logger=self._message_logger)
                if self._processing_events.get("chamber_partition_up"):  # sprawdzenie czy jest event otwierajacym przegrode wewnetrzna
                    debug(f"{self.device_name} - Starting open partition", message_logger=self._message_logger)
                    self.__move_partition(speed=-3000, **self.methods["move_partition"])
                    # Timeout: przegroda powinna osiągnąć pozycję GÓRA
                    self.add_sensor_timeout(
                        condition=lambda: self.get_partition_opened(),
                        timeout_s=self.__timeouts["partition_open_reached"],
                        description="Przegroda wewnętrzna nie otworzyła się",
                        metadata={"device": self.device_name},
                    )
                    self.fsm = KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_OPENING
                elif self._processing_events.get("chamber_unblock_for_client"):  # sprawdzenie czy jest event odblokowujacy przegrode dal klienta
                    debug(f"{self.device_name} - Unblocking for client", message_logger=self._message_logger)
                    self.__block_for_client(value=KomoraOdbiorczaZamek.ODBLOKOWANY.value, **self.methods["block_for_client"])
                    # Timeout: brama powinna zostać odblokowana
                    self.add_sensor_timeout(
                        condition=lambda: self.get_gate_unlocked(),
                        timeout_s=self.__timeouts["gate_unlocked_confirmed"],
                        description="Komora odbiorcza nie została odblokowana",
                        metadata={"device": self.device_name},
                    )
                    self.fsm = KomoraOdbiorczaState.RELEASED_FOR_CLIENT_GATE_CLOSED
                    self._move_event_to_finished(event_type="chamber_unblock_for_client", result="success")
                elif self.__is_failure(**self.methods["is_failure"]):  # sprawdzenie czy wystąpił błąd w silniku przegrody
                    error(f"{self.device_name} - Error detected patrition closed. Resetting error", message_logger=self._message_logger)
                    self.__reset_error(**self.methods["reset_error"])

            case KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_OPENING:
                # event enable_maintenance
                try:
                    self.__check_chamber_open()  # sprawdzenie krancowki odbiorczej klienta
                except Exception as e:
                    error(f"{self.device_name} - {e}", message_logger=self._message_logger)
                if self.__is_partition_up(**self.methods["partition_up"]):  # sprawdzenie czy przegroda wewnetrzna jest podniesiona
                    self.fsm = KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_OPENED
                    if self._processing_events.get("chamber_partition_up"):
                        self._move_event_to_finished(event_type="chamber_partition_up", result="success")

            case KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_CLOSING:
                try:
                    self.__check_chamber_open()  # sprawdzenie krancowki odbiorczej klienta
                except Exception as e:
                    error(f"{self.device_name} - {e}", message_logger=self._message_logger)
                if self.__is_failure(**self.methods["is_failure"]):  # sprawdzenie czy wystąpił błąd w silniku przegrody
                    self.fsm = KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_CLOSED
                    self._move_event_to_finished(event_type="chamber_partition_down", result="success")
                    error(f"{self.device_name} - Error detected during partition closing. Resetting error", message_logger=self._message_logger)
                    self.__reset_error(**self.methods["reset_error"])
                if self.__is_partition_down(**self.methods["partition_down"]):  # sprawdzenie czy przegroda wewnetrzna jest opuszczona
                    self.fsm = KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_CLOSED
                    self._move_event_to_finished(event_type="chamber_partition_down", result="success")

            case KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_OPEN_CONVEYOR_MOVING:
                try:
                    self.__check_chamber_open()  # sprawdzenie krancowki odbiorczej klienta
                except Exception as e:
                    error(f"{self.device_name} - {e}", message_logger=self._message_logger)
                if self._processing_events.get("chamber_unblock_chamber"):  # sprawdzenie czy jest event odblokujacy komora klienta oraz przegrode wewnetrzna
                    debug(f"{self.device_name} - Unblocking chamber. Conveyor stopped.", message_logger=self._message_logger)
                    self.fsm = KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_OPENED
                    self._move_event_to_finished(event_type="chamber_unblock_chamber", result="success")  # odblokowanie komory
                self.__check_chamber_open()  # sprawdzenie krancowki odbiorczej klienta

            case KomoraOdbiorczaState.CHAMBER_INIT_ERROR:
                if self._state == VirtualDeviceState.INITIALIZING:
                    self.set_state(VirtualDeviceState.ERROR)
                error(f"{self.device_name} - Chamber initialization error. Cannot proceed.", message_logger=self._message_logger)
                self._move_event_to_finished(event_type="chamber_initialize", result="error")

            case KomoraOdbiorczaState.ENABLING_MAINTENANCE:
                if self._processing_events.get("chamber_maintenance_enable"):  # jezli jest event wlaczajacy tryb serwisowy odpowiedz o sukcesie
                    info(
                        f"{self.device_name} - Komora w trybie serwisowym - opuszczenie rolety wewnętrznej i odblokowanie rolety zewnętrznej",
                        message_logger=self._message_logger,
                    )
                    self._move_event_to_finished(event_type="chamber_maintenance_enable", result="success")
                    self.__move_partition(speed=3000, **self.methods["move_partition"])  # opuszczenie przegrody
                    self.__block_for_client(value=KomoraOdbiorczaZamek.ODBLOKOWANY.value, **self.methods["block_for_client"])  # odblokowanie komory
                    self.fsm = KomoraOdbiorczaState.MAINTENANCE

            case KomoraOdbiorczaState.MAINTENANCE:
                # tryb serwisowy, czekanie na wyjscie z trybu serwisowego przez event
                if self._processing_events.get("chamber_maintenance_disable"):
                    info(
                        f"{self.device_name} - Komora w trybie serwisowym - podnoszenie rolety wewnętrznej i zablokowanie rolety zewnętrznej",
                        message_logger=self._message_logger,
                    )
                    self.__move_partition(speed=-3000, **self.methods["move_partition"])  # podniesienie przegrody - do trybu domyślnego
                    self.__block_for_client(value=KomoraOdbiorczaZamek.ZABLOKOWANY.value, **self.methods["block_for_client"])  # zablokowanie komory
                    self.fsm = KomoraOdbiorczaState.DISABLING_MAINTENANCE

            case KomoraOdbiorczaState.DISABLING_MAINTENANCE:
                if (
                    self.__is_partition_up(**self.methods["partition_up"]) and self.get_gate_locked()
                ):  # sprawdzenie czy przegroda wewnetrzna jest podniesiona i roleta zewnętrza zablokowana
                    if self._processing_events.get("chamber_maintenance_disable"):
                        info(
                            f"{self.device_name} - Komora wyszła z trybu serwisowegoa",
                            message_logger=self._message_logger,
                        )

                        self._move_event_to_finished(event_type="chamber_maintenance_disable", result="success")
                        self.fsm = KomoraOdbiorczaState.BLOCKED_FOR_CLIENT_PARTITION_OPENED  # na koniec przejsc do normalnej pracy

        # Odświeżenie cache czujników na końcu cyklu (jak w oven.py)

        if "chamber_open" in self.methods:
            self.__is_chamber_open(**self.methods["chamber_open"])  # aktualizuje __di_sensors["chamber_open"]
        if "partition_up" in self.methods:
            self.__is_partition_up(**self.methods["partition_up"])  # aktualizuje __di_sensors["partition"]["up"]
        if "partition_down" in self.methods:
            self.__is_partition_down(**self.methods["partition_down"])  # aktualizuje __di_sensors["partition"]["down"]
        if "product_sensor_1" in self.methods:
            self.__is_product_sensor_1(**self.methods["product_sensor_1"])  # aktualizuje __di_sensors["product"][0]
        if "product_sensor_2" in self.methods:
            self.__is_product_sensor_2(**self.methods["product_sensor_2"])  # aktualizuje __di_sensors["product"][1]
        if "sauce_1_sensor" in self.methods:
            self.__is_sauce_1_sensor(**self.methods["sauce_1_sensor"])  # aktualizuje __di_sensors["sauce"][0]
        if "sauce_2_sensor" in self.methods:
            self.__is_sauce_2_sensor(**self.methods["sauce_2_sensor"])  # aktualizuje __di_sensors["sauce"][1]
        if "sauce_3_sensor" in self.methods:
            self.__is_sauce_3_sensor(**self.methods["sauce_3_sensor"])  # aktualizuje __di_sensors["sauce"][2]
        if "block_for_client_check" in self.methods:
            self.__block_for_client_check(**self.methods["block_for_client_check"])  # aktualizuje __di_sensors["block_state"]
        if "is_failure" in self.methods:
            self.__is_failure(**self.methods["is_failure"])  # aktualizuje __di_sensors["failure"]
