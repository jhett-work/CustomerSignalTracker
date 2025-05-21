# CDP Signal Scanner Architecture Guide

## Overview

CDP Signal Scanner is a CLI tool designed to detect companies showing interest in Customer Data Platforms (CDPs). It scans multiple data sources, classifies signals, scores them, and produces a structured CSV output. The tool helps identify potential CDP customers by analyzing various indicators like job postings, executive movements, technology mentions, and growth/funding news.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

The CDP Signal Scanner follows a modular architecture with the following key components:

1. **Main CLI Application**: Central entry point that orchestrates the scanning process.
2. **Data Sources**: Pluggable modules that collect data from different sources.
3. **Signal Classification**: Logic for categorizing signals by type.
4. **Signal Scoring**: Algorithm for ranking signals by importance.
5. **Configuration Management**: YAML-based configuration system.
6. **Utility Functions**: Shared helper functions.

The system is built as a Python CLI application that uses asyncio for parallel data collection. It leverages multiple APIs (Greenhouse, SerpAPI, Google CSE) and web scraping to gather signal data.

## Key Components

### 1. CLI Interface

- Located in `cdp_signal_scanner/main.py`
- Built with Click for command-line argument parsing
- Handles company list input and output file specification
- Orchestrates the async scanning process

### 2. Data Sources

All data sources inherit from a common base class (`DataSourceBase`) that standardizes the interface and provides shared functionality:

- **Greenhouse Source**: Scrapes Greenhouse job boards for hiring signals
- **Indeed Source**: Uses SerpAPI to search Indeed for job listings
- **Careers Page Source**: Directly scrapes company career pages
- **Google CSE Source**: Uses Google Custom Search Engine for news/mentions

Each data source implements a `gather_signals` method that returns a standardized list of signal dictionaries.

### 3. Signal Classification

The system classifies signals into categories:
- Hiring for target personas
- Executive movements
- Technology signals
- Growth/funding news

Classification logic is implemented in the `DataSourceBase` class and used across all data sources.

### 4. Scoring System

The `SignalScorer` class in `cdp_signal_scanner/scoring.py` implements a weighted scoring algorithm. Different signal types are assigned point values via configuration:

- Hiring target personas with CDP keywords: 5 points
- Executive moves into target persona roles: 4 points
- Explicit CDP vendor mentions: 4 points
- Unified data concepts: 3 points
- Funding or expansion news: 2 points

### 5. Configuration System

The application uses a layered configuration approach:
- Default configuration defined in code
- External YAML configuration file (`config.yml`)
- Environment variables for sensitive information

Configuration covers scoring weights, keywords, API settings, and request parameters.

## Data Flow

1. **Input**: User provides a list of companies to scan and an output file path
2. **Configuration Loading**: System loads configuration from YAML and environment variables
3. **Data Collection**: For each company:
   - System initiates parallel scanning across all data sources
   - Each data source gathers and returns signals
4. **Processing**: System classifies and scores all collected signals
5. **Output**: Signals are formatted and saved to a CSV file

## External Dependencies

The system relies on several external services and libraries:

### APIs
- **SerpAPI**: For Indeed job search results (requires API key)
- **Google Custom Search Engine**: For news and web results (requires API key and CSE ID)
- **Greenhouse Job Board API**: For job listings (public API)

### Key Python Libraries
- **asyncio**: For parallel data collection
- **httpx**: For async HTTP requests
- **BeautifulSoup4**: For HTML parsing
- **Click**: For CLI interface
- **Pandas**: For data manipulation and CSV export
- **PyYAML**: For configuration loading
- **tenacity**: For retry logic and backoff
- **trafilatura**: For web content extraction

## Deployment Strategy

The application is designed to run as a command-line tool with the following deployment options:

1. **Local Execution**: Run directly on a local machine with Python 3.11+
2. **Replit Execution**: Configuration included for running in Replit environment
3. **Scheduled Runs**: Can be configured to run periodically via cron or other scheduler

The tool requires:
- Python 3.11 or higher
- API keys configured in environment variables
- Configuration file (default: `config.yml`)

## Development Guidelines

When extending the CDP Signal Scanner:

1. **Adding Data Sources**: Create a new class inheriting from `DataSourceBase` and implement the `gather_signals` method.
2. **Extending Classification**: Add new categories in the base source class and update scoring rules.
3. **Configuration Updates**: New parameters should be added to both the default config and example YAML.
4. **Testing**: Unit tests are provided for core components and should be extended for new functionality.

## Common Use Cases

1. **Scanning Competitor Customer Base**: Identify companies that might be evaluating CDP solutions
2. **Sales Prospecting**: Generate leads for CDP sales teams
3. **Market Research**: Track CDP adoption trends in specific industries