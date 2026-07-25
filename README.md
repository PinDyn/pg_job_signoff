# PG Job Signoff

On-site **Job Completion** sign-off for PG Aluminium: role-scoped magic links for **technician** and **client**, shortened with **frappe_tinyurl**, no CRM login required.

## Phases

| Phase | Status | What |
| --- | --- | --- |
| **1** | Done | Tokens, TinyURL short links, Desk Copy/Send, `/signoff` mobile page |
| **2** | Done | Installable **PWA**, offline submit queue, snag photo capture, branded motion |

Same APIs and Desk buttons for both phases — Phase 2 upgrades the `/signoff` experience only.

## What it does

Desk (status **Awaiting Sign Off**):

- Generate / regenerate technician & client links
- **Copy Short Link** (TinyURL only — token never shown)
- Email / WhatsApp the short link

Public `/signoff?token=…` (opened via TinyURL) — **PWA**:

- Installable on phone home screen (`manifest.webmanifest` + service worker)
- **Client:** job summary, optional comment, name + signature
- **Technician:** job summary, mark snags Resolved, **add snag photos**, name + signature
- Offline: form can be completed and queued in IndexedDB; syncs when back online
- When both signatures exist → Job Completion status becomes **Completed**

Checklist / site-completion / sales signature stay Desk-only.

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

1. Open a Job Completion in **Awaiting Sign Off**
2. **Sign-Off Links → Generate Technician / Client Link**
3. **Copy … Short Link** or Email / WhatsApp
4. Recipient opens short URL → signs on phone (optional: Install app)

## API

| Method | Guest | Purpose |
| --- | --- | --- |
| `pg_job_signoff.api.signoff.generate_signoff_link` | No | Create TinyURL short link |
| `pg_job_signoff.api.signoff.send_signoff_link` | No | Email / WhatsApp short link |
| `pg_job_signoff.api.signoff.get_signoff_payload` | Yes | Load role-scoped form data |
| `pg_job_signoff.api.signoff.submit_signoff` | Yes | Save signature (+ snags / photos / comment) |

Technician submit may include `snag_photos`: `{ "<snag_row_name>": "data:image/jpeg;base64,..." }`.

## Notes

- Tokens expire after 7 days; successful submit marks the token **Used**
- Regenerating a link revokes the previous Active token for that role
- Short links hide the token in shared text; after redirect the browser may show `/signoff?token=…`
- Offline queue is device-local (IndexedDB); clear site data clears the queue
