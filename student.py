"""
Student Blueprint for the Smart Campus Grievance System.
Allows authenticated students to submit grievances, view their own tickets,
and track resolution status with full audit history.
"""

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from auth import login_required
from db import get_db
from seed import CATEGORY_DEPARTMENT_MAP, VALID_CATEGORIES

bp = Blueprint('student', __name__, url_prefix='/student')


@bp.route('/dashboard')
@login_required
def dashboard():
    """Display all grievances submitted by the currently logged-in student."""
    db = get_db()
    # Query only this student's grievances, joined with departments for readable names
    grievances = db.execute(
        '''
        SELECT g.id, g.ticket_id, g.category, g.subject, g.location,
               g.priority, g.status, g.created_at, g.updated_at,
               d.name AS department_name
        FROM grievances g
        LEFT JOIN departments d ON g.department_id = d.id
        WHERE g.student_id = ?
        ORDER BY g.created_at DESC
        ''',
        (g.user['id'],),
    ).fetchall()

    return render_template('student/dashboard.html', grievances=grievances)


@bp.route('/grievances/new', methods=('GET', 'POST'))
@bp.route('/grievances', methods=('POST',))
@login_required
def new_grievance():
    """Submit a new campus grievance."""
    db = get_db()

    if request.method == 'POST':
        category = request.form.get('category', '').strip()
        subject = request.form.get('subject', '').strip()
        location = request.form.get('location', '').strip()
        description = request.form.get('description', '').strip()

        errors = []

        # Backend category validation
        if not category or category not in VALID_CATEGORIES:
            errors.append('Please select a valid grievance category.')

        if not subject:
            errors.append('Subject summary is required.')
        elif len(subject) < 5:
            errors.append('Subject must be at least 5 characters long.')

        if not location:
            errors.append('Campus location is required.')

        if not description:
            errors.append('Detailed description is required.')
        elif len(description) < 10:
            errors.append('Description must be at least 10 characters long.')

        if not errors:
            # Resolve department via category mapping
            dept_name = CATEGORY_DEPARTMENT_MAP.get(category)
            department_id = None
            if dept_name:
                dept_row = db.execute(
                    'SELECT id FROM departments WHERE name = ?',
                    (dept_name,),
                ).fetchone()
                if dept_row:
                    department_id = dept_row['id']

            try:
                # Atomic transaction: insert grievance, generate ticket_id, insert initial audit log
                cursor = db.cursor()

                # Insert with temporary ticket_id to obtain autoincrement ID
                cursor.execute(
                    '''
                    INSERT INTO grievances (
                        ticket_id, student_id, category, department_id,
                        subject, description, location, priority, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'medium', 'open')
                    ''',
                    (
                        'TEMP',
                        g.user['id'],
                        category,
                        department_id,
                        subject,
                        description,
                        location,
                    ),
                )
                grievance_id = cursor.lastrowid
                ticket_id = f'GR-{grievance_id:04d}'

                # Update with formatted ticket_id
                cursor.execute(
                    'UPDATE grievances SET ticket_id = ? WHERE id = ?',
                    (ticket_id, grievance_id),
                )

                # Record initial audit log entry
                cursor.execute(
                    '''
                    INSERT INTO grievance_logs (
                        grievance_id, changed_by, action, old_value, new_value, remarks
                    ) VALUES (?, ?, 'created', NULL, 'open', 'Grievance submitted by student')
                    ''',
                    (grievance_id, g.user['id']),
                )

                # Commit both changes together
                db.commit()

                flash(f'Grievance ticket {ticket_id} submitted successfully.', 'success')
                return redirect(url_for('student.view_grievance', id=grievance_id))

            except Exception:
                db.rollback()
                flash('An unexpected error occurred while submitting your grievance. Please try again.', 'danger')

        for err in errors:
            flash(err, 'danger')

    return render_template('student/new_grievance.html', categories=VALID_CATEGORIES)


@bp.route('/grievances/<int:id>')
@login_required
def view_grievance(id):
    """View details and timeline of a submitted grievance.

    Access Control: Students are strictly restricted to their own grievances.
    """
    db = get_db()
    grievance = db.execute(
        '''
        SELECT g.*, d.name AS department_name
        FROM grievances g
        LEFT JOIN departments d ON g.department_id = d.id
        WHERE g.id = ?
        ''',
        (id,),
    ).fetchone()

    if grievance is None:
        abort(404)

    # Enforce student ownership: return 403 Forbidden if not the grievance owner
    if grievance['student_id'] != g.user['id'] and g.user['role'] != 'admin':
        abort(403)

    # Fetch audit history logs for this grievance
    logs = db.execute(
        '''
        SELECT l.*, u.full_name AS actor_name, u.role AS actor_role
        FROM grievance_logs l
        JOIN users u ON l.changed_by = u.id
        WHERE l.grievance_id = ?
        ORDER BY l.created_at ASC
        ''',
        (id,),
    ).fetchall()

    return render_template('student/view_grievance.html', grievance=grievance, logs=logs)
