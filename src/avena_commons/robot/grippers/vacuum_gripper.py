"""Vacuum gripper implementation with autonomous state monitoring.

Implements a vacuum-based gripper with pressure monitoring, watchdog logic,
and event-driven control. Maintains internal state and autonomously monitors
vacuum status via robot_state_pkg.
"""

import time
from typing import Any, Dict, List, Optional

from pydantic import Field

from avena_commons.util.logger import debug, error, warning

from .base import BaseGripper, EventResult, GripperError, IOMapping, RobotToolConfig


class PressureCalculator:
    """Kalkulator ciśnienia z napięcia z filtrem mediany.

    Konwertuje napięcie wejściowe (0-10V) na ciśnienie w kPa z użyciem
    bufora kołowego i mediany dla stabilizacji odczytów.

    Attributes:
        adc_resolution (float): Rozdzielczość ADC (domyślnie 4096 dla 12-bit).
        adc_supply_voltage (float): Napięcie zasilania ADC w V (domyślnie 4.5V).
        buffer_size (int): Rozmiar bufora mediany (domyślnie 100 próbek).
        kpa_low (float): Dolna granica zakresu ciśnienia w kPa (domyślnie -100.0).
        kpa_high (float): Górna granica zakresu ciśnienia w kPa (domyślnie 0.0).
    """

    def __init__(
        self,
        adc_resolution: float = 4096.0,
        adc_supply_voltage: float = 4.5,
        buffer_size: int = 100,
        kpa_low: float = -100.0,
        kpa_high: float = 0.0,
    ) -> None:
        """Inicjalizuje kalkulator ciśnienia.

        Args:
            adc_resolution: Rozdzielczość ADC (np. 4096 dla 12-bit).
            adc_supply_voltage: Napięcie zasilania ADC w V.
            buffer_size: Rozmiar bufora dla filtru mediany.
            kpa_low: Dolna granica ciśnienia w kPa (podciśnienie).
            kpa_high: Górna granica ciśnienia w kPa.

        Raises:
            ValueError: Gdy parametry są poza dopuszczalnym zakresem.
        """
        if adc_resolution <= 0:
            raise ValueError("adc_resolution must be positive")
        if adc_supply_voltage <= 0:
            raise ValueError("adc_supply_voltage must be positive")
        if buffer_size <= 0:
            raise ValueError("buffer_size must be positive")
        if kpa_low >= kpa_high:
            raise ValueError("kpa_low must be less than kpa_high")

        self._adc_resolution = float(adc_resolution)
        self._adc_supply_voltage = float(adc_supply_voltage)
        self._buffer_size = int(buffer_size)
        self._kpa_low = float(kpa_low)
        self._kpa_high = float(kpa_high)

        self._voltage_buffer: List[int] = []
        self._buffer_index: int = 0

    def reset(self) -> None:
        """Czyści bufor mediany.

        Używane przy zmianie stanu systemu lub zmianie chwytaka,
        aby odrzucić stare próbki.
        """
        self._voltage_buffer.clear()
        self._buffer_index = 0

    def calculate_pressure(self, voltage_in: float) -> float:
        """Oblicza ciśnienie w kPa z napięcia wejściowego.

        Proces konwersji:
        1) Ograniczenie do zakresu ADC (0 - adc_supply_voltage)
        2) Konwersja do wartości ADC (0 - adc_resolution-1)
        3) Bufor kołowy z medianą (stabilizacja)
        4) Skalowanie do kPa

        Args:
            voltage_in: Napięcie wejściowe w zakresie 0-10V.

        Returns:
            float: Ciśnienie w kPa (ujemne dla podciśnienia).
                  Zakres: [kpa_low, kpa_high], domyślnie [-100.0, 0.0].
                  0V → -100.0 kPa (pełne podciśnienie)
                  max voltage (4.5V) → 0.0 kPa (ciśnienie atmosferyczne)

        Raises:
            ValueError: Nigdy - wartości są automatycznie ograniczane do zakresu.
        """
        # print(f"Input voltage: {voltage_in}")  # Debug print
        # 1) Clamp do zakresu ADC % -> V (0..10 V)
        p = 0.0 if voltage_in < 0.0 else (110.0 if voltage_in > 110.0 else voltage_in)
        v_adc = (p / 100.0) * 10.0  # Przeskalowanie 0-110% na 0-10V
        # print(f"ADC voltage (clamped to supply): {v_adc}")  # Debug print

        # 2) Konwersja V -> ADC counts (0 - adc_resolution-1)
        adc_count = int(
            (v_adc / self._adc_supply_voltage) * (self._adc_resolution - 1.0)
        )
        if adc_count < 0:
            adc_count = 0
        if adc_count >= int(self._adc_resolution - 1.0):
            adc_count = int(self._adc_resolution - 1.0)

        # print(f"ADC count: {adc_count}")  # Debug print

        # 3) Bufor kołowy + mediana
        if len(self._voltage_buffer) < self._buffer_size:
            self._voltage_buffer.append(adc_count)
        else:
            self._voltage_buffer[self._buffer_index] = adc_count
            self._buffer_index = (self._buffer_index + 1) % self._buffer_size

        # Mediana z posortowanego bufora
        sorted_buffer = sorted(self._voltage_buffer)
        median_index = len(sorted_buffer) // 2
        adc_median = sorted_buffer[median_index]
        # print(f"ADC median: {adc_median}")  # Debug print

        # 4) Skalowanie ADC -> kPa (jak w oryginale)
        # 0 ADC -> -100 kPa (full vacuum), max ADC -> 0 kPa (atmospheric)
        scale = (self._kpa_high - self._kpa_low) / (
            self._adc_resolution - 1.0
        )  # = (0 - (-100)) / 4095 = 100/4095
        pressure_kpa = (
            scale * adc_median + self._kpa_low
        )  # = (100/4095) * adc_median + (-100)
        # print(f"Calculated pressure (kPa): {pressure_kpa}")  # Debug print

        return float(pressure_kpa)

    @property
    def buffer_fill_level(self) -> float:
        """Zwraca stopień zapełnienia bufora jako procent.

        Returns:
            float: Procent zapełnienia bufora (0.0 - 100.0).
        """
        return (len(self._voltage_buffer) / self._buffer_size) * 100.0

    @property
    def is_buffer_full(self) -> bool:
        """Sprawdza czy bufor jest pełny.

        Returns:
            bool: True jeśli bufor zawiera buffer_size próbek.
        """
        return len(self._voltage_buffer) >= self._buffer_size


class VacuumGripperConfig(RobotToolConfig):
    """Configuration for vacuum gripper with pressure monitoring.

    Extends RobotToolConfig with vacuum-specific parameters for pressure
    thresholds, timing, and hardware calibration.
    """

    io_mapping: IOMapping = Field(
        ..., description="Mapping of logical IO names to physical pins"
    )

    pressure_threshold_kpa: float = Field(
        default=-10.0,
        description="Pressure threshold for holding detection in kPa (negative for vacuum)",
    )

    hold_debounce_ms: int = Field(
        default=250,
        description="Debounce time in milliseconds for state change confirmation",
    )

    adc_resolution: float = Field(
        default=4096.0,
        description="ADC resolution for pressure sensor (e.g., 4096 for 12-bit)",
    )

    adc_supply_voltage: float = Field(
        default=4.5, description="ADC supply voltage in volts"
    )

    pressure_buffer_size: int = Field(
        default=100, description="Size of median filter buffer for pressure readings"
    )

    light_voltage_range: tuple[float, float] = Field(
        default=(43.0, 0.0),
        description="Voltage range for light control (min_voltage, max_voltage) in volts. 100% intensity = min_voltage, 0% intensity = max_voltage.",
    )


class VacuumGripper(BaseGripper):
    """Vacuum gripper with autonomous pressure monitoring and watchdog.

    Implements event-driven vacuum control with internal state tracking,
    pressure calculation, and 4-case watchdog logic for vacuum loss detection.

    Attributes:
        _robot: Robot instance for direct robot_state_pkg access.
        _config: VacuumGripperConfig with all gripper parameters.
        _io_manager: IOManager for hardware communication.
        _pressure_calculator: PressureCalculator for voltage->kPa conversion.
        _pump_active: Current pump state (on/off).
        _pump_holding: Whether gripper is confirmed holding vacuum.
        _pump_holding_timer: Timer for debouncing state changes (ms).
        _light_active: Current light state.
        _current_pressure_kpa: Last calculated pressure value.
    """

    def __init__(self, robot, config: VacuumGripperConfig, message_logger=None):
        """Initialize vacuum gripper.

        Args:
            robot: Robot instance with tool IO methods and robot_state_pkg.
            config: VacuumGripperConfig with all parameters.
            message_logger: Optional logger for debug/error messages.
        """
        super().__init__(robot, config, message_logger)

        # Initialize pressure calculator
        self._pressure_calculator = PressureCalculator(
            adc_resolution=config.adc_resolution,
            adc_supply_voltage=config.adc_supply_voltage,
            buffer_size=config.pressure_buffer_size,
            kpa_low=-100.0,
            kpa_high=0.0,
        )

        # Internal state tracking
        self._pump_active: bool = False
        self._pump_holding: bool = False
        self._pump_holding_timer: Optional[float] = None
        self._light_active: bool = False
        self._last_pressure_kpa: float = 0.0  # Updated by update_io_state()
        self._last_holding: bool = False  # Updated by update_io_state()

        # Context tracking for callbacks
        self._current_path = None
        self._watchdog_override: bool = False
        self._testing_move: bool = False

    def get_robot_config(self) -> RobotToolConfig:
        """Return robot tool configuration.

        Returns:
            RobotToolConfig with tool parameters for robot initialization.
        """
        return RobotToolConfig(
            tool_id=self._config.tool_id,
            tool_coordinates=self._config.tool_coordinates,
            tool_type=self._config.tool_type,
            tool_installation=self._config.tool_installation,
            weight=self._config.weight,
            mass_coord=self._config.mass_coord,
        )

    def get_io_mapping(self) -> IOMapping:
        """Return IO mapping configuration.

        Returns:
            IOMapping with logical name to pin mappings.
        """
        return self._config.io_mapping

    def get_supported_events(self) -> set[str]:
        """Return set of event types supported by this gripper.

        Returns:
            Set of event type strings that this gripper can process.
        """
        return {"pump_on", "pump_off", "light_on", "light_off"}

    def on_initialize(self) -> None:
        """Handle gripper initialization - called after robot initialization.

        Currently does nothing, but can be used for future setup.
        """
        # Enable than disable pump to ensure known state
        try:
            self._io_manager.set_do("pump", True)
            if self._message_logger:
                debug("Pump set to ON state on enable", self._message_logger)
        except Exception as e:
            if self._message_logger:
                warning(
                    f"Failed to set pump to ON state on enable: {e}",
                    self._message_logger,
                )

        time.sleep(1)  # Wait 1 second to ensure pump state is set
        confirmation = self._io_manager.get_di("pump")  # Read back to ensure state

        try:
            self._io_manager.set_do("pump", False)
            if self._message_logger:
                debug("Pump set to OFF state on enable", self._message_logger)
        except Exception as e:
            if self._message_logger:
                warning(
                    f"Failed to set pump to OFF state on enable: {e}",
                    self._message_logger,
                )

        if confirmation:
            if self._message_logger:
                debug("Vacuum gripper initialized", self._message_logger)
        else:
            if self._message_logger:
                warning(
                    "Vacuum gripper pump state confirmation failed on enable",
                    self._message_logger,
                )
            raise GripperError(
                "VacuumGripper",
                "on_initialize",
                "Pump state confirmation failed on enable",
            )

    def on_enable(self) -> None:
        """Handle gripper enable - called after robot initialization.

        Enables light control relay to allow light intensity control.
        The relay is a digital output that must be ON to enable light control.
        Does NOT turn on the light itself - that's done via light_on event.
        """
        if self._message_logger:
            debug("Vacuum gripper enabled", self._message_logger)

        # Reset all state
        self._pump_active = False
        self._pump_holding = False
        self._pump_holding_timer = None
        self._light_active = False
        self._current_pressure_kpa = 0.0

        # Enable light control relay (digital output)
        # This relay must be ON to allow analog light intensity control
        try:
            # Check if light_control relay is mapped in IO
            if "light_control" in self._config.io_mapping.digital_outputs:
                self._io_manager.set_do("light_control", True)
                if self._message_logger:
                    debug(
                        "Light control relay enabled (light control now possible)",
                        self._message_logger,
                    )
            else:
                if self._message_logger:
                    debug(
                        "No light_control relay configured in IO mapping",
                        self._message_logger,
                    )
        except Exception as e:
            if self._message_logger:
                warning(
                    f"Failed to enable light control relay: {e}", self._message_logger
                )

    def on_disable(self) -> None:
        """Handle gripper disable - called before robot shutdown.

        Turns off light (if active) and disables light control relay.
        Also turns off pump to ensure safe state.
        """
        if self._message_logger:
            debug("Vacuum gripper disabling", self._message_logger)

        # Turn off light if active (set intensity to 0)
        if self._light_active:
            min_v, max_v = self._config.light_voltage_range
            try:
                self._io_manager.set_ao("light", min_v)
                self._light_active = False
                if self._message_logger:
                    debug("Light turned off during disable", self._message_logger)
            except Exception as e:
                if self._message_logger:
                    warning(
                        f"Failed to turn off light during disable: {e}",
                        self._message_logger,
                    )

        # Disable light control relay (digital output)
        try:
            if "light_control" in self._config.io_mapping.digital_outputs:
                self._io_manager.set_do("light_control", False)
                if self._message_logger:
                    debug("Light control relay disabled", self._message_logger)
        except Exception as e:
            if self._message_logger:
                warning(
                    f"Failed to disable light control relay: {e}", self._message_logger
                )

    def on_path_start(self, path) -> None:
        """Handle path start - track context for watchdog logic.

        Args:
            path: Path object with execution parameters.
        """
        self._current_path = path
        self._testing_move = getattr(path, "testing_move", False)

        # Set watchdog override for testing moves
        if self._testing_move:
            self._watchdog_override = True
            if self._message_logger:
                debug(
                    "Testing move detected - watchdog override enabled",
                    self._message_logger,
                )
        else:
            self._watchdog_override = False

    def on_waypoint_reached(self, waypoint) -> None:
        """Handle waypoint reached - check for watchdog override flag.

        Args:
            waypoint: Waypoint object that was reached.
        """
        # Check if waypoint has watchdog_override flag
        if hasattr(waypoint, "watchdog_override") and waypoint.watchdog_override:
            self._watchdog_override = True
            if self._message_logger:
                debug(f"Waypoint watchdog override enabled", self._message_logger)

    def on_path_end(self, path) -> None:
        """Handle path end - reset context.

        Args:
            path: Path object that completed.
        """
        self._current_path = None
        self._watchdog_override = False
        self._testing_move = False

    def validate_path_completion(self, path) -> bool:
        """Validate vacuum gripper state after path completion.

        For testing_move paths, validates that gripper is holding vacuum.

        Args:
            path: Path object to validate.

        Returns:
            bool: True if path completion is valid, False otherwise.
        """
        testing_move = getattr(path, "testing_move", False)

        if testing_move:
            # For testing moves, verify gripper is holding
            if not self._pump_holding:
                return False

            if self._message_logger:
                debug(
                    f"Testing move validation passed - holding at {self._last_pressure_kpa:.2f} kPa",
                    self._message_logger,
                )

        return True

    def update_io_state(self, io_state: dict) -> None:
        """Update gripper internal state from robot IO state dict.

        Reads pressure sensor, calculates pressure, and updates internal state variables.
        This is the ONLY place where IO is read.

        Args:
            io_state: Dict with IO fields from robot_state_pkg (tl_dgt_output_l, tl_dgt_input_l, tl_anglog_input).
        """
        # Update IOManager with fresh IO state
        self._io_manager.update_io_state(io_state)

        # Read pressure sensor voltage via IOManager (which now uses io_state)
        try:
            pressure_voltage = self._io_manager.get_ai("pressure_sensor")

            # Calculate pressure in kPa
            self._last_pressure_kpa = self._pressure_calculator.calculate_pressure(
                pressure_voltage
            )

            # Determine if pump is holding based on pressure threshold
            self._last_holding = (
                self._last_pressure_kpa < self._config.pressure_threshold_kpa
            )

        except Exception as e:
            if self._message_logger:
                error(
                    f"Error updating gripper IO state: {str(e)}", self._message_logger
                )
            # On error, maintain last known values

    def process_event(self, event) -> EventResult:
        """Process gripper event and execute corresponding IO action.

        Handles pump_on, pump_off, light_on, light_off events.
        Does NOT include watchdog logic - only executes IO operations.

        Args:
            event: Event object with event_type and optional data.

        Returns:
            EventResult with success status and updated state data.
        """
        event_type = event.event_type
        event_data = event.data

        try:
            if event_type == "pump_on":
                # Turn on vacuum pump
                self._io_manager.set_do("pump", True)
                self._pump_active = True

                if self._message_logger:
                    debug("Vacuum pump turned ON", self._message_logger)

                return EventResult(
                    result="success",
                    data={"pump_active": True, "add_to_processing": False},
                )

            elif event_type == "pump_off":
                # Turn off vacuum pump and reset pressure buffer
                self._io_manager.set_do("pump", False)
                self._pump_active = False
                self._pump_holding = False
                self._pump_holding_timer = None
                self._pressure_calculator.reset()

                if self._message_logger:
                    debug(
                        "Vacuum pump turned OFF, reset holding state",
                        self._message_logger,
                    )

                return EventResult(
                    result="success",
                    data={
                        "pump_active": False,
                        "holding": False,
                        "add_to_processing": False,
                    },
                )

            elif event_type == "light_on":
                # Turn on light with specified intensity
                intensity_percent = event_data.get("intensity", 100)

                if not (0 <= intensity_percent <= 100):
                    raise ValueError(
                        f"Gripper light intensity must be between 0 and 100, got: {intensity_percent}"
                    )

                # Get voltage range from config. Note the inverted logic:
                # 100% intensity -> min_voltage (e.g., 0.0V for max brightness)
                # 0% intensity -> max_voltage (e.g., 4.3V for off)
                min_v, max_v = self._config.light_voltage_range

                if intensity_percent == 0:
                    # Special case: 0% intensity means turn off light
                    ao_value = min_v
                elif intensity_percent == 100:
                    ao_value = max_v
                else:
                    ao_value = int(
                        round(
                            min_v - (intensity_percent / 100) * (min_v - max_v),
                            0,
                        )
                    )

                self._io_manager.set_ao("light", ao_value)
                self._light_active = True

                if self._message_logger:
                    debug(
                        f"Light turned ON at {intensity_percent}% intensity "
                        f"(AO value: {ao_value:.1f})",
                        self._message_logger,
                    )

                return EventResult(
                    result="success",
                    data={
                        "light_active": True,
                        "intensity_percent": intensity_percent,
                        "voltage": ao_value,
                        "add_to_processing": False,
                    },
                )

            elif event_type == "light_off":
                min_v, max_v = self._config.light_voltage_range
                # Turn off light
                self._io_manager.set_ao("light", min_v)
                self._light_active = False

                if self._message_logger:
                    debug("Light turned OFF", self._message_logger)

                return EventResult(
                    result="success",
                    data={"light_active": False, "add_to_processing": False},
                )

            else:
                # Unsupported event type
                return EventResult(
                    result="failure",
                    data={},
                    error_message=f"Unsupported event type: {event_type}",
                )

        except Exception as e:
            if self._message_logger:
                error(
                    f"Error processing event {event_type}: {str(e)}",
                    self._message_logger,
                )

            return EventResult(
                result="failure",
                data={},
                error_message=f"Event processing failed: {str(e)}",
            )

    def get_state(self) -> Dict[str, Any]:
        """Get current gripper state from last update_io_state() call.

        Returns processed state without reading IO hardware.
        Uses data updated by most recent update_io_state() call.

        Returns:
            Dict with keys: pump_active, pressure_kpa, holding, light_active, pressure_buffer_full.
        """
        return {
            "pump_active": self._pump_active,
            "pressure_kpa": self._last_pressure_kpa,
            "holding": self._last_holding,
            "light_active": self._light_active,
            "pressure_buffer_full": self._pressure_calculator.is_buffer_full,
        }

    def check_errors(self) -> Optional[GripperError]:
        """Check for gripper errors using 4-case watchdog logic.

        Implements autonomous vacuum monitoring:
        - Case 1: Pump turned off → Reset holding state
        - Case 2: Watchdog override active → Ignore vacuum loss (but stop if not testing)
        - Case 3: Vacuum lost while holding (no override) → WATCHDOG_ERROR
        - Case 4: State transition (debouncing) → Confirm stable state change

        Uses internal context from lifecycle callbacks and data from update_io_state().

        Returns:
            GripperError if unrecoverable error detected, None otherwise.
        """
        # Use state from last update_io_state() call - NO IO reads here
        current_holding = self._last_holding
        testing_move = self._testing_move
        watchdog_override = self._watchdog_override

        # Case 1: Pump was turned off - reset holding state
        if not self._pump_active and self._pump_holding:
            self._pump_holding = False
            self._pump_holding_timer = None

            if self._message_logger:
                debug("Pump turned off, reset holding state", self._message_logger)

            return None

        # Case 2: Pump holding with watchdog override active
        elif watchdog_override and self._pump_holding and not current_holding:
            self._pump_holding = False
            self._pump_holding_timer = None

            if self._message_logger:
                if not testing_move:
                    debug(
                        "Pump lost vacuum but watchdog override active (not in testing move)",
                        self._message_logger,
                    )
                else:
                    debug(
                        "Gripper watchdog override active, ignoring non-holding state",
                        self._message_logger,
                    )

            return None

        # Case 3: Pump should be holding but isn't (watchdog error)
        elif not watchdog_override and self._pump_holding and not current_holding:
            self._pump_holding_timer = None
            self._pump_holding = False

            error_msg = f"Pump lost vacuum while holding! Current pressure: {self._last_pressure_kpa:.2f} kPa"

            if self._message_logger:
                error(error_msg, self._message_logger)

            return GripperError(
                error_type="watchdog_error", message=error_msg, recoverable=False
            )

        # Case 4: State transition handling - pump just started or stopped holding
        elif current_holding and not self._pump_holding:
            current_time = time.perf_counter() * 1000  # Current time in milliseconds

            # Begin timer if this is the first detection of a potential state change
            if self._pump_holding_timer is None:
                self._pump_holding_timer = current_time

                if self._message_logger:
                    debug(
                        f"Potential pump state change detected: holding={current_holding}, pressure={self._last_pressure_kpa:.2f}",
                        self._message_logger,
                    )

            # Check if state has been stable for threshold period
            elif (
                current_time - self._pump_holding_timer
            ) >= self._config.hold_debounce_ms:
                if current_holding:
                    # Confirmed pump is now holding
                    self._pump_holding = True

                    if self._message_logger:
                        debug(
                            f"Pump state change confirmed - now holding with pressure: {self._last_pressure_kpa:.2f} kPa",
                            self._message_logger,
                        )
                else:
                    # Confirmed pump is no longer holding
                    self._pump_holding = False

                    if self._message_logger:
                        debug(
                            f"Pump state change confirmed - no longer holding, pressure: {self._last_pressure_kpa:.2f} kPa",
                            self._message_logger,
                        )

                self._pump_holding_timer = None

        else:
            # Reset timer if state matches again before threshold
            self._pump_holding_timer = None

        return None
