"""
arduino_cli_installer.py – Auto-installation of arduino-cli for provisioning station.

Detects OS and installs arduino-cli automatically if not found.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from typing import Optional


def get_os_type() -> str:
    """Return the operating system type."""
    return platform.system()  # Returns: Darwin (macOS), Linux, Windows


def is_arduino_cli_installed() -> bool:
    """Check if arduino-cli is available on PATH."""
    try:
        result = subprocess.run(
            ["arduino-cli", "version"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def install_arduino_cli_macos() -> tuple[bool, str]:
    """Install arduino-cli on macOS using Homebrew."""
    try:
        # Check if brew is installed
        result = subprocess.run(
            ["brew", "--version"],
            capture_output=True,
            timeout=5
        )
        if result.returncode != 0:
            return False, "Homebrew not installed. Install from: https://brew.sh"
        
        # Install arduino-cli
        print("Installing arduino-cli via Homebrew...")
        result = subprocess.run(
            ["brew", "install", "arduino-cli"],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            return True, "✓ arduino-cli installed successfully via Homebrew"
        else:
            return False, f"Installation failed:\n{result.stderr}"
    
    except subprocess.TimeoutExpired:
        return False, "Installation timed out"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def install_arduino_cli_linux() -> tuple[bool, str]:
    """Install arduino-cli on Linux."""
    try:
        print("Downloading arduino-cli installer for Linux...")
        
        # Download and run official installer script
        result = subprocess.run(
            [
                "sh", "-c",
                "curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh"
            ],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            # Move to PATH if needed
            home = os.path.expanduser("~")
            cli_path = os.path.join(home, "bin", "arduino-cli")
            
            if os.path.exists(cli_path):
                return True, "✓ arduino-cli installed successfully"
            else:
                return False, "Installer ran but arduino-cli not found at expected location"
        else:
            return False, f"Installation failed:\n{result.stderr}"
    
    except subprocess.TimeoutExpired:
        return False, "Installation timed out"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def install_arduino_cli_windows() -> tuple[bool, str]:
    """Install arduino-cli on Windows."""
    try:
        # Try Chocolatey first (most common)
        result = subprocess.run(
            ["choco", "--version"],
            capture_output=True,
            timeout=5
        )
        
        if result.returncode == 0:
            print("Installing arduino-cli via Chocolatey...")
            result = subprocess.run(
                ["choco", "install", "-y", "arduino-cli"],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                return True, "✓ arduino-cli installed successfully via Chocolatey"
            else:
                return False, f"Installation failed:\n{result.stderr}"
        else:
            # Fallback: download binary manually
            return False, (
                "Chocolatey not found. Please install arduino-cli manually:\n"
                "https://arduino.github.io/arduino-cli/latest/installation/#windows"
            )
    
    except subprocess.TimeoutExpired:
        return False, "Installation check/installation timed out"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def auto_install_arduino_cli() -> tuple[bool, str]:
    """
    Automatically detect OS and install arduino-cli.

    Returns
    -------
    (success: bool, message: str)
    """
    # First check if already installed
    if is_arduino_cli_installed():
        return True, "✓ arduino-cli already installed"
    
    os_type = get_os_type()
    
    if os_type == "Darwin":  # macOS
        return install_arduino_cli_macos()
    elif os_type == "Linux":
        return install_arduino_cli_linux()
    elif os_type == "Windows":
        return install_arduino_cli_windows()
    else:
        return False, f"Unsupported operating system: {os_type}"


def get_install_instructions() -> str:
    """Return installation instructions for the current OS."""
    os_type = get_os_type()
    
    if os_type == "Darwin":
        return (
            "Install Homebrew (if not already installed):\n"
            "  /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"\n\n"
            "Then install arduino-cli:\n"
            "  brew install arduino-cli"
        )
    elif os_type == "Linux":
        return (
            "Download and run the installer:\n"
            "  curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh"
        )
    elif os_type == "Windows":
        return (
            "Install Chocolatey (if not already installed):\n"
            "  Run PowerShell as Administrator and execute:\n"
            "  Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))\n\n"
            "Then install arduino-cli:\n"
            "  choco install arduino-cli"
        )
    else:
        return "Manual installation: https://arduino.github.io/arduino-cli/"
