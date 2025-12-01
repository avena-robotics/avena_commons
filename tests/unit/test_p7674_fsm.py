"""Testy jednostkowe dla P7674 z PhysicalDeviceBase FSM.

Testowane:
- Inicjalizacja z PhysicalDeviceBase
- Wątki DI/DO z obsługą set_error/clear_error
- Przejścia stanów przy błędach komunikacji
- Integracja FSM z wątkami roboczymi
"""

import time
from unittest.mock import MagicMock, patch


from avena_commons.io.device import PhysicalDeviceState
from avena_commons.io.device.io.p7674 import P7674


class TestP7674Initialization:
    """Testy inicjalizacji P7674."""

    def test_basic_initialization(self):
        """Sprawdza podstawową inicjalizację P7674."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1, period=0.1)

        assert device.device_name == "test_p7674"
        assert device.address == 1
        assert device.bus is mock_bus
        assert device.offset == 0
        assert device.period == 0.1

    def test_initialization_with_custom_max_errors(self):
        """Sprawdza inicjalizację z custom max_consecutive_errors."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0

        device = P7674(
            device_name="test_p7674", bus=mock_bus, address=1, max_consecutive_errors=5
        )

        assert device._max_consecutive_errors == 5

    def test_initialization_starts_working_on_success(self):
        """Sprawdza przejście do WORKING po udanej inicjalizacji."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1)

        # check_device_connection powinno zwrócić True i ustawić WORKING
        assert device.get_state() == PhysicalDeviceState.WORKING

    def test_initialization_sets_error_on_failure(self):
        """Sprawdza ustawienie błędu przy niepowodzeniu inicjalizacji."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = None  # Błąd komunikacji

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1)

        # Urządzenie powinno być w ERROR/FAULT z powodu błędu
        assert device.get_state() in {
            PhysicalDeviceState.ERROR,
            PhysicalDeviceState.FAULT,
        }

    def test_threads_started(self):
        """Sprawdza czy wątki DI/DO są uruchomione."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1, period=0.1)

        time.sleep(0.05)  # Czas na start wątków

        assert device._di_thread is not None
        assert device._di_thread.is_alive()
        assert device._do_thread is not None
        assert device._do_thread.is_alive()

        # Cleanup
        device.__del__()


class TestP7674DIThread:
    """Testy wątku odczytu DI."""

    def test_di_thread_reads_successfully(self):
        """Sprawdza czy wątek DI czyta wartości i wywołuje clear_error."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0b1010  # Testowa wartość DI

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1, period=0.05)

        time.sleep(0.15)  # Czas na kilka cykli wątku

        # Sprawdź czy wartość została odczytana
        assert device.di_value == 0b1010
        assert device._consecutive_errors == 0  # clear_error powinno resetować

        # Cleanup
        device.__del__()

    def test_di_thread_handles_error(self):
        """Sprawdza reakcję wątku DI na błąd komunikacji."""
        mock_bus = MagicMock()
        # Pierwsza próba OK (inicjalizacja), potem błędy
        mock_bus.read_holding_register.side_effect = [0, None, None, None]

        device = P7674(
            device_name="test_p7674",
            bus=mock_bus,
            address=1,
            period=0.05,
            max_consecutive_errors=3,
        )

        time.sleep(0.25)  # Czas na kilka błędnych cykli

        # Powinno być ERROR lub FAULT
        assert device.get_state() in {
            PhysicalDeviceState.ERROR,
            PhysicalDeviceState.FAULT,
        }
        assert device._consecutive_errors > 0

        # Cleanup
        device.__del__()

    def test_di_thread_escalates_to_fault(self):
        """Sprawdza eskalację do FAULT po przekroczeniu progu błędów."""
        mock_bus = MagicMock()
        # Inicjalizacja OK, potem ciągłe błędy
        mock_bus.read_holding_register.side_effect = [0] + [None] * 10

        device = P7674(
            device_name="test_p7674",
            bus=mock_bus,
            address=1,
            period=0.05,
            max_consecutive_errors=2,
        )

        time.sleep(0.3)  # Czas na przekroczenie progu

        # Po 2 błędach powinno być FAULT
        assert device.get_state() == PhysicalDeviceState.FAULT

        # Cleanup
        device.__del__()

    def test_di_method_returns_correct_bit(self):
        """Sprawdza czy metoda di() zwraca poprawne bity."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0b1010  # bity 1 i 3 ustawione

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1, offset=0)

        time.sleep(0.1)  # Czas na odczyt

        # Sprawdź poszczególne bity (indeksowanie od 0)
        assert device.di(0) == 0  # bit 0: 0
        assert device.di(1) == 1  # bit 1: 1
        assert device.di(2) == 0  # bit 2: 0
        assert device.di(3) == 1  # bit 3: 1

        # Cleanup
        device.__del__()


class TestP7674DOThread:
    """Testy wątku zapisu DO."""

    def test_do_thread_writes_on_change(self):
        """Sprawdza czy wątek DO zapisuje zmiany."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1, period=0.05)

        # Ustaw DO
        device.do(0, True)
        device.do(3, True)

        time.sleep(0.15)  # Czas na zapis

        # Sprawdź czy write_coils został wywołany
        assert mock_bus.write_coils.called

        # Sprawdź czy zapisany stan zawiera nasze ustawienia
        call_args = mock_bus.write_coils.call_args
        written_state = call_args[1]["values"]
        assert written_state[0] == 1  # DO 0 = True
        assert written_state[3] == 1  # DO 3 = True

        # Cleanup
        device.__del__()

    def test_do_thread_handles_write_error(self):
        """Sprawdza reakcję wątku DO na błąd zapisu."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0
        mock_bus.write_coils.side_effect = Exception("Write error")

        device = P7674(
            device_name="test_p7674",
            bus=mock_bus,
            address=1,
            period=0.05,
            max_consecutive_errors=2,
        )

        # Zmień stan DO aby wywołać zapis
        device.do(0, True)

        time.sleep(0.2)  # Czas na próby zapisu i błędy

        # Powinno być ERROR lub FAULT
        assert device.get_state() in {
            PhysicalDeviceState.ERROR,
            PhysicalDeviceState.FAULT,
        }

        # Cleanup
        device.__del__()

    def test_do_method_updates_buffer(self):
        """Sprawdza czy metoda do() aktualizuje bufor."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1)

        # Ustaw wartości DO
        device.do(0, True)
        device.do(5, True)
        device.do(15, False)

        # Sprawdź bufor (offset=0)
        assert device.coil_state[0] == 1
        assert device.coil_state[5] == 1
        assert device.coil_state[15] == 0

        # Cleanup
        device.__del__()

    def test_do_method_returns_current_state(self):
        """Sprawdza czy do() bez value zwraca aktualny stan."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1)

        device.do(3, True)

        # Odczyt stanu
        assert device.do(3) == 1
        assert device.do(4) == 0

        # Cleanup
        device.__del__()


class TestP7674ErrorRecovery:
    """Testy mechanizmu error recovery w P7674."""

    def test_clear_error_after_success(self):
        """Sprawdza czy clear_error resetuje licznik po sukcesie."""
        mock_bus = MagicMock()
        # Inicjalizacja OK, potem tylko sukcesy
        mock_bus.read_holding_register.return_value = 0xAA

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1, period=0.05)

        # Manualnie ustaw błędy
        device._consecutive_errors = 2

        time.sleep(0.15)  # Czas na kilka udanych cykli

        # Po sukcesach licznik powinien być zresetowany przez clear_error()
        assert device._consecutive_errors == 0

        # Cleanup
        device.__del__()


class TestP7674CheckDeviceConnection:
    """Testy check_device_connection z FSM."""

    def test_check_connection_returns_false_in_fault(self):
        """Sprawdza że check_device_connection zwraca False w FAULT."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1)

        # Wymuszenie stanu FAULT
        device.set_state(PhysicalDeviceState.FAULT)

        # check_device_connection powinno zwrócić False
        assert device.check_device_connection() is False

        # Cleanup
        device.__del__()

    def test_check_connection_calls_modbus_check(self):
        """Sprawdza że check_device_connection wywołuje sprawdzenie Modbus."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1)

        device.set_state(PhysicalDeviceState.WORKING)

        # Wywołaj check
        with patch(
            "avena_commons.io.device.io.p7674.modbus_check_device_connection",
            return_value=True,
        ) as mock_check:
            result = device.check_device_connection()

            assert result is True
            assert mock_check.called

        # Cleanup
        device.__del__()


class TestP7674Serialization:
    """Testy serializacji P7674."""

    def test_to_dict_includes_base_and_p7674_fields(self):
        """Sprawdza że to_dict zawiera pola z PhysicalDeviceBase i P7674."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0b1010

        device = P7674(
            device_name="test_p7674", bus=mock_bus, address=5, offset=2, period=0.1
        )

        time.sleep(0.1)

        result = device.to_dict()

        # Pola z PhysicalDeviceBase
        assert result["name"] == "test_p7674"
        assert "state" in result
        assert "state_name" in result
        assert "error" in result
        assert "consecutive_errors" in result

        # Pola specyficzne dla P7674
        assert result["address"] == 5
        assert result["offset"] == 2
        assert result["period"] == 0.1
        assert "di_value" in result
        assert "coil_state" in result
        assert "active_di_count" in result
        assert "active_do_count" in result

        # Cleanup
        device.__del__()

    def test_to_dict_calculates_active_counts(self):
        """Sprawdza obliczanie active_di_count i active_do_count."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0b1110  # 3 bity

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1)

        time.sleep(0.1)

        device.do(0, True)
        device.do(1, True)

        result = device.to_dict()

        assert result["active_di_count"] == 3  # 3 bity w 0b1110
        assert result["active_do_count"] == 2  # 2 DO ustawione

        # Cleanup
        device.__del__()


class TestP7674StringRepresentation:
    """Testy reprezentacji stringowej P7674."""

    def test_str_shows_device_state(self):
        """Sprawdza __str__ reprezentację."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1)

        result = str(device)

        assert "P7674" in result
        assert "test_p7674" in result

        # Cleanup
        device.__del__()

    def test_repr_shows_technical_details(self):
        """Sprawdza __repr__ dla developerów."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0

        device = P7674(device_name="test_p7674", bus=mock_bus, address=5, offset=2)

        result = repr(device)

        assert "P7674" in result
        assert "test_p7674" in result
        assert "address=5" in result
        assert "offset=2" in result

        # Cleanup
        device.__del__()


class TestP7674Cleanup:
    """Testy czyszczenia zasobów."""

    def test_del_stops_threads(self):
        """Sprawdza czy __del__ zatrzymuje wątki."""
        mock_bus = MagicMock()
        mock_bus.read_holding_register.return_value = 0

        device = P7674(device_name="test_p7674", bus=mock_bus, address=1, period=0.1)

        time.sleep(0.1)

        # Zachowaj referencje do wątków przed __del__
        di_thread = device._di_thread
        do_thread = device._do_thread

        assert di_thread.is_alive()
        assert do_thread.is_alive()

        # Wywołaj cleanup
        device.__del__()

        time.sleep(0.2)  # Czas na zamknięcie wątków

        # Wątki powinny być zatrzymane
        assert not di_thread.is_alive()
        assert not do_thread.is_alive()
