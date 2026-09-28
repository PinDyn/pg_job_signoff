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
OPEN_STATUSES = ("Draft", "Inspection", "Snag List", "Awaiting Sign Off")
TOKEN_TTL_DAYS = 7
DEFAULT_MAX_USES = 5
LEGACY_ROLES = ("technician", "client")
FORM_TYPES = ("handover", "site_completion", "snag")
LINK_KINDS = LEGACY_ROLES + FORM_TYPES

YNA = ["Yes", "No", "N/A"]
YN = ["Yes", "No"]

SHORT_LINK_FIELDS = {
	"technician": "custom_technician_signoff_short_link",
	"client": "custom_client_signoff_short_link",
	"handover": "custom_handover_signoff_short_link",
	"site_completion": "custom_site_completion_signoff_short_link",
	"snag": "custom_snag_signoff_short_link",
}

FORM_TITLES = {
	"handover": "Project Completion & Client Handover",
	"site_completion": "Site Completion & Outstanding Works",
	"snag": "Defect / Snag Report & Resolution",
	"technician": "Technician sign-off",
	"client": "Client sign-off",
}

CHECKS = [
	("check_windows_doors", "All windows and doors have been installed in accordance with the approved quotation"),
	("check_sliding_doors", "Sliding and folding doors adjusted correctly and locks aligned"),
	("check_window_handles", "All windows and doors have been tested and are locking correctly"),
	("check_glass_aligned", "Glazing installed according to specification"),
	("check_glass_no_damage", "Glass free from cracks, chips or visible defects"),
	("check_gaskets_seals", "Gaskets, seals and drainage checked"),
	("check_silicone", "Silicone sealing completed neatly"),
	("check_frames_plumb", "Frames checked for plumb and level"),
	("check_door_handles", "All ironmongery, escutcheons and striker plates installed"),
	("check_v_catches", "All hardware tested and functioning correctly"),
	("check_sf19_rubber", "SF19 rubber installed where visible and applicable"),
	("check_area_cleaned", "Installation area has been cleaned and all debris removed"),
	("check_keys_handed", "Keys handed over to client"),
	("check_warranty_info", "Warranty and maintenance information provided"),
]

SITE_STATUS = [
	("site_substantially_complete", "Installation substantially complete"),
	("site_safe_occupation", "Installation safe for occupation"),
	("site_outstanding_remain", "Outstanding items remain"),
	("site_temp_protection", "Temporary protection installed where required"),
	("site_client_informed_outstanding", "Client informed of outstanding items"),
]

SITE_REASONS = [
	("reason_builder_not_ready", "Builder not ready"),
	("reason_access_restrictions", "Access restrictions"),
	("reason_plastering_painting", "Plastering / painting outstanding"),
	("reason_client_postponement", "Client requested postponement"),
	("reason_flooring_incomplete", "Flooring incomplete"),
	("reason_materials_unavailable", "Materials unavailable"),
	("reason_electrical_incomplete", "Electrical work incomplete"),
	("reason_manufacturing_delay", "Manufacturing delay"),
	("reason_ceiling_outstanding", "Ceiling installation outstanding"),
	("reason_glass_unavailable", "Glass unavailable"),
	("reason_waterproofing_outstanding", "Waterproofing outstanding"),
	("reason_weather", "Weather conditions"),
	("reason_other", "Other"),
]

TEMP_STATUS = [
	("temp_safe_occupation", "Installation safe for occupation"),
	("temp_products_secure", "Products secure"),
	("temp_weather_protection", "Temporary weather protection installed"),
	("temp_locks_operational", "Locks operational where applicable"),
	("temp_client_informed", "Client informed of temporary arrangements"),
]

DEFECTS = [
	("defect_window", "defect_loc_window", "Window"),
	("defect_door", "defect_loc_door", "Door"),
	("defect_frame", "defect_loc_frame", "Frame"),
	("defect_glass", "defect_loc_glass", "Glass"),
	("defect_hardware", "defect_loc_hardware", "Hardware"),
	("defect_sealant", "defect_loc_sealant", "Sealant"),
]

CAUSES = [
	("cause_manufacturing", "Manufacturing"),
	("cause_client_damage", "Client damage"),
	("cause_glass_supplier", "Glass supplier"),
	("cause_wear_tear", "Wear and tear"),
	("cause_install_transport", "Installation / transport damage"),
	("cause_unknown", "Unknown"),
]

QI_FIELDS = [
	("qi_repair_satisfactory", "Repair completed satisfactory"),
	("qi_product_operates", "Product operates correctly"),
	("qi_locks_adjusted", "Locks adjusted"),
	("qi_glass_inspected", "Glass inspected"),
	("qi_silicone_neat", "Silicone finished neatly"),
	("qi_area_cleaned", "Area cleaned"),
	("qi_client_satisfied", "Client satisfied"),
]

FORM_SIGNATURES = {
	"handover": [
		("client_signature", "client_name", "Client", True),
		("sales_signature", "sales_name", "PG Sales", False),
	],
	"site_completion": [
		("snag_ops_signature", "snag_ops_name", "Operations Manager", False),
		("snag_sales_signature", "snag_sales_name", "PG Sales", False),
		("snag_client_signature", "snag_client_name", "Client", True),
		("snag_technician_signature", "snag_technician_name", "PG Technician", False),
	],
	"snag": [
		("snag_ops_signature", "snag_ops_name", "Operations Manager", False),
		("snag_sales_signature", "snag_sales_name", "PG Sales", False),
		("snag_client_signature", "snag_client_name", "Client", False),
		("snag_technician_signature", "snag_technician_name", "PG Technician", False),
	],
}

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


def _normalize_kind(role: str | None = None, form_type: str | None = None) -> str:
	kind = (form_type or role or "").strip().lower().replace("-", "_").replace(" ", "_")
	aliases = {
		"sitecompletion": "site_completion",
		"signoff": "handover",
		"sign_off": "handover",
	}
	kind = aliases.get(kind, kind)
	if kind not in LINK_KINDS:
		frappe.throw(_("Invalid form. Use handover, site_completion, or snag."))
	return kind


def _assert_link_status(kind: str, status: str | None):
	if kind == "handover" or kind in LEGACY_ROLES:
		if status != ALLOWED_STATUS_FOR_LINKS:
			label = _("Handover links") if kind == "handover" else _("Sign-off links")
			frappe.throw(
				_("{0} can only be generated when status is {1}").format(label, ALLOWED_STATUS_FOR_LINKS)
			)
		return
	if status not in OPEN_STATUSES:
		frappe.throw(
			_("This link can only be sent while the job is open (status: {0})").format(status or "Unknown")
		)


def _get_active_token(job_completion: str, kind: str):
	return frappe.db.get_value(
		"Job Signoff Token",
		{
			"job_completion": job_completion,
			"role": kind,
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


def _store_short_link_on_job(job_completion: str, kind: str, short_link: str):
	field = SHORT_LINK_FIELDS.get(kind)
	if field and frappe.get_meta("Job Completion").has_field(field):
		frappe.db.set_value("Job Completion", job_completion, field, short_link, update_modified=False)


def _revoke_active_tokens(job_completion: str, kind: str):
	names = frappe.get_all(
		"Job Signoff Token",
		filters={"job_completion": job_completion, "role": kind, "status": "Active"},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value("Job Signoff Token", name, "status", "Revoked", update_modified=False)


@frappe.whitelist()
def generate_signoff_link(
	job_completion: str,
	role: str | None = None,
	regenerate: int = 0,
	form_type: str | None = None,
) -> dict[str, Any]:
	"""Desk: create/refresh a short link for one form (handover, site completion, or snag)."""
	_require_login()
	kind = _normalize_kind(role, form_type)

	jc = frappe.get_doc("Job Completion", job_completion)
	jc.check_permission("write")
	_assert_link_status(kind, jc.status)

	existing = _get_active_token(job_completion, kind)
	if existing and not int(regenerate or 0):
		return {
			"role": kind,
			"form_type": kind if kind in FORM_TYPES else None,
			"title": FORM_TITLES.get(kind),
			"short_link": existing.short_link,
			"expires_on": existing.expires_on,
			"token_name": existing.name,
		}

	if existing and int(regenerate or 0):
		_revoke_active_tokens(job_completion, kind)

	raw_token = secrets.token_urlsafe(32)
	long_link = _site_signoff_url(raw_token)
	tiny_name, short_link = _create_tinyurl(long_link, job_completion, kind)

	token_doc = frappe.get_doc(
		{
			"doctype": "Job Signoff Token",
			"job_completion": job_completion,
			"role": kind,
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
	_store_short_link_on_job(job_completion, kind, short_link)
	frappe.db.commit()

	return {
		"role": kind,
		"form_type": kind if kind in FORM_TYPES else None,
		"title": FORM_TITLES.get(kind),
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

	kind = row.role
	jc_status = frappe.db.get_value("Job Completion", row.job_completion, "status")
	if kind == "handover":
		if jc_status != ALLOWED_STATUS_FOR_LINKS:
			frappe.throw(
				_("This handover link is not available (status: {0})").format(jc_status or "Unknown")
			)
	elif kind in ("site_completion", "snag"):
		if jc_status not in OPEN_STATUSES:
			frappe.throw(
				_("This link is not available (status: {0})").format(jc_status or "Unknown")
			)
	elif jc_status not in (ALLOWED_STATUS_FOR_LINKS, "Completed"):
		frappe.throw(
			_("This job is not ready for sign-off (status: {0})").format(jc_status or "Unknown")
		)

	return row


def _public_summary(jc) -> dict[str, Any]:
	"""Read-only job header fields — mirrors the Job Completion print form."""
	meta = frappe.get_meta(jc.doctype)

	def first(*names: str):
		for name in names:
			if meta.has_field(name):
				val = jc.get(name)
				if val not in (None, ""):
					return val
		return None

	return {
		"name": jc.name,
		"status": jc.status,
		"customer_name": jc.customer_name or jc.customer,
		"contact_number": jc.contact_number,
		"email_address": first("email_address"),
		"installation_address": jc.installation_address,
		"external_quote_ref": jc.external_quote_ref,
		"date_installed": jc.date_installed,
		"technician_name": first("technician_name"),
		"sales_consultant": first("sales_consultant", "sales_rep", "sales_name"),
		"installation_team": first("installation_team", "installer"),
		"return_visit_date": first("return_visit_date", "snag_date"),
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


SITE_ROW = "Site outstanding item"
DEFECT_ROW = "Defect description"
PART_ROW = "Replacement part"
WARRANTY_CHARGE = ["Warranty", "Charge", "N/A"]
REPORTED_BY = ["Client", "Technician", "Sales"]


def _field_value(jc, fieldname: str):
	val = jc.get(fieldname)
	if val in (None, ""):
		return ""
	if hasattr(val, "isoformat"):
		return str(val)[:10]
	return val


def _select_field(jc, fieldname, label, options, required=False, layout="row"):
	return {
		"type": "select",
		"fieldname": fieldname,
		"label": label,
		"options": options,
		"value": _field_value(jc, fieldname),
		"required": required,
		"layout": layout,
	}


def _text_field(jc, fieldname, label, type_="text", required=False):
	return {
		"type": type_,
		"fieldname": fieldname,
		"label": label,
		"value": _field_value(jc, fieldname),
		"required": required,
	}


def _check_fields(jc, pairs):
	return [
		{
			"type": "check",
			"fieldname": fieldname,
			"label": label,
			"value": 1 if jc.get(fieldname) else 0,
		}
		for fieldname, label in pairs
	]


def _numbered_checks(jc, start=1):
	fields = []
	number = start
	for fieldname, label in CHECKS:
		fields.append(_select_field(jc, fieldname, f"{number}. {label}", YNA))
		number += 1
	return fields


def _tech_field(jc, label):
	return _select_field(jc, "technician_name", label, TECHNICIAN_NAME_OPTIONS, required=True, layout="stack")


def _signature_name(jc, name_field: str) -> str:
	current = jc.get(name_field) or ""
	if current:
		return current
	if name_field in ("client_name", "snag_client_name"):
		return jc.get("client_name") or jc.get("snag_client_name") or ""
	if name_field in ("sales_name", "snag_sales_name"):
		return jc.get("snag_sales_name") or jc.get("sales_name") or jc.get("sales_consultant") or ""
	if name_field == "snag_technician_name":
		return jc.get("snag_technician_name") or jc.get("technician_name") or ""
	return ""


def _signature_section(jc, kind: str) -> dict[str, Any]:
	pads = []
	for sig_field, name_field, label, required in FORM_SIGNATURES[kind]:
		pads.append(
			{
				"fieldname": sig_field,
				"name_field": name_field,
				"label": label,
				"required": required,
				"name_value": _signature_name(jc, name_field),
			}
		)
	return {"type": "signatures", "title": "Signatures", "pads": pads}


def _rows_for_marker(jc, marker: str, mapper) -> list[dict[str, Any]]:
	rows = []
	for row in jc.get("snag_list") or []:
		if (row.resolution_notes or "") == marker:
			rows.append(mapper(row))
	return rows


def _handover_sections(jc) -> list[dict[str, Any]]:
	return [
		{"type": "fields", "title": "Technician", "fields": [_tech_field(jc, "Technician")]},
		{
			"type": "fields",
			"title": "Installation quality checks",
			"fields": _numbered_checks(jc, 1),
		},
		{
			"type": "fields",
			"title": "Comments",
			"fields": [_text_field(jc, "sign_off_comments", "Comments", "textarea")],
		},
		_signature_section(jc, "handover"),
	]


def _site_sections(jc) -> list[dict[str, Any]]:
	outstanding = _rows_for_marker(
		jc,
		SITE_ROW,
		lambda row: {
			"description": row.description or "",
			"location": row.location or "",
			"target_completion": str(row.target_completion)[:10] if row.target_completion else "",
		},
	)
	while len(outstanding) < 4:
		outstanding.append({"description": "", "location": "", "target_completion": ""})

	final_checks = [_select_field(jc, "custom_outstanding_works_completed", "1. Outstanding works completed", YN)]
	final_checks.extend(_numbered_checks(jc, 2))

	return [
		{
			"type": "fields",
			"title": "Visit",
			"fields": [
				_text_field(jc, "return_visit_date", "Return visit date", "date"),
				_text_field(jc, "sales_consultant", "Sales consultant"),
				_text_field(jc, "installation_team", "Installation team"),
				_tech_field(jc, "Technician completing works"),
			],
		},
		{"type": "fields", "title": "Initial site sign-off status", "fields": [_select_field(jc, fn, label, YN) for fn, label in SITE_STATUS]},
		{
			"type": "fields",
			"title": "Reason installation could not be completed",
			"layout": "grid",
			"fields": _check_fields(jc, SITE_REASONS) + [_text_field(jc, "reason_details", "Details", "textarea")],
		},
		{
			"type": "lines",
			"title": "Outstanding items",
			"fieldname": "outstanding_items",
			"columns": [
				{"fieldname": "description", "label": "Description", "type": "text"},
				{"fieldname": "location", "label": "Location", "type": "text"},
				{"fieldname": "target_completion", "label": "Target completion", "type": "date"},
			],
			"rows": outstanding,
		},
		{
			"type": "fields",
			"title": "Temporary condition of installation",
			"fields": [_select_field(jc, fn, label, YN) for fn, label in TEMP_STATUS]
			+ [_text_field(jc, "temp_notes", "Notes", "textarea")],
		},
		{"type": "fields", "title": "Quality inspection after repair", "fields": final_checks},
		{
			"type": "note",
			"title": "Client acceptance",
			"text": (
				"I confirm that all previously outstanding works listed on this document have now been "
				"completed to my satisfaction. I acknowledge that the installation has now been fully "
				"completed and handed over."
			),
		},
		{
			"type": "fields",
			"title": "Final comments",
			"fields": [_text_field(jc, "sign_off_comments", "Final comments", "textarea")],
		},
		_signature_section(jc, "site_completion"),
	]


def _snag_sections(jc) -> list[dict[str, Any]]:
	defect = ""
	for row in jc.get("snag_list") or []:
		if (row.resolution_notes or "") == DEFECT_ROW:
			defect = row.description or ""
			break
	parts = _rows_for_marker(
		jc,
		PART_ROW,
		lambda row: {
			"item": row.description or "",
			"quantity": row.quantity or "",
			"warranty_or_charge": row.warranty_or_charge or "",
			"invoice_value": row.invoice_value or "",
		},
	)
	while len(parts) < 2:
		parts.append({"item": "", "quantity": "", "warranty_or_charge": "", "invoice_value": ""})

	issue_fields = []
	for flag, loc, label in DEFECTS:
		issue_fields.append(
			{"type": "check", "fieldname": flag, "label": label, "value": 1 if jc.get(flag) else 0}
		)
		issue_fields.append(_text_field(jc, loc, f"{label} — location of defect"))

	return [
		{
			"type": "fields",
			"title": "Report",
			"fields": [
				_text_field(jc, "snag_date", "Date reported", "date"),
				_text_field(jc, "sales_consultant", "Sales consultant"),
				_text_field(jc, "installation_team", "Installation team"),
				_tech_field(jc, "Technician attending"),
			],
		},
		{"type": "fields", "title": "Issue identified", "fields": issue_fields},
		{
			"type": "fields",
			"title": "Defect",
			"fields": [
				{
					"type": "textarea",
					"fieldname": "defect_description",
					"label": "Detailed description of the defect",
					"value": defect,
				},
				_select_field(jc, "defect_reported_by", "Defect reported by", REPORTED_BY, layout="stack"),
			],
		},
		{
			"type": "fields",
			"title": "Cause of defect",
			"layout": "grid",
			"fields": _check_fields(jc, CAUSES),
		},
		{
			"type": "fields",
			"title": "Corrective action",
			"fields": [_text_field(jc, "corrective_action", "Corrective action", "textarea")],
		},
		{
			"type": "lines",
			"title": "Replacement parts",
			"fieldname": "replacement_parts",
			"columns": [
				{"fieldname": "item", "label": "Item", "type": "text"},
				{"fieldname": "quantity", "label": "Quantity", "type": "text"},
				{
					"fieldname": "warranty_or_charge",
					"label": "Warranty / Charge",
					"type": "select",
					"options": WARRANTY_CHARGE,
				},
				{"fieldname": "invoice_value", "label": "Invoice value", "type": "number"},
			],
			"rows": parts,
		},
		{
			"type": "fields",
			"title": "Additional hours",
			"fields": [
				_text_field(jc, "additional_labour_hours", "Additional labour per hour", "number"),
				_text_field(jc, "additional_km", "Additional km's to site", "number"),
			],
		},
		{
			"type": "fields",
			"title": "Warranty information",
			"fields": [
				_select_field(jc, "warranty_covered", "Covered under warranty", YN),
				_text_field(jc, "warranty_covered_reason", "Covered — reason", "textarea"),
				_select_field(jc, "warranty_not_covered", "Not covered under warranty", YN),
				_text_field(jc, "warranty_not_covered_reason", "Not covered — reason", "textarea"),
				_text_field(jc, "stock_loss_value", "Stock loss value", "number"),
				_text_field(jc, "warranty_invoice_number", "Invoice number"),
			],
		},
		{
			"type": "fields",
			"title": "Quality inspection after repair",
			"fields": [_select_field(jc, fn, label, YN) for fn, label in QI_FIELDS],
		},
		{
			"type": "fields",
			"title": "Outstanding items",
			"fields": [_text_field(jc, "outstanding_items_notes", "Outstanding items", "textarea")],
		},
		_signature_section(jc, "snag"),
	]


def _form_sections(jc, kind: str) -> list[dict[str, Any]]:
	if kind == "handover":
		return _handover_sections(jc)
	if kind == "site_completion":
		return _site_sections(jc)
	return _snag_sections(jc)


@frappe.whitelist(allow_guest=True)
def get_signoff_payload(token: str) -> dict[str, Any]:
	"""Public: read payload for /signoff page."""
	row = _load_token_or_throw(token)
	jc = frappe.get_doc("Job Completion", row.job_completion)
	kind = row.role

	payload = {
		"role": kind,
		"form_type": kind if kind in FORM_TYPES else None,
		"title": FORM_TITLES.get(kind, "Job sign-off"),
		"summary": _public_summary(jc),
		"already_signed": {
			"technician": bool(jc.technician_signature),
			"client": bool(jc.client_signature),
		},
	}

	if kind in FORM_TYPES:
		payload["sections"] = _form_sections(jc, kind)
		return payload

	if kind == "technician":
		payload["technician_name"] = jc.technician_name
		payload["technician_name_options"] = TECHNICIAN_NAME_OPTIONS
		payload["snags"] = _snag_rows(jc)
	elif kind == "client":
		payload["client_name"] = jc.client_name
		payload["sign_off_comments"] = jc.sign_off_comments
		checks = []
		for df in frappe.get_meta("Job Completion").fields:
			if df.fieldname and df.fieldname.startswith("check_") and df.fieldtype == "Select":
				val = jc.get(df.fieldname)
				if val:
					checks.append({"label": df.label, "value": val})
		payload["checklist_summary"] = checks

	return payload


def _maybe_complete_job(jc_name: str, kind: str):
	jc = frappe.get_doc("Job Completion", jc_name)
	complete = False
	if kind == "handover" and jc.client_signature and jc.status == ALLOWED_STATUS_FOR_LINKS:
		complete = True
	elif kind in LEGACY_ROLES and jc.technician_signature and jc.client_signature and jc.status == ALLOWED_STATUS_FOR_LINKS:
		complete = True
	if not complete:
		return
	jc.status = "Completed"
	jc.flags.ignore_permissions = True
	jc.save()


def _as_dict(value) -> dict:
	if isinstance(value, str):
		value = frappe.parse_json(value) or {}
	return value or {}


def _as_list(value) -> list:
	if isinstance(value, str):
		value = frappe.parse_json(value) or []
	return value or []


def _set_text(jc, field: str, value, limit: int = 8000):
	if not jc.meta.has_field(field):
		return
	jc.set(field, ("" if value is None else str(value))[:limit])


def _set_select(jc, field: str, value, options: list[str]):
	if not value or not jc.meta.has_field(field):
		return
	if value not in options:
		frappe.throw(_("{0} is not a valid choice for {1}").format(value, field))
	jc.set(field, value)


def _set_check(jc, field: str, value):
	if not jc.meta.has_field(field):
		return
	jc.set(field, 1 if value in (1, True, "1", "true", "True", "Yes", "on") else 0)


def _set_date(jc, field: str, value):
	if not jc.meta.has_field(field):
		return
	jc.set(field, str(value)[:10] if value else None)


def _set_number(jc, field: str, value):
	if not jc.meta.has_field(field):
		return
	if value in (None, ""):
		jc.set(field, 0)
		return
	try:
		jc.set(field, float(value))
	except (TypeError, ValueError):
		frappe.throw(_("Enter a number for {0}").format(field))


def _set_signature(jc, field: str, value, required: bool, label: str):
	if not value:
		if required:
			frappe.throw(_("{0} signature is required").format(label))
		return
	if not str(value).startswith("data:image") or len(str(value)) > 1_500_000:
		frappe.throw(_("Invalid {0} signature").format(label))
	if jc.meta.has_field(field):
		jc.set(field, value)


def _rewrite_marked_rows(jc, marker: str, new_rows: list[dict[str, Any]]):
	kept = []
	for row in jc.get("snag_list") or []:
		if (row.resolution_notes or "") == marker:
			continue
		kept.append(
			{
				"description": row.description,
				"location": row.location,
				"target_completion": row.target_completion,
				"quantity": row.quantity,
				"warranty_or_charge": row.warranty_or_charge,
				"photo": row.photo,
				"priority": row.priority or "Medium",
				"assigned_to": row.assigned_to,
				"status": row.status or "Open",
				"products_replaced": row.products_replaced,
				"invoice_value": row.invoice_value,
				"resolved_date": row.resolved_date,
				"resolution_notes": row.resolution_notes,
			}
		)
	jc.set("snag_list", [])
	for row in kept + new_rows:
		clean = {key: val for key, val in row.items() if val not in (None, "")}
		if clean.get("description") or clean.get("location"):
			jc.append("snag_list", clean)


def _submit_form(jc, kind: str, data: dict):
	fields = _as_dict(data.get("fields"))
	lines = _as_dict(data.get("lines"))
	signatures = _as_dict(data.get("signatures"))

	tech = (fields.get("technician_name") or "").strip()
	if tech not in TECHNICIAN_NAME_OPTIONS:
		frappe.throw(_("Select the technician"))
	jc.technician_name = tech

	for fieldname, _label in CHECKS:
		_set_select(jc, fieldname, fields.get(fieldname), YNA)

	if kind == "handover":
		_set_text(jc, "sign_off_comments", fields.get("sign_off_comments"))
		_set_text(jc, "client_name", (fields.get("client_name") or "").strip(), 140)
		_set_text(jc, "sales_name", (fields.get("sales_name") or "").strip(), 140)
		if not (jc.client_name or "").strip():
			frappe.throw(_("Client name is required"))

	elif kind == "site_completion":
		_set_date(jc, "return_visit_date", fields.get("return_visit_date"))
		_set_text(jc, "sales_consultant", fields.get("sales_consultant"), 140)
		_set_text(jc, "installation_team", fields.get("installation_team"), 140)
		for fieldname, _label in SITE_STATUS + TEMP_STATUS:
			_set_select(jc, fieldname, fields.get(fieldname), YN)
		for fieldname, _label in SITE_REASONS:
			_set_check(jc, fieldname, fields.get(fieldname))
		_set_text(jc, "reason_details", fields.get("reason_details"))
		_set_text(jc, "temp_notes", fields.get("temp_notes"))
		_set_select(jc, "custom_outstanding_works_completed", fields.get("custom_outstanding_works_completed"), YN)
		_set_text(jc, "sign_off_comments", fields.get("sign_off_comments"))
		outstanding = []
		for item in _as_list(lines.get("outstanding_items"))[:30]:
			item = _as_dict(item)
			description = (item.get("description") or "").strip()
			location = (item.get("location") or "").strip()
			target = (item.get("target_completion") or "").strip()
			if not description and not location and not target:
				continue
			outstanding.append(
				{
					"description": description or location,
					"location": location,
					"target_completion": target[:10] if target else None,
					"status": "Open",
					"priority": "Medium",
					"resolution_notes": SITE_ROW,
				}
			)
		_rewrite_marked_rows(jc, SITE_ROW, outstanding)

	elif kind == "snag":
		_set_date(jc, "snag_date", fields.get("snag_date"))
		_set_text(jc, "sales_consultant", fields.get("sales_consultant"), 140)
		_set_text(jc, "installation_team", fields.get("installation_team"), 140)
		for flag, loc, _label in DEFECTS:
			_set_check(jc, flag, fields.get(flag))
			_set_text(jc, loc, fields.get(loc), 140)
		_set_select(jc, "defect_reported_by", fields.get("defect_reported_by"), REPORTED_BY)
		for fieldname, _label in CAUSES:
			_set_check(jc, fieldname, fields.get(fieldname))
		_set_text(jc, "corrective_action", fields.get("corrective_action"))
		_set_number(jc, "additional_labour_hours", fields.get("additional_labour_hours"))
		_set_number(jc, "additional_km", fields.get("additional_km"))
		_set_select(jc, "warranty_covered", fields.get("warranty_covered"), YN)
		_set_text(jc, "warranty_covered_reason", fields.get("warranty_covered_reason"))
		_set_select(jc, "warranty_not_covered", fields.get("warranty_not_covered"), YN)
		_set_text(jc, "warranty_not_covered_reason", fields.get("warranty_not_covered_reason"))
		_set_number(jc, "stock_loss_value", fields.get("stock_loss_value"))
		_set_text(jc, "warranty_invoice_number", fields.get("warranty_invoice_number"), 140)
		for fieldname, _label in QI_FIELDS:
			_set_select(jc, fieldname, fields.get(fieldname), YN)
		_set_text(jc, "outstanding_items_notes", fields.get("outstanding_items_notes"))

		description = (fields.get("defect_description") or "").strip()
		issue_ticked = any(fields.get(flag) for flag, _loc, _label in DEFECTS)
		parts = []
		for item in _as_list(lines.get("replacement_parts"))[:30]:
			item = _as_dict(item)
			name = (item.get("item") or "").strip()
			if not name:
				continue
			warranty = item.get("warranty_or_charge") or ""
			if warranty and warranty not in WARRANTY_CHARGE:
				frappe.throw(_("Warranty / Charge must be Warranty, Charge, or N/A"))
			invoice = item.get("invoice_value")
			try:
				invoice_value = float(invoice) if invoice not in (None, "") else None
			except (TypeError, ValueError):
				frappe.throw(_("Invoice value must be a number"))
			parts.append(
				{
					"description": name,
					"quantity": (item.get("quantity") or "").strip(),
					"warranty_or_charge": warranty,
					"invoice_value": invoice_value,
					"status": "Open",
					"priority": "Medium",
					"resolution_notes": PART_ROW,
				}
			)
		if not description and not issue_ticked and not parts and not (fields.get("corrective_action") or "").strip():
			frappe.throw(_("Tick the item affected or describe the defect"))
		defect_rows = []
		if description:
			defect_rows.append(
				{
					"description": description,
					"status": "Open",
					"priority": "Medium",
					"resolution_notes": DEFECT_ROW,
				}
			)
		_rewrite_marked_rows(jc, DEFECT_ROW, defect_rows)
		_rewrite_marked_rows(jc, PART_ROW, parts)

	for sig_field, name_field, label, required in FORM_SIGNATURES[kind]:
		name = (fields.get(name_field) or "").strip()
		signature = signatures.get(sig_field)
		if signature and not name:
			frappe.throw(_("{0} name is required with the signature").format(label))
		if name and jc.meta.has_field(name_field):
			jc.set(name_field, name[:140])
		_set_signature(jc, sig_field, signature, required, label)

	if kind == "handover" and jc.meta.has_field("custom_client_signed_on") and jc.client_signature:
		jc.custom_client_signed_on = now_datetime()


@frappe.whitelist(allow_guest=True)
def submit_signoff(token: str, data: str | dict | None = None) -> dict[str, Any]:
	"""Public: submit role-allowed fields + signature."""
	row = _load_token_or_throw(token)

	if isinstance(data, str):
		data = frappe.parse_json(data) or {}
	data = data or {}

	jc = frappe.get_doc("Job Completion", row.job_completion)
	jc.flags.ignore_permissions = True
	kind = row.role

	if kind in FORM_TYPES:
		_submit_form(jc, kind, data)
	elif kind == "technician":
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
		frappe.throw(_("Invalid link"))

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

	_maybe_complete_job(jc.name, kind)
	frappe.db.commit()

	return {
		"ok": True,
		"job_completion": jc.name,
		"status": frappe.db.get_value("Job Completion", jc.name, "status"),
		"role": kind,
		"form_type": kind if kind in FORM_TYPES else None,
	}


@frappe.whitelist()
def send_signoff_link(
	job_completion: str,
	role: str | None = None,
	channel: str = "email",
	recipient: str | None = None,
	form_type: str | None = None,
) -> dict[str, Any]:
	"""Desk: send short link via email or WhatsApp."""
	_require_login()
	kind = _normalize_kind(role, form_type)
	channel = (channel or "email").strip().lower()

	link_info = generate_signoff_link(job_completion, kind, regenerate=0)
	short_link = link_info.get("short_link")
	if not short_link:
		frappe.throw(_("No short link available"))

	jc = frappe.get_doc("Job Completion", job_completion)
	label = FORM_TITLES.get(kind, kind)

	if channel == "email":
		email = (recipient or jc.email_address or "").strip()
		if not email:
			frappe.throw(_("No email address available. Pass recipient or set Email Address on the Job Completion."))
		subject = _("PG Aluminium — {0} for {1}").format(label, jc.name)
		message = _(
			"<p>Please complete the <b>{0}</b> form for job <b>{1}</b>.</p>"
			"<p><a href=\"{2}\">{2}</a></p>"
			"<p>This link expires in {3} days.</p>"
		).format(label, jc.name, short_link, TOKEN_TTL_DAYS)
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
		text = _("PG Aluminium — please complete the {0} form for job {1}: {2}").format(
			label, jc.name, short_link
		)

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
