import time
import random
import uuid
import datetime
import requests
import json
import os

INGESTOR_URL = os.environ.get("INGESTOR_URL", "http://ingestor:8000/logs")
HIGH_THROUGHPUT = os.environ.get("HIGH_THROUGHPUT", "false").lower() == "true"
LOG_COUNT_TARGET = int(os.environ.get("LOG_COUNT_TARGET", "1000000"))

def get_jittered_time():
    # Jitter +/- 30 seconds
    jitter = random.randint(-30, 30)
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=jitter)

def generate_nginx_log():
    dt = get_jittered_time()
    time_str = dt.strftime("%d/%b/%Y:%H:%M:%S +0000")
    paths = ["/api/v2/users", "/login", "/products", "/checkout", "/"]
    verbs = ["GET", "POST", "PUT"]
    statuses = [200, 201, 400, 404, 500]
    return f'127.0.0.1 - - [{time_str}] "{random.choice(verbs)} {random.choice(paths)} HTTP/1.1" {random.choice(statuses)} {random.randint(100, 5000)} "-" "Mozilla/5.0"'

def generate_json_log():
    dt = get_jittered_time()
    services = ["payment-service", "auth-service", "user-service", "inventory-service"]
    levels = ["INFO", "WARN", "ERROR", "DEBUG"]
    messages = [
        "Database connection timed out",
        "User logged in successfully",
        "Failed to process payment",
        "Item added to cart",
        "Cache miss for item"
    ]
    return json.dumps({
        "timestamp": dt.isoformat(),
        "level": random.choice(levels),
        "service": random.choice(services),
        "trace_id": str(uuid.uuid4()),
        "message": random.choice(messages)
    })

def generate_syslog():
    dt = get_jittered_time()
    time_str = dt.isoformat()
    hostnames = ["web-01", "db-02", "cache-01"]
    apps = ["sshd", "kernel", "cron"]
    messages = [
        "Accepted publickey for root",
        "Out of memory: Killed process 123",
        "pam_unix(cron:session): session opened for user root",
        "Connection to DB failed"
    ]
    return f'<34>1 {time_str} {random.choice(hostnames)} {random.choice(apps)} - - - {random.choice(messages)}'

def generate_log():
    choice = random.choice(["nginx", "json", "syslog"])
    if choice == "nginx":
        return generate_nginx_log()
    elif choice == "json":
        return generate_json_log()
    else:
        return generate_syslog()

def send_log(log_line):
    headers = {
        "X-Request-ID": str(uuid.uuid4()),
        "Content-Type": "text/plain"
    }
    try:
        requests.post(INGESTOR_URL, data=log_line, headers=headers, timeout=5)
    except Exception as e:
        print(f"Failed to send log: {e}")

def main():
    print(f"Starting log generator. High throughput: {HIGH_THROUGHPUT}, Target: {LOG_COUNT_TARGET}")
    
    # Wait for ingestor to be ready
    for _ in range(30):
        try:
            health_url = INGESTOR_URL.replace("/logs", "/health")
            resp = requests.get(health_url, timeout=2)
            if resp.status_code == 200:
                break
        except:
            pass
        print("Waiting for ingestor...")
        time.sleep(2)
        
    count = 0
    while True:
        log_line = generate_log()
        send_log(log_line)
        count += 1
        
        if count % 1000 == 0:
            print(f"Sent {count} logs...")
            
        if HIGH_THROUGHPUT:
            if count >= LOG_COUNT_TARGET:
                print(f"Reached target of {LOG_COUNT_TARGET} logs. Exiting.")
                break
            # Small or zero sleep for high throughput
            # Without sleep, it can overwhelm the ingestor, but we'll try sending fast.
        else:
            time.sleep(random.uniform(0.1, 1.0))

if __name__ == "__main__":
    main()
