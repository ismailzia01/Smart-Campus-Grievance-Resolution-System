"""
Database connection management for the Smart Campus Grievance System.
Uses Python's built-in sqlite3 module with Flask's application context.
"""

import sqlite3

import click
from flask import current_app, g


def get_db():
    """Get a database connection for the current request.

    Stores the connection on Flask's `g` object so the same connection
    is reused throughout a single request. Returns rows as sqlite3.Row
    objects for dict-like column access.
    """
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(e=None):
    """Close the database connection at the end of a request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Initialize the database by executing schema.sql.

    WARNING: This drops and recreates all tables.
    """
    db = get_db()
    with current_app.open_resource('schema.sql') as f:
        db.executescript(f.read().decode('utf-8'))


@click.command('init-db')
def init_db_command():
    """Clear existing data and create fresh tables."""
    init_db()
    click.echo('Database initialized.')


def init_app(app):
    """Register database functions with the Flask application.

    Called from the app factory to set up teardown and CLI commands.
    """
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)

