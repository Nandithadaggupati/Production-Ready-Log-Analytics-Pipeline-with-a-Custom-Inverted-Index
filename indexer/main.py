import time
import requests
import json
import os
import uuid
import re
import string
from collections import defaultdict
import dateutil.parser
from datetime import datetime, timezone

INGESTOR_URL = os.environ.get("INGESTOR_URL", "http://ingestor:8000/logs/batch")
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DOCS_DIR = os.path.join(DATA_DIR, "docs")
INDEX_DIR = os.path.join(DATA_DIR, "index")
INDEX_FILE = os.path.join(INDEX_DIR, "inverted_index.json")

# Ensure dirs exist
os.makedirs(DOCS_DIR, exist_ok=True)
os.makedirs(INDEX_DIR, exist_ok=True)

# Inverted index structure
inverted_index = defaultdict(list)

# Load index if exists
if os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, 'r') as f:
        data = json.load(f)
        for k, v in data.items():
            inverted_index[k] = v

def save_index():
    tmp_file = INDEX_FILE + ".tmp"
    with open(tmp_file, 'w') as f:
        json.dump(inverted_index, f)
    os.replace(tmp_file, INDEX_FILE)

# Parsers
def parse_json(raw: str) -> dict:
    data = json.loads(raw)
    dt = dateutil.parser.isoparse(data['timestamp']).astimezone(timezone.utc)
    return {
        "timestamp": dt.isoformat(),
        "log_type": "json",
        "level": data.get("level", "INFO"),
        "service": data.get("service", "unknown"),
        "message": data.get("message", ""),
        "raw": raw
    }

def parse_nginx(raw: str) -> dict:
    # 127.0.0.1 - - [10/Oct/2023:13:55:36 +0000] "GET /api/v2/users HTTP/1.1" 200 512 "-" "Mozilla/5.0"
    match = re.match(r'(?P<ip>\S+) \S+ \S+ \[(?P<time>.*?)\] "(?P<verb>\S+) (?P<path>\S+) (?P<http>\S+)" (?P<status>\d+) (?P<bytes>\d+) "(?P<referer>.*?)" "(?P<user_agent>.*?)"', raw)
    if not match:
        raise ValueError("Invalid nginx format")
    d = match.groupdict()
    dt = dateutil.parser.parse(d['time'].replace(':', ' ', 1)).astimezone(timezone.utc)
    status = int(d['status'])
    level = "ERROR" if status >= 400 else "INFO"
    return {
        "timestamp": dt.isoformat(),
        "log_type": "nginx",
        "level": level,
        "service": "nginx",
        "message": f"{d['verb']} {d['path']} HTTP {status}",
        "raw": raw
    }

def parse_syslog(raw: str) -> dict:
    # <34>1 2023-10-10T13:55:36.123Z my-hostname app-name - - - An error occurred.
    parts = raw.split(' ', 7)
    if len(parts) < 8:
        raise ValueError("Invalid syslog format")
    dt = dateutil.parser.isoparse(parts[1]).astimezone(timezone.utc)
    message = parts[7]
    level = "ERROR" if "error" in message.lower() or "killed" in message.lower() or "failed" in message.lower() else "INFO"
    return {
        "timestamp": dt.isoformat(),
        "log_type": "syslog",
        "level": level,
        "service": parts[3],
        "message": message,
        "raw": raw
    }

# Registry
PARSERS = {
    "json": parse_json,
    "nginx": parse_nginx,
    "syslog": parse_syslog
}

def detect_type(raw: str) -> str:
    if raw.startswith("{"):
        return "json"
    elif raw.startswith("<"):
        return "syslog"
    else:
        return "nginx"

def tokenize(text: str) -> list:
    text = text.lower()
    for p in string.punctuation:
        text = text.replace(p, ' ')
    return [w for w in text.split() if w]

def index_and_store(log_entry: dict):
    raw = log_entry["raw"]
    log_type = detect_type(raw)
    parser = PARSERS.get(log_type)
    if not parser:
        return
    
    try:
        doc = parser(raw)
        doc_id = str(uuid.uuid4())
        doc["id"] = doc_id
        doc["indexed_at"] = datetime.now(timezone.utc).isoformat()
        
        # Save to document store
        doc_path = os.path.join(DOCS_DIR, f"{doc_id}.json")
        with open(doc_path, 'w') as f:
            json.dump(doc, f)
            
        # Update inverted index
        tokens = set(tokenize(doc["message"]))
        for t in tokens:
            inverted_index[t].append(doc_id)
            
    except Exception as e:
        print(f"Error parsing log: {e}")

def main():
    print("Starting indexer...")
    while True:
        try:
            resp = requests.get(INGESTOR_URL, timeout=10)
            if resp.status_code == 200:
                batch = resp.json()
                if batch:
                    for item in batch:
                        index_and_store(item)
                    save_index()
                    print(f"Processed batch of {len(batch)} logs.")
                else:
                    time.sleep(1) # No logs
            else:
                time.sleep(2)
        except Exception as e:
            print(f"Error fetching logs: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
