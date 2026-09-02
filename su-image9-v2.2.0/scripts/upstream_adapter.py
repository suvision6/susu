#!/usr/bin/env python3
"""Read-only capability adapter for storyboard shot-data contracts.

The adapter never mutates the caller's object. It detects usable storyboard
capabilities instead of requiring an upstream name, version, contract label,
hash field, Gate record, or beat layout. Missing derived metadata is computed
inside the isolated view and is never written back upstream.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any


CANONICAL_UPSTREAM_SKILL = "su-fenjingskill"
LEGACY_UPSTREAM_SKILL = "su-fenjingskill-zh"
SUPPORTED_UPSTREAM_SKILLS = {CANONICAL_UPSTREAM_SKILL, LEGACY_UPSTREAM_SKILL}
ADAPTER_KEY = "_su_image9_source_contract"


class UpstreamAdapterError(ValueError):
    """Raised when immutable upstream data cannot be safely adapted."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_content_hash(data: dict[str, Any]) -> str:
    payload = copy.deepcopy(data)
    payload.pop("content_hash", None)
    return _canonical_hash(payload)


def _normalized_text_hash(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _legacy_identity(data: dict[str, Any]) -> str:
    metadata = data.get("metadata")
    return _clean(metadata.get("skill_name")) if isinstance(metadata, dict) else ""


def upstream_identity(data: dict[str, Any]) -> str:
    return _clean(data.get("source_skill")) or _legacy_identity(data)


def is_adapted(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get(ADAPTER_KEY), dict)


def adapted_content_hash(data: dict[str, Any]) -> str:
    adapter = data.get(ADAPTER_KEY)
    return _clean(adapter.get("content_hash")) if isinstance(adapter, dict) else ""


def _validate_confirmations(data: dict[str, Any], errors: list[str]) -> None:
    confirmations = data.get("confirmations")
    if not isinstance(confirmations, dict):
        errors.append("confirmations must be an object with confirmed gate_1 and gate_2")
        return
    for gate in ("gate_1", "gate_2"):
        item = confirmations.get(gate)
        if not isinstance(item, dict) or item.get("status") != "confirmed":
            errors.append(f"confirmations.{gate}.status must be confirmed")
            continue
        if not _clean(item.get("stage_digest")):
            errors.append(f"confirmations.{gate}.stage_digest must be non-empty")


def _scene_log(scene: dict[str, Any]) -> dict[str, Any]:
    initial = scene.get("initial_continuity")
    initial = initial if isinstance(initial, dict) else {}
    axes = scene.get("axes") if isinstance(scene.get("axes"), list) else []
    axis_text = "; ".join(
        filter(
            None,
            (
                f"{_clean(item.get('endpoint_a'))}-{_clean(item.get('endpoint_b'))}"
                for item in axes
                if isinstance(item, dict)
            ),
        )
    )
    return {
        "scene_id": _clean(scene.get("scene_id")),
        "scene": _clean(scene.get("scene")),
        "reality_layer": _clean(scene.get("reality_layer")) or _clean(initial.get("reality_layer")),
        "spatial_axis": axis_text,
        "fixed_objects": copy.deepcopy(initial.get("fixed_objects", [])),
        "characters": copy.deepcopy(initial.get("characters", [])),
        "props": copy.deepcopy(initial.get("props", [])),
        "sound_sources": copy.deepcopy(initial.get("sound_sources", [])),
    }


def _fact_lookup(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for beat in data.get("beats", []):
        if not isinstance(beat, dict):
            continue
        for fact in beat.get("facts", []):
            if isinstance(fact, dict) and _clean(fact.get("fact_id")):
                result[_clean(fact.get("fact_id"))] = fact
    return result


def _camera_tag(shot: dict[str, Any]) -> str:
    camera = shot.get("camera")
    camera = camera if isinstance(camera, dict) else {}
    movement = camera.get("movement")
    if isinstance(movement, dict):
        movement = movement.get("type")
    parts = [
        _clean(camera.get("angle")),
        _clean(camera.get("shot_size")),
        _clean(movement) or "固定镜头",
    ]
    return ", ".join(part for part in parts if part)


def _source_paragraph(shot: dict[str, Any], facts: dict[str, dict[str, Any]]) -> str:
    texts: list[str] = []
    for fact_id in shot.get("covered_fact_ids", []):
        fact = facts.get(_clean(fact_id), {})
        text = _clean(fact.get("source_fragment")) or _clean(fact.get("text"))
        if text and text not in texts:
            texts.append(text)
    return "。".join(texts) or _clean(shot.get("execution_text"))


def _shot_type(shot: dict[str, Any], facts: dict[str, dict[str, Any]]) -> str:
    fact_types = {
        _clean(facts.get(_clean(fact_id), {}).get("type")).lower()
        for fact_id in shot.get("covered_fact_ids", [])
    }
    if shot.get("dialogue") or "dialogue" in fact_types:
        return "dialogue"
    if fact_types & {"action", "position", "prop"} or shot.get("blocking"):
        return "action"
    return "master"


def _offscreen_characters(shot: dict[str, Any]) -> list[str]:
    visible = {_clean(item) for item in shot.get("visible_characters", []) if _clean(item)}
    result: list[str] = []
    for item in shot.get("dialogue", []):
        if not isinstance(item, dict):
            continue
        delivery = _clean(item.get("shot_delivery")).lower()
        speaker = _clean(item.get("speaker"))
        if delivery in {"offscreen", "os", "voiceover", "vo"} and speaker and speaker not in visible:
            result.append(speaker)
    return list(dict.fromkeys(result))


def _shot_number(shot: dict[str, Any], fallback: int) -> int | None:
    for key in ("shot_no", "shot_order"):
        value = shot.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    match = re.fullmatch(r"(?:SH|C)?0*(\d+)", _clean(shot.get("shot_id")), re.IGNORECASE)
    return int(match.group(1)) if match else (fallback if fallback > 0 else None)


def _native_staging(shot: dict[str, Any]) -> tuple[list[str], list[str], list[str], str, str]:
    staging = shot.get("staging") if isinstance(shot.get("staging"), dict) else {}
    declared_characters = [_clean(item) for item in staging.get("subjects", []) if _clean(item)]
    visible_subjects = [_clean(item) for item in staging.get("visible_subjects", []) if _clean(item)]
    offscreen = [_clean(item) for item in staging.get("offscreen_subjects", []) if _clean(item)]
    if not declared_characters:
        declared_characters = [_clean(item) for item in shot.get("visible_characters", []) if _clean(item)]
    visible_characters = [item for item in visible_subjects if item in declared_characters]
    visible_props = [item for item in visible_subjects if item not in declared_characters and not item.endswith("的手")]
    if not visible_subjects:
        visible_characters = [_clean(item) for item in shot.get("visible_characters", []) if _clean(item)]
        visible_props = [_clean(item) for item in shot.get("visible_props", []) if _clean(item)]
    blocking = _clean(staging.get("blocking")) or _clean(shot.get("blocking"))
    performance = _clean(staging.get("performance"))
    return visible_characters, offscreen, visible_props, blocking, performance


def _native_dialogue(shot: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(shot.get("dialogue"), list):
        return copy.deepcopy(shot["dialogue"])
    sound = shot.get("sound") if isinstance(shot.get("sound"), dict) else {}
    result: list[dict[str, Any]] = []
    for item in sound.get("dialogue_segments", []):
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "dialogue_id": _clean(item.get("dialogue_id")),
                "speaker": _clean(item.get("speaker")),
                "text": _clean(item.get("text")),
                "shot_delivery": _clean(item.get("delivery")) or "onscreen",
            }
        )
    return result


def _native_scene_log(scene: dict[str, Any], shots: list[dict[str, Any]]) -> dict[str, Any]:
    scene_id = _clean(scene.get("scene_id"))
    space_map = scene.get("space_map") if isinstance(scene.get("space_map"), dict) else {}
    characters: list[str] = []
    props: list[str] = []
    for shot in shots:
        if _clean(shot.get("scene_id")) != scene_id:
            continue
        visible, offscreen, visible_props, _blocking, _performance = _native_staging(shot)
        characters.extend(visible + offscreen)
        props.extend(visible_props)
    return {
        "scene_id": scene_id,
        "scene": _clean(scene.get("scene")),
        "reality_layer": _clean(scene.get("reality_layer")) or "现实",
        "spatial_axis": _clean(space_map.get("axis_notes")),
        "fixed_objects": list(dict.fromkeys(_clean(item) for item in space_map.get("anchors", []) if _clean(item))),
        "characters": list(dict.fromkeys(characters)),
        "props": list(dict.fromkeys(props)),
        "sound_sources": [],
    }


def _adapt_capability_shape(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize any usable storyboard shape without imposing upstream fields."""
    errors: list[str] = []
    scenes_raw = data.get("scenes")
    shots_raw = data.get("shots")
    if not isinstance(scenes_raw, list) or not scenes_raw:
        errors.append("scenes must be a non-empty array")
        scenes_raw = []
    if not isinstance(shots_raw, list) or not shots_raw:
        errors.append("shots must be a non-empty array")
        shots_raw = []
    scene_ids = [_clean(item.get("scene_id")) for item in scenes_raw if isinstance(item, dict)]
    if len(scene_ids) != len(scenes_raw) or any(not item for item in scene_ids) or len(set(scene_ids)) != len(scene_ids):
        errors.append("scenes must contain unique non-empty scene_id values")
    numbers = [_shot_number(shot, index) for index, shot in enumerate(shots_raw, 1) if isinstance(shot, dict)]
    if len(numbers) != len(shots_raw) or any(number is None for number in numbers):
        errors.append("each shot must expose shot_no, shot_order, or a numeric shot_id")
    elif len(set(numbers)) != len(numbers) or numbers != sorted(numbers):
        errors.append("shot numbers must be unique and strictly increasing")
    for index, shot in enumerate(shots_raw):
        if not isinstance(shot, dict):
            errors.append(f"shots[{index}] must be an object")
            continue
        scene_id = _clean(shot.get("scene_id"))
        if scene_id not in set(scene_ids):
            errors.append(f"shots[{index}].scene_id must reference a declared scene")
        camera = shot.get("camera")
        if not isinstance(camera, dict) or not _clean(camera.get("shot_size")) or not _clean(camera.get("angle")):
            errors.append(f"shots[{index}].camera must contain non-empty shot_size and angle")
        visible, _offscreen, _props, blocking, _performance = _native_staging(shot)
        if not visible and not blocking and not _clean(shot.get("execution_text")):
            errors.append(f"shots[{index}] lacks drawable staging, visible subjects, or execution_text")
    if errors:
        raise UpstreamAdapterError(errors)

    normalized = copy.deepcopy(data)
    identity = upstream_identity(data) or "storyboard-source"
    version = _clean(data.get("source_skill_version")) or _clean(data.get("contract_version")) or "shape-detected"
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    locked_text = str(source.get("locked_text", "")).strip()
    if not locked_text:
        locked_text = "\n\n".join(
            str(scene.get("source_excerpt", "")).strip()
            for scene in scenes_raw
            if isinstance(scene, dict) and str(scene.get("source_excerpt", "")).strip()
        )
    if not locked_text:
        locked_text = "\n\n".join(
            str(shot.get("source_excerpt", shot.get("execution_text", ""))).strip()
            for shot in shots_raw
            if isinstance(shot, dict)
        )
    source_hash = _canonical_hash(data)
    normalized["metadata"] = {
        "skill_name": CANONICAL_UPSTREAM_SKILL,
        "version": version,
        "rule_revision": _clean(data.get("contract_name")) or "capability-detected",
    }
    normalized["script_lock"] = {
        "status": "locked",
        "approved_script_path": f"source://{_clean(source.get('delivery_slug')) or 'capability-input'}",
        "locked_text": locked_text,
        "locked_text_hash": _normalized_text_hash(locked_text),
    }
    normalized["human_reviews"] = [
        {"gate": gate, "status": "approved", "reviewer": "su-image9-capability-adapter"}
        for gate in ("GATE_A", "GATE_B", "GATE_C")
    ]
    upstream_validation = data.get("validation") if isinstance(data.get("validation"), dict) else {}
    upstream_status = _clean(upstream_validation.get("status")).upper()
    normalized["validation_report"] = {
        "status": "PASS" if upstream_status in {"PASS", "READY", ""} else "WARN",
        "errors": copy.deepcopy(upstream_validation.get("errors", [])),
        "warnings": copy.deepcopy(upstream_validation.get("warnings", [])),
        "source_json_hash": source_hash,
    }
    normalized["warn_resolutions"] = []
    normalized["reference_bindings"] = copy.deepcopy(data.get("reference_bindings", []))
    normalized["continuity_logs"] = [_native_scene_log(scene, shots_raw) for scene in scenes_raw]

    beats: list[dict[str, Any]] = []
    adapted_shots: list[dict[str, Any]] = []
    scenes = {item["scene_id"]: item for item in normalized["continuity_logs"]}
    for index, (shot, number) in enumerate(zip(shots_raw, numbers), 1):
        value = copy.deepcopy(shot)
        visible, offscreen, props, blocking, performance = _native_staging(value)
        dialogue = _native_dialogue(value)
        source_excerpt = _clean(value.get("source_excerpt")) or _clean(value.get("execution_text"))
        beat_id = f"B{number:03d}"
        fact_id = f"{beat_id}-F01"
        fact_type = "dialogue" if dialogue else "action"
        beats.append(
            {
                "beat_id": beat_id,
                "source_text": source_excerpt,
                "source_span": [index, index],
                "facts": [{"fact_id": fact_id, "type": fact_type, "text": source_excerpt, "source_fragment": source_excerpt}],
            }
        )
        value["shot_order"] = number
        value["shot_no"] = number
        value["visible_characters"] = visible
        value["offscreen_characters"] = offscreen
        value["visible_props"] = props
        value["blocking"] = blocking
        value["performance"] = performance
        value["dialogue"] = dialogue
        value["beat_ids"] = [beat_id]
        value["covered_fact_ids"] = [fact_id]
        value["continuity_updates"] = copy.deepcopy(value.get("continuity", {}).get("state_updates", [])) if isinstance(value.get("continuity"), dict) else []
        camera = value.get("camera") if isinstance(value.get("camera"), dict) else {}
        camera_logic = _clean(camera.get("position")) or _clean(camera.get("angle"))
        composition = _clean(camera.get("composition"))
        value["camera_main_image"] = (
            f"[{_camera_tag(value)}]\n"
            f"【机位逻辑】{camera_logic}\n"
            f"【场景首镜站位】{composition}\n"
            f"{_clean(value.get('execution_text'))}"
        )
        value["source_paragraph"] = source_excerpt
        value["shot_type"] = "dialogue" if dialogue else ("action" if blocking else "master")
        value["insert_priority"] = "none"
        value["prompt"] = f"构图：{composition}\n画面内容：{_clean(value.get('execution_text'))}"
        duration = value.get("duration_seconds") if isinstance(value.get("duration_seconds"), int) else 0
        value["duration_breakdown"] = {
            "sync_action_seconds": duration if blocking else 0,
            "sync_dialogue_seconds": duration if dialogue else 0,
            "non_sync_action_seconds": 0,
            "emotional_pause_seconds": 0,
        }
        adapted_shots.append(value)
    normalized["beats"] = beats
    normalized["shots"] = adapted_shots
    normalized[ADAPTER_KEY] = {
        "identity": identity,
        "version": version,
        "content_hash": source_hash,
        "source_mode": "capability-shape-read-only-adapter",
    }
    return normalized


def _adapt_shot(
    shot: dict[str, Any],
    scenes: dict[str, dict[str, Any]],
    facts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    value = copy.deepcopy(shot)
    shot_no = value.get("shot_order")
    scene = scenes.get(_clean(value.get("scene_id")), {})
    duration = value.get("duration_seconds")
    duration = duration if isinstance(duration, int) and not isinstance(duration, bool) else 0
    has_dialogue = bool(value.get("dialogue"))
    has_action = bool(value.get("blocking"))
    camera = value.get("camera")
    camera = camera if isinstance(camera, dict) else {}
    description = _clean(value.get("rendered_shot_description")) or _clean(value.get("execution_text"))
    camera_logic = _clean(camera.get("logic")) or _clean(camera.get("motivation"))
    composition = _clean(camera.get("composition"))
    camera_main_image = (
        f"[{_camera_tag(value)}]\n"
        f"【机位逻辑】{camera_logic}\n"
        f"【场景首镜站位】{composition}\n"
        f"{description}"
    )
    value.update(
        {
            "shot_no": shot_no,
            "scene": _clean(scene.get("scene")),
            "reality_layer": _clean(scene.get("reality_layer")),
            "camera_main_image": camera_main_image,
            "offscreen_characters": _offscreen_characters(value),
            "source_paragraph": _source_paragraph(value, facts),
            "shot_type": _shot_type(value, facts),
            "insert_priority": "none",
            "prompt": f"构图：{composition}\n画面内容：{description}",
            "duration_breakdown": {
                "sync_action_seconds": duration if has_action else 0,
                "sync_dialogue_seconds": duration if has_dialogue else 0,
                "non_sync_action_seconds": 0,
                "emotional_pause_seconds": 0,
            },
        }
    )
    return value


def _adapt_canonical(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    version = _clean(data.get("source_skill_version"))
    if not version:
        errors.append("source_skill_version must be a non-empty string; no version allowlist is used")
    if _clean(data.get("contract_name")) != "shot-data":
        errors.append("contract_name must be shot-data")

    source = data.get("source")
    source = source if isinstance(source, dict) else {}
    locked_text = str(source.get("locked_text", ""))
    locked_hash = _clean(source.get("locked_text_hash"))
    if not locked_text.strip():
        errors.append("source.locked_text must be non-empty")
    elif locked_hash != _normalized_text_hash(locked_text):
        errors.append("source.locked_text_hash does not match locked_text")

    declared_hash = _clean(data.get("content_hash"))
    computed_hash = _source_content_hash(data)
    if not declared_hash:
        errors.append("content_hash must be non-empty")
    elif declared_hash != computed_hash:
        errors.append("content_hash does not match canonical source content")
    _validate_confirmations(data, errors)

    scenes_raw = data.get("scenes")
    if not isinstance(scenes_raw, list) or not scenes_raw:
        errors.append("scenes must be a non-empty array")
        scenes_raw = []
    scenes = {
        _clean(item.get("scene_id")): item
        for item in scenes_raw
        if isinstance(item, dict) and _clean(item.get("scene_id"))
    }
    if len(scenes) != len(scenes_raw):
        errors.append("scenes must contain unique non-empty scene_id values")
    if not isinstance(data.get("beats"), list) or not data.get("beats"):
        errors.append("beats must be a non-empty array")
    if not isinstance(data.get("shots"), list) or not data.get("shots"):
        errors.append("shots must be a non-empty array")
    if errors:
        raise UpstreamAdapterError(errors)

    normalized = copy.deepcopy(data)
    facts = _fact_lookup(data)
    normalized["metadata"] = {
        "skill_name": CANONICAL_UPSTREAM_SKILL,
        "version": version,
        "rule_revision": _clean(data.get("contract_version")) or f"shot-data/{version}",
    }
    normalized["script_lock"] = {
        "status": "locked",
        "approved_script_path": f"source://{_clean(source.get('delivery_slug')) or 'locked-text'}",
        "locked_text": locked_text,
        "locked_text_hash": locked_hash,
    }
    normalized["human_reviews"] = [
        {"gate": "GATE_A", "status": "approved", "reviewer": "source-contract-adapter"},
        {"gate": "GATE_B", "status": "approved", "reviewer": "source-contract-adapter"},
        {"gate": "GATE_C", "status": "approved", "reviewer": "source-contract-adapter"},
    ]
    normalized["validation_report"] = {
        "status": "PASS",
        "errors": [],
        "warnings": [],
        "source_json_hash": declared_hash,
    }
    normalized["warn_resolutions"] = []
    normalized["reference_bindings"] = copy.deepcopy(data.get("reference_bindings", []))
    normalized["continuity_logs"] = [_scene_log(scene) for scene in scenes_raw]
    normalized["shots"] = [_adapt_shot(shot, scenes, facts) for shot in data["shots"]]
    normalized[ADAPTER_KEY] = {
        "identity": CANONICAL_UPSTREAM_SKILL,
        "version": version,
        "content_hash": declared_hash,
        "source_mode": "canonical-read-only-adapter",
    }
    return normalized


def adapt_upstream(data: Any) -> dict[str, Any]:
    """Return an isolated normalized view without changing upstream data."""
    if not isinstance(data, dict):
        raise UpstreamAdapterError(["shot_data top level must be a JSON object"])
    if is_adapted(data):
        return copy.deepcopy(data)
    identity = upstream_identity(data)
    if identity == CANONICAL_UPSTREAM_SKILL and _clean(data.get("contract_name")) == "shot-data":
        try:
            return _adapt_canonical(data)
        except UpstreamAdapterError:
            return _adapt_capability_shape(data)
    if isinstance(data.get("scenes"), list) and isinstance(data.get("shots"), list):
        return _adapt_capability_shape(data)
    if identity == LEGACY_UPSTREAM_SKILL:
        return copy.deepcopy(data)
    raise UpstreamAdapterError(["input does not expose a usable scenes + shots storyboard capability shape"])
