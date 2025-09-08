"""
ActionExecutor - klasa zarządzająca wykonywaniem akcji scenariuszy.
"""

from typing import Any, Dict

from .base_action import ActionContext, ActionExecutionError, BaseAction
from .execute_scenario_action import ExecuteScenarioAction
from .log_action import LogAction
from .send_command_action import SendCommandAction
from .send_email_action import SendEmailAction
from .systemctl_action import SystemctlAction
from .wait_for_state_action import WaitForStateAction


class ActionExecutor:
    """
    Klasa odpowiedzialna za zarządzanie i wykonywanie akcji scenariuszy.

    Rejestruje wszystkie dostępne akcje i zapewnia jednolity interfejs
    do ich wykonywania przez Orchestrator.
    """

    def __init__(self, register_default_actions: bool = True):
        """
        Inicjalizuje ActionExecutor i opcjonalnie rejestruje domyślne akcje.

        Args:
            register_default_actions: Czy automatycznie zarejestrować domyślne akcje
        """
        self._actions: Dict[str, BaseAction] = {}
        if register_default_actions:
            self._register_default_actions()

    def _register_default_actions(self) -> None:
        """Rejestruje wszystkie domyślne akcje scenariuszy."""
        self._actions["log_event"] = LogAction()
        self._actions["send_command"] = SendCommandAction()
        self._actions["wait_for_state"] = WaitForStateAction()
        self._actions["systemctl"] = SystemctlAction()
        self._actions["send_email"] = SendEmailAction()
        
        # NOWE: Akcje kontroli przepływu scenariuszy
        self._actions["execute_scenario"] = ExecuteScenarioAction()
        
    def register_action(self, action_type: str, action_instance: BaseAction) -> None:
        """
        Rejestruje nową akcję lub nadpisuje istniejącą.

        Args:
            action_type: Typ akcji (klucz 'type' w JSON)
            action_instance: Instancja klasy implementującej BaseAction
        """
        self._actions[action_type] = action_instance

    def get_registered_actions(self) -> Dict[str, BaseAction]:
        """
        Zwraca słownik wszystkich zarejestrowanych akcji.

        Returns:
            Słownik {typ_akcji: instancja_akcji}
        """
        return self._actions.copy()

    async def execute_action(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> Any:
        """
        Wykonuje akcję na podstawie konfiguracji (deleguje do zarejestrowanej akcji).

        Args:
            action_config: Konfiguracja akcji z pliku YAML (musi zawierać klucz 'type')
            context: Kontekst wykonania akcji

        Returns:
            Wynik wykonania akcji (zależny od typu akcji)

        Raises:
            ActionExecutionError: W przypadku błędu wykonania lub nieznanego typu akcji
        """
        action_type = action_config.get("type")

        if not action_type:
            raise ActionExecutionError(
                "unknown", "Brak typu akcji (klucz: type) w konfiguracji"
            )

        if action_type not in self._actions:
            available_actions = list(self._actions.keys())
            raise ActionExecutionError(
                action_type,
                f'Nieznany typ akcji "{action_type}". Dostępne: {available_actions}',
            )

        action_instance = self._actions[action_type]

        # Logowanie początku akcji
        action_description = action_config.get("description", "")
        from avena_commons.util.logger import error, info

        info(
            f"🎬 START akcji: {action_type} | {action_description}",
            message_logger=context.message_logger,
        )

        try:
            result = await action_instance.execute(action_config, context)

            # Logowanie końca akcji (sukces)
            info(
                f"✅ END akcji: {action_type} | Zakończona pomyślnie",
                message_logger=context.message_logger,
            )

            return result

        except ActionExecutionError:
            # Logowanie końca akcji (błąd ActionExecutionError)
            error(
                f"❌ END akcji: {action_type} | Błąd ActionExecutionError",
                message_logger=context.message_logger,
            )
            # Przepuść błędy ActionExecutionError bez opakowywania
            raise

        except Exception as e:
            # Logowanie końca akcji (nieoczekiwany błąd)
            error(
                f"💥 END akcji: {action_type} | Nieoczekiwany błąd: {e}",
                message_logger=context.message_logger,
            )
            # Opakuj inne wyjątki w ActionExecutionError
            error(
                f"Nieoczekiwany błąd podczas wykonywania akcji '{action_type}': {e}",
                message_logger=context.message_logger,
            )
            raise ActionExecutionError(action_type, f"Nieoczekiwany błąd: {str(e)}", e)
