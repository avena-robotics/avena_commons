"""Warunek sprawdzający zawartość komunikatów błędów od klientów IO.

Cel: Umożliwia uruchamianie scenariuszy w zależności od konkretnych urządzeń/błędów
zawartych w error_message od klientów. Obsługuje różne tryby dopasowania.

Wejścia: Konfiguracja z kryteriami dopasowania, kontekst ze stanami klientów
Wyjścia: bool - czy warunek jest spełniony
Ograniczenia: Wymaga dostępu do orchestrator._state z error_message klientów
"""

import re
from typing import Any, Dict

from ..base.base_condition import BaseCondition


class ErrorMessageCondition(BaseCondition):
    """
    Sprawdza zawartość komunikatów błędów (error_message) od klientów.

    Umożliwia uruchamianie scenariuszy w zależności od konkretnych urządzeń
    lub typów błędów zawartych w error_message.

    Obsługiwane tryby dopasowania:
    - contains: sprawdza czy error_message zawiera określony tekst
    - starts_with: sprawdza czy error_message zaczyna się od określonego tekstu
    - regex: sprawdza czy error_message pasuje do wzorca regex
    - exact: sprawdza dokładne dopasowanie error_message

    Obsługiwane zakresy:
    - fault_clients_only: tylko klienci w stanie FAULT (domyślnie True)
    - error_clients_only: tylko klienci z error=True (domyślnie False)
    - all_clients: wszyscy klienci niezależnie od stanu (domyślnie False)

    Przykład konfiguracji:
    {
        "error_message": {
            "mode": "contains",
            "pattern": "feeder1",
            "case_sensitive": false,
            "fault_clients_only": true
        }
    }
    """

    async def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Ewaluuje warunek na podstawie komunikatów błędów klientów.

        Args:
            context: Kontekst z kluczem "clients" zawierającym stany klientów

        Returns:
            bool: True jeśli znaleziono dopasowanie, False w przeciwnym razie

        Raises:
            ValueError: Gdy konfiguracja jest nieprawidłowa
        """
        # Pobierz parametry konfiguracji bezpośrednio z self.config
        # (fabryka warunków przekazuje zawartość klucza "error_message" jako config)
        mode = self.config.get("mode", "contains")
        pattern = self.config.get("pattern")
        case_sensitive = self.config.get("case_sensitive", False)

        # Opcje zakresu sprawdzania
        fault_clients_only = self.config.get("fault_clients_only", True)
        error_clients_only = self.config.get("error_clients_only", False)
        all_clients = self.config.get("all_clients", False)

        if not pattern:
            if self.message_logger:
                self.message_logger.warning(
                    "ErrorMessageCondition: brak wymaganego parametru 'pattern'"
                )
            return False

        # Walidacja trybu
        valid_modes = ["contains", "starts_with", "regex", "exact"]
        if mode not in valid_modes:
            raise ValueError(
                f"ErrorMessageCondition: nieprawidłowy tryb '{mode}'. "
                f"Obsługiwane: {valid_modes}"
            )

        # Pobierz stany klientów
        clients_state = context.get("clients", {})
        if not clients_state:
            if self.message_logger:
                self.message_logger.debug(
                    "ErrorMessageCondition: brak danych o klientach w kontekście"
                )
            return False

        # Przygotuj wzorzec dla porównania
        search_pattern = pattern if case_sensitive else pattern.lower()

        # Kompiluj regex jeśli potrzebny
        regex_pattern = None
        if mode == "regex":
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                regex_pattern = re.compile(pattern, flags)
            except re.error as e:
                if self.message_logger:
                    self.message_logger.error(
                        f"ErrorMessageCondition: błędny wzorzec regex '{pattern}': {e}"
                    )
                return False

        # Sprawdź każdego klienta
        matching_clients = []

        for client_name, client_data in clients_state.items():
            if not isinstance(client_data, dict):
                continue

            # Sprawdź zakres - czy klient spełnia kryteria sprawdzania
            if not self._should_check_client(
                client_data, fault_clients_only, error_clients_only, all_clients
            ):
                continue

            # Pobierz error_message
            error_message = client_data.get("error_message")
            if not error_message:
                continue

            # Normalizuj error_message do string
            if isinstance(error_message, (list, tuple)):
                error_message = " ".join(str(msg) for msg in error_message)
            else:
                error_message = str(error_message)

            # Sprawdź dopasowanie
            if self._check_pattern_match(
                error_message, search_pattern, mode, case_sensitive, regex_pattern
            ):
                matching_clients.append(client_name)
                if self.message_logger:
                    self.message_logger.debug(
                        f"ErrorMessageCondition: dopasowanie znalezione w kliencie '{client_name}': "
                        f"'{error_message}' pasuje do wzorca '{pattern}' (tryb: {mode})"
                    )

        # Zwróć wynik
        found_match = len(matching_clients) > 0

        if self.message_logger:
            if found_match:
                self.message_logger.debug(
                    f"ErrorMessageCondition: warunek spełniony - znaleziono {len(matching_clients)} "
                    f"dopasowań: {matching_clients}"
                )
            else:
                self.message_logger.debug(
                    f"ErrorMessageCondition: warunek nie spełniony - brak dopasowań dla wzorca "
                    f"'{pattern}' (tryb: {mode})"
                )

        return found_match

    def _should_check_client(
        self,
        client_data: Dict[str, Any],
        fault_clients_only: bool,
        error_clients_only: bool,
        all_clients: bool,
    ) -> bool:
        """
        Sprawdza czy klient powinien być uwzględniony w sprawdzaniu.

        Args:
            client_data: Dane klienta ze stanu
            fault_clients_only: Czy sprawdzać tylko klientów w stanie FAULT
            error_clients_only: Czy sprawdzać tylko klientów z error=True
            all_clients: Czy sprawdzać wszystkich klientów

        Returns:
            bool: True jeśli klient powinien być sprawdzony
        """
        # Jeśli all_clients=True, sprawdzaj wszystkich
        if all_clients:
            return True

        # Jeśli fault_clients_only=True (domyślnie), sprawdzaj tylko FAULT
        if fault_clients_only:
            fsm_state = client_data.get("fsm_state")
            if fsm_state != "FAULT":
                return False

        # Jeśli error_clients_only=True, sprawdzaj tylko z error=True
        if error_clients_only:
            error_flag = client_data.get("error", False)
            if not error_flag:
                return False

        return True

    def _check_pattern_match(
        self,
        error_message: str,
        search_pattern: str,
        mode: str,
        case_sensitive: bool,
        regex_pattern: re.Pattern = None,
    ) -> bool:
        """
        Sprawdza czy error_message pasuje do wzorca według określonego trybu.

        Args:
            error_message: Komunikat błędu do sprawdzenia
            search_pattern: Wzorzec do wyszukania (już znormalizowany dla case sensitivity)
            mode: Tryb dopasowania
            case_sensitive: Czy uwzględniać wielkość liter
            regex_pattern: Skompilowany wzorzec regex (dla trybu regex)

        Returns:
            bool: True jeśli znaleziono dopasowanie
        """
        # Przygotuj tekst do porównania
        text_to_check = error_message if case_sensitive else error_message.lower()

        if mode == "contains":
            return search_pattern in text_to_check

        elif mode == "starts_with":
            return text_to_check.startswith(search_pattern)

        elif mode == "exact":
            return text_to_check == search_pattern

        elif mode == "regex":
            if regex_pattern is None:
                return False
            return bool(regex_pattern.search(error_message))

        return False

    def get_description(self) -> str:
        """
        Zwraca opis warunku dla celów logowania.

        Returns:
            str: Opis warunku z kluczowymi parametrami
        """
        mode = self.config.get("mode", "contains")
        pattern = self.config.get("pattern", "")

        return f"error_message: {mode}('{pattern}')"
