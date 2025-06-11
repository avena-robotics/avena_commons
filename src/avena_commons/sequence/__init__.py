"""
#### Moduł Sequence - Zarządzanie Maszynami Stanów

Implementacja maszyny stanów do zarządzania złożonymi operacjami sekwencyjnymi
z kontrolą przepływu kroków, obsługą błędów i mechanizmami ponawiania.

#### Komponenty:
- `Sequence`: Główna klasa zarządzania sekwencjami krok po kroku
- `SequenceStatus`: Kompletne informacje o stanie sekwencji
- `SequenceStepStatus`: Status pojedynczych kroków ze śledzeniem
- `StepState`: Enum stanów (PREPARE, EXECUTE, DONE, TEST_FAILED, ERROR)

#### Przykład użycia:
```python
from enum import Enum
from avena_commons.sequence import Sequence, StepState

class ProductionSequence(Enum):
    INITIALIZE = 1
    LOAD_MATERIAL = 2
    PROCESS = 3

# Tworzenie sekwencji
sequence = Sequence(
    produkt_id=12345,
    enum_class=ProductionSequence,
    parametry={"material_type": "steel"}
)

# Kontrola wykonania
sequence.run_step()      # PREPARE → EXECUTE
sequence.done_step()     # EXECUTE → DONE
sequence.next_step()     # Przejście do następnego kroku
```

#### Funkcjonalności:
- Kontrolowane przejścia stanów z walidacją FSM
- Mechanizmy ponawiania z licznikiem prób
- Przetwarzanie zdarzeń zewnętrznych
- Pełna serializacja JSON z walidacją Pydantic
- Logowanie zmian stanów z timestampami
"""

from .sequence import Sequence, SequenceStatus, SequenceStepStatus
from .step_state import StepState

__all__ = ["Sequence", "SequenceStatus", "SequenceStepStatus", "StepState"]
