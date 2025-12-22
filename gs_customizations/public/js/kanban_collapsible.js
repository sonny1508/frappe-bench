(function () {
    const TARGET_DOCTYPE = "Task";

    function patch_kanban() {
        if (!frappe.views || !frappe.views.KanbanView) return false;
        const proto = frappe.views.KanbanView.prototype;
        if (proto._collapse_patched) return true;
        proto._collapse_patched = true;

        const original_render = proto.render;
        proto.render = function () {
            const result = original_render.apply(this, arguments);

            if (this.doctype === TARGET_DOCTYPE) {
                setTimeout(() => inject_buttons(), 100);
            }

            return result;
        };

        inject_css();
        return true;
    }

    function inject_buttons() {
        document.querySelectorAll(".kanban-card").forEach(card => {
            if (card.dataset.collapsePatched) return;
            card.dataset.collapsePatched = "true";

            // Create toggle button
            const $btn = document.createElement("button");
            $btn.className = "kanban-toggle-btn";
            $btn.title = "Toggle details";
            $btn.innerHTML = frappe.utils.icon("expand", "sm");

            // Helper to toggle state
            const toggle = () => {
                const expanded = card.classList.toggle("expanded");
                $btn.innerHTML = frappe.utils.icon(
                    expanded ? "collapse" : "expand",
                    "sm"
                );
            };

            // Button click
            $btn.addEventListener("click", (e) => {
                e.preventDefault();
                e.stopPropagation();
                toggle();
            });

            // Card click (but not on links)
            card.addEventListener("click", (e) => {
                // Let actual links work normally
                if (e.target.closest("a")) return;
                
                // Only expand, don't collapse on card click
                if (card.classList.contains("expanded")) return;
                
                e.preventDefault();
                e.stopPropagation();
                toggle();
            });

            card.appendChild($btn);
        });
    }

    function inject_css() {
        if (document.getElementById("kanban-collapse-style")) return;
        const style = document.createElement("style");
        style.id = "kanban-collapse-style";
        style.textContent = `
            .kanban-card {
                position: relative;
            }
            .kanban-card .kanban-card-doc {
                display: none !important;
            }
            .kanban-card.expanded .kanban-card-doc {
                display: block !important;
            }
            .kanban-toggle-btn {
                position: absolute;
                top: 6px;
                right: 12px;
                background: var(--bg-light-gray);
                border: none;
                border-radius: 3px;
                padding: 2px 4px;
                cursor: pointer;
                opacity: 0.5;
                z-index: 5;
            }
            .kanban-toggle-btn:hover {
                opacity: 1;
            }
        `;
        document.head.appendChild(style);
    }

    // Use MutationObserver to handle drag/drop and dynamic changes
    function setup_observer() {
        const observer = new MutationObserver(() => {
            // Only run if we're on Task kanban
            if (cur_list?.doctype !== TARGET_DOCTYPE) return;
            inject_buttons();
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }

    const interval = setInterval(() => {
        if (patch_kanban()) {
            clearInterval(interval);
            setup_observer();
        }
    }, 200);
})();