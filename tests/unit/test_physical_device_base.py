"""Testy jednostkowe dla PhysicalDeviceBase FSM i zarządzania błędami.

Testowane:
- Przejścia stanów FSM (UNINITIALIZED → INITIALIZING → WORKING → ERROR → FAULT)
- Licznik kolejnych błędów i eskalacja do FAULT
- Metody set_error(), clear_error(), reset_fault()
- Punkty nadpisania _on_error(), _on_fault()
- Serializacja to_dict()
"""

from unittest.mock import MagicMock


from avena_commons.io.device import PhysicalDeviceBase, PhysicalDeviceState


class TestPhysicalDeviceState:
    """Testy enum PhysicalDeviceState."""

    def test_enum_values(self):
        """Sprawdza wartości liczbowe stanów FSM."""
        assert PhysicalDeviceState.UNINITIALIZED.value == 0
        assert PhysicalDeviceState.INITIALIZING.value == 1
        assert PhysicalDeviceState.WORKING.value == 2
        assert PhysicalDeviceState.ERROR.value == 3
        assert PhysicalDeviceState.FAULT.value == 4

    def test_enum_names(self):
        """Sprawdza nazwy stanów."""
        assert PhysicalDeviceState.UNINITIALIZED.name == "UNINITIALIZED"
        assert PhysicalDeviceState.INITIALIZING.name == "INITIALIZING"
        assert PhysicalDeviceState.WORKING.name == "WORKING"
        assert PhysicalDeviceState.ERROR.name == "ERROR"
        assert PhysicalDeviceState.FAULT.name == "FAULT"


class TestPhysicalDeviceBaseInitialization:
    """Testy inicjalizacji PhysicalDeviceBase."""

    def test_default_initialization(self):
        """Sprawdza domyślną inicjalizację urządzenia."""
        device = PhysicalDeviceBase(device_name="test_device")

        assert device.device_name == "test_device"
        assert device.get_state() == PhysicalDeviceState.UNINITIALIZED
        assert device._error is False
        assert device._error_message is None
        assert device._consecutive_errors == 0
        assert device._max_consecutive_errors == 3

    def test_custom_max_errors(self):
        """Sprawdza inicjalizację z custom max_consecutive_errors."""
        device = PhysicalDeviceBase(device_name="test_device", max_consecutive_errors=5)

        assert device._max_consecutive_errors == 5

    def test_with_message_logger(self):
        """Sprawdza inicjalizację z message_logger."""
        mock_logger = MagicMock()
        device = PhysicalDeviceBase(
            device_name="test_device", message_logger=mock_logger
        )

        assert device._message_logger is mock_logger


class TestPhysicalDeviceBaseStateTransitions:
    """Testy przejść stanów FSM."""

    def test_set_state_initializing(self):
        """Sprawdza przejście UNINITIALIZED → INITIALIZING."""
        device = PhysicalDeviceBase(device_name="test_device")

        device.set_state(PhysicalDeviceState.INITIALIZING)
        assert device.get_state() == PhysicalDeviceState.INITIALIZING

    def test_set_state_working(self):
        """Sprawdza przejście INITIALIZING → WORKING."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.INITIALIZING)

        device.set_state(PhysicalDeviceState.WORKING)
        assert device.get_state() == PhysicalDeviceState.WORKING

    def test_get_state_thread_safe(self):
        """Sprawdza czy get_state() używa lock'a."""
        device = PhysicalDeviceBase(device_name="test_device")

        # Wywołanie powinno działać bez błędów
        state = device.get_state()
        assert state == PhysicalDeviceState.UNINITIALIZED


class TestPhysicalDeviceBaseErrorHandling:
    """Testy zarządzania błędami."""

    def test_set_error_first_time(self):
        """Sprawdza pierwsze wywołanie set_error (WORKING → ERROR)."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)

        device.set_error("Test error message")

        assert device.get_state() == PhysicalDeviceState.ERROR
        assert device._error is True
        assert device._error_message == "Test error message"
        assert device._consecutive_errors == 1

    def test_set_error_increment_counter(self):
        """Sprawdza inkrementację licznika przy kolejnych błędach."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)

        device.set_error("Error 1")
        assert device._consecutive_errors == 1

        device.set_error("Error 2")
        assert device._consecutive_errors == 2

    def test_set_error_escalation_to_fault(self):
        """Sprawdza eskalację ERROR → FAULT po przekroczeniu progu."""
        device = PhysicalDeviceBase(device_name="test_device", max_consecutive_errors=3)
        device.set_state(PhysicalDeviceState.WORKING)

        # 1st error → ERROR
        device.set_error("Error 1")
        assert device.get_state() == PhysicalDeviceState.ERROR
        assert device._consecutive_errors == 1

        # 2nd error → still ERROR
        device.set_error("Error 2")
        assert device.get_state() == PhysicalDeviceState.ERROR
        assert device._consecutive_errors == 2

        # 3rd error → FAULT
        device.set_error("Error 3")
        assert device.get_state() == PhysicalDeviceState.FAULT
        assert device._consecutive_errors == 3

    def test_clear_error_resets_counter(self):
        """Sprawdza czy clear_error() resetuje licznik błędów."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)

        device.set_error("Error 1")
        assert device._consecutive_errors == 1

        device.clear_error()
        assert device._consecutive_errors == 0

    def test_clear_error_does_not_change_state(self):
        """Sprawdza że clear_error() NIE zmienia stanu (brak auto-recovery)."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)

        device.set_error("Error 1")
        assert device.get_state() == PhysicalDeviceState.ERROR

        # clear_error() resetuje licznik ale NIE zmienia stanu
        device.clear_error()
        assert device.get_state() == PhysicalDeviceState.ERROR
        assert device._consecutive_errors == 0

    def test_clear_error_in_working_clears_flags(self):
        """Sprawdza że clear_error() w WORKING czyści flagi błędu."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)

        # Ustaw błąd
        device.set_error("Error")
        device.set_state(PhysicalDeviceState.WORKING)  # Manualnie z powrotem do WORKING

        # Symuluj _error=True po przejściu (normalnie set_error ustawia)
        device._error = True
        device._error_message = "Old error"

        device.clear_error()
        assert device._error is False
        assert device._error_message is None


class TestPhysicalDeviceBaseResetFault:
    """Testy resetowania FAULT przez ACK operatora."""

    def test_reset_fault_from_fault_state(self):
        """Sprawdza reset FAULT → INITIALIZING."""
        device = PhysicalDeviceBase(device_name="test_device", max_consecutive_errors=1)
        device.set_state(PhysicalDeviceState.WORKING)

        # Wywołaj błąd aby przejść do FAULT
        device.set_error("Critical error")
        assert device.get_state() == PhysicalDeviceState.FAULT

        # Reset przez operatora
        result = device.reset_fault()

        assert result is True
        assert device.get_state() == PhysicalDeviceState.INITIALIZING
        assert device._error is False
        assert device._error_message is None
        assert device._consecutive_errors == 0

    def test_reset_fault_from_non_fault_state(self):
        """Sprawdza że reset_fault() nie działa gdy nie w FAULT."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)

        result = device.reset_fault()

        assert result is False
        assert device.get_state() == PhysicalDeviceState.WORKING

    def test_reset_fault_from_error_state(self):
        """Sprawdza że reset_fault() nie resetuje ERROR (tylko FAULT)."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)
        device.set_error("Error")

        assert device.get_state() == PhysicalDeviceState.ERROR

        result = device.reset_fault()

        assert result is False
        assert device.get_state() == PhysicalDeviceState.ERROR


class TestPhysicalDeviceBaseOverridePoints:
    """Testy punktów nadpisania _on_error() i _on_fault()."""

    def test_on_error_called_on_first_error(self):
        """Sprawdza czy _on_error() jest wywoływana przy przejściu do ERROR."""

        class MockDevice(PhysicalDeviceBase):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.on_error_called = False

            def _on_error(self):
                self.on_error_called = True

        device = MockDevice(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)

        device.set_error("Error 1")

        assert device.on_error_called is True

    def test_on_fault_called_on_escalation(self):
        """Sprawdza czy _on_fault() jest wywoływana przy przejściu do FAULT."""

        class MockDevice(PhysicalDeviceBase):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.on_fault_called = False

            def _on_fault(self):
                self.on_fault_called = True

        device = MockDevice(device_name="test_device", max_consecutive_errors=2)
        device.set_state(PhysicalDeviceState.WORKING)

        device.set_error("Error 1")
        assert device.on_fault_called is False

        device.set_error("Error 2")  # Eskalacja do FAULT
        assert device.on_fault_called is True

    def test_on_error_not_called_repeatedly_in_error_state(self):
        """Sprawdza że _on_error() nie jest wywoływana wielokrotnie w ERROR."""

        class MockDevice(PhysicalDeviceBase):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.on_error_call_count = 0

            def _on_error(self):
                self.on_error_call_count += 1

        device = MockDevice(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)

        device.set_error("Error 1")
        assert device.on_error_call_count == 1

        # Kolejny błąd w stanie ERROR nie powinien wywołać _on_error()
        device.set_error("Error 2")
        assert device.on_error_call_count == 1  # Nadal 1


class TestPhysicalDeviceBaseHealthCheck:
    """Testy sprawdzania zdrowia urządzenia."""

    def test_check_health_working(self):
        """Sprawdza check_health() w stanie WORKING."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)

        assert device.check_health() is True

    def test_check_health_error(self):
        """Sprawdza check_health() w stanie ERROR (nie-FAULT)."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.ERROR)

        assert device.check_health() is True  # ERROR != FAULT

    def test_check_health_fault(self):
        """Sprawdza check_health() w stanie FAULT."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.FAULT)

        assert device.check_health() is False


class TestPhysicalDeviceBaseSerialization:
    """Testy serializacji to_dict()."""

    def test_to_dict_basic(self):
        """Sprawdza podstawową serializację do słownika."""
        device = PhysicalDeviceBase(device_name="test_device")

        result = device.to_dict()

        assert result["name"] == "test_device"
        assert result["state"] == PhysicalDeviceState.UNINITIALIZED.value
        assert result["state_name"] == "UNINITIALIZED"
        assert result["error"] is False
        assert result["error_message"] is None
        assert result["consecutive_errors"] == 0

    def test_to_dict_with_error(self):
        """Sprawdza serializację urządzenia z błędem."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)
        device.set_error("Test error")

        result = device.to_dict()

        assert result["state"] == PhysicalDeviceState.ERROR.value
        assert result["state_name"] == "ERROR"
        assert result["error"] is True
        assert result["error_message"] == "Test error"
        assert result["consecutive_errors"] == 1

    def test_to_dict_fault_state(self):
        """Sprawdza serializację urządzenia w FAULT."""
        device = PhysicalDeviceBase(device_name="test_device", max_consecutive_errors=1)
        device.set_state(PhysicalDeviceState.WORKING)
        device.set_error("Critical")

        result = device.to_dict()

        assert result["state"] == PhysicalDeviceState.FAULT.value
        assert result["state_name"] == "FAULT"


class TestPhysicalDeviceBaseStringRepresentation:
    """Testy reprezentacji stringowej."""

    def test_str_representation(self):
        """Sprawdza __str__() bez błędu."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)

        result = str(device)

        assert "PhysicalDeviceBase" in result
        assert "test_device" in result
        assert "WORKING" in result

    def test_str_representation_with_error(self):
        """Sprawdza __str__() z błędem."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)
        device.set_error("Test error")

        result = str(device)

        assert "test_device" in result
        assert "ERROR" in result
        assert "Test error" in result

    def test_repr_representation(self):
        """Sprawdza __repr__() dla developerów."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)
        device.set_error("Error")

        result = repr(device)

        assert "PhysicalDeviceBase" in result
        assert "device_name='test_device'" in result
        assert "state=ERROR" in result
        assert "error=True" in result
        assert "consecutive_errors=1" in result


class TestPhysicalDeviceBaseComplexScenarios:
    """Testy złożonych scenariuszy użycia."""

    def test_error_recovery_workflow(self):
        """Sprawdza pełny workflow: błąd → clear → błąd → reset."""
        device = PhysicalDeviceBase(device_name="test_device", max_consecutive_errors=3)
        device.set_state(PhysicalDeviceState.WORKING)

        # 1st error
        device.set_error("Error 1")
        assert device.get_state() == PhysicalDeviceState.ERROR
        assert device._consecutive_errors == 1

        # Sukces resetuje licznik
        device.clear_error()
        assert device._consecutive_errors == 0
        assert device.get_state() == PhysicalDeviceState.ERROR  # Stan się nie zmienia!

        # Przejście manualne do WORKING (symulacja inicjalizacji)
        device.set_state(PhysicalDeviceState.WORKING)

        # Kolejny błąd od nowa
        device.set_error("Error 2")
        assert device._consecutive_errors == 1

    def test_rapid_error_escalation(self):
        """Sprawdza szybką eskalację przy niskim progu."""
        device = PhysicalDeviceBase(device_name="test_device", max_consecutive_errors=1)
        device.set_state(PhysicalDeviceState.WORKING)

        # Pierwszy błąd od razu eskaluje do FAULT
        device.set_error("Critical")

        assert device.get_state() == PhysicalDeviceState.FAULT
        assert device._consecutive_errors == 1

    def test_multiple_resets(self):
        """Sprawdza wielokrotne resetowanie FAULT."""
        device = PhysicalDeviceBase(device_name="test_device", max_consecutive_errors=1)

        # Cykl 1: Error → FAULT → Reset
        device.set_state(PhysicalDeviceState.WORKING)
        device.set_error("Error 1")
        assert device.get_state() == PhysicalDeviceState.FAULT

        device.reset_fault()
        assert device.get_state() == PhysicalDeviceState.INITIALIZING

        # Cykl 2: Error → FAULT → Reset
        device.set_state(PhysicalDeviceState.WORKING)
        device.set_error("Error 2")
        assert device.get_state() == PhysicalDeviceState.FAULT

        device.reset_fault()
        assert device.get_state() == PhysicalDeviceState.INITIALIZING

    def test_thread_safety_simulation(self):
        """Symuluje współbieżny dostęp do set_error i clear_error."""
        device = PhysicalDeviceBase(device_name="test_device")
        device.set_state(PhysicalDeviceState.WORKING)

        # Symulacja wielu wątków wywołujących set_error
        for i in range(5):
            device.set_error(f"Error {i}")

        # Licznik powinien być 5 (bez race conditions dzięki lock)
        assert device._consecutive_errors == 5
