# Permission Policy

The Skill has one approved capability: caller-scoped local file writing.

- storyboard_review.py writes only an explicit locked-workspace or report path.
- storyboard_delivery.py writes formal JSON, Markdown, and validation only under an explicit destination.
- export_xlsx.py writes one explicit XLSX destination.

The scripts do not access the network, spawn subprocesses, delete source material, install anything, or choose a broad recursive destination. Approval owner: suvision; review date: 2026-08-24; expiry: 2027-08-24.
