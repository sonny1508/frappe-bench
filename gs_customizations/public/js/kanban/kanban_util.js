/**
 * Kanban Horizontal Drag Scroll
 * Enables click-and-drag horizontal scrolling.
 *
 * Fully delegated: no per-element setup, no init timing. Frappe caches page
 * containers in the DOM, so querySelector(".frappe-list .result") could grab a
 * stale page's element on first SPA navigation — resolving the scroller from
 * e.target at mousedown time avoids that entirely.
 */

(function () {
	function isKanbanView() {
		const route = frappe.get_route && frappe.get_route();
		return route
			&& route[0]?.toLowerCase() === "list"
			&& route[1]?.toLowerCase() === "task"
			&& route[2]?.toLowerCase() === "kanban";
	}

	let scroller = null;
	let startX = 0;
	let startLeft = 0;

	document.addEventListener("mousedown", e => {
		if (e.button !== 0 || !isKanbanView()) return;

		// Only drag on empty board/column space — ignore cards, column
		// headers (Sortable column reorder handle), and interactive elements
		if (e.target.closest(
			".kanban-card-wrapper, .kanban-column-header, .add-card, .new-card-area, a, button, input, textarea"
		)) return;

		const r = e.target.closest(".frappe-list .result");
		if (!r || !r.querySelector(".kanban")) return;

		// Ignore native scrollbar clicks on the scroll containers
		const t = e.target;
		if ((t === r || t.classList.contains("kanban-cards"))
			&& (e.offsetX >= t.clientWidth || e.offsetY >= t.clientHeight)) return;

		scroller = r;
		startX = e.pageX;
		startLeft = r.scrollLeft;
	});

	document.addEventListener("mousemove", e => {
		if (!scroller) return;
		scroller.scrollLeft = startLeft - (e.pageX - startX);
	});

	document.addEventListener("mouseup", () => {
		scroller = null;
	});
})();
