#!/usr/bin/env python3
"""Internal source-alignment, format, director-method, and Gate review for su-fenjingskill 3.1.4.

director-workspace/3.1.4 is an internal audit carrier. It never becomes a fifth
formal delivery file and never decides artistic value through shot statistics.
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

try:  # supports both script-path and ``python -m scripts...`` execution
    from ._chinese_context import dialogue_pace_issues
    from ._schema_validation import validate_formal_schema, validate_workspace_schema
    from .source_alignment import (
        classification_review_hash,
        expected_alignment_hashes,
        looks_probably_narrative,
        text_hash as alignment_text_hash,
        validate_source_alignment,
    )
except ImportError:  # pragma: no cover - script-path execution
    from _chinese_context import dialogue_pace_issues
    from _schema_validation import validate_formal_schema, validate_workspace_schema
    from source_alignment import (
        classification_review_hash,
        expected_alignment_hashes,
        looks_probably_narrative,
        text_hash as alignment_text_hash,
        validate_source_alignment,
    )


WORKSPACE_CONTRACT = "director-workspace/3.1.4"
FORMAL_CONTRACT_NAME = "director-shot-data"
FORMAL_CONTRACT_VERSION = "3.1.4"
FORMAL_SOURCE_SKILL = "su-fenjingskill"
FORMAL_SOURCE_SKILL_VERSION = "3.1.4"

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
SHOT_FLOW_OWNERS = {
    "camera_setup",
    "blocking",
    "performance",
    "dialogue_segment",
    "effect",
    "ambience",
    "movement",
    "focus",
    "state_update",
    "edit_exit",
}
SHOT_FLOW_INDEX_OWNERS = {
    "dialogue_segment": ("sound", "dialogue_segments"),
    "effect": ("sound", "effects"),
    "state_update": ("continuity", "state_updates"),
}
SHOT_FLOW_SCALAR_OWNERS = {
    "blocking": ("staging", "blocking"),
    "performance": ("staging", "performance"),
    "ambience": ("sound", "ambience"),
    "focus": ("camera", "focus"),
    "edit_exit": ("edit", "exit"),
}
VAGUE_BOUNDARY_TRIGGERS = {
    "动作变化",
    "声音变化",
    "视线变化",
    "停顿",
    "空间变化",
    "信息变化",
    "关系变化",
    "节奏变化",
}
VAGUE_EDITORIAL_GAINS = {
    "需要切镜",
    "便于剪辑",
    "增强节奏",
    "强调情绪",
    "突出重点",
    "更清晰",
    "更有视听语言",
}
VIEWPOINT_OWNER_TYPES = {"subject", "relationship", "object", "space", "subjective"}
READING_PRIORITIES = {"space", "relationship", "body", "face", "detail"}
FRAMING_MODES = {"single", "two_shot", "group", "over_shoulder", "insert", "subjective", "space"}
CAMERA_RESPONSES = {"observe", "isolate", "reframe", "follow", "reveal", "withhold"}
FRAME_AXES = {"horizontal", "vertical", "depth", "layered", "centered", "diagonal", "subjective"}
GENERIC_UNIFORMITY_INTENTS = {
    "统一", "保持统一", "保持一致", "风格统一", "导演方法要求", "克制", "摄影机克制",
}
APPROVAL_EVENT_TYPES = {
    "gate_0_confirmed",
    "gate_1_approved",
    "gate_2_confirmed",
    "alignment_approved",
    "classification_approved",
}
GENERIC_VISIBLE_DEVELOPMENTS = {
    "继续反应", "保持反应", "继续表演", "保持画面", "继续看着", "维持状态", "倾听者反应",
}
RHYTHM_PROFILES = {"short_drama_under_10m", "platform_series_episode", "short_film_3_20m", "feature_film", "custom"}
ASPECT_RATIOS = {"9:16", "16:9", "1.85:1", "2.35:1", "2.39:1", "4:3", "custom"}
ORIENTATIONS = {"vertical", "horizontal", "custom"}


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


def gate_1_content_hash(hashes: Dict[str, str]) -> str:
    return canonical_hash(
        {
            "gate_0_content_hash": gate_0_content_hash(hashes),
            "source_hash": hashes.get("source_hash"),
            "source_model_hash": hashes.get("source_model_hash"),
            "method_hash": hashes.get("method_hash"),
        }
    )


def gate_0_content_hash(hashes: Dict[str, str]) -> str:
    return canonical_hash({"format_hash": hashes.get("format_hash")})


def gate_2_content_hash(hashes: Dict[str, str]) -> str:
    return canonical_hash(
        {
            "gate_1_content_hash": gate_1_content_hash(hashes),
            "strategy_hash": hashes.get("strategy_hash"),
            "topology_hash": hashes.get("topology_hash"),
        }
    )


def approval_event_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "content_hash": event.get("content_hash"),
        "reviewer": normalize_text(event.get("reviewer")),
        "note": normalize_text(event.get("note")),
        "timestamp_utc": event.get("timestamp_utc"),
        "previous_event_hash": event.get("previous_event_hash"),
    }


def approval_event_hash(event: Dict[str, Any]) -> str:
    return canonical_hash(approval_event_payload(event))


def append_approval_event(
    workspace: Dict[str, Any],
    *,
    event_type: str,
    content_hash: str,
    reviewer: str,
    note: str,
    timestamp_utc: str | None = None,
) -> Dict[str, Any]:
    if event_type not in APPROVAL_EVENT_TYPES:
        raise ValueError(f"未知审批事件类型：{event_type}")
    if not normalize_text(reviewer) or not normalize_text(note):
        raise ValueError("审批事件必须包含 reviewer 与 note")
    events = workspace.setdefault("approval_events", [])
    if not isinstance(events, list):
        raise ValueError("workspace.approval_events 必须是数组")
    previous_hash = events[-1].get("event_hash") if events and isinstance(events[-1], dict) else None
    event = {
        "event_id": f"AE{len(events) + 1:03d}",
        "event_type": event_type,
        "content_hash": content_hash,
        "reviewer": normalize_text(reviewer),
        "note": normalize_text(note),
        "timestamp_utc": timestamp_utc
        or _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "previous_event_hash": previous_hash,
    }
    event["event_hash"] = approval_event_hash(event)
    events.append(event)
    return event


def validate_approval_events(workspace: Dict[str, Any]) -> tuple[list[Dict[str, str]], Dict[str, Set[str]]]:
    errors: list[Dict[str, str]] = []
    events = workspace.get("approval_events")
    event_hashes_by_type: Dict[str, Set[str]] = {event_type: set() for event_type in APPROVAL_EVENT_TYPES}
    if not isinstance(events, list):
        return [make_issue("APPROVAL_EVENTS_INVALID", "approval_events", "approval_events 必须是数组。")], event_hashes_by_type
    previous_hash: str | None = None
    seen_ids: Set[str] = set()
    for index, event in enumerate(events):
        path = f"approval_events[{index}]"
        if not isinstance(event, dict):
            errors.append(make_issue("APPROVAL_EVENT_INVALID", path, "审批事件必须是对象。"))
            continue
        event_id = event.get("event_id")
        event_type = event.get("event_type")
        if not nonempty(event_id) or event_id in seen_ids:
            errors.append(make_issue("APPROVAL_EVENT_INVALID", path + ".event_id", "event_id 为空或重复。"))
        else:
            seen_ids.add(str(event_id))
        if event_type not in APPROVAL_EVENT_TYPES:
            errors.append(make_issue("APPROVAL_EVENT_INVALID", path + ".event_type", "未知审批事件类型。"))
        if event.get("previous_event_hash") != previous_hash:
            errors.append(make_issue("APPROVAL_EVENT_CHAIN_BROKEN", path + ".previous_event_hash", "审批事件哈希链断裂。"))
        expected = approval_event_hash(event)
        if event.get("event_hash") != expected:
            errors.append(make_issue("APPROVAL_EVENT_HASH_MISMATCH", path + ".event_hash", "审批事件哈希与内容不一致。"))
        if not nonempty(event.get("reviewer")) or not nonempty(event.get("note")):
            errors.append(make_issue("APPROVAL_EVENT_INVALID", path, "审批事件缺少 reviewer 或 note。"))
        if event_type in event_hashes_by_type and nonempty(event.get("content_hash")):
            event_hashes_by_type[event_type].add(str(event.get("content_hash")))
        previous_hash = event.get("event_hash") if nonempty(event.get("event_hash")) else previous_hash
    return errors, event_hashes_by_type


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
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


def validate_format_brief(brief: Any, path: str = "format_brief") -> List[Dict[str, str]]:
    errors: List[Dict[str, str]] = []
    if not isinstance(brief, dict):
        return [make_issue("FORMAT_BRIEF_REQUIRED", path, "拆镜前必须确认格式、画幅、节奏和对白速度。")]
    profile = brief.get("rhythm_profile")
    runtime = brief.get("target_runtime_seconds")
    ratio = brief.get("aspect_ratio")
    orientation = brief.get("orientation")
    if profile not in RHYTHM_PROFILES:
        errors.append(make_issue("RHYTHM_PROFILE_INVALID", path + ".rhythm_profile", "节奏预设尚未确认。"))
    if not isinstance(runtime, (int, float)) or isinstance(runtime, bool) or runtime <= 0:
        errors.append(make_issue("TARGET_RUNTIME_INVALID", path + ".target_runtime_seconds", "目标总时长必须大于零。"))
    elif profile == "short_drama_under_10m" and runtime > 600:
        errors.append(make_issue("RHYTHM_PROFILE_RUNTIME_MISMATCH", path + ".target_runtime_seconds", "十分钟短剧预设不得超过 600 秒。"))
    elif profile == "short_film_3_20m" and not 180 <= runtime <= 1200:
        errors.append(make_issue("RHYTHM_PROFILE_RUNTIME_MISMATCH", path + ".target_runtime_seconds", "短片预设必须位于 180–1200 秒。"))
    if ratio not in ASPECT_RATIOS:
        errors.append(make_issue("ASPECT_RATIO_INVALID", path + ".aspect_ratio", "画幅比例尚未确认。"))
    if orientation not in ORIENTATIONS:
        errors.append(make_issue("ORIENTATION_INVALID", path + ".orientation", "画面方向尚未确认。"))
    if ratio == "9:16" and orientation != "vertical":
        errors.append(make_issue("ASPECT_ORIENTATION_MISMATCH", path + ".orientation", "9:16 必须使用 vertical。"))
    if ratio in {"16:9", "1.85:1", "2.35:1", "2.39:1", "4:3"} and orientation != "horizontal":
        errors.append(make_issue("ASPECT_ORIENTATION_MISMATCH", path + ".orientation", f"{ratio} 必须使用 horizontal。"))
    pace = brief.get("dialogue_pace") if isinstance(brief.get("dialogue_pace"), dict) else {}
    for code, relative_path, message in dialogue_pace_issues(profile, pace):
        suffix = "." + relative_path if relative_path else ""
        errors.append(make_issue(code, path + ".dialogue_pace" + suffix, message))
    return errors


def validate_shot_flow(shots: Any) -> List[Dict[str, str]]:
    """Validate ordered front-end ownership without duplicating backend prose."""
    errors: List[Dict[str, str]] = []
    if not isinstance(shots, list):
        return errors
    for shot_index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        shot_path = f"shot_data.shots[{shot_index}]"
        flow = shot.get("shot_flow")
        if not isinstance(flow, list) or not flow:
            errors.append(
                make_issue(
                    "SHOT_FLOW_REQUIRED",
                    shot_path + ".shot_flow",
                    "正式镜头必须提供非空 shot_flow；迁移草稿需人工重建后才能进入正式交付。",
                )
            )
            continue

        owner_counts: Counter = Counter()
        dialogue_indices: List[int] = []
        sound = shot.get("sound") if isinstance(shot.get("sound"), dict) else {}
        camera = shot.get("camera") if isinstance(shot.get("camera"), dict) else {}
        for flow_index, item in enumerate(flow):
            item_path = f"{shot_path}.shot_flow[{flow_index}]"
            if not isinstance(item, dict):
                errors.append(make_issue("SHOT_FLOW_ITEM_INVALID", item_path, "shot_flow 项必须是对象。"))
                continue
            owner = item.get("owner")
            if owner not in SHOT_FLOW_OWNERS:
                errors.append(make_issue("SHOT_FLOW_OWNER_INVALID", item_path + ".owner", "shot_flow owner 无效。"))
                continue
            owner_counts[owner] += 1

            if owner in SHOT_FLOW_INDEX_OWNERS:
                parent_key, list_key = SHOT_FLOW_INDEX_OWNERS[owner]
                parent = shot.get(parent_key) if isinstance(shot.get(parent_key), dict) else {}
                values = parent.get(list_key) if isinstance(parent.get(list_key), list) else []
                index = item.get("index")
                if type(index) is not int or index < 0 or index >= len(values):
                    errors.append(
                        make_issue(
                            "SHOT_FLOW_INDEX_OUT_OF_RANGE",
                            item_path + ".index",
                            f"{owner} index 超出对应后端数组范围。",
                        )
                    )
                    continue
                if owner == "dialogue_segment":
                    dialogue_indices.append(index)
                continue

            if owner in SHOT_FLOW_SCALAR_OWNERS:
                parent_key, field_key = SHOT_FLOW_SCALAR_OWNERS[owner]
                parent = shot.get(parent_key) if isinstance(shot.get(parent_key), dict) else {}
                backend_text = parent.get(field_key)
                span = item.get("span")
                if span is not None and (
                    not isinstance(span, str)
                    or not span.strip()
                    or not isinstance(backend_text, str)
                    or span not in backend_text
                ):
                    errors.append(
                        make_issue(
                            "SHOT_FLOW_SPAN_MISMATCH",
                            item_path + ".span",
                            f"{owner} span 必须逐字存在于所属后端字符串。",
                        )
                    )

        camera_setup_count = owner_counts.get("camera_setup", 0)
        if camera_setup_count != 1:
            errors.append(
                make_issue(
                    "SHOT_FLOW_CAMERA_SETUP_COUNT",
                    shot_path + ".shot_flow",
                    f"camera_setup 必须恰好出现一次，当前为 {camera_setup_count} 次。",
                )
            )

        dialogue_count = len(sound.get("dialogue_segments", [])) if isinstance(sound.get("dialogue_segments"), list) else 0
        expected_dialogue_indices = list(range(dialogue_count))
        dialogue_index_counts = Counter(dialogue_indices)
        missing_dialogues = [index for index in expected_dialogue_indices if dialogue_index_counts[index] == 0]
        duplicate_dialogues = [index for index, count in dialogue_index_counts.items() if count > 1]
        if missing_dialogues:
            errors.append(
                make_issue(
                    "SHOT_FLOW_DIALOGUE_MISSING",
                    shot_path + ".shot_flow",
                    "对白片段未全部进入 shot_flow：{}。".format(", ".join(map(str, missing_dialogues))),
                )
            )
        if duplicate_dialogues:
            errors.append(
                make_issue(
                    "SHOT_FLOW_DIALOGUE_DUPLICATE",
                    shot_path + ".shot_flow",
                    "对白片段在 shot_flow 中重复：{}。".format(", ".join(map(str, duplicate_dialogues))),
                )
            )
        if dialogue_indices != expected_dialogue_indices:
            errors.append(
                make_issue(
                    "SHOT_FLOW_DIALOGUE_ORDER",
                    shot_path + ".shot_flow",
                    "对白片段必须按后端 dialogue_segments 的顺序恰好引用一次。",
                )
            )

        movement = camera.get("movement") if isinstance(camera.get("movement"), dict) else {}
        movement_type = movement.get("type")
        movement_count = owner_counts.get("movement", 0)
        if movement_type == "fixed" and movement_count:
            errors.append(
                make_issue(
                    "SHOT_FLOW_FIXED_MOVEMENT_FORBIDDEN",
                    shot_path + ".shot_flow",
                    "固定镜头不得加入空的 movement 流程项。",
                )
            )
        elif movement_type != "fixed":
            if movement_count == 0:
                errors.append(
                    make_issue(
                        "SHOT_FLOW_MOVEMENT_REQUIRED",
                        shot_path + ".shot_flow",
                        "非固定运镜必须在 shot_flow 中恰好出现一次。",
                    )
                )
            elif movement_count > 1:
                errors.append(
                    make_issue(
                        "SHOT_FLOW_MOVEMENT_DUPLICATE",
                        shot_path + ".shot_flow",
                        "非固定运镜在 shot_flow 中不得重复。",
                    )
                )
    return errors


def validate_topology_boundaries(scene_strategies: Any) -> List[Dict[str, str]]:
    """Require exactly one concrete boundary for each adjacent topology pair."""
    errors: List[Dict[str, str]] = []
    if not isinstance(scene_strategies, list):
        return errors
    for strategy_index, strategy in enumerate(scene_strategies):
        if not isinstance(strategy, dict):
            continue
        topology = strategy.get("topology") if isinstance(strategy.get("topology"), list) else []
        for unit_index, unit in enumerate(topology):
            if not isinstance(unit, dict):
                continue
            unit_path = f"scene_strategies[{strategy_index}].topology[{unit_index}]"
            boundary = unit.get("boundary_to_next")
            is_terminal = unit_index == len(topology) - 1
            if is_terminal:
                if boundary is not None:
                    errors.append(
                        make_issue(
                            "TERMINAL_BOUNDARY_FORBIDDEN",
                            unit_path + ".boundary_to_next",
                            "末拓扑单元没有下一单元，不得填写 boundary_to_next。",
                        )
                    )
                continue
            if not isinstance(boundary, dict):
                errors.append(
                    make_issue(
                        "BOUNDARY_TO_NEXT_MISSING",
                        unit_path + ".boundary_to_next",
                        "每个非末拓扑单元必须说明到下一单元的具体切点。",
                    )
                )
                continue
            relation = boundary.get("relation")
            trigger = boundary.get("trigger")
            editorial_gain = boundary.get("editorial_gain")
            if relation not in INTER_RELATIONS:
                errors.append(
                    make_issue(
                        "INTER_RELATION_INVALID",
                        unit_path + ".boundary_to_next.relation",
                        "镜间关系无效。",
                    )
                )
            if not nonempty(trigger):
                errors.append(
                    make_issue(
                        "BOUNDARY_TRIGGER_EMPTY",
                        unit_path + ".boundary_to_next.trigger",
                        "切点 trigger 必须写出具体动作、声音、视线、停顿、空间或信息事件。",
                    )
                )
            elif normalize_text(trigger) in VAGUE_BOUNDARY_TRIGGERS:
                errors.append(
                    make_issue(
                        "BOUNDARY_TRIGGER_VAGUE",
                        unit_path + ".boundary_to_next.trigger",
                        "trigger 不能只写抽象类别，必须指出当前具体事件。",
                    )
                )
            if not nonempty(editorial_gain):
                errors.append(
                    make_issue(
                        "BOUNDARY_EDITORIAL_GAIN_EMPTY",
                        unit_path + ".boundary_to_next.editorial_gain",
                        "editorial_gain 必须说明切开相对继续不切的具体观看收益。",
                    )
                )
            elif normalize_text(editorial_gain) in VAGUE_EDITORIAL_GAINS:
                errors.append(
                    make_issue(
                        "BOUNDARY_EDITORIAL_GAIN_VAGUE",
                        unit_path + ".boundary_to_next.editorial_gain",
                        "editorial_gain 不能只写抽象效果，必须说明相对不切的具体收益。",
                    )
                )
    return errors


def _camera_reason_specific(value: Any) -> bool:
    text = normalize_text(value)
    compact = "".join(text.split())
    return len(compact) >= 8 and text not in GENERIC_UNIFORMITY_INTENTS


def _string_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [normalize_text(item) for item in value if isinstance(item, str) and normalize_text(item)]


def validate_camera_grammar(
    scene_strategies: Any,
    formal_shot_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Validate Gate-2 viewing decisions against formal execution, without quotas."""
    errors: List[Dict[str, str]] = []
    if not isinstance(scene_strategies, list):
        return errors
    for strategy_index, strategy in enumerate(scene_strategies):
        if not isinstance(strategy, dict):
            continue
        strategy_path = f"scene_strategies[{strategy_index}]"
        grammar = strategy.get("camera_grammar") if isinstance(strategy.get("camera_grammar"), dict) else {}
        for field in ("dominant_principle", "progression"):
            if not nonempty(grammar.get(field)):
                errors.append(make_issue("CAMERA_DESIGN_UNRESOLVED", f"{strategy_path}.camera_grammar.{field}", "场级摄影语法尚未形成正式决定。"))
        change_triggers = grammar.get("change_triggers")
        if not isinstance(change_triggers, list) or any(not nonempty(item) for item in change_triggers):
            errors.append(make_issue("CAMERA_DESIGN_UNRESOLVED", f"{strategy_path}.camera_grammar.change_triggers", "场级摄影变化触发必须是具体事件数组；无变化时可为空数组。"))

        topology = strategy.get("topology") if isinstance(strategy.get("topology"), list) else []
        reason_owners: Dict[str, Dict[str, Set[str]]] = {
            "viewing": {}, "shot_size": {}, "angle": {}, "movement": {}, "aspect": {},
        }
        scene_shots: list[Dict[str, Any]] = []
        for unit_index, unit in enumerate(topology):
            if not isinstance(unit, dict):
                continue
            unit_path = f"{strategy_path}.topology[{unit_index}]"
            unit_id = normalize_text(unit.get("unit_id")) or unit_path
            design = unit.get("viewing_design") if isinstance(unit.get("viewing_design"), dict) else {}
            checks = (
                ("owner_type", VIEWPOINT_OWNER_TYPES),
                ("reading_priority", READING_PRIORITIES),
                ("framing_intent", FRAMING_MODES),
                ("camera_response", CAMERA_RESPONSES),
                ("frame_axis", FRAME_AXES),
            )
            for field, allowed in checks:
                if design.get(field) not in allowed:
                    errors.append(make_issue("CAMERA_DESIGN_UNRESOLVED", f"{unit_path}.viewing_design.{field}", f"{field} 尚未形成正式决定。"))
            if not nonempty_string_list(design.get("owner_refs")):
                errors.append(make_issue("CAMERA_DESIGN_UNRESOLVED", f"{unit_path}.viewing_design.owner_refs", "owner_refs 尚未形成正式决定。"))
            for field in ("visible_subjects", "offscreen_subjects"):
                value = design.get(field)
                if not isinstance(value, list) or any(not nonempty(item) for item in value):
                    errors.append(make_issue("CAMERA_DESIGN_UNRESOLVED", f"{unit_path}.viewing_design.{field}", f"{field} 必须是明确的主体数组；没有主体时可为空数组。"))
            if not nonempty(design.get("reason")):
                errors.append(make_issue("CAMERA_DESIGN_UNRESOLVED", f"{unit_path}.viewing_design.reason", "观看理由尚未形成正式决定。"))
            if not nonempty(design.get("aspect_ratio_fit")):
                errors.append(make_issue("CAMERA_DESIGN_UNRESOLVED", f"{unit_path}.viewing_design.aspect_ratio_fit", "画幅适配理由尚未形成正式决定。"))

            viewing_reason = normalize_text(design.get("reason"))
            if viewing_reason:
                reason_owners["viewing"].setdefault(viewing_reason, set()).add(unit_id)
            shot_refs = unit.get("shot_refs") if isinstance(unit.get("shot_refs"), list) else []
            for shot_id in shot_refs:
                shot = formal_shot_map.get(shot_id)
                if not isinstance(shot, dict):
                    continue
                scene_shots.append(shot)
                viewpoint = shot.get("viewpoint") if isinstance(shot.get("viewpoint"), dict) else {}
                camera = shot.get("camera") if isinstance(shot.get("camera"), dict) else {}
                staging = shot.get("staging") if isinstance(shot.get("staging"), dict) else {}
                expected_actual = (
                    ("owner_type", design.get("owner_type"), viewpoint.get("owner_type")),
                    ("owner_refs", design.get("owner_refs"), viewpoint.get("owner_refs")),
                    ("reading_priority", design.get("reading_priority"), viewpoint.get("reading_priority")),
                    ("camera_response", design.get("camera_response"), viewpoint.get("camera_response")),
                    ("reason", design.get("reason"), viewpoint.get("reason")),
                    ("framing_intent", design.get("framing_intent"), camera.get("framing_mode")),
                    ("visible_subjects", design.get("visible_subjects"), staging.get("visible_subjects")),
                    ("offscreen_subjects", design.get("offscreen_subjects"), staging.get("offscreen_subjects")),
                    ("frame_axis", design.get("frame_axis"), camera.get("frame_axis")),
                    ("aspect_ratio_fit", design.get("aspect_ratio_fit"), camera.get("aspect_ratio_reason")),
                )
                for field, expected, actual in expected_actual:
                    if expected != actual:
                        errors.append(
                            make_issue(
                                "VIEWING_DESIGN_EXECUTION_DIVERGED",
                                f"{unit_path}.viewing_design.{field}",
                                f"Gate 2 的 {field} 与正式镜头 {shot_id} 不一致。",
                            )
                        )
                movement = camera.get("movement") if isinstance(camera.get("movement"), dict) else {}
                response = viewpoint.get("camera_response")
                intra = unit.get("intra_shot_operations") if isinstance(unit.get("intra_shot_operations"), list) else []
                if response == "follow" and movement.get("type") not in {"follow", "track"}:
                    errors.append(make_issue("CAMERA_RESPONSE_NOT_REALIZED", f"{unit_path}.viewing_design.camera_response", f"{shot_id} 未用跟随或横移落实 follow。"))
                if response in {"reframe", "reveal"} and movement.get("type") == "fixed" and not set(intra).intersection(
                    {"blocking_recompose", "camera_reframe", "focus_shift"}
                ):
                    errors.append(make_issue("CAMERA_RESPONSE_NOT_REALIZED", f"{unit_path}.viewing_design.camera_response", f"{shot_id} 未用调度、焦点或运动落实 {response}。"))
                for category, reason in (
                    ("shot_size", camera.get("shot_size_reason")),
                    ("angle", camera.get("angle_reason")),
                    ("movement", movement.get("reason")),
                    ("aspect", camera.get("aspect_ratio_reason")),
                ):
                    reason_text = normalize_text(reason)
                    if reason_text:
                        reason_owners[category].setdefault(reason_text, set()).add(unit_id)

        for category, values in reason_owners.items():
            for reason, unit_ids in values.items():
                if len(unit_ids) > 1:
                    errors.append(
                        make_issue(
                            "CAMERA_DECISION_TEMPLATE_COLLAPSE",
                            strategy_path + ".topology",
                            f"不同拓扑单元重复使用相同的 {category} 理由：{reason}",
                        )
                    )

        if len(scene_shots) >= 2:
            signatures = []
            for shot in scene_shots:
                viewpoint = shot.get("viewpoint") if isinstance(shot.get("viewpoint"), dict) else {}
                camera = shot.get("camera") if isinstance(shot.get("camera"), dict) else {}
                movement = camera.get("movement") if isinstance(camera.get("movement"), dict) else {}
                signatures.append(
                    (
                        camera.get("framing_mode"),
                        camera.get("angle"),
                        movement.get("type"),
                        viewpoint.get("owner_type"),
                    )
                )
            category_uniform = all(len({signature[index] for signature in signatures}) == 1 for index in range(4))
            if category_uniform and not _camera_reason_specific(grammar.get("uniformity_intent")):
                errors.append(
                    make_issue(
                        "CAMERA_UNIFORMITY_INTENT_REQUIRED",
                        f"{strategy_path}.camera_grammar.uniformity_intent",
                        "整场观看、构图、角度与运动均相同时，必须说明当前场景特定的统一意图。",
                    )
                )
    return errors


def _specific_visible_development(value: Any) -> bool:
    text = normalize_text(value)
    compact = "".join(text.split())
    return len(compact) >= 6 and text not in GENERIC_VISIBLE_DEVELOPMENTS


def validate_dialogue_edit_plans(
    scene_strategies: Any,
    formal_shot_map: Dict[str, Dict[str, Any]],
    dialogue_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Require every dialogue turn to make an explicit picture decision before topology execution."""
    errors: List[Dict[str, str]] = []
    if not isinstance(scene_strategies, list):
        return errors
    planned_ids: list[str] = []
    seen_ids: set[str] = set()
    for strategy_index, strategy in enumerate(scene_strategies):
        if not isinstance(strategy, dict):
            continue
        strategy_path = f"scene_strategies[{strategy_index}]"
        topology = strategy.get("topology") if isinstance(strategy.get("topology"), list) else []
        unit_map = {
            unit.get("unit_id"): (unit_index, unit)
            for unit_index, unit in enumerate(topology)
            if isinstance(unit, dict) and nonempty(unit.get("unit_id"))
        }
        scene_subjects: set[str] = set()
        for _, unit in unit_map.values():
            for shot_id in unit.get("shot_refs", []) if isinstance(unit.get("shot_refs"), list) else []:
                shot = formal_shot_map.get(shot_id)
                staging = shot.get("staging") if isinstance(shot, dict) and isinstance(shot.get("staging"), dict) else {}
                scene_subjects.update(_string_values(staging.get("subjects")))
        plan = strategy.get("dialogue_edit_plan")
        if not isinstance(plan, list):
            errors.append(make_issue("DIALOGUE_EDIT_PLAN_REQUIRED", strategy_path + ".dialogue_edit_plan", "每场必须提供对白观看机会计划；无对白时使用空数组。"))
            continue
        previous_unit_id: str | None = None
        previous_visible_developments: set[str] = set()
        for plan_index, item in enumerate(plan):
            item_path = f"{strategy_path}.dialogue_edit_plan[{plan_index}]"
            if not isinstance(item, dict):
                errors.append(make_issue("DIALOGUE_EDIT_PLAN_INVALID", item_path, "对白观看机会必须是对象。"))
                continue
            dialogue_id = item.get("dialogue_id")
            planned_ids.append(dialogue_id)
            if dialogue_id in seen_ids:
                errors.append(make_issue("DIALOGUE_EDIT_PLAN_DUPLICATE", item_path + ".dialogue_id", f"对白 {dialogue_id} 被重复规划。"))
            else:
                seen_ids.add(dialogue_id)
            source_dialogue = dialogue_map.get(dialogue_id)
            if not isinstance(source_dialogue, dict):
                errors.append(make_issue("DIALOGUE_EDIT_PLAN_UNKNOWN", item_path + ".dialogue_id", f"对白 {dialogue_id!r} 不存在。"))
                continue
            if item.get("speaker") != source_dialogue.get("speaker"):
                errors.append(make_issue("DIALOGUE_EDIT_SPEAKER_MISMATCH", item_path + ".speaker", f"对白 {dialogue_id} 的说话者与来源不一致。"))
            speaker = normalize_text(item.get("speaker"))
            listeners = _string_values(item.get("listener_refs"))
            power_centers = _string_values(item.get("power_center_refs"))
            if scene_subjects and speaker not in scene_subjects:
                errors.append(make_issue("DIALOGUE_SPEAKER_OUTSIDE_SCENE", item_path + ".speaker", "对白说话者未进入本场人物集合。"))
            unknown_attention = [ref for ref in listeners + power_centers if scene_subjects and ref not in scene_subjects]
            if unknown_attention:
                errors.append(make_issue("DIALOGUE_ATTENTION_SUBJECT_UNKNOWN", item_path, f"对白观看计划引用本场之外的人物：{unknown_attention}。"))
            if speaker and speaker in listeners:
                errors.append(make_issue("DIALOGUE_LISTENER_EQUALS_SPEAKER", item_path + ".listener_refs", "listener_refs 不得把说话者本人当作倾听者。"))
            if len(scene_subjects) >= 3 and (not listeners or not power_centers):
                errors.append(make_issue("MULTIPERSON_ATTENTION_MAP_REQUIRED", item_path, "多人对白必须明确本轮倾听者与权力中心。"))
            if not nonempty(item.get("attention_shift")):
                errors.append(make_issue("DIALOGUE_ATTENTION_SHIFT_EMPTY", item_path + ".attention_shift", "必须说明这一轮对白改变了什么信息、关系或注意力。"))
            steps = item.get("picture_steps") if isinstance(item.get("picture_steps"), list) else []
            if not steps:
                errors.append(make_issue("DIALOGUE_PICTURE_STEPS_EMPTY", item_path + ".picture_steps", "每句对白至少需要一个画面步骤。"))
                continue
            spans: list[str] = []
            for step_index, step in enumerate(steps):
                step_path = f"{item_path}.picture_steps[{step_index}]"
                if not isinstance(step, dict):
                    errors.append(make_issue("DIALOGUE_PICTURE_STEP_INVALID", step_path, "画面步骤必须是对象。"))
                    continue
                span = step.get("text_span") if isinstance(step.get("text_span"), str) else ""
                spans.append(span)
                unit_id = step.get("topology_unit_id")
                unit_entry = unit_map.get(unit_id)
                if unit_entry is None:
                    errors.append(make_issue("DIALOGUE_PICTURE_UNIT_UNKNOWN", step_path + ".topology_unit_id", f"画面步骤引用不存在的本场 topology unit {unit_id!r}。"))
                    continue
                unit_index, unit = unit_entry
                design = unit.get("viewing_design") if isinstance(unit.get("viewing_design"), dict) else {}
                for field, expected in (
                    ("owner_type", design.get("owner_type")),
                    ("owner_refs", design.get("owner_refs")),
                    ("framing_intent", design.get("framing_intent")),
                ):
                    if step.get(field) != expected:
                        errors.append(make_issue("DIALOGUE_PICTURE_VIEWING_DIVERGED", step_path + "." + field, f"对白画面步骤的 {field} 与 {unit_id} viewing_design 不一致。"))
                executed = False
                for shot_id in unit.get("shot_refs", []) if isinstance(unit.get("shot_refs"), list) else []:
                    shot = formal_shot_map.get(shot_id)
                    sound = shot.get("sound") if isinstance(shot, dict) and isinstance(shot.get("sound"), dict) else {}
                    segments = sound.get("dialogue_segments") if isinstance(sound.get("dialogue_segments"), list) else []
                    if any(
                        isinstance(segment, dict)
                        and segment.get("dialogue_id") == dialogue_id
                        and segment.get("text") == span
                        for segment in segments
                    ):
                        executed = True
                        break
                if not executed:
                    errors.append(make_issue("DIALOGUE_PICTURE_STEP_NOT_EXECUTED", step_path, "对白画面步骤没有在所绑定镜头中逐字执行。"))

                decision = step.get("entry_decision")
                if previous_unit_id is None:
                    if decision != "establish":
                        errors.append(make_issue("DIALOGUE_FIRST_STEP_NOT_ESTABLISHED", step_path + ".entry_decision", "本场第一个对白画面步骤必须 establish。"))
                elif unit_id == previous_unit_id:
                    if decision not in {"hold", "reframe"}:
                        errors.append(make_issue("DIALOGUE_EDIT_DECISION_MISMATCH", step_path + ".entry_decision", "同一 topology unit 内只能 hold 或 reframe。"))
                    development = normalize_text(step.get("visible_development"))
                    if not _specific_visible_development(development):
                        errors.append(make_issue("MISSED_DIALOGUE_VIEW_CHANGE", step_path + ".visible_development", "继续保持同一画面时，必须写出这一轮新增的可见动作、反应、距离、焦点或关系变化。"))
                    elif development in previous_visible_developments:
                        errors.append(make_issue("DIALOGUE_HOLD_TEMPLATE_COLLAPSE", step_path + ".visible_development", "不同对白节点不能复制同一画内发展来证明继续不切。"))
                    previous_visible_developments.add(development)
                    if decision == "reframe" and not set(unit.get("intra_shot_operations", [])).intersection({"blocking_recompose", "camera_reframe", "focus_shift"}):
                        errors.append(make_issue("DIALOGUE_REFRAME_NOT_REALIZED", step_path + ".entry_decision", "reframe 必须由调度、摄影机或焦点重构落实。"))
                elif decision != "cut":
                    errors.append(make_issue("DIALOGUE_EDIT_DECISION_MISMATCH", step_path + ".entry_decision", "进入新的 topology unit 必须明确为 cut。"))
                if decision in {"hold", "reframe"} and step.get("cut_phase") != "hold":
                    errors.append(make_issue("DIALOGUE_HOLD_PHASE_INVALID", step_path + ".cut_phase", "不切或镜内重构的 cut_phase 必须为 hold。"))
                if not nonempty(step.get("picture_value")):
                    errors.append(make_issue("DIALOGUE_PICTURE_VALUE_EMPTY", step_path + ".picture_value", "必须说明当前画面相对其他观看对象的具体价值。"))
                previous_unit_id = unit_id
            if "".join(spans) != source_dialogue.get("text"):
                errors.append(make_issue("DIALOGUE_EDIT_TEXT_MISMATCH", item_path + ".picture_steps", f"对白 {dialogue_id} 的画面步骤文本拼接后不等于来源原文。"))

    expected_ids = list(dialogue_map)
    if planned_ids != expected_ids:
        missing = [dialogue_id for dialogue_id in expected_ids if dialogue_id not in seen_ids]
        extra = [dialogue_id for dialogue_id in planned_ids if dialogue_id not in dialogue_map]
        errors.append(make_issue("DIALOGUE_EDIT_COVERAGE_MISMATCH", "scene_strategies[].dialogue_edit_plan", f"对白观看计划必须按来源顺序恰好覆盖一次；缺少 {missing}，多出 {extra}。"))
    return errors


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
    format_brief = workspace.get("format_brief") if isinstance(workspace.get("format_brief"), dict) else {}
    method = workspace.get("director_method") if isinstance(workspace.get("director_method"), dict) else {}
    strategies = workspace.get("scene_strategies")
    return {
        "source_hash": text_hash(source.get("locked_text")),
        "format_hash": canonical_hash(format_brief),
        "method_hash": canonical_hash(method),
        "strategy_hash": canonical_hash(strategy_payload(strategies)),
        "topology_hash": canonical_hash(topology_payload(strategies)),
    }


def all_expected_hashes(workspace: Dict[str, Any], shot_data: Dict[str, Any]) -> Dict[str, str]:
    return {**expected_hashes(workspace), **expected_alignment_hashes(workspace, shot_data)}


def lock_workspace(workspace: Any, shot_data: Any = None) -> Dict[str, Any]:
    """Recompute locks and invalidate only the dependent review stages.

    Dependency matrix:
    - format brief -> Gate 0, Gate 1, Gate 2, alignment
    - source/source-model or method -> Gate 1, Gate 2, alignment
    - strategy/topology -> Gate 2, alignment
    - formal execution only -> alignment only
    """
    if not isinstance(workspace, dict):
        raise ValueError("workspace 顶层必须是对象")
    if not isinstance(shot_data, dict):
        raise ValueError("lock 必须提供正式 shot data")
    locked = copy.deepcopy(workspace)
    hashes = all_expected_hashes(locked, shot_data)
    source = locked.setdefault("source", {})
    if not isinstance(source, dict):
        raise ValueError("workspace.source 必须是对象")
    source["source_hash"] = hashes["source_hash"]
    gate_zero = locked.setdefault("gate_0", {})
    if not isinstance(gate_zero, dict):
        raise ValueError("workspace.gate_0 必须是对象")
    gate_zero["format_hash"] = hashes["format_hash"]
    gate_one = locked.setdefault("gate_1", {})
    if not isinstance(gate_one, dict):
        raise ValueError("workspace.gate_1 必须是对象")
    gate_one["method_hash"] = hashes["method_hash"]
    review_lock = locked.setdefault("review_lock", {})
    if not isinstance(review_lock, dict):
        raise ValueError("workspace.review_lock 必须是对象")

    protected_keys = (
        "source_hash",
        "format_hash",
        "method_hash",
        "strategy_hash",
        "topology_hash",
        "source_model_hash",
        "execution_hash",
        "alignment_hash",
    )
    previous_hashes = {key: review_lock.get(key) for key in protected_keys}
    changed_keys = {
        key for key in protected_keys if previous_hashes.get(key) != hashes.get(key)
    }
    review_lock.update(hashes)

    gate_0_changed = "format_hash" in changed_keys
    gate_1_changed = gate_0_changed or bool(changed_keys & {"source_hash", "source_model_hash", "method_hash"})
    gate_2_changed = gate_1_changed or bool(changed_keys & {"strategy_hash", "topology_hash"})
    alignment_changed = bool(changed_keys)

    if gate_0_changed:
        gate_zero["status"] = "invalidated"
        gate_zero["note"] = "format brief changed; Gate 0 requires renewed confirmation"
        review_lock["gate_0_status"] = "invalidated"
        review_lock["gate_0_note"] = "format, runtime, aspect ratio, orientation, coverage bias, or dialogue pace changed"
    if gate_1_changed:
        gate_one["mode"] = "invalidated"
        gate_one["status"] = "invalidated"
        gate_one["note"] = "source model or director method changed; Gate 1 requires renewed review"
        review_lock["gate_1_status"] = "invalidated"
        review_lock["gate_1_basis"] = "source, authority, facts, assumptions, or director method changed"
    if gate_2_changed:
        review_lock["gate_2_status"] = "invalidated"
        review_lock["gate_2_confirmation_note"] = "Gate 1, scene strategy, or topology changed; Gate 2 requires renewed confirmation"
    if alignment_changed:
        review_lock["alignment_status"] = "invalidated"
        review_lock["alignment_note"] = "source alignment or formal execution changed; alignment requires renewed review"
    return locked


def validate_workspace(
    workspace: Any,
    shot_data: Any,
    *,
    check_review_states: bool = True,
) -> Dict[str, Any]:
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    if not isinstance(workspace, dict):
        errors.append(make_issue("WORKSPACE_NOT_OBJECT", "$", "director workspace 顶层必须是对象。"))
        return report(errors, warnings, {})
    if not isinstance(shot_data, dict):
        errors.append(make_issue("SHOT_DATA_NOT_OBJECT", "shot_data", "正式 shot data 顶层必须是对象。"))
        return report(errors, warnings, {})

    raw_shots = shot_data.get("shots") if isinstance(shot_data.get("shots"), list) else []
    errors.extend(validate_shot_flow(raw_shots))
    errors.extend(validate_topology_boundaries(workspace.get("scene_strategies")))
    workspace_schema_errors = validate_workspace_schema(workspace)
    formal_schema_errors = validate_formal_schema(shot_data)
    if workspace_schema_errors or formal_schema_errors:
        schema_errors = [*errors, *workspace_schema_errors, *formal_schema_errors]
        if workspace.get("workspace_contract") != WORKSPACE_CONTRACT:
            schema_errors.append(
                make_issue(
                    "WORKSPACE_CONTRACT_MISMATCH",
                    "workspace_contract",
                    "内部工作区必须使用 director-workspace/3.1.4。",
                )
            )
        expected_formal_identity = {
            "contract_name": FORMAL_CONTRACT_NAME,
            "contract_version": FORMAL_CONTRACT_VERSION,
            "source_skill": FORMAL_SOURCE_SKILL,
            "source_skill_version": FORMAL_SOURCE_SKILL_VERSION,
        }
        for key, expected in expected_formal_identity.items():
            if shot_data.get(key) != expected:
                schema_errors.append(
                    make_issue(
                        "FORMAL_CONTRACT_MISMATCH",
                        "shot_data." + key,
                        "正式交付字段 {} 必须保持 {!r}。".format(key, expected),
                    )
                )
        result = report(schema_errors, warnings, {})
        result["dimensions"] = {
            "source_integrity": "NOT_RUN",
            "source_authority": "NOT_RUN",
            "source_coverage": "NOT_RUN",
            "source_alignment": "NOT_RUN",
            "gate_review": "NOT_RUN",
            "formal_structure": "FAIL",
        }
        return result

    if workspace.get("workspace_contract") != WORKSPACE_CONTRACT:
        errors.append(
            make_issue(
                "WORKSPACE_CONTRACT_MISMATCH",
                "workspace_contract",
                "内部工作区必须使用 director-workspace/3.1.4。",
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

    # JSON Schema is the only structural source of truth. Once a required
    # field/type/additional-property violation exists, stop before semantic
    # traversal so malformed input is rejected deterministically rather than
    # reaching code that assumes a valid shape.
    if any(item.get("code") in {"WORKSPACE_SCHEMA_INVALID", "FORMAL_SCHEMA_INVALID"} for item in errors):
        result = report(errors, warnings, {})
        result["dimensions"] = {
            "source_integrity": "FAIL",
            "source_authority": "FAIL",
            "source_coverage": "FAIL",
            "source_alignment": "FAIL",
            "dialogue_playback": "FAIL",
            "gate_review": "FAIL",
            "formal_structure": "FAIL",
        }
        return result

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

    workspace_format = workspace.get("format_brief") if isinstance(workspace.get("format_brief"), dict) else {}
    formal_format = shot_data.get("format_brief") if isinstance(shot_data.get("format_brief"), dict) else {}
    if workspace_format != formal_format:
        errors.append(
            make_issue(
                "FORMAT_BRIEF_DIVERGED",
                "shot_data.format_brief",
                "正式 shot data 与 Gate 0 确认的格式、画幅、节奏或对白速度不一致。",
            )
        )
    errors.extend(validate_format_brief(workspace_format, "format_brief"))

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
    formal_shot_map = {
        item.get("shot_id"): item
        for item in formal_shots
        if isinstance(item, dict) and nonempty(item.get("shot_id"))
    }
    dialogue_map = {
        item.get("dialogue_id"): item
        for item in formal_dialogues
        if isinstance(item, dict) and nonempty(item.get("dialogue_id"))
    }

    hashes = all_expected_hashes(workspace, shot_data)
    stored_source_hash = workspace_source.get("source_hash")
    if stored_source_hash != hashes["source_hash"]:
        errors.append(
            make_issue(
                "SOURCE_LOCK_INVALIDATED",
                "source.source_hash",
                "locked_text 已变化；Gate 1 和 Gate 2 必须失效并重新审阅。",
            )
        )

    gate_zero = workspace.get("gate_0") if isinstance(workspace.get("gate_0"), dict) else {}
    if gate_zero.get("format_hash") != hashes["format_hash"]:
        errors.append(make_issue("GATE_0_INVALIDATED", "gate_0.format_hash", "成片格式参数已变化；必须重新确认 Gate 0。"))
    if check_review_states:
        if gate_zero.get("status") != "confirmed":
            errors.append(make_issue("GATE_0_REQUIRED", "gate_0.status", "拆镜前必须确认成片类型、画幅、节奏和对白速度。"))
        if not nonempty(gate_zero.get("note")):
            errors.append(make_issue("GATE_0_NOTE_EMPTY", "gate_0.note", "Gate 0 缺少确认说明。"))

    alignment_report = validate_source_alignment(
        workspace,
        shot_data,
        check_lock=check_review_states,
    )
    errors.extend(alignment_report["errors"])
    warnings.extend(alignment_report["warnings"])

    source_units = workspace_source.get("source_units") if isinstance(workspace_source.get("source_units"), list) else []
    source_kind_counts: Counter = Counter()
    for index, unit in enumerate(source_units):
        if not isinstance(unit, dict):
            continue
        kind = unit.get("kind")
        if kind in SOURCE_KINDS:
            source_kind_counts[kind] += 1
        if kind != "dialogue" or unit.get("authority_role") != "performance_authority":
            continue
        path = "source.source_units[{}]".format(index)
        dialogue_id = unit.get("dialogue_id")
        if dialogue_id not in dialogue_map:
            errors.append(make_issue("SOURCE_DIALOGUE_NOT_REGISTERED", path + ".dialogue_id", "来源对白没有进入正式 dialogue inventory。"))
            continue
        dialogue = dialogue_map[dialogue_id]
        dialogue_text = normalize_text(dialogue.get("text"))
        if dialogue_text and dialogue_text not in normalize_text(unit.get("exact_text")):
            errors.append(make_issue("SOURCE_DIALOGUE_TEXT_MISMATCH", path + ".exact_text", "正式对白未逐字出现在对应来源单元中。"))
        if nonempty(unit.get("speaker")) and unit.get("speaker") != dialogue.get("speaker"):
            errors.append(make_issue("SOURCE_DIALOGUE_SPEAKER_MISMATCH", path + ".speaker", "内部来源说话者与正式 dialogue inventory 不一致。"))

    source_passages = workspace_source.get("source_passages") if isinstance(workspace_source.get("source_passages"), list) else []
    valid_passage_ids = {
        item.get("passage_id")
        for item in source_passages
        if isinstance(item, dict) and nonempty(item.get("passage_id"))
    }
    shot_bindings_value = workspace.get("shot_bindings")
    shot_bindings = shot_bindings_value if isinstance(shot_bindings_value, list) else []
    binding_by_shot = {
        item.get("shot_id"): item
        for item in shot_bindings
        if isinstance(item, dict) and nonempty(item.get("shot_id"))
    }

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
    if check_review_states:
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

    errors.extend(validate_camera_grammar(scene_strategies, formal_shot_map))
    errors.extend(validate_dialogue_edit_plans(scene_strategies, formal_shot_map, dialogue_map))

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

            source_refs = unit.get("source_passage_ids")
            if not isinstance(source_refs, list) or not source_refs:
                errors.append(make_issue("TOPOLOGY_SOURCE_REFS_EMPTY", unit_path + ".source_passage_ids", "拓扑单元必须引用权威 passage。"))
                source_refs = []
            else:
                unknown_source_passages = [ref for ref in source_refs if ref not in valid_passage_ids]
                if unknown_source_passages:
                    errors.append(make_issue("TOPOLOGY_SOURCE_UNKNOWN", unit_path + ".source_passage_ids", "拓扑引用不存在的来源 passage。"))

            declared_fact_refs = unit.get("source_fact_ids")
            if not isinstance(declared_fact_refs, list):
                declared_fact_refs = []

            expected_passage_refs: Set[str] = set()
            expected_fact_refs: Set[str] = set()
            for shot_id in refs:
                formal_shot = formal_shot_map.get(shot_id)
                if isinstance(formal_shot, dict) and formal_shot.get("scene_id") != scene_id:
                    errors.append(
                        make_issue(
                            "TOPOLOGY_SCENE_MISMATCH",
                            unit_path + ".shot_refs",
                            f"镜头 {shot_id} 属于 {formal_shot.get('scene_id')}，不能进入 {scene_id} 的场级策略。",
                        )
                    )
                binding = binding_by_shot.get(shot_id)
                if not isinstance(binding, dict):
                    continue
                expected_passage_refs.update(
                    item for item in binding.get("passage_ids", []) if isinstance(item, str)
                )
                for realization in binding.get("fact_realizations", []):
                    if isinstance(realization, dict) and isinstance(realization.get("fact_id"), str):
                        expected_fact_refs.add(realization["fact_id"])
            if set(source_refs) != expected_passage_refs:
                errors.append(
                    make_issue(
                        "TOPOLOGY_PASSAGE_BINDING_DIVERGED",
                        unit_path + ".source_passage_ids",
                        "topology source_passage_ids 必须与其 shot bindings 的 passage 并集完全一致。",
                    )
                )
            if set(declared_fact_refs) != expected_fact_refs:
                errors.append(
                    make_issue(
                        "TOPOLOGY_FACT_BINDING_DIVERGED",
                        unit_path + ".source_fact_ids",
                        "topology source_fact_ids 必须与其 shot bindings 的 fact realization 并集完全一致。",
                    )
                )

            intra = unit.get("intra_shot_operations")
            if not isinstance(intra, list) or any(item not in INTRA_OPERATIONS for item in intra):
                errors.append(make_issue("INTRA_OPERATION_INVALID", unit_path + ".intra_shot_operations", "镜内操作无效。"))
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

    approval_errors, approval_hashes = validate_approval_events(workspace)
    errors.extend(approval_errors)

    if check_review_states:
        if review_lock.get("format_hash") != hashes["format_hash"]:
            errors.append(make_issue("GATE_0_INVALIDATED", "review_lock.format_hash", "成片格式参数已变化；Gate 0、Gate 1、Gate 2 与 alignment 必须重新确认。"))
        for key in ("source_hash", "source_model_hash", "method_hash"):
            if review_lock.get(key) != hashes[key]:
                errors.append(
                    make_issue(
                        "GATE_1_INVALIDATED",
                        "review_lock." + key,
                        "{} 已变化；Gate 1、Gate 2 与 alignment 必须重新审阅。".format(key),
                    )
                )
        for key in ("strategy_hash", "topology_hash"):
            if review_lock.get(key) != hashes[key]:
                errors.append(
                    make_issue(
                        "GATE_2_INVALIDATED",
                        "review_lock." + key,
                        "{} 已变化；Gate 2 与 alignment 必须重新确认。".format(key),
                    )
                )
        for key in ("execution_hash", "alignment_hash"):
            if review_lock.get(key) != hashes[key]:
                errors.append(
                    make_issue(
                        "ALIGNMENT_INVALIDATED",
                        "review_lock." + key,
                        "{} 已变化；只作废 alignment，不自动作废已确认的 Gate 2。".format(key),
                    )
                )

        if review_lock.get("gate_0_status") != "confirmed":
            errors.append(make_issue("REVIEW_LOCK_GATE_0_NOT_CONFIRMED", "review_lock.gate_0_status", "review lock 中 Gate 0 未确认。"))
        if review_lock.get("gate_1_status") != "passed":
            errors.append(make_issue("REVIEW_LOCK_GATE_1_NOT_PASSED", "review_lock.gate_1_status", "review lock 中 Gate 1 未通过。"))
        if review_lock.get("gate_2_status") != "confirmed":
            errors.append(make_issue("GATE_2_REQUIRED", "review_lock.gate_2_status", "所有新正式交付必须先确认 Gate 2。"))
        if review_lock.get("alignment_status") != "passed":
            errors.append(make_issue("ALIGNMENT_REQUIRED", "review_lock.alignment_status", "正式交付必须先通过 execution/source alignment。"))
        if not nonempty(review_lock.get("gate_0_note")):
            errors.append(make_issue("GATE_0_NOTE_EMPTY", "review_lock.gate_0_note", "review lock 缺少 Gate 0 确认说明。"))
        if not nonempty(review_lock.get("gate_1_basis")):
            errors.append(make_issue("GATE_1_BASIS_EMPTY", "review_lock.gate_1_basis", "review lock 缺少 Gate 1 依据。"))
        if not nonempty(review_lock.get("gate_2_confirmation_note")):
            errors.append(make_issue("GATE_2_NOTE_EMPTY", "review_lock.gate_2_confirmation_note", "Gate 2 缺少确认说明。"))
        if not nonempty(review_lock.get("alignment_note")):
            errors.append(make_issue("ALIGNMENT_NOTE_EMPTY", "review_lock.alignment_note", "alignment 缺少确认说明。"))

        expected_gate_0_event = gate_0_content_hash(hashes)
        expected_gate_1_event = gate_1_content_hash(hashes)
        expected_gate_2_event = gate_2_content_hash(hashes)
        if expected_gate_0_event not in approval_hashes["gate_0_confirmed"]:
            errors.append(make_issue("GATE_0_APPROVAL_EVENT_MISSING", "approval_events", "当前格式、画幅、节奏和对白速度没有对应的 Gate 0 确认事件。"))
        if expected_gate_1_event not in approval_hashes["gate_1_approved"]:
            errors.append(make_issue("GATE_1_APPROVAL_EVENT_MISSING", "approval_events", "当前 source model 与 director method 没有对应的 Gate 1 审批事件。"))
        if expected_gate_2_event not in approval_hashes["gate_2_confirmed"]:
            errors.append(make_issue("GATE_2_APPROVAL_EVENT_MISSING", "approval_events", "当前 strategy/topology 没有对应的 Gate 2 确认事件。"))
        if hashes["alignment_hash"] not in approval_hashes["alignment_approved"]:
            errors.append(make_issue("ALIGNMENT_APPROVAL_EVENT_MISSING", "approval_events", "当前正式执行与来源绑定没有对应的 alignment 审批事件。"))
        classification_reviews = workspace_source.get("classification_reviews") if isinstance(workspace_source.get("classification_reviews"), list) else []
        for review_index, classification_review in enumerate(classification_reviews):
            if not isinstance(classification_review, dict):
                continue
            review_hash = classification_review.get("review_hash")
            if review_hash not in approval_hashes["classification_approved"]:
                errors.append(
                    make_issue(
                        "CLASSIFICATION_APPROVAL_EVENT_MISSING",
                        f"source.classification_reviews[{review_index}]",
                        "当前 non_narrative 分类复核没有对应的独立审批事件。",
                    )
                )

    metrics = {
        **alignment_report.get("metrics", {}),
        "source_kind_counts": dict(source_kind_counts),
        "scene_count": len(scene_ids),
        "formal_shot_count": len(shot_ids),
        "topology_unit_count": len(topology_unit_ids),
        "dialogue_edit_plan_count": sum(
            len(strategy.get("dialogue_edit_plan", []))
            for strategy in scene_strategies
            if isinstance(strategy, dict) and isinstance(strategy.get("dialogue_edit_plan"), list)
        ),
        "gate_1_mode": gate_one.get("mode"),
        "gate_0_status": review_lock.get("gate_0_status"),
        "gate_2_status": review_lock.get("gate_2_status"),
    }
    result = report(errors, warnings, metrics)
    result["dimensions"] = dict(alignment_report.get("dimensions", {}))
    gate_error_prefixes = (
        "GATE_",
        "REVIEW_LOCK",
        "ALIGNMENT_",
        "APPROVAL_",
        "TOPOLOGY_",
        "FORMAL_SHOTS_",
        "SCENE_STRATEGY_",
        "STRATEGY_",
        "INTRA_",
        "INTER_",
        "BOUNDARY_",
        "CAMERA_",
        "VIEWING_",
        "DIALOGUE_",
        "MISSED_",
        "FORMAT_",
        "PREMATURE_",
    )
    result["dimensions"]["gate_review"] = (
        "FAIL"
        if any(item["code"].startswith(gate_error_prefixes) for item in errors)
        else "PASS"
    )
    result["dimensions"]["formal_structure"] = (
        "FAIL"
        if any(item["code"] in {"FORMAL_SCHEMA_INVALID", "WORKSPACE_SCHEMA_INVALID"} for item in errors)
        else "PASS"
    )
    if errors and all(value == "PASS" for value in result["dimensions"].values()):
        result["dimensions"]["gate_review"] = "FAIL"
    return result


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


def _semantic_preflight(workspace: Dict[str, Any], shot_data: Dict[str, Any]) -> None:
    preflight = validate_workspace(workspace, shot_data, check_review_states=False)
    if preflight["errors"]:
        codes = ", ".join(sorted({item["code"] for item in preflight["errors"]}))
        raise ValueError(f"审批前语义/结构校验失败：{codes}")


def confirm_gate_0(
    workspace: Dict[str, Any],
    shot_data: Dict[str, Any],
    *,
    reviewer: str,
    note: str,
) -> Dict[str, Any]:
    updated = lock_workspace(workspace, shot_data)
    _semantic_preflight(updated, shot_data)
    hashes = all_expected_hashes(updated, shot_data)
    updated["gate_0"].update(
        {
            "status": "confirmed",
            "format_hash": hashes["format_hash"],
            "note": normalize_text(note),
        }
    )
    updated["review_lock"]["gate_0_status"] = "confirmed"
    updated["review_lock"]["gate_0_note"] = normalize_text(note)
    append_approval_event(
        updated,
        event_type="gate_0_confirmed",
        content_hash=gate_0_content_hash(hashes),
        reviewer=reviewer,
        note=note,
    )
    return updated


def approve_gate_1(
    workspace: Dict[str, Any],
    shot_data: Dict[str, Any],
    *,
    reviewer: str,
    note: str,
) -> Dict[str, Any]:
    updated = lock_workspace(workspace, shot_data)
    _semantic_preflight(updated, shot_data)
    hashes = all_expected_hashes(updated, shot_data)
    _, approval_hashes = validate_approval_events(updated)
    if (
        updated.get("review_lock", {}).get("gate_0_status") != "confirmed"
        or gate_0_content_hash(hashes) not in approval_hashes["gate_0_confirmed"]
    ):
        raise ValueError("Gate 1 审批前必须先确认当前成片格式的 Gate 0")
    gate_one = updated["gate_1"]
    review_lock = updated["review_lock"]
    gate_one.update(
        {
            "mode": "confirmed",
            "status": "passed",
            "method_hash": hashes["method_hash"],
            "note": normalize_text(note),
        }
    )
    review_lock["gate_1_status"] = "passed"
    review_lock["gate_1_basis"] = normalize_text(note)
    append_approval_event(
        updated,
        event_type="gate_1_approved",
        content_hash=gate_1_content_hash(hashes),
        reviewer=reviewer,
        note=note,
    )
    return updated


def confirm_gate_2(
    workspace: Dict[str, Any],
    shot_data: Dict[str, Any],
    *,
    reviewer: str,
    note: str,
) -> Dict[str, Any]:
    updated = lock_workspace(workspace, shot_data)
    _semantic_preflight(updated, shot_data)
    hashes = all_expected_hashes(updated, shot_data)
    _, approval_hashes = validate_approval_events(updated)
    if (
        gate_0_content_hash(hashes) not in approval_hashes["gate_0_confirmed"]
        or updated.get("review_lock", {}).get("gate_1_status") != "passed"
        or gate_1_content_hash(hashes) not in approval_hashes["gate_1_approved"]
    ):
        raise ValueError("Gate 2 确认前必须先确认 Gate 0 并通过当前内容的 Gate 1")
    updated["review_lock"]["gate_2_status"] = "confirmed"
    updated["review_lock"]["gate_2_confirmation_note"] = normalize_text(note)
    append_approval_event(
        updated,
        event_type="gate_2_confirmed",
        content_hash=gate_2_content_hash(hashes),
        reviewer=reviewer,
        note=note,
    )
    return updated


def approve_alignment(
    workspace: Dict[str, Any],
    shot_data: Dict[str, Any],
    *,
    reviewer: str,
    note: str,
) -> Dict[str, Any]:
    updated = lock_workspace(workspace, shot_data)
    _semantic_preflight(updated, shot_data)
    hashes = all_expected_hashes(updated, shot_data)
    _, approval_hashes = validate_approval_events(updated)
    if gate_0_content_hash(hashes) not in approval_hashes["gate_0_confirmed"]:
        raise ValueError("alignment 审批前缺少当前格式参数的 Gate 0 确认事件")
    if gate_1_content_hash(hashes) not in approval_hashes["gate_1_approved"]:
        raise ValueError("alignment 审批前缺少当前内容的 Gate 1 审批事件")
    if gate_2_content_hash(hashes) not in approval_hashes["gate_2_confirmed"]:
        raise ValueError("alignment 审批前缺少当前内容的 Gate 2 确认事件")
    updated["review_lock"]["alignment_status"] = "passed"
    updated["review_lock"]["alignment_note"] = normalize_text(note)
    append_approval_event(
        updated,
        event_type="alignment_approved",
        content_hash=hashes["alignment_hash"],
        reviewer=reviewer,
        note=note,
    )
    return updated


def approve_non_narrative_classification(
    workspace: Dict[str, Any],
    shot_data: Dict[str, Any],
    *,
    unit_id: str,
    reviewer: str,
    note: str,
) -> Dict[str, Any]:
    updated = copy.deepcopy(workspace)
    source = updated.get("source") if isinstance(updated.get("source"), dict) else {}
    units = source.get("source_units") if isinstance(source.get("source_units"), list) else []
    unit = next((item for item in units if isinstance(item, dict) and item.get("unit_id") == unit_id), None)
    if unit is None:
        raise ValueError(f"不存在 source unit：{unit_id}")
    if looks_probably_narrative(unit.get("exact_text")):
        raise ValueError("该 source unit 含明确对白或动作信号，禁止批准为 non_narrative")
    unit["kind"] = "metadata"
    unit["authority_role"] = "non_narrative"
    review = {
        "unit_id": unit_id,
        "decision": "non_narrative",
        "status": "approved",
        "reason": normalize_text(note),
        "source_text_hash": alignment_text_hash(unit.get("exact_text")),
        "reviewer": normalize_text(reviewer),
    }
    review["review_hash"] = classification_review_hash(review)
    reviews = source.setdefault("classification_reviews", [])
    if not isinstance(reviews, list):
        raise ValueError("source.classification_reviews 必须是数组")
    reviews[:] = [item for item in reviews if not (isinstance(item, dict) and item.get("unit_id") == unit_id)]
    reviews.append(review)
    updated = lock_workspace(updated, shot_data)
    append_approval_event(
        updated,
        event_type="classification_approved",
        content_hash=review["review_hash"],
        reviewer=reviewer,
        note=note,
    )
    return updated


def _add_review_write_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--shot-data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--note", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="验证并操作 su-fenjingskill 3.1.4 的格式、来源、导演方法、Gate 与 alignment 审批链。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    lock_parser = subparsers.add_parser("lock", help="重算 review lock，并按唯一依赖矩阵作废受影响的审阅阶段。")
    lock_parser.add_argument("--workspace", type=Path, required=True)
    lock_parser.add_argument("--shot-data", type=Path, required=True)
    lock_parser.add_argument("--output", type=Path, required=True)

    validate_parser = subparsers.add_parser("validate", help="验证内部工作区与正式 3.1.4 shot data。")
    validate_parser.add_argument("--workspace", type=Path, required=True)
    validate_parser.add_argument("--shot-data", type=Path, required=True)
    validate_parser.add_argument("--report", type=Path)

    gate0_parser = subparsers.add_parser("confirm-gate0", help="为当前成片类型、画幅、节奏与对白速度写入 Gate 0 确认事件。")
    _add_review_write_args(gate0_parser)

    gate1_parser = subparsers.add_parser("approve-gate1", help="为当前 source model 与 director method 写入 Gate 1 审批事件。")
    _add_review_write_args(gate1_parser)

    gate2_parser = subparsers.add_parser("confirm-gate2", help="为当前 scene strategy 与 topology 写入 Gate 2 确认事件。")
    _add_review_write_args(gate2_parser)

    alignment_parser = subparsers.add_parser("approve-alignment", help="为当前来源绑定与正式执行写入 alignment 审批事件。")
    _add_review_write_args(alignment_parser)

    classification_parser = subparsers.add_parser("approve-classification", help="人工批准一个 source unit 为 non_narrative metadata；操作后 Gate 1/2/alignment 均失效。")
    _add_review_write_args(classification_parser)
    classification_parser.add_argument("--unit-id", required=True)

    status_parser = subparsers.add_parser("status", help="输出当前哈希、状态和审批事件匹配情况。")
    status_parser.add_argument("--workspace", type=Path, required=True)
    status_parser.add_argument("--shot-data", type=Path, required=True)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        workspace = load_json(args.workspace)
        shot_data = load_json(args.shot_data)
        if args.command == "lock":
            updated = lock_workspace(workspace, shot_data)
            write_json(args.output, updated)
            sys.stdout.write("workspace: {}\n".format(args.output))
            return 0
        if args.command == "validate":
            review_report = validate_workspace(workspace, shot_data)
            if args.report:
                write_json(args.report, review_report)
            sys.stdout.write(json.dumps(review_report, ensure_ascii=False, indent=2) + "\n")
            return 0 if review_report["status"] == "PASS" else 1
        if args.command == "confirm-gate0":
            updated = confirm_gate_0(workspace, shot_data, reviewer=args.reviewer, note=args.note)
        elif args.command == "approve-gate1":
            updated = approve_gate_1(workspace, shot_data, reviewer=args.reviewer, note=args.note)
        elif args.command == "confirm-gate2":
            updated = confirm_gate_2(workspace, shot_data, reviewer=args.reviewer, note=args.note)
        elif args.command == "approve-alignment":
            updated = approve_alignment(workspace, shot_data, reviewer=args.reviewer, note=args.note)
        elif args.command == "approve-classification":
            updated = approve_non_narrative_classification(
                workspace,
                shot_data,
                unit_id=args.unit_id,
                reviewer=args.reviewer,
                note=args.note,
            )
        elif args.command == "status":
            hashes = all_expected_hashes(workspace, shot_data)
            approval_errors, approval_hashes = validate_approval_events(workspace)
            payload = {
                "expected_hashes": hashes,
                "stored_review_lock": workspace.get("review_lock"),
                "approval_chain_errors": approval_errors,
                "approval_matches": {
                    "gate_0": gate_0_content_hash(hashes) in approval_hashes["gate_0_confirmed"],
                    "gate_1": gate_1_content_hash(hashes) in approval_hashes["gate_1_approved"],
                    "gate_2": gate_2_content_hash(hashes) in approval_hashes["gate_2_confirmed"],
                    "alignment": hashes["alignment_hash"] in approval_hashes["alignment_approved"],
                },
            }
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            return 0
        else:  # pragma: no cover
            raise ValueError(f"未知命令：{args.command}")
        write_json(args.output, updated)
        sys.stdout.write("workspace: {}\n".format(args.output))
        return 0
    except FileExistsError as exc:
        sys.stderr.write("FAIL: {}\n".format(exc))
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write("FAIL: {}\n".format(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
