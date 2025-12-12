from enum import Enum

from avena_commons.event_listener import Event
from avena_commons.io import VirtualDevice, VirtualDeviceState
from avena_commons.io.virtual_device.sensor_watchdog import SensorTimerTask
from avena_commons.util.logger import debug, error, warning

class TestDevice(VirtualDevice):
    def __init__(self, timeouts: dict | None = None, **kwargs):
        super().__init__(**kwargs)
        self.in_run = False
    
    def __run_jog_1(self, speed: int, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])(speed=speed)
    
    def __is_motor_running_1(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __stop_1(self, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])()
    
    def __run_jog_2(self, speed: int, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])(speed=speed)
    
    def __is_motor_running_2(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __stop_2(self, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])()
    
    def __run_jog_3(self, speed: int, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])(speed=speed)
    
    def __is_motor_running_3(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __stop_3(self, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])()
    
    def _instant_execute_event(self, event: Event) -> Event:  # FIXME tylko zwracamy?
        return event

    def get_current_state(self):
        return self._state

    def __read_counter_1(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_counter_2(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_counter_3(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value


    def tick(self):
        # print(self._processing_events, )
        if self._processing_events.get("testdevice_run_jog"):
            print("start")
            self.__run_jog_1(speed=-2000000, **self.methods["run_jog_1"])  # start 1 ruchu
            self.__run_jog_2(speed=-2000000, **self.methods["run_jog_2"])  # start 1 ruchu
            self.__run_jog_3(speed=-2000000, **self.methods["run_jog_3"])  # start 1 ruchu
            self._move_event_to_finished(event_type="testdevice_run_jog", result="success")
            self.in_run = True

            
        if self._processing_events.get("testdevice_stop"):
            self.__stop_1(**self.methods["stop_1"])
            self.__stop_2(**self.methods["stop_2"])
            self.__stop_3(**self.methods["stop_3"])
            self._move_event_to_finished(event_type="testdevice_stop", result="success")
            self.in_run = False

        if self.in_run:
            print(f"Counters: {self.__read_counter_1(**self.methods['read_counter_1'])}, {self.__read_counter_2(**self.methods['read_counter_2'])}, {self.__read_counter_3(**self.methods['read_counter_3'])}")
