"""
Base class for all data sources used in CDP Signal Scanner.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class DataSourceBase(ABC):
    """
    Abstract base class for all data sources.
    
    Attributes:
        config (Dict): Configuration dictionary
        client (httpx.AsyncClient): Async HTTP client for making requests
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the data source with configuration.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(config["scraping"]["timeout"]),
            headers=config["scraping"]["headers"]
        )
    
    @abstractmethod
    async def gather_signals(self, company: str) -> List[Dict[str, Any]]:
        """
        Gather signals for a company from this data source.
        
        Args:
            company: Name of the company to scan
            
        Returns:
            List of signal dictionaries
        """
        pass
    
    async def clean_up(self):
        """
        Clean up resources used by the data source.
        """
        await self.client.aclose()

    def clean_text(self, text: str) -> str:
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

    def classify_signal(self, signal: Dict[str, Any]) -> str:
        """
        Classify a signal into one of the predefined categories.
        
        Args:
            signal: Signal dictionary
            
        Returns:
            Classification category
        """
        content = self.clean_text(signal.get("snippet", ""))
        
        # Check if it's a job posting for a target persona
        if any(persona in content for persona in self.config["keywords"]["target_personas"]):
            if "job" in content or "hiring" in content or "career" in content:
                return "hiring_target_persona"
        
        # Check if it's an executive move
        if ("join" in content or "hired" in content or "appointed" in content or 
            "named" in content) and any(persona in content for persona in self.config["keywords"]["target_personas"]):
            return "executive_move"
        
        # Check if it's a technology signal
        if any(tech in content for tech in self.config["keywords"]["data_tech"]) or \
           any(vendor in content for vendor in self.config["keywords"]["cdp_vendors"]):
            return "technology_signal"
        
        # Check if it's growth or funding news
        if ("series" in content or "funding" in content or "raised" in content or 
            "investment" in content or "launch" in content or "expand" in content):
            return "growth_funding"
        
        # Default to "other" if no clear classification
        return "other"
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException))
    )
    async def make_request(self, url: str, method: str = "GET", **kwargs) -> httpx.Response:
        """
        Make an HTTP request with retry logic.
        
        Args:
            url: URL to request
            method: HTTP method to use
            **kwargs: Additional arguments to pass to httpx
            
        Returns:
            HTTP response
        """
        response = await self.client.request(method, url, **kwargs)
        response.raise_for_status()
        return response
