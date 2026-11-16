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
 * Integrates live filtering with pagination, URL synchronization, and error handling.
 */
function initAdminLiveFilter() {
    const filterForm = document.getElementById('filter-form');
    const tbody = document.getElementById('grievances-tbody');
    const statusSelect = document.getElementById('filter-status');
    const prioritySelect = document.getElementById('filter-priority');
    const departmentSelect = document.getElementById('filter-department');
    const searchInput = document.getElementById('filter-search');

    const paginationContainer = document.getElementById('pagination-container');
    const paginationSummary = document.getElementById('pagination-summary');
    const paginationIndicator = document.getElementById('pagination-indicator');
    const paginationPrev = document.getElementById('pagination-prev');
    const paginationNext = document.getElementById('pagination-next');
    const errorBanner = document.getElementById('filter-error-banner');

    if (!filterForm || !tbody) {
        return;
    }

    let debounceTimer = null;
    let currentAbortController = null;
    let latestRequestId = 0;
    const initialParams = new URLSearchParams(window.location.search);
    let currentPage = parseInt(initialParams.get('page'), 10) || 1;

    function buildFilterParams(page = 1) {
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
        if (page > 1) {
            params.set('page', page.toString());
        }
        return params;
    }

    function showFilterError(message) {
        if (errorBanner) {
            errorBanner.textContent = message;
            errorBanner.style.display = 'block';
        }
    }

    function hideFilterError() {
        if (errorBanner) {
            errorBanner.textContent = '';
            errorBanner.style.display = 'none';
        }
    }

    function updatePagination(data) {
        if (!paginationContainer) {
            return;
        }

        const page = data.page || 1;
        const perPage = data.per_page || 10;
        const totalItems = data.total_items !== undefined ? data.total_items : (data.count || 0);
        const totalPages = data.total_pages || Math.max(1, Math.ceil(totalItems / perPage));

        // Update total-record count and range summary
        if (paginationSummary) {
            if (totalItems > 0) {
                const start = ((page - 1) * perPage) + 1;
                const end = Math.min(page * perPage, totalItems);
                paginationSummary.textContent = `Showing ${start} to ${end} of ${totalItems} grievances`;
            } else {
                paginationSummary.textContent = 'Showing 0 of 0 grievances';
            }
        }

        // Update page indicator
        if (paginationIndicator) {
            paginationIndicator.textContent = `Page ${page} of ${totalPages}`;
        }

        // Update Previous control (actual anchor element)
        if (paginationPrev) {
            if (page > 1) {
                paginationPrev.style.opacity = '1';
                paginationPrev.style.pointerEvents = 'auto';
                paginationPrev.dataset.page = (page - 1).toString();
                const prevParams = buildFilterParams(page - 1);
                paginationPrev.setAttribute('href', `?${prevParams.toString()}`);
                paginationPrev.setAttribute('aria-disabled', 'false');
                paginationPrev.setAttribute('tabindex', '0');
            } else {
                paginationPrev.style.opacity = '0.5';
                paginationPrev.style.pointerEvents = 'none';
                paginationPrev.removeAttribute('data-page');
                paginationPrev.removeAttribute('href');
                paginationPrev.setAttribute('aria-disabled', 'true');
                paginationPrev.setAttribute('tabindex', '-1');
            }
        }

        // Update Next control (actual anchor element)
        if (paginationNext) {
            if (page < totalPages) {
                paginationNext.style.opacity = '1';
                paginationNext.style.pointerEvents = 'auto';
                paginationNext.dataset.page = (page + 1).toString();
                const nextParams = buildFilterParams(page + 1);
                paginationNext.setAttribute('href', `?${nextParams.toString()}`);
                paginationNext.setAttribute('aria-disabled', 'false');
                paginationNext.setAttribute('tabindex', '0');
            } else {
                paginationNext.style.opacity = '0.5';
                paginationNext.style.pointerEvents = 'none';
                paginationNext.removeAttribute('data-page');
                paginationNext.removeAttribute('href');
                paginationNext.setAttribute('aria-disabled', 'true');
                paginationNext.setAttribute('tabindex', '-1');
            }
        }

        // Show pagination controls only when there are multiple pages
        paginationContainer.style.display = totalPages > 1 ? 'flex' : 'none';
    }

    function fetchFilteredGrievances(targetPage = 1, updateHistory = true) {
        // Cancel any pending in-flight request to prevent stale race conditions
        if (currentAbortController) {
            currentAbortController.abort();
            currentAbortController = null;
        }

        const requestId = ++latestRequestId;
        const abortController = new AbortController();
        currentAbortController = abortController;

        currentPage = targetPage;
        const params = buildFilterParams(currentPage);
        // Ensure page is always explicitly included for the API call
        params.set('page', currentPage.toString());
        const apiUrl = `/admin/api/grievances?${params.toString()}`;

        // Synchronize browser URL query parameters
        if (updateHistory && window.history && window.history.pushState) {
            const browserParams = buildFilterParams(currentPage);
            const browserQuery = browserParams.toString();
            const browserUrl = browserQuery ? `${window.location.pathname}?${browserQuery}` : window.location.pathname;
            window.history.pushState({ page: currentPage }, '', browserUrl);
        }

        hideFilterError();
        tbody.style.opacity = '0.5';

        fetch(apiUrl, {
            signal: abortController.signal,
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
        })
            .then(async (res) => {
                if (requestId !== latestRequestId) {
                    return null;
                }
                if (!res.ok) {
                    let errorMsg = `Server returned status ${res.status}`;
                    try {
                        const errJson = await res.json();
                        if (errJson.messages && errJson.messages.length) {
                            errorMsg = errJson.messages.join(' ');
                        } else if (errJson.error) {
                            errorMsg = errJson.error;
                        }
                    } catch (_) {}
                    throw new Error(errorMsg);
                }
                return res.json();
            })
            .then((data) => {
                // Ensure only the latest request updates the DOM and state
                if (!data || requestId !== latestRequestId) {
                    return;
                }
                renderGrievanceRows(data.grievances);
                updatePagination(data);
                tbody.style.opacity = '1';
            })
            .catch((err) => {
                // Silently ignore aborted requests or stale responses
                if (err.name === 'AbortError' || requestId !== latestRequestId) {
                    return;
                }
                console.error('Failed to fetch filtered grievances:', err);
                showFilterError(err.message || 'An error occurred while filtering grievances. Please try again.');
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

    // Reset current page to 1 whenever filters or search keywords change
    function onFilterChange() {
        fetchFilteredGrievances(1);
    }

    // Intercept form submit to prevent full reload when JS is active
    filterForm.addEventListener('submit', (e) => {
        e.preventDefault();
        onFilterChange();
    });

    if (statusSelect) {
        statusSelect.addEventListener('change', onFilterChange);
    }
    if (prioritySelect) {
        prioritySelect.addEventListener('change', onFilterChange);
    }
    if (departmentSelect) {
        departmentSelect.addEventListener('change', onFilterChange);
    }
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(onFilterChange, 300);
        });
    }

    // Attach AJAX pagination navigation click handler
    if (paginationContainer) {
        paginationContainer.addEventListener('click', (e) => {
            const paginationBtn = e.target.closest('#pagination-prev, #pagination-next');
            if (paginationBtn) {
                if (paginationBtn.getAttribute('aria-disabled') === 'true' || !paginationBtn.dataset.page) {
                    e.preventDefault();
                    return;
                }
                e.preventDefault();
                const targetPage = parseInt(paginationBtn.dataset.page, 10);
                if (targetPage && targetPage !== currentPage) {
                    fetchFilteredGrievances(targetPage);
                }
            }
        });

        // Ensure keyboard spacebar key triggers pagination on focused anchor
        paginationContainer.addEventListener('keydown', (e) => {
            if (e.key === ' ' || e.key === 'Spacebar') {
                const target = e.target.closest('#pagination-prev, #pagination-next');
                if (target && target.getAttribute('aria-disabled') !== 'true' && target.dataset.page) {
                    e.preventDefault();
                    target.click();
                }
            }
        });
    }

    // Handle browser back and forward button navigation
    window.addEventListener('popstate', () => {
        const urlParams = new URLSearchParams(window.location.search);
        if (statusSelect) statusSelect.value = urlParams.get('status') || '';
        if (prioritySelect) prioritySelect.value = urlParams.get('priority') || '';
        if (departmentSelect) departmentSelect.value = urlParams.get('department') || '';
        if (searchInput) searchInput.value = urlParams.get('search') || '';
        const page = parseInt(urlParams.get('page'), 10) || 1;
        fetchFilteredGrievances(page, false);
    });
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

