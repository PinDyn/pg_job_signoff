# Copyright (c) 2026, PinDyn and contributors
# Phase 2: thin PWA shell — payload is loaded client-side (supports offline queue).

import frappe
from frappe import _


no_cache = 1


def get_context(context):
	token = frappe.form_dict.get("token") or ""
	context.token = token
	context.brand = "PG Aluminium"
	context.no_cache = 1
	context.title = _("Job Sign-Off")
	context.pwa = True
	context.manifest_url = "/manifest.webmanifest"
	context.sw_url = "/pg-signoff-sw.js"

	# Optional warm payload for first paint; client will refresh via API
	context.payload = None
	context.role = None
	context.error = None

	if not token:
		context.error = _("Missing sign-off token.")
	else:
		try:
			from pg_job_signoff.api.signoff import get_signoff_payload

			payload = get_signoff_payload(token=token)
			context.payload = payload
			context.role = payload.get("role")
		except Exception as e:
			msg = str(e).strip()
			if msg.startswith("ValidationError:") or "<" in msg:
				msg = _("This sign-off link is invalid or expired.")
			context.error = msg or _("This sign-off link is invalid or expired.")

	# Serialize in Python — sandboxed Jinja cannot call frappe.as_json()
	context.boot_json = frappe.as_json(
		{
			"token": context.token,
			"brand": context.brand,
			"error": context.error,
			"role": context.role,
			"payload": context.payload,
		}
	)

	return context
