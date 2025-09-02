"""Moduł urządzeń IO: funkcje pomocnicze i podmoduły `io`, `motor_driver`, `sensor`.

Zawiera narzędzia do sprawdzania połączenia urządzeń Modbus oraz eksportuje
pakiety z definicjami urządzeń fizycznych.
"""

from avena_commons.util.logger import debug, error, info


def modbus_check_device_connection(
    device_name: str, bus, address: int, register: int, message_logger
):
    """Sprawdza połączenie urządzenia poprzez odczyt rejestru Holding.

    Args:
        device_name (str): Nazwa urządzenia do logowania.
        bus: Obiekt magistrali Modbus z metodą `read_holding_register`.
        address (int): Adres slave.
        register (int): Adres rejestru do odczytu.
        message_logger: Logger do zapisu komunikatów.

    Returns:
        bool: True jeśli odczyt zwrócił liczbę całkowitą; w przeciwnym razie False.
    """
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
