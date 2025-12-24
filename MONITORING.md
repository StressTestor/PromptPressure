# Monitoring with Prometheus and Grafana

This document describes how to set up and use the monitoring capabilities added to PromptPressure using Prometheus and Grafana.

## Overview

PromptPressure now includes built-in monitoring capabilities using Prometheus metrics. The system exposes key metrics about API requests, evaluation performance, and error rates through a Prometheus-compatible endpoint.

## Metrics Exposed

The following metrics are exposed by the application on port 8000:

### API Request Metrics

- `promptpressure_api_requests_total` - Total number of API requests by model, adapter, and status
- `promptpressure_api_request_duration_seconds` - Histogram of API request durations by model and adapter
- `promptpressure_api_errors_total` - Total number of API errors by model, adapter, and error type

### Evaluation Metrics

- `promptpressure_active_evaluations` - Number of currently running evaluations
- `promptpressure_evaluation_duration_seconds` - Summary of evaluation durations

### Response Metrics

- `promptpressure_total_prompts` - Total number of prompts processed
- `promptpressure_successful_responses_total` - Total number of successful responses
- `promptpressure_error_responses_total` - Total number of error responses
- `promptpressure_average_response_time_seconds` - Average response time in seconds

## Setup Instructions

### 1. Install Dependencies

The required dependencies are automatically included in `requirements.txt`:

```text
prometheus-client
```

Install with:

```bash
pip install -r requirements.txt
```

### 2. Run the Application

When you run the evaluation suite, the Prometheus metrics server will automatically start on port 8000:

```bash
python run_eval.py --multi-config config_openrouter_gpt_oss_20b_free.yaml config.yaml
```

Or use the one-click batch script (OpenRouter evals + OpenRouter post-analysis + metrics):

```powershell
./run_promptpressure_cloud.bat
```

Notes:

- Cloud-first quickstart: `config_openrouter_gpt_oss_20b_free.yaml` (OpenRouter) and `config.yaml` (e.g., Groq).
- You can use any cloud provider configs; LM Studio is fully supported but optional.

### 3. Access Metrics

Once the application is running, you can access the metrics endpoint at:

```text
http://localhost:8000/
```

### 4. Configure Prometheus

Add the following job to your Prometheus configuration (`prometheus.yml`):

```yaml
scrape_configs:
  - job_name: 'promptpressure'
    static_configs:
      - targets: ['localhost:8000']
```

### 5. Set up Grafana

1. Install Grafana (if not already installed)
2. Add Prometheus as a data source:
   - URL: `http://localhost:9090` (or your Prometheus server address)
   - Access: Server (default)
3. Create dashboards using the exposed metrics

## Example Grafana Dashboard Queries

Here are some example queries you can use in Grafana:

### API Request Rate

```promql
rate(promptpressure_api_requests_total[5m])
```

### Success Rate

```promql
promptpressure_api_requests_total{status="success"} / ignoring(status) promptpressure_api_requests_total
```

### Average Response Time

```promql
promptpressure_average_response_time_seconds
```

### Error Rate

```promql
rate(promptpressure_api_errors_total[5m])
```

### Active Evaluations

```promql
promptpressure_active_evaluations
```

## Customizing Metrics Port

The default metrics port is 8000. To change this, modify the `METRICS_PORT` variable in `monitoring.py`:

```python
# Server configuration
METRICS_PORT = 8000  # Change this value
```

## Stopping the Metrics Server

The metrics server will automatically stop when the application finishes execution. If you need to manually stop it, you can call:

```python
from monitoring import stop_metrics_server
stop_metrics_server()
```

## Troubleshooting

### Port Already in Use

If you get an error that port 8000 is already in use, you can:

1. Change the `METRICS_PORT` in `monitoring.py` to a different port
2. Stop the process using port 8000

### Metrics Not Appearing

If metrics are not appearing:

1. Verify the application is running
2. Check that port 8000 is accessible
3. Verify Prometheus is scraping the endpoint
4. Check application logs for any error messages
