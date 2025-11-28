"""Testy jednostkowe dla TaskTimeout z automatycznym tickowaniem watchdogów w tle.

Sprawdza czy wątek tickowania działa, czy zadania timeout są obsługiwane.
"""
import threading
import time

import pytest

from avena_commons.io.virtual_device.sensor_watchdog import SensorTimerTask
from avena_commons.util.task_timeout import TaskTimeout


class DummyTimeout(TaskTimeout):
    def __init__(self, *args, **kwargs):
        self.timeout_triggered = threading.Event()
        super().__init__(*args, **kwargs)
        self.device_name = "DummyDevice"

    def on_sensor_timeout(self, task: SensorTimerTask) -> None:
        self.timeout_triggered.set()
        self.last_task = task

def test_background_tick_triggers_timeout():
    dummy = DummyTimeout()
    # Warunek nigdy nie spełniony, timeout po 0.2s
    task_id = dummy.add_sensor_timeout(
        condition=lambda: False,
        timeout_s=0.2,
        description="Test timeout"
    )
    # Czekaj na wywołanie timeout (max 1s)
    triggered = dummy.timeout_triggered.wait(timeout=1.0)
    assert triggered, "Timeout should be triggered by background thread"
    assert hasattr(dummy, 'last_task')
    assert dummy.last_task.description == "Test timeout"
    # Sprzątanie
    del dummy

def test_cancel_prevents_timeout():
    dummy = DummyTimeout()
    task_id = dummy.add_sensor_timeout(
        condition=lambda: False,
        timeout_s=0.5,
        description="Should not timeout"
    )
    # Anuluj przed upływem czasu
    time.sleep(0.1)
    cancelled = dummy.cancel_sensor_timeout(task_id)
    assert cancelled, "Task should be cancelled"
    # Poczekaj dłużej niż timeout
    triggered = dummy.timeout_triggered.wait(timeout=0.6)
    assert not triggered, "Timeout should NOT be triggered after cancel"
    del dummy
