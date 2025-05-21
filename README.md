# CDP Signal Scanner

A CLI tool that scans multiple data sources to detect companies showing interest in Customer Data Platforms, scoring and categorizing the signals.

## Overview

CDP Signal Scanner helps identify companies that might be in the market for a Customer Data Platform (CDP) solution by gathering signals from:

- Greenhouse Job Board API
- Indeed (via SerpAPI)
- Company careers pages
- Google Custom Search API

The tool classifies each signal into categories like hiring for target personas, executive moves, technology signals, and growth/funding news. It then scores these signals to help prioritize companies with the strongest buying intent.

## Features

- **Multiple data sources**: Gathers signals from job boards, news, company websites, and search engines
- **Intelligent classification**: Categorizes signals by type of buying indicator
- **Configurable scoring**: Weights different signal types based on their importance
- **Parallel processing**: Uses asyncio to efficiently gather data from multiple sources
- **Rate limiting & backoff**: Respects API rate limits and implements exponential backoff on failures
- **CSV output**: Saves results to a structured CSV file for easy analysis

## Installation

1. Clone this repository
2. Install dependencies:

```bash
pip install -r requirements.txt
