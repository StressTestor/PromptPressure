
import os
import pytest
from reporting import ReportGenerator

@pytest.fixture
def sample_results():
    return [
        {"id": "1", "prompt": "test prompt", "response": "test response", "model": "mock", "scores": {"compliance": True}}
    ]

@pytest.fixture
def mock_config(tmp_path):
    return {
        "output_dir": str(tmp_path),
        "collect_metrics": True,
        "model_name": "Test Model",
        "adapter": "mock",
        "report_template_dir": "templates" # Relative to project root, might need adjustment in test env
    }

def test_report_generator_init(tmp_path):
    config = {"output_dir": str(tmp_path)}
    generator = ReportGenerator(str(tmp_path), config)
    assert generator.output_dir == str(tmp_path)

def test_html_report_generation(tmp_path, sample_results):
    # We need to ensure the template dir exists or is found.
    # The ReportGenerator looks for 'templates' in project root relative to its file.
    # Since we are running tests, the relative path from project root should work if CWD is correct.
    
    config = {
        "output_dir": str(tmp_path), 
        "model_name": "TestMe", 
        "adapter": "mock",
        "report_formats": ["html"]
    }
    generator = ReportGenerator(str(tmp_path), config)
    
    # We rely on the actual templates existing in the source tree
    files = generator.generate(sample_results, metrics={"errors": 0})
    
    assert len(files) == 1
    assert files[0].endswith("report.html")
    assert os.path.exists(files[0])
    
    with open(files[0], 'r') as f:
        content = f.read()
        assert "TestMe" in content
        assert "test response" in content

def test_markdown_report_generation(tmp_path, sample_results):
    config = {
        "output_dir": str(tmp_path), 
        "model_name": "TestMe", 
        "adapter": "mock",
        "report_formats": ["markdown"]
    }
    generator = ReportGenerator(str(tmp_path), config)
    
    files = generator.generate(sample_results, metrics={"errors": 0})
    
    assert len(files) == 1
    assert files[0].endswith("report.md")
    assert os.path.exists(files[0])
    
    with open(files[0], 'r') as f:
        content = f.read()
        assert "**Model:** TestMe" in content
        assert "test response" in content
