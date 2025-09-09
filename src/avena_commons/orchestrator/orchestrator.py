"""Moduł Orchestrator.

Odpowiedzialność:
- Ładowanie, rejestracja i sortowanie scenariuszy, akcji, warunków
- Harmonogram i współbieżne wykonywanie scenariuszy z limitami
- Integracja z komponentami zewnętrznymi i klientami (monitoring stanu)

Eksponuje:
- Klasa `Orchestrator`
"""

import asyncio
import importlib
import inspect
import json
import traceback
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from avena_commons.event_listener.event import Event
from avena_commons.event_listener.event_listener import (
    EventListener,
    EventListenerState,
)
from avena_commons.util.logger import MessageLogger, debug, error, info, warning

# Import nowego systemu akcji
from .actions import ActionContext, ActionExecutionError, ActionExecutor
from .actions.base_action import BaseAction
from .base.base_condition import BaseCondition

# Import komponentów
from .components import DatabaseComponent, LynxAPIComponent

# Import nowego systemu warunków
from .factories.condition_factory import ConditionFactory

# Import modeli pydantic
from .models import ScenarioModel


class Orchestrator(EventListener):
    """
    Orchestrator sterujący wykonywaniem scenariuszy zdarzeniowych.

    Odpowiada za:
    - ładowanie i sortowanie scenariuszy,
    - rejestrację i wykonywanie akcji,
    - ładowanie, rejestrację i ewaluację warunków,
    - zarządzanie komponentami zewnętrznymi (np. bazami danych),
    - harmonogram i współbieżne uruchamianie scenariuszy z limitami.

    Współpracuje z `EventListener`, nasłuchując i interpretując zdarzenia systemowe.

    Przykład:
        >>> orch = Orchestrator(name="orch", port=5000, address="127.0.0.1")
    """

    def __init__(
        self,
        name: str,
        port: int,
        address: str,
        message_logger: MessageLogger | None = None,
        debug: bool = True,
    ):
        """
        Inicjalizuje instancję Orchestratora.

        Args:
            name (str): Unikalna nazwa instancji.
            port (int): Port nasłuchu komponentu.
            address (str): Adres IP lub host do komunikacji.
            message_logger (MessageLogger | None): Opcjonalny logger komunikatów.
            debug (bool): Czy włączyć tryb debug (domyślnie True).

        Raises:
            Exception: Błędy inicjalizacji zależności lub ładowania modułów.
        """
        self._message_logger = message_logger
        self._debug = debug

        # Konfiguracja domyślna z komponentami systemu
        self._default_configuration = {
            "clients": {},
            "components": {},  # Komponenty zewnętrzne (bazy danych)
            # Systemowe źródła (built-in z paczki)
            "builtin_scenarios_directory": str(Path(__file__).parent / "scenarios"),
            "builtin_actions_directory": str(Path(__file__).parent / "actions"),
            "builtin_conditions_directory": str(Path(__file__).parent / "conditions"),
            # Źródła użytkownika (z JSON) - opcjonalne
            "scenarios_directory": None,  # Użytkownik może nadpisać w JSON
            "actions_directory": None,  # Użytkownik może nadpisać w JSON
            "conditions_directory": None,  # Użytkownik może nadpisać w JSON
            # Limity wykonywania scenariuszy
            "max_concurrent_scenarios": 1,  # Maksymalna liczba jednoczesnych scenariuszy (domyślnie 1)
            # Konfiguracja SMTP dla akcji send_email (globalna)
            "smtp": {
                "host": "",
                "port": 587,
                "username": "",
                "password": "",
                "starttls": False,
                "tls": False,
                "from": "",
                # Maksymalna liczba kolejnych błędów ActionExecutionError
                # po której wysyłka e-maili będzie ignorowana (4. i kolejne próby)
                # Wartość <= 0 wyłącza ten limit
                "max_error_attempts": 3,
            },
            # Konfiguracja SMS dla akcji send_sms (globalna)
            "sms": {
                "enabled": False,
                "url": "",
                "login": "",
                "password": "",
                "cert_path": "",
                "serviceId": 0,
                "source": "",
                # Maksymalna liczba kolejnych błędów ActionExecutionError
                # po której wysyłka SMS będzie ignorowana (4. i kolejne próby)
                # Wartość <= 0 wyłącza ten limit
                "max_error_attempts": 3,
            },
        }

        self._scenarios = OrderedDict()
        self._scenario_last_execution = {}
        self._autonomous_execution_history = []

        # Tracking aktywnych scenariuszy - zabezpieczenie przed wielokrotnym uruchamianiem
        self._running_scenarios: Dict[str, asyncio.Task] = {}
        self._scenario_execution_count: Dict[str, int] = {}

        # NOWE: Liczniki wykonań scenariuszy dla systemu blokowania po przekroczeniu limitu
        self._scenario_execution_counters: Dict[str, int] = {}
        # Flagi scenariuszy zablokowanych do ACK
        self._blocked_scenarios: Dict[str, bool] = {}

        # Komponenty zewnętrzne (bazy danych, API)
        self._components: Dict[str, Any] = {}

        self._action_executor = ActionExecutor(
            register_default_actions=False
        )  # Nowy system akcji - akcje będą ładowane dynamicznie
        # self._autonomous_manager = AutonomousManager(
        #     self, self._message_logger
        # )  # System autonomiczny

        # Globalne liczniki kolejnych błędów akcji (wg typu akcji)
        # Klucze: np. "send_sms", "send_email"
        self._action_error_counts: Dict[str, int] = {}

        try:
            super().__init__(
                name=name,
                port=port,
                address=address,
                message_logger=self._message_logger,
            )
            # self._load_actions()  # Wczytaj dynamiczne akcje
            self._load_conditions()  # Wczytaj warunki systemowe i użytkownika
            # self._load_scenarios()
        except Exception as e:
            error(f"Initialisation error: {e}", message_logger=self._message_logger)

    # ==== Liczniki błędów akcji (globalne) ====
    def get_action_error_count(self, action_type: str) -> int:
        """Zwróć liczbę kolejnych błędów dla danego typu akcji."""
        return int(self._action_error_counts.get(action_type, 0))

    def increment_action_error_count(self, action_type: str) -> int:
        """Zwiększ licznik kolejnych błędów dla danego typu akcji i zwróć aktualną wartość."""
        current = int(self._action_error_counts.get(action_type, 0)) + 1
        self._action_error_counts[action_type] = current
        return current

    def reset_action_error_count(self, action_type: str) -> None:
        """Wyzeruj licznik kolejnych błędów dla danego typu akcji."""
        if action_type in self._action_error_counts:
            del self._action_error_counts[action_type]

    def should_skip_action_due_to_errors(
        self, action_type: str, max_attempts: int
    ) -> bool:
        """
        Zwróć True, jeżeli należy pominąć wykonanie akcji z powodu przekroczenia
        dozwolonej liczby kolejnych błędów (max_attempts > 0 i count >= max_attempts).
        """
        if max_attempts is None:
            return False
        try:
            max_attempts_int = int(max_attempts)
        except Exception:
            max_attempts_int = 0
        if max_attempts_int <= 0:
            return False
        return self.get_action_error_count(action_type) >= max_attempts_int

    # ==== Liczniki wykonań scenariuszy ====
    def get_scenario_execution_count(self, scenario_name: str) -> int:
        """Zwraca liczbę wykonań scenariusza od ostatniego ACK."""
        return self._scenario_execution_counters.get(scenario_name, 0)

    def increment_scenario_execution_count(self, scenario_name: str) -> int:
        """Zwiększa licznik wykonań scenariusza i zwraca aktualną wartość."""
        current = self._scenario_execution_counters.get(scenario_name, 0) + 1
        self._scenario_execution_counters[scenario_name] = current
        return current

    def reset_scenario_execution_count(self, scenario_name: str) -> None:
        """Resetuje licznik wykonań scenariusza po ACK."""
        if scenario_name in self._scenario_execution_counters:
            del self._scenario_execution_counters[scenario_name]
        if scenario_name in self._blocked_scenarios:
            del self._blocked_scenarios[scenario_name]
        info(
            f"🔁 Reset licznika wykonań dla scenariusza: {scenario_name}",
            message_logger=self._message_logger,
        )

    def reset_all_scenario_execution_counters(self) -> None:
        """Resetuje wszystkie liczniki wykonań scenariuszy po ACK."""
        reset_count = len(self._scenario_execution_counters) + len(self._blocked_scenarios)
        self._scenario_execution_counters.clear()
        self._blocked_scenarios.clear()
        if reset_count > 0:
            info(
                f"🔁 Reset wszystkich liczników scenariuszy ({reset_count} scenariuszy)",
                message_logger=self._message_logger,
            )

    def is_scenario_blocked(self, scenario_name: str) -> bool:
        """Sprawdza czy scenariusz jest zablokowany z powodu przekroczenia limitu."""
        return self._blocked_scenarios.get(scenario_name, False)

    def should_block_scenario_due_to_limit(self, scenario_name: str, max_executions: Optional[int]) -> bool:
        """
        Sprawdza czy scenariusz powinien być zablokowany z powodu przekroczenia limitu wykonań.
        
        Args:
            scenario_name: Nazwa scenariusza
            max_executions: Limit wykonań (None = bez limitu)
            
        Returns:
            True jeśli scenariusz powinien być zablokowany, False w przeciwnym razie
        """
        if max_executions is None or max_executions <= 0:
            return False
            
        current_count = self.get_scenario_execution_count(scenario_name)
        should_block = current_count >= max_executions
        
        if should_block and not self.is_scenario_blocked(scenario_name):
            # Pierwszy raz przekraczamy limit - zablokuj scenariusz
            self._blocked_scenarios[scenario_name] = True
            warning(
                f"🚫 BLOKADA scenariusza '{scenario_name}' - przekroczono limit {max_executions} wykonań "
                f"(aktualnie: {current_count}). Wymagane ACK do odblokowania.",
                message_logger=self._message_logger,
            )
            
        return should_block

    def get_scenarios_execution_status(self) -> Dict[str, Any]:
        """
        Zwraca status wykonań scenariuszy z informacjami o licznikach i blokadach.
        
        Returns:
            Słownik ze statusem wykonań wszystkich scenariuszy
        """
        status = {}
        
        for scenario_name, scenario in self._scenarios.items():
            # Pobierz limit z modelu scenariusza
            max_executions = scenario.get("max_executions")
            current_count = self.get_scenario_execution_count(scenario_name)
            is_blocked = self.is_scenario_blocked(scenario_name)
            
            status[scenario_name] = {
                "max_executions": max_executions,
                "current_executions": current_count,
                "is_blocked": is_blocked,
                "can_execute": not is_blocked and (max_executions is None or current_count < max_executions),
            }
            
        return status

    def _load_scenarios(self):
        """
        Ładuje scenariusze z dwóch źródeł:
        1. Systemowe (built-in) z paczki - zdefiniowane w _default_configuration
        2. Użytkownika (custom) z JSON - opcjonalne dodatkowe scenariusze

        Każdy scenariusz musi być w oddzielnym pliku JSON.
        """
        try:
            self._scenarios = OrderedDict()

            # KROK 1: Wczytaj systemowe scenariusze (built-in)
            builtin_dir = self._configuration.get("builtin_scenarios_directory")
            if builtin_dir:
                builtin_path = Path(builtin_dir)
                self._load_scenarios_from_directory(builtin_path, "systemowe")

            # KROK 2: Wczytaj scenariusze użytkownika (custom)
            custom_dir = self._configuration.get("scenarios_directory")
            if custom_dir:
                custom_path = Path(custom_dir)
                if custom_path.exists():
                    self._load_scenarios_from_directory(custom_path, "użytkownika")
                else:
                    warning(
                        f"Katalog scenariuszy użytkownika {custom_path} nie istnieje (pomijam)",
                        message_logger=self._message_logger,
                    )

            # Podsumowanie
            loaded_count = len(self._scenarios)
            if loaded_count > 0:
                info(
                    f"🎯 Łącznie załadowanych scenariuszy: {loaded_count}",
                    message_logger=self._message_logger,
                )
                for i, (scenario_name, scenario_data) in enumerate(
                    self._scenarios.items(), 1
                ):
                    source = scenario_data.get("_source", "unknown")
                    info(
                        f"   {i}. {scenario_name} ({source})",
                        message_logger=self._message_logger,
                    )

                # Sortuj scenariusze według priorytetu po załadowaniu
                self._sort_scenarios_by_priority()

            else:
                warning(
                    "⚠️ Nie załadowano żadnych scenariuszy",
                    message_logger=self._message_logger,
                )

        except Exception as e:
            error(
                f"❌ Błąd ładowania scenariuszy: {e}",
                message_logger=self._message_logger,
            )
            error(
                f"Traceback: {traceback.format_exc()}",
                message_logger=self._message_logger,
            )

    def _load_conditions(self):
        """
        Ładuje warunki z dwóch źródeł:
        1. Systemowe (built-in) z paczki - zdefiniowane w _default_configuration
        2. Użytkownika (custom) z JSON - opcjonalne dodatkowe warunki

        Każdy warunek musi być w oddzielnym pliku Python.
        """
        try:
            info(
                "🔧 Rozpoczynam ładowanie warunków...",
                message_logger=self._message_logger,
            )

            # KROK 1: Wczytaj systemowe warunki (built-in)
            builtin_dir = self._configuration.get("builtin_conditions_directory")
            if builtin_dir:
                builtin_path = Path(builtin_dir)
                self._load_conditions_from_directory(builtin_path, "systemowe")

            # KROK 2: Wczytaj warunki użytkownika (custom)
            custom_dir = self._configuration.get("conditions_directory")
            if custom_dir:
                custom_path = Path(custom_dir)
                if custom_path.exists():
                    self._load_conditions_from_directory(custom_path, "użytkownika")
                else:
                    warning(
                        f"Katalog warunków użytkownika {custom_path} nie istnieje (pomijam)",
                        message_logger=self._message_logger,
                    )

            # Podsumowanie
            registered_conditions = ConditionFactory.get_registered_conditions()
            if registered_conditions:
                info(
                    f"🎯 Łącznie zarejestrowanych warunków: {len(registered_conditions)}",
                    message_logger=self._message_logger,
                )
                for i, condition_name in enumerate(registered_conditions, 1):
                    info(
                        f"   {i}. {condition_name}",
                        message_logger=self._message_logger,
                    )
            else:
                warning(
                    "⚠️ Nie załadowano żadnych warunków",
                    message_logger=self._message_logger,
                )

        except Exception as e:
            error(
                f"❌ Błąd ładowania warunków: {e}",
                message_logger=self._message_logger,
            )
            error(
                f"Traceback: {traceback.format_exc()}",
                message_logger=self._message_logger,
            )

    def _load_components(self):
        """
        Ładuje komponenty zewnętrzne z konfiguracji.

        Na razie obsługujemy tylko komponenty typu database.
        """
        try:
            info(
                "🔧 Rozpoczynam ładowanie komponentów...",
                message_logger=self._message_logger,
            )

            components_config = self._configuration.get("components", {})
            if not components_config:
                info(
                    "ℹ️ Brak komponentów w konfiguracji",
                    message_logger=self._message_logger,
                )
                return

            info(
                f"Znaleziono {len(components_config)} komponentów do załadowania: {list(components_config.keys())}",
                message_logger=self._message_logger,
            )

            # Wczytaj każdy komponent
            for component_name, component_config in components_config.items():
                try:
                    component_type = component_config.get(
                        "type", "database"
                    )  # Domyślnie database

                    if component_type == "database":
                        info(
                            f"🔧 Ładowanie komponentu bazodanowego: {component_name}",
                            message_logger=self._message_logger,
                        )

                        # Utwórz komponent bazodanowy
                        component = DatabaseComponent(
                            name=component_name,
                            config=component_config,
                            message_logger=self._message_logger,
                        )

                        # Zapisz komponent
                        self._components[component_name] = component

                        info(
                            f"✅ Komponent bazodanowy '{component_name}' załadowany",
                            message_logger=self._message_logger,
                        )

                    elif component_type == "lynx_api":
                        info(
                            f"🔧 Ładowanie komponentu Lynx API: {component_name}",
                            message_logger=self._message_logger,
                        )

                        # Utwórz komponent Lynx API
                        component = LynxAPIComponent(
                            name=component_name,
                            config=component_config,
                            message_logger=self._message_logger,
                        )

                        # Zapisz komponent
                        self._components[component_name] = component

                        info(
                            f"✅ Komponent Lynx API '{component_name}' załadowany",
                            message_logger=self._message_logger,
                        )

                    else:
                        warning(
                            f"⚠️ Nieznany typ komponentu '{component_type}' dla '{component_name}' - pomijam",
                            message_logger=self._message_logger,
                        )

                except Exception as e:
                    error(
                        f"❌ Błąd ładowania komponentu '{component_name}': {e}",
                        message_logger=self._message_logger,
                    )
                    # Kontynuuj z innymi komponentami
                    continue

            # Podsumowanie
            loaded_count = len(self._components)
            if loaded_count > 0:
                info(
                    f"🎯 Łącznie załadowanych komponentów: {loaded_count}",
                    message_logger=self._message_logger,
                )
                for i, component_name in enumerate(self._components.keys(), 1):
                    info(
                        f"   {i}. {component_name} (database)",
                        message_logger=self._message_logger,
                    )
            else:
                warning(
                    "⚠️ Nie załadowano żadnych komponentów",
                    message_logger=self._message_logger,
                )

        except Exception as e:
            error(
                f"❌ Błąd ładowania komponentów: {e}",
                message_logger=self._message_logger,
            )
            error(
                f"Traceback: {traceback.format_exc()}",
                message_logger=self._message_logger,
            )

    async def _initialize_components(self):
        """
        Inicjalizuje wszystkie załadowane komponenty.

        Wywołuje initialize() i connect() na każdym komponencie.
        """
        if not self._components:
            info(
                "ℹ️ Brak komponentów do inicjalizacji",
                message_logger=self._message_logger,
            )
            return

        info(
            f"🚀 Inicjalizacja {len(self._components)} komponentów...",
            message_logger=self._message_logger,
        )

        failed_components = []

        for component_name, component in self._components.items():
            try:
                info(
                    f"🔧 Inicjalizacja komponentu: {component_name}",
                    message_logger=self._message_logger,
                )

                # KROK 1: Inicjalizacja (walidacja konfiguracji)
                if not await component.initialize():
                    error(
                        f"❌ Inicjalizacja komponentu '{component_name}' nie powiodła się",
                        message_logger=self._message_logger,
                    )
                    failed_components.append(component_name)
                    continue

                # KROK 2: Nawiązanie połączenia
                if not await component.connect():
                    error(
                        f"❌ Połączenie komponentu '{component_name}' nie powiodło się",
                        message_logger=self._message_logger,
                    )
                    failed_components.append(component_name)
                    continue

                # KROK 3: Health check
                if not await component.health_check():
                    warning(
                        f"⚠️ Health check komponentu '{component_name}' nie powiódł się",
                        message_logger=self._message_logger,
                    )
                    # Nie usuwamy komponentu - może się naprawić później

                info(
                    f"✅ Komponent '{component_name}' zainicjalizowany i połączony",
                    message_logger=self._message_logger,
                )

            except Exception as e:
                error(
                    f"❌ Błąd inicjalizacji komponentu '{component_name}': {e}",
                    message_logger=self._message_logger,
                )
                failed_components.append(component_name)

        # Usuń komponenty które nie mogły się zainicjalizować
        for component_name in failed_components:
            if component_name in self._components:
                error(
                    f"🗑️ Usuwanie nieudanego komponentu: {component_name}",
                    message_logger=self._message_logger,
                )
                del self._components[component_name]

        # Podsumowanie
        successful_count = len(self._components)
        failed_count = len(failed_components)

        if successful_count > 0:
            info(
                f"🎯 Pomyślnie zainicjalizowanych komponentów: {successful_count}",
                message_logger=self._message_logger,
            )

        if failed_count > 0:
            warning(
                f"⚠️ Komponenty które nie mogły się zainicjalizować: {failed_count} ({failed_components})",
                message_logger=self._message_logger,
            )

    async def _disconnect_components(self):
        """
        Rozłącza wszystkie komponenty podczas zamykania orchestratora.
        """
        if not self._components:
            return

        info(
            f"🔌 Rozłączanie {len(self._components)} komponentów...",
            message_logger=self._message_logger,
        )

        for component_name, component in self._components.items():
            try:
                await component.disconnect()
                info(
                    f"✅ Komponent '{component_name}' rozłączony",
                    message_logger=self._message_logger,
                )
            except Exception as e:
                error(
                    f"❌ Błąd rozłączania komponentu '{component_name}': {e}",
                    message_logger=self._message_logger,
                )

        self._components.clear()

    def get_components_status(self) -> Dict[str, Any]:
        """
        Zwraca status wszystkich komponentów.

        Returns:
            Słownik ze statusem komponentów
        """
        components_status = {}

        for component_name, component in self._components.items():
            components_status[component_name] = component.get_status()

        return {
            "total_components": len(self._components),
            "components": components_status,
        }

    def _load_scenarios_from_directory(self, scenarios_dir: Path, source_type: str):
        """Ładuje scenariusze z konkretnego katalogu."""
        if not scenarios_dir.exists():
            warning(
                f"Katalog scenariuszy {source_type} {scenarios_dir} nie istnieje",
                message_logger=self._message_logger,
            )
            return

        info(
            f"Wczytywanie scenariuszy {source_type} z katalogu: {scenarios_dir}",
            message_logger=self._message_logger,
        )

        # Znajdź wszystkie pliki *.json
        json_files = list(scenarios_dir.glob("*.json"))

        if not json_files:
            warning(
                f"Nie znaleziono plików JSON w katalogu {source_type} {scenarios_dir}",
                message_logger=self._message_logger,
            )
            return

        info(
            f"Znaleziono {len(json_files)} plików scenariuszy {source_type}: {[f.name for f in json_files]}",
            message_logger=self._message_logger,
        )

        # Wczytaj każdy plik JSON jako scenariusz
        for json_file in json_files:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    scenario_data = json.load(f)

                # Waliduj scenariusz przez Pydantic
                try:
                    scenario_model = ScenarioModel(**scenario_data)

                    # Dodaj informację o źródle
                    scenario_dict = scenario_model.dict()
                    scenario_dict["_source"] = source_type

                    # Zapisz walidowany scenariusz
                    scenario_name = scenario_model.name

                    # Sprawdź czy scenariusz już istnieje (custom może nadpisać systemowy)
                    if scenario_name in self._scenarios:
                        existing_source = self._scenarios[scenario_name].get(
                            "_source", "unknown"
                        )
                        info(
                            f"   ⚠️ Scenariusz '{scenario_name}' z {source_type} nadpisuje istniejący z {existing_source}",
                            message_logger=self._message_logger,
                        )

                    # Ustaw wewnętrzną flagę dla scenariuszy manualnych (domyślnie False)
                    try:
                        trigger_cfg = scenario_dict.get("trigger", {}) or {}
                        trigger_type = str(trigger_cfg.get("type", "")).lower()
                        if trigger_type == "manual":
                            internal = scenario_dict.setdefault("_internal", {})
                            # Zachowaj istniejącą wartość jeśli już była ustawiona (np. przy reload)
                            internal["manual_run_requested"] = bool(
                                internal.get("manual_run_requested", False)
                            )
                    except Exception:
                        # Nie blokuj ładowania scenariuszy w razie problemów z flagą wewnętrzną
                        error(
                            f"Błąd podczas ustawiania flagi manual_run_requested dla scenariusza {scenario_name}: {e}",
                            message_logger=self._message_logger,
                        )

                    self._scenarios[scenario_name] = scenario_dict

                    info(
                        f"✅ Załadowano scenariusz {source_type}: '{scenario_name}' z pliku {json_file.name}",
                        message_logger=self._message_logger,
                    )

                    # Dodatkowe informacje o scenariuszu
                    if scenario_model.description:
                        info(
                            f"   📝 Opis: {scenario_model.description}",
                            message_logger=self._message_logger,
                        )

                    if scenario_model.tags:
                        info(
                            f"   🏷️ Tagi: {', '.join(scenario_model.tags)}",
                            message_logger=self._message_logger,
                        )

                    actions_count = len(scenario_model.actions)
                    info(
                        f"   ⚙️ Akcji: {actions_count}",
                        message_logger=self._message_logger,
                    )

                except Exception as validation_error:
                    error(
                        f"❌ Błąd walidacji scenariusza {source_type} w {json_file}: {validation_error}",
                        message_logger=self._message_logger,
                    )
                    continue

            except json.JSONDecodeError as json_error:
                error(
                    f"❌ Błąd parsowania JSON {source_type} w {json_file}: {json_error}",
                    message_logger=self._message_logger,
                )
            except Exception as e:
                error(
                    f"❌ Błąd ładowania scenariusza {source_type} z {json_file}: {e}",
                    message_logger=self._message_logger,
                )

    def _load_conditions_from_directory(self, conditions_dir: Path, source_type: str):
        """Ładuje warunki z konkretnego katalogu."""
        if not conditions_dir.exists():
            warning(
                f"Katalog warunków {source_type} {conditions_dir} nie istnieje",
                message_logger=self._message_logger,
            )
            return

        info(
            f"Wczytywanie warunków {source_type} z katalogu: {conditions_dir}",
            message_logger=self._message_logger,
        )

        # Znajdź wszystkie pliki *.py (oprócz __init__.py)
        py_files = [f for f in conditions_dir.glob("*.py") if f.name != "__init__.py"]

        if not py_files:
            warning(
                f"Nie znaleziono plików Python w katalogu {source_type} {conditions_dir}",
                message_logger=self._message_logger,
            )
            return

        info(
            f"Znaleziono {len(py_files)} plików warunków {source_type}: {[f.name for f in py_files]}",
            message_logger=self._message_logger,
        )
        # Wczytaj każdy plik Python jako moduł
        for py_file in py_files:
            try:
                # Importuj moduł - różne ścieżki dla systemowych i użytkownika
                if source_type == "systemowe":
                    module_name = (
                        f"avena_commons.orchestrator.conditions.{py_file.stem}"
                    )
                else:
                    custom_dir = (
                        str(conditions_dir)
                        .replace("\\", "/")
                        .strip("/")
                        .replace("/", ".")
                    )
                    module_name = f"{custom_dir}.{py_file.stem}"

                module = importlib.import_module(module_name)

                # Znajdź klasy warunków w module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        inspect.isclass(attr)
                        and issubclass(attr, BaseCondition)
                        and attr != BaseCondition
                    ):
                        # Zarejestruj w fabryce
                        condition_name = attr_name.replace("Condition", "").lower()
                        ConditionFactory.register_condition_type(condition_name, attr)

                        info(
                            f"✅ Zarejestrowano warunek {source_type}: {condition_name} ({attr_name})",
                            message_logger=self._message_logger,
                        )

            except Exception as e:
                error(
                    f"❌ Błąd ładowania warunku {source_type} z {py_file}: {e}",
                    message_logger=self._message_logger,
                )

    def _sort_scenarios_by_priority(self):
        """
        Sortuje scenariusze według priorytetu (od najwyższego do najniższego).

        Sprawdza priorytet w dwóch formatach:
        1. Na poziomie głównym: scenario["priority"]
        2. W trigger.conditions: scenario["trigger"]["conditions"]["priority"] (kompatybilność wsteczna)
        """

        def get_scenario_priority(scenario_item):
            scenario_name, scenario = scenario_item

            # Sprawdź priorytet na poziomie głównym (nowy format)
            priority = scenario.get("priority")

            if priority is not None:
                return priority

            # Sprawdź priorytet w trigger.conditions (stary format - dla kompatybilności)
            trigger = scenario.get("trigger", {})
            conditions = trigger.get("conditions", {})
            return conditions.get("priority", 0)  # Domyślny priorytet = 0

        # Sortuj scenariusze według priorytetu
        sorted_scenarios = sorted(
            self._scenarios.items(),
            key=get_scenario_priority,
            reverse=False,  # Od najniższego do najwyższego
        )

        # Utwórz nowy OrderedDict z posortowanymi scenariuszami
        self._scenarios = OrderedDict(sorted_scenarios)

        # Debug log
        priorities_info = [
            (name, get_scenario_priority((name, scenario)))
            for name, scenario in self._scenarios.items()
        ]
        info(
            f"📋 Scenariusze posortowane według priorytetu: {priorities_info}",
            message_logger=self._message_logger,
        )

    def _load_actions(self):
        """
        Wczytuje akcje z dwóch źródeł:
        1. Systemowe (built-in) z paczki - zdefiniowane w _default_configuration
        2. Użytkownika (custom) z JSON - opcjonalne dodatkowe akcje
        """
        try:
            # KROK 1: Wczytaj systemowe akcje (built-in)
            builtin_dir = self._configuration.get("builtin_actions_directory")
            if builtin_dir:
                builtin_path = Path(builtin_dir)
                self._load_actions_from_directory(builtin_path, "systemowe")

            # KROK 2: Wczytaj akcje użytkownika (custom)
            custom_dir = self._configuration.get("actions_directory")
            if custom_dir:
                custom_path = Path(custom_dir)
                if custom_path.exists():
                    self._load_actions_from_directory(custom_path, "użytkownika")
                else:
                    warning(
                        f"Katalog akcji użytkownika {custom_path} nie istnieje (pomijam)",
                        message_logger=self._message_logger,
                    )

            # Podsumowanie
            registered_actions = self._action_executor.get_registered_actions()
            info(
                f"Łącznie zarejestrowano {len(registered_actions)} akcji: {list(registered_actions.keys())}",
                message_logger=self._message_logger,
            )

        except Exception as e:
            error(f"Błąd ładowania akcji: {e}", message_logger=self._message_logger)

    def _load_actions_from_directory(self, actions_dir: Path, source_type: str):
        """Ładuje akcje z konkretnego katalogu."""
        if not actions_dir.exists():
            warning(
                f"Katalog akcji {source_type} {actions_dir} nie istnieje",
                message_logger=self._message_logger,
            )
            return

        info(
            f"Wczytywanie akcji {source_type} z katalogu: {actions_dir}",
            message_logger=self._message_logger,
        )

        # Znajdź wszystkie pliki *_action.py (oprócz base_action.py)
        action_files = []
        for py_file in actions_dir.glob("*_action.py"):
            if py_file.name != "base_action.py":
                action_files.append(py_file)

        info(
            f"Znaleziono {len(action_files)} plików z akcjami {source_type}: {[f.name for f in action_files]}",
            message_logger=self._message_logger,
        )

        # Importuj moduły i znajdź klasy BaseAction
        for action_file in action_files:
            try:
                # Dynamiczny import z odpowiednim modułem bazowym
                if source_type == "systemowe":
                    module_name = (
                        f"avena_commons.orchestrator.actions.{action_file.stem}"
                    )
                else:
                    # Custom actions - import względny do bieżącego katalogu
                    import sys

                    sys.path.insert(0, str(actions_dir.parent))
                    module_name = f"{actions_dir.name}.{action_file.stem}"

                # Dynamiczny import modułu
                action_module = importlib.import_module(module_name)

                # Znajdź wszystkie klasy w module
                for name, obj in inspect.getmembers(action_module, inspect.isclass):
                    # Sprawdź czy klasa dziedziczy po BaseAction i nie jest BaseAction
                    if (
                        issubclass(obj, BaseAction)
                        and obj != BaseAction
                        and obj.__module__ == module_name
                    ):
                        try:
                            # Utwórz instancję akcji
                            action_instance = obj()

                            # Określ typ akcji na podstawie nazwy klasy
                            action_type = self._get_action_type_from_class_name(name)

                            # Sprawdź czy akcja ma zdefiniowaną właściwość action_type
                            if hasattr(action_instance, "action_type"):
                                action_type = action_instance.action_type

                            # Zarejestruj akcję w ActionExecutor
                            self._action_executor.register_action(
                                action_type, action_instance
                            )

                            info(
                                f"Zarejestrowano akcję {source_type}: {action_type} ({name})",
                                message_logger=self._message_logger,
                            )

                        except Exception as e:
                            error(
                                f"Błąd tworzenia instancji akcji {source_type} {name}: {e}",
                                message_logger=self._message_logger,
                            )

            except Exception as e:
                error(
                    f"Błąd importowania modułu akcji {source_type} {action_file}: {e}",
                    message_logger=self._message_logger,
                )

    def _get_action_type_from_class_name(self, class_name: str) -> str:
        """
        Konwertuje nazwę klasy akcji na typ akcji używany w YAML.

        Args:
            class_name: Nazwa klasy akcji (np. "LogAction", "SendCommandAction")

        Returns:
            Typ akcji w formacie snake_case (np. "log_action", "send_command_action")
        """
        # Usuń sufiks "Action" jeśli istnieje
        if class_name.endswith("Action"):
            class_name = class_name[:-6]

        # Konwertuj CamelCase na snake_case
        result = ""
        for i, char in enumerate(class_name):
            if char.isupper() and i > 0:
                result += "_"
            result += char.lower()

        # Dodaj sufiks jeśli potrzebny (dla kompatybilności z istniejącymi typami)
        # np. LogAction -> log_event (zamiast log_action)
        action_type_mapping = {
            "log": "log_event",
            "send_command": "send_command",
            "wait_for_state": "wait_for_state",
            "lynx_refund": "lynx_refund",
        }

        return action_type_mapping.get(result, result)

    def register_action(self, action_type: str, action_instance: BaseAction) -> None:
        """
        Rejestruje nową akcję lub nadpisuje istniejącą.

        Metoda umożliwia dodawanie niestandardowych akcji z zewnątrz orkiestratora.

        Args:
            action_type: Typ akcji używany w YAML (np. "custom_action")
            action_instance: Instancja klasy implementującej BaseAction
        """
        self._action_executor.register_action(action_type, action_instance)
        info(
            f"Zarejestrowano zewnętrzną akcję: {action_type} ({action_instance.__class__.__name__})",
            message_logger=self._message_logger,
        )

    def get_registered_actions(self) -> Dict[str, BaseAction]:
        """
        Zwraca słownik wszystkich zarejestrowanych akcji.

        Returns:
            Słownik {typ_akcji: instancja_akcji}
        """
        return self._action_executor.get_registered_actions()

    def get_scenarios_status(self) -> Dict[str, Any]:
        """
        Zwraca status wszystkich scenariuszy do monitorowania.

        Returns:
            Słownik ze statusem scenariuszy, aktywnymi taskami i statystykami
        """
        running_scenarios_info = {}
        active_count = 0

        for name, task in self._running_scenarios.items():
            is_running = not task.done()
            if is_running:
                active_count += 1

            running_scenarios_info[name] = {
                "running": is_running,
                "done": task.done(),
                "cancelled": task.cancelled() if hasattr(task, "cancelled") else False,
            }

            # Jeśli task jest zakończony, spróbuj pobrać wynik
            if task.done():
                try:
                    result = task.result()
                    running_scenarios_info[name]["result"] = result
                except Exception as e:
                    running_scenarios_info[name]["exception"] = str(e)

        max_concurrent = self._configuration.get("max_concurrent_scenarios", 1)

        # Informacje o priorytetach scenariuszy
        def get_priority(scenario):
            # Sprawdź priorytet na poziomie głównym (nowy format)
            priority = scenario.get("priority")
            if priority is not None:
                return priority

            # Sprawdź priorytet w trigger.conditions (stary format - dla kompatybilności)
            trigger = scenario.get("trigger", {})
            conditions = trigger.get("conditions", {})
            return conditions.get("priority", 0)  # Domyślny priorytet = 0

        scenarios_priorities = {
            name: get_priority(scenario) for name, scenario in self._scenarios.items()
        }

        return {
            "total_scenarios": len(self._scenarios),
            "running_scenarios": running_scenarios_info,
            "active_scenarios_count": active_count,
            "max_concurrent_scenarios": max_concurrent,
            "can_start_new": active_count < max_concurrent,
            "scenarios_priorities": scenarios_priorities,
            "execution_counts": self._scenario_execution_count.copy(),
            "last_executions": {
                name: time.isoformat()
                for name, time in self._scenario_last_execution.items()
            },
            "execution_history_count": len(self._autonomous_execution_history),
            "scenarios_list": list(self._scenarios.keys()),
            # NOWE: Informacje o licznikach wykonań i blokadach
            "execution_counters": self.get_scenarios_execution_status(),
        }

    def set_manual_scenario_run_requested(
        self, scenario_name: str, value: bool = True
    ) -> bool:
        """
        Ustawia wewnętrzną flagę uruchomienia dla scenariusza manualnego.

        Args:
            scenario_name: Nazwa scenariusza manualnego
            value: Czy oznaczyć scenariusz do uruchomienia (True/False)

        Returns:
            True jeśli ustawiono flagę, False w przeciwnym razie
        """
        if scenario_name not in self._scenarios:
            warning(
                f"Nie znaleziono scenariusza: {scenario_name}",
                message_logger=self._message_logger,
            )
            return False

        scenario = self._scenarios[scenario_name]
        trigger_cfg = scenario.get("trigger", {}) or {}
        trigger_type = str(trigger_cfg.get("type", "")).lower()
        if trigger_type != "manual":
            warning(
                f"Scenariusz '{scenario_name}' nie jest manualny - pomijam ustawienie flagi",
                message_logger=self._message_logger,
            )
            return False

        internal = scenario.setdefault("_internal", {})
        internal["manual_run_requested"] = bool(value)
        info(
            f"Ustawiono manual_run_requested={value} dla scenariusza: {scenario_name}",
            message_logger=self._message_logger,
        )
        return True

    # async def start_autonomous_mode(self):
    #     """
    #     Uruchamia tryb autonomiczny orkiestratora.

    #     W trybie autonomicznym orkiestrator będzie monitorować stan systemu
    #     i automatycznie uruchamiać scenariusze gdy ich warunki są spełnione.
    #     """
    #     info(
    #         "🤖 Uruchamiam tryb autonomiczny orkiestratora",
    #         message_logger=self._message_logger,
    #     )

    #     # Sprawdź czy są scenariusze autonomiczne
    #     autonomous_scenarios = self._autonomous_manager._get_autonomous_scenarios()
    #     if not autonomous_scenarios:
    #         warning(
    #             "⚠️ Brak scenariuszy autonomicznych - tryb autonomiczny bez efektu",
    #             message_logger=self._message_logger,
    #         )
    #     else:
    #         info(
    #             f"🎯 Znaleziono {len(autonomous_scenarios)} scenariuszy autonomicznych:",
    #             message_logger=self._message_logger,
    #         )
    #         for name in autonomous_scenarios.keys():
    #             info(f"   • {name}", message_logger=self._message_logger)

    #     # Uruchom monitoring w tle
    #     asyncio.create_task(self._autonomous_manager.start_autonomous_monitoring())

    # def stop_autonomous_mode(self):
    #     """Zatrzymuje tryb autonomiczny orkiestratora."""
    #     info(
    #         "🛑 Zatrzymuję tryb autonomiczny orkiestratora",
    #         message_logger=self._message_logger,
    #     )
    #     self._autonomous_manager.stop_autonomous_monitoring()

    # def get_autonomous_status(self) -> Dict[str, Any]:
    #     """
    #     Zwraca status trybu autonomicznego.

    #     Returns:
    #         Słownik ze statusem autonomicznym, scenariuszami i historią wykonań
    #     """
    #     return {
    #         "is_running": self._autonomous_manager.is_running,
    #         "monitor_interval_seconds": self._autonomous_manager.monitor_interval,
    #         "scenarios": self._autonomous_manager.get_autonomous_scenarios_status(),
    #         "execution_history": [
    #             {
    #                 "scenario_name": exec.scenario_name,
    #                 "execution_time": exec.execution_time.isoformat(),
    #                 "success": exec.success,
    #             }
    #             for exec in self._autonomous_manager.get_execution_history()[
    #                 -10:
    #             ]  # Ostatnie 10
    #         ],
    #     }

    # async def simulate_component_state(self, component_name: str, state: str):
    #     """
    #     Symuluje stan komponentu dla testowania scenariuszy autonomicznych.

    #     Args:
    #         component_name: Nazwa komponentu
    #         state: Stan do ustawienia (np. "STOPPED", "ERROR", "RUN")
    #     """
    #     if component_name not in self._configuration.get("components", {}):
    #         warning(
    #             f"Nieznany komponent: {component_name}",
    #             message_logger=self._message_logger,
    #         )
    #         return

    #     # Ustaw stan w orkiestratorze
    #     if component_name not in self._state:
    #         self._state[component_name] = {}
    #     self._state[component_name]["fsm_state"] = state

    #     info(
    #         f"🧪 Symulacja: ustawiono {component_name} w stan {state}",
    #         message_logger=self._message_logger,
    #     )

    async def _execute_scenario_with_tracking(
        self, scenario_name: str, trigger_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Wykonuje scenariusz z pełnym tracking i cleanup.

        Args:
            scenario_name: Nazwa scenariusza do wykonania
            trigger_data: Opcjonalne dane z triggera

        Returns:
            True jeśli scenariusz wykonał się pomyślnie, False w przeciwnym razie
        """
        execution_start = datetime.now()

        try:
            info(
                f"▶️ START scenariusza: {scenario_name}",
                message_logger=self._message_logger,
            )
            success = await self.execute_scenario(scenario_name, trigger_data)

            # Zapisz wyniki
            execution_time = datetime.now()
            self._scenario_last_execution[scenario_name] = execution_time
            self._autonomous_execution_history.append({
                "scenario_name": scenario_name,
                "execution_time": execution_time.isoformat(),
                "success": success,
                "duration_seconds": (execution_time - execution_start).total_seconds(),
            })

            # Ogranicz historię do 100 ostatnich
            if len(self._autonomous_execution_history) > 100:
                self._autonomous_execution_history = self._autonomous_execution_history[
                    -100:
                ]

            if success:
                info(
                    f"✅ SUKCES scenariusza: {scenario_name}",
                    message_logger=self._message_logger,
                )
                # Jeśli to scenariusz manualny oznaczony do uruchomienia, zresetuj flagę
                try:
                    scenario = self._scenarios.get(scenario_name, {})
                    trigger_cfg = scenario.get("trigger", {}) or {}
                    trigger_type = str(trigger_cfg.get("type", "")).lower()
                    if trigger_type == "manual":
                        internal = scenario.setdefault("_internal", {})
                        if internal.get("manual_run_requested"):
                            internal["manual_run_requested"] = False
                            debug(
                                f"🔁 Reset manual_run_requested dla scenariusza: {scenario_name}",
                                message_logger=self._message_logger,
                            )
                except Exception:
                    pass
            else:
                warning(
                    f"⚠️ NIEPOWODZENIE scenariusza: {scenario_name}",
                    message_logger=self._message_logger,
                )

            return success

        except Exception as e:
            error(
                f"❌ BŁĄD w scenariuszu {scenario_name}: {e}",
                message_logger=self._message_logger,
            )
            error(
                f"Traceback: {traceback.format_exc()}",
                message_logger=self._message_logger,
            )
            return False

        finally:
            # CLEANUP - zawsze wykonane
            execution_end = datetime.now()
            duration = (execution_end - execution_start).total_seconds()

            info(
                f"🏁 KONIEC scenariusza {scenario_name} (czas: {duration:.2f}s)",
                message_logger=self._message_logger,
            )

            # Usuń z liczników
            if scenario_name in self._scenario_execution_count:
                self._scenario_execution_count[scenario_name] -= 1
                if self._scenario_execution_count[scenario_name] <= 0:
                    del self._scenario_execution_count[scenario_name]

    async def execute_scenario(
        self, scenario_name: str, trigger_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Wykonuje scenariusz o podanej nazwie.

        Args:
            scenario_name: Nazwa scenariusza do wykonania
            trigger_data: Opcjonalne dane z triggera (dla zmiennych szablonowych)

        Returns:
            True jeśli scenariusz wykonał się pomyślnie, False w przeciwnym razie
        """
        debug(
            f"Uruchamiam scenariusz: {scenario_name}",
            message_logger=self._message_logger,
        )
        if scenario_name not in self._scenarios:
            error(
                f"Scenariusz '{scenario_name}' nie został znaleziony",
                message_logger=self._message_logger,
            )
            return False

        scenario = self._scenarios[scenario_name]
        
        # ZWIĘKSZ LICZNIK WYKONAŃ PRZED ROZPOCZĘCIEM
        execution_count = self.increment_scenario_execution_count(scenario_name)
        max_executions = scenario.get("max_executions")
        
        if max_executions is not None:
            info(
                f"Rozpoczynam wykonywanie scenariusza: {scenario_name} "
                f"(wykonanie {execution_count}/{max_executions})",
                message_logger=self._message_logger,
            )
        else:
            info(
                f"Rozpoczynam wykonywanie scenariusza: {scenario_name} "
                f"(wykonanie #{execution_count}, bez limitu)",
                message_logger=self._message_logger,
            )

        # Przygotuj kontekst wykonania
        context = ActionContext(
            orchestrator=self,
            message_logger=self._message_logger,
            trigger_data=trigger_data,
            scenario_name=scenario_name,
        )

        try:
            actions = scenario.get("actions", [])
            for action_config in actions:
                await self._action_executor.execute_action(action_config, context)

            info(
                f"Scenariusz '{scenario_name}' zakończony pomyślnie",
                message_logger=self._message_logger,
            )
            return True

        except ActionExecutionError as e:
            error(
                f"Błąd wykonywania scenariusza '{scenario_name}': {e}",
                message_logger=self._message_logger,
            )
            return False
        except Exception as e:
            error(
                f"Nieoczekiwany błąd w scenariuszu '{scenario_name}': {e}",
                message_logger=self._message_logger,
            )
            error(
                f"Traceback: {traceback.format_exc()}",
                message_logger=self._message_logger,
            )
            return False

    async def _execute_action(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> Any:
        """
        Deleguje wykonanie akcji do ActionExecutor.
        Metoda używana przez wait_for_state_action dla obsługi on_failure.
        """
        return await self._action_executor.execute_action(action_config, context)

    async def _analyze_event(self, event: Event) -> bool:
        """
        Analizuje i obsługuje zdarzenia przychodzące do Orchestratora.

        Obsługuje m.in. aktualizację stanów klientów dla zdarzeń
        `CMD_GET_STATE` i `CMD_HEALTH_CHECK` oraz porządkuje listę
        przetwarzanych zdarzeń.

        Args:
            event (Event): Otrzymane zdarzenie.

        Returns:
            bool: Zawsze True (zdarzenie zostało obsłużone).
        """
        match event.event_type:
            case "CMD_GET_STATE":
                if event.result is not None:
                    old_state = self._state.get(event.source, {}).get(
                        "fsm_state", "UNKNOWN"
                    )
                    new_state = event.data["fsm_state"]
                    self._state[event.source]["fsm_state"] = new_state

                    # Zapisz pola błędu raportowane przez klienta
                    self._state[event.source]["error"] = bool(
                        event.data.get("error", False)
                    )
                    self._state[event.source]["error_message"] = event.data.get(
                        "error_message"
                    )

                    debug(
                        f"📊 _state update: {event.source} FSM: {old_state} → {new_state}",
                        message_logger=self._message_logger,
                    )

                    # Event ma result - usuń go z processing
                    self._find_and_remove_processing_event(event)
            case "CMD_HEALTH_CHECK":
                if event.result is not None:
                    self._state[event.source]["health_check"] = event.data
                    # Event ma result - usuń go z processing
                    self._find_and_remove_processing_event(event)
            # case "EXECUTE_SCENARIO":
            #     if event.result is None:
            #         scenario_name = event.data.get("scenario_name")
            #         if scenario_name:
            #             # Przygotuj dane triggera z wydarzenia
            #             trigger_data = {
            #                 "source": event.source,
            #                 "event_type": event.event_type,
            #                 "data": event.data,
            #                 "payload": event.data,  # Dla kompatybilności z dokumentacją
            #             }

            #             success = await self.execute_scenario(
            #                 scenario_name, trigger_data
            #             )
            #             event.result = Result(
            #                 result="success" if success else "error",
            #                 data={
            #                     "scenario_executed": scenario_name,
            #                     "success": success,
            #                 },
            #             )
            #         else:
            #             event.result = Result(
            #                 result="error",
            #                 error_message="Brak nazwy scenariusza w danych wydarzenia",
            #             )
            #         await self._reply(event)
            case _:
                pass
        return True

    # Pozostałe metody EventListener bez zmian...
    async def on_initializing(self):
        """Metoda wywoływana podczas przejścia w stan INITIALIZING.
        Tu komponent powinien nawiązywać połączenia, alokować zasoby itp."""
        info(f"Orchestrator initializing", message_logger=self._message_logger)

        clients = self._configuration.get("clients", {})
        if clients:
            debug(
                f"🔧 Inicjalizuję strukturę _state dla {len(clients)} klientów: {list(clients.keys())}",
                message_logger=self._message_logger,
            )
            for client_name in clients.keys():
                if client_name not in self._state:
                    self._state[client_name] = {}
                    debug(
                        f"✅ Initialized state structure for client: {client_name}",
                        message_logger=self._message_logger,
                    )
                else:
                    debug(
                        f"♻️ State structure already exists for client: {client_name}",
                        message_logger=self._message_logger,
                    )
        else:
            warning(
                f"⚠️ Brak klientów w konfiguracji - _state pozostanie pusty",
                message_logger=self._message_logger,
            )

        self._load_components()  # Wczytaj komponenty z konfiguracji
        await self._initialize_components()  # Inicjalizuj i połącz komponenty
        self._load_actions()  # Wczytaj akcje: systemowe i użytkownika
        self._load_scenarios()  # Wczytaj scenariusze: systemowe i użytkownika

    async def on_initialized(self):
        """Metoda wywoływana podczas przejścia w stan INITIALIZED.
        Tu komponent powinien nawiązywać połączenia, alokować zasoby itp."""
        clients_count = len(self._configuration.get("clients", {}))
        if clients_count == 0:
            warning(
                "⚠️ BRAK KLIENTÓW: Orkiestrator nie ma skonfigurowanych żadnych komponentów!",
                message_logger=self._message_logger,
            )
            warning(
                "💡 Akcje '@all' nie będą działać bez skonfigurowanych clients w konfiguracji",
                message_logger=self._message_logger,
            )
        else:
            info(
                f"👥 Orkiestrator ma {clients_count} skonfigurowanych komponentów: {list(self._configuration.get('clients', {}).keys())}",
                message_logger=self._message_logger,
            )

        info(f"Orchestrator initialized", message_logger=self._message_logger)
        self._change_fsm_state(EventListenerState.STARTING)

    async def on_starting(self):
        """Metoda wywoływana podczas przejścia w stan STARTING.
        Tu komponent przygotowuje się do uruchomienia głównych operacji."""
        info(f"Orchestrator starting", message_logger=self._message_logger)

    async def on_run(self):
        """Metoda wywoływana podczas przejścia w stan RUN.
        Tu komponent rozpoczyna swoje główne zadania operacyjne."""
        info(f"Orchestrator running", message_logger=self._message_logger)

    async def on_pausing(self):
        """Metoda wywoływana podczas przejścia w stan PAUSING.
        Tu komponent przygotowuje się do wstrzymania operacji."""
        pass

    async def on_pause(self):
        """Metoda wywoływana podczas przejścia w stan PAUSE.
        Tu komponent jest wstrzymany ale gotowy do wznowienia."""
        pass

    async def on_resuming(self):
        """Metoda wywoływana podczas przejścia RESUMING (PAUSE → RUN).
        Tu komponent przygotowuje się do wznowienia operacji."""
        # Przygotowujemy się do uruchomienia local_check w RUN (uruchomienie w on_run)
        pass

    async def on_stopping(self):
        """Metoda wywoływana podczas przejścia w stan STOPPING.
        Tu komponent finalizuje wszystkie zadania przed całkowitym zatrzymaniem."""
        pass

    async def on_stopped(self):
        """Metoda wywoływana po przejściu w stan STOPPED.
        Tu komponent jest całkowicie zatrzymany i wyczyszczony."""
        await self._disconnect_components()  # Rozłącz komponenty
        self._change_fsm_state(EventListenerState.INITIALIZING)

    async def on_soft_stopping(self):
        """Metoda wywoływana podczas przejścia SOFT_STOPPING (RUN → INITIALIZED).
        Tu komponent kończy bieżące operacje ale zachowuje stan."""
        pass

    async def on_ack(self):
        """
        Metoda wywoływana po otrzymaniu ACK operatora ze stanu FAULT.
        
        Tu komponent wykonuje operacje czyszczenia i przygotowania do stanu STOPPED.
        Resetuje również wszystkie liczniki wykonań scenariuszy i odblokowuje je.
        """
        info(
            "🔧 ACK otrzymany - resetuję liczniki wykonań scenariuszy",
            message_logger=self._message_logger,
        )
        self.reset_all_scenario_execution_counters()

    async def on_error(self):
        """Metoda wywoływana podczas przejścia w stan ON_ERROR.
        Tu komponent przechodzi w stan błędu i oczekuje na ACK operatora."""
        pass

    async def on_fault(self):
        """Metoda wywoływana podczas przejścia w stan FAULT.
        Tu komponent przechodzi w stan błędu i oczekuje na ACK operatora."""
        pass

    async def _should_execute_scenario(self, scenario: dict) -> bool:
        """
        Sprawdza czy scenariusz powinien być wykonany na podstawie aktualnego stanu.
        
        Uwzględnia:
        - Warunki triggera
        - Limit wykonań scenariusza (max_executions)
        - Status blokady scenariusza
        """
        scenario_name = scenario.get("name", "unknown")
        
        # KROK 1: Sprawdź blokadę z powodu przekroczenia limitu wykonań
        max_executions = scenario.get("max_executions")
        if self.should_block_scenario_due_to_limit(scenario_name, max_executions):
            debug(
                f"🚫 Scenariusz '{scenario_name}' zablokowany - przekroczono limit wykonań",
                message_logger=self._message_logger,
            )
            return False
            
        # KROK 2: Sprawdź warunki triggera
        trigger = scenario.get("trigger", {})
        conditions = trigger.get("conditions", {})

        if not conditions:
            return True  # Brak warunków = zawsze wykonuj

        try:
            # Użyj nowego systemu warunków
            condition = ConditionFactory.create_condition(
                conditions, self._message_logger
            )

            # Przygotuj kontekst tylko z clients - przefiltruj do znanych klientów
            configured_clients = self._configuration.get("clients", {})
            filtered_clients_state = {
                client_name: self._state.get(client_name, {})
                for client_name in configured_clients.keys()
            }

            context = {
                "clients": filtered_clients_state,
                "components": self._components,  # Dodaj komponenty do kontekstu
            }

            # Ewaluuj warunek
            return await condition.evaluate(context)

        except Exception as e:
            error(
                f"❌ Błąd ewaluacji warunków dla scenariusza {scenario_name}: {e}",
                message_logger=self._message_logger,
            )
            return False

    def _is_scenario_in_cooldown(self, scenario_name: str, scenario: dict) -> bool:
        """
        Sprawdza czy scenariusz jest w okresie cooldown.

        Args:
            scenario_name: Nazwa scenariusza
            scenario: Konfiguracja scenariusza

        Returns:
            True jeśli scenariusz jest w cooldown, False w przeciwnym razie
        """
        # Sprawdź cooldown na poziomie głównym (nowy format)
        cooldown_seconds = scenario.get("cooldown")
        if cooldown_seconds is None:
            # Sprawdź cooldown w trigger.conditions (stary format - dla kompatybilności)
            trigger = scenario.get("trigger", {})
            conditions = trigger.get("conditions", {})
            cooldown_seconds = conditions.get("cooldown_seconds", 60)  # Domyślnie 60s

        if scenario_name not in self._scenario_last_execution:
            return False  # Pierwszy raz - nie ma cooldown

        last_execution = self._scenario_last_execution[scenario_name]
        time_since_last = datetime.now() - last_execution

        is_in_cooldown = time_since_last.total_seconds() < cooldown_seconds

        if is_in_cooldown:
            remaining = cooldown_seconds - time_since_last.total_seconds()
            debug(
                f"⏱️ Scenariusz {scenario_name} w cooldown, pozostało: {remaining:.1f}s",
                message_logger=self._message_logger,
            )

        return is_in_cooldown

    async def _check_scenarios(self):
        """
        Sprawdza warunki i uruchamia scenariusze jeśli potrzeba.

        Implementuje zabezpieczenia przed wielokrotnym uruchamianiem:
        - Tracking aktywnych scenariuszy
        - Cooldown mechanism
        - Execution limits
        - Automatic cleanup
        """
        # debug(self._configuration, message_logger=self._message_logger)
        # debug(self._state, message_logger=self._message_logger)
        # debug(self._scenarios, message_logger=self._message_logger)
        if not self._scenarios:
            return

        debug(
            f"🔍 Sprawdzam {len(self._scenarios)} scenariuszy, aktywnych: {len(self._running_scenarios)}, limit: {self._configuration.get('max_concurrent_scenarios', 1)}",
            message_logger=self._message_logger,
        )

        # Sprawdź globalny limit jednoczesnych scenariuszy
        max_concurrent_scenarios = self._configuration.get(
            "max_concurrent_scenarios", 1
        )
        active_scenarios_count = len([
            task for task in self._running_scenarios.values() if not task.done()
        ])

        if active_scenarios_count >= max_concurrent_scenarios:
            debug(
                f"🚫 Osiągnięto globalny limit jednoczesnych scenariuszy: {active_scenarios_count}/{max_concurrent_scenarios}",
                message_logger=self._message_logger,
            )
            # Tylko cleanup zakończonych tasków, nie uruchamiaj nowych
            for scenario_name, task in list(self._running_scenarios.items()):
                if task.done():
                    try:
                        result = await task
                        debug(
                            f"✅ Task scenariusza {scenario_name} zakończony: {result}",
                            message_logger=self._message_logger,
                        )
                    except Exception as e:
                        error(
                            f"❌ Task scenariusza {scenario_name} zakończony błędem: {e}",
                            message_logger=self._message_logger,
                        )
                    finally:
                        del self._running_scenarios[scenario_name]
                await asyncio.sleep(0)
            return

        # Iteruj przez scenariusze (już posortowane według priorytetu)
        for scenario_name, scenario in self._scenarios.items():
            try:
                # KROK 0: Pomijaj scenariusze manualne w trybie autonomicznym,
                # chyba że mają ustawioną wewnętrzną flagę manual_run_requested=True
                trigger_cfg = scenario.get("trigger", {}) or {}
                trigger_type = str(trigger_cfg.get("type", "")).lower()
                if trigger_type == "manual":
                    internal = scenario.get("_internal", {}) or {}
                    manual_requested = bool(internal.get("manual_run_requested", False))
                    if not manual_requested:
                        debug(
                            f"⏭️ Pomijam scenariusz manualny w auto-sprawdzeniu (brak flagi): {scenario_name}",
                            message_logger=self._message_logger,
                        )
                        continue
                    else:
                        debug(
                            f"✅ Scenariusz manualny oznaczony do uruchomienia: {scenario_name}",
                            message_logger=self._message_logger,
                        )

                # KROK 1: Cleanup zakończonych tasków
                if scenario_name in self._running_scenarios:
                    task = self._running_scenarios[scenario_name]
                    if task.done():
                        # Pobierz wynik i usuń
                        try:
                            result = await task
                            debug(
                                f"✅ Task scenariusza {scenario_name} zakończony: {result}",
                                message_logger=self._message_logger,
                            )
                        except Exception as e:
                            error(
                                f"❌ Task scenariusza {scenario_name} zakończony błędem: {e}",
                                message_logger=self._message_logger,
                            )
                        finally:
                            del self._running_scenarios[scenario_name]
                    else:
                        debug(
                            f"⏳ Scenariusz {scenario_name} wciąż działa - pomijam",
                            message_logger=self._message_logger,
                        )
                        continue

                # KROK 2: Sprawdź cooldown
                if self._is_scenario_in_cooldown(scenario_name, scenario):
                    continue

                # KROK 3: Sprawdź warunki
                if not await self._should_execute_scenario(scenario):
                    continue

                # KROK 4: Sprawdź limity wykonań (opcjonalne)
                max_concurrent = scenario.get("max_concurrent_executions", 1)
                if (
                    len([
                        task
                        for task in self._running_scenarios.values()
                        if not task.done()
                    ])
                    >= max_concurrent
                ):
                    debug(
                        f"🚫 Scenariusz {scenario_name} osiągnął limit: {max_concurrent}",
                        message_logger=self._message_logger,
                    )
                    continue

                # KROK 5: Uruchom scenariusz w tle
                # Pobierz priorytet scenariusza (sprawdź oba formaty)
                scenario_priority = scenario.get("priority")
                if scenario_priority is None:
                    trigger = scenario.get("trigger", {})
                    conditions = trigger.get("conditions", {})
                    scenario_priority = conditions.get("priority", 0)

                info(
                    f"🎯 Warunki spełnione dla scenariusza: {scenario_name} (priorytet: {scenario_priority})",
                    message_logger=self._message_logger,
                )

                info(
                    f"🚀 Uruchamiam scenariusz w tle: {scenario_name} (priorytet: {scenario_priority})",
                    message_logger=self._message_logger,
                )

                # Utwórz task dla scenariusza
                task = asyncio.create_task(
                    self._execute_scenario_with_tracking(
                        scenario_name,
                        {
                            "source": "autonomous_mode",
                            "event_type": "AUTONOMOUS_TRIGGER",
                            "timestamp": datetime.now().isoformat(),
                        },
                    )
                )

                # Dodaj do tracking
                self._running_scenarios[scenario_name] = task
                self._scenario_execution_count[scenario_name] = (
                    self._scenario_execution_count.get(scenario_name, 0) + 1
                )

                debug(
                    f"📊 Aktywne scenariusze: {list(self._running_scenarios.keys())}",
                    message_logger=self._message_logger,
                )

                # KRYTYCZNE: Daj event loop szansę na uruchomienie tasku
                await asyncio.sleep(0)
                debug(
                    f"🔄 Przekazano kontrolę do event loop dla uruchomienia tasku {scenario_name}",
                    message_logger=self._message_logger,
                )

            except Exception as e:
                error(
                    f"❌ Błąd podczas sprawdzania scenariusza {scenario_name}: {e}",
                    message_logger=self._message_logger,
                )
                error(
                    f"Traceback: {traceback.format_exc()}",
                    message_logger=self._message_logger,
                )

    async def _check_local_data(self):  # MARK: CHECK LOCAL DATA
        """
        Odpytuje zdalnych klientów o stan lokalny i uruchamia kontrolę scenariuszy.

        Wysyła zdarzenia `CMD_GET_STATE` do wszystkich skonfigurowanych klientów,
        dodając je do kolejki „processing”, a następnie wywołuje sprawdzenie
        warunków scenariuszy w trybie autonomicznym.
        """
        for key, client in self._configuration["clients"].items():
            client_port = client["port"]
            client_address = client["address"]
            event = await self._event(
                destination=key,
                destination_address=client_address,
                destination_port=client_port,
                event_type="CMD_GET_STATE",
                data={},
                to_be_processed=False,
                is_system_event=True,
            )
            self._add_to_processing(event)

        # NOWY: Sprawdź scenariusze autonomiczne
        try:
            await self._check_scenarios()
        except Exception as e:
            error(
                f"Błąd w sprawdzaniu scenariuszy: {e}",
                message_logger=self._message_logger,
            )

    def _clear_before_shutdown(self):
        """
        Czyści zasoby i anuluje aktywne scenariusze przed wyłączeniem.

        Upewnia się, że wszystkie zadania scenariuszy zostały anulowane oraz
        zwalnia referencję do loggera.
        """
        __logger = self._message_logger  # Zapisz referencję jeśli potrzebna

        # Anuluj wszystkie aktywne scenariusze przed zamknięciem
        self._clear_running_scenarios()

        # Ustaw na None aby inne wątki nie próbowały używać
        self._message_logger = None

    def _clear_running_scenarios(self):
        """
        Anuluje wszystkie aktywne scenariusze przed zamknięciem orkiestratora.
        """
        if self._running_scenarios:
            info(
                f"🛑 Anulowanie {len(self._running_scenarios)} aktywnych scenariuszy...",
                message_logger=self._message_logger,
            )

            for scenario_name, task in self._running_scenarios.items():
                if not task.done():
                    info(
                        f"   ❌ Anulowanie scenariusza: {scenario_name}",
                        message_logger=self._message_logger,
                    )
                    task.cancel()
                else:
                    info(
                        f"   ✅ Scenariusz już zakończony: {scenario_name}",
                        message_logger=self._message_logger,
                    )

            # Wyczyść tracking
            self._running_scenarios.clear()
            self._scenario_execution_count.clear()

            # Wyczyść liczniki wykonań scenariuszy
            self._scenario_execution_counters.clear()
            self._blocked_scenarios.clear()

            info(
                "🧹 Cleanup aktywnych scenariuszy zakończony",
                message_logger=self._message_logger,
            )
