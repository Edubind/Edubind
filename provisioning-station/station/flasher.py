"""
flasher.py – Flash firmware onto an Arduino/ESP32 device using arduino-cli or PlatformIO.

Supports:
    - Arduino R4 WiFi  (arduino:renesas_uno:unor4wifi) via arduino-cli
    - Arduino R4 WiFi  (uno_r4_wifi) via PlatformIO
    - ESP32            (esp32:esp32:esp32) via arduino-cli
    - ESP32            (esp32) via PlatformIO
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FlashResult:
    success: bool
    logs: str
    return_code: int
    sha256: str = ""  # SHA-256 of the flashed artifact (for OTA tracking)


def _verify_sha256(file_path: str, expected_hash: str) -> bool:
    """Return True if *file_path* matches *expected_hash* (hex SHA-256)."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().lower() == expected_hash.lower()


def _compute_sha256(file_path: str) -> str:
    """Return the hex-encoded SHA-256 of *file_path*."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def _detect_platformio_project(project_path: str) -> bool:
    """Return True if *project_path* is a PlatformIO project (contains platformio.ini)."""
    return os.path.isfile(os.path.join(project_path, "platformio.ini"))


def _find_platformio_artifact(project_path: str, env: str) -> Optional[str]:
    """
    Find the compiled firmware artifact for a PlatformIO environment.
    
    Searches common output directories:
      - <project>/.pio/build/<env>/firmware.bin
      - <project>/.pio/build/<env>/firmware.elf
      - <project>/.pio/build/<env>/*.bin
    
    Returns the first .bin file found, or None if not found.
    """
    build_dir = os.path.join(project_path, ".pio", "build", env)
    if not os.path.isdir(build_dir):
        return None

    # Priority: firmware.bin > *.bin > firmware.elf
    candidates = [
        os.path.join(build_dir, "firmware.bin"),
        os.path.join(build_dir, "firmware.elf"),
    ]

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    # Fallback: any .bin file
    for fname in os.listdir(build_dir):
        if fname.endswith(".bin"):
            return os.path.join(build_dir, fname)

    return None


def flash_firmware_platformio(
    project_path: str,
    port: str,
    env: str = "uno_r4_wifi",
    pio_path: str = "platformio",
    reset_before: bool = True,
) -> FlashResult:
    """
    Build and flash firmware using PlatformIO.

    Parameters
    ----------
    project_path:  Path to the PlatformIO project root
    port:          Serial port (e.g., "/dev/ttyUSB0" or "COM3")
    env:           PlatformIO environment (default: "uno_r4_wifi")
    pio_path:      Path to platformio executable (default: "platformio")
    reset_before:  If True, trigger bootloader via 1200bps DTR toggle

    Returns
    -------
    FlashResult with success flag, logs, return code, and SHA-256 of artifact.
    """
    logs = f"[pio] Building environment '{env}' from {project_path}\n"

    if not os.path.isdir(project_path):
        return FlashResult(
            success=False,
            logs=logs + f"Project path not found: {project_path}",
            return_code=-1,
        )

    # Build step
    try:
        build_cmd = [pio_path, "run", "-d", project_path, "-e", env]
        result = subprocess.run(build_cmd, capture_output=True, text=True, timeout=300)
        logs += result.stdout + result.stderr

        if result.returncode != 0:
            return FlashResult(
                success=False,
                logs=logs + f"\n[pio] Build failed with return code {result.returncode}",
                return_code=result.returncode,
            )
    except subprocess.TimeoutExpired:
        return FlashResult(
            success=False,
            logs=logs + "[pio] Build timed out after 300s",
            return_code=-3,
        )
    except FileNotFoundError:
        return FlashResult(
            success=False,
            logs=logs + f"[pio] platformio not found at: {pio_path}. "
                 "Install it: pip install platformio",
            return_code=-4,
        )

    # Find artifact
    artifact_path = _find_platformio_artifact(project_path, env)
    if not artifact_path:
        return FlashResult(
            success=False,
            logs=logs + f"[pio] No firmware artifact found in {project_path}/.pio/build/{env}",
            return_code=-5,
        )

    logs += f"[pio] Found artifact: {artifact_path}\n"
    artifact_sha256 = _compute_sha256(artifact_path)
    logs += f"[pio] SHA-256: {artifact_sha256}\n"

    # Reset bootloader
    if reset_before:
        logs += f"[pio] Toggling bootloader on {port}...\n"
        try:
            import serial
            import time
            s = serial.Serial(port, baudrate=1200, timeout=0.1)
            s.close()
            time.sleep(1.5)
        except Exception:
            pass

    # Upload step
    try:
        upload_cmd = [
            pio_path, "run", "-d", project_path, "-e", env,
            "-t", "upload",
            "--upload-port", port,
        ]
        result = subprocess.run(upload_cmd, capture_output=True, text=True, timeout=120)
        logs += result.stdout + result.stderr

        if result.returncode != 0:
            return FlashResult(
                success=False,
                logs=logs + f"\n[pio] Upload failed with return code {result.returncode}",
                return_code=result.returncode,
                sha256=artifact_sha256,
            )
    except subprocess.TimeoutExpired:
        return FlashResult(
            success=False,
            logs=logs + "[pio] Upload timed out after 120s",
            return_code=-6,
            sha256=artifact_sha256,
        )

    return FlashResult(
        success=True,
        logs=logs + "[pio] ✓ Flash successful\n",
        return_code=0,
        sha256=artifact_sha256,
    )


def flash_firmware(
    port: str,
    fqbn: str,
    firmware_path: str,
    expected_sha256: Optional[str] = None,
    arduino_cli_path: str = "arduino-cli",
    extra_flags: Optional[list[str]] = None,
    reset_before: bool = True,
) -> FlashResult:
    """
    Flash *firmware_path* onto the device at *port* using arduino-cli.

    Parameters
    ----------
    port:            Serial port (e.g. "/dev/ttyUSB0" or "COM3")
    fqbn:            Full Qualified Board Name (e.g. "esp32:esp32:esp32")
    firmware_path:   Absolute path to the .bin/.hex artifact
    expected_sha256: If provided, the artifact is verified before flashing
    arduino_cli_path: Path to the arduino-cli binary (default: "arduino-cli")
    extra_flags:     Additional flags passed to arduino-cli upload
    reset_before:    If True (default), attempt a 1200bps toggle on *port*

    Returns
    -------
    FlashResult with success flag, combined stdout/stderr logs, and return code.
    """

    if not os.path.isfile(firmware_path):
        return FlashResult(
            success=False,
            logs=f"Firmware file not found: {firmware_path}",
            return_code=-1,
        )

    if expected_sha256:
        if not _verify_sha256(firmware_path, expected_sha256):
            return FlashResult(
                success=False,
                logs=f"SHA-256 mismatch for {firmware_path}. "
                     f"Expected: {expected_sha256}",
                return_code=-2,
            )

    artifact_sha256 = _compute_sha256(firmware_path)
    logs = f"[cli] Firmware: {firmware_path}\n[cli] SHA-256: {artifact_sha256}\n"

    if reset_before:
        logs += f"[cli] Toggling bootloader on {port}...\n"
        try:
            import serial
            import time
            # For Arduino R4 WiFi, opening at 1200bps and CLOSING triggers the reset.
            # We add DTR=True/RTS=True to ensure the signal is physically sent
            # and wait longer for the USB stack to re-enumerate.
            s = serial.Serial(port, baudrate=1200, dsrdtr=True, rtscts=True)
            time.sleep(0.1)
            s.close()
            time.sleep(2.5) # Increased from 1.5
        except Exception:
            pass

    # Build candidate ports
    candidates: list[str] = [port]
    if port.startswith("/dev/cu."):
        candidates.append(port.replace("/dev/cu.", "/dev/tty.", 1))
    elif port.startswith("/dev/tty."):
        candidates.append(port.replace("/dev/tty.", "/dev/cu.", 1))

    # Add dynamically re-detected ports for the same board model
    try:
        from station.device_detector import list_ports as _list_ports
        for dev in _list_ports():
            if dev.fqbn == fqbn and dev.port not in candidates:
                candidates.append(dev.port)
    except Exception:
        pass

    if extra_flags is None:
        extra_flags = []

    result: Optional[subprocess.CompletedProcess] = None

    # Normalize artifact path for arduino:renesas_uno
    upload_path = firmware_path
    cleanup_upload_path = False
    if fqbn.startswith("arduino:renesas_uno:") and not firmware_path.lower().endswith(".bin"):
        fd, tmp_bin_path = tempfile.mkstemp(suffix=".bin")
        os.close(fd)
        shutil.copyfile(firmware_path, tmp_bin_path)
        upload_path = tmp_bin_path
        cleanup_upload_path = True
        logs += f"[cli] Normalized artifact: {upload_path}\n"

    try:
        for attempt in range(1, 4):
            for p in candidates:
                logs += f"[cli] Attempt {attempt} on port {p}\n"
                if fqbn.startswith("esp8266:"):
                    cmd = [
                        "esptool",
                        "--port", p,
                        "write_flash",
                        "0x0",
                        upload_path,
                    ]
                else:
                    cmd = [
                        arduino_cli_path,
                        "upload",
                        "--port", p,
                        "--fqbn", fqbn,
                        "--input-file", upload_path,
                        "--verify",
                    ]
                cmd.extend(extra_flags)

                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    logs += result.stdout + result.stderr
                    if result.returncode == 0:
                        break
                except subprocess.TimeoutExpired:
                    return FlashResult(
                        success=False,
                        logs=logs + "arduino-cli timed out after 120s",
                        return_code=-3,
                        sha256=artifact_sha256,
                    )
                except FileNotFoundError:
                    if fqbn.startswith("esp8266:"):
                        return FlashResult(
                            success=False,
                            logs=logs + "esptool not found on PATH. Install it (e.g. pip install esptool) "
                                 "or ensure Arduino ESP8266 tools are available.",
                            return_code=-7,
                            sha256=artifact_sha256,
                        )
                    return FlashResult(
                        success=False,
                        logs=logs + f"arduino-cli not found at: {arduino_cli_path}. "
                             "Install from https://arduino.github.io/arduino-cli/",
                        return_code=-4,
                        sha256=artifact_sha256,
                    )
            if result and result.returncode == 0:
                break
            import time
            time.sleep(1.0)
    finally:
        if cleanup_upload_path:
            try:
                os.unlink(upload_path)
            except OSError:
                pass

    if result is None:
        return FlashResult(
            success=False,
            logs=logs + "No serial port candidates provided",
            return_code=-5,
            sha256=artifact_sha256,
        )

    return FlashResult(
        success=result.returncode == 0,
        logs=logs,
        return_code=result.returncode,
        sha256=artifact_sha256,
    )

