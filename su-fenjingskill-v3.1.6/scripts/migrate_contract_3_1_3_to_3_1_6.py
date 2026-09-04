#!/usr/bin/env python3
"""Create non-overwriting 3.1.6 review drafts from valid 3.1.3 inputs."""

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
except ImportError:  # pragma: no cover
    from _schema_validation import validate_formal_schema, validate_workspace_schema


SCRIPT_INTERFACE = "file-read-write"
SCRIPT_INTERFACE_REASON = "Explicit non-overwriting 3.1.3 to 3.1.6 draft migration."
ZERO_HASH = "0" * 64
CANONICAL_SHOT_SIZE_RE = re.compile(
    r"^(?:大远景|远景|中远景|全景|中全景|中景|中近景|近景|特写|大特写|极特写)"
    r"(?:→(?:大远景|远景|中远景|全景|中全景|中景|中近景|近景|特写|大特写|极特写))*$"
)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} 顶层必须是对象")
    return value


def safe_slug(data: Dict[str, Any]) -> str:
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    slug = source.get("delivery_slug")
    if isinstance(slug, str) and re.fullmatch(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
        return slug
    return "untitled-scene-001"


def unresolved_format_brief() -> Dict[str, Any]:
    return {
        "rhythm_profile": "unresolved",
        "target_runtime_seconds": 0,
        "aspect_ratio": "unresolved",
        "orientation": "unresolved",
        "dialogue_pace": {
            "standard_id": "unresolved",
            "pace_profile": "unresolved",
            "rate_basis": "unresolved",
            "range_min_cps": 0,
            "range_max_cps": 0,
            "default_cps": 0,
            "selected_cps": 0,
            "strong_pause_seconds": 0,
            "soft_pause_seconds": 0,
            "basis": "migration pending: Gate 0 dialogue pace must be confirmed",
            "overrides": [],
        },
        "coverage_bias": "migration pending: dialogue coverage bias must be selected",
        "confirmation_note": "migration pending: format brief is unresolved",
    }


def _validate_identity(shot_data: Dict[str, Any], workspace: Dict[str, Any]) -> None:
    expected = {
        "contract_name": "director-shot-data",
        "contract_version": "3.1.3",
        "source_skill": "su-fenjingskill",
        "source_skill_version": "3.1.3",
    }
    for key, value in expected.items():
        if shot_data.get(key) != value:
            raise ValueError(f"迁移输入 {key} 必须是 {value!r}")
    if workspace.get("workspace_contract") != "director-workspace/3.1.3":
        raise ValueError("--workspace 必须是 director-workspace/3.1.3")
    formal_text = normalize_text((shot_data.get("source") or {}).get("locked_text"))
    workspace_text = normalize_text((workspace.get("source") or {}).get("locked_text"))
    if not formal_text or formal_text != workspace_text:
        raise ValueError("3.1.3 workspace 与 shot data 的 locked_text 缺失或不一致")


def build_drafts(
    shot_data: Dict[str, Any], workspace: Dict[str, Any]
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    _validate_identity(shot_data, workspace)
    shot_draft = copy.deepcopy(shot_data)
    workspace_draft = copy.deepcopy(workspace)
    shot_draft["contract_version"] = "3.1.6"
    shot_draft["source_skill_version"] = "3.1.6"
    shot_draft["format_brief"] = unresolved_format_brief()
    timing_rebuilds: list[str] = []
    aspect_rebuilds: list[str] = []
    shot_size_term_rebuilds: list[str] = []
    for shot in shot_draft.get("shots", []):
        if not isinstance(shot, dict):
            continue
        shot_id = str(shot.get("shot_id", ""))
        camera = shot.get("camera") if isinstance(shot.get("camera"), dict) else {}
        if not CANONICAL_SHOT_SIZE_RE.fullmatch(normalize_text(camera.get("shot_size")).replace(" ", "")):
            camera["shot_size"] = "unresolved"
            shot_size_term_rebuilds.append(shot_id)
        camera["frame_axis"] = "unresolved"
        camera["aspect_ratio_reason"] = ""
        shot["timing_plan"] = {
            "status": "unresolved",
            "blocks": [],
            "computed_duration_seconds": 0,
            "confidence": "unresolved",
            "basis": "migration pending: timing blocks must be rebuilt from shot_flow and Gate 0 pace",
        }
        timing_rebuilds.append(shot_id)
        aspect_rebuilds.append(shot_id)
    shot_draft["validation"] = {
        "status": "draft",
        "warnings": [
            "MIGRATION_REVIEW_REQUIRED: Gate 0 format, rhythm, aspect ratio and dialogue pace are unresolved.",
            "MIGRATION_REVIEW_REQUIRED: every dialogue turn needs a new dialogue_edit_plan.",
            "MIGRATION_REVIEW_REQUIRED: frame-axis/aspect execution and timing blocks are unresolved.",
            "MIGRATION_REVIEW_REQUIRED: Gate 0, Gate 1, Gate 2 and Alignment are invalidated.",
        ],
    }

    workspace_draft["workspace_contract"] = "director-workspace/3.1.6"
    workspace_draft["format_brief"] = unresolved_format_brief()
    workspace_draft["gate_0"] = {
        "status": "invalidated",
        "format_hash": ZERO_HASH,
        "note": "3.1.3 migration requires Gate 0 confirmation",
    }
    dialogue_plan_rebuilds: list[str] = []
    for strategy in workspace_draft.get("scene_strategies", []):
        if not isinstance(strategy, dict):
            continue
        strategy["dialogue_edit_plan"] = []
        dialogue_plan_rebuilds.append(str(strategy.get("scene_id", "")))
        for unit in strategy.get("topology", []):
            if not isinstance(unit, dict):
                continue
            design = unit.get("viewing_design") if isinstance(unit.get("viewing_design"), dict) else {}
            design["frame_axis"] = "unresolved"
            design["aspect_ratio_fit"] = ""
    gate_one = workspace_draft.get("gate_1") if isinstance(workspace_draft.get("gate_1"), dict) else {}
    gate_one.update({
        "mode": "invalidated",
        "status": "invalidated",
        "method_hash": ZERO_HASH,
        "note": "3.1.3 to 3.1.6 migration requires renewed Gate 1",
    })
    workspace_draft["gate_1"] = gate_one
    review_lock = workspace_draft.get("review_lock") if isinstance(workspace_draft.get("review_lock"), dict) else {}
    for key in ("source_hash", "format_hash", "method_hash", "strategy_hash", "topology_hash", "source_model_hash", "execution_hash", "alignment_hash"):
        review_lock[key] = ZERO_HASH
    review_lock.update({
        "gate_0_status": "invalidated",
        "gate_0_note": "migration requires Gate 0",
        "gate_1_status": "invalidated",
        "gate_1_basis": "migration requires Gate 1",
        "gate_2_status": "invalidated",
        "gate_2_confirmation_note": "migration requires Gate 2",
        "alignment_status": "invalidated",
        "alignment_note": "migration requires renewed alignment",
    })
    workspace_draft["review_lock"] = review_lock
    workspace_draft["approval_events"] = []

    formal_schema_errors = validate_formal_schema(shot_draft)
    workspace_schema_errors = validate_workspace_schema(workspace_draft)
    report = {
        "migration": "director-shot-data/3.1.3 -> director-shot-data/3.1.6",
        "workspace_migration": "director-workspace/3.1.3 -> director-workspace/3.1.6",
        "status": "DRAFT_REVIEW_REQUIRED",
        "formal_ready": False,
        "schema_status": "VALID_MIGRATION_CARRIER" if not formal_schema_errors and not workspace_schema_errors else "SCHEMA_FAIL",
        "formal_schema_errors": formal_schema_errors,
        "workspace_schema_errors": workspace_schema_errors,
        "format_brief_rebuild_required": True,
        "dialogue_edit_plan_rebuild_required": dialogue_plan_rebuilds,
        "shot_timing_rebuild_required": timing_rebuilds,
        "shot_aspect_execution_rebuild_required": aspect_rebuilds,
        "shot_size_term_rebuild_required": shot_size_term_rebuilds,
        "review_stages_invalidated": ["gate_0", "gate_1", "gate_2", "alignment"],
        "next_steps": [
            "confirm rhythm profile, target runtime, aspect ratio, orientation and dialogue pace in Gate 0",
            "rebuild dialogue_edit_plan against every source dialogue turn",
            "reconfirm scene strategy, topology, camera grammar and aspect-ratio execution",
            "replace unresolved or non-standard shot-size wording with the canonical Chinese shot-size vocabulary",
            "rebuild timing blocks from shot_flow and approve Alignment before build-all",
        ],
    }
    return shot_draft, workspace_draft, report


def write_json_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def ensure_empty_target(path: Path) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f"迁移输出目录必须不存在或为空：{path}")
    path.mkdir(parents=True, exist_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="非覆盖迁移 3.1.3 到 3.1.6 审阅草稿。")
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
            "shot_data_draft": args.output_dir / f"{slug}-shot-data-3.1.6-draft.json",
            "workspace_draft": args.output_dir / f"{slug}-director-workspace-3.1.6-draft.json",
            "migration_report": args.output_dir / f"{slug}-migration-report.json",
        }
        write_json_new(paths["shot_data_draft"], shot_draft)
        write_json_new(paths["workspace_draft"], workspace_draft)
        write_json_new(paths["migration_report"], report)
        for key, path in paths.items():
            sys.stdout.write(f"{key}: {path}\n")
        sys.stdout.write("status: DRAFT_REVIEW_REQUIRED\n")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
