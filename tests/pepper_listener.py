from avena_commons.pepper.pepper import Pepper
from avena_commons.util.logger import MessageLogger

# python pepper_listener.py

if __name__ == "__main__":
    
    pepper_logger = MessageLogger(filename="temp/pepper_autonomous_benchmark.log", debug=True)
    
    pepper_listener = Pepper(
        name="pepper_autonomous_benchmark",
        address="127.0.0.1", 
        port="8001",
        message_logger=pepper_logger
    )
    pepper_listener.start()