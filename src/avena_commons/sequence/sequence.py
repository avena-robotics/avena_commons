"""Moduł zarządzania sekwencjami kroków.

Odpowiedzialność:
- Zarządzanie stanem i przepływem kroków w sekwencjach
- Obsługa restartów sekwencji i warunków restartowania
- Śledzenie statusu wykonania poszczególnych kroków

Eksponuje:
- Klasa `Sequence` (główny manager sekwencji)
- Klasa `SequenceStatus` (status całej sekwencji)
- Klasa `SequenceStepStatus` (status pojedynczego kroku)
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from avena_commons.event_listener import Result
from avena_commons.util.logger import MessageLogger, debug, error, info

from .step_state import StepState


class SequenceStepStatus(BaseModel):
    """Status of a single step in the sequence.

    Stores information about the step's state, number of execution attempts,
    and parameters needed for its execution.

    Attributes:
        step_id (int): Unique step identifier
        fsm_state (StepState): Current state of the step in the state machine
        retry_count (int): Counter for step execution attempts
        params (dict[str, Any]): Parameters needed for step execution
    """

    step_id: int
    fsm_state: StepState = StepState.PREPARE
    error_code: int = 0
    retry_count: int = 0
    params: dict[str, Any] = {}  # dane/parametry potrzebne do kroku


class SequenceStatus(BaseModel):
    """Status of the entire sequence of steps.

    Stores information about the current sequence state, including current step,
    statuses of all steps, and whether the sequence has been completed.

    Attributes:
        sequence_enum (str | type[Enum]): Sequence type (as string or enum)
        current_step (int): Number of currently executing step
        steps (dict[int, SequenceStepStatus]): Dictionary containing statuses of all steps
        finished (bool): Flag indicating whether the sequence has been completed
    """

    sequence_enum: str | type[Enum]  # Akceptujemy zarówno string jak i enum
    current_step: int
    steps: dict[int, SequenceStepStatus]
    finished: bool = False

    # model_config = {
    #     "json_encoders": {
    #         type(Enum): lambda v: v.__name__  # encoder dla typu enum
    #     }
    # }

    def is_finished(self) -> bool:
        """Checks if the sequence has finished.

        Returns:
            bool: True if the sequence has finished, False otherwise
        """
        return self.finished

    @field_validator("sequence_enum", mode="before")
    @classmethod
    def validate_sequence_enum(cls, v):
        """Validates and normalizes the sequence_enum value.

        Args:
            v: Value to validate, can be string or Enum type

        Returns:
            str: Normalized sequence name

        Raises:
            ValueError: When passed type is neither string nor Enum
        """
        if isinstance(v, str):
            # Jeśli to string, zwracamy go bez zmian
            return v
        elif isinstance(v, type) and issubclass(v, Enum):
            # Jeśli to enum, zwracamy jego nazwę
            return v.__name__
        raise ValueError(f"Invalid sequence_enum type: {type(v)}")

    @property
    def get_current_step_status(self) -> SequenceStepStatus:
        """Gets the status of currently executing step.

        Returns:
            SequenceStepStatus: Status of current step or DONE status if sequence is completed
        """
        if self.current_step == 0:  # Sekwencja zakończona
            return SequenceStepStatus(step_id=0, fsm_state=StepState.DONE)
        return self.steps[self.current_step]


class Sequence(BaseModel):
    """Class managing the state and flow of steps in a sequence.

    Responsible for controlling sequence execution, managing step states,
    and handling events related to step execution.

    Attributes:
        sequence_enum (str | type[Enum]): Enum defining sequence steps
        status (SequenceStatus): Current sequence status
        parametry (dict[str, Any]): Sequence configuration parameters
        restart (bool): Flag indicating if sequence should be restarted
        can_restart (bool): Flag indicating if sequence is in restartable state
        restart_target_step (int): Step number to restart to when restart is triggered
    """

    produkt_id: int
    sequence_enum: str | type[Enum]
    status: SequenceStatus = Field(default_factory=SequenceStatus)
    parametry: dict[str, Any] = Field(default_factory=dict)
    creation_timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    restart: bool = Field(default=False)
    can_restart: bool = Field(default=False)
    restart_target_step: int = Field(default=1)

    @field_validator("sequence_enum", mode="before")
    @classmethod
    def validate_sequence_enum(cls, v):
        if isinstance(v, str):
            return v
        elif isinstance(v, type) and issubclass(v, Enum):
            return v.__name__
        raise ValueError(f"Invalid sequence_enum type: {type(v)}")

    def __init__(
        self, produkt_id: int, enum_class=None, initial_step=1, parametry=None, **data
    ):
        # Obsługa kompatybilności wstecznej
        if not enum_class and "sequence_enum" in data:
            # Stary styl inicjalizacji - używamy przekazanych danych
            # Unikamy podwójnego przekazania 'parametry'
            if parametry is not None and "parametry" not in data:
                super().__init__(produkt_id=produkt_id, parametry=parametry, **data)
            else:
                super().__init__(produkt_id=produkt_id, **data)
            # Nie wymuszamy rozwiązywania klasy enuma przy wczytywaniu ze stanu.
            # Jeżeli enum_class nie jest podany, pozostawiamy None i działamy na danych statusu.
            enum_class = data.pop("enum_class", None)
        else:
            # Nowy styl inicjalizacji - generujemy wszystko na podstawie enum_class
            if enum_class is None:
                raise ValueError(
                    "Parametr 'enum_class' jest wymagany przy nowym stylu inicjalizacji"
                )

            sequence_enum = enum_class.__name__

            # Przygotowujemy status
            current_step = initial_step
            steps = {
                step.value: SequenceStepStatus(
                    step_id=step.value, fsm_state=StepState.PREPARE
                )
                for step in enum_class
                if not step.name.startswith("__")
            }

            status_obj = data.get(
                "status",
                SequenceStatus(
                    sequence_enum=sequence_enum, current_step=current_step, steps=steps
                ),
            )

            # Wywołujemy konstruktor
            super().__init__(
                produkt_id=produkt_id,
                sequence_enum=sequence_enum,
                status=status_obj,
                parametry=parametry or {},
            )

        # Zapisujemy klasę enuma do użycia później (może być None)
        self.__enum_class = enum_class

        # Nie musimy inicjalizować status, bo jest już zainicjalizowany przez BaseModel
        # lub przez nasz kod wyżej

    # class Config:
    #     use_enum_values = True
    # def model_dump(self) -> dict:
    #     return {
    #         "sequence_enum": self.sequence_enum if isinstance(self.sequence_enum, str) else self.sequence_enum.__name__,
    #         "status": self.status.model_dump(),
    #         "parametry": self.parametry,
    #     }

    def process_event(
        self,
        produkt_id: int,
        result: Result,
        message_logger: MessageLogger | None = None,
    ) -> None:
        """Obsługa zdarzeń dla sekwencji."""
        step_status = self.status.get_current_step_status
        old_state = step_status.fsm_state

        # Obsługa różnych typów zdarzeń
        if result.result == "success":
            step_status.fsm_state = StepState.DONE
        elif result.result == "failure":
            step_status.fsm_state = StepState.ERROR
            step_status.error_code = result.error_code
            error(
                f"Wystapil blad podczas wykonywania kroku {step_status.step_id} sekwencji {self.sequence_enum}. Produkt ID: {produkt_id}. Error code: {result.error_code}",
                message_logger=message_logger,
            )
        elif result.result == "test_failed":
            step_status.fsm_state = StepState.TEST_FAILED
        if produkt_id != self.produkt_id:
            error(
                f"Produkt ID mismatch. Expected {self.produkt_id}, got {produkt_id}",
                message_logger=message_logger,
            )
        # Logowanie zmiany stanu
        if old_state != step_status.fsm_state:
            self._log_state_change(StepState(step_status.fsm_state), message_logger)

    def _do_prepare(
        self,
        step_status: SequenceStepStatus,
        message_logger: MessageLogger | None = None,
    ) -> None:
        """Przygotowanie do wykonania kroku."""
        step_status.fsm_state = StepState.PREPARE
        self._log_state_change(StepState.PREPARE, message_logger)

    def _do_execute(
        self,
        step_status: SequenceStepStatus,
        message_logger: MessageLogger | None = None,
    ) -> None:
        """Wykonanie kroku."""
        step_status.fsm_state = StepState.EXECUTE
        self._log_state_change(StepState.EXECUTE, message_logger)

    def _do_done(
        self,
        step_status: SequenceStepStatus,
        message_logger: MessageLogger | None = None,
    ) -> None:
        """Zakończenie kroku."""
        step_status.fsm_state = StepState.DONE
        self._log_state_change(StepState.DONE, message_logger)

    def _do_error(
        self,
        step_status: SequenceStepStatus,
        message_logger: MessageLogger | None = None,
    ) -> None:
        """Zakończenie kroku."""
        step_status.fsm_state = StepState.ERROR
        self._log_state_change(StepState.ERROR, message_logger)

    def _log_state_change(
        self, state: StepState, message_logger: MessageLogger | None = None
    ) -> None:
        """Centralny mechanizm logowania zmiany stanu."""
        step_id = self.status.current_step
        step_name = self._get_step_name(step_id)

        message = f"{self.sequence_enum}.{step_name}.{state.name} produkt_id={self.produkt_id}"
        info(message, message_logger=message_logger)

    def _get_step_name(self, step_id: int) -> str:
        """Pobiera nazwę kroku na podstawie jego ID."""
        # Zamiast szukać w globals(), używamy zapisanej referencji do klasy enuma
        enum_class = getattr(self, "_Sequence__enum_class", None)
        if not enum_class:
            return f"STEP_{step_id}"

        for member in enum_class:
            if member.value == step_id:
                return member.name

        return f"STEP_{step_id}"

    def run_step(self, message_logger: MessageLogger | None = None) -> None:
        """Executes the current step in the sequence.

        Changes the step state from PREPARE to EXECUTE, allowing it to be processed
        by the munchies_algo logic.

        Args:
            message_logger (MessageLogger, optional): Logger for recording messages. Defaults to None.
        """
        step_status = self.status.get_current_step_status

        if step_status.fsm_state == StepState.PREPARE:
            self._do_execute(step_status, message_logger)

    def rerun_step(self, message_logger: MessageLogger | None = None) -> None:
        """Reruns the current step in the sequence.

        Increments the current step and sets its state to PREPARE, allowing it to be
        executed again in the munchies_algo logic.

        Args:
            message_logger (MessageLogger, optional): Logger for recording messages. Defaults to None.
        """
        step_status = self.status.get_current_step_status
        step_status.retry_count += 1
        self._do_prepare(step_status, message_logger)

        # if step_status.fsm_state == StepState.ERROR:
        #     self._do_prepare(step_status, message_logger)

    def error_step(self, message_logger: MessageLogger | None = None) -> None:
        """Marks the current step as error."""
        self._do_error(self.status.get_current_step_status, message_logger)

    def set_restart(
        self, value: bool = True, message_logger: MessageLogger | None = None
    ) -> None:
        """Ustawia flagę restart dla sekwencji.

        Args:
            value (bool): Wartość flagi restart (domyślnie True).
            message_logger (MessageLogger | None): Logger do zapisywania komunikatów.
        """
        self.restart = value
        info(
            f"Ustawiono flagę restart={value} dla sekwencji {self.sequence_enum} produktu {self.produkt_id}",
            message_logger=message_logger,
        )

    def set_can_restart(
        self, value: bool = True, message_logger: MessageLogger | None = None
    ) -> None:
        """Ustawia flagę can_restart dla sekwencji.

        Args:
            value (bool): Wartość flagi can_restart (domyślnie True).
            message_logger (MessageLogger | None): Logger do zapisywania komunikatów.
        """
        self.can_restart = value
        info(
            f"Ustawiono flagę can_restart={value} dla sekwencji {self.sequence_enum} produktu {self.produkt_id}",
            message_logger=message_logger,
        )

    def get_restart(self) -> bool:
        """Zwraca wartość flagi restart.

        Returns:
            bool: Wartość flagi restart.
        """
        return self.restart

    def get_can_restart(self) -> bool:
        """Zwraca wartość flagi can_restart.

        Returns:
            bool: Wartość flagi can_restart.
        """
        return self.can_restart

    def reset_restart_flags(self, message_logger: MessageLogger | None = None) -> None:
        """Resetuje flagi restart i can_restart do False.

        Args:
            message_logger (MessageLogger | None): Logger do zapisywania komunikatów.
        """
        self.restart = False
        self.can_restart = False
        info(
            f"Zresetowano flagi restart dla sekwencji {self.sequence_enum} produktu {self.produkt_id}",
            message_logger=message_logger,
        )

    def should_restart(self, message_logger: MessageLogger | None = None) -> bool:
        """Sprawdza czy sekwencja powinna zostać zrestartowana.

        Returns:
            bool: True jeśli sekwencja powinna zostać zrestartowana (restart=True i can_restart=True).
        """
        debug(
            f"Sprawdzanie warunków restartu: restart={self.restart}, can_restart={self.can_restart}",
            message_logger=message_logger,
        )
        return self.restart and self.can_restart

    def restart_sequence(self, message_logger: MessageLogger | None = None) -> bool:
        """Restartuje sekwencję jeśli spełnione są warunki restartu.

        Resetuje sekwencję do kroku określonego przez atrybut restart_to_step
        i przygotowuje do ponownego wykonania. Zeruje liczniki ponowień wszystkich kroków i flagi restart.

        Args:
            message_logger (MessageLogger | None): Logger do zapisywania komunikatów.

        Returns:
            bool: True jeśli restart został wykonany, False w przeciwnym razie.
        """
        if not self.should_restart(message_logger=message_logger):
            debug(
                f"Warunki restartu nie spełnione, pomijam restart sekwencji, should_restart: {self.should_restart}",
                message_logger=message_logger,
            )
            return False

        info(
            f"Restartowanie sekwencji {self.sequence_enum} dla produktu {self.produkt_id} do kroku {self.restart_target_step}",
            message_logger=message_logger,
        )

        # Resetuj status sekwencji
        self.status.finished = False
        self.status.current_step = self.restart_target_step

        # Resetuj wszystkie kroki do stanu PREPARE i wyzeruj liczniki ponowień
        for step_status in self.status.steps.values():
            step_status.fsm_state = StepState.PREPARE
            step_status.retry_count = 0
            step_status.error_code = 0

        # Resetuj flagi restart
        self.reset_restart_flags(message_logger=message_logger)

        # Przygotuj określony krok
        if self.restart_target_step in self.status.steps:
            self._do_prepare(
                self.status.steps[self.restart_target_step], message_logger
            )

        info(
            f"Sekwencja {self.sequence_enum} została zrestartowana dla produktu {self.produkt_id} do kroku {self.restart_target_step}",
            message_logger=message_logger,
        )

        return True

    def restart_to_step(
        self, step_id: int, message_logger: MessageLogger | None = None
    ) -> None:
        """Restartuje sekwencję do określonego kroku.

        Ustawia atrybut restart_target_step, flagę restart, can_restart i wykonuje restart.
        Jest to wygodna metoda do wymuszenia restartu bez sprawdzania warunków.

        Args:
            step_id (int): Numer kroku, do którego ma zostać zresetowana sekwencja.
            message_logger (MessageLogger | None): Logger do zapisywania komunikatów.
        """
        debug(
            f"Wymuszanie restartu sekwencji {self.sequence_enum} do kroku {step_id} dla produktu {self.produkt_id}",
            message_logger=message_logger,
        )
        self.restart_target_step = step_id
        self.set_restart(True, message_logger)
        self.set_can_restart(True, message_logger)

        debug(
            f"Ustawionpo restart_target_step={step_id}, restart=True, can_restart=True",
            message_logger=message_logger,
        )
        self.restart_sequence(message_logger)

    def set_restart_target_step(
        self, step_id: int, message_logger: MessageLogger | None = None
    ) -> None:
        """Ustawia numer kroku, do którego sekwencja ma zostać zresetowana podczas restartu.

        Args:
            step_id (int): Numer kroku, do którego ma zostać zresetowana sekwencja.
            message_logger (MessageLogger | None): Logger do zapisywania komunikatów.
        """
        self.restart_target_step = step_id
        info(
            f"Ustawiono restart_target_step={step_id} dla sekwencji {self.sequence_enum} produktu {self.produkt_id}",
            message_logger=message_logger,
        )

    def done_step(self, message_logger: MessageLogger | None = None):
        """Marks the current step as done.

        Sets the current step's state to DONE and checks for restart conditions.

        Args:
            message_logger (MessageLogger, optional): Logger for recording messages. Defaults to None.
        """
        step_status = self.status.get_current_step_status

        # Sprawdź czy to jest ostatni krok i czy powinniśmy zrestartować
        if self.should_restart(message_logger=message_logger):
            info(
                f"Wykryto żądanie restartu sekwencji {self.sequence_enum} po zakończeniu ostatniego kroku",
                message_logger=message_logger,
            )
            self.restart_sequence(message_logger)
            return  # Nie przechodzimy do next_step, bo zrestartowaliśmy

        self._do_done(step_status, message_logger)
        # Jeśli nie restartujemy, kontynuuj normalnie
        # self.next_step(message_logger)

    def next_step(self, message_logger: MessageLogger | None = None) -> None:
        """Advances to the next step in the sequence.

        Increments the step counter if there are more steps to execute,
        otherwise marks the sequence as finished. Also handles sequence restart
        if restart conditions are met in the last step.

        Args:
            message_logger (MessageLogger, optional): Logger for recording messages. Defaults to None.
        """
        if self.should_restart(message_logger=message_logger):
            info(
                f"Wykryto żądanie restartu sekwencji {self.sequence_enum} po zakończeniu wszystkich kroków",
                message_logger=message_logger,
            )
            self.restart_sequence(message_logger)
        elif self.status.current_step < len(self.status.steps):
            self.status.current_step += 1
            self._do_prepare(
                self.status.steps[self.status.current_step], message_logger
            )
        else:
            self.status.finished = True

    def go_to_step(
        self, step_id: int, message_logger: MessageLogger | None = None
    ) -> None:
        """Jumps to a specific step in the sequence.

        Sets the current step to the specified step_id and prepares it for execution.

        Args:
            step_id (int): The ID of the step to jump to
            message_logger (MessageLogger, optional): Logger for recording messages. Defaults to None.
        """
        self.status.current_step = step_id
        self._do_prepare(self.status.steps[step_id], message_logger)

    def end(self, message_logger: MessageLogger | None = None) -> None:
        """Ends the sequence.

        Marks the sequence as finished and sets current_step to 0,
        which is a special value indicating sequence completion.

        Args:
            message_logger (MessageLogger, optional): Logger for recording messages. Defaults to None.
        """
        info(
            f"Sekwencja {self.sequence_enum} zakonczona", message_logger=message_logger
        )
        self.status.finished = True
        self.status.current_step = 0
