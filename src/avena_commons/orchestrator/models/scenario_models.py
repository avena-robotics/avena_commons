"""
Modele Pydantic dla scenariuszy orkiestratora.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


class TriggerModel(BaseModel):
    """Model dla wyzwalacza scenariusza."""

    type: str = Field(
        ...,
        description="Typ wyzwalacza (np. 'manual', 'automatic', 'scheduled', 'event')",
    )
    description: Optional[str] = Field(None, description="Opis wyzwalacza")
    conditions: Optional[Dict[str, Any]] = Field(None, description="Warunki wyzwalania")

    @validator("type")
    def validate_trigger_type(cls, v):
        """Waliduje typ wyzwalacza."""
        valid_types = {"manual", "automatic", "scheduled", "event"}
        if v not in valid_types:
            raise ValueError(
                f"Nieprawidłowy typ wyzwalacza: {v}. Dozwolone: {valid_types}"
            )
        return v


class ActionModel(BaseModel):
    """Model dla pojedynczej akcji scenariusza."""

    type: str = Field(..., description="Typ akcji (np. 'log_event', 'send_command')")

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
    target_state: Optional[str] = Field(None, description="Docelowy stan komponentu")
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

    @validator("type")
    def validate_action_type(cls, v):
        """Waliduje czy typ akcji jest znany."""
        known_types = {
            "log_event",
            "send_command",
            "wait_for_state",
            "test",
            "custom_process",  # Dodaj inne znane typy
        }
        if v not in known_types:
            # Nie blokujemy nieznanych typów - mogą być dynamicznie ładowane
            pass
        return v

    @validator("level")
    def validate_log_level(cls, v):
        """Waliduje poziom logowania."""
        if v is not None:
            valid_levels = {"info", "warning", "error", "success", "debug"}
            if v not in valid_levels:
                raise ValueError(
                    f"Nieprawidłowy poziom logowania: {v}. Dozwolone: {valid_levels}"
                )
        return v

    @validator("timeout")
    def validate_timeout_format(cls, v):
        """Waliduje format timeout."""
        if v is not None:
            if not (v.endswith("s") or v.endswith("m") or v.endswith("h")):
                raise ValueError(
                    'Timeout musi kończyć się na "s", "m" lub "h" (np. "30s", "2m", "1h")'
                )
        return v


# Forward reference dla ActionModel.on_failure
ActionModel.model_rebuild()


class ScenarioModel(BaseModel):
    """Model dla całego scenariusza."""

    name: str = Field(..., description="Nazwa scenariusza")
    description: Optional[str] = Field(None, description="Opis scenariusza")
    version: Optional[str] = Field("1.0", description="Wersja scenariusza")
    author: Optional[str] = Field(None, description="Autor scenariusza")
    created_at: Optional[str] = Field(None, description="Data utworzenia")
    tags: Optional[List[str]] = Field(None, description="Tagi scenariusza")

    # Parametry wykonania scenariusza
    priority: Optional[int] = Field(
        0, description="Priorytet scenariusza (wyższy = ważniejszy)"
    )
    cooldown: Optional[int] = Field(
        60, description="Okres cooldown w sekundach między wykonaniami"
    )

    # Trigger i akcje
    trigger: TriggerModel = Field(..., description="Wyzwalacz scenariusza")
    actions: List[ActionModel] = Field(
        ..., min_items=1, description="Lista akcji do wykonania"
    )

    # Metadane
    metadata: Optional[Dict[str, Any]] = Field(None, description="Dodatkowe metadane")

    @validator("name")
    def validate_name_not_empty(cls, v):
        """Waliduje czy nazwa nie jest pusta."""
        if not v.strip():
            raise ValueError("Nazwa scenariusza nie może być pusta")
        return v.strip()

    @validator("actions")
    def validate_actions_not_empty(cls, v):
        """Waliduje czy lista akcji nie jest pusta."""
        if not v:
            raise ValueError("Scenariusz musi zawierać przynajmniej jedną akcję")
        return v


class ScenarioCollection(BaseModel):
    """Model dla kolekcji scenariuszy (jeśli potrzebna)."""

    scenarios: List[ScenarioModel] = Field(..., description="Lista scenariuszy")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadane kolekcji")

    @validator("scenarios")
    def validate_unique_scenario_names(cls, v):
        """Waliduje czy nazwy scenariuszy są unikalne."""
        names = [scenario.name for scenario in v]
        if len(names) != len(set(names)):
            raise ValueError("Nazwy scenariuszy muszą być unikalne")
        return v


class ScenarioExecutionContext(BaseModel):
    """Model dla kontekstu wykonania scenariusza."""

    scenario_name: str = Field(..., description="Nazwa wykonywanego scenariusza")
    trigger_data: Optional[Dict[str, Any]] = Field(None, description="Dane z triggera")
    execution_id: Optional[str] = Field(None, description="Unikalny ID wykonania")
    started_at: Optional[str] = Field(None, description="Czas rozpoczęcia")
    variables: Optional[Dict[str, Any]] = Field(None, description="Zmienne kontekstowe")


class ScenarioExecutionResult(BaseModel):
    """Model dla wyniku wykonania scenariusza."""

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
