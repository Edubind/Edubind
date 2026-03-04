/*
 * mac_reporter.ino – Provisioning helper sketch for Edubind devices
 *
 * This sketch is uploaded BEFORE the production firmware.  It provides:
 *   1. MAC address reporting over Serial (text command "MAC")
 *   2. Binary config-blob injection into EEPROM (512 bytes, ACK protocol)
 *
 * ── Binary injection protocol ──
 *   Station → device : 4-byte marker  0xCF 0xFA 0xCE 0x01
 *   Station → device : 512-byte config blob
 *   Device  → station: 4-byte ACK     0xCF 0xFA 0xCE 0x02
 *
 * No WiFi connection is attempted — the sketch is pure serial + EEPROM,
 * so provisioning never blocks and the 64-byte UART buffer cannot overflow.
 *
 * Supported boards:
 *  - Arduino R4 WiFi  (ARDUINO_ARCH_RENESAS)
 *  - ESP32 / ESP32-S3 (ESP32 / ESP32_S3)
 *  - ESP8266           (ESP8266)
 */

// ── Config blob constants (must match config_injector.py / eeprom_store.h) ──
static const uint8_t CONFIG_MARKER[4] = {0xCF, 0xFA, 0xCE, 0x01};
static const uint8_t CONFIG_ACK[4]    = {0xCF, 0xFA, 0xCE, 0x02};
static const uint16_t CONFIG_BLOB_SIZE = 512;

// Primary magic that must be at offset 0 of a valid blob
static const uint8_t BLOB_MAGIC[4] = {0xED, 0xB1, 0x1D, 0x01};

// ── Persistent state for binary reception (survives across loop() calls) ──
static uint8_t  markerMatchIdx     = 0;
static bool     receivingBlob      = false;
static uint8_t  blobBuf[CONFIG_BLOB_SIZE];
static uint16_t blobBytesReceived  = 0;

// ── EEPROM helpers ──────────────────────────────────────────────────────────
#include <EEPROM.h>

static bool storeConfigBlob(const uint8_t* blob) {
  // Validate primary magic
  if (blob[0] != BLOB_MAGIC[0] || blob[1] != BLOB_MAGIC[1] ||
      blob[2] != BLOB_MAGIC[2] || blob[3] != BLOB_MAGIC[3]) {
    return false;
  }
  for (uint16_t i = 0; i < CONFIG_BLOB_SIZE; i++) {
    EEPROM.write(i, blob[i]);
  }
  return true;
}

// ── Board-specific MAC reading ──────────────────────────────────────────────
#ifdef ARDUINO_ARCH_RENESAS
  #include <WiFiS3.h>
#elif defined(ESP32) || defined(ESP32_S3)
  #include <WiFi.h>
  #include <esp_mac.h>
#elif defined(ESP8266)
  #include <ESP8266WiFi.h>
#endif

static void printMACAddress() {
  byte mac[6];
#ifdef ARDUINO_ARCH_RENESAS
  WiFi.macAddress(mac);
#elif defined(ESP32) || defined(ESP32_S3)
  esp_read_mac(mac, ESP_MAC_WIFI_STA);
#elif defined(ESP8266)
  WiFi.macAddress(mac);
#else
  memset(mac, 0, 6);
#endif
  char buf[18];
  snprintf(buf, sizeof(buf), "%02X:%02X:%02X:%02X:%02X:%02X",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  Serial.println(buf);
}

// ── Serial handler (binary + text multiplexed) ─────────────────────────────
static void handleSerial() {
  while (Serial.available() > 0) {
    uint8_t b = (uint8_t)Serial.read();

    // ── Binary blob reception ──
    if (receivingBlob) {
      blobBuf[blobBytesReceived++] = b;
      if (blobBytesReceived >= CONFIG_BLOB_SIZE) {
        receivingBlob     = false;
        blobBytesReceived = 0;
        markerMatchIdx    = 0;
        Serial.println(F("[DBG] blob_done"));
        if (storeConfigBlob(blobBuf)) {
          Serial.println(F("[DBG] magic_ok - sending ACK"));
          Serial.write(CONFIG_ACK, 4);
          Serial.flush();
        } else {
          Serial.println(F("[DBG] magic_fail"));
        }
      }
      continue;
    }

    // ── Marker detection ──
    if (b == CONFIG_MARKER[markerMatchIdx]) {
      markerMatchIdx++;
      if (markerMatchIdx == 4) {
        receivingBlob     = true;
        blobBytesReceived = 0;
        markerMatchIdx    = 0;
        Serial.println(F("[DBG] marker_ok - waiting for 512b"));
      }
      continue;
    }
    if (markerMatchIdx > 0) {
      markerMatchIdx = (b == CONFIG_MARKER[0]) ? 1 : 0;
      if (markerMatchIdx) continue;
    }

    // ── Text command accumulation ──
    static char cmdBuf[32];
    static uint8_t cmdIdx = 0;
    char ch = (char)b;
    if (ch == '\n' || ch == '\r') {
      if (cmdIdx > 0) {
        cmdBuf[cmdIdx] = '\0';
        if (strcmp(cmdBuf, "MAC") == 0 || strcmp(cmdBuf, "mac") == 0 ||
            strcmp(cmdBuf, "get_mac") == 0 || strcmp(cmdBuf, "MAC_ADDR") == 0) {
          printMACAddress();
        } else if (strcmp(cmdBuf, "version") == 0) {
          Serial.println("prov-helper-2.0");
        } else if (strcmp(cmdBuf, "PING") == 0 || strcmp(cmdBuf, "ping") == 0) {
          Serial.println("PONG");
        }
        cmdIdx = 0;
      }
    } else if (cmdIdx < sizeof(cmdBuf) - 1) {
      cmdBuf[cmdIdx++] = ch;
    }
  }
}

// ── Arduino entry points ────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(300);
  // Print MAC once on boot so the station can read it immediately
  printMACAddress();
  Serial.println(F("[DBG] READY – prov-helper-2.0"));
}

void loop() {
  handleSerial();
}
