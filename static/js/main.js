/**
 * Smart Campus Grievance & Resolution System
 * Vanilla JavaScript client-side enhancements:
 * - Asynchronous Admin Dashboard filtering via /admin/api/grievances
 * - Dynamic resolution details field toggle on status select
 * - Client-side form validation enhancements
 * - Dismissible flash notifications
 */

'use strict';

document.addEventListener('DOMContentLoaded', () => {
    initFlashDismissal();
    initResolutionFieldToggle();
    initAdminLiveFilter();
    initFormValidation();
});

/**
 * Enable close buttons on alert messages and auto-fade info alerts after 6 seconds.
 */
function initFlashDismissal() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach((alert) => {
        // Create a small dismiss button
        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.innerHTML = '&times;';
        closeBtn.className = 'alert-close-btn';
        closeBtn.setAttribute('aria-label', 'Dismiss alert');
        closeBtn.addEventListener('click', () => {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 200);
        });
        alert.appendChild(closeBtn);
    });
}

/**
 * Toggle resolution details textarea in admin view when status is set to 'resolved'.
 */
function initResolutionFieldToggle() {
    const statusSelect = document.getElementById('status');
    const resolutionGroup = document.getElementById('resolution-details-group');
    const resolutionTextarea = document.getElementById('resolution_details');

    if (statusSelect && resolutionGroup) {
        function checkStatus() {
            if (statusSelect.value === 'resolved') {
                resolutionGroup.style.display = 'block';
                if (resolutionTextarea) {
                    resolutionTextarea.setAttribute('required', 'required');
                }
            } else {
                resolutionGroup.style.display = 'none';
                if (resolutionTextarea) {
                    resolutionTextarea.removeAttribute('required');
                }
            }
        }

        statusSelect.addEventListener('change', checkStatus);
        checkStatus(); // Initial run on load
    }
}

/**
 * Asynchronous filtering on the admin dashboard using the JSON API endpoint.
 */
function initAdminLiveFilter() {
    const filterForm = document.getElementById('filter-form');
    const tbody = document.getElementById('grievances-tbody');
    const statusSelect = document.getElementById('filter-status');
    const prioritySelect = document.getElementById('filter-priority');
    const departmentSelect = document.getElementById('filter-department');
    const searchInput = document.getElementById('filter-search');

    if (!filterForm || !tbody) {
        return;
    }

    let debounceTimer = null;

    function fetchFilteredGrievances() {
        const params = new URLSearchParams();

        if (statusSelect && statusSelect.value) {
            params.set('status', statusSelect.value);
        }
        if (prioritySelect && prioritySelect.value) {
            params.set('priority', prioritySelect.value);
        }
        if (departmentSelect && departmentSelect.value) {
            params.set('department', departmentSelect.value);
        }
        if (searchInput && searchInput.value.trim()) {
            params.set('search', searchInput.value.trim());
        }

        const url = `/admin/api/grievances?${params.toString()}`;

        // Indicate loading
        tbody.style.opacity = '0.5';

        fetch(url, {
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
        })
            .then((res) => {
                if (!res.ok) {
                    throw new Error(`HTTP error ${res.status}`);
                }
                return res.json();
            })
            .then((data) => {
                renderGrievanceRows(data.grievances);
                tbody.style.opacity = '1';
            })
            .catch((err) => {
                console.error('Failed to fetch filtered grievances:', err);
                tbody.style.opacity = '1';
            });
    }

    function renderGrievanceRows(grievances) {
        tbody.innerHTML = '';

        if (!grievances || grievances.length === 0) {
            const tr = document.createElement('tr');
            tr.id = 'no-results-row';
            tr.innerHTML = `
                <td colspan="10" class="text-center text-muted" style="padding: 32px;">
                    No grievances found matching the specified criteria.
                </td>
            `;
            tbody.appendChild(tr);
            return;
        }

        grievances.forEach((g) => {
            const tr = document.createElement('tr');

            const statusLabel = g.status === 'in_progress' ? 'In Progress' : capitalize(g.status);
            const priorityLabel = capitalize(g.priority);

            tr.innerHTML = `
                <td class="cell-mono font-bold">${escapeHtml(g.ticket_id)}</td>
                <td>
                    <div class="student-cell">
                        <span class="student-name">${escapeHtml(g.student_name)}</span>
                        <span class="student-email text-muted">${escapeHtml(g.student_email)}</span>
                    </div>
                </td>
                <td>${escapeHtml(g.category)}</td>
                <td class="cell-subject">${escapeHtml(g.subject)}</td>
                <td>${escapeHtml(g.department_name)}</td>
                <td class="text-muted">${escapeHtml(g.location)}</td>
                <td>
                    <span class="badge badge-priority-${escapeHtml(g.priority)}">
                        ${priorityLabel}
                    </span>
                </td>
                <td>
                    <span class="badge badge-status-${escapeHtml(g.status)}">
                        ${statusLabel}
                    </span>
                </td>
                <td class="cell-date text-muted">${escapeHtml(g.created_at)}</td>
                <td>
                    <a href="${escapeHtml(g.url)}" class="btn btn-primary btn-sm">Manage</a>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    // Intercept form submit to prevent full reload when JS is active
    filterForm.addEventListener('submit', (e) => {
        e.preventDefault();
        fetchFilteredGrievances();
    });

    if (statusSelect) {
        statusSelect.addEventListener('change', fetchFilteredGrievances);
    }
    if (prioritySelect) {
        prioritySelect.addEventListener('change', fetchFilteredGrievances);
    }
    if (departmentSelect) {
        departmentSelect.addEventListener('change', fetchFilteredGrievances);
    }
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(fetchFilteredGrievances, 300);
        });
    }
}

/**
 * Client-side validation checks before submit.
 */
function initFormValidation() {
    const registerForm = document.querySelector('form[action*="register"]');
    if (registerForm) {
        registerForm.addEventListener('submit', (e) => {
            const password = registerForm.querySelector('input[name="password"]');
            const confirm = registerForm.querySelector('input[name="confirm_password"]');

            if (password && confirm && password.value !== confirm.value) {
                e.preventDefault();
                alert('Passwords do not match. Please ensure both password fields are identical.');
                confirm.focus();
            }
        });
    }
}

/**
 * Helper to capitalize a string.
 */
function capitalize(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * Simple HTML escape helper to prevent XSS in dynamic DOM insertions.
 */
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}
