"""
Seed the database with campus departments and provision an administrator account.

Usage:
    flask seed-db
"""

import os
import sys

import click
from werkzeug.security import generate_password_hash

from db import get_db

# Valid grievance categories supported by the system
VALID_CATEGORIES = [
    'Internet / Wi-Fi',
    'Classroom Equipment',
    'Hostel Facilities',
    'Library Facilities',
    'Other',
]

# Category-to-department mapping used throughout the application
CATEGORY_DEPARTMENT_MAP = {
    'Internet / Wi-Fi': 'IT',
    'Classroom Equipment': 'Maintenance',
    'Hostel Facilities': 'Hostel Administration',
    'Library Facilities': 'Library Department',
    'Other': None,
}

# Department definitions
DEPARTMENTS = [
    ('IT', 'Handles internet, Wi-Fi, and technology-related issues'),
    ('Maintenance', 'Handles classroom equipment, furniture, and building maintenance'),
    ('Hostel Administration', 'Handles hostel facilities, rooms, and accommodation issues'),
    ('Library Department', 'Handles library facilities, books, and reading room issues'),
]


def seed_departments():
    """Insert default departments if they do not already exist."""
    db = get_db()
    for name, description in DEPARTMENTS:
        db.execute(
            'INSERT OR IGNORE INTO departments (name, description) VALUES (?, ?)',
            (name, description),
        )
    db.commit()


def provision_admin(email, password, full_name='Campus Administrator'):
    """Provision an admin user.

    Security & Safety Guarantees:
    - Never promotes an existing student account to administrator.
    - Never overwrites an existing administrator password.
    - Creates a new admin account only if the email is unregistered.
    """
    db = get_db()
    existing = db.execute(
        'SELECT id, email, role FROM users WHERE email = ?',
        (email,),
    ).fetchone()

    if existing is not None:
        if existing['role'] == 'student':
            return False, f"Account with email ({email}) is an existing student account. Promoting student accounts to administrator is prohibited."
        return False, f"Admin account ({email}) already exists. Preserving existing account without modification."

    db.execute(
        'INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)',
        (
            full_name,
            email,
            generate_password_hash(password),
            'admin',
        ),
    )
    db.commit()
    return True, f"Admin account ({email}) provisioned successfully."


@click.command('seed-db')
@click.option('--email', default=None, help='Admin email address')
def seed_db_command(email):
    """Seed departments and provision the administrator account.

    Passwords are never accepted as command-line arguments to prevent
    credential exposure in process lists and shell history.
    """
    seed_departments()
    click.echo('Departments seeded.')

    # Determine admin credentials: CLI email option or Environment -> Interactive prompt
    admin_email = email or os.environ.get('ADMIN_EMAIL')
    admin_password = os.environ.get('ADMIN_PASSWORD')

    # If credentials are not present and running in an interactive terminal, prompt for them
    if not admin_email:
        if sys.stdin.isatty():
            admin_email = click.prompt('Enter Administrator Email', type=str)
        else:
            click.echo('No ADMIN_EMAIL provided in environment or arguments. Skipping admin provisioning.')
            return

    if not admin_password:
        if sys.stdin.isatty():
            admin_password = click.prompt(
                'Enter Administrator Password',
                hide_input=True,
                confirmation_prompt=True,
            )
        else:
            click.echo('No ADMIN_PASSWORD provided in environment. Skipping admin provisioning.')
            return

    created, message = provision_admin(admin_email, admin_password)
    click.echo(message)


def init_app(app):
    """Register the seed command with the Flask application."""
    app.cli.add_command(seed_db_command)
