"""
test_audit_logger.py – Unit tests for AuditLogger.
"""

import json
import tempfile
from pathlib import Path

import pytest

from station.audit_logger import AuditLogger


class TestAuditLogger:
    @pytest.fixture
    def temp_audit_path(self) -> Path:
        """Create temporary audit log file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            temp_path = Path(f.name)
        yield temp_path
        temp_path.unlink(missing_ok=True)

    @pytest.fixture
    def audit_logger(self, temp_audit_path: Path) -> AuditLogger:
        """Create AuditLogger with temporary file."""
        return AuditLogger(temp_audit_path)

    def test_init(self, audit_logger: AuditLogger) -> None:
        """Test AuditLogger initialization."""
        assert audit_logger.audit_path is not None

    def test_log_job_creates_entry(self, audit_logger: AuditLogger, temp_audit_path: Path) -> None:
        """Test logging a job creates an entry."""
        job_info = {
            "device_id": "DEVICE-001",
            "firmware_version": "1.0.0",
            "operator": "john",
            "result": "SUCCESS",
        }
        
        audit_logger.log_job(job_info)
        
        # Verify file has content
        assert temp_audit_path.stat().st_size > 0

    def test_log_job_json_format(self, audit_logger: AuditLogger, temp_audit_path: Path) -> None:
        """Test logged entries are valid JSON lines."""
        job_info = {
            "device_id": "DEVICE-002",
            "firmware_version": "2.0.0",
            "operator": "jane",
            "result": "FAILED",
            "error_reason": "Flash timeout",
        }
        
        audit_logger.log_job(job_info)
        
        with open(temp_audit_path, "r") as f:
            line = f.readline()
            entry = json.loads(line)
            assert entry["device_id"] == "DEVICE-002"
            assert entry["result"] == "FAILED"
            assert "timestamp" in entry

    def test_get_recent_jobs(self, audit_logger: AuditLogger) -> None:
        """Test retrieving recent jobs."""
        for i in range(5):
            audit_logger.log_job({
                "device_id": f"DEVICE-{i}",
                "firmware_version": "1.0.0",
                "operator": "test",
                "result": "SUCCESS",
            })
        
        jobs = audit_logger.get_recent_jobs(limit=10)
        assert len(jobs) == 5
        # Should be in reverse order (newest first)
        assert jobs[0]["device_id"] == "DEVICE-4"

    def test_get_recent_jobs_limit(self, audit_logger: AuditLogger) -> None:
        """Test get_recent_jobs respects limit."""
        for i in range(20):
            audit_logger.log_job({
                "device_id": f"DEVICE-{i}",
                "firmware_version": "1.0.0",
                "operator": "test",
                "result": "SUCCESS",
            })
        
        jobs = audit_logger.get_recent_jobs(limit=5)
        assert len(jobs) == 5

    def test_export_csv(self, audit_logger: AuditLogger) -> None:
        """Test exporting logs to CSV."""
        for i in range(3):
            audit_logger.log_job({
                "device_id": f"DEVICE-{i}",
                "firmware_version": "1.0.0",
                "operator": "test",
                "result": "SUCCESS" if i % 2 == 0 else "FAILED",
            })
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            csv_path = f.name
        
        try:
            count = audit_logger.export_csv(csv_path)
            assert count == 3
            
            with open(csv_path, "r") as f:
                content = f.read()
                assert "device_id" in content
                assert "DEVICE-0" in content
        finally:
            Path(csv_path).unlink(missing_ok=True)

    def test_get_stats(self, audit_logger: AuditLogger) -> None:
        """Test statistics generation."""
        jobs_data = [
            ("DEVICE-1", "SUCCESS"),
            ("DEVICE-1", "SUCCESS"),
            ("DEVICE-2", "FAILED"),
            ("DEVICE-3", "SUCCESS"),
        ]
        
        for device_id, result in jobs_data:
            audit_logger.log_job({
                "device_id": device_id,
                "firmware_version": "1.0.0",
                "operator": "test",
                "result": result,
            })
        
        stats = audit_logger.get_stats()
        
        assert stats["total_jobs"] == 4
        assert stats["successful"] == 3
        assert stats["failed"] == 1
        assert stats["success_rate"] == 75.0
        assert stats["unique_devices"] == 3

    def test_get_stats_empty(self, audit_logger: AuditLogger) -> None:
        """Test statistics with no jobs."""
        stats = audit_logger.get_stats()
        
        assert stats["total_jobs"] == 0
        assert stats["successful"] == 0
        assert stats["failed"] == 0
        assert stats["success_rate"] == 0.0
