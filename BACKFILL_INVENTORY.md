# GCS URL-Rename Backfill — Field Inventory

What the backfill rewrites in the database, grouped by **field type**.

- **Change:** `…frappe_s3_attachment.controller.generate_file…` → `…frappe_gcp_attachment.controller.generate_file…`
- **The object key (`?key=…`) is never touched** — only the module name in the URL string.
- **Raw SQL** → `modified` / `modified_by` are **not** changed, and no Version/audit rows are created.
- **Every column below is a Postgres `text` column**, so the backfill uses a plain `REPLACE()` — the JSON/JSONB cast path is never needed for this data.

## Totals

| Category | Fields | URLs |
|---|---:|---:|
| Attachment fields (`Attach` / `Attach Image`) | 27 | 30,630 |
| URL / link fields (bare URL in a text field) | 2 | 33,166 |
| JSON / serialized-data fields (URL inside a JSON blob) | 3 | 9,102 |
| Rich-text / HTML fields | 1 | 96 |
| **Total** | **33** | **72,994** |

---

## 1. Attachment fields — `Attach` / `Attach Image`

The direct file-attach fields. This is the bulk of the duplicated URL copies.

| Doctype | Field | Type | URLs |
|---|---|---|---:|
| Project Progress Report Attachments | image_link | Attach | 11,348 |
| Nirmaan Attachments | attachment | Attach | 9,852 |
| Project Payments | payment_attachment | Attach | 6,090 |
| TDS Repository | tds_attachment | Attach | 743 |
| Project Payments | voucher_attachment | Attach | 639 |
| Project TDS Item List | tds_attachment | Attach | 603 |
| Non Project Expenses | payment_attachment | Attach | 567 |
| Project Inflows | inflow_attachment | Attach | 289 |
| Project Invoices | attachment | Attach | 166 |
| Non Project Expenses | invoice_attachment | Attach | 143 |
| PMO Project Task | attachment | Attach | 38 |
| Design Tracker Task Child Table | approval_proof | Attach | 37 |
| Asset Management | asset_declaration_attachment | Attach | 27 |
| Commission Report Task Child Table | approval_proof | Attach | 17 |
| Delivery Note Attachments | image | Attach Image | 13 |
| Procurement Orders | attachment | Attach | 11 |
| Project TDS Setting | client_logo | Attach | 10 |
| Project TDS Setting | consultant_logo | Attach | 8 |
| Project TDS Setting | architect_logo | Attach | 8 |
| Project TDS Setting | gc_contractor_logo | Attach | 7 |
| Customer PO Child Table | customer_po_attachment | Attach | 6 |
| Asset Master | asset_certificate_attachment | Attach | 2 |
| Milestone Attachments | image | Attach Image | 2 |
| Asset Master | asset_invoice_attachment | Attach | 1 |
| PO Adjustment Items | refund_attachment | Attach | 1 |
| Project TDS Setting | mananger_logo | Attach | 1 |
| User | user_image | Attach Image | 1 |

**Subtotal: 27 fields, 30,630 URLs.**

---

## 2. URL / link fields — bare URL in a text field

Plain file-pointer fields (not an attachment widget, not JSON).

| Doctype | Field | Type | URLs |
|---|---|---|---:|
| File | file_url | Code | 33,164 |
| BOQs | source_file_url | Small Text | 2 |

**Subtotal: 2 fields, 33,166 URLs.**

> `File.file_url` is the canonical file pointer and the **catch-all**: it holds one row for *every* uploaded file (33,164), including the 12,728 standalone files and the ~4,385 attached to doctypes that have no field of their own (Vendor Invoices, Procurement Requests, Service Requests, Projects, Project Progress Reports, Data Import). Renaming this one field covers all of them.

---

## 3. JSON / serialized-data fields — URL embedded inside a JSON blob

The URL sits inside a larger serialized structure; the `REPLACE()` still swaps only the module-name substring.

| Doctype | Field | Type | URLs |
|---|---|---|---:|
| Version | data | Code (JSON) | 7,741 |
| Deleted Document | data | Code (JSON) | 1,355 |
| Commission Report Task Child Table | response_data | Long Text (JSON) | 6 |

**Subtotal: 3 fields, 9,102 URLs.**

> `Version.data` and `Deleted Document.data` are **history / audit** blobs — renaming them keeps old snapshots internally consistent; they are not user-facing images.

---

## 4. Rich-text / HTML fields

| Doctype | Field | Type | URLs |
|---|---|---|---:|
| Communication | content | Text Editor (HTML) | 96 |

**Subtotal: 1 field, 96 URLs.**

> Emails whose HTML body embeds an inline file link.

---

## Not in scope (verified, correctly excluded)

- **Doctypes with files but no field** — Vendor Invoices (3,359), Procurement Requests (611), Service Requests (335), Projects (55), Project Progress Reports (12), Data Import (13), + 12,728 standalone. Their `attached_to_field` points to **columns that don't exist** (phantom fields), so there is no field copy to rewrite — they are covered entirely by `File.file_url` (category 2).
- **`Error Log.error`** — 20 old exception tracebacks that name the hook path. Historical logs, not file URLs; the safety-scan will warn about it — leave it.
- **App-name metadata** (`User.last_known_versions`, `DefaultValue.defvalue`, `Installed Application.app_name`) and `Print Format.html` (references the kept `nirmaan_stack.api.frappe_s3_attachment` module) — these hold the app *name*, not `.controller` URLs, so the precise needle skips them.

_Counts are a snapshot from the 2026-07-16 live-DB scan; small drift over time is normal (new uploads already use `frappe_gcp_attachment` URLs and need no rename)._
