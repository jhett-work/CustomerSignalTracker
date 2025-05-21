"""
Company careers page scraper for CDP Signal Scanner.
"""

import os
import logging
import asyncio
from typing import Dict, List, Any, Optional
import httpx
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse

from .base import DataSourceBase

logger = logging.getLogger(__name__)


class CareersPageSource(DataSourceBase):
    """
    Scrapes company career pages to identify hiring signals related to CDPs.
    Uses BeautifulSoup for HTML parsing and respects robots.txt.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the careers page scraper.
        
        Args:
            config: Configuration dictionary
        """
        super().__init__(config)
        self.robots_cache = {}  # Cache for robots.txt rules
    
    async def gather_signals(self, company: str) -> List[Dict[str, Any]]:
        """
        Gather hiring signals from company career pages.
        
        Args:
            company: Name of the company to scan
            
        Returns:
            List of signal dictionaries
        """
        signals = []
        
        try:
            # Find company website - use multiple attempts with different patterns
            company_urls = await self._find_all_company_websites(company)
            if not company_urls:
                logger.info(f"Could not find website for {company}, skipping careers page scan")
                return signals
            
            # Try each possible company URL
            for company_url in company_urls:
                try:
                    # Find careers page URL
                    careers_url = await self._find_careers_page(company_url)
                    if careers_url:
                        # Check robots.txt before scraping
                        if not await self._can_scrape(careers_url):
                            logger.info(f"Robots.txt disallows scraping of {careers_url}, skipping")
                            continue
                        
                        # Scrape the careers page
                        logger.info(f"Scraping careers page: {careers_url}")
                        response = await self.make_request(careers_url)
                        
                        # Parse HTML
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Look for job listings
                        job_listings = await self._extract_job_listings(soup, careers_url)
                        
                        # Process each job listing
                        for job in job_listings:
                            title = job.get("title", "")
                            url = job.get("url", "")
                            description = job.get("description", "")
                            
                            # Create a signal if the job is relevant
                            if self._is_relevant_job(title, description):
                                snippet = f"{title} - {company} Careers"
                                
                                signal = {
                                    "source": "Company Careers Page",
                                    "source_url": url,
                                    "snippet": snippet,
                                    "raw_data": {
                                        "title": title,
                                        "description": description[:300] + "..." if len(description) > 300 else description
                                    },
                                    "signal_category": self.classify_signal({
                                        "snippet": f"{title} {description}"
                                    })
                                }
                                signals.append(signal)
                        
                        # If we found signals, return them; otherwise continue to the next URL
                        if signals:
                            logger.info(f"Found {len(signals)} signals from careers page for {company}")
                            return signals
                    
                    # Try to find jobs via sitemap as a fallback
                    sitemap_signals = await self._scan_sitemap(company_url)
                    if sitemap_signals:
                        signals.extend(sitemap_signals)
                        logger.info(f"Found {len(sitemap_signals)} signals from sitemap for {company}")
                        return signals
                
                except Exception as e:
                    logger.warning(f"Error processing URL {company_url} for {company}: {str(e)}")
                    continue  # Try the next URL
            
            # If we reach here with signals, return them
            if signals:
                logger.info(f"Found {len(signals)} total signals for {company}")
                return signals
                
            # No signals found from any URL
            logger.info(f"No career signals found for {company}")
            return []
            
        except Exception as e:
            logger.error(f"Error scraping career information for {company}: {str(e)}")
            return []  # Return empty list instead of raising to avoid breaking the entire scan
    
    async def _find_all_company_websites(self, company: str) -> List[str]:
        """
        Find multiple possible company website URLs using various strategies.
        
        Args:
            company: Name of the company to scan
            
        Returns:
            List of possible company website URLs
        """
        urls = []
        
        try:
            # Clean company name for various formats
            clean_company = company.replace(",", " ").replace(".", " ").strip()
            company_slug = clean_company.lower().replace(" ", "")
            company_slug_dash = clean_company.lower().replace(" ", "-")
            
            # Add common URL patterns
            urls.extend([
                f"https://{company_slug}.com",
                f"https://www.{company_slug}.com",
                f"https://{company_slug}.ai",
                f"https://www.{company_slug}.ai",
                f"https://{company_slug}.co",
                f"https://www.{company_slug}.co",
                f"https://{company_slug}.io",
                f"https://www.{company_slug}.io",
                f"https://{company_slug_dash}.com",
                f"https://www.{company_slug_dash}.com"
            ])
            
            # Use Google CSE API if available
            google_api_key = os.getenv("GOOGLE_API_KEY")
            google_cse_id = os.getenv("GOOGLE_CSE_ID")
            
            if google_api_key and google_cse_id:
                query = f"{clean_company} official website"
                url = f"https://www.googleapis.com/customsearch/v1?key={google_api_key}&cx={google_cse_id}&q={query}"
                
                try:
                    response = await self.make_request(url)
                    data = response.json()
                    
                    # Extract results that look like company websites
                    for item in data.get("items", []):
                        link = item.get("link", "")
                        # Check if it's likely a company domain
                        if self._is_likely_company_domain(link, clean_company):
                            urls.insert(0, link)  # Add to beginning of list (higher priority)
                except Exception as e:
                    logger.warning(f"Error using Google CSE for {company}: {str(e)}")
            
            # Return de-duplicated list of URLs
            return list(dict.fromkeys(urls))  # Preserves order while removing duplicates
                
        except Exception as e:
            logger.warning(f"Error finding websites for {company}: {str(e)}")
            return urls
    
    async def _find_company_website(self, company: str) -> Optional[str]:
        """
        Find the company's primary website URL.
        
        Args:
            company: Name of the company to scan
            
        Returns:
            Company website URL or None if not found
        """
        websites = await self._find_all_company_websites(company)
        return websites[0] if websites else None
    
    def _is_likely_company_domain(self, url: str, company: str) -> bool:
        """
        Check if a URL is likely to be the company's domain.
        
        Args:
            url: URL to check
            company: Company name
            
        Returns:
            True if likely a company domain
        """
        if not url:
            return False
        
        try:
            # Parse the URL
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            
            # Clean company name for comparison
            clean_company = company.lower().replace(" ", "").replace(",", "").replace(".", "")
            
            # Check if company name is in domain
            return clean_company in domain or domain.split('.')[0] in clean_company
        except:
            return False
    
    async def _find_careers_page(self, company_url: str) -> Optional[str]:
        """
        Find the careers page URL for a company.
        
        Args:
            company_url: Company website URL
            
        Returns:
            Careers page URL or None if not found
        """
        common_careers_paths = [
            "/careers", "/jobs", "/work-with-us", "/join-us", "/join-our-team",
            "/about/careers", "/about/jobs", "/company/careers", "/company/jobs",
            "/en/careers", "/en/jobs"
        ]
        
        # Check all common paths
        for path in common_careers_paths:
            try:
                careers_url = urljoin(company_url, path)
                response = await self.client.head(
                    careers_url, 
                    follow_redirects=True,
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    return careers_url
            except:
                continue
        
        # If no common path works, look for careers links on the homepage
        try:
            response = await self.make_request(company_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for links with careers-related text
            careers_keywords = ["career", "job", "join", "work with us", "position"]
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                link_text = link.get_text().lower()
                
                if any(keyword in link_text for keyword in careers_keywords):
                    return urljoin(company_url, href)
        except:
            pass
        
        return None
    
    async def _can_scrape(self, url: str) -> bool:
        """
        Check if we're allowed to scrape a URL according to robots.txt.
        
        Args:
            url: URL to check
            
        Returns:
            True if scraping is allowed
        """
        try:
            # Parse the URL
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            
            # Check cache first
            if base_url in self.robots_cache:
                return self.robots_cache[base_url]
            
            # Fetch robots.txt
            robots_url = f"{base_url}/robots.txt"
            try:
                response = await self.client.get(robots_url, timeout=5.0)
                
                if response.status_code == 200:
                    robots_txt = response.text
                    
                    # Extract user-agent and disallow rules
                    user_agent_lines = [line.strip() for line in robots_txt.split('\n') 
                                    if line.strip().lower().startswith('user-agent:')]
                    disallow_lines = [line.strip() for line in robots_txt.split('\n') 
                                   if line.strip().lower().startswith('disallow:')]
                    
                    # Check if our user-agent or * is disallowed from the URL path
                    path = parsed.path or '/'
                    
                    for disallow in disallow_lines:
                        # Extract disallowed path
                        disallowed_path = disallow.split(':', 1)[1].strip()
                        
                        # Check if our path matches the disallowed path
                        if disallowed_path and path.startswith(disallowed_path):
                            self.robots_cache[base_url] = False
                            return False
            except:
                # If robots.txt doesn't exist or can't be parsed, assume we can scrape
                pass
            
            # If we get here, scraping is allowed
            self.robots_cache[base_url] = True
            return True
            
        except Exception as e:
            logger.warning(f"Error checking robots.txt for {url}: {str(e)}")
            # Be conservative and allow scraping on error
            return True
    
    async def _extract_job_listings(self, soup: BeautifulSoup, careers_url: str) -> List[Dict[str, Any]]:
        """
        Extract job listings from a careers page.
        
        Args:
            soup: BeautifulSoup object for the careers page
            careers_url: URL of the careers page for resolving relative links
            
        Returns:
            List of job dictionaries
        """
        job_listings = []
        
        # Look for common job listing patterns
        # 1. Look for job titles in headings
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5']):
            title = heading.get_text().strip()
            
            # Check if heading looks like a job title
            if self._is_likely_job_title(title):
                # Find a nearby link
                link = heading.find_parent('a') or heading.find('a')
                url = urljoin(careers_url, link['href']) if link and link.has_attr('href') else careers_url
                
                # Try to find a description
                description = ""
                next_p = heading.find_next('p')
                if next_p:
                    description = next_p.get_text().strip()
                
                job_listings.append({
                    'title': title,
                    'url': url,
                    'description': description
                })
        
        # 2. Look for job listings in list items
        for li in soup.find_all('li'):
            # Check if list item contains a job title
            title = li.get_text().strip()
            if self._is_likely_job_title(title):
                # Find a link
                link = li.find('a')
                url = urljoin(careers_url, link['href']) if link and link.has_attr('href') else careers_url
                
                job_listings.append({
                    'title': title,
                    'url': url,
                    'description': ""
                })
        
        # 3. Look for job listings in divs with common job listing classes
        job_classes = ['job', 'position', 'opening', 'vacancy', 'career']
        for class_name in job_classes:
            for element in soup.find_all(class_=lambda c: c and class_name in c.lower()):
                # Try to find a title
                title_elem = element.find(['h1', 'h2', 'h3', 'h4', 'h5']) or element
                title = title_elem.get_text().strip()
                
                # Find a link
                link = element.find('a')
                url = urljoin(careers_url, link['href']) if link and link.has_attr('href') else careers_url
                
                # Try to find a description
                description = ""
                desc_elem = element.find('p')
                if desc_elem:
                    description = desc_elem.get_text().strip()
                
                job_listings.append({
                    'title': title,
                    'url': url,
                    'description': description
                })
        
        return job_listings
    
    def _is_likely_job_title(self, text: str) -> bool:
        """
        Check if text is likely to be a job title.
        
        Args:
            text: Text to check
            
        Returns:
            True if likely a job title
        """
        # Common job title words
        job_title_words = [
            'manager', 'director', 'engineer', 'developer', 'specialist',
            'analyst', 'coordinator', 'lead', 'head', 'chief', 'vp', 'president',
            'officer', 'cto', 'ceo', 'cmo', 'cio', 'marketing', 'data', 'product',
            'senior', 'junior', 'associate', 'principal', 'staff', 'intern'
        ]
        
        # Clean and lowercase text
        clean_text = self.clean_text(text)
        
        # Check if it contains job title words
        return any(word in clean_text for word in job_title_words)
    
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
            
        # Analytics Engineer and Data Scientist roles can be highly relevant
        if "analytics engineer" in clean_title or "data scientist" in clean_title:
            if any(keyword in clean_title or keyword in clean_desc 
                  for keyword in ["growth", "marketing", "customer"]):
                return True
                
        # Check if title contains data roles we're specifically interested in
        data_roles = ["data", "analytics", "customer insights", "audience", "segmentation"]
        if any(role in clean_title for role in data_roles):
            # Look for customer-focused terms in the description
            customer_terms = ["customer", "user", "audience", "segment", "profile", "personalization"]
            if any(term in clean_desc for term in customer_terms):
                return True
        
        # Check if any CDP-related keywords are in the title or description
        cdp_keywords = self.config["keywords"]["cdp_related"] + self.config["keywords"]["cdp_vendors"] + self.config["keywords"]["data_tech"]
        
        return any(keyword in combined_text for keyword in cdp_keywords)
    
    async def _scan_sitemap(self, company_url: str) -> List[Dict[str, Any]]:
        """
        Scan sitemap for job listings as a fallback.
        
        Args:
            company_url: Company website URL
            
        Returns:
            List of signal dictionaries
        """
        signals = []
        
        try:
            # Try to fetch the sitemap
            sitemap_url = urljoin(company_url, "/sitemap.xml")
            response = await self.client.get(sitemap_url, timeout=10.0)
            
            if response.status_code != 200:
                # Try alternative sitemap URL
                sitemap_url = urljoin(company_url, "/sitemap_index.xml")
                response = await self.client.get(sitemap_url, timeout=10.0)
            
            if response.status_code != 200:
                return signals
            
            # Parse the sitemap
            soup = BeautifulSoup(response.text, 'xml')
            
            # Look for URLs in the sitemap
            urls = []
            
            # Check for sitemap index
            for sitemap in soup.find_all('sitemap'):
                loc = sitemap.find('loc')
                if loc:
                    try:
                        # Fetch and parse the sub-sitemap
                        sub_url = loc.get_text().strip()
                        sub_response = await self.client.get(sub_url, timeout=10.0)
                        if sub_response.status_code == 200:
                            sub_soup = BeautifulSoup(sub_response.text, 'xml')
                            for url in sub_soup.find_all('url'):
                                loc = url.find('loc')
                                if loc:
                                    urls.append(loc.get_text().strip())
                    except:
                        continue
            
            # Check for direct URLs
            for url in soup.find_all('url'):
                loc = url.find('loc')
                if loc:
                    urls.append(loc.get_text().strip())
            
            # Filter URLs for potential job pages
            job_keywords = ['career', 'job', 'position', 'opening', 'vacancy']
            job_urls = [url for url in urls if any(keyword in url.lower() for keyword in job_keywords)]
            
            # Process each job URL
            for job_url in job_urls[:20]:  # Limit to 20 URLs to avoid overloading
                try:
                    job_response = await self.client.get(job_url, timeout=10.0)
                    if job_response.status_code == 200:
                        job_soup = BeautifulSoup(job_response.text, 'html.parser')
                        
                        # Extract the title from the page
                        title = job_soup.title.get_text() if job_soup.title else ""
                        
                        # Extract a description
                        description = ""
                        meta_desc = job_soup.find('meta', attrs={'name': 'description'})
                        if meta_desc and meta_desc.has_attr('content'):
                            description = meta_desc['content']
                        
                        # Check if the page is relevant
                        if self._is_relevant_job(title, description):
                            signal = {
                                "source": "Company Sitemap",
                                "source_url": job_url,
                                "snippet": title,
                                "raw_data": {
                                    "title": title,
                                    "description": description
                                },
                                "signal_category": self.classify_signal({
                                    "snippet": f"{title} {description}"
                                })
                            }
                            signals.append(signal)
                except:
                    continue
            
            return signals
            
        except Exception as e:
            logger.warning(f"Error scanning sitemap for {company_url}: {str(e)}")
            return signals
