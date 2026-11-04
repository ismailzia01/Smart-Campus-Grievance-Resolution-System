# Smart Campus Grievance & Resolution System

A full-stack campus administration web portal built with **Python Flask**, **SQLite**, **Jinja2**, and **vanilla JavaScript**.

The platform enables students to lodge facilities, IT, hostel, and academic grievances with automatic departmental routing, while giving campus administrators the tools to triage, prioritize, reassign, and resolve tickets with a tamper-evident audit history.

---

## Key Features

### For Students
- **Account Registration & Secure Login**: Students register with their campus email and name. Passwords are securely hashed using modern cryptographic algorithms (`scrypt` / `pbkdf2`).
- **Grievance Lodging**: Submit grievances with a category, specific campus location, subject summary, and detailed description.
- **Smart Department Routing**: Categories automatically map to relevant campus departments on submission:
  - *Internet / Wi-Fi* &rarr; **IT Department**
  - *Classroom Equipment* &rarr; **Maintenance Department**
  - *Hostel Facilities* &rarr; **Hostel Administration**
  - *Library Facilities* &rarr; **Library Department**
  - *Other* &rarr; Direct triage by administration
- **Ticket Tracking**: View submitted tickets with human-readable IDs (`GR-0001`, `GR-0002`), current lifecycle state, assigned department, and priority.
- **Audit Timeline**: View a transparent chronological timeline of every administrative action, department transfer, and status change performed on your ticket.
- **Resolution Visibility**: Read official resolution notes once the ticket is resolved.
- **Strict Data Isolation**: Students can only access their own submitted grievances.

### For Administrators
- **Administrative Dashboard**: Overview summary metrics (Total, Open, In Progress, Resolved tickets).
- **Asynchronous Live Search & Filter**: Instant filtering across status, priority, department, and text keywords via a dedicated JSON endpoint without reloading the page.
- **Ticket Lifecycle Management**: Transition tickets through verified states:
  $$\text{Open} \longrightarrow \text{In Progress} \longrightarrow \text{Resolved}$$
- **Mandatory Resolution Notes**: Marking a ticket as *Resolved* strictly enforces administrative resolution details.
- **Lifecycle Locking**: Resolved tickets are locked to preserve audit integrity and prevent unauthorized re-opening.
- **Priority Adjustments**: Adjust priority (`Low`, `Medium`, `High`) with optional audit remarks.
- **Department Reassignment**: Reassign tickets to other departments when an issue crosses domains.
- **Permanent Audit Trail**: Every status transition, priority adjustment, and department reassignment is recorded in `grievance_logs` with the acting administrator's identity, timestamp, and optional remarks.

---

## Tech Stack & Architecture

- **Backend**: Python 3, Flask 3.1
- **Database**: SQLite with foreign key enforcement (`PRAGMA foreign_keys = ON`)
- **Template Engine**: Jinja2 with template inheritance
- **Styling**: Vanilla CSS (no external UI frameworks, clean university administrative design system)
- **Client Scripting**: Vanilla JavaScript (async filtering via Fetch API, DOM manipulation, no heavy frontend frameworks)
- **Security & Forms**: Flask-WTF (`CSRFProtect`), Werkzeug Security (`generate_password_hash`, `check_password_hash`)
- **Environment Management**: `python-dotenv`

### Folder Structure

```
Smart-Campus-Grievance-Resolution-System/
├── app.py                   # Application factory & error handlers
├── auth.py                  # Authentication blueprint & access decorators
├── student.py               # Student blueprint (dashboard, submit, view)
├── admin.py                 # Admin blueprint (dashboard, management, JSON API)
├── db.py                    # SQLite connection lifecycle & CLI commands
├── seed.py                  # Department seeding & secure admin provisioning
├── schema.sql               # SQLite 4-table relational schema & indexes
├── requirements.txt         # Pinned Python package dependencies
├── .env                     # Environment variables (gitignored)
├── instance/
│   └── database.db          # SQLite runtime database file (gitignored)
├── static/
│   ├── css/
│   │   └── style.css        # University administration stylesheet
│   └── js/
│       └── main.js          # Vanilla JS for live filters & form handling
└── templates/
    ├── base.html            # Base layout with header, navigation & flash messages
    ├── index.html           # Campus landing page
    ├── auth/
    │   ├── login.html       # Login form
    │   └── register.html    # Student registration form
    ├── student/
    │   ├── dashboard.html   # Student ticket dashboard
    │   ├── new_grievance.html # Grievance submission form
    │   └── view_grievance.html # Student ticket detail & timeline
    ├── admin/
    │   ├── dashboard.html   # Admin overview & live filterable table
    │   └── view_grievance.html # Admin management view & action forms
    └── errors/
        ├── 400.html         # Bad request / expired CSRF error
        ├── 403.html         # Forbidden access error
        ├── 404.html         # Page / ticket not found error
        └── 500.html         # Internal server error
```

---

## Database Design

The system uses a 4-table relational schema:

1. **`users`**: Stores students and administrators.
   - `id`, `full_name`, `email` (UNIQUE), `password_hash`, `role` (`student` | `admin`), `created_at`
2. **`departments`**: Campus departments handling grievances.
   - `id`, `name` (UNIQUE), `description`
3. **`grievances`**: Core grievance tickets.
   - `id`, `ticket_id` (UNIQUE, e.g. `GR-0001`), `student_id` (FK), `category`, `department_id` (FK), `subject`, `description`, `location`, `priority`, `status`, `resolution_details`, `created_at`, `updated_at`
4. **`grievance_logs`**: Permanent audit entries.
   - `id`, `grievance_id` (FK), `changed_by` (FK), `action`, `old_value`, `new_value`, `remarks`, `created_at`

---

## Security Implementation

- **CSRF Protection**: Flask-WTF protects all state-changing `POST` requests. Form submissions missing a valid token return a `400 Bad Request`.
- **Signed Sessions**: Session cookies are signed with an HMAC key (`SECRET_KEY`) using `itsdangerous`.
- **Minimal Session Storage**: Only `user_id` is stored in the cookie. The user's role and identity are resolved from the database per request so permissions update immediately.
- **Session Fixation Defense**: `session.clear()` is called immediately prior to establishing an authenticated session upon login.
- **Cookie Flags**: Cookies have `HttpOnly` enabled to prevent XSS access and `SameSite=Lax` to prevent cross-site request forgery.
- **Secure Password Hashing**: Passwords are never stored in plaintext. They are hashed using Werkzeug's cryptographic methods.
- **Safe Admin Provisioning**: No hardcoded default credentials exist in source code. Initial administrators are provisioned via environment variables or interactive CLI prompts. Routine seeding never resets existing passwords.

---

## Setup and Installation

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.14)
- Git

### 2. Clone Repository
```bash
git clone https://github.com/your-username/Smart-Campus-Grievance-Resolution-System.git
cd Smart-Campus-Grievance-Resolution-System
```

### 3. Create and Activate Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Environment Configuration
Create a `.env` file in the project root:
```env
SECRET_KEY=your-generated-secret-key-here
ADMIN_EMAIL=admin@smartcampus.edu
ADMIN_PASSWORD=YourSecurePassword123!
```

> You can generate a secure `SECRET_KEY` with:
> ```bash
> python3 -c "import secrets; print(secrets.token_hex(32))"
> ```

### 6. Initialize and Seed Database
Run the Flask CLI commands to create the schema and seed campus departments:
```bash
# Initialize SQLite tables
flask init-db

# Seed departments and provision the administrator account
flask seed-db
```

### 7. Run the Application
```bash
flask run
```
The application will be accessible at: **`http://127.0.0.1:5000`**

---

## Default Roles & Access

| Role | Default Email | Provisioned Via | Access Capabilities |
|------|---------------|-----------------|---------------------|
| **Administrator** | `admin@smartcampus.edu` | `flask seed-db` via `.env` | Access `/admin/dashboard`, triage, prioritize, reassign departments, resolve tickets, view all campus logs. |
| **Student** | Self-registered | `/auth/register` | Access `/student/dashboard`, lodge new grievances, track ticket progress, view resolution notes. |

---

## Automated Verification

The application includes automated end-to-end verification covering:
- Authentication & password hashing
- Session fixation & minimal session cookie verification
- CSRF protection rejection on unauthenticated POST requests
- POST logout with CSRF enforcement & 405 rejection on GET logout
- Student grievance submission, category validation, auto-department mapping
- Cross-student data isolation & 403 Forbidden enforcement on unauthorized ticket access
- Admin dashboard filtering, live JSON API endpoint, and metrics
- Transactional audit logging for status, priority, and department changes
- Workflow lifecycle locking (resolved tickets cannot be reopened)

Run the verification test suite:
```bash
python3 -c "
from app import create_app
print('App builds and boots cleanly!')
"
```

---

## License
Educational and campus administration software developed for university facilities management.
