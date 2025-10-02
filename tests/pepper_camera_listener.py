from avena_commons.pepper_camera.pepper_camera import PepperCamera
from avena_commons.util.logger import MessageLogger

# python pepper_camera_listener.py

if __name__ == "__main__":
    camera_logger = MessageLogger(
        filename="temp/pepper_camera_autonomous_benchmark.log", debug=True
    )

    pepper_camera = PepperCamera(
        name="pepper_camera_autonomous_benchmark",
        address="127.0.0.1",
        port="8002",
        message_logger=camera_logger,
    )
    pepper_camera.start()
