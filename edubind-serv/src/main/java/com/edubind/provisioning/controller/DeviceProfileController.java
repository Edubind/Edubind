package com.edubind.provisioning.controller;

import com.edubind.provisioning.model.DeviceProfile;
import com.edubind.provisioning.service.DeviceProfileService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/profiles")
public class DeviceProfileController {

    private final DeviceProfileService service;

    public DeviceProfileController(DeviceProfileService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<DeviceProfile> create(@Valid @RequestBody DeviceProfile profile) {
        return ResponseEntity.status(HttpStatus.CREATED).body(service.create(profile));
    }

    @GetMapping
    public List<DeviceProfile> list() {
        return service.findAll();
    }

    @GetMapping("/{id}")
    public ResponseEntity<DeviceProfile> get(@PathVariable String id) {
        return service.findById(id)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @PutMapping("/{id}")
    public ResponseEntity<DeviceProfile> update(@PathVariable String id,
                                                @Valid @RequestBody DeviceProfile profile) {
        try {
            return ResponseEntity.ok(service.update(id, profile));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.notFound().build();
        }
    }
}
