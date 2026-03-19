import nmap
import asyncio
import csv
import ipaddress
import time
from datetime import datetime
from typing import List, Tuple
from loguru import logger
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


def scan_target(
    target: str, ports: str, retries: int = 3, retry_backoff: int = 2
) -> Tuple[int, List[Tuple[str, List[str]]]]:
    """
    Scan a single target and return results.
    Returns (host_count, results_list)
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

            return len(nm.all_hosts()), results

        except Exception as exc:
            if attempt == retries:
                logger.error(f"Failed target {target} after {retries} attempts: {exc}")
                return 0, []
            time.sleep(retry_backoff**attempt)

    return 0, []


async def run_scan(scan: Scan, max_workers: int = 16) -> None:
    """Execute scan and update database with results"""
    csv_file = Scan.scan_dir(scan.id) / "results.csv"
    csv_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Parse targets
        targets = await get_targets_from_range(scan.ip_range)
        scan.total_targets = len(targets)
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
        completed = 0

        async def scan_with_progress(target: str) -> None:
            nonlocal completed
            host_count, results = await asyncio.to_thread(
                scan_target, target, scan.ports, scan.retries
            )
            all_results.extend(results)
            completed += 1
            scan.progress = completed
            await scan.save()
            logger.debug(f"Scan progress: {completed}/{len(targets)}")

        # Process targets in chunks to respect max_workers
        semaphore = asyncio.Semaphore(max_workers)

        async def bounded_scan(target: str) -> None:
            async with semaphore:
                await scan_with_progress(target)

        await asyncio.gather(*[bounded_scan(t) for t in targets])

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
