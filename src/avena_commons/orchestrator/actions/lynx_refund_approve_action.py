"""
Implementacja akcji lynx_refund_approve dla scenariuszy.
Wysyła żądanie approve refund do Nayax Core Lynx API.
"""

from typing import Any, Dict

from avena_commons.util.logger import debug, info

from ..models.scenario_models import ScenarioContext
from .base_action import ActionExecutionError, BaseAction


class LynxRefundApproveAction(BaseAction):
    """
    Akcja wysyłania żądania approve refund do Lynx API.

    Wymaga komponentu Lynx API skonfigurowanego w orchestratorze.

    Obsługuje zmienne szablonowe:
    - type: "lynx_refund_approve"
    - component: "lynx_api"
    - transaction_id: "{{ trigger.transaction_id }}"
    - is_refunded_externally: false
    - refund_document_url: "{{ trigger.refund_document_url }}"
    - machine_au_time: "{{ trigger.machine_au_time }}"

    Dostępne zmienne szablonowe:
    - {{ trigger.transaction_id }} - ID transakcji z triggera
    - {{ trigger.refund_document_url }} - URL dokumentu zwrotu
    - {{ trigger.machine_au_time }} - Czas autoryzacji maszyny
    - {{ trigger.source }} - Źródło triggera
    - {{ error_message }} - Uniwersalny error message (z trigger lub stanu)
    """

    async def execute(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> Dict[str, Any]:
        """
        Wykonuje akcję wysyłania żądania approve refund.

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
                    "lynx_refund_approve",
                    "Brak nazwy komponentu Lynx API (pole: component)",
                )

            component = context.components.get(component_name)
            
            if not component:
                raise ActionExecutionError(
                    "lynx_refund_approve",
                    f"Komponent '{component_name}' nie został znaleziony",
                )

            # Sprawdź czy komponent to Lynx API
            if not hasattr(component, "send_refund_approve_request"):
                raise ActionExecutionError(
                    "lynx_refund_approve",
                    f"Komponent '{component_name}' nie jest komponentem Lynx API",
                )

            # Sprawdź czy transaction_id jest określone
            transaction_id = action_config.get("transaction_id")
            if transaction_id is None:
                raise ActionExecutionError(
                    "lynx_refund_approve", "Brak ID transakcji (pole: transaction_id)"
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
                    "lynx_refund_approve",
                    f"ID transakcji musi być liczbą, otrzymano: {transaction_id}",
                )

            # Pobierz opcjonalne parametry i rozwiąż zmienne szablonowe
            is_refunded_externally = action_config.get("is_refunded_externally", False)
            refund_document_url = action_config.get("refund_document_url", "")
            machine_au_time = action_config.get("machine_au_time")

            # Rozwiąż zmienne szablonowe
            if isinstance(refund_document_url, str):
                refund_document_url = self._resolve_template_variables(
                    refund_document_url, context
                )

            if isinstance(machine_au_time, str) and machine_au_time:
                machine_au_time = self._resolve_template_variables(
                    machine_au_time, context
                )

            # Konwersje typów
            try:
                # is_refunded_externally powinno być boolean
                if isinstance(is_refunded_externally, str):
                    is_refunded_externally = is_refunded_externally.lower() in (
                        "true",
                        "1",
                        "yes",
                        "on",
                    )
                else:
                    is_refunded_externally = bool(is_refunded_externally)
            except (ValueError, TypeError) as e:
                raise ActionExecutionError(
                    "lynx_refund_approve",
                    f"Błąd konwersji parametru is_refunded_externally: {e}",
                )

            debug(
                f"Wysyłanie żądania approve refund do Lynx API - TransactionID: {transaction_id}, "
                f"IsRefundedExternally: {is_refunded_externally}, RefundDocumentUrl: '{refund_document_url}', "
                f"SiteID z komponentu: {component.get_site_id()}",
                message_logger=context.message_logger,
            )

            # Wykonaj żądanie approve refund (site_id jest automatycznie pobierane z komponentu)
            result = await component.send_refund_approve_request(
                transaction_id=transaction_id,
                is_refunded_externally=is_refunded_externally,
                refund_document_url=refund_document_url,
                machine_au_time=machine_au_time,
            )

            if result.get("success"):
                info(
                    f"✅ Żądanie approve refund dla transakcji {transaction_id} wysłane pomyślnie",
                    message_logger=context.message_logger,
                )
            else:
                raise ActionExecutionError(
                    "lynx_refund_approve",
                    f"Żądanie approve refund nie powiodło się: {result.get('error', 'Nieznany błąd')}",
                )

            return result

        except ActionExecutionError:
            # Przepuść dalej błędy ActionExecutionError
            raise

        except Exception as e:
            raise ActionExecutionError(
                "lynx_refund_approve",
                f"Nieoczekiwany błąd podczas wykonywania akcji: {e}",
            )
