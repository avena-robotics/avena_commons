import argparse
import base64
import datetime
import os
import pickle
import threading
import time
from typing import Any, Dict

import cv2
import numpy as np
import requests

from avena_commons.event_listener import Event, EventListener, EventListenerState
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import MessageLogger

image_loader_logger = MessageLogger(
    filename="temp/image_loader.log",
    core=14,
    debug=False,
)

# Base URL for HTTP requests
base_url = "http://127.0.0.1"

# Control system EventListener
listener = EventListener(
    name="image_loader", port=8005, message_logger=image_loader_logger
)
thread1 = threading.Thread(target=listener.start)
thread1.start()
time.sleep(1)
listener._change_fsm_state(EventListenerState.INITIALIZING)
time.sleep(1)
listener._change_fsm_state(EventListenerState.STARTING)
time.sleep(1)

# Data directory
DATA_DIR = "/home/avena/avena_commons/resources/tests/test_2024_07_18/24"

# Fragment configuration
FRAGMENT_CONFIG = {
    "top_right": {
        "fragment_id": 0,
        "position": "top-right",
        "roi": {"x": [430, 510], "y": [200, 280]},
    },
    "bottom_right": {
        "fragment_id": 1,
        "position": "bottom-right",
        "roi": {"x": [430, 510], "y": [120, 200]},
    },
    "bottom_left": {
        "fragment_id": 2,
        "position": "bottom-left",
        "roi": {"x": [180, 260], "y": [200, 280]},
    },
    "top_left": {
        "fragment_id": 3,
        "position": "top-left",
        "roi": {"x": [180, 260], "y": [120, 200]},
    },
}


def load_frame(position: str, frame_number: int) -> Dict[str, np.ndarray]:
    """Load color (PNG) and depth (pickle) for given position and frame number."""
    folder = os.path.join(DATA_DIR, position)

    # Load color image (PNG)
    color_path = os.path.join(folder, f"rgb_{position}_{frame_number}.png")
    if not os.path.exists(color_path):
        raise FileNotFoundError(f"Color image not found: {color_path}")

    color_image = cv2.imread(color_path)
    if color_image is None:
        raise ValueError(f"Failed to load color image: {color_path}")

    # Load depth image (pickle)
    depth_path = os.path.join(folder, f"depth_{position}_{frame_number}.pkl")
    if not os.path.exists(depth_path):
        raise FileNotFoundError(f"Depth image not found: {depth_path}")

    with open(depth_path, "rb") as f:
        depth_image = pickle.load(f)

    if depth_image is None:
        raise ValueError(f"Failed to load depth image: {depth_path}")

    return {"color": color_image, "depth": depth_image}


def create_fragments(frame_number: int) -> Dict[str, Dict[str, Any]]:
    """Load all 4 fragments for given frame number."""
    fragments = {}

    for position, config in FRAGMENT_CONFIG.items():
        try:
            frame_data = load_frame(position, frame_number)

            # Validate that both color and depth are present
            if "color" not in frame_data or "depth" not in frame_data:
                print(f"Fragment {position} missing color or depth data")
                return None

            if frame_data["color"] is None or frame_data["depth"] is None:
                print(f"Fragment {position} has None for color or depth")
                return None

            fragments[position] = {
                "color": frame_data["color"],
                "depth": frame_data["depth"],
                "fragment_id": config["fragment_id"],
                "position": config["position"],
                "roi": config["roi"],
            }

        except (FileNotFoundError, ValueError) as e:
            print(f"Error loading frame {frame_number} for {position}: {e}")
            return None

    return fragments


def serialize_fragments(
    fragments: Dict[str, Dict[str, np.ndarray]],
) -> Dict[str, Dict[str, Any]]:
    """Serialize fragments to JSON-compatible format (same as PepperCameraConnector)."""
    serializable_fragments = {}

    for fragment_name, fragment_data in fragments.items():
        serializable_fragment = {}

        for key, value in fragment_data.items():
            if isinstance(value, np.ndarray):
                # Convert numpy arrays to base64
                array_bytes = value.tobytes()
                encoded_array = base64.b64encode(array_bytes).decode("utf-8")

                serializable_fragment[key] = {
                    "data": encoded_array,
                    "dtype": str(value.dtype),
                    "shape": value.shape,
                }
            else:
                # Keep other values as-is
                serializable_fragment[key] = value

        serializable_fragments[fragment_name] = serializable_fragment

    return serializable_fragments


def send_fragments_event(
    serialized_fragments: Dict[str, Dict[str, Any]], destination: str, port: int
):
    """Send fragments as Event to the event listener."""

    for fragment_name, fragment_data in serialized_fragments.items():
        event = Event(
            source="image_loader",
            source_port=8005,
            destination=destination,
            destination_port=port,
            event_type="process_fragments",
            data={
                "fragment": fragment_data,  # Single fragment
                "fragment_name": fragment_name,
                "fragment_id": fragment_data.get("fragment_id"),
                "timestamp": datetime.datetime.now().isoformat(),
            },
            to_be_processed=False,
        )

        response = requests.post(
            f"{base_url}:{port}/event",
            json=event.to_dict(),
            timeout=1.0,
        )

        if response.status_code != 200:
            raise ConnectionError(f"Failed to send event: HTTP {response.status_code}")
    return response


def main(destination: str, port: int, duration_seconds: int):
    """Main loop to send frames in loop for specified duration at 30Hz.

    Args:
        destination: Target service name
        port: Target service port
        duration_seconds: Total duration to run in seconds
    """
    # Find number of available frames by checking one position folder
    test_folder = os.path.join(DATA_DIR, "bottom_left")

    if not os.path.exists(test_folder):
        print(f"Data folder not found: {test_folder}")
        return

    frame_files = [
        f
        for f in os.listdir(test_folder)
        if f.startswith("rgb_") and f.endswith(".png")
    ]
    num_frames = len(frame_files)

    if num_frames == 0:
        print("No frames found!")
        return

    print(f"Found {num_frames} frames to process")
    print(f"Sending at 30Hz (one frame every ~33ms)")
    print(f"Destination: {destination}")
    print(f"Port: {port}")
    print(f"Duration: {duration_seconds} seconds")
    print(f"Data directory: {DATA_DIR}\n")

    successful_frames = 0
    failed_frames = 0
    total_sent = 0

    start_time = time.time()
    elapsed_time = 0

    # Loop through frames repeatedly until duration is reached
    while elapsed_time < duration_seconds:
        for frame_number in range(num_frames):
            # Check if we've exceeded duration
            elapsed_time = time.time() - start_time
            if elapsed_time >= duration_seconds:
                break

            total_sent += 1
            loop_num = total_sent // num_frames
            print(
                f"[{elapsed_time:.1f}s] Loop {loop_num} - Frame {frame_number}/{num_frames - 1}",
                end=" ",
            )

            with Catchtime() as ct:
                # Load fragments (validates both color and depth exist)
                fragments = create_fragments(frame_number)
                if fragments is None:
                    print(f"❌ FAILED - Missing color or depth")
                    failed_frames += 1
                    continue

                # Validate all 4 fragments loaded
                if len(fragments) != 4:
                    print(f"❌ FAILED - Only {len(fragments)}/4 fragments loaded")
                    failed_frames += 1
                    continue

                # Serialize
                serialized = serialize_fragments(fragments)

                # Send event
                try:
                    response = send_fragments_event(serialized, destination, port)
                    if response.status_code == 200:
                        print(f"✓ OK - {ct.ms:.2f}ms")
                        successful_frames += 1
                    else:
                        print(f"❌ HTTP {response.status_code} - {ct.ms:.2f}ms")
                        failed_frames += 1
                except Exception as e:
                    print(f"❌ ERROR: {e}")
                    failed_frames += 1

            # Send at 30Hz
            time.sleep(0.033)

    elapsed_time = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"Processing complete!")
    print(f"Duration: {elapsed_time:.2f}s / {duration_seconds}s")
    print(f"Total frames sent: {total_sent}")
    print(f"Successful: {successful_frames}")
    print(f"Failed: {failed_frames}")
    print(f"Loops completed: {total_sent // num_frames}")
    print(f"{'=' * 60}")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Load and send image fragments to a destination service",
        epilog="""
Example usage with taskset:
  taskset -c 0-3 python load_images_listener.py pepper_1 8001 120
  taskset -c 4-7 python load_images_listener.py vision_service 8002 60
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "destination", help="Target service name (e.g., 'pepper_1', 'vision_service')"
    )

    parser.add_argument(
        "port", type=int, help="Target service port number (e.g., 8001, 8002)"
    )

    parser.add_argument(
        "duration", type=int, help="Duration to run in seconds (e.g., 120, 300)"
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args.destination, args.port, args.duration)
