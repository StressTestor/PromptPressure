import importlib
import inspect
import sys
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger("promptpressure.plugins")

class ScorerPlugin(ABC):
    """
    Abstract base class for third-party scorer plugins.
    Plugins must implement the `score` method.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the scorer."""
        pass

    @abstractmethod
    async def score(self, prompt: str, response: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate a score for the given response.
        
        Args:
            prompt: The input prompt.
            response: The model's response.
            metadata: Additional metadata (latency, config, etc.).
            
        Returns:
            Dict containing 'score' (float/int) and optionally 'reason' (str) or other metrics.
        """
        pass

class PluginInstaller:
    """Handles installation of plugins from external sources."""
    
    @staticmethod
    def install(source: str):
        """Install a plugin from a source string (git url or pip package)."""
        import subprocess
        import sys
        
        logger.info(f"Installing plugin from source: {source}")
        
        # Security Note: verifying source is trusted would happen here
        if source.startswith("git+"):
            # Installing from git
            subprocess.check_call([sys.executable, "-m", "pip", "install", source])
        elif source == "local":
            # Just a placeholder for local plugins
            pass
        else:
            # Assume pip package
            subprocess.check_call([sys.executable, "-m", "pip", "install", source])

class PluginManager:
    def __init__(self, plugin_dir: str = "plugins"):
        self.plugin_dir = plugin_dir
        self.scorers: Dict[str, ScorerPlugin] = {}
        self.registry_path = "registry.json"
        
    def list_available_plugins(self) -> List[Dict[str, str]]:
        """List plugins available in the registry."""
        import json
        if not os.path.exists(self.registry_path):
            return []
        with open(self.registry_path, 'r') as f:
            return json.load(f)
            
    def install_plugin(self, name: str):
        """Install a plugin by name from the registry."""
        registry = self.list_available_plugins()
        plugin_info = next((p for p in registry if p["name"] == name), None)
        if not plugin_info:
            raise ValueError(f"Plugin '{name}' not found in registry")
            
        PluginInstaller.install(plugin_info["source"])
        # Reload plugins after installation
        self.load_plugins()

    def load_plugins(self):
        """
        Discover and load ScorerPlugin implementations from the plugin directory.
        """
        if not os.path.exists(self.plugin_dir):
            logger.info(f"Plugin directory '{self.plugin_dir}' not found. Skipping plugin loading.")
            return

        sys.path.insert(0, os.getcwd())  # Ensure CWD is in path to import plugins

        for filename in os.listdir(self.plugin_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                try:
                    module_path = f"{self.plugin_dir.replace('/', '.')}.{module_name}"
                    module = importlib.import_module(module_path)
                    
                    for name, obj in inspect.getmembers(module):
                        if (inspect.isclass(obj) 
                            and issubclass(obj, ScorerPlugin) 
                            and obj is not ScorerPlugin):
                            
                            instance = obj()
                            self.scorers[instance.name] = instance
                            logger.info(f"Loaded plugin: {instance.name}")
                            
                except Exception as e:
                    logger.error(f"Failed to load plugin {filename}: {e}")

    async def run_scorers(self, prompt: str, response: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run all loaded scorers on the given input/output.
        """
        results = {}
        for name, scorer in self.scorers.items():
            try:
                score_result = await scorer.score(prompt, response, metadata)
                results[name] = score_result
            except Exception as e:
                logger.error(f"Error running scorer {name}: {e}")
                results[name] = {"error": str(e)}
        return results
