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

On first run, you will be prompted to login with your credentials. The application will:
- Store your backend URL and JWT token securely in `~/.edubind/provisioning.json`
- Auto-connect on restart using the stored token
- Warn you when tokens are expiring soon

### 2. Configuration & Authentication

**Features (as of v2.0):**
- JWT Bearer authentication with the backend
- Persistent settings (Backend URL, operator name, auth tokens)
- Local audit logging in `~/.edubind/audit.log` (CSV export available)
- Automatic token refresh on 401 errors
- Built-in token expiry monitoring

**New modules:**
- `station/config_manager.py` – Persistent configuration storage
- `station/auth_manager.py` – JWT login and token management  
- `station/audit_logger.py` – Local audit trail for provisioning jobs

### 3. Flash firmware

Install [arduino-cli](https://arduino.github.io/arduino-cli/) then see
`firmware/README.md` for per-board build instructions.

## Provisioning workflow

1. **Login** with your Edubind credentials (first run only)
2. **Connect** to the backend – automatic with stored token
3. **Plug in** an Arduino R4 WiFi or ESP32 via USB
4. **Refresh ports** – the board is detected automatically
5. **Select firmware** from the catalogue
6. **Enter Device ID** (e.g. `ESP32-SCHOOL-A-001`)
7. **Click "Start Provisioning"** – the station will:
   - Register the device in the backend
   - Create a provisioning job
   - Download the firmware artifact
   - Flash it via `arduino-cli`
   - Inject the WiFi/endpoint config over serial
   - Report the result (SUCCESS/FAILED) to the backend
