import unittest

from avena_commons.util.error_level import (
    ErrorCodeException,
    ErrorCodes,
    ErrorGroups,
    ErrorInterface,
    InvalidError,
)


# python -m unittest discover -s tests
# Unit Testing
class TestErrorManager(unittest.TestCase):
    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self.error_manager = ErrorInterface()

    def test_valid_error_set(self):
        self.error_manager.set_error(ErrorCodes.CONNECTION_ERROR)
        self.assertEqual(self.error_manager.current_error[-1].error_code, ErrorCodes.CONNECTION_ERROR)

    def test_invalid_error_set(self):
        with self.assertRaises(InvalidError):
            self.error_manager.set_error(999)  # Pass an obviously invalid error code

    def test_string_error_set(self):
        with self.assertRaises(InvalidError):
            self.error_manager.set_error("SomeNonexistentError")  # Pass a string that isn't a valid Enum name

    def test_error_acknowledgement(self):
        self.error_manager.set_error(ErrorCodes.CONNECTION_ERROR)
        self.error_manager.ack_errors()
        self.assertEqual(len(self.error_manager.get_error_history()), 0)

    def test_acknowledging_errors(self):
        self.error_manager.set_error(ErrorCodes.PUMP_ERROR)
        self.error_manager.set_error(ErrorCodes.QR_WARNING)
        self.assertEqual(len(self.error_manager.get_error_history()), 2)
        self.error_manager.ack_errors()
        self.assertEqual(len(self.error_manager.get_error_history()), 0)

    def test_error_with_message_logging(self):
        self.error_manager.set_error(ErrorCodes.PUMP_WATCHDOG_ERROR, "Pump watchdog triggered")
        self.assertEqual(
            self.error_manager.get_error_history()[-1].message,
            "Pump watchdog triggered",
        )

    def test_error_with_message(self):
        message = "Connection timeout"
        self.error_manager.set_error(ErrorCodes.CONNECTION_ERROR, message)
        self.assertIn(message, (entry.message for entry in self.error_manager.get_error_history()))

    def test_log_error_with_no_message(self):
        self.error_manager.set_error(ErrorCodes.DEVICE_WARNING)
        self.assertEqual(self.error_manager.get_error_history()[-1].message, "")

    def test_get_current_error_empty(self):
        self.error_manager.ack_errors()
        self.assertFalse(self.error_manager.current_error)

    def test_multiple_error_handling(self):
        self.error_manager.ack_errors()
        self.error_manager.set_error(ErrorCodes.CONNECTION_ERROR, "First error")
        self.error_manager.set_error(ErrorCodes.INITIALIZATION_ERROR, "Second error")
        self.assertEqual(len(self.error_manager.get_error_history()), 2)
        self.assertEqual(self.error_manager.get_error_history()[0].message, "First error")
        self.assertEqual(self.error_manager.get_error_history()[1].message, "Second error")

    def test_error_group_enum(self):
        self.error_manager.set_error(ErrorCodes.CONNECTION_ERROR)
        self.assertEqual(self.error_manager.current_error[-1].error_group, ErrorGroups.CRITICAL)

    def test_error_code_membership(self):
        for code in self.error_manager.error_groups.keys():
            self.assertTrue(isinstance(code, ErrorCodes))

    def test_error_group_membership(self):
        for group in self.error_manager.error_groups.values():
            self.assertTrue(isinstance(group, ErrorGroups))

    def test_error_group_retrieval(self):
        error_code = ErrorCodes.DEVICE_WARNING
        expected_group = ErrorGroups.WARNING
        self.assertEqual(self.error_manager.get_group(error_code), expected_group)

    def test_current_error_check(self):
        self.error_manager.set_error(ErrorCodes.CONNECTION_ERROR)
        self.assertTrue(self.error_manager.check_current_error(ErrorCodes.CONNECTION_ERROR))

    def test_current_error_check_fail(self):
        self.error_manager.set_error(ErrorCodes.CONNECTION_ERROR)
        self.assertFalse(self.error_manager.check_current_error(ErrorCodes.PUMP_ERROR))

    def test_ack_specific_error(self):
        self.error_manager.set_error(ErrorCodes.CONNECTION_ERROR)
        self.error_manager.set_error(ErrorCodes.INITIALIZATION_ERROR)
        self.error_manager.ack_error(ErrorCodes.CONNECTION_ERROR)
        self.assertFalse(self.error_manager.check_current_error(ErrorCodes.CONNECTION_ERROR))

    def test_set_check_ack_specific_error(self):
        self.error_manager.set_error(ErrorCodes.CONNECTION_ERROR)
        self.assertTrue(self.error_manager.check_current_error(ErrorCodes.CONNECTION_ERROR))
        self.assertTrue(self.error_manager.check_current_group(ErrorGroups.CRITICAL))
        self.error_manager.ack_error(ErrorCodes.CONNECTION_ERROR)
        self.assertFalse(self.error_manager.check_current_error(ErrorCodes.CONNECTION_ERROR))
        self.assertFalse(self.error_manager.check_current_group(ErrorGroups.CRITICAL))

    def test_custom_exception(self):
        with self.assertRaises(ErrorCodeException):
            raise ErrorCodeException(ErrorCodes.CONNECTION_ERROR, "Failed to connect to the server")

    def test_custom_exception_message(self):
        try:
            raise ErrorCodeException(ErrorCodes.CONNECTION_ERROR, "Failed to connect to the server")
        except ErrorCodeException as ce:
            self.assertEqual(ce.message, "Failed to connect to the server")

    def test_custom_exception_error_code(self):
        try:
            raise ErrorCodeException(ErrorCodes.CONNECTION_ERROR, "Failed to connect to the server")
        except ErrorCodeException as ce:
            self.assertEqual(ce.error_code, ErrorCodes.CONNECTION_ERROR)

    def test_set_error_with_exception(self):
        with self.assertRaises(ErrorCodeException):
            try:
                raise ErrorCodeException(ErrorCodes.CONNECTION_ERROR, "Failed to connect to the server")
            except ErrorCodeException as ce:
                self.error_manager.set_error(ce.error_code, ce.message)
                self.assertEqual(
                    self.error_manager.current_error[-1].error_code,
                    ErrorCodes.CONNECTION_ERROR,
                )
                raise


# if __name__ == "__main__":
#     print("\n==================================================================================")
#     info("ErrorManager usage example\n")
#     # Create an instance of ErrorManager
#     error_manager = ErrorManager()

#     info("Error setting:")
#     try:
#         raise ErrorCodeException(ErrorCodes.CONNECTION_ERROR, "Failed to connect to the server")
#     except ErrorCodeException as ce:
#         # Set an error
#         error_manager.set_error(ce.error_code, ce.message)
#     info("Getting the current error:")
#     # Get the current error
#     current_error = error_manager.current_error
#     error_code = current_error.error_code
#     error_group = current_error.error_group
#     debug(f"Current Error: {error_code.name}, Group: {error_group.name}")

#     info("Errors acknowledged:")
#     # Acknowledge errors
#     error_manager.ack_errors()
#     debug(f"Errors acknowledged: Error_manager.current_error returns {error_manager.current_error}")


#     print("\n==================================================================================")
#     info("Setting another 2 errors:")
#     try:
#         raise ErrorCodeException(ErrorCodes.CONNECTION_ERROR, "Failed to connect to the server")
#     except ErrorCodeException as ce:
#         # Set an error
#         error_manager.set_error(ce.error_code, ce.message)
#     try:
#         raise ErrorCodeException(ErrorCodes.DEVICE_ERROR, "Failed to setup device")
#     except ErrorCodeException as ce:
#         # Set an error
#         error_manager.set_error(ce.error_code, ce.message)

#     # Get the error history
#     info("Error history reading:")
#     error_history = error_manager.get_error_history()
#     for value in error_history:
#         debug(f"{value}")
#     error_manager.ack_errors()


#     print("\n==================================================================================")
#     info("Registering an action for the ERROR group:")
#     # Register an action for a specific error group
#     def do_something():
#         debug("do_something: Action executed")

#     error_manager.register_action(ErrorGroups.CRITICAL, action=do_something)

#     info("Setting an error to trigger the action:")
#     # Set an error to trigger the action
#     error_manager.set_error(ErrorCodes.RUN_PROGRAM_ERROR, "Error while running the program")


#     print("\n==================================================================================")
#     info("Removing the action for the error group")
#     # Remove the action for the error group
#     error_manager.remove_action(ErrorGroups.CRITICAL, do_something)

#     info("Setting another error to check if the action is removed:")
#     # Set another error to check if the action is removed
#     error_manager.set_error(ErrorCodes.INITIALIZATION_ERROR, "Init error")
