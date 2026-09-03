#!/usr/bin/env python3
"""Create non-overwriting 3.1.2 review drafts from historical 3.1.0 data.

The migrator is intentionally conservative. It preserves source and directing
content, removes fields that no longer exist in the 3.1.2 contract, and marks all
review evidence as invalidated. It never invents passages, facts, bindings, or
approval events, so its outputs cannot be mistaken for formal READY artifacts.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SCRIPT_INTERFACE = "file-read-write"
SCRIPT_INTERFACE_REASON = "Explicit non-overwriting migration into a caller-selected empty directory."
REMOVED_LEGACY_FIELDS = {"production_risks"}


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


def write_json_new(path: Path, value: Any) -> None:
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    except FileExistsError as exc:
        raise FileExistsError(f"拒绝覆盖已有文件：{path}") from exc


def safe_slug(data: Dict[str, Any]) -> str:
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    slug = source.get("delivery_slug")
    if isinstance(slug, str) and re.fullmatch(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
        return slug
    return "untitled-scene-001"


def zero_hash() -> str:
    return "0" * 64


def strip_removed_fields(value: Any) -> Any:
    """Return a deep copy without fields removed from the active 3.1.2 model."""
    if isinstance(value, dict):
        return {
            key: strip_removed_fields(item)
            for key, item in value.items()
            if key not in REMOVED_LEGACY_FIELDS
        }
    if isinstance(value, list):
        return [strip_removed_fields(item) for item in value]
    return copy.deepcopy(value)


def source_units_draft(locked_text: str) -> List[Dict[str, Any]]:
    """Build a lossless line ledger without declaring any line non-narrative.

    Every non-empty line defaults to performance authority and ``action``. A human
    must later refine dialogue/headings/transitions and create the semantic facts.
    This conservative default cannot silently remove narrative material.
    """
    units: List[Dict[str, Any]] = []
    for line_number, line in enumerate(locked_text.split("\n"), start=1):
        if not line.strip():
            continue
        units.append(
            {
                "unit_id": f"SU{len(units) + 1:03d}",
                "scope_id": "GLOBAL",
                "line_start": line_number,
                "line_end": line_number,
                "kind": "action",
                "language": "unresolved",
                "authority_role": "performance_authority",
                "exact_text": line,
                "semantic_summary": "migration pending: classify kind and register facts; narrative coverage remains mandatory",
            }
        )
    return units


def migrate_strategy(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    migrated = strip_removed_fields(value)
    for strategy in migrated:
        if not isinstance(strategy, dict):
            continue
        topology = strategy.get("topology")
        if not isinstance(topology, list):
            continue
        for unit in topology:
            if not isinstance(unit, dict):
                continue
            unit.pop("source_unit_ids", None)
            unit["source_passage_ids"] = []
            unit["source_fact_ids"] = []
    return migrated


def build_drafts(
    shot_data: Dict[str, Any], old_workspace: Optional[Dict[str, Any]]
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    if shot_data.get("contract_name") != "director-shot-data" or shot_data.get("contract_version") != "3.1.0":
        raise ValueError("迁移输入必须是 director-shot-data/3.1.0")
    if shot_data.get("source_skill") != "su-fenjingskill" or shot_data.get("source_skill_version") != "3.1.1":
        raise ValueError("迁移输入必须来自 su-fenjingskill 3.1.1")
    formal_source = shot_data.get("source") if isinstance(shot_data.get("source"), dict) else {}
    locked_text = normalize_text(formal_source.get("locked_text"))
    if not locked_text:
        raise ValueError("3.1.0 输入缺少 locked_text")
    if old_workspace is not None:
        if old_workspace.get("workspace_contract") != "director-workspace/3.1.0":
            raise ValueError("--workspace 必须是 director-workspace/3.1.0")
        old_source = old_workspace.get("source") if isinstance(old_workspace.get("source"), dict) else {}
        if normalize_text(old_source.get("locked_text")) != locked_text:
            raise ValueError("历史 workspace 与 shot-data locked_text 不一致")

    shot_draft = strip_removed_fields(shot_data)
    shot_draft["contract_version"] = "3.1.2"
    shot_draft["source_skill_version"] = "3.1.2"
    shot_draft["validation"] = {
        "status": "draft",
        "warnings": [
            "LEGACY_CONTRACT_REQUIRES_MIGRATION: 历史 source_excerpt 仅作为迁移证据，必须由 3.1.2 workspace 重新派生。",
            "missing evidence: language authority, passages, protected facts, shot bindings, approval-event chain, alignment review, and renewed Gate 2.",
        ],
    }

    nonempty_lines = [index for index, line in enumerate(locked_text.split("\n"), start=1) if line.strip()]
    authority_ranges = (
        [{"start_line": min(nonempty_lines), "end_line": max(nonempty_lines)}]
        if nonempty_lines
        else []
    )
    old_workspace_clean = strip_removed_fields(old_workspace) if old_workspace else {}
    workspace_draft: Dict[str, Any] = {
        "workspace_contract": "director-workspace/3.1.2",
        "source": {
            "locked_text": locked_text,
            "source_hash": hashlib.sha256(locked_text.encode("utf-8")).hexdigest(),
            "authority_policy": {
                "performance_authority": "unresolved",
                "reference_languages": [],
                "bilingual_relation": "independent",
                "authority_basis": "migration pending: source authority must be reviewed",
            },
            "scopes": [
                {
                    "scope_id": "GLOBAL",
                    "scope_kind": "global",
                    "authority_line_ranges": authority_ranges,
                    "reference_line_ranges": [],
                }
            ],
            "source_units": source_units_draft(locked_text),
            "classification_reviews": [],
            "source_gaps": [],
            "source_passages": [],
            "source_facts": [],
        },
        "supplemental_reference_facts": [],
        "assumption_obligations": [],
        "director_method": copy.deepcopy(old_workspace_clean.get("director_method", {})),
        "gate_1": copy.deepcopy(old_workspace_clean.get("gate_1", {})),
        "scene_strategies": migrate_strategy(old_workspace_clean.get("scene_strategies", [])),
        "shot_bindings": [],
        "director_inferences": [],
        "approval_events": [],
        "review_lock": {
            "source_hash": zero_hash(),
            "method_hash": zero_hash(),
            "strategy_hash": zero_hash(),
            "topology_hash": zero_hash(),
            "source_model_hash": zero_hash(),
            "execution_hash": zero_hash(),
            "alignment_hash": zero_hash(),
            "alignment_status": "pending",
            "alignment_note": "migration pending",
            "gate_1_status": "invalidated",
            "gate_1_basis": "3.1.0 migration invalidates prior source/method review evidence",
            "gate_2_status": "invalidated",
            "gate_2_confirmation_note": "3.1.2 passages, facts, bindings, and alignment require renewed confirmation",
        },
    }
    if isinstance(workspace_draft.get("gate_1"), dict):
        workspace_draft["gate_1"]["mode"] = "invalidated"
        workspace_draft["gate_1"]["status"] = "invalidated"
        workspace_draft["gate_1"]["method_hash"] = zero_hash()
        workspace_draft["gate_1"]["note"] = "3.1.0 migration requires renewed review"

    report = {
        "migration": "director-shot-data/3.1.0 -> director-shot-data/3.1.2",
        "status": "DRAFT_REVIEW_REQUIRED",
        "historical_input_preserved": True,
        "formal_ready": False,
        "removed_legacy_fields": sorted(REMOVED_LEGACY_FIELDS),
        "blocking_requirements": [
            "classify every source unit by authority language, scope, and kind",
            "create complete authoritative passages",
            "register protected source facts",
            "bind every formal shot and required fact",
            "separate director inferences and source-gap assumptions",
            "recompute source, method, strategy, topology, source-model, execution, and alignment hashes",
            "record Gate 1, Gate 2, and alignment approval events",
            "pass combined 3.1.2 validation before formal build-all",
        ],
        "missing_evidence": [
            "human semantic adjudication",
            "renewed Gate 1 and Gate 2 confirmation",
            "execution/source alignment approval",
        ],
    }
    return shot_draft, workspace_draft, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="非覆盖迁移 director-shot-data/3.1.0 到 3.1.2 审阅草稿。")
    parser.add_argument("--shot-data", type=Path, required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    stage: Path | None = None
    try:
        if args.output_dir.exists() and (not args.output_dir.is_dir() or any(args.output_dir.iterdir())):
            raise FileExistsError(f"迁移输出目录必须不存在或为空：{args.output_dir}")
        shot_data = load_json(args.shot_data)
        old_workspace = load_json(args.workspace) if args.workspace else None
        shot_draft, workspace_draft, report = build_drafts(shot_data, old_workspace)
        parent = args.output_dir.parent
        parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=f".{args.output_dir.name}-stage-", dir=str(parent)))
        slug = safe_slug(shot_data)
        staged_paths = {
            "shot_data_draft": stage / f"{slug}-shot-data-3.1.2-draft.json",
            "workspace_draft": stage / f"{slug}-director-workspace-3.1.2-draft.json",
            "migration_report": stage / f"{slug}-migration-report.json",
        }
        write_json_new(staged_paths["shot_data_draft"], shot_draft)
        write_json_new(staged_paths["workspace_draft"], workspace_draft)
        write_json_new(staged_paths["migration_report"], report)
        output_preexisted = args.output_dir.exists()
        if output_preexisted:
            args.output_dir.rmdir()
        try:
            os.replace(stage, args.output_dir)
            stage = None
        except Exception:
            if output_preexisted and not args.output_dir.exists():
                args.output_dir.mkdir(parents=False, exist_ok=False)
            raise
        paths = {label: args.output_dir / path.name for label, path in staged_paths.items()}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
        sys.stderr.write(f"FAIL: {exc}\n")
        return 2
    for label, path in paths.items():
        sys.stdout.write(f"{label}: {path}\n")
    sys.stdout.write("status: DRAFT_REVIEW_REQUIRED\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
