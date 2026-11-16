"""
Comprehensive test suite for the Smart Campus Grievance & Resolution System.

Covers:
- JSON API pagination (Point 1)
- Concurrent status updates / conditional SQL (Point 2)
- Ticket privacy / uniform 404 (Point 3)
- Full regression suite for authentication, student, and admin workflows
"""

import json
import os
import re
import tempfile
import unittest
from unittest import mock

from werkzeug.security import generate_password_hash

from backend import create_app
from backend.admin import build_grievance_query
from backend.db import get_db
from backend.seed import provision_admin


class BaseTestCase(unittest.TestCase):
    """Shared test setup: create a temporary database and configure the test app."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.app = create_app({
            'TESTING': True,
            'DATABASE': self.db_path,
            'SECRET_KEY': 'test-secret-key-for-unit-tests',
            'WTF_CSRF_ENABLED': True,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db = get_db()
            schema_path = os.path.join(os.path.dirname(__file__), '..', 'databases', 'schema.sql')
            with open(schema_path, 'r') as f:
                db.executescript(f.read())

            # Seed departments
            departments = [
                ('IT', 'Technology issues'),
                ('Maintenance', 'Building maintenance'),
                ('Hostel Administration', 'Hostel issues'),
                ('Library Department', 'Library issues'),
            ]
            for name, desc in departments:
                db.execute('INSERT OR IGNORE INTO departments (name, description) VALUES (?, ?)', (name, desc))

            # Create admin user
            db.execute(
                'INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)',
                ('Test Admin', 'admin@test.edu', generate_password_hash('adminpass1'), 'admin'),
            )
            # Create two student users
            db.execute(
                'INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)',
                ('Student One', 'student1@test.edu', generate_password_hash('student1pass'), 'student'),
            )
            db.execute(
                'INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)',
                ('Student Two', 'student2@test.edu', generate_password_hash('student2pass'), 'student'),
            )
            db.commit()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def _get_csrf_token(self, html):
        """Extract CSRF token from HTML response."""
        match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
        if not match:
            match = re.search(r'value="([^"]+)"[^>]*name="csrf_token"', html)
        return match.group(1) if match else None

    def _login(self, email, password):
        """Log in a user and return the response."""
        resp = self.client.get('/auth/login')
        token = self._get_csrf_token(resp.data.decode())
        return self.client.post('/auth/login', data={
            'email': email,
            'password': password,
            'csrf_token': token,
        }, follow_redirects=True)

    def _logout(self):
        """Log out the current user."""
        # Need a page with a CSRF token
        resp = self.client.get('/')
        token = self._get_csrf_token(resp.data.decode())
        if token:
            return self.client.post('/auth/logout', data={'csrf_token': token}, follow_redirects=True)
        return None

    def _create_grievance_as_student(self, student_email, student_password, subject='Test Grievance', index=0):
        """Create a grievance and return its database ID."""
        self._login(student_email, student_password)
        resp = self.client.get('/student/grievances/new')
        token = self._get_csrf_token(resp.data.decode())
        self.client.post('/student/grievances/new', data={
            'category': 'Internet / Wi-Fi',
            'subject': subject,
            'location': 'Building A',
            'description': 'This is a detailed test description for the grievance.',
            'csrf_token': token,
        }, follow_redirects=True)
        self._logout()

        # Get the grievance ID from the database
        with self.app.app_context():
            db = get_db()
            row = db.execute(
                'SELECT id FROM grievances WHERE subject = ? ORDER BY id DESC LIMIT 1',
                (subject,),
            ).fetchone()
            return row['id'] if row else None


class TestJSONAPIPagination(BaseTestCase):
    """Point 1: Verify /admin/api/grievances supports pagination with LIMIT/OFFSET."""

    def test_api_returns_pagination_metadata(self):
        """JSON API should return page, per_page, total_items, total_pages fields."""
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/api/grievances')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn('page', data)
        self.assertIn('per_page', data)
        self.assertIn('total_items', data)
        self.assertIn('total_pages', data)
        self.assertEqual(data['page'], 1)
        self.assertEqual(data['per_page'], 10)

    def test_api_pagination_with_many_records(self):
        """With 15 records, page 1 should return 10 and page 2 should return 5."""
        # Create 15 grievances via direct DB insert
        with self.app.app_context():
            db = get_db()
            student = db.execute('SELECT id FROM users WHERE email = ?', ('student1@test.edu',)).fetchone()
            for i in range(15):
                db.execute(
                    '''INSERT INTO grievances (ticket_id, student_id, category, subject,
                       description, location, priority, status)
                       VALUES (?, ?, ?, ?, ?, ?, 'medium', 'open')''',
                    (f'GR-{1000+i}', student['id'], 'Internet / Wi-Fi',
                     f'Pagination Test {i}', f'Description {i}', 'Building A'),
                )
            db.commit()

        self._login('admin@test.edu', 'adminpass1')

        # Page 1 should have 10
        resp = self.client.get('/admin/api/grievances?page=1')
        data = json.loads(resp.data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data['count'], 10)
        self.assertEqual(data['total_items'], 15)
        self.assertEqual(data['total_pages'], 2)
        self.assertEqual(data['page'], 1)

        # Page 2 should have 5
        resp = self.client.get('/admin/api/grievances?page=2')
        data = json.loads(resp.data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data['count'], 5)
        self.assertEqual(data['page'], 2)

    def test_api_pagination_invalid_page_zero(self):
        """Page 0 should return 400 error."""
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/api/grievances?page=0')
        self.assertEqual(resp.status_code, 400)

    def test_api_pagination_invalid_page_string(self):
        """Non-integer page should return 400 error."""
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/api/grievances?page=abc')
        self.assertEqual(resp.status_code, 400)

    def test_api_pagination_negative_page(self):
        """Negative page should return 400 error."""
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/api/grievances?page=-1')
        self.assertEqual(resp.status_code, 400)

    def test_api_pagination_exceeds_total(self):
        """Page beyond total pages should return 400 when records exist."""
        with self.app.app_context():
            db = get_db()
            student = db.execute('SELECT id FROM users WHERE email = ?', ('student1@test.edu',)).fetchone()
            db.execute(
                '''INSERT INTO grievances (ticket_id, student_id, category, subject,
                   description, location, priority, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'medium', 'open')''',
                ('GR-9001', student['id'], 'Internet / Wi-Fi',
                 'Single Record', 'Description', 'Building A'),
            )
            db.commit()

        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/api/grievances?page=99')
        self.assertEqual(resp.status_code, 400)

    def test_api_pagination_preserves_filters(self):
        """Pagination should work with existing filters."""
        with self.app.app_context():
            db = get_db()
            student = db.execute('SELECT id FROM users WHERE email = ?', ('student1@test.edu',)).fetchone()
            for i in range(5):
                db.execute(
                    '''INSERT INTO grievances (ticket_id, student_id, category, subject,
                       description, location, priority, status)
                       VALUES (?, ?, ?, ?, ?, ?, 'high', 'open')''',
                    (f'GR-H{i}', student['id'], 'Internet / Wi-Fi',
                     f'High Priority {i}', f'Description {i}', 'Building A'),
                )
            for i in range(3):
                db.execute(
                    '''INSERT INTO grievances (ticket_id, student_id, category, subject,
                       description, location, priority, status)
                       VALUES (?, ?, ?, ?, ?, ?, 'low', 'open')''',
                    (f'GR-L{i}', student['id'], 'Internet / Wi-Fi',
                     f'Low Priority {i}', f'Description {i}', 'Building A'),
                )
            db.commit()

        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/api/grievances?priority=high&page=1')
        data = json.loads(resp.data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data['total_items'], 5)
        self.assertEqual(data['count'], 5)

    def test_api_no_student_email_in_response(self):
        """JSON responses should not contain student_email field."""
        with self.app.app_context():
            db = get_db()
            student = db.execute('SELECT id FROM users WHERE email = ?', ('student1@test.edu',)).fetchone()
            db.execute(
                '''INSERT INTO grievances (ticket_id, student_id, category, subject,
                   description, location, priority, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'medium', 'open')''',
                ('GR-PRIV', student['id'], 'Internet / Wi-Fi',
                 'Privacy Test', 'Description', 'Building A'),
            )
            db.commit()

        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/api/grievances')
        data = json.loads(resp.data)
        for g_item in data['grievances']:
            self.assertNotIn('student_email', g_item)

    def test_api_pagination_empty_results_page_one(self):
        """When no records match, page=1 should return 200 with total_pages=1 and empty list."""
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/api/grievances?page=1')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['total_items'], 0)
        self.assertEqual(data['page'], 1)
        self.assertEqual(data['total_pages'], 1)
        self.assertEqual(data['grievances'], [])

    def test_api_pagination_empty_results_out_of_range(self):
        """When no records match, requesting page=2 or page=99 should return 400 Bad Request."""
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/api/grievances?page=99')
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertIn('exceeds total pages', data.get('error', ''))


class TestConcurrentStatusUpdates(BaseTestCase):
    """Point 2: Verify conditional SQL UPDATE prevents stale concurrent status changes."""

    def _create_test_grievance(self):
        """Insert a grievance directly and return its ID."""
        with self.app.app_context():
            db = get_db()
            student = db.execute('SELECT id FROM users WHERE email = ?', ('student1@test.edu',)).fetchone()
            cursor = db.cursor()
            cursor.execute(
                '''INSERT INTO grievances (ticket_id, student_id, category, subject,
                   description, location, priority, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'medium', 'open')''',
                ('GR-CONC', student['id'], 'Internet / Wi-Fi',
                 'Concurrency Test', 'Test description', 'Building A'),
            )
            db.commit()
            return cursor.lastrowid

    def test_normal_status_transition(self):
        """Normal open -> in_progress transition should succeed."""
        gid = self._create_test_grievance()
        self._login('admin@test.edu', 'adminpass1')

        resp = self.client.get(f'/admin/grievances/{gid}')
        token = self._get_csrf_token(resp.data.decode())

        resp = self.client.post(f'/admin/grievances/{gid}/status', data={
            'status': 'in_progress',
            'remarks': 'Starting work',
            'csrf_token': token,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'in_progress', resp.data)

        # Verify in database
        with self.app.app_context():
            db = get_db()
            row = db.execute('SELECT status FROM grievances WHERE id = ?', (gid,)).fetchone()
            self.assertEqual(row['status'], 'in_progress')

    def test_stale_concurrent_update_prevented(self):
        """If another admin changes status between SELECT and UPDATE, the conditional SQL must detect it."""
        gid = self._create_test_grievance()
        self._login('admin@test.edu', 'adminpass1')

        resp = self.client.get(f'/admin/grievances/{gid}')
        token = self._get_csrf_token(resp.data.decode())

        from backend.db import get_db as real_get_db

        class CursorProxy:
            def __init__(self, real_cur, db_path, target_gid):
                self._cur = real_cur
                self._db_path = db_path
                self._gid = target_gid

            def __getattr__(self, name):
                return getattr(self._cur, name)

            def execute(self, sql, *exec_args, **exec_kwargs):
                if 'UPDATE grievances' in sql:
                    import sqlite3
                    with sqlite3.connect(self._db_path) as conn:
                        conn.execute("UPDATE grievances SET status = 'in_progress' WHERE id = ?", (self._gid,))
                return self._cur.execute(sql, *exec_args, **exec_kwargs)

        class ConnectionProxy:
            def __init__(self, real_conn, db_path, target_gid):
                self._conn = real_conn
                self._db_path = db_path
                self._gid = target_gid

            def __getattr__(self, name):
                return getattr(self._conn, name)

            def cursor(self):
                return CursorProxy(self._conn.cursor(), self._db_path, self._gid)

        with mock.patch('backend.admin.get_db', side_effect=lambda: ConnectionProxy(real_get_db(), self.db_path, gid)):
            resp = self.client.post(f'/admin/grievances/{gid}/status', data={
                'status': 'in_progress',
                'remarks': 'Race condition test',
                'csrf_token': token,
            }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'modified by another administrator', resp.data)

    def test_stale_concurrent_update_to_resolved(self):
        """Stale resolved transition caught by conditional UPDATE when status changed concurrently."""
        gid = self._create_test_grievance()
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE grievances SET status = 'in_progress' WHERE id = ?", (gid,))

        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get(f'/admin/grievances/{gid}')
        token = self._get_csrf_token(resp.data.decode())

        from backend.db import get_db as real_get_db

        class CursorProxy:
            def __init__(self, real_cur, db_path, target_gid):
                self._cur = real_cur
                self._db_path = db_path
                self._gid = target_gid

            def __getattr__(self, name):
                return getattr(self._cur, name)

            def execute(self, sql, *exec_args, **exec_kwargs):
                if 'UPDATE grievances' in sql:
                    import sqlite3
                    with sqlite3.connect(self._db_path) as conn:
                        conn.execute(
                            "UPDATE grievances SET status = 'resolved', resolution_details = 'Done' WHERE id = ?",
                            (self._gid,),
                        )
                return self._cur.execute(sql, *exec_args, **exec_kwargs)

        class ConnectionProxy:
            def __init__(self, real_conn, db_path, target_gid):
                self._conn = real_conn
                self._db_path = db_path
                self._gid = target_gid

            def __getattr__(self, name):
                return getattr(self._conn, name)

            def cursor(self):
                return CursorProxy(self._conn.cursor(), self._db_path, self._gid)

        with mock.patch('backend.admin.get_db', side_effect=lambda: ConnectionProxy(real_get_db(), self.db_path, gid)):
            resp = self.client.post(f'/admin/grievances/{gid}/status', data={
                'status': 'resolved',
                'resolution_details': 'My duplicate resolution',
                'remarks': 'Stale resolve',
                'csrf_token': token,
            }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'modified by another administrator', resp.data)

    def test_conditional_update_sql_directly(self):
        """Directly verify conditional SQL UPDATE rejects stale status."""
        gid = self._create_test_grievance()
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            # Simulate first admin updating open -> in_progress
            cur1 = conn.cursor()
            cur1.execute(
                "UPDATE grievances SET status = ? WHERE id = ? AND status = ?",
                ('in_progress', gid, 'open'),
            )
            self.assertEqual(cur1.rowcount, 1)

            # Concurrent/stale second admin attempting update assuming status was still 'open'
            cur2 = conn.cursor()
            cur2.execute(
                "UPDATE grievances SET status = ? WHERE id = ? AND status = ?",
                ('resolved', gid, 'open'),
            )
            self.assertEqual(cur2.rowcount, 0)

    def test_valid_transition_chain(self):
        """Full lifecycle: open -> in_progress -> resolved should work sequentially."""
        gid = self._create_test_grievance()
        self._login('admin@test.edu', 'adminpass1')

        # open -> in_progress
        resp = self.client.get(f'/admin/grievances/{gid}')
        token = self._get_csrf_token(resp.data.decode())
        self.client.post(f'/admin/grievances/{gid}/status', data={
            'status': 'in_progress',
            'remarks': 'Working on it',
            'csrf_token': token,
        }, follow_redirects=True)

        # in_progress -> resolved
        resp = self.client.get(f'/admin/grievances/{gid}')
        token = self._get_csrf_token(resp.data.decode())
        resp = self.client.post(f'/admin/grievances/{gid}/status', data={
            'status': 'resolved',
            'resolution_details': 'Issue fixed.',
            'remarks': 'Done',
            'csrf_token': token,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            db = get_db()
            row = db.execute('SELECT status FROM grievances WHERE id = ?', (gid,)).fetchone()
            self.assertEqual(row['status'], 'resolved')

    def test_backward_transition_blocked(self):
        """in_progress -> open should be blocked."""
        gid = self._create_test_grievance()
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute('UPDATE grievances SET status = ? WHERE id = ?', ('in_progress', gid))
        conn.commit()
        conn.close()

        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get(f'/admin/grievances/{gid}')
        token = self._get_csrf_token(resp.data.decode())

        resp = self.client.post(f'/admin/grievances/{gid}/status', data={
            'status': 'open',
            'csrf_token': token,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Backward transitions are not permitted', resp.data)

    def test_resolved_cannot_reopen(self):
        """resolved -> open or resolved -> in_progress should be blocked."""
        gid = self._create_test_grievance()
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE grievances SET status = 'resolved', resolution_details = 'Done' WHERE id = ?",
            (gid,),
        )
        conn.commit()
        conn.close()

        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get(f'/admin/grievances/{gid}')
        token = self._get_csrf_token(resp.data.decode())

        resp = self.client.post(f'/admin/grievances/{gid}/status', data={
            'status': 'open',
            'csrf_token': token,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'cannot be reopened', resp.data)


class TestTicketPrivacy(BaseTestCase):
    """Point 3: Verify uniform 404 for another student's ticket and nonexistent ticket."""

    def test_own_ticket_accessible(self):
        """A student should be able to view their own grievance."""
        gid = self._create_grievance_as_student('student1@test.edu', 'student1pass', 'My Own Ticket')
        self.assertIsNotNone(gid)

        self._login('student1@test.edu', 'student1pass')
        resp = self.client.get(f'/student/grievances/{gid}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'My Own Ticket', resp.data)

    def test_other_students_ticket_returns_404(self):
        """Accessing another student's ticket should return 404 (not 403)."""
        gid = self._create_grievance_as_student('student1@test.edu', 'student1pass', 'Student1 Private Ticket')
        self.assertIsNotNone(gid)

        self._login('student2@test.edu', 'student2pass')
        resp = self.client.get(f'/student/grievances/{gid}')
        self.assertEqual(resp.status_code, 404)

    def test_nonexistent_ticket_returns_404(self):
        """Accessing a nonexistent ticket ID should return 404."""
        self._login('student1@test.edu', 'student1pass')
        resp = self.client.get('/student/grievances/99999')
        self.assertEqual(resp.status_code, 404)

    def test_uniform_404_response(self):
        """Both cases (other student's ticket and nonexistent ticket) must return identical status codes."""
        gid = self._create_grievance_as_student('student1@test.edu', 'student1pass', 'Enumeration Test')
        self.assertIsNotNone(gid)

        # Access another student's ticket
        self._login('student2@test.edu', 'student2pass')
        resp_other = self.client.get(f'/student/grievances/{gid}')

        # Access nonexistent ticket
        resp_missing = self.client.get('/student/grievances/99999')

        # Both must be 404 — no distinction allowed
        self.assertEqual(resp_other.status_code, 404)
        self.assertEqual(resp_missing.status_code, 404)
        self.assertEqual(resp_other.status_code, resp_missing.status_code)

    def test_admin_can_view_any_ticket(self):
        """Admin should still be able to view any student's grievance."""
        gid = self._create_grievance_as_student('student1@test.edu', 'student1pass', 'Admin View Test')
        self.assertIsNotNone(gid)

        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get(f'/student/grievances/{gid}')
        self.assertEqual(resp.status_code, 200)


class TestRegressionSuite(BaseTestCase):
    """Full regression tests covering auth, student, and admin workflows."""

    def test_landing_page(self):
        """Landing page should be accessible."""
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)

    def test_registration(self):
        """New student should be able to register."""
        resp = self.client.get('/auth/register')
        token = self._get_csrf_token(resp.data.decode())
        resp = self.client.post('/auth/register', data={
            'full_name': 'New Student',
            'email': 'newstudent@test.edu',
            'password': 'securepass1',
            'confirm_password': 'securepass1',
            'csrf_token': token,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Registration successful', resp.data)

    def test_registration_short_password(self):
        """Password under 8 characters should be rejected."""
        resp = self.client.get('/auth/register')
        token = self._get_csrf_token(resp.data.decode())
        resp = self.client.post('/auth/register', data={
            'full_name': 'Short Pass',
            'email': 'short@test.edu',
            'password': '1234567',
            'confirm_password': '1234567',
            'csrf_token': token,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'at least 8 characters', resp.data)

    def test_login_logout(self):
        """Student login and logout cycle should work."""
        resp = self._login('student1@test.edu', 'student1pass')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Welcome back', resp.data)

        resp = self._logout()
        self.assertIsNotNone(resp)
        self.assertIn(b'logged out', resp.data)

    def test_invalid_login(self):
        """Wrong credentials should fail."""
        resp = self._login('student1@test.edu', 'wrongpassword')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Invalid email or password', resp.data)

    def test_student_dashboard_requires_login(self):
        """Student dashboard should redirect unauthenticated users."""
        resp = self.client.get('/student/dashboard')
        self.assertEqual(resp.status_code, 302)

    def test_admin_dashboard_requires_admin(self):
        """Student should not access admin dashboard."""
        self._login('student1@test.edu', 'student1pass')
        resp = self.client.get('/admin/dashboard')
        self.assertEqual(resp.status_code, 403)

    def test_submit_grievance(self):
        """Student should be able to submit a grievance."""
        self._login('student1@test.edu', 'student1pass')
        resp = self.client.get('/student/grievances/new')
        token = self._get_csrf_token(resp.data.decode())
        resp = self.client.post('/student/grievances/new', data={
            'category': 'Internet / Wi-Fi',
            'subject': 'Wi-Fi down in Block C',
            'location': 'Block C, Floor 2',
            'description': 'The Wi-Fi has been intermittent for the past week in Block C.',
            'csrf_token': token,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'submitted successfully', resp.data)

    def test_admin_dashboard_access(self):
        """Admin should access the dashboard with stats."""
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/dashboard')
        self.assertEqual(resp.status_code, 200)

    def test_admin_invalid_filter(self):
        """Admin dashboard should return 400 Bad Request and not return broader unfiltered results on invalid filters."""
        with self.app.app_context():
            db = get_db()
            student = db.execute('SELECT id FROM users WHERE email = ?', ('student1@test.edu',)).fetchone()
            db.execute(
                '''INSERT INTO grievances (ticket_id, student_id, category, subject,
                   description, location, priority, status)
                   VALUES ('GR-LEAK', ?, 'Internet / Wi-Fi', 'Unfiltered Query Leak Test', 'Desc', 'Loc', 'medium', 'open')''',
                (student['id'],),
            )
            db.commit()

        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/dashboard?status=bogus')
        # Must return 400 Bad Request consistent with JSON endpoint
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b'Invalid status filter', resp.data)
        # Must not display broader/unfiltered records
        self.assertNotIn(b'Unfiltered Query Leak Test', resp.data)

    def test_admin_invalid_priority_filter(self):
        """Admin dashboard should return 400 on invalid priority filter."""
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/dashboard?priority=ultra')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b'Invalid priority filter', resp.data)

    def test_admin_invalid_department_filter(self):
        """Admin dashboard should return 400 on nonexistent department ID."""
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/dashboard?department=9999')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b'Department ID', resp.data)

    def test_safe_redirect_validation(self):
        """Login with external redirect URL should be rejected."""
        resp = self.client.get('/auth/login')
        token = self._get_csrf_token(resp.data.decode())
        resp = self.client.post('/auth/login?next=//evil.com', data={
            'email': 'student1@test.edu',
            'password': 'student1pass',
            'csrf_token': token,
        })
        # Should not redirect to evil.com; should redirect to a safe page
        self.assertNotIn(b'evil.com', resp.data)

    def test_duplicate_email_registration(self):
        """Registering with an existing email should fail."""
        resp = self.client.get('/auth/register')
        token = self._get_csrf_token(resp.data.decode())
        resp = self.client.post('/auth/register', data={
            'full_name': 'Duplicate',
            'email': 'student1@test.edu',
            'password': 'password123',
            'confirm_password': 'password123',
            'csrf_token': token,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'already exists', resp.data)

    def test_grievance_audit_log_created(self):
        """Submitting a grievance should create an audit log entry."""
        gid = self._create_grievance_as_student('student1@test.edu', 'student1pass', 'Audit Log Test')
        self.assertIsNotNone(gid)

        with self.app.app_context():
            db = get_db()
            log = db.execute(
                'SELECT * FROM grievance_logs WHERE grievance_id = ? AND action = ?',
                (gid, 'created'),
            ).fetchone()
            self.assertIsNotNone(log)
            self.assertEqual(log['new_value'], 'open')

    def test_status_change_creates_audit_log(self):
        """Admin status change should create an audit log entry."""
        gid = self._create_test_grievance_direct()
        self._login('admin@test.edu', 'adminpass1')

        resp = self.client.get(f'/admin/grievances/{gid}')
        token = self._get_csrf_token(resp.data.decode())
        self.client.post(f'/admin/grievances/{gid}/status', data={
            'status': 'in_progress',
            'remarks': 'Audit test',
            'csrf_token': token,
        }, follow_redirects=True)

        with self.app.app_context():
            db = get_db()
            log = db.execute(
                'SELECT * FROM grievance_logs WHERE grievance_id = ? AND action = ?',
                (gid, 'status_change'),
            ).fetchone()
            self.assertIsNotNone(log)
            self.assertEqual(log['old_value'], 'open')
            self.assertEqual(log['new_value'], 'in_progress')

    def test_dashboard_pagination_empty_results_clamps_page(self):
        """When no records exist, requesting page=99 clamps page to 1."""
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/dashboard?page=99')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Page 1 of 1', resp.data)
        self.assertIn(b'Showing 0 of 0 grievances', resp.data)
        self.assertNotIn(b'Page 99 of 1', resp.data)

    def test_dashboard_html_table_omits_student_email(self):
        """Dashboard HTML table row displays student name but omits student email."""
        gid = self._create_test_grievance_direct()
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/dashboard')
        self.assertEqual(resp.status_code, 200)
        # Student name should be in the student cell
        self.assertIn(b'Student One', resp.data)
        # Student email should NOT be rendered in the table cell
        self.assertNotIn(b'class="student-email', resp.data)
        self.assertNotIn(b'student1@test.edu', resp.data)

    def test_admin_detail_view_preserves_student_email(self):
        """Individual ticket detail view retains student email for administration."""
        gid = self._create_test_grievance_direct()
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get(f'/admin/grievances/{gid}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'student1@test.edu', resp.data)

    def test_dashboard_pagination_controls_are_anchors(self):
        """Pagination controls are always actual anchor elements with aria-disabled attributes."""
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/dashboard')
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        # Verify pagination-prev is an anchor tag with aria-disabled
        self.assertRegex(html, r'<a[^>]+id="pagination-prev"[^>]*aria-disabled="true"')
        # Verify pagination-next is an anchor tag with aria-disabled
        self.assertRegex(html, r'<a[^>]+id="pagination-next"[^>]*aria-disabled="true"')

    def test_dashboard_pagination_container_has_data_current_page(self):
        """Pagination container carries data-current-page matching the rendered clamped page."""
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/dashboard?page=99')
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        self.assertIn('data-current-page="1"', html)

    def test_build_grievance_query_minimizes_personal_data(self):
        """build_grievance_query excludes student_id and student_email from SELECT clause."""
        query, params = build_grievance_query()
        select_clause = query.split('FROM')[0]
        # Excludes unnecessary student personal data
        self.assertNotIn('student_email', select_clause)
        self.assertNotIn('student_id', select_clause)
        # Retains student full name
        self.assertIn('student_name', select_clause)

    def test_search_by_student_email_works_with_minimized_query(self):
        """Searching by student email remains functional even with minimized SELECT clause."""
        gid = self._create_test_grievance_direct()
        self._login('admin@test.edu', 'adminpass1')
        resp = self.client.get('/admin/api/grievances?search=student1@test.edu')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data['total_items'], 1)
        self.assertEqual(data['grievances'][0]['id'], gid)
        self.assertNotIn('student_email', data['grievances'][0])

    def test_js_debounce_and_history_sync_implementation(self):
        """Verify static/js/main.js implements debounce cancellation, history synchronization, and DOM-based page initialization."""
        js_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'static', 'js', 'main.js')
        with open(js_path, 'r') as f:
            js_code = f.read()

        # Debounce cancellation
        self.assertIn('clearPendingDebounce', js_code)
        # AbortController cancellation
        self.assertIn('AbortController', js_code)
        self.assertIn('currentAbortController.abort()', js_code)
        # DOM dataset current page initialization
        self.assertIn('dataset.currentPage', js_code)
        # Avoid duplicate history entries
        self.assertIn('browserUrl !== currentUrl', js_code)
        # popstate debounce clearing and form restoration
        self.assertIn('popstate', js_code)

    def _create_test_grievance_direct(self):
        """Insert a test grievance directly into the DB."""
        with self.app.app_context():
            db = get_db()
            student = db.execute('SELECT id FROM users WHERE email = ?', ('student1@test.edu',)).fetchone()
            cursor = db.cursor()
            cursor.execute(
                '''INSERT INTO grievances (ticket_id, student_id, category, subject,
                   description, location, priority, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'medium', 'open')''',
                ('GR-REG', student['id'], 'Internet / Wi-Fi',
                 'Regression Test', 'Test description content', 'Building A'),
            )
            db.commit()
            return cursor.lastrowid


class TestAdminProvisioningHardening(BaseTestCase):
    """Point 3: Hardened admin credential provisioning validation."""

    def test_provision_admin_invalid_email(self):
        """Invalid email formats should be rejected."""
        with self.app.app_context():
            ok, msg = provision_admin('notanemail', 'secureAdminPass1')
            self.assertFalse(ok)
            self.assertIn('Invalid email address format', msg)

            ok, msg = provision_admin('', 'secureAdminPass1')
            self.assertFalse(ok)

            ok, msg = provision_admin('@missinglocal.com', 'secureAdminPass1')
            self.assertFalse(ok)

    def test_provision_admin_short_password(self):
        """Passwords under 8 characters should be rejected."""
        with self.app.app_context():
            ok, msg = provision_admin('newadmin@test.edu', 'short7')
            self.assertFalse(ok)
            self.assertIn('at least 8 characters', msg)

    def test_provision_admin_long_password(self):
        """Passwords exceeding 128 characters should be rejected."""
        with self.app.app_context():
            ok, msg = provision_admin('newadmin@test.edu', 'A' * 129)
            self.assertFalse(ok)
            self.assertIn('cannot exceed 128 characters', msg)

    def test_provision_admin_success(self):
        """Valid admin credentials should provision successfully."""
        with self.app.app_context():
            ok, msg = provision_admin('valid.admin@campus.edu', 'validPassword123')
            self.assertTrue(ok)
            self.assertIn('provisioned successfully', msg)

            db = get_db()
            user = db.execute('SELECT * FROM users WHERE email = ?', ('valid.admin@campus.edu',)).fetchone()
            self.assertIsNotNone(user)
            self.assertEqual(user['role'], 'admin')

    def test_provision_admin_cannot_promote_student(self):
        """Existing student account cannot be promoted to admin."""
        with self.app.app_context():
            ok, msg = provision_admin('student1@test.edu', 'newPassword123')
            self.assertFalse(ok)
            self.assertIn('existing student account', msg)

            db = get_db()
            user = db.execute('SELECT role FROM users WHERE email = ?', ('student1@test.edu',)).fetchone()
            self.assertEqual(user['role'], 'student')

    def test_provision_admin_preserves_existing_admin(self):
        """Existing administrator account is preserved without password overwrite."""
        with self.app.app_context():
            ok, msg = provision_admin('admin@test.edu', 'differentPassword123')
            self.assertFalse(ok)
            self.assertIn('already exists', msg)


if __name__ == '__main__':
    unittest.main(verbosity=2)
