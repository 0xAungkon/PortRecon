import nmap
import asyncio
import csv
import ipaddress
import io
import json
import time
from datetime import datetime
from typing import List, Tuple
from loguru import logger
from fastapi import UploadFile
from models.scan import Scan, ScanStatus


async def parse_range(cidr_range: str) -> str:
    """
    Parse IP range in 'START-END' notation.
    Returns nmap-compatible range string.
    """
    parts = cidr_range.strip().split("-", maxsplit=1)
    if len(parts) != 2:
        raise ValueError(f"Invalid range format: {cidr_range}")

    start_ip, end_ip = parts
    # Validate both are legal IPs
    ipaddress.ip_address(start_ip)
    ipaddress.ip_address(end_ip)

    s = start_ip.split(".")
    e = end_ip.split(".")

    if s[:3] != e[:3]:
        # Differs beyond last octet
        return f"{s[0]}.{s[1]}.{s[2]}.{s[3]}-{e[0]}.{e[1]}.{e[2]}.{e[3]}"

    # Same first three octets, differ only in last
    return f"{s[0]}.{s[1]}.{s[2]}.{s[3]}-{e[3]}"


async def get_targets_from_range(ip_range: str) -> List[str]:
    """
    Parse comma-separated IP ranges and return list of nmap targets.
    Each range should be in 'START-END' format (e.g., '192.168.1.1-192.168.1.50')
    Multiple ranges separated by commas are supported.
    """
    targets = []
    ranges = [r.strip() for r in ip_range.split(",") if r.strip()]
    
    for range_str in ranges:
        try:
            target = await parse_range(range_str)
            targets.append(target)
        except ValueError as e:
            logger.error(f"Invalid IP range '{range_str}': {e}")
            raise ValueError(f"Invalid IP range '{range_str}': {e}")
    
    return targets


def _validate_range_pair(start_ip: str, end_ip: str) -> str:
    ipaddress.ip_address(start_ip)
    ipaddress.ip_address(end_ip)
    return f"{start_ip}-{end_ip}"


def _parse_json_ranges(content: str) -> List[str]:
    payload = json.loads(content)
    entries = payload.get("ranges", []) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise ValueError("JSON input must be a list of ranges or an object with a 'ranges' list")

    ranges: List[str] = []
    for item in entries:
        if isinstance(item, str):
            parts = [part.strip() for part in item.split("-", maxsplit=1)]
            if len(parts) != 2:
                raise ValueError(f"Invalid range value: {item}")
            ranges.append(_validate_range_pair(parts[0], parts[1]))
            continue

        if isinstance(item, dict):
            start_ip = str(item.get("start", "")).strip()
            end_ip = str(item.get("end", "")).strip()
            if not start_ip or not end_ip:
                raise ValueError("Each JSON range object must contain 'start' and 'end'")
            ranges.append(_validate_range_pair(start_ip, end_ip))
            continue

        raise ValueError("JSON ranges must contain strings or objects")

    return ranges


def _parse_csv_ranges(content: str) -> List[str]:
    reader = csv.reader(io.StringIO(content))
    ranges: List[str] = []

    for row in reader:
        if not row:
            continue

        cells = [str(cell).strip() for cell in row]
        if len(cells) < 2:
            continue

        start_ip, end_ip = cells[0], cells[1]
        if start_ip.lower() in {"start", "start_ip"} and end_ip.lower() in {"end", "end_ip"}:
            continue

        ranges.append(_validate_range_pair(start_ip, end_ip))

    return ranges


async def parse_ip_ranges_file(upload_file: UploadFile) -> List[str]:
    if not upload_file.filename:
        raise ValueError("Input file name is required")

    raw_content = await upload_file.read()
    await upload_file.seek(0)

    content = raw_content.decode("utf-8", errors="ignore").strip()
    if not content:
        raise ValueError("Uploaded file is empty")

    file_name = upload_file.filename.lower()

    if file_name.endswith(".json"):
        ranges = _parse_json_ranges(content)
    elif file_name.endswith(".csv") or file_name.endswith(".txt"):
        ranges = _parse_csv_ranges(content)
    else:
        try:
            ranges = _parse_json_ranges(content)
        except Exception:
            ranges = _parse_csv_ranges(content)

    if not ranges:
        raise ValueError("No valid IP ranges found in uploaded file")

    return ranges


def _count_hosts_in_range(range_str: str) -> int:
    parts = range_str.strip().split("-", maxsplit=1)
    if len(parts) != 2:
        raise ValueError(f"Invalid range format: {range_str}")

    start_ip = ipaddress.ip_address(parts[0].strip())
    end_ip = ipaddress.ip_address(parts[1].strip())

    if start_ip.version != end_ip.version:
        raise ValueError(f"IP version mismatch in range: {range_str}")
    if int(end_ip) < int(start_ip):
        raise ValueError(f"Range end before start: {range_str}")

    return int(end_ip) - int(start_ip) + 1


def count_hosts_in_ranges(range_list: List[str]) -> int:
    return sum(_count_hosts_in_range(range_str) for range_str in range_list)


def scan_target(
    target: str, ports: str, retries: int = 3, retry_backoff: int = 2
) -> Tuple[int, List[Tuple[str, List[str]]], bool]:
    """
    Scan a single target and return results.
    Returns (host_count, results_list, success)
    """
    nm = nmap.PortScanner()
    port_list = [int(p.strip()) for p in ports.split(",")]
    results = []

    for attempt in range(1, retries + 1):
        try:
            nm.scan(hosts=target, ports=ports, arguments="-Pn -T4 --open")

            for host in nm.all_hosts():
                open_ports = [
                    str(p)
                    for p in port_list
                    if nm[host].has_tcp(p) and nm[host]["tcp"][p]["state"] == "open"
                ]
                if open_ports:
                    results.append((host, open_ports))

            return len(nm.all_hosts()), results, True

        except Exception as exc:
            if attempt == retries:
                logger.error(f"Failed target {target} after {retries} attempts: {exc}")
                return 0, [], False
            time.sleep(retry_backoff**attempt)

    return 0, [], False


async def run_scan(scan: Scan, max_workers: int = 16) -> None:
    """Execute scan and update database with results"""
    csv_file = Scan.scan_dir(scan.id) / "results.csv"
    csv_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        raw_ranges = [r.strip() for r in scan.ip_range.split(",") if r.strip()]
        targets = await get_targets_from_range(scan.ip_range)

        total_ranges = len(raw_ranges)
        total_hosts = count_hosts_in_ranges(raw_ranges)

        scan.total_ranges = total_ranges
        scan.completed_ranges = 0
        scan.total_hosts = total_hosts
        scan.completed_hosts = 0
        scan.failed_hosts = 0
        scan.progress_percent = 0

        scan.progress = 0
        scan.total_targets = total_hosts
        scan.status = ScanStatus.RUNNING
        scan.started_at = datetime.utcnow()
        await scan.save()
        logger.info(f"Started scan {scan.id}: {targets}")

        # Initialize CSV
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Host", "Open Ports"])

        # Run scans in parallel (limited by max_workers)
        all_results = []
        completed_ranges = 0

        async def scan_with_progress(target: str, hosts_in_target: int) -> None:
            nonlocal completed_ranges
            host_count, results, success = await asyncio.to_thread(
                scan_target, target, scan.ports, scan.retries
            )
            all_results.extend(results)

            completed_ranges += 1
            scan.completed_ranges = completed_ranges
            scan.progress = completed_ranges

            if success:
                scan.completed_hosts += hosts_in_target
            else:
                scan.failed_hosts += hosts_in_target

            scan.progress_percent = (
                round((completed_ranges / total_ranges) * 100) if total_ranges else 0
            )

            await scan.save()
            logger.debug(
                f"Scan progress: ranges {completed_ranges}/{total_ranges}, "
                f"hosts completed={scan.completed_hosts}, failed={scan.failed_hosts}, discovered={host_count}"
            )

        # Process targets in chunks to respect max_workers
        semaphore = asyncio.Semaphore(max_workers)

        async def bounded_scan(target: str, hosts_in_target: int) -> None:
            async with semaphore:
                await scan_with_progress(target, hosts_in_target)

        range_target_pairs = list(zip(raw_ranges, targets))
        await asyncio.gather(
            *[
                bounded_scan(target, _count_hosts_in_range(raw_range))
                for raw_range, target in range_target_pairs
            ]
        )

        # Write all results to CSV
        if all_results:
            with open(csv_file, "a", newline="") as f:
                writer = csv.writer(f)
                for host, ports in all_results:
                    writer.writerow([host, ",".join(ports)])

        # Mark as completed
        scan.status = ScanStatus.COMPLETED
        scan.completed_at = datetime.utcnow()
        scan.results_file = str(csv_file)
        scan.progress = scan.total_ranges
        scan.progress_percent = 100 if scan.total_ranges else 0
        await scan.save()
        logger.info(f"Completed scan {scan.id}")

    except Exception as e:
        logger.error(f"Scan {scan.id} failed: {e}")
        scan.status = ScanStatus.FAILED
        scan.error_message = str(e)
        scan.completed_at = datetime.utcnow()
        await scan.save()


async def read_csv_results(scan_id: str) -> List[dict]:
    """Read CSV results and return as list of dicts"""
    csv_file = Scan.scan_dir(scan_id) / "results.csv"

    if not csv_file.exists():
        return []

    results = []
    try:
        with open(csv_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Host"):
                    ports = row.get("Open Ports", "").split(",")
                    results.append(
                        {"host": row["Host"], "open_ports": [p.strip() for p in ports if p.strip()]}
                    )
    except Exception as e:
        logger.error(f"Error reading CSV {scan_id}: {e}")

    return results
