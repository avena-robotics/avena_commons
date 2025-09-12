"""
Implementacja akcji send_command dla scenariuszy.
"""

from typing import Any, Dict, List

from avena_commons.util.logger import debug, info

from ..models.scenario_models import ScenarioContext
from .base_action import ActionExecutionError, BaseAction


class SendCommandAction(BaseAction):
    """
    Akcja wysyłania komend FSM do serwisów.

    Obsługuje różne selektory:
    - client: pojedynczy serwis
    - group: jedna grupa serwisów
    - groups: wiele grup serwisów
    - target: "@all" dla wszystkich serwisów

    Przykład użycia w YAML:
    - type: "send_command"
      client: "io"
      command: "CMD_INITIALIZE"

    - type: "send_command"
      groups: ["supervisors", "base_io"]
      command: "CMD_GRACEFUL_STOP"
    """

    async def execute(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> None:
        """
        Wykonuje akcję wysyłania komendy.

        Args:
            action_config: Konfiguracja akcji
            context: Kontekst wykonania

        Raises:
            ActionExecutionError: W przypadku błędu wykonania
        """
        try:
            # Sprawdź czy komenda jest określona
            command = action_config.get("command")
            if not command:
                raise ActionExecutionError(
                    "send_command", "Brak komendy do wysłania (pole: command)"
                )

            # Określ komponenty docelowe
            target_clients = self._resolve_target_clients(action_config, context)
            if not target_clients:
                raise ActionExecutionError(
                    "send_command", "Nie znaleziono komponentów docelowych"
                )

            debug(
                f"📤 send_command: Wysyłam '{command}' do {len(target_clients)} klientów: {target_clients}",
                message_logger=context.message_logger,
            )

            # Wyślij komendę do wszystkich komponentów docelowych
            for client_name in target_clients:
                await self._send_command_to_client(client_name, command, context)

            info(
                f"✅ send_command: Pomyślnie wysłano '{command}' do wszystkich {len(target_clients)} klientów",
                message_logger=context.message_logger,
            )

        except ActionExecutionError:
            # Przepuść błędy ActionExecutionError
            raise
        except Exception as e:
            raise ActionExecutionError("send_command", f"Nieoczekiwany błąd: {str(e)}")

    def _resolve_target_clients(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> List[str]:
        """
        Rozwiązuje komponenty docelowe na podstawie selektorów.

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

    # def _get_all_clients(self, orchestrator) -> List[str]:
    #     """
    #     Pobiera wszystkie zarejestrowane serwisy.

    #     Args:
    #         orchestrator: Referencja do Orchestratora

    #     Returns:
    #         Lista nazw wszystkich serwisów
    #     """
    #     config = orchestrator._configuration.get("clients", {})
    #     return list(config.keys())

    async def _send_command_to_client(
        self, client_name: str, command: str, context: ScenarioContext
    ) -> None:
        """
        Wysyła komendę do konkretnego komponentu.

        Args:
            client_name: Nazwa serwisu
            command: Komenda do wysłania
            context: Kontekst wykonania

        Raises:
            ActionExecutionError: W przypadku błędu wysyłania
        """
        if client_name not in context.clients:
            raise ActionExecutionError(
                "send_command",
                f'Serwis "{client_name}" nie znaleziony w konfiguracji',
            )

        client_config = context.clients[client_name]

        try:
            # Użyj metody _event z Orchestratora do wysłania komendy
            event = await context.orchestrator._event(
                destination=client_name,
                destination_address=client_config["address"],
                destination_port=client_config["port"],
                event_type=command,
                data={},
                to_be_processed=True,
            )

            info(
                f"Wysłano komendę '{command}' do serwisu '{client_name}'",
                message_logger=context.message_logger,
            )

        except Exception as e:
            raise ActionExecutionError(
                "send_command",
                f'Błąd wysyłania komendy "{command}" do "{client_name}": {str(e)}',
                e,
            )
