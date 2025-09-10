"""
Akcja send_sms_to_customer dla scenariuszy orkiestratora.

Wysyła SMS-y do klientów przez MultiInfo Plus API, pobierając numery telefonów
z danych triggera. Wzorowana na send_sms_action, ale numery "to" są pobierane
z listy w trigger_data zamiast być definiowane bezpośrednio w akcji.

Przykład konfiguracji:
{
  "type": "send_sms_to_customer",
  "phone_field": "client_phone_number",
  "text": "Twoje zamówienie nr {{ pickup_number }} jest gotowe (APS ID: {{ aps_id }}).",
  "ignore_errors": false
}

Gdzie phone_field określa nazwę pola zawierającego numer telefonu w rekordach
z trigger_data (domyślnie "client_phone_number" lub "phone").
"""

from __future__ import annotations

from typing import Any, Dict, List

import requests

from avena_commons.util.logger import error, info, warning

from .base_action import ActionContext, ActionExecutionError, BaseAction


class SendSmsToCustomerAction(BaseAction):
    """Wyślij SMS do klientów przez MultiInfo Plus API.

    Pobiera numery telefonów z danych triggera i wysyła wiadomości SMS.
    Wymaga konfiguracji SMS w orchestratorze: url, login, password, serviceId, source.
    """

    action_type = "send_sms_to_customer"

    async def execute(
        self, action_config: Dict[str, Any], context: ActionContext
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

            # 2) Pobierz listę klientów/rekordów z trigger_data
            if not context.trigger_data:
                raise ActionExecutionError(self.action_type, "Brak danych trigger_data")

            # Szukaj listy w trigger_data - może być pod różnymi kluczami
            customer_records = None
            for key in context.trigger_data:
                value = context.trigger_data[key]
                if isinstance(value, list) and value:
                    # Sprawdź czy pierwszy element listy ma strukturę rekordu (dict)
                    if isinstance(value[0], dict):
                        customer_records = value
                        info(
                            f"send_sms_to_customer: znaleziono listę rekordów pod kluczem '{key}' ({len(value)} rekordów)",
                            message_logger=context.message_logger,
                        )
                        break

            if not customer_records:
                raise ActionExecutionError(
                    self.action_type,
                    "Nie znaleziono listy rekordów klientów w trigger_data",
                )

            # 3) Określ pole z numerem telefonu
            phone_field = action_config.get("phone_field")
            if not phone_field:
                # Próbuj znaleźć automatycznie
                sample_record = customer_records[0]
                phone_candidates = [
                    "client_phone_number",  # Standardowe pole w systemie
                    "telefon",
                    "phone",
                    "numer_telefonu",
                    "phone_number",
                    "tel",
                ]
                for candidate in phone_candidates:
                    if candidate in sample_record:
                        phone_field = candidate
                        break

                if not phone_field:
                    raise ActionExecutionError(
                        self.action_type,
                        f"Nie znaleziono pola z numerem telefonu. Sprawdź dostępne pola: {list(sample_record.keys())}",
                    )

            # 4) Pobierz numery telefonów z rekordów
            recipients_with_data = []
            for record in customer_records:
                if isinstance(record, dict) and phone_field in record:
                    phone = str(record[phone_field]).strip()
                    if phone:
                        recipients_with_data.append({"phone": phone, "record": record})

            if not recipients_with_data:
                warning(
                    f"send_sms_to_customer: brak prawidłowych numerów telefonów w polu '{phone_field}'",
                    message_logger=context.message_logger,
                )
                return

            info(
                f"send_sms_to_customer: przygotowano {len(recipients_with_data)} adresatów z pola '{phone_field}'",
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
                phone = recipient_data["phone"]
                record = recipient_data["record"]

                # Zastąp placeholdery w tekście danymi z rekordu klienta
                text = self._resolve_template_variables_with_record(
                    raw_text, context, record
                )

                dest = _normalize_dest(phone)
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
                                f"📱 send_sms_to_customer: Wysłano SMS do {dest} (segment {idx}/{len(segments)}){(' (id: ' + sms_id_info + ')') if sms_id_info else ''}",
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

    def _resolve_template_variables_with_record(
        self, text: str, context: ActionContext, record: Dict[str, Any]
    ) -> str:
        """Rozwiąż zmienne w tekście używając danych z rekordu klienta oraz standardowego kontekstu.

        Args:
            text: Tekst z placeholderami do zastąpienia.
            context: Kontekst akcji z danymi triggera.
            record: Pojedynczy rekord klienta z danymi.

        Returns:
            str: Tekst z zastąpionymi placeholderami.
        """
        # Najpierw użyj standardowej metody z base_action
        resolved_text = self._resolve_template_variables(text, context)

        # Następnie zastąp placeholdery danymi z rekordu klienta
        for key, value in record.items():
            placeholder = f"{{{{ {key} }}}}"
            if placeholder in resolved_text:
                resolved_text = resolved_text.replace(placeholder, str(value))

        return resolved_text
