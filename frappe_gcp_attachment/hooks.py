# -*- coding: utf-8 -*-
from __future__ import unicode_literals

app_name = "frappe_gcp_attachment"
app_title = "Frappe GCP Attachment"
app_publisher = "Nirmaan"
app_description = "Frappe app to upload file attachments to Google Cloud Storage."
app_icon = "octicon octicon-cloud-upload"
app_color = "blue"
app_email = "techadmin@nirmaan.app"
app_license = "MIT"

# Route File uploads/deletes to the GCS controller (mirrors frappe_s3_attachment's wiring).
doc_events = {
    "File": {
        "after_insert": "frappe_gcp_attachment.controller.file_upload_to_gcs",
        "on_trash": "frappe_gcp_attachment.controller.delete_from_cloud"
    }
}
