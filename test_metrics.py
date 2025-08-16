"""
Test script for the metrics collection functionality.
"""

import json
from metrics import MetricsCollector, MetricsAnalyzer

def test_metrics_collection():
    """Test the basic metrics collection functionality."""
    print("Testing metrics collection...")
    
    # Create a metrics collector
    collector = MetricsCollector()
    
    # Simulate some successful responses
    collector.record_success(0.5)
    collector.record_success(0.7)
    collector.record_success(0.6)
    
    # Simulate an error
    try:
        raise ValueError("Test error")
    except Exception as e:
        collector.record_error(e, "Test prompt")
    
    # Add a custom metric
    collector.add_custom_metric("test_metric", 42)
    
    # Get metrics
    metrics = collector.get_metrics()
    print("Collected metrics:", json.dumps(metrics, indent=2))
    
    return metrics

def test_metrics_analysis():
    """Test the metrics analysis functionality."""
    print("\nTesting metrics analysis...")
    
    # Sample results
    results = [
        {"response": "This is a short response."},
        {"response": "This is a much longer response with more words and content to analyze."},
        {"response": "Medium length response here."}
    ]
    
    # Get analyzer
    analyzer = get_metrics_analyzer()
    
    # Calculate metrics
    metrics = analyzer.calculate_metrics(results)
    print("Calculated metrics:", json.dumps(metrics, indent=2))
    
    # Generate report
    report_path = analyzer.generate_report(metrics, ".")
    print(f"Report generated at: {report_path}")
    
    return metrics

def custom_word_density_metric(response: str) -> float:
    """Custom metric: words per character."""
    if len(response) == 0:
        return 0
    return len(response.split()) / len(response)

def test_custom_metrics():
    """Test custom metrics registration."""
    print("\nTesting custom metrics registration...")
    
    # Register custom metric
    analyzer = get_metrics_analyzer()
    analyzer.register_metric_function("word_density", custom_word_density_metric)
    
    # Sample results
    results = [
        {"response": "High density short response."},
        {"response": "This    response    has    lots    of    spaces    but    fewer    words."}
    ]
    
    # Calculate metrics
    metrics = analyzer.calculate_metrics(results)
    print("Custom metrics:", json.dumps(metrics["custom_metrics_results"], indent=2))

if __name__ == "__main__":
    from metrics import get_metrics_analyzer
    
    # Run tests
    test_metrics_collection()
    test_metrics_analysis()
    test_custom_metrics()
    
    print("\nAll tests completed successfully!")
