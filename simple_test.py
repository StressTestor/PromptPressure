"""
Simple test for metrics functionality.
"""

from metrics import MetricsCollector

collector = MetricsCollector()
collector.record_success(0.5)
metrics = collector.get_metrics()
print("Metrics collected successfully:")
print(f"Total prompts: {metrics['total_prompts']}")
print(f"Successful responses: {metrics['successful_responses']}")
print(f"Average response time: {metrics['average_response_time']}")
