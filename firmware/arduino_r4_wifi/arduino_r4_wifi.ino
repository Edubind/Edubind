/*
 * Edubind Firmware – Arduino UNO R4 WiFi
 *
 * Features:
 *  - Reads device config from EEPROM (written by the provisioning station)
 *  - Connects to WiFi using the stored SSID/password
 *  - Periodically sends a heartbeat to the Edubind server
 *  - Accepts a new config blob over serial during provisioning
 *
 * Config blob layout (256 bytes) – must match config_injector.py:
 *   0-3    Magic: 0xED 0xB1 0x1D 0x01
 *   4-67   WiFi SSID (null-terminated, 64 bytes)
 *   68-131 WiFi Password (null-terminated, 64 bytes)
 *   132-211 Server endpoint URL (null-terminated, 80 bytes)
 *   212-243 Device ID (null-terminated, 32 bytes)
 *   244-255 Reserved (zero)
 */

#include <EEPROM.h>
#include <WiFiS3.h>         // Arduino UNO R4 WiFi built-in WiFi library
#include <ArduinoHttpClient.h>

// ─── Config layout constants (must match config_injector.py) ──────────────
#define CONFIG_MAGIC_0  0xED
#define CONFIG_MAGIC_1  0xB1
#define CONFIG_MAGIC_2  0x1D
#define CONFIG_MAGIC_3  0x01
#define CONFIG_BLOB_SIZE      256
#define CONFIG_SSID_OFFSET    4
#define CONFIG_SSID_LEN       64
#define CONFIG_PASS_OFFSET    68
#define CONFIG_PASS_LEN       64
#define CONFIG_ENDPOINT_OFFSET 132
#define CONFIG_ENDPOINT_LEN   80
#define CONFIG_DEVID_OFFSET   212
#define CONFIG_DEVID_LEN      32

// ─── Provisioning serial protocol ─────────────────────────────────────────
static const uint8_t CONFIG_START_MARKER[4] = {0xCF, 0xFA, 0xCE, 0x01};
static const uint8_t CONFIG_ACK[4]          = {0xCF, 0xFA, 0xCE, 0x02};

// ─── Runtime device config (loaded from EEPROM at boot) ───────────────────
struct DeviceConfig {
    char wifiSsid[CONFIG_SSID_LEN];
    char wifiPassword[CONFIG_PASS_LEN];
    char serverEndpoint[CONFIG_ENDPOINT_LEN];
    char deviceId[CONFIG_DEVID_LEN];
    bool valid;
};

static DeviceConfig g_config;

// ─── Firmware version ─────────────────────────────────────────────────────
#define FW_VERSION "1.0.0"
#define HEARTBEAT_INTERVAL_MS 30000UL

// ─── Function prototypes ──────────────────────────────────────────────────
bool loadConfigFromEEPROM(DeviceConfig &cfg);
void saveConfigToEEPROM(const uint8_t *blob);
bool listenForProvisioningConfig();
bool connectWiFi(const char *ssid, const char *password, uint8_t maxAttempts = 20);
void sendHeartbeat(const DeviceConfig &cfg);
void parseServerEndpoint(const char *endpoint, String &host, int &port, String &path);

// ─────────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000);  // Wait for serial (max 3 s)

    Serial.println("[Edubind] Firmware v" FW_VERSION " starting…");

    // Always listen for provisioning config first (5-second window)
    if (listenForProvisioningConfig()) {
        Serial.println("[Edubind] Provisioning config received and saved.");
    }

    if (!loadConfigFromEEPROM(g_config)) {
        Serial.println("[Edubind] WARNING: No valid config in EEPROM. "
                       "Device will not connect until provisioned.");
        return;
    }

    Serial.print("[Edubind] Device ID: ");
    Serial.println(g_config.deviceId);
    Serial.print("[Edubind] Connecting to WiFi SSID: ");
    Serial.println(g_config.wifiSsid);

    if (!connectWiFi(g_config.wifiSsid, g_config.wifiPassword)) {
        Serial.println("[Edubind] WiFi connection failed.");
    } else {
        Serial.print("[Edubind] WiFi connected. IP: ");
        Serial.println(WiFi.localIP());
    }
}

// ─────────────────────────────────────────────────────────────────────────
void loop() {
    static unsigned long lastHeartbeat = 0;

    // Re-check for provisioning at runtime (e.g. re-provisioning)
    if (Serial.available() >= 4) {
        listenForProvisioningConfig();
    }

    if (!g_config.valid) {
        delay(1000);
        return;
    }

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[Edubind] WiFi disconnected. Reconnecting…");
        connectWiFi(g_config.wifiSsid, g_config.wifiPassword, 5);
    }

    unsigned long now = millis();
    if (now - lastHeartbeat >= HEARTBEAT_INTERVAL_MS || lastHeartbeat == 0) {
        lastHeartbeat = now;
        sendHeartbeat(g_config);
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Load device configuration from EEPROM.
// Returns true if the magic header is valid.
bool loadConfigFromEEPROM(DeviceConfig &cfg) {
    uint8_t blob[CONFIG_BLOB_SIZE];
    for (int i = 0; i < CONFIG_BLOB_SIZE; i++) {
        blob[i] = EEPROM.read(i);
    }
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
    cfg.wifiSsid[CONFIG_SSID_LEN - 1]         = '\0';
    cfg.wifiPassword[CONFIG_PASS_LEN - 1]     = '\0';
    cfg.serverEndpoint[CONFIG_ENDPOINT_LEN - 1] = '\0';
    cfg.deviceId[CONFIG_DEVID_LEN - 1]        = '\0';

    cfg.valid = true;
    return true;
}

// ─────────────────────────────────────────────────────────────────────────
// Save a 256-byte config blob to EEPROM.
void saveConfigToEEPROM(const uint8_t *blob) {
    for (int i = 0; i < CONFIG_BLOB_SIZE; i++) {
        EEPROM.update(i, blob[i]);   // update() only writes if value changed (extends EEPROM life)
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Listen on the serial port for a provisioning config blob.
// Waits up to 5 seconds for the start marker.
// Returns true if config was received and saved to EEPROM.
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

        // Check if last 4 bytes match the start marker
        bool match = true;
        for (int i = 0; i < 4; i++) {
            if (markerBuf[(markerIdx - 4 + i) % 4] != CONFIG_START_MARKER[i]) {
                match = false;
                break;
            }
        }
        if (markerIdx < 4) match = false;

        if (match) {
            // Read the 256-byte blob
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
                saveConfigToEEPROM(blob);
                // Send ACK
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
    uint8_t attempts = 0;
    WiFi.disconnect();
    delay(100);
    while (attempts < maxAttempts) {
        WiFi.begin(ssid, password);
        delay(1500);
        if (WiFi.status() == WL_CONNECTED) {
            return true;
        }
        attempts++;
    }
    return false;
}

// ─────────────────────────────────────────────────────────────────────────
// Send a heartbeat POST to the Edubind server.
void sendHeartbeat(const DeviceConfig &cfg) {
    if (WiFi.status() != WL_CONNECTED) return;

    String host;
    int port = 8080;
    String path;
    parseServerEndpoint(cfg.serverEndpoint, host, port, path);

    WiFiClient wifiClient;
    HttpClient http(wifiClient, host, port);

    String body = "{\"deviceId\":\"";
    body += cfg.deviceId;
    body += "\",\"firmware\":\"" FW_VERSION "\"}";

    String endpoint = path.endsWith("/") ? path + "api/devices/heartbeat"
                                         : path + "/api/devices/heartbeat";

    int err = http.post(endpoint, "application/json", body);
    if (err == 0) {
        int status = http.responseStatusCode();
        Serial.print("[Edubind] Heartbeat sent. HTTP ");
        Serial.println(status);
    } else {
        Serial.print("[Edubind] Heartbeat failed: ");
        Serial.println(err);
    }
    http.stop();
}

// ─────────────────────────────────────────────────────────────────────────
// Parse "http://host:port/path" into components.
void parseServerEndpoint(const char *endpoint, String &host, int &port, String &path) {
    String url(endpoint);
    int start = 0;
    if (url.startsWith("http://"))  start = 7;
    if (url.startsWith("https://")) start = 8;
    url = url.substring(start);

    int slashIdx = url.indexOf('/');
    String hostPort = (slashIdx >= 0) ? url.substring(0, slashIdx) : url;
    path = (slashIdx >= 0) ? url.substring(slashIdx) : "/";

    int colonIdx = hostPort.indexOf(':');
    if (colonIdx >= 0) {
        host = hostPort.substring(0, colonIdx);
        port = hostPort.substring(colonIdx + 1).toInt();
    } else {
        host = hostPort;
        port = 80;
    }
}
