"""
Example script demonstrating the metrics collection functionality in PromptPressure.

This script shows how to:
1. Configure metrics collection in a YAML config
2. Run an evaluation with metrics collection enabled
3. Register custom metrics functions
4. Analyze the collected metrics
"""

import os
import json
from datetime import datetime

# Example of registering a custom metric function
def sentiment_score_metric(response: str) -> float:
    """Example custom metric that simulates sentiment scoring."""
    # In a real implementation, you would use a sentiment analysis model
    # This is just a mock implementation for demonstration
    positive_words = ['good', 'great', 'excellent', 'amazing', 'wonderful']
    negative_words = ['bad', 'terrible', 'awful', 'horrible', 'worst']
    
    words = response.lower().split()
    positive_count = sum(1 for word in words if word in positive_words)
    negative_count = sum(1 for word in words if word in negative_words)
    
    if positive_count + negative_count == 0:
        return 0.0
    
    return (positive_count - negative_count) / (positive_count + negative_count)

def create_example_config():
    """Create an example configuration file with metrics enabled."""
    config = {
        "adapter": "mock",
        "model": "test-model",
        "model_name": "Test Model",
        "dataset": "evals_dataset.json",
        "output": "example_results.csv",
        "temperature": 0.7,
        "collect_metrics": True,
        "custom_metrics": ["response_length", "word_count", "sentiment_score"]
    }
    
    with open("example_metrics_config.yaml", "w") as f:
        import yaml
        yaml.dump(config, f)
    
    print("Created example configuration: example_metrics_config.yaml")

def register_custom_metrics():
    """Register custom metrics functions."""
    from metrics import get_metrics_analyzer
    
    analyzer = get_metrics_analyzer()
    analyzer.register_metric_function("sentiment_score", sentiment_score_metric)
    
    print("Registered custom sentiment score metric")

def demonstrate_metrics_usage():
    """Demonstrate how to use the metrics functionality."""
    print("=== PromptPressure Metrics Collection Example ===\n")
    
    # 1. Create example configuration
    create_example_config()
    
    # 2. Register custom metrics
    register_custom_metrics()
    
    # 3. Explain how to run evaluation
    print("\nTo run an evaluation with metrics collection, use:")
    print("python run_eval.py --multi-config example_metrics_config.yaml")
    
    # 4. Explain what metrics are collected
    print("\nMetrics collected during evaluation:")
    print("- Response times (min, max, average)")
    print("- Error rates and details")
    print("- Custom metrics (response length, word count, sentiment score)")
    print("- Aggregated performance statistics")
    
    # 5. Explain output files
    print("\nOutput files generated:")
    print("- results.csv: Evaluation results")
    print("- results.json: Evaluation results in JSON format")
    print("- metrics.json: Detailed metrics for this run")
    print("- metrics_report.json: Custom metrics analysis report")
    
    print("\nWhen running multiple configurations, an aggregated_metrics.json file is also generated.")

if __name__ == "__main__":
    demonstrate_metrics_usage()
