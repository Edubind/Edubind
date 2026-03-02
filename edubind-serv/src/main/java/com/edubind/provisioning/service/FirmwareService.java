package com.edubind.provisioning.service;

import com.edubind.provisioning.model.Device;
import com.edubind.provisioning.model.Firmware;
import com.edubind.provisioning.repository.FirmwareRepository;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.Optional;

@Service
@Transactional
public class FirmwareService {

    private final FirmwareRepository repository;

    public FirmwareService(FirmwareRepository repository) {
        this.repository = repository;
    }

    public Firmware register(Firmware firmware) {
        return repository.save(firmware);
    }

    @Transactional(readOnly = true)
    public Optional<Firmware> findById(String id) {
        return repository.findById(id);
    }

    @Transactional(readOnly = true)
    public List<Firmware> findAll() {
        return repository.findAll();
    }

    @Transactional(readOnly = true)
    public List<Firmware> findByBoard(Device.BoardModel board) {
        return repository.findByBoardModel(board);
    }

    /**
     * Returns the firmware artifact as a {@link Resource} for download.
     * The artifact path is stored relative to the working directory or as an absolute path.
     */
    @Transactional(readOnly = true)
    public Resource getArtifact(String firmwareId) {
        Firmware firmware = repository.findById(firmwareId)
                .orElseThrow(() -> new IllegalArgumentException("Firmware not found: " + firmwareId));
        Path path = Paths.get(firmware.getArtifactPath());
        Resource resource = new FileSystemResource(path);
        if (!resource.exists()) {
            throw new IllegalStateException("Firmware artifact not found on disk: " + firmware.getArtifactPath());
        }
        return resource;
    }
}
