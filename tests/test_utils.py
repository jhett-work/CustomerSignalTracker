"""
Unit tests for the utilities module.
"""

import pytest
from cdp_signal_scanner.utils import clean_company_name, extract_domain, extract_keywords


def test_clean_company_name():
    """Test company name cleaning function."""
    assert clean_company_name("Acme Inc.") == "Acme"
    assert clean_company_name("Acme, Inc.") == "Acme"
    assert clean_company_name("Acme Corp") == "Acme"
    assert clean_company_name("Acme LLC") == "Acme"
    assert clean_company_name("Acme Ltd.") == "Acme"
    assert clean_company_name("Acme   Corporation") == "Acme"
    assert clean_company_name("ACME.com, Inc") == "ACMEcom"


def test_extract_domain():
    """Test domain extraction function."""
    assert extract_domain("https://www.example.com/path") == "example.com"
    assert extract_domain("http://subdomain.example.co.uk/") == "subdomain.example.co.uk"
    assert extract_domain("https://example.com") == "example.com"
    assert extract_domain("not-a-url") is None


def test_extract_keywords():
    """Test keyword extraction function."""
    keywords = ["apple", "banana", "cherry"]
    
    assert extract_keywords("I like apples and bananas", keywords) == ["apple", "banana"]
    assert extract_keywords("Cherry is my favorite", keywords) == ["cherry"]
    assert extract_keywords("No matching keywords here", keywords) == []
    assert extract_keywords("", keywords) == []
    
    # Case insensitivity
    assert extract_keywords("APPLE and BANANA", keywords) == ["apple", "banana"]
    
    # Partial words shouldn't match
    text = "I have an application and a bandana"
    assert extract_keywords(text, keywords) == []
