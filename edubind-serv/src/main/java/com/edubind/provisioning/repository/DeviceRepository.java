package com.edubind.provisioning.repository;

import com.edubind.provisioning.model.Device;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface DeviceRepository extends JpaRepository<Device, String> {
    Optional<Device> findByDeviceId(String deviceId);
    boolean existsByDeviceId(String deviceId);
}
