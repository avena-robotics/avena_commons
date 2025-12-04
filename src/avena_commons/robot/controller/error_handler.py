from typing import Callable

from .enum import RobotControllerState


def handle_errors(
    default_state: RobotControllerState = RobotControllerState.ERROR,
    default_msg: str | None = None,
):
    """
    Dekorator, który obsługuje wyjątki, zapisuje wiadomość i ustawia stan Error.

    Args:
        default_state (RobotControllerState.Error): Domyślny kod błędu używany przy wystąpieniu wyjątku.
        default_msg (str | None): Domyślny prefiks wiadomości błędu.
            Jeśli None, używa "Operacja nie powiodła się w {function_name}".
            Domyślnie None.

    Returns:
        Callable: Dekorowana funkcja, która obsługuje błędy.

    Example:
        @handle_errors()
        def process_data(self, data):
            return
    """

    def decorator(func: Callable):
        # @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                self._state = default_state
                self._error_message = (
                    default_msg
                    if default_msg is not None
                    else f"Operacja nie powiodła się w {func.__name__}"
                )
                if self._message_logger:
                    self._message_logger.error(
                        f"{self._error_message}: {str(e)}"
                    )
                return None

        return wrapper

    return decorator