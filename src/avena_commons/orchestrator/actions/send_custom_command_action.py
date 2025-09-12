"""
Implementacja akcji send_custom_command dla scenariuszy.
Umożliwia wysyłanie poleceń niestandardowych z dowolnymi danymi do serwisów.
"""

from typing import Any, Dict, List

from avena_commons.util.logger import debug, info

from ..models.scenario_models import ScenarioContext
from .base_action import ActionExecutionError, BaseAction


class SendCustomCommandAction(BaseAction):
    """
    Akcja wysyłania poleceń niestandardowych z danymi do serwisów.

    Obsługuje różne selektory:
    - client: pojedynczy serwis
    - group: jedna grupa serwisów
    - groups: wiele grup serwisów
    - target: "@all" dla wszystkich serwisów

    W przeciwieństwie do send_command, pozwala na wysłanie dowolnych danych
    wraz z poleceniem niestandardowym.

    Przykład użycia w JSON:
    {
        "type": "send_custom_command",
        "client": "supervisor_1",
        "command": "SET_POSITION",
        "data": {
            "x": 100.5,
            "y": 200.3,
            "z": 15.0,
            "speed": 0.8
        },
        "description": "Ustawienie pozycji robota"
    }

    {
        "type": "send_custom_command",
        "group": "sensors",
        "command": "CONFIGURE_THRESHOLDS",
        "data": {
            "min_value": 0.1,
            "max_value": 95.0,
            "alert_enabled": true
        }
    }
    """

    async def execute(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> None:
        """
        Wykonuje akcję wysyłania polecenia niestandardowego z danymi.

        Args:
            action_config: Konfiguracja akcji z polami:
                - command (str): Nazwa polecenia niestandardowego
                - data (dict): Słownik z danymi do wysłania
                - client/group/groups/target: Selektor celów
                - timeout (optional): Timeout dla polecenia
            context: Kontekst wykonania

        Raises:
            ActionExecutionError: W przypadku błędu wykonania
        """
        try:
            # Sprawdź czy komenda jest określona
            command = action_config.get("command")
            if not command:
                raise ActionExecutionError(
                    "send_custom_command", "Brak komendy do wysłania (pole: command)"
                )

            # Pobierz dane do wysłania (domyślnie pusty słownik)
            command_data = action_config.get("data", {})
            if not isinstance(command_data, dict):
                raise ActionExecutionError(
                    "send_custom_command",
                    f"Pole 'data' musi być słownikiem, otrzymano: {type(command_data).__name__}",
                )

            # Rozwiąż zmienne szablonowe w danych
            resolved_data = self._resolve_template_variables_in_data(
                command_data, context
            )

            # Określ komponenty docelowe
            target_clients = self._resolve_target_clients(action_config, context)
            if not target_clients:
                raise ActionExecutionError(
                    "send_custom_command", "Nie znaleziono komponentów docelowych"
                )

            debug(
                f"📤 send_custom_command: Wysyłam '{command}' z danymi {resolved_data} do {len(target_clients)} klientów: {target_clients}",
                message_logger=context.message_logger,
            )

            # Wyślij polecenie do wszystkich komponentów docelowych
            for client_name in target_clients:
                await self._send_custom_command_to_client(
                    client_name, command, resolved_data, action_config, context
                )

            info(
                f"✅ send_custom_command: Pomyślnie wysłano '{command}' do wszystkich {len(target_clients)} klientów",
                message_logger=context.message_logger,
            )

        except ActionExecutionError:
            # Przepuść błędy ActionExecutionError
            raise
        except Exception as e:
            raise ActionExecutionError(
                "send_custom_command", f"Nieoczekiwany błąd: {str(e)}"
            )

    def _resolve_target_clients(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> List[str]:
        """
        Rozwiązuje komponenty docelowe na podstawie selektorów.
        Identyczna logika jak w SendCommandAction.

        Args:
            action_config: Konfiguracja akcji
            context: Kontekst wykonania

        Returns:
            Lista nazw komponentów docelowych
        """
        target_clients = []
        orchestrator = context.orchestrator

        # Sprawdź selektor "@all"
        if "target" in action_config and action_config["target"] == "@all":
            target_clients.extend(context.clients)

        # Sprawdź pojedynczy komponent
        elif "client" in action_config and action_config["client"]:
            client_name = self._resolve_template_variables(
                action_config["client"], context
            )
            target_clients.append(client_name)

        # Sprawdź pojedynczą grupę
        elif "group" in action_config and action_config["group"]:
            group_name = action_config["group"]
            target_clients.extend(self._get_clients_by_group(group_name, orchestrator))

        # Sprawdź wiele grup
        elif "groups" in action_config and action_config["groups"]:
            groups = action_config["groups"]
            if isinstance(groups, list):
                for group_name in groups:
                    target_clients.extend(
                        self._get_clients_by_group(group_name, orchestrator)
                    )

        # Usunięcie duplikatów
        target_clients = list(set(target_clients))

        return target_clients

    def _get_clients_by_group(self, group_name: str, orchestrator) -> List[str]:
        """
        Pobiera serwisy należące do określonej grupy.

        Args:
            group_name: Nazwa grupy
            orchestrator: Referencja do Orchestratora

        Returns:
            Lista nazw serwisów w grupie
        """
        clients = []
        config = orchestrator._configuration.get("clients", {})

        for client_name, client_config in config.items():
            if client_config.get("group") == group_name:
                clients.append(client_name)

        return clients

    def _resolve_template_variables_in_data(
        self, data: Dict[str, Any], context: ScenarioContext
    ) -> Dict[str, Any]:
        """
        Rozwiązuje zmienne szablonowe w słowniku danych.

        Args:
            data: Słownik z danymi mogącymi zawierać zmienne szablonowe
            context: Kontekst z danymi do podstawienia

        Returns:
            Słownik z podstawionymi zmiennymi
        """
        resolved_data = {}

        for key, value in data.items():
            if isinstance(value, str):
                # Rozwiąż zmienne szablonowe w wartościach tekstowych
                resolved_data[key] = self._resolve_template_variables(value, context)
            elif isinstance(value, dict):
                # Rekurencyjnie rozwiąż zagnieżdżone słowniki
                resolved_data[key] = self._resolve_template_variables_in_data(
                    value, context
                )
            elif isinstance(value, list):
                # Rozwiąż zmienne w listach
                resolved_data[key] = [
                    self._resolve_template_variables(item, context)
                    if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                # Pozostaw inne typy bez zmian
                resolved_data[key] = value

        return resolved_data

    async def _send_custom_command_to_client(
        self,
        client_name: str,
        command: str,
        command_data: Dict[str, Any],
        action_config: Dict[str, Any],
        context: ScenarioContext,
    ) -> None:
        """
        Wysyła polecenie niestandardowe z danymi do konkretnego komponentu.

        Args:
            client_name: Nazwa serwisu
            command: Polecenie do wysłania
            command_data: Dane do wysłania z poleceniem
            action_config: Konfiguracja akcji (dla ewentualnego timeout)
            context: Kontekst wykonania

        Raises:
            ActionExecutionError: W przypadku błędu wysyłania
        """
        if client_name not in context.clients:
            raise ActionExecutionError(
                "send_custom_command",
                f'Serwis "{client_name}" nie znaleziony w konfiguracji',
            )

        client_config = context.clients[client_name]

        try:
            # Pobierz timeout z konfiguracji akcji (jeśli podany)
            timeout = action_config.get("timeout", 20.0)
            if isinstance(timeout, str):
                timeout = self._parse_timeout(timeout)

            # Użyj metody _event z Orchestratora do wysłania polecenia z danymi
            event = await context.orchestrator._event(
                destination=client_name,
                destination_address=client_config["address"],
                destination_port=client_config["port"],
                event_type=command,
                data=command_data,  # Tu przekazujemy dane niestandardowe!
                to_be_processed=True,
                maximum_processing_time=float(timeout),
            )

            info(
                f"Wysłano polecenie niestandardowe '{command}' z danymi do serwisu '{client_name}'",
                message_logger=context.message_logger,
            )

        except Exception as e:
            raise ActionExecutionError(
                "send_custom_command",
                f'Błąd wysyłania polecenia "{command}" z danymi do "{client_name}": {str(e)}',
                e,
            )
