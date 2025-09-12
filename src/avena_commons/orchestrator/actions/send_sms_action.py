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

from .base_action import ActionExecutionError, BaseAction
from ..models.scenario_models import ScenarioContext


class SendSmsAction(BaseAction):
    """Wyślij SMS przez MultiInfo Plus API.

    Wymaga co najmniej: url, login, password, serviceId, source.
    Certyfikat TLS (cert_path) może być wymagany przez środowisko bramki.
    """

    action_type = "send_sms"

    async def execute(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> None:
        # Globalny limiter prób: pomiń akcję po przekroczeniu kolejnych błędów
        orch = context.orchestrator
        pre_sms_cfg = action_config.get("sms", {}) or {}
        if not pre_sms_cfg:
            pre_sms_cfg = (orch._configuration or {}).get("sms", {}) or {}

        enabled_pre = bool(pre_sms_cfg.get("enabled", False))
        if not enabled_pre:
            warning(
                "send_sms: SMS globalnie wyłączony (sms.enabled = False) - pomijam",
                message_logger=context.message_logger,
            )
            return

        try:
            try:
                max_attempts = int(pre_sms_cfg.get("max_error_attempts", 0) or 0)
            except Exception:
                max_attempts = 0
            if orch.should_skip_action_due_to_errors(self.action_type, max_attempts):
                warning(
                    f"send_sms: pomijam wysyłkę (przekroczony limit kolejnych błędów: {orch.get_action_error_count(self.action_type)}/{max_attempts})",
                    message_logger=context.message_logger,
                )
                return

            success = False
            had_action_error = False
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
                    if fsm in {"FAULT"}:
                        clients_in_fault.append(client_name)
                clients_in_fault_str = (
                    ", ".join(sorted(clients_in_fault))
                    if clients_in_fault
                    else "(brak)"
                )
                text = text.replace("{{ clients_in_fault }}", clients_in_fault_str)

                # Nowe: {{ clients_error_messages }} - format jak w e-mailu, ale bez details_line
                if "{{ clients_error_messages }}" in text:
                    formatted_entries: List[str] = []
                    try:
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

                                    # Heurystyka: jeśli występuje ", {", odetnij część słownikową, zostaw pierwszą linię
                                    first_line = msg.strip()
                                    if ", {" in msg:
                                        pre, _rest = msg.split(", {", 1)
                                        first_line = pre.strip()

                                    entry_lines = [
                                        f"- {client_name}:",
                                        f"  --> {first_line}",
                                    ]
                                    formatted_entries.append("\n".join(entry_lines))
                            except Exception:
                                continue
                    except Exception:
                        formatted_entries = []

                    clients_error_messages_str = (
                        "\n".join(formatted_entries) if formatted_entries else "(brak)"
                    )
                    text = text.replace(
                        "{{ clients_error_messages }}", clients_error_messages_str
                    )

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

                # Nowe: fallback dla {{ trigger.error_message }} oraz {{ error_message }}
                if "{{ trigger.error_message }}" in text:
                    trig_err = None
                    if (
                        context.trigger_data
                        and context.trigger_data.get("error_message") is not None
                    ):
                        trig_err = str(context.trigger_data["error_message"])
                    else:
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
                    text = text.replace("{{ trigger.error_message }}", trig_err)
            except Exception:
                # Nie przerywaj wysyłki przy problemach z rozszerzeniami placeholderów
                pass

            # 4) Wyślij SMS (GET /sendsms.aspx)
            endpoint = "sendsms.aspx"
            full_url = url_base.rstrip("/") + "/" + endpoint

            # Konfiguracja długości segmentu (domyślnie 160 znaków)
            try:
                segment_length = int(sms_cfg.get("max_length", 160))
            except Exception:
                segment_length = 160

            def _split_text(message: str, max_len: int) -> List[str]:
                if not message:
                    return [""]
                if len(message) <= max_len:
                    return [message]
                segments: List[str] = []
                start = 0
                while start < len(message):
                    end = start + max_len
                    segments.append(message[start:end])
                    start = end
                return segments

            segments = _split_text(text, segment_length)
            ignore_errors = bool(action_config.get("ignore_errors", False))

            def _normalize_dest(number: str) -> str:
                n = (number or "").strip()
                if n.startswith("+48"):
                    n = n[1:]  # usuń '+' → '48...'
                n = n.replace(" ", "").replace("-", "")
                if not n.startswith("48") and len(n) == 9 and n.isdigit():
                    n = f"48{n}"
                return n

            all_ok = True
            for raw_dest in recipients:
                dest = _normalize_dest(raw_dest)
                for idx, segment in enumerate(segments, start=1):
                    params = {
                        "login": login,
                        "password": password,
                        "serviceId": service_id,
                        "orig": source,
                        "dest": dest,
                        "text": segment,
                    }

                    response = requests.get(
                        full_url, params=params, cert=cert_path, timeout=30
                    )

                    # Ocena sukcesu (dostosowana do MultiInfo Plus):
                    #  - "0\n1835172048\n" (pierwszy token to kod 0, następny to smsId)
                    #  - "1835172048" (sam smsId)
                    #  - treść zawiera "OK"
                    ok = False
                    sms_id_info = None
                    if response.status_code == 200:
                        body = (response.text or "").strip()
                        tokens = [t for t in body.replace(";", " ").split() if t]
                        if tokens:
                            first = tokens[0]
                            if first.lstrip("-").isdigit():
                                try:
                                    code_or_id = int(first)
                                    if code_or_id >= 0:
                                        ok = True
                                        if len(tokens) > 1 and tokens[1].isdigit():
                                            sms_id_info = tokens[1]
                                        elif code_or_id > 0:
                                            sms_id_info = str(code_or_id)
                                except ValueError:
                                    ok = False
                            elif "OK" in body.upper():
                                ok = True

                    if ok:
                        info(
                            f"📱 send_sms: Wysłano SMS do {dest} (segment {idx}/{len(segments)}){(' (id: ' + sms_id_info + ')') if sms_id_info else ''}. Treść segmentu: {segment}",
                            message_logger=context.message_logger,
                        )
                    else:
                        all_ok = False
                        error(
                            f"send_sms: niepowodzenie wysyłki do {dest} (segment {idx}/{len(segments)}): {response.status_code} - {response.text}.",
                            message_logger=context.message_logger,
                        )

            if not all_ok and not ignore_errors:
                raise ActionExecutionError(
                    self.action_type, "Co najmniej jedna wysyłka SMS nie powiodła się"
                )
            success = True

        except ActionExecutionError:
            had_action_error = True
            raise
        except requests.exceptions.Timeout:
            had_action_error = True
            error(
                "send_sms: timeout żądania do bramki SMS",
                message_logger=context.message_logger,
            )
            raise ActionExecutionError(
                self.action_type, "Timeout żądania do bramki SMS"
            )
        except requests.exceptions.RequestException as e:
            had_action_error = True
            error(
                f"send_sms: błąd żądania HTTP: {e}",
                message_logger=context.message_logger,
            )
            raise ActionExecutionError(self.action_type, f"Błąd żądania HTTP: {e}", e)
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
                    orch.reset_action_error_count(self.action_type)
                elif had_action_error:
                    orch.increment_action_error_count(self.action_type)
            except Exception:
                # Licznik błędów nie może przerwać dalszego działania
                pass
