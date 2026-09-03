#!/usr/bin/env python3
"""Deterministic renderer for the Agent-facing backend execution record.

The renderer is deliberately pure: it accepts one shot object and returns text.
The structured shot model is the only execution source of truth. A stored
``execution_text`` that differs from this renderer is stale and must not be
accepted by the formal validator.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Imported by the formal backend to serialize structured execution facts."


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

MOTIVATION_LABELS = {
    "information": "信息",
    "emotion": "情绪",
    "relationship": "关系",
    "space": "空间",
    "time": "时间",
    "subjective": "主观感知",
    "symbolic": "象征",
    "spectacle": "奇观",
    "rhythm": "节奏",
    "other": "其他",
}

DIALOGUE_DELIVERY_LABELS = {
    "onscreen": "画内",
    "os": "画外",
    "vo": "旁白",
    "mediated": "媒介声",
    "unresolved": "待确认",
}

# Values stored in structured fields may themselves be enums. Translate the
# known internal vocabulary before it reaches the Chinese formal column.
INTERNAL_VALUE_LABELS = {
    "subject": "人物",
    "relationship": "人物关系",
    "object": "物件",
    "space": "空间",
    "subjective": "主观感知",
    "single": "单人构图",
    "two_shot": "双人构图",
    "group": "群像构图",
    "over_shoulder": "过肩构图",
    "insert": "细节插入",
    "observe": "观察",
    "isolate": "隔离",
    "reframe": "重构图",
    "follow": "跟随",
    "withhold": "延迟揭示",
    "body": "身体",
    "face": "面孔",
    "detail": "细节",
    "scene_end": "场景结束",
    "scene_transition": "场景转场",
    "hard_cut": "硬切",
    "jump_cut": "跳切",
    "match_cut": "匹配剪辑",
    "sound_bridge": "声音桥接",
    "visual_bridge": "视觉桥接",
    "camera_reframe": "摄影机重构图",
    "actor_reframe": "人物重构图",
    "focus_shift": "焦点转移",
    "blocking_change": "调度变化",
    "reveal": "揭示",
    "conceal": "隐藏",
    "hold": "保持",
    "cutaway": "插入镜头",
    "reaction": "反应",
    "eyeline_match": "视线匹配",
    "movement_match": "动作匹配",
    "continuity_match": "连续性匹配",
    "contrast": "对比",
    "parallel": "平行关系",
    "causal_progression": "因果推进",
    "relationship_accumulation": "关系累积",
    "information_release": "信息释放",
    "rhythmic_acceleration": "节奏加速",
    "rhythmic_deceleration": "节奏减速",
    "horizontal": "横向分布",
    "vertical": "纵向分布",
    "depth": "纵深轴",
    "layered": "前后景分层",
    "centered": "中心轴",
    "diagonal": "对角轴",
    "sequential": "顺序发生",
    "high": "高",
    "medium": "中",
    "low": "低",
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def translated(value: Any) -> str:
    text = normalize_text(value)
    return INTERNAL_VALUE_LABELS.get(text, text)


def numeric(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def joined(values: Any, *, empty: str = "无") -> str:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return empty
    items = [translated(value) for value in values if normalize_text(value)]
    return "；".join(items) if items else empty


def movement_text(value: Any) -> str:
    movement = value if isinstance(value, Mapping) else {}
    movement_type = normalize_text(movement.get("type"))
    label = MOVEMENT_LABELS.get(movement_type, translated(movement_type) or "未定义")
    fields = [
        ("触发", movement.get("trigger")),
        ("速度", movement.get("speed")),
        ("路径", movement.get("path")),
        ("终止", movement.get("end_condition")),
        ("理由", movement.get("reason")),
    ]
    details = "；".join(f"{name}：{translated(raw)}" for name, raw in fields if normalize_text(raw))
    return f"{label}；{details}" if details else label


def dialogue_text(value: Any) -> str:
    segments = value if isinstance(value, list) else []
    rendered: list[str] = []
    for segment in segments:
        if not isinstance(segment, Mapping):
            continue
        delivery = DIALOGUE_DELIVERY_LABELS.get(
            normalize_text(segment.get("delivery")), translated(segment.get("delivery")) or "未定义"
        )
        dialogue_id = normalize_text(segment.get("dialogue_id"))
        text = normalize_text(segment.get("text"))
        if text:
            rendered.append(f"{dialogue_id}（{delivery}）：“{text}”")
    return "；".join(rendered) if rendered else "无"


def state_updates_text(value: Any) -> str:
    updates = value if isinstance(value, list) else []
    rendered: list[str] = []
    for update in updates:
        if not isinstance(update, Mapping):
            continue
        rendered.append(
            "{entity}·{field}：{before}→{after}".format(
                entity=translated(update.get("entity")) or "未定义主体",
                field=translated(update.get("field")) or "状态",
                before=translated(update.get("from")) or "未定义",
                after=translated(update.get("to")) or "未定义",
            )
        )
    return "；".join(rendered) if rendered else "无"


def intentional_breaks_text(value: Any) -> str:
    breaks = value if isinstance(value, list) else []
    rendered: list[str] = []
    for item in breaks:
        if not isinstance(item, Mapping):
            continue
        rendered.append(
            "违例：{what}；观众效果：{effect}；戏剧理由：{reason}；重新定位：{reorientation}".format(
                what=translated(item.get("what_breaks")) or "未定义",
                effect=translated(item.get("audience_effect")) or "未定义",
                reason=translated(item.get("dramatic_reason")) or "未定义",
                reorientation=translated(item.get("reorientation")) or "未定义",
            )
        )
    return "；".join(rendered) if rendered else "无"


def timing_plan_text(value: Any) -> str:
    plan = value if isinstance(value, Mapping) else {}
    blocks = plan.get("blocks") if isinstance(plan.get("blocks"), list) else []
    rendered: list[str] = []
    for block in blocks:
        if not isinstance(block, Mapping):
            continue
        rendered.append(
            "{block_id}（语速 {pace_ref}，flow {start}–{end}，{mode}）：对白 {dialogue:g}s／动作 {action:g}s／摄影 {camera:g}s／声音 {sound:g}s／反应 {reaction:g}s／停留 {hold:g}s＝{computed:g}s".format(
                block_id=normalize_text(block.get("block_id")) or "未定义时间块",
                pace_ref=normalize_text(block.get("pace_ref")) or "未定义",
                start=block.get("flow_start_index", "?"),
                end=block.get("flow_end_index", "?"),
                mode=translated(block.get("mode")) or "未定义",
                dialogue=numeric(block.get("dialogue_seconds")),
                action=numeric(block.get("action_seconds")),
                camera=numeric(block.get("camera_seconds")),
                sound=numeric(block.get("sound_seconds")),
                reaction=numeric(block.get("reaction_seconds")),
                hold=numeric(block.get("hold_seconds")),
                computed=numeric(block.get("computed_seconds")),
            )
        )
    total = plan.get("computed_duration_seconds")
    confidence = translated(plan.get("confidence")) or "未定义"
    basis = translated(plan.get("basis")) or "未定义"
    blocks_text = "；".join(rendered) if rendered else "无"
    return f"时间块：{blocks_text}；总时长：{total} 秒；置信度：{confidence}；依据：{basis}"


def canonical_execution_text(shot: Mapping[str, Any]) -> str:
    """Render the exact Agent-facing execution_text for a formal shot."""
    viewpoint = shot.get("viewpoint") if isinstance(shot.get("viewpoint"), Mapping) else {}
    camera = shot.get("camera") if isinstance(shot.get("camera"), Mapping) else {}
    staging = shot.get("staging") if isinstance(shot.get("staging"), Mapping) else {}
    sound = shot.get("sound") if isinstance(shot.get("sound"), Mapping) else {}
    edit = shot.get("edit") if isinstance(shot.get("edit"), Mapping) else {}
    continuity = shot.get("continuity") if isinstance(shot.get("continuity"), Mapping) else {}
    motivation = shot.get("motivation") if isinstance(shot.get("motivation"), Mapping) else {}
    timing_plan = shot.get("timing_plan") if isinstance(shot.get("timing_plan"), Mapping) else {}
    movement = camera.get("movement") if isinstance(camera.get("movement"), Mapping) else {}

    movement_label = MOVEMENT_LABELS.get(
        normalize_text(movement.get("type")), translated(movement.get("type")) or "未定义"
    )
    header = "【{}｜{}｜{}】".format(
        translated(camera.get("shot_size")) or "未定义景别",
        translated(camera.get("angle")) or "未定义角度",
        movement_label,
    )

    lines = [header]
    lines.append(
        "【观看】所有权：{owner_type}（{owner_refs}）；读取：{reading}；摄影机响应：{response}；理由：{reason}".format(
            owner_type=translated(viewpoint.get("owner_type")) or "未定义",
            owner_refs=joined(viewpoint.get("owner_refs")),
            reading=translated(viewpoint.get("reading_priority")) or "未定义",
            response=translated(viewpoint.get("camera_response")) or "未定义",
            reason=translated(viewpoint.get("reason")) or "未定义",
        )
    )
    lines.append(
        "【摄影】构图类型：{framing}；主要主体：{primary_subjects}；前景主体：{foreground_subjects}；画框轴向：{frame_axis}；画幅适配：{aspect_ratio_reason}；机位：{position}；构图：{composition}；景别：{shot_size}（{shot_size_reason}）；角度：{angle}（{angle_reason}）；镜头意图：{lens}；运动：{movement}；焦点：{focus}；光线变化：{light}".format(
            framing=translated(camera.get("framing_mode")) or "未定义",
            primary_subjects=joined(camera.get("primary_subjects")),
            foreground_subjects=joined(camera.get("foreground_subjects")),
            frame_axis=translated(camera.get("frame_axis")) or "未定义",
            aspect_ratio_reason=translated(camera.get("aspect_ratio_reason")) or "未定义",
            position=translated(camera.get("position")) or "未定义",
            composition=translated(camera.get("composition")) or "未定义",
            shot_size=translated(camera.get("shot_size")) or "未定义",
            shot_size_reason=translated(camera.get("shot_size_reason")) or "未定义",
            angle=translated(camera.get("angle")) or "未定义",
            angle_reason=translated(camera.get("angle_reason")) or "未定义",
            lens=translated(camera.get("lens_intent")) or "未定义",
            movement=movement_text(movement),
            focus=translated(camera.get("focus")) or "未定义",
            light=translated(camera.get("lighting_change")) or "无",
        )
    )
    lines.append(
        "【调度与表演】主体：{subjects}；画内：{visible}；画外：{offscreen}；调度：{blocking}；表演：{performance}".format(
            subjects=joined(staging.get("subjects")),
            visible=joined(staging.get("visible_subjects")),
            offscreen=joined(staging.get("offscreen_subjects")),
            blocking=translated(staging.get("blocking")) or "未定义",
            performance=translated(staging.get("performance")) or "未定义",
        )
    )
    lines.append(
        "【声音】声场：{perspective}；对白：{dialogue}；音效：{effects}；环境：{ambience}；音乐：{music}".format(
            perspective=translated(sound.get("perspective")) or "未定义",
            dialogue=dialogue_text(sound.get("dialogue_segments")),
            effects=joined(sound.get("effects")),
            ambience=translated(sound.get("ambience")) or "无",
            music=translated(sound.get("music")) or "无",
        )
    )
    lines.append(
        "【剪辑】入点：{entry}；出点：{exit}；下一关系：{transition}".format(
            entry=translated(edit.get("entry")) or "未定义",
            exit=translated(edit.get("exit")) or "未定义",
            transition=translated(edit.get("transition_to_next")) or "未定义",
        )
    )
    lines.append(
        "【连续性】轴线：{axis}；银幕方向：{direction}；状态变化：{updates}；有意违例：{breaks}".format(
            axis=translated(continuity.get("axis")) or "未定义",
            direction=translated(continuity.get("screen_direction")) or "未定义",
            updates=state_updates_text(continuity.get("state_updates")),
            breaks=intentional_breaks_text(continuity.get("intentional_breaks")),
        )
    )
    lines.append("【时长】" + timing_plan_text(timing_plan))
    primary = MOTIVATION_LABELS.get(
        normalize_text(motivation.get("primary")), translated(motivation.get("primary")) or "未定义"
    )
    lines.append(
        "【镜头动机】主因：{primary}；理由：{reason}；时长依据：{duration_basis}".format(
            primary=primary,
            reason=translated(motivation.get("reason")) or "未定义",
            duration_basis=translated(shot.get("duration_basis")) or "未定义",
        )
    )
    return "\n".join(lines)
