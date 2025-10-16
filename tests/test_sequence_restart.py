"""Test modułu restart funkcjonalności sekwencji.

Testy sprawdzają:
- Ustawianie flag restart i can_restart
- Poprawność działania restartu sekwencji
- Zachowanie w różnych stanach sekwencji
"""

from enum import IntEnum

from avena_commons.sequence import Sequence
from avena_commons.sequence.step_state import StepState


class SequenceEnumForTesting(IntEnum):
    """Enum testowy dla sekwencji."""

    STEP_1 = 1
    STEP_2 = 2
    STEP_3 = 3


class TestSequenceRestart:
    """Testy funkcjonalności restartu sekwencji."""

    def test_set_restart_flag(self):
        """Test ustawiania flagi restart."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        # Inicjalnie restart=False
        assert sequence.get_restart() is False

        # Ustaw restart=True
        sequence.set_restart(True)
        assert sequence.get_restart() is True

        # Ustaw restart=False
        sequence.set_restart(False)
        assert sequence.get_restart() is False

    def test_set_can_restart_flag(self):
        """Test ustawiania flagi can_restart."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        # Inicjalnie can_restart=False
        assert sequence.get_can_restart() is False

        # Ustaw can_restart=True
        sequence.set_can_restart(True)
        assert sequence.get_can_restart() is True

        # Ustaw can_restart=False
        sequence.set_can_restart(False)
        assert sequence.get_can_restart() is False

    def test_should_restart_both_flags_true(self):
        """Test should_restart gdy obie flagi są True."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        sequence.set_restart(True)
        sequence.set_can_restart(True)

        assert sequence.should_restart() is True

    def test_should_restart_only_restart_true(self):
        """Test should_restart gdy tylko restart=True."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        sequence.set_restart(True)
        sequence.set_can_restart(False)

        assert sequence.should_restart() is False

    def test_should_restart_only_can_restart_true(self):
        """Test should_restart gdy tylko can_restart=True."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        sequence.set_restart(False)
        sequence.set_can_restart(True)

        assert sequence.should_restart() is False

    def test_should_restart_both_flags_false(self):
        """Test should_restart gdy obie flagi są False."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        sequence.set_restart(False)
        sequence.set_can_restart(False)

        assert sequence.should_restart() is False

    def test_reset_restart_flags(self):
        """Test resetowania flag restart."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        # Ustaw obie flagi na True
        sequence.set_restart(True)
        sequence.set_can_restart(True)

        # Zresetuj
        sequence.reset_restart_flags()

        assert sequence.get_restart() is False
        assert sequence.get_can_restart() is False

    def test_restart_sequence_success(self):
        """Test pomyślnego restartu sekwencji."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        # Przejdź do drugiego kroku
        sequence.run_step()
        sequence.done_step()

        # Sprawdź że jesteśmy na kroku 2
        assert sequence.status.current_step == 2
        assert sequence.status.finished is False

        # Ustaw flagi restart
        sequence.set_restart(True)
        sequence.set_can_restart(True)

        # Zrestartuj
        restart_result = sequence.restart_sequence()

        assert restart_result is True
        assert sequence.status.current_step == 1
        assert sequence.status.finished is False
        assert sequence.get_restart() is False
        assert sequence.get_can_restart() is False

        # Sprawdź że wszystkie kroki zostały zresetowane
        for step_status in sequence.status.steps.values():
            assert step_status.fsm_state == StepState.PREPARE
            assert step_status.retry_count == 0
            assert step_status.error_code == 0

    def test_restart_sequence_failure_conditions_not_met(self):
        """Test niepomyślnego restartu gdy warunki nie są spełnione."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        # Nie ustawiaj flag restart
        restart_result = sequence.restart_sequence()

        assert restart_result is False
        assert sequence.status.current_step == 1  # Nie zmienił się

    def test_done_step_with_restart_on_last_step(self):
        """Test done_step z restartem na ostatnim kroku."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        # Przejdź do ostatniego kroku (step 3)
        sequence.run_step()
        sequence.done_step()  # step 1 -> 2
        sequence.run_step()
        sequence.done_step()  # step 2 -> 3
        sequence.run_step()

        # Sprawdź że jesteśmy na ostatnim kroku
        assert sequence.status.current_step == 3

        # Ustaw flagi restart
        sequence.set_restart(True)
        sequence.set_can_restart(True)

        # Wykonaj done_step na ostatnim kroku
        sequence.done_step()

        # Sprawdź że sekwencja została zrestartowana
        assert sequence.status.current_step == 1
        assert sequence.status.finished is False
        assert sequence.get_restart() is False
        assert sequence.get_can_restart() is False

    def test_done_step_without_restart_on_last_step(self):
        """Test done_step bez restartu na ostatnim kroku."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        # Przejdź do ostatniego kroku (step 3)
        sequence.run_step()
        sequence.done_step()  # step 1 -> 2
        sequence.run_step()
        sequence.done_step()  # step 2 -> 3
        sequence.run_step()

        # Sprawdź że jesteśmy na ostatnim kroku
        assert sequence.status.current_step == 3

        # Nie ustawiaj flag restart

        # Wykonaj done_step na ostatnim kroku
        sequence.done_step()

        # Sprawdź że sekwencja została zakończona normalnie
        assert sequence.status.finished is True

    def test_next_step_with_restart_on_last_step(self):
        """Test next_step z restartem po osiągnięciu ostatniego kroku."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        # Przejdź do przedostatniego kroku
        sequence.run_step()
        sequence.done_step()  # step 1 -> 2
        sequence.run_step()
        sequence.done_step()  # step 2 -> 3

        # Sprawdź że jesteśmy na ostatnim kroku
        assert sequence.status.current_step == 3

        # Ustaw flagi restart
        sequence.set_restart(True)
        sequence.set_can_restart(True)

        # Wykonaj next_step na ostatnim kroku
        sequence.next_step()

        # Sprawdź że sekwencja została zrestartowana
        assert sequence.status.current_step == 1
        assert sequence.status.finished is False
        assert sequence.get_restart() is False
        assert sequence.get_can_restart() is False

    def test_restart_sequence_to_specific_step(self):
        """Test restartu sekwencji do określonego kroku."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        # Przejdź do trzeciego kroku
        sequence.run_step()
        sequence.done_step()  # step 1 -> 2
        sequence.run_step()
        sequence.done_step()  # step 2 -> 3

        # Sprawdź że jesteśmy na kroku 3
        assert sequence.status.current_step == 3

        # Ustaw flagi restart i docelowy krok
        sequence.set_restart(True)
        sequence.set_can_restart(True)
        sequence.set_restart_target_step(2)

        # Zrestartuj
        restart_result = sequence.restart_sequence()

        assert restart_result is True
        assert sequence.status.current_step == 2
        assert sequence.status.finished is False
        assert sequence.get_restart() is False
        assert sequence.get_can_restart() is False

        # Sprawdź że wszystkie kroki zostały zresetowane
        for step_status in sequence.status.steps.values():
            assert step_status.fsm_state == StepState.PREPARE
            assert step_status.retry_count == 0
            assert step_status.error_code == 0

    def test_restart_to_step_convenience_method(self):
        """Test wygodnej metody restart_to_step."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        # Przejdź do trzeciego kroku
        sequence.run_step()
        sequence.done_step()  # step 1 -> 2
        sequence.run_step()
        sequence.done_step()  # step 2 -> 3

        # Sprawdź że jesteśmy na kroku 3
        assert sequence.status.current_step == 3

        # Użyj wygodnej metody restart_to_step (powinna ustawić flagi i zrestartować)
        sequence.restart_to_step(2)

        assert sequence.status.current_step == 2
        assert sequence.status.finished is False
        assert sequence.get_restart() is False
        assert sequence.get_can_restart() is False

        # Sprawdź że wszystkie kroki zostały zresetowane
        for step_status in sequence.status.steps.values():
            assert step_status.fsm_state == StepState.PREPARE
            assert step_status.retry_count == 0
            assert step_status.error_code == 0

    def test_restart_sequence_to_step_1_default(self):
        """Test że domyślnie restart_sequence resetuje do kroku 1."""
        sequence = Sequence(produkt_id=1, enum_class=SequenceEnumForTesting)

        # Przejdź do trzeciego kroku
        sequence.run_step()
        sequence.done_step()  # step 1 -> 2
        sequence.run_step()
        sequence.done_step()  # step 2 -> 3

        # Ustaw flagi restart
        sequence.set_restart(True)
        sequence.set_can_restart(True)

        # Zrestartuj bez parametru (powinno zresetować do kroku 1)
        restart_result = sequence.restart_sequence()

        assert restart_result is True
        assert sequence.status.current_step == 1
        assert sequence.status.finished is False

    def test_set_restart_target_step(self):
        """Test ustawiania atrybutu restart_to_step."""
        sequence = Sequence(produkt_id=2, enum_class=SequenceEnumForTesting)

        # Sprawdź domyślną wartość
        assert sequence.restart_target_step == 1

        # Ustaw nową wartość
        sequence.set_restart_target_step(3)
        assert sequence.restart_target_step == 3

        # Sprawdź że restart używa nowej wartości
        sequence.set_restart(True)
        sequence.set_can_restart(True)
        restart_result = sequence.restart_sequence()

        assert restart_result is True
        assert sequence.status.current_step == 3
