# Edubind Firmware

Arduino/ESP32 firmware for Edubind provisioned devices.

## Supported boards

| Board                 | Folder             | FQBN                                  |
|-----------------------|--------------------|---------------------------------------|
| Arduino UNO R4 WiFi   | `arduino_r4_wifi/` | `arduino:renesas_uno:unor4wifi`        |
| ESP32 (generic)       | `esp32/`           | `esp32:esp32:esp32`                   |

## Building

Install [arduino-cli](https://arduino.github.io/arduino-cli/) then:

```bash
# Arduino R4 WiFi
arduino-cli core install arduino:renesas_uno
arduino-cli lib install "ArduinoHttpClient"
arduino-cli compile --fqbn arduino:renesas_uno:unor4wifi arduino_r4_wifi/

# ESP32
arduino-cli core install esp32:esp32
arduino-cli compile --fqbn esp32:esp32:esp32 esp32/
```

## Config injection

The firmware listens on the serial port for a 256-byte config blob during the
first 5 seconds after boot (or whenever `Serial.available() >= 4` at runtime).

The provisioning station (`provisioning-station/`) handles this automatically.

### Config blob layout (256 bytes)

| Offset | Length | Field             |
|--------|--------|-------------------|
| 0      | 4      | Magic `ED B1 1D 01` |
| 4      | 64     | WiFi SSID          |
| 68     | 64     | WiFi Password      |
| 132    | 80     | Server endpoint URL |
| 212    | 32     | Device ID          |
| 244    | 12     | Reserved (zeros)   |

## Heartbeat

Every 30 seconds the device sends a POST to `<serverEndpoint>/api/devices/heartbeat`
with the payload:

```json
{"deviceId": "<id>", "firmware": "1.0.0"}
```
