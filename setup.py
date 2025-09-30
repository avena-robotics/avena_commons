"""Setup script for avena_commons with automatic pyorbbecsdk installation."""

import os
import platform
import subprocess
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.install import install


class CustomInstallCommand(install):
    """Custom installation command that installs appropriate pyorbbecsdk wheel."""
    
    def run(self):
        """Run the installation and then install appropriate pyorbbecsdk wheel."""
        # First run the standard installation
        install.run(self)
        
        # Then install the appropriate pyorbbecsdk wheel
        self._install_pyorbbecsdk()
    
    def _install_pyorbbecsdk(self):
        """Install the appropriate pyorbbecsdk wheel based on platform and Python version."""
        # Get current Python version (major.minor)
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        current_platform = platform.system()
        
        # Determine the appropriate wheel file
        wheel_file = None
        install_dir = Path(__file__).parent / "install"
        
        if current_platform == "Windows":
            if python_version.startswith("3.10"):
                wheel_file = install_dir / "pyorbbecsdk-2.0.13-cp310-cp310-win_amd64.whl"
            elif python_version.startswith("3.12"):
                wheel_file = install_dir / "pyorbbecsdk-2.0.13-cp312-cp312-win_amd64.whl"
        elif current_platform == "Linux":
            if python_version.startswith("3.10"):
                wheel_file = install_dir / "pyorbbecsdk-2.0.13-cp310-cp310-linux_x86_64.whl"
            elif python_version.startswith("3.12"):
                wheel_file = install_dir / "pyorbbecsdk-2.0.13-cp312-cp312-linux_x86_64.whl"
        
        if wheel_file and wheel_file.exists():
            print(f"Installing pyorbbecsdk from {wheel_file}")
            try:
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", str(wheel_file)
                ])
                print("pyorbbecsdk installed successfully")
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to install pyorbbecsdk: {e}")
        else:
            print(f"Warning: No suitable pyorbbecsdk wheel found for {current_platform} Python {python_version}")


if __name__ == "__main__":
    setup(
        cmdclass={
            'install': CustomInstallCommand,
        }
    )