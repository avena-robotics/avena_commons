"""Klasa bazowa dla urządzeń fizycznych z FSM i zarządzaniem błędami.

Odpowiedzialność:
- Śledzenie stanu urządzenia fizycznego (FSM)
- Zarządzanie błędami i ich propagacja
- Możliwość nadpisania akcji przy przejściach stanów
- ACK i reset błędów

Eksponuje:
- Enum `PhysicalDeviceState`
- Klasa bazowa `PhysicalDeviceBase`
"""

from enum import Enum
from threading import Lock
from typing import Any, Dict

from avena_commons.util.logger import MessageLogger, debug, error, info


class PhysicalDeviceState(Enum):
    """Stany FSM urządzenia fizycznego.

    Attributes:
        UNINITIALIZED: Urządzenie nie zostało jeszcze zainicjalizowane.
        INITIALIZING: Urządzenie jest w trakcie inicjalizacji.
        WORKING: Urządzenie pracuje prawidłowo.
        ERROR: Urządzenie wykryło błąd.
        FAULT: Urządzenie w stanie krytycznego błędu, wymaga interwencji operatora.
    """

    UNINITIALIZED = 0
    INITIALIZING = 1
    WORKING = 2
    ERROR = 3
    FAULT = 4


class PhysicalDeviceBase:
    """Abstrakcyjna klasa bazowa dla urządzeń fizycznych z FSM i zarządzaniem błędami.

    Klasa dostarcza mechanizmy:
    - FSM stanu urządzenia (UNINITIALIZED → INITIALIZING → WORKING → ERROR → FAULT)
    - Śledzenie liczby kolejnych błędów z progiem eskalacji do FAULT
    - Możliwość nadpisania akcji przy przejściach stanów (on_error, on_fault)
    - Reset błędów przez ACK operatora (reset_fault)

    Args:
        device_name (str): Nazwa urządzenia.
        max_consecutive_errors (int): Maksymalna liczba kolejnych błędów przed przejściem do FAULT.
        message_logger (MessageLogger | None): Logger wiadomości.
        **kwargs: Dodatkowe argumenty specyficzne dla urządzenia potomnego.
    """

    def __init__(
        self,
        device_name: str,
        max_consecutive_errors: int = 3,
        message_logger: MessageLogger | None = None,
        **kwargs,
    ):
        """Inicjalizuje bazowy stan urządzenia fizycznego.

        Args:
            device_name: Nazwa urządzenia.
            max_consecutive_errors: Próg liczby błędów przed FAULT (domyślnie 3).
            message_logger: Logger wiadomości używany do logowania.
            **kwargs: Dodatkowe parametry dla klas potomnych.
        """
        self.device_name = device_name
        self.message_logger = message_logger
        self._state = PhysicalDeviceState.UNINITIALIZED
        self._error: bool = False
        self._error_message: str | None = None
        self._consecutive_errors: int = 0
        self._max_consecutive_errors = max_consecutive_errors
        self._state_lock = Lock()

        debug(
            f"{self.device_name} - PhysicalDeviceBase initialized (max_errors={max_consecutive_errors})",
            message_logger=message_logger,
        )

    def set_state(self, new_state: PhysicalDeviceState) -> None:
        """Ustawia nowy stan FSM urządzenia.

        Args:
            new_state: Nowy stan urządzenia.
        """
        with self._state_lock:
            old_state = self._state
            self._state = new_state
            if old_state != new_state:
                info(
                    f"{self.device_name} - State transition: {old_state.name} → {new_state.name}",
                    message_logger=self._message_logger,
                )

    def get_state(self) -> PhysicalDeviceState:
        """Zwraca aktualny stan FSM urządzenia.

        Returns:
            PhysicalDeviceState: Aktualny stan urządzenia.
        """
        with self._state_lock:
            return self._state

    def set_error(self, error_message: str) -> None:
        """Rejestruje błąd i aktualizuje FSM urządzenia.

        Logika:
        - Zwiększa licznik kolejnych błędów (_consecutive_errors)
        - Jeśli licznik błędów przekroczy próg → przejście do FAULT (wywołanie on_fault)
        - W przeciwnym razie → przejście do ERROR (wywołanie on_error)

        Args:
            error_message: Opis błędu do zapisania.

        Raises:
            None: Nie rzuca wyjątków, tylko loguje i zmienia stan.
        """
        with self._state_lock:
            self._error = True
            self._error_message = error_message
            self._consecutive_errors += 1

            # Eskalacja do FAULT po przekroczeniu progu
            if self._consecutive_errors >= self._max_consecutive_errors:
                old_state = self._state
                self._state = PhysicalDeviceState.FAULT
                error(
                    f"{self.device_name} - FAULT: {error_message} (consecutive_errors={self._consecutive_errors})",
                    message_logger=self._message_logger,
                )
                # Wywołaj on_fault (nadpisywalne przez potomne klasy)
                if old_state != PhysicalDeviceState.FAULT:
                    self._on_fault()
            else:
                # Przejście do ERROR
                old_state = self._state
                if self._state not in {
                    PhysicalDeviceState.ERROR,
                    PhysicalDeviceState.FAULT,
                }:
                    self._state = PhysicalDeviceState.ERROR
                    error(
                        f"{self.device_name} - ERROR: {error_message} (consecutive_errors={self._consecutive_errors}/{self._max_consecutive_errors})",
                        message_logger=self._message_logger,
                    )
                    # Wywołaj on_error (nadpisywalne przez potomne klasy)
                    self._on_error()

    def clear_error(self) -> None:
        """Resetuje licznik kolejnych błędów po udanej operacji.

        Nie zmienia stanu urządzenia - ERROR i FAULT wymagają jawnego ACK.
        Używane w wątkach po udanych operacjach aby resetować licznik.

        Returns:
            None
        """
        with self._state_lock:
            self._consecutive_errors = 0
            # W stanie WORKING czyścimy też flagi błędu
            if self._state == PhysicalDeviceState.WORKING:
                self._error = False
                self._error_message = None

    def _on_error(self) -> None:
        """Wywoływana przy przejściu do stanu ERROR.
        
        Potomne klasy mogą nadpisać aby wykonać akcje przy błędzie
        (np. zatrzymanie napędów, wyłączenie wyjść).
        
        Uwaga: Wywoływana wewnątrz lock'a, unikaj długich operacji.
        """
        pass

    def _on_fault(self) -> None:
        """Wywoływana przy przejściu do stanu FAULT.
        
        Potomne klasy mogą nadpisać aby wykonać akcje przy krytycznym błędzie
        (np. awaryjne zatrzymanie, zablokowanie wyjść).
        
        Uwaga: Wywoływana wewnątrz lock'a, unikaj długich operacji.
        """
        pass

    def check_health(self) -> bool:
        """Sprawdza czy urządzenie jest w stanie zdrowym (nie FAULT).

        Returns:
            bool: True jeśli urządzenie nie jest w FAULT, False w przeciwnym wypadku.
        """
        with self._state_lock:
            return self._state != PhysicalDeviceState.FAULT

    def reset_fault(self) -> bool:
        """Resetuje urządzenie z FAULT do INITIALIZING (wymaga zewnętrznego ACK).

        Metoda używana przez operatora/nadzorcę do resetu po krytycznym błędzie.

        Returns:
            bool: True jeśli reset się powiódł, False jeśli urządzenie nie było w FAULT.
        """
        with self._state_lock:
            if self._state == PhysicalDeviceState.FAULT:
                self._state = PhysicalDeviceState.INITIALIZING
                self._error = False
                self._error_message = None
                self._consecutive_errors = 0
                info(
                    f"{self.device_name} - FAULT reset → INITIALIZING",
                    message_logger=self._message_logger,
                )
                return True
            else:
                info(
                    f"{self.device_name} - Cannot reset: not in FAULT state (current: {self._state.name})",
                    message_logger=self._message_logger,
                )
                return False

    def to_dict(self) -> Dict[str, Any]:
        """Zwraca słownikową reprezentację stanu urządzenia.

        Returns:
            dict: Słownik zawierający:
                - name: nazwa urządzenia
                - state: wartość liczbowa stanu FSM
                - state_name: nazwa stanu FSM
                - error: flaga błędu (bool)
                - error_message: opis błędu (str | None)
                - consecutive_errors: liczba kolejnych błędów
        """
        with self._state_lock:
            return {
                "name": self.device_name,
                "state": self._state.value,
                "state_name": self._state.name,
                "error": self._error,
                "error_message": self._error_message,
                "consecutive_errors": self._consecutive_errors,
            }

    def __str__(self) -> str:
        """Zwraca czytelną reprezentację urządzenia w formie stringa.

        Returns:
            str: Reprezentacja urządzenia dla użytkownika.
        """
        with self._state_lock:
            error_info = f", error='{self._error_message}'" if self._error else ""
            return f"{self.__class__.__name__}(name='{self.device_name}', state={self._state.name}{error_info})"

    def __repr__(self) -> str:
        """Zwraca reprezentację urządzenia dla developerów.

        Returns:
            str: Szczegółowa reprezentacja techniczna.
        """
        with self._state_lock:
            return (
                f"{self.__class__.__name__}("
                f"device_name='{self.device_name}', "
                f"state={self._state.name}, "
                f"error={self._error}, "
                f"consecutive_errors={self._consecutive_errors})"
            )
