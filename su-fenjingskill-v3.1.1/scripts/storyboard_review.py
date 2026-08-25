#!/usr/bin/env python3
"""Internal source, director-method, and Gate review for su-fenjingskill 3.1.1.

director-workspace/3.1.0 is an internal audit carrier. It never becomes a fifth
formal delivery file and never decides artistic value through shot statistics.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


WORKSPACE_CONTRACT = "director-workspace/3.1.0"
FORMAL_CONTRACT_NAME = "director-shot-data"
FORMAL_CONTRACT_VERSION = "3.1.0"
FORMAL_SOURCE_SKILL = "su-fenjingskill"
FORMAL_SOURCE_SKILL_VERSION = "3.1.1"

MECHANISMS = {
    "relationship_accumulation",
    "information_suspense",
    "offscreen_threat",
    "comedy_setup_payoff",
    "action_causality",
    "ensemble_power",
    "ritual_repetition",
    "montage_music_concept",
    "subjective_memory",
    "spectacle_discovery",
}
SOURCE_KINDS = {
    "scene_heading",
    "action",
    "dialogue",
    "stage_direction",
    "source_sound",
    "transition",
    "metadata",
}
COVERAGE_STATUSES = {"covered", "intentionally_withheld", "intentionally_omitted"}
GATE_ONE_MODES = {"user_specified", "confirmed", "required", "invalidated"}
INTRA_OPERATIONS = {
    "hold",
    "blocking_recompose",
    "camera_reframe",
    "focus_shift",
    "light_shift",
    "sound_shift",
}
INTER_RELATIONS = {
    "cut",
    "reaction_cut",
    "action_cut",
    "gaze_cut",
    "match_cut",
    "jump_cut",
    "ellipsis",
    "intercut",
    "montage",
    "sound_lead",
    "sound_lag",
    "sound_bridge",
    "sound_break",
    "dissolve",
    "fade",
    "scene_transition",
    "scene_end",
}
METHOD_STRING_FIELDS = (
    "method_id",
    "method_name",
    "reference_source",
    "applicability",
    "time_model",
    "base_editing_unit",
    "boundary_priorities",
    "hold_policy",
    "montage_intercut_policy",
    "viewpoint_knowledge",
    "space_reveal",
    "performance_editing",
    "camera_agency",
    "sound_image_relation",
    "continuity_attitude",
    "mechanism_adaptation",
    "exception_conditions",
)
METHOD_LIST_FIELDS = ("preferred_patterns", "avoid_patterns")
STRATEGY_STRING_FIELDS = (
    "scene_id",
    "entry_state",
    "exit_state",
    "dramatic_task",
    "turn_or_progression",
    "audience_knowledge_path",
    "blocking_space_strategy",
    "time_edit_structure",
    "shot_density_curve",
    "performance_strategy",
    "sound_strategy",
    "opening_function",
    "turn_function",
    "ending_function",
    "method_application",
    "conflict_resolution",
)
STRATEGY_LIST_FIELDS = (
    "protected_processes",
    "required_clarity",
    "failure_risks",
)
BOUNDARY_FIELDS = (
    "source_change",
    "mechanism_need",
    "method_basis",
    "alternative_rejected",
)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def text_hash(value: Any) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def make_issue(code: str, path: str, message: str) -> Dict[str, str]:
    return {"code": code, "path": path, "message": message}


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonempty_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def strategy_payload(scene_strategies: Any) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    if not isinstance(scene_strategies, list):
        return payload
    for strategy in scene_strategies:
        if not isinstance(strategy, dict):
            continue
        item = {key: copy.deepcopy(value) for key, value in strategy.items() if key != "topology"}
        payload.append(item)
    return payload


def topology_payload(scene_strategies: Any) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    if not isinstance(scene_strategies, list):
        return payload
    for strategy in scene_strategies:
        if not isinstance(strategy, dict):
            continue
        payload.append(
            {
                "scene_id": strategy.get("scene_id"),
                "topology": copy.deepcopy(strategy.get("topology", [])),
            }
        )
    return payload


def expected_hashes(workspace: Dict[str, Any]) -> Dict[str, str]:
    source = workspace.get("source") if isinstance(workspace.get("source"), dict) else {}
    method = workspace.get("director_method") if isinstance(workspace.get("director_method"), dict) else {}
    strategies = workspace.get("scene_strategies")
    return {
        "source_hash": text_hash(source.get("locked_text")),
        "method_hash": canonical_hash(method),
        "strategy_hash": canonical_hash(strategy_payload(strategies)),
        "topology_hash": canonical_hash(topology_payload(strategies)),
    }


def lock_workspace(workspace: Any) -> Dict[str, Any]:
    if not isinstance(workspace, dict):
        raise ValueError("workspace 顶层必须是对象")
    locked = copy.deepcopy(workspace)
    hashes = expected_hashes(locked)
    source = locked.setdefault("source", {})
    if not isinstance(source, dict):
        raise ValueError("workspace.source 必须是对象")
    source["source_hash"] = hashes["source_hash"]
    gate_one = locked.setdefault("gate_1", {})
    if not isinstance(gate_one, dict):
        raise ValueError("workspace.gate_1 必须是对象")
    gate_one["method_hash"] = hashes["method_hash"]
    review_lock = locked.setdefault("review_lock", {})
    if not isinstance(review_lock, dict):
        raise ValueError("workspace.review_lock 必须是对象")
    review_lock.update(hashes)
    return locked


def validate_workspace(workspace: Any, shot_data: Any) -> Dict[str, Any]:
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    if not isinstance(workspace, dict):
        errors.append(make_issue("WORKSPACE_NOT_OBJECT", "$", "director workspace 顶层必须是对象。"))
        return report(errors, warnings, {})
    if not isinstance(shot_data, dict):
        errors.append(make_issue("SHOT_DATA_NOT_OBJECT", "shot_data", "正式 shot data 顶层必须是对象。"))
        return report(errors, warnings, {})

    if workspace.get("workspace_contract") != WORKSPACE_CONTRACT:
        errors.append(
            make_issue(
                "WORKSPACE_CONTRACT_MISMATCH",
                "workspace_contract",
                "内部工作区必须使用 director-workspace/3.1.0。",
            )
        )

    expected_formal = {
        "contract_name": FORMAL_CONTRACT_NAME,
        "contract_version": FORMAL_CONTRACT_VERSION,
        "source_skill": FORMAL_SOURCE_SKILL,
        "source_skill_version": FORMAL_SOURCE_SKILL_VERSION,
    }
    for key, expected in expected_formal.items():
        if shot_data.get(key) != expected:
            errors.append(
                make_issue(
                    "FORMAL_CONTRACT_MISMATCH",
                    "shot_data." + key,
                    "正式交付字段 {} 必须保持 {!r}。".format(key, expected),
                )
            )

    formal_source = shot_data.get("source") if isinstance(shot_data.get("source"), dict) else {}
    workspace_source = workspace.get("source") if isinstance(workspace.get("source"), dict) else {}
    locked_text = normalize_text(workspace_source.get("locked_text"))
    formal_locked_text = normalize_text(formal_source.get("locked_text"))
    if not locked_text:
        errors.append(make_issue("LOCKED_TEXT_EMPTY", "source.locked_text", "内部锁定来源为空。"))
    if locked_text != formal_locked_text:
        errors.append(
            make_issue(
                "FORMAL_SOURCE_DIVERGED",
                "shot_data.source.locked_text",
                "正式 shot data 与内部工作区的 locked_text 不一致。",
            )
        )

    formal_scenes = shot_data.get("scenes") if isinstance(shot_data.get("scenes"), list) else []
    formal_shots = shot_data.get("shots") if isinstance(shot_data.get("shots"), list) else []
    formal_dialogues = (
        formal_source.get("dialogue_lines")
        if isinstance(formal_source.get("dialogue_lines"), list)
        else []
    )
    scene_ids = {
        item.get("scene_id")
        for item in formal_scenes
        if isinstance(item, dict) and nonempty(item.get("scene_id"))
    }
    shot_ids = {
        item.get("shot_id")
        for item in formal_shots
        if isinstance(item, dict) and nonempty(item.get("shot_id"))
    }
    dialogue_map = {
        item.get("dialogue_id"): item
        for item in formal_dialogues
        if isinstance(item, dict) and nonempty(item.get("dialogue_id"))
    }

    hashes = expected_hashes(workspace)
    stored_source_hash = workspace_source.get("source_hash")
    if stored_source_hash != hashes["source_hash"]:
        errors.append(
            make_issue(
                "SOURCE_LOCK_INVALIDATED",
                "source.source_hash",
                "locked_text 已变化；Gate 1 和 Gate 2 必须失效并重新审阅。",
            )
        )

    source_units = (
        workspace_source.get("source_units")
        if isinstance(workspace_source.get("source_units"), list)
        else []
    )
    if not source_units:
        errors.append(make_issue("SOURCE_UNITS_EMPTY", "source.source_units", "缺少反向来源单元。"))

    source_lines = locked_text.split("\n") if locked_text else []
    covered_lines: Set[int] = set()
    unit_ids: Set[str] = set()
    valid_unit_ids: Set[str] = set()
    source_kind_counts: Counter = Counter()

    for index, unit in enumerate(source_units):
        path = "source.source_units[{}]".format(index)
        if not isinstance(unit, dict):
            errors.append(make_issue("SOURCE_UNIT_INVALID", path, "source unit 必须是对象。"))
            continue
        unit_id = unit.get("unit_id")
        if not nonempty(unit_id):
            errors.append(make_issue("SOURCE_UNIT_ID_EMPTY", path + ".unit_id", "source unit ID 为空。"))
        elif unit_id in unit_ids:
            errors.append(make_issue("SOURCE_UNIT_ID_DUPLICATE", path + ".unit_id", "source unit ID 重复。"))
        else:
            unit_ids.add(unit_id)
            valid_unit_ids.add(unit_id)

        scene_id = unit.get("scene_id")
        if scene_id not in scene_ids:
            errors.append(make_issue("SOURCE_UNIT_SCENE_UNKNOWN", path + ".scene_id", "source unit 引用不存在的正式场景。"))

        kind = unit.get("kind")
        if kind not in SOURCE_KINDS:
            errors.append(make_issue("SOURCE_UNIT_KIND_INVALID", path + ".kind", "source unit kind 无效。"))
        else:
            source_kind_counts[kind] += 1

        line_start = unit.get("line_start")
        line_end = unit.get("line_end")
        if (
            not isinstance(line_start, int)
            or isinstance(line_start, bool)
            or not isinstance(line_end, int)
            or isinstance(line_end, bool)
            or line_start < 1
            or line_end < line_start
            or line_end > len(source_lines)
        ):
            errors.append(make_issue("SOURCE_UNIT_RANGE_INVALID", path, "source unit 行范围无效。"))
        else:
            actual_text = normalize_text("\n".join(source_lines[line_start - 1 : line_end]))
            if normalize_text(unit.get("exact_text")) != actual_text:
                errors.append(
                    make_issue(
                        "SOURCE_UNIT_TEXT_MISMATCH",
                        path + ".exact_text",
                        "source unit exact_text 与 locked_text 行范围不一致。",
                    )
                )
            for line_number in range(line_start, line_end + 1):
                if source_lines[line_number - 1].strip():
                    covered_lines.add(line_number)

        if not nonempty(unit.get("semantic_summary")):
            errors.append(make_issue("SOURCE_UNIT_SUMMARY_EMPTY", path + ".semantic_summary", "source unit 缺少语义摘要。"))

        coverage_status = unit.get("coverage_status")
        if coverage_status not in COVERAGE_STATUSES:
            errors.append(make_issue("SOURCE_COVERAGE_STATUS_INVALID", path + ".coverage_status", "覆盖状态无效。"))
        shot_refs = unit.get("shot_refs")
        if not isinstance(shot_refs, list):
            errors.append(make_issue("SOURCE_SHOT_REFS_INVALID", path + ".shot_refs", "shot_refs 必须是数组。"))
            shot_refs = []
        unknown_shots = [shot_id for shot_id in shot_refs if shot_id not in shot_ids]
        if unknown_shots:
            errors.append(
                make_issue(
                    "SOURCE_SHOT_REF_UNKNOWN",
                    path + ".shot_refs",
                    "source unit 引用不存在镜头：{}。".format(", ".join(map(str, unknown_shots))),
                )
            )
        if coverage_status == "covered" and not shot_refs:
            errors.append(make_issue("SOURCE_UNIT_UNCOVERED", path + ".shot_refs", "covered 单元必须引用至少一个正式镜头。"))
        if coverage_status in {"intentionally_withheld", "intentionally_omitted"} and not nonempty(unit.get("reason")):
            errors.append(make_issue("SOURCE_OMISSION_REASON_EMPTY", path + ".reason", "有意隐藏或省略必须说明导演理由。"))

        if kind == "dialogue":
            dialogue_id = unit.get("dialogue_id")
            if dialogue_id not in dialogue_map:
                errors.append(
                    make_issue(
                        "SOURCE_DIALOGUE_NOT_REGISTERED",
                        path + ".dialogue_id",
                        "来源对白没有进入正式 dialogue inventory。",
                    )
                )
            else:
                dialogue = dialogue_map[dialogue_id]
                dialogue_text = normalize_text(dialogue.get("text"))
                if dialogue_text and dialogue_text not in normalize_text(unit.get("exact_text")):
                    errors.append(
                        make_issue(
                            "SOURCE_DIALOGUE_TEXT_MISMATCH",
                            path + ".exact_text",
                            "正式对白未逐字出现在对应来源单元中。",
                        )
                    )
                unit_speaker = unit.get("speaker")
                if nonempty(unit_speaker) and unit_speaker != dialogue.get("speaker"):
                    errors.append(
                        make_issue(
                            "SOURCE_DIALOGUE_SPEAKER_MISMATCH",
                            path + ".speaker",
                            "内部来源说话者与正式 dialogue inventory 不一致。",
                        )
                    )

    uncovered_lines = [
        index
        for index, line in enumerate(source_lines, start=1)
        if line.strip() and index not in covered_lines
    ]
    if uncovered_lines:
        errors.append(
            make_issue(
                "SOURCE_LINES_UNCOVERED",
                "source.source_units",
                "非空来源行未进入内部审计：{}。".format(", ".join(map(str, uncovered_lines))),
            )
        )

    method = workspace.get("director_method")
    if not isinstance(method, dict):
        errors.append(make_issue("DIRECTOR_METHOD_MISSING", "director_method", "缺少导演方法合同。"))
        method = {}
    for field in METHOD_STRING_FIELDS:
        if not nonempty(method.get(field)):
            errors.append(make_issue("DIRECTOR_METHOD_FIELD_EMPTY", "director_method." + field, "导演方法字段为空。"))
    for field in METHOD_LIST_FIELDS:
        if not nonempty_string_list(method.get(field)):
            errors.append(make_issue("DIRECTOR_METHOD_LIST_EMPTY", "director_method." + field, "导演方法列表必须包含具体项目。"))

    gate_one = workspace.get("gate_1")
    if not isinstance(gate_one, dict):
        errors.append(make_issue("GATE_1_MISSING", "gate_1", "缺少 Gate 1 记录。"))
        gate_one = {}
    if gate_one.get("mode") not in GATE_ONE_MODES:
        errors.append(make_issue("GATE_1_MODE_INVALID", "gate_1.mode", "Gate 1 mode 无效。"))
    if gate_one.get("mode") not in {"user_specified", "confirmed"} or gate_one.get("status") != "passed":
        errors.append(make_issue("GATE_1_REQUIRED", "gate_1", "导演方法尚未满足自适应 Gate 1。"))
    if gate_one.get("method_hash") != hashes["method_hash"]:
        errors.append(
            make_issue(
                "GATE_1_INVALIDATED",
                "gate_1.method_hash",
                "导演方法已变化；Gate 1 和 Gate 2 必须重新审阅。",
            )
        )
    if not nonempty(gate_one.get("note")):
        errors.append(make_issue("GATE_1_NOTE_EMPTY", "gate_1.note", "Gate 1 缺少用户指定依据或确认说明。"))

    scene_strategies = workspace.get("scene_strategies")
    if not isinstance(scene_strategies, list) or not scene_strategies:
        errors.append(make_issue("SCENE_STRATEGIES_EMPTY", "scene_strategies", "至少需要一个场级策略。"))
        scene_strategies = []

    strategy_scene_ids: Set[str] = set()
    topology_unit_ids: Set[str] = set()
    topology_shot_refs: List[str] = []
    for index, strategy in enumerate(scene_strategies):
        path = "scene_strategies[{}]".format(index)
        if not isinstance(strategy, dict):
            errors.append(make_issue("SCENE_STRATEGY_INVALID", path, "场级策略必须是对象。"))
            continue
        scene_id = strategy.get("scene_id")
        if scene_id not in scene_ids:
            errors.append(make_issue("STRATEGY_SCENE_UNKNOWN", path + ".scene_id", "场级策略引用不存在的正式场景。"))
        if scene_id in strategy_scene_ids:
            errors.append(make_issue("STRATEGY_SCENE_DUPLICATE", path + ".scene_id", "同一场景存在重复策略。"))
        elif nonempty(scene_id):
            strategy_scene_ids.add(scene_id)

        for field in STRATEGY_STRING_FIELDS:
            if not nonempty(strategy.get(field)):
                errors.append(make_issue("SCENE_STRATEGY_FIELD_EMPTY", path + "." + field, "场级策略字段为空。"))
        for field in STRATEGY_LIST_FIELDS:
            if not nonempty_string_list(strategy.get(field)):
                errors.append(make_issue("SCENE_STRATEGY_LIST_EMPTY", path + "." + field, "场级策略列表必须包含具体项目。"))
        primary = strategy.get("primary_mechanism")
        secondary = strategy.get("secondary_mechanism")
        if primary not in MECHANISMS:
            errors.append(make_issue("PRIMARY_MECHANISM_INVALID", path + ".primary_mechanism", "主机制无效。"))
        if secondary is not None and secondary not in MECHANISMS:
            errors.append(make_issue("SECONDARY_MECHANISM_INVALID", path + ".secondary_mechanism", "辅机制无效。"))
        if secondary is not None and secondary == primary:
            errors.append(make_issue("MECHANISM_DUPLICATE", path + ".secondary_mechanism", "主辅机制不得相同。"))

        topology = strategy.get("topology")
        if not isinstance(topology, list) or not topology:
            errors.append(make_issue("TOPOLOGY_EMPTY", path + ".topology", "Gate 2 必须确认镜头拓扑。"))
            topology = []
        for topology_index, unit in enumerate(topology):
            unit_path = "{}.topology[{}]".format(path, topology_index)
            if not isinstance(unit, dict):
                errors.append(make_issue("TOPOLOGY_UNIT_INVALID", unit_path, "拓扑单元必须是对象。"))
                continue
            topology_id = unit.get("unit_id")
            if not nonempty(topology_id):
                errors.append(make_issue("TOPOLOGY_ID_EMPTY", unit_path + ".unit_id", "拓扑单元 ID 为空。"))
            elif topology_id in topology_unit_ids:
                errors.append(make_issue("TOPOLOGY_ID_DUPLICATE", unit_path + ".unit_id", "拓扑单元 ID 重复。"))
            else:
                topology_unit_ids.add(topology_id)

            refs = unit.get("shot_refs")
            if not isinstance(refs, list) or not refs:
                errors.append(make_issue("TOPOLOGY_SHOT_REFS_EMPTY", unit_path + ".shot_refs", "拓扑单元必须引用正式镜头。"))
                refs = []
            for shot_id in refs:
                if shot_id not in shot_ids:
                    errors.append(make_issue("TOPOLOGY_SHOT_UNKNOWN", unit_path + ".shot_refs", "拓扑引用不存在的正式镜头。"))
                else:
                    topology_shot_refs.append(shot_id)

            source_refs = unit.get("source_unit_ids")
            if not isinstance(source_refs, list) or not source_refs:
                errors.append(make_issue("TOPOLOGY_SOURCE_REFS_EMPTY", unit_path + ".source_unit_ids", "拓扑单元必须引用来源单元。"))
            else:
                unknown_source_units = [ref for ref in source_refs if ref not in valid_unit_ids]
                if unknown_source_units:
                    errors.append(make_issue("TOPOLOGY_SOURCE_UNKNOWN", unit_path + ".source_unit_ids", "拓扑引用不存在的来源单元。"))

            intra = unit.get("intra_shot_operations")
            if not isinstance(intra, list) or any(item not in INTRA_OPERATIONS for item in intra):
                errors.append(make_issue("INTRA_OPERATION_INVALID", unit_path + ".intra_shot_operations", "镜内操作无效。"))
            relation = unit.get("inter_shot_relation")
            if relation not in INTER_RELATIONS:
                errors.append(make_issue("INTER_RELATION_INVALID", unit_path + ".inter_shot_relation", "镜间关系无效。"))
            if topology_index < len(topology) - 1 and relation == "scene_end":
                errors.append(make_issue("PREMATURE_SCENE_END", unit_path + ".inter_shot_relation", "非末拓扑单元不得使用 scene_end。"))
            if topology_index == len(topology) - 1 and relation not in {"scene_end", "scene_transition"}:
                warnings.append(
                    make_issue(
                        "SCENE_BOUNDARY_REVIEW",
                        unit_path + ".inter_shot_relation",
                        "末拓扑单元建议明确 scene_end 或 scene_transition。",
                    )
                )

            boundary_reason = unit.get("boundary_reason")
            if not isinstance(boundary_reason, dict):
                errors.append(make_issue("BOUNDARY_REASON_MISSING", unit_path + ".boundary_reason", "缺少核心边界理由。"))
            else:
                for field in BOUNDARY_FIELDS:
                    if not nonempty(boundary_reason.get(field)):
                        errors.append(make_issue("BOUNDARY_REASON_EMPTY", unit_path + ".boundary_reason." + field, "边界理由字段为空。"))

    missing_scene_strategies = sorted(scene_ids - strategy_scene_ids)
    extra_scene_strategies = sorted(strategy_scene_ids - scene_ids)
    if missing_scene_strategies or extra_scene_strategies:
        errors.append(
            make_issue(
                "SCENE_STRATEGY_PARITY",
                "scene_strategies",
                "正式场景与内部策略不一致；缺少 {}，多出 {}。".format(
                    missing_scene_strategies, extra_scene_strategies
                ),
            )
        )

    shot_ref_counts = Counter(topology_shot_refs)
    missing_topology_shots = sorted(shot_ids - set(shot_ref_counts))
    duplicate_topology_shots = sorted(
        shot_id for shot_id, count in shot_ref_counts.items() if count > 1
    )
    if missing_topology_shots:
        errors.append(
            make_issue(
                "FORMAL_SHOTS_OUTSIDE_TOPOLOGY",
                "scene_strategies[].topology",
                "正式镜头未进入已确认拓扑：{}。".format(", ".join(missing_topology_shots)),
            )
        )
    if duplicate_topology_shots:
        errors.append(
            make_issue(
                "FORMAL_SHOTS_MULTI_BOUND",
                "scene_strategies[].topology",
                "正式镜头被多个拓扑单元重复绑定：{}。".format(", ".join(duplicate_topology_shots)),
            )
        )

    review_lock = workspace.get("review_lock")
    if not isinstance(review_lock, dict):
        errors.append(make_issue("REVIEW_LOCK_MISSING", "review_lock", "缺少 review lock。"))
        review_lock = {}
    for key in ("source_hash", "method_hash"):
        if review_lock.get(key) != hashes[key]:
            errors.append(
                make_issue(
                    "GATE_1_INVALIDATED",
                    "review_lock." + key,
                    "{} 已变化；Gate 1 和 Gate 2 必须重新审阅。".format(key),
                )
            )
    for key in ("strategy_hash", "topology_hash"):
        if review_lock.get(key) != hashes[key]:
            errors.append(
                make_issue(
                    "GATE_2_INVALIDATED",
                    "review_lock." + key,
                    "{} 已变化；Gate 2 必须重新确认。".format(key),
                )
            )
    if review_lock.get("gate_1_status") != "passed":
        errors.append(make_issue("REVIEW_LOCK_GATE_1_NOT_PASSED", "review_lock.gate_1_status", "review lock 中 Gate 1 未通过。"))
    if review_lock.get("gate_2_status") != "confirmed":
        errors.append(make_issue("GATE_2_REQUIRED", "review_lock.gate_2_status", "所有新正式交付必须先确认 Gate 2。"))
    if not nonempty(review_lock.get("gate_1_basis")):
        errors.append(make_issue("GATE_1_BASIS_EMPTY", "review_lock.gate_1_basis", "review lock 缺少 Gate 1 依据。"))
    if not nonempty(review_lock.get("gate_2_confirmation_note")):
        errors.append(make_issue("GATE_2_NOTE_EMPTY", "review_lock.gate_2_confirmation_note", "Gate 2 缺少确认说明。"))

    metrics = {
        "source_line_count": len(source_lines),
        "nonempty_source_line_count": sum(1 for line in source_lines if line.strip()),
        "source_unit_count": len(source_units),
        "source_kind_counts": dict(source_kind_counts),
        "scene_count": len(scene_ids),
        "formal_shot_count": len(shot_ids),
        "topology_unit_count": len(topology_unit_ids),
        "gate_1_mode": gate_one.get("mode"),
        "gate_2_status": review_lock.get("gate_2_status"),
    }
    return report(errors, warnings, metrics)


def report(
    errors: List[Dict[str, str]],
    warnings: List[Dict[str, str]],
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "workspace_contract": WORKSPACE_CONTRACT,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "metrics": metrics,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="验证 su-fenjingskill 3.1.1 内部来源、导演方法和双 Gate 工作区。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    lock_parser = subparsers.add_parser("lock", help="计算内部 review lock 哈希，不改变 Gate 状态。")
    lock_parser.add_argument("--workspace", type=Path, required=True)
    lock_parser.add_argument("--output", type=Path, required=True)

    validate_parser = subparsers.add_parser("validate", help="验证内部工作区与正式 3.1.0 shot data。")
    validate_parser.add_argument("--workspace", type=Path, required=True)
    validate_parser.add_argument("--shot-data", type=Path, required=True)
    validate_parser.add_argument("--report", type=Path)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        workspace = load_json(args.workspace)
        if args.command == "lock":
            locked = lock_workspace(workspace)
            write_json(args.output, locked)
            sys.stdout.write("workspace: {}\n".format(args.output))
            return 0

        shot_data = load_json(args.shot_data)
        review_report = validate_workspace(workspace, shot_data)
        if args.report:
            write_json(args.report, review_report)
        sys.stdout.write(json.dumps(review_report, ensure_ascii=False, indent=2) + "\n")
        return 0 if review_report["status"] == "PASS" else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write("FAIL: {}\n".format(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
