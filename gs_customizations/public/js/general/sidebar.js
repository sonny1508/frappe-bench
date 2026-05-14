
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
			frappe.boot.user_info?.[email]?.fullname ||
			email;

		$item.find(".group-by-value").text(fullname);

	});

}

requestAnimationFrame(function render_loop() {
	idebar_user_to_fullname();
	requestAnimationFrame(render_loop);

});