"""
PortRecon — ollama_model_list.

This change:
Scans a list of Ollama hosts and exports the available models to JSON and CSV files.


Use:
  python main.py --hosts hosts.txt

"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import requests

# Defaults
HOST_FILE = "ollama.csv"
TIMEOUT = 5
MAX_WORKERS = 20  # tune for large networks

OUTPUT_JSON = "ollama_hosts.json"
OUTPUT_CSV = "ollama_hosts.csv"
OUTPUT_FILTERED_JSON = "ollama_hosts_with_models.json"


def fetch_ollama_info(host: str, timeout: int = TIMEOUT) -> dict:
    """Fetch /api/tags from an Ollama host and return a normalized result dict.

    host may be provided as bare "host:port" or include a scheme.
    """
    # Normalize base URL
    if host.startswith("http://") or host.startswith("https://"):
        base_url = host.rstrip("/")
    else:
        base_url = f"http://{host.rstrip('/') }"

    result = {
        "host": host,
        "status": "ok",
        "models": [],
        "runtime": "unknown",
        "error": None,
    }

    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=timeout)
        # Raise for HTTP errors (will be caught below)
        resp.raise_for_status()

        try:
            tags = resp.json()
        except ValueError:
            # Invalid JSON (HTML, empty response, etc.). Capture a short snippet.
            text_snippet = resp.text[:200].replace("\n", " ")
            raise Exception(f"Invalid JSON from {base_url}/api/tags: {text_snippet} (status={resp.status_code})")

        result["models"] = [m.get("name") for m in tags.get("models", []) if m.get("name")]

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


def split_host_port(host: str) -> Tuple[str, Optional[int]]:
    """Return (host, port) parsed from a host string. Port is int or None.

    The returned host does not include a scheme.
    """
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    p = urlparse(host)
    netloc = p.netloc
    if ":" in netloc:
        h, port_str = netloc.rsplit(":", 1)
        try:
            port = int(port_str)
        except Exception:
            port = None
    else:
        h = netloc
        port = None
    return h, port


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scan a list of Ollama hosts and export models")
    p.add_argument("--hosts", default=HOST_FILE, help="Path to hosts file (one host per line) or CSV (e.g. ollama.csv)")
    p.add_argument("--output-json", default=OUTPUT_JSON, help="Full JSON output")
    p.add_argument("--output-csv", default=OUTPUT_CSV, help="CSV output")
    p.add_argument("--output-filtered", default=OUTPUT_FILTERED_JSON, help="Filtered JSON with only hosts that have models")
    p.add_argument("--timeout", type=int, default=TIMEOUT, help="HTTP timeout in seconds")
    p.add_argument("--workers", type=int, default=MAX_WORKERS, help="Max concurrent workers")
    p.add_argument("--quiet", action="store_true", help="Reduce output")
    return p.parse_args(argv)


def load_hosts_from_path(path: Path) -> List[str]:
    """Load hosts from plain text (one per line) or CSV.

    Supported CSV formats:
    - `Host,Open Ports` (output from `2.ollama-checker.py`) -> combined as host:port
    - CSV with a `host` or `Host` column -> takes that column's values
    - Falls back to first column values for other CSVs
    """
    hosts: List[str] = []
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = [fn.lower() for fn in (reader.fieldnames or [])]

            for row in reader:
                # Prefer Host + Open Ports format
                if "host" in fieldnames and "open ports" in fieldnames:
                    host = row.get("Host") or row.get("host")
                    ports = row.get("Open Ports") or row.get("open ports") or ""
                    host = host.strip() if host else ""
                    ports = ports.strip() if ports else ""
                    if host and ports:
                        hosts.append(f"{host}:{ports}")
                    elif host:
                        hosts.append(host)
                # Generic host column
                elif "host" in fieldnames:
                    host = row.get("Host") or row.get("host")
                    if host and host.strip():
                        hosts.append(host.strip())
                else:
                    # Fallback: first column value
                    first = next(iter(row.values()), "")
                    if first and str(first).strip():
                        hosts.append(str(first).strip())
    else:
        # Plain text file: one host per line
        hosts = [h.strip() for h in path.read_text(encoding="utf-8").splitlines() if h.strip()]

    return hosts


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO, format="%(message)s")

    hosts_path = Path(args.hosts)
    if not hosts_path.exists():
        logging.error("Hosts file not found: %s", hosts_path)
        return 2

    hosts = load_hosts_from_path(hosts_path)
    results: List[dict] = []

    logging.info("Scanning %d hosts using %d workers...", len(hosts), args.workers)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_ollama_info, host, args.timeout): host for host in hosts}
        for future in as_completed(futures):
            r = future.result()
            results.append(r)

    # Export full JSON
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Export CSV
    with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["host", "status", "runtime", "models", "error"])
        for r in results:
            writer.writerow([
                r.get("host"),
                r.get("status"),
                r.get("runtime"),
                ";".join(r.get("models", [])),
                r.get("error"),
            ])

    # Export filtered JSON (only hosts that have models)
    filtered = []
    for r in results:
        if r.get("models"):
            h, port = split_host_port(r.get("host", ""))
            filtered.append({"host": h, "port": port, "models": r.get("models", [])})

    with open(args.output_filtered, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)

    # Console summary
    logging.info("\n=== Scan Summary ===")
    for r in results:
        logging.info("%25s | %8s | %3d models", r.get("host"), r.get("runtime"), len(r.get("models", [])))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
