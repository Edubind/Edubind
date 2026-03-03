package com.edubind.provisioning.repository;

import com.edubind.provisioning.model.ProvisioningJob;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface ProvisioningJobRepository extends JpaRepository<ProvisioningJob, String> {
    List<ProvisioningJob> findByDeviceId(String deviceId);
}
