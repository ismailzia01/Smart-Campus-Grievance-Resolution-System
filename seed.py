"""
Seed the database with departments and a default admin account.

Usage:
    flask seed-db
"""

import click
from flask import current_app
from werkzeug.security import generate_password_hash

from db import get_db

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

# Default admin credentials
DEFAULT_ADMIN = {
    'full_name': 'Campus Admin',
    'email': 'admin@smartcampus.edu',
    'password': 'admin123',
}


def seed_db():
    """Insert departments and default admin into the database."""
    db = get_db()

    # Insert departments
    for name, description in DEPARTMENTS:
        db.execute(
            'INSERT OR IGNORE INTO departments (name, description) VALUES (?, ?)',
            (name, description),
        )

    # Insert default admin account
    existing = db.execute(
        'SELECT id FROM users WHERE email = ?',
        (DEFAULT_ADMIN['email'],),
    ).fetchone()

    if existing is None:
        db.execute(
            'INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)',
            (
                DEFAULT_ADMIN['full_name'],
                DEFAULT_ADMIN['email'],
                generate_password_hash(DEFAULT_ADMIN['password']),
                'admin',
            ),
        )

    db.commit()


@click.command('seed-db')
def seed_db_command():
    """Seed the database with departments and default admin."""
    seed_db()
    click.echo('Database seeded.')
    click.echo(f"  Admin email:    {DEFAULT_ADMIN['email']}")
    click.echo(f"  Admin password: {DEFAULT_ADMIN['password']}")


def init_app(app):
    """Register the seed command with the Flask application."""
    app.cli.add_command(seed_db_command)
