#!/usr/bin/env python3
"""
PepperCamera Listener - Launch script for camera EventListeners.

Supports both physical and virtual cameras with CLI configuration.

Usage:
    python tests/pepper_camera_listener.py --name virtual_camera_1 --port 9001
    python tests/pepper_camera_listener.py --name physical_camera --port 9000 --config custom.json
"""

import argparse
import sys

from avena_commons.pepper_camera.pepper_camera import PepperCamera
from avena_commons.util.logger import LoggerPolicyPeriod, MessageLogger


def main():
    parser = argparse.ArgumentParser(
        description="PepperCamera EventListener Launcher"
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Service name (must match config filename: tests/{name}_config.json)"
    )
    parser.add_argument(
        "--address",
        default="127.0.0.1",
        help="Bind address (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        required=True,
        help="Service port"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    # Create logger
    logger = MessageLogger(
        filename=f"temp/{args.name}.log",
        core=12,
        debug=False,
        period=LoggerPolicyPeriod.LAST_15_MINUTES,
        files_count=10,
        colors=False,
    )
    
    print(f"🚀 Starting PepperCamera: {args.name}")
    print(f"   Address: {args.address}:{args.port}")
    print(f"   Config:  tests/{args.name}_config.json")
    print(f"   Logs:    temp/{args.name}.log")
    
    try:
        camera = PepperCamera(
            name=args.name,
            address=args.address,
            port=args.port,
            message_logger=logger,
        )
        camera.start()
    except KeyboardInterrupt:
        print(f"\n🛑 Stopping {args.name}...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()