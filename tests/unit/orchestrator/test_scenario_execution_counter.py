"""
Testy jednostkowe dla systemu licznika wykonań scenariuszy.

Cel: Testowanie mechanizmu blokowania scenariuszy po przekroczeniu limitu wykonań
i resetowania liczników po ACK.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from avena_commons.orchestrator import Orchestrator
from avena_commons.orchestrator.models import ScenarioModel
from avena_commons.util.logger import MessageLogger


def create_mock_logger():
    """Tworzy mock MessageLogger."""
    return MagicMock(spec=MessageLogger)


def create_orchestrator(mock_logger=None):
    """Tworzy Orchestratora z podstawową konfiguracją."""
    if mock_logger is None:
        mock_logger = create_mock_logger()
    return Orchestrator(
        name="test_orch",
        port=5000,
        address="127.0.0.1",
        message_logger=mock_logger,
        debug=True
    )


def get_test_scenario_data():
    """Zwraca scenariusz testowy z limitem wykonań."""
    return {
        "name": "test_counter_scenario",
        "description": "Scenariusz testowy z limitem wykonań",
        "priority": 0,
        "cooldown": 1,
        "max_executions": 3,
        "trigger": {
            "type": "manual",
            "description": "Manualny trigger"
        },
        "actions": [
            {
                "type": "log_event",
                "level": "info",
                "message": "Test wykonania scenariusza"
            }
        ]
    }


def get_test_scenario_no_limit():
    """Zwraca scenariusz bez limitu wykonań."""
    return {
        "name": "test_no_limit_scenario",
        "description": "Scenariusz bez limitu wykonań",
        "priority": 0,
        "cooldown": 1,
        "max_executions": None,
        "trigger": {
            "type": "manual",
            "description": "Manualny trigger"
        },
        "actions": [
            {
                "type": "log_event",
                "level": "info",
                "message": "Test wykonania scenariusza bez limitu"
            }
        ]
    }


class TestScenarioExecutionCounter:
    """Testy systemu licznika wykonań scenariuszy."""
    
    def test_get_scenario_execution_count_initial(self):
        """Test początkowej wartości licznika wykonań."""
        orchestrator = create_orchestrator()
        count = orchestrator.get_scenario_execution_count("nonexistent_scenario")
        assert count == 0, f"Początkowy licznik powinien być 0, ale jest {count}"

    def test_increment_scenario_execution_count(self):
        """Test zwiększania licznika wykonań scenariusza."""
        orchestrator = create_orchestrator()
        scenario_name = "test_scenario"
        
        # Pierwsze zwiększenie
        count1 = orchestrator.increment_scenario_execution_count(scenario_name)
        assert count1 == 1, f"Pierwsze zwiększenie powinno dać 1, ale dało {count1}"
        assert orchestrator.get_scenario_execution_count(scenario_name) == 1
        
        # Drugie zwiększenie
        count2 = orchestrator.increment_scenario_execution_count(scenario_name)
        assert count2 == 2, f"Drugie zwiększenie powinno dać 2, ale dało {count2}"
        assert orchestrator.get_scenario_execution_count(scenario_name) == 2

    def test_reset_scenario_execution_count(self):
        """Test resetowania licznika wykonań scenariusza."""
        orchestrator = create_orchestrator()
        scenario_name = "test_scenario"
        
        # Zwiększ licznik
        orchestrator.increment_scenario_execution_count(scenario_name)
        orchestrator.increment_scenario_execution_count(scenario_name)
        assert orchestrator.get_scenario_execution_count(scenario_name) == 2
        
        # Resetuj licznik
        orchestrator.reset_scenario_execution_count(scenario_name)
        assert orchestrator.get_scenario_execution_count(scenario_name) == 0
        assert not orchestrator.is_scenario_blocked(scenario_name)

    def test_reset_all_scenario_execution_counters(self):
        """Test resetowania wszystkich liczników wykonań."""
        orchestrator = create_orchestrator()
        
        # Ustaw liczniki dla kilku scenariuszy
        orchestrator.increment_scenario_execution_count("scenario1")
        orchestrator.increment_scenario_execution_count("scenario2")
        orchestrator._blocked_scenarios["scenario1"] = True
        
        # Resetuj wszystkie
        orchestrator.reset_all_scenario_execution_counters()
        
        assert orchestrator.get_scenario_execution_count("scenario1") == 0
        assert orchestrator.get_scenario_execution_count("scenario2") == 0
        assert not orchestrator.is_scenario_blocked("scenario1")

    def test_is_scenario_blocked_initial(self):
        """Test początkowego statusu blokady scenariusza."""
        orchestrator = create_orchestrator()
        assert not orchestrator.is_scenario_blocked("test_scenario")

    def test_should_block_scenario_no_limit(self):
        """Test że scenariusze bez limitu nie są blokowane."""
        orchestrator = create_orchestrator()
        scenario_name = "test_scenario"
        
        # Zwiększ licznik dużo razy
        for _ in range(10):
            orchestrator.increment_scenario_execution_count(scenario_name)
        
        # Sprawdź czy nie blokuje bez limitu
        assert not orchestrator.should_block_scenario_due_to_limit(scenario_name, None)
        assert not orchestrator.should_block_scenario_due_to_limit(scenario_name, 0)
        assert not orchestrator.should_block_scenario_due_to_limit(scenario_name, -1)

    def test_should_block_scenario_with_limit(self):
        """Test blokowania scenariusza po przekroczeniu limitu."""
        orchestrator = create_orchestrator()
        scenario_name = "test_scenario"
        max_executions = 3
        
        # Wykonaj scenariusz poniżej limitu
        for _ in range(2):
            orchestrator.increment_scenario_execution_count(scenario_name)
        
        assert not orchestrator.should_block_scenario_due_to_limit(scenario_name, max_executions)
        assert not orchestrator.is_scenario_blocked(scenario_name)
        
        # Wykonaj scenariusz na granicy limitu
        orchestrator.increment_scenario_execution_count(scenario_name)  # 3 wykonania
        
        should_block = orchestrator.should_block_scenario_due_to_limit(scenario_name, max_executions)
        assert should_block, "Scenariusz powinien zostać zablokowany po przekroczeniu limitu"
        assert orchestrator.is_scenario_blocked(scenario_name), "Scenariusz powinien być oznaczony jako zablokowany"

    def test_get_scenarios_execution_status(self):
        """Test pobierania statusu wykonań scenariuszy."""
        orchestrator = create_orchestrator()
        test_scenario_data = get_test_scenario_data()
        test_scenario_no_limit = get_test_scenario_no_limit()
        
        # Załaduj scenariusze testowe
        orchestrator._scenarios["test_counter_scenario"] = test_scenario_data
        orchestrator._scenarios["test_no_limit_scenario"] = test_scenario_no_limit
        
        # Zwiększ licznik jednego scenariusza
        orchestrator.increment_scenario_execution_count("test_counter_scenario")
        orchestrator.increment_scenario_execution_count("test_counter_scenario")
        
        # Pobierz status
        status = orchestrator.get_scenarios_execution_status()
        
        assert "test_counter_scenario" in status
        assert "test_no_limit_scenario" in status
        
        counter_status = status["test_counter_scenario"]
        assert counter_status["max_executions"] == 3
        assert counter_status["current_executions"] == 2
        assert counter_status["is_blocked"] == False
        assert counter_status["can_execute"] == True
        
        no_limit_status = status["test_no_limit_scenario"]
        assert no_limit_status["max_executions"] is None
        assert no_limit_status["current_executions"] == 0
        assert no_limit_status["is_blocked"] == False
        assert no_limit_status["can_execute"] == True


class TestScenarioModelMaxExecutions:
    """Testy modelu scenariusza z polem max_executions."""
    
    def test_scenario_model_with_max_executions(self):
        """Test tworzenia modelu scenariusza z limitem wykonań."""
        scenario_data = {
            "name": "test_scenario",
            "description": "Test scenario",
            "max_executions": 5,
            "trigger": {
                "type": "manual"
            },
            "actions": [
                {
                    "type": "log_event",
                    "level": "info",
                    "message": "Test"
                }
            ]
        }
        
        model = ScenarioModel(**scenario_data)
        assert model.max_executions == 5

    def test_scenario_model_without_max_executions(self):
        """Test tworzenia modelu scenariusza bez limitu wykonań."""
        scenario_data = {
            "name": "test_scenario",
            "description": "Test scenario",
            "trigger": {
                "type": "manual"
            },
            "actions": [
                {
                    "type": "log_event",
                    "level": "info",
                    "message": "Test"
                }
            ]
        }
        
        model = ScenarioModel(**scenario_data)
        assert model.max_executions is None


async def test_should_execute_scenario_blocked():
    """Test że zablokowane scenariusze nie są wykonywane."""
    orchestrator = create_orchestrator()
    test_scenario_data = get_test_scenario_data()
    scenario_name = "test_counter_scenario"
    orchestrator._scenarios[scenario_name] = test_scenario_data
    
    # Przekrocz limit wykonań
    for _ in range(3):
        orchestrator.increment_scenario_execution_count(scenario_name)
    
    # Zablokuj scenariusz
    orchestrator.should_block_scenario_due_to_limit(scenario_name, 3)
    
    # Sprawdź czy scenariusz nie powinien być wykonany
    should_execute = await orchestrator._should_execute_scenario(test_scenario_data)
    assert not should_execute, "Zablokowany scenariusz nie powinien być wykonywany"


async def test_should_execute_scenario_not_blocked():
    """Test że niezablokowane scenariusze mogą być wykonane."""
    orchestrator = create_orchestrator()
    test_scenario_data = get_test_scenario_data()
    scenario_name = "test_counter_scenario"
    orchestrator._scenarios[scenario_name] = test_scenario_data
    
    # Zwiększ licznik poniżej limitu
    orchestrator.increment_scenario_execution_count(scenario_name)
    
    # Sprawdź czy scenariusz powinien być wykonany
    should_execute = await orchestrator._should_execute_scenario(test_scenario_data)
    assert should_execute, "Niezablokowany scenariusz powinien móc być wykonany"


async def test_execute_scenario_increments_counter():
    """Test że wykonanie scenariusza zwiększa licznik."""
    orchestrator = create_orchestrator()
    test_scenario_data = get_test_scenario_data()
    scenario_name = "test_counter_scenario"
    orchestrator._scenarios[scenario_name] = test_scenario_data
    
    # Mock action executor żeby nie wykonywać rzeczywistych akcji
    with patch.object(orchestrator._action_executor, 'execute_action', new_callable=AsyncMock):
        initial_count = orchestrator.get_scenario_execution_count(scenario_name)
        assert initial_count == 0
        
        # Wykonaj scenariusz
        result = await orchestrator.execute_scenario(scenario_name)
        
        assert result == True
        final_count = orchestrator.get_scenario_execution_count(scenario_name)
        assert final_count == 1, f"Licznik powinien wzrosnąć do 1, ale jest {final_count}"


async def test_on_ack_resets_counters():
    """Test że ACK resetuje wszystkie liczniki wykonań."""
    orchestrator = create_orchestrator()
    
    # Ustaw liczniki i blokady
    orchestrator.increment_scenario_execution_count("scenario1")
    orchestrator.increment_scenario_execution_count("scenario2")
    orchestrator._blocked_scenarios["scenario1"] = True
    
    # Wywołaj ACK
    await orchestrator.on_ack()
    
    # Sprawdź czy liczniki zostały zresetowane
    assert orchestrator.get_scenario_execution_count("scenario1") == 0
    assert orchestrator.get_scenario_execution_count("scenario2") == 0
    assert not orchestrator.is_scenario_blocked("scenario1")


def run_tests():
    """Uruchamia wszystkie testy."""
    print("🧪 Uruchamianie testów systemu licznika wykonań scenariuszy...")
    
    # Testy synchroniczne
    test_case = TestScenarioExecutionCounter()
    test_case.test_get_scenario_execution_count_initial()
    print("✅ test_get_scenario_execution_count_initial")
    
    test_case.test_increment_scenario_execution_count()
    print("✅ test_increment_scenario_execution_count")
    
    test_case.test_reset_scenario_execution_count()
    print("✅ test_reset_scenario_execution_count")
    
    test_case.test_reset_all_scenario_execution_counters()
    print("✅ test_reset_all_scenario_execution_counters")
    
    test_case.test_is_scenario_blocked_initial()
    print("✅ test_is_scenario_blocked_initial")
    
    test_case.test_should_block_scenario_no_limit()
    print("✅ test_should_block_scenario_no_limit")
    
    test_case.test_should_block_scenario_with_limit()
    print("✅ test_should_block_scenario_with_limit")
    
    test_case.test_get_scenarios_execution_status()
    print("✅ test_get_scenarios_execution_status")
    
    # Testy modelu
    model_test = TestScenarioModelMaxExecutions()
    model_test.test_scenario_model_with_max_executions()
    print("✅ test_scenario_model_with_max_executions")
    
    model_test.test_scenario_model_without_max_executions()
    print("✅ test_scenario_model_without_max_executions")
    
    # Testy asynchroniczne
    async def run_async_tests():
        await test_should_execute_scenario_blocked()
        print("✅ test_should_execute_scenario_blocked")
        
        await test_should_execute_scenario_not_blocked()
        print("✅ test_should_execute_scenario_not_blocked")
        
        await test_execute_scenario_increments_counter()
        print("✅ test_execute_scenario_increments_counter")
        
        await test_on_ack_resets_counters()
        print("✅ test_on_ack_resets_counters")
    
    # Uruchom testy asynchroniczne
    asyncio.run(run_async_tests())
    
    print("\n🎉 Wszystkie testy przeszły pomyślnie!")


if __name__ == "__main__":
    run_tests()
