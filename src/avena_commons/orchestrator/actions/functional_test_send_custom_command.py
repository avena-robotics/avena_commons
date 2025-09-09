#!/usr/bin/env python3
"""
Test funkcjonalny dla SendCustomCommandAction.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from avena_commons.orchestrator.actions import ActionExecutor
from avena_commons.orchestrator.actions.base_action import ActionContext


async def test_send_custom_command():
    """Test podstawowej funkcjonalności send_custom_command."""
    print("🧪 Test funkcjonalny SendCustomCommandAction")
    
    # Tworzymy mock orchestratora
    mock_orchestrator = MagicMock()
    mock_orchestrator._configuration = {
        "clients": {
            "io": {
                "address": "127.0.0.1",
                "port": 8001,
                "group": "base_io"
            },
            "supervisor_1": {
                "address": "127.0.0.1", 
                "port": 8002,
                "group": "supervisors"
            },
            "supervisor_2": {
                "address": "127.0.0.1",
                "port": 8003, 
                "group": "supervisors"
            }
        }
    }
    
    # Mock metody _event
    mock_event = MagicMock()
    mock_orchestrator._event = AsyncMock(return_value=mock_event)
    
    # Kontekst wykonania
    context = ActionContext(
        orchestrator=mock_orchestrator,
        message_logger=None,
        trigger_data=None,
        scenario_name="test_scenario"
    )
    
    # ActionExecutor
    executor = ActionExecutor()
    
    # Test 1: Wysłanie do pojedynczego klienta
    print("\n📤 Test 1: Wysłanie do pojedynczego klienta")
    action_config = {
        "type": "send_custom_command",
        "client": "io",
        "command": "CUSTOM_CALIBRATE_SENSOR",
        "data": {
            "sensor_id": 42,
            "calibration_values": [1.0, 2.5, 3.7],
            "timeout": 30,
            "mode": "precision"
        },
        "description": "Test kalibracji sensora"
    }
    
    await executor.execute_action(action_config, context)
    print("✅ Test 1 zakończony pomyślnie")
    
    # Sprawdzamy czy _event została wywołana
    mock_orchestrator._event.assert_called()
    call_args = mock_orchestrator._event.call_args
    assert call_args.kwargs['destination'] == 'io'
    assert call_args.kwargs['event_type'] == 'CUSTOM_CALIBRATE_SENSOR'
    assert call_args.kwargs['data'] == action_config['data']
    print("✅ Parametry wywołania _event są poprawne")
    
    # Test 2: Wysłanie do grupy klientów
    print("\n📤 Test 2: Wysłanie do grupy klientów")
    mock_orchestrator._event.reset_mock()
    
    action_config = {
        "type": "send_custom_command", 
        "group": "supervisors",
        "command": "SET_POSITION",
        "data": {
            "x": 100.5,
            "y": 200.3,
            "z": 15.0,
            "speed": 0.8
        },
        "description": "Ustawienie pozycji dla wszystkich supervisorów"
    }
    
    await executor.execute_action(action_config, context)
    print("✅ Test 2 zakończony pomyślnie")
    
    # Sprawdzamy czy wywołano _event dla obu supervisorów
    assert mock_orchestrator._event.call_count == 2
    print("✅ Wywołano _event dla obu supervisorów w grupie")
    
    # Test 3: Wysłanie do wszystkich klientów
    print("\n📤 Test 3: Wysłanie do wszystkich klientów (@all)")
    mock_orchestrator._event.reset_mock()
    
    action_config = {
        "type": "send_custom_command",
        "target": "@all", 
        "command": "GLOBAL_STATUS_UPDATE",
        "data": {
            "status": "maintenance_mode",
            "timestamp": "2025-09-09T12:00:00Z",
            "message": "System entering maintenance"
        },
        "description": "Globalna aktualizacja statusu"
    }
    
    await executor.execute_action(action_config, context)
    print("✅ Test 3 zakończony pomyślnie")
    
    # Sprawdzamy czy wywołano _event dla wszystkich klientów
    assert mock_orchestrator._event.call_count == 3  # io, supervisor_1, supervisor_2
    print("✅ Wywołano _event dla wszystkich klientów")
    
    print("\n🎉 Wszystkie testy funkcjonalne zakończone pomyślnie!")
    print("🚀 SendCustomCommandAction działa poprawnie!")


if __name__ == "__main__":
    asyncio.run(test_send_custom_command())
