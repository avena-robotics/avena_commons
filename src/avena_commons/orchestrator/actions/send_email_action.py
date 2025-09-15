"""
Implementacja akcji send_email dla scenariuszy.

Pozwala wysyłać wiadomości e-mail via SMTP. Wspiera podstawowe
uwierzytelnianie i TLS/STARTTLS. Pola `subject` i `body` wspierają
proste zmienne szablonowe via BaseAction._resolve_template_variables.

Przykład użycia w JSON scenariusza:
{
  "type": "send_email",
  "to": ["ops@example.com"],
  "subject": "BŁĄD w {{ trigger.source }}",
  "body": "Komponent {{ trigger.source }} zgłosił FAULT (kod: {{ trigger.payload.error_code }})",
  "smtp": {
    "host": "smtp.example.com",
    "port": 587,
    "username": "user",
    "password": "pass",
    "starttls": true,
    "from": "orchestrator@example.com"
  }
}
"""

from typing import Any, Dict

from avena_commons.util.logger import error, warning

from .base_action import ActionExecutionError, BaseAction, ScenarioContext


class SendEmailAction(BaseAction):
    action_type = "send_email"

    async def execute(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> None:
        """
        Wysyła wiadomość e-mail na podstawie konfiguracji akcji i kontekstu.

        Args:
            action_config (Dict[str, Any]): Konfiguracja z polami:
                - to (str|List[str]): Adres(y) odbiorców.
                - subject (str): Temat wiadomości (wspiera {{ }} szablony).
                - body (str): Treść wiadomości (wspiera {{ }} szablony).
                - smtp (Dict[str, Any]): Konfiguracja SMTP (opcjonalnie, nadpisuje globalną).
            context (ScenarioContext): Kontekst wykonania z dostępem do orchestratora i triggera.

        Raises:
            ActionExecutionError: W przypadku braków konfiguracji lub błędu wysyłki.

        """
        # Inicjalizuj placeholdery dla tej akcji
        self._initialize_placeholders(context)

        orch = context.orchestrator

        # Pobierz komponent email z kontekstu
        email_component = None
        for comp_name, comp in context.components.items():
            if (
                hasattr(comp, "__class__")
                and comp.__class__.__name__ == "EmailComponent"
            ):
                email_component = comp
                break

        if not email_component:
            raise ActionExecutionError(
                "send_email", "Brak komponentu EmailComponent w kontekście"
            )

        if not email_component.is_initialized:
            raise ActionExecutionError(
                "send_email", "Komponent EmailComponent nie jest zainicjalizowany"
            )

        if not email_component.is_enabled:
            warning(
                "send_email: Email globalnie wyłączony - pomijam",
                message_logger=context.message_logger,
            )
            return

        try:
            max_attempts = email_component.max_error_attempts
            if self.should_skip_action_due_to_errors(self.action_type, max_attempts):
                warning(
                    f"send_email: pomijam wysyłkę (przekroczony limit kolejnych błędów: {self.get_action_error_count(self.action_type)}/{max_attempts})",
                    message_logger=context.message_logger,
                )
                return

            success = False
            had_action_error = False

            # Odbiorcy: używamy metody z komponentu
            to_field = action_config.get("to")
            try:
                to_addresses = email_component.parse_recipients(to_field)
            except ValueError as e:
                raise ActionExecutionError("send_email", str(e))

            raw_subject = action_config.get("subject", "")
            raw_body = action_config.get("body", "")
            if not raw_subject:
                raise ActionExecutionError("send_email", "Brak subject")
            if not raw_body:
                raise ActionExecutionError("send_email", "Brak body")

            # Szablony (i gotowe placeholdery z kontekstu)
            subject = self._resolve_template_variables(raw_subject, context)
            body = self._resolve_template_variables(raw_body, context)

            # Wysyłka e-maila przez komponent
            try:
                await email_component.send_email(to_addresses, subject, body)
                success = True
            except Exception as e:
                had_action_error = True
                error(
                    f"send_email: błąd wysyłki e-mail: {e}",
                    message_logger=context.message_logger,
                )
                raise ActionExecutionError("send_email", f"Błąd wysyłki e-mail: {e}", e)
        finally:
            try:
                if success:
                    self.reset_action_error_count(self.action_type)
                elif had_action_error:
                    self.increment_action_error_count(self.action_type)
            except Exception:
                pass
