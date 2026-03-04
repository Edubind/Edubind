"""
audit_logger.py – Audit logging for provisioning jobs.

Records all provisioning operations locally for traceability and reporting.
Stores in ~/.edubind/audit.log (JSON-lines format).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


class AuditLogger:
    """Records provisioning job audit trail locally and optionally to backend."""

    DEFAULT_AUDIT_DIR = Path.home() / ".edubind"
    DEFAULT_AUDIT_FILE = DEFAULT_AUDIT_DIR / "audit.log"
    RETENTION_DAYS = 30

    def __init__(self, audit_path: Optional[Path] = None) -> None:
        """
        Parameters
        ----------
        audit_path: Path to audit log file. Defaults to ~/.edubind/audit.log
        """
        self.audit_path = audit_path or self.DEFAULT_AUDIT_FILE
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def log_job(self, job_info: dict[str, Any]) -> None:
        """
        Log a provisioning job record.

        Parameters
        ----------
        job_info: Dictionary with job details:
            - device_id: str
            - firmware_version: str
            - operator: str
            - config_hash: str
            - result: "SUCCESS" or "FAILED"
            - error_reason: Optional[str]
            - duration_sec: float
            - backend_url: str
            - station_hostname: str
        """
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            **job_info,
        }
        
        try:
            with open(self.audit_path, "a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            print(f"Warning: Failed to write audit log: {e}")

        # Cleanup old logs if file is getting large
        try:
            self._cleanup_old_logs()
        except OSError as e:
            print(f"Warning: Failed to cleanup audit logs: {e}")

    def get_recent_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Retrieve recent audit log entries.

        Parameters
        ----------
        limit: Maximum number of entries to return

        Returns
        -------
        List of job records (newest first)
        """
        jobs = []
        if not self.audit_path.exists():
            return jobs

        try:
            with open(self.audit_path, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            job = json.loads(line)
                            jobs.append(job)
                        except json.JSONDecodeError:
                            pass
        except OSError:
            pass

        # Return newest first
        return list(reversed(jobs[-limit:]))

    def export_csv(self, output_path: str, limit: int = 1000) -> int:
        """
        Export audit logs to CSV format.

        Parameters
        ----------
        output_path: Path to write CSV file
        limit: Maximum number of records to export

        Returns
        -------
        Number of records exported
        """
        jobs = self.get_recent_jobs(limit)
        if not jobs:
            return 0

        import csv
        try:
            # Get all unique keys
            all_keys = set()
            for job in jobs:
                all_keys.update(job.keys())
            
            fieldnames = sorted(list(all_keys))

            with open(output_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(jobs)

            return len(jobs)
        except OSError as e:
            print(f"Error writing CSV: {e}")
            return 0

    def get_stats(self) -> dict[str, Any]:
        """
        Generate summary statistics from audit logs.

        Returns
        -------
        Dictionary with stats:
            - total_jobs: int
            - successful: int
            - failed: int
            - success_rate: float (0-100)
            - unique_devices: int
            - unique_operators: int
        """
        jobs = self.get_recent_jobs(limit=10000)
        if not jobs:
            return {
                "total_jobs": 0,
                "successful": 0,
                "failed": 0,
                "success_rate": 0.0,
                "unique_devices": 0,
                "unique_operators": 0,
            }

        successful = sum(1 for j in jobs if j.get("result") == "SUCCESS")
        failed = sum(1 for j in jobs if j.get("result") == "FAILED")
        total = len(jobs)
        success_rate = (successful / total * 100) if total > 0 else 0.0

        devices = set(j.get("device_id") for j in jobs if j.get("device_id"))
        operators = set(j.get("operator") for j in jobs if j.get("operator"))

        return {
            "total_jobs": total,
            "successful": successful,
            "failed": failed,
            "success_rate": round(success_rate, 2),
            "unique_devices": len(devices),
            "unique_operators": len(operators),
        }

    def _cleanup_old_logs(self) -> None:
        """Remove audit log entries older than RETENTION_DAYS."""
        if not self.audit_path.exists():
            return

        cutoff_date = datetime.utcnow() - timedelta(days=self.RETENTION_DAYS)
        recent_jobs = []

        try:
            with open(self.audit_path, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            job = json.loads(line)
                            try:
                                job_date = datetime.fromisoformat(job.get("timestamp", ""))
                                if job_date > cutoff_date:
                                    recent_jobs.append(job)
                            except (ValueError, TypeError):
                                # Keep unparseable timestamps
                                recent_jobs.append(job)
                        except json.JSONDecodeError:
                            pass

            # Rewrite file with retained jobs
            with open(self.audit_path, "w") as f:
                for job in recent_jobs:
                    f.write(json.dumps(job) + "\n")
        except OSError:
            pass
