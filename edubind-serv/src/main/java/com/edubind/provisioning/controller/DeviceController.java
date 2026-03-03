package com.edubind.provisioning.controller;

import com.edubind.provisioning.model.Device;
import com.edubind.provisioning.service.DeviceService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/devices")
public class DeviceController {

    private final DeviceService service;

    public DeviceController(DeviceService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<Device> register(@Valid @RequestBody Device device) {
        return ResponseEntity.status(HttpStatus.CREATED).body(service.register(device));
    }

    @GetMapping
    public List<Device> list() {
        return service.findAll();
    }

    @GetMapping("/{id}")
    public ResponseEntity<Device> get(@PathVariable String id) {
        return service.findById(id)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @PutMapping("/{id}/status")
    public ResponseEntity<Device> updateStatus(@PathVariable String id,
                                               @RequestParam Device.Status status) {
        try {
            return ResponseEntity.ok(service.updateStatus(id, status));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.notFound().build();
        }
    }

    @PutMapping("/{deviceId}/profile/{profileId}")
    public ResponseEntity<Device> assignProfile(@PathVariable String deviceId,
                                                @PathVariable String profileId) {
        try {
            return ResponseEntity.ok(service.assignProfile(deviceId, profileId));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.notFound().build();
        }
    }

    /**
     * Returns the config blob for a device (used by the provisioning station to inject config).
     * The blob is a JSON object containing the device's assigned profile settings.
     */
    @GetMapping("/{id}/config")
    public ResponseEntity<?> getConfig(@PathVariable String id) {
        return service.findById(id)
                .map(device -> {
                    if (device.getAssignedProfile() == null) {
                        return ResponseEntity.ok().body((Object) java.util.Map.of(
                                "deviceId", device.getDeviceId(),
                                "model", device.getModel()
                        ));
                    }
                    return ResponseEntity.ok().body((Object) java.util.Map.of(
                            "deviceId", device.getDeviceId(),
                            "model", device.getModel(),
                            "wifiSsid", device.getAssignedProfile().getWifiSsid() != null
                                    ? device.getAssignedProfile().getWifiSsid() : "",
                            "wifiPassword", device.getAssignedProfile().getWifiPassword() != null
                                    ? device.getAssignedProfile().getWifiPassword() : "",
                            "serverEndpoint", device.getAssignedProfile().getServerEndpoint() != null
                                    ? device.getAssignedProfile().getServerEndpoint() : "",
                            "options", device.getAssignedProfile().getOptionsJson() != null
                                    ? device.getAssignedProfile().getOptionsJson() : "{}"
                    ));
                })
                .orElse(ResponseEntity.notFound().build());
    }
}
