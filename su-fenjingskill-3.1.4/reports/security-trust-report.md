# Security Trust Report

- OK: `True`
- Scanned files: `66`
- Scripts: `11`
- Internal script modules: `5`
- Secret findings: `0`
- Network-capable scripts: `0`
- Network policy covered scripts: `0`
- Network policy missing scripts: `0`
- File-write scripts: `6`
- Permission approvals: `0 / 1`
- Permission approval gaps: `1`
- CLI help smoke checked: `6`
- CLI help smoke failures: `0`
- Interactive scripts: `0`
- Package hash scope: `source-contract-without-generated-reports`
- Package hash files: `66`
- Package SHA256: `71b18baa97f6a5e6bc6e0edc07af858c99089d2f190974f816223f7d4cd8a91a`

## Failures

- None

## Warnings

- Permission approvals invalid: file_write

## Dependency Evidence

- Files: `requirements.txt`
- Pinned entries: `0`
- Unpinned entries: `0`

## Network Policy

- Policy file: `security/network_policy.json`
- Present: `False`
- Covered scripts: `0`
- Missing scripts: `none`
- Mismatches: `0`

## Permission Governance

- Policy file: `security/permission_policy.json`
- Present: `True`
- Required capabilities: `file_write`
- Approved capabilities: `none`
- Missing approvals: `none`
- Invalid approvals: `file_write`
- Expired approvals: `none`

## CLI Help Smoke

- Enabled: `True`
- Timeout seconds: `5.0`
- Checked scripts: `6`
- Passed scripts: `6`
- Failed scripts: `none`

## Script Surface

| Script | Interface | Declared | Argparse | Main Guard | Input | Network | File Write | Subprocess | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| scripts/_chinese_context.py | internal-module | True | False | False | False | False | False | False | Imported by storyboard_delivery.py for deterministic Chinese-language checks. |
| scripts/_execution_text.py | internal-module | True | False | False | False | False | False | False | Imported by the formal backend to serialize structured execution facts. |
| scripts/_schema_validation.py | internal-module | True | False | False | False | False | False | False | Imported by formal validators for Draft 2020-12 Schema checks. |
| scripts/_xlsx_projection.py | internal-module | True | False | False | False | False | False | False | Imported by export_xlsx.py to build the deterministic human-facing projection. |
| scripts/export_xlsx.py | cli | False | True | True | False | False | True | False | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts/migrate_contract_3_1_0_to_3_1_2.py | file-read-write | True | True | True | False | False | True | False | Explicit non-overwriting migration into a caller-selected empty directory. |
| scripts/migrate_contract_3_1_2_to_3_1_3.py | file-read-write | True | True | True | False | False | True | False | Explicit non-overwriting migration into a caller-selected empty directory. |
| scripts/migrate_contract_3_1_3_to_3_1_4.py | file-read-write | True | True | True | False | False | True | False | Explicit non-overwriting 3.1.3 to 3.1.4 draft migration. |
| scripts/source_alignment.py | internal-module | True | False | False | False | False | False | False | Imported by reviewer, formal builder, exporter, and migration tests for deterministic source alignment. |
| scripts/storyboard_delivery.py | cli | False | True | True | False | False | True | False | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts/storyboard_review.py | cli | False | True | True | False | False | True | False | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
