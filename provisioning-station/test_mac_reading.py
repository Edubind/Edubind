#!/usr/bin/env python3
"""
Test script for MAC address reading from devices.
This demonstrates how the DeviceCommunicator works.
"""

from station.device_communicator import DeviceCommunicator

def test_device_communication():
    """Test device communication capabilities."""
    print("=" * 60)
    print("DEVICE COMMUNICATOR TEST")
    print("=" * 60)
    print()
    print("Available methods:")
    print("  - get_mac_address():  Read MAC address from device")
    print("  - get_device_info():  Read device information")
    print()
    print("Usage example:")
    print()
    print("  from station.device_communicator import DeviceCommunicator")
    print()
    print("  try:")
    print("      with DeviceCommunicator('/dev/ttyUSB0') as comm:")
    print("          mac = comm.get_mac_address()")
    print("          print(f'MAC: {mac}')")
    print()
    print("          info = comm.get_device_info()")
    print("          print(f'Device Info: {info}')")
    print()
    print("  except Exception as e:")
    print("      print(f'Error: {e}')")
    print()
    print("=" * 60)
    print()
    print("Features:")
    print("  ✓ Serial communication with configurable baudrate")
    print("  ✓ Automatic MAC address parsing from device response")
    print("  ✓ Support for multiple command formats (mac, MAC, get_mac, etc.)")
    print("  ✓ Firmware version detection")
    print("  ✓ Device name/ID detection")
    print("  ✓ Context manager support for safe connection handling")
    print("  ✓ Configurable timeouts and error handling")
    print()

if __name__ == "__main__":
    test_device_communication()
