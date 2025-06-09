import os
import sys
import threading
import time

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)

from avena_commons.event_listener.event import Event
from avena_commons.event_listener.event_listener import EventListener
from avena_commons.util.logger import MessageLogger


class EventListenerServer(EventListener):
    def __init__(
        self,
        name: str,
        address: str = "127.0.0.1",
        port: int = 8000,
        message_logger: MessageLogger | None = None,
        do_not_load_state: bool = False,
        raport_overtime: bool = True,
    ):
        super().__init__(
            name, address, port, message_logger, do_not_load_state, raport_overtime
        )


class EventListenerClient(EventListener):
    def __init__(
        self,
        name: str,
        address: str = "127.0.0.1",
        port: int = 8000,
        message_logger: MessageLogger | None = None,
        do_not_load_state: bool = False,
        raport_overtime: bool = True,
    ):
        super().__init__(
            name, address, port, message_logger, do_not_load_state, raport_overtime
        )

    def _analyze_event(self, event: Event):
        self._reply(event)


if __name__ == "__main__":
    server = EventListenerServer("server", port=8000)
    # client = EventListenerClient("client", port=9000)

    # Uruchomienie serwerów w osobnych wątkach, aby nie blokowały się wzajemnie
    server_thread = threading.Thread(target=server.start)
    # client_thread = threading.Thread(target=client.start)

    server_thread.start()
    # client_thread.start()

    time.sleep(5)

    server.shutdown()
    # client.shutdown()

    time.sleep(5)
    # try:
    #     # Ta pętla utrzymuje główny wątek przy życiu i pozwala na przechwycenie Ctrl+C
    #     while server_thread.is_alive() and client_thread.is_alive():
    #         threading.Event().wait(0.5)
    # except KeyboardInterrupt:
    #     print("\nOtrzymano Ctrl+C, zamykanie serwerów...")
    #     # To jest obejście problemu w EventListener - wywołujemy jego prywatną metodę shutdown.
    #     # Nie jest to idealne rozwiązanie, ale pozwoli rozwiązać problem bez modyfikacji biblioteki.
    #     server._EventListener__shutdown()
    #     client._EventListener__shutdown()

    # Czekamy na faktyczne zakończenie wątków
    server_thread.join()
    # client_thread.join()

    print("Serwery zamknięte.")
