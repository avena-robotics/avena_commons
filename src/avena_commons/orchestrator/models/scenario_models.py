"""
Modele Pydantic dla scenariuszy orkiestratora.
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class TriggerModel(BaseModel):
    """
    Model wyzwalacza scenariusza.

    Attributes:
        type (str): Typ wyzwalacza (manual/automatic/scheduled/event).
        description (str | None): Opis wyzwalacza.
        conditions (Dict[str, Any] | None): Warunki wyzwalania (np. do ewaluacji).
    """

    type: str = Field(
        ...,
        description="Typ wyzwalacza (np. 'manual', 'automatic', 'scheduled', 'event')",
    )
    description: Optional[str] = Field(None, description="Opis wyzwalacza")
    conditions: Optional[Dict[str, Any]] = Field(None, description="Warunki wyzwalania")

    @field_validator("type")
    def validate_trigger_type(cls, v):
        """Waliduje typ wyzwalacza."""
        valid_types = {"manual", "automatic", "scheduled", "event"}
        if v not in valid_types:
            raise ValueError(
                f"Nieprawidłowy typ wyzwalacza: {v}. Dozwolone: {valid_types}"
            )
        return v


class ActionModel(BaseModel):
    """
    Model pojedynczej akcji scenariusza.

    Zawiera parametry wspólne i specyficzne dla wybranych typów akcji.
    Rozszerzony o kontrolę przepływu scenariuszy (execute_scenario).
    """

    type: str = Field(
        ...,
        description="Typ akcji (np. 'log_event', 'send_command', 'execute_scenario')",
    )

    # Parametry wspólne
    description: Optional[str] = Field(None, description="Opis akcji")

    # Parametry akcji log_event
    level: Optional[str] = Field(
        None, description="Poziom logowania (info, warning, error, success)"
    )
    message: Optional[str] = Field(None, description="Wiadomość do zalogowania")

    # Parametry akcji send_command
    client: Optional[str] = Field(None, description="Nazwa pojedynczego klienta")
    group: Optional[str] = Field(None, description="Nazwa grupy komponentów")
    groups: Optional[List[str]] = Field(None, description="Lista nazw grup komponentów")
    target: Optional[str] = Field(None, description="Cel akcji (np. '@all')")
    command: Optional[str] = Field(None, description="Komenda FSM do wysłania")

    # Parametry akcji wait_for_state
    # target_state może być stringiem lub listą stringów; alternatywnie można użyć target_states
    target_state: Optional[Union[str, List[str]]] = Field(
        None,
        description="Docelowy stan komponentu (string) lub lista akceptowanych stanów",
    )
    target_states: Optional[Union[str, List[str]]] = Field(
        None,
        description="Lista akceptowanych stanów (alias dla target_state)",
    )
    timeout: Optional[str] = Field(
        None, description="Timeout operacji (np. '30s', '2m')"
    )
    check_interval: Optional[str] = Field(
        None, description="Interwał sprawdzania stanu"
    )
    on_timeout: Optional[str] = Field(None, description="Akcja przy timeout")
    on_failure: Optional[List["ActionModel"]] = Field(
        None, description="Akcje przy błędzie"
    )

    # Dodatkowe parametry dla niestandardowych akcji
    data: Optional[Dict[str, Any]] = Field(None, description="Dodatkowe dane dla akcji")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Parametry akcji")

    # Parametry akcji send_email
    to: Optional[Union[str, List[str]]] = Field(
        None,
        description="Adres(y) odbiorców e-mail (string lub lista) oraz numer sms (string lub lista)",
    )
    subject: Optional[str] = Field(None, description="Temat wiadomości e-mail")
    body: Optional[str] = Field(None, description="Treść wiadomości e-mail")
    smtp: Optional[Dict[str, Any]] = Field(
        None,
        description="Konfiguracja SMTP per-akcja (opcjonalne, nadpisuje globalną)",
    )

    # Parametry akcji send_sms
    text: Optional[str] = Field(None, description="Treść wiadomości SMS")
    sms: Optional[Dict[str, Any]] = Field(
        None, description="Konfiguracja SMS per-akcja (opcjonalne, nadpisuje globalną)"
    )

    # NOWE: Parametry kontroli przepływu scenariuszy
    # Parametry akcji execute_scenario
    scenario: Optional[str] = Field(
        None, description="Nazwa scenariusza do uruchomienia"
    )
    wait_for_completion: Optional[bool] = Field(
        True, description="Czy czekać na zakończenie zagnieżdżonego scenariusza"
    )
    on_nested_failure: Optional[str] = Field(
        "fail", description="Akcja przy błędzie zagnieżdżonego ('continue' lub 'fail')"
    )

    @field_validator("type")
    def validate_action_type(cls, v):
        """Waliduje czy typ akcji jest znany."""
        known_types = {
            "log_event",
            "send_command",
            "wait_for_state",
            "send_email",
            "send_sms",
            "test",
            "custom_process",
            # NOWE: Typy kontroli przepływu scenariuszy
            "execute_scenario",
            "evaluate_condition",
        }
        if v not in known_types:
            # Nie blokujemy nieznanych typów - mogą być dynamicznie ładowane
            pass
        return v

    @field_validator("level")
    def validate_log_level(cls, v):
        """Waliduje poziom logowania."""
        if v is not None:
            valid_levels = {"info", "warning", "error", "success", "debug"}
            if v not in valid_levels:
                raise ValueError(
                    f"Nieprawidłowy poziom logowania: {v}. Dozwolone: {valid_levels}"
                )
        return v

    @field_validator("timeout")
    def validate_timeout_format(cls, v):
        """Waliduje format timeout."""
        if v is not None:
            if not (v.endswith("s") or v.endswith("m") or v.endswith("h")):
                raise ValueError(
                    'Timeout musi kończyć się na "s", "m" lub "h" (np. "30s", "2m", "1h")'
                )
        return v

    class Config:
        # Zachowuj dodatkowe klucze w akcjach (np. nowe pola specyficzne dla akcji)
        extra = "allow"


# Forward reference dla ActionModel.on_failure
ActionModel.model_rebuild()


class ScenarioModel(BaseModel):
    """
    Model całego scenariusza wykonywanego przez Orchestratora.

    Attributes:
        name (str): Nazwa scenariusza.
        description (str | None): Opis scenariusza.
        priority (int | None): Priorytet (mniejsza wartość = ważniejszy).
        cooldown (int | None): Cooldown w sekundach między uruchomieniami.
        trigger (TriggerModel): Wyzwalacz scenariusza.
        actions (List[ActionModel]): Lista akcji do wykonania.
        metadata (Dict[str, Any] | None): Dodatkowe metadane.
    """

    name: str = Field(..., description="Nazwa scenariusza")
    description: Optional[str] = Field(None, description="Opis scenariusza")
    version: Optional[str] = Field("1.0", description="Wersja scenariusza")
    author: Optional[str] = Field(None, description="Autor scenariusza")
    created_at: Optional[str] = Field(None, description="Data utworzenia")
    tags: Optional[List[str]] = Field(None, description="Tagi scenariusza")

    # Parametry wykonania scenariusza
    priority: Optional[int] = Field(
        0, description="Priorytet scenariusza (mniejszy = ważniejszy)"
    )
    cooldown: Optional[int] = Field(
        60, description="Okres cooldown w sekundach między wykonaniami"
    )
    max_executions: Optional[int] = Field(
        None,
        description="Maksymalna liczba wykonań przed zablokowaniem do ACK (None = bez limitu)",
    )

    # Trigger i akcje
    trigger: TriggerModel = Field(..., description="Wyzwalacz scenariusza")
    actions: List[ActionModel] = Field(
        ..., min_items=1, description="Lista akcji do wykonania"
    )

    # Metadane
    metadata: Optional[Dict[str, Any]] = Field(None, description="Dodatkowe metadane")

    @field_validator("name")
    def validate_name_not_empty(cls, v):
        """Waliduje czy nazwa nie jest pusta."""
        if not v.strip():
            raise ValueError("Nazwa scenariusza nie może być pusta")
        return v.strip()

    @field_validator("actions")
    def validate_actions_not_empty(cls, v):
        """Waliduje czy lista akcji nie jest pusta."""
        if not v:
            raise ValueError("Scenariusz musi zawierać przynajmniej jedną akcję")
        return v


class ScenarioCollection(BaseModel):
    """
    Model kolekcji scenariuszy (np. przy wczytywaniu wielu na raz).
    """

    scenarios: List[ScenarioModel] = Field(..., description="Lista scenariuszy")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadane kolekcji")

    @field_validator("scenarios")
    def validate_unique_scenario_names(cls, v):
        """Waliduje czy nazwy scenariuszy są unikalne."""
        names = [scenario.name for scenario in v]
        if len(names) != len(set(names)):
            raise ValueError("Nazwy scenariuszy muszą być unikalne")
        return v


class ScenarioExecutionContext(BaseModel):
    """
    Model kontekstu wykonania scenariusza.
    """

    scenario_name: str = Field(..., description="Nazwa wykonywanego scenariusza")
    trigger_data: Optional[Dict[str, Any]] = Field(None, description="Dane z triggera")
    execution_id: Optional[str] = Field(None, description="Unikalny ID wykonania")
    started_at: Optional[str] = Field(None, description="Czas rozpoczęcia")
    variables: Optional[Dict[str, Any]] = Field(None, description="Zmienne kontekstowe")


class ScenarioExecutionResult(BaseModel):
    """
    Model wyniku wykonania scenariusza.
    """

    success: bool = Field(..., description="Czy scenariusz wykonał się pomyślnie")
    scenario_name: str = Field(..., description="Nazwa scenariusza")
    execution_id: Optional[str] = Field(None, description="ID wykonania")
    started_at: Optional[str] = Field(None, description="Czas rozpoczęcia")
    finished_at: Optional[str] = Field(None, description="Czas zakończenia")
    duration_ms: Optional[int] = Field(None, description="Czas trwania w milisekundach")

    # Wyniki poszczególnych akcji
    action_results: Optional[List[Dict[str, Any]]] = Field(
        None, description="Wyniki akcji"
    )

    # Błędy
    error_message: Optional[str] = Field(None, description="Komunikat błędu")
    error_details: Optional[Dict[str, Any]] = Field(None, description="Szczegóły błędu")
    failed_action_index: Optional[int] = Field(
        None, description="Indeks akcji która się nie powiodła"
    )
