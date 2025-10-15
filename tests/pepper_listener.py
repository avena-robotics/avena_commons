import argparse

from avena_commons.pepper.pepper import Pepper
from avena_commons.util.logger import MessageLogger

# python pepper_listener.py pepper_1 8001


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Start Pepper listener service",
        epilog="""
Example usage with taskset:
  taskset -c 0-3 python pepper_listener.py pepper_1 8001
  taskset -c 8-15 python pepper_listener.py pepper_2 8002
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "name", help="Pepper service name (e.g., 'pepper_1', 'pepper_2')"
    )

    parser.add_argument(
        "port", type=int, help="Port number for the service (e.g., 8001, 8002)"
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    pepper_logger = MessageLogger(
        filename=f"temp/{args.name}.log",
        core=15,
        debug=False,
    )

    pepper_listener = Pepper(
        name=args.name,
        address="127.0.0.1",
        port=str(args.port),
        message_logger=pepper_logger,
    )
    pepper_listener.start()
