"""
Smart Campus Grievance & Resolution System
A full-stack web application for managing campus grievances.
Built with Flask, SQLite, and vanilla JavaScript.
"""

import os

from flask import Flask, render_template


def create_app():
    """Application factory for the Smart Campus Grievance System."""
    app = Flask(__name__)

    # Configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev'),
        DATABASE=os.path.join(app.instance_path, 'database.db'),
    )

    # Ensure the instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)

    # Register database helpers
    import db
    db.init_app(app)

    # Register seed command
    import seed
    seed.init_app(app)

    # --- Routes ---

    @app.route('/')
    def index():
        """Render the landing page."""
        return render_template('index.html')

    return app
