from enum import Enum

from avena_commons.event_listener import Event
from avena_commons.io import VirtualDevice, VirtualDeviceState
from avena_commons.io.virtual_device.sensor_watchdog import SensorTimerTask
from avena_commons.util.logger import debug, error, warning


class Buttons(VirtualDevice):
    def __init__(self, 
                 timeouts: dict | None = None, **kwargs):
        super().__init__(**kwargs)
        self.set_state(VirtualDeviceState.INITIALIZING)
        # Track DI inputs similar to Oven: store latest states of sensors

    def __read_button_1(self, **kwargs):
        # debug(f"READ SENSOR 1 {self.device_name} - {self.devices[kwargs['device']]} - reading sensor 1", message_logger=self._message_logger)
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value

    def __read_button_2(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value

    def __read_button_3(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value

    def __read_button_4(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value

    def _instant_execute_event(self, event: Event) -> Event:
        match event.event_type:
            case "buttons_read_button_1":
                event.data["button_state"] = self.__read_button_1(**self.methods["read_button_1"])
            case "buttons_read_button_2":
                event.data["button_state"] = self.__read_button_2(**self.methods["read_button_2"])
            case "buttons_read_button_3":
                event.data["button_state"] = self.__read_button_3(**self.methods["read_button_3"])
            case "buttons_read_button_4":
                event.data["button_state"] = self.__read_button_4(**self.methods["read_button_4"])
            case _:
                warning(f"{self.device_name} - Nieznane zdarzenie: {event.event_type}", message_logger=self._message_logger)
        
        return event

    def get_current_state(self):
        return self._state

    def tick(self):
        pass
        