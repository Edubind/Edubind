package com.edubind.provisioning.controller;

import com.edubind.provisioning.model.Device;
import com.edubind.provisioning.model.Firmware;
import com.edubind.provisioning.service.FirmwareService;
import jakarta.validation.Valid;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/firmwares")
public class FirmwareController {

    private final FirmwareService service;

    public FirmwareController(FirmwareService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<Firmware> register(@Valid @RequestBody Firmware firmware) {
        return ResponseEntity.status(HttpStatus.CREATED).body(service.register(firmware));
    }

    @GetMapping
    public List<Firmware> list(@RequestParam(required = false) Device.BoardModel board) {
        return board != null ? service.findByBoard(board) : service.findAll();
    }

    @GetMapping("/{id}")
    public ResponseEntity<Firmware> get(@PathVariable String id) {
        return service.findById(id)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping("/{id}/download")
    public ResponseEntity<Resource> download(@PathVariable String id) {
        try {
            Resource resource = service.getArtifact(id);
            return ResponseEntity.ok()
                    .header(HttpHeaders.CONTENT_DISPOSITION,
                            "attachment; filename=\"" + resource.getFilename() + "\"")
                    .contentType(MediaType.APPLICATION_OCTET_STREAM)
                    .body(resource);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.notFound().build();
        } catch (IllegalStateException e) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).build();
        }
    }
}
