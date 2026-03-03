package com.edubind.provisioning.service;

import com.edubind.provisioning.model.DeviceProfile;
import com.edubind.provisioning.repository.DeviceProfileRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

@Service
@Transactional
public class DeviceProfileService {

    private final DeviceProfileRepository repository;

    public DeviceProfileService(DeviceProfileRepository repository) {
        this.repository = repository;
    }

    public DeviceProfile create(DeviceProfile profile) {
        return repository.save(profile);
    }

    @Transactional(readOnly = true)
    public Optional<DeviceProfile> findById(String id) {
        return repository.findById(id);
    }

    @Transactional(readOnly = true)
    public List<DeviceProfile> findAll() {
        return repository.findAll();
    }

    public DeviceProfile update(String id, DeviceProfile updated) {
        DeviceProfile existing = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Profile not found: " + id));
        existing.setName(updated.getName());
        existing.setWifiSsid(updated.getWifiSsid());
        existing.setWifiPassword(updated.getWifiPassword());
        existing.setServerEndpoint(updated.getServerEndpoint());
        existing.setOptionsJson(updated.getOptionsJson());
        return repository.save(existing);
    }
}
