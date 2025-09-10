"""
Komponent Lynx API dla orchestratora.

Obsługuje połączenia z serwisem Nayax Core Lynx API
i udostępnia interfejs do wysyłania żądań refund.
"""

import os
from datetime import datetime
from typing import Any, Dict, Optional

import requests

from avena_commons.util.logger import debug, error, info


class LynxAPIComponent:
    """
    Komponent do obsługi komunikacji z Nayax Core Lynx API.

    Inicjalizowany przez orchestrator przy starcie i udostępniany akcjom.

    Wymagane parametry w konfiguracji lub zmiennych środowiskowych:
    - ACCESS_TOKEN: Token dostępu do API

    Opcjonalne parametry:
    - SITE_ID: Identyfikator miejsca/situ (domyślnie 0)
    """

    def __init__(self, name: str, config: Dict[str, Any], message_logger=None):
        """
        Inicjalizuje komponent Lynx API.

        Args:
            name: Nazwa komponentu
            config: Konfiguracja komponentu z orchestratora
            message_logger: Logger wiadomości
        """
        self.name = name
        self.config = config
        self._message_logger = message_logger
        self._is_initialized = False
        self._site_id: Optional[int] = None
        self._access_token: Optional[str] = None
        self._base_url: str = "https://qa-lynx.nayax.com"

        # Session do reuseowania połączeń HTTP
        self._session: Optional[requests.Session] = None

    def validate_config(self) -> bool:
        """
        Waliduje konfigurację komponentu Lynx API.

        Returns:
            True jeśli konfiguracja jest poprawna

        Raises:
            ValueError: Jeśli brakuje wymaganych parametrów
            ImportError: Jeśli brakuje biblioteki requests
        """
        try:
            import importlib.util

            if importlib.util.find_spec("requests") is None:
                raise ImportError(
                    "Biblioteka 'requests' jest wymagana dla komponentu Lynx API. "
                    "Zainstaluj ją: pip install requests"
                )
        except ImportError as e:
            raise e

        required_params = [
            "ACCESS_TOKEN",
        ]

        missing_params = []

        for param in required_params:
            # Sprawdź najpierw w konfiguracji komponentu, potem w env
            value = self.config.get(param) or os.getenv(param)
            if not value:
                missing_params.append(param)
            else:
                # Zapisz parametr do użycia
                if param == "ACCESS_TOKEN":
                    self._access_token = value

        # Opcjonalny parametr SITE_ID (domyślnie 0)
        site_id = self.config.get("SITE_ID") or os.getenv("SITE_ID") or "0"
        try:
            self._site_id = int(site_id)
        except (ValueError, TypeError):
            raise ValueError(f"SITE_ID musi być liczbą całkowitą, otrzymano: {site_id}")

        if missing_params:
            raise ValueError(
                f"Brakuje wymaganych parametrów konfiguracji dla komponentu Lynx API '{self.name}': "
                f"{', '.join(missing_params)}. "
                "Parametry muszą być dostępne w konfiguracji komponentu lub zmiennych środowiskowych."
            )

        debug(
            f"✅ Walidacja konfiguracji komponentu Lynx API '{self.name}' pomyślna",
            message_logger=self._message_logger,
        )

        return True

    async def initialize(self) -> bool:
        """
        Inicjalizuje komponent Lynx API.

        Returns:
            True jeśli inicjalizacja przebiegła pomyślnie
        """
        try:
            # Waliduj konfigurację
            self.validate_config()

            info(
                f"🔧 Inicjalizacja komponentu Lynx API: {self.name}",
                message_logger=self._message_logger,
            )

            # Utwórz session HTTP
            self._session = requests.Session()
            self._session.headers.update({
                "accept": "application/json",
                "content-type": "application/json",
                "Authorization": f"Bearer {self._access_token}",
            })

            self._is_initialized = True

            debug(
                f"✅ Komponent Lynx API '{self.name}' zainicjalizowany",
                message_logger=self._message_logger,
            )

            return True

        except Exception as e:
            error(
                f"❌ Błąd inicjalizacji komponentu Lynx API '{self.name}': {e}",
                message_logger=self._message_logger,
            )
            self._is_initialized = False
            return False

    async def connect(self) -> bool:
        """
        Testuje połączenie z API Lynx.

        Returns:
            True jeśli połączenie zostało nawiązane pomyślnie
        """
        if not self._is_initialized:
            error(
                f"❌ Komponent Lynx API '{self.name}' nie jest zainicjalizowany",
                message_logger=self._message_logger,
            )
            return False

        try:
            info(
                f"🔌 Testowanie połączenia z Lynx API: {self.name}",
                message_logger=self._message_logger,
            )

            # Możesz dodać tutaj test endpoint jeśli API go udostępnia
            # Na razie zakładamy, że inicjalizacja oznacza gotowość do użycia

            info(
                f"✅ Komponent Lynx API '{self.name}' gotowy do użycia",
                message_logger=self._message_logger,
            )
            return True

        except Exception as e:
            error(
                f"❌ Błąd testowania połączenia z Lynx API '{self.name}': {e}",
                message_logger=self._message_logger,
            )
            return False

    async def disconnect(self) -> bool:
        """
        Zamyka połączenie z API.

        Returns:
            True jeśli rozłączenie przebiegło pomyślnie
        """
        try:
            if self._session:
                info(
                    f"🔌 Zamykanie sesji Lynx API: {self.name}",
                    message_logger=self._message_logger,
                )
                self._session.close()
                self._session = None

            self._is_initialized = False

            debug(
                f"✅ Komponent Lynx API '{self.name}' rozłączony",
                message_logger=self._message_logger,
            )
            return True

        except Exception as e:
            error(
                f"❌ Błąd rozłączania komponentu Lynx API '{self.name}': {e}",
                message_logger=self._message_logger,
            )
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        Zwraca status komponentu.

        Returns:
            Słownik ze statusem komponentu
        """
        return {
            "name": self.name,
            "type": "lynx_api",
            "initialized": self._is_initialized,
            "site_id": self._site_id,
            "base_url": self._base_url,
            "has_session": self._session is not None,
        }

    def get_site_id(self) -> Optional[int]:
        """Zwraca ID situ."""
        return self._site_id

    def get_base_url(self) -> str:
        """Zwraca bazowy URL API."""
        return self._base_url

    async def send_refund_request(
        self,
        transaction_id: int,
        refund_amount: float = 0,
        refund_email_list: str = "",
        refund_reason: str = "",
    ) -> Dict[str, Any]:
        """
        Wysyła żądanie refund do Lynx API.

        Args:
            transaction_id: ID transakcji do zwrotu
            refund_amount: Kwota zwrotu (domyślnie 0)
            refund_email_list: Lista emaili (opcjonalnie)
            refund_reason: Powód zwrotu (opcjonalnie)

        Returns:
            Odpowiedź z API

        Raises:
            Exception: W przypadku błędu komunikacji z API
        """
        if not self._is_initialized or not self._session:
            raise Exception(
                f"Komponent Lynx API '{self.name}' nie jest zainicjalizowany"
            )

        url = f"{self._base_url}/operational/v1/payment/refund-request"

        payload = {
            "RefundAmount": refund_amount,
            "RefundEmailList": refund_email_list,
            "RefundReason": refund_reason,
            "TransactionId": transaction_id,
            "SiteId": self._site_id,  # Użyj site_id z konfiguracji komponentu
            "MachineAuTime": datetime.utcnow().isoformat() + "Z",
        }

        try:
            debug(
                f"🚀 Wysyłanie żądania refund do Lynx API dla transakcji {transaction_id}",
                message_logger=self._message_logger,
            )

            response = self._session.post(url, json=payload)
            response.raise_for_status()  # Rzuci wyjątek dla kodów błędów HTTP

            result = response.json() if response.content else {}

            info(
                f"✅ Żądanie refund wysłane pomyślnie dla transakcji {transaction_id}",
                message_logger=self._message_logger,
            )

            return {
                "success": True,
                "status_code": response.status_code,
                "response": result,
                "transaction_id": transaction_id,
            }

        except requests.exceptions.RequestException as e:
            error(
                f"❌ Błąd wysyłania żądania refund dla transakcji {transaction_id}: {e}",
                message_logger=self._message_logger,
            )
            return {"success": False, "error": str(e), "transaction_id": transaction_id}

        except Exception as e:
            error(
                f"❌ Nieoczekiwany błąd przy wysyłaniu refund dla transakcji {transaction_id}: {e}",
                message_logger=self._message_logger,
            )
            return {"success": False, "error": str(e), "transaction_id": transaction_id}

    async def send_refund_approve_request(
        self,
        transaction_id: int,
        is_refunded_externally: bool = False,
        refund_document_url: str = "",
        machine_au_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Wysyła żądanie approve refund do Lynx API.

        Args:
            transaction_id: ID transakcji do zatwierdzenia zwrotu
            is_refunded_externally: Czy zwrot został wykonany zewnętrznie
            refund_document_url: URL do dokumentu zwrotu (jeśli zewnętrzny)
            machine_au_time: Czas autoryzacji maszyny (opcjonalnie, domyślnie bieżący)

        Returns:
            Odpowiedź z API

        Raises:
            Exception: W przypadku błędu komunikacji z API
        """
        if not self._is_initialized or not self._session:
            raise Exception(
                f"Komponent Lynx API '{self.name}' nie jest zainicjalizowany"
            )

        url = f"{self._base_url}/operational/v1/payment/refund-approve"

        # Użyj podanego czasu
        if machine_au_time is None:
            raise ValueError(
                "machine_au_time musi być pobrany. Dane:  transaction_id: {transaction_id}, is_refunded_externally: {is_refunded_externally}, refund_document_url: {refund_document_url}, machine_au_time: {machine_au_time}"
            )

        payload = {
            "IsRefundedExternally": is_refunded_externally,
            "RefundDocumentUrl": refund_document_url,
            "TransactionId": transaction_id,
            "SiteId": self._site_id,  # Użyj site_id z konfiguracji komponentu
            "MachineAuTime": machine_au_time,
        }

        try:
            debug(
                f"🚀 Wysyłanie żądania approve refund do Lynx API dla transakcji {transaction_id}",
                message_logger=self._message_logger,
            )

            response = self._session.post(url, json=payload)
            response.raise_for_status()  # Rzuci wyjątek dla kodów błędów HTTP

            result = response.json() if response.content else {}

            info(
                f"✅ Żądanie approve refund wysłane pomyślnie dla transakcji {transaction_id}",
                message_logger=self._message_logger,
            )

            return {
                "success": True,
                "status_code": response.status_code,
                "response": result,
                "transaction_id": transaction_id,
            }

        except requests.exceptions.RequestException as e:
            error(
                f"❌ Błąd wysyłania żądania approve refund dla transakcji {transaction_id}: {e}",
                message_logger=self._message_logger,
            )
            return {"success": False, "error": str(e), "transaction_id": transaction_id}

        except Exception as e:
            error(
                f"❌ Nieoczekiwany błąd przy wysyłaniu approve refund dla transakcji {transaction_id}: {e}",
                message_logger=self._message_logger,
            )
            return {"success": False, "error": str(e), "transaction_id": transaction_id}
