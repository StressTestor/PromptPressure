import os
import json
from datetime import datetime
from typing import Dict, List, Any
from pathlib import Path
import jinja2

class ReportGenerator:
    def __init__(self, output_dir: str, config: Dict[str, Any]):
        self.output_dir = output_dir
        self.config = config
        self.template_dir = config.get("report_template_dir", "templates")
        self.formats = config.get("report_formats", ["html", "markdown"])
        
        # Setup Jinja2 environment
        # We look for templates in the project root's 'templates' dir
        project_root = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(project_root, self.template_dir)
        
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        
        # Add custom filters
        self.env.filters['datetime'] = self._format_datetime

    def _format_datetime(self, value, format="%Y-%m-%d %H:%M:%S"):
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value).strftime(format)
        return value

    def generate(self, results: List[Dict], metrics: Dict[str, Any] = None, analysis: List[Dict] = None):
        """
        Generate reports based on the configured formats.
        
        Args:
            results: List of evaluation result dictionaries
            metrics: Dictionary containing collected metrics (optional)
            analysis: List of post-analysis results with scores (optional)
        """
        data = self._prepare_data(results, metrics, analysis)
        
        generated_files = []
        for fmt in self.formats:
            try:
                if fmt.lower() == 'html':
                    path = self._generate_html(data)
                    generated_files.append(path)
                elif fmt.lower() == 'markdown':
                    path = self._generate_markdown(data)
                    generated_files.append(path)
            except Exception as e:
                print(f"Error generating {fmt} report: {e}")
                
        return generated_files

    def _prepare_data(self, results, metrics, analysis):
        """Prepare data structure for templates."""
        # Merge analysis scores into results if available
        if analysis:
            # Create a map of id -> scores
            score_map = {item.get('id'): item.get('scores') for item in analysis}
            for item in results:
                if item.get('id') in score_map:
                    item['scores'] = score_map[item['id']]

        # Calculate summary stats
        total = len(results)
        # Assuming simple pass/fail isn't directly available unless we have scores.
        # If we have scores, we can calculate a "pass" if all boolean flags are true?
        # For now, let's just pass the raw data and let the template decide or calculate simple stats here.
        
        return {
            "timestamp": datetime.now(),
            "config": self.config,
            "results": results,
            "metrics": metrics or {},
            "analysis_available": bool(analysis),
            "total_evals": total
        }

    def _generate_html(self, data):
        template = self.env.get_template("report_default.html")
        output = template.render(**data)
        outfile = os.path.join(self.output_dir, "report.html")
        with open(outfile, "w", encoding="utf-8") as f:
            f.write(output)
        return outfile

    def _generate_markdown(self, data):
        template = self.env.get_template("report_default.md")
        output = template.render(**data)
        outfile = os.path.join(self.output_dir, "report.md")
        with open(outfile, "w", encoding="utf-8") as f:
            f.write(output)
        return outfile
