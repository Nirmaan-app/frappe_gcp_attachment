# Frappe GCP Attachment

Frappe app that uploads File attachments to **Google Cloud Storage** (the GCS successor to
`frappe_s3_attachment`). On `File` `after_insert` it moves the uploaded file to a GCS bucket and
rewrites `file_url`:

- **Public** files → `blob.make_public()` + a direct `https://storage.googleapis.com/<bucket>/<key>` URL.
- **Private** files → an internal redirect `/api/method/frappe_gcp_attachment.controller.generate_file?key=<key>`
  that mints a short-lived signed URL on each request.

Config lives in the **GCP File Attachment** settings doctype (bucket, project id, service-account JSON,
folder prefix, signed-URL expiry, delete-on-trash).

#### License

MIT
