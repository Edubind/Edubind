package com.edubind.provisioning.model;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.Instant;

@Entity
@Table(name = "provisioning_jobs")
public class ProvisioningJob {

    public enum Result {
        PENDING, SUCCESS, FAILED
    }

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private String id;

    @NotNull
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "device_id", nullable = false)
    private Device device;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "firmware_id")
    private Firmware firmware;

    /** SHA-256 hash of the config blob used during this job */
    private String configHash;

    /** Login of the operator who ran the job */
    @NotBlank
    private String operator;

    /** Hostname of the provisioning station */
    private String stationHostname;

    @Enumerated(EnumType.STRING)
    private Result result = Result.PENDING;

    @Column(columnDefinition = "TEXT")
    private String logs;

    @Column(nullable = false, updatable = false)
    private Instant startedAt = Instant.now();

    private Instant completedAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public Device getDevice() { return device; }
    public void setDevice(Device device) { this.device = device; }

    public Firmware getFirmware() { return firmware; }
    public void setFirmware(Firmware firmware) { this.firmware = firmware; }

    public String getConfigHash() { return configHash; }
    public void setConfigHash(String configHash) { this.configHash = configHash; }

    public String getOperator() { return operator; }
    public void setOperator(String operator) { this.operator = operator; }

    public String getStationHostname() { return stationHostname; }
    public void setStationHostname(String stationHostname) { this.stationHostname = stationHostname; }

    public Result getResult() { return result; }
    public void setResult(Result result) { this.result = result; }

    public String getLogs() { return logs; }
    public void setLogs(String logs) { this.logs = logs; }

    public Instant getStartedAt() { return startedAt; }
    public Instant getCompletedAt() { return completedAt; }
    public void setCompletedAt(Instant completedAt) { this.completedAt = completedAt; }
}
