#!/usr/bin/env python3
"""
Entry point for running the CDP Signal Scanner web application.
"""

import os
from cdp_signal_scanner.web_app import run_web_app

if __name__ == "__main__":
    # Get port from environment variable, default to 5000
    port = int(os.environ.get("PORT", 5000))
    
    # Run the web app
    run_web_app(host="0.0.0.0", port=port, debug=False)