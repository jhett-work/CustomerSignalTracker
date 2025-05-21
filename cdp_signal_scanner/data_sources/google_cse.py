"""
Google Custom Search Engine data source for CDP Signal Scanner.
"""

import os
import logging
import asyncio
from typing import Dict, List, Any, Optional
import httpx
from urllib.parse import quote

from .base import DataSourceBase

logger = logging.getLogger(__name__)


class GoogleCSESource(DataSourceBase):
    """
    Fetches search results from Google Custom Search API to identify
    news, blogs, press releases, and product pages related to CDPs.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Google CSE data source.
        
        Args:
            config: Configuration dictionary
        """
        super().__init__(config)
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.cse_id = os.getenv("GOOGLE_CSE_ID")
        
        if not self.api_key:
            logger.warning("GOOGLE_API_KEY not found in environment variables")
        if not self.cse_id:
            logger.warning("GOOGLE_CSE_ID not found in environment variables")
    
    async def gather_signals(self, company: str) -> List[Dict[str, Any]]:
        """
        Gather news and press signals from Google CSE API.
        
        Args:
            company: Name of the company to scan
            
        Returns:
            List of signal dictionaries
        """
        signals = []
        
        # If we have CSE ID but no API key, use fallback mechanism
        if not self.api_key and self.cse_id:
            logger.info(f"Using fallback Google CSE approach for {company} (CSE ID available but no API key)")
            return await self._fallback_search_without_api(company)
            
        # If neither is available, skip this source
        if not self.api_key or not self.cse_id:
            logger.error("Skipping Google CSE scan: API key or CSE ID not set")
            return signals
        
        try:
            # Create search queries based on signals we're looking for
            queries = []
            
            # Add CDP vendor related queries
            for vendor in self.config["keywords"]["cdp_vendors"]:
                queries.append(f'"{company}" "{vendor}"')
            
            # Add CDP concept related queries
            for concept in self.config["keywords"]["cdp_related"]:
                queries.append(f'"{company}" "{concept}"')
            
            # Add data tech related queries
            for tech in self.config["keywords"]["data_tech"]:
                queries.append(f'"{company}" "{tech}"')
            
            # Add executive movement queries
            queries.append(f'"{company}" "appoints" "chief" OR "vp" OR "director"')
            queries.append(f'"{company}" "hires" "chief" OR "vp" OR "director"')
            
            # Add funding and growth queries
            queries.append(f'"{company}" "funding" OR "series" OR "raised"')
            queries.append(f'"{company}" "expansion" OR "launches" OR "growth"')
            
            # Process each query with rate limiting
            for i, query in enumerate(queries):
                # Apply rate limiting as Google CSE has strict quotas
                if i > 0:
                    # Wait according to the rate limit in config
                    rate_limit = self.config["api"]["google_cse"]["rate_limit"]
                    await asyncio.sleep(60 / rate_limit)  # Convert to seconds
                
                results = await self._search_google(query)
                signals.extend(results)
            
            # Deduplicate signals by URL
            unique_signals = []
            seen_urls = set()
            for signal in signals:
                url = signal.get("source_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_signals.append(signal)
            
            logger.info(f"Found {len(unique_signals)} unique signals from Google CSE for {company}")
            return unique_signals
            
        except Exception as e:
            logger.error(f"Error fetching Google CSE data for {company}: {str(e)}")
            # Try a fallback approach with a simpler query if quota is exhausted
            if "quota" in str(e).lower():
                logger.info(f"Trying fallback Google CSE approach for {company}")
                return await self._fallback_search(company)
            raise
    
    async def _search_google(self, query: str) -> List[Dict[str, Any]]:
        """
        Search Google using Custom Search API.
        
        Args:
            query: Search query
            
        Returns:
            List of signal dictionaries
        """
        signals = []
        
        try:
            # Prepare the Google CSE request
            encoded_query = quote(query)
            url = f"https://www.googleapis.com/customsearch/v1?key={self.api_key}&cx={self.cse_id}&q={encoded_query}"
            
            response = await self.make_request(url)
            data = response.json()
            
            # Check if we hit quota limits
            if "error" in data:
                error = data["error"]
                if error.get("code") == 429 or "quota" in error.get("message", "").lower():
                    raise Exception(f"Google CSE API quota exceeded: {error.get('message')}")
            
            # Process the search results
            items = data.get("items", [])
            
            for item in items:
                title = item.get("title", "")
                snippet = item.get("snippet", "")
                link = item.get("link", "")
                
                # Check if the result is relevant
                if self._is_relevant_result(title, snippet):
                    signal = {
                        "source": "Google CSE",
                        "source_url": link,
                        "snippet": f"{title} - {snippet}",
                        "raw_data": {
                            "title": title,
                            "snippet": snippet,
                        },
                        "signal_category": self.classify_signal({
                            "snippet": f"{title} {snippet}"
                        })
                    }
                    signals.append(signal)
            
            return signals
            
        except Exception as e:
            if "quota" in str(e).lower():
                raise  # Re-raise quota errors to trigger fallback
            logger.warning(f"Error in Google CSE search for query '{query}': {str(e)}")
            return []
    
    def _is_relevant_result(self, title: str, snippet: str) -> bool:
        """
        Check if a search result is relevant to our CDP signal search.
        
        Args:
            title: Result title
            snippet: Result snippet
            
        Returns:
            True if result is relevant
        """
        # Clean and lowercase text for matching
        clean_title = self.clean_text(title)
        clean_snippet = self.clean_text(snippet)
        
        combined_text = f"{clean_title} {clean_snippet}"
        
        # Check for CDP vendors
        if any(vendor.lower() in combined_text for vendor in self.config["keywords"]["cdp_vendors"]):
            return True
        
        # Check for CDP concepts
        if any(concept.lower() in combined_text for concept in self.config["keywords"]["cdp_related"]):
            return True
        
        # Check for combined data tech + customer terms
        data_tech_terms = [tech.lower() for tech in self.config["keywords"]["data_tech"]]
        customer_terms = ["customer", "user", "experience", "journey", "personalization", "segment"]
        
        if any(tech in combined_text for tech in data_tech_terms) and any(term in combined_text for term in customer_terms):
            return True
        
        # Check for executive movements related to data, marketing or customer experience
        exec_keywords = ["appoint", "hire", "join", "name", "chief", "vp", "director", "head of"]
        target_departments = ["data", "analytics", "marketing", "digital", "customer experience", "technology"]
        
        if any(keyword in combined_text for keyword in exec_keywords) and any(dept in combined_text for dept in target_departments):
            return True
        
        # Check for funding and growth with tech indicators
        growth_keywords = ["funding", "series", "raised", "expansion", "launches", "growth"]
        tech_indicators = ["platform", "solution", "technology", "software", "data-driven", "analytics"]
        
        if any(keyword in combined_text for keyword in growth_keywords) and any(indicator in combined_text for indicator in tech_indicators):
            return True
            
        # Special case: check for phrases that strongly indicate CDP interest
        strong_indicators = [
            "unified customer data", 
            "customer 360", 
            "single customer view",
            "first-party data strategy",
            "data activation",
            "personalization strategy"
        ]
        
        if any(indicator in combined_text for indicator in strong_indicators):
            return True
        
        return False
    
    async def _fallback_search(self, company: str) -> List[Dict[str, Any]]:
        """
        Fallback search method when Google CSE quota is exhausted.
        Uses a more targeted approach with fewer queries.
        
        Args:
            company: Company name
            
        Returns:
            List of signal dictionaries
        """
        signals = []
        
        try:
            # Create a single targeted query to minimize API usage
            cdp_vendors = " OR ".join([f'"{vendor}"' for vendor in self.config["keywords"]["cdp_vendors"][:3]])
            cdp_terms = " OR ".join([f'"{term}"' for term in self.config["keywords"]["cdp_related"][:3]])
            
            query = f'"{company}" ({cdp_vendors}) OR ({cdp_terms})'
            results = await self._search_google(query)
            signals.extend(results)
            
            return signals
            
        except Exception as e:
            logger.error(f"Fallback Google CSE search also failed for {company}: {str(e)}")
            return []
    
    async def _fallback_search_without_api(self, company: str) -> List[Dict[str, Any]]:
        """
        Fallback search method when Google API key is not available but CSE ID is.
        Uses BeautifulSoup to scrape results from the public CSE interface.
        
        Args:
            company: Company name
            
        Returns:
            List of signal dictionaries
        """
        signals = []
        
        if not self.cse_id:
            logger.error("Cannot use fallback search: CSE ID not set")
            return signals
            
        try:
            # Create targeted keyword lists for our search
            cdp_related_keywords = self.config["keywords"]["cdp_related"][:8]  # Increased from 5
            cdp_vendors = self.config["keywords"]["cdp_vendors"][:8]  # Increased from 5
            data_tech_keywords = self.config["keywords"]["data_tech"][:5]  # Added data tech keywords
            personalization_terms = ["real-time personalization", "customer journey", "personalized experience"]
            
            # Try to find signals for each keyword group
            for keyword_group, group_name in [
                (cdp_vendors, "CDP Vendors"),
                (cdp_related_keywords, "CDP Concepts"),
                (data_tech_keywords, "Data Technologies"),
                (personalization_terms, "Personalization")
            ]:
                for keyword in keyword_group:
                    # Create search query
                    query = f"{company} {keyword}"
                    logger.info(f"Performing fallback search for: {query}")
                    
                    # Use direct CSE search URL
                    encoded_query = quote(query)
                    url = f"https://cse.google.com/cse?cx={self.cse_id}&q={encoded_query}"
                    
                    try:
                        response = await self.make_request(url)
                        
                        # Use BeautifulSoup to parse the response
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Find search result items
                        results = []
                        
                        # Look for search results in common CSE formats
                        result_containers = soup.select('.gsc-webResult .gsc-result')
                        if not result_containers:
                            result_containers = soup.select('.gs-result')
                        if not result_containers:
                            result_containers = soup.select('.gsc-result')
                        
                        for result in result_containers:
                            try:
                                # Extract title, snippet and link
                                title_elem = result.select_one('.gs-title')
                                snippet_elem = result.select_one('.gs-snippet')
                                link_elem = result.select_one('a.gs-title')
                                
                                if title_elem and link_elem:
                                    title = title_elem.get_text().strip()
                                    snippet = snippet_elem.get_text().strip() if snippet_elem else ""
                                    link = link_elem.get('href', '')
                                    
                                    # Skip if no link is found
                                    if not link or not title:
                                        continue
                                        
                                    # Check if the result is relevant
                                    if self._is_relevant_result(title, snippet):
                                        signal = {
                                            "source": "Google CSE (Fallback)",
                                            "source_url": link,
                                            "snippet": f"{title} - {snippet}",
                                            "raw_data": {
                                                "title": title,
                                                "snippet": snippet,
                                                "keywords": f"{keyword} (from {group_name})"
                                            },
                                            "signal_category": self.classify_signal({
                                                "snippet": f"{title} {snippet}"
                                            })
                                        }
                                        results.append(signal)
                            except Exception as e:
                                logger.warning(f"Error processing search result: {str(e)}")
                        
                        logger.info(f"Found {len(results)} results for query '{query}'")
                        signals.extend(results)
                    
                    except Exception as e:
                        logger.warning(f"Error in fallback search for query '{query}': {str(e)}")
                        
                    # Add a small delay between requests to be polite
                    await asyncio.sleep(2)
            
            # Return unique signals
            unique_signals = []
            seen_urls = set()
            for signal in signals:
                url = signal.get("source_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_signals.append(signal)
            
            logger.info(f"Found {len(unique_signals)} unique signals from fallback CSE search for {company}")
            return unique_signals
            
        except Exception as e:
            logger.error(f"Error in fallback search without API for {company}: {str(e)}")
            return []
