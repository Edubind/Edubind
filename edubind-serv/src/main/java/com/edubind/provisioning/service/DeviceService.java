package com.edubind.provisioning.service;

import com.edubind.provisioning.model.Device;
import com.edubind.provisioning.model.DeviceProfile;
import com.edubind.provisioning.repository.DeviceProfileRepository;
import com.edubind.provisioning.repository.DeviceRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

@Service
@Transactional
public class DeviceService {

    private final DeviceRepository deviceRepository;
    private final DeviceProfileRepository profileRepository;

    public DeviceService(DeviceRepository deviceRepository,
                         DeviceProfileRepository profileRepository) {
        this.deviceRepository = deviceRepository;
        this.profileRepository = profileRepository;
    }

    public Device register(Device device) {
        if (deviceRepository.existsByDeviceId(device.getDeviceId())) {
            throw new IllegalArgumentException(
                    "Device already registered: " + device.getDeviceId());
        }
        device.setStatus(Device.Status.PROVISIONING_PENDING);
        return deviceRepository.save(device);
    }

    @Transactional(readOnly = true)
    public Optional<Device> findById(String id) {
        return deviceRepository.findById(id);
    }

    @Transactional(readOnly = true)
    public Optional<Device> findByDeviceId(String deviceId) {
        return deviceRepository.findByDeviceId(deviceId);
    }

    @Transactional(readOnly = true)
    public List<Device> findAll() {
        return deviceRepository.findAll();
    }

    public Device updateStatus(String id, Device.Status status) {
        Device device = deviceRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Device not found: " + id));
        device.setStatus(status);
        return deviceRepository.save(device);
    }

    public Device assignProfile(String deviceId, String profileId) {
        Device device = deviceRepository.findByDeviceId(deviceId)
                .orElseThrow(() -> new IllegalArgumentException("Device not found: " + deviceId));
        DeviceProfile profile = profileRepository.findById(profileId)
                .orElseThrow(() -> new IllegalArgumentException("Profile not found: " + profileId));
        device.setAssignedProfile(profile);
        return deviceRepository.save(device);
    }
}
