# Copyright (c) 2026, PinDyn and contributors
# For license information, please see license.txt

"""Job Completion sign-off public + desk APIs."""

from __future__ import annotations

import secrets
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_to_date, get_url, now_datetime


ALLOWED_STATUS_FOR_LINKS = "Awaiting Sign Off"
TOKEN_TTL_DAYS = 7
DEFAULT_MAX_USES = 5

TECHNICIAN_NAME_OPTIONS = [
	"Alfred Rantshi",
	"George Lerutla",
	"Given Mongwe",
	"Gift Mulovhedzi",
	"Jan Ngobeni",
	"Sidney Mathebula",
	"Other",
]


def _require_login():
	if frappe.session.user == "Guest":
		frappe.throw(_("Login required"), frappe.PermissionError)


def _get_active_token(job_completion: str, role: str):
	return frappe.db.get_value(
		"Job Signoff Token",
		{
			"job_completion": job_completion,
			"role": role,
			"status": "Active",
		},
		["name", "token", "short_link", "expires_on", "use_count", "max_uses"],
		as_dict=True,
	)


def _site_signoff_url(token: str) -> str:
	return get_url(f"/signoff?token={token}")


def _create_tinyurl(long_link: str, job_completion: str, role: str) -> tuple[str, str]:
	"""Create TinyURL doc; returns (tinyurl_name, short_link)."""
	if not frappe.db.exists("DocType", "TinyURL"):
		frappe.throw(
			_("frappe_tinyurl is not installed. Install and configure TinyURL Settings first.")
		)

	settings = frappe.get_single("TinyURL Settings")
	if not settings.get("domain") or not settings.get_password("api_key"):
		frappe.throw(
			_("TinyURL Settings are incomplete. Set Domain and API Key before generating links.")
		)

	alias = secrets.token_urlsafe(10).replace("-", "").replace("_", "")[:12].lower()
	# Ensure uniqueness locally
	while frappe.db.exists("TinyURL", {"alias": alias}):
		alias = secrets.token_urlsafe(10).replace("-", "").replace("_", "")[:12].lower()

	doc = frappe.get_doc(
		{
			"doctype": "TinyURL",
			"long_link": long_link,
			"alias": alias,
			"reference_doctype": "Job Completion",
			"reference_name": job_completion,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	if not doc.short_link:
		frappe.throw(_("TinyURL was created but short_link is empty. Check TinyURL Settings / API."))
	return doc.name, doc.short_link


def _store_short_link_on_job(job_completion: str, role: str, short_link: str):
	field = (
		"custom_technician_signoff_short_link"
		if role == "technician"
		else "custom_client_signoff_short_link"
	)
	if frappe.get_meta("Job Completion").has_field(field):
		frappe.db.set_value("Job Completion", job_completion, field, short_link, update_modified=False)


def _revoke_active_tokens(job_completion: str, role: str):
	names = frappe.get_all(
		"Job Signoff Token",
		filters={"job_completion": job_completion, "role": role, "status": "Active"},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value("Job Signoff Token", name, "status", "Revoked", update_modified=False)


@frappe.whitelist()
def generate_signoff_link(job_completion: str, role: str, regenerate: int = 0) -> dict[str, Any]:
	"""Desk: create/refresh a role-scoped sign-off short link."""
	_require_login()
	role = (role or "").strip().lower()
	if role not in ("technician", "client"):
		frappe.throw(_("Invalid role"))

	jc = frappe.get_doc("Job Completion", job_completion)
	jc.check_permission("write")

	if jc.status != ALLOWED_STATUS_FOR_LINKS:
		frappe.throw(
			_("Sign-off links can only be generated when status is {0}").format(
				ALLOWED_STATUS_FOR_LINKS
			)
		)

	existing = _get_active_token(job_completion, role)
	if existing and not int(regenerate or 0):
		return {
			"role": role,
			"short_link": existing.short_link,
			"expires_on": existing.expires_on,
			"token_name": existing.name,
		}

	if existing and int(regenerate or 0):
		_revoke_active_tokens(job_completion, role)

	raw_token = secrets.token_urlsafe(32)
	long_link = _site_signoff_url(raw_token)
	tiny_name, short_link = _create_tinyurl(long_link, job_completion, role)

	token_doc = frappe.get_doc(
		{
			"doctype": "Job Signoff Token",
			"job_completion": job_completion,
			"role": role,
			"status": "Active",
			"token": raw_token,
			"long_link": long_link,
			"tinyurl": tiny_name,
			"short_link": short_link,
			"expires_on": add_to_date(now_datetime(), days=TOKEN_TTL_DAYS),
			"max_uses": DEFAULT_MAX_USES,
			"use_count": 0,
		}
	)
	token_doc.insert(ignore_permissions=True)
	_store_short_link_on_job(job_completion, role, short_link)
	frappe.db.commit()

	return {
		"role": role,
		"short_link": short_link,
		"expires_on": token_doc.expires_on,
		"token_name": token_doc.name,
	}


def _load_token_or_throw(token: str):
	token = (token or "").strip()
	if not token:
		frappe.throw(_("Missing token"), frappe.AuthenticationError)

	row = frappe.db.get_value(
		"Job Signoff Token",
		{"token": token},
		[
			"name",
			"token",
			"job_completion",
			"role",
			"status",
			"expires_on",
			"max_uses",
			"use_count",
			"signed_on",
			"short_link",
		],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Invalid or unknown sign-off link"), frappe.AuthenticationError)

	if row.status == "Revoked":
		frappe.throw(_("This sign-off link has been revoked"), frappe.AuthenticationError)
	if row.status == "Used" or row.signed_on:
		frappe.throw(_("This sign-off link has already been used"), frappe.AuthenticationError)
	if row.expires_on and now_datetime() > row.expires_on:
		frappe.db.set_value("Job Signoff Token", row.name, "status", "Expired", update_modified=False)
		frappe.throw(_("This sign-off link has expired"), frappe.AuthenticationError)
	if row.max_uses and row.use_count >= row.max_uses:
		frappe.throw(_("This sign-off link has reached its use limit"), frappe.AuthenticationError)

	jc_status = frappe.db.get_value("Job Completion", row.job_completion, "status")
	if jc_status not in (ALLOWED_STATUS_FOR_LINKS, "Completed"):
		frappe.throw(
			_("This job is not ready for sign-off (status: {0})").format(jc_status or "Unknown")
		)

	return row


def _public_summary(jc) -> dict[str, Any]:
	return {
		"name": jc.name,
		"status": jc.status,
		"customer_name": jc.customer_name or jc.customer,
		"installation_address": jc.installation_address,
		"date_installed": jc.date_installed,
		"external_quote_ref": jc.external_quote_ref,
		"contact_number": jc.contact_number,
	}


def _snag_rows(jc) -> list[dict[str, Any]]:
	rows = []
	for row in jc.get("snag_list") or []:
		rows.append(
			{
				"name": row.name,
				"idx": row.idx,
				"description": row.description,
				"location": row.location,
				"priority": row.priority,
				"status": row.status,
				"target_completion": row.target_completion,
				"photo": row.photo,
			}
		)
	return rows


def _save_data_url_file(data_url: str, filename: str, linked_doctype: str, linked_name: str) -> str:
	"""Save a data: URL as a File and return file_url."""
	import base64

	if not data_url or not str(data_url).startswith("data:"):
		frappe.throw(_("Invalid image data"))

	header, b64data = data_url.split(",", 1)
	content = base64.b64decode(b64data)
	ext = "png"
	if "jpeg" in header or "jpg" in header:
		ext = "jpg"
	elif "webp" in header:
		ext = "webp"

	from frappe.utils.file_manager import save_file

	if not filename.endswith(f".{ext}"):
		filename = f"{filename}.{ext}"

	file_doc = save_file(
		filename,
		content,
		linked_doctype,
		linked_name,
		is_private=1,
		df="photo",
	)
	return file_doc.file_url


@frappe.whitelist(allow_guest=True)
def get_signoff_payload(token: str) -> dict[str, Any]:
	"""Public: role-scoped read payload for /signoff page."""
	row = _load_token_or_throw(token)
	jc = frappe.get_doc("Job Completion", row.job_completion)

	payload = {
		"role": row.role,
		"summary": _public_summary(jc),
		"already_signed": {
			"technician": bool(jc.technician_signature),
			"client": bool(jc.client_signature),
		},
	}

	if row.role == "technician":
		payload["technician_name"] = jc.technician_name
		payload["technician_name_options"] = TECHNICIAN_NAME_OPTIONS
		payload["snags"] = _snag_rows(jc)
	elif row.role == "client":
		payload["client_name"] = jc.client_name
		payload["sign_off_comments"] = jc.sign_off_comments
		# Read-only checklist summary for context (no edit)
		checks = []
		for df in frappe.get_meta("Job Completion").fields:
			if df.fieldname and df.fieldname.startswith("check_") and df.fieldtype == "Select":
				val = jc.get(df.fieldname)
				if val:
					checks.append({"label": df.label, "value": val})
		payload["checklist_summary"] = checks

	return payload


def _maybe_complete_job(jc_name: str):
	jc = frappe.get_doc("Job Completion", jc_name)
	if jc.technician_signature and jc.client_signature and jc.status == ALLOWED_STATUS_FOR_LINKS:
		jc.status = "Completed"
		jc.flags.ignore_permissions = True
		jc.save()


@frappe.whitelist(allow_guest=True)
def submit_signoff(token: str, data: str | dict | None = None) -> dict[str, Any]:
	"""Public: submit role-allowed fields + signature."""
	row = _load_token_or_throw(token)

	if isinstance(data, str):
		data = frappe.parse_json(data) or {}
	data = data or {}

	jc = frappe.get_doc("Job Completion", row.job_completion)
	jc.flags.ignore_permissions = True

	if row.role == "technician":
		tech_name = (data.get("technician_name") or "").strip()
		signature = data.get("technician_signature")
		if not tech_name:
			frappe.throw(_("Technician name is required"))
		if not signature:
			frappe.throw(_("Technician signature is required"))

		jc.technician_name = tech_name
		jc.technician_signature = signature

		# Mark selected snags Resolved + optional photos
		resolved_names = data.get("resolved_snags") or []
		if isinstance(resolved_names, str):
			resolved_names = frappe.parse_json(resolved_names) or []
		resolved_set = set(resolved_names)

		snag_photos = data.get("snag_photos") or {}
		if isinstance(snag_photos, str):
			snag_photos = frappe.parse_json(snag_photos) or {}

		for snag in jc.get("snag_list") or []:
			if snag.name in resolved_set and snag.status != "Resolved":
				snag.status = "Resolved"
				if not snag.resolved_date:
					snag.resolved_date = now_datetime().date()

			photo_data = snag_photos.get(snag.name)
			if photo_data:
				snag.photo = _save_data_url_file(
					photo_data,
					f"snag-{jc.name}-{snag.idx}",
					"Job Completion",
					jc.name,
				)

		if frappe.get_meta("Job Completion").has_field("custom_technician_signed_on"):
			jc.custom_technician_signed_on = now_datetime()

	elif row.role == "client":
		client_name = (data.get("client_name") or "").strip()
		signature = data.get("client_signature")
		if not client_name:
			frappe.throw(_("Client name is required"))
		if not signature:
			frappe.throw(_("Client signature is required"))

		jc.client_name = client_name
		jc.client_signature = signature
		comment = data.get("sign_off_comments")
		if comment is not None:
			jc.sign_off_comments = comment

		if frappe.get_meta("Job Completion").has_field("custom_client_signed_on"):
			jc.custom_client_signed_on = now_datetime()
	else:
		frappe.throw(_("Invalid role"))

	jc.save()

	frappe.db.set_value(
		"Job Signoff Token",
		row.name,
		{
			"status": "Used",
			"signed_on": now_datetime(),
			"last_used_on": now_datetime(),
			"use_count": (row.use_count or 0) + 1,
		},
		update_modified=False,
	)

	_maybe_complete_job(jc.name)
	frappe.db.commit()

	return {
		"ok": True,
		"job_completion": jc.name,
		"status": frappe.db.get_value("Job Completion", jc.name, "status"),
		"role": row.role,
	}


@frappe.whitelist()
def send_signoff_link(
	job_completion: str,
	role: str,
	channel: str = "email",
	recipient: str | None = None,
) -> dict[str, Any]:
	"""Desk: send short link via email or WhatsApp."""
	_require_login()
	role = (role or "").strip().lower()
	channel = (channel or "email").strip().lower()

	link_info = generate_signoff_link(job_completion, role, regenerate=0)
	short_link = link_info.get("short_link")
	if not short_link:
		frappe.throw(_("No short link available"))

	jc = frappe.get_doc("Job Completion", job_completion)
	label = "Technician" if role == "technician" else "Client"

	if channel == "email":
		email = (recipient or jc.email_address or "").strip()
		if not email:
			frappe.throw(_("No email address available. Pass recipient or set Email Address on the Job Completion."))
		subject = _("PG Aluminium — {0} sign-off for {1}").format(label, jc.name)
		message = _(
			"<p>Please complete the {0} sign-off for job <b>{1}</b>.</p>"
			"<p><a href=\"{2}\">{2}</a></p>"
			"<p>This link expires in {3} days.</p>"
		).format(label.lower(), jc.name, short_link, TOKEN_TTL_DAYS)
		frappe.sendmail(
			recipients=[email],
			subject=subject,
			message=message,
			reference_doctype="Job Completion",
			reference_name=jc.name,
		)
		return {"ok": True, "channel": "email", "recipient": email, "short_link": short_link}

	if channel == "whatsapp":
		phone = (recipient or jc.contact_number or "").strip()
		if not phone:
			frappe.throw(_("No phone number available. Pass recipient or set Contact Number on the Job Completion."))
		# Normalize SA-style numbers lightly
		digits = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
		text = _(
			"PG Aluminium — please complete the {0} sign-off for job {1}: {2}"
		).format(label.lower(), jc.name, short_link)

		if frappe.db.exists("DocType", "WhatsApp Message"):
			msg = frappe.get_doc(
				{
					"doctype": "WhatsApp Message",
					"to": digits,
					"type": "Outgoing",
					"message_type": "Text",
					"message": text,
				}
			)
			msg.flags.ignore_permissions = True
			msg.insert()
			return {
				"ok": True,
				"channel": "whatsapp",
				"recipient": digits,
				"short_link": short_link,
				"whatsapp_message": msg.name,
			}

		frappe.throw(_("WhatsApp Message doctype not available on this site"))

	frappe.throw(_("Unsupported channel. Use email or whatsapp."))
