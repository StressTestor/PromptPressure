# Monitoring Setup with Prometheus and Grafana

This directory contains the configuration files needed to set up monitoring for PromptPressure using Prometheus and Grafana.

## Prerequisites

- Docker and Docker Compose installed on your system
- PromptPressure application running with monitoring enabled

## Setup Instructions

1. Make sure Docker is running on your system

2. Start Prometheus and Grafana services:
   ```bash
   docker-compose up -d
   ```

3. Verify the services are running:
   ```bash
   docker-compose ps
   ```

4. Access the services in your browser:
   - Prometheus: http://localhost:9090
   - Grafana: http://localhost:3000 (default credentials: admin/admin)

5. Run your PromptPressure evaluation:
   ```bash
   python run_eval.py --multi-config config.yaml
   ```

6. In Grafana:
   - Navigate to Configuration > Data Sources
   - Add Prometheus as a data source with URL: http://prometheus:9090
   - Import the dashboard using the grafana_dashboard.json file from the project root

## Configuration Files

- `prometheus.yml`: Prometheus configuration with scraping targets
- `docker-compose.yml`: Docker Compose file to run Prometheus and Grafana

## Stopping Services

To stop the monitoring services:
```bash
docker-compose down
```
