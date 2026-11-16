"""
Administrator Blueprint for the Smart Campus Grievance System.
Provides administrative dashboard, search/filter controls, JSON API endpoint for
asynchronous filtering, department reassignment, priority adjustment,
status transitions, and transactional audit logging.
"""

import math

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

# Explicitly allowed status transitions: open -> in_progress, open -> resolved, in_progress -> resolved
# Backward transitions and reopening are strictly forbidden
VALID_STATUS_TRANSITIONS = {
    'open': ['in_progress', 'resolved'],
    'in_progress': ['resolved'],
    'resolved': [],
}


def validate_admin_filters(db, status=None, priority=None, department_id=None):
    """Validate admin filter parameters against allowed values and database records.

    Returns a list of error strings if any filter is invalid.
    """
    errors = []
    if status and status not in ALLOWED_STATUSES:
        errors.append(f"Invalid status filter '{status}'. Allowed statuses: {', '.join(ALLOWED_STATUSES)}.")

    if priority and priority not in ALLOWED_PRIORITIES:
        errors.append(f"Invalid priority filter '{priority}'. Allowed priorities: {', '.join(ALLOWED_PRIORITIES)}.")

    if department_id:
        try:
            dept_id_int = int(department_id)
            dept = db.execute('SELECT id FROM departments WHERE id = ?', (dept_id_int,)).fetchone()
            if not dept:
                errors.append(f"Department ID '{department_id}' does not exist.")
        except (ValueError, TypeError):
            errors.append(f"Invalid department filter '{department_id}'. Must be a valid department ID.")

    return errors


def build_grievance_query(status=None, priority=None, department_id=None, search=None, limit=None, offset=None):
    """Construct filtered grievance query and parameters with optional pagination."""
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
        except (ValueError, TypeError):
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

    if limit is not None:
        query += ' LIMIT ?'
        params.append(int(limit))
        if offset is not None:
            query += ' OFFSET ?'
            params.append(int(offset))

    return query, params


def count_filtered_grievances(db, status=None, priority=None, department_id=None, search=None):
    """Count total matching grievances for pagination."""
    query = '''
        SELECT COUNT(*)
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
        except (ValueError, TypeError):
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

    return db.execute(query, params).fetchone()[0]


@bp.route('/dashboard')
@admin_required
def dashboard():
    """Administrative dashboard displaying campus grievances with filters and pagination."""
    db = get_db()

    # Extract filter parameters
    status = request.args.get('status', '').strip()
    priority = request.args.get('priority', '').strip()
    department_id = request.args.get('department', '').strip()
    search = request.args.get('search', '').strip()

    # Validate filters instead of silently ignoring invalid options
    filter_errors = validate_admin_filters(db, status, priority, department_id)
    if filter_errors:
        for err in filter_errors:
            flash(err, 'danger')

        # Refuse to execute an unfiltered query on invalid parameters;
        # return a 400 Bad Request response with an empty result set and flash messages
        departments = db.execute('SELECT id, name FROM departments ORDER BY name ASC').fetchall()
        stats = {
            'total': db.execute('SELECT COUNT(*) FROM grievances').fetchone()[0],
            'open': db.execute("SELECT COUNT(*) FROM grievances WHERE status = 'open'").fetchone()[0],
            'in_progress': db.execute("SELECT COUNT(*) FROM grievances WHERE status = 'in_progress'").fetchone()[0],
            'resolved': db.execute("SELECT COUNT(*) FROM grievances WHERE status = 'resolved'").fetchone()[0],
        }
        pagination = {
            'page': 1,
            'per_page': 10,
            'total_items': 0,
            'total_pages': 1,
            'has_prev': False,
            'has_next': False,
            'prev_page': 1,
            'next_page': 1,
        }
        return render_template(
            'admin/dashboard.html',
            grievances=[],
            departments=departments,
            stats=stats,
            current_status=status,
            current_priority=priority,
            current_department=department_id,
            current_search=search,
            pagination=pagination,
            filter_params={},
            filter_errors=filter_errors,
        ), 400

    # Pagination setup (10 records per page)
    try:
        page = int(request.args.get('page', 1))
    except (ValueError, TypeError):
        page = 1
    if page < 1:
        page = 1

    per_page = 10
    total_items = count_filtered_grievances(db, status, priority, department_id, search)
    total_pages = max(1, math.ceil(total_items / per_page))
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page
    query, params = build_grievance_query(status, priority, department_id, search, limit=per_page, offset=offset)
    grievances = db.execute(query, params).fetchall()

    departments = db.execute('SELECT id, name FROM departments ORDER BY name ASC').fetchall()

    stats = {
        'total': db.execute('SELECT COUNT(*) FROM grievances').fetchone()[0],
        'open': db.execute("SELECT COUNT(*) FROM grievances WHERE status = 'open'").fetchone()[0],
        'in_progress': db.execute("SELECT COUNT(*) FROM grievances WHERE status = 'in_progress'").fetchone()[0],
        'resolved': db.execute("SELECT COUNT(*) FROM grievances WHERE status = 'resolved'").fetchone()[0],
    }

    pagination = {
        'page': page,
        'per_page': per_page,
        'total_items': total_items,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_page': page - 1,
        'next_page': page + 1,
    }

    # Preserve search and filter parameters for pagination links
    filter_params = {}
    if status:
        filter_params['status'] = status
    if priority:
        filter_params['priority'] = priority
    if department_id:
        filter_params['department'] = department_id
    if search:
        filter_params['search'] = search

    return render_template(
        'admin/dashboard.html',
        grievances=grievances,
        departments=departments,
        stats=stats,
        current_status=status,
        current_priority=priority,
        current_department=department_id,
        current_search=search,
        pagination=pagination,
        filter_params=filter_params,
    )


@bp.route('/api/grievances')
@admin_required
def api_grievances():
    """JSON API endpoint for asynchronous admin filtering with pagination.

    Provides filtered grievance data for dynamic UI updates without full page reload.
    Supports pagination via the 'page' query parameter with a fixed page size of 10 records per page.
    Validates invalid filters and out-of-range page parameters with 400 Bad Request.
    Removes unnecessary student personal information (such as personal email) from responses.
    """
    db = get_db()
    status = request.args.get('status', '').strip()
    priority = request.args.get('priority', '').strip()
    department_id = request.args.get('department', '').strip()
    search = request.args.get('search', '').strip()

    # Validate filters instead of silently ignoring
    filter_errors = validate_admin_filters(db, status, priority, department_id)
    if filter_errors:
        return jsonify({'error': 'Invalid filter parameters', 'messages': filter_errors}), 400

    # Pagination parameter validation
    try:
        page = int(request.args.get('page', 1))
        if page < 1:
            return jsonify({'error': 'Invalid page parameter. Must be a positive integer.'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid page parameter. Must be a positive integer.'}), 400

    per_page = 10

    total_items = count_filtered_grievances(db, status, priority, department_id, search)
    total_pages = max(1, math.ceil(total_items / per_page))

    if page > total_pages:
        return jsonify({'error': f'Page {page} exceeds total pages ({total_pages}).'}), 400

    offset = (page - 1) * per_page
    query, params = build_grievance_query(status, priority, department_id, search, limit=per_page, offset=offset)
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
            # Removed unnecessary student personal email to protect student privacy in API responses
            'url': url_for('admin.view_grievance', id=r['id']),
        })

    return jsonify({
        'count': len(results),
        'total_items': total_items,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'grievances': results,
    })


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

    if old_status == new_status:
        flash(f'Grievance is already marked as {new_status}.', 'warning')
        return redirect(url_for('admin.view_grievance', id=id))

    # Enforce explicit status transitions: open -> in_progress, open -> resolved, in_progress -> resolved
    # No backward transitions or reopening
    allowed_next = VALID_STATUS_TRANSITIONS.get(old_status, [])
    if new_status not in allowed_next:
        if old_status == 'resolved':
            flash('A resolved grievance cannot be reopened.', 'danger')
        else:
            flash(
                f'Invalid status transition from {old_status} to {new_status}. '
                'Backward transitions are not permitted.',
                'danger',
            )
        return redirect(url_for('admin.view_grievance', id=id))

    if new_status == 'resolved' and not resolution_details:
        flash('Resolution details are required when marking a ticket as resolved.', 'danger')
        return redirect(url_for('admin.view_grievance', id=id))

    try:
        cursor = db.cursor()
        # Use conditional UPDATE with WHERE status = ? to prevent concurrent stale updates
        # from bypassing transition rules. If another request changed the status between
        # our SELECT and UPDATE, rowcount will be 0 and we abort safely.
        if new_status == 'resolved':
            cursor.execute(
                '''
                UPDATE grievances
                SET status = ?, resolution_details = ?, updated_at = datetime('now')
                WHERE id = ? AND status = ?
                ''',
                (new_status, resolution_details, id, old_status),
            )
        else:
            cursor.execute(
                '''
                UPDATE grievances
                SET status = ?, updated_at = datetime('now')
                WHERE id = ? AND status = ?
                ''',
                (new_status, id, old_status),
            )

        if cursor.rowcount == 0:
            db.rollback()
            flash(
                'This grievance was modified by another administrator. '
                'Please review the current status and try again.',
                'warning',
            )
            return redirect(url_for('admin.view_grievance', id=id))

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

