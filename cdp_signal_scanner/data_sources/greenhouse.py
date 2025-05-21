"""
Greenhouse Job Board API data source for CDP Signal Scanner.
"""

import os
import logging
import asyncio
from typing import Dict, List, Any, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
import json

from .base import DataSourceBase

logger = logging.getLogger(__name__)


class GreenhouseSource(DataSourceBase):
    """
    Fetches job listings from Greenhouse Job Board API to identify
    hiring signals related to CDPs.
    """
    
    GREENHOUSE_API_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    
    # Common Greenhouse board tokens for companies
    COMMON_TOKENS = [
        "company", "main", "careers", "jobs", "hiring",
        # Add more common token patterns here
    ]
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Greenhouse data source.
        
        Args:
            config: Configuration dictionary
        """
        super().__init__(config)
    
    async def get_greenhouse_token(self, company: str) -> Optional[str]:
        """
        Try to find the Greenhouse token for a company.
        
        Args:
            company: Company name
            
        Returns:
            Greenhouse board token or None if not found
        """
        # Try common patterns for the token
        company_slug = company.lower().replace(" ", "").replace(",", "").replace(".", "")
        company_slug_with_dash = company.lower().replace(" ", "-").replace(",", "").replace(".", "")
        
        potential_tokens = [
            company_slug,
            company_slug_with_dash,
            *[f"{company_slug}{suffix}" for suffix in self.COMMON_TOKENS],
            *[f"{company_slug_with_dash}{suffix}" for suffix in self.COMMON_TOKENS],
            *[f"{suffix}{company_slug}" for suffix in self.COMMON_TOKENS],
            *[f"{suffix}{company_slug_with_dash}" for suffix in self.COMMON_TOKENS],
        ]
        
        # Try each token until one works
        for token in potential_tokens:
            try:
                url = self.GREENHOUSE_API_URL.format(token=token)
                response = await self.client.get(url)
                if response.status_code == 200:
                    logger.info(f"Found Greenhouse token for {company}: {token}")
                    return token
            except httpx.HTTPError:
                pass
        
        logger.info(f"No Greenhouse token found for {company}")
        return None
    
    async def gather_signals(self, company: str) -> List[Dict[str, Any]]:
        """
        Gather hiring signals from Greenhouse Job Board API.
        
        Args:
            company: Name of the company to scan
            
        Returns:
            List of signal dictionaries
        """
        signals = []
        
        # Get Greenhouse token for the company
        token = await self.get_greenhouse_token(company)
        if not token:
            logger.info(f"Skipping Greenhouse scan for {company}: No token found")
            return signals
        
        try:
            # Fetch jobs from Greenhouse API
            url = self.GREENHOUSE_API_URL.format(token=token)
            response = await self.make_request(url)
            data = response.json()
            
            if "jobs" not in data:
                logger.warning(f"Unexpected Greenhouse API response for {company}")
                return signals
            
            # Process job listings
            for job in data["jobs"]:
                # Extract relevant information
                title = job.get("title", "")
                location = job.get("location", {}).get("name", "")
                department = job.get("departments", [{}])[0].get("name", "") if job.get("departments") else ""
                job_url = job.get("absolute_url", "")
                
                # Combine information into a snippet
                snippet = f"{title} - {department} - {location}"
                
                # Check if job is related to our target personas or keywords
                if self._is_relevant_job(title, department, job.get("content", "")):
                    signal = {
                        "source": "Greenhouse",
                        "source_url": job_url,
                        "snippet": snippet,
                        "raw_data": {
                            "title": title,
                            "department": department,
                            "location": location,
                        },
                        "signal_category": "hiring_target_persona" if self._is_target_persona(title) else "other"
                    }
                    signals.append(signal)
            
            logger.info(f"Found {len(signals)} signals from Greenhouse for {company}")
            return signals
            
        except Exception as e:
            logger.error(f"Error fetching Greenhouse data for {company}: {str(e)}")
            raise
    
    def _is_relevant_job(self, title: str, department: str, content: str) -> bool:
        """
        Check if a job is relevant to our CDP signal search.
        
        Args:
            title: Job title
            department: Job department
            content: Job description content
            
        Returns:
            True if job is relevant
        """
        # Clean and lowercase text for matching
        clean_title = self.clean_text(title)
        clean_dept = self.clean_text(department)
        
        # Check if it's a target persona
        if self._is_target_persona(clean_title):
            return True
        
        # Check if department is relevant
        relevant_departments = ["marketing", "data", "analytics", "engineering", "product"]
        if any(dept in clean_dept for dept in relevant_departments):
            # Check if any CDP-related keywords are in the title
            cdp_keywords = self.config["keywords"]["cdp_related"] + self.config["keywords"]["cdp_vendors"]
            if any(keyword in clean_title for keyword in cdp_keywords):
                return True
        
        return False
    
    def _is_target_persona(self, title: str) -> bool:
        """
        Check if a job title matches one of our target personas.
        
        Args:
            title: Job title to check
            
        Returns:
            True if it's a target persona
        """
        clean_title = self.clean_text(title)
        return any(persona in clean_title for persona in self.config["keywords"]["target_personas"])
