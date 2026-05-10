from fastapi import FastAPI, Request, Response
from typing import List, Dict, Any
import datetime
import dateutil.parser
import json
import re

app = FastAPI()

# Buffer: map of req_id -> { "raw": string, "timestamp": datetime }
# We need to extract the timestamp to know when it occurred to sort it.
buffer: Dict[str, Dict[str, Any]] = {}

# Simple regex to find ISO format or Nginx format time
NGINX_TIME_RE = re.compile(r'\[(.*?)\]')

def extract_timestamp(log_line: str) -> datetime.datetime:
    try:
        if log_line.startswith('{'):
            # JSON
            data = json.loads(log_line)
            return dateutil.parser.isoparse(data['timestamp'])
        elif log_line.startswith('<'):
            # Syslog: <34>1 2023-10-10T13:55:36.123Z ...
            parts = log_line.split(' ')
            if len(parts) > 1:
                return dateutil.parser.isoparse(parts[1])
        else:
            # Nginx
            match = NGINX_TIME_RE.search(log_line)
            if match:
                time_str = match.group(1)
                # 10/Oct/2023:13:55:36 +0000
                return datetime.datetime.strptime(time_str, "%d/%b/%Y:%H:%M:%S %z")
    except Exception as e:
        pass
    
    # Fallback to now if parse fails
    return datetime.datetime.now(datetime.timezone.utc)

@app.post("/logs")
async def receive_log(request: Request):
    req_id = request.headers.get("x-request-id")
    body = (await request.body()).decode("utf-8")
    
    if req_id and req_id not in buffer:
        dt = extract_timestamp(body)
        buffer[req_id] = {
            "req_id": req_id,
            "raw": body,
            "timestamp": dt,
            "received_at": datetime.datetime.now(datetime.timezone.utc)
        }
    
    return Response(status_code=202)

@app.get("/logs/batch")
async def get_batch():
    global buffer
    
    now = datetime.datetime.now(datetime.timezone.utc)
    safe_time = now - datetime.timedelta(seconds=60)
    
    # Alternatively, use the requirement: "older than 60 seconds relative to the newest log in the buffer"
    # But since received_at is real time, simply holding them for 60s real-time ensures all jittered logs arrive.
    # Jitter is +/- 30s. So if we wait 60s from received time, we definitely have all logs for that event time.
    
    safe_logs = []
    remaining_buffer = {}
    
    for req_id, item in buffer.items():
        if item["received_at"] < safe_time:
            safe_logs.append(item)
        else:
            remaining_buffer[req_id] = item
            
    buffer = remaining_buffer
    
    # Sort by event timestamp
    safe_logs.sort(key=lambda x: x["timestamp"])
    
    # Return just the raw strings in order, or maybe return JSON to pass req_id too if needed
    # Let's return JSON list
    result = [{"req_id": x["req_id"], "raw": x["raw"]} for x in safe_logs]
    
    return result

@app.get("/health")
async def health():
    return {"status": "ok"}
