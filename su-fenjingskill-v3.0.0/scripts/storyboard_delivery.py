#!/usr/bin/env python3
"""Lean backend for su-fenjingskill v3.0.0.

This module protects source text, checks deterministic contradictions, and renders
files. It intentionally does not decide shot count, camera style, or artistic
quality; those remain director decisions defined by SKILL.md and references/.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

CONTRACT_NAME = "director-shot-data"
CONTRACT_VERSION = "3.0.0"
SOURCE_SKILL = "su-fenjingskill"
SOURCE_SKILL_VERSION = "3.0.0"

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


def is_source_excerpt(excerpt: Any, locked_text: str) -> bool:
    excerpt_norm = normalize_text(excerpt)
    source_norm = normalize_text(locked_text)
    return bool(excerpt_norm) and excerpt_norm in source_norm


def expected_shot_id(index: int) -> str:
    return f"SH{index:03d}"


def ratio_warning(
    values: list[str],
    dimension: str,
    warnings: list[dict[str, str]],
) -> None:
    """Flag possible visual collapse for human review; never fail automatically."""
    if len(values) < 8:
        return
    nonempty = [value for value in values if value]
    if not nonempty:
        return
    dominant, count = Counter(nonempty).most_common(1)[0]
    ratio = count / len(nonempty)
    if ratio >= 0.8:
        warnings.append(
            issue(
                "DIRECTOR_UNIFORMITY_REVIEW",
                f"shots[].camera.{dimension}",
                f"{dimension} 中“{dominant}”占 {count}/{len(nonempty)}（{ratio:.0%}）。这不是艺术错误，但应确认其确有场景级导演理由。",
            )
        )


def validate_data(data: Any) -> dict[str, Any]:
    """Validate deterministic contract and source-integrity rules.

    Artistic repetition, style, pacing, or coverage choices are warnings at most.
    """
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not isinstance(data, dict):
        errors.append(issue("DATA_NOT_OBJECT", "$", "顶层数据必须是 JSON 对象。"))
        return _report(errors, warnings, 0, 0, 0.0, 0)

    expected_constants = {
        "contract_name": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "source_skill": SOURCE_SKILL,
        "source_skill_version": SOURCE_SKILL_VERSION,
    }
    for key, expected in expected_constants.items():
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
        if locked_text and not is_source_excerpt(scene.get("source_excerpt"), locked_text):
            errors.append(issue("SCENE_EXCERPT_NOT_IN_SOURCE", f"{path}.source_excerpt", "场景原文片段未逐字出现在 locked_text 中。"))
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

        if locked_text and not is_source_excerpt(shot.get("source_excerpt"), locked_text):
            errors.append(issue("SHOT_EXCERPT_NOT_IN_SOURCE", f"{path}.source_excerpt", "镜头原剧本段落未逐字出现在 locked_text 中。"))

        duration = shot.get("duration_seconds")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
            errors.append(issue("DURATION_INVALID", f"{path}.duration_seconds", "镜头时长必须大于 0。"))
        else:
            total_duration += float(duration)
            if duration <= 1.0:
                warnings.append(issue("VERY_SHORT_SHOT_REVIEW", f"{path}.duration_seconds", f"{shot_id} 为 {duration:g} 秒；确认它由真实节奏或信息落点驱动。"))
            if duration >= 20.0:
                warnings.append(issue("LONG_SHOT_REVIEW", f"{path}.duration_seconds", f"{shot_id} 为 {duration:g} 秒；确认调度、焦点与声音变化足以支撑完整时间。"))
        if not get_nonempty_string(shot, "duration_basis"):
            warnings.append(issue("DURATION_BASIS_EMPTY", f"{path}.duration_basis", "缺少时长依据；不阻断，但会降低生产可执行性。"))

        motivation = shot.get("motivation")
        if not isinstance(motivation, dict):
            errors.append(issue("MOTIVATION_MISSING", f"{path}.motivation", "每个镜头都必须说明存在理由。"))
        else:
            if motivation.get("primary") not in {"information", "emotion", "relationship", "space", "subjective", "rhythm", "transition"}:
                errors.append(issue("MOTIVATION_PRIMARY_INVALID", f"{path}.motivation.primary", "镜头动机类别无效。"))
            for key in ("reason", "cut_or_hold_reason"):
                if not get_nonempty_string(motivation, key):
                    errors.append(issue("MOTIVATION_EMPTY", f"{path}.motivation.{key}", f"镜头动机字段 {key} 为空。"))
            motivation_text = " ".join(str(motivation.get(key, "")) for key in ("reason", "cut_or_hold_reason"))
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

        execution_text = shot.get("execution_text")
        if not isinstance(execution_text, str) or not execution_text.strip():
            errors.append(issue("EXECUTION_TEXT_EMPTY", f"{path}.execution_text", "第五列画面内容为空。"))
        else:
            for term in PLACEHOLDER_TERMS:
                if term in execution_text:
                    warnings.append(issue("EXECUTION_PLACEHOLDER", f"{path}.execution_text", f"画面内容含模板词“{term}”；应改为可见、可拍的具体描述。"))
            if "【" not in execution_text or "画面内容" not in execution_text:
                warnings.append(issue("EXECUTION_FORMAT_REVIEW", f"{path}.execution_text", "第五列未采用建议的镜头头＋【画面内容】结构。"))

        sound = shot.get("sound")
        if sound is not None and not isinstance(sound, dict):
            errors.append(issue("SOUND_INVALID", f"{path}.sound", "sound 必须是对象。"))
            sound = None
        if isinstance(sound, dict):
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
                    warnings.append(issue("INTENTIONAL_CONTINUITY_BREAK", break_path, "存在有意连续性破坏；请按导演意图人工复核。"))

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

    ratio_warning(shot_sizes, "shot_size", warnings)
    ratio_warning(angles, "angle", warnings)
    ratio_warning(movements, "movement.type", warnings)

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
    elif warnings or open_assumption_count:
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
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def build_outputs(
    data: dict[str, Any],
    output_dir: Path,
    *,
    strict: bool = False,
) -> tuple[dict[str, Any], dict[str, Path]]:
    """Build JSON, Markdown, and validation report.

    Default behavior preserves director work even when validation fails. With
    ``strict=True``, a failing input emits only the validation report.
    """
    report = validate_data(data)
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = safe_slug(data)
    paths = {
        "json": output_dir / f"{slug}-shot-data.json",
        "markdown": output_dir / f"{slug}-storyboard.md",
        "validation": output_dir / f"{slug}-storyboard-validation.json",
    }
    write_json(paths["validation"], report)
    if strict and report["status"] == "FAIL":
        return report, {"validation": paths["validation"]}

    built = prepare_built_data(data, report)
    write_json(paths["json"], built)
    paths["markdown"].write_text(render_markdown(built, report), encoding="utf-8")
    return report, paths


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("顶层 JSON 必须是对象。")
    return value


def exit_code(status: str) -> int:
    if status == "FAIL":
        return 1
    if status == "READY_WITH_ASSUMPTIONS":
        return 2
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        data = load_json(args.input)
        report = validate_data(data)
    except ValueError as exc:
        report = _report(
            [issue("JSON_READ_FAILED", "$", str(exc))],
            [],
            0,
            0,
            0.0,
            0,
        )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return exit_code(report["status"])


def cmd_build(args: argparse.Namespace) -> int:
    try:
        data = load_json(args.input)
    except ValueError as exc:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        report = _report(
            [issue("JSON_READ_FAILED", "$", str(exc))],
            [],
            0,
            0,
            0.0,
            0,
        )
        report_path = args.output_dir / "untitled-scene-001-storyboard-validation.json"
        write_json(report_path, report)
        sys.stderr.write(f"FAIL: {exc}\nvalidation: {report_path}\n")
        return 1

    report, paths = build_outputs(data, args.output_dir, strict=args.strict)
    sys.stdout.write(f"status: {report['status']}\n")
    for label, path in paths.items():
        sys.stdout.write(f"{label}: {path}\n")
    return exit_code(report["status"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="su-fenjingskill v3 后端：来源保护、确定性校验与文件渲染。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="校验 director-shot-data JSON。")
    validate_parser.add_argument("--input", type=Path, required=True, help="输入 JSON 文件。")
    validate_parser.add_argument("--report", type=Path, help="可选的 validation report 输出路径。")
    validate_parser.set_defaults(func=cmd_validate)

    build_parser_ = subparsers.add_parser("build", help="生成 JSON、Markdown 和 validation report。")
    build_parser_.add_argument("--input", type=Path, required=True, help="输入 JSON 文件。")
    build_parser_.add_argument("--output-dir", type=Path, required=True, help="输出目录。")
    build_parser_.add_argument(
        "--strict",
        action="store_true",
        help="FAIL 时只生成 validation report；默认仍保留可读导演成果。",
    )
    build_parser_.set_defaults(func=cmd_build)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
