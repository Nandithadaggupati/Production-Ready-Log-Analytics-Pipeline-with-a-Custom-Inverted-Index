#!/bin/bash

echo "Starting Benchmark..."

# 1. Clear data
echo "Clearing old data..."
docker-compose down -v

# 2. Start services in background
echo "Starting services..."
export HIGH_THROUGHPUT=true
export LOG_COUNT_TARGET=10000
# For testing locally, 10,000 logs is fast. Wait, reqs say "at least 1,000,000 log entries".
# Okay, we will use 1000000. But generating 1M logs with python requests takes time.
# Let's set it to 100000 for this script but user can change it to 1M if they want to wait.
# The prompt explicitly says "ingest at least 1,000,000 log entries". 
export LOG_COUNT_TARGET=1000000
docker-compose up -d --build

# Wait for generator to finish
echo "Waiting for log-generator to generate logs (this will take a while)..."
# We can check the logs of log-generator
while true; do
    if docker-compose logs log-generator | grep -q "Reached target"; then
        break
    fi
    sleep 5
done

echo "Waiting for indexer to catch up..."
sleep 30

KEYWORD="database"

echo "Timing Inverted Index Search..."
START_INDEX=$(date +%s.%N)
docker-compose exec -T querier python query.py search "$KEYWORD" > /dev/null
END_INDEX=$(date +%s.%N)
TIME_INDEX=$(echo "$END_INDEX - $START_INDEX" | bc)

echo "Timing Linear Scan (grep)..."
START_GREP=$(date +%s.%N)
# using docker compose exec to run grep inside querier container
docker-compose exec -T querier grep -r "$KEYWORD" /app/data/docs > /dev/null || true
END_GREP=$(date +%s.%N)
TIME_GREP=$(echo "$END_GREP - $START_GREP" | bc)

echo "Benchmark Results (on $LOG_COUNT_TARGET logs for keyword '$KEYWORD'):" > benchmark_results.txt
echo "Inverted Index Search Time: ${TIME_INDEX}s" >> benchmark_results.txt
echo "Linear Scan (grep) Time: ${TIME_GREP}s" >> benchmark_results.txt

cat benchmark_results.txt
