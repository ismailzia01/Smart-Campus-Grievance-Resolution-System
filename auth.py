"""
Authentication Blueprint for the Smart Campus Grievance System.
Handles registration, login, logout, session management, and authorization decorators.
"""

from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.before_app_request
def load_logged_in_user():
    """Load the current authenticated user into Flask's `g` context.

    Minimal session: only `user_id` is stored in the signed session cookie.
    Full user details (including role) are retrieved from the database
    on every request to ensure role revocation takes immediate effect.
    """
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            'SELECT id, full_name, email, role, created_at FROM users WHERE id = ?',
            (user_id,),
        ).fetchone()


def login_required(view):
    """Decorator to require login for a view."""
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.path))
        return view(**kwargs)
    return wrapped_view


def admin_required(view):
    """Decorator to require administrator privileges for a view."""
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.path))
        if g.user['role'] != 'admin':
            abort(403)
        return view(**kwargs)
    return wrapped_view


@bp.route('/register', methods=('GET', 'POST'))
def register():
    """Student registration endpoint."""
    if g.user is not None:
        return redirect(url_for('index'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        errors = []
        if not full_name:
            errors.append('Full name is required.')
        if not email or '@' not in email:
            errors.append('A valid email address is required.')
        if not password:
            errors.append('Password is required.')
        elif len(password) < 6:
            errors.append('Password must be at least 6 characters long.')
        if password != confirm_password:
            errors.append('Passwords do not match.')

        if not errors:
            db = get_db()
            existing = db.execute(
                'SELECT id FROM users WHERE email = ?',
                (email,),
            ).fetchone()

            if existing is not None:
                errors.append('An account with this email already exists.')
            else:
                db.execute(
                    'INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)',
                    (
                        full_name,
                        email,
                        generate_password_hash(password),
                        'student',
                    ),
                )
                db.commit()
                flash('Registration successful! You may now log in.', 'success')
                return redirect(url_for('auth.login'))

        for err in errors:
            flash(err, 'danger')

    return render_template('auth/register.html')


@bp.route('/login', methods=('GET', 'POST'))
def login():
    """User login endpoint for students and administrators."""
    if g.user is not None:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        db = get_db()
        user = db.execute(
            'SELECT id, full_name, email, password_hash, role FROM users WHERE email = ?',
            (email,),
        ).fetchone()

        if user is None or not check_password_hash(user['password_hash'], password):
            flash('Invalid email or password.', 'danger')
        else:
            # Prevent session fixation by clearing existing session before establishing a new one
            session.clear()
            # Store only minimal information in session
            session['user_id'] = user['id']

            flash(f"Welcome back, {user['full_name']}!", 'success')

            # Respect 'next' redirect if provided and safe
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)

            # Redirect based on user role
            if user['role'] == 'admin':
                if 'admin.dashboard' in current_app.view_functions:
                    return redirect(url_for('admin.dashboard'))
            else:
                if 'student.dashboard' in current_app.view_functions:
                    return redirect(url_for('student.dashboard'))

            return redirect(url_for('index'))

    return render_template('auth/login.html')


@bp.route('/logout', methods=('POST',))
def logout():
    """User logout endpoint. Requires POST request with CSRF protection."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))
