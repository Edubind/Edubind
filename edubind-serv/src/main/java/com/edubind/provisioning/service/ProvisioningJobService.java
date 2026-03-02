package com.edubind.provisioning.service;

import com.edubind.provisioning.model.Device;
import com.edubind.provisioning.model.Firmware;
import com.edubind.provisioning.model.ProvisioningJob;
import com.edubind.provisioning.repository.DeviceRepository;
import com.edubind.provisioning.repository.FirmwareRepository;
import com.edubind.provisioning.repository.ProvisioningJobRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

@Service
@Transactional
public class ProvisioningJobService {

    private final ProvisioningJobRepository jobRepository;
    private final DeviceRepository deviceRepository;
    private final FirmwareRepository firmwareRepository;

    public ProvisioningJobService(ProvisioningJobRepository jobRepository,
                                  DeviceRepository deviceRepository,
                                  FirmwareRepository firmwareRepository) {
        this.jobRepository = jobRepository;
        this.deviceRepository = deviceRepository;
        this.firmwareRepository = firmwareRepository;
    }

    public ProvisioningJob startJob(String deviceId, String firmwareId, String operator,
                                    String stationHostname) {
        Device device = deviceRepository.findByDeviceId(deviceId)
                .orElseThrow(() -> new IllegalArgumentException("Device not found: " + deviceId));

        Firmware firmware = firmwareRepository.findById(firmwareId)
                .orElseThrow(() -> new IllegalArgumentException("Firmware not found: " + firmwareId));

        ProvisioningJob job = new ProvisioningJob();
        job.setDevice(device);
        job.setFirmware(firmware);
        job.setOperator(operator);
        job.setStationHostname(stationHostname);
        job.setResult(ProvisioningJob.Result.PENDING);

        return jobRepository.save(job);
    }

    public ProvisioningJob reportResult(String jobId, ProvisioningJob.Result result,
                                        String logs, String configHash) {
        ProvisioningJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new IllegalArgumentException("Job not found: " + jobId));

        job.setResult(result);
        job.setLogs(logs);
        job.setConfigHash(configHash);
        job.setCompletedAt(Instant.now());

        // Update device status accordingly
        Device device = job.getDevice();
        device.setStatus(result == ProvisioningJob.Result.SUCCESS
                ? Device.Status.PROVISIONED
                : Device.Status.FAILED);
        deviceRepository.save(device);

        return jobRepository.save(job);
    }

    @Transactional(readOnly = true)
    public Optional<ProvisioningJob> findById(String id) {
        return jobRepository.findById(id);
    }

    @Transactional(readOnly = true)
    public List<ProvisioningJob> findAll() {
        return jobRepository.findAll();
    }

    @Transactional(readOnly = true)
    public List<ProvisioningJob> findByDevice(String deviceId) {
        return jobRepository.findByDeviceId(deviceId);
    }
}
