# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`avena_commons` is a Python utility library for Avena Robotics systems providing communication, configuration management, I/O device control, orchestration, and system monitoring.

**Python Version:** >=3.10
**License:** Apache 2.0

## Common Commands

### Development Setup
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e '.[dev]'
```

### Testing
```bash
# Run all tests (requires 90% coverage minimum - currently 10% configured)
pytest

# Run tests with coverage report
pytest --cov=avena_commons --cov-report=term-missing --cov-fail-under=90

# Run specific test file
pytest tests/unit/test_module.py

# Run with verbose output
pytest -v
```

### Code Quality
```bash
# Format code
ruff format .

# Lint code
ruff check .

# Fix auto-fixable issues
ruff check . --fix
```

### Building
```bash
# Build with tests (recommended before submitting)
tox -e build

# Build without tests (for quick distribution)
tox -e build-no-tests

# Manual build
python -m build
```

### Running System Dashboard
```bash
# After installation, run the system dashboard
run_system_dashboard
# Opens at https://localhost:5001
```

## Architecture Overview

### Core Design Patterns

#### 1. Connector/Worker Pattern
The library uses a multiprocessing pattern for hardware abstraction and concurrent operations:
- **Connector**: Main process interface with thread-safe pipe communication
- **Worker**: Separate process running control loops at specified frequencies
- Communication via multiprocessing pipes with command/response pattern
- Used extensively for hardware I/O, camera interfaces, and real-time operations

Key implementation details:
- Workers run in separate processes for CPU core assignment and isolation
- Control loops use `ControlLoop` utility for precise timing
- Commands sent through pipes with pattern matching (STOP, GET_STATE, setters/getters)
- Thread safety managed with locks in Connector classes

See: `docs/connector_worker_usage.md` for detailed implementation guide

#### 2. Event-Driven Architecture
The `EventListener` base class provides asynchronous event processing:
- FastAPI-based HTTP event server
- Priority queue system for event handling
- FSM (Finite State Machine) pattern for component lifecycle
- JSON event serialization with Pydantic models

Standard FSM states: `STOPPED → INITIALIZING → INITIALIZED → STARTING → STARTED → STOPPING`

#### 3. Orchestrator System
Central component for coordinating complex multi-component workflows:

**Location:** `src/avena_commons/orchestrator/`

**Key Concepts:**
- **Scenarios**: YAML-defined workflows with actions and conditions
- **Actions**: Executable operations (send commands, wait for states, database updates, email/SMS, systemctl)
- **Conditions**: Boolean evaluations for flow control (client state, database queries, custom logic)
- **Components**: External systems tracked and controlled by orchestrator

**Action Types:**
- `send_command`: Send FSM commands to components
- `wait_for_state`: Block until component reaches target state
- `database_update_action_base`: Update database records
- `send_email_action`, `send_sms_action`: Notifications
- `systemctl_action`: System service control
- Custom actions via plugin system

**Condition Types:**
- `client_state_condition`: Check component FSM state
- `database_list_condition`: Query database for records
- Custom conditions via `ConditionFactory`

**Scenario Execution:**
- Load scenarios from YAML files in `orchestrator/scenarios/`
- Actions execute sequentially with timeout support
- Conditions evaluate before action execution
- Concurrent scenario execution with configurable limits
- Context passed between actions via `ScenarioContext`

**Testing:** Test services provided in `tests/services/` simulate real components with FSM state machines

### Module Structure

```
src/avena_commons/
├── config/              # INI-based configuration management
├── connection/          # POSIX shared memory IPC (AvenaComm)
├── dashboard/           # Flask-based monitoring dashboard with Alpine.js frontend
├── event_listener/      # Event-driven architecture base classes
│   └── types/          # Event type definitions (IoAction, KdsAction, Supervisor*)
├── io/                  # Industrial I/O device management
│   ├── bus/            # ModbusRTU, ModbusTCP protocol implementations
│   ├── device/         # Device drivers (P7674, EC3A I/O modules)
│   └── virtual_device/ # Device simulation and watchdog
├── nayax/              # Payment system integration
├── orchestrator/        # Workflow orchestration engine
│   ├── actions/        # Executable workflow actions
│   ├── conditions/     # Workflow conditional logic
│   ├── components/     # External system integrations (email, SMS, database, APIs)
│   ├── factories/      # Factory patterns for dynamic loading
│   ├── models/         # Pydantic data models
│   └── scenarios/      # YAML scenario definitions
├── pepper/             # Pepper robot integration
├── sequence/           # Sequential operation state machines
├── system_dashboard/   # System monitoring web interface
├── util/               # Utilities (timing, logging, control loops)
└── vision/             # Computer vision and camera interfaces
```

## Key Architectural Decisions

### Testing Philosophy
- **Unit tests** in `tests/unit/`: Isolated component tests with mocks
- **Integration tests** in `tests/integration/`: Cross-component interactions
- Mirror source structure in test directory
- Use pytest fixtures in `conftest.py` for shared setup
- Target 90% code coverage (currently configured at 10% minimum)

### Configuration Management
- INI files for system configuration via `Config` and `ControllerConfig`
- Environment variables supported (e.g., `AVENA_COMMONS_SKIP_AUTO_INSTALL`)
- Configuration values validated on load

### Logging
- `MessageLogger` from `util.logger` for structured logging
- Log levels: debug, info, warning, error
- Thread-safe logging with file and console output
- Use message_logger parameter throughout codebase

### Hardware I/O
- Bus protocols: EtherCAT (pysoem), ModbusRTU, ModbusTCP (pymodbus 3.9.2)
- Virtual devices for testing without hardware
- Device state management with enums
- Centralized `IO_server` for device coordination

### Camera Integration
- Automatic SDK installation via `install_orbec_sdk` command
- Orbec camera support with pyorbbecsdk
- OpenCV integration for processing
- Connector/Worker pattern for camera management

## Important Implementation Guidelines

### When Adding New Features

1. **Follow src/ layout**: All code goes in `src/avena_commons/`, tests in `tests/`
2. **Mirror test structure**: `src/avena_commons/module.py` → `tests/unit/test_module.py`
3. **Use type hints**: All public functions should have type annotations
4. **Write docstrings**: PEP 257 style with param/return/raises documentation
5. **Add tests first**: Write failing tests, then implement, target 90%+ coverage
6. **Format with Ruff**: Run `ruff format .` before committing

### When Working with Orchestrator

1. **Scenario files** go in `src/avena_commons/orchestrator/scenarios/` as YAML
2. **New actions** extend `BaseAction` in `orchestrator/actions/`
3. **New conditions** extend `BaseCondition` in `orchestrator/conditions/`
4. **Register in factories** for dynamic loading
5. **Test scenarios** use mock services from `tests/services/`

Example scenario structure:
```yaml
- name: "Scenario Name"
  conditions:
    - type: "client_state_condition"
      component: "component_name"
      expected_state: "INITIALIZED"
  actions:
    - type: "send_command"
      component: "component_name"
      command: "CMD_INITIALIZE"
    - type: "wait_for_state"
      component: "component_name"
      target_state: "INITIALIZED"
      timeout: "30s"
```

### When Implementing Connector/Worker

1. **Connector** inherits from `util.worker.Connector`
   - Override `_run()` to instantiate Worker
   - Override `_send_thru_pipe()` if needed
   - Use threading.Lock for pipe safety
   - Implement properties with `@Connector._read_only_property` decorator

2. **Worker** inherits from `util.worker.Worker`
   - Override `_run(pipe_in)` with main loop
   - Use `ControlLoop` for timing
   - Handle commands with match/case pattern
   - Send responses via `pipe_in.send()`
   - Heavy operations run in separate threads

### When Working with EventListener Components

1. Inherit from `EventListener` base class
2. Implement FSM state transitions
3. Handle events via `_handle_event()` override
4. Use async/await for I/O operations
5. Register with orchestrator via configuration
6. Test with mock EventListener clients

## Dependencies and Compatibility

### Key Dependencies
- **numpy==1.26.4**: Array operations (pinned version)
- **pymodbus==3.9.2**: Modbus protocol (pinned version)
- **FastAPI/uvicorn**: Event listener HTTP server
- **Flask**: System dashboard web interface
- **pydantic**: Data validation and serialization
- **opencv-python**: Computer vision
- **pysoem**: EtherCAT protocol (Linux-specific)
- **posix-ipc**: Shared memory (Linux-specific)

### Platform-Specific Notes
- Some features are Linux-only (posix-ipc, EtherCAT)
- Windows compatibility maintained for core features
- Use platform checks: `platform_system=="Linux"` in dependencies

## Code Style and Standards

- **Line length**: 88 characters (Black default)
- **Formatting**: Ruff (enforces PEP 8)
- **Linting rules**: Ruff checks E (errors), W (warnings), F (pyflakes), I (imports)
- **E501 ignored**: Line length handled by formatter
- **Naming**: snake_case for functions/variables, CamelCase for classes
- **Imports**: Sorted and grouped by Ruff
- **Docstrings**: Required for all public APIs

## Special Files and Directories

- `.cursorrules`: AI contribution guidelines (comprehensive, reference this)
- `.ruff.toml`: Linting configuration
- `tox.ini`: Test automation and build configuration
- `pyproject.toml`: Project metadata, dependencies, tool configuration
- `docs/`: Architecture documentation and implementation notes
- `resources/`: Non-code assets
- `temp/`: Temporary files (gitignored)
- `install/`: Installation scripts and resources

## Common Pitfalls to Avoid

1. **Don't import from tests**: Test code should never be imported by source
2. **Don't hardcode paths**: Use `pathlib` and relative imports
3. **Don't skip error handling**: Always handle exceptions in Workers and EventListeners
4. **Don't block Workers**: Heavy operations must run in threads
5. **Don't forget locks**: Pipe communication needs thread safety
6. **Don't ignore FSM states**: Components must follow STOPPED→STARTED lifecycle
7. **Don't create circular imports**: Use TYPE_CHECKING for type hints if needed
8. **Don't modify pyproject.toml** without understanding build implications

## Useful Entry Points

- `run_system_dashboard`: Web-based system monitoring
- `install_orbec_sdk`: Camera SDK installation utility

## Additional Resources

- Connector/Worker guide: `docs/connector_worker_usage.md`
- Dashboard architecture: `docs/architecture/README_DASHBOARD_TREE.md`
- Test services guide: `tests/README_test_services.md`
- Orchestrator scenarios: `tests/services/README_orchestrator_scenarios.md`
- Vision documentation: `docs/vision.md`
