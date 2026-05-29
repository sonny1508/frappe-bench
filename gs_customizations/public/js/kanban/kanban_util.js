/**
 * Kanban Horizontal Drag Scroll
 * Enables click-and-drag horizontal scrolling
 */

(function () {
	function enableDrag() {
		const r = document.querySelector(".frappe-list .result");
		if (!r || r.dataset.dragScroll) return;

		r.dataset.dragScroll = 1;

		let x, left;

		r.onmousedown = e => {
			x = e.pageX;
			left = r.scrollLeft;
		};

		r.onmousemove = e => {
			if (x == null) return;
			r.scrollLeft = left - (e.pageX - x);
		};

		document.onmouseup = () => x = null;
	}

	frappe.router.on("change", () => setTimeout(enableDrag, 500));
})();

