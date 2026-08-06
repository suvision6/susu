#!/usr/bin/env python3
"""Read-only detector for legacy su-image9 prompt packages.

Legacy prompt packages cannot be made trustworthy by renaming fields or replacing
canon text. Detect them and require regeneration from the original shot_data.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

CURRENT_VERSIONS = {"2.1.2"}
LEGACY_VERSION_PATTERNS = (
    (re.compile(r"^1\.6(?:\.|$)"), "1.6.x"),
    (re.compile(r"^1\.7(?:\.|$)"), "1.7.x"),
    (re.compile(r"^2\.0\.2$"), "2.0.2"),
    (re.compile(r"^2\.0\.3$"), "2.0.3"),
)

EXIT_CURRENT = 0
EXIT_REGENERATE = 1
EXIT_CONTRACT_FAIL = 2
EXIT_TOOL_ERROR = 3


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def detect_version(plan: dict[str, Any], prompt_text: str) -> tuple[str, list[str]]:
    evidence: list[str] = []
    explicit = str(plan.get("version", "")).strip()
    if explicit:
        evidence.append(f"panel_plan.version={explicit}")
        for pattern, label in LEGACY_VERSION_PATTERNS:
            if pattern.match(explicit):
                return label, evidence
        if explicit in CURRENT_VERSIONS:
            return explicit, evidence

    if re.search(r"(?m)^\s*P\d{2}\s*:", prompt_text) or re.search(r"(?m)^#\s+P\d{2}\b", prompt_text):
        evidence.append("legacy Pxx page/panel labels")
        return "1.6.x", evidence
    if any(marker in prompt_text for marker in ("@CANON(STYLE_LOCK)", "@CANON(CANVAS_LOCK)", "@CANON(REFERENCE_LOCK)")):
        evidence.append("1.7.x canon markers")
        return "1.7.x", evidence
    if all(marker in prompt_text for marker in ("@CANON(HARD_PHRASES)", "@CANON(GEOMETRY_BLUEPRINT)")):
        evidence.append("2.0.x canon markers")
        return explicit or "2.0.x-unknown", evidence
    return explicit or "unknown", evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect legacy su-image9 artifacts without modifying or migrating them."
    )
    parser.add_argument("--panel-plan", required=True, type=Path)
    parser.add_argument("--final-prompts", required=True, type=Path)
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Deprecated compatibility argument. It is never created or written.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = load_json(args.panel_plan)
        prompt_text = args.final_prompts.read_text(encoding="utf-8-sig")
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "CONTRACT_FAIL", "error": f"invalid panel_plan JSON: {exc}"}, ensure_ascii=False))
        return EXIT_CONTRACT_FAIL
    except (OSError, UnicodeError) as exc:
        print(json.dumps({"status": "TOOL_ERROR", "error": str(exc)}, ensure_ascii=False))
        return EXIT_TOOL_ERROR

    if not isinstance(plan, dict):
        print(json.dumps({"status": "CONTRACT_FAIL", "error": "panel_plan root must be an object"}, ensure_ascii=False))
        return EXIT_CONTRACT_FAIL
    if plan.get("skill") not in (None, "su-image9"):
        print(json.dumps({"status": "CONTRACT_FAIL", "error": "panel_plan is not a su-image9 artifact"}, ensure_ascii=False))
        return EXIT_CONTRACT_FAIL

    detected, evidence = detect_version(plan, prompt_text)
    if detected in CURRENT_VERSIONS:
        result = {
            "status": "CURRENT_NO_MIGRATION_REQUIRED",
            "detected_version": detected,
            "modified_files": [],
            "evidence": evidence,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return EXIT_CURRENT

    result = {
        "status": "F-LEGACY-REGENERATE",
        "detected_version": detected,
        "modified_files": [],
        "evidence": evidence,
        "required_action": "Regenerate the complete prompt package from the original locked shot_data.json with the current derive script.",
        "note": "No output directory or migrated artifact was created.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_REGENERATE


if __name__ == "__main__":
    raise SystemExit(main())
