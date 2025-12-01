"""
Testy jednostkowe dla klasy TaskTimeout.

Moduł zawiera kompleksowe testy funkcjonalności TaskTimeout, w tym:
- dodawanie zadań timeout
- anulowanie zadań
- obsługę timeoutów
- niestandardowe akcje on_timeout
- metadata zadań
"""

import time
from unittest.mock import Mock, patch

import pytest

from avena_commons.io.virtual_device.sensor_watchdog import SensorTimerTask
from avena_commons.util.task_timeout import TaskTimeout


class ConcreteTaskTimeout(TaskTimeout):
    """Konkretna implementacja TaskTimeout do testów."""

    def __init__(self, device_name: str = "TestDevice", **kwargs):
        self.device_name = device_name
        self._message_logger = kwargs.get("message_logger")
        super().__init__(**kwargs)
        self.timeout_callbacks = []
        self.error_logs = []

    def on_sensor_timeout(self, task: SensorTimerTask) -> None:
        """Niestandardowa akcja timeout dla testów."""
        self.timeout_callbacks.append({
            "task_id": task.id,
            "description": task.description,
            "metadata": task.metadata,
        })


class TestTaskTimeoutBasic:
    """Testy podstawowej funkcjonalności TaskTimeout."""

    def test_initialization(self):
        """Test inicjalizacji obiektu TaskTimeout."""
        task_timeout = ConcreteTaskTimeout(device_name="TestDevice")

        assert task_timeout.device_name == "TestDevice"
        assert task_timeout._message_logger is None
        assert hasattr(task_timeout, "_TaskTimeout__watchdog")

    def test_initialization_with_logger(self):
        """Test inicjalizacji z loggerem."""
        mock_logger = Mock()
        task_timeout = ConcreteTaskTimeout(
            device_name="TestDevice", message_logger=mock_logger
        )

        assert task_timeout._message_logger == mock_logger

    def test_add_sensor_timeout_basic(self):
        """Test podstawowego dodawania zadania timeout."""
        task_timeout = ConcreteTaskTimeout()
        condition_met = False

        def condition():
            return condition_met

        task_id = task_timeout.add_sensor_timeout(
            condition=condition, timeout_s=1.0, description="Test timeout task"
        )

        assert task_id is not None
        assert isinstance(task_id, str)

    def test_add_sensor_timeout_with_custom_id(self):
        """Test dodawania zadania z niestandardowym ID."""
        task_timeout = ConcreteTaskTimeout()

        custom_id = "my_custom_task_id"
        task_id = task_timeout.add_sensor_timeout(
            condition=lambda: False,
            timeout_s=1.0,
            description="Custom ID task",
            id=custom_id,
        )

        assert task_id == custom_id

    def test_add_sensor_timeout_with_metadata(self):
        """Test dodawania zadania z metadanymi."""
        task_timeout = ConcreteTaskTimeout()
        metadata = {"sensor_name": "temperature", "threshold": 25.5}

        task_id = task_timeout.add_sensor_timeout(
            condition=lambda: False,
            timeout_s=1.0,
            description="Task with metadata",
            metadata=metadata,
        )

        assert task_id is not None


class TestTaskTimeoutConditions:
    """Testy warunków i ich spełniania."""

    def test_condition_met_before_timeout(self):
        """Test spełnienia warunku przed timeoutem."""
        task_timeout = ConcreteTaskTimeout()
        condition_met = False

        def condition():
            return condition_met

        task_id = task_timeout.add_sensor_timeout(
            condition=condition, timeout_s=1.0, description="Condition met task"
        )

        # Wywołaj tick przed spełnieniem warunku
        task_timeout.tick_watchdogs()

        # Spełnij warunek
        condition_met = True
        task_timeout.tick_watchdogs()

        # Nie powinno być timeout callbacks
        assert len(task_timeout.timeout_callbacks) == 0

    def test_timeout_triggered(self):
        """Test wywołania timeout gdy warunek nie zostanie spełniony."""
        task_timeout = ConcreteTaskTimeout()

        task_id = task_timeout.add_sensor_timeout(
            condition=lambda: False,  # Warunek nigdy nie spełniony
            timeout_s=0.01,  # Bardzo krótki timeout
            description="Timeout task",
            id="timeout_test",
        )

        # Poczekaj na timeout
        time.sleep(0.02)
        task_timeout.tick_watchdogs()

        # Powinien być wywołany timeout
        assert len(task_timeout.timeout_callbacks) == 1
        assert task_timeout.timeout_callbacks[0]["task_id"] == "timeout_test"

    def test_multiple_conditions_mixed(self):
        """Test wielu zadań z różnymi wynikami."""
        task_timeout = ConcreteTaskTimeout()

        condition1_met = False
        condition2_met = True

        task1_id = task_timeout.add_sensor_timeout(
            condition=lambda: condition1_met,
            timeout_s=0.01,
            description="Will timeout",
            id="task1",
        )

        task2_id = task_timeout.add_sensor_timeout(
            condition=lambda: condition2_met,
            timeout_s=1.0,
            description="Will succeed",
            id="task2",
        )

        # Tick - task2 powinien się zakończyć sukcesem
        task_timeout.tick_watchdogs()

        # Poczekaj na timeout task1
        time.sleep(0.02)
        task_timeout.tick_watchdogs()

        # Tylko task1 powinien mieć timeout
        assert len(task_timeout.timeout_callbacks) == 1
        assert task_timeout.timeout_callbacks[0]["task_id"] == "task1"


class TestTaskTimeoutCancel:
    """Testy anulowania zadań."""

    def test_cancel_existing_task(self):
        """Test anulowania istniejącego zadania."""
        task_timeout = ConcreteTaskTimeout()

        task_id = task_timeout.add_sensor_timeout(
            condition=lambda: False, timeout_s=1.0, description="Task to cancel"
        )

        result = task_timeout.cancel_sensor_timeout(task_id)

        assert result is True

    def test_cancel_nonexistent_task(self):
        """Test anulowania nieistniejącego zadania."""
        task_timeout = ConcreteTaskTimeout()

        result = task_timeout.cancel_sensor_timeout("nonexistent_id")

        assert result is False

    def test_cancel_prevents_timeout(self):
        """Test że anulowanie zapobiega wykonaniu timeout."""
        task_timeout = ConcreteTaskTimeout()

        task_id = task_timeout.add_sensor_timeout(
            condition=lambda: False,
            timeout_s=0.01,
            description="Cancelled task",
            id="cancel_test",
        )

        # Anuluj przed timeoutem
        cancelled = task_timeout.cancel_sensor_timeout(task_id)
        assert cancelled is True

        # Poczekaj na potencjalny timeout
        time.sleep(0.02)
        task_timeout.tick_watchdogs()

        # Nie powinno być timeout callbacks
        assert len(task_timeout.timeout_callbacks) == 0


class TestTaskTimeoutCustomActions:
    """Testy niestandardowych akcji on_timeout."""

    def test_custom_on_timeout_action(self):
        """Test niestandardowej akcji timeout."""
        task_timeout = ConcreteTaskTimeout()
        custom_action_called = []

        def custom_timeout_action(task: SensorTimerTask):
            custom_action_called.append({"id": task.id, "desc": task.description})

        task_id = task_timeout.add_sensor_timeout(
            condition=lambda: False,
            timeout_s=0.01,
            description="Custom action task",
            id="custom_action",
            on_timeout=custom_timeout_action,
        )

        # Poczekaj na timeout
        time.sleep(0.02)
        task_timeout.tick_watchdogs()

        # Powinna być wywołana niestandardowa akcja
        assert len(custom_action_called) == 1
        assert custom_action_called[0]["id"] == "custom_action"

    def test_custom_action_with_metadata(self):
        """Test niestandardowej akcji z metadanymi."""
        task_timeout = ConcreteTaskTimeout()
        received_metadata = []

        def custom_action(task: SensorTimerTask):
            received_metadata.append(task.metadata)

        metadata = {"sensor": "pressure", "value": 100}

        task_timeout.add_sensor_timeout(
            condition=lambda: False,
            timeout_s=0.01,
            description="Metadata task",
            on_timeout=custom_action,
            metadata=metadata,
        )

        time.sleep(0.02)
        task_timeout.tick_watchdogs()

        assert len(received_metadata) == 1
        assert received_metadata[0] == metadata


class TestTaskTimeoutMetadata:
    """Testy obsługi metadanych."""

    def test_metadata_passed_to_timeout(self):
        """Test przekazywania metadanych do timeout."""
        task_timeout = ConcreteTaskTimeout()

        metadata = {
            "device_id": "DEV123",
            "sensor_type": "temperature",
            "expected_value": 25.0,
        }

        task_timeout.add_sensor_timeout(
            condition=lambda: False,
            timeout_s=0.01,
            description="Metadata test",
            id="meta_test",
            metadata=metadata,
        )

        time.sleep(0.02)
        task_timeout.tick_watchdogs()

        assert len(task_timeout.timeout_callbacks) == 1
        assert task_timeout.timeout_callbacks[0]["metadata"] == metadata

    def test_empty_metadata(self):
        """Test zadania bez metadanych."""
        task_timeout = ConcreteTaskTimeout()

        task_timeout.add_sensor_timeout(
            condition=lambda: False,
            timeout_s=0.01,
            description="No metadata task",
            id="no_meta",
        )

        time.sleep(0.02)
        task_timeout.tick_watchdogs()

        assert len(task_timeout.timeout_callbacks) == 1
        # Metadata powinno być None lub pusty dict
        metadata = task_timeout.timeout_callbacks[0]["metadata"]
        assert metadata is None or metadata == {}


class TestTaskTimeoutMultipleTasks:
    """Testy wielu równoczesnych zadań."""

    def test_multiple_tasks_independent(self):
        """Test wielu niezależnych zadań."""
        task_timeout = ConcreteTaskTimeout()

        conditions = [False, False, False]

        task_ids = []
        for i in range(3):
            task_id = task_timeout.add_sensor_timeout(
                condition=lambda idx=i: conditions[idx],
                timeout_s=1.0,
                description=f"Task {i}",
                id=f"task_{i}",
            )
            task_ids.append(task_id)

        # Spełnij jeden warunek
        conditions[1] = True
        task_timeout.tick_watchdogs()

        # Anuluj jeden task
        task_timeout.cancel_sensor_timeout(task_ids[2])

        # Pozostałe ticki nie powinny wywołać timeoutów (długi timeout)
        task_timeout.tick_watchdogs()

        assert len(task_timeout.timeout_callbacks) == 0

    def test_sequential_task_additions(self):
        """Test sekwencyjnego dodawania zadań."""
        task_timeout = ConcreteTaskTimeout()

        for i in range(5):
            task_timeout.add_sensor_timeout(
                condition=lambda: True,  # Wszystkie spełnione
                timeout_s=1.0,
                description=f"Sequential task {i}",
            )

        task_timeout.tick_watchdogs()

        # Żadne nie powinny timeout (wszystkie spełnione)
        assert len(task_timeout.timeout_callbacks) == 0

    def test_multiple_timeouts_simultaneously(self):
        """Test wielu timeoutów występujących jednocześnie."""
        task_timeout = ConcreteTaskTimeout()

        for i in range(3):
            task_timeout.add_sensor_timeout(
                condition=lambda: False,
                timeout_s=0.01,
                description=f"Timeout task {i}",
                id=f"timeout_{i}",
            )

        time.sleep(0.02)
        task_timeout.tick_watchdogs()

        # Wszystkie 3 powinny mieć timeout
        assert len(task_timeout.timeout_callbacks) == 3


class TestTaskTimeoutEdgeCases:
    """Testy przypadków brzegowych."""

    def test_zero_timeout(self):
        """Test z timeoutem równym zero."""
        task_timeout = ConcreteTaskTimeout()

        task_timeout.add_sensor_timeout(
            condition=lambda: False,
            timeout_s=0.0,
            description="Zero timeout",
            id="zero",
        )

        task_timeout.tick_watchdogs()

        # Powinien natychmiast timeout
        assert len(task_timeout.timeout_callbacks) == 1

    def test_very_long_timeout(self):
        """Test z bardzo długim timeoutem."""
        task_timeout = ConcreteTaskTimeout()

        task_timeout.add_sensor_timeout(
            condition=lambda: False, timeout_s=1000.0, description="Long timeout"
        )

        task_timeout.tick_watchdogs()

        # Nie powinno być timeoutu
        assert len(task_timeout.timeout_callbacks) == 0

    def test_condition_raises_exception(self):
        """Test gdy warunek rzuca wyjątek."""
        task_timeout = ConcreteTaskTimeout()

        def faulty_condition():
            raise ValueError("Test exception")

        task_timeout.add_sensor_timeout(
            condition=faulty_condition, timeout_s=0.01, description="Faulty condition"
        )

        # Tick nie powinien crashować
        task_timeout.tick_watchdogs()

        # Watchdog powinien obsłużyć wyjątek wewnętrznie

    def test_tick_without_tasks(self):
        """Test tick gdy nie ma żadnych zadań."""
        task_timeout = ConcreteTaskTimeout()

        # Nie powinno crashować
        task_timeout.tick_watchdogs()
        task_timeout.tick_watchdogs()

        assert len(task_timeout.timeout_callbacks) == 0


class TestTaskTimeoutIntegration:
    """Testy integracyjne symulujące rzeczywiste użycie."""

    def test_sensor_monitoring_scenario(self):
        """Test scenariusza monitorowania czujnika."""
        task_timeout = ConcreteTaskTimeout(device_name="TempSensor")

        sensor_value = 0
        target_value = 100

        def sensor_ready():
            return sensor_value >= target_value

        task_id = task_timeout.add_sensor_timeout(
            condition=sensor_ready,
            timeout_s=1.0,
            description="Waiting for sensor to reach target",
            metadata={"target": target_value},
        )

        # Symuluj stopniowy wzrost wartości
        for _ in range(5):
            task_timeout.tick_watchdogs()
            sensor_value += 20

        task_timeout.tick_watchdogs()

        # Warunek spełniony, nie ma timeoutu
        assert len(task_timeout.timeout_callbacks) == 0

    def test_timeout_recovery_scenario(self):
        """Test scenariusza z timeoutem i obsługą błędu."""
        task_timeout = ConcreteTaskTimeout(device_name="MotorController")
        recovery_actions = []

        def recovery_action(task: SensorTimerTask):
            recovery_actions.append(f"Recovery for {task.description}")

        task_timeout.add_sensor_timeout(
            condition=lambda: False,
            timeout_s=0.01,
            description="Motor initialization",
            on_timeout=recovery_action,
            metadata={"motor_id": "M1"},
        )

        time.sleep(0.02)
        task_timeout.tick_watchdogs()

        assert len(recovery_actions) == 1
        assert "Motor initialization" in recovery_actions[0]

    def test_multiple_sensor_monitoring(self):
        """Test monitorowania wielu czujników jednocześnie."""
        task_timeout = ConcreteTaskTimeout(device_name="MultiSensorDevice")

        sensors = {
            "temp": {"value": 0, "target": 25},
            "pressure": {"value": 0, "target": 100},
            "humidity": {"value": 0, "target": 50},
        }

        for sensor_name, sensor_data in sensors.items():
            task_timeout.add_sensor_timeout(
                condition=lambda s=sensor_name: sensors[s]["value"]
                >= sensors[s]["target"],
                timeout_s=1.0,
                description=f"Waiting for {sensor_name}",
                id=sensor_name,
                metadata=sensor_data,
            )

        # Symuluj niektóre czujniki osiągające cel
        sensors["temp"]["value"] = 30
        sensors["humidity"]["value"] = 60

        task_timeout.tick_watchdogs()

        # Temp i humidity spełnione, pressure nadal czeka
        # Anuluj pressure przed timeoutem
        task_timeout.cancel_sensor_timeout("pressure")

        assert len(task_timeout.timeout_callbacks) == 0


class TestTaskTimeoutMessageLogger:
    """Testy integracji z message_logger."""

    @patch("avena_commons.util.logger.error")
    def test_timeout_with_logger(self, mock_error):
        """Test logowania błędów przy timeout."""
        mock_logger = Mock()
        task_timeout = ConcreteTaskTimeout(
            device_name="LoggedDevice", message_logger=mock_logger
        )

        task_timeout.add_sensor_timeout(
            condition=lambda: False,
            timeout_s=0.01,
            description="Logged timeout task",
            id="logged_task",
        )

        time.sleep(0.02)
        task_timeout.tick_watchdogs()

        # Sprawdź czy error został wywołany
        assert mock_error.called

        # Sprawdź argumenty wywołania
        call_args = mock_error.call_args
        assert "LoggedDevice" in str(call_args)
        assert "Timeout" in str(call_args)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
