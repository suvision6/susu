#!/usr/bin/env python3
"""Human-facing XLSX projection for director-shot-data/3.1.4.

The structured shot model remains the factual backend.  This module produces
the deliberately smaller spreadsheet frontend by following ``shot_flow`` in
time order.  Flow entries point back to canonical fields; they never carry a
second, freely-written execution description.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any, Mapping, Sequence


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Imported by export_xlsx.py to build the deterministic human-facing projection."


FLOW_OWNERS = frozenset(
    {
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
)
INDEX_OWNERS = frozenset({"dialogue_segment", "effect", "state_update"})
SPAN_OWNERS = frozenset({"blocking", "performance", "ambience", "focus", "edit_exit"})

MOVEMENT_LABELS = {
    "fixed": "固定",
    "push": "推进",
    "pull": "拉远",
    "pan": "横摇",
    "tilt": "俯仰摇摄",
    "track": "横移",
    "follow": "跟随",
    "orbit": "环绕",
    "crane": "升降",
    "handheld": "手持",
    "vehicle": "载具运动",
    "zoom": "变焦",
    "focus": "移焦",
    "compound": "复合运动",
    "other": "其他运动",
}

FRAMING_LABELS = {
    "single": "单人构图",
    "two_shot": "双人构图",
    "group": "群像构图",
    "over_shoulder": "过肩构图",
    "insert": "细节插入",
    "subjective": "主观视角",
    "space": "空间构图",
}

CANONICAL_SHOT_SIZE_TERMS = frozenset(
    {"大远景", "远景", "中远景", "全景", "中全景", "中景", "中近景", "近景", "特写", "大特写", "极特写"}
)

DESIGN_LABELS = (
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

RHYTHM_LABELS = {
    "short_drama_under_10m": "十分钟以内短剧",
    "platform_series_episode": "平台长剧集",
    "short_film_3_20m": "3–20分钟短片",
    "feature_film": "长片电影",
    "custom": "自定义节奏",
}

PACE_LABELS = {
    "fast": "快速",
    "natural": "自然",
    "deliberate": "从容",
    "variable": "可变",
    "custom": "自定义",
}

_BACKEND_LEAK_PATTERNS = (
    re.compile(r"【(?:摄影|调度与表演|声音|剪辑|连续性|时长|镜头动机)】"),
    re.compile(r"(?<![A-Za-z0-9])(?:D|F|P|A|G)[0-9]{3,}(?![A-Za-z0-9])"),
    re.compile(r"\b(?:Gate|Alignment)\b", re.IGNORECASE),
    re.compile(r"(?:音乐|状态变化|光线变化|对白|音效|环境)：无"),
    re.compile(r"未定义"),
    re.compile(r"来源动作按序"),
)

_TEMPLATE_PHRASES = (
    "以人物共享关系为主体",
    "自然透视，保留人物真实距离",
    "焦点优先保持人物关系可读",
    "保持当前场景客观声场",
    "关系轴同侧",
    "人物进入、退让与继续行进的方向",
    "保持到当前关系动作与迟到反应完整落地",
)


class XlsxProjectionError(ValueError):
    """Raised when the factual backend cannot produce a faithful frontend."""

    def __init__(self, message: str, *, code: str = "XLSX_PROJECTION_INVALID") -> None:
        super().__init__(message)
        self.code = code


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def is_canonical_shot_size(value: Any, *, allow_unresolved: bool = False) -> bool:
    text = normalize_text(value).replace(" ", "")
    if allow_unresolved and text == "unresolved":
        return True
    terms = text.split("→") if text else []
    return bool(terms) and all(term in CANONICAL_SHOT_SIZE_TERMS for term in terms)


def _semantic_text(value: Any) -> str:
    return re.sub(r"[^\w\u3400-\u9fff]+", "", normalize_text(value), flags=re.UNICODE).casefold()


def _substantially_contains(left: Any, right: Any, *, minimum: int = 10) -> bool:
    a = _semantic_text(left)
    b = _semantic_text(right)
    return min(len(a), len(b)) >= minimum and (a in b or b in a)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise XlsxProjectionError(f"{path} 必须是对象。")
    return value


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise XlsxProjectionError(f"{path} 必须是数组。")
    return value


def _required_text(value: Any, path: str) -> str:
    text = normalize_text(value)
    if not text:
        raise XlsxProjectionError(f"{path} 不能为空。")
    return text


def build_dialogue_index(data: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    source = _mapping(data.get("source"), "source")
    lines = _sequence(source.get("dialogue_lines", []), "source.dialogue_lines")
    result: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(lines):
        line = _mapping(raw, f"source.dialogue_lines[{index}]")
        dialogue_id = _required_text(line.get("dialogue_id"), f"source.dialogue_lines[{index}].dialogue_id")
        _required_text(line.get("speaker"), f"source.dialogue_lines[{index}].speaker")
        _required_text(line.get("text"), f"source.dialogue_lines[{index}].text")
        if dialogue_id in result:
            raise XlsxProjectionError(f"source.dialogue_lines 存在重复 ID：{dialogue_id}")
        result[dialogue_id] = line
    return result


def _owner_source(shot: Mapping[str, Any], owner: str) -> Any:
    camera = _mapping(shot.get("camera"), "shot.camera")
    staging = _mapping(shot.get("staging"), "shot.staging")
    sound = _mapping(shot.get("sound"), "shot.sound")
    edit = _mapping(shot.get("edit"), "shot.edit")
    continuity = _mapping(shot.get("continuity"), "shot.continuity")
    if owner == "camera_setup":
        return camera
    if owner == "blocking":
        return staging.get("blocking")
    if owner == "performance":
        return staging.get("performance")
    if owner == "dialogue_segment":
        return sound.get("dialogue_segments", [])
    if owner == "effect":
        return sound.get("effects", [])
    if owner == "ambience":
        return sound.get("ambience")
    if owner == "movement":
        return camera.get("movement")
    if owner == "focus":
        return camera.get("focus")
    if owner == "state_update":
        return continuity.get("state_updates", [])
    if owner == "edit_exit":
        return edit.get("exit")
    raise XlsxProjectionError(f"未知 shot_flow owner：{owner}")


def _validate_flow_item(shot: Mapping[str, Any], item: Any, item_index: int) -> tuple[str, Any]:
    shot_id = normalize_text(shot.get("shot_id")) or "<unknown-shot>"
    path = f"{shot_id}.shot_flow[{item_index}]"
    flow_item = _mapping(item, path)
    owner = _required_text(flow_item.get("owner"), f"{path}.owner")
    if owner not in FLOW_OWNERS:
        raise XlsxProjectionError(f"{path}.owner 无效：{owner}")
    allowed_keys = {"owner"}
    if owner in INDEX_OWNERS:
        allowed_keys.add("index")
    elif owner in SPAN_OWNERS:
        allowed_keys.add("span")
    if set(flow_item) - allowed_keys:
        raise XlsxProjectionError(f"{path} 含 owner 不允许的字段：{sorted(set(flow_item) - allowed_keys)}")

    source = _owner_source(shot, owner)
    if owner in INDEX_OWNERS:
        if set(flow_item) != {"owner", "index"}:
            raise XlsxProjectionError(f"{path} 必须且只能包含 owner 与 index。")
        source_items = _sequence(source, f"{shot_id}.{owner}")
        index = flow_item.get("index")
        if isinstance(index, bool) or not isinstance(index, int):
            raise XlsxProjectionError(f"{path}.index 必须是整数。")
        if index < 0 or index >= len(source_items):
            raise XlsxProjectionError(f"{path}.index 越界：{index}")
        return owner, source_items[index]

    if owner in SPAN_OWNERS:
        source_text = _required_text(source, f"{shot_id}.{owner}")
        if "span" not in flow_item:
            return owner, source_text
        span = _required_text(flow_item.get("span"), f"{path}.span")
        if span not in str(source):
            raise XlsxProjectionError(f"{path}.span 不是所属后端字符串的逐字片段。")
        return owner, span

    if set(flow_item) != {"owner"}:
        raise XlsxProjectionError(f"{path} 只能包含 owner。")
    return owner, source


def validate_shot_flow(shot: Mapping[str, Any]) -> list[tuple[str, Any]]:
    """Validate one formal flow and return its resolved backend references."""
    shot_id = normalize_text(shot.get("shot_id")) or "<unknown-shot>"
    flow = _sequence(shot.get("shot_flow"), f"{shot_id}.shot_flow")
    if not flow:
        raise XlsxProjectionError(f"{shot_id}.shot_flow 为空，迁移 draft 不能导出正式 XLSX。")
    resolved = [_validate_flow_item(shot, raw, index) for index, raw in enumerate(flow)]

    camera_setup_count = sum(owner == "camera_setup" for owner, _ in resolved)
    if camera_setup_count != 1:
        raise XlsxProjectionError(f"{shot_id}.shot_flow 必须恰好引用一次 camera_setup。")

    dialogue_indices = [
        int(_mapping(flow[index], f"{shot_id}.shot_flow[{index}]").get("index"))
        for index, (owner, _) in enumerate(resolved)
        if owner == "dialogue_segment"
    ]
    dialogue_segments = _sequence(
        _mapping(shot.get("sound"), f"{shot_id}.sound").get("dialogue_segments", []),
        f"{shot_id}.sound.dialogue_segments",
    )
    expected_dialogue_indices = list(range(len(dialogue_segments)))
    if dialogue_indices != expected_dialogue_indices:
        raise XlsxProjectionError(
            f"{shot_id}.shot_flow 对白引用必须不重不漏并保持顺序："
            f"expected={expected_dialogue_indices}, actual={dialogue_indices}"
        )

    movement = _mapping(_mapping(shot.get("camera"), f"{shot_id}.camera").get("movement"), f"{shot_id}.camera.movement")
    movement_type = _required_text(movement.get("type"), f"{shot_id}.camera.movement.type")
    movement_count = sum(owner == "movement" for owner, _ in resolved)
    if movement_type != "fixed" and movement_count != 1:
        raise XlsxProjectionError(f"{shot_id} 的非固定运镜必须在 shot_flow 中恰好引用一次 movement。")
    if movement_type == "fixed" and movement_count != 0:
        raise XlsxProjectionError(f"{shot_id} 的固定镜头不得在 shot_flow 中引用 movement。")

    for owner in ("effect", "state_update"):
        indices = [
            int(_mapping(flow[index], f"{shot_id}.shot_flow[{index}]").get("index"))
            for index, (resolved_owner, _) in enumerate(resolved)
            if resolved_owner == owner
        ]
        if len(indices) != len(set(indices)):
            raise XlsxProjectionError(f"{shot_id}.shot_flow 重复引用 {owner}。")
    return resolved


def projection_optional_items(shot: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Return optional human-front-end clauses that must not repeat across a scene."""
    result: list[tuple[str, str]] = []
    for owner, value in validate_shot_flow(shot):
        if owner not in {"ambience", "focus", "edit_exit"}:
            continue
        text = normalize_text(value)
        if len(_semantic_text(text)) >= 8:
            result.append((owner, text))
    return result


def _validate_frontend_projection_sources(
    shot: Mapping[str, Any], resolved: Sequence[tuple[str, Any]], shot_id: str
) -> None:
    camera = _mapping(shot.get("camera"), f"{shot_id}.camera")
    shot_size = _required_text(camera.get("shot_size"), f"{shot_id}.camera.shot_size")
    if not is_canonical_shot_size(shot_size):
        raise XlsxProjectionError(
            f"{shot_id}.camera.shot_size 使用非标准景别“{shot_size}”；只能使用规范景别及其箭头转写。",
            code="SHOT_SIZE_TERM_NONSTANDARD",
        )

    position = _required_text(camera.get("position"), f"{shot_id}.camera.position")
    angle = _required_text(camera.get("angle"), f"{shot_id}.camera.angle")
    redundant_terms = [term for term in (angle, shot_size) if term and term in position]
    if redundant_terms:
        raise XlsxProjectionError(
            f"{shot_id}.camera.position 重复摄影头已经表达的术语：{'、'.join(redundant_terms)}。机位只写可架设位置与朝向。",
            code="XLSX_CAMERA_SETUP_REDUNDANT",
        )

    composition = _required_text(camera.get("composition"), f"{shot_id}.camera.composition")
    comparable = [
        (owner, normalize_text(value))
        for owner, value in resolved
        if owner in {"blocking", "performance", "effect", "ambience", "focus", "edit_exit"}
    ]
    for owner, value in comparable:
        if _substantially_contains(composition, value):
            raise XlsxProjectionError(
                f"{shot_id}.camera.composition 与 shot_flow 的 {owner} 重复同一画面内容；构图只写空间排列，事件只保留一次。",
                code="XLSX_PROJECTION_REDUNDANT_CONTENT",
            )

    for left_index, (left_owner, left_text) in enumerate(comparable):
        for right_owner, right_text in comparable[left_index + 1 :]:
            if left_owner == right_owner:
                continue
            if _substantially_contains(left_text, right_text):
                raise XlsxProjectionError(
                    f"{shot_id}.shot_flow 的 {left_owner} 与 {right_owner} 重复同一内容；前端事件不得换字段复述。",
                    code="XLSX_PROJECTION_REDUNDANT_CONTENT",
                )

    for owner, value in comparable:
        if owner == "focus" and any(
            phrase in value
            for phrase in ("当前动作结束前不抢先泄露下一镜信息", "到当前反应落定", "焦点优先保持人物关系可读")
        ):
            raise XlsxProjectionError(
                f"{shot_id}.shot_flow 引用了没有实际焦点转移的模板说明；普通对焦保留在后台即可。",
                code="XLSX_PROJECTION_NONESSENTIAL_FOCUS",
            )


def _movement_label(movement: Mapping[str, Any], path: str) -> str:
    movement_type = _required_text(movement.get("type"), f"{path}.type")
    label = MOVEMENT_LABELS.get(movement_type)
    if label is None:
        raise XlsxProjectionError(f"{path}.type 无法投影：{movement_type}")
    return label


def _single_line(value: Any) -> str:
    return " ".join(part.strip() for part in normalize_text(value).split("\n") if part.strip())


def _camera_position_for_frontend(value: Any, path: str) -> str:
    """Keep the physical setup while omitting routine backend axis proof."""
    position = _required_text(value, path)
    position = re.sub(
        r"[，,]?\s*(?:摄影机)?保持(?:在)?(?:既定|当前)?关系轴同侧",
        "",
        position,
    ).strip("，,；; ")
    if not position:
        raise XlsxProjectionError(f"{path} 只有普通轴线声明，缺少可展示的实际机位。")
    return position


def _camera_setup_for_frontend(camera: Mapping[str, Any], staging: Mapping[str, Any], shot_id: str) -> str:
    framing_mode = _required_text(camera.get("framing_mode"), f"{shot_id}.camera.framing_mode")
    framing_label = FRAMING_LABELS.get(framing_mode)
    if framing_label is None:
        raise XlsxProjectionError(f"{shot_id}.camera.framing_mode 无法投影：{framing_mode}")
    primary = [normalize_text(item) for item in _sequence(camera.get("primary_subjects"), f"{shot_id}.camera.primary_subjects") if normalize_text(item)]
    foreground = [normalize_text(item) for item in _sequence(camera.get("foreground_subjects"), f"{shot_id}.camera.foreground_subjects") if normalize_text(item)]
    offscreen = [normalize_text(item) for item in _sequence(staging.get("offscreen_subjects"), f"{shot_id}.staging.offscreen_subjects") if normalize_text(item)]
    if framing_mode in {"single", "two_shot", "group", "over_shoulder", "insert"} and not primary:
        raise XlsxProjectionError(f"{shot_id}.camera.primary_subjects 不能为空。")
    if framing_mode == "over_shoulder" and not foreground:
        raise XlsxProjectionError(f"{shot_id}.camera.foreground_subjects 不能为空。")

    if framing_mode == "over_shoulder":
        framing = f"以前景{'、'.join(foreground)}越肩看向{'、'.join(primary)}"
    elif framing_mode == "single":
        framing = f"以{'、'.join(primary)}为单人画面主体"
    elif framing_mode == "two_shot":
        framing = f"以{'、'.join(primary)}构成双人关系画面"
    elif framing_mode == "group":
        framing = f"以{'、'.join(primary)}构成群像画面"
    elif framing_mode == "insert":
        framing = f"以{'、'.join(primary)}为细节主体"
    elif framing_mode == "subjective":
        framing = "采用主观视角"
    else:
        framing = "先建立空间关系"
    if offscreen:
        framing += f"，{'、'.join(offscreen)}留在画外"
    position = _camera_position_for_frontend(camera.get("position"), f"{shot_id}.camera.position")
    composition = _required_text(camera.get("composition"), f"{shot_id}.camera.composition")
    return f"{framing}；摄影机位于{position}，{composition}"


def _sentence(value: Any) -> str:
    text = _single_line(value)
    if not text:
        return ""
    if text[-1] in "。！？!?；;…":
        return text
    if text.endswith("”") and len(text) > 1 and text[-2] in "。！？!?…":
        return text
    return text.rstrip("，,：:") + "。"


def _render_dialogue(segment: Any, dialogue_index: Mapping[str, Mapping[str, Any]], path: str) -> str:
    item = _mapping(segment, path)
    dialogue_id = _required_text(item.get("dialogue_id"), f"{path}.dialogue_id")
    source = dialogue_index.get(dialogue_id)
    if source is None:
        raise XlsxProjectionError(f"{path}.dialogue_id 未登记于 source.dialogue_lines：{dialogue_id}")
    speaker = _required_text(source.get("speaker"), f"source.dialogue_lines[{dialogue_id}].speaker")
    text = _required_text(item.get("text"), f"{path}.text")
    source_text = _required_text(source.get("text"), f"source.dialogue_lines[{dialogue_id}].text")
    if text not in source_text:
        raise XlsxProjectionError(f"{path}.text 不是来源对白的逐字片段。")
    delivery = _required_text(item.get("delivery"), f"{path}.delivery")
    if delivery == "onscreen":
        return f"{speaker}说：“{text}”"
    if delivery == "os":
        return f"{speaker}在画外说：“{text}”"
    if delivery == "vo":
        return f"{speaker}的旁白：“{text}”"
    if delivery == "mediated":
        return f"介质中传来{speaker}的声音：“{text}”"
    if delivery == "unresolved":
        return f"{speaker}的声音：“{text}”"
    raise XlsxProjectionError(f"{path}.delivery 无法投影：{delivery}")


def _render_movement(movement: Any, path: str) -> str:
    item = _mapping(movement, path)
    movement_type = _required_text(item.get("type"), f"{path}.type")
    if movement_type == "fixed":
        return ""
    label = _movement_label(item, path)
    trigger = _required_text(item.get("trigger"), f"{path}.trigger")
    speed = _required_text(item.get("speed"), f"{path}.speed")
    route = _required_text(item.get("path"), f"{path}.path")
    end_condition = _required_text(item.get("end_condition"), f"{path}.end_condition")
    return f"当{trigger}时，摄影机以{speed}{label}，路径为{route}，到{end_condition}停止"


def _render_state_update(update: Any, path: str) -> str:
    item = _mapping(update, path)
    entity = _required_text(item.get("entity"), f"{path}.entity")
    field = _required_text(item.get("field"), f"{path}.field")
    before = normalize_text(item.get("from"))
    after = _required_text(item.get("to"), f"{path}.to")
    if before:
        return f"{entity}的{field}由{before}变为{after}"
    return f"{entity}的{field}变为{after}"


def assert_frontend_text_clean(text: str, path: str = "xlsx_projection") -> None:
    if text.count("\n") != 1:
        raise XlsxProjectionError(f"{path} 必须只有摄影头与单一画面自然段。")
    header, body = text.split("\n", 1)
    if not re.fullmatch(r"【[^【】\n]+，[^【】\n]+，[^【】\n]+】", header):
        raise XlsxProjectionError(f"{path} 摄影头格式无效：{header}")
    if not body.startswith("【画面内容】") or not body[len("【画面内容】") :].strip():
        raise XlsxProjectionError(f"{path} 缺少单一画面自然段。")
    for pattern in _BACKEND_LEAK_PATTERNS:
        match = pattern.search(text)
        if match:
            raise XlsxProjectionError(f"{path} 泄漏后端或空值文本：{match.group(0)}")
    for phrase in _TEMPLATE_PHRASES:
        if phrase in text:
            raise XlsxProjectionError(f"{path} 含跨镜模板套话：{phrase}")


def render_xlsx_execution_text(
    shot: Mapping[str, Any], dialogue_index: Mapping[str, Mapping[str, Any]]
) -> str:
    """Render the compact fifth XLSX column from canonical references."""
    shot_id = normalize_text(shot.get("shot_id")) or "<unknown-shot>"
    camera = _mapping(shot.get("camera"), f"{shot_id}.camera")
    staging = _mapping(shot.get("staging"), f"{shot_id}.staging")
    movement = _mapping(camera.get("movement"), f"{shot_id}.camera.movement")
    angle = _required_text(camera.get("angle"), f"{shot_id}.camera.angle")
    shot_size = _required_text(camera.get("shot_size"), f"{shot_id}.camera.shot_size")
    resolved_flow = validate_shot_flow(shot)
    _validate_frontend_projection_sources(shot, resolved_flow, shot_id)
    header = f"【{angle}，{shot_size}，{_movement_label(movement, f'{shot_id}.camera.movement')}】"

    sentences: list[str] = []
    for flow_index, (owner, resolved) in enumerate(resolved_flow):
        path = f"{shot_id}.shot_flow[{flow_index}]"
        if owner == "camera_setup":
            camera_value = _mapping(resolved, f"{path}.camera_setup")
            rendered = _camera_setup_for_frontend(camera_value, staging, shot_id)
        elif owner in SPAN_OWNERS:
            rendered = _required_text(resolved, path)
        elif owner == "dialogue_segment":
            rendered = _render_dialogue(resolved, dialogue_index, path)
        elif owner == "effect":
            rendered = _required_text(resolved, path)
        elif owner == "movement":
            rendered = _render_movement(resolved, f"{shot_id}.camera.movement")
        elif owner == "state_update":
            rendered = _render_state_update(resolved, path)
        else:  # pragma: no cover - kept exhaustive by FLOW_OWNERS
            raise XlsxProjectionError(f"{path} 无法投影 owner：{owner}")
        sentence = _sentence(rendered)
        if sentence:
            sentences.append(sentence)
    result = f"{header}\n【画面内容】{''.join(sentences)}"
    assert_frontend_text_clean(result, f"{shot_id}.xlsx_projection")
    return result


def project_storyboard_rows(data: Mapping[str, Any]) -> list[list[Any]]:
    dialogue_index = build_dialogue_index(data)
    scenes_raw = _sequence(data.get("scenes", []), "scenes")
    scene_names: dict[str, str] = {}
    for index, raw in enumerate(scenes_raw):
        scene = _mapping(raw, f"scenes[{index}]")
        scene_id = _required_text(scene.get("scene_id"), f"scenes[{index}].scene_id")
        scene_names[scene_id] = _required_text(scene.get("scene"), f"scenes[{index}].scene")

    rows: list[list[Any]] = []
    shots = _sequence(data.get("shots", []), "shots")
    for index, raw in enumerate(shots):
        shot = _mapping(raw, f"shots[{index}]")
        scene_id = _required_text(shot.get("scene_id"), f"shots[{index}].scene_id")
        if scene_id not in scene_names:
            raise XlsxProjectionError(f"shots[{index}].scene_id 未登记：{scene_id}")
        rows.append(
            [
                _required_text(shot.get("shot_id"), f"shots[{index}].shot_id"),
                scene_names[scene_id],
                normalize_text(shot.get("source_excerpt")),
                shot.get("duration_seconds", ""),
                render_xlsx_execution_text(shot, dialogue_index),
                normalize_text(shot.get("notes")),
            ]
        )
    return rows


def project_director_design_rows(data: Mapping[str, Any]) -> list[list[str]]:
    design = _mapping(data.get("director_design"), "director_design")
    return [[label, _required_text(design.get(key), f"director_design.{key}")] for label, key in DESIGN_LABELS]


def project_assumption_rows(data: Mapping[str, Any]) -> list[list[str]]:
    assumptions = _sequence(data.get("assumptions", []), "assumptions")
    if not assumptions:
        return [["—", "无开放假设"]]
    rows: list[list[str]] = []
    for index, raw in enumerate(assumptions, start=1):
        item = _mapping(raw, f"assumptions[{index - 1}]")
        statement = _required_text(item.get("statement"), f"assumptions[{index - 1}].statement")
        impact = _required_text(item.get("impact"), f"assumptions[{index - 1}].impact")
        rows.append([f"待确认项 {index}", f"{statement}\n影响：{impact}"])
    return rows


def _format_duration(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def project_xlsx(data: Mapping[str, Any]) -> dict[str, Any]:
    source = _mapping(data.get("source"), "source")
    format_brief = _mapping(data.get("format_brief"), "format_brief")
    dialogue_pace = _mapping(format_brief.get("dialogue_pace"), "format_brief.dialogue_pace")
    title = _required_text(source.get("title"), "source.title")
    storyboard_rows = project_storyboard_rows(data)
    total_duration = sum((Decimal(str(row[3])) for row in storyboard_rows), Decimal("0"))
    return {
        "title": title,
        "summary": (
            f"画幅 {_required_text(format_brief.get('aspect_ratio'), 'format_brief.aspect_ratio')}｜"
            f"节奏 {RHYTHM_LABELS.get(format_brief.get('rhythm_profile'), format_brief.get('rhythm_profile'))}｜"
            f"对白 {PACE_LABELS.get(dialogue_pace.get('pace_profile'), dialogue_pace.get('pace_profile'))} "
            f"{_format_duration(Decimal(str(dialogue_pace.get('selected_cps'))))}字/秒"
            f"（区间 {_format_duration(Decimal(str(dialogue_pace.get('range_min_cps'))))}–{_format_duration(Decimal(str(dialogue_pace.get('range_max_cps'))))}）｜"
            f"共 {len(storyboard_rows)} 镜｜总时长 {_format_duration(total_duration)} 秒"
        ),
        "storyboard_rows": storyboard_rows,
        "director_design_rows": project_director_design_rows(data),
        "assumption_rows": project_assumption_rows(data),
    }


def projection_sha256(data: Mapping[str, Any]) -> str:
    payload = json.dumps(
        project_xlsx(data),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def projected_dialogue_segment_count(data: Mapping[str, Any]) -> int:
    shots = _sequence(data.get("shots", []), "shots")
    count = 0
    for shot_index, raw in enumerate(shots):
        shot = _mapping(raw, f"shots[{shot_index}]")
        flow = _sequence(shot.get("shot_flow"), f"shots[{shot_index}].shot_flow")
        count += sum(
            isinstance(item, Mapping) and item.get("owner") == "dialogue_segment" for item in flow
        )
    return count
