// Frappe v15 reads a route value as one [operator, value] pair. A field with several conditions,
// e.g. status: [["!=", "Completed"], ["!=", "Cancelled"]], either throws on value[0].startsWith or
// builds a broken filter. This is Frappe's method with that case added, so core stays unpatched.
frappe.views.ListView.prototype.parse_filters_from_route_options = function () {
    const filters = [];

    let params = new URLSearchParams(window.location.search);
    if (!params.toString() && frappe.route_options) {
        params = new Map(Object.entries(frappe.route_options));
    }

    params.forEach((value, field) => {
        let doctype = null;

        let value_array;
        if (
            Array.isArray(value) &&
            !Array.isArray(value[0]) &&
            value[0].startsWith("[") &&
            value[0].endsWith("]")
        ) {
            value_array = [];
            for (var i = 0; i < value.length; i++) {
                value_array.push(JSON.parse(value[i]));
            }
        } else if (typeof value === "string" && value.startsWith("[") && value.endsWith("]")) {
            value = JSON.parse(value);
        }

        // if `Child DocType.fieldname`
        if (field.includes(".")) {
            doctype = field.split(".")[0];
            field = field.split(".")[1];
        }

        // find the table in which the key exists
        // for example the filter could be {"item_code": "X"}
        // where item_code is in the child table.

        // we can search all tables for mapping the doctype
        if (!doctype) {
            doctype = frappe.meta.get_doctype_for_field(this.doctype, field);
        }

        if (doctype) {
            if (value_array) {
                for (var j = 0; j < value_array.length; j++) {
                    if (Array.isArray(value_array[j])) {
                        filters.push([doctype, field, value_array[j][0], value_array[j][1]]);
                    } else {
                        filters.push([doctype, field, "=", value_array[j]]);
                    }
                }
            } else if (Array.isArray(value) && Array.isArray(value[0])) {
                value.forEach((val) => {
                    filters.push([doctype, field, val[0], val[1]]);
                });
            } else if (Array.isArray(value)) {
                filters.push([doctype, field, value[0], value[1]]);
            } else {
                filters.push([doctype, field, "=", value]);
            }
        }
    });

    return filters;
};
