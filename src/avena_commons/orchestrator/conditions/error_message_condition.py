"""Warunek sprawdzający zawartość komunikatów błędów od klientów IO.

Cel: Umożliwia uruchamianie scenariuszy w zależności od konkretnych urządzeń/błędów
zawartych w error_message od klientów lub bezpośrednio w io_server.failed_virtual_devices.
Obsługuje różne tryby dopasowania i wyciąganie danych.

Wejścia: Konfiguracja z kryteriami dopasowania, kontekst ze stanami klientów
Wyjścia: bool - czy warunek jest spełniony, opcjonalnie zapisuje dane do kontekstu + ekstrahuje szczegóły urządzeń
Ograniczenia: check_io_devices=True działa tylko dla klientów IO z failed_virtual_devices
"""

import re
from typing import Any, Dict

from ..base.base_condition import BaseCondition


class ErrorMessageCondition(BaseCondition):
    """
    Sprawdza zawartość komunikatów błędów (error_message) od klientów.

    Umożliwia uruchamianie scenariuszy w zależności od konkretnych urządzeń
    lub typów błędów zawartych w error_message. Obsługuje również wyciąganie
    danych z wiadomości błędów do kontekstu scenariusza.

    Obsługiwane tryby dopasowania:
    - contains: sprawdza czy error_message zawiera określony tekst
    - starts_with: sprawdza czy error_message zaczyna się od określonego tekstu
    - regex: sprawdza czy error_message pasuje do wzorca regex
    - exact: sprawdza dokładne dopasowanie error_message

    Obsługiwane zakresy:
    - fault_clients_only: tylko klienci w stanie FAULT (domyślnie True)
    - error_clients_only: tylko klienci z error=True (domyślnie False)
    - all_clients: wszyscy klienci niezależnie od stanu (domyślnie False)

    Wsparcie dla klientów IO (check_io_devices=True):
    - check_io_devices: sprawdza io_server.failed_virtual_devices zamiast error_message
    - extract_physical_device_to: nazwa zmiennej dla urządzenia fizycznego
    - extract_error_message_to: nazwa zmiennej dla komunikatu błędu
    - extract_device_type_to: nazwa zmiennej dla typu urządzenia fizycznego

    Wyciąganie danych (tylko dla trybu regex):
    - extract_to_context: dict mapujący nazwy zmiennych kontekstu na:
      * numery grup regex (int): np. {"wydawka_id": 1} dla grupy (\\d+)
      * nazwy grup regex (str): np. {"wydawka_id": "id"} dla grupy (?P<id>\\d+)

    Przykład konfiguracji prostej:
    {
        "error_message": {
            "mode": "contains",
            "pattern": "feeder1",
            "case_sensitive": false,
            "fault_clients_only": true
        }
    }

    Przykład konfiguracji dla klienta IO (sprawdzanie urządzeń):
    {
        "error_message": {
            "mode": "contains",
            "pattern": "feeder",
            "check_io_devices": true,
            "extract_physical_device_to": "urzadzenie_fizyczne",
            "extract_error_message_to": "komunikat_bledu",
            "extract_device_type_to": "typ_urzadzenia"
        }
    }

    Przykład konfiguracji z wyciąganiem danych (numerowana grupa):
    {
        "error_message": {
            "mode": "regex",
            "pattern": "feeder(\\d+)",
            "case_sensitive": false,
            "fault_clients_only": true,
            "extract_to_context": {
                "wydawka_id": 1
            }
        }
    }

    Przykład konfiguracji z wyciąganiem danych (nazwana grupa):
    {
        "error_message": {
            "mode": "regex",
            "pattern": "feeder(?P<id>\\d+)",
            "case_sensitive": false,
            "fault_clients_only": true,
            "extract_to_context": {
                "wydawka_id": "id"
            }
        }
    }
    """

    async def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Ewaluuje warunek na podstawie komunikatów błędów klientów.

        Args:
            context: Kontekst z kluczem "clients" zawierającym stany klientów
                    lub instancja ScenarioContext

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
        extract_to_context = self.config.get("extract_to_context", {})

        # Parametry dla sprawdzania urządzeń IO
        check_io_devices = self.config.get("check_io_devices", False)
        extract_physical_device_to = self.config.get("extract_physical_device_to")
        extract_error_message_to = self.config.get("extract_error_message_to")
        extract_device_type_to = self.config.get("extract_device_type_to")

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

        # Sprawdź czy mamy ScenarioContext czy zwykły dict
        scenario_context = None
        if hasattr(context, "clients") and hasattr(context, "set"):
            # To jest ScenarioContext
            scenario_context = context
            clients_state = context.clients
        else:
            # To jest zwykły dict z kontekstem
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

            # Jeśli check_io_devices=True, sprawdź io_server.failed_virtual_devices
            if check_io_devices:
                io_server = client_data.get("io_server", {})
                failed_devices = io_server.get("failed_virtual_devices", {})

                if failed_devices:
                    for vdev_name, vdev_info in failed_devices.items():
                        # Sprawdź czy nazwa urządzenia wirtualnego pasuje do wzorca
                        match_result = self._check_pattern_match(
                            vdev_name,
                            search_pattern,
                            mode,
                            case_sensitive,
                            regex_pattern,
                        )

                        if match_result:
                            matching_clients.append(client_name)

                            # Ekstrahuj informacje o urządzeniach fizycznych
                            if scenario_context:
                                failed_physical = vdev_info.get(
                                    "failed_physical_devices", {}
                                )

                                if failed_physical:
                                    first_physical_name = next(
                                        iter(failed_physical.keys()), None
                                    )

                                    if first_physical_name:
                                        physical_info = failed_physical[
                                            first_physical_name
                                        ]

                                        if extract_physical_device_to:
                                            scenario_context.set(
                                                extract_physical_device_to,
                                                first_physical_name,
                                            )

                                        if extract_error_message_to:
                                            error_msg = physical_info.get(
                                                "error_message", "Unknown error"
                                            )
                                            scenario_context.set(
                                                extract_error_message_to, error_msg
                                            )

                                        if extract_device_type_to:
                                            device_type = physical_info.get(
                                                "device_type", "Unknown"
                                            )
                                            scenario_context.set(
                                                extract_device_type_to, device_type
                                            )

                                        if self.message_logger:
                                            self.message_logger.debug(
                                                f"ErrorMessageCondition: wyciągnięto dane urządzenia - "
                                                f"fizyczne: {first_physical_name}, "
                                                f"typ: {physical_info.get('device_type')}, "
                                                f"błąd: {physical_info.get('error_message')}"
                                            )

                            if self.message_logger:
                                self.message_logger.debug(
                                    f"ErrorMessageCondition: dopasowanie w io_server.failed_virtual_devices "
                                    f"klienta '{client_name}': '{vdev_name}' pasuje do wzorca '{pattern}' (tryb: {mode})"
                                )
                            break  # Znaleziono dopasowanie w tym kliencie
                continue  # Następny klient (jeśli check_io_devices)

            # Standardowe sprawdzanie error_message
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
            match_result = self._check_pattern_match(
                error_message, search_pattern, mode, case_sensitive, regex_pattern
            )

            if match_result:
                matching_clients.append(client_name)

                # Jeśli to regex i mamy extract_to_context, wyciągnij dane
                if (
                    mode == "regex"
                    and extract_to_context
                    and regex_pattern
                    and scenario_context
                ):
                    regex_match = regex_pattern.search(error_message)
                    if regex_match:
                        for context_key, group_identifier in extract_to_context.items():
                            try:
                                # Obsługa nazwanych grup (string) i numerowanych grup (int)
                                if isinstance(group_identifier, str):
                                    # Nazwana grupa - używamy groupdict()
                                    extracted_value = regex_match.groupdict().get(
                                        group_identifier
                                    )
                                    if extracted_value is None:
                                        if self.message_logger:
                                            self.message_logger.warning(
                                                f"ErrorMessageCondition: nie znaleziono nazwanej grupy '{group_identifier}' "
                                                f"dla klucza '{context_key}'"
                                            )
                                        continue
                                    group_type = "nazwanej"
                                else:
                                    # Numerowana grupa - używamy group(index)
                                    extracted_value = regex_match.group(
                                        group_identifier
                                    )
                                    group_type = "numerowanej"

                                # Spróbuj przekonwertować na liczbę jeśli to możliwe
                                try:
                                    extracted_value = int(extracted_value)
                                except ValueError:
                                    # Zostaw jako string jeśli konwersja nie jest możliwa
                                    pass

                                scenario_context.set(context_key, extracted_value)
                                if self.message_logger:
                                    self.message_logger.debug(
                                        f"ErrorMessageCondition: wyciągnięto '{context_key}' = {extracted_value} "
                                        f"(typ: {type(extracted_value).__name__}) z {group_type} grupy '{group_identifier}' w kliencie '{client_name}'"
                                    )
                            except (IndexError, ValueError) as e:
                                if self.message_logger:
                                    self.message_logger.warning(
                                        f"ErrorMessageCondition: nie można wyciągnąć grupy '{group_identifier}' "
                                        f"dla klucza '{context_key}': {e}"
                                    )

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
