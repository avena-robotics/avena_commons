import threading
import time
import traceback

from avena_commons.util.logger import MessageLogger, debug, error, info, warning


class URM14:
    """Controller for DFRobot URM14 RS485 Precision Ultrasonic Sensor"""

    # Register indices
    PID = 0  # Product ID
    VID = 1  # Version ID
    ADDR = 2  # Device address
    COM_BAUDRATE = 3  # Communication baud rate
    COM_PARITY_STOP = 4  # Communication parity and stop bits
    DISTANCE = 5  # Distance measurement
    INTERNAL_TEMPERATURE = 6  # Internal temperature
    EXTERNAL_TEMPERATURE = 7  # External temperature
    CONTROL = 8  # Control register
    NOISE = 9  # Noise level

    # Control register bits
    TEMP_CPT_SEL_BIT = 0x00  # Temperature compensation selection bit
    TEMP_CPT_ENABLE_BIT = 0x00 << 1  # Temperature compensation enable bit
    MEASURE_MODE_BIT = 0x00 << 2  # Measurement mode bit
    MEASURE_TRIG_BIT = 0x00 << 3  # Measurement trigger bit

    # Baudrate mapping
    BAUDRATE_MAP = {
        1: 2400,
        2: 4800,
        3: 9600,
        4: 14400,
        5: 19200,
        6: 38400,
        7: 57600,
        8: 115200,
    }

    # Default settings
    DEFAULT_SLAVE_ADDR = 0x0C  # Default device address (12)
    PUBLIC_ADDR = 0x00  # Public address for broadcasting
    DEFAULT_BAUDRATE = 19200  # Default baudrate

    def __init__(
        self,
        device_name: str,
        bus,
        address=DEFAULT_SLAVE_ADDR,
        message_logger: MessageLogger | None = None,
        debug=True,
    ):
        """Initialize the URM14 sensor controller

        Args:
            bus (ModbusRTU): ModbusRTU bus instance
            address (int): Slave address of the device
            message_logger (MessageLogger): Logger for messaging
            debug (bool): Enable debug logging
        """
        try:
            self.message_logger = message_logger

            info(
                f"Initializing URM14 {device_name} at address {address}",
                message_logger=self.message_logger,
            )
            self.device_name = device_name
            self.bus = bus
            self.slave_addr = address
            self.__debug = debug

            # Initialize the sensor - ensure it's in a known state
            self._initialize_sensor()

            # Cache for distance readings
            self.distance_cache = None
            self.distance_cache_time = 0
            self.distance_cache_timeout = 0.05  # 50ms timeout for distance readings
            self.distance_lock = threading.Lock()

        except Exception as e:
            error(
                f"Error initializing URM14: {str(e)}",
                message_logger=self.message_logger,
            )
            error(traceback.format_exc(), message_logger=self.message_logger)

    def _initialize_sensor(self):
        """Initialize the sensor to ensure it's in the right mode"""
        try:
            # Check if we can communicate with the sensor first
            pid = self.read_register(self.PID)
            vid = self.read_register(self.VID)
            info(
                f"Connected to sensor - Product ID: {pid}, Version ID: {vid}",
                message_logger=self.message_logger,
            )

            # Set continuous measurement mode
            control = 0x0000
            self.write_register(self.CONTROL, control)
            info(
                f"Sensor initialized, control register: 0x{control:04X}",
                message_logger=self.message_logger,
            )

            # Allow sensor to initialize
            time.sleep(0.5)
        except Exception as e:
            warning(
                f"Failed to initialize sensor: {e}", message_logger=self.message_logger
            )

    def read_register(self, register):
        """Read a holding register from the device

        Args:
            register (int): Register address to read

        Returns:
            int: Register value
        """
        try:
            response = self.bus.read_holding_register(
                address=self.slave_addr, register=register
            )
            if (
                not response and response != 0
            ):  # Check if response is False (error) but allow 0 as valid value
                error(
                    f"Failed to read register {register}",
                    message_logger=self.message_logger,
                )
                raise Exception(f"Failed to read register {register}")
            return response
        except Exception as e:
            error(
                f"Error reading register {register}: {str(e)}",
                message_logger=self.message_logger,
            )
            raise

    def write_register(self, register, value):
        """Write to a holding register

        Args:
            register (int): Register address to write to
            value (int): Value to write

        Returns:
            bool: True if successful
        """
        try:
            response = self.bus.write_holding_register(
                address=self.slave_addr, register=register, value=value
            )
            if not response:
                error(
                    f"Failed to write register {register}",
                    message_logger=self.message_logger,
                )
                raise Exception(f"Failed to write register {register}")
            return True
        except Exception as e:
            error(
                f"Error writing register {register}: {str(e)}",
                message_logger=self.message_logger,
            )
            raise

    def read_distance(self):
        """Read distance measurement with caching

        Returns:
            float: Distance in mm
        """
        with self.distance_lock:
            current_time = time.time()
            # Check if cache is valid
            if (
                self.distance_cache is not None
                and (current_time - self.distance_cache_time)
                < self.distance_cache_timeout
            ):
                # Use cached value
                if self.__debug:
                    debug(
                        f"Using cached distance value: {self.distance_cache}",
                        message_logger=self.message_logger,
                    )
                return self.distance_cache

            # Cache expired or not set, perform actual read
            try:
                distance = self.read_register(self.DISTANCE)
                if self.__debug:
                    debug(
                        f"Updated distance cache with value: {distance}mm",
                        message_logger=self.message_logger,
                    )

                # Update cache
                self.distance_cache = distance
                self.distance_cache_time = current_time
                return distance
            except Exception as e:
                error(
                    f"Error reading distance: {str(e)}",
                    message_logger=self.message_logger,
                )
                return None

    def get_internal_temperature(self):
        """Read internal temperature

        Returns:
            float: Temperature in degrees Celsius
        """
        try:
            temp = self.read_register(self.INTERNAL_TEMPERATURE) / 10.0
            if self.__debug:
                debug(
                    f"Internal temperature: {temp}°C",
                    message_logger=self.message_logger,
                )
            return temp
        except Exception as e:
            error(
                f"Error reading internal temperature: {str(e)}",
                message_logger=self.message_logger,
            )
            return None

    def get_external_temperature(self):
        """Read external temperature

        Returns:
            float: Temperature in degrees Celsius
        """
        try:
            temp = self.read_register(self.EXTERNAL_TEMPERATURE) / 10.0
            if self.__debug:
                debug(
                    f"External temperature: {temp}°C",
                    message_logger=self.message_logger,
                )
            return temp
        except Exception as e:
            error(
                f"Error reading external temperature: {str(e)}",
                message_logger=self.message_logger,
            )
            return None

    def get_noise(self):
        """Read noise level

        Returns:
            int: Noise level
        """
        try:
            noise = self.read_register(self.NOISE)
            if self.__debug:
                debug(f"Noise level: {noise}", message_logger=self.message_logger)
            return noise
        except Exception as e:
            error(
                f"Error reading noise level: {str(e)}",
                message_logger=self.message_logger,
            )
            return None

    def get_control_register(self):
        """Read control register

        Returns:
            int: Control register value
        """
        try:
            control = self.read_register(self.CONTROL)
            if self.__debug:
                debug(
                    f"Control register: 0x{control:04X}",
                    message_logger=self.message_logger,
                )
            return control
        except Exception as e:
            error(
                f"Error reading control register: {str(e)}",
                message_logger=self.message_logger,
            )
            return None

    def set_control_register(self, value):
        """Set control register

        Args:
            value (int): Control register value

        Returns:
            bool: True if successful
        """
        try:
            result = self.write_register(self.CONTROL, value)
            if self.__debug:
                debug(
                    f"Control register set to: 0x{value:04X}",
                    message_logger=self.message_logger,
                )
            return result
        except Exception as e:
            error(
                f"Error setting control register: {str(e)}",
                message_logger=self.message_logger,
            )
            return False

    def set_measurement_mode(self, continuous=True):
        """Set measurement mode

        Args:
            continuous (bool): True for continuous measurement, False for trigger mode

        Returns:
            bool: True if successful
        """
        try:
            control = self.get_control_register()
            if continuous:
                control |= self.MEASURE_MODE_BIT  # Set the bit
            else:
                control &= ~self.MEASURE_MODE_BIT  # Clear the bit
            result = self.set_control_register(control)
            if self.__debug:
                debug(
                    f"Measurement mode set to {'continuous' if continuous else 'trigger'}",
                    message_logger=self.message_logger,
                )
            return result
        except Exception as e:
            error(
                f"Error setting measurement mode: {str(e)}",
                message_logger=self.message_logger,
            )
            return False

    def trigger_measurement(self):
        """Trigger a single measurement in trigger mode

        Returns:
            bool: True if successful
        """
        try:
            control = self.get_control_register()
            # Set trigger bit
            control |= self.MEASURE_TRIG_BIT
            result = self.set_control_register(control)
            # Wait for measurement to complete
            time.sleep(0.2)
            if self.__debug:
                debug(f"Measurement triggered", message_logger=self.message_logger)
            return result
        except Exception as e:
            error(
                f"Error triggering measurement: {str(e)}",
                message_logger=self.message_logger,
            )
            return False

    def set_temperature_compensation(self, external=False, enable=True):
        """Configure temperature compensation

        Args:
            external (bool): True to use external temperature, False for internal
            enable (bool): True to enable temperature compensation, False to disable

        Returns:
            bool: True if successful
        """
        try:
            control = self.get_control_register()

            # Set temperature source bit
            if external:
                control |= self.TEMP_CPT_SEL_BIT  # Set for external
            else:
                control &= ~self.TEMP_CPT_SEL_BIT  # Clear for internal

            # Set temperature compensation enable bit
            if enable:
                control |= self.TEMP_CPT_ENABLE_BIT  # Set to enable
            else:
                control &= ~self.TEMP_CPT_ENABLE_BIT  # Clear to disable

            result = self.set_control_register(control)
            if self.__debug:
                debug(
                    f"Temperature compensation set to: source={'external' if external else 'internal'}, enabled={enable}",
                    message_logger=self.message_logger,
                )
            return result
        except Exception as e:
            error(
                f"Error setting temperature compensation: {str(e)}",
                message_logger=self.message_logger,
            )
            return False

    def change_address(self, new_address):
        """Change the slave address of the device

        Args:
            new_address (int): New slave address (1-247)

        Returns:
            bool: True if successful
        """
        if not 1 <= new_address <= 247:
            error(
                f"Invalid slave address: {new_address}. Must be between 1 and 247.",
                message_logger=self.message_logger,
            )
            raise ValueError("Slave address must be between 1 and 247")

        try:
            result = self.bus.write_holding_register(
                address=self.PUBLIC_ADDR, register=self.ADDR, value=new_address
            )
            if not result:
                error(f"Failed to change address", message_logger=self.message_logger)
                raise Exception(f"Failed to change address")

            info(
                f"Device address changed to {new_address}. Please reset the device.",
                message_logger=self.message_logger,
            )
            self.slave_addr = new_address
            return True
        except Exception as e:
            error(
                f"Error changing address: {str(e)}", message_logger=self.message_logger
            )
            return False

    def change_baudrate(self, baudrate_index):
        """Change the baudrate of the device

        Args:
            baudrate_index (int): Baudrate index (1-8)
                1: 2400, 2: 4800, 3: 9600, 4: 14400,
                5: 19200, 6: 38400, 7: 57600, 8: 115200

        Returns:
            bool: True if successful
        """
        if not 1 <= baudrate_index <= 8:
            error(
                f"Invalid baudrate index: {baudrate_index}. Must be between 1 and 8.",
                message_logger=self.message_logger,
            )
            raise ValueError("Baudrate index must be between 1 and 8")

        try:
            result = self.write_register(self.COM_BAUDRATE, baudrate_index)
            if result:
                info(
                    f"Device baudrate changed to {self.BAUDRATE_MAP[baudrate_index]}. Please reset the device.",
                    message_logger=self.message_logger,
                )
                return True
            return False
        except Exception as e:
            error(
                f"Error changing baudrate: {str(e)}", message_logger=self.message_logger
            )
            return False
