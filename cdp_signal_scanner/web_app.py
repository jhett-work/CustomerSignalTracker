"""
Web frontend for CDP Signal Scanner.

This module provides a simple web interface for running the CDP Signal Scanner,
allowing users to scan companies for CDP signals through a browser.
"""

import asyncio
import os
from typing import List, Optional
import csv
import tempfile
from pathlib import Path

import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, send_file

from cdp_signal_scanner.main import scan_companies

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_key_for_cdp_scanner")

# Create templates directory if it doesn't exist
os.makedirs(os.path.join(os.path.dirname(__file__), "templates"), exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    """
    Main page for CDP Signal Scanner web interface.
    Handles both GET (form display) and POST (form submission) requests.
    """
    if request.method == "POST":
        # Get companies from form
        companies_input = request.form.get("companies", "").strip()
        companies_file = request.files.get("companies_file")
        
        # Initialize an empty list for companies
        companies = []
        
        # Add companies from text input
        if companies_input:
            companies.extend([c.strip() for c in companies_input.split(",") if c.strip()])
        
        # Add companies from file upload
        if companies_file and companies_file.filename:
            # Create a temporary file to store the uploaded content
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
                companies_file.save(temp_file.name)
                
                # Read companies from the CSV file
                try:
                    with open(temp_file.name, 'r') as f:
                        reader = csv.reader(f)
                        for row in reader:
                            if row and row[0].strip():  # Skip empty rows
                                companies.append(row[0].strip())
                except Exception as e:
                    flash(f"Error reading companies file: {str(e)}", "error")
                    
                # Clean up the temporary file
                os.unlink(temp_file.name)
        
        # Check if we have companies to scan
        if not companies:
            flash("Please enter at least one company name or upload a CSV file", "error")
            return redirect(url_for("index"))
        
        # Save companies to session for the results page
        session_id = f"scan_{hash(''.join(companies))}"
        
        # Redirect to results page
        return redirect(url_for("results", companies=",".join(companies), session_id=session_id))
    
    # For GET request, just show the form
    return render_template("index.html")


@app.route("/results", methods=["GET"])
def results():
    """
    Display results page, showing either scan status or results.
    """
    # Get parameters from URL
    companies_str = request.args.get("companies", "")
    session_id = request.args.get("session_id", "")
    
    if not companies_str:
        flash("No companies specified", "error")
        return redirect(url_for("index"))
    
    # Parse companies list
    companies = [c.strip() for c in companies_str.split(",") if c.strip()]
    
    # Check if results already exist
    results_file = os.path.join(tempfile.gettempdir(), f"{session_id}_results.csv")
    
    if os.path.exists(results_file):
        # Load existing results
        try:
            df = pd.read_csv(results_file)
            return render_template("results.html", 
                                companies=companies,
                                results=df.to_dict('records'),
                                companies_str=companies_str,
                                session_id=session_id,
                                scan_complete=True)
        except Exception as e:
            flash(f"Error loading results: {str(e)}", "error")
            
    # No existing results, start the scan
    return render_template("results.html", 
                          companies=companies,
                          results=[],
                          companies_str=companies_str,
                          session_id=session_id,
                          scan_complete=False)


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """
    API endpoint to start a scan and return results.
    """
    data = request.get_json() or {}
    companies_str = data.get("companies", "")
    session_id = data.get("session_id", "")
    
    if not companies_str or not session_id:
        return {"error": "Missing companies or session ID"}, 400
    
    # Parse companies list
    companies = [c.strip() for c in companies_str.split(",") if c.strip()]
    
    if not companies:
        return {"error": "No valid companies to scan"}, 400
    
    # Create a temporary file for results
    results_file = os.path.join(tempfile.gettempdir(), f"{session_id}_results.csv")
    
    # Run the scan asynchronously
    def run_scan_task():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Run the scan
            results_df = loop.run_until_complete(scan_companies(companies))
            
            # Save results to file
            results_df.to_csv(results_file, index=False)
        except Exception as e:
            print(f"Error in scan task: {str(e)}")
        finally:
            loop.close()
    
    # Start the scan in a separate thread
    import threading
    scan_thread = threading.Thread(target=run_scan_task)
    scan_thread.daemon = True
    scan_thread.start()
    
    return {"status": "scan_started", "message": f"Scanning {len(companies)} companies..."}, 200


@app.route("/api/scan_status", methods=["GET"])
def api_scan_status():
    """
    API endpoint to check scan status.
    """
    session_id = request.args.get("session_id", "")
    
    if not session_id:
        return {"error": "Missing session ID"}, 400
    
    # Check if results file exists
    results_file = os.path.join(tempfile.gettempdir(), f"{session_id}_results.csv")
    
    if os.path.exists(results_file):
        # Load results
        try:
            df = pd.read_csv(results_file)
            return {
                "status": "complete",
                "results_count": len(df),
                "results": df.to_dict('records')
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}, 500
    
    return {"status": "running", "message": "Scan is still running..."}, 200


@app.route("/download", methods=["GET"])
def download_results():
    """
    Download results as CSV file.
    """
    session_id = request.args.get("session_id", "")
    
    if not session_id:
        flash("Missing session ID", "error")
        return redirect(url_for("index"))
    
    # Check if results file exists
    results_file = os.path.join(tempfile.gettempdir(), f"{session_id}_results.csv")
    
    if not os.path.exists(results_file):
        flash("Results not found", "error")
        return redirect(url_for("index"))
    
    # Serve the file for download
    return send_file(results_file, 
                    as_attachment=True, 
                    download_name="cdp_signals.csv", 
                    mimetype="text/csv")


def create_templates():
    """
    Create HTML templates for the web app if they don't exist.
    """
    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    os.makedirs(templates_dir, exist_ok=True)
    
    # Create index.html template
    index_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CDP Signal Scanner</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { padding-top: 2rem; padding-bottom: 2rem; }
            .form-container { max-width: 800px; margin: 0 auto; }
            .flash-message { margin-bottom: 1rem; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="form-container">
                <h1 class="text-center mb-4">CDP Signal Scanner</h1>
                <p class="lead text-center mb-4">Scan companies for signals indicating interest in Customer Data Platforms</p>
                
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category if category != 'error' else 'danger' }} flash-message">
                                {{ message }}
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                
                <div class="card">
                    <div class="card-body">
                        <form method="post" enctype="multipart/form-data">
                            <div class="mb-3">
                                <label for="companies" class="form-label">Companies to scan (comma-separated):</label>
                                <input type="text" class="form-control" id="companies" name="companies" 
                                    placeholder="Example: Adobe, Microsoft, Shopify">
                            </div>
                            
                            <div class="mb-3">
                                <label for="companies_file" class="form-label">Or upload a CSV file with company names:</label>
                                <input class="form-control" type="file" id="companies_file" name="companies_file" 
                                    accept=".csv">
                                <div class="form-text">CSV file should contain one company name per row.</div>
                            </div>
                            
                            <div class="d-grid gap-2">
                                <button type="submit" class="btn btn-primary">Start Scan</button>
                            </div>
                        </form>
                    </div>
                </div>
                
                <div class="mt-4">
                    <h4>What does this scanner look for?</h4>
                    <ul>
                        <li><strong>Hiring Signals:</strong> Job postings related to CDPs or customer data management</li>
                        <li><strong>Technology Signals:</strong> Mentions of CDP technologies or implementations</li>
                        <li><strong>Executive Moves:</strong> Leadership changes in data-related roles</li>
                        <li><strong>Business Documents:</strong> References in SEC filings, investor presentations, and news</li>
                        <li><strong>Growth/Funding:</strong> Company expansions that might signal CDP investment</li>
                    </ul>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    
    # Create results.html template
    results_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CDP Signal Scanner - Results</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { padding-top: 2rem; padding-bottom: 2rem; }
            .results-container { max-width: 1000px; margin: 0 auto; }
            .flash-message { margin-bottom: 1rem; }
            .signal-card { margin-bottom: 1rem; }
            .score-badge { font-size: 1.2rem; }
            .loading-spinner { display: flex; justify-content: center; margin: 3rem 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="results-container">
                <h1 class="text-center mb-4">CDP Signal Scanner Results</h1>
                
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category if category != 'error' else 'danger' }} flash-message">
                                {{ message }}
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                
                <div class="card mb-4">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="mb-0">Scanning {{ companies|length }} companies</h5>
                        <a href="{{ url_for('index') }}" class="btn btn-outline-primary btn-sm">New Scan</a>
                    </div>
                    <div class="card-body">
                        <div class="mb-3">
                            <strong>Companies:</strong> {{ companies|join(", ") }}
                        </div>
                        
                        {% if not scan_complete %}
                            <div id="scan-status" class="alert alert-info">
                                Scan in progress... This may take a few minutes depending on the number of companies.
                            </div>
                            <div id="loading-spinner" class="loading-spinner">
                                <div class="spinner-border text-primary" role="status">
                                    <span class="visually-hidden">Loading...</span>
                                </div>
                            </div>
                        {% else %}
                            <div id="scan-status" class="alert alert-success">
                                Scan complete!
                            </div>
                        {% endif %}
                        
                        <div id="scan-actions" class="text-center" {% if not scan_complete %}style="display: none;"{% endif %}>
                            <a href="{{ url_for('download_results', session_id=session_id) }}" class="btn btn-success">
                                Download CSV
                            </a>
                        </div>
                    </div>
                </div>
                
                <div id="results-container">
                    {% if results %}
                        <h3>Found {{ results|length }} signals:</h3>
                        
                        {% for result in results %}
                            <div class="card signal-card">
                                <div class="card-header d-flex justify-content-between">
                                    <span>{{ result.account }}</span>
                                    <span class="badge bg-primary score-badge">Score: {{ result.score }}</span>
                                </div>
                                <div class="card-body">
                                    <h5 class="card-title">{{ result.signal_category }}</h5>
                                    <p class="card-text">{{ result.snippet }}</p>
                                    <a href="{{ result.source_url }}" target="_blank" class="btn btn-sm btn-outline-secondary">
                                        View Source
                                    </a>
                                </div>
                                <div class="card-footer text-muted">
                                    Source: {{ result.source }}
                                </div>
                            </div>
                        {% endfor %}
                    {% else %}
                        <div id="no-results" class="alert alert-warning" {% if not scan_complete %}style="display: none;"{% endif %}>
                            No signals found for the specified companies.
                        </div>
                    {% endif %}
                </div>
            </div>
        </div>
        
        <script>
            {% if not scan_complete %}
            // Start the scan
            fetch('/api/scan', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    companies: '{{ companies_str }}',
                    session_id: '{{ session_id }}'
                })
            })
            .then(response => response.json())
            .then(data => {
                console.log('Scan started:', data);
                
                // Poll for results
                const checkStatus = () => {
                    fetch(`/api/scan_status?session_id={{ session_id }}`)
                        .then(response => response.json())
                        .then(statusData => {
                            console.log('Status update:', statusData);
                            
                            if (statusData.status === 'complete') {
                                // Update the UI with results
                                document.getElementById('scan-status').className = 'alert alert-success';
                                document.getElementById('scan-status').textContent = 'Scan complete!';
                                document.getElementById('loading-spinner').style.display = 'none';
                                document.getElementById('scan-actions').style.display = 'block';
                                
                                // Display results
                                const resultsContainer = document.getElementById('results-container');
                                
                                if (statusData.results_count > 0) {
                                    // Build results HTML
                                    let resultsHtml = `<h3>Found ${statusData.results_count} signals:</h3>`;
                                    
                                    statusData.results.forEach(result => {
                                        resultsHtml += `
                                            <div class="card signal-card">
                                                <div class="card-header d-flex justify-content-between">
                                                    <span>${result.account}</span>
                                                    <span class="badge bg-primary score-badge">Score: ${result.score}</span>
                                                </div>
                                                <div class="card-body">
                                                    <h5 class="card-title">${result.signal_category}</h5>
                                                    <p class="card-text">${result.snippet}</p>
                                                    <a href="${result.source_url}" target="_blank" class="btn btn-sm btn-outline-secondary">
                                                        View Source
                                                    </a>
                                                </div>
                                                <div class="card-footer text-muted">
                                                    Source: ${result.source || 'N/A'}
                                                </div>
                                            </div>
                                        `;
                                    });
                                    
                                    resultsContainer.innerHTML = resultsHtml;
                                    
                                    if (document.getElementById('no-results')) {
                                        document.getElementById('no-results').style.display = 'none';
                                    }
                                } else {
                                    // No results
                                    if (document.getElementById('no-results')) {
                                        document.getElementById('no-results').style.display = 'block';
                                    } else {
                                        resultsContainer.innerHTML = `
                                            <div id="no-results" class="alert alert-warning">
                                                No signals found for the specified companies.
                                            </div>
                                        `;
                                    }
                                }
                                
                                // Stop polling
                                clearInterval(statusInterval);
                            }
                            else if (statusData.status === 'error') {
                                // Show error
                                document.getElementById('scan-status').className = 'alert alert-danger';
                                document.getElementById('scan-status').textContent = 'Error: ' + statusData.message;
                                document.getElementById('loading-spinner').style.display = 'none';
                                
                                // Stop polling
                                clearInterval(statusInterval);
                            }
                        })
                        .catch(error => {
                            console.error('Error checking status:', error);
                        });
                };
                
                // Check status every 5 seconds
                const statusInterval = setInterval(checkStatus, 5000);
                
                // Also check immediately
                checkStatus();
            })
            .catch(error => {
                console.error('Error starting scan:', error);
                document.getElementById('scan-status').className = 'alert alert-danger';
                document.getElementById('scan-status').textContent = 'Error starting scan. Please try again.';
                document.getElementById('loading-spinner').style.display = 'none';
            });
            {% endif %}
        </script>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    
    # Write templates to files
    with open(os.path.join(templates_dir, "index.html"), "w") as f:
        f.write(index_template.strip())
    
    with open(os.path.join(templates_dir, "results.html"), "w") as f:
        f.write(results_template.strip())


def run_web_app(host="0.0.0.0", port=5000, debug=False):
    """
    Run the Flask web application.
    
    Args:
        host: Host to bind to
        port: Port to listen on
        debug: Whether to run in debug mode
    """
    # Create templates if they don't exist
    create_templates()
    
    # Start the app
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_web_app(debug=True)