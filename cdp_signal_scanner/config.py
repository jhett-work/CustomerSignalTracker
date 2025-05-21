"""
Configuration loader and management for CDP Signal Scanner.
"""

import os
import logging
from typing import Dict, Any
import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "scoring": {
        "hiring_target_persona_with_cdp_keywords": 5,
        "executive_move_target_persona": 4,
        "explicit_cdp_vendor_mention": 4,
        "unified_data_concepts": 3,
        "funding_or_expansion": 2
    },
    "keywords": {
        "cdp_vendors": [
            "segment", "mparticle", "rudderstack", "tealium", 
            "adobe real-time cdp", "blueconic", "lytics", "treasure data"
        ],
        "target_personas": [
            "director data platform", "vp marketing", "growth marketing manager",
            "cto", "vp engineering", "director security", "marketing ops", 
            "chief marketing officer", "chief digital officer", 
            "vp product", "head of analytics", "head of data"
        ],
        "cdp_related": [
            "customer data platform", "cdp", "data integration", "customer 360",
            "unified data", "real-time personalization", "data orchestration",
            "customer journey", "omnichannel", "first-party data"
        ],
        "data_tech": [
            "snowflake", "dbt", "fivetran", "bigquery", 
            "redshift", "databricks", "data lakehouse", "data warehouse"
        ]
    },
    "api": {
        "serpapi": {
            "rate_limit": 5,  # Requests per second
            "backoff_factor": 1.5,
            "max_retries": 3
        },
        "google_cse": {
            "rate_limit": 10,  # Requests per minute
            "backoff_factor": 2,
            "max_retries": 3
        }
    },
    "scraping": {
        "timeout": 10,  # Seconds
        "max_retries": 3,
        "headers": {
            "User-Agent": "CDP Signal Scanner/0.1.0 (research tool, contact hello@example.com)"
        }
    }
}


def load_config() -> Dict[str, Any]:
    """
    Load configuration from config.yml file and merge with defaults.
    
    Returns:
        Dict containing the merged configuration
    """
    config = DEFAULT_CONFIG.copy()
    
    # Try to load config from file
    try:
        config_path = os.getenv("CONFIG_PATH", "config.yml")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    # Recursively update config with file values
                    deep_update(config, file_config)
            logger.info(f"Loaded configuration from {config_path}")
        else:
            logger.warning(f"Config file {config_path} not found, using defaults")
    except Exception as e:
        logger.warning(f"Error loading config file: {str(e)}, using defaults")
    
    return config


def deep_update(source: Dict, updates: Dict) -> Dict:
    """
    Recursively update a nested dictionary.
    
    Args:
        source: Original dictionary to update
        updates: Dictionary with updates to apply
        
    Returns:
        Updated dictionary
    """
    for key, value in updates.items():
        if key in source and isinstance(source[key], dict) and isinstance(value, dict):
            deep_update(source[key], value)
        else:
            source[key] = value
    return source
