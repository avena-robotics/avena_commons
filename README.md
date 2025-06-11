# avena_commons

A utility library for working with Avena Robotics systems.

## Quick Start

**Install from source:**
```bash
pip install .
```

**Run system dashboard:**
```bash
run_system_dashboard
# Opens at https://localhost:5001
```

## Development

**Setup:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

**Test:**
```bash
pytest  # Runs tests with 90% coverage requirement
```

**Build with tests:**
```bash
tox -e build  # Tests must pass before building
```

**Build without tests:**
```bash
tox -e build-no-tests
```


**Code quality:**
```bash
ruff check .     # Lint
ruff format .    # Format
```

## Project Structure
```
src/avena_commons/     # Source code
tests/                 # Test files (unit/ and integration/)
```

**Contributing:** 90% test coverage required, follow PEP 8, run `tox -e build` before submitting.

