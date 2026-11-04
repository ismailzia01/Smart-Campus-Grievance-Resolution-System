"""
Smart Campus Grievance & Resolution System
A full-stack web application for managing campus grievances.
Built with Flask, SQLite, and vanilla JavaScript.
"""

import os

from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()


def create_app(test_config=None):
    """Application factory for the Smart Campus Grievance System."""
    app = Flask(__name__, instance_relative_config=True)

    # Configuration defaults
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-insecure-key-change-in-prod'),
        DATABASE=os.path.join(app.instance_path, 'database.db'),
        # Session cookie security settings
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true',
    )

    if test_config:
        app.config.from_mapping(test_config)

    # Ensure the instance directory exists
    os.makedirs(app.instance_path, exist_ok=True)

    # Initialize CSRF protection globally
    csrf.init_app(app)

    # Register database helpers
    import db
    db.init_app(app)

    # Register seed commands
    import seed
    seed.init_app(app)

    # Register Blueprints
    import auth
    app.register_blueprint(auth.bp)

    import student
    app.register_blueprint(student.bp)

    @app.context_processor
    def inject_helpers():
        return {
            'has_endpoint': lambda endpoint: endpoint in app.view_functions
        }

    # --- Landing Page Route ---
    @app.route('/')
    def index():
        """Render the landing page."""
        return render_template('index.html')

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
