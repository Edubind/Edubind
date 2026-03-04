#!/usr/bin/env python3
"""
Diagnostic script to identify connected USB devices and their VID:PID.
Run this to see what devices are actually connected.
"""

try:
    import serial.tools.list_ports as list_ports
    
    print("=" * 60)
    print("USB DEVICE DETECTION DIAGNOSTIC")
    print("=" * 60)
    
    ports = list(list_ports.comports())
    print(f"\nTotal ports found: {len(ports)}\n")
    
    usb_devices = []
    
    if not ports:
        print("No ports detected. Check USB connections and install drivers.")
    else:
        for i, port_info in enumerate(ports, 1):
            print(f"Device #{i}")
            print(f"  Port:        {port_info.device}")
            print(f"  Description: {port_info.description}")
            print(f"  Manufacturer: {port_info.manufacturer}")
            print(f"  Serial:       {port_info.serial_number}")
            if port_info.vid is not None and port_info.pid is not None:
                hex_vid_pid = f"{port_info.vid:04X}:{port_info.pid:04X}"
                print(f"  VID:PID:      {hex_vid_pid} (hex) / {port_info.vid}:{port_info.pid} (dec)")
                usb_devices.append((hex_vid_pid, port_info.device, port_info.description or port_info.manufacturer or "Unknown"))
            else:
                print(f"  VID:PID:      None (not a USB device)")
            print()
    
    print("=" * 60)
    print("KNOWN IDENTIFIERS IN CODE:")
    print("=" * 60)
    from station.device_detector import _BOARD_IDENTIFIERS
    for (vid, pid), board in _BOARD_IDENTIFIERS.items():
        print(f"  {vid:04X}:{pid:04X} → {board}")
    
    print("\n" + "=" * 60)
    print("DETECTION RESULTS:")
    print("=" * 60)
    from station.device_detector import list_ports as detect_ports
    detected = detect_ports()
    print(f"✓ Successfully detected: {len(detected)} device(s)")
    for dev in detected:
        print(f"  - {dev.port}: {dev.board_model}")
    
    if usb_devices:
        unknown = []
        for vid_pid, port, desc in usb_devices:
            if not any(dev.port == port for dev in detected):
                unknown.append((vid_pid, port, desc))
        
        if unknown:
            print(f"\n⚠ {len(unknown)} USB device(s) not recognized:")
            for vid_pid, port, desc in unknown:
                print(f"  - {port} ({desc}): VID:PID {vid_pid}")
                print(f"    Add this to _BOARD_IDENTIFIERS in device_detector.py if it's a supported board.")
    
    print("\n" + "=" * 60)
    print("SYSTEM-LEVEL USB DEVICES (macOS):")
    print("=" * 60)
    import subprocess
    try:
        result = subprocess.run(
            ["system_profiler", "SPUSBDataType"],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout
        # Find Arduino and ESP32 related devices
        lines = output.split('\n')
        in_device = False
        current_device = []
        for line in lines:
            if 'Arduino' in line or 'ESP32' in line or 'CH340' in line or 'CP210' in line:
                in_device = True
            if in_device:
                current_device.append(line)
                if '  $' in line or (line.strip() == '' and current_device):
                    if len(current_device) > 1:
                        print('\n'.join(current_device[:10]))
                        print()
                    current_device = []
                    in_device = False
    except Exception as e:
        print(f"Could not query system USB devices: {e}")
    
except ImportError as e:
    print(f"Error: {e}")
    print("Install pyserial: pip install pyserial")
