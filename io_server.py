import os
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from avena_commons.io import IO_server
from avena_commons.util.logger import LoggerPolicyPeriod, MessageLogger
from dotenv import load_dotenv

load_dotenv(override=True)
# python3 io_server2.py

if __name__ == "__main__":
    if not os.path.exists("temp"):
        os.mkdir("temp")
    temp_path = os.path.abspath("temp")
    message_logger = MessageLogger(filename=f"{temp_path}/io.log", period=LoggerPolicyPeriod.LAST_15_MINUTES, files_count=40, colors=False, core=11)

    # Initialize the IO server with the specified configuration
    io_server = IO_server(
        name="io",
        port=os.getenv("IO_LISTENER_PORT"),
        general_config_file="io_config general.json",
        configuration_file="io_config.json",
        message_logger=message_logger,
        debug=True,
        load_state=False,  # TODO: zmienić na true jak produkcja
    )
    io_server.start()
