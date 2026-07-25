frappe.ui.form.on("Job Completion", {
	refresh(frm) {
		if (frm.is_new()) return;

		const can_link = frm.doc.status === "Awaiting Sign Off";

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

		function generate(role, regenerate) {
			return frappe.call({
				method: "pg_job_signoff.api.signoff.generate_signoff_link",
				args: {
					job_completion: frm.doc.name,
					role: role,
					regenerate: regenerate ? 1 : 0,
				},
				freeze: true,
				freeze_message: __("Creating short link…"),
			}).then((r) => {
				const msg = r.message || {};
				const field =
					role === "technician"
						? "custom_technician_signoff_short_link"
						: "custom_client_signoff_short_link";
				if (frm.fields_dict[field]) {
					frm.set_value(field, msg.short_link);
				}
				frappe.show_alert({
					message: __("{0} short link ready", [role === "technician" ? "Technician" : "Client"]),
					indicator: "green",
				});
				return msg;
			});
		}

		function send(role, channel) {
			const recipient_field = channel === "email" ? "email_address" : "contact_number";
			const default_to = frm.doc[recipient_field] || "";

			const d = new frappe.ui.Dialog({
				title: __("Send {0} sign-off ({1})", [
					role === "technician" ? __("Technician") : __("Client"),
					channel,
				]),
				fields: [
					{
						fieldname: "recipient",
						fieldtype: "Data",
						label: channel === "email" ? __("Email") : __("WhatsApp number"),
						reqd: 1,
						default: default_to,
					},
				],
				primary_action_label: __("Send"),
				primary_action(values) {
					d.hide();
					frappe
						.call({
							method: "pg_job_signoff.api.signoff.send_signoff_link",
							args: {
								job_completion: frm.doc.name,
								role: role,
								channel: channel,
								recipient: values.recipient,
							},
							freeze: true,
						})
						.then(() => {
							frappe.show_alert({
								message: __("Sign-off link sent"),
								indicator: "green",
							});
							frm.reload_doc();
						});
				},
			});
			d.show();
		}

		if (can_link) {
			frm.add_custom_button(__("Generate Technician Link"), () => generate("technician", 0), __(
				"Sign-Off Links"
			));
			frm.add_custom_button(__("Generate Client Link"), () => generate("client", 0), __(
				"Sign-Off Links"
			));
			frm.add_custom_button(
				__("Regenerate Technician Link"),
				() => generate("technician", 1),
				__("Sign-Off Links")
			);
			frm.add_custom_button(
				__("Regenerate Client Link"),
				() => generate("client", 1),
				__("Sign-Off Links")
			);

			frm.add_custom_button(
				__("Copy Technician Short Link"),
				() => {
					const existing = frm.doc.custom_technician_signoff_short_link;
					if (existing) {
						copy_text(existing);
					} else {
						generate("technician", 0).then((msg) => copy_text(msg.short_link));
					}
				},
				__("Sign-Off Links")
			);
			frm.add_custom_button(
				__("Copy Client Short Link"),
				() => {
					const existing = frm.doc.custom_client_signoff_short_link;
					if (existing) {
						copy_text(existing);
					} else {
						generate("client", 0).then((msg) => copy_text(msg.short_link));
					}
				},
				__("Sign-Off Links")
			);

			frm.add_custom_button(
				__("Email Technician Link"),
				() => send("technician", "email"),
				__("Sign-Off Links")
			);
			frm.add_custom_button(
				__("Email Client Link"),
				() => send("client", "email"),
				__("Sign-Off Links")
			);
			frm.add_custom_button(
				__("WhatsApp Technician Link"),
				() => send("technician", "whatsapp"),
				__("Sign-Off Links")
			);
			frm.add_custom_button(
				__("WhatsApp Client Link"),
				() => send("client", "whatsapp"),
				__("Sign-Off Links")
			);
		} else if (frm.doc.custom_technician_signoff_short_link || frm.doc.custom_client_signoff_short_link) {
			if (frm.doc.custom_technician_signoff_short_link) {
				frm.add_custom_button(
					__("Copy Technician Short Link"),
					() => copy_text(frm.doc.custom_technician_signoff_short_link),
					__("Sign-Off Links")
				);
			}
			if (frm.doc.custom_client_signoff_short_link) {
				frm.add_custom_button(
					__("Copy Client Short Link"),
					() => copy_text(frm.doc.custom_client_signoff_short_link),
					__("Sign-Off Links")
				);
			}
		}
	},
});
