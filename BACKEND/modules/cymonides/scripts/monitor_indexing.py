#!/usr/bin/env python3
"""
Live progress monitor for German CR and WorldCheck indexing
"""
import subprocess
import re
import time
import sys
from datetime import datetime

def clear_screen():
    print("\033[2J\033[H", end="")

def get_file_size(filepath):
    """Get file size in GB"""
    try:
        result = subprocess.check_output(['du', '-sh', filepath], stderr=subprocess.DEVNULL).decode()
        size_str = result.split()[0]
        return size_str
    except Exception as e:
        return "N/A"

def get_progress():
    data = {
        'crde': {'current': 0, 'total': 5000000, 'type': 'companies', 'size': 'N/A', 'est_size': 'N/A'},
        'worldcheck': {'current': 0, 'total': 5400000, 'type': 'records', 'size': 'N/A', 'est_size': 'N/A'},
        'elastic': 0,
        'processes': []
    }

    # Get file sizes
    crde_file = "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/Search-Engineer.02.backup/iv. LOCATION/a. KNOWN_UNKNOWN/SOURCE_CATEGORY/PUBLIC-RECORDS/LOCAL/CORPORATE-REGISTRY/DE/de_CR.jsonl"
    wc_file = "/Volumes/My Book/DOWNLOADS/Free - world-check.com (10.2022).txt"

    data['crde']['size'] = get_file_size(crde_file)
    data['worldcheck']['size'] = get_file_size(wc_file)

    # German CR
    try:
        crde_log = subprocess.check_output(['tail', '-1', '/tmp/crde_1.log'], stderr=subprocess.DEVNULL).decode()
        crde_match = re.search(r'Indexed (\d+) companies', crde_log)
        if crde_match:
            data['crde']['current'] = int(crde_match.group(1))
    except Exception as e:

        print(f"[Monitor Indexing] Error: {e}")

        pass

    # WorldCheck
    try:
        wc_log = subprocess.check_output(['tail', '-1', '/tmp/worldcheck_1.log'], stderr=subprocess.DEVNULL).decode()
        wc_match = re.search(r'Indexed (\d+) records', wc_log)
        if wc_match:
            data['worldcheck']['current'] = int(wc_match.group(1))
    except Exception as e:

        print(f"[Monitor Indexing] Error: {e}")

        pass

    # Elasticsearch
    try:
        # CYMONIDES MANDATE: Use cymonides-1-* pattern for all project nodes
        result = subprocess.check_output(['curl', '-s', 'http://localhost:9200/cymonides-1-*/_count'], stderr=subprocess.DEVNULL)
        count_match = re.search(r'"count"\s*:\s*(\d+)', result.decode())
        if count_match:
            data['elastic'] = int(count_match.group(1))
    except Exception as e:

        print(f"[Monitor Indexing] Error: {e}")

        pass

    # Processes
    try:
        ps = subprocess.check_output(['ps', 'aux'], stderr=subprocess.DEVNULL).decode()
        for line in ps.split('\n'):
            if 'Python' in line and 'index_' in line and 'grep' not in line:
                parts = line.split()
                if 'index_companies_with_edges.py' in line:
                    data['processes'].append({
                        'name': 'German CR',
                        'pid': parts[1],
                        'cpu': parts[2],
                        'mem': parts[3]
                    })
                elif 'index_worldcheck_with_edges.py' in line:
                    data['processes'].append({
                        'name': 'WorldCheck',
                        'pid': parts[1],
                        'cpu': parts[2],
                        'mem': parts[3]
                    })
    except Exception as e:

        print(f"[Monitor Indexing] Error: {e}")

        pass

    return data

def draw_progress_bar(current, total, width=50):
    pct = (current / total) * 100 if total > 0 else 0
    filled = int((current / total) * width) if total > 0 else 0
    bar = '█' * filled + '░' * (width - filled)
    return f"[{bar}] {pct:.2f}%"

def format_number(n):
    return f"{n:,}"

def main():
    start_time = time.time()
    iteration = 0

    try:
        while True:
            clear_screen()
            data = get_progress()
            elapsed = time.time() - start_time

            print("╔" + "═" * 78 + "╗")
            print("║" + " DRILL SEARCH - LIVE INDEXING MONITOR ".center(78) + "║")
            print("╠" + "═" * 78 + "╣")
            print(f"║ {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<76} ║")
            print(f"║ Elapsed: {int(elapsed//3600)}h {int((elapsed%3600)//60)}m {int(elapsed%60)}s{' '*57}║")
            print("╠" + "═" * 78 + "╣")

            # German CR
            crde = data['crde']
            pct = (crde['current'] / crde['total']) * 100
            remaining = crde['total'] - crde['current']
            rate = crde['current'] / elapsed if elapsed > 0 else 0
            eta_sec = remaining / rate if rate > 0 else 0
            eta_hours = eta_sec / 3600

            print("║ GERMAN CR (crde)" + " " * 60 + "║")
            print(f"║ {draw_progress_bar(crde['current'], crde['total'])} ║")
            print(f"║ Progress: {format_number(crde['current'])} / {format_number(crde['total'])} companies{' '*21}║")
            print(f"║ Remaining: {format_number(remaining)} companies{' '*44}║")
            print(f"║ Source size: {crde['size']:<10} │  Rate: {rate:.1f} companies/sec{' '*22}║")
            print(f"║ ETA: {eta_hours:.1f} hours{' '*64}║")
            print("╠" + "═" * 78 + "╣")

            # WorldCheck
            wc = data['worldcheck']
            pct_wc = (wc['current'] / wc['total']) * 100
            remaining_wc = wc['total'] - wc['current']
            rate_wc = wc['current'] / elapsed if elapsed > 0 else 0
            eta_sec_wc = remaining_wc / rate_wc if rate_wc > 0 else 0
            eta_hours_wc = eta_sec_wc / 3600

            print("║ WORLDCHECK" + " " * 66 + "║")
            print(f"║ {draw_progress_bar(wc['current'], wc['total'])} ║")
            print(f"║ Progress: {format_number(wc['current'])} / {format_number(wc['total'])} records{' '*23}║")
            print(f"║ Remaining: {format_number(remaining_wc)} records{' '*46}║")
            print(f"║ Source size: {wc['size']:<10} │  Rate: {rate_wc:.1f} records/sec{' '*24}║")
            print(f"║ ETA: {eta_hours_wc:.1f} hours{' '*64}║")
            print("╠" + "═" * 78 + "╣")

            # Elasticsearch
            print(f"║ ELASTICSEARCH: {format_number(data['elastic'])} total documents{' '*38}║")
            print("╠" + "═" * 78 + "╣")

            # Processes
            print("║ PROCESSES" + " " * 67 + "║")
            if data['processes']:
                for proc in data['processes']:
                    print(f"║ {proc['name']:<15} PID: {proc['pid']:<8} CPU: {proc['cpu']:>5}%  MEM: {proc['mem']:>5}%{' '*21}║")
            else:
                print("║ No active processes found" + " " * 51 + "║")

            print("╚" + "═" * 78 + "╝")
            print("\nPress Ctrl+C to exit")

            time.sleep(5)
            iteration += 1

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")
        sys.exit(0)

if __name__ == "__main__":
    main()
