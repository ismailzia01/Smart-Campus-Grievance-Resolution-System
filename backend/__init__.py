"""
Backend package for Smart Campus Grievance & Resolution System.
Provides the Flask application factory and initializes core modules.
"""

import os
import secrets

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect

# Load environment variables from .env file if present
load_dotenv()

csrf = CSRFProtect()


def resolve_secret_key(app, test_config=None):
    """Resolve SECRET_KEY with strict production enforcement and safe development fallback.

    - In testing: uses provided test secret.
    - In production: strictly requires SECRET_KEY in environment, refusing to start otherwise.
    - In development: uses SECRET_KEY from environment/.env; if absent, generates a secure
      ephemeral key and issues a warning without exposing the key value.
    """
    if test_config and 'SECRET_KEY' in test_config:
        return test_config['SECRET_KEY']

    env_secret = os.environ.get('SECRET_KEY', '').strip()
    is_production = (
        os.environ.get('FLASK_ENV') == 'production'
        or os.environ.get('ENVIRONMENT', '').lower() == 'production'
    )

    if env_secret:
        return env_secret

    if is_production:
        raise RuntimeError(
            'SECRET_KEY environment variable is required in production mode. '
            'Configure a secure, random SECRET_KEY in your environment.'
        )

    # Safe development configuration: generate an ephemeral cryptographic key
    # Never log or print the generated secret itself
    app.logger.warning(
        'No SECRET_KEY configured in environment. Using a generated ephemeral secret key for local development.'
    )
    return secrets.token_hex(32)


def create_app(test_config=None):
    """Application factory for the Smart Campus Grievance System."""
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    template_dir = os.path.join(project_root, 'frontend', 'templates')
    static_dir = os.path.join(project_root, 'frontend', 'static')
    instance_dir = os.path.join(project_root, 'instance')
    schema_file = os.path.join(project_root, 'databases', 'schema.sql')

    app = Flask(
        __name__,
        instance_path=instance_dir,
        template_folder=template_dir,
        static_folder=static_dir,
        instance_relative_config=True,
    )

    secret_key = resolve_secret_key(app, test_config)

    # Configuration defaults
    app.config.from_mapping(
        SECRET_KEY=secret_key,
        DATABASE=os.path.join(app.instance_path, 'database.db'),
        SCHEMA_PATH=schema_file,
        # Session cookie security settings
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() in ('true', '1', 'yes'),
    )

    if test_config:
        app.config.from_mapping(test_config)

    # Ensure the instance directory exists
    os.makedirs(app.instance_path, exist_ok=True)

    # Initialize CSRF protection globally
    csrf.init_app(app)

    # Register database helpers
    from . import db
    db.init_app(app)

    # Register seed commands
    from . import seed
    seed.init_app(app)

    # Register Blueprints
    from . import auth
    app.register_blueprint(auth.bp)

    from . import student
    app.register_blueprint(student.bp)

    from . import admin
    app.register_blueprint(admin.bp)

    # Register template filters and globals for timezone conversion
    from .time_utils import to_ist
    app.add_template_filter(to_ist, 'to_ist')
    app.add_template_filter(to_ist, 'format_ist')
    app.add_template_global(to_ist, 'to_ist')
    app.add_template_global(to_ist, 'format_ist')

    @app.context_processor
    def inject_helpers():
        return {
            'has_endpoint': lambda endpoint: endpoint in app.view_functions,
            'to_ist': to_ist,
            'format_ist': to_ist,
        }

    # --- Landing Page Route ---
    @app.route('/')
    def index():
        """Render the landing page."""
        return render_template('index.html')

    # --- Error Handlers ---
    @app.errorhandler(400)
    def bad_request_error(error):
        return render_template('errors/400.html'), 400

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        return render_template('errors/500.html'), 500

    return app
