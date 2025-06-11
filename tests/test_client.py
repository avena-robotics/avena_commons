import argparse
import asyncio
import logging
import os
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

# Konfiguracja logowania
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
# logger = logging.getLogger(__name__)

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from avena_commons.event_listener import (
    Event,
    EventListener,
    EventListenerState,
    Result,
)
from avena_commons.util.logger import (
    LoggerPolicyPeriod,
    MessageLogger,
    debug,
    error,
    info,
    warning,
)

# Dodanie pomocniczej funkcji do bezpiecznego logowania
# def safe_log(log_func, message, message_logger=None):
#     """Bezpieczna funkcja logująca, obsługująca BrokenPipeError."""
#     try:
#         log_func(message, message_logger=message_logger)
#     except BrokenPipeError:
#         print(f"{message} (pipe zamknięty)")
#     except Exception as e:
#         print(f"Błąd podczas logowania '{message}': {e}")


class TestClient(EventListener):
    def __init__(
        self,
        name: str,
        port: int,
        address: str,
        message_logger=None,
        debug=False,
    ):
        super().__init__(
            name=name,
            address=address,
            port=port,
            do_not_load_state=True,
            message_logger=message_logger,
        )
        # self.logger = logging.getLogger(f"TestClient_{port}")
        # self.logger.info(f"Klient utworzony na porcie {port}")
        self._is_running = False
        self._server_thread = None
        self.message_logger = message_logger
        self._loop = None

    async def _analyze_event(self, event: Event) -> bool:
        event.result = Result(result="success")
        await self._reply(event)
        return True

    async def _check_local_data(self):
        pass

    def _run_server(self):
        """Uruchamia serwer uvicorn w tym wątku."""
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            super().start()
        except asyncio.exceptions.CancelledError:
            info(
                f"Serwer na porcie {self._EventListener__port} zatrzymany.",
                message_logger=self.message_logger,
            )
        except Exception as e:
            error(
                f"Błąd serwera na porcie {self._EventListener__port}: {e}",
                message_logger=self.message_logger,
            )
        finally:
            self._is_running = False
            if self._loop:
                self._loop.close()

    def start(self):
        """Uruchamia klienta i jego serwer w osobnym wątku."""
        if self._is_running:
            warning(
                f"Klient na porcie {self._EventListener__port} już działa.",
                message_logger=self.message_logger,
            )
            return

        self._is_running = True
        self._server_thread = threading.Thread(
            target=self._run_server,
            daemon=True,
            name=f"ServerThread-{self._EventListener__port}",
        )
        self._server_thread.start()
        info(
            f"Wątek serwera dla portu {self._EventListener__port} uruchomiony.",
            message_logger=self.message_logger,
        )

    def shutdown(self):
        """Zamyka klienta i jego serwer."""
        if not self._is_running:
            return

        info(
            f"Zamykanie klienta na porcie {self._EventListener__port}",
            message_logger=self.message_logger,
        )

        # Zatrzymaj serwer
        if hasattr(self, "server") and self.server:
            if self._loop and self._loop.is_running():
                try:
                    # Ustaw krótszy timeout dla shutdown
                    future = asyncio.run_coroutine_threadsafe(
                        self.server.shutdown(), self._loop
                    )
                    future.result(timeout=1.0)  # Zmniejszony timeout do 1 sekundy
                except Exception as e:
                    error(
                        f"Błąd podczas zamykania serwera na porcie {self._EventListener__port}: {e}"
                    )

        # Poczekaj na zakończenie wątku serwera
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=1.0)  # Zmniejszony timeout do 1 sekundy

        self._is_running = False
        self.message_logger = None


def create_clients(
    number_of_clients: int,
    base_port: int = 9000,
    message_logger=None,
):
    """Tworzy określoną liczbę klientów.

    Args:
        number_of_clients (int): Liczba klientów do utworzenia
        base_port (int): Port bazowy, od którego będą numerowane porty klientów
        message_logger: Logger wiadomości (opcjonalny)
    """
    info(
        f"Tworzenie {number_of_clients} klientów, port bazowy: {base_port}",
        message_logger=message_logger,
    )
    clients = []
    for i in range(1, number_of_clients + 1):
        client_number = i + 1
        client = TestClient(
            name=f"test_{base_port + client_number}",
            port=base_port + client_number,
            address="127.0.0.1",
            message_logger=message_logger,
            debug=True,
        )
        clients.append(client)
        debug(
            f"Utworzono klienta {client_number} na porcie {base_port + client_number}",
            message_logger=message_logger,
        )
    return clients


def shutdown_client(client):
    """Funkcja pomocnicza do zamykania klienta w osobnym wątku."""
    try:
        client.shutdown()
    except Exception as e:
        error(f"Błąd podczas zamykania klienta {client._EventListener__port}: {e}")


def signal_handler(signum, frame, clients):
    """Obsługa sygnału Ctrl+C."""
    info("Otrzymano sygnał zamknięcia. Rozpoczynanie sekwencji zamykania...")

    # Zamknij wszystkich klientów równolegle
    with ThreadPoolExecutor(max_workers=len(clients)) as executor:
        # Uruchom zamykanie wszystkich klientów równolegle
        futures = [executor.submit(shutdown_client, client) for client in clients]

        # Poczekaj na zakończenie wszystkich operacji z krótkim timeoutem
        for future in futures:
            try:
                future.result(timeout=2.0)  # Timeout dla całego procesu zamykania
            except Exception as e:
                error(f"Timeout podczas zamykania klienta: {e}")

    # Daj krótką chwilę na zakończenie
    time.sleep(0.5)
    sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="test")
    parser.add_argument(
        "-c",
        "--clients",
        type=int,
        default=10,
        help="test clients number (default: 10)",
    )
    args = parser.parse_args()

    temp_path = os.path.abspath("temp")
    message_logger = MessageLogger(
        filename=f"{temp_path}/test_client.log",
        period=LoggerPolicyPeriod.LAST_15_MINUTES,
    )
    # message_logger = None
    base_port = 9000
    clients = []

    try:
        info(
            f"Uruchamianie programu z {args.clients} klientami",
            message_logger=message_logger,
        )
        # Tworzenie klientów
        clients = create_clients(
            args.clients,
            base_port=base_port,
            message_logger=message_logger,
        )

        # Rejestracja obsługi sygnału Ctrl+C
        signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, clients))
        signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, clients))

        # Uruchamianie wszystkich klientów
        for client in clients:
            client.start()

        # Oczekiwanie na zakończenie
        info(
            "Wszyscy klienci uruchomieni. Oczekiwanie na sygnał zamknięcia (Ctrl+C)..."
        )
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None, clients)
    except Exception as e:
        error(f"Nieoczekiwany błąd w głównym wątku: {e}", message_logger=message_logger)
        signal_handler(signal.SIGTERM, None, clients)
    finally:
        info("Program zakończony.", message_logger=None)
