// Copyright (c) 2026, NPM2 Solutions Srl and contributors
// For license information, please see license.txt

frappe.ui.form.on("Distribution Source", {
	refresh(frm) {
		// One-paste onboarding: the vendor sends an onboarding token (from the hub's
		// Worgify Distribution page); paste it here and the Source self-configures.
		frm.add_custom_button(__("Connect to Hub"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Connect to the Worgify hub"),
				fields: [
					{
						fieldname: "token",
						fieldtype: "Small Text",
						label: __("Onboarding token"),
						reqd: 1,
						description: __(
							"Paste the onboarding token your training provider gave you. It configures the hub URL, client id and shared secret automatically."
						),
					},
				],
				primary_action_label: __("Connect"),
				primary_action: ({ token }) => {
					frappe.call({
						method: "lms.worgify_federation.apply_onboarding_token",
						args: { token },
						freeze: true,
						freeze_message: __("Connecting to the hub…"),
						callback: (r) => {
							if (r.message) {
								frappe.show_alert({
									message: __("Connected to {0} as {1}", [
										r.message.hub_base_url,
										r.message.distribution_client,
									]),
									indicator: "green",
								});
								d.hide();
								frm.reload_doc();
							}
						},
					});
				},
			});
			d.show();
		});
	},
});
