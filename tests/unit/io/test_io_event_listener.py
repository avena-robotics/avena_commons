"""
Testy jednostkowe dla modułu io_event_listener.

Ten moduł zawiera kompleksowe testy dla klasy IO_server, które pokrywają
różne scenariusze inicjalizacji, przetwarzania eventów i zarządzania urządzeniami.
Testy są podzielone na logiczne grupy i wykorzystują mock'i dla izolacji testów.
"""

import json
import pytest
from unittest.mock import (
    Mock,
    patch,
    # MagicMock,
    mock_open,
    # call,
    AsyncMock,
    PropertyMock,
)
# from pathlib import Path
import tempfile
import os
# import asyncio

from avena_commons.io.io_event_listener import IO_server
from avena_commons.event_listener.event import Event
from avena_commons.util.logger import MessageLogger


class TestIOServerInitialization:
    """Testy inicjalizacji klasy IO_server."""

    @pytest.fixture
    def mock_message_logger(self):
        """Fixture dla mock'a MessageLogger."""
        return Mock(spec=MessageLogger)

    @pytest.fixture
    def sample_config(self):
        """Fixture z przykładową konfiguracją."""
        return {
            "bus": {
                "modbus_1": {
                    "class": "ModbusRTU",
                    "configuration": {"port": "/dev/ttyUSB0", "baudrate": 9600},
                }
            },
            "device": {
                "motor1": {
                    "class": "MotorDriver",
                    "configuration": {"address": 1},
                    "bus": "modbus_1",
                }
            },
            "virtual_device": {
                "feeder1": {
                    "class": "Feeder",
                    "methods": {"start": {"device": "motor1", "method": "start_motor"}},
                }
            },
        }

    @pytest.fixture
    def temp_config_file(self, sample_config):
        """Fixture tworząca tymczasowy plik konfiguracji."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(sample_config, f)
            temp_path = f.name

        yield temp_path

        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    def test_init_successful(self, mock_message_logger, temp_config_file):
        """Test pomyślnej inicjalizacji IO_server."""
        with (
            patch.object(IO_server, "_load_device_configuration") as mock_load,
            patch.object(IO_server, "_build_state_dict") as mock_build_state,
            patch(
                "avena_commons.io.io_event_listener.EventListener.__init__"
            ) as mock_super_init,
        ):
            mock_build_state.return_value = {"test": "state"}
            mock_super_init.return_value = None

            server = IO_server(
                name="test_server",
                port=8080,
                configuration_file=temp_config_file,
                general_config_file="general.json",
                message_logger=mock_message_logger,
                debug=True,
            )

            # Sprawdź czy inicjalizacja przebiegła pomyślnie
            assert server._message_logger == mock_message_logger
            assert server._debug is True
            assert server.check_local_data_frequency == 50

            # Sprawdź czy metody zostały wywołane
            mock_load.assert_called_once_with(temp_config_file, "general.json")
            mock_build_state.assert_called_once()
            mock_super_init.assert_called_once()

    def test_init_with_exception(self, mock_message_logger, temp_config_file):
        """Test inicjalizacji z wyjątkiem."""
        with (
            patch.object(IO_server, "_load_device_configuration") as mock_load,
            patch("avena_commons.io.io_event_listener.error") as mock_error,
        ):
            mock_load.side_effect = Exception("Test exception")

            server = IO_server(
                name="test_server",
                port=8080,
                configuration_file=temp_config_file,
                general_config_file="general.json",
                message_logger=mock_message_logger,
                debug=True,
            )

            # Sprawdź czy błąd został zalogowany
            mock_error.assert_called_once()
            assert "Initialisation error" in mock_error.call_args[0][0]

    def test_init_default_parameters(self, temp_config_file):
        """Test inicjalizacji z domyślnymi parametrami."""
        with (
            patch.object(IO_server, "_load_device_configuration"),
            patch.object(IO_server, "_build_state_dict"),
            patch("avena_commons.io.io_event_listener.EventListener.__init__"),
        ):
            server = IO_server(
                name="test_server",
                port=8080,
                configuration_file=temp_config_file,
                general_config_file="general.json",
            )

            # Sprawdź domyślne wartości
            assert server._message_logger is None
            assert server._debug is True


class TestEventAnalysis:
    """Testy analizy i przetwarzania eventów."""

    @pytest.fixture
    def mock_server(self):
        """Fixture dla mock'a IO_server."""
        with (
            patch.object(IO_server, "_load_device_configuration"),
            patch.object(IO_server, "_build_state_dict"),
            patch("avena_commons.io.io_event_listener.EventListener.__init__"),
        ):
            server = IO_server(
                name="test_server",
                port=8080,
                configuration_file="test.json",
                general_config_file="general.json",
                debug=True,
            )

            server._add_to_processing = Mock()
            server.device_selector = AsyncMock()
            return server

    @pytest.mark.asyncio
    async def test_analyze_event_successful(self, mock_server):
        """Test pomyślnej analizy eventu."""
        # Przygotuj dane
        test_event = Event(
            event_type="motor_start",
            source="test_source",
            data={"device_id": "1", "action": "start"},
        )

        mock_server.device_selector.return_value = True

        # Wykonaj test
        result = await mock_server._analyze_event(test_event)

        # Sprawdź rezultat
        assert result is True
        mock_server.device_selector.assert_called_once_with(test_event)
        mock_server._add_to_processing.assert_called_once_with(test_event)

    @pytest.mark.asyncio
    async def test_analyze_event_not_added_to_processing(self, mock_server):
        """Test analizy eventu, który nie zostaje dodany do przetwarzania."""
        test_event = Event(
            event_type="motor_start",
            source="test_source",
            data={"device_id": "1", "action": "start"},
        )

        mock_server.device_selector.return_value = False

        result = await mock_server._analyze_event(test_event)

        assert result is True
        mock_server.device_selector.assert_called_once_with(test_event)
        mock_server._add_to_processing.assert_not_called()

    @pytest.mark.asyncio
    async def test_analyze_event_with_debug_logging(self, mock_server):
        """Test analizy eventu z logowaniem debug."""
        test_event = Event(
            event_type="motor_start", source="test_source", data={"device_id": "1"}
        )

        mock_server.device_selector.return_value = True

        with patch("avena_commons.io.io_event_listener.debug") as mock_debug:
            result = await mock_server._analyze_event(test_event)

            assert result is True
            mock_debug.assert_called_once()
            assert "Analyzing event" in mock_debug.call_args[0][0]


class TestDeviceSelector:
    """Testy selekcji urządzeń."""

    @pytest.fixture
    def mock_server_with_devices(self):
        """Fixture dla mock'a IO_server z urządzeniami wirtualnymi."""
        with (
            patch.object(IO_server, "_load_device_configuration"),
            patch.object(IO_server, "_build_state_dict"),
            patch("avena_commons.io.io_event_listener.EventListener.__init__"),
        ):
            server = IO_server(
                name="test_server",
                port=8080,
                configuration_file="test.json",
                general_config_file="general.json",
                debug=True,
            )

            # Dodaj mock urządzenia wirtualne
            mock_device = Mock()
            mock_device.execute_event = Mock()

            server.virtual_devices = {"motor1": mock_device}

            server._reply = Mock()
            return server

    @pytest.mark.asyncio
    async def test_device_selector_missing_device_id(self, mock_server_with_devices):
        """Test selekcji urządzenia bez device_id."""
        test_event = Event(
            event_type="motor_start",
            source="test_source",
            data={"action": "start"},  # Brak device_id
        )

        with patch("avena_commons.io.io_event_listener.error") as mock_error:
            result = await mock_server_with_devices.device_selector(test_event)

            assert result is False
            mock_error.assert_called_once()
            assert "Device ID not found" in mock_error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_device_selector_missing_event_type(self, mock_server_with_devices):
        """Test selekcji urządzenia bez event_type."""
        test_event = Event(
            event_type="",  # Pusty event_type
            source="test_source",
            data={"device_id": "1"},
        )

        with patch("avena_commons.io.io_event_listener.error") as mock_error:
            result = await mock_server_with_devices.device_selector(test_event)

            assert result is False
            mock_error.assert_called_once()
            assert "Action type is missing" in mock_error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_device_selector_invalid_event_type_format(
        self, mock_server_with_devices
    ):
        """Test selekcji urządzenia z nieprawidłowym formatem event_type."""
        test_event = Event(
            event_type="invalid",  # Brak podkreślenia
            source="test_source",
            data={"device_id": "1"},
        )

        with patch("avena_commons.io.io_event_listener.error") as mock_error:
            result = await mock_server_with_devices.device_selector(test_event)

            assert result is False
            mock_error.assert_called_once()
            assert "Invalid event_type format" in mock_error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_device_selector_device_not_found(self, mock_server_with_devices):
        """Test selekcji nieistniejącego urządzenia."""
        test_event = Event(
            event_type="nonexistent_start",
            source="test_source",
            data={"device_id": "999"},
        )

        with patch("avena_commons.io.io_event_listener.error") as mock_error:
            result = await mock_server_with_devices.device_selector(test_event)

            assert result is False
            mock_error.assert_called_once()
            assert (
                "Virtual device nonexistent999 not found" in mock_error.call_args[0][0]
            )

    @pytest.mark.asyncio
    async def test_device_selector_method_not_found(self, mock_server_with_devices):
        """Test selekcji urządzenia bez odpowiedniej metody."""
        test_event = Event(
            event_type="motor_start", source="test_source", data={"device_id": "1"}
        )

        # Usuń metodę z mock urządzenia
        del mock_server_with_devices.virtual_devices["motor1"].execute_event

        with patch("avena_commons.io.io_event_listener.error") as mock_error:
            result = await mock_server_with_devices.device_selector(test_event)

            assert result is False
            mock_error.assert_called_once()
            assert "Method execute_event not found" in mock_error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_device_selector_successful_with_event_return(
        self, mock_server_with_devices
    ):
        """Test pomyślnej selekcji urządzenia z zwróceniem eventu."""
        test_event = Event(
            event_type="motor_start", source="test_source", data={"device_id": "1"}
        )

        # Skonfiguruj mock urządzenie do zwrócenia eventu
        return_event = Event(
            event_type="motor_started", source="device", data={"status": "success"}
        )
        mock_server_with_devices.virtual_devices[
            "motor1"
        ].execute_event.return_value = return_event

        result = await mock_server_with_devices.device_selector(test_event)

        assert result is False  # Nie dodaje do przetwarzania
        mock_server_with_devices.virtual_devices[
            "motor1"
        ].execute_event.assert_called_once_with(test_event)
        mock_server_with_devices._reply.assert_called_once_with(return_event)

    @pytest.mark.asyncio
    async def test_device_selector_successful_without_event_return(
        self, mock_server_with_devices
    ):
        """Test pomyślnej selekcji urządzenia bez zwrócenia eventu."""
        test_event = Event(
            event_type="motor_start", source="test_source", data={"device_id": "1"}
        )

        # Skonfiguruj mock urządzenie do zwrócenia None
        mock_server_with_devices.virtual_devices[
            "motor1"
        ].execute_event.return_value = None

        result = await mock_server_with_devices.device_selector(test_event)

        assert result is True  # Dodaje do przetwarzania
        mock_server_with_devices.virtual_devices[
            "motor1"
        ].execute_event.assert_called_once_with(test_event)
        mock_server_with_devices._reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_device_selector_exception_in_method_call(
        self, mock_server_with_devices
    ):
        """Test obsługi wyjątku podczas wywołania metody urządzenia."""
        test_event = Event(
            event_type="motor_start", source="test_source", data={"device_id": "1"}
        )

        # Skonfiguruj mock urządzenie do rzucania wyjątku
        mock_server_with_devices.virtual_devices[
            "motor1"
        ].execute_event.side_effect = Exception("Test exception")

        with patch("avena_commons.io.io_event_listener.error") as mock_error:
            result = await mock_server_with_devices.device_selector(test_event)

            assert result is False
            mock_error.assert_called_once()
            assert "Error calling method execute_event" in mock_error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_device_selector_no_virtual_devices_attribute(
        self, mock_server_with_devices
    ):
        """Test selekcji urządzenia gdy brak atrybutu virtual_devices."""
        test_event = Event(
            event_type="motor_start", source="test_source", data={"device_id": "1"}
        )

        # Usuń atrybut virtual_devices
        del mock_server_with_devices.virtual_devices

        with patch("avena_commons.io.io_event_listener.error") as mock_error:
            result = await mock_server_with_devices.device_selector(test_event)

            assert result is False
            mock_error.assert_called_once()
            assert "Virtual device motor1 not found" in mock_error.call_args[0][0]


class TestCheckLocalData:
    """Testy metody _check_local_data."""

    @pytest.fixture
    def mock_server_with_devices(self):
        """Fixture dla mock'a IO_server z urządzeniami wirtualnymi."""
        with (
            patch.object(IO_server, "_load_device_configuration"),
            patch.object(IO_server, "_build_state_dict"),
            patch("avena_commons.io.io_event_listener.EventListener.__init__"),
        ):
            server = IO_server(
                name="test_server",
                port=8080,
                configuration_file="test.json",
                general_config_file="general.json",
                debug=True,
            )

            # Dodaj mock urządzenia wirtualne
            mock_device1 = Mock()
            mock_device1.tick = Mock()
            mock_device1.finished_events = Mock(return_value=[])

            mock_device2 = Mock()
            mock_device2.tick = Mock()
            mock_device2.finished_events = Mock(return_value=[])

            server.virtual_devices = {"device1": mock_device1, "device2": mock_device2}

            server._find_and_remove_processing_event = Mock()
            server._reply = Mock()

            return server

    @pytest.mark.asyncio
    async def test_check_local_data_successful(self, mock_server_with_devices):
        """Test pomyślnego sprawdzenia lokalnych danych."""
        with patch("avena_commons.io.io_event_listener.MeasureTime") as mock_measure:
            mock_measure.return_value.__enter__ = Mock(return_value=mock_measure)
            mock_measure.return_value.__exit__ = Mock(return_value=None)

            await mock_server_with_devices._check_local_data()

            # Sprawdź czy tick został wywołany dla każdego urządzenia
            mock_server_with_devices.virtual_devices[
                "device1"
            ].tick.assert_called_once()
            mock_server_with_devices.virtual_devices[
                "device2"
            ].tick.assert_called_once()

            # Sprawdź czy finished_events został wywołany dla każdego urządzenia
            mock_server_with_devices.virtual_devices[
                "device1"
            ].finished_events.assert_called_once()
            mock_server_with_devices.virtual_devices[
                "device2"
            ].finished_events.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_local_data_with_finished_events(
        self, mock_server_with_devices
    ):
        """Test sprawdzenia lokalnych danych z gotowymi eventami."""
        # Przygotuj gotowe eventy
        finished_event = Event(
            event_type="motor_finished", source="device", data={"status": "completed"}
        )

        mock_server_with_devices.virtual_devices[
            "device1"
        ].finished_events.return_value = [finished_event]
        mock_server_with_devices._find_and_remove_processing_event.return_value = (
            finished_event
        )

        with (
            patch("avena_commons.io.io_event_listener.MeasureTime") as mock_measure,
            patch("avena_commons.io.io_event_listener.debug") as mock_debug,
        ):
            mock_measure.return_value.__enter__ = Mock(return_value=mock_measure)
            mock_measure.return_value.__exit__ = Mock(return_value=None)

            await mock_server_with_devices._check_local_data()

            # Sprawdź czy event został przetworzony
            mock_server_with_devices._find_and_remove_processing_event.assert_called_once_with(
                event=finished_event
            )
            mock_server_with_devices._reply.assert_called_once_with(finished_event)

    @pytest.mark.asyncio
    async def test_check_local_data_tick_exception(self, mock_server_with_devices):
        """Test obsługi wyjątku w metodzie tick."""
        # Skonfiguruj mock urządzenie do rzucania wyjątku
        mock_server_with_devices.virtual_devices[
            "device1"
        ].tick.side_effect = Exception("Tick exception")

        with (
            patch("avena_commons.io.io_event_listener.MeasureTime") as mock_measure,
            patch("avena_commons.io.io_event_listener.error") as mock_error,
        ):
            mock_measure.return_value.__enter__ = Mock(return_value=mock_measure)
            mock_measure.return_value.__exit__ = Mock(return_value=None)

            await mock_server_with_devices._check_local_data()

            # Sprawdź czy błąd został zalogowany
            mock_error.assert_called()
            assert "Error calling tick()" in mock_error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_check_local_data_finished_events_exception(
        self, mock_server_with_devices
    ):
        """Test obsługi wyjątku w przetwarzaniu finished_events."""
        # Przygotuj gotowe eventy
        finished_event = Event(
            event_type="motor_finished", source="device", data={"status": "completed"}
        )

        mock_server_with_devices.virtual_devices[
            "device1"
        ].finished_events.return_value = [finished_event]
        mock_server_with_devices._find_and_remove_processing_event.side_effect = (
            Exception("Processing exception")
        )

        with (
            patch("avena_commons.io.io_event_listener.MeasureTime") as mock_measure,
            patch("avena_commons.io.io_event_listener.error") as mock_error,
        ):
            mock_measure.return_value.__enter__ = Mock(return_value=mock_measure)
            mock_measure.return_value.__exit__ = Mock(return_value=None)

            await mock_server_with_devices._check_local_data()

            # Sprawdź czy błąd został zalogowany
            mock_error.assert_called()
            assert "Error processing events" in mock_error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_check_local_data_no_virtual_devices(self, mock_server_with_devices):
        """Test gdy nie ma urządzeń wirtualnych."""
        del mock_server_with_devices.virtual_devices

        with patch("avena_commons.io.io_event_listener.MeasureTime") as mock_measure:
            mock_measure.return_value.__enter__ = Mock(return_value=mock_measure)
            mock_measure.return_value.__exit__ = Mock(return_value=None)

            # Nie powinno rzucać wyjątku
            await mock_server_with_devices._check_local_data()

    @pytest.mark.asyncio
    async def test_check_local_data_invalid_finished_event(
        self, mock_server_with_devices
    ):
        """Test obsługi nieprawidłowego finished_event."""
        # Przygotuj nieprawidłowy event (nie jest typu Event)
        invalid_event = {"not": "an_event"}

        mock_server_with_devices.virtual_devices[
            "device1"
        ].finished_events.return_value = [invalid_event]

        with (
            patch("avena_commons.io.io_event_listener.MeasureTime") as mock_measure,
            patch("avena_commons.io.io_event_listener.error") as mock_error,
        ):
            mock_measure.return_value.__enter__ = Mock(return_value=mock_measure)
            mock_measure.return_value.__exit__ = Mock(return_value=None)

            await mock_server_with_devices._check_local_data()

            # Sprawdź czy błąd został zalogowany
            mock_error.assert_called()
            assert "Finished event is not of type Event" in mock_error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_check_local_data_event_not_found_in_processing(
        self, mock_server_with_devices
    ):
        """Test gdy event nie zostaje znaleziony w przetwarzaniu."""
        finished_event = Event(
            event_type="motor_finished", source="device", data={"status": "completed"}
        )

        mock_server_with_devices.virtual_devices[
            "device1"
        ].finished_events.return_value = [finished_event]
        # Mockuj _find_and_remove_processing_event aby zwrócić None (event nie znaleziony)
        mock_server_with_devices._find_and_remove_processing_event = Mock(
            return_value=None
        )
        # Upewnij się że debug jest włączony
        mock_server_with_devices._debug = True

        with (
            patch("avena_commons.io.io_event_listener.MeasureTime") as mock_measure,
            patch("avena_commons.io.io_event_listener.debug") as mock_debug,
        ):
            mock_measure.return_value.__enter__ = Mock(return_value=mock_measure)
            mock_measure.return_value.__exit__ = Mock(return_value=None)

            await mock_server_with_devices._check_local_data()

            # Sprawdź czy nie był wywoływany _reply
            mock_server_with_devices._reply.assert_not_called()

            # Sprawdź czy debug został wywołany z komunikatem "Event not found in processing"
            mock_debug.assert_called()
            all_debug_calls = [call[0][0] for call in mock_debug.call_args_list]

            # Sprawdź czy jeden z wywołań zawiera oczekiwany komunikat
            found_message = any(
                "Event not found in processing" in msg for msg in all_debug_calls
            )
            assert found_message, (
                f"Expected 'Event not found in processing' in debug calls: {all_debug_calls}"
            )


class TestExecuteBeforeShutdown:
    """Testy metody _execute_before_shutdown."""

    @pytest.fixture
    def mock_server_with_state(self):
        """Fixture dla mock'a IO_server ze stanem."""
        with patch("avena_commons.io.io_event_listener.EventListener.__init__"):
            server = IO_server.__new__(IO_server)
            server._message_logger = None
            server._debug = True

            server._state = {
                "io_server": {
                    "name": "test_server",
                    "port": 8080,
                    "configuration_file": "test.json",
                    "general_config_file": "general.json",
                },
                "virtual_devices": {
                    "device1": {"name": "device1", "type": "TestDevice"}
                },
            }

            server._build_state_dict = Mock(return_value={"updated": "state"})

            return server

    def test_execute_before_shutdown_successful(self, mock_server_with_state):
        """Test pomyślnego wykonania operacji przed zamknięciem."""
        with patch("avena_commons.io.io_event_listener.debug") as mock_debug:
            mock_server_with_state._execute_before_shutdown()

            # Sprawdź czy stan został zaktualizowany
            mock_server_with_state._build_state_dict.assert_called_once()

            # Sprawdź czy debug został wywołany
            mock_debug.assert_called_once()
            assert "State updated before shutdown" in mock_debug.call_args[0][0]

    def test_execute_before_shutdown_no_state(self, mock_server_with_state):
        """Test wykonania operacji przed zamknięciem bez stanu."""
        del mock_server_with_state._state

        # Nie powinno rzucać wyjątku
        mock_server_with_state._execute_before_shutdown()

    def test_execute_before_shutdown_exception(self, mock_server_with_state):
        """Test obsługi wyjątku podczas zamknięcia."""
        mock_server_with_state._build_state_dict.side_effect = Exception(
            "Shutdown exception"
        )

        with patch("avena_commons.io.io_event_listener.error") as mock_error:
            mock_server_with_state._execute_before_shutdown()

            # Sprawdź czy błąd został zalogowany
            mock_error.assert_called_once()
            assert "Error during shutdown preparation" in mock_error.call_args[0][0]


class TestLoadDeviceConfiguration:
    """Testy metody _load_device_configuration."""

    @pytest.fixture
    def mock_server(self):
        """Fixture dla mock'a IO_server."""
        with patch("avena_commons.io.io_event_listener.EventListener.__init__"):
            server = IO_server.__new__(IO_server)
            server._message_logger = None
            server._debug = True

            # Inicjalizuj atrybuty wymagane przez metody
            server.buses = {}
            server.physical_devices = {}
            server.virtual_devices = {}

            return server

    @pytest.fixture
    def complete_config(self):
        """Fixture z pełną konfiguracją."""
        return {
            "bus": {
                "modbus_1": {
                    "class": "ModbusRTU",
                    "configuration": {"port": "/dev/ttyUSB0", "baudrate": 9600},
                },
                "modbus_2": {
                    "class": "ModbusTCP",
                    "configuration": {"host": "192.168.1.100", "port": 502},
                },
            },
            "device": {
                "motor1": {
                    "class": "MotorDriver",
                    "configuration": {"address": 1, "max_speed": 1000},
                    "bus": "modbus_1",
                },
                "sensor1": {
                    "class": "TemperatureSensor",
                    "configuration": {"address": 2, "calibration": 1.05},
                    "bus": "modbus_1",
                },
            },
            "virtual_device": {
                "feeder1": {
                    "class": "Feeder",
                    "methods": {
                        "start": {"device": "motor1", "method": "start_motor"},
                        "stop": {"device": "motor1", "method": "stop_motor"},
                    },
                },
                "controller1": {
                    "class": "Controller",
                    "methods": {
                        "read_temperature": {
                            "device": "sensor1",
                            "method": "read_value",
                        }
                    },
                },
            },
        }

    def test_load_device_configuration_successful(self, mock_server, complete_config):
        """Test pomyślnego ładowania konfiguracji urządzeń."""
        with (
            patch.object(mock_server, "_load_and_merge_configs") as mock_load_merge,
            patch.object(mock_server, "_init_class_from_config") as mock_init_class,
        ):
            mock_load_merge.return_value = complete_config

            # Mock'uj inicjalizację klas
            mock_bus = Mock()
            mock_bus.configure = Mock()
            mock_device = Mock()
            mock_device.check_device_connection = Mock()
            mock_virtual_device = Mock()

            def mock_init_side_effect(
                device_name, class_name, folder_name, config, parent=None
            ):
                if folder_name == "bus":
                    return mock_bus
                elif folder_name == "device":
                    return mock_device
                elif folder_name == "virtual_device":
                    return mock_virtual_device
                return None

            mock_init_class.side_effect = mock_init_side_effect

            mock_server._load_device_configuration("test.json", "general.json")

            # Sprawdź czy kontenersy zostały utworzone
            assert hasattr(mock_server, "buses")
            assert hasattr(mock_server, "physical_devices")
            assert hasattr(mock_server, "virtual_devices")

            # Sprawdź czy urządzenia zostały dodane
            assert len(mock_server.buses) == 2
            assert len(mock_server.physical_devices) == 2
            assert len(mock_server.virtual_devices) == 2

            # Sprawdź czy metody konfiguracji zostały wywołane
            mock_bus.configure.assert_called()
            mock_device.check_device_connection.assert_called()

    def test_load_device_configuration_missing_class(
        self, mock_server, complete_config
    ):
        """Test ładowania konfiguracji z brakującą klasą."""
        # Usuń klasę z konfiguracji urządzenia wirtualnego, nie z bus'a
        del complete_config["virtual_device"]["feeder1"]["class"]

        with (
            patch.object(mock_server, "_load_and_merge_configs") as mock_load_merge,
            patch.object(mock_server, "_init_class_from_config") as mock_init_class,
            patch("avena_commons.io.io_event_listener.warning") as mock_warning,
        ):
            mock_load_merge.return_value = complete_config

            # Mock'uj inicjalizację wszystkich urządzeń
            mock_bus = Mock()
            mock_bus.configure = Mock()
            mock_device = Mock()
            mock_device.check_device_connection = Mock()
            mock_virtual_device = Mock()

            def mock_init_side_effect(
                device_name, class_name, folder_name, config, parent=None
            ):
                if folder_name == "bus":
                    return mock_bus
                elif folder_name == "device":
                    return mock_device
                elif folder_name == "virtual_device":
                    return mock_virtual_device
                return Mock()  # Zwróć mock zamiast None

            mock_init_class.side_effect = mock_init_side_effect

            mock_server._load_device_configuration("test.json", "general.json")

            # Sprawdź czy ostrzeżenie zostało zalogowane dla virtual device
            mock_warning.assert_called()
            assert (
                "Virtual device feeder1 missing class definition"
                in mock_warning.call_args[0][0]
            )

    def test_load_device_configuration_init_failure(self, mock_server, complete_config):
        """Test obsługi błędu inicjalizacji urządzenia."""
        with (
            patch.object(mock_server, "_load_and_merge_configs") as mock_load_merge,
            patch.object(mock_server, "_init_class_from_config") as mock_init_class,
        ):
            mock_load_merge.return_value = complete_config
            mock_init_class.return_value = None  # Symuluj błąd inicjalizacji

            # Powinno rzucać RuntimeError
            with pytest.raises(RuntimeError):
                mock_server._load_device_configuration("test.json", "general.json")

    def test_load_device_configuration_file_not_found(self, mock_server):
        """Test obsługi błędu braku pliku konfiguracji."""
        with patch.object(mock_server, "_load_and_merge_configs") as mock_load_merge:
            mock_load_merge.side_effect = FileNotFoundError("Config file not found")

            with pytest.raises(FileNotFoundError):
                mock_server._load_device_configuration(
                    "nonexistent.json", "general.json"
                )

    def test_load_device_configuration_invalid_json(self, mock_server):
        """Test obsługi błędu nieprawidłowego JSON."""
        with patch.object(mock_server, "_load_and_merge_configs") as mock_load_merge:
            mock_load_merge.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)

            with pytest.raises(ValueError):
                mock_server._load_device_configuration("invalid.json", "general.json")

    def test_load_device_configuration_bus_configure_exception(
        self, mock_server, complete_config
    ):
        """Test obsługi wyjątku podczas konfiguracji magistrali."""
        with (
            patch.object(mock_server, "_load_and_merge_configs") as mock_load_merge,
            patch.object(mock_server, "_init_class_from_config") as mock_init_class,
            patch("avena_commons.io.io_event_listener.error") as mock_error,
        ):
            mock_load_merge.return_value = complete_config

            mock_bus = Mock()
            mock_bus.configure = Mock(side_effect=Exception("Configure error"))
            mock_device = Mock()
            mock_device.check_device_connection = Mock()

            def mock_init_side_effect(
                device_name, class_name, folder_name, config, parent=None
            ):
                if folder_name == "bus":
                    return mock_bus
                elif folder_name == "device":
                    return mock_device
                return Mock()

            mock_init_class.side_effect = mock_init_side_effect

            with pytest.raises(Exception):
                mock_server._load_device_configuration("test.json", "general.json")

            # Sprawdź czy błąd został zalogowany
            mock_error.assert_called()

    def test_load_device_configuration_device_check_connection_exception(
        self, mock_server, complete_config
    ):
        """Test obsługi wyjątku podczas sprawdzania połączenia urządzenia."""
        with (
            patch.object(mock_server, "_load_and_merge_configs") as mock_load_merge,
            patch.object(mock_server, "_init_class_from_config") as mock_init_class,
            patch("avena_commons.io.io_event_listener.error") as mock_error,
        ):
            mock_load_merge.return_value = complete_config

            mock_bus = Mock()
            mock_bus.configure = Mock()
            mock_device = Mock()
            mock_device.check_device_connection = Mock(
                side_effect=Exception("Connection error")
            )

            def mock_init_side_effect(
                device_name, class_name, folder_name, config, parent=None
            ):
                if folder_name == "bus":
                    return mock_bus
                elif folder_name == "device":
                    return mock_device
                return Mock()

            mock_init_class.side_effect = mock_init_side_effect

            mock_server._load_device_configuration("test.json", "general.json")

            # Sprawdź czy błąd został zalogowany
            mock_error.assert_called()
            assert "Error checking device connection" in mock_error.call_args[0][0]

    def test_load_device_configuration_virtual_device_missing_referenced_device(
        self, mock_server, complete_config
    ):
        """Test ładowania urządzenia wirtualnego z brakującym odwołaniem do urządzenia fizycznego."""
        # Zmień odwołanie na nieistniejące urządzenie
        complete_config["virtual_device"]["feeder1"]["methods"]["start"]["device"] = (
            "nonexistent_device"
        )

        with (
            patch.object(mock_server, "_load_and_merge_configs") as mock_load_merge,
            patch.object(mock_server, "_init_class_from_config") as mock_init_class,
            patch("avena_commons.io.io_event_listener.warning") as mock_warning,
        ):
            mock_load_merge.return_value = complete_config

            mock_bus = Mock()
            mock_bus.configure = Mock()
            mock_device = Mock()
            mock_device.check_device_connection = Mock()
            mock_virtual_device = Mock()

            def mock_init_side_effect(
                device_name, class_name, folder_name, config, parent=None
            ):
                if folder_name == "bus":
                    return mock_bus
                elif folder_name == "device":
                    return mock_device
                elif folder_name == "virtual_device":
                    return mock_virtual_device
                return None

            mock_init_class.side_effect = mock_init_side_effect

            mock_server._load_device_configuration("test.json", "general.json")

            # Sprawdź czy ostrzeżenie zostało zalogowane
            mock_warning.assert_called()
            assert "references non-existent device" in mock_warning.call_args[0][0]


class TestLoadAndMergeConfigs:
    """Testy metody _load_and_merge_configs."""

    @pytest.fixture
    def mock_server(self):
        """Fixture dla mock'a IO_server."""
        with (
            patch.object(IO_server, "_load_device_configuration"),
            patch.object(IO_server, "_build_state_dict"),
            patch("avena_commons.io.io_event_listener.EventListener.__init__"),
        ):
            server = IO_server(
                name="test_server",
                port=8080,
                configuration_file="test.json",
                general_config_file="general.json",
                debug=True,
            )

            # Przywróć oryginalną metodę dla testów
            server._load_and_merge_configs = IO_server._load_and_merge_configs.__get__(
                server, IO_server
            )
            server._deep_merge = IO_server._deep_merge.__get__(server, IO_server)

            return server

    @pytest.fixture
    def general_config(self):
        """Fixture z konfiguracją ogólną."""
        return {
            "bus": {
                "modbus_1": {
                    "class": "ModbusRTU",
                    "configuration": {"baudrate": 9600, "timeout": 1.0},
                }
            },
            "device": {
                "motor1": {
                    "class": "MotorDriver",
                    "configuration": {"max_speed": 1000, "acceleration": 100},
                }
            },
        }

    @pytest.fixture
    def local_config(self):
        """Fixture z konfiguracją lokalną."""
        return {
            "bus": {
                "modbus_1": {
                    "configuration": {
                        "port": "/dev/ttyUSB0",
                        "baudrate": 19200,  # Override
                    }
                }
            },
            "device": {
                "motor1": {
                    "configuration": {
                        "address": 1,
                        "max_speed": 2000,  # Override
                    }
                }
            },
        }

    def test_load_and_merge_configs_both_files(
        self, mock_server, general_config, local_config
    ):
        """Test ładowania i łączenia obu plików konfiguracji."""
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("json.load") as mock_json_load,
        ):
            # Skonfiguruj mock'a do zwrócenia różnych konfiguracji
            mock_json_load.side_effect = [general_config, local_config]

            # Zresetuj licznik wywołań przed testem
            mock_file.reset_mock()

            result = mock_server._load_and_merge_configs("general.json", "local.json")

            # Sprawdź czy pliki zostały otwarte
            assert mock_file.call_count == 2

            # Sprawdź czy wartości zostały prawidłowo połączone
            assert (
                result["bus"]["modbus_1"]["configuration"]["baudrate"] == 19200
            )  # Override
            assert (
                result["bus"]["modbus_1"]["configuration"]["port"] == "/dev/ttyUSB0"
            )  # New
            assert (
                result["bus"]["modbus_1"]["configuration"]["timeout"] == 1.0
            )  # Original

            assert (
                result["device"]["motor1"]["configuration"]["max_speed"] == 2000
            )  # Override
            assert result["device"]["motor1"]["configuration"]["address"] == 1  # New
            assert (
                result["device"]["motor1"]["configuration"]["acceleration"] == 100
            )  # Original

    def test_load_and_merge_configs_only_local(self, mock_server, local_config):
        """Test ładowania tylko lokalnego pliku konfiguracji."""
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("json.load") as mock_json_load,
        ):
            mock_json_load.return_value = local_config

            # Zresetuj licznik wywołań przed testem
            mock_file.reset_mock()

            result = mock_server._load_and_merge_configs(None, "local.json")

            # Sprawdź czy tylko lokalny plik został otwarty
            assert mock_file.call_count == 1
            assert result == local_config

    def test_load_and_merge_configs_only_general(self, mock_server, general_config):
        """Test ładowania tylko ogólnego pliku konfiguracji."""
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("json.load") as mock_json_load,
        ):
            mock_json_load.return_value = general_config

            # Zresetuj licznik wywołań przed testem
            mock_file.reset_mock()

            result = mock_server._load_and_merge_configs("general.json", None)

            # Sprawdź czy tylko ogólny plik został otwarty
            assert mock_file.call_count == 1
            assert result == general_config

    def test_load_and_merge_configs_no_files(self, mock_server):
        """Test gdy nie ma żadnych plików konfiguracji."""
        result = mock_server._load_and_merge_configs(None, None)
        assert result == {}

    def test_load_and_merge_configs_general_file_not_found(
        self, mock_server, local_config
    ):
        """Test gdy plik ogólny nie istnieje."""
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("json.load") as mock_json_load,
            patch("avena_commons.io.io_event_listener.warning") as mock_warning,
        ):
            # Pierwsza próba otwarcia rzuca FileNotFoundError, druga się udaje
            mock_file.side_effect = [
                FileNotFoundError("General file not found"),
                mock_open().return_value,
            ]
            mock_json_load.return_value = local_config

            result = mock_server._load_and_merge_configs("general.json", "local.json")

            # Sprawdź czy ostrzeżenie zostało zalogowane
            mock_warning.assert_called()
            assert (
                "General configuration file not found" in mock_warning.call_args[0][0]
            )
            assert result == local_config

    def test_load_and_merge_configs_local_file_not_found(
        self, mock_server, general_config
    ):
        """Test gdy plik lokalny nie istnieje."""
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("json.load") as mock_json_load,
            patch("avena_commons.io.io_event_listener.warning") as mock_warning,
        ):
            # Pierwsza próba otwarcia się udaje, druga rzuca FileNotFoundError
            mock_file.side_effect = [
                mock_open().return_value,
                FileNotFoundError("Local file not found"),
            ]
            mock_json_load.return_value = general_config

            result = mock_server._load_and_merge_configs("general.json", "local.json")

            # Sprawdź czy ostrzeżenie zostało zalogowane
            mock_warning.assert_called()
            assert "Local configuration file not found" in mock_warning.call_args[0][0]
            assert result == general_config

    def test_load_and_merge_configs_invalid_json_general(self, mock_server):
        """Test obsługi nieprawidłowego JSON w pliku ogólnym."""
        with patch("builtins.open", mock_open()), patch("json.load") as mock_json_load:
            mock_json_load.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)

            with pytest.raises(json.JSONDecodeError):
                mock_server._load_and_merge_configs("general.json", None)

    def test_load_and_merge_configs_invalid_json_local(
        self, mock_server, general_config
    ):
        """Test obsługi nieprawidłowego JSON w pliku lokalnym."""
        with patch("builtins.open", mock_open()), patch("json.load") as mock_json_load:
            # Pierwszy load się udaje, drugi rzuca błąd
            mock_json_load.side_effect = [
                general_config,
                json.JSONDecodeError("Invalid JSON", "", 0),
            ]

            with pytest.raises(json.JSONDecodeError):
                mock_server._load_and_merge_configs("general.json", "local.json")


class TestDeepMerge:
    """Testy metody _deep_merge."""

    @pytest.fixture
    def mock_server(self):
        """Fixture dla mock'a IO_server."""
        with (
            patch.object(IO_server, "_load_device_configuration"),
            patch.object(IO_server, "_build_state_dict"),
            patch("avena_commons.io.io_event_listener.EventListener.__init__"),
        ):
            server = IO_server(
                name="test_server",
                port=8080,
                configuration_file="test.json",
                general_config_file="general.json",
                debug=True,
            )

            # Przywróć oryginalną metodę dla testów
            server._deep_merge = IO_server._deep_merge.__get__(server, IO_server)

            return server

    def test_deep_merge_simple_override(self, mock_server):
        """Test prostego nadpisania wartości."""
        base = {"key1": "value1", "key2": "value2"}
        override = {"key2": "new_value2", "key3": "value3"}

        result = mock_server._deep_merge(base, override)

        expected = {"key1": "value1", "key2": "new_value2", "key3": "value3"}
        assert result == expected

    def test_deep_merge_nested_dicts(self, mock_server):
        """Test głębokiego łączenia zagnieżdżonych słowników."""
        base = {
            "section1": {"key1": "value1", "key2": "value2"},
            "section2": {"key3": "value3"},
        }

        override = {
            "section1": {"key2": "new_value2", "key4": "value4"},
            "section3": {"key5": "value5"},
        }

        result = mock_server._deep_merge(base, override)

        expected = {
            "section1": {"key1": "value1", "key2": "new_value2", "key4": "value4"},
            "section2": {"key3": "value3"},
            "section3": {"key5": "value5"},
        }

        assert result == expected

    def test_deep_merge_mixed_types(self, mock_server):
        """Test łączenia różnych typów danych."""
        base = {
            "dict_key": {"nested": "value"},
            "list_key": [1, 2, 3],
            "str_key": "string",
        }

        override = {
            "dict_key": {"new_nested": "new_value"},
            "list_key": [4, 5, 6],  # Będzie nadpisane
            "str_key": "new_string",
        }

        result = mock_server._deep_merge(base, override)

        expected = {
            "dict_key": {"nested": "value", "new_nested": "new_value"},
            "list_key": [4, 5, 6],
            "str_key": "new_string",
        }

        assert result == expected

    def test_deep_merge_empty_dicts(self, mock_server):
        """Test łączenia pustych słowników."""
        base = {}
        override = {"key": "value"}

        result = mock_server._deep_merge(base, override)
        assert result == {"key": "value"}

        result = mock_server._deep_merge({"key": "value"}, {})
        assert result == {"key": "value"}

    def test_deep_merge_deeply_nested(self, mock_server):
        """Test głęboko zagnieżdżonych struktur."""
        base = {"level1": {"level2": {"level3": {"key": "original"}}}}

        override = {
            "level1": {
                "level2": {"level3": {"key": "overridden", "new_key": "new_value"}}
            }
        }

        result = mock_server._deep_merge(base, override)

        expected = {
            "level1": {
                "level2": {"level3": {"key": "overridden", "new_key": "new_value"}}
            }
        }

        assert result == expected


class TestInitClassFromConfig:
    """Testy metody _init_class_from_config."""

    @pytest.fixture
    def mock_server(self):
        """Fixture dla mock'a IO_server."""
        with (
            patch.object(IO_server, "_load_device_configuration"),
            patch.object(IO_server, "_build_state_dict"),
            patch("avena_commons.io.io_event_listener.EventListener.__init__"),
        ):
            server = IO_server(
                name="test_server",
                port=8080,
                configuration_file="test.json",
                general_config_file="general.json",
                debug=True,
            )

            # Przywróć oryginalną metodę dla testów
            server._init_class_from_config = IO_server._init_class_from_config.__get__(
                server, IO_server
            )

            return server

    def test_init_class_from_config_simple_class(self, mock_server):
        """Test inicjalizacji prostej klasy."""
        mock_class = Mock()
        mock_instance = Mock()
        mock_class.return_value = mock_instance

        config = {
            "class": "TestClass",
            "configuration": {"param1": "value1", "param2": "value2"},
        }

        with patch("importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_module.TestClass = mock_class
            mock_import.return_value = mock_module

            result = mock_server._init_class_from_config(
                device_name="test_device",
                class_name="TestClass",
                folder_name="device",
                config=config,
            )

            assert result == mock_instance
            mock_class.assert_called_once_with(
                message_logger=mock_server._message_logger,
                device_name="test_device",
                param1="value1",
                param2="value2",
            )

    def test_init_class_from_config_with_path(self, mock_server):
        """Test inicjalizacji klasy z ścieżką."""
        mock_class = Mock()
        mock_instance = Mock()
        mock_class.return_value = mock_instance

        config = {"class": "subfolder/TestClass", "configuration": {"param1": "value1"}}

        with patch("importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_module.TestClass = mock_class
            mock_import.return_value = mock_module

            result = mock_server._init_class_from_config(
                device_name="test_device",
                class_name="subfolder/TestClass",
                folder_name="device",
                config=config,
            )

            assert result == mock_instance
            # Sprawdź czy próbowano zaimportować z prawidłową ścieżką
            mock_import.assert_called()

    def test_init_class_from_config_virtual_device(self, mock_server):
        """Test inicjalizacji urządzenia wirtualnego."""
        mock_class = Mock()
        mock_instance = Mock()
        mock_class.return_value = mock_instance

        config = {
            "class": "VirtualDevice",
            "configuration": {"param1": "value1"},
            "devices": {"device1": Mock()},
            "methods": {"method1": {"device": "device1"}},
        }

        with patch("importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_module.VirtualDevice = mock_class
            mock_import.return_value = mock_module

            result = mock_server._init_class_from_config(
                device_name="test_virtual",
                class_name="VirtualDevice",
                folder_name="virtual_device",
                config=config,
            )

            assert result == mock_instance
            # Sprawdź czy parametry dla urządzenia wirtualnego zostały przekazane
            call_args = mock_class.call_args[1]
            assert "devices" in call_args
            assert "methods" in call_args
            assert call_args["device_name"] == "test_virtual"

    def test_init_class_from_config_with_parent_bus(self, mock_server):
        """Test inicjalizacji urządzenia z magistralą nadrzędną."""
        mock_class = Mock()
        mock_instance = Mock()
        mock_class.return_value = mock_instance
        mock_parent_bus = Mock()

        config = {"class": "PhysicalDevice", "configuration": {"address": 1}}

        with patch("importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_module.PhysicalDevice = mock_class
            mock_import.return_value = mock_module

            result = mock_server._init_class_from_config(
                device_name="test_device",
                class_name="PhysicalDevice",
                folder_name="device",
                config=config,
                parent=mock_parent_bus,
            )

            assert result == mock_instance
            # Sprawdź czy magistrala została przekazana
            call_args = mock_class.call_args[1]
            assert call_args["bus"] == mock_parent_bus

    def test_init_class_from_config_import_error(self, mock_server):
        """Test obsługi błędu importu."""
        config = {"class": "NonExistentClass", "configuration": {}}

        with (
            patch("importlib.import_module") as mock_import,
            patch("avena_commons.io.io_event_listener.error") as mock_error,
        ):
            mock_import.side_effect = ImportError("Module not found")

            result = mock_server._init_class_from_config(
                device_name="test_device",
                class_name="NonExistentClass",
                folder_name="device",
                config=config,
            )

            assert result is None
            mock_error.assert_called()

    def test_init_class_from_config_attribute_error(self, mock_server):
        """Test obsługi błędu braku atrybutu."""
        config = {"class": "TestClass", "configuration": {}}

        with (
            patch("importlib.import_module") as mock_import,
            patch("avena_commons.io.io_event_listener.error") as mock_error,
        ):
            mock_module = Mock()
            del mock_module.TestClass  # Brak atrybutu
            mock_import.return_value = mock_module

            result = mock_server._init_class_from_config(
                device_name="test_device",
                class_name="TestClass",
                folder_name="device",
                config=config,
            )

            assert result is None
            mock_error.assert_called()

    def test_init_class_from_config_constructor_exception(self, mock_server):
        """Test obsługi wyjątku w konstruktorze."""
        mock_class = Mock()
        mock_class.side_effect = Exception("Constructor error")

        config = {"class": "TestClass", "configuration": {}}

        with (
            patch("importlib.import_module") as mock_import,
            patch("avena_commons.io.io_event_listener.error") as mock_error,
        ):
            mock_module = Mock()
            mock_module.TestClass = mock_class
            mock_import.return_value = mock_module

            result = mock_server._init_class_from_config(
                device_name="test_device",
                class_name="TestClass",
                folder_name="device",
                config=config,
            )

            assert result is None
            mock_error.assert_called()

    def test_init_class_from_config_set_additional_attributes(self, mock_server):
        """Test ustawiania dodatkowych atrybutów."""
        mock_class = Mock()
        mock_instance = Mock()
        mock_class.return_value = mock_instance

        config = {
            "class": "TestClass",
            "configuration": {"param1": "value1"},
            "additional_attr": "additional_value",
        }

        with (
            patch("importlib.import_module") as mock_import,
            patch("avena_commons.io.io_event_listener.debug") as mock_debug,
        ):
            mock_module = Mock()
            mock_module.TestClass = mock_class
            mock_import.return_value = mock_module

            result = mock_server._init_class_from_config(
                device_name="test_device",
                class_name="TestClass",
                folder_name="device",
                config=config,
            )

            assert result == mock_instance
            # Sprawdź czy dodatkowy atrybut został ustawiony
            assert hasattr(mock_instance, "additional_attr")


class TestBuildStateDict:
    """Testy metody _build_state_dict."""

    @pytest.fixture
    def mock_server_with_full_setup(self):
        """Fixture dla mock'a IO_server z pełnym setupem."""
        with patch("avena_commons.io.io_event_listener.EventListener.__init__"):
            server = IO_server.__new__(IO_server)
            server._message_logger = None
            server._debug = True
            server.check_local_data_frequency = 50

            # Dodaj mock urządzenia
            mock_virtual_device = Mock()
            mock_virtual_device.to_dict = Mock(
                return_value={"name": "vdev1", "state": "active"}
            )

            mock_bus = Mock()
            mock_bus.to_dict = Mock(return_value={"name": "bus1", "connected": True})

            mock_physical_device = Mock()
            mock_physical_device.to_dict = Mock(
                return_value={"name": "pdev1", "status": "running"}
            )

            server.virtual_devices = {"vdev1": mock_virtual_device}
            server.buses = {"bus1": mock_bus}
            server.physical_devices = {"pdev1": mock_physical_device}

            return server

    def test_build_state_dict_successful(self, mock_server_with_full_setup):
        """Test pomyślnego budowania słownika stanu."""
        result = mock_server_with_full_setup._build_state_dict(
            name="test_server",
            port=8080,
            configuration_file="test.json",
            general_config_file="general.json",
        )

        # Sprawdź strukturę podstawową
        assert "io_server" in result
        assert "virtual_devices" in result
        assert "buses" in result
        assert "physical_devices" in result

        # Sprawdź dane serwera IO
        io_server = result["io_server"]
        assert io_server["name"] == "test_server"
        assert io_server["port"] == 8080
        assert io_server["configuration_file"] == "test.json"
        assert io_server["general_config_file"] == "general.json"
        assert io_server["debug"] is True

        # Sprawdź urządzenia wirtualne
        assert "vdev1" in result["virtual_devices"]
        assert result["virtual_devices"]["vdev1"]["name"] == "vdev1"
        assert result["virtual_devices"]["vdev1"]["state"] == "active"

        # Sprawdź magistrale
        assert "bus1" in result["buses"]
        assert result["buses"]["bus1"]["name"] == "bus1"
        assert result["buses"]["bus1"]["connected"] is True

        # Sprawdź urządzenia fizyczne
        assert "pdev1" in result["physical_devices"]
        assert result["physical_devices"]["pdev1"]["name"] == "pdev1"
        assert result["physical_devices"]["pdev1"]["status"] == "running"

    def test_build_state_dict_no_to_dict_method(self, mock_server_with_full_setup):
        """Test budowania stanu gdy urządzenia nie mają metody to_dict."""
        # Usuń metody to_dict
        del mock_server_with_full_setup.virtual_devices["vdev1"].to_dict
        del mock_server_with_full_setup.buses["bus1"].to_dict
        del mock_server_with_full_setup.physical_devices["pdev1"].to_dict

        result = mock_server_with_full_setup._build_state_dict(
            name="test_server",
            port=8080,
            configuration_file="test.json",
            general_config_file="general.json",
        )

        # Sprawdź czy zostały utworzone fallback'i
        assert result["virtual_devices"]["vdev1"]["no_to_dict_method"] is True
        assert result["buses"]["bus1"]["no_to_dict_method"] is True
        assert result["physical_devices"]["pdev1"]["no_to_dict_method"] is True

    def test_build_state_dict_to_dict_exception(self, mock_server_with_full_setup):
        """Test obsługi wyjątku w metodzie to_dict."""
        # Skonfiguruj mock'a do rzucania wyjątku
        mock_server_with_full_setup.virtual_devices[
            "vdev1"
        ].to_dict.side_effect = Exception("to_dict error")

        with patch("avena_commons.io.io_event_listener.error") as mock_error:
            result = mock_server_with_full_setup._build_state_dict(
                name="test_server",
                port=8080,
                configuration_file="test.json",
                general_config_file="general.json",
            )

            # Sprawdź czy błąd został zalogowany
            mock_error.assert_called()
            assert (
                "Error building state for virtual device" in mock_error.call_args[0][0]
            )

            # Sprawdź czy informacja o błędzie została zapisana
            assert "error" in result["virtual_devices"]["vdev1"]

    def test_build_state_dict_no_devices(self, mock_server_with_full_setup):
        """Test budowania stanu gdy nie ma urządzeń."""
        # Usuń wszystkie urządzenia
        del mock_server_with_full_setup.virtual_devices
        del mock_server_with_full_setup.buses
        del mock_server_with_full_setup.physical_devices

        result = mock_server_with_full_setup._build_state_dict(
            name="test_server",
            port=8080,
            configuration_file="test.json",
            general_config_file="general.json",
        )

        # Sprawdź czy podstawowa struktura została utworzona
        assert "io_server" in result
        assert "virtual_devices" in result
        assert "buses" in result
        assert "physical_devices" in result

        # Sprawdź czy kontenery są puste
        assert len(result["virtual_devices"]) == 0
        assert len(result["buses"]) == 0
        assert len(result["physical_devices"]) == 0

    def test_build_state_dict_global_exception(self, mock_server_with_full_setup):
        """Test obsługi globalnego wyjątku."""
        # Mockuj właściwość używaną w metodzie _build_state_dict aby rzucała wyjątek
        type(mock_server_with_full_setup).check_local_data_frequency = PropertyMock(
            side_effect=Exception("Simulated error")
        )

        with patch("avena_commons.io.io_event_listener.error") as mock_error:
            result = mock_server_with_full_setup._build_state_dict(
                name="test_server",
                port=8080,
                configuration_file="test.json",
                general_config_file="general.json",
            )

            # Sprawdź czy błąd został zalogowany
            mock_error.assert_called()
            assert "Error building state dict" in mock_error.call_args[0][0]

            # Sprawdź czy minimalny stan został zwrócony
            assert "io_server" in result
            assert "error" in result["io_server"]


class TestUpdateState:
    """Testy metody update_state."""

    @pytest.fixture
    def mock_server_with_state(self):
        """Fixture dla mock'a IO_server ze stanem."""
        with patch("avena_commons.io.io_event_listener.EventListener.__init__"):
            server = IO_server.__new__(IO_server)
            server._message_logger = None
            server._debug = True

            server._build_state_dict = Mock(return_value={"updated": "state"})

            # Dodaj istniejący stan
            server._state = {
                "io_server": {
                    "name": "test_server",
                    "port": 8080,
                    "configuration_file": "test.json",
                    "general_config_file": "general.json",
                },
                "virtual_devices": {"device1": {"name": "device1"}},
            }

            return server

    def test_update_state_successful(self, mock_server_with_state):
        """Test pomyślnej aktualizacji stanu."""
        with patch("avena_commons.io.io_event_listener.debug") as mock_debug:
            result = mock_server_with_state.update_state()

            # Sprawdź czy _build_state_dict został wywołany
            mock_server_with_state._build_state_dict.assert_called_once()

            # Sprawdź czy stan został zaktualizowany
            assert result == {"updated": "state"}
            assert mock_server_with_state._state == {"updated": "state"}

            # Sprawdź czy debug został wywołany
            mock_debug.assert_called_once()
            assert "State updated manually" in mock_debug.call_args[0][0]

    def test_update_state_no_existing_state(self, mock_server_with_state):
        """Test aktualizacji stanu gdy nie ma istniejącego stanu."""
        # Usuń istniejący stan
        del mock_server_with_state._state

        result = mock_server_with_state.update_state()

        # Sprawdź czy _build_state_dict został wywołany z domyślnymi parametrami
        mock_server_with_state._build_state_dict.assert_called_once_with(
            name="unknown", port=0, configuration_file="", general_config_file=""
        )

        assert result == {"updated": "state"}

    def test_update_state_exception(self, mock_server_with_state):
        """Test obsługi wyjątku podczas aktualizacji stanu."""
        # Skonfiguruj mock'a do rzucania wyjątku
        mock_server_with_state._build_state_dict.side_effect = Exception("Update error")

        with patch("avena_commons.io.io_event_listener.error") as mock_error:
            result = mock_server_with_state.update_state()

            # Sprawdź czy błąd został zalogowany
            mock_error.assert_called_once()
            assert "Error updating state" in mock_error.call_args[0][0]

            # Sprawdź czy zwrócony został poprzedni stan
            assert "io_server" in result
            assert result["io_server"]["name"] == "test_server"

    def test_update_state_exception_no_existing_state(self, mock_server_with_state):
        """Test obsługi wyjątku gdy nie ma istniejącego stanu."""
        # Usuń istniejący stan
        del mock_server_with_state._state

        # Skonfiguruj mock'a do rzucania wyjątku
        mock_server_with_state._build_state_dict.side_effect = Exception("Update error")

        with patch("avena_commons.io.io_event_listener.error") as mock_error:
            result = mock_server_with_state.update_state()

            # Sprawdź czy błąd został zalogowany
            mock_error.assert_called_once()
            assert "Error updating state" in mock_error.call_args[0][0]

            # Sprawdź czy zwrócony został pusty słownik
            assert result == {}
