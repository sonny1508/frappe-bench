import json
import frappe
from frappe import _

TASK_PRIORITY_ORDER = {
    "Overdue": 0,
    "Urgent": 1,
    "High": 2,
    "Medium": 3,
    "Low": 4,
    "Support": 5
}

TASK_COLUMN_INDICATORS = {
    "Open": "cyan",
    "Working": "blue",
    "QA Pending": "purple",
    "QA Reviewing": "pink",
    "QA Feedback": "yellow",
    "QA Approved": "green",
    "Delivered": "cyan",
    "Client Feedback": "yellow",
    "Completed": "green",
    "Cancelled": "cyan",
    "Template": "grey",
    # add more as needed
}

def set_default_indicators(doc, method=None):
    if doc.reference_doctype != "Task":
        return
    
    for column in doc.columns:
        # Only set if indicator is not already set (preserve user customizations)
        if not column.indicator and column.column_name in TASK_COLUMN_INDICATORS:
            column.indicator = TASK_COLUMN_INDICATORS[column.column_name]


def get_task_column_orders(board, colnames):
    """Card order of each Task column, by priority, from a single query.

    Within a priority, cards keep get_all's order (most recently modified
    first), so a card that has just been moved goes to the top of its group.

    Without the user's permissions on purpose: the board keeps one order for
    everyone, and each person's own view of the tasks would give a different
    one, so every open by someone else would rewrite it.
    """
    filters = [[board.reference_doctype, board.field_name, "in", colnames]]

    # Only the board's first filter, usually its project. "Status is not
    # Closed" is left out, so a Closed column still gets an order.
    if board.filters and (board_filters := frappe.parse_json(board.filters)):
        filters.append(board_filters[0])

    tasks = frappe.get_all(
        board.reference_doctype,
        filters=filters,
        fields=["name", "priority", board.field_name],
    )

    by_column = {colname: [] for colname in colnames}
    for task in tasks:
        by_column[task.get(board.field_name)].append(task)

    return {
        colname: frappe.as_json([
            t.name for t in sorted(rows, key=lambda t: TASK_PRIORITY_ORDER.get(t.priority, 99))
        ])
        for colname, rows in by_column.items()
    }


def save_task_column_orders(board, colnames):
    """Re-sort Task columns, writing only the rows whose order changed.

    Straight to the rows instead of board.save(). The order is derived data that
    changes on every drop. A save fails the whole drop when anyone else saved the
    board while the Task was saving (TimestampMismatchError), and Kanban Board's
    on_change clears Task's doctype cache and everyone's user settings.
    """
    orders = get_task_column_orders(board, colnames)
    for column in board.columns:
        new_order = orders.get(column.column_name)
        if new_order is not None and column.order != new_order:
            column.order = new_order
            frappe.db.set_value(
                "Kanban Board Column", column.name, "order", new_order, update_modified=False
            )


@frappe.whitelist()
def update_order(board_name, order):
    """Override: called by the board every time it opens, with the card order on screen.

    For Task it never moves a card and never takes the order on screen: each
    column is re-sorted by priority, all from one query, and only the columns
    whose order changed are written. Opening a board used to cost a query per
    card, a query per column and a board save.
    """
    board = frappe.get_doc("Kanban Board", board_name)
    doctype = board.reference_doctype
    fieldname = board.field_name
    order_dict = json.loads(order)
    updated_cards = []

    if not frappe.has_permission(doctype, "write"):
        return board, updated_cards

    if doctype == "Task":
        # The screen was drawn from the database a moment ago, so a card in
        # the "wrong" column means someone moved it since. Moving it back would
        # undo their change.
        save_task_column_orders(board, list(order_dict))
        return board, updated_cards

    cards_on_screen = [card for cards in order_dict.values() for card in cards]
    current = dict(
        frappe.get_all(
            doctype,
            filters={"name": ["in", cards_on_screen]},
            fields=["name", fieldname],
            as_list=True,
        )
    ) if cards_on_screen else {}

    for col_name, cards in order_dict.items():
        # Update card's column field if changed
        for card in cards:
            if current.get(card) != col_name:
                frappe.set_value(doctype, card, fieldname, col_name)
                updated_cards.append(dict(name=card, column=col_name))

        for column in board.columns:
            if column.column_name == col_name:
                column.order = json.dumps(cards)

    return board.save(ignore_permissions=True), updated_cards


@frappe.whitelist()
def update_order_for_single_card(board_name, docname, from_colname, to_colname, old_index, new_index):
    """Override: Handle single card move but maintain priority order for Task"""
    board = frappe.get_doc("Kanban Board", board_name)
    doctype = board.reference_doctype
    fieldname = board.field_name

    frappe.has_permission(doctype, "write", throw=True)

    # Update the card's column field
    frappe.set_value(doctype, docname, fieldname, to_colname)

    if doctype == "Task":
        # Re-sort both columns by priority
        save_task_column_orders(board, list({from_colname, to_colname}))
        return board

    # Original behavior
    old_index = frappe.parse_json(old_index)
    new_index = frappe.parse_json(new_index)

    from_col_order, from_col_idx = get_kanban_column_order_and_index(board, from_colname)
    to_col_order, to_col_idx = get_kanban_column_order_and_index(board, to_colname)

    if from_colname == to_colname:
        from_col_order = to_col_order

    if from_col_order:
        to_col_order.insert(new_index, from_col_order.pop(old_index))

    board.columns[from_col_idx].order = frappe.as_json(from_col_order)
    board.columns[to_col_idx].order = frappe.as_json(to_col_order)

    board.save(ignore_permissions=True)
    return board


@frappe.whitelist()
def add_card(board_name, docname, colname):
    """Override: Add card and maintain priority order for Task"""
    board = frappe.get_doc("Kanban Board", board_name)
    doctype = board.reference_doctype

    frappe.has_permission(doctype, "write", throw=True)

    if doctype == "Task":
        # Re-sort the column by priority
        save_task_column_orders(board, [colname])
        return board

    # Original behavior
    col_order, col_idx = get_kanban_column_order_and_index(board, colname)
    col_order.insert(0, docname)
    board.columns[col_idx].order = frappe.as_json(col_order)

    return board.save(ignore_permissions=True)


def get_kanban_column_order_and_index(board, colname):
    """Helper function from original"""
    for i, col in enumerate(board.columns):
        if col.column_name == colname:
            col_order = frappe.parse_json(col.order)
            col_idx = i
            return col_order, col_idx
    return [], 0


@frappe.whitelist()
def resort_all_task_kanban_boards():
    """Utility: Re-sort all existing Task Kanban boards by priority"""
    boards = frappe.get_all("Kanban Board", filters={"reference_doctype": "Task"})
    
    for b in boards:
        board = frappe.get_doc("Kanban Board", b.name)
        orders = get_task_column_orders(board, [c.column_name for c in board.columns])
        for column in board.columns:
            column.order = orders[column.column_name]
        board.save(ignore_permissions=True)
    
    frappe.db.commit()
    return f"Re-sorted {len(boards)} Task Kanban board(s)"
