# Copyright (c) 2026, PinDyn and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class JobSignoffToken(Document):
	def validate(self):
		if self.role not in ("technician", "client"):
			frappe.throw("Role must be technician or client")
