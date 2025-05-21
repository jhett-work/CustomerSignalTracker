"""
Unit tests for the scoring module.
"""

import pytest
from cdp_signal_scanner.scoring import SignalScorer


def test_score_hiring_target_persona_with_cdp_keywords():
    """Test scoring a hiring signal with CDP keywords."""
    config = {
        "hiring_target_persona_with_cdp_keywords": 5,
        "executive_move_target_persona": 4,
        "explicit_cdp_vendor_mention": 4,
        "unified_data_concepts": 3,
        "funding_or_expansion": 2
    }
    
    scorer = SignalScorer(config)
    
    signal = {
        "signal_category": "hiring_target_persona",
        "snippet": "Director Data Platform with experience in customer data platforms and Segment."
    }
    
    score = scorer.score_signal(signal)
    assert score == 5  # Should get the full 5 points for the matching category


def test_score_executive_move():
    """Test scoring an executive movement signal."""
    config = {
        "hiring_target_persona_with_cdp_keywords": 5,
        "executive_move_target_persona": 4,
        "explicit_cdp_vendor_mention": 4,
        "unified_data_concepts": 3,
        "funding_or_expansion": 2
    }
    
    scorer = SignalScorer(config)
    
    signal = {
        "signal_category": "executive_move",
        "snippet": "ACME Corp appoints new VP of Marketing to lead data-driven initiatives."
    }
    
    score = scorer.score_signal(signal)
    assert score == 4  # Should get 4 points for executive move


def test_score_technology_signal_with_cdp_vendor():
    """Test scoring a technology signal with CDP vendor mention."""
    config = {
        "hiring_target_persona_with_cdp_keywords": 5,
        "executive_move_target_persona": 4,
        "explicit_cdp_vendor_mention": 4,
        "unified_data_concepts": 3,
        "funding_or_expansion": 2
    }
    
    scorer = SignalScorer(config)
    
    signal = {
        "signal_category": "technology_signal",
        "snippet": "ACME Corp selects Segment as its Customer Data Platform for unified profiles."
    }
    
    score = scorer.score_signal(signal)
    # Should get 4 for explicit mention plus 3 for unified data concepts
    assert score == 7


def test_score_growth_funding():
    """Test scoring a growth/funding signal."""
    config = {
        "hiring_target_persona_with_cdp_keywords": 5,
        "executive_move_target_persona": 4,
        "explicit_cdp_vendor_mention": 4,
        "unified_data_concepts": 3,
        "funding_or_expansion": 2
    }
    
    scorer = SignalScorer(config)
    
    signal = {
        "signal_category": "growth_funding",
        "snippet": "ACME Corp announces Series C funding to accelerate global expansion."
    }
    
    score = scorer.score_signal(signal)
    assert score == 2  # Should get 2 points for growth/funding


def test_score_with_unified_data_concepts():
    """Test scoring a signal with unified data concepts."""
    config = {
        "hiring_target_persona_with_cdp_keywords": 5,
        "executive_move_target_persona": 4,
        "explicit_cdp_vendor_mention": 4,
        "unified_data_concepts": 3,
        "funding_or_expansion": 2
    }
    
    scorer = SignalScorer(config)
    
    signal = {
        "signal_category": "other",
        "snippet": "ACME Corp implements customer 360 view for better personalization."
    }
    
    score = scorer.score_signal(signal)
    assert score == 3  # Should get 3 points for unified data concepts


def test_score_other_category():
    """Test scoring a signal with 'other' category but relevant content."""
    config = {
        "hiring_target_persona_with_cdp_keywords": 5,
        "executive_move_target_persona": 4,
        "explicit_cdp_vendor_mention": 4,
        "unified_data_concepts": 3,
        "funding_or_expansion": 2
    }
    
    scorer = SignalScorer(config)
    
    signal = {
        "signal_category": "other",
        "snippet": "ACME Corp mentions Segment in latest blog post."
    }
    
    score = scorer.score_signal(signal)
    # Should get 4 points for mentioning a CDP vendor
    assert score == 4


def test_score_multiple_factors():
    """Test scoring a signal with multiple scoring factors."""
    config = {
        "hiring_target_persona_with_cdp_keywords": 5,
        "executive_move_target_persona": 4,
        "explicit_cdp_vendor_mention": 4,
        "unified_data_concepts": 3,
        "funding_or_expansion": 2
    }
    
    scorer = SignalScorer(config)
    
    signal = {
        "signal_category": "technology_signal",
        "snippet": "ACME Corp implements mParticle for customer 360 view and real-time personalization."
    }
    
    score = scorer.score_signal(signal)
    # Should get 4 for explicit vendor mention plus 3 for unified data concepts
    assert score == 7


def test_score_with_empty_snippet():
    """Test scoring a signal with an empty snippet."""
    config = {
        "hiring_target_persona_with_cdp_keywords": 5,
        "executive_move_target_persona": 4,
        "explicit_cdp_vendor_mention": 4,
        "unified_data_concepts": 3,
        "funding_or_expansion": 2
    }
    
    scorer = SignalScorer(config)
    
    signal = {
        "signal_category": "technology_signal",
        "snippet": ""
    }
    
    score = scorer.score_signal(signal)
    # Should get the base score for the category (2)
    assert score == 2


def test_score_with_custom_config():
    """Test scoring with a custom configuration."""
    config = {
        "hiring_target_persona_with_cdp_keywords": 10,  # Higher value than default
        "executive_move_target_persona": 8,
        "explicit_cdp_vendor_mention": 7,
        "unified_data_concepts": 5,
        "funding_or_expansion": 3
    }
    
    scorer = SignalScorer(config)
    
    signal = {
        "signal_category": "hiring_target_persona",
        "snippet": "Director Data Platform with experience in customer data platforms and Segment."
    }
    
    score = scorer.score_signal(signal)
    assert score == 10  # Should use the custom config value
