frappe.ui.form.on("Job Completion", {
	refresh(frm) {
		if (frm.is_new()) return;

		const forms = [
			{
				id: "handover",
				label: __("Handover Link"),
				field: "custom_handover_signoff_short_link",
				statuses: ["Awaiting Sign Off"],
			},
			{
				id: "site_completion",
				label: __("Site Completion Link"),
				field: "custom_site_completion_signoff_short_link",
				statuses: ["Draft", "Inspection", "Snag List", "Awaiting Sign Off"],
			},
			{
				id: "snag",
				label: __("Snag Link"),
				field: "custom_snag_signoff_short_link",
				statuses: ["Draft", "Inspection", "Snag List", "Awaiting Sign Off"],
			},
		];

		function copy_text(text) {
			if (!text) {
				frappe.msgprint(__("No short link yet. Generate the link first."));
				return;
			}
			if (navigator.clipboard && navigator.clipboard.writeText) {
				navigator.clipboard.writeText(text).then(() => {
					frappe.show_alert({ message: __("Short link copied"), indicator: "green" });
				});
			} else {
				frappe.msgprint(text);
			}
		}

		function remember_link(form, short_link) {
			if (short_link && frm.fields_dict[form.field]) {
				frm.set_value(form.field, short_link);
			}
		}

		function generate(form, regenerate) {
			return frappe.call({
				method: "pg_job_signoff.api.signoff.generate_signoff_link",
				args: {
					job_completion: frm.doc.name,
					form_type: form.id,
					regenerate: regenerate ? 1 : 0,
				},
				freeze: true,
				freeze_message: __("Creating short link…"),
			}).then((r) => {
				const msg = r.message || {};
				remember_link(form, msg.short_link);
				return msg;
			});
		}

		function on_button(dialog, fieldname, fn) {
			const control = dialog.fields_dict[fieldname];
			if (!control) return;
			const $btn = control.$input || (control.input && $(control.input));
			if ($btn) $btn.on("click", fn);
		}

		function open_link(form) {
			generate(form, 0).then((msg) => {
				const dialog = new frappe.ui.Dialog({
					title: form.label,
					fields: [
						{
							fieldname: "short_link",
							fieldtype: "Small Text",
							label: __("Short link"),
							read_only: 1,
							default: msg.short_link || "",
						},
						{
							fieldname: "copy",
							fieldtype: "Button",
							label: __("Copy link"),
						},
						{
							fieldname: "recipient",
							fieldtype: "Data",
							label: __("Email or WhatsApp number"),
							default: frm.doc.email_address || frm.doc.contact_number || "",
						},
						{
							fieldname: "send_email",
							fieldtype: "Button",
							label: __("Send email"),
						},
						{
							fieldname: "send_whatsapp",
							fieldtype: "Button",
							label: __("Send WhatsApp"),
						},
						{
							fieldname: "regen",
							fieldtype: "Button",
							label: __("Regenerate link"),
						},
					],
				});

				function send(channel) {
					const recipient = dialog.get_value("recipient");
					if (!recipient) {
						frappe.msgprint(__("Enter an email or WhatsApp number"));
						return;
					}
					frappe.call({
						method: "pg_job_signoff.api.signoff.send_signoff_link",
						args: {
							job_completion: frm.doc.name,
							form_type: form.id,
							channel: channel,
							recipient: recipient,
						},
						freeze: true,
						callback(r) {
							if (!r.exc) {
								const sent = (r.message || {}).short_link;
								if (sent) dialog.set_value("short_link", sent);
								remember_link(form, sent);
								frappe.show_alert({ message: __("Link sent"), indicator: "green" });
							}
						},
					});
				}

				dialog.show();
				on_button(dialog, "copy", () => copy_text(dialog.get_value("short_link")));
				on_button(dialog, "send_email", () => send("email"));
				on_button(dialog, "send_whatsapp", () => send("whatsapp"));
				on_button(dialog, "regen", () => {
					generate(form, 1).then((fresh) => {
						dialog.set_value("short_link", fresh.short_link || "");
						frappe.show_alert({ message: __("New short link ready"), indicator: "green" });
					});
				});
			});
		}

		forms.forEach((form) => {
			if (form.statuses.includes(frm.doc.status)) {
				frm.add_custom_button(form.label, () => open_link(form), __("Sign-Off Links"));
			} else if (frm.doc[form.field]) {
				frm.add_custom_button(
					__("Copy {0}", [form.label]),
					() => copy_text(frm.doc[form.field]),
					__("Sign-Off Links")
				);
			}
		});
	},
});
