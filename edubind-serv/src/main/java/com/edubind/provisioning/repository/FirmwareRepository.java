package com.edubind.provisioning.repository;

import com.edubind.provisioning.model.Device;
import com.edubind.provisioning.model.Firmware;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface FirmwareRepository extends JpaRepository<Firmware, String> {
    List<Firmware> findByBoardModel(Device.BoardModel boardModel);
}
