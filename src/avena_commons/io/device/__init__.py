from avena_commons.util.logger import debug, error, info


def modbus_check_device_connection(
    device_name: str, bus, address: int, register: int, message_logger
):
    try:
        debug(
            f"{device_name} Checking device connection", message_logger=message_logger
        )
        response = bus.read_holding_register(address=address, register=register)
        if type(response) == int:
            info(f"{device_name} Device connected", message_logger=message_logger)
            return True
        else:
            error(f"{device_name} Device not connected", message_logger=message_logger)
            return False
    except Exception as e:
        error(
            f"{device_name} Exception:Error reading status: {e}",
            message_logger=message_logger,
        )


from . import io, motor_driver, sensor

__all__ = [
    "io",
    "motor_driver",
    "sensor",
]
