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

import smtplib
from email.message import EmailMessage
from typing import Any, Dict, List

from avena_commons.util.logger import error, info, warning

from .base_action import ActionContext, ActionExecutionError, BaseAction


class SendEmailAction(BaseAction):
    action_type = "send_email"

    async def execute(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> None:
        """
        Wysyła wiadomość e-mail na podstawie konfiguracji akcji i kontekstu.

        Args:
            action_config (Dict[str, Any]): Konfiguracja z polami:
                - to (str|List[str]): Adres(y) odbiorców.
                - subject (str): Temat wiadomości (wspiera {{ }} szablony).
                - body (str): Treść wiadomości (wspiera {{ }} szablony).
                - smtp (Dict[str, Any]): Konfiguracja SMTP (opcjonalnie, nadpisuje globalną).
            context (ActionContext): Kontekst wykonania z dostępem do orchestratora i triggera.

        Raises:
            ActionExecutionError: W przypadku braków konfiguracji lub błędu wysyłki.

        """
        orch = context.orchestrator
        pre_smtp_cfg = action_config.get("smtp", {}) or {}
        if not pre_smtp_cfg:
            pre_smtp_cfg = (orch._configuration or {}).get("smtp", {}) or {}
        try:
            try:
                max_attempts = int(pre_smtp_cfg.get("max_error_attempts", 0) or 0)
            except Exception:
                max_attempts = 0
            if orch.should_skip_action_due_to_errors(self.action_type, max_attempts):
                warning(
                    f"send_email: pomijam wysyłkę (przekroczony limit kolejnych błędów: {orch.get_action_error_count(self.action_type)}/{max_attempts})",
                    message_logger=context.message_logger,
                )
                return

            success = False
            had_action_error = False
            # Priorytet: per-akcja (legacy) -> globalny orchestrator._configuration['smtp']
            smtp_cfg = action_config.get("smtp", {}) or {}
            if not smtp_cfg:
                orch = context.orchestrator
                smtp_cfg = (orch._configuration or {}).get("smtp", {}) or {}

            host = smtp_cfg.get("host")
            port = int(smtp_cfg.get("port", 587))
            username = smtp_cfg.get("username")
            password = smtp_cfg.get("password")
            use_starttls = bool(smtp_cfg.get("starttls", True))
            use_tls = bool(smtp_cfg.get("tls", False))  # alternatywa dla portu 465
            mail_from = smtp_cfg.get("from") or username

            if not host:
                raise ActionExecutionError(
                    "send_email", "Brak smtp.host w konfiguracji (globalnej lub akcji)"
                )
            if not mail_from:
                raise ActionExecutionError(
                    "send_email",
                    "Brak smtp.from (lub username) w konfiguracji (globalnej lub akcji)",
                )

            # Odbiorcy: dopuszczamy string lub listę
            to_field = action_config.get("to")
            if not to_field:
                raise ActionExecutionError(
                    "send_email", "Brak pola to (lista adresów lub string)"
                )
            to_addresses: List[str]
            if isinstance(to_field, list):
                to_addresses = [str(a).strip() for a in to_field if str(a).strip()]
            else:
                to_addresses = [str(to_field).strip()]
            if not to_addresses:
                raise ActionExecutionError(
                    "send_email", "Lista adresów to jest pusta po przetworzeniu"
                )

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
                    if fsm in {"ON_FAULT", "FAULT"}:
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
                    clients_with_errors = []
                    try:
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
                    except Exception:
                        clients_with_errors = []
                    clients_error_messages_str = (
                        "; ".join(sorted(clients_with_errors))
                        if clients_with_errors
                        else "(brak)"
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

            # Zbuduj wiadomość
            message = EmailMessage()
            message["From"] = mail_from
            message["To"] = ", ".join(to_addresses)
            message["Subject"] = subject
            message.set_content(body)

            # Połączenie SMTP
            if use_tls:
                # SMTPS (implicit TLS), zwykle port 465
                with smtplib.SMTP_SSL(host=host, port=port) as smtp:
                    smtp.ehlo()
                    if username and password and smtp.has_extn("auth"):
                        smtp.login(username, password)
                    elif username and password:
                        warning(
                            "send_email: Serwer nie wspiera AUTH - pomijam logowanie",
                            message_logger=context.message_logger,
                        )
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(host=host, port=port) as smtp:
                    smtp.ehlo()
                    if use_starttls:
                        smtp.starttls()
                        smtp.ehlo()
                    if username and password and smtp.has_extn("auth"):
                        smtp.login(username, password)
                    elif username and password:
                        warning(
                            "send_email: Serwer nie wspiera AUTH - pomijam logowanie",
                            message_logger=context.message_logger,
                        )
                    smtp.send_message(message)

            info(
                f"📧 send_email: Wysłano e-mail do {to_addresses} z tematem '{subject}'",
                message_logger=context.message_logger,
            )
            success = True

        except ActionExecutionError:
            had_action_error = True
            raise
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
                    orch.reset_action_error_count(self.action_type)
                elif had_action_error:
                    orch.increment_action_error_count(self.action_type)
            except Exception:
                pass
