/**
 * Kanban Horizontal Drag Scroll
 * Enables click-and-drag horizontal scrolling
 */

(function () {
	function isKanbanView() {
		const route = frappe.get_route && frappe.get_route();
		return route
			&& route[0]?.toLowerCase() === "list"
			&& route[1]?.toLowerCase() === "task"
			&& route[2]?.toLowerCase() === "kanban";
	}

	let activeScroller = null;
	let startX = null;
	let startLeft = null;

	function enableDrag() {
		if (!isKanbanView()) return;

		const r = document.querySelector(".frappe-list .result");
		if (!r || r.dataset.dragScroll) return;

		r.dataset.dragScroll = 1;
		activeScroller = r;

		r.addEventListener("mousedown", e => {
			// Only drag on empty column space — ignore clicks on cards
			if (e.target.closest(".kanban-card")) return;
			startX = e.pageX;
			startLeft = r.scrollLeft;
		});
	}

	document.addEventListener("mousemove", e => {
		if (startX == null || !activeScroller) return;
		activeScroller.scrollLeft = startLeft - (e.pageX - startX);
	});

	document.addEventListener("mouseup", () => {
		startX = null;
	});

	// Fires on SPA navigation
	frappe.router.on("change", () => setTimeout(enableDrag, 500));

	// Fires on initial page load (direct URL / hard refresh)
	$(document).on("page-change", () => setTimeout(enableDrag, 500));
})();

