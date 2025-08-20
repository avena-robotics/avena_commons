"""
Przykładowa akcja testowa dla demonstracji systemu dynamicznego ładowania akcji.
"""

from typing import Any, Dict

from avena_commons.util.logger import info

from .base_action import ActionContext, BaseAction


class TestAction(BaseAction):
    """
    Przykładowa akcja testowa.

    Demonstruje jak napisać niestandardową akcję która będzie automatycznie
    wczytana przez system dynamicznego ładowania orkiestratora.
    """

    async def execute(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> Any:
        """
        Wykonuje akcję testową - wypisuje wiadomość z konfiguracją.

        Args:
            action_config: Konfiguracja akcji z pliku YAML
            context: Kontekst wykonania z danymi Orchestratora

        Returns:
            Słownik z wynikiem testu
        """
        message = action_config.get("message", "Test akcji wykonany pomyślnie!")

        # Rozwiąż zmienne szablonowe jeśli są w wiadomości
        resolved_message = self._resolve_template_variables(message, context)

        info(
            f"[TestAction] {resolved_message}",
            message_logger=context.message_logger,
        )

        # Dodatkowe informacje o konfiguracji
        if action_config.get("show_config", False):
            info(
                f"[TestAction] Konfiguracja akcji: {action_config}",
                message_logger=context.message_logger,
            )

        if action_config.get("show_trigger", False) and context.trigger_data:
            info(
                f"[TestAction] Dane triggera: {context.trigger_data}",
                message_logger=context.message_logger,
            )

        return {
            "status": "success",
            "message": resolved_message,
            "scenario": context.scenario_name,
            "config": action_config,
        }


class CustomProcessAction(BaseAction):
    """
    Druga przykładowa akcja w tym samym pliku.

    Pokazuje, że można mieć wiele akcji w jednym pliku.
    """

    # Opcjonalnie można zdefiniować własny typ akcji
    action_type = "custom_process"

    async def execute(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> Any:
        """
        Wykonuje niestandardowe przetwarzanie.

        Args:
            action_config: Konfiguracja akcji z pliku YAML
            context: Kontekst wykonania z danymi Orchestratora

        Returns:
            Wynik przetwarzania
        """
        process_type = action_config.get("process_type", "default")
        data = action_config.get("data", {})

        info(
            f"[CustomProcessAction] Wykonuję przetwarzanie typu: {process_type}",
            message_logger=context.message_logger,
        )

        # Symulacja różnych typów przetwarzania
        if process_type == "count":
            result = len(data) if isinstance(data, (list, dict, str)) else 0
        elif process_type == "sum":
            result = (
                sum(data)
                if isinstance(data, list)
                and all(isinstance(x, (int, float)) for x in data)
                else 0
            )
        else:
            result = f"Processed: {process_type}"

        info(
            f"[CustomProcessAction] Wynik przetwarzania: {result}",
            message_logger=context.message_logger,
        )

        return {
            "process_type": process_type,
            "result": result,
            "input_data": data,
        }
