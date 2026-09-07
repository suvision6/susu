"""Read-only source projection. Original bytes and all fields remain in the plan.

This is not a screenplay director or a semantic judge. Unknown execution fields
are retained and flagged for the separate source review, not silently erased.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import copy
import json
import re
from .common import DeliveryError, digest, issue, leaves, load_json, position_label, seconds, text_value

@dataclass
class Source:
    payload: bytes
    name: str
    document: object
    shots: list[dict]
    issues: list[dict]

    @property
    def sha256(self):
        return digest(self.payload)

# Field ownership, not source skill/version, selects the supported shape.
VISUAL = ("scene_context", "subjects", "visible_subjects", "offscreen_subjects", "blocking",
          "visible_behavior", "performance", "camera", "start_state", "end_state", "delta_text",
          "visible_props", "continuity", "continuity_updates", "lighting_style", "allowed_lighting_changes",
          "constraints", "audio", "scene_material", "screen_text", "staging")
AUDIT_LEAVES = {"reason", "rationale", "motivation", "hold_reason", "confidence", "owner", "provenance",
                "evidence_fact_ids", "duration_basis", "cut_or_hold_reason"}
KNOWN_TOP = set(VISUAL) | {
    "source_shot_id", "shot_id", "id", "source_order", "order", "scene_id", "source_excerpt", "source",
    "duration_seconds", "duration", "sound", "dialogue", "dialogues", "execution_text", "rendered_shot_description",
    "emotion_intent", "motivation", "edit", "notes", "duration_basis", "source_locator", "source_kind",
    "covered_fact_ids", "shot_phases", "missing_fields", "availability", "source_available", "compilable",
    "cut_design", "source_shot_hash", "field_hashes", "narrative_intent", "transition_to_next",
}

def _values(value):
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]

def _dialogues(raw: dict, authority: dict, sid: str, issues: list) -> list[dict]:
    sound = raw.get("sound", {})
    sound = sound if isinstance(sound, dict) else {}
    nested = sound.get("dialogue_segments")
    flat = raw.get("dialogue", raw.get("dialogues"))
    supplied = nested if nested is not None else flat
    # Two nonempty owners must agree after resolving their source references.
    def convert(values):
        output = []
        for index, part in enumerate(_values(values)):
            part = {"text": part} if isinstance(part, str) else part
            if not isinstance(part, dict):
                issues.append(issue("DIALOGUE_INVALID", "对白项不是对象或文字", sid)); continue
            did = str(part.get("dialogue_id", ""))
            parent = authority.get(did, {})
            if did and authority and not parent:
                issues.append(issue("DIALOGUE_ID_UNKNOWN", f"未找到来源对白 {did}", sid))
            literal = part.get("text", parent.get("text", ""))
            speaker = part.get("speaker", part.get("character", parent.get("speaker", "")))
            full_text = parent.get("text", part.get("source_text", literal))
            if not isinstance(literal, str) or not literal:
                issues.append(issue("DIALOGUE_INVALID", "对白载荷必须为非空原文", sid)); continue
            if parent and part.get("speaker") and part["speaker"] != parent.get("speaker"):
                issues.append(issue("DIALOGUE_SPEAKER_CONFLICT", f"{did} 说话人冲突", sid))
            if not isinstance(full_text, str) or literal not in full_text:
                issues.append(issue("DIALOGUE_TEXT_CONFLICT", f"{did} 片段不属于来源原文", sid))
            raw_position = part.get("delivery", part.get("shot_delivery", part.get("position", part.get("on_screen", ""))))
            try:
                position = position_label(raw_position)
            except DeliveryError as exc:
                position = ""
                issues.append(issue("DIALOGUE_POSITION_UNKNOWN", str(exc), sid))
            output.append({"event_id": f"{sid}:D{index+1:03d}", "dialogue_id": did or f"{sid}:D{index+1:03d}",
                           "speaker": str(speaker), "text": literal, "source_text": full_text,
                           "position": position, "source_position": raw_position,
                           "source_path": f"{sid}.dialogue[{index}]"})
        return output
    result = convert(supplied)
    if nested and flat:
        other = convert(flat)
        comparable = lambda rows: [(d["speaker"], d["text"], d["position"]) for d in rows]
        if comparable(result) != comparable(other):
            issues.append(issue("UPSTREAM_FIELD_CONFLICT", "顶层与 sound 对白所有者冲突", sid))
    return result

def _script_segments(text: str):
    """Parse explicit full-line speaker labels only; preserve the original source.

    This is not an NLP inference. Ambiguous prose still needs Agent source review.
    """
    dialogue = []; narrative = []
    non_speakers = {"场景", "时间", "地点", "备注", "动作", "画面", "镜头", "声音", "字幕", "屏幕文字", "画面文字", "内景", "外景"}
    for line_number, line in enumerate(text.splitlines(keepends=True), 1):
        match = re.fullmatch(r"[ \t]*([^：:\n。！？；，]{1,40})[：:][ \t]*(.+?)[\r\n]*", line)
        if not match:
            narrative.append(line); continue
        label, literal = match[1].strip(), match[2]
        voice = re.search(r"[（(]([^）)]+)[）)]$", label)
        speaker = label[:voice.start()].strip() if voice else label
        if speaker in non_speakers or not speaker:
            narrative.append(line); continue
        if len(literal) >= 2 and (literal[0], literal[-1]) in {(chr(34),chr(34)), ("“","”")}:
            literal = literal[1:-1]
        if not literal:
            narrative.append(line); continue
        dialogue.append({"speaker":speaker, "text":literal, "position":voice[1] if voice else "",
                         "source_line":line_number})
    return "".join(narrative), dialogue

def normalize(payload: bytes, name: str = "source.json") -> Source:
    try:
        decoded = payload.decode("utf-8-sig")
    except UnicodeError as exc:
        raise DeliveryError("请由 Agent 读取该载体，再建立带原文定位的 UTF-8 只读副本") from exc
    is_json = Path(name).suffix.lower() == ".json"
    document = load_json(decoded) if is_json else {"text": decoded}
    lexical = json.loads(decoded, parse_float=str) if is_json else {}
    precise_items = lexical if isinstance(lexical, list) else lexical.get("shots", lexical.get("source_shots")) if isinstance(lexical, dict) else None
    issues: list[dict] = []
    if isinstance(document, list):
        document = {"shots": document}
    if not isinstance(document, dict):
        raise DeliveryError("来源必须为对象、镜头数组或 UTF-8 原文")
    items = document.get("shots", document.get("source_shots"))
    if items is None:
        raw_text = document.get("text", document.get("script", document.get("screenplay")))
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise DeliveryError("没有可读取的 shots 或原文 text；不要猜测字段含义")
        # A source paragraph is not a newly invented camera shot.
        narrative, dialogue = _script_segments(raw_text)
        items = [{"source_shot_id": "P001", "source_kind": "event", "source_excerpt": raw_text,
                  "delta_text": narrative, "dialogue":dialogue,
                  "source_locator": {"start_line": 1, "end_line": len(raw_text.splitlines())}}]
        issues.append(issue("UNSTRUCTURED_REVIEW_REQUIRED", "原文未分镜；按事件转写，不补摄影或时长", "P001", "REVIEW"))
    if not isinstance(items, list) or not items:
        raise DeliveryError("来源镜头／源段列表为空或不可读")
    authority = {}
    source_header = document.get("source", {})
    for row in _values(source_header.get("dialogue_lines") if isinstance(source_header, dict) else None):
        if not isinstance(row, dict) or not row.get("dialogue_id"):
            raise DeliveryError("来源对白台账缺少 dialogue_id")
        did = str(row["dialogue_id"])
        if did in authority and authority[did] != row:
            raise DeliveryError(f"来源对白 ID 冲突：{did}")
        authority[did] = row
    scenes = {str(s.get("scene_id", s.get("id", ""))): s for s in document.get("scenes", []) if isinstance(s, dict)}
    seen = set(); shots = []
    for index, original in enumerate(items):
        if not isinstance(original, dict):
            raise DeliveryError(f"第 {index+1} 个来源项目不是对象")
        raw = copy.deepcopy(original)
        sid = str(raw.get("source_shot_id", raw.get("shot_id", raw.get("id", f"P{index+1:03d}"))))
        if not sid or sid in seen:
            raise DeliveryError(f"来源 ID 为空或重复：{sid}")
        seen.add(sid)
        kind = raw.get("source_kind", "shot" if any(k in raw for k in ("source_shot_id", "shot_id", "id")) else "event")
        try:
            precise = precise_items[index] if isinstance(precise_items, list) and isinstance(precise_items[index], dict) else raw
            duration = seconds(precise.get("duration_seconds", precise.get("duration")))
        except DeliveryError as exc:
            duration = None; issues.append(issue("SOURCE_DURATION_INVALID", str(exc), sid))
        if raw.get("source_available") is False or raw.get("compilable") is False:
            issues.append(issue("SOURCE_UNAVAILABLE", "来源标记为不可编译", sid))
        facts = []
        def add(value, path, category):
            for leaf_path, text in leaves(value, path):
                parts = re.split(r"[.\[\]]+", leaf_path)
                if any(p in AUDIT_LEAVES for p in parts):
                    continue
                if isinstance(text, (str, int, float)) and not isinstance(text, bool):
                    facts.append({"path": leaf_path, "text": str(text), "kind": category})
        staging = raw.get("staging", {})
        if isinstance(staging, dict):
            for a, b in (("subjects", "subjects"), ("visible_subjects", "visible_subjects"),
                         ("offscreen_subjects", "offscreen_subjects"), ("blocking", "blocking")):
                if staging.get(a) and raw.get(b) and _values(staging[a]) != _values(raw[b]):
                    issues.append(issue("UPSTREAM_FIELD_CONFLICT", f"staging.{a} 与 {b} 冲突", sid))
        for key in VISUAL:
            add(raw.get(key), key, "sound" if key == "audio" else "visual")
        sound = raw.get("sound", {})
        if isinstance(sound, dict):
            for key, value in sound.items():
                if key != "dialogue_segments":
                    add(value, "sound." + key, "sound")
        scene = scenes.get(str(raw.get("scene_id", "")), {})
        scene_context = raw.get("scene_context", {})
        scene_name = text_value(scene_context.get("scene", scene_context.get("location", ""))) if isinstance(scene_context, dict) else str(scene_context or "")
        scene_name = scene_name or str(scene.get("scene", raw.get("scene_id", "")))
        # Preserve global scene material as raw context, not a per-Cut future state.
        for key in ("execution_text", "rendered_shot_description"):
            if raw.get(key):
                if not facts and key == "rendered_shot_description":
                    add(raw[key], key, "visual")
                else:
                    issues.append(issue("EXECUTION_TEXT_REVIEW_REQUIRED", f"重新读取 {key}，核对独有事实及审计文字", sid, "REVIEW"))
        for key, value in raw.items():
            if key not in KNOWN_TOP and value not in (None, "", [], {}):
                issues.append(issue("UNKNOWN_FIELD_REVIEW_REQUIRED", f"保留未识别字段：{key}", sid, "REVIEW"))
        dialogue = _dialogues(raw, authority, sid, issues)
        shots.append({"id": sid, "order": index, "kind": kind, "duration": duration,
                      "scene": scene_name, "scene_raw": scene, "raw": raw,
                      "facts": facts, "dialogue": dialogue,
                      "locator": raw.get("source_locator", {"json_path": f"shots[{index}]"})})
    # Split source lines must reconstruct in source order; distinct IDs remain distinct events.
    segments = {}
    for shot in shots:
        for event in shot["dialogue"]:
            if event["dialogue_id"] in authority:
                segments.setdefault(event["dialogue_id"], []).append((shot["id"], event["text"]))
    for did, parts in segments.items():
        full = authority[did].get("text", "")
        joined = "".join(text for _, text in parts)
        if joined != full:
            cursor = 0; ordered = True
            for _, text in parts:
                found = full.find(text, cursor)
                if found < 0:
                    ordered = False; break
                cursor = found + len(text)
            for sid, _ in parts:
                issues.append(issue("DIALOGUE_SEGMENTS_INCOMPLETE", f"{did} 片段未覆盖整句；核对是否为用户锁定的局部范围", sid, "REVIEW" if ordered else "ERROR"))
    return Source(payload, name, document, shots, issues)

def load_source(path: str | Path) -> Source:
    path = Path(path)
    return normalize(path.read_bytes(), path.name)
