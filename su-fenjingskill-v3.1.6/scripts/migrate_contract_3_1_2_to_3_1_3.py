#!/usr/bin/env python3
"""Create non-overwriting 3.1.3 review drafts from valid 3.1.2 inputs.

The migration preserves source, scene, shot, duration, and legacy structured
execution facts. It deliberately does not infer the new ordered ``shot_flow``,
viewpoint/framing/visibility decisions, camera grammar, viewing design, or new
Gate-2 boundary evidence. All review stages are invalidated, so the generated
drafts cannot be mistaken for formal READY artifacts.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


SCRIPT_INTERFACE = "file-read-write"
SCRIPT_INTERFACE_REASON = "Explicit non-overwriting migration into a caller-selected empty directory."
ZERO_HASH = "0" * 64


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


def _validate_input_identity(shot_data: Dict[str, Any], workspace: Dict[str, Any]) -> None:
    expected_formal = {
        "contract_name": "director-shot-data",
        "contract_version": "3.1.2",
        "source_skill": "su-fenjingskill",
        "source_skill_version": "3.1.2",
    }
    for key, expected in expected_formal.items():
        if shot_data.get(key) != expected:
            raise ValueError(f"迁移输入 {key} 必须是 {expected!r}")
    if workspace.get("workspace_contract") != "director-workspace/3.1.2":
        raise ValueError("--workspace 必须是 director-workspace/3.1.2")
    formal_source = shot_data.get("source") if isinstance(shot_data.get("source"), dict) else {}
    workspace_source = workspace.get("source") if isinstance(workspace.get("source"), dict) else {}
    locked_text = normalize_text(formal_source.get("locked_text"))
    if not locked_text:
        raise ValueError("3.1.2 shot data 缺少 locked_text")
    if normalize_text(workspace_source.get("locked_text")) != locked_text:
        raise ValueError("3.1.2 workspace 与 shot data 的 locked_text 不一致")


def build_drafts(
    shot_data: Dict[str, Any], workspace: Dict[str, Any]
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Return independent 3.1.3 drafts and a complete rebuild report."""
    _validate_input_identity(shot_data, workspace)
    shot_draft = copy.deepcopy(shot_data)
    workspace_draft = copy.deepcopy(workspace)

    shot_draft["contract_version"] = "3.1.3"
    shot_draft["source_skill_version"] = "3.1.3"
    shot_ids_requiring_flow: list[str] = []
    shot_camera_rebuilds: list[Dict[str, Any]] = []
    shots = shot_draft.get("shots") if isinstance(shot_draft.get("shots"), list) else []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        shot_id = str(shot.get("shot_id", ""))
        motivation = shot.get("motivation") if isinstance(shot.get("motivation"), dict) else {}
        motivation.pop("cut_or_hold_reason", None)
        edit = shot.get("edit") if isinstance(shot.get("edit"), dict) else {}
        edit.pop("reason", None)
        # These fields did not exist in 3.1.2. A schema-valid migration carrier
        # uses the contract's explicit unresolved state; it never copies mixed
        # newer keys or invents a directing decision.
        shot["viewpoint"] = {
            "owner_type": "unresolved",
            "owner_refs": [],
            "reading_priority": "unresolved",
            "camera_response": "unresolved",
            "reason": "",
        }
        camera = shot.get("camera") if isinstance(shot.get("camera"), dict) else {}
        camera.update(
            {
                "framing_mode": "unresolved",
                "primary_subjects": [],
                "foreground_subjects": [],
                "shot_size_reason": "",
                "angle_reason": "",
            }
        )
        staging = shot.get("staging") if isinstance(shot.get("staging"), dict) else {}
        staging.update({"visible_subjects": [], "offscreen_subjects": []})
        shot["shot_flow"] = []
        shot_ids_requiring_flow.append(shot_id)
        shot_camera_rebuilds.append(
            {
                "shot_id": shot_id,
                "required_fields": [
                    "viewpoint",
                    "camera.framing_mode",
                    "camera.primary_subjects",
                    "camera.foreground_subjects",
                    "camera.shot_size_reason",
                    "camera.angle_reason",
                    "staging.visible_subjects",
                    "staging.offscreen_subjects",
                ],
            }
        )
    shot_draft["validation"] = {
        "status": "draft",
        "warnings": [
            "MIGRATION_REVIEW_REQUIRED: shot_flow 尚未重建，当前数据不得作为正式交付。",
            "MIGRATION_REVIEW_REQUIRED: unresolved viewpoint、framing 与画内外主体尚未重建。",
            "MIGRATION_SEMANTIC_BLOCK: 草稿结构合法，但 unresolved 摄影决定不得进入正式构建。",
            "MIGRATION_REVIEW_REQUIRED: Gate 1、Gate 2 与 Alignment 已全部失效。",
        ],
    }

    workspace_draft["workspace_contract"] = "director-workspace/3.1.3"
    boundary_rebuilds: list[Dict[str, str]] = []
    strategies = (
        workspace_draft.get("scene_strategies")
        if isinstance(workspace_draft.get("scene_strategies"), list)
        else []
    )
    for strategy in strategies:
        if not isinstance(strategy, dict):
            continue
        strategy["camera_grammar"] = {
            "dominant_principle": "",
            "change_triggers": [],
            "progression": "",
            "uniformity_intent": "",
        }
        topology = strategy.get("topology") if isinstance(strategy.get("topology"), list) else []
        for unit_index, unit in enumerate(topology):
            if not isinstance(unit, dict):
                continue
            unit["viewing_design"] = {
                "owner_type": "unresolved",
                "owner_refs": [],
                "visible_subjects": [],
                "offscreen_subjects": [],
                "reading_priority": "unresolved",
                "framing_intent": "unresolved",
                "camera_response": "unresolved",
                "reason": "",
            }
            unit.pop("inter_shot_relation", None)
            unit.pop("boundary_reason", None)
            unit.pop("boundary_to_next", None)
            if unit_index < len(topology) - 1:
                boundary_rebuilds.append(
                    {
                        "scene_id": str(strategy.get("scene_id", "")),
                        "unit_id": str(unit.get("unit_id", "")),
                        "next_unit_id": str(topology[unit_index + 1].get("unit_id", ""))
                        if isinstance(topology[unit_index + 1], dict)
                        else "",
                    }
                )

    gate_one = workspace_draft.get("gate_1")
    if not isinstance(gate_one, dict):
        gate_one = {}
        workspace_draft["gate_1"] = gate_one
    gate_one.update(
        {
            "mode": "invalidated",
            "status": "invalidated",
            "method_hash": ZERO_HASH,
            "note": "3.1.2 to 3.1.3 migration requires renewed Gate 1 review",
        }
    )
    review_lock = workspace_draft.get("review_lock")
    if not isinstance(review_lock, dict):
        review_lock = {}
        workspace_draft["review_lock"] = review_lock
    for hash_key in (
        "source_hash",
        "method_hash",
        "strategy_hash",
        "topology_hash",
        "source_model_hash",
        "execution_hash",
        "alignment_hash",
    ):
        review_lock[hash_key] = ZERO_HASH
    review_lock.update(
        {
            "gate_1_status": "invalidated",
            "gate_1_basis": "3.1.3 contract migration requires renewed method confirmation",
            "gate_2_status": "invalidated",
            "gate_2_confirmation_note": "boundary_to_next must be rebuilt and confirmed without inference",
            "alignment_status": "invalidated",
            "alignment_note": "shot_flow and execution/source alignment require renewed review",
        }
    )

    report = {
        "migration": "director-shot-data/3.1.2 -> director-shot-data/3.1.3",
        "workspace_migration": "director-workspace/3.1.2 -> director-workspace/3.1.3",
        "status": "DRAFT_REVIEW_REQUIRED",
        "historical_input_preserved": True,
        "formal_ready": False,
        "preserved_facts": [
            "locked source and dialogue inventory",
            "assumptions and director design",
            "scenes, shots, duration, camera, staging, sound, edit entry/exit, and continuity",
            "source ledger, passages, facts, shot bindings, and director inferences",
        ],
        "removed_redundant_fields": [
            "shots[].motivation.cut_or_hold_reason",
            "shots[].edit.reason",
            "scene_strategies[].topology[].inter_shot_relation",
            "scene_strategies[].topology[].boundary_reason",
        ],
        "shot_flow_rebuild_required": shot_ids_requiring_flow,
        "shot_viewing_rebuild_required": shot_camera_rebuilds,
        "workspace_camera_grammar_rebuild_required": [
            str(strategy.get("scene_id", ""))
            for strategy in strategies
            if isinstance(strategy, dict)
        ],
        "workspace_viewing_design_rebuild_required": [
            {
                "scene_id": str(strategy.get("scene_id", "")),
                "unit_id": str(unit.get("unit_id", "")),
            }
            for strategy in strategies
            if isinstance(strategy, dict)
            for unit in (
                strategy.get("topology")
                if isinstance(strategy.get("topology"), list)
                else []
            )
            if isinstance(unit, dict)
        ],
        "boundary_to_next_rebuild_required": boundary_rebuilds,
        "schema_status": "VALID_MIGRATION_CARRIER",
        "invalidated_reviews": ["Gate 1", "Gate 2", "Alignment"],
        "blocking_requirements": [
            "author each shot_flow from existing backend facts in actual playback order",
            "author each shot viewpoint, framing mode, primary/foreground subjects, visibility, and shot-size/angle reasons without inference from legacy defaults",
            "author each scene camera_grammar and each topology unit viewing_design from renewed directing review",
            "author relation, concrete trigger, and concrete editorial_gain for every non-terminal topology unit",
            "renew Gate 1, Gate 2, and Alignment approvals against 3.1.3 hashes",
            "pass combined 3.1.3 schema and semantic validation before build-all",
        ],
    }
    return shot_draft, workspace_draft, report


def write_json_new(path: Path, value: Any) -> None:
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    except FileExistsError as exc:
        raise FileExistsError(f"拒绝覆盖已有文件：{path}") from exc


def _remove_created_files(paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="非覆盖迁移 3.1.2 到 3.1.3 审阅草稿。")
    parser.add_argument("--shot-data", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    created_paths: list[Path] = []
    created_output_dir = False
    try:
        if args.output_dir.exists():
            if not args.output_dir.is_dir() or any(args.output_dir.iterdir()):
                raise FileExistsError(f"迁移输出目录必须不存在或为空：{args.output_dir}")
        else:
            args.output_dir.mkdir(parents=True, exist_ok=False)
            created_output_dir = True
        shot_data = load_json(args.shot_data)
        workspace = load_json(args.workspace)
        shot_draft, workspace_draft, report = build_drafts(shot_data, workspace)
        slug = safe_slug(shot_data)
        paths = {
            "shot_data_draft": args.output_dir / f"{slug}-shot-data-3.1.3-draft.json",
            "workspace_draft": args.output_dir / f"{slug}-director-workspace-3.1.3-draft.json",
            "migration_report": args.output_dir / f"{slug}-migration-report.json",
        }
        for label, value in (
            ("shot_data_draft", shot_draft),
            ("workspace_draft", workspace_draft),
            ("migration_report", report),
        ):
            write_json_new(paths[label], value)
            created_paths.append(paths[label])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _remove_created_files(created_paths)
        if created_output_dir:
            try:
                args.output_dir.rmdir()
            except OSError:
                pass
        sys.stderr.write(f"FAIL: {exc}\n")
        return 2
    for label, path in paths.items():
        sys.stdout.write(f"{label}: {path}\n")
    sys.stdout.write("status: DRAFT_REVIEW_REQUIRED\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
