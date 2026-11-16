"""
Seed the database with campus departments and provision an administrator account.

Usage:
    flask seed-db
"""

import os
import sys

import click
from werkzeug.security import generate_password_hash

from .auth import is_valid_email
from .db import get_db

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
    - Validates email format strictly.
    - Enforces password length between 8 and 128 characters.
    - Never promotes an existing student account to administrator.
    - Never overwrites an existing administrator password.
    - Creates a new admin account only if the email is unregistered.
    """
    if not email or not isinstance(email, str) or not is_valid_email(email.strip()):
        return False, "Invalid email address format. A valid campus email is required."

    email = email.strip().lower()

    if not password or not isinstance(password, str):
        return False, "Administrator password is required."

    if len(password) < 8:
        return False, "Administrator password must be at least 8 characters long."

    if len(password) > 128:
        return False, "Administrator password cannot exceed 128 characters."

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
            while True:
                admin_email = click.prompt('Enter Administrator Email', type=str)
                if is_valid_email(admin_email.strip()):
                    admin_email = admin_email.strip().lower()
                    break
                click.echo('Invalid email format. Please enter a valid campus email address.', err=True)
        else:
            click.echo('No ADMIN_EMAIL provided in environment or arguments. Skipping admin provisioning.')
            return
    elif not is_valid_email(admin_email.strip()):
        click.echo(f"Error: Invalid administrator email '{admin_email}'.", err=True)
        return

    if not admin_password:
        if sys.stdin.isatty():
            while True:
                admin_password = click.prompt(
                    'Enter Administrator Password',
                    hide_input=True,
                    confirmation_prompt=True,
                )
                if len(admin_password) < 8:
                    click.echo('Password must be at least 8 characters long.', err=True)
                elif len(admin_password) > 128:
                    click.echo('Password cannot exceed 128 characters.', err=True)
                else:
                    break
        else:
            click.echo('No ADMIN_PASSWORD provided in environment. Skipping admin provisioning.')
            return
    elif len(admin_password) < 8 or len(admin_password) > 128:
        click.echo('Error: Administrator password must be between 8 and 128 characters long.', err=True)
        return

    created, message = provision_admin(admin_email, admin_password)
    click.echo(message)


def init_app(app):
    """Register the seed command with the Flask application."""
    app.cli.add_command(seed_db_command)
