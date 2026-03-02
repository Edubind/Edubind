package com.edubind.provisioning.model;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.Instant;

@Entity
@Table(name = "devices")
public class Device {

    public enum Status {
        PROVISIONING_PENDING, PROVISIONED, FAILED, DECOMMISSIONED
    }

    public enum BoardModel {
        ARDUINO_R4_WIFI, ESP32
    }

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private String id;

    @NotBlank
    @Column(unique = true, nullable = false)
    private String deviceId;

    @NotNull
    @Enumerated(EnumType.STRING)
    private BoardModel model;

    private String hardwareRevision;

    private String site;

    @Column(name = "device_group")
    private String group;

    @Enumerated(EnumType.STRING)
    private Status status = Status.PROVISIONING_PENDING;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "profile_id")
    private DeviceProfile assignedProfile;

    @Column(nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    private Instant updatedAt = Instant.now();

    @PreUpdate
    void onUpdate() {
        this.updatedAt = Instant.now();
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }

    public BoardModel getModel() { return model; }
    public void setModel(BoardModel model) { this.model = model; }

    public String getHardwareRevision() { return hardwareRevision; }
    public void setHardwareRevision(String hardwareRevision) { this.hardwareRevision = hardwareRevision; }

    public String getSite() { return site; }
    public void setSite(String site) { this.site = site; }

    public String getGroup() { return group; }
    public void setGroup(String group) { this.group = group; }

    public Status getStatus() { return status; }
    public void setStatus(Status status) { this.status = status; }

    public DeviceProfile getAssignedProfile() { return assignedProfile; }
    public void setAssignedProfile(DeviceProfile assignedProfile) { this.assignedProfile = assignedProfile; }

    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }
}
