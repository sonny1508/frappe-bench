// hotfix for v15
const orig = frappe.views.ListView.prototype.parse_filters_from_route_options;

frappe.views.ListView.prototype.parse_filters_from_route_options = function () {
    if (frappe.route_options) {
        for (const key in frappe.route_options) {
            const v = frappe.route_options[key];
            if (Array.isArray(v) && Array.isArray(v[0])) {
                // leave it as-is; v16 parser can handle this shape
            }
        }
    }
    return orig.apply(this, arguments);
};
