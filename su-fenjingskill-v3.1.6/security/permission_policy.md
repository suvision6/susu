# Permission Policy

The Skill has one approved capability: caller-scoped local file writing.

- `storyboard_review.py` writes only an explicit new workspace or report path and refuses overwrite.
- `storyboard_delivery.py build-all` stages the fixed JSON, Markdown, XLSX and validation files under an explicit parent, verifies them, then atomically commits the whole output directory.
- `export_xlsx.py` is a compatibility/development utility that writes one explicit new XLSX only after the same formal preflight; it is not a second formal delivery phase.
- `migrate_contract_3_1_0_to_3_1_2.py`, `migrate_contract_3_1_2_to_3_1_3.py`, `migrate_contract_3_1_3_to_3_1_5.py` and `migrate_contract_3_1_4_to_3_1_5.py` each write only three draft files inside an explicit empty output directory.

The scripts do not access the network, spawn subprocesses, install packages, overwrite source material or choose a broad recursive destination. Temporary staging trees created by `build-all` are removed on failure. Approval owner: suvision; review date: 2026-09-04; expiry: 2027-09-01.
