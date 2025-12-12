from enum import Enum

from avena_commons.event_listener import Event
from avena_commons.io import VirtualDevice, VirtualDeviceState
from avena_commons.io.virtual_device.sensor_watchdog import SensorTimerTask
from avena_commons.util.logger import debug, error, warning

class TestDevice3(VirtualDevice):
    def __init__(self, timeouts: dict | None = None, **kwargs):
        super().__init__(**kwargs)
    
    def __run_jog(self, speed: int, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])(speed=speed)
    
    def __is_motor_running(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __stop(self, **kwargs):
        return getattr(self.devices[kwargs["device"]], kwargs["method"])()
    
    def __read_input_11(self, **kwargs):
        print(kwargs["device"], kwargs["method"])
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_12(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_13(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_14(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_15(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_16(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_21(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_22(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_23(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_24(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_25(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_26(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_31(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_32(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_33(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_34(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_35(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def __read_input_36(self, **kwargs):
        value = getattr(self.devices[kwargs["device"]], kwargs["method"])
        return value
    
    def write_output_11(self, value, **kwargs):
        setattr(self.devices[kwargs["device"]], kwargs["method"], value)

    def write_output_21(self, value, **kwargs):
        setattr(self.devices[kwargs["device"]], kwargs["method"], value)
    
    def write_output_31(self, value, **kwargs):
        setattr(self.devices[kwargs["device"]], kwargs["method"], value)

    def write_output_12(self, value, **kwargs):
        setattr(self.devices[kwargs["device"]], kwargs["method"], value)

    def write_output_22(self, value, **kwargs):
        setattr(self.devices[kwargs["device"]], kwargs["method"], value)
    
    def write_output_32(self, value, **kwargs):
        setattr(self.devices[kwargs["device"]], kwargs["method"], value)

    def write_output_13(self, value, **kwargs):
        setattr(self.devices[kwargs["device"]], kwargs["method"], value)

    def write_output_23(self, value, **kwargs):
        setattr(self.devices[kwargs["device"]], kwargs["method"], value)
    
    def write_output_33(self, value, **kwargs):
        setattr(self.devices[kwargs["device"]], kwargs["method"], value)

    
    def _instant_execute_event(self, event: Event) -> Event:  # FIXME tylko zwracamy?
        return event

    def get_current_state(self):
        return self._state

    def tick(self):

        if self._processing_events.get("testdevice_read_inputs"):
            print("")
            print("--------------------------------------------")
            print(f" Device 1")
            print(f"Inputs: ")
            print(f"1. {self.__read_input_11(**self.methods['read_input_11'])}")
            print(f"2. {self.__read_input_12(**self.methods['read_input_12'])}")
            print(f"3. {self.__read_input_13(**self.methods['read_input_13'])}")
            print(f"4. {self.__read_input_14(**self.methods['read_input_14'])}")
            print(f"5. {self.__read_input_15(**self.methods['read_input_15'])}")
            print(f"6. {self.__read_input_16(**self.methods['read_input_16'])}")
            print("")
            print(f" Device 2")
            print(f"Inputs: ")
            print(f"1. {self.__read_input_21(**self.methods['read_input_21'])}")
            print(f"2. {self.__read_input_22(**self.methods['read_input_22'])}")
            print(f"3. {self.__read_input_23(**self.methods['read_input_23'])}")
            print(f"4. {self.__read_input_24(**self.methods['read_input_24'])}")
            print(f"5. {self.__read_input_25(**self.methods['read_input_25'])}")
            print(f"6. {self.__read_input_26(**self.methods['read_input_26'])}")
            print("")
            print(f" Device 3")
            print(f"Inputs: ")
            print(f"1. {self.__read_input_31(**self.methods['read_input_31'])}")
            print(f"2. {self.__read_input_32(**self.methods['read_input_32'])}")
            print(f"3. {self.__read_input_33(**self.methods['read_input_33'])}")
            print(f"4. {self.__read_input_34(**self.methods['read_input_34'])}")
            print(f"5. {self.__read_input_35(**self.methods['read_input_35'])}")
            print(f"6. {self.__read_input_36(**self.methods['read_input_36'])}")
            print("")

            self._move_event_to_finished(event_type="testdevice_read_inputs", result="success")
        
        if self._processing_events.get("testdevice_write_outputs_1"):
            self.write_output_11(True, **self.methods['write_output_11'])
            self.write_output_21(True, **self.methods['write_output_21'])
            self.write_output_31(True, **self.methods['write_output_31'])

            self._move_event_to_finished(event_type="testdevice_write_outputs_1", result="success")
        
        if self._processing_events.get("testdevice_write_outputs_2"):
            self.write_output_12(True, **self.methods['write_output_12'])
            self.write_output_22(True, **self.methods['write_output_22'])
            self.write_output_32(True, **self.methods['write_output_32'])

            self._move_event_to_finished(event_type="testdevice_write_outputs_2", result="success")

        if self._processing_events.get("testdevice_write_outputs_3"):
            self.write_output_13(True, **self.methods['write_output_13'])
            self.write_output_23(True, **self.methods['write_output_23'])
            self.write_output_33(True, **self.methods['write_output_33'])

            self._move_event_to_finished(event_type="testdevice_write_outputs_3", result="success")

        if self._processing_events.get("testdevice_write_outputs_stop"):
            self.write_output_11(False, **self.methods['write_output_11'])
            self.write_output_21(False, **self.methods['write_output_21'])
            self.write_output_31(False, **self.methods['write_output_31'])

            self.write_output_12(False, **self.methods['write_output_12'])
            self.write_output_22(False, **self.methods['write_output_22'])
            self.write_output_32(False, **self.methods['write_output_32'])

            self.write_output_13(False, **self.methods['write_output_13'])
            self.write_output_23(False, **self.methods['write_output_23'])
            self.write_output_33(False, **self.methods['write_output_33'])

            self._move_event_to_finished(event_type="testdevice_write_outputs_stop", result="success")

        if self._processing_events.get("testdevice_run_jog"):
            print("start")
            self.__run_jog(speed=-20000, **self.methods["run_jog"])  # start 1 ruchu=
            self._move_event_to_finished(event_type="testdevice_run_jog", result="success")
            self.in_run = True

            
        if self._processing_events.get("testdevice_stop"):
            self.__stop(**self.methods["stop"])
            self._move_event_to_finished(event_type="testdevice_stop", result="success")
            self.in_run = False