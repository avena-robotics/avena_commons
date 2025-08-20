import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from avena_commons.dashboard.dashboard import Dashboard
from avena_commons.event_listener import Event, EventListener
from avena_commons.util.logger import LoggerPolicyPeriod, MessageLogger, debug


class TestDashboard(Dashboard):
    def __init__(
        self,
        name: str,
        port: int,
        address: str,
        message_logger=None,
        debug=False,
    ):
        self.check_local_data_frequency = 1
        super().__init__(
            name=name,
            address=address,
            port=port,
            do_not_load_state=True,
            message_logger=message_logger,
        )
        self.start()


if __name__ == "__main__":
    temp_path = os.path.abspath("temp")
    message_logger = MessageLogger(
        filename=f"{temp_path}/test_dashboard.log",
        period=LoggerPolicyPeriod.LAST_15_MINUTES,
    )
    # message_logger = None
    port = 9600
    try:
        app = TestDashboard(
            name=f"test_dashboard",
            address="127.0.0.1",
            port=port,
            message_logger=message_logger,
            debug=True,
        )

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
    finally:
        try:
            # supervisor.cleanup()
            pass
        except NameError:
            pass
