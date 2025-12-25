from plugins.core import ScorerPlugin
from typing import Dict, Any

class LengthScorer(ScorerPlugin):
    @property
    def name(self) -> str:
        return "length_scorer"

    async def score(self, prompt: str, response: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simple scorer that calculates character and word count.
        """
        char_count = len(response)
        word_count = len(response.split())
        
        # Example logic: favorable if response is not empty
        score = 1.0 if char_count > 0 else 0.0
        
        return {
            "score": score,
            "metrics": {
                "char_count": char_count,
                "word_count": word_count
            }
        }
