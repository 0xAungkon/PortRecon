import csv
import requests
import sys
import json
import os
from urllib3.exceptions import InsecureRequestWarning
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

# Suppress SSL warnings
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Global lock for thread-safe output
output_lock = threading.Lock()

STATE_FILE = "ollama-state.json"
OLLAMA_CSV = "ollama.csv"
NMAP_CSV = "nmap_results.csv"

def load_state():
    """Load progress state from state.json"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            return {"checked": set(), "found": []}
    return {"checked": set(), "found": []}

def save_state(state):
    """Save progress state to state.json"""
    state_copy = state.copy()
    state_copy["checked"] = list(state_copy["checked"])
    with open(STATE_FILE, "w") as f:
        json.dump(state_copy, f, indent=2)

def check_ollama_host(host, port, timeout=5):
    """
    Check if Ollama is running on the given host and port.
    Returns tuple (host, port, True/False) if "Ollama is running" is found.
    """
    try:
        url = f"http://{host}:{port}"
        response = requests.get(url, timeout=timeout, verify=False)
        
        # Check if response contains "Ollama is running"
        if "Ollama is running" in response.text:
            return (host, port, True)
        
        # Also check for common Ollama response patterns
        if response.status_code == 200:
            return (host, port, True)
            
    except requests.exceptions.RequestException:
        pass
    
    return (host, port, False)

def update_progress(checked, total, found):
    """Display progress percentage"""
    percentage = (checked / total) * 100 if total > 0 else 0
    bar_length = 40
    filled = int(bar_length * checked // total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_length - filled)
    
    sys.stdout.write(f"\r[{bar}] {percentage:.1f}% ({checked}/{total}) | Found: {found}   ")
    sys.stdout.flush()

def main():
    """Read CSV, check each host in parallel, and save results to ollama.csv"""
    
    # Load existing state
    state = load_state()
    checked_set = set(state.get("checked", []))
    ollama_hosts = state.get("found", [])
    
    # Read the nmap_results.csv
    try:
        with open(NMAP_CSV, "r") as f:
            reader = csv.DictReader(f)
            hosts_list = [(row["Host"].strip(), row["Open Ports"].strip()) for row in reader]
        
        total = len(hosts_list)
        
        # Filter out already checked hosts
        hosts_to_check = [(h, p) for h, p in hosts_list if f"{h}:{p}" not in checked_set]
        
        if hosts_to_check:
            print(f"Resuming scan: {len(checked_set)} already checked, {len(hosts_to_check)} remaining out of {total}...\n")
        else:
            print(f"Scan complete! All {total} hosts have been checked.")
            if ollama_hosts:
                with open(OLLAMA_CSV, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=["Host", "Open Ports"])
                    writer.writeheader()
                    writer.writerows(ollama_hosts)
                print(f"✓ Found {len(ollama_hosts)}/{total} hosts with Ollama running")
                print(f"Results saved to {OLLAMA_CSV}")
            return
        
        checked = len(checked_set)
        found = len(ollama_hosts)
        
        # Use ThreadPoolExecutor for parallel requests
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(check_ollama_host, host, port, 5): (host, port)
                for host, port in hosts_to_check
            }
            
            for future in as_completed(futures):
                host, port, is_ollama = future.result()
                host_port_key = f"{host}:{port}"
                checked_set.add(host_port_key)
                checked += 1
                
                if is_ollama:
                    found += 1
                    ollama_hosts.append({"Host": host, "Open Ports": port})
                
                # Update progress and save state periodically
                update_progress(checked, total, found)
                if checked % 10 == 0 or checked == len(hosts_to_check):
                    state = {"checked": list(checked_set), "found": ollama_hosts}
                    save_state(state)
        
        # Write results to ollama.csv
        print("\n")  # New line after progress bar
        if ollama_hosts:
            with open(OLLAMA_CSV, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Host", "Open Ports"])
                writer.writeheader()
                writer.writerows(ollama_hosts)
            
            print(f"✓ Found {found}/{total} hosts with Ollama running")
            print(f"Results saved to {OLLAMA_CSV}")
        else:
            print(f"✗ No hosts with Ollama found (checked {total})")
        
        # Save final state
        state = {"checked": list(checked_set), "found": ollama_hosts}
        save_state(state)
    
    except FileNotFoundError:
        print(f"Error: {NMAP_CSV} not found")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nScan paused. Progress saved to state.json")
        state = {"checked": list(checked_set), "found": ollama_hosts}
        save_state(state)
        print("Run the script again to resume from where you left off.")
        sys.exit(0)

if __name__ == "__main__":
    main()
