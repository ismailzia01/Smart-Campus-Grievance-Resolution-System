"""
Administrator Blueprint for the Smart Campus Grievance System.
Provides administrative dashboard, search/filter controls, JSON API endpoint for
asynchronous filtering, department reassignment, priority adjustment,
status transitions, and transactional audit logging.
"""

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from auth import admin_required
from db import get_db

bp = Blueprint('admin', __name__, url_prefix='/admin')

ALLOWED_STATUSES = ['open', 'in_progress', 'resolved']
ALLOWED_PRIORITIES = ['low', 'medium', 'high']


def build_grievance_query(status=None, priority=None, department_id=None, search=None):
    """Construct filtered grievance query and parameters."""
    query = '''
        SELECT g.id, g.ticket_id, g.category, g.subject, g.location,
               g.priority, g.status, g.created_at, g.updated_at,
               d.id AS department_id, d.name AS department_name,
               u.id AS student_id, u.full_name AS student_name, u.email AS student_email
        FROM grievances g
        LEFT JOIN departments d ON g.department_id = d.id
        JOIN users u ON g.student_id = u.id
        WHERE 1=1
    '''
    params = []

    if status and status in ALLOWED_STATUSES:
        query += ' AND g.status = ?'
        params.append(status)

    if priority and priority in ALLOWED_PRIORITIES:
        query += ' AND g.priority = ?'
        params.append(priority)

    if department_id:
        try:
            dept_id_int = int(department_id)
            query += ' AND g.department_id = ?'
            params.append(dept_id_int)
        except ValueError:
            pass

    if search:
        search_pattern = f'%{search.strip()}%'
        query += '''
            AND (
                g.ticket_id LIKE ? OR
                g.subject LIKE ? OR
                g.description LIKE ? OR
                g.location LIKE ? OR
                u.full_name LIKE ? OR
                u.email LIKE ?
            )
        '''
        params.extend([search_pattern] * 6)

    query += ' ORDER BY g.created_at DESC'
    return query, params


@bp.route('/dashboard')
@admin_required
def dashboard():
    """Administrative dashboard displaying all campus grievances with filter controls."""
    db = get_db()

    # Extract filter parameters
    status = request.args.get('status', '').strip()
    priority = request.args.get('priority', '').strip()
    department_id = request.args.get('department', '').strip()
    search = request.args.get('search', '').strip()

    query, params = build_grievance_query(status, priority, department_id, search)
    grievances = db.execute(query, params).fetchall()

    departments = db.execute('SELECT id, name FROM departments ORDER BY name ASC').fetchall()

    # Calculate summary statistics for admin overview cards
    stats = {
        'total': db.execute('SELECT COUNT(*) FROM grievances').fetchone()[0],
        'open': db.execute("SELECT COUNT(*) FROM grievances WHERE status = 'open'").fetchone()[0],
        'in_progress': db.execute("SELECT COUNT(*) FROM grievances WHERE status = 'in_progress'").fetchone()[0],
        'resolved': db.execute("SELECT COUNT(*) FROM grievances WHERE status = 'resolved'").fetchone()[0],
    }

    return render_template(
        'admin/dashboard.html',
        grievances=grievances,
        departments=departments,
        stats=stats,
        current_status=status,
        current_priority=priority,
        current_department=department_id,
        current_search=search,
    )


@bp.route('/api/grievances')
@admin_required
def api_grievances():
    """JSON API endpoint for asynchronous admin filtering.

    Provides filtered grievance data for dynamic UI updates without full page reload.
    """
    db = get_db()
    status = request.args.get('status', '').strip()
    priority = request.args.get('priority', '').strip()
    department_id = request.args.get('department', '').strip()
    search = request.args.get('search', '').strip()

    query, params = build_grievance_query(status, priority, department_id, search)
    rows = db.execute(query, params).fetchall()

    results = []
    for r in rows:
        results.append({
            'id': r['id'],
            'ticket_id': r['ticket_id'],
            'category': r['category'],
            'subject': r['subject'],
            'location': r['location'],
            'priority': r['priority'],
            'status': r['status'],
            'created_at': r['created_at'][:16],
            'department_name': r['department_name'] or 'Pending Assignment',
            'student_name': r['student_name'],
            'student_email': r['student_email'],
            'url': url_for('admin.view_grievance', id=r['id']),
        })

    return jsonify({'count': len(results), 'grievances': results})


@bp.route('/grievances/<int:id>')
@admin_required
def view_grievance(id):
    """Detailed administrative view and management panel for a grievance."""
    db = get_db()
    grievance = db.execute(
        '''
        SELECT g.*, d.name AS department_name,
               u.full_name AS student_name, u.email AS student_email
        FROM grievances g
        LEFT JOIN departments d ON g.department_id = d.id
        JOIN users u ON g.student_id = u.id
        WHERE g.id = ?
        ''',
        (id,),
    ).fetchone()

    if grievance is None:
        abort(404)

    departments = db.execute('SELECT id, name FROM departments ORDER BY name ASC').fetchall()

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

    return render_template(
        'admin/view_grievance.html',
        grievance=grievance,
        departments=departments,
        logs=logs,
    )


@bp.route('/grievances/<int:id>/status', methods=('POST',))
@admin_required
def update_status(id):
    """Update grievance lifecycle status with transactional audit log."""
    db = get_db()
    grievance = db.execute('SELECT * FROM grievances WHERE id = ?', (id,)).fetchone()
    if grievance is None:
        abort(404)

    new_status = request.form.get('status', '').strip()
    remarks = request.form.get('remarks', '').strip()
    resolution_details = request.form.get('resolution_details', '').strip()

    if new_status not in ALLOWED_STATUSES:
        flash('Invalid status specified.', 'danger')
        return redirect(url_for('admin.view_grievance', id=id))

    old_status = grievance['status']

    # Workflow validation: no backward transition from resolved
    if old_status == 'resolved' and new_status != 'resolved':
        flash('A resolved grievance cannot be reopened.', 'danger')
        return redirect(url_for('admin.view_grievance', id=id))

    if old_status == new_status:
        flash(f'Grievance is already marked as {new_status}.', 'warning')
        return redirect(url_for('admin.view_grievance', id=id))

    if new_status == 'resolved' and not resolution_details:
        flash('Resolution details are required when marking a ticket as resolved.', 'danger')
        return redirect(url_for('admin.view_grievance', id=id))

    try:
        cursor = db.cursor()
        if new_status == 'resolved':
            cursor.execute(
                '''
                UPDATE grievances
                SET status = ?, resolution_details = ?, updated_at = datetime('now')
                WHERE id = ?
                ''',
                (new_status, resolution_details, id),
            )
        else:
            cursor.execute(
                '''
                UPDATE grievances
                SET status = ?, updated_at = datetime('now')
                WHERE id = ?
                ''',
                (new_status, id),
            )

        cursor.execute(
            '''
            INSERT INTO grievance_logs (
                grievance_id, changed_by, action, old_value, new_value, remarks
            ) VALUES (?, ?, 'status_change', ?, ?, ?)
            ''',
            (id, g.user['id'], old_status, new_status, remarks or None),
        )

        db.commit()
        flash(f'Status updated from {old_status} to {new_status}.', 'success')
    except Exception:
        db.rollback()
        flash('Failed to update status due to a database error.', 'danger')

    return redirect(url_for('admin.view_grievance', id=id))


@bp.route('/grievances/<int:id>/priority', methods=('POST',))
@admin_required
def update_priority(id):
    """Update grievance priority level with transactional audit log."""
    db = get_db()
    grievance = db.execute('SELECT * FROM grievances WHERE id = ?', (id,)).fetchone()
    if grievance is None:
        abort(404)

    new_priority = request.form.get('priority', '').strip()
    remarks = request.form.get('remarks', '').strip()

    if new_priority not in ALLOWED_PRIORITIES:
        flash('Invalid priority level specified.', 'danger')
        return redirect(url_for('admin.view_grievance', id=id))

    old_priority = grievance['priority']
    if old_priority == new_priority:
        flash(f'Priority is already set to {new_priority}.', 'warning')
        return redirect(url_for('admin.view_grievance', id=id))

    try:
        cursor = db.cursor()
        cursor.execute(
            '''
            UPDATE grievances
            SET priority = ?, updated_at = datetime('now')
            WHERE id = ?
            ''',
            (new_priority, id),
        )

        cursor.execute(
            '''
            INSERT INTO grievance_logs (
                grievance_id, changed_by, action, old_value, new_value, remarks
            ) VALUES (?, ?, 'priority_change', ?, ?, ?)
            ''',
            (id, g.user['id'], old_priority, new_priority, remarks or None),
        )

        db.commit()
        flash(f'Priority updated from {old_priority} to {new_priority}.', 'success')
    except Exception:
        db.rollback()
        flash('Failed to update priority due to a database error.', 'danger')

    return redirect(url_for('admin.view_grievance', id=id))


@bp.route('/grievances/<int:id>/department', methods=('POST',))
@admin_required
def update_department(id):
    """Reassign grievance to a different campus department with transactional audit log."""
    db = get_db()
    grievance = db.execute(
        '''
        SELECT g.*, d.name AS current_department_name
        FROM grievances g
        LEFT JOIN departments d ON g.department_id = d.id
        WHERE g.id = ?
        ''',
        (id,),
    ).fetchone()

    if grievance is None:
        abort(404)

    new_dept_id_raw = request.form.get('department_id', '').strip()
    remarks = request.form.get('remarks', '').strip()

    try:
        new_dept_id = int(new_dept_id_raw)
    except ValueError:
        flash('Invalid department selection.', 'danger')
        return redirect(url_for('admin.view_grievance', id=id))

    dept = db.execute('SELECT * FROM departments WHERE id = ?', (new_dept_id,)).fetchone()
    if dept is None:
        flash('Selected department does not exist.', 'danger')
        return redirect(url_for('admin.view_grievance', id=id))

    old_dept_name = grievance['current_department_name'] or 'Unassigned'
    new_dept_name = dept['name']

    if grievance['department_id'] == new_dept_id:
        flash(f'Grievance is already assigned to {new_dept_name}.', 'warning')
        return redirect(url_for('admin.view_grievance', id=id))

    try:
        cursor = db.cursor()
        cursor.execute(
            '''
            UPDATE grievances
            SET department_id = ?, updated_at = datetime('now')
            WHERE id = ?
            ''',
            (new_dept_id, id),
        )

        cursor.execute(
            '''
            INSERT INTO grievance_logs (
                grievance_id, changed_by, action, old_value, new_value, remarks
            ) VALUES (?, ?, 'department_change', ?, ?, ?)
            ''',
            (id, g.user['id'], old_dept_name, new_dept_name, remarks or None),
        )

        db.commit()
        flash(f'Department reassigned to {new_dept_name}.', 'success')
    except Exception:
        db.rollback()
        flash('Failed to reassign department due to a database error.', 'danger')

    return redirect(url_for('admin.view_grievance', id=id))
