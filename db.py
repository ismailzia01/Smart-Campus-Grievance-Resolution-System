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


def database_has_tables(db):
    """Check if the database already contains application tables."""
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('users', 'departments', 'grievances', 'grievance_logs')"
    )
    return cursor.fetchone() is not None


def init_db(force=False):
    """Initialize the database by executing schema.sql.

    Refuses to overwrite an existing database containing tables unless force=True.
    """
    db = get_db()
    if database_has_tables(db) and not force:
        raise RuntimeError(
            'Database already contains existing tables. Initialization aborted to prevent data loss. '
            'Use "flask reset-db" to perform a destructive reset.'
        )
    with current_app.open_resource('schema.sql') as f:
        db.executescript(f.read().decode('utf-8'))


def reset_db():
    """Destructively drop all existing tables and re-initialize the database."""
    db = get_db()
    db.execute('PRAGMA foreign_keys = OFF')
    drop_statements = '''
        DROP TABLE IF EXISTS grievance_logs;
        DROP TABLE IF EXISTS grievances;
        DROP TABLE IF EXISTS departments;
        DROP TABLE IF EXISTS users;
    '''
    db.executescript(drop_statements)
    db.execute('PRAGMA foreign_keys = ON')
    init_db(force=True)


@click.command('init-db')
def init_db_command():
    """Initialize database tables without overwriting existing data."""
    try:
        init_db()
        click.echo('Database initialized successfully.')
    except RuntimeError as e:
        click.echo(f'Initialization cancelled: {e}', err=True)


@click.command('reset-db')
@click.confirmation_option(
    prompt='WARNING: This will permanently delete all existing tables and data. Are you sure you want to proceed?'
)
def reset_db_command():
    """Destructively reset and recreate all database tables."""
    reset_db()
    click.echo('Database reset successfully. All previous tables have been cleared and recreated.')


def init_app(app):
    """Register database functions with the Flask application.

    Called from the app factory to set up teardown and CLI commands.
    """
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(reset_db_command)

