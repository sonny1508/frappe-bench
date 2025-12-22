(function () {
    const TARGET_DOCTYPE = "Task";
    let appliedForBoard = null;

    function patch_kanban() {
        if (!frappe.views?.KanbanView) return false;
        const proto = frappe.views.KanbanView.prototype;
        if (proto._filter_patched) return true;
        proto._filter_patched = true;

        const original_render = proto.render;
        proto.render = function () {
            const result = original_render.apply(this, arguments);

            const boardName = cur_list?.board?.name;
            if (this.doctype === TARGET_DOCTYPE && boardName && appliedForBoard !== boardName) {
                appliedForBoard = boardName;
                setTimeout(apply_board_filters, 50);
            }

            return result;
        };

        return true;
    }

    function apply_board_filters() {
        const board = cur_list?.board;
        if (!board?.filters) return;

        const filters = typeof board.filters === "string"
            ? JSON.parse(board.filters)
            : board.filters;

        if (!filters?.length) return;

        cur_list.filter_area.clear();
        cur_list.filter_area.add(filters.map(f => [f[0], f[1], f[2], f[3]]));
    }

    const interval = setInterval(() => {
        if (patch_kanban()) clearInterval(interval);
    }, 200);
})();