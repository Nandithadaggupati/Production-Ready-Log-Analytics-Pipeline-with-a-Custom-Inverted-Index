import os
import json
import time
import dateutil.parser
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import schedule

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DOCS_DIR = os.path.join(DATA_DIR, "docs")
REPORTS_DIR = os.environ.get("REPORTS_DIR", "/app/reports")

def generate_reports():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Generating daily reports...")
    
    if not os.path.exists(DOCS_DIR):
        print(f"Docs dir {DOCS_DIR} not found.")
        return
        
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    
    # service -> {"total_events": int, "errors": int, "error_msgs": map, "latencies": list}
    stats = defaultdict(lambda: {
        "total_events": 0,
        "errors": 0,
        "error_msgs": defaultdict(int),
        "latencies": []
    })
    
    for fname in os.listdir(DOCS_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(DOCS_DIR, fname)
        try:
            with open(path, 'r') as f:
                doc = json.load(f)
            
            dt = dateutil.parser.isoparse(doc['timestamp'])
            # Only process last 24h
            if dt < yesterday:
                continue
                
            svc = doc.get("service", "unknown")
            s = stats[svc]
            
            s["total_events"] += 1
            if doc.get("level") == "ERROR":
                s["errors"] += 1
                s["error_msgs"][doc.get("message", "")] += 1
                
            if "indexed_at" in doc:
                idx_dt = dateutil.parser.isoparse(doc["indexed_at"])
                latency_ms = (idx_dt - dt).total_seconds() * 1000.0
                s["latencies"].append(latency_ms)
                
        except Exception as e:
            print(f"Error processing {fname}: {e}")

    # Generate JSON reports
    today_str = now.strftime("%Y-%m-%d")
    report_day_dir = os.path.join(REPORTS_DIR, today_str)
    os.makedirs(report_day_dir, exist_ok=True)
    
    for svc, s in stats.items():
        err_rate = s["errors"] / s["total_events"] if s["total_events"] > 0 else 0.0
        
        sorted_msgs = sorted(s["error_msgs"].items(), key=lambda x: x[1], reverse=True)[:10]
        top_10 = [{"message": m, "count": c} for m, c in sorted_msgs]
        
        latencies = sorted(s["latencies"])
        if latencies:
            p95_idx = int(len(latencies) * 0.95)
            # handle exact boundary
            p95_idx = min(p95_idx, len(latencies) - 1)
            p95 = latencies[p95_idx]
        else:
            p95 = 0.0
            
        report = {
            "service_name": svc,
            "report_date": today_str,
            "total_events": s["total_events"],
            "error_rate": err_rate,
            "top_10_error_messages": top_10,
            "p95_ingestion_latency_ms": p95
        }
        
        report_path = os.path.join(report_day_dir, f"{svc}.json")
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
            
    print(f"[{datetime.now(timezone.utc).isoformat()}] Reports generated successfully.")

def main():
    print("Scheduler service started.")
    # Run once on startup so reports are available immediately for testing
    generate_reports()
    
    schedule.every().day.at("00:00").do(generate_reports)
    
    # Run schedule
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()
