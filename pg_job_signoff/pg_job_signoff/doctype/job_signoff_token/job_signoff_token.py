# Copyright (c) 2026, PinDyn and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class JobSignoffToken(Document):
	def validate(self):
		allowed = ("technician", "client", "handover", "site_completion", "snag")
		if self.role not in allowed:
			frappe.throw("Link type must be handover, site completion, snag, technician, or client")
