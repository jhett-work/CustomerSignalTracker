"""
Signal scoring and classification module for CDP Signal Scanner.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class SignalScorer:
    """
    Scores signals based on configurable rules to indicate
    how strongly they suggest a company is in the market for a CDP.
    
    This class implements a simple additive scoring model
    but is designed to be easily replaced with a more sophisticated
    algorithm in the future.
    """
    
    def __init__(self, scoring_config: Dict[str, int]):
        """
        Initialize the signal scorer with scoring rules.
        
        Args:
            scoring_config: Dictionary of scoring rules and their point values
        """
        self.scoring_config = scoring_config
        logger.info("Initialized signal scorer with config: %s", scoring_config)
    
    def score_signal(self, signal: Dict[str, Any]) -> int:
        """
        Score a signal based on its content and category.
        
        Args:
            signal: Signal dictionary to score
            
        Returns:
            Numeric score indicating the signal's strength
        """
        score = 0
        category = signal.get("signal_category", "other")
        snippet = signal.get("snippet", "").lower()
        
        # Clean the snippet to improve matching
        snippet = self._clean_text(snippet)
        
        # Score based on signal category
        if category == "hiring_target_persona":
            # Check if it also has CDP keywords
            if self._contains_cdp_keywords(snippet):
                score += self.scoring_config.get("hiring_target_persona_with_cdp_keywords", 5)
            else:
                score += 2  # Base score for hiring a target persona
        
        elif category == "executive_move":
            score += self.scoring_config.get("executive_move_target_persona", 4)
        
        elif category == "technology_signal":
            # Check for explicit CDP vendor mentions
            if self._contains_cdp_vendor(snippet):
                score += self.scoring_config.get("explicit_cdp_vendor_mention", 4)
            else:
                score += 2  # Base score for technology signal
        
        elif category == "growth_funding":
            score += self.scoring_config.get("funding_or_expansion", 2)
        
        # Additional points for specific keywords or concepts
        if self._contains_unified_data_concepts(snippet):
            score += self.scoring_config.get("unified_data_concepts", 3)
        
        # If we didn't score anything but it's a valid signal, give it a base score of 1
        if score == 0 and category != "other":
            score = 1
        
        logger.debug("Scored signal with category %s: %d points", category, score)
        return score
    
    def _clean_text(self, text: str) -> str:
        """
        Clean text to improve keyword matching.
        
        Args:
            text: Text to clean
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # Convert to lowercase
        text = text.lower()
        
        # Replace punctuation with spaces
        for char in ",.!?;:()[]{}\"'":
            text = text.replace(char, " ")
        
        # Remove extra whitespace
        text = " ".join(text.split())
        
        return text
    
    def _contains_cdp_keywords(self, text: str) -> bool:
        """
        Check if text contains CDP-related keywords.
        
        Args:
            text: Text to check
            
        Returns:
            True if text contains CDP keywords
        """
        cdp_keywords = [
            "customer data platform", "cdp", "data integration", "customer 360",
            "unified data", "real-time personalization", "data orchestration",
            "customer journey", "omnichannel", "first-party data"
        ]
        return any(keyword in text for keyword in cdp_keywords)
    
    def _contains_cdp_vendor(self, text: str) -> bool:
        """
        Check if text contains CDP vendor mentions.
        
        Args:
            text: Text to check
            
        Returns:
            True if text contains CDP vendor mentions
        """
        cdp_vendors = [
            "segment", "mparticle", "rudderstack", "tealium", 
            "adobe real-time cdp", "blueconic", "lytics", "treasure data"
        ]
        return any(vendor in text for vendor in cdp_vendors)
    
    def _contains_unified_data_concepts(self, text: str) -> bool:
        """
        Check if text contains unified data concepts.
        
        Args:
            text: Text to check
            
        Returns:
            True if text contains unified data concepts
        """
        concepts = [
            "customer 360", "unified data", "real-time personalization",
            "single view of customer", "data unification", "identity resolution"
        ]
        return any(concept in text for concept in concepts)
