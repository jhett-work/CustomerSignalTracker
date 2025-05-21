"""
Unit tests for data source modules.
"""

import pytest
import httpx
from unittest.mock import patch, MagicMock
import asyncio
import json
from bs4 import BeautifulSoup

from cdp_signal_scanner.data_sources.base import DataSourceBase
from cdp_signal_scanner.data_sources.greenhouse import GreenhouseSource


# Test classification logic in the base class
def test_classify_signal():
    """Test signal classification in the base class."""
    config = {
        "keywords": {
            "target_personas": ["director data platform", "vp marketing", "cto"],
            "cdp_vendors": ["segment", "mparticle"],
            "data_tech": ["snowflake", "dbt"]
        }
    }
    
    class TestSource(DataSourceBase):
        async def gather_signals(self, company):
            return []
    
    source = TestSource(config)
    
    # Test hiring classification
    signal = {"snippet": "We're hiring a Director Data Platform to lead our team."}
    assert source.classify_signal(signal) == "hiring_target_persona"
    
    # Test executive move classification
    signal = {"snippet": "ACME Corp appoints new VP Marketing to lead initiatives."}
    assert source.classify_signal(signal) == "executive_move"
    
    # Test technology signal classification
    signal = {"snippet": "ACME Corp chooses Snowflake and Segment for data infrastructure."}
    assert source.classify_signal(signal) == "technology_signal"
    
    # Test growth/funding classification
    signal = {"snippet": "ACME Corp announces Series B funding round of $30M."}
    assert source.classify_signal(signal) == "growth_funding"
    
    # Test default classification
    signal = {"snippet": "ACME Corp releases quarterly report."}
    assert source.classify_signal(signal) == "other"


# Test Greenhouse source
@pytest.mark.asyncio
async def test_greenhouse_token_finder():
    """Test Greenhouse token finder logic."""
    config = {
        "scraping": {
            "timeout": 10,
            "headers": {"User-Agent": "Test"}
        },
        "keywords": {
            "target_personas": ["director data"],
            "cdp_vendors": ["segment"],
            "data_tech": ["snowflake"]
        }
    }
    
    # Mock responses for Greenhouse API attempts
    mock_responses = {
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs": httpx.Response(200, json={"jobs": []}),
        "https://boards-api.greenhouse.io/v1/boards/acmecorp/jobs": httpx.Response(404),
    }
    
    source = GreenhouseSource(config)
    
    # Mock the HTTP client's get method
    async def mock_get(url, *args, **kwargs):
        if url in mock_responses:
            return mock_responses[url]
        return httpx.Response(404)
    
    source.client.get = mock_get
    
    # Test finding a valid token
    token = await source.get_greenhouse_token("Acme")
    assert token == "acme"
    
    # Test with a company that doesn't have a Greenhouse board
    token = await source.get_greenhouse_token("Nonexistent")
    assert token is None


# Test job relevance logic in Greenhouse source
def test_greenhouse_job_relevance():
    """Test job relevance detection in Greenhouse source."""
    config = {
        "scraping": {
            "timeout": 10,
            "headers": {"User-Agent": "Test"}
        },
        "keywords": {
            "target_personas": ["director data", "vp marketing", "cto"],
            "cdp_related": ["customer data platform", "data integration"],
            "cdp_vendors": ["segment", "mparticle"],
            "data_tech": ["snowflake", "dbt"]
        }
    }
    
    source = GreenhouseSource(config)
    
    # Test relevant job titles
    assert source._is_relevant_job("Director, Data Platform", "Engineering", "") is True
    assert source._is_relevant_job("VP Marketing", "Marketing", "") is True
    assert source._is_relevant_job("Software Engineer", "Data", "Experience with Snowflake") is True
    
    # Test irrelevant job titles
    assert source._is_relevant_job("Administrative Assistant", "Operations", "") is False
    assert source._is_relevant_job("Sales Representative", "Sales", "") is False
    
    # Test target persona detection
    assert source._is_target_persona("director data platform") is True
    assert source._is_target_persona("vp marketing operations") is True
    assert source._is_target_persona("software engineer") is False
