"""
Test dla SendCustomCommandAction.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

from actions.base_action import ActionContext, ActionExecutionError
from actions.send_custom_command_action import SendCustomCommandAction


# Dodaj ścieżkę do sys.path aby umożliwić import
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from actions.base_action import ActionContext, ActionExecutionError
from actions.send_custom_command_action import SendCustomCommandAction


async def test_send_custom_command_basic():
    """Podstawowy test wysyłania polecenia niestandardowego."""

    # Przygotowanie
    action = SendCustomCommandAction()
    mock_orchestrator = MagicMock()
    mock_orchestrator._configuration = {
        "clients": {
            "test_client": {
                "address": "192.168.1.100",
                "port": 8001,
                "group": "test_group",
            }
        }
    }
    mock_orchestrator._event = AsyncMock()

    context = ActionContext(
        orchestrator=mock_orchestrator,
        message_logger=MagicMock(),
        trigger_data={"source": "test_trigger", "admin_email": "admin@test.com"},
        scenario_name="test_scenario",
    )

    action_config = {
        "client": "test_client",
        "command": "CUSTOM_CALIBRATE",
        "data": {"sensor_id": 42, "values": [1.0, 2.5, 3.7], "precision": "high"},
        "timeout": "20s",
    }

    # Wykonanie
    await action.execute(action_config, context)

    # Weryfikacja
    mock_orchestrator._event.assert_called_once_with(
        destination="test_client",
        destination_address="192.168.1.100",
        destination_port=8001,
        event_type="CUSTOM_CALIBRATE",
        data={"sensor_id": 42, "values": [1.0, 2.5, 3.7], "precision": "high"},
        to_be_processed=True,
        maximum_processing_time=20.0,
    )

    print("✅ test_send_custom_command_basic: PASSED")


async def test_template_variables_resolution():
    """Test rozwiązywania zmiennych szablonowych w danych."""

    # Przygotowanie
    action = SendCustomCommandAction()
    mock_orchestrator = MagicMock()
    mock_orchestrator._configuration = {
        "clients": {"test_client": {"address": "192.168.1.100", "port": 8001}}
    }
    mock_orchestrator._event = AsyncMock()

    context = ActionContext(
        orchestrator=mock_orchestrator,
        message_logger=MagicMock(),
        trigger_data={"source": "test_trigger", "admin_email": "admin@test.com"},
        scenario_name="test_scenario",
    )

    action_config = {
        "client": "test_client",
        "command": "NOTIFY_ADMIN",
        "data": {
            "source": "{{ trigger.source }}",
            "admin_email": "{{ trigger.admin_email }}",
            "message": "Alert from {{ trigger.source }}",
            "static_value": "unchanged",
        },
    }

    # Wykonanie
    await action.execute(action_config, context)

    # Weryfikacja
    call_args = mock_orchestrator._event.call_args
    data = call_args.kwargs["data"]

    assert data["source"] == "test_trigger"
    assert data["admin_email"] == "admin@test.com"
    assert data["message"] == "Alert from test_trigger"
    assert data["static_value"] == "unchanged"

    print("✅ test_template_variables_resolution: PASSED")


async def test_missing_command_error():
    """Test błędu gdy brak komendy."""

    # Przygotowanie
    action = SendCustomCommandAction()
    mock_orchestrator = MagicMock()
    mock_orchestrator._configuration = {"clients": {}}

    context = ActionContext(orchestrator=mock_orchestrator, message_logger=MagicMock())

    action_config = {
        "client": "test_client",
        "data": {"key": "value"},
        # Brak 'command'
    }

    # Wykonanie i weryfikacja
    try:
        await action.execute(action_config, context)
        assert False, "Powinien wystąpić ActionExecutionError"
    except ActionExecutionError as e:
        assert "Brak komendy do wysłania" in str(e)
        assert e.action_type == "send_custom_command"
        print("✅ test_missing_command_error: PASSED")


async def test_all_clients_selector():
    """Test selektora @all."""

    # Przygotowanie
    action = SendCustomCommandAction()
    mock_orchestrator = MagicMock()
    mock_orchestrator._configuration = {
        "clients": {
            "client_1": {"address": "192.168.1.100", "port": 8001},
            "client_2": {"address": "192.168.1.101", "port": 8002},
            "client_3": {"address": "192.168.1.102", "port": 8003},
        }
    }
    mock_orchestrator._event = AsyncMock()

    context = ActionContext(orchestrator=mock_orchestrator, message_logger=MagicMock())

    action_config = {
        "target": "@all",
        "command": "SYSTEM_STATUS",
        "data": {"check_type": "full"},
    }

    # Wykonanie
    await action.execute(action_config, context)

    # Weryfikacja - powinno być 3 wywołania dla 3 klientów
    assert mock_orchestrator._event.call_count == 3

    calls = mock_orchestrator._event.call_args_list
    destinations = [call.kwargs["destination"] for call in calls]
    assert set(destinations) == {"client_1", "client_2", "client_3"}

    print("✅ test_all_clients_selector: PASSED")


async def run_all_tests():
    """Uruchomienie wszystkich testów."""
    print("🧪 Uruchamianie testów SendCustomCommandAction...")

    try:
        await test_send_custom_command_basic()
        await test_template_variables_resolution()
        await test_missing_command_error()
        await test_all_clients_selector()

        print("\n🎉 Wszystkie testy zakończone pomyślnie!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(run_all_tests())
