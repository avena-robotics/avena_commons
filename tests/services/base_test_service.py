"""
Bazowa klasa dla testowych usług - implementuje podstawową maszynę stanów FSM.
"""

from typing import Optional

from avena_commons.event_listener.event import Event, Result
from avena_commons.event_listener.event_listener import (
    EventListener,
    EventListenerState,
)
from avena_commons.util.logger import MessageLogger, error, info, warning


class BaseTestService(EventListener):
    """
    Bazowa klasa dla testowych usług.

    Implementuje podstawową maszynę stanów FSM zgodną z dokumentacją:
    - READY: Stan początkowy, gotowy na polecenia
    - INITIALIZING: Wykonuje inicjalizację
    - INITIALIZED: Inicjalizacja zakończona, gotowy do startu
    - STARTED: Główny stan operacyjny
    - STOPPING: Graceful shutdown w toku
    - STOPPED: Zatrzymany, gotowy do bezpiecznego zamknięcia
    - FAULT: Stan błędu
    """

    def __init__(
        self,
        name: str,
        port: int,
        address: str = "127.0.0.1",
        message_logger: Optional[MessageLogger] = None,
        initialization_time: float = 2.0,
        shutdown_time: float = 1.0,
    ):
        """
        Inicjalizuje testową usługę.

        Args:
            name: Nazwa usługi
            port: Port serwera
            address: Adres IP
            message_logger: Logger wiadomości
            initialization_time: Czas symulacji inicjalizacji (sekundy)
            shutdown_time: Czas symulacji zamykania (sekundy)
        """
        self._service_name = name
        self._initialization_time = initialization_time
        self._shutdown_time = shutdown_time

        super().__init__(
            name=name, port=port, address=address, message_logger=message_logger
        )

        # Usługa zaczyna w stanie READY zgodnie z dokumentacją
        # (EventListener standardowo zaczyna w STOPPED, więc zmieniamy)
        self._change_fsm_state(EventListenerState.STOPPED)
        info(
            f"Testowa usługa '{name}' zainicjalizowana w stanie STOPPED",
            message_logger=self._message_logger,
        )

    async def _analyze_event(self, event: Event) -> bool:
        """
        Analizuje wydarzenia i reaguje na komendy FSM.
        """
        match event.event_type:
            case "CMD_INITIALIZE":
                if event.result is None:
                    await self._handle_cmd_initialize(event)
                else:
                    # To jest odpowiedź na nasze zapytanie - ignorujemy
                    pass

            case "CMD_RUN" | "CMD_START":  # Obsługujemy oba warianty
                if event.result is None:
                    await self._handle_cmd_run(event)
                else:
                    pass

            case "CMD_GRACEFUL_STOP":
                if event.result is None:
                    await self._handle_cmd_graceful_stop(event)
                else:
                    pass

            case "CMD_RESET":
                if event.result is None:
                    await self._handle_cmd_reset(event)
                else:
                    pass

            case _:
                # Inne zdarzenia - możemy je obsłużyć w klasach potomnych
                await self._handle_custom_event(event)

        return True

    async def _handle_cmd_initialize(self, event: Event):
        """Obsługuje komendę inicjalizacji."""
        match self.fsm_state:
            case EventListenerState.STOPPED:
                info(
                    f"{self._service_name}: Rozpoczynam inicjalizację...",
                    message_logger=self._message_logger,
                )
                self._change_fsm_state(EventListenerState.INITIALIZING)

                # Wyślij potwierdzenie
                event.result = Result(
                    result="success", data={"message": "Inicjalizacja rozpoczęta"}
                )
                await self._reply(event)

            case _:
                warning(
                    f"{self._service_name}: CMD_INITIALIZE w nieprawidłowym stanie: {self.fsm_state.name}",
                    message_logger=self._message_logger,
                )
                event.result = Result(
                    result="error",
                    error_message=f"Nie można zainicjalizować w stanie {self.fsm_state.name}",
                )
                await self._reply(event)

    async def _handle_cmd_run(self, event: Event):
        """Obsługuje komendę uruchomienia."""
        match self.fsm_state:
            case EventListenerState.INITIALIZED:
                info(
                    f"{self._service_name}: Przechodzę do stanu operacyjnego...",
                    message_logger=self._message_logger,
                )
                self._change_fsm_state(EventListenerState.STARTING)

                # Wyślij potwierdzenie
                event.result = Result(
                    result="success", data={"message": "Uruchomienie rozpoczęte"}
                )
                await self._reply(event)

            case _:
                warning(
                    f"{self._service_name}: CMD_RUN w nieprawidłowym stanie: {self.fsm_state.name}",
                    message_logger=self._message_logger,
                )
                event.result = Result(
                    result="error",
                    error_message=f"Nie można uruchomić w stanie {self.fsm_state.name}",
                )
                await self._reply(event)

    async def _handle_cmd_graceful_stop(self, event: Event):
        """Obsługuje komendę graceful stop."""
        match self.fsm_state:
            case EventListenerState.STARTED:
                info(
                    f"{self._service_name}: Rozpoczynam graceful shutdown...",
                    message_logger=self._message_logger,
                )
                self._change_fsm_state(EventListenerState.STOPPING)

                # Wyślij potwierdzenie
                event.result = Result(
                    result="success", data={"message": "Graceful stop rozpoczęty"}
                )
                await self._reply(event)

            case _:
                warning(
                    f"{self._service_name}: CMD_GRACEFUL_STOP w nieprawidłowym stanie: {self.fsm_state.name}",
                    message_logger=self._message_logger,
                )
                event.result = Result(
                    result="error",
                    error_message=f"Nie można zatrzymać w stanie {self.fsm_state.name}",
                )
                await self._reply(event)

    async def _handle_cmd_reset(self, event: Event):
        """Obsługuje komendę reset ze stanu FAULT."""
        match self.fsm_state:
            case EventListenerState.FAULT:
                info(
                    f"{self._service_name}: Reset ze stanu FAULT...",
                    message_logger=self._message_logger,
                )
                self._change_fsm_state(EventListenerState.STOPPED)

                # Wyślij potwierdzenie
                event.result = Result(
                    result="success", data={"message": "Reset wykonany"}
                )
                await self._reply(event)

            case _:
                warning(
                    f"{self._service_name}: CMD_RESET w nieprawidłowym stanie: {self.fsm_state.name}",
                    message_logger=self._message_logger,
                )
                event.result = Result(
                    result="error", error_message=f"Reset możliwy tylko w stanie FAULT"
                )
                await self._reply(event)

    async def _handle_custom_event(self, event: Event):
        """
        Obsługuje niestandardowe zdarzenia - do przedefiniowania w klasach potomnych.
        """
        if event.result is None:
            # Testowa komenda wymuszająca FAULT dla usług demo
            if event.event_type == "CMD_FORCE_FAULT":
                # Odczytaj error i error_message z event.data jeśli są
                error_flag = False
                error_msg = None
                if event.data:
                    error_flag = bool(event.data.get("error", False))
                    error_msg = event.data.get("error_message")

                # Ustaw stan błędu i komunikat
                if error_flag:
                    self._error = True
                if error_msg:
                    self._error_message = error_msg

                error(
                    f"{self._service_name}: Otrzymano CMD_FORCE_FAULT - przejście do FAULT"
                    + (f"; error_message: {error_msg}" if error_msg else ""),
                    message_logger=self._message_logger,
                )
                self._change_fsm_state(EventListenerState.ON_ERROR)
                event.result = Result(
                    result="success",
                    data={
                        "message": "Forced fault",
                        "error": error_flag,
                        "error_message": error_msg,
                    },
                )
                await self._reply(event)
                return

            event.result = Result(
                result="info",
                data={"message": f"Obsłużono zdarzenie {event.event_type}"},
            )
            await self._reply(event)

    # Przejścia stanów FSM zgodnie z dokumentacją

    # async def on_initializing(self):
    #     """STOPPED → INITIALIZING: Symulacja procesu inicjalizacji."""

    #     # Przejdź do INITIALIZED
    #     self._change_fsm_state(EventListenerState.INITIALIZED)

    # async def on_initialized(self):
    #     """INITIALIZED: Oczekiwanie na komendę start."""
    #     info(
    #         f"{self._service_name}: Gotowy do uruchomienia",
    #         message_logger=self._message_logger,
    #     )

    # async def on_starting(self):
    #     """INITIALIZED → STARTING → RUN: Uruchomienie operacji."""
    #     info(
    #         f"{self._service_name}: Uruchamiam operacje...",
    #         message_logger=self._message_logger,
    #     )

    #     # Krótka symulacja startu
    #     await asyncio.sleep(0.5)

    #     # Przejdź do RUN
    #     self._change_fsm_state(EventListenerState.RUN)
    #     info(
    #         f"{self._service_name}: Operacje uruchomione - stan RUN",
    #         message_logger=self._message_logger,
    #     )

    async def on_run(self):
        """RUN: Główny cykl operacyjny."""
        # Tutaj można dodać symulację działania usługi
        await self._simulate_work()

    # async def on_stopping(self):
    #     """STARTED → STOPPING → STOPPED: Graceful shutdown."""
    #     info(
    #         f"{self._service_name}: Wykonuję graceful shutdown ({self._shutdown_time}s)...",
    #         message_logger=self._message_logger,
    #     )

    #     # Symuluj proces zamykania
    #     await asyncio.sleep(self._shutdown_time)

    #     # Przejdź do STOPPED
    #     self._change_fsm_state(EventListenerState.STOPPED)
    #     info(
    #         f"{self._service_name}: Graceful shutdown zakończony - stan STOPPED",
    #         message_logger=self._message_logger,
    #     )

    # async def on_stopped(self):
    #     """STOPPED: Stan pasywny."""
    #     # W stanie stopped nic nie robimy, czekamy na komendy
    #     pass

    # async def on_fault(self):
    #     """FAULT: Stan błędu - czeka na reset."""
    #     error(
    #         f"{self._service_name}: W stanie FAULT - oczekiwanie na reset",
    #         message_logger=self._message_logger,
    #     )

    async def _simulate_work(self):
        """
        Symuluje pracę usługi w stanie RUN.
        Do przedefiniowania w klasach potomnych.
        """
        # Domyślnie nic nie robimy
        pass

    def get_service_info(self) -> dict:
        """
        Zwraca informacje o usłudze dla statusu.
        """
        return {
            "name": self._service_name,
            "state": self.fsm_state.name,
            "port": self._port,
            "address": self._address,
        }
