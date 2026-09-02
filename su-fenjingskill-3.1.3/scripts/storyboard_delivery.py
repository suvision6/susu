#!/usr/bin/env python3
"""Formal director-shot-data/3.1.3 backend shipped by su-fenjingskill 3.1.3.

This module protects source text, checks deterministic contradictions, and renders
files. It intentionally does not decide shot count, camera style, or artistic
quality; those remain director decisions defined by SKILL.md and references/.
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
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

try:  # supports both script-path and ``python -m scripts...`` execution
    from ._chinese_context import (
        chinese_dialogue_minimum_seconds,
        contains_cjk,
        dialogue_label_issue,
        leaked_internal_enums,
        remarks_policy,
    )
    from ._schema_validation import validate_formal_schema
    from ._execution_text import canonical_execution_text
    from ._xlsx_projection import XlsxProjectionError, render_xlsx_execution_text
    from .source_alignment import materialize_source_excerpts
    from .storyboard_review import validate_workspace
except ImportError:  # pragma: no cover - script-path execution
    from _chinese_context import (
        chinese_dialogue_minimum_seconds,
        contains_cjk,
        dialogue_label_issue,
        leaked_internal_enums,
        remarks_policy,
    )
    from _schema_validation import validate_formal_schema
    from _execution_text import canonical_execution_text
    from _xlsx_projection import XlsxProjectionError, render_xlsx_execution_text
    from source_alignment import materialize_source_excerpts
    from storyboard_review import validate_workspace

CONTRACT_NAME = "director-shot-data"
CONTRACT_VERSION = "3.1.3"
SOURCE_SKILL = "su-fenjingskill"
SOURCE_SKILL_VERSION = "3.1.3"

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHOT_ID_RE = re.compile(r"^SH([0-9]{3,})$")
SCENE_ID_RE = re.compile(r"^SC[0-9]{3,}$")
DIALOGUE_ID_RE = re.compile(r"^D[0-9]{3,}$")

GENERIC_MOTIVATIONS = (
    "更有电影感",
    "丰富角度",
    "避免重复",
    "画面更丰富",
    "保持流畅",
    "增强氛围",
    "增加变化",
    "避免单调",
)
PLACEHOLDER_TERMS = (
    "按原文",
    "完成信息",
    "所在区域",
    "处于主要观看位置",
    "按事件顺序",
    "当前可见结果",
)
VIEWPOINT_OWNER_TYPES = {"subject", "relationship", "object", "space", "subjective"}
READING_PRIORITIES = {"space", "relationship", "body", "face", "detail"}
CAMERA_RESPONSES = {"observe", "isolate", "reframe", "follow", "reveal", "withhold"}
FRAMING_MODES = {"single", "two_shot", "group", "over_shoulder", "insert", "subjective", "space"}
BODY_DETAIL_SUFFIXES = {
    "手", "双手", "左手", "右手", "脚", "双脚", "左脚", "右脚", "脸", "眼睛", "目光",
    "背影", "身体", "声音", "呼吸", "衣角", "影子", "喉结", "嘴唇", "耳朵", "耳根",
}


def normalize_text(value: Any) -> str:
    """Normalize line endings and trailing whitespace without rewriting content."""
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def get_nonempty_string(obj: dict[str, Any], key: str) -> bool:
    return isinstance(obj.get(key), str) and bool(obj[key].strip())


def _string_array(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [normalize_text(item) for item in value if isinstance(item, str) and normalize_text(item)]


def _same_subject(left: Any, right: Any) -> bool:
    """Match one named subject with its explicit body/trace representation."""
    left_text = re.sub(r"\s+", "", normalize_text(left)).casefold()
    right_text = re.sub(r"\s+", "", normalize_text(right)).casefold()
    if not left_text or not right_text:
        return False
    if left_text == right_text:
        return True
    for whole, detail in ((left_text, right_text), (right_text, left_text)):
        prefix = whole + "的"
        if detail.startswith(prefix) and detail[len(prefix):] in BODY_DETAIL_SUFFIXES:
            return True
    return False


def _contains_subject(subjects: list[str], target: Any) -> bool:
    return any(_same_subject(item, target) for item in subjects)


def _camera_design_issues(
    shot: dict[str, Any],
    dialogue_map: dict[str, dict[str, Any]],
    path: str,
) -> list[dict[str, str]]:
    """Validate factual viewing choices without imposing category quotas."""
    errors: list[dict[str, str]] = []
    viewpoint = shot.get("viewpoint") if isinstance(shot.get("viewpoint"), dict) else {}
    camera = shot.get("camera") if isinstance(shot.get("camera"), dict) else {}
    staging = shot.get("staging") if isinstance(shot.get("staging"), dict) else {}
    sound = shot.get("sound") if isinstance(shot.get("sound"), dict) else {}

    enum_fields = (
        (viewpoint, "owner_type", VIEWPOINT_OWNER_TYPES, f"{path}.viewpoint.owner_type"),
        (viewpoint, "reading_priority", READING_PRIORITIES, f"{path}.viewpoint.reading_priority"),
        (viewpoint, "camera_response", CAMERA_RESPONSES, f"{path}.viewpoint.camera_response"),
        (camera, "framing_mode", FRAMING_MODES, f"{path}.camera.framing_mode"),
    )
    for container, field, allowed, field_path in enum_fields:
        if container.get(field) not in allowed:
            errors.append(issue("CAMERA_DESIGN_UNRESOLVED", field_path, f"{field} 尚未形成正式摄影决定。"))

    owner_refs = _string_array(viewpoint.get("owner_refs"))
    primary_subjects = _string_array(camera.get("primary_subjects"))
    foreground_subjects = _string_array(camera.get("foreground_subjects"))
    subjects = _string_array(staging.get("subjects"))
    visible_subjects = _string_array(staging.get("visible_subjects"))
    offscreen_subjects = _string_array(staging.get("offscreen_subjects"))
    for value, field_path, label in (
        (owner_refs, f"{path}.viewpoint.owner_refs", "画面所有者"),
        (camera.get("shot_size_reason"), f"{path}.camera.shot_size_reason", "景别理由"),
        (camera.get("angle_reason"), f"{path}.camera.angle_reason", "角度理由"),
        (viewpoint.get("reason"), f"{path}.viewpoint.reason", "观看理由"),
    ):
        if (isinstance(value, list) and not value) or (not isinstance(value, list) and not normalize_text(value)):
            errors.append(issue("CAMERA_DESIGN_UNRESOLVED", field_path, f"{label}尚未形成正式决定。"))

    semantic_overlap = sorted(
        {visible for visible in visible_subjects for hidden in offscreen_subjects if _same_subject(visible, hidden)}
    )
    if semantic_overlap:
        errors.append(
            issue(
                "SUBJECT_VISIBILITY_OVERLAP",
                f"{path}.staging",
                "同一主体不能同时处于画内与画外：{}。".format("、".join(semantic_overlap)),
            )
        )
    unassigned = [
        subject for subject in subjects
        if not _contains_subject(visible_subjects, subject) and not _contains_subject(offscreen_subjects, subject)
    ]
    if unassigned:
        errors.append(
            issue(
                "SUBJECT_VISIBILITY_UNDECLARED",
                f"{path}.staging",
                "镜头主体必须明确画内或画外状态：{}。".format("、".join(unassigned)),
            )
        )
    unknown_states = [
        subject for subject in visible_subjects + offscreen_subjects
        if not _contains_subject(subjects, subject)
    ]
    if unknown_states:
        errors.append(
            issue(
                "SUBJECT_VISIBILITY_UNKNOWN",
                f"{path}.staging",
                "画内／画外状态引用了未登记的镜头主体：{}。".format("、".join(unknown_states)),
            )
        )

    for subject in primary_subjects:
        if not _contains_subject(visible_subjects, subject):
            errors.append(issue("FRAMING_SUBJECT_NOT_VISIBLE", f"{path}.camera.primary_subjects", f"主要主体 {subject} 必须位于画内。"))
    for subject in foreground_subjects:
        if not _contains_subject(visible_subjects, subject):
            errors.append(issue("FRAMING_SUBJECT_NOT_VISIBLE", f"{path}.camera.foreground_subjects", f"前景主体 {subject} 必须位于画内。"))

    framing_mode = camera.get("framing_mode")
    if framing_mode == "single" and len(primary_subjects) != 1:
        errors.append(issue("FRAMING_CARDINALITY_INVALID", f"{path}.camera.primary_subjects", "single 必须恰有一个主要主体。"))
    elif framing_mode == "two_shot" and len(primary_subjects) != 2:
        errors.append(issue("FRAMING_CARDINALITY_INVALID", f"{path}.camera.primary_subjects", "two_shot 必须恰有两个主要主体。"))
    elif framing_mode == "group" and len(primary_subjects) < 3:
        errors.append(issue("FRAMING_CARDINALITY_INVALID", f"{path}.camera.primary_subjects", "group 必须至少有三个主要主体。"))
    elif framing_mode == "over_shoulder":
        if not primary_subjects or not foreground_subjects or any(
            _same_subject(primary, foreground)
            for primary in primary_subjects
            for foreground in foreground_subjects
        ):
            errors.append(
                issue(
                    "OVER_SHOULDER_SUBJECTS_INVALID",
                    f"{path}.camera",
                    "over_shoulder 必须同时提供互不重叠的前景主体和主要主体。",
                )
            )
    if framing_mode == "insert":
        owner_type = viewpoint.get("owner_type")
        has_body_detail = any("的" in item and item.rsplit("的", 1)[-1] in BODY_DETAIL_SUFFIXES for item in primary_subjects)
        if viewpoint.get("reading_priority") != "detail" or owner_type not in {"object", "subject"} or not primary_subjects or (
            owner_type == "subject" and not has_body_detail
        ):
            errors.append(
                issue(
                    "INSERT_VIEWPOINT_INVALID",
                    f"{path}.viewpoint",
                    "insert 必须以物件或身体细节为主要对象，并把读取优先级设为 detail。",
                )
            )

    if viewpoint.get("owner_type") != "space":
        missing_owner_refs = [item for item in owner_refs if not _contains_subject(visible_subjects, item)]
        if viewpoint.get("owner_type") == "subjective":
            missing_owner_refs = [
                item for item in owner_refs
                if not _contains_subject(visible_subjects + offscreen_subjects, item)
            ]
        if missing_owner_refs:
            errors.append(
                issue(
                    "VIEWPOINT_OWNER_NOT_RESOLVED",
                    f"{path}.viewpoint.owner_refs",
                    "画面所有者未落实到当前可见／主观主体：{}。".format("、".join(missing_owner_refs)),
                )
            )

    dialogue_segments = sound.get("dialogue_segments") if isinstance(sound.get("dialogue_segments"), list) else []
    for segment_index, segment in enumerate(dialogue_segments):
        if not isinstance(segment, dict):
            continue
        source_line = dialogue_map.get(segment.get("dialogue_id"))
        if not isinstance(source_line, dict):
            continue
        speaker = source_line.get("speaker")
        delivery = segment.get("delivery")
        segment_path = f"{path}.sound.dialogue_segments[{segment_index}].delivery"
        if delivery == "onscreen" and not _contains_subject(visible_subjects, speaker):
            errors.append(issue("DIALOGUE_VISIBILITY_MISMATCH", segment_path, f"画内对白说话者 {speaker} 必须可见。"))
        elif delivery == "os" and (
            not _contains_subject(offscreen_subjects, speaker) or _contains_subject(visible_subjects, speaker)
        ):
            errors.append(issue("DIALOGUE_VISIBILITY_MISMATCH", segment_path, f"画外对白说话者 {speaker} 必须只登记为画外。"))

    response = viewpoint.get("camera_response")
    movement = camera.get("movement") if isinstance(camera.get("movement"), dict) else {}
    movement_type = movement.get("type")
    flow_owners = {item.get("owner") for item in shot.get("shot_flow", []) if isinstance(item, dict)}
    if response == "follow" and movement_type not in {"follow", "track"}:
        errors.append(issue("CAMERA_RESPONSE_NOT_REALIZED", f"{path}.viewpoint.camera_response", "follow 必须由跟随或横移运动落实。"))
    if response in {"reframe", "reveal"} and movement_type == "fixed" and not flow_owners.intersection({"blocking", "focus"}):
        errors.append(issue("CAMERA_RESPONSE_NOT_REALIZED", f"{path}.viewpoint.camera_response", f"{response} 必须由调度、焦点或摄影机运动落实。"))
    return errors


def expected_shot_id(index: int) -> str:
    return f"SH{index:03d}"


def validate_structure(data: Any, *, allow_legacy: bool = False) -> dict[str, Any]:
    """Validate deterministic contract and source-integrity rules.

    Artistic repetition, style, pacing, or coverage choices are warnings at most.
    """
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not isinstance(data, dict):
        errors.append(issue("DATA_NOT_OBJECT", "$", "顶层数据必须是 JSON 对象。"))
        return _report(errors, warnings, 0, 0, 0.0, 0)

    is_legacy_contract = (
        allow_legacy
        and data.get("contract_version") == "3.1.0"
        and data.get("source_skill_version") == "3.1.1"
    )
    if not is_legacy_contract:
        errors.extend(validate_formal_schema(data))

    expected_constants = {
        "contract_name": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "source_skill": SOURCE_SKILL,
        "source_skill_version": SOURCE_SKILL_VERSION,
    }
    for key, expected in expected_constants.items():
        if allow_legacy and key == "contract_version" and data.get(key) == "3.1.0":
            continue
        if allow_legacy and key == "source_skill_version" and data.get(key) == "3.1.1":
            continue
        if data.get(key) != expected:
            errors.append(
                issue(
                    "CONTRACT_IDENTITY_MISMATCH",
                    key,
                    f"应为 {expected!r}，当前为 {data.get(key)!r}。",
                )
            )

    project_id = data.get("project_id")
    if not isinstance(project_id, str) or not PROJECT_ID_RE.fullmatch(project_id):
        warnings.append(
            issue(
                "PROJECT_ID_FALLBACK_NEEDED",
                "project_id",
                "project_id 缺失或格式不稳定；构建时可使用稳定临时值，不阻断导演方案。",
            )
        )

    source = data.get("source")
    if not isinstance(source, dict):
        errors.append(issue("SOURCE_MISSING", "source", "缺少 source 对象。"))
        source = {}

    locked_text = normalize_text(source.get("locked_text"))
    source_has_cjk = contains_cjk(locked_text)
    if not locked_text:
        errors.append(issue("LOCKED_TEXT_EMPTY", "source.locked_text", "来源文本为空，无法保护事实与对白。"))

    if not get_nonempty_string(source, "title"):
        warnings.append(issue("TITLE_FALLBACK_NEEDED", "source.title", "标题为空；可使用稳定临时标题。"))

    slug = source.get("delivery_slug")
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        warnings.append(
            issue(
                "DELIVERY_SLUG_FALLBACK_NEEDED",
                "source.delivery_slug",
                "delivery_slug 不是 ASCII 小写 kebab-case；构建时将采用稳定临时 slug。",
            )
        )

    input_kind = source.get("input_kind")
    allowed_input_kinds = {"screenplay", "screenplay_segment", "locked_fragment", "concept_board"}
    if input_kind not in allowed_input_kinds:
        errors.append(
            issue(
                "INPUT_KIND_INVALID",
                "source.input_kind",
                f"input_kind 必须属于 {sorted(allowed_input_kinds)}。",
            )
        )

    dialogue_lines = source.get("dialogue_lines", [])
    if not isinstance(dialogue_lines, list):
        errors.append(issue("DIALOGUE_LINES_NOT_ARRAY", "source.dialogue_lines", "dialogue_lines 必须是数组。"))
        dialogue_lines = []

    dialogue_map: dict[str, dict[str, Any]] = {}
    for index, line in enumerate(dialogue_lines):
        path = f"source.dialogue_lines[{index}]"
        if not isinstance(line, dict):
            errors.append(issue("DIALOGUE_LINE_INVALID", path, "对白项必须是对象。"))
            continue
        dialogue_id = line.get("dialogue_id")
        if not isinstance(dialogue_id, str) or not DIALOGUE_ID_RE.fullmatch(dialogue_id):
            errors.append(issue("DIALOGUE_ID_INVALID", f"{path}.dialogue_id", "对白 ID 应为 D001、D002……"))
            continue
        if dialogue_id in dialogue_map:
            errors.append(issue("DIALOGUE_ID_DUPLICATE", f"{path}.dialogue_id", f"对白 ID {dialogue_id} 重复。"))
            continue
        dialogue_map[dialogue_id] = line
        text = normalize_text(line.get("text"))
        speaker = normalize_text(line.get("speaker"))
        if not text:
            errors.append(issue("DIALOGUE_TEXT_EMPTY", f"{path}.text", "对白正文为空。"))
        elif locked_text and text not in locked_text:
            errors.append(
                issue(
                    "DIALOGUE_NOT_IN_SOURCE",
                    f"{path}.text",
                    f"对白 {dialogue_id} 未逐字出现在 locked_text 中。",
                )
            )
        label_issue = dialogue_label_issue(text, speaker)
        if label_issue == "speaker-label":
            errors.append(
                issue(
                    "CHINESE_DIALOGUE_SPEAKER_LABEL",
                    f"{path}.text",
                    "中文实际口播混入角色名或说话标签；角色名与括号表演说明必须分离。",
                )
            )
        elif label_issue == "performance-direction":
            errors.append(
                issue(
                    "CHINESE_DIALOGUE_DIRECTION_LABEL",
                    f"{path}.text",
                    "中文实际口播不得以括号表演说明开头。",
                )
            )
        if not get_nonempty_string(line, "speaker"):
            errors.append(issue("DIALOGUE_SPEAKER_EMPTY", f"{path}.speaker", "对白说话者为空。"))
        if line.get("voice_type") not in {"scene_dialogue", "vo", "mediated", "unresolved"}:
            errors.append(issue("VOICE_TYPE_INVALID", f"{path}.voice_type", "声音身份不在允许集合中。"))

    assumptions = data.get("assumptions", [])
    if not isinstance(assumptions, list):
        errors.append(issue("ASSUMPTIONS_NOT_ARRAY", "assumptions", "assumptions 必须是数组。"))
        assumptions = []
    open_assumptions = 0
    seen_assumption_ids: set[str] = set()
    for index, assumption in enumerate(assumptions):
        path = f"assumptions[{index}]"
        if not isinstance(assumption, dict):
            errors.append(issue("ASSUMPTION_INVALID", path, "假设项必须是对象。"))
            continue
        assumption_id = assumption.get("assumption_id")
        if not isinstance(assumption_id, str) or not re.fullmatch(r"^A[0-9]{3,}$", assumption_id):
            errors.append(issue("ASSUMPTION_ID_INVALID", f"{path}.assumption_id", "假设 ID 应为 A001、A002……"))
        elif assumption_id in seen_assumption_ids:
            errors.append(issue("ASSUMPTION_ID_DUPLICATE", f"{path}.assumption_id", f"假设 ID {assumption_id} 重复。"))
        else:
            seen_assumption_ids.add(assumption_id)
        for key in ("scope", "statement", "reason", "impact", "status"):
            if not get_nonempty_string(assumption, key):
                errors.append(issue("ASSUMPTION_FIELD_EMPTY", f"{path}.{key}", f"假设字段 {key} 为空。"))
        if assumption.get("scope") not in {"source", "scene", "shot", "delivery"}:
            errors.append(issue("ASSUMPTION_SCOPE_INVALID", f"{path}.scope", "假设 scope 无效。"))
        if assumption.get("status") not in {"open", "confirmed", "resolved"}:
            errors.append(issue("ASSUMPTION_STATUS_INVALID", f"{path}.status", "假设 status 无效。"))
        if assumption.get("status") == "open":
            open_assumptions += 1
            warnings.append(
                issue(
                    "OPEN_ASSUMPTION",
                    path,
                    f"开放假设：{str(assumption.get('statement', '')).rstrip('。；; ')}；影响：{assumption.get('impact', '')}",
                )
            )

    director_design = data.get("director_design")
    required_design_fields = (
        "scene_purpose",
        "dramatic_question",
        "turning_point",
        "audience_position",
        "pov_strategy",
        "emotional_arc",
        "blocking_strategy",
        "visual_strategy",
        "sound_strategy",
        "rhythm_strategy",
    )
    if not isinstance(director_design, dict):
        errors.append(issue("DIRECTOR_DESIGN_MISSING", "director_design", "缺少导演设计。"))
    else:
        for key in required_design_fields:
            if not get_nonempty_string(director_design, key):
                errors.append(issue("DIRECTOR_DESIGN_FIELD_EMPTY", f"director_design.{key}", f"导演设计字段 {key} 为空。"))

    scenes = data.get("scenes", [])
    if not isinstance(scenes, list) or not scenes:
        errors.append(issue("SCENES_EMPTY", "scenes", "至少需要一个场景。"))
        scenes = []

    scene_map: dict[str, dict[str, Any]] = {}
    for index, scene in enumerate(scenes):
        path = f"scenes[{index}]"
        if not isinstance(scene, dict):
            errors.append(issue("SCENE_INVALID", path, "场景项必须是对象。"))
            continue
        scene_id = scene.get("scene_id")
        if not isinstance(scene_id, str) or not SCENE_ID_RE.fullmatch(scene_id):
            errors.append(issue("SCENE_ID_INVALID", f"{path}.scene_id", "场景 ID 应为 SC001、SC002……"))
            continue
        if scene_id in scene_map:
            errors.append(issue("SCENE_ID_DUPLICATE", f"{path}.scene_id", f"场景 ID {scene_id} 重复。"))
            continue
        scene_map[scene_id] = scene
        if not get_nonempty_string(scene, "scene"):
            errors.append(issue("SCENE_NAME_EMPTY", f"{path}.scene", "场景名称为空。"))
        if not get_nonempty_string(scene, "source_excerpt"):
            errors.append(issue("SCENE_EXCERPT_EMPTY", f"{path}.source_excerpt", "场景原文段落为空。"))
        for key in ("lighting_strategy", "color_strategy"):
            if not get_nonempty_string(scene, key):
                warnings.append(issue("SCENE_STRATEGY_EMPTY", f"{path}.{key}", f"{key} 为空；若无变化，可写明继承自然光或场级基线。"))

    shots = data.get("shots", [])
    if not isinstance(shots, list) or not shots:
        errors.append(issue("SHOTS_EMPTY", "shots", "至少需要一个镜头。"))
        shots = []

    segment_map: dict[str, list[str]] = defaultdict(list)
    shot_sizes: list[str] = []
    angles: list[str] = []
    movements: list[str] = []
    total_duration = 0.0

    for index, shot in enumerate(shots, start=1):
        path = f"shots[{index - 1}]"
        if not isinstance(shot, dict):
            errors.append(issue("SHOT_INVALID", path, "镜头项必须是对象。"))
            continue

        shot_id = shot.get("shot_id")
        expected_id = expected_shot_id(index)
        if shot_id != expected_id:
            errors.append(
                issue(
                    "SHOT_ID_SEQUENCE",
                    f"{path}.shot_id",
                    f"镜号应按数组顺序连续为 {expected_id}，当前为 {shot_id!r}。",
                )
            )

        scene_id = shot.get("scene_id")
        if scene_id not in scene_map:
            errors.append(issue("SHOT_SCENE_UNKNOWN", f"{path}.scene_id", f"镜头引用不存在的场景 {scene_id!r}。"))

        if not get_nonempty_string(shot, "source_excerpt"):
            errors.append(issue("SHOT_EXCERPT_EMPTY", f"{path}.source_excerpt", "镜头原剧本段落为空。"))

        duration = shot.get("duration_seconds")
        numeric_duration = 0.0
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
            errors.append(issue("DURATION_INVALID", f"{path}.duration_seconds", "镜头时长必须大于 0。"))
        else:
            numeric_duration = float(duration)
            total_duration += numeric_duration

        motivation = shot.get("motivation")
        if not isinstance(motivation, dict):
            errors.append(issue("MOTIVATION_MISSING", f"{path}.motivation", "每个镜头都必须说明存在理由。"))
        else:
            if motivation.get("primary") not in {"information", "emotion", "relationship", "space", "subjective", "rhythm", "transition"}:
                errors.append(issue("MOTIVATION_PRIMARY_INVALID", f"{path}.motivation.primary", "镜头动机类别无效。"))
            for key in ("reason",):
                if not get_nonempty_string(motivation, key):
                    errors.append(issue("MOTIVATION_EMPTY", f"{path}.motivation.{key}", f"镜头动机字段 {key} 为空。"))
            motivation_text = str(motivation.get("reason", ""))
            if any(term in motivation_text for term in GENERIC_MOTIVATIONS):
                warnings.append(issue("GENERIC_SHOT_MOTIVATION", f"{path}.motivation", "镜头动机包含通用美化词；应改写为当前人物、信息、空间或节奏的具体收益。"))

        camera = shot.get("camera")
        if not isinstance(camera, dict):
            errors.append(issue("CAMERA_MISSING", f"{path}.camera", "缺少摄影设计。"))
            camera = {}
        for key in ("shot_size", "angle", "position", "composition", "lens_intent", "focus"):
            if not get_nonempty_string(camera, key):
                errors.append(issue("CAMERA_FIELD_EMPTY", f"{path}.camera.{key}", f"摄影字段 {key} 为空。"))
        shot_sizes.append(str(camera.get("shot_size", "")))
        angles.append(str(camera.get("angle", "")))
        movement = camera.get("movement")
        if not isinstance(movement, dict):
            errors.append(issue("MOVEMENT_MISSING", f"{path}.camera.movement", "缺少摄录机运动对象。"))
        else:
            movement_type = str(movement.get("type", ""))
            movements.append(movement_type)
            allowed_movements = {
                "fixed", "push", "pull", "pan", "tilt", "track", "follow",
                "orbit", "crane", "handheld", "vehicle", "zoom", "focus",
                "compound", "other",
            }
            if movement_type not in allowed_movements:
                errors.append(issue("MOVEMENT_TYPE_INVALID", f"{path}.camera.movement.type", "摄影机运动类型无效。"))
            if not get_nonempty_string(movement, "reason"):
                errors.append(issue("MOVEMENT_REASON_EMPTY", f"{path}.camera.movement.reason", "固定或运动都必须说明观看理由。"))
            if movement_type != "fixed":
                for key in ("trigger", "speed", "path", "end_condition"):
                    if not get_nonempty_string(movement, key):
                        errors.append(issue("MOVEMENT_EXECUTION_INCOMPLETE", f"{path}.camera.movement.{key}", f"非固定镜头缺少 {key}。"))

        errors.extend(_camera_design_issues(shot, dialogue_map, path))

        execution_text = shot.get("execution_text")
        if not isinstance(execution_text, str) or not execution_text.strip():
            errors.append(issue("EXECUTION_TEXT_EMPTY", f"{path}.execution_text", "后台 execution_text 为空。"))
        else:
            for term in PLACEHOLDER_TERMS:
                if term in execution_text:
                    warnings.append(issue("EXECUTION_PLACEHOLDER", f"{path}.execution_text", f"画面内容含模板词“{term}”；应改为可见、可拍的具体描述。"))
            required_sections = ("【观看】", "【摄影】", "【调度与表演】", "【声音】", "【剪辑】", "【连续性】", "【镜头动机】")
            if not all(section in execution_text for section in required_sections):
                errors.append(issue("EXECUTION_FORMAT_INVALID", f"{path}.execution_text", "后台 execution_text 缺少 canonical sections。"))
            if source_has_cjk and not contains_cjk(execution_text):
                errors.append(
                    issue(
                        "CHINESE_EXECUTION_TEXT_REQUIRED",
                        f"{path}.execution_text",
                        "中文来源的后台 execution_text 必须包含可执行中文，不能只交付英文或内部代码。",
                    )
                )
            leaked_terms = leaked_internal_enums(execution_text, locked_text)
            if leaked_terms:
                errors.append(
                    issue(
                        "CHINESE_EXECUTION_INTERNAL_ENUM",
                        f"{path}.execution_text",
                        "后台 execution_text 泄露内部枚举：{}。".format(", ".join(leaked_terms)),
                    )
                )
            canonical_text = canonical_execution_text(shot)
            if normalize_text(execution_text) != normalize_text(canonical_text):
                errors.append(
                    issue(
                        "EXECUTION_TEXT_DIVERGED",
                        f"{path}.execution_text",
                        "后台 execution_text 必须由结构化观看、摄影、调度、声音、剪辑、连续性、动机与时长依据确定性生成；当前文字已与 canonical shot model 漂移。",
                    )
                )

        sound = shot.get("sound")
        if sound is not None and not isinstance(sound, dict):
            errors.append(issue("SOUND_INVALID", f"{path}.sound", "sound 必须是对象。"))
            sound = None
        if isinstance(sound, dict):
            shot_dialogue_texts: list[str] = []
            segments = sound.get("dialogue_segments", [])
            if not isinstance(segments, list):
                errors.append(issue("DIALOGUE_SEGMENTS_NOT_ARRAY", f"{path}.sound.dialogue_segments", "dialogue_segments 必须是数组。"))
                segments = []
            for segment_index, segment in enumerate(segments):
                segment_path = f"{path}.sound.dialogue_segments[{segment_index}]"
                if not isinstance(segment, dict):
                    errors.append(issue("DIALOGUE_SEGMENT_INVALID", segment_path, "对白播放片段必须是对象。"))
                    continue
                dialogue_id = segment.get("dialogue_id")
                if dialogue_id not in dialogue_map:
                    errors.append(issue("DIALOGUE_REFERENCE_UNKNOWN", f"{segment_path}.dialogue_id", f"引用不存在的对白 {dialogue_id!r}。"))
                    continue
                text = segment.get("text")
                if not isinstance(text, str) or text == "":
                    errors.append(issue("DIALOGUE_SEGMENT_EMPTY", f"{segment_path}.text", "对白播放片段为空。"))
                else:
                    segment_map[dialogue_id].append(text)
                    shot_dialogue_texts.append(text)
                    if isinstance(execution_text, str) and text not in execution_text:
                        errors.append(
                            issue(
                                "DIALOGUE_NOT_IN_EXECUTION_TEXT",
                                f"{segment_path}.text",
                                f"对白片段 {dialogue_id} 未逐字出现在本镜 execution_text 中。",
                            )
                        )
                delivery = segment.get("delivery")
                if delivery not in {"onscreen", "os", "vo", "mediated", "unresolved"}:
                    errors.append(issue("DIALOGUE_DELIVERY_INVALID", f"{segment_path}.delivery", "对白在本镜中的落位无效。"))
                source_voice = dialogue_map[dialogue_id].get("voice_type")
                if source_voice == "vo" and delivery != "vo":
                    errors.append(issue("VOICE_IDENTITY_CHANGED", segment_path, f"来源对白 {dialogue_id} 为 VO，不得改成 {delivery}。"))
                if source_voice == "mediated" and delivery != "mediated":
                    errors.append(issue("VOICE_IDENTITY_CHANGED", segment_path, f"来源对白 {dialogue_id} 为介质声，不得改成 {delivery}。"))
                if source_voice == "unresolved" and delivery != "unresolved":
                    warnings.append(issue("UNRESOLVED_VOICE_ASSUMED", segment_path, f"来源对白 {dialogue_id} 声音身份未决，当前暂定为 {delivery}；应登记假设。"))
            chinese_playback = "".join(
                text for text in shot_dialogue_texts if contains_cjk(text)
            )
            minimum_seconds = chinese_dialogue_minimum_seconds(chinese_playback)
            if chinese_playback and numeric_duration and minimum_seconds > numeric_duration:
                errors.append(
                    issue(
                        "CHINESE_DIALOGUE_UNPLAYABLE",
                        f"{path}.duration_seconds",
                        (
                            f"{shot_id} 的中文对白最低可播时间约 {minimum_seconds:.2f} 秒，"
                            f"当前镜长为 {numeric_duration:g} 秒。"
                        ),
                    )
                )

        notes = normalize_text(shot.get("notes"))
        note_policy = remarks_policy(notes)
        if note_policy == "review":
            warnings.append(
                issue(
                    "REMARKS_SEMANTIC_REVIEW",
                    f"{path}.notes",
                    "备注只应保存真实待确认或有意连续性违例；请人工复核该非空备注。",
                )
            )

        continuity = shot.get("continuity")
        if continuity is not None and not isinstance(continuity, dict):
            errors.append(issue("CONTINUITY_INVALID", f"{path}.continuity", "continuity 必须是对象。"))
            continuity = None
        if isinstance(continuity, dict):
            breaks = continuity.get("intentional_breaks", [])
            if not isinstance(breaks, list):
                errors.append(issue("INTENTIONAL_BREAKS_NOT_ARRAY", f"{path}.continuity.intentional_breaks", "intentional_breaks 必须是数组。"))
            else:
                for break_index, deliberate_break in enumerate(breaks):
                    break_path = f"{path}.continuity.intentional_breaks[{break_index}]"
                    if not isinstance(deliberate_break, dict):
                        errors.append(issue("INTENTIONAL_BREAK_INVALID", break_path, "有意连续性破坏必须是对象。"))
                        continue
                    for key in ("what_breaks", "audience_effect", "dramatic_reason", "reorientation"):
                        if not get_nonempty_string(deliberate_break, key):
                            errors.append(issue("INTENTIONAL_BREAK_INCOMPLETE", f"{break_path}.{key}", f"有意破坏缺少 {key}。"))

        try:
            render_xlsx_execution_text(shot, dialogue_map)
        except XlsxProjectionError as exc:
            errors.append(
                issue(
                    "XLSX_PROJECTION_INVALID",
                    f"{path}.shot_flow",
                    str(exc),
                )
            )

    for dialogue_id, line in dialogue_map.items():
        source_text = str(line.get("text", ""))
        rendered_text = "".join(segment_map.get(dialogue_id, []))
        if rendered_text != source_text:
            errors.append(
                issue(
                    "DIALOGUE_COVERAGE_MISMATCH",
                    f"source.dialogue_lines[{dialogue_id}]",
                    f"对白 {dialogue_id} 的跨镜片段拼接后不等于来源原文：来源={source_text!r}，拼接={rendered_text!r}。",
                )
            )

    return _report(
        errors,
        warnings,
        len(scenes),
        len(shots),
        total_duration,
        open_assumptions,
    )


def _report(
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
    scene_count: int,
    shot_count: int,
    total_duration: float,
    open_assumption_count: int,
) -> dict[str, Any]:
    if errors:
        status = "FAIL"
    elif open_assumption_count:
        status = "READY_WITH_ASSUMPTIONS"
    else:
        status = "READY"
    return {
        "contract_name": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "scene_count": scene_count,
            "shot_count": shot_count,
            "total_duration_seconds": round(total_duration, 3),
            "open_assumption_count": open_assumption_count,
        },
        "boundary": "后端只判断来源、引用、结构和确定性执行矛盾；镜头是否有导演价值仍由人工审片清单判断。",
    }


def _combined_report(
    formal_report: dict[str, Any],
    workspace_report: dict[str, Any] | None,
    materialization_warnings: list[dict[str, str]],
    *,
    workspace_missing: bool = False,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    dimensions = {
        "source_integrity": "FAIL" if workspace_missing else "PASS",
        "source_authority": "FAIL" if workspace_missing else "PASS",
        "source_coverage": "FAIL" if workspace_missing else "PASS",
        "source_alignment": "FAIL" if workspace_missing else "PASS",
        "dialogue_playback": "PASS",
        "gate_review": "FAIL" if workspace_missing else "PASS",
        "formal_structure": "PASS" if not formal_report.get("errors") else "FAIL",
        "export_parity": "NOT_RUN",
    }
    if workspace_missing:
        errors.append(issue("WORKSPACE_REQUIRED", "workspace", "3.1.3 正式 validate/build/export 必须提供 director-workspace/3.1.3。"))
    elif isinstance(workspace_report, dict):
        errors.extend(workspace_report.get("errors", []))
        warnings.extend(workspace_report.get("warnings", []))
        dimensions.update(workspace_report.get("dimensions", {}))
        if workspace_report.get("status") != "PASS":
            dimensions["gate_review"] = workspace_report.get("dimensions", {}).get("gate_review", "FAIL")
    errors.extend(formal_report.get("errors", []))
    warnings.extend(formal_report.get("warnings", []))
    warnings.extend(materialization_warnings)

    dialogue_error_codes = {
        "DIALOGUE_COVERAGE_MISMATCH",
        "DIALOGUE_NOT_IN_EXECUTION_TEXT",
        "DIALOGUE_REFERENCE_UNKNOWN",
        "SOURCE_DIALOGUE_NOT_REGISTERED",
        "SOURCE_DIALOGUE_TEXT_MISMATCH",
        "SOURCE_DIALOGUE_SPEAKER_MISMATCH",
    }
    if any(item.get("code") in dialogue_error_codes or str(item.get("code", "")).startswith("CHINESE_DIALOGUE") for item in errors):
        dimensions["dialogue_playback"] = "FAIL"

    if errors:
        status = "FAIL"
    elif formal_report.get("summary", {}).get("open_assumption_count", 0):
        status = "READY_WITH_ASSUMPTIONS"
    else:
        status = "READY"
    summary = dict(formal_report.get("summary", {}))
    if isinstance(workspace_report, dict):
        summary.update(workspace_report.get("metrics", {}))
    return {
        "contract_name": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "source_skill": SOURCE_SKILL,
        "source_skill_version": SOURCE_SKILL_VERSION,
        "status": status,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "dimensions": dimensions,
        "summary": summary,
        "boundary": "READY 只表示来源、权威、覆盖、语义对齐、对白、Gate 和正式结构均无确定性阻断；不替代导演审美判断。",
    }


def validate_delivery(
    data: Any,
    workspace: Any,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Run the only formal readiness path and return its canonical materialized copy."""
    if not isinstance(data, dict):
        formal_report = validate_structure(data)
        return _combined_report(formal_report, None, [], workspace_missing=workspace is None), None
    if workspace is None:
        formal_report = validate_structure(data)
        return _combined_report(formal_report, None, [], workspace_missing=True), None

    # Validate the caller-provided formal object before any deterministic
    # materialization. Required fields cannot be silently recreated and thereby
    # bypass the published Schema contract.
    raw_schema_issues = validate_formal_schema(data)
    if raw_schema_issues:
        formal_report = validate_structure(data)
        return _combined_report(formal_report, None, []), None

    try:
        materialized, materialization_warnings = materialize_source_excerpts(workspace, data)
    except Exception as exc:
        formal_report = validate_structure(data)
        formal_report["errors"].append(issue("SOURCE_MATERIALIZATION_FAILED", "workspace", str(exc)))
        formal_report["error_count"] = len(formal_report["errors"])
        formal_report["status"] = "FAIL"
        return _combined_report(formal_report, None, []), None
    # Review locks are calculated against the canonical, passage-derived excerpts,
    # never against user-editable copies of the third column.
    workspace_report = validate_workspace(workspace, materialized)
    formal_report = validate_structure(materialized)
    return _combined_report(formal_report, workspace_report, materialization_warnings), materialized


def validate_data(data: Any, workspace: Any = None) -> dict[str, Any]:
    """Compatibility API: formal readiness now requires workspace evidence."""
    report, _ = validate_delivery(data, workspace)
    return report


def safe_slug(data: dict[str, Any]) -> str:
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    slug = source.get("delivery_slug")
    if isinstance(slug, str) and SLUG_RE.fullmatch(slug):
        return slug
    return "untitled-scene-001"


def markdown_cell(value: Any) -> str:
    text = normalize_text(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def format_duration(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value).is_integer():
            return f"{int(value)}秒"
        return f"{float(value):g}秒"
    return ""


def render_markdown(data: dict[str, Any], report: dict[str, Any]) -> str:
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    title = source.get("title") or "未命名场景"
    design = data.get("director_design") if isinstance(data.get("director_design"), dict) else {}
    scenes = data.get("scenes") if isinstance(data.get("scenes"), list) else []
    scene_names = {
        scene.get("scene_id"): scene.get("scene", "")
        for scene in scenes
        if isinstance(scene, dict)
    }

    design_labels = (
        ("场景任务", "scene_purpose"),
        ("戏剧问题", "dramatic_question"),
        ("转折点", "turning_point"),
        ("观众位置", "audience_position"),
        ("视点策略", "pov_strategy"),
        ("情绪弧线", "emotional_arc"),
        ("人物调度", "blocking_strategy"),
        ("摄影策略", "visual_strategy"),
        ("声音策略", "sound_strategy"),
        ("节奏策略", "rhythm_strategy"),
    )

    lines = [
        f"# {title}｜导演分镜",
        "",
        f"- 合同：`{CONTRACT_NAME}/{CONTRACT_VERSION}`",
        f"- 状态：`{report['status']}`",
        f"- 总时长：`{report['summary']['total_duration_seconds']:g} 秒`",
        "",
        "## 导演设计摘要",
        "",
        "| 维度 | 设计 |",
        "| --- | --- |",
    ]
    for label, key in design_labels:
        lines.append(f"| {label} | {markdown_cell(design.get(key, ''))} |")

    assumptions = data.get("assumptions") if isinstance(data.get("assumptions"), list) else []
    if assumptions:
        lines.extend(["", "## 假设与待确认项", ""])
        for item in assumptions:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- **{item.get('assumption_id', 'A???')} · {item.get('status', 'open')}**："
                f"{item.get('statement', '')}（影响：{item.get('impact', '')}）"
            )

    lines.extend(
        [
            "",
            "## 六列导演分镜",
            "",
            "| 镜号 | 场景 | 原剧本段落 | 镜头时长 | 运镜＋主画面描述 | 备注 |",
            "| --- | --- | --- | ---: | --- | --- |",
        ]
    )
    shots = data.get("shots") if isinstance(data.get("shots"), list) else []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        row = (
            shot.get("shot_id", ""),
            scene_names.get(shot.get("scene_id"), shot.get("scene_id", "")),
            shot.get("source_excerpt", ""),
            format_duration(shot.get("duration_seconds")),
            shot.get("execution_text", ""),
            shot.get("notes", ""),
        )
        lines.append("| " + " | ".join(markdown_cell(value) for value in row) + " |")


    if report["warnings"] or report["errors"]:
        lines.extend(["", "## 后端复核", ""])
        for item in report["errors"]:
            lines.append(f"- **FAIL · {item['code']}** `{item['path']}`：{item['message']}")
        for item in report["warnings"]:
            lines.append(f"- **WARN · {item['code']}** `{item['path']}`：{item['message']}")

    lines.extend(
        [
            "",
            "---",
            "本表由同一 director-shot-data 数据生成。后端校验不替代导演对镜头动机、调度、观看与节奏的判断。",
            "",
        ]
    )
    return "\n".join(lines)


def write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def prepare_built_data(data: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    built = copy.deepcopy(data)
    if not isinstance(built.get("source"), dict):
        built["source"] = {}
    built["source"]["delivery_slug"] = safe_slug(built)
    if not isinstance(built.get("project_id"), str) or not PROJECT_ID_RE.fullmatch(built.get("project_id", "")):
        built["project_id"] = f"{built['source']['delivery_slug']}-project"
    status_map = {
        "READY": "ready",
        "READY_WITH_ASSUMPTIONS": "ready_with_assumptions",
        "FAIL": "fail",
    }
    built["validation"] = {
        "status": status_map[report["status"]],
        "warnings": [f"{item['code']}: {item['message']}" for item in report["warnings"]],
    }
    return built


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_json(data: dict[str, Any], path: Path) -> dict[str, Any]:
    reloaded = load_json(path)
    if reloaded != data:
        raise ValueError("JSON round-trip 与 canonical shot data 不一致。")
    return {"status": "PASS", "shot_row_count": len(data.get("shots", []))}


def verify_markdown(data: dict[str, Any], path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if "## 六列导演分镜" not in text:
        raise ValueError("Markdown 缺少六列导演分镜章节。")
    scenes = data.get("scenes") if isinstance(data.get("scenes"), list) else []
    scene_names = {
        scene.get("scene_id"): scene.get("scene", "")
        for scene in scenes
        if isinstance(scene, dict)
    }
    for shot in data.get("shots", []) if isinstance(data.get("shots"), list) else []:
        if not isinstance(shot, dict):
            continue
        values = (
            shot.get("shot_id", ""),
            scene_names.get(shot.get("scene_id"), shot.get("scene_id", "")),
            shot.get("source_excerpt", ""),
            format_duration(shot.get("duration_seconds")),
            shot.get("execution_text", ""),
            shot.get("notes", ""),
        )
        for value_raw in values:
            value = normalize_text(value_raw)
            rendered = value.replace("|", "\\|").replace("\n", "<br>")
            if value and rendered not in text:
                raise ValueError(f"Markdown 未完整承载 {shot.get('shot_id', 'SH???')} 的核心分镜事实。")
    design = data.get("director_design") if isinstance(data.get("director_design"), dict) else {}
    design_keys = (
        "scene_purpose", "dramatic_question", "turning_point", "audience_position",
        "pov_strategy", "emotional_arc", "blocking_strategy", "visual_strategy",
        "sound_strategy", "rhythm_strategy",
    )
    for key in design_keys:
        value = markdown_cell(design.get(key, ""))
        if value and value not in text:
            raise ValueError(f"Markdown 未完整承载 director_design.{key}。")
    assumptions = data.get("assumptions") if isinstance(data.get("assumptions"), list) else []
    for item in assumptions:
        if not isinstance(item, dict):
            continue
        for key in ("statement", "impact"):
            value = normalize_text(item.get(key))
            if value and value not in text:
                raise ValueError(f"Markdown 未完整承载 assumption.{key}。")
    return {
        "status": "PASS",
        "shot_row_count": len(data.get("shots", [])),
        "design_field_count": len(design_keys),
    }


def _write_xlsx(data: dict[str, Any], path: Path) -> None:
    """Late import avoids a module cycle while keeping one canonical XLSX writer."""
    try:
        from .export_xlsx import export_xlsx
    except ImportError:  # pragma: no cover - script-path execution
        from export_xlsx import export_xlsx
    export_xlsx(data, path)


def _verify_xlsx(data: dict[str, Any], path: Path) -> dict[str, Any]:
    try:
        from .export_xlsx import verify_xlsx
    except ImportError:  # pragma: no cover - script-path execution
        from export_xlsx import verify_xlsx
    return verify_xlsx(data, path)


def _atomic_failure_report(report: dict[str, Any], exc: Exception) -> dict[str, Any]:
    failed = copy.deepcopy(report)
    failed.setdefault("errors", []).append(
        issue("BUILD_TRANSACTION_ABORTED", "output_dir", f"四文件原子构建失败：{exc}")
    )
    failed["error_count"] = len(failed["errors"])
    failed["status"] = "FAIL"
    failed.setdefault("dimensions", {})["export_parity"] = "FAIL"
    failed["build_transaction"] = "ROLLED_BACK"
    failed.pop("artifacts", None)
    return failed


def build_outputs(
    data: dict[str, Any],
    workspace: dict[str, Any] | None,
    output_dir: Path,
    *,
    strict: bool = True,
) -> tuple[dict[str, Any], dict[str, Path]]:
    """Atomically build the fixed four-file formal delivery.

    All artifacts are first generated and verified in a sibling staging directory.
    The validation report is written last. Any exception removes the staging tree
    and leaves the requested formal output directory absent or empty.

    ``strict`` is retained for call-site compatibility; 3.1.3 is always fail-closed.
    """
    del strict
    report, materialized = validate_delivery(data, workspace)
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        blocking = issue(
            "OUTPUT_DIR_NOT_EMPTY",
            "output_dir",
            "3.1.3 正式 build-all 只允许不存在或为空的输出目录；拒绝覆盖任何已有文件。",
        )
        failed = copy.deepcopy(report)
        failed.setdefault("errors", []).append(blocking)
        failed["error_count"] = len(failed["errors"])
        failed["status"] = "FAIL"
        failed.setdefault("dimensions", {})["export_parity"] = "FAIL"
        return failed, {}
    if report["status"] == "FAIL" or materialized is None:
        report = copy.deepcopy(report)
        report.setdefault("dimensions", {})["export_parity"] = "NOT_RUN"
        return report, {}

    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-stage-", dir=str(parent)))
    slug = safe_slug(materialized)
    stage_paths = {
        "json": stage / f"{slug}-shot-data.json",
        "markdown": stage / f"{slug}-storyboard.md",
        "xlsx": stage / f"{slug}-storyboard.xlsx",
        "validation": stage / f"{slug}-storyboard-validation.json",
    }
    try:
        built = prepare_built_data(materialized, report)
        schema_issues = validate_formal_schema(built)
        if schema_issues:
            raise ValueError(
                "built shot-data 不满足正式 Schema："
                + ", ".join(sorted({item["path"] for item in schema_issues}))
            )
        write_json(stage_paths["json"], built)
        json_verification = verify_json(built, stage_paths["json"])
        markdown = render_markdown(built, report)
        with stage_paths["markdown"].open("x", encoding="utf-8") as handle:
            handle.write(markdown)
        if stage_paths["markdown"].read_text(encoding="utf-8") != markdown:
            raise ValueError("Markdown 写入后内容与 canonical renderer 不一致")
        markdown_verification = verify_markdown(built, stage_paths["markdown"])

        _write_xlsx(built, stage_paths["xlsx"])
        xlsx_verification = _verify_xlsx(built, stage_paths["xlsx"])

        final_report = copy.deepcopy(report)
        final_report.setdefault("dimensions", {})["export_parity"] = "PASS"
        final_report["build_transaction"] = "COMMITTED"
        final_report["export_checks"] = {
            "json": json_verification,
            "markdown": markdown_verification,
            "xlsx": xlsx_verification,
        }
        json_sha256 = sha256_file(stage_paths["json"])
        markdown_sha256 = sha256_file(stage_paths["markdown"])
        xlsx_sha256 = sha256_file(stage_paths["xlsx"])
        final_report["artifact_sha256"] = {
            "json": json_sha256,
            "markdown": markdown_sha256,
            "xlsx": xlsx_sha256,
        }
        final_report["artifacts"] = {
            "shot_data_json": {
                "filename": stage_paths["json"].name,
                "sha256": json_sha256,
            },
            "storyboard_markdown": {
                "filename": stage_paths["markdown"].name,
                "sha256": markdown_sha256,
            },
            "storyboard_xlsx": {
                "filename": stage_paths["xlsx"].name,
                "sha256": xlsx_sha256,
                "verification": xlsx_verification,
            },
        }
        write_json(stage_paths["validation"], final_report)

        expected_names = {path.name for path in stage_paths.values()}
        actual_names = {path.name for path in stage.iterdir() if path.is_file()}
        if actual_names != expected_names:
            raise ValueError(
                f"正式 staging 文件集合漂移：expected={sorted(expected_names)}, actual={sorted(actual_names)}"
            )

        output_preexisted = output_dir.exists()
        if output_preexisted:
            output_dir.rmdir()
        try:
            os.replace(stage, output_dir)
        except Exception:
            if output_preexisted and not output_dir.exists():
                output_dir.mkdir(parents=False, exist_ok=False)
            raise
        final_paths = {label: output_dir / path.name for label, path in stage_paths.items()}
        return final_report, final_paths
    except Exception as exc:
        shutil.rmtree(stage, ignore_errors=True)
        return _atomic_failure_report(report, exc), {}

def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("顶层 JSON 必须是对象。")
    return value


def exit_code(status: str, *, fail_on_warn: bool = False) -> int:
    if status == "FAIL":
        return 1
    if status == "READY_WITH_ASSUMPTIONS" and fail_on_warn:
        return 1
    return 0


def cmd_structure_validate(args: argparse.Namespace) -> int:
    try:
        data = load_json(args.input)
        report = validate_structure(data, allow_legacy=True)
    except ValueError as exc:
        report = _report([issue("JSON_READ_FAILED", "$", str(exc))], [], 0, 0, 0.0, 0)
    rendered = {
        "check_kind": "STRUCTURE_ONLY",
        "status": "PASS" if not report["errors"] else "FAIL",
        "errors": report["errors"],
        "warnings": report["warnings"],
        "summary": report["summary"],
        "boundary": "结构检查不包含 workspace、来源覆盖、语义对齐或 Gate，不得当作正式 READY。",
    }
    sys.stdout.write(json.dumps(rendered, ensure_ascii=False, indent=2) + "\n")
    return 0 if rendered["status"] == "PASS" else 1


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        data = load_json(args.input)
        workspace = load_json(args.workspace) if args.workspace else None
        report = validate_data(data, workspace)
    except ValueError as exc:
        report = _report([issue("JSON_READ_FAILED", "$", str(exc))], [], 0, 0, 0.0, 0)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        if args.report.exists():
            sys.stderr.write(f"FAIL: 拒绝覆盖已有 validation report：{args.report}\n")
            return 1
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
    sys.stdout.write(rendered)
    return exit_code(report["status"], fail_on_warn=args.fail_on_warn)


def cmd_build(args: argparse.Namespace) -> int:
    if args.output_dir.exists() and (not args.output_dir.is_dir() or any(args.output_dir.iterdir())):
        sys.stderr.write("FAIL: 3.1.3 正式 build-all 输出目录必须不存在或为空；未修改任何已有文件。\n")
        return 1
    try:
        data = load_json(args.input)
        workspace = load_json(args.workspace) if args.workspace else None
    except ValueError as exc:
        report = _report(
            [issue("JSON_READ_FAILED", "$", str(exc))],
            [],
            0,
            0,
            0.0,
            0,
        )
        report["dimensions"] = {"export_parity": "NOT_RUN"}
        sys.stderr.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return 2

    report, paths = build_outputs(data, workspace, args.output_dir)
    stream = sys.stderr if report["status"] == "FAIL" else sys.stdout
    stream.write(f"status: {report['status']}\n")
    for label, path in paths.items():
        stream.write(f"{label}: {path}\n")
    if report["status"] == "FAIL":
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return exit_code(report["status"], fail_on_warn=args.fail_on_warn)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="su-fenjingskill 3.1.3 后端：来源保护、Gate、镜内 flow、XLSX 前端投影与原子四文件交付。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    structure_parser = subparsers.add_parser("structure-validate", help="仅检查 shot-data 结构；不产生正式 readiness。")
    structure_parser.add_argument("--input", type=Path, required=True, help="输入 JSON 文件。")
    structure_parser.set_defaults(func=cmd_structure_validate)

    validate_parser = subparsers.add_parser("validate", help="组合校验 3.1.3 workspace 与正式 shot data。")
    validate_parser.add_argument("--input", type=Path, required=True, help="输入 JSON 文件。")
    validate_parser.add_argument("--workspace", type=Path, help="director-workspace/3.1.3；正式 readiness 必需。")
    validate_parser.add_argument("--report", type=Path, help="可选 validation report 输出路径。")
    validate_parser.add_argument("--fail-on-warn", action="store_true", help="将 READY_WITH_ASSUMPTIONS 视为失败。")
    validate_parser.set_defaults(func=cmd_validate)

    for command in ("build-all", "build"):
        build_parser_ = subparsers.add_parser(command, help="通过 combined gate 后原子生成固定四文件。")
        build_parser_.add_argument("--input", type=Path, required=True, help="输入 JSON 文件。")
        build_parser_.add_argument("--workspace", type=Path, required=True, help="director-workspace/3.1.3。")
        build_parser_.add_argument("--output-dir", type=Path, required=True, help="输出目录。")
        build_parser_.add_argument("--fail-on-warn", action="store_true", help="将 READY_WITH_ASSUMPTIONS 视为失败。")
        build_parser_.set_defaults(func=cmd_build)
    return parser

def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
