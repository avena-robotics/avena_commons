import os
import sys

# Add the src directory to the system path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from dotenv import load_dotenv

# from avena_commons.camera.camera import Camera
from avena_commons.pepper_camera.pepper_camera import PepperCamera as Camera
from avena_commons.util.logger import (
    LoggerPolicyPeriod,
    MessageLogger,
)

if __name__ == "__main__":
    message_logger = MessageLogger(
        filename=f"temp/test_camera.log",
        debug=True,
        period=LoggerPolicyPeriod.LAST_15_MINUTES,
        files_count=40,
    )
    load_dotenv(override=True)

    port = 9900

    print("port: ", port)
    listener = Camera(
        name=f"camera_server_192.168.1.10",
        address="127.0.0.1",
        port=port,
        message_logger=message_logger,
    )
    listener.start()
