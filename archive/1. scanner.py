# playground_scan.py

import json
import sys
import nmap
import concurrent.futures
import time
import csv
import threading
import os

# ---------------- Load JSON data ----------------
try: 
    with open('data.json', 'r') as file:
        data = json.load(file)
    if not data:
        sys.exit("No data found in the JSON file.")
except:
    sys.exit("Error reading the JSON file.")

# ---------------- Convert IP range to Nmap format ----------------
def to_nmap_range(start, end):
    s = list(map(int, start.split('.')))
    e = list(map(int, end.split('.')))
    return f"{s[0]}-{e[0]}.{s[1]}-{e[1]}.{s[2]}-{e[2]}.{s[3]}-{e[3]}"

targets = []
for item in data:
    try:
        targets.append(to_nmap_range(item['start'], item['end']))
    except KeyError as e:
        print(f"Missing key in data item: {e}")

# ---------------- Config ----------------
PORTS = "80"
MAX_WORKERS = 8
RETRIES = 3
CSV_FILE = "nmap_results.csv"
STATE_FILE = "state.json"

csv_lock = threading.Lock()
state_lock = threading.Lock()

# ---------------- Load state for resume ----------------
if os.path.exists(STATE_FILE):
    with open(STATE_FILE, "r") as f:
        state = json.load(f)
else:
    state = {"completed_targets": []}

# Initialize CSV if not exist
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Host", "Open Ports"])

total_targets = len(targets)
start_time = time.time()

# ---------------- Functions ----------------
def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def print_progress(completed, total):
    elapsed = time.time() - start_time
    percent = (completed / total) * 100 if total > 0 else 0
    if completed > 0:
        est_total_time = elapsed / (completed / total)
        remaining = est_total_time - elapsed
    else:
        remaining = 0
    print(f"\rProgress: {completed}/{total} ({percent:.2f}%), ETA: {int(remaining)}s", end="", flush=True)
    sys.stdout.flush()

def scan_target(target):
    nm = nmap.PortScanner()
    ports_list = [int(p) for p in PORTS.split(",")]
    for attempt in range(RETRIES):
        try:
            nm.scan(hosts=target, ports=PORTS, arguments="-Pn -T4")
            result = {}
            for host in nm.all_hosts():
                open_ports = []
                for p in ports_list:
                    if nm[host].has_tcp(p) and nm[host]['tcp'][p]['state'] == 'open':
                        open_ports.append(str(p))
                if open_ports:
                    result[host] = ",".join(open_ports)
                    # Write immediately to CSV
                    with csv_lock:
                        with open(CSV_FILE, "a", newline="") as f:
                            writer = csv.writer(f)
                            writer.writerow([host, result[host]])
            # Mark target as completed
            with state_lock:
                state["completed_targets"].append(target)
            save_state()
            return len(nm.all_hosts())
        except Exception:
            if attempt + 1 == RETRIES:
                return 0
            time.sleep(2)

# ---------------- Run scans ----------------
completed_count = len(state["completed_targets"])

with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
    futures = {}
    for t in targets:
        if t not in state["completed_targets"]:
            futures[exe.submit(scan_target, t)] = t

    for f in concurrent.futures.as_completed(futures):
        completed_count += 1
        print_progress(completed_count, total_targets)

print("\nScan completed.")
