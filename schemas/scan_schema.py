from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class ScanStatusSchema(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ScanCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    ip_range: str = Field(..., min_length=1, max_length=255)
    ports: str = Field(..., min_length=1, max_length=255)
    workers: int = Field(default=16, ge=1, le=64)
    retries: int = Field(default=3, ge=1, le=10)


class ScanResponse(BaseModel):
    id: str
    name: str
    ip_range: str
    ports: str
    workers: int
    retries: int
    status: ScanStatusSchema
    progress: int
    total_targets: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ScanListResponse(BaseModel):
    id: str
    name: str
    status: ScanStatusSchema
    progress: int
    total_targets: int
    created_at: datetime

    class Config:
        from_attributes = True


class ScanResultJSON(BaseModel):
    host: str
    open_ports: list[str]


class ScanOutputResponse(BaseModel):
    scan_id: str
    name: str
    status: ScanStatusSchema
    results: list[ScanResultJSON]
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
