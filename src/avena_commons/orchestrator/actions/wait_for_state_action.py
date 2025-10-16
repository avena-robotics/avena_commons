"""
Implementacja akcji wait_for_state dla scenariuszy.
"""

import asyncio
from typing import Any, Dict, List

from avena_commons.util.logger import debug, error, info, warning

from ..models.scenario_models import ScenarioContext
from .base_action import ActionExecutionError, BaseAction


class WaitForStateAction(BaseAction):
    """
    Akcja oczekiwania na określony stan serwisów z timeout.

    Obsługuje te same selektory co send_command oraz dodatkową obsługę on_failure.

    Przykład użycia w YAML:
    - type: "wait_for_state"
      client: "io"
      target_state: "INITIALIZED"
      timeout: "30s"

    - type: "wait_for_state"
      groups: ["supervisors", "base_io"]
      target_state: "STOPPED"
      timeout: "45s"
      on_failure:
        - type: "log_event"
          level: "critical"
          message: "Timeout podczas oczekiwania na stan STOPPED"
    """

    async def execute(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> None:
        """
        Wykonuje oczekiwanie na stan serwisów z timeout.

        Args:
            action_config: Konfiguracja z kluczami:
                - target_state/target_states: oczekiwany stan (string) lub lista stanów (np. ["INITIALIZED", "PAUSED"])
                - timeout: timeout jako string (np. "30s") lub liczba sekund
                - client/group/groups/target: selektory serwisów
                - on_failure: lista akcji do wykonania w przypadku timeout (opcjonalnie)
            context: Kontekst wykonania akcji

        Raises:
            ActionExecutionError: W przypadku timeout lub błędnej konfiguracji
        """
        try:
            debug(
                f"🔍 wait_for_state execute: rozpoczynam, config keys: {list(action_config.keys())}",
                message_logger=context.message_logger,
            )

            # Pobierz oczekiwany(e) stan(y)
            raw_target_state = action_config.get("target_state")
            raw_target_states = action_config.get("target_states")

            target_states: List[str] = []
            if raw_target_states is not None:
                if isinstance(raw_target_states, list):
                    target_states = [str(s) for s in raw_target_states if s]
                else:
                    target_states = (
                        [str(raw_target_states)] if raw_target_states else []
                    )
            elif raw_target_state is not None:
                if isinstance(raw_target_state, list):
                    target_states = [str(s) for s in raw_target_state if s]
                else:
                    target_states = [str(raw_target_state)] if raw_target_state else []

            debug(
                f"🎯 target_states: {target_states}",
                message_logger=context.message_logger,
            )

            if not target_states:
                raise ActionExecutionError(
                    "wait_for_state",
                    "Brak oczekiwanego stanu (klucze: target_state lub target_states)",
                )

            # Pobierz timeout i skonwertuj na sekundy
            timeout_str = action_config.get("timeout", "30s")
            debug(
                f"⏱️ timeout_str: '{timeout_str}'", message_logger=context.message_logger
            )

            timeout_seconds = self._parse_timeout(timeout_str)
            debug(
                f"⏱️ timeout_seconds: {timeout_seconds}",
                message_logger=context.message_logger,
            )

            # Określ komponenty docelowe (używamy tej samej logiki co send_command)
            debug(
                f"🔍 Resolving target clients...", message_logger=context.message_logger
            )
            target_clients = self._resolve_target_clients(action_config, context)
            debug(
                f"👥 target_clients: {target_clients}",
                message_logger=context.message_logger,
            )

            if not target_clients:
                raise ActionExecutionError(
                    "wait_for_state", "Nie znaleziono klientów docelowych"
                )

            info(
                f"Oczekiwanie na stan(y) {target_states} dla serwisów: {target_clients} (timeout: {timeout_seconds}s)",
                message_logger=context.message_logger,
            )

            # Wykonaj oczekiwanie z timeout
            debug(
                f"🚀 Rozpoczynam asyncio.wait_for...",
                message_logger=context.message_logger,
            )
            try:
                await asyncio.wait_for(
                    self._wait_for_clients_state(
                        target_clients, target_states, context
                    ),
                    timeout=timeout_seconds,
                )

                info(
                    f"Wszystkie serwisy osiągnęły jeden z oczekiwanych stanów {target_states}",
                    message_logger=context.message_logger,
                )

            except asyncio.TimeoutError:
                debug(
                    f"💥 asyncio.TimeoutError po {timeout_seconds}s",
                    message_logger=context.message_logger,
                )
                # Timeout - wykonaj akcje on_failure jeśli są zdefiniowane
                await self._handle_timeout(
                    action_config, target_clients, target_states, context
                )

        except Exception as e:
            debug(
                f"💥 Exception w wait_for_state execute: {e}",
                message_logger=context.message_logger,
            )
            if isinstance(e, ActionExecutionError):
                raise
            raise ActionExecutionError(
                "wait_for_state", f"Błąd podczas oczekiwania na stan: {str(e)}", e
            )

    def _resolve_target_clients(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> List[str]:
        """
        Rozwiązuje serwisy docelowe na podstawie selektorów.
        Używa tej samej logiki co SendCommandAction.
        """
        target_clients = []

        # Sprawdź selektor "@all"
        if "target" in action_config and action_config["target"] == "@all":
            target_clients.extend(context.clients)

        # Sprawdź pojedynczy serwis
        elif "client" in action_config and action_config["client"]:
            client_name = self._resolve_template_variables(
                action_config["client"], context
            )
            target_clients.append(client_name)

        # Sprawdź pojedynczą grupę
        elif "group" in action_config and action_config["group"]:
            group_name = action_config["group"]
            target_clients.extend(
                self._get_clients_by_group(group_name, context.orchestrator)
            )

        # Sprawdź wiele grup
        elif "groups" in action_config and action_config["groups"]:
            groups = action_config["groups"]
            if isinstance(groups, list):
                for group_name in groups:
                    target_clients.extend(
                        self._get_clients_by_group(group_name, context.orchestrator)
                    )

        # Usunięcie duplikatów
        target_clients = list(set(target_clients))

        # Opcjonalna filtracja po stanie FSM
        try:
            state_in = action_config.get("state_in")
            state_not_in = action_config.get("state_not_in")

            if isinstance(state_in, str):
                state_in = [state_in]
            if isinstance(state_not_in, str):
                state_not_in = [state_not_in]

            if state_in:
                target_clients = [
                    client_name
                    for client_name in target_clients
                    if context.orchestrator._state.get(client_name, {}).get("fsm_state")
                    in set(state_in)
                ]

            if state_not_in:
                excluded = set(state_not_in)
                target_clients = [
                    client_name
                    for client_name in target_clients
                    if context.orchestrator._state.get(client_name, {}).get("fsm_state")
                    not in excluded
                ]
        except Exception:
            # Jeśli coś pójdzie nie tak z filtracją, zwróć niefiltrowaną listę
            pass

        return target_clients

    def _get_clients_by_group(self, group_name: str, orchestrator) -> List[str]:
        """Pobiera serwisy należące do określonej grupy."""
        clients = []
        config = orchestrator._configuration.get("clients", {})

        for client_name, client_config in config.items():
            if client_config.get("group") == group_name:
                clients.append(client_name)

        return clients

    def _get_all_clients(self, orchestrator) -> List[str]:
        """Pobiera wszystkie zarejestrowane serwisy."""
        config = orchestrator._configuration.get("clients", {})
        return list(config.keys())

    async def _wait_for_clients_state(
        self, clients: List[str], target_states: List[str], context: ScenarioContext
    ) -> None:
        """
        Czeka aż wszystkie serwisy osiągną określony stan.

        Args:
            clients: Lista nazw serwisów
            target_state: Oczekiwany stan
            context: Kontekst wykonania
        """
        info(
            f"🔍 _wait_for_clients_state: ROZPOCZĘCIE - czekam na jeden ze stanów {target_states} dla {len(clients)} klientów: {clients}",
            message_logger=context.message_logger,
        )

        debug(
            f"🔍 wait_for_state: Czekam na stan(y) {target_states} dla {len(clients)} klientów: {clients}",
            message_logger=context.message_logger,
        )

        iteration = 0
        while True:
            iteration += 1

            # Sprawdź stan wszystkich serwisów
            all_ready = True
            states_info = []

            for client_name in clients:
                # Pobierz aktualny stan serwisu z orchestratora
                client_state = context.orchestrator._state.get(client_name, {})
                current_fsm_state = client_state.get("fsm_state", "UNKNOWN")

                states_info.append(f"{client_name}={current_fsm_state}")

                if current_fsm_state not in set(target_states):
                    all_ready = False

            debug(
                f"🔍 wait_for_state iteracja {iteration}: {', '.join(states_info)} | Wszystkie gotowe: {all_ready}",
                message_logger=context.message_logger,
            )

            if all_ready:
                info(
                    f"✅ wait_for_state: Wszystkie klienty osiągnęły jeden z oczekiwanych stanów {target_states}: {', '.join(states_info)}",
                    message_logger=context.message_logger,
                )
                break

            # Czekaj krótko przed następnym sprawdzeniem
            await asyncio.sleep(1.0)

    async def _handle_timeout(
        self,
        action_config: Dict[str, Any],
        clients: List[str],
        target_states: List[str],
        context: ScenarioContext,
    ) -> None:
        """
        Obsługuje timeout - loguje błąd i wykonuje akcje on_failure jeśli są zdefiniowane.

        Args:
            action_config: Konfiguracja akcji
            clients: Lista serwisów które nie osiągnęły stanu
            target_state: Oczekiwany stan
            context: Kontekst wykonania

        Raises:
            ActionExecutionError: Po wykonaniu akcji on_failure (lub od razu jeśli ich nie ma)
        """
        timeout_message = (
            f"Timeout oczekiwania na stan(y) {target_states} dla serwisów: {clients}"
        )
        error(timeout_message, message_logger=context.message_logger)

        # Sprawdź czy są zdefiniowane akcje on_failure
        on_failure_actions = action_config.get("on_failure", [])

        if on_failure_actions and isinstance(on_failure_actions, list):
            warning(
                "Wykonywanie akcji on_failure po timeout",
                message_logger=context.message_logger,
            )

            # Wykonaj każdą akcję on_failure
            for failure_action in on_failure_actions:
                try:
                    # Tu potrzebujemy dostępu do ActionExecutor z Orchestratora
                    await context.orchestrator._execute_action(failure_action, context)
                except Exception as e:
                    error(
                        f"Błąd wykonywania akcji on_failure: {e}",
                        message_logger=context.message_logger,
                    )

        # Po wykonaniu akcji on_failure nadal rzucamy wyjątek
        raise ActionExecutionError("wait_for_state", timeout_message)
