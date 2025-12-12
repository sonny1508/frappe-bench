import json
import frappe
from frappe import _

TASK_PRIORITY_ORDER = {
    "Urgent": 1,
    "High": 2,
    "Medium": 3,
    "Low": 4,
    "Support": 5
}

def get_order_for_column(board, colname):
    """Override: Get card order sorted by priority for Task doctype"""
    filters = [[board.reference_doctype, board.field_name, "=", colname]]
    
    if board.filters:
        filters.append(frappe.parse_json(board.filters)[0])
    
    if board.reference_doctype == "Task":
        # Fetch with priority and modified fields
        tasks = frappe.get_list(
            board.reference_doctype,
            filters=filters,
            fields=["name", "priority", "modified"]
        )
        
        # Sort by priority first, then by modified ascending (oldest first within same priority)
        tasks.sort(key=lambda x: (
            TASK_PRIORITY_ORDER.get(x.get("priority"), 99),
            x.get("modified")
        ))
        
        return frappe.as_json([t.name for t in tasks])
    else:
        return frappe.as_json(
            frappe.get_list(board.reference_doctype, filters=filters, pluck="name")
        )


@frappe.whitelist()
def update_order(board_name, order):
    """Override: Save order but re-sort by priority for Task"""
    board = frappe.get_doc("Kanban Board", board_name)
    doctype = board.reference_doctype
    fieldname = board.field_name
    order_dict = json.loads(order)
    updated_cards = []

    if not frappe.has_permission(doctype, "write"):
        return board, updated_cards

    for col_name, cards in order_dict.items():
        # Update card's column field if changed
        for card in cards:
            column = frappe.get_value(doctype, {"name": card}, fieldname)
            if column != col_name:
                frappe.set_value(doctype, card, fieldname, col_name)
                updated_cards.append(dict(name=card, column=col_name))

        # Get the column and set order
        for column in board.columns:
            if column.column_name == col_name:
                if doctype == "Task":
                    # Force priority sorting instead of drag-drop order
                    column.order = get_order_for_column(board, col_name)
                else:
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
        for column in board.columns:
            if column.column_name in [from_colname, to_colname]:
                column.order = get_order_for_column(board, column.column_name)
    else:
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
        for column in board.columns:
            if column.column_name == colname:
                column.order = get_order_for_column(board, colname)
    else:
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
        for column in board.columns:
            column.order = get_order_for_column(board, column.column_name)
        board.save(ignore_permissions=True)
    
    frappe.db.commit()
    return f"Re-sorted {len(boards)} Task Kanban board(s)"