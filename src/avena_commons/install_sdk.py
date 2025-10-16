"""Automatic installation of pyorbbecsdk based on system and Python version."""

import os
import platform
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Optional


def get_wheel_path() -> Optional[Path]:
    """Get the appropriate wheel file path for current system and Python version."""
    # Get current Python version (major.minor)
    python_version = f"cp{sys.version_info.major}{sys.version_info.minor}"
    current_platform = platform.system().lower()
    machine = platform.machine().lower()

    # Map platform names
    if current_platform == "windows":
        platform_tag = "win_amd64"
    elif current_platform == "linux":
        if machine in ["x86_64", "amd64"]:
            platform_tag = "linux_x86_64"
        else:
            return None  # Unsupported architecture
    else:
        return None  # Unsupported platform

    # Find package installation directory
    try:
        import avena_commons

        package_dir = Path(avena_commons.__file__).parent
    except ImportError:
        # Fallback to current directory structure during development
        package_dir = Path(__file__).parent

    # Look for wheel files in the install directory
    install_dir = package_dir / ".." / ".." / ".." / "install"
    if not install_dir.exists():
        # Try alternative path if installed via pip
        install_dir = package_dir.parent / "install"

    if not install_dir.exists():
        return None

    # Find the best matching wheel
    wheel_patterns = [
        f"pyorbbecsdk-*-{python_version}-{python_version}-{platform_tag}.whl",
        f"pyorbbecsdk-*-{python_version}-*-{platform_tag}.whl",
    ]

    for pattern in wheel_patterns:
        wheels = list(install_dir.glob(pattern))
        if wheels:
            # Return the newest version (assuming lexicographical order works)
            return sorted(wheels)[-1]

    return None


def is_pyorbbecsdk_installed() -> bool:
    """Check if pyorbbecsdk is already installed."""
    try:
        import pyorbbecsdk

        return True
    except ImportError:
        return False


def install_pyorbbecsdk(force: bool = False) -> bool:
    """
    Install pyorbbecsdk wheel if not already installed.

    Args:
        force: If True, reinstall even if already installed.

    Returns:
        True if installation successful or already installed, False otherwise.
    """
    if not force and is_pyorbbecsdk_installed():
        return True

    wheel_path = get_wheel_path()
    if not wheel_path:
        warnings.warn(
            f"No suitable pyorbbecsdk wheel found for "
            f"{platform.system()} Python {sys.version_info.major}.{sys.version_info.minor}. "
            f"Orbec camera support will not be available.",
            RuntimeWarning,
        )
        return False

    if not wheel_path.exists():
        warnings.warn(
            f"Wheel file {wheel_path} not found. "
            f"Orbec camera support will not be available.",
            RuntimeWarning,
        )
        return False

    print(f"Installing pyorbbecsdk from {wheel_path}")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", str(wheel_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("pyorbbecsdk installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        warnings.warn(
            f"Failed to install pyorbbecsdk: {e}. "
            f"Orbec camera support will not be available.",
            RuntimeWarning,
        )
        return False


def ensure_pyorbbecsdk():
    """Ensure pyorbbecsdk is installed, install if necessary."""
    if not is_pyorbbecsdk_installed():
        install_pyorbbecsdk()


# Auto-install on import (can be disabled by setting environment variable)
if os.environ.get("AVENA_COMMONS_SKIP_AUTO_INSTALL") != "1":
    ensure_pyorbbecsdk()


def main():
    """Command line entry point for manual installation."""
    import argparse

    parser = argparse.ArgumentParser(description="Install pyorbbecsdk SDK")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reinstallation even if already installed",
    )
    parser.add_argument(
        "--check", action="store_true", help="Only check if SDK is installed"
    )

    args = parser.parse_args()

    if args.check:
        if is_pyorbbecsdk_installed():
            print("pyorbbecsdk is installed")
            sys.exit(0)
        else:
            print("pyorbbecsdk is NOT installed")
            sys.exit(1)

    if install_pyorbbecsdk(force=args.force):
        print("Installation completed successfully")
        sys.exit(0)
    else:
        print("Installation failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
