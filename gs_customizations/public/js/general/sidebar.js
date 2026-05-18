let sidebar_user_map = {};

frappe.call({
	method: "frappe.client.get_list",
	args: {
		doctype: "User",
		fields: ["name", "full_name"],
		// filters: {
		// 	enabled: 1
		// },
		limit_page_length: 200
	},
	callback(r) {

		(r.message || []).forEach(user => {
			sidebar_user_map[user.name] = user.full_name;
		});

	}
});

function sidebar_user_to_fullname() {

	$(".group-by-item").each(function () {

		let $item = $(this);

		let email = decodeURIComponent(
			$item.attr("data-value") || ""
		);

		if (!email.includes("@")) {
			return;
		}

		let fullname =
			sidebar_user_map[email] ||
			email;

		$item.find(".group-by-value").text(fullname);

	});

}

requestAnimationFrame(function render_loop() {
	sidebar_user_to_fullname();
	requestAnimationFrame(render_loop);

});