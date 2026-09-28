# PG Job Signoff

On-site **Job Completion** forms for PG Aluminium: separate magic links for **handover**, **site completion**, and **snag**, shortened with **frappe_tinyurl**, no CRM login required.

## Phases

| Phase | Status | What |
| --- | --- | --- |
| **1** | Done | Tokens, TinyURL short links, Desk Copy/Send, `/signoff` mobile page |
| **2** | Done | Installable **PWA**, offline submit queue, snag photo capture, branded motion |

Same APIs and Desk buttons for both phases — Phase 2 upgrades the `/signoff` experience only.

## What it does

Desk — three separate short links:

| Link | When it can be sent | Form |
| --- | --- | --- |
| **Handover** | Status **Awaiting Sign Off** | Project completion checklist, comments, client + sales signatures. Client signature moves the job to **Completed** |
| **Site completion** | Draft, Inspection, Snag List, or Awaiting Sign Off | Outstanding works, temporary condition, return-visit inspection |
| **Snag** | Same open statuses | Newer defect / snag report, including additional labour hours and km |

Each link can be copied, emailed, or sent on WhatsApp. Regenerating revokes the previous active link for that form only.

Public `/signoff?token=…` (opened via TinyURL) — **PWA**:

- Installable on phone home screen (`manifest.webmanifest` + service worker)
- One page per link, matching that paper form
- Offline: form can be completed and queued in IndexedDB; syncs when back online

## Dependencies

- Frappe / ERPNext (custom Job Completion DocType already on site)
- [`frappe_tinyurl`](https://github.com/PinDyn/frappe_tinyurl) — configure **TinyURL Settings** (Domain + API Key)
- Optional: `frappe_whatsapp` for WhatsApp send

## Install (bench)

```bash
cd /path/to/frappe-bench
bench get-app /path/to/pg_job_signoff
# or: bench get-app https://github.com/PinDyn/pg_job_signoff.git

bench --site pg-aluminium.pindynerp.com install-app pg_job_signoff
bench --site pg-aluminium.pindynerp.com migrate
bench build --app pg_job_signoff
bench --site pg-aluminium.pindynerp.com clear-cache
```

Confirm **TinyURL Settings** has Domain + API Key.

After upgrade to Phase 2 assets:

```bash
bench build --app pg_job_signoff
bench --site pg-aluminium.pindynerp.com clear-cache
```

PWA files served from app `www/`:

- `/manifest.webmanifest`
- `/pg-signoff-sw.js`

## Desk usage

1. Open a Job Completion
2. **Sign-Off Links → Handover Link**, **Site Completion Link**, or **Snag Link**
3. Copy, email, or WhatsApp that short link
4. Recipient opens the short URL and completes that form (optional: Install app)

Handover is available only in **Awaiting Sign Off**. Site completion and snag are available while the job is still open.

## API

| Method | Guest | Purpose |
| --- | --- | --- |
| `pg_job_signoff.api.signoff.generate_signoff_link` | No | Create a TinyURL for `form_type`: `handover`, `site_completion`, or `snag` |
| `pg_job_signoff.api.signoff.send_signoff_link` | No | Email / WhatsApp that short link |
| `pg_job_signoff.api.signoff.get_signoff_payload` | Yes | Load role-scoped form data |
| `pg_job_signoff.api.signoff.submit_signoff` | Yes | Save signature (+ snags / photos / comment) |

Technician submit may include `snag_photos`: `{ "<snag_row_name>": "data:image/jpeg;base64,..." }`.

## Notes

- Tokens expire after 7 days; successful submit marks the token **Used**
- Regenerating a link revokes the previous Active token for that form only
- Short links hide the token in shared text; after redirect the browser may show `/signoff?token=…`
- Offline queue is device-local (IndexedDB); clear site data clears the queue
