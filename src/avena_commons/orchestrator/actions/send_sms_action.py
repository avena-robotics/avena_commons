"""
Akcja send_sms dla scenariuszy orkiestratora.

Wysyła SMS-y przez MultiInfo Plus API (Api61), wzorowane na implementacji w aps_kiosk.
Parametry bramki SMS są konfigurowane globalnie w konfiguracji Orchestratora
(orchestrator._configuration['sms']) i mogą opcjonalnie zostać nadpisane lokalnie
w akcji (pole "sms"). Pola "to" i "text" są wymagane na poziomie akcji.

Przykład użycia w JSON scenariusza:
{
  "type": "send_sms",
  "to": ["+48123123123", "+48555111222"],
  "text": "BŁĄD w {{ trigger.source }}. Status: {{ clients_in_fault }}"
}
"""

from __future__ import annotations

from typing import Any, Dict, List

from avena_commons.util.logger import error, warning

from .base_action import ActionExecutionError, BaseAction, ScenarioContext


class SendSmsAction(BaseAction):
    """Wyślij SMS przez MultiInfo Plus API.

    Wymaga co najmniej: url, login, password, serviceId, source.
    Certyfikat TLS (cert_path) może być wymagany przez środowisko bramki.
    """

    action_type = "send_sms"

    async def execute(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> None:
        # Inicjalizuj placeholdery dla tej akcji
        self._initialize_placeholders(context)

        # Pobierz komponent SMS z kontekstu
        sms_component = None
        for comp_name, comp in context.components.items():
            if hasattr(comp, "__class__") and comp.__class__.__name__ == "SmsComponent":
                sms_component = comp
                break

        if not sms_component:
            raise ActionExecutionError(
                "send_sms", "Brak komponentu SmsComponent w kontekście"
            )

        if not sms_component.is_initialized:
            raise ActionExecutionError(
                "send_sms", "Komponent SmsComponent nie jest zainicjalizowany"
            )

        if not sms_component.is_enabled:
            warning(
                "send_sms: SMS globalnie wyłączony - pomijam",
                message_logger=context.message_logger,
            )
            return

        orch = context.orchestrator
        success = False
        had_action_error = False

        try:
            max_attempts = sms_component.max_error_attempts
            if self.should_skip_action_due_to_errors(self.action_type, max_attempts):
                warning(
                    f"send_sms: pomijam wysyłkę (przekroczony limit kolejnych błędów: {self.get_action_error_count(self.action_type)}/{max_attempts})",
                    message_logger=context.message_logger,
                )
                return

            # Odbiorcy: parsowanie podobnie jak w komponencie
            to_field = action_config.get("to")
            if not to_field:
                raise ActionExecutionError(
                    self.action_type, "Brak pola 'to' (lista lub string)"
                )

            recipients: List[str]
            if isinstance(to_field, list):
                recipients = [str(a).strip() for a in to_field if str(a).strip()]
            else:
                recipients = [str(to_field).strip()]
            if not recipients:
                raise ActionExecutionError(
                    self.action_type, "Lista adresatów 'to' jest pusta"
                )

            # Treść wiadomości
            raw_text = action_config.get("text") or action_config.get("message")
            if not raw_text:
                raise ActionExecutionError(
                    self.action_type, "Brak pola 'text' (lub 'message')"
                )

            # Szablony zmiennych (i gotowe placeholdery z kontekstu)
            text = self._resolve_template_variables(raw_text, context)

            # Wysyłka SMS przez komponent
            ignore_errors = bool(action_config.get("ignore_errors", False))
            all_ok, sent_count, errors = await sms_component.send_sms(
                recipients, text, ignore_errors
            )

            if not all_ok and not ignore_errors:
                raise ActionExecutionError(
                    self.action_type, "Co najmniej jedna wysyłka SMS nie powiodła się"
                )
            success = True

        except ActionExecutionError:
            had_action_error = True
            raise
        except Exception as e:
            had_action_error = True
            error(
                f"send_sms: nieoczekiwany błąd: {e}",
                message_logger=context.message_logger,
            )
            raise ActionExecutionError(self.action_type, f"Nieoczekiwany błąd: {e}", e)
        finally:
            try:
                if success:
                    self.reset_action_error_count(self.action_type)
                elif had_action_error:
                    self.increment_action_error_count(self.action_type)
            except Exception:
                # Licznik błędów nie może przerwać dalszego działania
                pass
