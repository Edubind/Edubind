# Integration Guide: Provisioning Station ↔ Arduino Firmware

**How the Python provisioning-station (fleet initialization) integrates with the Arduino R4 WiFi / ESP32 firmware.**

---

## Overview

```
┌─────────────────────────────┐
│  Provisioning Station       │
│  (Python Desktop App)       │
│                             │
│  • Detects Arduino via USB  │
│  • Flashes firmware binary  │
│  • Injects EEPROM config    │
│  • Reports to backend       │
└─────────────┬───────────────┘
              │ USB/Serial
              │ (9600 baud)
              ▼
┌─────────────────────────────┐
│  Arduino Device             │
│  (Renesas-RA / ESP32)       │
│                             │
│  1. Powers on               │
│  2. setup() runs            │
│  3. Reads EEPROM config     │
│  4. Boot sequence           │
│  5. loop() runs forever     │
└─────────────────────────────┘
              │
              ▼
         WiFi / CoAP
              │
              ▼
┌─────────────────────────────┐
│  edubind-serv (Java)        │
│  Backend & Device Registry  │
└─────────────────────────────┘
```

---

## 1. EEPROM Configuration Format

The provisioning-station injects a **256-byte config blob** via serial. The firmware expects this format:

### Config Blob Structure

```
Offset  Size    Field                       Example
──────  ──────  ─────────────────────────   ─────────────────────
0       4       Magic: 0xED 0xB1 0x1D 0x01  [fixed header]
4       64      WiFi SSID (UTF-8)           "SchoolNetwork-5G"
68      64      WiFi Password (UTF-8)       "P@ssw0rd123"
132     64      Server Endpoint URL (UTF-8) "192.168.1.10:5683"
196     24      MAC Address (UTF-8)         "AA:BB:CC:DD:EE:FF"
220     32      PSK Key (hex)               "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
252     4       Reserved (zeros)            [padding]
────────────────────────────────────────────────────────────────
TOTAL:  256 bytes
```

**Python code injection** (in `station/config_injector.py`):
```python
DeviceConfig(
    mac_address="AA:BB:CC:DD:EE:FF",
    wifi_ssid="SchoolNetwork-5G",
    wifi_password="P@ssw0rd123",
    server_endpoint="192.168.1.10:5683",
    psk_key="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
)
```

**Arduino code reading** (in firmware `eeprom_store.cpp`):
```cpp
struct EepromConfig {
  uint8_t magic[4];        // 0xED, 0xB1, 0x1D, 0x01
  char ssid[64];
  char password[64];
  char endpoint[64];
  char mac_address[24];
  char psk_key[32];
  uint8_t reserved[4];
};
```

### EEPROM Map (Arduino firmware)

| Offset | Length | Purpose                   | Managed By          |
|--------|--------|---------------------------|---------------------|
| 0–3    | 4      | `"EDBI"` magic (config)   | Provisioning Station |
| 4–67   | 64     | WiFi SSID                 | Provisioning Station |
| 68–131 | 64     | WiFi password             | Provisioning Station |
| 132–195| 64     | Server endpoint           | Provisioning Station |
| 196–219| 24     | MAC Address               | Provisioning Station |
| 220–251| 32     | PSK Key                   | Provisioning Station |
| 252–255| 4      | Reserved                  | (unused)             |
| 256+   | ?      | OTA boot counter, PSK...  | Firmware internals   |

---

## 2. Serial Handshake Protocol

When the provisioning-station injects config, it uses a **4-step handshake** on the USB serial port:

### Step-by-Step

#### **Step 1: Station initiates**
```
Station → Device:  0xCF 0xFA 0xCE 0x01
          (4 bytes, magic marker)

Timeout: 5 seconds
Arduino: Detects this pattern, enables config-accept mode
```

#### **Step 2: Station sends config blob**
```
Station → Device:  [256 bytes: config structure]

Timeout: 10 seconds
Arduino: Write to EEPROM, verify SHA-256
```

#### **Step 3: Device acknowledges**
```
Device → Station:  0xCF 0xFA 0xCE 0x02
          (4 bytes, ACK marker)

Timeout: 15 seconds
Station: Waits for ACK; if timeout, retry
```

#### **Step 4: Device returns SHA-256 of config**
```
Device → Station:  [32 bytes: SHA-256 hash]

Station: Verifies config integrity, reports SUCCESS/FAILED
```

### Firmware Implementation

In your Arduino `setup()`, add code like:

```cpp
void setup() {
    Serial.begin(115200);
    
    // ... other setup code ...
    
    // Check for provisioning mode
    if (waitForProvisioningMarker(5000)) {  // 5 sec timeout
        uint8_t config[256];
        if (receiveConfigBlob(config, 10000)) {  // 10 sec timeout
            if (storeConfigInEeprom(config)) {
                sendAckMarker();
                sendSha256Hash(config, 256);
                delay(2000);  // Allow station to finish logging
                // Config is ready for use
            }
        }
    }
    
    // ... proceed with normal setup (WiFi, CoAP, etc.) ...
    loadConfigFromEeprom(&myConfig);
    connectWiFi(myConfig.ssid, myConfig.password);
}
```

---

## 3. Integration Points

### 3.1 Python → Backend (Device Registration)

**provisioning-station** calls:
```python
backend_client.register_device(
    mac_address="AA:BB:CC:DD:EE:FF",
    room_id=1
)
# Response: {"deviceId": 1, "macAddress": "AA:BB:CC:DD:EE:FF", "pskKey": "a1b2..."}
```

**Backend** creates device record in database and generates PSK.

---

### 3.2 Firmware Flashing & Configuration

**provisioning-station** calls:
1. Downloads firmware from OTA API (`/api/ota/firmwares`)
2. Flashes using `arduino-cli` / `esptool.py`.
3. Over serial, writes WiFi, MAC, Server CoAP endpoint, and PSK into EEPROM.

**Station** builds `DeviceConfig` and injects via serial.

---

### 3.3 Arduino Boot Sequence

After device receives configuration via serial:

```cpp
// Step 1: Read EEPROM config (already written by station)
// Step 2: WiFi connects using injected SSID/password
// Step 3: Device registers with backend via CoAP PSK
// Step 4: loop() runs, sends periodic heartbeats
```

The **PSK (Pre-Shared Key)** injected into EEPROM is used for CoAP encryption:
- All CoAP messages are encrypted with `AES-128-GCM` using this PSK
- Backend stores the PSK in `security_credentials` table (indexed by MAC address)
- Device authenticates over CoAP with MAC in custom option 2078 + encrypted payload

---

## 4. Configuration Strategy

Your solution uses an **offline-first approach** aligned with the Edubind architecture:

### **Provisioning Workflow**
1. **Device Registration**: Station calls `POST /api/devices/register` with MAC + Room ID
   - Response: Device DB record with **PSK key** (returned once / must be stored)
2. **Config Injection**: Station injects into EEPROM:
   - WiFi SSID/Password (for network access)
   - CoAP Server Endpoint (RPi 5 IP:port)
   - MAC Address (for CoAP authentication)
   - PSK Key (AES-128 symmetric key for CoAP encryption)
3. **Device Boot**: Arduino reads EEPROM, connects WiFi, then CoAP-registers with backend
4. **CoAP Authentication**: Device uses MAC + PSK for all encrypted CoAP messages

### **Alignment with Edubind API**

From the backend documentation:

```
POST /api/devices/register
{
  "macAddress": "AA:BB:CC:DD:EE:FF",
  "roomId": 1
}

Response 201:
{
  "deviceId": 1,
  "macAddress": "AA:BB:CC:DD:EE:FF",
  "pskKey": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
  "message": "Device registered successfully. Flash this PSK key into the device firmware. This key will NOT be shown again."
}
```

**The provisioning-station** now:
1. Takes MAC + Room ID from operator UI
2. Calls `register_device()` to get PSK
3. Injects PSK (along with WiFi & CoAP endpoint) into EEPROM
4. Device boots and uses PSK for all CoAP `AES-128-GCM` encryption

This perfectly aligns with Edubind's **2-tier authentication**:
- **HTTP tier** (Station ↔ Backend): JWT Bearer tokens
- **CoAP tier** (Arduino ↔ Backend): AES-128-GCM + MAC binding

---

## 5. Troubleshooting

### Scenario: Device doesn't accept config via serial

**Checklist:**
1. ✅ Arduino is powered & USB connected
2. ✅ Correct FQBN in provisioning settings (e.g., `arduino:renesas_uno:unor4wifi`)
3. ✅ Serial port detected (refresh ports in UI)
4. ✅ Baud rate is 9600 or compatible
5. ✅ Firmware `setup()` is listening for magic marker `0xCF 0xFA 0xCE 0x01`
6. ✅ No other serial application reading from the port

**Debug:**
```bash
# Manual test with pyserial
python3
>>> import serial
>>> s = serial.Serial('/dev/ttyACM0', 9600)
>>> s.write(bytes([0xCF, 0xFA, 0xCE, 0x01]))
>>> s.read(4)  # Should see ACK after config sent
```

---

### Scenario: Config written but device doesn't use WiFi credentials

**Checklist:**
1. ✅ EEPROM write succeeded (check step 3 ACK)
2. ✅ `loadConfigFromEeprom()` is called in `setup()`
3. ✅ WiFi SSID/password are null-terminated strings
4. ✅ Firmware is not using hardcoded fallback credentials

**Debug:**
```cpp
// Add to setup() after loadConfigFromEeprom()
Serial.print("Loaded SSID: ");
Serial.println(eepromConfig.ssid);
Serial.print("Loaded endpoint: ");
Serial.println(eepromConfig.endpoint);
```

---

## 6. API Endpoints Used by Provisioning Station

Based on the Edubind backend API documentation:

### Authentication

```bash
POST /api/auth/login
{
  "username": "operator1",
  "password": "password123"
}
→ Response: { "token": "...", "role": "ADMIN", "expiresIn": 86400000 }
```

All subsequent requests include: `Authorization: Bearer <token>`

### Device Registration

```bash
POST /api/devices/register
{
  "macAddress": "AA:BB:CC:DD:EE:FF",
  "roomId": 1
}
→ Response: { "deviceId": 1, "pskKey": "a1b2c3d4e5..." }
```

### Firmware Management

```bash
GET /api/ota/firmwares
→ Response: [ { "version": "1.0.0", "sha256Hash": "...", ... } ]

GET /api/ota/firmware/1.0.0
→ Download binary to local disk
```

### Device Listing

```bash
GET /api/devices
→ Response: [ { "id": 1, "macAddress": "...", "status": "ONLINE", ... } ]
```

---

## 7. Provisioning Timeline

```
T0: Operator launches provisioning-station GUI
    ├─ Login with username + password (JWT)
    ├─ UI shows available USB ports & firmwares
    └─ Operator fills Device MAC + Room ID

T1: Operator clicks "Start Provisioning"
    ├─ Backend: POST /api/devices/register
    ├─ Response: PSK key (one-time secret)
    └─ PSK is stored in memory for injection

T2: Station downloads firmware
    ├─ GET /api/ota/firmwares (list all)
    ├─ GET /api/ota/firmware/version (download binary)
    └─ Binary saved to /tmp/firmware.bin

T3: Station flashes firmware
    ├─ arduino-cli compile + upload
    ├─ Device reset after upload
    └─ Firmware's setup() ready to receive config

T4: Station injects config via serial
    ├─ Send marker: 0xCF 0xFA 0xCE 0x01
    ├─ Send 256-byte blob (WiFi + PSK + endpoint)
    ├─ Device writes to EEPROM
    └─ Device sends ACK + SHA-256

T5: Station audits locally
    ├─ AuditLogger records event
    └─ JSON-lines: ~/.edubind/audit.log

T6: Device boots with injected config
    ├─ Reads EEPROM: SSID, PSK, CoAP endpoint
    ├─ WiFi.begin(ssid, password)
    ├─ CoAP client connects with PSK authentication
    └─ Device → Backend: heartbeat (CoAP POST /heartbeat)

T7: Backend marks device online
    ├─ Receives heartbeat (MAC + PSK verification)
    ├─ Updates device.status = "ONLINE"
    ├─ Room manager: device visible in UI
    └─ Ready for QR code distribution
```

### For Provisioning Station Operators

1. **Prepare the backend first**
   - Ensure backend is running and accessible
   - Register Classroom/Site in backend database

2. **Flash firmware before provisioning**
   - Compile firmware with `pio run -e uno_r4_wifi`
   - Upload to device: `pio run -e uno_r4_wifi --target upload`
   - Device should show on USB ports list

3. **Provision immediately after flash**
   - Device's `setup()` waits for config on first boot
   - If it boots without config, fallback to hardcoded defaults (poor production practice)

4. **Verify success**
   - Station shows "✓ Provisioning completed successfully"
   - Device heartbeat appears in backend within 5-10 seconds
   - Your fleet manager shows device online

### For Firmware Developers

1. **Implement the handshake correctly**
   - Use exact magic markers (`0xCF 0xFA 0xCE 0x01` / `0x02`)
   - Respect timeouts (5s marker, 10s config, 15s ACK)
   - Return SHA-256 for verification

2. **Persist config in EEPROM**
   - Store in well-defined offset (avoid conflicts with OTA counter)
   - Validate magic byte on every `setup()`

3. **Fall back gracefully**
   - If no EEPROM config, use compile-time defaults or enter fallback mode
   - Log which config source was used (debug output)

4. **Security considerations**
   - WiFi password is stored in clear text in EEPROM
   - Future: Encrypt EEPROM, use TLS certificates, implement secure provisioning

---

## 8. Alignment with Your Solution

| Requirement | Provisioning Station | Arduino Firmware | Status |
|---|---|---|---|
| USB device detection | ✅ `device_detector.py` | ← receives | ✅ Aligned |
| Firmware flash | ✅ `flasher.py` (arduino-cli) | upload target | ✅ Aligned |
| Config injection | ✅ `config_injector.py` | `setup()` listener | ✅ Aligned |
| Serial protocol | ✅ 256-byte blob + handshake | reads + verifies | ✅ Aligned |
| Backend registration | ✅ `BackendClient.register_device()` | (not responsible) | ✅ Separate concern |
| Audit trail | ✅ `audit_logger.py` (local + backend) | (emits heartbeat) | ✅ Separate concern |
| JWT auth | ✅ `AuthManager` (station↔backend) | (N/A for device) | ✅ Out of scope |

---

## Next Steps

1. **Test with R4 WiFi board**
   - Compile & upload reference firmware from `Projet_IoT/`
   - Run provisioning-station: `python main.py`
   - Provision one device end-to-end

2. **Validate EEPROM persistence**
   - Unplug device, power it off 30 seconds
   - Power on; verify device reconnects using EEPROM config
   - No re-provisioning needed

3. **Extend to fleet provisioning**
   - Test 5, 10, 100 devices in sequence
   - Monitor backend for device onboarding
   - Check audit log for success rates

4. **Hardening (Phase 3+)**
   - Implement retry logic in flasher.py (stage 2 robustness)
   - Add EEPROM encryption for WiFi password
   - Implement OTA firmware updates via provisioning station

---

**Status:** ✅ Integration points documented and aligned.  
All pieces are ready for end-to-end provisioning workflow.
