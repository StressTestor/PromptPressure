
import json
import pytest
from metrics import MetricsCollector, MetricsAnalyzer, get_metrics_analyzer

def custom_word_count_metric(prompt, response, **kwargs):
    return len(response.split())

def custom_word_density_metric(prompt, response, **kwargs):
    words = len(response.split())
    chars = len(response)
    if chars == 0:
        return 0
    return words / chars

def test_metrics_collection_full():
    collector = MetricsCollector()
    
    # Record some events
    # collector.record_prompt() metrics are updated in record_success/error
    collector.record_success(0.5)
    collector.record_success(0.7)
    collector.record_error(ValueError("Test error"), "Error prompt")
    
    metrics = collector.get_metrics()
    
    assert metrics["total_prompts"] == 3
    assert metrics["successful_responses"] == 2
    assert metrics["errors"] == 1
    # Average of 0.5 and 0.7 is 0.6
    assert abs(metrics["average_response_time"] - 0.6) < 0.0001
    assert len(metrics["error_details"]) == 1
    assert metrics["error_details"][0]["error_type"] == "ValueError"


def test_metrics_analysis_full():
    analyzer = get_metrics_analyzer()
    
    results = [
        {"response": "Short response"},
        {"response": "A slightly longer response with more words"}
    ]
    
    metrics = analyzer.calculate_metrics(results)
    
    metrics = analyzer.calculate_metrics(results)
    
    assert "response_length" in metrics["custom_metrics_results"]
    assert metrics["total_evaluations"] == 2
    assert metrics["custom_metrics_results"]["response_length"]["mean"] > 0

def test_custom_metrics_full():
    # Reset analyzer singleton-ish behavior if needed, or just use it
    analyzer = get_metrics_analyzer()
    analyzer.register_metric_function("word_density", custom_word_density_metric)
    
    results = [
        {"response": "High density short response."},
        {"response": "This    response    has    lots    of    spaces    but    fewer    words."}
    ]
    
    metrics = analyzer.calculate_metrics(results)
    
    assert "custom_metrics_results" in metrics
    assert "word_density" in metrics["custom_metrics_results"]
