"""
Implementacja akcji log_event dla scenariuszy.
"""

from typing import Any, Dict

from avena_commons.util.logger import debug, error, info, warning

from .base_action import ActionExecutionError, BaseAction
from ..models.scenario_models import ScenarioContext


class LogAction(BaseAction):
    """
    Akcja logowania komunikatów z różnymi poziomami.

    Obsługuje poziomy: info, warning, error, critical, success, debug

    Przykład użycia w YAML:
    - type: "log_event"
      level: "info"
      message: "Rozpoczynam proces inicjalizacji"

    - type: "log_event"
      level: "error"
      message: "Błąd w komponencie {{ trigger.source }}"
    """

    async def execute(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> None:
        """
        Wykonuje logowanie komunikatu z określonym poziomem.

        Args:
            action_config: Konfiguracja z kluczami:
                - level: poziom logowania (info, warning, error, critical, success, debug)
                - message: komunikat do zalogowania (może zawierać zmienne {{ }})
            context: Kontekst wykonania akcji

        Raises:
            ActionExecutionError: W przypadku błędnej konfiguracji
        """
        try:
            # Pobierz poziom logowania (domyślnie info)
            level = action_config.get("level", "info").lower()

            # Pobierz komunikat
            message = action_config.get("message", "")
            if not message:
                raise ActionExecutionError(
                    "log_event", "Brak komunikatu do zalogowania (klucz: message)"
                )

            # Rozwiąż zmienne szablonowe w komunikacie
            resolved_message = self._resolve_template_variables(message, context)

            # Wykonaj logowanie na odpowiednim poziomie
            match level:
                case "info":
                    info(resolved_message, message_logger=context.message_logger)
                case "warning" | "warn":
                    warning(resolved_message, message_logger=context.message_logger)
                case "error":
                    error(resolved_message, message_logger=context.message_logger)
                case "critical":
                    # Critical to error z prefiksem
                    error(
                        f"CRITICAL: {resolved_message}",
                        message_logger=context.message_logger,
                    )
                case "success":
                    # Success to info z symbolem ✓
                    info(f"✓ {resolved_message}", message_logger=context.message_logger)
                case "debug":
                    debug(resolved_message, message_logger=context.message_logger)
                case _:
                    # Nieznany poziom - użyj info z ostrzeżeniem
                    warning(
                        f"Nieznany poziom logowania '{level}', używam 'info'",
                        message_logger=context.message_logger,
                    )
                    info(resolved_message, message_logger=context.message_logger)

        except Exception as e:
            if isinstance(e, ActionExecutionError):
                raise
            raise ActionExecutionError(
                "log_event", f"Błąd podczas logowania: {str(e)}", e
            )
