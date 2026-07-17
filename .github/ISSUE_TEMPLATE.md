<!--
Thanks for reporting an issue with Frappe GCP Attachment.
Please fill in as much of the template below as you can.
-->

**Describe the issue**
A clear and concise description of what went wrong.

**Steps to reproduce**
1. …
2. …

**Expected behaviour**


**Actual behaviour / error**
<!-- Paste the FULL traceback. The real cause is usually the google.api_core / boto3 line,
     not the "File Upload Failed. Please try again." wrapper. -->
```
```

**Environment**
- Frappe / ERPNext version:
- `frappe_gcp_attachment` version:
- GCS bucket access: fine-grained ACLs / uniform?
- Service account role:

**Config sanity check**
- [ ] `GCP File Attachment` has a bucket name
- [ ] The bucket exists
- [ ] The service account has `Storage Object Admin` on the bucket
