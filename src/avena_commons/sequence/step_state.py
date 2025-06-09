from enum import Enum


class StepState(str, Enum):
    """State machine state for a single sequence step.

    Represents possible states that a step can be in:
    - PREPARE: Step is being prepared for execution
    - EXECUTE: Step is currently executing
    - DONE: Step has completed successfully
    - TEST_FAILED: Step has failed its test
    - ERROR: An error occurred during step execution
    """

    PREPARE = "PREPARE"
    EXECUTE = "EXECUTE"
    DONE = "DONE"
    TEST_FAILED = "TEST_FAILED"
    ERROR = "ERROR"  # opcjonalnie
