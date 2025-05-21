#!/usr/bin/env python3
"""
Main entry point for the CDP Signal Scanner CLI application.
Scans multiple data sources to detect companies showing interest in Customer Data Platforms.
"""

import os
import asyncio
import logging
from typing import List, Optional
import csv
import pandas as pd
import click
from dotenv import load_dotenv

from .config import load_config
from .data_sources.greenhouse import GreenhouseSource
from .data_sources.indeed import IndeedSource
from .data_sources.careers_page import CareersPageSource
from .data_sources.google_cse import GoogleCSESource
from .data_sources.business_documents import BusinessDocumentsSource
from .scoring import SignalScorer

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("cdp-signal-scanner")

# Load environment variables from .env file
load_dotenv()


async def scan_company(company: str, config: dict, scorer: SignalScorer) -> List[dict]:
    """
    Scan a single company for CDP signals across all data sources.
    
    Args:
        company: Name of the company to scan
        config: Configuration dictionary
        scorer: SignalScorer instance for scoring signals
        
    Returns:
        List of signal dictionaries with classification and scores
    """
    logger.info(f"Scanning company: {company}")
    
    # Initialize data sources
    greenhouse = GreenhouseSource(config)
    careers = CareersPageSource(config)
    business_docs = BusinessDocumentsSource(config)
    
    # Check which API-dependent sources we can use
    google_cse = None
    indeed = None
    
    # Initialize Google CSE source if CSE ID is available (can work without API key)
    if os.getenv("GOOGLE_CSE_ID"):
        google_cse = GoogleCSESource(config)
    
    if os.getenv("SERPAPI_API_KEY"):
        indeed = IndeedSource(config)
    
    # Gather signals from available sources in parallel
    tasks = [
        greenhouse.gather_signals(company),
        careers.gather_signals(company),
        business_docs.gather_signals(company),
    ]
    
    # Add optional sources if available
    if google_cse:
        tasks.append(google_cse.gather_signals(company))
    if indeed:
        tasks.append(indeed.gather_signals(company))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results and handle exceptions
    all_signals = []
    source_names = ["Greenhouse", "Careers Page", "Business Documents"] 
    if google_cse:
        source_names.append("Google CSE")
    if indeed:
        source_names.append("Indeed")
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            if i < len(source_names):
                source_name = source_names[i]
                logger.error(f"Error scanning {company} with {source_name}: {str(result)}")
        else:
            # Ensure result is a list before extending
            if result and isinstance(result, list):
                all_signals.extend(result)
    
    # Score and classify all signals
    for signal in all_signals:
        signal["score"] = scorer.score_signal(signal)
        
    return all_signals


async def scan_companies(companies: List[str]) -> pd.DataFrame:
    """
    Scan multiple companies for CDP signals.
    
    Args:
        companies: List of company names to scan
        
    Returns:
        DataFrame with aggregated signals and scores, sorted by total company score
    """
    # Load config
    config = load_config()
    
    # Initialize scorer
    scorer = SignalScorer(config["scoring"])
    
    # Scan all companies
    all_results = []
    company_scores = {}
    
    for company in companies:
        results = await scan_company(company, config, scorer)
        
        # Add company to each result and track total score
        company_total_score = 0
        for result in results:
            result["account"] = company
            company_total_score += result.get("score", 0)
        
        # Store company's total score for later sorting
        company_scores[company] = company_total_score
        all_results.extend(results)
    
    # Convert to DataFrame
    if not all_results:
        logger.warning("No signals found for any company")
        # Create empty DataFrame with expected columns
        return pd.DataFrame(columns=[
            "account", "signal_category", "snippet", "score", "source_url", "total_company_score"
        ])
    
    # Create main results DataFrame
    df = pd.DataFrame(all_results)
    
    # Add total company score to each row
    df["total_company_score"] = df["account"].map(company_scores)
    
    # Sort by total company score (descending) and then by individual signal score (descending)
    df = df.sort_values(by=["total_company_score", "score"], ascending=[False, False])
    
    # Ensure the DataFrame has all required columns
    required_columns = ["account", "signal_category", "snippet", "score", "source_url"]
    for col in required_columns:
        if col not in df.columns:
            df[col] = pd.Series("", index=df.index)
    
    # Sort by score (descending)
    df = df.sort_values("score", ascending=False)
    
    return df


@click.command()
@click.option("--companies", help="Comma-separated list of company names")
@click.option("--file", help="CSV file with company names (one per line)")
@click.option("--output", default="signals.csv", help="Output CSV file path")
def main(companies: Optional[str], file: Optional[str], output: str):
    """
    CDP Signal Scanner - Detect companies showing interest in Customer Data Platforms
    
    Scan one or more companies for signals indicating interest in CDPs,
    score and categorize the signals, and output results to a CSV file.
    """
    if not companies and not file:
        raise click.UsageError("Either --companies or --file must be provided")
    
    # Get list of companies to scan
    company_list = []
    if companies:
        company_list = [c.strip() for c in companies.split(",")]
    
    if file:
        try:
            with open(file, 'r') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row:  # Skip empty rows
                        company_list.append(row[0].strip())
        except Exception as e:
            raise click.FileError(file, hint=f"Could not read companies file: {str(e)}")
    
    if not company_list:
        raise click.UsageError("No companies provided to scan")
    
    # Run the scan
    logger.info(f"Starting scan for {len(company_list)} companies")
    
    # Create event loop and run scan
    loop = asyncio.get_event_loop()
    results_df = loop.run_until_complete(scan_companies(company_list))
    
    # Save results to CSV
    results_df.to_csv(output, index=False)
    logger.info(f"Results saved to {output}")
    
    # Print results to console
    if not results_df.empty:
        click.echo("\nResults:")
        click.echo(results_df)
    else:
        click.echo("No signals found")


if __name__ == "__main__":
    main()
