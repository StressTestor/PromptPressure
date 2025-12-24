"""
Monitoring module for PromptPressure using Prometheus.

This module provides Prometheus metrics exposure for the PromptPressure evaluation suite.
It exposes key metrics such as API response times, success rates, error rates, and custom metrics.
"""

import time
import threading
from typing import Dict, Any
from prometheus_client import start_http_server, Counter, Gauge, Histogram, Summary

# Prometheus metrics definitions
API_REQUESTS_TOTAL = Counter('promptpressure_api_requests_total', 'Total number of API requests', ['model', 'adapter', 'status'])
API_REQUEST_DURATION = Histogram('promptpressure_api_request_duration_seconds', 'API request duration in seconds', ['model', 'adapter'])
API_ERRORS_TOTAL = Counter('promptpressure_api_errors_total', 'Total number of API errors', ['model', 'adapter', 'error_type'])
ACTIVE_EVALUATIONS = Gauge('promptpressure_active_evaluations', 'Number of currently running evaluations')
EVALUATION_DURATION = Summary('promptpressure_evaluation_duration_seconds', 'Time spent processing evaluations')

# Custom metrics for PromptPressure
TOTAL_PROMPTS = Counter('promptpressure_total_prompts', 'Total number of prompts processed')
SUCCESSFUL_RESPONSES = Counter('promptpressure_successful_responses_total', 'Total number of successful responses')
ERROR_RESPONSES = Counter('promptpressure_error_responses_total', 'Total number of error responses')
AVERAGE_RESPONSE_TIME = Gauge('promptpressure_average_response_time_seconds', 'Average response time in seconds')

# Server configuration
METRICS_PORT = 8000


class MetricsServer:
    """A Prometheus metrics server for PromptPressure."""
    
    def __init__(self, port: int = METRICS_PORT):
        self.port = port
        self.server_thread = None
        self.running = False
    
    def start(self):
        """Start the Prometheus metrics server in a separate thread."""
        if not self.running:
            self.server_thread = threading.Thread(target=self._run_server, daemon=True)
            self.server_thread.start()
            self.running = True
            print(f"Prometheus metrics server started on port {self.port}")
    
    def _run_server(self):
        """Run the Prometheus HTTP server."""
        try:
            start_http_server(self.port)
            # Keep the thread alive
            while self.running:
                time.sleep(1)
        except Exception as e:
            print(f"Error starting Prometheus metrics server: {e}")
    
    def stop(self):
        """Stop the Prometheus metrics server."""
        if self.running:
            self.running = False
            if self.server_thread:
                self.server_thread.join(timeout=2)
            print("Prometheus metrics server stopped")


def record_api_request(model: str, adapter: str, duration: float, success: bool = True, error_type: str = None):
    """Record an API request metric."""
    # Record request count
    status = 'success' if success else 'error'
    API_REQUESTS_TOTAL.labels(model=model, adapter=adapter, status=status).inc()
    
    # Record duration
    API_REQUEST_DURATION.labels(model=model, adapter=adapter).observe(duration)
    
    # Record errors if applicable
    if not success:
        API_ERRORS_TOTAL.labels(model=model, adapter=adapter, error_type=error_type or 'unknown').inc()


def record_evaluation_start():
    """Record the start of an evaluation."""
    ACTIVE_EVALUATIONS.inc()


def record_evaluation_end(duration: float):
    """Record the end of an evaluation."""
    ACTIVE_EVALUATIONS.dec()
    EVALUATION_DURATION.observe(duration)


def record_prompt_processing():
    """Record a prompt being processed."""
    TOTAL_PROMPTS.inc()


def record_response(success: bool, response_time: float = 0):
    """Record a response (success or error)."""
    if success:
        SUCCESSFUL_RESPONSES.inc()
        if response_time > 0:
            AVERAGE_RESPONSE_TIME.set(response_time)
    else:
        ERROR_RESPONSES.inc()


def update_custom_metrics(metrics_data: Dict[str, Any]):
    """Update custom metrics from the MetricsCollector."""
    if 'total_prompts' in metrics_data:
        # This is handled by record_prompt_processing()
        pass
    
    if 'successful_responses' in metrics_data:
        # This is handled by record_response()
        pass
        
    if 'errors' in metrics_data:
        # This is handled by record_response()
        pass
        
    if 'average_response_time' in metrics_data:
        AVERAGE_RESPONSE_TIME.set(metrics_data['average_response_time'])
    
    # Handle custom metrics
    if 'custom_metrics' in metrics_data:
        for name, value in metrics_data['custom_metrics'].items():
            # For demonstration - in practice you might want to create specific metrics
            # based on the type of custom metrics you're collecting
            pass


# Global metrics server instance
_metrics_server = None


def get_metrics_server() -> MetricsServer:
    """Get the global metrics server instance."""
    global _metrics_server
    if _metrics_server is None:
        _metrics_server = MetricsServer()
    return _metrics_server


def start_metrics_server():
    """Start the global metrics server."""
    server = get_metrics_server()
    server.start()


def stop_metrics_server():
    """Stop the global metrics server."""
    global _metrics_server
    if _metrics_server:
        _metrics_server.stop()
