# Security policy

## Supported versions

During beta, security fixes target the latest release and the previous minor
release when a safe backport is practical.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do not
open a public issue for leaked credentials, arbitrary file deletion, path
traversal, unexpected network transfer, or spend-limit bypasses.

Include the affected version, platform, reproduction, impact, and whether a real
provider key or billable request was involved. Revoke any exposed key with the
provider immediately; this project cannot revoke third-party credentials.

The project is community-supported and cannot promise a response time. We will
avoid publishing exploit details before a fix is available when coordinated
disclosure is possible.
