-- Smart Campus Grievance & Resolution System
-- Database schema for SQLite

-- Users: students and administrators
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'student' CHECK (role IN ('student', 'admin')),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Campus departments that handle grievances
CREATE TABLE IF NOT EXISTS departments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT
);

-- Grievance submissions
CREATE TABLE IF NOT EXISTS grievances (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id          TEXT    NOT NULL UNIQUE,
    student_id         INTEGER NOT NULL,
    category           TEXT    NOT NULL,
    department_id      INTEGER,
    subject            TEXT    NOT NULL,
    description        TEXT    NOT NULL,
    location           TEXT    NOT NULL,
    priority           TEXT    NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high')),
    status             TEXT    NOT NULL DEFAULT 'open'    CHECK (status IN ('open', 'in_progress', 'resolved')),
    resolution_details TEXT,
    created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT    NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (student_id)    REFERENCES users(id),
    FOREIGN KEY (department_id) REFERENCES departments(id)
);

-- Audit trail for every grievance change
CREATE TABLE IF NOT EXISTS grievance_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    grievance_id INTEGER NOT NULL,
    changed_by   INTEGER NOT NULL,
    action       TEXT    NOT NULL,
    old_value    TEXT,
    new_value    TEXT,
    remarks      TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (grievance_id) REFERENCES grievances(id),
    FOREIGN KEY (changed_by)   REFERENCES users(id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_grievances_student    ON grievances(student_id);
CREATE INDEX IF NOT EXISTS idx_grievances_status     ON grievances(status);
CREATE INDEX IF NOT EXISTS idx_grievances_department ON grievances(department_id);
CREATE INDEX IF NOT EXISTS idx_logs_grievance        ON grievance_logs(grievance_id);


