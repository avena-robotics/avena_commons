"""
Implementacja akcji lynx_refund dla scenariuszy.
Wysyła żądanie refund do Nayax Core Lynx API.
"""

from typing import Any, Dict

from avena_commons.util.logger import debug, info

from .base_action import ActionExecutionError, BaseAction, ScenarioContext


class LynxRefundAction(BaseAction):
    """
    Akcja wysyłania żądania refund do Lynx API.

    Wymaga komponentu Lynx API skonfigurowanego w orchestratorze.

    Obsługuje zmienne szablonowe:
    - type: "lynx_refund"
    - component: "lynx_api"
    - transaction_id: "{{ context.result_key.transaction_id }}"
    - refund_reason: "Auto refund - {{ context.error_message }}"
    - refund_email_list: "{{ context.admin_email }}"

    Dostępne zmienne szablonowe:
    - {{ context.transaction_id }} - ID transakcji z triggera
    - {{ context.error_message }} - Wiadomość błędu z triggera
    - {{ context.source }} - Źródło triggera
    - {{ error_message }} - Uniwersalny error message (z trigger lub stanu)
    """

    async def execute(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> Dict[str, Any]:
        """
        Wykonuje akcję wysyłania żądania refund.

        Args:
            action_config: Konfiguracja akcji
            context: Kontekst wykonania

        Returns:
            Wynik wykonania akcji z API

        Raises:
            ActionExecutionError: W przypadku błędu wykonania
        """
        try:
            # Sprawdź czy podano komponent
            component_name = action_config.get("component")
            if not component_name:
                raise ActionExecutionError(
                    "lynx_refund", "Brak nazwy komponentu Lynx API (pole: component)"
                )

            # Pobierz komponent z orchestratora
            if not hasattr(context.orchestrator, "_components"):
                raise ActionExecutionError(
                    "lynx_refund", "Orchestrator nie ma zdefiniowanych komponentów"
                )

            if not component_name in context.components:
                raise ActionExecutionError(
                    "lynx_refund", f"Komponent '{component_name}' nie został znaleziony"
                )
                
            lynx_component = context.components[component_name]

            # Sprawdź czy komponent to Lynx API
            if not hasattr(lynx_component, "send_refund_request"):
                raise ActionExecutionError(
                    "lynx_refund",
                    f"Komponent '{component_name}' nie jest komponentem Lynx API",
                )

            # Sprawdź czy transaction_id jest określone
            transaction_id = action_config.get("transaction_id")
            if transaction_id is None:
                raise ActionExecutionError(
                    "lynx_refund", "Brak ID transakcji (pole: transaction_id)"
                )

            # Rozwiąż zmienne szablonowe dla transaction_id
            if isinstance(transaction_id, str):
                transaction_id = self._resolve_template_variables(
                    transaction_id, context
                )

            # Spróbuj przekonwertować na int
            try:
                transaction_id = int(transaction_id)
            except (ValueError, TypeError):
                raise ActionExecutionError(
                    "lynx_refund",
                    f"ID transakcji musi być liczbą, otrzymano: {transaction_id}",
                )

            # Pobierz opcjonalne parametry i rozwiąż zmienne szablonowe
            refund_amount = action_config.get("refund_amount", 0)
            refund_email_list = action_config.get("refund_email_list", "")
            refund_reason = action_config.get("refund_reason", "")

            # Rozwiąż zmienne szablonowe
            if isinstance(refund_email_list, str):
                refund_email_list = self._resolve_template_variables(
                    refund_email_list, context
                )

            if isinstance(refund_reason, str):
                refund_reason = self._resolve_template_variables(refund_reason, context)

            # Konwersje typów
            try:
                refund_amount = float(refund_amount) if refund_amount is not None else 0
            except (ValueError, TypeError) as e:
                raise ActionExecutionError(
                    "lynx_refund", f"Błąd konwersji parametrów liczbowych: {e}"
                )

            debug(
                f"Wysyłanie żądania refund do Lynx API - TransactionID: {transaction_id}, "
                f"Amount: {refund_amount}, Reason: '{refund_reason}', SiteID z komponentu: {lynx_component.get_site_id()}",
                message_logger=context.message_logger,
            )

            # Wykonaj żądanie refund (site_id jest automatycznie pobierane z komponentu)
            result = await lynx_component.send_refund_request(
                transaction_id=transaction_id,
                refund_amount=refund_amount,
                refund_email_list=refund_email_list,
                refund_reason=refund_reason,
            )

            if result.get("success"):
                info(
                    f"✅ Żądanie refund dla transakcji {transaction_id} wysłane pomyślnie",
                    message_logger=context.message_logger,
                )
            else:
                raise ActionExecutionError(
                    "lynx_refund",
                    f"Żądanie refund nie powiodło się: {result.get('error', 'Nieznany błąd')}",
                )

            return result

        except ActionExecutionError:
            # Przepuść dalej błędy ActionExecutionError
            raise

        except Exception as e:
            raise ActionExecutionError(
                "lynx_refund", f"Nieoczekiwany błąd podczas wykonywania akcji: {e}"
            )
