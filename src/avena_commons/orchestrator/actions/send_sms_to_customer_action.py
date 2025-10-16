"""Akcja wysyłania SMS do klientów przez komponent SmsComponent.

AI: Implementuje akcję send_sms_to_customer używając SmsComponent zamiast bezpośredniej konfiguracji SMS.
Pobiera numery telefonów z danych triggera i wysyła wiadomości SMS.
"""

from __future__ import annotations

from typing import Any, Dict, List

from avena_commons.util.logger import error, warning

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
        # Pobierz komponent SMS z kontekstu
        sms_component = None
        for comp_name, comp in context.components.items():
            if hasattr(comp, "__class__") and comp.__class__.__name__ == "SmsComponent":
                sms_component = comp
                break

        if not sms_component:
            raise ActionExecutionError(
                "send_sms_to_customer", "Brak komponentu SmsComponent w kontekście"
            )

        if not sms_component.is_initialized:
            raise ActionExecutionError(
                "send_sms_to_customer",
                "Komponent SmsComponent nie jest zainicjalizowany",
            )

        if not sms_component.is_enabled:
            warning(
                "send_sms_to_customer: SMS globalnie wyłączony - pomijam",
                message_logger=context.message_logger,
            )
            return

        success = False
        had_action_error = False

        try:
            max_attempts = sms_component.max_error_attempts
            if self.should_skip_action_due_to_errors(self.action_type, max_attempts):
                warning(
                    f"send_sms_to_customer: pomijam wysyłkę (przekroczony limit kolejnych błędów: {self.get_action_error_count(self.action_type)}/{max_attempts})",
                    message_logger=context.message_logger,
                )
                return

            # Pobierz dane klientów z konfiguracji akcji
            customer_records_field = action_config.get("customers")
            if customer_records_field:
                customer_records = self._resolve_template_variables(
                    customer_records_field, context
                )
            else:
                # Pobierz dane z kontekstu dla numerów telefonów
                context_data = context.context or {}
                phone_field = action_config.get("phone_field", "client_phone_number")

                # Alternatywne nazwy pól
                alt_phone_fields = [
                    "phone",
                    "phone_number",
                    "client_phone",
                    "customer_phone",
                ]
                if phone_field not in alt_phone_fields:
                    alt_phone_fields.insert(0, phone_field)

                recipients: List[str] = []

                # Jeśli context_data to lista obiektów/rekordów
                if isinstance(context_data, list):
                    for record in context_data:
                        if isinstance(record, dict):
                            phone = None
                            for field in alt_phone_fields:
                                if field in record and record[field]:
                                    phone = str(record[field]).strip()
                                    break
                            if phone:
                                recipients.append(phone)

                # Jeśli context_data to słownik z polem zawierającym listę numerów
                elif isinstance(context_data, dict):
                    for field in alt_phone_fields:
                        if field in context_data:
                            field_value = context_data[field]
                            if isinstance(field_value, list):
                                for phone in field_value:
                                    if phone:
                                        recipients.append(str(phone).strip())
                            elif field_value:
                                recipients.append(str(field_value).strip())
                            break

                if not recipients:
                    warning(
                        f"send_sms_to_customer: brak numerów telefonów w context_data (szukane pola: {alt_phone_fields})",
                        message_logger=context.message_logger,
                    )
                    return

                # Użyj prostej listy numerów
                customer_records = recipients

            if not customer_records:
                raise ActionExecutionError(
                    self.action_type, "Brak danych klientów w context"
                )

            # Przygotuj listę numerów telefonów
            recipients_phone_numbers = []

            # Jeśli customer_records to lista rekordów (z polem client_phone_number)
            if (
                isinstance(customer_records, list)
                and customer_records
                and isinstance(customer_records[0], dict)
            ):
                for record in customer_records:
                    phone = record.get("client_phone_number")
                    if phone:
                        recipients_phone_numbers.append(str(phone).strip())

            # Jeśli customer_records to już lista numerów telefonów
            elif isinstance(customer_records, list):
                recipients_phone_numbers = [
                    str(phone).strip() for phone in customer_records if phone
                ]

            if not recipients_phone_numbers:
                warning(
                    f"send_sms_to_customer: brak prawidłowych numerów telefonów",
                    message_logger=context.message_logger,
                )
                return

            # Treść wiadomości
            raw_text = action_config.get("text") or action_config.get("message")
            if not raw_text:
                raise ActionExecutionError(
                    self.action_type, "Brak pola 'text' (lub 'message')"
                )

            # Szablony zmiennych
            text = self._resolve_template_variables(raw_text, context)

            # Wysyłka SMS przez komponent
            ignore_errors = bool(action_config.get("ignore_errors", False))
            all_ok, sent_count, errors = await sms_component.send_sms(
                recipients_phone_numbers, text, ignore_errors
            )

            if not all_ok and not ignore_errors:
                raise ActionExecutionError(
                    self.action_type,
                    "Co najmniej jedna wysyłka SMS do klienta nie powiodła się",
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
                    self.reset_action_error_count(self.action_type)
                elif had_action_error:
                    self.increment_action_error_count(self.action_type)
            except Exception:
                # Licznik błędów nie może przerwać dalszego działania
                pass
