import uuid
import json
import asyncio
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from pathlib import Path
from loguru import logger

from models.scan import Scan, ScanStatus
from schemas.scan_schema import (
    ScanListResponse,
    ScanOutputResponse,
    ScanResultJSON,
)
from services.scan_service import (
    run_scan,
    read_csv_results,
    parse_ip_ranges_file,
    count_hosts_in_ranges,
)
from utils.queue_manager import scan_queue

router = APIRouter(prefix="/api/v1/scan", tags=["scans"])


def _normalized_progress(scan: Scan) -> dict:
    total_ranges = scan.total_ranges or 0
    completed_ranges = scan.completed_ranges or 0
    total_hosts = scan.total_hosts or 0
    completed_hosts = scan.completed_hosts or 0
    failed_hosts = scan.failed_hosts or 0
    progress_percent = scan.progress_percent or 0

    # Backward compatibility for scans created before extended metrics existed.
    if total_hosts == 0 and (scan.total_targets or 0) > 0:
        total_hosts = scan.total_targets
    if total_ranges == 0 and (scan.total_targets or 0) > 0:
        total_ranges = scan.total_targets
    if completed_ranges == 0 and (scan.progress or 0) > 0:
        completed_ranges = scan.progress
    if completed_hosts == 0 and completed_ranges > 0 and total_ranges > 0 and total_hosts > 0:
        completed_hosts = int(round((completed_ranges / total_ranges) * total_hosts))
    if progress_percent == 0 and total_ranges > 0 and completed_ranges > 0:
        progress_percent = round((completed_ranges / total_ranges) * 100)

    completed_ranges = min(completed_ranges, total_ranges) if total_ranges else completed_ranges
    completed_hosts = min(completed_hosts, total_hosts) if total_hosts else completed_hosts
    failed_hosts = min(failed_hosts, max(total_hosts - completed_hosts, 0)) if total_hosts else failed_hosts

    return {
        "total_ranges": total_ranges,
        "completed_ranges": completed_ranges,
        "total_hosts": total_hosts,
        "completed_hosts": completed_hosts,
        "failed_hosts": failed_hosts,
        "progress_percent": progress_percent,
    }


@router.post("", response_model=dict)
async def create_scan(
    name: str = Form(...),
    ports: str = Form(...),
    workers: int = Form(10),
    retries: int = Form(3),
    ip_file: UploadFile = File(...),
):
    """Create a new scan and queue it for processing"""
    if workers < 1 or workers > 64:
        raise HTTPException(status_code=400, detail="workers must be between 1 and 64")
    if retries < 1 or retries > 10:
        raise HTTPException(status_code=400, detail="retries must be between 1 and 10")

    try:
        ranges = await parse_ip_ranges_file(ip_file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    total_ranges = len(ranges)
    total_hosts = count_hosts_in_ranges(ranges)

    scan_id = str(uuid.uuid4())
    scan_dir = Scan.scan_dir(scan_id)
    scan_dir.mkdir(parents=True, exist_ok=True)

    input_ext = Path(ip_file.filename or "").suffix or ".txt"
    input_file_path = scan_dir / f"input_ranges{input_ext}"

    input_bytes = await ip_file.read()

    def _write_input_file() -> None:
        with open(input_file_path, "wb") as handle:
            handle.write(input_bytes)

    await asyncio.to_thread(_write_input_file)

    # Create scan record
    scan = await Scan.create(
        id=scan_id,
        name=name,
        ip_range=",".join(ranges),
        input_file_name=ip_file.filename,
        input_file_path=str(input_file_path),
        ports=ports,
        workers=workers,
        retries=retries,
        status=ScanStatus.PENDING,
        progress=0,
        total_targets=total_hosts,
        total_ranges=total_ranges,
        completed_ranges=0,
        total_hosts=total_hosts,
        completed_hosts=0,
        failed_hosts=0,
        progress_percent=0,
    )

    logger.info(f"Created scan {scan_id} with name '{name}'")

    # Enqueue scan
    async def scan_callback():
        scan_refreshed = await Scan.get(id=scan_id)
        await run_scan(scan_refreshed, max_workers=workers)

    await scan_queue.enqueue(scan_id, scan_callback)

    return {"id": scan_id, "status": "queued"}


@router.get("", response_model=list[ScanListResponse])
async def list_scans():
    """Get all scans with their current status"""
    scans = await Scan.all()
    scans = sorted(scans, key=lambda s: s.created_at, reverse=True)
    response: list[ScanListResponse] = []
    for scan in scans:
        metrics = _normalized_progress(scan)
        response.append(
            ScanListResponse(
                id=scan.id,
                name=scan.name,
                input_file_name=scan.input_file_name,
                ports=scan.ports,
                workers=scan.workers,
                retries=scan.retries,
                status=scan.status,
                progress=scan.progress,
                total_targets=scan.total_targets,
                total_ranges=metrics["total_ranges"],
                completed_ranges=metrics["completed_ranges"],
                total_hosts=metrics["total_hosts"],
                completed_hosts=metrics["completed_hosts"],
                failed_hosts=metrics["failed_hosts"],
                progress_percent=metrics["progress_percent"],
                created_at=scan.created_at,
            )
        )

    return response


@router.get("/{uuid}", response_class=StreamingResponse)
async def get_scan_progress(uuid: str):
    """Get scan progress with streaming updates"""
    try:
        scan = await Scan.get(id=uuid)
    except Exception:
        raise HTTPException(status_code=404, detail="Scan not found")

    async def progress_stream():
        """Stream progress updates"""
        while True:
            # Refresh scan data
            scan_updated = await Scan.get(id=uuid)
            metrics = _normalized_progress(scan_updated)

            progress_data = {
                "id": scan_updated.id,
                "name": scan_updated.name,
                "status": scan_updated.status,
                "progress": scan_updated.progress,
                "total_targets": scan_updated.total_targets,
                "total_ranges": metrics["total_ranges"],
                "completed_ranges": metrics["completed_ranges"],
                "total_hosts": metrics["total_hosts"],
                "completed_hosts": metrics["completed_hosts"],
                "failed_hosts": metrics["failed_hosts"],
                "progress_percent": metrics["progress_percent"],
                "is_processing": scan_queue.is_processing(uuid),
                "is_queued": scan_queue.is_queued(uuid),
            }

            yield f"data: {json.dumps(progress_data)}\n\n"

            # If completed or failed, stop streaming
            if scan_updated.status in [ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.STOPPED]:
                break

            await asyncio.sleep(1)

    return StreamingResponse(progress_stream(), media_type="text/event-stream")


@router.post("/{uuid}/cancel", response_model=dict)
async def cancel_scan(uuid: str):
    """Cancel a running or queued scan."""
    try:
        scan = await Scan.get(id=uuid)
    except Exception:
        raise HTTPException(status_code=404, detail="Scan not found")

    if scan.status in [ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.STOPPED]:
        return {"id": uuid, "status": scan.status, "cancelled": False}

    scan.status = ScanStatus.STOPPED
    scan.error_message = "Cancelled by user"
    scan.completed_at = scan.completed_at or datetime.utcnow()
    await scan.save()

    scan_queue.cancel(uuid)
    await Scan.clear_lock(uuid)

    logger.info(f"Cancelled scan {uuid}")
    return {"id": uuid, "status": ScanStatus.STOPPED, "cancelled": True}


@router.get("/{uuid}/output", response_model=ScanOutputResponse)
async def get_scan_output(uuid: str):
    """Get scan results as JSON"""
    try:
        scan = await Scan.get(id=uuid)
    except Exception:
        raise HTTPException(status_code=404, detail="Scan not found")

    if scan.status != ScanStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Scan not completed. Current status: {scan.status}",
        )

    results = await read_csv_results(uuid)
    results_json = [
        ScanResultJSON(host=r["host"], open_ports=r["open_ports"]) for r in results
    ]

    return ScanOutputResponse(
        scan_id=uuid,
        name=scan.name,
        status=scan.status,
        results=results_json,
        completed_at=scan.completed_at,
    )


@router.get("/{uuid}/download")
async def download_scan_results(uuid: str):
    """Download scan results as CSV file"""
    try:
        scan = await Scan.get(id=uuid)
    except Exception:
        raise HTTPException(status_code=404, detail="Scan not found")

    if scan.status != ScanStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Scan not completed. Current status: {scan.status}",
        )

    csv_file = Path(scan.results_file) if scan.results_file else Path("scans") / uuid / "results.csv"

    if not csv_file.exists():
        raise HTTPException(status_code=404, detail="Results file not found")

    return FileResponse(
        path=csv_file,
        filename=f"{scan.name}_{uuid}.csv",
        media_type="text/csv",
    )
