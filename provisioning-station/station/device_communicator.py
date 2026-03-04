"""
device_communicator.py – Serial communication with Arduino/ESP32 devices.

Provides methods to query device information such as MAC address via serial port.
"""

from __future__ import annotations

import re
import time
from typing import Optional

try:
    import serial
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False


class DeviceCommunicator:
    """Communicate with devices over serial port."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0) -> None:
        """
        Parameters
        ----------
        port: Serial port (e.g. /dev/ttyUSB0)
        baudrate: Serial communication speed
        timeout: Read timeout in seconds
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None

    def connect(self) -> None:
        """Open serial connection."""
        if not _SERIAL_AVAILABLE:
            raise RuntimeError("pyserial is not installed. Run: pip install pyserial")
        
        try:
            self._serial = serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.timeout
            )
            # Pulse DTR/RTS to reset the board cleanly
            self._serial.dtr = False
            self._serial.rts = False
            time.sleep(0.1)
            self._serial.dtr = True
            self._serial.rts = True
            time.sleep(0.5)  # Wait for device to initialize
            # Flush any pending data from device (boot output, etc.)
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
        except serial.SerialException as e:
            raise RuntimeError(f"Failed to open serial port {self.port}: {e}")

    def disconnect(self) -> None:
        """Close serial connection."""
        if self._serial:
            try:
                if self._serial.is_open:
                    self._serial.close()
            except Exception:
                pass
            finally:
                self._serial = None
            
            # Give OS time to fully release the port
            import time
            time.sleep(0.2)

    def _send_command(self, command: str, retry_count: int = 1, retry_delay: float = 0.5) -> str:
        """
        Send a command and read response with retry logic.

        Parameters
        ----------
        command: Command to send (will add newline)
        retry_count: Number of times to retry if no response
        retry_delay: Delay in seconds between retries

        Returns
        -------
        Response string (stripped), or empty string if no response
        """
        if not self._serial or not self._serial.is_open:
            raise RuntimeError("Serial port not connected")

        for attempt in range(retry_count):
            try:
                # Clear any existing data from buffer (device boot output)
                if attempt == 0:
                    self._serial.reset_input_buffer()
                
                # Send command
                self._serial.write((command + "\n").encode())
                
                # Read response with timeout
                response = b""
                start_time = time.time()
                end_marker_found = False
                
                while time.time() - start_time < self.timeout:
                    if self._serial.in_waiting > 0:
                        chunk = self._serial.read(self._serial.in_waiting)
                        response += chunk
                        
                        # Look for end markers (newline, OK, ERROR, etc.)
                        if b"\n" in chunk or b"OK" in chunk or b"ERROR" in chunk:
                            end_marker_found = True
                    
                    if end_marker_found and len(response) > 0:
                        break
                    
                    time.sleep(0.01)
                
                # Extract meaningful response lines (filter out boot/debug output)
                decoded = response.decode("utf-8", errors="ignore").strip()
                if decoded:
                    # Filter lines that look like responses (not debug output starting with '[')
                    lines = decoded.split('\n')
                    for line in reversed(lines):  # Start from end (most recent)
                        line_clean = line.strip()
                        if line_clean and not line_clean.startswith('['):
                            return line_clean
                    # If all lines are debug, return the last one anyway
                    return lines[-1].strip() if lines else ""
                
                # If no response, retry after delay
                if attempt < retry_count - 1:
                    time.sleep(retry_delay)
            
            except Exception:
                if attempt < retry_count - 1:
                    time.sleep(retry_delay)
                else:
                    return ""
        
        return ""

    def get_mac_address(self) -> Optional[str]:
        """
        Query device MAC address.
        
        Uses retry logic to handle device startup timing issues.

        Returns
        -------
        MAC address string (e.g. "AA:BB:CC:DD:EE:FF") or None if not found
        """
        try:
            # Try commands most likely to be supported
            commands = [
                ("MAC", 3),       # (command, retry_count)
                ("mac", 3),
                ("get_mac", 2),
                ("MAC_ADDR", 2),
            ]
            
            for cmd, retry_count in commands:
                try:
                    response = self._send_command(cmd, retry_count=retry_count, retry_delay=0.3)
                    if response:
                        # Extract MAC address from response using regex
                        mac_pattern = r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})"
                        match = re.search(mac_pattern, response)
                        if match:
                            return match.group(1).upper()
                except Exception:
                    continue
            
            return None
        except Exception as e:
            raise RuntimeError(f"Failed to read MAC address: {e}")

    def get_device_info(self) -> dict[str, str]:
        """
        Query device information.

        Returns
        -------
        Dictionary with device info (mac, fw_version, etc.)
        """
        info = {}
        
        try:
            # Try to get MAC
            mac = self.get_mac_address()
            if mac:
                info["mac"] = mac
            
            # Try to get firmware version
            try:
                response = self._send_command("version")
                if response:
                    version_pattern = r"(\d+\.\d+\.\d+)"
                    match = re.search(version_pattern, response)
                    if match:
                        info["firmware_version"] = match.group(1)
            except Exception:
                pass
            
            # Try to get device ID/name
            try:
                response = self._send_command("name")
                if response and not response.lower().startswith("unknown"):
                    info["device_name"] = response
            except Exception:
                pass
        
        except Exception:
            pass
        
        return info

    def get_ota_status(self) -> Optional[dict[str, str]]:
        """
        Query OTA boot status from device.
        
        Sends "OTA_STATUS" command and parses response like:
            OTA_STATUS:boot_count=2,boot_loop=N,fw_version=1.3.1
        
        Uses retry logic to handle device boot output contention.
        
        Returns
        -------
        Dict with keys: boot_count, boot_loop, fw_version, or None if query fails
        """
        try:
            # Use retry logic since device might still be printing boot output
            response = self._send_command("OTA_STATUS", retry_count=3, retry_delay=1.0)
            if not response:
                return None
            
            # Handle both exact match and partial match (in case debug output mixed in)
            if "OTA_STATUS" not in response and "boot_count" not in response:
                return None
            
            # Parse "OTA_STATUS:boot_count=2,boot_loop=N,fw_version=1.3.1"
            # or just "boot_count=2,boot_loop=N,fw_version=1.3.1"
            status_dict = {}
            
            # Extract the key=value portion
            if ":" in response:
                kv_part = response.split(":", 1)[1]  # Get everything after first colon
            else:
                kv_part = response  # Already just the key=value part
            
            for kv_pair in kv_part.split(","):
                try:
                    k, v = kv_pair.split("=", 1)
                    status_dict[k.strip()] = v.strip()
                except ValueError:
                    continue  # Skip malformed pairs
            
            return status_dict if status_dict else None
        except Exception as e:
            return None

    def wait_for_boot_complete(self, timeout: float = 15.0) -> bool:
        """
        Wait for device to finish booting and become responsive.
        
        Polls for OTA_STATUS response until it succeeds or timeout expires.
        This indicates the device has fully booted and is responding to commands.
        
        Parameters
        ----------
        timeout: Maximum seconds to wait
        
        Returns
        -------
        True if device became responsive, False otherwise
        """
        import time
        start = time.time()
        
        while time.time() - start < timeout:
            try:
                # Try OTA_STATUS command - this is what we know the firmware implements
                # and it will succeed once device finishes booting
                status = self.get_ota_status()
                if status is not None:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        
        return False

    def reset_boot_counter(self) -> bool:
        """
        Send command to reset the OTA boot counter on device.
        
        Sends "OTA_RESET_BOOT" command to clear boot-loop guard.
        This should be called after flashing if boot-loop is detected.
        
        Returns
        -------
        True if command sent successfully, False otherwise
        """
        try:
            response = self._send_command("OTA_RESET_BOOT")
            # Device might not echo response; just check if port is still open
            return True
        except Exception:
            return False

    def __enter__(self) -> DeviceCommunicator:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        """Context manager exit."""
        self.disconnect()
