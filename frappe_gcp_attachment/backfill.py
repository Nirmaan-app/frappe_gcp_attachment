"""
ONE-TIME backfill for the frappe_s3_attachment -> frappe_gcp_attachment APP RENAME.

Every stored PRIVATE-file URL names the old module:
    /api/method/frappe_s3_attachment.controller.generate_file?key=<KEY>
This rewrites the module name  ->  frappe_gcp_attachment.controller  everywhere a URL is
stored. The object KEY is unchanged, so files served from GCS at the same key keep working.

DOCTYPE-WISE: it walks an EXPLICIT list of (doctype -> fields) taken from the 2026-07 audit, so
you can see and control exactly what is touched, and it reports per doctype. TARGETS is the whole
contract: a field that is not listed there is never looked at, so re-audit it against any doctype
added since 2026-07 before trusting a run on a new site.

RUN THIS *BEFORE* uninstalling frappe_s3_attachment, and *AFTER* the S3->GCS copy +
`frappe_gcp_attachment` is installed with a working GCS bucket.
(Public files would be direct https://amazonaws URLs needing a host swap, not a rename -- this
site has 0 public files, so none of that exists.)

RUN (dry-run first, always):
  bench --site localhost execute frappe_gcp_attachment.backfill.run --kwargs "{'dry_run': True}"
  bench --site localhost execute frappe_gcp_attachment.backfill.run --kwargs "{'dry_run': False}"
  # limit to one doctype while testing:
  bench --site localhost execute frappe_gcp_attachment.backfill.run --kwargs "{'dry_run': False, 'only': 'Project Invoices'}"

Idempotent + committed per doctype: once rewritten a row no longer matches, so a re-run resumes
safely from wherever it stopped.
"""

import frappe

OLD = "frappe_s3_attachment.controller"
NEW = "frappe_gcp_attachment.controller"
NEEDLE = f"%{OLD}%"
NEW_NEEDLE = f"%{NEW}%"

# ---------------------------------------------------------------------------
# EXPLICIT doctype -> [fields] map (from the URL audit). One block per doctype.
# ---------------------------------------------------------------------------
TARGETS = {
    # --- Frappe core ---
    "File":                                 ["file_url"],
    "Version":                              ["data"],           # audit / version history
    "Deleted Document":                     ["data"],
    "Communication":                        ["content"],        # emails
    "User":                                 ["user_image"],
    # --- nirmaan_stack: attachments ---
    "Nirmaan Attachments":                  ["attachment"],
    "Project Progress Report Attachments":  ["image_link"],
    "Project Payments":                     ["payment_attachment", "voucher_attachment"],
    "TDS Repository":                       ["tds_attachment"],
    "Project TDS Item List":                ["tds_attachment"],
    "Non Project Expenses":                 ["payment_attachment", "invoice_attachment"],
    "Project Inflows":                      ["inflow_attachment"],
    "Project Invoices":                     ["attachment"],
    "PMO Project Task":                     ["attachment"],
    "Design Tracker Task Child Table":      ["approval_proof"],
    "Asset Management":                     ["asset_declaration_attachment"],
    "Commission Report Task Child Table":   ["approval_proof", "response_data"],   # response_data = JSON with images
    "Delivery Note Attachments":            ["image"],
    "Procurement Orders":                   ["attachment"],
    "Project TDS Setting":                  ["client_logo", "consultant_logo", "architect_logo",
                                             "gc_contractor_logo", "mananger_logo"],
    "Customer PO Child Table":              ["customer_po_attachment"],
    "Milestone Attachments":                ["image"],
    "Asset Master":                         ["asset_certificate_attachment", "asset_invoice_attachment"],
    "PO Adjustment Items":                  ["refund_attachment"],
    "BOQs":                                 ["source_file_url"],
}


def _count(table, col, pat=NEEDLE):
    try:
        return frappe.db.sql(f'SELECT COUNT(*) FROM "{table}" WHERE "{col}"::text LIKE %s', (pat,))[0][0]
    except Exception:
        frappe.db.rollback()
        return None


def _progress_summary():
    """End-of-run status: how many URLs are renamed (frappe_gcp) vs remaining
    (frappe_s3) across ALL target doctypes, with the pending list."""
    tot_old = tot_new = done = 0
    pending = []
    for dt, cols in TARGETS.items():
        table = "tab" + dt
        o = sum((_count(table, c) or 0) for c in cols)
        g = sum((_count(table, c, NEW_NEEDLE) or 0) for c in cols)
        tot_old += o
        tot_new += g
        if o:
            pending.append((dt, o))
        elif g:
            done += 1
    total = tot_old + tot_new
    pct = (100 * tot_new // total) if total else 100
    print("\n" + "=" * 54)
    print("  BACKFILL PROGRESS")
    print("=" * 54)
    print(f"  renamed   (frappe_gcp) : {tot_new}")
    print(f"  remaining (frappe_s3)  : {tot_old}")
    print(f"  progress: {tot_new}/{total}  ({pct}%)   done doctypes: {done}, pending: {len(pending)}")
    if pending:
        print("  still to do:")
        for dt, o in sorted(pending, key=lambda x: -x[1]):
            print(f"      {o:>7}  {dt}")
    else:
        print("  🎉 ALL DONE — no old URLs remain in any target doctype.")
    print("=" * 54)


def _coltype(table, col):
    r = frappe.db.sql(
        "SELECT data_type FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
        (table, col))
    return (r[0][0] if r else "").lower()


def _rewrite(table, col):
    dtype = _coltype(table, col)
    if dtype in ("json", "jsonb"):
        frappe.db.sql(
            f'UPDATE "{table}" SET "{col}" = REPLACE("{col}"::text, %s, %s)::{dtype} '
            f'WHERE "{col}"::text LIKE %s', (OLD, NEW, NEEDLE))
    else:
        frappe.db.sql(
            f'UPDATE "{table}" SET "{col}" = REPLACE("{col}"::text, %s, %s) '
            f'WHERE "{col}"::text LIKE %s', (OLD, NEW, NEEDLE))


def run(dry_run=True, only=None):
    grand = confirmed = 0
    print(f"[rename] {'DRY RUN — ' if dry_run else ''}scanning {len(TARGETS)} doctypes for '{OLD}' URLs\n")
    for dt, fields in TARGETS.items():
        if only and dt != only:
            continue
        table = "tab" + dt
        col_counts = [(c, _count(table, c) or 0) for c in fields]
        dt_total = sum(n for _, n in col_counts)
        if not dt_total:
            continue
        print(f"  {dt}: {dt_total}")
        for col, n in col_counts:
            if not n:
                continue
            if dry_run:
                print(f"      {col}: {n} (would rewrite)")
                continue
            try:
                _rewrite(table, col)
                after = _count(table, col) or 0          # re-count = VERIFY it actually changed
                rep = n - after
                confirmed += rep
                flag = "✓" if after == 0 else f"⚠ {after} STILL LEFT"
                print(f"      {col}: matched {n} → replaced {rep}, remaining {after} {flag}")
            except Exception as exc:
                frappe.db.rollback()
                print(f"      ! FAILED {col}: {str(exc).splitlines()[0][:90]}")
        grand += dt_total
        if not dry_run:
            frappe.db.commit()   # commit per doctype -> resumable

    if dry_run:
        print(f"\n[rename] would rewrite {grand} rows across listed doctypes.")
    else:
        print(f"\n[rename] REPLACED {confirmed} of {grand} matched rows (verified by re-count — remaining should be 0).")

    if dry_run:
        print("[rename] DRY RUN — no writes. Re-run with dry_run=False to apply.")

    _progress_summary()   # <-- overall status at the very end of every run


# ---------------------------------------------------------------------------
# INTERACTIVE one-by-one runner:
#   bench --site <site> execute frappe_gcp_attachment.backfill.interactive
#
# Shows a live menu of the doctypes that STILL hold old URLs (+ an ALL option).
# A doctype is "done" the instant it has 0 old URLs left, so it AUTOMATICALLY
# drops off the menu — a later run (even ALL) never re-touches it. No ledger
# file needed: the idempotent rewrite IS the progress marker. The counts in the
# menu double as the dry-run preview; each pick is confirmed before it writes.
# ---------------------------------------------------------------------------
def _hits(only=None):
    """[(doctype, remaining_count)] for TARGET doctypes that still hold old URLs."""
    rows = []
    for dt, fields in TARGETS.items():
        if only and dt != only:
            continue
        table = "tab" + dt
        total = sum(n for n in (_count(table, c) for c in fields) if n)
        if total:
            rows.append((dt, total))
    return rows


def _run_one(dt):
    """Rewrite + commit a single doctype (so it is instantly 'done' / hidden)."""
    table, replaced = "tab" + dt, 0
    for col in TARGETS[dt]:
        n = _count(table, col) or 0
        if not n:
            continue
        try:
            _rewrite(table, col)
            after = _count(table, col) or 0              # re-count = VERIFY
            rep = n - after
            replaced += rep
            flag = "✓" if after == 0 else f"⚠ {after} left"
            print(f"      {col}: matched {n} → replaced {rep}, remaining {after} {flag}")
        except Exception as exc:
            frappe.db.rollback()
            print(f"      ! {col} FAILED: {str(exc).splitlines()[0][:90]}")
    frappe.db.commit()   # commit per doctype -> resumable + immediately hidden next loop
    print(f"  [{dt}] confirmed {replaced} replaced\n")


def interactive():
    print("\nInteractive GCP URL rename.")
    print("Completed doctypes vanish from the list (0 old URLs = done), so re-running")
    print("never repeats one — not even via ALL. The counts below are your dry preview.\n")
    while True:
        remaining = _hits()
        if not remaining:
            print("✓ Nothing left — every listed doctype is already renamed.")
            _progress_summary()
            return
        print(f"--- {len(remaining)} doctype(s) still holding old URLs ---")
        for i, (dt, n) in enumerate(remaining, 1):
            print(f"  {i:>2}) {dt:<44} {n:>6}")
        print("   a) run ALL remaining        q) quit")
        try:
            c = input("pick #, 'a', or 'q': ").strip().lower()
        except EOFError:
            print("(no interactive terminal — run this from a real shell)")
            return
        if c == "q":
            _progress_summary()
            print("bye.")
            return
        if c == "a":
            for dt, _ in list(remaining):
                _run_one(dt)
            continue
        if c.isdigit() and 1 <= int(c) <= len(remaining):
            dt = remaining[int(c) - 1][0]
            ans = input(f"  run '{dt}'?  [y = run / s = skip for now / b = back]: ").strip().lower()
            if ans == "y":
                _run_one(dt)
            elif ans == "s":
                print(f"  skipped '{dt}' — still there next time.\n")
            continue
        print("  ? not a valid choice\n")
