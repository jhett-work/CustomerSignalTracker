"""
Utility functions for CDP Signal Scanner.
"""

import logging
import re
from typing import Dict, List, Any, Set, Optional
from urllib.parse import urlparse
import httpx
import asyncio

logger = logging.getLogger(__name__)


def clean_company_name(company: str) -> str:
    """
    Clean a company name for use in searches and URLs.
    
    Args:
        company: Raw company name
        
    Returns:
        Cleaned company name
    """
    # Remove common legal suffixes
    suffixes = [
        r"\bInc\b", r"\bInc\.\b", r"\bCorp\b", r"\bCorp\.\b", 
        r"\bLLC\b", r"\bL\.L\.C\.\b", r"\bLtd\b", r"\bLtd\.\b",
        r"\bLimited\b", r"\bLLC\.\b", r"\bCorporation\b"
    ]
    
    clean = company
    for suffix in suffixes:
        clean = re.sub(suffix, "", clean, flags=re.IGNORECASE)
    
    # Remove punctuation and excess whitespace
    clean = re.sub(r'[,\.\'"]', '', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    
    return clean


def extract_domain(url: str) -> Optional[str]:
    """
    Extract the domain name from a URL.
    
    Args:
        url: URL to extract domain from
        
    Returns:
        Domain name or None if invalid URL
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        
        # Remove www. prefix if present
        if domain.startswith('www.'):
            domain = domain[4:]
            
        return domain
    except:
        return None


async def check_robots_txt(url: str, client: httpx.AsyncClient, cache: Dict[str, Set[str]]) -> bool:
    """
    Check if scraping is allowed for a URL according to robots.txt.
    
    Args:
        url: URL to check
        client: HTTP client to use
        cache: Cache for robots.txt results
        
    Returns:
        True if scraping is allowed
    """
    try:
        # Parse the URL
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path or "/"
        
        # Check if we've already processed this domain
        if base_url in cache:
            # Check if the path is in the disallowed paths
            return not any(path.startswith(p) for p in cache[base_url])
        
        # Fetch the robots.txt file
        robots_url = f"{base_url}/robots.txt"
        try:
            response = await client.get(robots_url, timeout=5.0, follow_redirects=True)
            
            if response.status_code == 200:
                robots_txt = response.text
                
                # Extract disallowed paths
                disallowed = set()
                lines = robots_txt.split('\n')
                
                current_agent = None
                for line in lines:
                    line = line.strip()
                    
                    if not line or line.startswith('#'):
                        continue
                    
                    # Check for User-agent line
                    if line.lower().startswith('user-agent:'):
                        agent = line.split(':', 1)[1].strip()
                        current_agent = agent
                    
                    # Check for Disallow line
                    elif line.lower().startswith('disallow:') and (current_agent == '*' or current_agent == 'cdp-signal-scanner'):
                        path = line.split(':', 1)[1].strip()
                        if path:
                            disallowed.add(path)
                
                # Cache the disallowed paths
                cache[base_url] = disallowed
                
                # Check if the path is allowed
                return not any(path.startswith(p) for p in disallowed)
        except:
            # If we can't fetch or parse robots.txt, we'll be conservative and allow scraping
            cache[base_url] = set()
            return True
    except:
        # If there's any error, be conservative and allow scraping
        return True


def extract_keywords(text: str, keywords: List[str]) -> List[str]:
    """
    Extract matching keywords from text.
    
    Args:
        text: Text to search in
        keywords: List of keywords to look for
        
    Returns:
        List of found keywords
    """
    if not text:
        return []
    
    # Clean the text
    clean_text = text.lower()
    
    # Find matching keywords
    found = []
    for keyword in keywords:
        if keyword.lower() in clean_text:
            found.append(keyword)
    
    return found
