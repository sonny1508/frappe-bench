/**
 * Simple Kanban Idle Auto-Refresh
 * Reloads the page after 5 minutes of no activity
 * Only applies to Task DocType Kanban view
 */
(function() {
    "use strict";

    const IDLE_LIMIT_MS = 5 * 60 * 1000; // 5 minutes
    const CHECK_INTERVAL_MS = 60 * 1000;  // Check every 60 seconds

    let lastActivity = Date.now();

    function isTaskKanbanView() {
        if (typeof frappe === 'undefined' || !frappe.get_route) {
            return false;
        }
        const route = frappe.get_route();
        return route
            && route[0]?.toLowerCase() === "list"
            && route[1]?.toLowerCase() === "task"
            && route[2]?.toLowerCase() === "kanban";
    }

    function reloadIfIdle() {
        // Reloading without a connection would leave the browser's error page.
        if (navigator.onLine && Date.now() - lastActivity >= IDLE_LIMIT_MS && isTaskKanbanView()) {
            location.reload();
        }
    }

    // Timers stop while the computer sleeps or the browser freezes a background
    // tab, so nothing checks the idle time until the page wakes up. The first
    // mouse move back must reload an old page, not count as activity on it.
    function onActivity() {
        reloadIfIdle();
        // Just woken with the network not back yet: keep the idle time, so the
        // next event reloads.
        if (navigator.onLine) {
            lastActivity = Date.now();
        }
    }

    function checkIdle() {
        if (!isTaskKanbanView()) {
            lastActivity = Date.now();
            return;
        }
        reloadIfIdle();
    }

    ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'].forEach(event => {
        document.addEventListener(event, onActivity, { passive: true });
    });

    document.addEventListener('visibilitychange', reloadIfIdle);
    window.addEventListener('online', reloadIfIdle);

    setInterval(checkIdle, CHECK_INTERVAL_MS);
})();
