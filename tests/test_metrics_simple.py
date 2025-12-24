
from metrics import MetricsCollector

def test_metrics_simple_collection():
    collector = MetricsCollector()
    collector.record_success(0.5)
    metrics = collector.get_metrics()
    
    assert metrics['total_prompts'] == 1
    
    assert metrics['successful_responses'] == 1
    assert metrics['average_response_time'] == 0.5
