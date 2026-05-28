/**
 * Simple Kanban Idle Auto-Refresh
 * Refreshes after 10 minutes of no activity
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
    
    function resetIdleTimer() {
        lastActivity = Date.now();
    }
    
    function checkIdle() {
        if (!isTaskKanbanView()) {
            resetIdleTimer();
            return;
        }
        
        const idleTime = Date.now() - lastActivity;
        const idleMinutes = Math.round(idleTime / 1000 / 60);
        
        console.log(`[Kanban Idle] Idle for ${idleMinutes} minutes`);
        
        if (idleTime >= IDLE_LIMIT_MS) {
            console.log('[Kanban Idle] 10 minutes reached - refreshing page');
            location.reload();
        }
    }
    
    ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'].forEach(event => {
        document.addEventListener(event, resetIdleTimer, { passive: true });
    });
    
    setInterval(checkIdle, CHECK_INTERVAL_MS);
    
    console.log('[Kanban Idle] Auto-refresh enabled for Task Kanban (10 min idle limit)');
})();