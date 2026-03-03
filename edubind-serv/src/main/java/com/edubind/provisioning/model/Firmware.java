package com.edubind.provisioning.model;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.Instant;

@Entity
@Table(name = "firmwares")
public class Firmware {

    public enum ReleaseChannel {
        STABLE, BETA, RC
    }

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private String id;

    @NotBlank
    private String version;

    @NotNull
    @Enumerated(EnumType.STRING)
    private Device.BoardModel boardModel;

    /** Path or URL to the compiled .hex / .bin artifact */
    @NotBlank
    private String artifactPath;

    /** SHA-256 hash of the artifact for integrity verification */
    @NotBlank
    private String sha256Hash;

    @Enumerated(EnumType.STRING)
    private ReleaseChannel releaseChannel = ReleaseChannel.STABLE;

    private String description;

    @Column(nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getVersion() { return version; }
    public void setVersion(String version) { this.version = version; }

    public Device.BoardModel getBoardModel() { return boardModel; }
    public void setBoardModel(Device.BoardModel boardModel) { this.boardModel = boardModel; }

    public String getArtifactPath() { return artifactPath; }
    public void setArtifactPath(String artifactPath) { this.artifactPath = artifactPath; }

    public String getSha256Hash() { return sha256Hash; }
    public void setSha256Hash(String sha256Hash) { this.sha256Hash = sha256Hash; }

    public ReleaseChannel getReleaseChannel() { return releaseChannel; }
    public void setReleaseChannel(ReleaseChannel releaseChannel) { this.releaseChannel = releaseChannel; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public Instant getCreatedAt() { return createdAt; }
}
