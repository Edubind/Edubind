# Edubind – Arduino Fleet Provisioning System

End-to-end provisioning solution for Arduino R4 WiFi and ESP32 devices.

## Architecture

```
┌──────────────────────────┐        REST API        ┌───────────────────────┐
│  Provisioning Station    │ ◄────────────────────► │  edubind-serv         │
│  (Python desktop app)    │   http://localhost:8080 │  (Spring Boot / Java) │
│                          │                         │                       │
│  - Detects USB boards    │                         │  - Device registry    │
│  - Downloads firmware    │                         │  - Firmware catalogue │
│  - Flashes via           │                         │  - Provisioning jobs  │
│    arduino-cli           │                         │  - Audit log          │
│  - Injects WiFi config   │                         │                       │
│  - Reports result        │                         │  DB: H2 (dev)         │
└──────────────────────────┘                         └───────────────────────┘
            │ USB/Serial
            ▼
┌──────────────────────────┐
│  Arduino Device          │
│  (R4 WiFi or ESP32)      │
│                          │
│  - Accepts config blob   │
│  - Stores in EEPROM/NVS  │
│  - Connects to WiFi      │
│  - Sends heartbeats      │
└──────────────────────────┘
```

## Components

| Component | Path | Language |
|---|---|---|
| Desktop provisioning app | `provisioning-station/` | Python 3.9+ |
| Backend API | `edubind-serv/` | Java 17 / Spring Boot 3 |
| Arduino R4 WiFi firmware | `firmware/arduino_r4_wifi/` | C/C++ (Arduino) |

## Quick start

### 1. Run the provisioning station

```bash
cd provisioning-station
pip install -r requirements.txt
python main.py
```

### 2. Flash firmware

Install [arduino-cli](https://arduino.github.io/arduino-cli/) then see
`firmware/README.md` for per-board build instructions.

## Provisioning workflow

1. **Connect** the provisioning station to the backend (enter URL + operator name)
2. **Plug in** an Arduino R4 WiFi or ESP32 via USB
3. **Refresh ports** – the board is detected automatically
4. **Select firmware** from the catalogue
5. **Enter Device ID** (e.g. `ESP32-SCHOOL-A-001`)
6. **Click "Start Provisioning"** – the station will:
   - Register the device in the backend
   - Create a provisioning job
   - Download the firmware artifact
   - Flash it via `arduino-cli`
   - Inject the WiFi/endpoint config over serial
   - Report the result (SUCCESS/FAILED) to the backend
