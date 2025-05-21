"""
Indeed job search data source for CDP Signal Scanner using SerpAPI.
"""

import os
import logging
import asyncio
from typing import Dict, List, Any, Optional
from urllib.parse import quote

from .base import DataSourceBase

logger = logging.getLogger(__name__)


class IndeedSource(DataSourceBase):
    """
    Fetches job listings from Indeed using SerpAPI to identify
    hiring signals related to CDPs.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Indeed data source.
        
        Args:
            config: Configuration dictionary
        """
        super().__init__(config)
        self.api_key = os.getenv("SERPAPI_API_KEY")
        if not self.api_key:
            logger.warning("SERPAPI_API_KEY not found in environment variables")
    
    async def gather_signals(self, company: str) -> List[Dict[str, Any]]:
        """
        Gather hiring signals from Indeed via SerpAPI.
        
        Args:
            company: Name of the company to scan
            
        Returns:
            List of signal dictionaries
        """
        signals = []
        
        if not self.api_key:
            logger.error("Skipping Indeed scan: SERPAPI_API_KEY not set")
            return signals
        
        try:
            # Create search queries based on target personas and CDP keywords
            queries = []
            
            # Create queries for each target persona
            for persona in self.config["keywords"]["target_personas"]:
                queries.append(f"{persona} {company}")
            
            # Add queries for CDP-related keywords
            for keyword in self.config["keywords"]["cdp_related"]:
                queries.append(f"{keyword} {company}")
            
            # Add queries for CDP vendors
            for vendor in self.config["keywords"]["cdp_vendors"]:
                queries.append(f"{vendor} {company}")
            
            # Process each query with rate limiting
            for i, query in enumerate(queries):
                # Respect rate limits to avoid 429 errors
                if i > 0:
                    await asyncio.sleep(1)  # Simple rate limiting
                
                results = await self._search_indeed(query)
                signals.extend(results)
            
            # Deduplicate signals by URL
            unique_signals = []
            seen_urls = set()
            for signal in signals:
                url = signal.get("source_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_signals.append(signal)
            
            logger.info(f"Found {len(unique_signals)} unique signals from Indeed for {company}")
            return unique_signals
            
        except Exception as e:
            logger.error(f"Error fetching Indeed data for {company}: {str(e)}")
            raise
    
    async def _search_indeed(self, query: str) -> List[Dict[str, Any]]:
        """
        Search Indeed using SerpAPI.
        
        Args:
            query: Search query
            
        Returns:
            List of signal dictionaries
        """
        signals = []
        
        try:
            # Prepare the SerpAPI request
            encoded_query = quote(query)
            url = f"https://serpapi.com/search.json?engine=google_jobs&q={encoded_query}&api_key={self.api_key}"
            
            response = await self.make_request(url)
            data = response.json()
            
            # Process the search results
            jobs_results = data.get("jobs_results", [])
            
            for job in jobs_results:
                title = job.get("title", "")
                company_name = job.get("company_name", "")
                location = job.get("location", "")
                job_url = job.get("job_link", "")
                description = job.get("description", "")
                
                # Create a signal if the job is relevant
                if self._is_relevant_job(title, description):
                    snippet = f"{title} at {company_name} - {location}"
                    
                    signal = {
                        "source": "Indeed",
                        "source_url": job_url,
                        "snippet": snippet,
                        "raw_data": {
                            "title": title,
                            "company": company_name,
                            "location": location,
                            "description": description[:300] + "..." if len(description) > 300 else description
                        },
                        "signal_category": self.classify_signal({
                            "snippet": f"{title} {description}"
                        })
                    }
                    signals.append(signal)
            
            return signals
            
        except Exception as e:
            logger.warning(f"Error in Indeed search for query '{query}': {str(e)}")
            return []
    
    def _is_relevant_job(self, title: str, description: str) -> bool:
        """
        Check if a job is relevant to our CDP signal search.
        
        Args:
            title: Job title
            description: Job description
            
        Returns:
            True if job is relevant
        """
        # Clean and lowercase text for matching
        clean_title = self.clean_text(title)
        clean_desc = self.clean_text(description)
        
        combined_text = f"{clean_title} {clean_desc}"
        
        # Check if it's a target persona
        if any(persona in clean_title for persona in self.config["keywords"]["target_personas"]):
            return True
        
        # Check if any CDP-related keywords are in the title or description
        cdp_keywords = self.config["keywords"]["cdp_related"] + self.config["keywords"]["cdp_vendors"] + self.config["keywords"]["data_tech"]
        
        return any(keyword in combined_text for keyword in cdp_keywords)
