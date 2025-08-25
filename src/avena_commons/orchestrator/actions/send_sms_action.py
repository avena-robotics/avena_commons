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

import requests

from avena_commons.util.logger import error, info, warning

from .base_action import ActionContext, ActionExecutionError, BaseAction


class SendSmsAction(BaseAction):
    """Wyślij SMS przez MultiInfo Plus API.

    Wymaga co najmniej: url, login, password, serviceId, source.
    Certyfikat TLS (cert_path) może być wymagany przez środowisko bramki.
    """

    action_type = "send_sms"

    async def execute(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> None:
        try:
            # 1) Konfiguracja: per-akcja (opcjonalnie) -> globalna orchestrator._configuration['sms']
            sms_cfg = action_config.get("sms", {}) or {}
            if not sms_cfg:
                orch = context.orchestrator
                sms_cfg = (orch._configuration or {}).get("sms", {}) or {}

            enabled = bool(sms_cfg.get("enabled", False))
            if not enabled:
                warning(
                    "send_sms: SMS globalnie wyłączony (sms.enabled = False) - pomijam",
                    message_logger=context.message_logger,
                )
                return

            url_base = (sms_cfg.get("url") or "").strip()
            login = (sms_cfg.get("login") or "").strip()
            password = (sms_cfg.get("password") or "").strip()
            service_id = sms_cfg.get("serviceId")
            source = (sms_cfg.get("source") or "").strip()
            cert_path = (sms_cfg.get("cert_path") or "").strip() or None

            if not url_base:
                raise ActionExecutionError(
                    self.action_type, "Brak sms.url w konfiguracji"
                )
            if not login:
                raise ActionExecutionError(
                    self.action_type, "Brak sms.login w konfiguracji"
                )
            if not password:
                raise ActionExecutionError(
                    self.action_type, "Brak sms.password w konfiguracji"
                )
            if not service_id:
                raise ActionExecutionError(
                    self.action_type, "Brak sms.serviceId w konfiguracji"
                )
            if not source:
                raise ActionExecutionError(
                    self.action_type, "Brak sms.source w konfiguracji"
                )

            # 2) Odbiorcy i treść
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

            raw_text = action_config.get("text") or action_config.get("message")
            if not raw_text:
                raise ActionExecutionError(
                    self.action_type, "Brak pola 'text' (lub 'message')"
                )

            # 3) Szablony zmiennych
            text = self._resolve_template_variables(raw_text, context)

            # Dodatkowy placeholder: {{ clients_in_fault }}
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
                text = text.replace("{{ clients_in_fault }}", clients_in_fault_str)

                if "{{ trigger.source }}" in text:
                    trigger_source = None
                    if context.trigger_data and context.trigger_data.get("source"):
                        trigger_source = str(context.trigger_data["source"])
                    else:
                        trigger_source = (
                            ", ".join(sorted(clients_in_fault))
                            if clients_in_fault
                            else "autonomous"
                        )
                    text = text.replace("{{ trigger.source }}", trigger_source)
            except Exception:
                # Nie przerywaj wysyłki przy problemach z rozszerzeniami placeholderów
                pass

            # 4) Wyślij SMS (GET /sendsms.aspx)
            endpoint = "sendsms.aspx"
            full_url = url_base.rstrip("/") + "/" + endpoint

            all_ok = True
            for dest in recipients:
                params = {
                    "login": login,
                    "password": password,
                    "serviceId": service_id,
                    "orig": source,
                    "dest": dest,
                    "text": text,
                }

                response = requests.get(
                    full_url, params=params, cert=cert_path, timeout=30
                )

                # Prosty model oceny sukcesu (zgodny ze schematem z aps_kiosk)
                ok = False
                if response.status_code == 200:
                    body = (response.text or "").strip()
                    parts = [p.strip() for p in body.split(";") if p.strip()]
                    if parts and (parts[0].isdigit() or "OK" in body.upper()):
                        ok = True

                if ok:
                    info(
                        f"📱 send_sms: Wysłano SMS do {dest}",
                        message_logger=context.message_logger,
                    )
                else:
                    all_ok = False
                    error(
                        f"send_sms: niepowodzenie wysyłki do {dest}: {response.status_code} - {response.text}",
                        message_logger=context.message_logger,
                    )

            if not all_ok:
                raise ActionExecutionError(
                    self.action_type, "Co najmniej jedna wysyłka SMS nie powiodła się"
                )

        except ActionExecutionError:
            raise
        except requests.exceptions.Timeout:
            error(
                "send_sms: timeout żądania do bramki SMS",
                message_logger=context.message_logger,
            )
            raise ActionExecutionError(
                self.action_type, "Timeout żądania do bramki SMS"
            )
        except requests.exceptions.RequestException as e:
            error(
                f"send_sms: błąd żądania HTTP: {e}",
                message_logger=context.message_logger,
            )
            raise ActionExecutionError(self.action_type, f"Błąd żądania HTTP: {e}", e)
        except Exception as e:
            error(
                f"send_sms: nieoczekiwany błąd: {e}",
                message_logger=context.message_logger,
            )
            raise ActionExecutionError(self.action_type, f"Nieoczekiwany błąd: {e}", e)
