"""
Enhanced metrics collection and analysis for PromptPressure Eval Suite.

This module provides extensible metrics collection capabilities including:
- Time tracking for API calls
- Error rate monitoring
- Response quality metrics
- Custom user-defined metrics
- Aggregation and reporting functions
"""

import time
import json
import os
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime
class MetricsCollector:
    """Collects and manages evaluation metrics."""
    
    def __init__(self):
        self.metrics = {
            "total_prompts": 0,
            "successful_responses": 0,
            "errors": 0,
            "total_response_time": 0.0,
            "average_response_time": 0.0,
            "error_details": [],
            "custom_metrics": {},
            "timestamp": datetime.now().isoformat()
        }
        
    def start_timer(self) -> float:
        """Start timing an operation."""
        return time.time()
        
    def end_timer(self, start_time: float) -> float:
        """End timing an operation and return elapsed time."""
        return time.time() - start_time
        
    def record_success(self, response_time: float):
        """Record a successful response."""
        self.metrics["total_prompts"] += 1
        self.metrics["successful_responses"] += 1
        self.metrics["total_response_time"] += response_time
        self.metrics["average_response_time"] = (
            self.metrics["total_response_time"] / self.metrics["successful_responses"]
        )
        
    def record_error(self, error: Exception, prompt: str = ""):
        """Record an error during evaluation."""
        self.metrics["total_prompts"] += 1
        self.metrics["errors"] += 1
        self.metrics["error_details"].append({
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt
        })
        
    def add_custom_metric(self, name: str, value: Any):
        """Add a custom metric."""
        self.metrics["custom_metrics"][name] = value
        
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return self.metrics.copy()
        
    def reset(self):
        """Reset metrics collection."""
        self.__init__()

def default_response_length_metric(response: str) -> int:
    """Default metric: response length."""
    return len(response)

def default_word_count_metric(response: str) -> int:
    """Default metric: word count in response."""
    return len(response.split())

class MetricsAnalyzer:
    """Analyzes collected metrics and generates reports."""
    
    def __init__(self):
        self.custom_metrics_functions: Dict[str, Callable] = {
            "response_length": default_response_length_metric,
            "word_count": default_word_count_metric
        }
        
    def register_metric_function(self, name: str, func: Callable):
        """Register a custom metric calculation function."""
        self.custom_metrics_functions[name] = func
        
    def calculate_metrics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate metrics from evaluation results."""
        metrics = {
            "total_evaluations": len(results),
            "custom_metrics_results": {}
        }
        
        # Calculate custom metrics for each result
        for name, func in self.custom_metrics_functions.items():
            try:
                metric_values = [func(result["response"]) for result in results if "response" in result]
                if metric_values:
                    metrics["custom_metrics_results"][name] = {
                        "mean": sum(metric_values) / len(metric_values),
                        "min": min(metric_values),
                        "max": max(metric_values),
                        "total": sum(metric_values)
                    }
            except Exception as e:
                metrics["custom_metrics_results"][name] = {
                    "error": f"Failed to calculate metric: {str(e)}"
                }
                
        return metrics
        
    def generate_report(self, metrics: Dict[str, Any], output_dir: str) -> str:
        """Generate a metrics report and save to file."""
        report_path = os.path.join(output_dir, "metrics_report.json")
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "metrics": metrics
        }
        
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
            
        return report_path

def get_metrics_analyzer() -> MetricsAnalyzer:
    """Get a singleton instance of MetricsAnalyzer."""
    if not hasattr(get_metrics_analyzer, "_instance"):
        get_metrics_analyzer._instance = MetricsAnalyzer()
    return get_metrics_analyzer._instance
