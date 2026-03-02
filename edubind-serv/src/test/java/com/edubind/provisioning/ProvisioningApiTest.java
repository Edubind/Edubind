package com.edubind.provisioning;

import com.edubind.provisioning.model.Device;
import com.edubind.provisioning.model.DeviceProfile;
import com.edubind.provisioning.model.Firmware;
import com.edubind.provisioning.model.ProvisioningJob;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Map;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ProvisioningApiTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper mapper;

    @Test
    void registerDevice_thenListIt() throws Exception {
        Device device = new Device();
        device.setDeviceId("ESP32-TEST-001");
        device.setModel(Device.BoardModel.ESP32);
        device.setHardwareRevision("v1.0");
        device.setSite("site-A");

        mvc.perform(post("/api/devices")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(mapper.writeValueAsString(device)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.deviceId").value("ESP32-TEST-001"))
                .andExpect(jsonPath("$.status").value("PROVISIONING_PENDING"));

        mvc.perform(get("/api/devices"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.deviceId == 'ESP32-TEST-001')]").exists());
    }

    @Test
    void createProfile_thenAssignToDevice() throws Exception {
        // Create profile
        DeviceProfile profile = new DeviceProfile();
        profile.setName("school-profile-test");
        profile.setWifiSsid("SchoolWifi");
        profile.setWifiPassword("secret123");
        profile.setServerEndpoint("http://edubind-serv:8080");

        String profileResponse = mvc.perform(post("/api/profiles")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(mapper.writeValueAsString(profile)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();

        String profileId = mapper.readTree(profileResponse).get("id").asText();

        // Register device
        Device device = new Device();
        device.setDeviceId("R4-WIFI-ASSIGN-001");
        device.setModel(Device.BoardModel.ARDUINO_R4_WIFI);

        String deviceResponse = mvc.perform(post("/api/devices")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(mapper.writeValueAsString(device)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();

        String deviceId = mapper.readTree(deviceResponse).get("deviceId").asText();

        // Assign profile to device
        mvc.perform(put("/api/devices/" + deviceId + "/profile/" + profileId))
                .andExpect(status().isOk());

        // Fetch device config
        mvc.perform(get("/api/devices/" + mapper.readTree(deviceResponse).get("id").asText() + "/config"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.wifiSsid").value("SchoolWifi"));
    }

    @Test
    void duplicateDeviceId_shouldReturn409() throws Exception {
        Device device = new Device();
        device.setDeviceId("ESP32-DUP-001");
        device.setModel(Device.BoardModel.ESP32);

        mvc.perform(post("/api/devices")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(mapper.writeValueAsString(device)))
                .andExpect(status().isCreated());

        // Second registration with same deviceId should return 409 Conflict
        mvc.perform(post("/api/devices")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(mapper.writeValueAsString(device)))
                .andExpect(status().isConflict());
    }

    @Test
    void listFirmwaresByBoard() throws Exception {
        Firmware fw = new Firmware();
        fw.setVersion("1.0.0");
        fw.setBoardModel(Device.BoardModel.ESP32);
        fw.setArtifactPath("/tmp/esp32_v1.0.0.bin");
        fw.setSha256Hash("abc123");
        fw.setReleaseChannel(Firmware.ReleaseChannel.STABLE);

        mvc.perform(post("/api/firmwares")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(mapper.writeValueAsString(fw)))
                .andExpect(status().isCreated());

        mvc.perform(get("/api/firmwares?board=ESP32"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.version == '1.0.0')]").exists());
    }
}
