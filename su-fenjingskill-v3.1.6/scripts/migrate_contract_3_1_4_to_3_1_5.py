#!/usr/bin/env python3
"""Create non-overwriting 3.1.5 review drafts from 3.1.4 inputs."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

try:
    from ._schema_validation import validate_formal_schema, validate_workspace_schema
    from .storyboard_review import all_expected_hashes
except ImportError:  # pragma: no cover
    from _schema_validation import validate_formal_schema, validate_workspace_schema
    from storyboard_review import all_expected_hashes


SCRIPT_INTERFACE = "file-read-write"
SCRIPT_INTERFACE_REASON = "Explicit non-overwriting 3.1.4 to 3.1.5 draft migration."


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} 顶层必须是对象")
    return value


def safe_slug(data: Dict[str, Any]) -> str:
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    slug = source.get("delivery_slug")
    return slug if isinstance(slug, str) and re.fullmatch(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug) else "untitled-scene-001"


def _validate_identity(shot_data: Dict[str, Any], workspace: Dict[str, Any]) -> None:
    expected = {
        "contract_name": "director-shot-data",
        "contract_version": "3.1.4",
        "source_skill": "su-fenjingskill",
        "source_skill_version": "3.1.4",
    }
    for key, value in expected.items():
        if shot_data.get(key) != value:
            raise ValueError(f"迁移输入 {key} 必须是 {value!r}")
    if workspace.get("workspace_contract") != "director-workspace/3.1.4":
        raise ValueError("--workspace 必须是 director-workspace/3.1.4")
    formal_text = normalize_text((shot_data.get("source") or {}).get("locked_text"))
    workspace_text = normalize_text((workspace.get("source") or {}).get("locked_text"))
    if not formal_text or formal_text != workspace_text:
        raise ValueError("3.1.4 workspace 与 shot data 的 locked_text 缺失或不一致")


def build_drafts(
    shot_data: Dict[str, Any], workspace: Dict[str, Any]
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    _validate_identity(shot_data, workspace)
    shot_draft = copy.deepcopy(shot_data)
    workspace_draft = copy.deepcopy(workspace)
    shot_draft["contract_version"] = "3.1.5"
    shot_draft["source_skill_version"] = "3.1.5"
    shot_draft["validation"] = {
        "status": "draft",
        "warnings": [
            "MIGRATION_REVIEW_REQUIRED: dialogue hold/reframe evidence must pass normalized anti-template checks.",
            "MIGRATION_REVIEW_REQUIRED: hold_seconds must be rebuilt as independent event blocks.",
            "MIGRATION_REVIEW_REQUIRED: Gate 2 and Alignment are invalidated; no shot count or duration is inferred.",
        ],
    }

    workspace_draft["workspace_contract"] = "director-workspace/3.1.5"
    events = workspace_draft.get("approval_events") if isinstance(workspace_draft.get("approval_events"), list) else []
    retained_events = []
    for event in events:
        if not isinstance(event, dict) or event.get("event_type") in {"gate_2_confirmed", "alignment_approved"}:
            break
        retained_events.append(copy.deepcopy(event))
    workspace_draft["approval_events"] = retained_events

    hashes = all_expected_hashes(workspace_draft, shot_draft)
    review_lock = workspace_draft.get("review_lock") if isinstance(workspace_draft.get("review_lock"), dict) else {}
    for key, value in hashes.items():
        review_lock[key] = value
    review_lock.update({
        "gate_2_status": "invalidated",
        "gate_2_confirmation_note": "3.1.4 migration requires renewed dialogue-view and topology review under 3.1.5 semantics",
        "alignment_status": "invalidated",
        "alignment_note": "3.1.4 timing and execution evidence require renewed 3.1.5 alignment",
    })
    workspace_draft["review_lock"] = review_lock

    formal_schema_errors = validate_formal_schema(shot_draft)
    workspace_schema_errors = validate_workspace_schema(workspace_draft)
    report = {
        "migration": "director-shot-data/3.1.4 -> director-shot-data/3.1.5",
        "workspace_migration": "director-workspace/3.1.4 -> director-workspace/3.1.5",
        "status": "DRAFT_REVIEW_REQUIRED",
        "formal_ready": False,
        "schema_status": "VALID_MIGRATION_CARRIER" if not formal_schema_errors and not workspace_schema_errors else "SCHEMA_FAIL",
        "formal_schema_errors": formal_schema_errors,
        "workspace_schema_errors": workspace_schema_errors,
        "preserved": ["locked source", "format brief", "director method", "formal shots", "Gate 0 and Gate 1 records when present"],
        "review_stages_invalidated": ["gate_2", "alignment"],
        "next_steps": [
            "replace identifier-only dialogue, viewing, camera and boundary distinctions with shot-specific evidence",
            "rebuild hold_seconds as independent silent/waiting/afterglow blocks",
            "reconfirm Gate 2 without adding shots or durations by migration guess",
            "approve Alignment only after 3.1.5 semantic validation passes",
        ],
    }
    return shot_draft, workspace_draft, report


def ensure_empty_target(path: Path) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f"迁移输出目录必须不存在或为空：{path}")
    path.mkdir(parents=True, exist_ok=True)


def write_json_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="非覆盖迁移 3.1.4 到 3.1.5 审阅草稿。")
    parser.add_argument("--shot-data", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        ensure_empty_target(args.output_dir)
        shot_data = load_json(args.shot_data)
        workspace = load_json(args.workspace)
        shot_draft, workspace_draft, report = build_drafts(shot_data, workspace)
        slug = safe_slug(shot_data)
        paths = {
            "shot_data_draft": args.output_dir / f"{slug}-shot-data-3.1.5-draft.json",
            "workspace_draft": args.output_dir / f"{slug}-director-workspace-3.1.5-draft.json",
            "migration_report": args.output_dir / f"{slug}-migration-report.json",
        }
        for key, path in paths.items():
            write_json_new(path, {"shot_data_draft": shot_draft, "workspace_draft": workspace_draft, "migration_report": report}[key])
            sys.stdout.write(f"{key}: {path}\n")
        sys.stdout.write("status: DRAFT_REVIEW_REQUIRED\n")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
