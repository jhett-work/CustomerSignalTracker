"""
Business documents data source for CDP Signal Scanner.
Scans 10-K reports, annual reports, investor presentations, and news sources.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup
import trafilatura

from cdp_signal_scanner.data_sources.base import DataSourceBase

logger = logging.getLogger(__name__)

class BusinessDocumentsSource(DataSourceBase):
    """
    Scans business documents including 10-K reports, annual reports,
    investor presentations, and recent news for CDP-related signals.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the business documents source.
        
        Args:
            config: Configuration dictionary
        """
        super().__init__(config)
        self.max_docs_per_source = config.get("max_docs_per_source", 5)
        self.max_age_days = config.get("max_age_days", 365)  # Default to 1 year
        
    async def gather_signals(self, company: str) -> List[Dict[str, Any]]:
        """
        Gather signals from business documents and news sources.
        
        Args:
            company: Name of the company to scan
            
        Returns:
            List of signal dictionaries
        """
        logger.info(f"Scanning business documents for {company}")
        signals = []
        
        # Gather signals from multiple document sources in parallel
        tasks = [
            self._gather_sec_filings(company),
            self._gather_investor_relations(company),
            self._gather_recent_news(company),
            self._gather_analyst_reports(company)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                source_name = ["SEC Filings", "Investor Relations", "Recent News", "Analyst Reports"][i]
                logger.error(f"Error scanning {source_name} for {company}: {str(result)}")
            else:
                if result:
                    logger.info(f"Found {len(result)} signals from {['SEC Filings', 'Investor Relations', 'Recent News', 'Analyst Reports'][i]} for {company}")
                    signals.extend(result)
        
        return signals
    
    async def _gather_sec_filings(self, company: str) -> List[Dict[str, Any]]:
        """
        Gather signals from SEC filings (10-K, 10-Q, etc).
        
        Args:
            company: Company name
            
        Returns:
            List of signal dictionaries
        """
        signals = []
        
        # Use SEC EDGAR search
        try:
            # Formulate search URL
            search_url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={quote(company)}&owner=exclude&action=getcompany"
            
            response = await self.make_request(
                search_url,
                headers={
                    "User-Agent": "CDPSignalScanner research.tool@example.com"  # SEC requires a user-agent
                }
            )
            
            # Parse results with BeautifulSoup
            soup = BeautifulSoup(response.text, "html.parser")
            filing_tables = soup.select(".tableFile2")
            
            if not filing_tables:
                logger.info(f"No SEC filings found for {company}")
                return signals
            
            # Look for 10-K (annual) and 10-Q (quarterly) reports
            filing_links = []
            
            for table in filing_tables:
                rows = table.select("tr")
                for row in rows:
                    cells = row.select("td")
                    if len(cells) >= 4:
                        filing_type = cells[0].get_text().strip()
                        filing_date = cells[3].get_text().strip()
                        
                        # Check if this is a report we're interested in and if it's recent enough
                        if filing_type in ["10-K", "10-Q", "8-K", "S-1"]:
                            try:
                                date = datetime.strptime(filing_date, "%Y-%m-%d")
                                if (datetime.now() - date).days <= self.max_age_days:
                                    # Find the document link
                                    doc_links = row.select("a[id^='documentsbutton']")
                                    if doc_links:
                                        doc_link = doc_links[0]["href"]
                                        filing_links.append({
                                            "type": filing_type,
                                            "date": filing_date,
                                            "url": urljoin("https://www.sec.gov", doc_link)
                                        })
                                        
                                        # Limit the number of filings we process
                                        if len(filing_links) >= self.max_docs_per_source:
                                            break
                            except ValueError:
                                # Skip if date parsing fails
                                continue
            
            # Process each filing to extract relevant content
            for filing in filing_links:
                try:
                    # Get the filing page
                    filing_page = await self.make_request(
                        filing["url"],
                        headers={
                            "User-Agent": "CDPSignalScanner research.tool@example.com"
                        }
                    )
                    
                    # Find the actual document link (usually an HTML or text file)
                    filing_soup = BeautifulSoup(filing_page.text, "html.parser")
                    document_links = filing_soup.select("table.tableFile a")
                    
                    # Look for the main document
                    doc_url = None
                    for link in document_links:
                        if ".htm" in link["href"].lower() and not "_def" in link["href"].lower():
                            doc_url = urljoin("https://www.sec.gov", link["href"])
                            break
                    
                    if not doc_url:
                        continue
                    
                    # Get the actual document
                    doc_response = await self.make_request(
                        doc_url,
                        headers={
                            "User-Agent": "CDPSignalScanner research.tool@example.com"
                        }
                    )
                    
                    # Extract text with trafilatura for better content extraction
                    doc_text = trafilatura.extract(doc_response.text)
                    
                    if not doc_text:
                        # Fallback to basic extraction
                        doc_soup = BeautifulSoup(doc_response.text, "html.parser")
                        doc_text = doc_soup.get_text()
                    
                    # Look for CDP-related content
                    doc_text_lower = self.clean_text(doc_text)
                    
                    # Check for CDP-related keywords
                    cdp_keywords = self.config["keywords"]["cdp_related"] + self.config["keywords"]["cdp_vendors"]
                    
                    # Find paragraphs containing CDP keywords
                    paragraphs = re.split(r'\n+', doc_text)
                    relevant_paragraphs = []
                    
                    for paragraph in paragraphs:
                        paragraph = paragraph.strip()
                        if len(paragraph) < 20:  # Skip very short paragraphs
                            continue
                            
                        cleaned_para = self.clean_text(paragraph)
                        
                        # Check if paragraph contains any CDP keywords
                        if any(keyword.lower() in cleaned_para for keyword in cdp_keywords):
                            relevant_paragraphs.append(paragraph)
                            
                            # Limit the number of paragraphs
                            if len(relevant_paragraphs) >= 5:
                                break
                    
                    # If we found relevant content, create a signal
                    if relevant_paragraphs:
                        snippet = " ... ".join(relevant_paragraphs[:3])  # First 3 paragraphs only
                        
                        if len(snippet) > 800:
                            snippet = snippet[:797] + "..."
                        
                        signal = {
                            "source": f"SEC Filing ({filing['type']})",
                            "source_url": doc_url,
                            "filing_date": filing["date"],
                            "snippet": snippet,
                            "raw_data": {
                                "filing_type": filing["type"],
                                "filing_date": filing["date"],
                                "relevant_paragraphs": relevant_paragraphs
                            }
                        }
                        
                        # Classify the signal
                        signal["signal_category"] = self.classify_signal(signal)
                        signals.append(signal)
                
                except Exception as e:
                    logger.warning(f"Error processing SEC filing {filing['url']} for {company}: {str(e)}")
                    continue
                    
                # Sleep briefly between requests to be polite to SEC servers
                await asyncio.sleep(1)
        
        except Exception as e:
            logger.error(f"Error gathering SEC filings for {company}: {str(e)}")
        
        return signals
    
    async def _gather_investor_relations(self, company: str) -> List[Dict[str, Any]]:
        """
        Gather signals from investor relations websites, annual reports, and presentations.
        
        Args:
            company: Company name
            
        Returns:
            List of signal dictionaries
        """
        signals = []
        
        try:
            # First try to locate the company's investor relations page
            company_website = await self._find_company_website(company)
            
            if not company_website:
                logger.info(f"Could not find website for {company}, skipping investor relations scan")
                return signals
            
            # Common IR page patterns
            ir_patterns = [
                "/investor-relations",
                "/investors",
                "/investor",
                "/ir",
                "/financials",
                "/annual-reports",
                "/quarterly-results",
                "/financial-information",
                "/about/investors",
                "/about/investor-relations"
            ]
            
            # Try each pattern to find the IR page
            ir_url = None
            for pattern in ir_patterns:
                test_url = urljoin(company_website, pattern)
                try:
                    response = await self.make_request(test_url, method="HEAD", timeout=5.0, follow_redirects=True)
                    if response.status_code < 400:
                        ir_url = test_url
                        break
                except:
                    continue
            
            if not ir_url:
                logger.info(f"No investor relations page found for {company}")
                return signals
            
            # Scrape the IR page for documents
            response = await self.make_request(ir_url, follow_redirects=True)
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Look for links to annual reports, presentations, etc.
            doc_links = []
            
            # Keywords that might indicate investor documents
            doc_keywords = [
                "annual report", "annual-report", "10-k", "10k",
                "investor presentation", "investor-presentation",
                "earnings", "financial results", "quarterly report",
                "investor day", "shareholder"
            ]
            
            # Find links that might be documents
            for a in soup.find_all("a"):
                href = a.get("href")
                text = a.get_text().lower().strip()
                
                if not href:
                    continue
                
                # Check if the link or its text contains document keywords
                is_doc_link = any(keyword in text or keyword in href.lower() for keyword in doc_keywords)
                
                # Check if it's a PDF or other document type
                is_document_format = any(ext in href.lower() for ext in [".pdf", ".ppt", ".pptx", ".doc", ".docx"])
                
                if (is_doc_link or is_document_format) and not "#" == href[0]:
                    full_url = href if href.startswith(("http://", "https://")) else urljoin(ir_url, href)
                    doc_links.append({
                        "url": full_url,
                        "title": text if text else "Document",
                        "type": "PDF" if ".pdf" in href.lower() else "Presentation" if any(ext in href.lower() for ext in [".ppt", ".pptx"]) else "Document"
                    })
            
            # Process the most promising documents
            doc_links = doc_links[:self.max_docs_per_source]
            
            for doc in doc_links:
                try:
                    # For PDFs and presentations, we need special handling
                    if doc["type"] in ["PDF", "Presentation"]:
                        # For now, we'll just record the link as we can't easily parse these
                        # A future enhancement could download and parse these with specialized libraries
                        
                        # Record as a potential signal based on title
                        cdp_keywords = self.config["keywords"]["cdp_related"] + self.config["keywords"]["cdp_vendors"]
                        title_lower = doc["title"].lower()
                        
                        if any(keyword.lower() in title_lower for keyword in cdp_keywords):
                            signal = {
                                "source": f"Investor {doc['type']}",
                                "source_url": doc["url"],
                                "snippet": f"Document Title: {doc['title']} - This {doc['type'].lower()} may contain CDP-related information but requires manual review",
                                "raw_data": {
                                    "document_type": doc["type"],
                                    "document_title": doc["title"]
                                }
                            }
                            
                            # Classify the signal
                            signal["signal_category"] = self.classify_signal(signal)
                            signals.append(signal)
                    else:
                        # For HTML documents, we can try to scrape them
                        try:
                            response = await self.make_request(doc["url"], follow_redirects=True)
                            
                            # Extract text with trafilatura for better content extraction
                            doc_text = trafilatura.extract(response.text)
                            
                            if not doc_text:
                                # Fallback to basic extraction
                                doc_soup = BeautifulSoup(response.text, "html.parser")
                                doc_text = doc_soup.get_text()
                            
                            # Check for CDP-related keywords
                            cdp_keywords = self.config["keywords"]["cdp_related"] + self.config["keywords"]["cdp_vendors"]
                            doc_text_lower = self.clean_text(doc_text)
                            
                            # Find paragraphs containing CDP keywords
                            paragraphs = re.split(r'\n+', doc_text)
                            relevant_paragraphs = []
                            
                            for paragraph in paragraphs:
                                paragraph = paragraph.strip()
                                if len(paragraph) < 20:  # Skip very short paragraphs
                                    continue
                                    
                                cleaned_para = self.clean_text(paragraph)
                                
                                # Check if paragraph contains any CDP keywords
                                if any(keyword.lower() in cleaned_para for keyword in cdp_keywords):
                                    relevant_paragraphs.append(paragraph)
                                    
                                    # Limit the number of paragraphs
                                    if len(relevant_paragraphs) >= 5:
                                        break
                            
                            # If we found relevant content, create a signal
                            if relevant_paragraphs:
                                snippet = " ... ".join(relevant_paragraphs[:3])  # First 3 paragraphs only
                                
                                if len(snippet) > 800:
                                    snippet = snippet[:797] + "..."
                                
                                signal = {
                                    "source": f"Investor Document ({doc['title']})",
                                    "source_url": doc["url"],
                                    "snippet": snippet,
                                    "raw_data": {
                                        "document_title": doc["title"],
                                        "relevant_paragraphs": relevant_paragraphs
                                    }
                                }
                                
                                # Classify the signal
                                signal["signal_category"] = self.classify_signal(signal)
                                signals.append(signal)
                        except Exception as e:
                            logger.warning(f"Error processing investor document {doc['url']}: {str(e)}")
                except Exception as e:
                    logger.warning(f"Error processing investor document {doc['url']}: {str(e)}")
                
                # Sleep briefly between requests
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error gathering investor relations documents for {company}: {str(e)}")
        
        return signals
    
    async def _gather_recent_news(self, company: str) -> List[Dict[str, Any]]:
        """
        Gather signals from recent news about the company.
        
        Args:
            company: Company name
            
        Returns:
            List of signal dictionaries
        """
        signals = []
        
        try:
            # Since we don't have direct news API access, we'll try some basic approaches
            # 1. Look for news on the company website
            company_website = await self._find_company_website(company)
            
            if not company_website:
                logger.info(f"Could not find website for {company}, skipping news scan")
                return signals
            
            # Common news page patterns
            news_patterns = [
                "/news",
                "/press",
                "/press-releases",
                "/newsroom",
                "/press-room",
                "/media",
                "/media-center",
                "/about/news",
                "/about/press",
                "/corporate/news"
            ]
            
            # Try each pattern to find the news page
            news_url = None
            for pattern in news_patterns:
                test_url = urljoin(company_website, pattern)
                try:
                    response = await self.make_request(test_url, method="HEAD", timeout=5.0, follow_redirects=True)
                    if response.status_code < 400:
                        news_url = test_url
                        break
                except:
                    continue
            
            if news_url:
                # Scrape the news page for recent articles
                response = await self.make_request(news_url, follow_redirects=True)
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Look for news articles
                article_links = []
                
                # Heuristics to find news items - many sites use different structures
                # Try a variety of common patterns
                
                # 1. Look for article or news item containers
                article_containers = (
                    soup.select(".news-item, .press-release, .article, article, .news-article") or
                    soup.select("[class*=news], [class*=article], [class*=press]") or
                    soup.select(".post, .entry, .media-item")
                )
                
                if article_containers:
                    for container in article_containers[:self.max_docs_per_source]:
                        link = container.find("a")
                        if link and link.get("href"):
                            title = link.get_text().strip() or container.find("h2") or container.find("h3")
                            title = title.get_text().strip() if hasattr(title, "get_text") else str(title)
                            
                            # Try to find a date
                            date_elem = (
                                container.select_one(".date, .time, [class*=date], [class*=time]") or
                                container.find("time")
                            )
                            date = date_elem.get_text().strip() if date_elem else ""
                            
                            href = link.get("href")
                            full_url = href if href.startswith(("http://", "https://")) else urljoin(news_url, href)
                            
                            article_links.append({
                                "url": full_url,
                                "title": title,
                                "date": date
                            })
                else:
                    # 2. If we didn't find containers, just look for links that might be news
                    for a in soup.find_all("a"):
                        href = a.get("href")
                        if not href:
                            continue
                            
                        # Heuristics to identify news links
                        path_parts = href.split("/")
                        if any(part in ["news", "press", "release", "article"] for part in path_parts):
                            title = a.get_text().strip()
                            
                            if title and len(title) > 10:  # Skip very short or empty titles
                                full_url = href if href.startswith(("http://", "https://")) else urljoin(news_url, href)
                                article_links.append({
                                    "url": full_url,
                                    "title": title,
                                    "date": ""
                                })
                
                # Process the news articles
                article_links = article_links[:self.max_docs_per_source]
                
                for article in article_links:
                    try:
                        response = await self.make_request(article["url"], follow_redirects=True)
                        
                        # Extract text with trafilatura for better content extraction
                        article_text = trafilatura.extract(response.text)
                        
                        if not article_text:
                            # Fallback to basic extraction
                            article_soup = BeautifulSoup(response.text, "html.parser")
                            article_text = article_soup.get_text()
                        
                        # Check for CDP-related keywords
                        cdp_keywords = self.config["keywords"]["cdp_related"] + self.config["keywords"]["cdp_vendors"]
                        article_text_lower = self.clean_text(article_text)
                        
                        # Find paragraphs containing CDP keywords
                        paragraphs = re.split(r'\n+', article_text)
                        relevant_paragraphs = []
                        
                        for paragraph in paragraphs:
                            paragraph = paragraph.strip()
                            if len(paragraph) < 20:  # Skip very short paragraphs
                                continue
                                
                            cleaned_para = self.clean_text(paragraph)
                            
                            # Check if paragraph contains any CDP keywords
                            if any(keyword.lower() in cleaned_para for keyword in cdp_keywords):
                                relevant_paragraphs.append(paragraph)
                                
                                # Limit the number of paragraphs
                                if len(relevant_paragraphs) >= 5:
                                    break
                        
                        # If we found relevant content, create a signal
                        if relevant_paragraphs:
                            snippet = " ... ".join(relevant_paragraphs[:3])  # First 3 paragraphs only
                            
                            if len(snippet) > 800:
                                snippet = snippet[:797] + "..."
                            
                            signal = {
                                "source": f"Company News ({article['date']})" if article["date"] else "Company News",
                                "source_url": article["url"],
                                "snippet": f"{article['title']}: {snippet}",
                                "raw_data": {
                                    "article_title": article["title"],
                                    "article_date": article["date"],
                                    "relevant_paragraphs": relevant_paragraphs
                                }
                            }
                            
                            # Classify the signal
                            signal["signal_category"] = self.classify_signal(signal)
                            signals.append(signal)
                    except Exception as e:
                        logger.warning(f"Error processing news article {article['url']}: {str(e)}")
                    
                    # Sleep briefly between requests
                    await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error gathering news for {company}: {str(e)}")
        
        return signals
    
    async def _gather_analyst_reports(self, company: str) -> List[Dict[str, Any]]:
        """
        Gather signals from analyst reports.
        Note: Most analyst reports require login/subscription, so we'll look for
        public analyst commentary and perspectives.
        
        Args:
            company: Company name
            
        Returns:
            List of signal dictionaries
        """
        signals = []
        
        # This is challenging without specific API access, but we can look for
        # analyst perspectives in publicly available content
        
        try:
            # Check for analyst mentions in recent articles
            cdp_related = "+OR+".join([f'"{k}"' for k in self.config["keywords"]["cdp_related"][:5]])
            query = f"{company}+({cdp_related})+analyst+report+OR+research"
            
            # See if there are any public results with our CSE ID
            cse_id = os.getenv("GOOGLE_CSE_ID")
            if cse_id:
                encoded_query = quote(query)
                url = f"https://cse.google.com/cse?cx={cse_id}&q={encoded_query}"
                
                try:
                    response = await self.make_request(url)
                    soup = BeautifulSoup(response.text, "html.parser")
                    
                    # Find search result items
                    result_containers = (
                        soup.select(".gsc-webResult .gsc-result") or
                        soup.select(".gs-result") or
                        soup.select(".gsc-result")
                    )
                    
                    for result in result_containers[:self.max_docs_per_source]:
                        try:
                            # Extract title, snippet and link
                            title_elem = result.select_one(".gs-title")
                            snippet_elem = result.select_one(".gs-snippet")
                            link_elem = result.select_one("a.gs-title")
                            
                            if title_elem and link_elem:
                                title = title_elem.get_text().strip()
                                snippet = snippet_elem.get_text().strip() if snippet_elem else ""
                                link = link_elem.get("href", "")
                                
                                # Skip if no link is found
                                if not link or not title:
                                    continue
                                    
                                # Check for analyst-related terms
                                combined_text = (title + " " + snippet).lower()
                                if any(term in combined_text for term in ["analyst", "research", "report", "perspective", "opinion"]):
                                    signal = {
                                        "source": "Analyst Perspective",
                                        "source_url": link,
                                        "snippet": f"{title} - {snippet}",
                                        "raw_data": {
                                            "title": title,
                                            "snippet": snippet
                                        }
                                    }
                                    
                                    # Classify the signal
                                    signal["signal_category"] = self.classify_signal(signal)
                                    signals.append(signal)
                        except Exception as e:
                            logger.warning(f"Error processing search result: {str(e)}")
                except Exception as e:
                    logger.warning(f"Error querying CSE for analyst reports: {str(e)}")
        
        except Exception as e:
            logger.error(f"Error gathering analyst reports for {company}: {str(e)}")
        
        return signals
    
    async def _find_company_website(self, company: str) -> Optional[str]:
        """
        Try to find the company's primary website.
        
        Args:
            company: Company name
            
        Returns:
            Company website URL or None if not found
        """
        # Try common domain patterns
        company_slug = company.lower().replace(" ", "").replace(",", "").replace(".", "")
        company_dash = company.lower().replace(" ", "-").replace(",", "").replace(".", "")
        
        domains = [
            f"https://{company_slug}.com",
            f"https://www.{company_slug}.com",
            f"https://{company_dash}.com",
            f"https://www.{company_dash}.com"
        ]
        
        for domain in domains:
            try:
                response = await self.make_request(domain, method="HEAD", timeout=5.0, follow_redirects=True)
                if response.status_code < 400:
                    return domain
            except:
                continue
        
        # If we couldn't find the website, return None
        return None