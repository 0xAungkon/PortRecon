import json
import sys
import nmap
import concurrent.futures
import csv
import threading
import ipaddress
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# ---------------- Config ----------------
PORTS = "80,8000"
MAX_WORKERS = 16
RETRIES = 3
RETRY_BACKOFF = 2
CSV_FILE = "nmap_results.csv"

csv_lock = threading.Lock()
progress_lock = threading.Lock()
completed_count = 0
total_targets = 0
start_time = time.time()

# ---------------- Load ranges ----------------
try:
    with open("data.json", "r") as f:
        raw_ranges = json.load(f)
    if not raw_ranges:
        sys.exit("Empty data.json.")
except FileNotFoundError:
    sys.exit("data.json not found.")
except json.JSONDecodeError as e:
    sys.exit(f"Malformed JSON: {e}")

# ---------------- Parse ranges into nmap targets ----------------
def parse_range(cidr_range: str) -> str:
    """
    Accepts 'START-END' notation like '101.2.160.0-101.2.167.255'
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
        # Differs beyond last octet — use full start-end nmap range
        return f"{s[0]}.{s[1]}.{s[2]}.{s[3]}-{e[0]}.{e[1]}.{e[2]}.{e[3]}"
    # Same first three octets, differ only in last
    return f"{s[0]}.{s[1]}.{s[2]}.{s[3]}-{e[3]}"

targets = []
for raw in raw_ranges:
    try:
        targets.append(parse_range(raw))
    except ValueError as e:
        log.warning(f"Skipping invalid range '{raw}': {e}")

if not targets:
    sys.exit("No valid targets parsed.")

total_targets = len(targets)
port_list = [int(p.strip()) for p in PORTS.split(",")]

# ---------------- Initialize CSV ----------------
with open(CSV_FILE, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Host", "Open Ports"])

# ---------------- Scan function ----------------
def scan_target(target: str) -> int:
    nm = nmap.PortScanner()
    for attempt in range(1, RETRIES + 1):
        try:
            nm.scan(hosts=target, ports=PORTS, arguments="-Pn -T4 --open")
            rows = []
            for host in nm.all_hosts():
                open_ports = [
                    str(p)
                    for p in port_list
                    if nm[host].has_tcp(p) and nm[host]["tcp"][p]["state"] == "open"
                ]
                if open_ports:
                    rows.append([host, ",".join(open_ports)])
            if rows:
                with csv_lock:
                    with open(CSV_FILE, "a", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerows(rows)
            return len(nm.all_hosts())
        except Exception as exc:
            if attempt == RETRIES:
                log.error(f"Failed target {target} after {RETRIES} attempts: {exc}")
                return 0
            time.sleep(RETRY_BACKOFF ** attempt)

# ---------------- Progress ----------------
def print_progress(done: int, total: int):
    elapsed = time.time() - start_time
    pct = (done / total * 100) if total else 0
    eta = int((elapsed / done) * (total - done)) if done else 0
    print(f"\rProgress: {done}/{total} ({pct:.1f}%)  ETA: {eta}s   ", end="", flush=True)

# ---------------- Execute ----------------
log.info(f"Scanning {total_targets} targets | Ports: {PORTS} | Workers: {MAX_WORKERS}")

with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {executor.submit(scan_target, t): t for t in targets}
    for future in concurrent.futures.as_completed(futures):
        with progress_lock:
            completed_count += 1
            print_progress(completed_count, total_targets)
        try:
            future.result()
        except Exception as e:
            log.error(f"Unhandled error for {futures[future]}: {e}")

print(f"\nDone. Results saved to {CSV_FILE}")