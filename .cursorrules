---
applyTo: '**/*'
---
# Avena Commons Contribution Guidelines (for AI-Generated Code)

These guidelines describe how to structure, test, and style code contributions to the **`avena_commons`** package. They ensure consistency and maintainability, especially when AI tools are used to generate code. Follow these instructions closely to align with project standards and best practices.

## 1. Folder Structure Best Practices

* **Use the `src/` layout:** All source code resides under `src/avena_commons/`, and tests reside in a separate `tests/` directory at the root level. This layout prevents accidental imports from the working directory during development and forces installations for testing. For example:

  ```text
  avena_commons/
  ├── pyproject.toml         # Project metadata and build config
  ├── src/
  │   └── avena_commons/
  │       ├── __init__.py    # Makes this a package
  │       ├── moduleA.py
  │       └── moduleB.py
  └── tests/
      ├── unit/
      │   └── test_moduleA.py
      └── integration/
          └── test_featureX.py
  ```

  *Example: Source code under `src/avena_commons/` and tests in `tests/`. Unit and integration tests are separated into subfolders for clarity.*

* **Organize modules into subpackages:** Group related modules into subpackages (subdirectories with their own `__init__.py`). For instance, if the package spans multiple domains (e.g. image\_processing, database\_utils), create `src/avena_commons/image_processing/` and `src/avena_commons/database_utils/` with an `__init__.py` in each. This hierarchy makes the codebase easier to navigate and maintain. Each subpackage’s `__init__.py` should import or expose only what is necessary for the public API, or can be left empty if not needed for initialization.

* **Use `__init__.py` files appropriately:** Ensure every package directory contains an `__init__.py` (even if empty) to define it as a Python package. This is required for Python to recognize the module structure and allows relative imports within the project. Avoid putting execution logic in `__init__.py`; use it mainly to define package-level variables (like version) or to import commonly used subcomponents.

* **Test directory structure:** Mirror the source code structure in the `tests/` directory. For each module or subpackage in `avena_commons`, create a corresponding test module under `tests/`. For example, tests for `avena_commons/image_processing/filters.py` should reside in `tests/image_processing/test_filters.py`. This one-to-one mapping makes it easy to find tests for a given piece of code and vice versa. Keep **unit tests** (testing individual functions or classes in isolation) separate from **integration tests** (testing interactions between components or with external systems). A common approach is to have subfolders like `tests/unit/` and `tests/integration/` to clearly separate fast, isolated unit tests from slower integration tests that might involve databases, network calls, or larger workflows.

* **Data and resource files:** If the package requires data files (e.g. sample images, configuration templates, etc.), store them under `src/avena_commons/data/` (or a similarly named subfolder). Include an `__init__.py` in the data folder only if you need to make it a package (usually not required for just data files). To ensure these files are packaged, either list them under `package_data` in the build config or use the `include-package-data = True` setting with a MANIFEST.in if using Setuptools. Access such data files in code using the standard library (e.g. `importlib.resources` in Python 3.9+) instead of hardcoding file paths.

## 2. Testing Guidelines

* **Pytest test discovery conventions:** Follow Pytest’s naming conventions so that tests are automatically discovered. Test file names should start or end with `test` (e.g. `test_module.py` or `module_test.py`), and each test function should be prefixed with `test_`. For example, a test function might be `def test_feature_xyz(): ...`. Pytest will collect all such functions and execute them. Organizing test code this way means you can simply run `pytest` to execute the entire test suite.

* **Unit vs integration tests:** Place **unit tests** in the `tests/unit/` directory and **integration tests** in `tests/integration/` (or other appropriate subdirectories) to distinguish their purpose. Unit tests should focus on small pieces of functionality and use **mocks/stubs** for external interfaces. Integration tests can exercise the system more holistically (e.g., actual database or API calls). This separation helps in continuous integration (CI) environments – for example, you might run unit tests on every commit, but run the slower integration tests less frequently or under specific conditions. Clearly mark integration tests (using Pytest markers like `@pytest.mark.integration`) if you want to easily include/exclude them during test runs. By default, aim to have all tests pass on a development machine with `pytest` alone; CI can be configured to skip certain marked tests if needed.

* **Test organization and style:** Write tests that mirror the structure of the code and cover various scenarios (normal cases, edge cases, error conditions). Keep tests **small and focused** – ideally one logical check per test function. Use descriptive names for test functions to indicate what they’re checking (e.g. `test_parse_config_invalid_file()` clearly indicates the scenario). It’s often helpful to group related tests into test classes (class names beginning with `Test`) for organizational purposes, but avoid `__init__` methods in test classes (use `setup_method` or fixtures for setup).

* **Using fixtures for setup/teardown:** Take advantage of **pytest fixtures** to manage repetitive setup or teardown tasks. Fixtures can provide test data or state and are injected into tests by naming convention. For example, you might have a `@pytest.fixture` that prepares a temporary directory or database connection. Test functions that accept a parameter with the same name as a fixture will automatically use it. Use **`conftest.py`** to define fixtures that should be globally available to multiple test modules (such as a fixture to load a config or create a common test client). Fixtures help keep tests clean and focused on assertions rather than setup details.

* **Testing examples:** Here’s a simple example of a test using a fixture:

  ```python
  # File: tests/unit/test_example.py
  import pytest
  from avena_commons import compute_value

  @pytest.fixture
  def sample_input():
      # Setup: provide input data for tests
      return {"x": 42, "y": 3.14}

  def test_compute_value_basic(sample_input):
      result = compute_value(sample_input["x"], sample_input["y"])
      assert result is not None
      assert isinstance(result, float)
  ```

  In this example, the `sample_input` fixture provides a dictionary that the test can use. The test function `test_compute_value_basic` requests this fixture by name, and Pytest ensures it’s executed before the test runs. The assertions then check that the result is not `None` and has the expected type. You should write similar targeted tests for each new function or class added.

* **Test coverage requirements:** We require a high level of test coverage (e.g. **90% or above** of statements). Every new code contribution should include unit tests such that overall coverage does not drop below this threshold. Use the **pytest-cov** plugin to measure coverage. For example, running tests with coverage can be done via:

  ```bash
  pytest --cov=avena_commons --cov-report=term-missing --cov-fail-under=90
  ```

  This command will produce a coverage report and **fail the test run if coverage is below 90%**. It’s recommended to run this periodically (or via a tox/CI configuration) to ensure the test suite adequately covers the code. A 90% coverage rate means 10% of lines are not executed by tests, which is a reasonable buffer to allow for things like debug logs or error handling branches. When adding new modules, strive for **100% coverage** on those modules if possible. If certain code is difficult to test (e.g. calls to hardware or external systems), you can use mocks or simulate conditions to still cover the logic.

* **Running tests:** Developers (or AI contributors) should run tests locally before submitting code. Activate the `venv` (see Development Environment Setup below) and simply use the `pytest` command. Ensure that both unit and integration tests pass. If needed, use markers or names to run a subset (e.g. `pytest -m "not integration"` to skip integration tests, if integration tests are marked accordingly). All tests, including integration ones, will be run in the continuous integration pipeline, so they should be reliable (no flaky tests) and not depend on unavailable external resources (or skip themselves with a clear message if such resources are absent).

## 3. Coding Standards and Linting

* **Follow PEP 8 style guidelines:** Code must adhere to the PEP 8 style guide for Python, which improves code readability and consistency. Key conventions include using 4 spaces per indentation level, using **snake\_case** for function and variable names and **CamelCase** for class names, and keeping line lengths under about 79 characters (unless overridden by project-specific rules). PEP 8 suggests a maximum line length of 79 characters for code (and 72 for comments/docstrings), to allow side-by-side viewing and avoid horizontal scrolling. In practice, our project may allow slightly longer lines (some teams use 88 or 100 characters as a limit), but **never exceed 120 characters** per line. If you use an auto-formatter like Black, note that Black’s default line length is 88 characters – you can configure this in `pyproject.toml` if needed, but stick to the project’s chosen limit. Remember: **code is read far more often than it is written**, so prioritizing readability and consistency is paramount.

* **Naming conventions:** Choose clear, descriptive names for variables, functions, and classes. Avoid single-letter names or abbreviations that obscure meaning. Function and method names should be verbs or verb phrases (e.g., `calculate_total`, `send_message`), reflecting what they do. Variable names should reflect their content or purpose (e.g., `timeout_sec` for a timeout value in seconds). Class names should typically be nouns in CamelCase (e.g., `DataProcessor`). Constants (module-level variables meant to be immutable) should be UPPER\_CASE. These conventions align with standard Python style and make the code self-documenting.

* **Mandatory linting with Ruff:** We use **Ruff** as the linter to catch code style issues and common errors. Ruff is an extremely fast Python linter that encapsulates many checks from Flake8, pycodestyle, import order, etc., in one tool. All code contributions must pass Ruff with no warnings or errors. The configuration for Ruff is in `pyproject.toml` under `[tool.ruff]` (see **pyproject.toml Guidelines** below). Typically, this includes rules enforcing PEP 8 conventions (spacing, naming, imports), removing unused imports/variables, and other best practices. For example, Ruff will warn about things like unused imports, undefined names, or stylistic issues. Run Ruff locally (e.g., `ruff .` at the project root) to check your code. You can also integrate it into your editor or as a pre-commit hook for continuous feedback. **Do not ignore Ruff’s output** – fix all issues it reports before committing. In rare cases where a rule needs to be overridden (e.g., a naming that violates a convention but is justified), adjust the configuration in `pyproject.toml` rather than ignoring warnings inline, to keep the codebase clean.

* **Automatic formatting (optional):** While not strictly mandated, it’s strongly recommended to use a formatter like **Black** to maintain consistent code style. Black will auto-format your code to conform to a standard style (PEP 8 with a few opinions, such as 88-char lines) and can save time on manual formatting. If you use Black, be sure to configure it (via `pyproject.toml` \[tool.black] section) with the project’s settings (for example, line-length and any excludes). Running Black should produce no changes after your final edits – that’s a good check that your code is properly formatted. Even if you don’t use Black, ensure your code is **PEP 8 compliant and nicely formatted** before submission. This means proper indentation, spacing around operators and commas, etc. (Ruff will catch many of these issues as well). Consistent formatting makes diffs cleaner and reviews easier.

* **Type hints and mypy (optional but encouraged):** The project values code clarity and reliability, so using **Python type hints** is encouraged for new code. Adding type annotations to function signatures and variables can greatly help with understanding the code and catching errors early. We may run **mypy** (a static type checker) on the codebase in the future, or at least use type hints for documentation purposes. Consider adding type annotations to all public functions/methods. If you run mypy on your code, fix any type errors it reports. For instance, ensure functions declare their return types and that all branches return compatible types. While mypy usage is not yet mandatory, *adhering to type-checking discipline is highly recommended* for AI-generated code to ensure correctness (AI may sometimes make type assumptions; explicit annotations help avoid mistakes).

* **Documentation and comments:** Write docstrings for all public modules, classes, functions, and methods. Follow the conventions of **PEP 257** for docstrings – start with a one-line summary in imperative tone (“Do this, return that”), optionally followed by a more detailed explanation after a blank line. The docstring should clearly explain what the function or class does, its parameters, return values, possible exceptions, and usage examples if applicable. For example:

  ```python
  def compute_value(x: int, y: float) -> float:
      """Compute a combined value from x and y.

      Uses a proprietary formula to combine an integer and a float into a single score.
      :param x: The count of items (must be non-negative).
      :param y: The weight factor as a float.
      :return: A floating-point score representing the combined value.
      :raises ValueError: if x is negative or y is NaN.
      """
      ...
  ```

  This docstring concisely **summarizes the function’s behavior and documents its arguments, return value, exceptions, and any important restrictions**. Write similar docstrings for classes (including listing important attributes or methods) and modules (explaining the module’s purpose). In addition to docstrings, use in-line comments sparingly to explain non-obvious logic, but prefer clear code over excessive comments. Remember that *documentation is also part of code quality*, and it helps future maintainers (and yourself) understand the intent behind the code.

* **Avoid common pitfalls:** Ensure the AI-generated code does not include problematic patterns:

  * No hard-coded paths or secrets in the code.
  * Avoid global mutable state; prefer functions or classes with well-defined interfaces.
  * Handle errors and exceptions gracefully – use appropriate exception types, and don’t catch exceptions broadly or silently.
  * Ensure compatibility with supported Python versions (check `pyproject.toml` for `requires-python` or use Python 3.10+ features only if allowed).
  * Write efficient code: for example, avoid nested loops of large complexity if a vectorized or more efficient approach is available. However, **readability should not be sacrificed for micro-optimizations** – find a balance, and comment on any complex optimizations you implement.

In summary, all contributed code (AI-generated or not) must be **clean, readable, and conformant to our linting and style rules**. Code style guidelines exist to make the codebase uniform and maintainable. Any merge request that does not pass linting or deviates from these standards will require revisions.

## 4. pyproject.toml Guidelines

Our project uses `pyproject.toml` to configure packaging, dependencies, and tool settings. All contributors should be comfortable editing this file when necessary:

* **Project metadata (\[project] table):** Basic project info is declared under `[project]` in pyproject.toml. This includes fields like `name`, `version`, `description`, `authors`, and so on. When contributing, **do not change metadata fields** (like authors or license) without permission. However, you might need to update the version for a new release (see versioning below). The project adheres to semantic versioning (MAJOR.MINOR.PATCH). If your contribution is significant (e.g. new features) and we’re preparing a release, you may bump the **MINOR** or **PATCH** version accordingly, but coordinate with the maintainers on this. Version updates are done by editing the `version = "x.y.z"` field in `[project]`. Ensure the version string is updated in any other places it might exist (sometimes the package **init**.py may also define `__version__`; if so, update it consistently).

* **Dependencies:** The `[project.dependencies]` array in pyproject.toml lists the runtime dependencies of the package. If your code addition requires a new dependency, **justify its necessity** and add it to this list. Each dependency entry is a string, optionally with a version specifier. For example:

  ```toml
  [project]
  dependencies = [
    "requests>=2.28",
    "numpy>=1.23,<2.0",
    "awesome-lib>=0.5.1"
  ]
  ```

  List the dependency name and version pinning (use inclusive lower bounds and exclusive upper bounds for safety when appropriate). **Avoid overly restrictive pins** unless necessary; allow compatibility with future patch versions. If a dependency is only needed for specific functionality or an optional feature, consider making it an **optional dependency** instead of a required one.

* **Optional dependencies (extras):** Use `[project.optional-dependencies]` to declare groups of optional dependencies (also known as “extras”). Each entry under this table defines an extra name and a list of packages. For example, we might define:

  ```toml
  [project.optional-dependencies]
  dev = [
    "pytest>=7.0",
    "pytest-cov",
    "ruff",
    "black",
    "mypy"
  ]
  vision = [
    "opencv-python",
    "Pillow"
  ]
  ```

  In this snippet, installing the project with `pip install avena_commons[dev]` would include development/testing tools like pytest and linters, whereas `[vision]` might pull in image processing libraries for vision-related features. When adding a new optional feature that brings new dependencies, define a new extra or use an existing one if appropriate. This keeps the core installation light for users who don’t need those optional parts.

* **Updating dependencies:** If you upgrade the minimum required version of a dependency (for example, requiring a newer version of numpy due to new APIs used), update the specifier in `pyproject.toml` accordingly. Also update any mentions in documentation (like README or docs) about supported versions. After modifying dependencies in pyproject.toml, it’s good practice to regenerate the `requirements.txt` (if we maintain one for exact pins) or update the lock file if using one. Ensure that the package still builds and all tests pass with the new dependency version.

* **Build system and setuptools config:** The `[build-system]` table in pyproject.toml declares the build backend (we use Setuptools) and the required versions. This usually looks like:

  ```toml
  [build-system]
  requires = ["setuptools>=61.0", "wheel"]
  build-backend = "setuptools.build_meta"
  ```

  You normally shouldn’t need to change this. If you add package data or change package finding, check if a `[tool.setuptools]` section is present. For example, if we rely on automatic package discovery, we might have:

  ```toml
  [tool.setuptools.packages.find]
  where = ["src"]
  ```

  which tells Setuptools to find packages under `src`. If your contribution involves adding a new top-level package or changing the structure, ensure this still works (most likely, we stay within one package `avena_commons`, so this wouldn’t change).

* **Tool configuration (\[tool.* tables):*\* We use the `[tool.ruff]` section in pyproject.toml to configure the Ruff linter, instead of separate config files. For instance, it may specify settings like line length, excluded directories, or enabled/disabled rules. For example:

  ```toml
  [tool.ruff]
  line-length = 88
  select = ["E", "W", "F", "I"]  # which error codes to check (example)
  ignore = ["E501"]             # example: ignore line-length error if handled by black
  ```

  If you find Ruff is flagging something that needs an exception or new rule (e.g., you want to enable a new lint rule), discuss it with maintainers and update the pyproject config accordingly. Similarly, other tools like Black or mypy can be configured under `[tool.black]`, `[tool.mypy]`, etc. For instance, we might set `[tool.black] line-length = 88` to keep Black consistent with Ruff. Check the **pyproject.toml** diff in your contributions to ensure you didn’t unintentionally alter any tool settings. Only change these settings with good reason.

* **Project scripts/entry points:** The pyproject file is also where command-line **entry points** are defined (in the `[project.scripts]` table). See the next section for details on adding scripts. In pyproject, it looks like:

  ```toml
  [project.scripts]
  mytool = "avena_commons.cli:main"
  ```

  which means after installation, a command `mytool` will be available, invoking `avena_commons.cli.main()`. When adding or modifying scripts, update this section accordingly. Each script should have a unique name (typically the tool or command name) and point to a callable in the package (“module\:function”). Avoid changing or removing existing script names without discussion, as that can break users’ workflows.

* **Versioning and release notes:** If your contribution is going out in a release, ensure the version is bumped as described earlier. In addition, if we maintain a CHANGELOG or release notes, add an entry summarizing your changes (AI contributions should be transparent about what was added or fixed). This might not be in pyproject.toml but is part of the release process. For example, update `CHANGELOG.md` with a bullet about the new feature or bugfix you implemented.

In short, treat the **pyproject.toml** as the central configuration for the project. Any changes to dependencies, scripts, or metadata should be done carefully and reviewed. The file should remain well-formatted (TOML is sensitive to syntax) and comments can be added for clarity if needed (although TOML doesn’t officially support comments, some tooling might ignore `#`). Always verify that after editing pyproject.toml, you can still build the package (e.g., run `pip install .` or `python -m build`) to catch any syntax errors or config mistakes.

## 5. Development Environment Setup

To ensure consistency, set up a local development environment using Python’s built-in **venv** and install the package in editable mode with dev dependencies:

* **Python version:** Ensure you have a compatible Python version installed (check `pyproject.toml` for `requires-python`; for example, if it says `>=3.8`, use Python 3.8 or newer). We recommend using the latest LTS Python (e.g. Python 3.10 or 3.11) for development.

* **Create a virtual environment:** In the project root (where pyproject.toml resides), create a virtual environment. For example, on a Unix-like system:

  ```bash
  python3 -m venv venv
  source venv/bin/activate   # On Windows use: venv\Scripts\activate
  ```

  This creates an isolated Python environment named "venv" (you can name it differently if you prefer). **Always activate the venv** before working on the project to ensure you’re using the project’s Python and not the system Python.

* **Upgrade pip:** It’s a good idea to upgrade pip and setuptools in your venv:

  ```bash
  pip install --upgrade pip setuptools wheel
  ```

* **Install package and dependencies:** There are two common ways to install the dependencies:

  1. **Using pyproject (preferred):** If optional dev/test dependencies are defined in pyproject (e.g., under `optional-dependencies.dev`), you can install them all in one go with an editable install. For example:

     ```bash
     pip install -e '.[dev]'
     ```

     The `-e` flag installs the package in **editable** mode (so changes to code are immediately reflected without reinstalling) and `'.[dev]'` means "install this project plus the 'dev' extra dependencies". This should pull in packages like pytest, ruff, etc., as listed in pyproject. We might have several extras (like `[dev]`, `[vision]`, etc.); you can combine them as needed, e.g., `pip install -e '.[dev,vision]'`.

  2. **Using requirements files:** Some projects maintain explicit `requirements.txt` or `requirements-dev.txt`. If such files exist, you can do:

     ```bash
     pip install -r requirements.txt
     pip install -r requirements-dev.txt
     pip install -e .
     ```

     (The last line installs the package in editable mode after base requirements are in place.) Check the repository for any `requirements*.txt` files and follow instructions in the README if provided. In our case, we lean towards using pyproject extras to avoid duplicating dependency definitions.

* **Verify installation:** After installation, you should be able to import the package and run the tests. For example, run a Python shell and `import avena_commons` to ensure it’s available. If the package uses any native extensions or requires additional setup (not likely here, since this is a pure Python commons library), refer to any documentation on building those (e.g., if there were C extensions, you’d need build tools).

* **Pre-commit hooks (if configured):** We might have a `.pre-commit-config.yaml` in the repo (common for enforcing linters/formatters on commits). If so, install pre-commit in your venv (`pip install pre-commit`) and run `pre-commit install` to set up git hooks. This will automatically run tools like Ruff or Black on commit. Even if not configured, manually run the linters/formatters as described before pushing your changes.

* **Working on multiple features:** If using an AI to generate multiple contributions, consider isolating each feature or fix on its own **git branch**. This is more of a git workflow tip, but it helps in managing changes and code reviews. The development environment (venv) can be reused across branches.

* **Reproducing test environment:** Our CI pipeline (if any) likely runs on a fresh environment. To mimic this, you could use tools like `tox` or GitHub Codespaces (or simply create a fresh venv) to ensure all needed dependencies are declared and no local-only configurations exist. For example, if you run `pytest` in a clean env after `pip install -e '.[dev]'` and everything passes, you’ve likely captured all dependencies properly.

* **Troubleshooting environment issues:** If you encounter import errors or missing packages when running tests, double-check that those packages are listed in pyproject dependencies (or the appropriate requirements file). The development environment should be reproducible by others, so avoid relying on globally installed packages or environment-specific settings. Document any special setup in the README or a developer guide if needed (for example, if integration tests require a running database or specific OS packages, note that somewhere).

In summary, **use a virtual environment** to encapsulate the project’s dependencies, and install the project in editable mode with all dev requirements. This ensures consistency and prevents the “it works on my machine” syndrome. AI-generated code should assume this standard setup and not require unconventional environment tweaks.

## 6. Scripts and Entry Points

The `avena_commons` package may provide command-line tools or scripts via console entry points defined in pyproject.toml. Here’s how to define a new script and ensure it works correctly:

* **Defining console scripts:** Console scripts are defined under the `[project.scripts]` section in pyproject.toml, mapping a command name to a Python function. For example:

  ```toml
  [project.scripts]
  avena-tool = "avena_commons.cli:main"
  ```

  This means that after installation, a user can run `$ avena-tool` in the shell, which will execute `avena_commons/cli.py`’s `main()` function. Under the hood, installing the package creates an entry point that essentially does `from avena_commons import cli; sys.exit(cli.main())` when `avena-tool` is invoked. When adding a new script, pick a short, hyphenated name (if multi-word) for the command and point it to an appropriate function in the codebase.

* **Implementing the script function:** In the above example, you would implement a `main()` function in `src/avena_commons/cli.py`. This function should parse any arguments (using something like argparse or click if needed) and perform the desired action. It should also handle errors gracefully and provide a proper exit code (return 0 for success, non-zero for error). For scripts, it’s often useful to guard execution with `if __name__ == "__main__": main()` in the module, so that the script can be run with `python -m avena_commons.cli` as well during development.

* **Testing console scripts:** It’s important to test that the entry point works. There are a few ways to test scripts:

  * **Function-level testing:** The simplest is to call the script’s main function directly in a test. For example, if `main()` uses `argparse` to parse sys.argv, you can simulate arguments by patching `sys.argv` or better, refactor `main()` to accept an arguments list for easier testing. Then in a unit test, you might do:

    ```python
    from avena_commons import cli
    def test_cli_no_args(monkeypatch, capsys):
        # Simulate no arguments
        monkeypatch.setattr(sys, "argv", ["avena-tool"])
        exit_code = cli.main()
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "Usage" in captured.out  # expecting usage info on no args
    ```

    This uses pytest’s `monkeypatch` fixture to set `sys.argv` and `capsys` to capture output. Adjust to your script’s behavior (for instance, if `main()` calls `sys.exit()`, you might catch SystemExit exception instead).

  * **End-to-end invocation:** For more confidence, you can test the installed console script using `subprocess`. Pytest allows invoking commands via `pytest.parametrize` with `capsys` or using Python’s `subprocess.run`. For example:

    ```python
    import subprocess, sys
    def test_cli_script_execution():
        # Ensure the script runs and returns expected output
        completed = subprocess.run([sys.executable, "-m", "avena_commons.cli", "--help"], capture_output=True, text=True)
        assert completed.returncode == 0
        assert "Usage:" in completed.stdout
    ```

    This runs the module as a script (which is equivalent to the console entry point) and checks that help text is shown. You can also test the console entry point directly by invoking the `avena-tool` command if the package is installed in the test environment. In a tox or CI setup, one could install the distribution and run the command.

  * **Simulate entry point call:** You can also directly call the entry point function via import as the pyproject does. For example:

    ```python
    from avena_commons.cli import main as cli_main
    # Call the main function with arguments
    result = cli_main(["--option", "value"])
    ```

    This requires designing `main()` to accept an argument list. Many CLI tools pattern their main function to accept `argv=None` and default to `sys.argv` internally, so you can pass a custom list when testing.

* **Documenting scripts:** If you add a new script, update the README or usage documentation. Provide examples of how to use the command, and list it under any reference of available CLI tools. This helps users discover the functionality. Also, include help text in the script itself (if using argparse, ensure `parser.description` and argument `help` strings are set meaningfully).

* **Entry point naming conventions:** Use short, lowercase command names, with hyphens if needed, and avoid clashing with existing system commands. For instance, prefer `avena-download` over a generic name like `download` which might conflict. The prefix `avena` (or similar) can help namespace the tools. Since these scripts are user-facing, be mindful of the name and try to make it mnemonic.

* **Testing multiple scenarios:** Ensure your script handles various scenarios: valid inputs, invalid inputs (and shows errors), edge cases, etc. If the script interacts with external services or files, simulate those in tests (you might use temporary files via pytest’s `tmp_path` fixture, or requests-mock for HTTP calls, etc., depending on what the script does). The goal is to have your console entry points as robust and tested as the rest of the library code.

* **Avoid side effects on import:** When writing the module that contains the script (e.g., `cli.py`), avoid executing code on import (aside from setting up parser definitions). The `main()` function should encapsulate the execution. This ensures that simply importing `avena_commons.cli` (or any module) during tests doesn’t unexpectedly perform I/O or other actions. It also aligns with entry point behavior, which expects to call a function to run.

By following these steps, any new **project.scripts** entry defined in pyproject.toml will be properly integrated and verified. In summary: **declare the entry point in pyproject.toml, implement the corresponding function, and write tests to validate it works as intended**. This provides users with a reliable CLI tool and maintains our quality standards.

## 7. AI-Specific Contribution Instructions

When using AI to assist in code contributions, the following additional guidelines ensure that AI-generated code aligns with human-quality standards:

* **Adherence to all above rules:** The AI should be instructed to follow **all the guidelines in sections 1-6**. This includes project structure, testing, coding style, and configuration conventions. AI-generated code must pass the same checks as human-written code. For instance, if the AI creates a new module, it must also create a corresponding test module with comprehensive tests, maintain 90%+ coverage, and include proper docstrings and type hints. Remind the AI of the linting standards (Ruff rules, PEP 8) so it formats code correctly (e.g., spaces around operators, correct naming). Consistency is key – a reader should not be able to tell which code was AI-generated vs. human-written because both meet the same quality bar.

* **Small, focused commits:** Aim to have the AI produce changes in small logical units. It’s better to have one feature or fix per commit/PR with well-structured code and tests, than a giant AI-generated dump of code. This makes review and integration easier. Encourage the AI to **iteratively refine** the code: first draft a solution, then run tests/linters, then adjust. If an AI tool is integrated into your workflow (like GitHub Copilot or an internal AI assistant), use it to write boilerplate or suggest improvements, but always review the suggestions for compliance with our guidelines.

* **Code review and self-check:** Even if the code is generated by AI, it **must be reviewed by a human or a rigorous automated process**. The AI should double-check its output. For example, after generating a function, the AI (or the user guiding it) should:

  * Ensure the function name and signature make sense.
  * Verify that edge cases are handled (maybe prompt the AI: "What if X happens?").
  * Confirm that the code complexity is reasonable (no obviously inefficient loops or recursion without base case, etc.).
  * Check that variables and functions are named clearly and consistently.
  * Run the tests (if possible) to see that everything passes, or have the AI generate tests if some are missing.

  The AI can be guided to "run" through mental execution of the code for simple cases to validate logic. Additionally, after code generation, running actual test suite (by the developer) is critical. If tests fail or coverage is low, feed that information back to the AI to fix issues.

* **Documentation and explanations:** AI-generated code contributions should come with appropriate documentation. That means:

  * **Docstrings** as described earlier (the AI should generate a docstring for each public function/class it writes, summarizing its behavior).
  * **Comments** where needed to clarify complex logic. If the AI writes an algorithm, it should include a comment block explaining the approach in plain English for future maintainers.
  * **Commit message or PR description:** When you create a commit/PR with AI-generated code, write a clear description of what the change does and why. If the AI can help draft this, ensure it’s accurate and not too verbose. It should mention if the code was AI-assisted (for transparency) and highlight any important considerations (e.g., "Added new function to calculate X. Uses algorithm from \[reference]. 90% test coverage achieved.").

* **Reusability and modularity:** Guide the AI to write code that is modular and reusable. For example, if adding a new feature, it might be tempting for an AI to write one giant function. Instead, have it break the solution into smaller helper functions or classes if appropriate. Each function should have a single responsibility (as per clean code principles). This not only makes the code easier to test (unit tests for each piece) but also easier to maintain. Encourage the AI to avoid duplicating code – if similar logic exists elsewhere in `avena_commons`, it should call that or refactor common parts. Don’t let the AI reinvent the wheel if the functionality can tie into existing utilities.

* **Performance considerations:** While the primary goal is correctness and clarity, AI contributions should also consider performance. The AI might not inherently know the efficiency of certain operations, so you should prompt it to consider big-O complexity or memory usage for significant code (e.g., if processing large datasets, ensure it uses efficient data structures). If the AI suggests a brute-force solution where a more optimized approach is known, guide it to improve (maybe provide hints or the name of an algorithm). Always test performance-critical code with sample inputs (and include such tests if possible, e.g., a test that runs the function on a small scale input to ensure it finishes quickly).

* **Security and validity checks:** Make sure AI-generated code doesn’t introduce security issues or handle inputs unsafely. For example, if dealing with file paths, the AI should consider using safe operations (like avoiding `os.system` calls with unsanitized input, etc.). If input data can be of the wrong type or range, the code should validate and either sanitize or raise a clear exception (and tests should cover these cases). Prompt the AI to include error handling as part of the implementation. For instance, "Include a check that the input is not null and of the correct type, raising ValueError if not."

* **Consistency with project design:** If the project has certain patterns or design philosophies, ensure the AI follows them. For example, if all database interactions go through a specific module, an AI contribution shouldn’t directly open new database connections elsewhere – it should use the established utilities. Keep the **architecture coherent**. If unsure, consult existing code for examples and maybe feed those to the AI as context or examples ("Here is how logging is done in other modules... follow a similar approach").

* **Testing AI-generated code:** As emphasized, tests are non-negotiable. When the AI writes new code, have it also generate tests for that code. The tests should cover normal cases, boundary conditions, and error conditions. After generating tests, manually review them to ensure they truly verify the code’s behavior (sometimes AI might write superficial tests). Running the tests will further validate both code and tests. If a bug is found, correct the code and update tests or vice versa.

* **No sensitive data or licensing issues:** Ensure the AI does not introduce any code from external sources that might violate licenses. All contributions should either be original or derived from permissibly licensed snippets. Since this is a commons library, keep everything compatible with its license (likely MIT or Apache; check pyproject or LICENSE file). Don’t let the AI copy large chunks from Stack Overflow or GitHub unless it’s a well-known algorithm under compatible license. Always prefer the AI’s own synthesized solution or refer to standard library usage.

* **Continuous learning:** If the AI makes a mistake (like a failing test or lint error), treat it as you would a junior developer: provide feedback and let it attempt a fix. For example, if Ruff flags a line too long or an unused variable, point that out to the AI so it can correct it. Over time, the AI should internalize these standards (if it’s an interactive session). Keeping a prompt or checklist of our specific guidelines handy for the AI can help it to self-review before finalizing the code (e.g., "Check that the code follows PEP8: any long lines? any bad names? Does each function have a docstring?").

In essence, **AI contributions must meet the same quality standards as human contributions**. Use the AI as a tool to enhance productivity (generate boilerplate, suggest algorithms, etc.), but always enforce the project’s best practices on the output. The maintainers will do a thorough review, so it’s best if the AI (with your guidance) preempts any issues by following this instruction set closely. By doing so, AI-generated modules or functions will be well-structured, well-tested, and easy to maintain, fitting seamlessly into the Avena Commons project.

**Sources:**

* Python Packaging Guide – Structuring Projects and Tests
* Pytest Documentation – Test discovery & best practices
* Pytest with Eric – Test structure mirroring application code
* Pytest Docs – Using fixtures in tests
* Coverage Best Practices – Pytest-cov usage
* PEP 8 Style Guide – Importance of readability & consistency
* Real Python – PEP 8 naming conventions and line length guidelines
* Ruff Documentation – Configuration in pyproject.toml
* PEP 621 – Declaring dependencies and optional dependencies in pyproject
* Python Packaging Guide – Entry points for console scripts
* PEP 257 – Docstring conventions for functions and classes
