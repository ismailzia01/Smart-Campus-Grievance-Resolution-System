"""
Smart Campus Grievance & Resolution System
A full-stack web application for managing campus grievances.
Built with Flask, SQLite, and vanilla JavaScript.
"""

from flask import Flask, render_template

app = Flask(__name__)


@app.route('/')
def index():
    """Render the landing page."""
    return render_template('index.html')
