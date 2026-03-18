from tortoise import fields
from tortoise.models import Model
from datetime import datetime
from enum import Enum


class ScanStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Scan(Model):
    id = fields.CharField(max_length=36, pk=True)  # UUID
    name = fields.CharField(max_length=255)
    ip_range = fields.CharField(max_length=255)
    ports = fields.CharField(max_length=255)
    workers = fields.IntField()
    retries = fields.IntField()
    status = fields.CharEnumField(ScanStatus, default=ScanStatus.PENDING)
    progress = fields.IntField(default=0)
    total_targets = fields.IntField(default=0)
    results_file = fields.CharField(max_length=255, null=True)
    error_message = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    started_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)

    class Meta:
        table = "scans"

    def __str__(self):
        return f"Scan(id={self.id}, name={self.name}, status={self.status})"
