#!/usr/bin/env python3
"""Chinese semantic audit for su-image9 v2.1.2.

Reads a validated shot_data.json and reports upstream semantic conflicts that
would make the visual derivation unreliable. This module never mutates the
source data and never invents story facts.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any


CONFLICT_CODE = "F-SEMANTIC-CONFLICT"


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(value or ""))).strip()


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalized_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = clean_text(item) if isinstance(item, str) else ""
        if text and text not in result:
            result.append(text)
    return result


def has_dialogue_fact(shot: dict[str, Any], data: dict[str, Any]) -> bool:
    fact_ids = {clean_text(fid) for fid in as_list(shot.get("covered_fact_ids"))}
    for beat in as_list(data.get("beats")):
        if not isinstance(beat, dict):
            continue
        for fact in as_list(beat.get("facts")):
            if not isinstance(fact, dict):
                continue
            if clean_text(fact.get("fact_id")) in fact_ids and clean_text(fact.get("type")).lower() == "dialogue":
                return True
    return False


def has_action_fact(shot: dict[str, Any], data: dict[str, Any]) -> bool:
    fact_ids = {clean_text(fid) for fid in as_list(shot.get("covered_fact_ids"))}
    for beat in as_list(data.get("beats")):
        if not isinstance(beat, dict):
            continue
        for fact in as_list(beat.get("facts")):
            if not isinstance(fact, dict):
                continue
            if clean_text(fact.get("fact_id")) in fact_ids and clean_text(fact.get("type")).lower() in {"action", "position"}:
                return True
    return False


def has_prop_fact(shot: dict[str, Any], data: dict[str, Any]) -> bool:
    fact_ids = {clean_text(fid) for fid in as_list(shot.get("covered_fact_ids"))}
    for beat in as_list(data.get("beats")):
        if not isinstance(beat, dict):
            continue
        for fact in as_list(beat.get("facts")):
            if not isinstance(fact, dict):
                continue
            if clean_text(fact.get("fact_id")) in fact_ids and clean_text(fact.get("type")).lower() == "prop":
                return True
    return False


def covered_beat_count(shot: dict[str, Any]) -> int:
    return len(as_list(shot.get("beat_ids")))


def action_and_dialogue_seconds(shot: dict[str, Any]) -> int:
    breakdown = as_dict(shot.get("duration_breakdown"))
    return int(breakdown.get("sync_action_seconds", 0) or 0) + int(breakdown.get("sync_dialogue_seconds", 0) or 0)


def shot_duration_seconds(shot: dict[str, Any]) -> int:
    return int(shot.get("duration_seconds", 0) or 0)


def shot_type(shot: dict[str, Any]) -> str:
    return clean_text(shot.get("shot_type")).lower()


def source_paragraph_subjects(shot: dict[str, Any]) -> set[str]:
    """Extract candidate subjects from source_paragraph using simple heuristics."""
    text = clean_text(shot.get("source_paragraph"))
    subjects: set[str] = set()
    if not text:
        return subjects
    # Look for "X和Y", "X与Y", "X、Y" at sentence start or after punctuation.
    for match in re.finditer(r"([一-龥A-Za-z0-9]+)(?:和|与|、)", text):
        subjects.add(match.group(1))
    # First noun-like token before a verb.
    first_match = re.search(r"^([一-龥A-Za-z]+)[走到说拿看听]", text)
    if first_match:
        subjects.add(first_match.group(1))
    return subjects


def continuity_update_entities(shot: dict[str, Any]) -> set[str]:
    entities: set[str] = set()
    for update in as_list(shot.get("continuity_updates")):
        if not isinstance(update, dict):
            continue
        entity = clean_text(update.get("entity"))
        if entity:
            entities.add(entity)
    return entities


def audit_shot(shot: dict[str, Any], data: dict[str, Any]) -> list[str]:
    """Return a list of human-readable conflict messages for a single shot."""
    messages: list[str] = []
    shot_no = int(shot.get("shot_no", 0))
    prefix = f"shot_no={shot_no}"

    # Conflict 1: position update with identical from/to
    for update in as_list(shot.get("continuity_updates")):
        if not isinstance(update, dict):
            continue
        field = clean_text(update.get("field")).lower()
        from_value = clean_text(update.get("from"))
        to_value = clean_text(update.get("to"))
        if field == "position" and from_value and from_value == to_value:
            messages.append(
                f"{prefix} 的 position update 起点与终点相同（{from_value}），请确认该角色是否需要真实移动。"
            )

    # Conflict 2: action performer mismatch between source_paragraph and continuity_updates
    subjects = source_paragraph_subjects(shot)
    entities = continuity_update_entities(shot)
    if subjects and entities and not (subjects & entities):
        messages.append(
            f"{prefix} 的 source_paragraph 主语（{', '.join(sorted(subjects))}）与 continuity_updates 实体（{', '.join(sorted(entities))}）不一致，请确认动作执行者。"
        )

    # Conflict 3: single shot carries too many distinct beats for its action/dialogue time
    beat_count = covered_beat_count(shot)
    duration = shot_duration_seconds(shot)
    active_seconds = action_and_dialogue_seconds(shot)
    if beat_count >= 3 and active_seconds < 2:
        messages.append(
            f"{prefix} 覆盖 {beat_count} 个 Beat，但动作/对白时长仅 {active_seconds} 秒，单张静态图可能无法承载多个叙事阶段。"
        )
    elif beat_count >= 2 and duration > 0 and active_seconds / duration < 0.4:
        messages.append(
            f"{prefix} 覆盖 {beat_count} 个 Beat，但动作/对白时长占比过低（{active_seconds}/{duration} 秒），请确认是否需要拆分镜头。"
        )

    # Conflict 4: insert_priority must_have without prop fact or visible prop
    insert_priority = clean_text(shot.get("insert_priority")).lower()
    if insert_priority == "must_have":
        if not has_prop_fact(shot, data):
            messages.append(f"{prefix} 的 insert_priority 为 must_have，但未覆盖 prop fact，请确认道具插入需求。")
        if not as_list(shot.get("visible_props")):
            messages.append(f"{prefix} 的 insert_priority 为 must_have，但 visible_props 为空，无法生成道具插入。")

    # Conflict 5: non-reality layer without visual cue in camera_main_image or notes
    scene_id = clean_text(shot.get("scene_id"))
    layer = ""
    for log in as_list(data.get("continuity_logs")):
        if isinstance(log, dict) and clean_text(log.get("scene_id")) == scene_id:
            layer = clean_text(log.get("reality_layer"))
            break
    if layer and layer != "现实":
        camera_text = clean_text(shot.get("camera_main_image"))
        notes = clean_text(shot.get("notes"))
        cue_terms = ("主观", "回忆", "梦境", "闪回", "幻觉", "虚化", "留白", "边缘")
        if not any(term in camera_text or term in notes for term in cue_terms):
            messages.append(
                f"{prefix} 属于现实层“{layer}”，但 camera_main_image 与 notes 中缺少可视化线索（如主观、回忆、留白等），模型可能无法区分。"
            )

    # Conflict 6: contradictory directional terms in camera_main_image
    camera_text = clean_text(shot.get("camera_main_image"))
    direction_pairs = [
        ("左", "右"),
        ("上", "下"),
        ("前", "后"),
        ("内", "外"),
        ("进", "出"),
    ]
    for a, b in direction_pairs:
        if a in camera_text and b in camera_text:
            messages.append(f"{prefix} 的 camera_main_image 同时出现“{a}”与“{b}”，请确认方位描述是否矛盾。")

    return messages


def audit_data(data: dict[str, Any]) -> list[str]:
    """Run semantic audit across all shots and return conflict messages."""
    messages: list[str] = []
    for shot in as_list(data.get("shots")):
        if not isinstance(shot, dict):
            continue
        messages.extend(audit_shot(shot, data))
    return messages


def semantic_conflicts(data: dict[str, Any]) -> list[str]:
    """Public entry point used by the deriver."""
    return audit_data(data)


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv or sys.argv[1:]
    if len(args) != 1 or args[0] in ("-h", "--help"):
        print("usage: semantic_audit.py <shot_data.json>", file=sys.stderr)
        return 0 if args and args[0] in ("-h", "--help") else 2
    path = Path(args[0])
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    conflicts = semantic_conflicts(data)
    print(json.dumps(conflicts, ensure_ascii=False, indent=2))
    return 0 if not conflicts else 1


if __name__ == "__main__":
    raise SystemExit(main())
