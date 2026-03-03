package com.edubind.provisioning.controller;

import com.edubind.provisioning.model.ProvisioningJob;
import com.edubind.provisioning.service.ProvisioningJobService;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/provisioning/jobs")
public class ProvisioningJobController {

    private final ProvisioningJobService service;

    public ProvisioningJobController(ProvisioningJobService service) {
        this.service = service;
    }

    record StartJobRequest(@NotBlank String deviceId,
                           @NotBlank String firmwareId,
                           @NotBlank String operator,
                           String stationHostname) {}

    record ReportRequest(ProvisioningJob.Result result,
                         String logs,
                         String configHash) {}

    @PostMapping
    public ResponseEntity<ProvisioningJob> start(@RequestBody StartJobRequest req) {
        try {
            ProvisioningJob job = service.startJob(
                    req.deviceId(), req.firmwareId(), req.operator(), req.stationHostname());
            return ResponseEntity.status(HttpStatus.CREATED).body(job);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().build();
        }
    }

    @GetMapping
    public List<ProvisioningJob> list(@RequestParam(required = false) String deviceId) {
        return deviceId != null ? service.findByDevice(deviceId) : service.findAll();
    }

    @GetMapping("/{id}")
    public ResponseEntity<ProvisioningJob> get(@PathVariable String id) {
        return service.findById(id)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @PostMapping("/{id}/report")
    public ResponseEntity<ProvisioningJob> report(@PathVariable String id,
                                                   @RequestBody ReportRequest req) {
        try {
            return ResponseEntity.ok(service.reportResult(id, req.result(), req.logs(), req.configHash()));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.notFound().build();
        }
    }
}
