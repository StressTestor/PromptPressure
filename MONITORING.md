# monitoring with prometheus

promptpressure exposes prometheus metrics on port 9090 while evals are running.

## metrics exposed

### api requests
- `promptpressure_api_requests_total` - request count by model, adapter, status
- `promptpressure_api_request_duration_seconds` - request duration histogram
- `promptpressure_api_errors_total` - error count by model, adapter, error type

### evaluation
- `promptpressure_active_evaluations` - currently running evals
- `promptpressure_evaluation_duration_seconds` - eval duration summary

### response
- `promptpressure_total_prompts` - total prompts processed
- `promptpressure_successful_responses_total` - successful responses
- `promptpressure_error_responses_total` - error responses
- `promptpressure_average_response_time_seconds` - avg response time

## setup

metrics start automatically when you run an eval. access them at `http://localhost:9090/`.

### prometheus config

```yaml
scrape_configs:
  - job_name: 'promptpressure'
    static_configs:
      - targets: ['localhost:9090']
```

### grafana

1. add prometheus as a data source (`http://localhost:9090`)
2. import the dashboard from `promptpressure/monitoring/docker-compose.yml`

### docker (optional)

```bash
cd promptpressure/monitoring
docker-compose up -d
```

this starts prometheus and grafana. grafana at `http://localhost:3000` (admin/admin).

## example queries

```promql
# request rate
rate(promptpressure_api_requests_total[5m])

# success rate
promptpressure_api_requests_total{status="success"} / ignoring(status) promptpressure_api_requests_total

# avg response time
promptpressure_average_response_time_seconds

# error rate
rate(promptpressure_api_errors_total[5m])
```

## changing the port

edit `METRICS_PORT` in `promptpressure/monitoring/__init__.py`. default is 9090.
