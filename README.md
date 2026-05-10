# Log Analytics Pipeline

A production-ready, containerized log analytics engine built from scratch. It ingests, parses, indexes, and queries heterogeneous log data (Nginx, JSON, Syslog).

## Architecture

The system consists of 5 microservices orchestrated by Docker Compose:

1.  **log-generator**: Continuously generates synthetic logs with a simulated out-of-order delivery (random +/- 30s jitter).
2.  **ingestor**: FastAPI web service that receives logs, buffers them to handle out-of-order events, and deduplicates using `X-Request-ID`.
3.  **indexer**: Core processing engine. Polls ordered logs from the ingestor, parses them using a pluggable registry, builds a custom inverted index, and persists documents to disk.
4.  **querier**: Command-line interface for searching, filtering, and aggregating logs. It reads directly from the persisted inverted index and document store.
5.  **scheduler**: Runs daily to generate summary reports (JSON) for each service.

## Core Features

-   **Custom Inverted Index**: Implemented without external search libraries. Provides lightning-fast keyword search across log messages.
-   **Out-of-Order Handling**: The ingestor uses a 60-second time-window buffer to ensure logs are processed in chronological order of their event timestamps.
-   **Deduplication**: Prevents duplicate processing based on unique request IDs.
-   **Pluggable Parser Registry**: Easily extendable to support new log formats without modifying the core indexing logic.

## Prerequisites

-   Docker
-   Docker Compose

## Setup and Usage

1.  **Start the Pipeline**:
    ```bash
    docker-compose up -d --build
    ```
    This single command starts all services. Data will be persisted in `./data` and `./reports` on the host machine.

2.  **Verify Data Ingestion**:
    Check the logs of the indexer to see it processing batches:
    ```bash
    docker-compose logs -f indexer
    ```

3.  **Use the Querier CLI**:
    Execute commands inside the `querier` container.

    -   **Keyword Search**:
        ```bash
        docker-compose exec querier python query.py search "database"
        ```
    -   **Field and Time Filtering**:
        ```bash
        docker-compose exec querier python query.py filter level=ERROR --last 1h
        ```
    -   **Combined Search and Filter**:
        ```bash
        docker-compose exec querier python query.py search "failed" filter service=nginx
        ```
    -   **Aggregation**:
        ```bash
        docker-compose exec querier python query.py aggregate count by service,level --last 24h
        ```

4.  **View Daily Reports**:
    Reports are automatically generated in the `./reports/YYYY-MM-DD/` directory.
    ```bash
    cat ./reports/$(date +%Y-%m-%d)/nginx.json
    ```

## Benchmarking

A benchmarking script is provided to compare the performance of the custom inverted index against a naive linear scan (`grep`).

1.  Run the benchmark script:
    ```bash
    chmod +x benchmark.sh
    ./benchmark.sh
    ```
2.  The script will clear existing data, ingest a large volume of logs in high-throughput mode, and output the timing results to `benchmark_results.txt`.
