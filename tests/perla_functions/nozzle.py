from dotenv import load_dotenv

from avena_commons.event_listener import Event, EventListener
from avena_commons.util.logger import MessageLogger

load_dotenv(override=True)


class Nozzle(EventListener):
    """
    Main logic class for handling events and managing the state of the Nozzle system.
    """

    def __init__(
        self,
        name: str,
        address: str,
        port: str,
        message_logger: MessageLogger | None = None,
        do_not_load_state: bool = False,
    ):
        """
        Initializes the Nozzle with necessary configurations and state.

        Args:
            message_logger (Optional[MessageLogger]): Logger for logging messages.
            do_not_load_state (bool): Flag to skip loading state.

        Raises:
            ValueError: If required environment variables are missing.
        """

        if not port:
            raise ValueError(
                "Brak wymaganej zmiennej środowiskowej NOZZLE_LISTENER_PORT"
            )

        super().__init__(
            name=name,
            address=address,
            port=port,
            message_logger=message_logger,
            do_not_load_state=do_not_load_state,
        )

    # MARK: ANALYZE EVENT
    async def _analyze_event(self, event: Event) -> bool:
        """
        Analyzes and routes events to the appropriate handler based on their source.

        Args:
            event (Event): The event to analyze.

        Returns:
            bool: True if the event was handled successfully, False otherwise.
        """
        pass

        return True

    # MARK: CHECK LOCAL DATA
    async def _check_local_data(self):
        """
        Periodically checks and processes local data, including orders, products, and system states.

        Raises:
            Exception: If an error occurs during data processing.
        """
        pass
