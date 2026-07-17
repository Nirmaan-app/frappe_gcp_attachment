from __future__ import unicode_literals

import datetime
import io
import json
import os
import random
import re
import string
import urllib.parse
from datetime import timedelta

import frappe
import magic
from google.cloud import storage
from google.oauth2 import service_account


class GCPOperations(object):
    """Google Cloud Storage backend for Frappe File attachments.

    `S3Operations` is kept as an alias (below the class) so callers migrating from
    `frappe_s3_attachment` only change the import path, not the class or method names.
    Config is read from the "GCP File Attachment" settings doctype.
    """

    def __init__(self):
        self.settings_doc = frappe.get_doc('GCP File Attachment', 'GCP File Attachment')
        self.GCS_CLIENT = self._build_gcs_client()
        self.BUCKET = self.settings_doc.gcs_bucket_name
        self.folder_name = self.settings_doc.folder_name
        self.gcs_bucket = self.GCS_CLIENT.bucket(self.BUCKET)

    def _build_gcs_client(self):
        """Build a signing-capable GCS client from the pasted service-account JSON."""
        doc = self.settings_doc
        project = (doc.gcs_project_id or "").strip() or None
        raw = (doc.gcs_credentials_json or "").strip()
        if raw:
            info = json.loads(raw)
            creds = service_account.Credentials.from_service_account_info(info)
            return storage.Client(project=project or info.get("project_id"), credentials=creds)
        # Fallback: Application Default Credentials (cannot sign private URLs).
        return storage.Client(project=project)

    # ---- helpers ----
    def strip_special_chars(self, file_name):
        regex = re.compile('[^0-9a-zA-Z._-]')
        return regex.sub('', file_name)

    def sanitize_filename_for_header(self, file_name):
        return re.sub(r'[^\x20-\x7E]', '', file_name)

    def key_generator(self, file_name, parent_doctype, parent_name):
        hook_cmd = frappe.get_hooks().get("gcs_key_generator") or frappe.get_hooks().get("s3_key_generator")
        if hook_cmd:
            try:
                k = frappe.get_attr(hook_cmd[0])(
                    file_name=file_name, parent_doctype=parent_doctype, parent_name=parent_name
                )
                if k:
                    return k.rstrip('/').lstrip('/')
            except Exception:
                pass

        file_name = file_name.replace(' ', '_')
        file_name = self.strip_special_chars(file_name)
        key = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))

        today = datetime.datetime.now()
        year = today.strftime("%Y")
        month = today.strftime("%m")
        day = today.strftime("%d")

        if self.folder_name:
            final_key = f"{self.folder_name}/{year}/{month}/{day}/{parent_doctype}/{key}_{file_name}"
        else:
            final_key = f"{year}/{month}/{day}/{parent_doctype}/{key}_{file_name}"
        return final_key

    def public_url(self, key):
        """Permanent public URL — public files are made readable at upload via make_public()
        (needs the bucket on fine-grained ACLs / Uniform Bucket-Level Access OFF)."""
        return f"https://storage.googleapis.com/{self.BUCKET}/{key}"

    # ---- upload / delete / read / sign ----
    def upload_files_to_s3_with_key(self, file_path, file_name, is_private, parent_doctype, parent_name):
        mime_type = magic.from_file(file_path, mime=True)
        key = self.key_generator(file_name, parent_doctype, parent_name)
        try:
            blob = self.gcs_bucket.blob(key)
            blob.upload_from_filename(file_path, content_type=mime_type)
            if not is_private:
                blob.make_public()
        except Exception:
            frappe.throw(frappe._("File Upload Failed. Please try again."))
        return key

    def delete_from_s3(self, key):
        if not self.settings_doc.delete_file_from_cloud:
            return
        try:
            self.gcs_bucket.blob(key).delete()
        except Exception:
            frappe.throw(frappe._("Access denied: Could not delete file"))

    def read_file_from_s3(self, key):
        # boto3-shaped {"Body": <readable>} so callers doing response["Body"].read() work unchanged.
        data = self.gcs_bucket.blob(key).download_as_bytes()
        return {"Body": io.BytesIO(data)}

    def get_url(self, key, file_name=None):
        expiry = self.settings_doc.signed_url_expiry_time or 120
        disposition = None
        if file_name:
            safe = self.sanitize_filename_for_header(file_name)
            disposition = f'inline; filename="{safe}"'
        blob = self.gcs_bucket.blob(key)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expiry),
            method="GET",
            response_disposition=disposition,
        )


# Backward-compatible alias: nirmaan_stack imports `S3Operations`; only the module path changes.
S3Operations = GCPOperations


# ===========================================================================
# Module-level functions (hooked from hooks.py). Private URLs self-reference this
# module: /api/method/frappe_gcp_attachment.controller.generate_file
# ===========================================================================
GENERATE_FILE_METHOD = "frappe_gcp_attachment.controller.generate_file"


@frappe.whitelist()
def file_upload_to_gcs(doc, method):
    gcp = GCPOperations()
    path = doc.file_url
    site_path = frappe.utils.get_site_path()
    parent_doctype = doc.attached_to_doctype or 'File'
    parent_name = doc.attached_to_name
    ignore = frappe.local.conf.get('ignore_gcs_upload_for_doctype') \
        or frappe.local.conf.get('ignore_s3_upload_for_doctype') or ['Data Import']

    if parent_doctype not in ignore:
        file_path = site_path + ('/public' if not doc.is_private else '') + path
        key = gcp.upload_files_to_s3_with_key(
            file_path, doc.file_name, doc.is_private, parent_doctype, parent_name
        )

        if doc.is_private:
            file_url = f"/api/method/{GENERATE_FILE_METHOD}?key={key}&file_name={urllib.parse.quote(doc.file_name)}"
        else:
            file_url = gcp.public_url(key)

        os.remove(file_path)
        frappe.db.sql(
            """UPDATE `tabFile` SET file_url=%s, folder=%s, old_parent=%s, content_hash=%s WHERE name=%s""",
            (file_url, 'Home/Attachments', 'Home/Attachments', key, doc.name),
        )
        doc.file_url = file_url

        if parent_doctype and frappe.get_meta(parent_doctype).get('image_field'):
            frappe.db.set_value(
                parent_doctype, parent_name, frappe.get_meta(parent_doctype).get('image_field'), file_url
            )

        frappe.db.commit()


@frappe.whitelist()
def generate_file(key=None, file_name=None):
    if key:
        gcp = GCPOperations()
        signed_url = gcp.get_url(key, file_name)
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = signed_url
    else:
        frappe.local.response['body'] = "Key not found."
    return


def upload_existing_files(name, file_name):
    file_doc_name = frappe.db.get_value('File', {'name': name})
    if file_doc_name:
        doc = frappe.get_doc('File', name)
        gcp = GCPOperations()
        path = doc.file_url
        site_path = frappe.utils.get_site_path()
        parent_doctype = doc.attached_to_doctype
        parent_name = doc.attached_to_name

        file_path = site_path + ('/public' if not doc.is_private else '') + path
        key = gcp.upload_files_to_s3_with_key(
            file_path, doc.file_name, doc.is_private, parent_doctype, parent_name
        )

        if doc.is_private:
            file_url = f"/api/method/{GENERATE_FILE_METHOD}?key={key}"
        else:
            file_url = gcp.public_url(key)

        os.remove(file_path)
        frappe.db.sql(
            """UPDATE `tabFile` SET file_url=%s, folder=%s, old_parent=%s, content_hash=%s WHERE name=%s""",
            (file_url, 'Home/Attachments', 'Home/Attachments', key, doc.name),
        )
        frappe.db.commit()


def gcs_file_regex_match(file_url):
    return re.match(
        r'^(https:|/api/method/frappe_gcp_attachment.controller.generate_file)', file_url
    )


@frappe.whitelist()
def migrate_existing_files():
    files_list = frappe.get_all('File', fields=['name', 'file_url', 'file_name'])
    for file in files_list:
        if file['file_url'] and not gcs_file_regex_match(file['file_url']):
            upload_existing_files(file['name'], file['file_name'])
    return True


def delete_from_cloud(doc, method):
    gcp = GCPOperations()
    gcp.delete_from_s3(doc.content_hash)


@frappe.whitelist()
def ping():
    return "pong"
