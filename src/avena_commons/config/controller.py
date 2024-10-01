from configparser import ConfigParser
from .common import Config
import os


class ControllerConfig(Config):
    def __init__(self, config_file, read_only=True):
        super().__init__(config_file, read_only)
        self.__section = "CONTROLLER"
        self.config = ConfigParser(
            defaults={
                "CONTROLLER_PATH": os.path.expanduser("~") + "/controller",
                "RESOURCES_PATH": "%(CONTROLLER_PATH)s/resources",
                "URDF_PATH": "%(CONTROLLER_PATH)s/URDFS/urdf_janusz/robot.urdf",
                "LOG_LEVEL": "INFO",
                "APS": "APS00",
            }
        )
        super().read_from_file()
        # print(self)

    def get(self, key):
        element = self.config.get(self.__section, key)
        # print(f"CONFIG:{type(self).__name__}.{key.lower()} = {element}")
        try:
            value = float(element)
            # print(f"{element} is float")
            return value
        except ValueError:
            pass
            # print("Not a float")

        try:
            value = int(element)
            # print(f"{element} is int")
            return value
        except ValueError:
            pass
            # print("Not a int")

        # try:
        #     value = bool(element)
        #     print(f"{element} is bool (value: {value})")
        #     return value
        # except ValueError:
        #     print("Not a bool")

        # print(f"{element} is string")
        return element

    def get_controller_configuration(self):
        params = dict(self.config[self.__section])
        return params

    def __str__(self) -> str:
        return super().__str__()

    def __del__(self):
        pass
