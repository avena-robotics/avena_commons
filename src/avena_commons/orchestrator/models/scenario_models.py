"""
Modele Pydantic dla scenariuszy orkiestratora.
"""

from typing import Any, Dict

from pydantic import BaseModel, Field


class ScenarioContext(BaseModel):
    """
    Prosty kontekst scenariusza przechowujący wszystkie potrzebne dane.
    
    Używany przez warunki i akcje do wymiany danych w ramach scenariusza.
    """
    
    scenario_name: str = Field(..., description="Nazwa scenariusza")
    
    orchestrator: Any = Field(..., description="Instancja Orchestratora", exclude=True)
    
    # Komponenty systemu (readonly dla warunków/akcji)
    action_executor: Any = Field(..., description="Executor akcji", exclude=True)
    message_logger: Any = Field(..., description="Logger wiadomości", exclude=True) 
    clients: Dict[str, Any] = Field(default_factory=dict, description="Stan klientów")
    components: Dict[str, Any] = Field(default_factory=dict, description="Komponenty zewnętrzne")
    
    # Słownik na zmienne scenariusza (modyfikowalne przez warunki/akcje)
    context: Dict[str, Any] = Field(default_factory=dict, description="Zmienne scenariusza")
    
    class Config:
        arbitrary_types_allowed = True
        exclude = {"action_executor", "message_logger", "orchestrator"}
    
    def get(self, key: str, default: Any = None) -> Any:
        """Pobiera zmienną z kontekstu scenariusza."""
        return self.context.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Ustawia zmienną w kontekście scenariusza."""
        self.context[key] = value
    
    def update(self, data: Dict[str, Any]) -> None:
        """Aktualizuje zmienne kontekstu z słownika."""
        self.context.update(data)

    def to_dict(self) -> dict:
        """Konwertuje kontekst scenariusza na słownik, z wyłączeniem pól exclude."""
        return self.model_dump(exclude=self.Config.exclude)