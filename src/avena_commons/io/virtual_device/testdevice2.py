from enum import Enum

from avena_commons.event_listener import Event
from avena_commons.io import VirtualDevice, VirtualDeviceState
from avena_commons.io.virtual_device.sensor_watchdog import SensorTimerTask
from avena_commons.util.logger import debug, error, warning

class TestDevice2(VirtualDevice):
    def __init__(self, timeouts: dict | None = None, **kwargs):
        super().__init__(**kwargs)
    
    def __run_jog(self, speed: int, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])(speed=speed)
    
    def __is_motor_running(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __stop(self, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])()
    
    def __read_counter_1(self, **kwargs):
        print("read_cnt in virtual_device")
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    
    def __read_counter_2(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_counter_3(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def _instant_execute_event(self, event: Event) -> Event:  # FIXME tylko zwracamy?
        return event

    def get_current_state(self):
        return self._state

    
    def tick(self):
        print(f"Counters: {self.__read_counter_1(**self.methods['read_counter_1'])}, {self.__read_counter_2(**self.methods['read_counter_2'])}, {self.__read_counter_3(**self.methods['read_counter_3'])}")
    
        