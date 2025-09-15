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

from typing import Any, Dict, List

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

            # Szablony (trigger.*)
            subject = self._resolve_template_variables(raw_subject, context)
            body = self._resolve_template_variables(raw_body, context)

            # Dodatkowe placeholdery specyficzne dla tej akcji (stan orchestratora)
            try:
                orch = context.orchestrator
                clients_in_fault = []
                for client_name, st in orch._state.items():
                    fsm = st.get("fsm_state")
                    if fsm in {"FAULT"}:
                        clients_in_fault.append(client_name)
                clients_in_fault_str = (
                    ", ".join(sorted(clients_in_fault))
                    if clients_in_fault
                    else "(brak)"
                )
                # Proste podstawienie, jeżeli występuje w treści/temacie
                subject = subject.replace(
                    "{{ clients_in_fault }}", clients_in_fault_str
                )
                body = body.replace("{{ clients_in_fault }}", clients_in_fault_str)

                # Nowe: {{ clients_error_messages }} - zbuduj listę klientów z błędami i ich komunikaty
                if (
                    "{{ clients_error_messages }}" in subject
                    or "{{ clients_error_messages }}" in body
                ):
                    formatted_entries: List[str] = []
                    try:
                        # deterministyczna kolejność według nazwy klienta
                        for client_name, st in sorted(
                            orch._state.items(), key=lambda x: x[0]
                        ):
                            try:
                                if (
                                    st.get("error")
                                    and st.get("error_message") is not None
                                ):
                                    raw_msg = st.get("error_message")
                                    if isinstance(raw_msg, (list, tuple)):
                                        raw_msg = ", ".join(str(m) for m in raw_msg)
                                    msg = str(raw_msg)

                                    # Podziel komunikat na część opisową i szczegóły słownika (jeśli występują)
                                    first_line = msg.strip()
                                    details_line = None
                                    if ", {" in msg:
                                        pre, rest = msg.split(", {", 1)
                                        first_line = pre.strip()
                                        details_line = "{" + rest.strip()

                                    entry_lines = [
                                        f"- {client_name}:",
                                        f"  --> {first_line}",
                                    ]
                                    if details_line:
                                        # Sformatuj szczegóły słownika do: key: value => key: value
                                        def _format_details_line(details: str) -> str:
                                            s = (details or "").strip()
                                            if s.startswith("{") and s.endswith("}"):
                                                s = s[1:-1]
                                            parts: List[str] = []
                                            for chunk in s.split(","):
                                                if ":" not in chunk:
                                                    continue
                                                key, val = chunk.split(":", 1)
                                                key = key.strip().strip("'\"")
                                                val = val.strip().strip("'\"")
                                                parts.append(f"{key}: {val}")
                                            return (
                                                " => ".join(parts) if parts else details
                                            )

                                        formatted_details = _format_details_line(
                                            details_line
                                        )
                                        entry_lines.append(f"      {formatted_details}")

                                    formatted_entries.append("\n".join(entry_lines))
                            except Exception:
                                continue
                    except Exception:
                        formatted_entries = []

                    clients_error_messages_str = (
                        "\n".join(formatted_entries) if formatted_entries else "(brak)"
                    )
                    subject = subject.replace(
                        "{{ clients_error_messages }}", clients_error_messages_str
                    )
                    body = body.replace(
                        "{{ clients_error_messages }}", clients_error_messages_str
                    )

                # Fallback dla {{ trigger.source }} jeśli brak w trigger_data
                if "{{ trigger.source }}" in subject or "{{ trigger.source }}" in body:
                    trigger_source = None
                    if context.trigger_data and context.trigger_data.get("source"):
                        trigger_source = str(context.trigger_data["source"])
                    else:
                        trigger_source = (
                            ", ".join(sorted(clients_in_fault))
                            if clients_in_fault
                            else "autonomous"
                        )
                    subject = subject.replace("{{ trigger.source }}", trigger_source)
                    body = body.replace("{{ trigger.source }}", trigger_source)

                # Nowe: fallback dla {{ trigger.error_message }} jeśli nie podano w trigger_data
                if (
                    "{{ trigger.error_message }}" in subject
                    or "{{ trigger.error_message }}" in body
                ):
                    trig_err = None
                    if (
                        context.trigger_data
                        and context.trigger_data.get("error_message") is not None
                    ):
                        trig_err = str(context.trigger_data["error_message"])
                    else:
                        # Spróbuj zebrać z orchestrator._state
                        clients_with_errors = []
                        for client_name, st in orch._state.items():
                            try:
                                if (
                                    st.get("error")
                                    and st.get("error_message") is not None
                                ):
                                    msg = st.get("error_message")
                                    if isinstance(msg, (list, tuple)):
                                        msg = ", ".join(str(m) for m in msg)
                                    clients_with_errors.append(f"{client_name}: {msg}")
                            except Exception:
                                continue
                        trig_err = (
                            "; ".join(sorted(clients_with_errors))
                            if clients_with_errors
                            else "(brak)"
                        )
                    subject = subject.replace("{{ trigger.error_message }}", trig_err)
                    body = body.replace("{{ trigger.error_message }}", trig_err)
            except Exception:
                # Ciche pominięcie - e-mail i tak zostanie wysłany bez rozszerzeń
                pass

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
