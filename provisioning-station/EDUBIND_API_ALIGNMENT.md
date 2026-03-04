# Provisioning Station — Backend API Alignment

## Overview

The provisioning-station has been updated to **fully align with the Edubind backend API** (Java/Spring Boot running on RPi 5) as documented in the provided architecture specification.

---

## Key Changes

### 1. **Authentication** – JWT Bearer Tokens

**File:** `station/auth_manager.py`

- **Login endpoint:** `POST /api/auth/login`
  - Request: `{ "username": "...", "password": "..." }`
  - Response: `{ "token": "...", "role": "...", "expiresIn": 86400000 }`
  
- **Token refresh:** `POST /api/auth/refresh`
  - Automatic retry on 401 responses
  
- **Expiration field:** Changed from `expires_in` (seconds, old) to `expiresIn` (milliseconds, new)

**Impact:** Station now authenticates using the same JWT mechanism as the Chrome extension. Token is persisted across sessions and automatically refreshed.

---

### 2. **Device Registration** – PSK Generation

**File:** `station/backend_client.py`

- **Endpoint:** `POST /api/devices/register`
  - Request: `{ "macAddress": "AA:BB:CC:DD:EE:FF", "roomId": 1 }`
  - Response: `{ "deviceId": 1, "macAddress": "...", "pskKey": "a1b2c3d4e5..." }`
  
**New workflow:**
1. Operator provides MAC address + Room ID
2. Backend generates a unique 128-bit PSK (Pre-Shared Key) for CoAP encryption
3. PSK is returned **exactly once** (operator must copy, cannot retrieve later)
4. Station injects PSK into device EEPROM along with WiFi credentials

**Impact:** Devices are now cryptographically bound to the backend via AES-128-GCM encryption on CoAP channels.

---

### 3. **Firmware Management** – OTA API

**File:** `station/backend_client.py`

- **List firmwares:** `GET /api/ota/firmwares`
  - Response: `[ { "version": "1.0.0", "sha256Hash": "...", "sizeBytes": ..., ... } ]`
  
- **Download firmware:** `GET /api/ota/firmware/{version}`
  - Downloads binary directly by version string
  - No explicit "firmware_id" required (version is the identifier)

**Changes from old API:**
- Old: `GET /api/firmwares` with optional `board` filter
- New: `GET /api/ota/firmwares` (unified endpoint)
- Old: `GET /api/firmwares/{firmware_id}/download`
- New: `GET /api/ota/firmware/{version}` (simpler URI)

---

### 4. **Config Injection** – PSK + Endpoint

**File:** `station/config_injector.py`

**Updated EEPROM layout (256 bytes):**

| Offset | Size | Field                     | Edubind        |
|--------|------|---------------------------|----------------|
| 0–3    | 4    | Magic: 0xED 0xB1 0x1D 0x01 | Fixed          |
| 4–67   | 64   | WiFi SSID                 | From Operator  |
| 68–131 | 64   | WiFi Password             | From Operator  |
| 132–195| 64   | CoAP Server Endpoint      | RPi5:5683      |
| 196–219| 24   | Device MAC Address        | (verification) |
| 220–251| 32   | PSK Key (hex)             | **From Backend** |
| 252–255| 4    | Reserved                  | (zeros)        |

**New:** PSK key is now injected alongside WiFi credentials and MAC address.

**DeviceConfig dataclass updated:**
```python
@dataclass
class DeviceConfig:
    mac_address: str       # (was device_id)
    wifi_ssid: str
    wifi_password: str
    server_endpoint: str   # CoAP endpoint, e.g., "192.168.1.10:5683"
    psk_key: str          # AES-128 key in hex format
```

**Impact:** Devices now authenticate to backend securely with both WiFi credentials and cryptographic identity.

---

### 5. **UI Changes** – MAC + Room ID

**File:** `station/ui/app.py`

**Old provisioning inputs:**
- Device ID (user-defined)
- Site (location)

**New provisioning inputs:**
- **MAC Address** ← MAC of the Arduino (scanned/noted by operator)
- **Room ID** ← Room number from backend (dropdown from backend room list)
- WiFi SSID (global, stored in Settings)
- WiFi Password (global, stored in Settings)
- Firmware version (from backend OTA listings)

**Workflow:**
1. Login to backend (JWT)
2. Fill in MAC address + Room ID
3. Select firmware
4. Click "Start Provisioning"
   - Device registered in backend (MAC + Room ID → receives PSK)
   - Firmware downloaded
   - Config injected (WiFi + PSK + endpoint)
   - Local audit logged

**Impact:** Operator now works with device MAC addresses and backend-managed room assignments. No more custom device IDs.

---

### 6. **Persistent Settings** – Backend URL + WiFi Config

**File:** `station/config_manager.py`

**Stored in `~/.edubind/provisioning.json`:**
```json
{
  "backend_url": "http://10.191.14.110:8080",
  "operator_name": "tutor1",
  "wifi_ssid": "SchoolNetwork-5G",
  "wifi_password": "P@ssw0rd123",
  "jwt_token": "eyJ...",
  "jwt_expires_at": "2026-03-03T14:00:00"
}
```

**New fields:**
- `wifi_ssid` – WiFi network name (global for all devices in provisioning batch)
- `wifi_password` – WiFi password (global)

**Impact:** Operator doesn't need to enter WiFi credentials for every device. Settings persist across restarts.

---

### 7. **Audit Trail** – Local Logging (No Online Job API)

**File:** `station/audit_logger.py` & `station/ui/app.py`

**Changed:** Provisioning jobs are **logged locally only** (not synced to backend).

**Local audit log** (`~/.edubind/audit.log`):
```json
{ "timestamp": "2026-03-03T10:00:00", "device_id": "AA:BB:CC:DD:EE:FF", "firmware_version": "1.0.1", "operator": "tutor1", "result": "SUCCESS", "error_reason": null, ... }
```

**Why:** The backend API spec doesn't provide a `/api/provisioning/jobs` endpoint for the Android/Station fleet provisioning workflow. Audit stays local; fleet health is tracked via device heartbeats instead.

---

## End-to-End Flow (Updated)

```
┌─────────────────┐
│ Provisioning    │
│ Station (Python)│
└────────┬────────┘
         │
         ├─ 1. POST /api/auth/login (JWT)
         │   ↓ Response: Bearer token
         │
         ├─ 2. GET /api/ota/firmwares
         │   ↓ Response: List of firmware versions
         │
         ├─ 3. Operator enters MAC + Room ID
         │
         ├─ 4. POST /api/devices/register {mac, room}
         │   ↓ Response: { deviceId, pskKey }
         │
         ├─ 5. GET /api/ota/firmware/{version}
         │   ↓ Download binary
         │
         ├─ 6. flash_firmware() to USB device
         │   ↓ Arduino now booted, listening for config
         │
         ├─ 7. inject_config() via serial
         │   • Sends: WiFi SSID + password + PSK + endpoint
         │   • EEPROM written
         │   ↓ Device sends ACK
         │
         └─ 8. Log locally + display success
             ↓
             Arduino setup() completes
             │
             ├─ Read EEPROM config
             ├─ WiFi.connect()
             ├─ CoAP.register() with PSK auth
             └─ Send heartbeat → Backend marks ONLINE
```

---

## API Endpoints Summary

| Method | Endpoint                    | Role   | Provisioning Use                   |
|--------|-----------------------------|---------|------------------------------------|
| POST   | `/api/auth/login`           | Public | Initial authentication             |
| POST   | `/api/auth/refresh`         | Bearer | Token refresh on 401               |
| GET    | `/api/ota/firmwares`        | Bearer | List available firmware versions   |
| GET    | `/api/ota/firmware/{version}` | Bearer | Download firmware binary           |
| GET    | `/api/devices`              | Bearer | List registered devices (optional) |
| POST   | `/api/devices/register`     | Bearer | Register new device, get PSK       |
| DELETE | `/api/devices/{id}`         | Admin  | Remove device (if needed)          |
| PUT    | `/api/devices/{id}/room`    | Admin  | Move device to different room      |

---

## Configuration Checklist

- [x] **Backend URL:** Update in UI Settings or `~/.edubind/provisioning.json`
- [x] **Operator credentials:** Use valid login (must exist in backend users table)
- [x] **WiFi SSID + Password:** Set once in Settings, reused for all devices
- [x] **Rooms:** Created in backend (must exist before provisioning)
- [x] **Firmware:** Uploaded to backend OTA storage (`/api/ota/upload`)
- [x] **Arduino device:** Assembled, USB connected, IDE drivers installed

---

## Testing Steps

1. **Login test**
   ```
   Start app → Enter backend URL + credentials → Click "Connect"
   Expected: Status shows "✓ Connected", firmware list loads
   ```

2. **Device registration test**
   ```
   Enter MAC address + Room ID → Click provisioning
   Expected: Backend returns PSK, shown in log
   ```

3. **EEPROM verification**
   ```
   Unplug device after provisioning → Wait 30s → Power on
   Expected: Device reconnects automatically using EEPROM config
   ```

4. **Backend heartbeat verification**
   ```
   Device boots → Check backend /api/devices list
   Expected: Device status = "ONLINE", lastSeen updated
   ```

---

## Files Modified

- `station/auth_manager.py` – JWT token lifecycle
- `station/backend_client.py` – REST API paths aligned with backend spec
- `station/config_manager.py` – WiFi SSID/password persistent storage
- `station/config_injector.py` – EEPROM layout includes PSK
- `station/ui/app.py` – MAC + Room ID provisioning workflow
- `INTEGRATION.md` – Architecture documentation updated

---

**Status:** ✅ Provisioning station now fully integrated with Edubind backend API.  
**Next:** End-to-end testing with physical hardware.
