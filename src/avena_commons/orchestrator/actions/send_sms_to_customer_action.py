"""
Akcja send_sms_to_customer dla scenariuszy orkiestratora.

Wysyła SMS-y do klientów przez MultiInfo Plus API, pobierając numery telefonów
z danych triggera. Wzorowana na send_sms_action, ale numery "to" są pobierane
z listy w context zamiast być definiowane bezpośrednio w akcji.

Przykład konfiguracji:
{
  "type": "send_sms_to_customer",
  "phone_field": "client_phone_number",
  "text": "Twoje zamówienie nr {{ pickup_number }} jest gotowe (APS ID: {{ aps_id }}).",
  "ignore_errors": false
}

Gdzie phone_field określa nazwę pola zawierającego numer telefonu w rekordach
z context (domyślnie "client_phone_number" lub "phone").
"""

from __future__ import annotations

from typing import Any, Dict, List

import requests

from avena_commons.util.logger import debug, error, info, warning

from .base_action import ActionExecutionError, BaseAction, ScenarioContext


class SendSmsToCustomerAction(BaseAction):
    """Wyślij SMS do klientów przez MultiInfo Plus API.

    Pobiera numery telefonów z danych triggera i wysyła wiadomości SMS.
    Wymaga konfiguracji SMS w orchestratorze: url, login, password, serviceId, source.
    """

    action_type = "send_sms_to_customer"

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
                "send_sms_to_customer: SMS globalnie wyłączony (sms.enabled = False) - pomijam",
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
                    f"send_sms_to_customer: pomijam wysyłkę (przekroczony limit kolejnych błędów: {orch.get_action_error_count(self.action_type)}/{max_attempts})",
                    message_logger=context.message_logger,
                )
                return

            success = False
            had_action_error = False

            # 1) Konfiguracja SMS: per-akcja (opcjonalnie) -> globalna orchestrator._configuration['sms']
            sms_cfg = action_config.get("sms", {}) or {}
            if not sms_cfg:
                orch = context.orchestrator
                sms_cfg = (orch._configuration or {}).get("sms", {}) or {}

            enabled = bool(sms_cfg.get("enabled", False))
            if not enabled:
                warning(
                    "send_sms_to_customer: SMS globalnie wyłączony (sms.enabled = False) - pomijam",
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

            customer_records_field = action_config.get("customers")

            customer_records = self._resolve_template_variables(
                customer_records_field, context
            )

            if not customer_records:
                raise ActionExecutionError(
                    self.action_type, "Brak danych klientów w context"
                )

            # 3) Pobierz numery telefonów z rekordów
            recipients_with_data = []
            for i, record in enumerate(customer_records):
                # kds_order_number = customer_records['kds_order_number'] if 'kds_order_number' in customer_records else None
                client_phone_number = (
                    record["client_phone_number"]
                    if "client_phone_number" in record
                    else None
                )
                recipients_with_data.append(client_phone_number)

            if not recipients_with_data:
                warning(
                    f"send_sms_to_customer: brak prawidłowych numerów telefonów w polu 'client_phone_number'",
                    message_logger=context.message_logger,
                )
                return

            info(
                f"send_sms_to_customer: przygotowano {len(recipients_with_data)}, {recipients_with_data} adresatów z pola 'client_phone_number'",
                message_logger=context.message_logger,
            )

            # 5) Treść wiadomości
            raw_text = action_config.get("text") or action_config.get("message")
            if not raw_text:
                raise ActionExecutionError(
                    self.action_type, "Brak pola 'text' (lub 'message')"
                )

            # 6) Konfiguracja długości segmentu
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

            def _normalize_dest(number: str) -> str:
                n = (number or "").strip()
                if n.startswith("+48"):
                    n = n[1:]  # usuń '+' → '48...'
                n = n.replace(" ", "").replace("-", "")
                if not n.startswith("48") and len(n) == 9 and n.isdigit():
                    n = f"48{n}"
                return n

            # 7) Wyślij SMS do każdego klienta
            endpoint = "sendsms.aspx"
            full_url = url_base.rstrip("/") + "/" + endpoint
            ignore_errors = bool(action_config.get("ignore_errors", False))
            all_ok = True
            sent_count = 0

            for recipient_data in recipients_with_data:
                text = self._resolve_template_variables(raw_text, context)

                dest = _normalize_dest(recipient_data)
                segments = _split_text(text, segment_length)

                recipient_ok = True
                for idx, segment in enumerate(segments, start=1):
                    params = {
                        "login": login,
                        "password": password,
                        "serviceId": service_id,
                        "orig": source,
                        "dest": dest,
                        "text": segment,
                    }

                    try:
                        response = requests.get(
                            full_url, params=params, cert=cert_path, timeout=30
                        )

                        # Ocena sukcesu (dostosowana do MultiInfo Plus)
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
                                f"📱 send_sms_to_customer: Wysłano SMS do {dest} (segment {idx}/{len(segments)}){(' (id: ' + sms_id_info + ')') if sms_id_info else ''}. Treść segmentu: {segment}",
                                message_logger=context.message_logger,
                            )
                        else:
                            recipient_ok = False
                            all_ok = False
                            error(
                                f"send_sms_to_customer: niepowodzenie wysyłki do {dest} (segment {idx}/{len(segments)}): {response.status_code} - {response.text}",
                                message_logger=context.message_logger,
                            )

                    except requests.exceptions.Timeout:
                        recipient_ok = False
                        all_ok = False
                        error(
                            f"send_sms_to_customer: timeout żądania do {dest}",
                            message_logger=context.message_logger,
                        )
                    except requests.exceptions.RequestException as e:
                        recipient_ok = False
                        all_ok = False
                        error(
                            f"send_sms_to_customer: błąd HTTP do {dest}: {e}",
                            message_logger=context.message_logger,
                        )
                    except Exception as e:
                        recipient_ok = False
                        all_ok = False
                        error(
                            f"send_sms_to_customer: nieoczekiwany błąd wysyłki do {dest}: {e}",
                            message_logger=context.message_logger,
                        )

                if recipient_ok:
                    sent_count += 1

            info(
                f"send_sms_to_customer: zakończono wysyłkę - pomyślnie wysłano do {sent_count}/{len(recipients_with_data)} adresatów",
                message_logger=context.message_logger,
            )

            if not all_ok and not ignore_errors:
                raise ActionExecutionError(
                    self.action_type,
                    f"Niepowodzenie wysyłki do {len(recipients_with_data) - sent_count} adresatów",
                )

            success = True

        except ActionExecutionError:
            had_action_error = True
            raise
        except Exception as e:
            had_action_error = True
            error(
                f"send_sms_to_customer: nieoczekiwany błąd: {e}",
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
