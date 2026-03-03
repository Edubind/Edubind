package com.edubind.provisioning.repository;

import com.edubind.provisioning.model.DeviceProfile;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface DeviceProfileRepository extends JpaRepository<DeviceProfile, String> {
    Optional<DeviceProfile> findByName(String name);
}
