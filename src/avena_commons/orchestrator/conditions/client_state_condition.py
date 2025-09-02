from typing import Any, Dict, List

from ..base.base_condition import BaseCondition


class ClientStateCondition(BaseCondition):
    """Sprawdza stan klienta."""

    async def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Ewaluacja warunku na podstawie stanów klientów w kontekście.

        Obsługiwane klucze w konfiguracji:
        - any_service_in_state (str|List[str]) – True, jeśli dowolny klient jest w jednym z podanych stanów.
        - no_service_in_state (str|List[str]) – True, jeśli żaden klient nie jest w żadnym z podanych stanów.
        - all_services_in_state (str|List[str]) – True, jeśli wszyscy klienci są w wymaganym stanie/stanach.
        - client (str), state (str) – klasyczne sprawdzenie pojedynczego klienta.
        - exclude_clients (str|List[str]) – lista klientów do pominięcia.

        Args:
            context (Dict[str, Any]): Kontekst z kluczem "clients" zawierającym stany klientów.

        Returns:
            bool: Wynik ewaluacji warunku.
        """
        # Sprawdź czy mamy parametry any_service_in_state lub no_service_in_state
        any_service_in_state = self.config.get("any_service_in_state")
        no_service_in_state = self.config.get("no_service_in_state")
        all_services_in_state = self.config.get("all_services_in_state")
        # Opcjonalna lista klientów do wykluczenia z ewaluacji
        exclude_clients = self.config.get("exclude_clients")
        if isinstance(exclude_clients, str):
            exclude_clients = [exclude_clients]
        exclude_set: set[str] | None = set(exclude_clients) if exclude_clients else None

        # Pobierz aktualny stan klientów z kontekstu
        clients_state = context.get("clients", {})

        if any_service_in_state:
            # Normalizuj do listy
            if isinstance(any_service_in_state, str):
                any_service_in_state = [any_service_in_state]
            # Sprawdź czy przynajmniej jeden klient jest w jednym z wymaganych stanów
            return self._check_any_service_in_state(
                clients_state, any_service_in_state, exclude_set
            )

        elif no_service_in_state:
            # Normalizuj do listy
            if isinstance(no_service_in_state, str):
                no_service_in_state = [no_service_in_state]
            # Sprawdź czy żaden klient nie jest w żadnym z zabronionych stanów
            return self._check_no_service_in_state(
                clients_state, no_service_in_state, exclude_set
            )

        elif all_services_in_state:
            # Normalizuj: dopuszczamy string lub listę
            return self._check_all_services_in_state(
                clients_state, all_services_in_state, exclude_set
            )

        else:
            # Standardowe sprawdzenie pojedynczego klienta
            client_name = self.config.get("client")
            expected_state = self.config.get("state")

            if not client_name or expected_state is None:
                if self.message_logger:
                    self.message_logger.warning(
                        "ClientStateCondition: brak client/state lub any_service_in_state/no_service_in_state w konfiguracji"
                    )
                return False

            current_state = clients_state.get(client_name, {}).get("fsm_state")

            if self.message_logger:
                self.message_logger.debug(
                    f"ClientStateCondition: {client_name} = {current_state}, oczekiwany: {expected_state}"
                )

            return current_state == expected_state

    def _check_any_service_in_state(
        self,
        clients_state: Dict[str, Any],
        required_states: List[str],
        exclude_clients: set[str] | None = None,
    ) -> bool:
        """Sprawdza czy przynajmniej jeden klient jest w jednym z wymaganych stanów.

        Jeśli podano `exclude_clients`, klienci z tej listy są pomijani.
        """
        required: set[str] = set(required_states)
        for client_name, client_data in clients_state.items():
            if not isinstance(client_data, dict):
                continue
            if exclude_clients and client_name in exclude_clients:
                continue
            current_state = client_data.get("fsm_state")
            if isinstance(current_state, str) and current_state in required:
                if self.message_logger:
                    self.message_logger.debug(
                        f"ClientStateCondition: {client_name} w stanie {current_state} (wymagane: {sorted(required)})"
                    )
                return True

        if self.message_logger:
            self.message_logger.debug(
                f"ClientStateCondition: żaden klient nie jest w wymaganych stanach {required_states}"
            )
        return False

    def _check_all_services_in_state(
        self,
        clients_state: Dict[str, Any],
        required_state_or_list: Any,
        exclude_clients: set[str] | None = None,
    ) -> bool:
        """Sprawdza czy wszyscy klienci są w wymaganym stanie/stanach.

        Ignoruje wpisy niebędące klientami (brak słownika lub brak klucza 'fsm_state').
        Jeśli podano `exclude_clients`, klienci z tej listy są pomijani przy sprawdzaniu.
        """
        considered = 0
        if isinstance(required_state_or_list, list):
            allowed: set[str] = set(required_state_or_list)
            for client_name, client_data in clients_state.items():
                if not isinstance(client_data, dict):
                    continue
                if exclude_clients and client_name in exclude_clients:
                    continue
                current_state = client_data.get("fsm_state")
                if not isinstance(current_state, str):
                    # ignoruj wpisy bez poprawnego stanu (np. klucz 'clients')
                    continue
                considered += 1
                if current_state not in allowed:
                    if self.message_logger:
                        self.message_logger.debug(
                            f"ClientStateCondition: klient {client_name} nie jest w wymaganych stanach {sorted(allowed)} (ma: {current_state})"
                        )
                    return False
            return considered > 0
        else:
            required_state = str(required_state_or_list)
            for client_name, client_data in clients_state.items():
                if not isinstance(client_data, dict):
                    continue
                if exclude_clients and client_name in exclude_clients:
                    continue
                current_state = client_data.get("fsm_state")
                if not isinstance(current_state, str):
                    # ignoruj wpisy bez poprawnego stanu (np. klucz 'clients')
                    continue
                considered += 1
                if current_state != required_state:
                    if self.message_logger:
                        self.message_logger.debug(
                            f"ClientStateCondition: klient {client_name} nie jest w wymaganym stanie {required_state} (ma: {current_state})"
                        )
                    return False
            return considered > 0

    def _check_no_service_in_state(
        self,
        clients_state: Dict[str, Any],
        forbidden_states: List[str],
        exclude_clients: set[str] | None = None,
    ) -> bool:
        """Sprawdza czy żaden klient nie jest w żadnym z zabronionych stanów.

        Jeśli podano `exclude_clients`, klienci z tej listy są pomijani.
        """
        forbidden: set[str] = set(forbidden_states)
        for client_name, client_data in clients_state.items():
            if not isinstance(client_data, dict):
                continue
            if exclude_clients and client_name in exclude_clients:
                continue
            current_state = client_data.get("fsm_state")
            if isinstance(current_state, str) and current_state in forbidden:
                if self.message_logger:
                    self.message_logger.debug(
                        f"ClientStateCondition: znaleziono klienta {client_name} w zabronionym stanie {current_state} (zabronione: {forbidden_states})"
                    )
                return False

        if self.message_logger:
            self.message_logger.debug(
                f"ClientStateCondition: żaden klient nie jest w zabronionych stanach {forbidden_states}"
            )
        return True
