/*
 * Edubind Firmware – ESP32
 *
 * Features:
 *  - Reads device config from NVS (Preferences) partition
 *    and accepts a config blob via serial during provisioning
 *  - Connects to WiFi using the stored SSID/password
 *  - Periodically sends a heartbeat to the Edubind server
 *
 * Config blob layout (256 bytes) – must match config_injector.py:
 *   0-3    Magic: 0xED 0xB1 0x1D 0x01
 *   4-67   WiFi SSID (null-terminated, 64 bytes)
 *   68-131 WiFi Password (null-terminated, 64 bytes)
 *   132-211 Server endpoint URL (null-terminated, 80 bytes)
 *   212-243 Device ID (null-terminated, 32 bytes)
 *   244-255 Reserved (zero)
 */

#include <Preferences.h>
#include <WiFi.h>
#include <HTTPClient.h>

// ─── Config layout constants (must match config_injector.py) ──────────────
#define CONFIG_MAGIC_0  0xED
#define CONFIG_MAGIC_1  0xB1
#define CONFIG_MAGIC_2  0x1D
#define CONFIG_MAGIC_3  0x01
#define CONFIG_BLOB_SIZE       256
#define CONFIG_SSID_OFFSET     4
#define CONFIG_SSID_LEN        64
#define CONFIG_PASS_OFFSET     68
#define CONFIG_PASS_LEN        64
#define CONFIG_ENDPOINT_OFFSET 132
#define CONFIG_ENDPOINT_LEN    80
#define CONFIG_DEVID_OFFSET    212
#define CONFIG_DEVID_LEN       32

// ─── Provisioning serial protocol ─────────────────────────────────────────
static const uint8_t CONFIG_START_MARKER[4] = {0xCF, 0xFA, 0xCE, 0x01};
static const uint8_t CONFIG_ACK[4]          = {0xCF, 0xFA, 0xCE, 0x02};

// ─── Runtime device config ────────────────────────────────────────────────
struct DeviceConfig {
    char wifiSsid[CONFIG_SSID_LEN];
    char wifiPassword[CONFIG_PASS_LEN];
    char serverEndpoint[CONFIG_ENDPOINT_LEN];
    char deviceId[CONFIG_DEVID_LEN];
    bool valid;
};

static DeviceConfig g_config;
static Preferences g_prefs;

// ─── Firmware version ─────────────────────────────────────────────────────
#define FW_VERSION "1.0.0"
#define HEARTBEAT_INTERVAL_MS 30000UL
#define NVS_NAMESPACE "edubind"
#define NVS_KEY_BLOB  "cfg_blob"

// ─── Function prototypes ──────────────────────────────────────────────────
bool loadConfigFromNVS(DeviceConfig &cfg);
void saveConfigToNVS(const uint8_t *blob);
bool listenForProvisioningConfig();
bool connectWiFi(const char *ssid, const char *password, uint8_t maxAttempts = 20);
void sendHeartbeat(const DeviceConfig &cfg);

// ─────────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(500);  // Give serial time to initialise

    Serial.println("[Edubind ESP32] Firmware v" FW_VERSION " starting…");

    // Always listen for provisioning config first (5-second window)
    if (listenForProvisioningConfig()) {
        Serial.println("[Edubind ESP32] Provisioning config received and saved.");
    }

    if (!loadConfigFromNVS(g_config)) {
        Serial.println("[Edubind ESP32] WARNING: No valid config in NVS. "
                       "Device will not connect until provisioned.");
        return;
    }

    Serial.print("[Edubind ESP32] Device ID: ");
    Serial.println(g_config.deviceId);
    Serial.print("[Edubind ESP32] Connecting to WiFi: ");
    Serial.println(g_config.wifiSsid);

    if (!connectWiFi(g_config.wifiSsid, g_config.wifiPassword)) {
        Serial.println("[Edubind ESP32] WiFi connection failed.");
    } else {
        Serial.print("[Edubind ESP32] WiFi connected. IP: ");
        Serial.println(WiFi.localIP());
    }
}

// ─────────────────────────────────────────────────────────────────────────
void loop() {
    static unsigned long lastHeartbeat = 0;

    // Re-check for provisioning at runtime (e.g. re-provisioning)
    if (Serial.available() >= 4) {
        if (listenForProvisioningConfig()) {
            loadConfigFromNVS(g_config);
            if (g_config.valid) {
                connectWiFi(g_config.wifiSsid, g_config.wifiPassword, 5);
            }
        }
    }

    if (!g_config.valid) {
        delay(1000);
        return;
    }

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[Edubind ESP32] WiFi lost. Reconnecting…");
        connectWiFi(g_config.wifiSsid, g_config.wifiPassword, 5);
    }

    unsigned long now = millis();
    if (now - lastHeartbeat >= HEARTBEAT_INTERVAL_MS || lastHeartbeat == 0) {
        lastHeartbeat = now;
        sendHeartbeat(g_config);
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Load device configuration from NVS (Preferences).
bool loadConfigFromNVS(DeviceConfig &cfg) {
    g_prefs.begin(NVS_NAMESPACE, true);  // read-only
    size_t len = g_prefs.getBytesLength(NVS_KEY_BLOB);
    if (len != CONFIG_BLOB_SIZE) {
        g_prefs.end();
        cfg.valid = false;
        return false;
    }
    uint8_t blob[CONFIG_BLOB_SIZE];
    g_prefs.getBytes(NVS_KEY_BLOB, blob, CONFIG_BLOB_SIZE);
    g_prefs.end();

    if (blob[0] != CONFIG_MAGIC_0 || blob[1] != CONFIG_MAGIC_1 ||
        blob[2] != CONFIG_MAGIC_2 || blob[3] != CONFIG_MAGIC_3) {
        cfg.valid = false;
        return false;
    }

    memcpy(cfg.wifiSsid,       blob + CONFIG_SSID_OFFSET,     CONFIG_SSID_LEN);
    memcpy(cfg.wifiPassword,   blob + CONFIG_PASS_OFFSET,     CONFIG_PASS_LEN);
    memcpy(cfg.serverEndpoint, blob + CONFIG_ENDPOINT_OFFSET, CONFIG_ENDPOINT_LEN);
    memcpy(cfg.deviceId,       blob + CONFIG_DEVID_OFFSET,    CONFIG_DEVID_LEN);

    // Ensure null-termination
    cfg.wifiSsid[CONFIG_SSID_LEN - 1]          = '\0';
    cfg.wifiPassword[CONFIG_PASS_LEN - 1]      = '\0';
    cfg.serverEndpoint[CONFIG_ENDPOINT_LEN - 1] = '\0';
    cfg.deviceId[CONFIG_DEVID_LEN - 1]          = '\0';

    cfg.valid = true;
    return true;
}

// ─────────────────────────────────────────────────────────────────────────
// Save a 256-byte config blob to NVS (Preferences).
void saveConfigToNVS(const uint8_t *blob) {
    g_prefs.begin(NVS_NAMESPACE, false);  // read-write
    g_prefs.putBytes(NVS_KEY_BLOB, blob, CONFIG_BLOB_SIZE);
    g_prefs.end();
}

// ─────────────────────────────────────────────────────────────────────────
// Listen on the serial port for a provisioning config blob (5-second window).
bool listenForProvisioningConfig() {
    unsigned long deadline = millis() + 5000UL;
    uint8_t markerBuf[4] = {0, 0, 0, 0};
    uint8_t markerIdx = 0;

    while (millis() < deadline) {
        if (!Serial.available()) {
            delay(10);
            continue;
        }
        uint8_t b = (uint8_t)Serial.read();
        markerBuf[markerIdx % 4] = b;
        markerIdx++;

        bool match = true;
        for (int i = 0; i < 4; i++) {
            if (markerBuf[(markerIdx - 4 + i) % 4] != CONFIG_START_MARKER[i]) {
                match = false;
                break;
            }
        }
        if (markerIdx < 4) match = false;

        if (match) {
            uint8_t blob[CONFIG_BLOB_SIZE];
            int received = 0;
            unsigned long blobDeadline = millis() + 3000UL;
            while (received < CONFIG_BLOB_SIZE && millis() < blobDeadline) {
                if (Serial.available()) {
                    blob[received++] = (uint8_t)Serial.read();
                } else {
                    delay(5);
                }
            }
            if (received == CONFIG_BLOB_SIZE) {
                saveConfigToNVS(blob);
                Serial.write(CONFIG_ACK, 4);
                Serial.flush();
                return true;
            }
        }
    }
    return false;
}

// ─────────────────────────────────────────────────────────────────────────
// Connect to WiFi with retry logic.
bool connectWiFi(const char *ssid, const char *password, uint8_t maxAttempts) {
    WiFi.disconnect(true);
    delay(100);
    WiFi.begin(ssid, password);
    uint8_t attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < maxAttempts) {
        delay(1000);
        attempts++;
        Serial.print('.');
    }
    Serial.println();
    return WiFi.status() == WL_CONNECTED;
}

// ─────────────────────────────────────────────────────────────────────────
// Send a heartbeat POST to the Edubind server.
void sendHeartbeat(const DeviceConfig &cfg) {
    if (WiFi.status() != WL_CONNECTED) return;

    String url(cfg.serverEndpoint);
    if (!url.endsWith("/")) url += "/";
    url += "api/devices/heartbeat";

    HTTPClient http;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");

    String body = "{\"deviceId\":\"";
    body += cfg.deviceId;
    body += "\",\"firmware\":\"" FW_VERSION "\"}";

    int code = http.POST(body);
    Serial.print("[Edubind ESP32] Heartbeat → HTTP ");
    Serial.println(code);
    http.end();
}
