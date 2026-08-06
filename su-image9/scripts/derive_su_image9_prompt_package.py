#!/usr/bin/env python3
"""Derive a deterministic su-image9 v2.1.2 prompt package from signed shot_data."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

import semantic_audit


VERSION = "2.1.2"
SCHEMA_VERSION = "2.1"
UPSTREAM_SKILL = "su-fenjingskill-zh"
PAGE_SIZE = 9

EXIT_PASS = 0
EXIT_REVIEW_REQUIRED = 1
EXIT_CONTRACT_FAIL = 2
EXIT_TOOL_ERROR = 3

PAGE_MODE = "single_scene_single_reality_layer"
COMPLETION_SOURCE_ONLY = "source_only"
COMPLETION_DERIVED_ANGLE = "derived_angle"

CANON_MARKERS = (
    "HARD_PHRASES",
    "SYSTEM_STYLE_LAYER",
    "GEOMETRY_BLUEPRINT",
    "NEGATIVE_CONSTRAINTS",
)

AUTO_WHITELIST_WARNING_TOKENS = (
    "reference missing",
    "[reference missing]",
    "[合理补足]",
    "节奏",
    "cut/min",
    "短镜比例",
)

TRANSITION_SHOT_TYPES = {"transition", "black", "blackout", "audio", "sound_only"}
TRANSITION_CAMERA_TERMS = ("黑场", "纯声音", "纯音", "black frame", "blackout", "sound only", "audio only")
CLOSE_CAMERA_TERMS = ("特写", "大特写", "近景", "close-up", "close up", "extreme close", "insert", "插入")
ANCHOR_CAMERA_TERMS = ("大全景", "大远景", "全景", "远景", "wide", "full", "master", "establishing")

VEHICLE_TERMS = (
    "车辆",
    "汽车",
    "轿车",
    "卡车",
    "货车",
    "摩托",
    "自行车",
    "巴士",
    "公交",
    "列车",
    "火车",
)
ENGLISH_VEHICLE_TERMS = ("vehicle", "car", "truck", "motorcycle", "bicycle", "bus", "train")

# Narrative-driven derived angle specs. Each tuple: (key, drawn_tag_english, composition_task_english, rationale_chinese)
BASE_ANGLE_SPECS: tuple[tuple[str, str, str, str], ...] = (
    (
        "same_axis_wider",
        "same-axis wider composition",
        "Use a wider composition on the established side of the axis, revealing only registered geometry.",
        "同轴更宽，展示已登记的空间边界与固定物，不改变人物关系。",
    ),
    (
        "same_axis_tighter",
        "same-axis tighter composition",
        "Use a tighter composition on the same axis without advancing the action or emotional result.",
        "同轴更紧，压缩到核心人物或动作，不推进剧情。",
    ),
    (
        "same_side_three_quarter",
        "same-side three-quarter view",
        "Use a three-quarter view from the established side of the axis while preserving eyelines and positions.",
        "同侧三分之四角度，保留眼线和画面左右关系。",
    ),
    (
        "same_side_profile",
        "same-side profile view",
        "Use a profile view from the established side of the axis without reversing screen direction.",
        "同侧侧面，强调运动方向或空间深度，不跨轴。",
    ),
    (
        "high_angle",
        "same-side high angle",
        "Use a restrained high angle from the established side, preserving the identical action state and geometry.",
        "同侧高机位，轻微俯视以展现场面关系，不改变动作状态。",
    ),
    (
        "low_angle",
        "same-side low angle",
        "Use a restrained low angle from the established side, preserving the identical action state and geometry.",
        "同侧低机位，轻微仰视以强调人物存在感，不改变动作状态。",
    ),
    (
        "over_shoulder",
        "same-side over-shoulder view",
        "Use an over-shoulder view only between the already visible characters; preserve eyelines and screen sides.",
        "双人过肩，保留说者与听者的空间关系和视线方向。",
    ),
    (
        "prop_insert",
        "registered-prop insert",
        "Use an insert of an already visible registered prop without changing its owner, position, state, or action stage.",
        "已登记道具插入，聚焦道具状态或持手，不新增剧情事实。",
    ),
    (
        "speaker_close_up",
        "speaker close-up",
        "Isolate the speaking character on the established side of the axis; keep the addressee off-screen or only partially visible.",
        "说话者近景，保留台词落点时的表情与语气线索。",
    ),
    (
        "listener_reaction",
        "listener reaction close-up",
        "Isolate the listening character on the established side of the axis; show reaction without advancing the dialogue fact.",
        "听者反应近景，捕捉对话中的情绪反馈，不推进对白事实。",
    ),
    (
        "action_start",
        "action start moment",
        "Freeze the representative instant at the start of the action progression, before the main movement begins.",
        "动作起点瞬间，保留动作开始前的代表性姿态。",
    ),
    (
        "action_process",
        "action process moment",
        "Freeze the representative instant in the middle of the action progression, showing clear movement direction.",
        "动作过程瞬间，展示明确的方向和动势，但不到达终点。",
    ),
    (
        "action_end",
        "action end moment",
        "Freeze the representative instant at the end of the action progression, showing the result posture without adding emotional aftermath.",
        "动作终点瞬间，保留结果姿态，不添加情绪后果。",
    ),
    (
        "subjective_hint",
        "subjective-framing hint",
        "Use a slightly de-stabilized or partial framing within the same monochrome graphite style to suggest a non-reality layer; do not add color, haze, or dream effects.",
        "非现实层的受控主观构图提示，保持黑白石墨、不使用彩色或雾效。",
    ),
)

ANGLE_INDEX = {spec[0]: spec for spec in BASE_ANGLE_SPECS}


class ContractViolation(Exception):
    """The signed source does not satisfy the public 2.1 input contract."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class DerivationReview(Exception):
    """The source is valid, but a page cannot be derived without human judgment."""

    def __init__(self, code: str, message: str, page: str = "PACKAGE"):
        super().__init__(message)
        self.code = code
        self.message = message
        self.page = page

    def as_reason(self) -> dict[str, str]:
        return {"code": self.code, "page": self.page, "message": self.message}


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(value or ""))).strip()


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def upstream_provenance(data: dict[str, Any]) -> tuple[str, str]:
    """Return the declared upstream version and rule revision verbatim."""

    metadata = as_dict(data.get("metadata"))
    return clean_text(metadata.get("version")), clean_text(metadata.get("rule_revision"))


def normalized_text_list(value: Any) -> list[str]:
    """Normalize string or legacy object arrays without coercing booleans/scalars."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = clean_text(item)
        elif isinstance(item, dict):
            text = clean_text(item.get("name"))
        else:
            continue
        if text and text not in result:
            result.append(text)
    return result


def entity_descriptions(value: Any, *, character: bool = False) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            description = clean_text(item)
        elif isinstance(item, dict):
            name = clean_text(item.get("name"))
            details: list[str] = []
            for field in ("position", "facing" if character else "", "state", "owner", "presence"):
                if not field:
                    continue
                field_value = clean_text(item.get(field))
                if field_value:
                    details.append(f"{field} {field_value}")
            description = f"{name}: {', '.join(details)}" if name and details else name
        else:
            description = ""
        if description and description not in result:
            result.append(description)
    return result


def canonical_json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_data_hash(data: dict[str, Any]) -> str:
    value = copy.deepcopy(data)
    value.pop("validation_report", None)
    return canonical_json_hash(value)


def upstream_gate_content_hash(data: dict[str, Any]) -> str:
    """Hash scope used by current Gate-based upstream contracts."""

    value = copy.deepcopy(data)
    value.pop("validation_report", None)
    value.pop("human_reviews", None)
    metadata = as_dict(value.get("metadata"))
    if metadata:
        metadata.pop("revision_log", None)
    return canonical_json_hash(value)


def source_file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canon_file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def warning_id(message: str) -> str:
    return "W-" + hashlib.sha1(clean_text(message).encode("utf-8")).hexdigest()[:12]


def warning_digest(report: dict[str, Any]) -> str:
    warnings = sorted(clean_text(item) for item in as_list(report.get("warnings")))
    payload = json.dumps(warnings, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def script_text_hash(value: str) -> str:
    fingerprint = re.sub(r"\s+", "", clean_text(value))
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


def normalized_script_text_hash(value: str) -> str:
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_hash_candidates(data: dict[str, Any]) -> set[str]:
    return {canonical_data_hash(data), upstream_gate_content_hash(data)}


def script_hash_candidates(value: str) -> set[str]:
    return {script_text_hash(value), normalized_script_text_hash(value)}


def is_auto_whitelist_warning(message: str) -> bool:
    return any(token in message for token in AUTO_WHITELIST_WARNING_TOKENS)


def approved_gate(data: dict[str, Any], gate: str) -> bool:
    return any(
        isinstance(item, dict)
        and clean_text(item.get("gate")) == gate
        and clean_text(item.get("status")) == "approved"
        and bool(clean_text(item.get("reviewer")))
        for item in as_list(data.get("human_reviews"))
    )


def camera_tag(shot: dict[str, Any]) -> str:
    match = re.match(r"\s*\[([^\]]+)\]", str(shot.get("camera_main_image", "")))
    return clean_text(match.group(1)) if match else ""


def valid_name_array(value: Any, *, allow_objects: bool) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if isinstance(item, str):
            if not clean_text(item):
                return False
        elif allow_objects and isinstance(item, dict):
            if not clean_text(item.get("name")):
                return False
        else:
            return False
    return True


def reference_binding_schema_errors(data: dict[str, Any]) -> list[str]:
    raw = data.get("reference_bindings", [])
    errors: list[str] = []
    if not isinstance(raw, list):
        return ["reference_bindings must be an array"]
    allowed_types = {"character", "prop", "space", "panel"}
    allowed_attributes = {"identity", "shape", "ownership", "fixed_geometry"}
    seen_assets: set[str] = set()
    for index, item in enumerate(raw):
        label = f"reference_bindings[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        expected_keys = {"asset_id", "asset_sha256", "binding_type", "target_id", "locked_attributes", "status"}
        if set(item) != expected_keys:
            errors.append(f"{label} must contain exactly {sorted(expected_keys)}")
            continue
        asset_id = clean_text(item.get("asset_id"))
        asset_sha256 = clean_text(item.get("asset_sha256")).lower()
        binding_type = clean_text(item.get("binding_type")).lower()
        target_id = clean_text(item.get("target_id"))
        status = clean_text(item.get("status")).lower()
        locked_attributes = item.get("locked_attributes")
        if status != "bound":
            errors.append(f"{label}.status must be bound; use an empty array for reference state none")
        if not asset_id or asset_id in seen_assets:
            errors.append(f"{label}.asset_id must be non-empty and unique")
        if not re.fullmatch(r"[0-9a-f]{64}", asset_sha256):
            errors.append(f"{label}.asset_sha256 must be a lowercase SHA-256")
        if binding_type not in allowed_types or not target_id:
            errors.append(f"{label} must bind to one explicit character, prop, space, or panel target")
        if not valid_name_array(locked_attributes, allow_objects=False) or not locked_attributes:
            errors.append(f"{label}.locked_attributes must be a non-empty string array")
        normalized_attributes = normalized_text_list(locked_attributes) if isinstance(locked_attributes, list) else []
        if any(attribute not in allowed_attributes for attribute in normalized_attributes):
            errors.append(f"{label}.locked_attributes contains an unsupported attribute")
        if asset_id:
            seen_assets.add(asset_id)
    return errors


def validate_reference_bindings(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized bound references; an empty list means reference state none."""
    schema_errors = reference_binding_schema_errors(data)
    if schema_errors:
        raise ContractViolation(schema_errors)
    raw = data.get("reference_bindings", [])
    normalized: list[dict[str, Any]] = []
    for item in raw:
        normalized.append(
            {
                "asset_id": clean_text(item.get("asset_id")),
                "asset_sha256": clean_text(item.get("asset_sha256")).lower(),
                "binding_type": clean_text(item.get("binding_type")).lower(),
                "target_id": clean_text(item.get("target_id")),
                "locked_attributes": normalized_text_list(item.get("locked_attributes")),
                "status": "bound",
            }
        )
    supplied_assets = data.get("reference_assets", data.get("assets", []))
    if isinstance(supplied_assets, list) and supplied_assets and not normalized:
        raise DerivationReview("F-ASSET", "reference assets were supplied without an explicit bound target")
    return normalized


def scene_logs(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        clean_text(item.get("scene_id")): item
        for item in as_list(data.get("continuity_logs"))
        if isinstance(item, dict) and clean_text(item.get("scene_id"))
    }


def reality_layer(shot: dict[str, Any], logs: dict[str, dict[str, Any]]) -> str:
    direct = clean_text(shot.get("reality_layer"))
    if direct:
        return direct
    return clean_text(logs.get(clean_text(shot.get("scene_id")), {}).get("reality_layer"))


def validate_source_contract(data: Any) -> list[str]:
    """Validate the signed upstream contract without repairing or coercing it."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["shot_data top level must be a JSON object"]

    metadata = as_dict(data.get("metadata"))
    if metadata.get("skill_name") != UPSTREAM_SKILL:
        errors.append(f'metadata.skill_name must be "{UPSTREAM_SKILL}"')
    upstream_version = metadata.get("version")
    upstream_rule_revision = metadata.get("rule_revision")
    if not isinstance(upstream_version, str) or not clean_text(upstream_version):
        errors.append("metadata.version must be a non-empty string; any upstream version is accepted")
    if not isinstance(upstream_rule_revision, str) or not clean_text(upstream_rule_revision):
        errors.append("metadata.rule_revision must be a non-empty string; any upstream rule revision is accepted")

    lock = as_dict(data.get("script_lock"))
    if lock.get("status") != "locked":
        errors.append('script_lock.status must be "locked"')
    locked_text = str(lock.get("locked_text", "")).replace("\r\n", "\n").replace("\r", "\n")
    if not locked_text.strip():
        errors.append("script_lock.locked_text must contain the approved script")
    elif clean_text(lock.get("locked_text_hash")) not in script_hash_candidates(locked_text):
        errors.append("script_lock.locked_text_hash does not match a supported upstream text-hash contract")
    if not clean_text(lock.get("approved_script_path")):
        errors.append("script_lock.approved_script_path is required")
    for gate in ("GATE_A", "GATE_B", "GATE_C"):
        if not approved_gate(data, gate):
            errors.append(f"human_reviews must contain an approved {gate} record")
    errors.extend(reference_binding_schema_errors(data))

    report = as_dict(data.get("validation_report"))
    status = clean_text(report.get("status")).upper()
    if status not in {"PASS", "WARN"}:
        errors.append("validation_report.status must be PASS or WARN")
    supplied_hash = clean_text(report.get("source_json_hash"))
    expected_hashes = source_hash_candidates(data)
    if not supplied_hash:
        errors.append("validation_report.source_json_hash is required")
    elif supplied_hash not in expected_hashes:
        errors.append("validation_report.source_json_hash does not match a supported upstream content-hash contract")
    if as_list(report.get("errors")):
        errors.append("validation_report.errors must be empty")

    warnings = [clean_text(item) for item in as_list(report.get("warnings")) if clean_text(item)]
    if status == "PASS" and warnings:
        errors.append("PASS validation_report cannot contain warnings")
    if status == "WARN" and not warnings:
        errors.append("WARN validation_report must contain at least one warning")
    resolutions: dict[str, dict[str, Any]] = {}
    if not isinstance(data.get("warn_resolutions"), list):
        errors.append("warn_resolutions must be an array")
    for item in as_list(data.get("warn_resolutions")):
        if not isinstance(item, dict):
            errors.append("warn_resolutions entries must be objects")
            continue
        warn_id_value = clean_text(item.get("warn_id"))
        if not warn_id_value:
            errors.append("warn_resolutions.warn_id is required")
            continue
        if warn_id_value in resolutions:
            errors.append(f"duplicate warn_resolutions entry: {warn_id_value}")
        resolutions[warn_id_value] = item
    for warning in warnings:
        warn_id_value = warning_id(warning)
        resolution = resolutions.get(warn_id_value)
        if resolution is None:
            errors.append(f"warning {warn_id_value} has no warn_resolutions entry")
            continue
        resolved_by = clean_text(resolution.get("resolved_by"))
        if resolved_by not in {"human", "auto_whitelist"}:
            errors.append(f"warning {warn_id_value} has an invalid resolved_by value")
        elif resolved_by != "human" and not is_auto_whitelist_warning(warning):
            errors.append(f"warning {warn_id_value} is not whitelisted and must be resolved by human")
        if clean_text(resolution.get("resolution")) not in {"keep", "revise", "accepted_without_change"}:
            errors.append(f"warning {warn_id_value} has an invalid resolution")
        if not clean_text(resolution.get("note")):
            errors.append(f"warning {warn_id_value} resolution note is required")

    raw_logs = data.get("continuity_logs")
    if not isinstance(raw_logs, list):
        errors.append("continuity_logs must be an array")
        raw_logs = []
    raw_scene_ids = [clean_text(item.get("scene_id")) for item in raw_logs if isinstance(item, dict)]
    if len([item for item in raw_scene_ids if item]) != len(set(item for item in raw_scene_ids if item)):
        errors.append("continuity_logs.scene_id values must be unique")
    logs = scene_logs(data)
    if not logs:
        errors.append("continuity_logs must contain scene_id keyed records")
    for scene_id, log in logs.items():
        for field in ("fixed_objects", "characters", "props"):
            if field in log and not valid_name_array(log.get(field), allow_objects=True):
                errors.append(f"continuity_logs.{scene_id}.{field} must contain only strings or named objects")
    beats = data.get("beats")
    if not isinstance(beats, list) or not beats:
        errors.append("beats must be a non-empty array")
    else:
        for beat_index, beat in enumerate(beats):
            beat_label = f"beats[{beat_index}]"
            if not isinstance(beat, dict):
                errors.append(f"{beat_label} must be an object")
                continue
            if not clean_text(beat.get("beat_id")):
                errors.append(f"{beat_label}.beat_id is required")
            facts = beat.get("facts")
            if not isinstance(facts, list) or not facts:
                errors.append(f"{beat_label}.facts must be a non-empty array")
                continue
            for fact_index, fact in enumerate(facts):
                fact_label = f"{beat_label}.facts[{fact_index}]"
                if not isinstance(fact, dict):
                    errors.append(f"{fact_label} must be an object")
                    continue
                if not clean_text(fact.get("fact_id")) or not clean_text(fact.get("type")):
                    errors.append(f"{fact_label}.fact_id and type are required")
    shots = data.get("shots")
    if not isinstance(shots, list) or not shots:
        errors.append("shots must be a non-empty array")
        return errors
    shot_numbers: list[int] = []
    for index, shot in enumerate(shots, 1):
        label = f"shots[{index - 1}]"
        if not isinstance(shot, dict):
            errors.append(f"{label} must be an object")
            continue
        shot_no = shot.get("shot_no")
        if isinstance(shot_no, bool) or not isinstance(shot_no, int) or shot_no < 1:
            errors.append(f"{label}.shot_no must be a positive integer")
        else:
            shot_numbers.append(shot_no)
        scene_id = clean_text(shot.get("scene_id"))
        if not scene_id:
            errors.append(f"{label}.scene_id is required")
        elif scene_id not in logs:
            errors.append(f"{label}.scene_id {scene_id} is not registered in continuity_logs")
        elif not reality_layer(shot, logs):
            errors.append(f"{label} has no reality_layer in the shot or continuity log")
        if not camera_tag(shot):
            errors.append(f"{label}.camera_main_image must begin with a camera tag")
        for field in ("beat_ids", "covered_fact_ids"):
            values = shot.get(field)
            if not valid_name_array(values, allow_objects=False) or not values:
                errors.append(f"{label}.{field} must be a non-empty string array")
        for field in ("visible_characters", "offscreen_characters", "visible_props"):
            if not valid_name_array(shot.get(field), allow_objects=True):
                errors.append(f"{label}.{field} must contain only strings or named objects")
        updates = shot.get("continuity_updates")
        if not isinstance(updates, list):
            errors.append(f"{label}.continuity_updates must be an array")
        else:
            for update_index, update in enumerate(updates):
                update_label = f"{label}.continuity_updates[{update_index}]"
                if not isinstance(update, dict):
                    errors.append(f"{update_label} must be an object")
                    continue
                for field in ("entity_type", "entity", "field", "from", "to"):
                    if not clean_text(update.get(field)):
                        errors.append(f"{update_label}.{field} is required")
                evidence = update.get("evidence_fact_ids")
                if not valid_name_array(evidence, allow_objects=False) or not evidence:
                    errors.append(f"{update_label}.evidence_fact_ids must be a non-empty string array")
    if shot_numbers != sorted(shot_numbers) or len(shot_numbers) != len(set(shot_numbers)):
        errors.append("shots must use unique, strictly increasing shot_no values")
    return errors


def is_transition_shot(shot: dict[str, Any]) -> bool:
    shot_type = clean_text(shot.get("shot_type")).lower()
    camera = camera_tag(shot).lower()
    return shot_type in TRANSITION_SHOT_TYPES or any(term in camera for term in TRANSITION_CAMERA_TERMS)


def page_chunks(
    shots: list[dict[str, Any]],
    logs: dict[str, dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Split on scene, reality layer, nine-source capacity, and visual transitions."""
    pages: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_key: tuple[str, str] | None = None
    for shot in shots:
        key = (clean_text(shot.get("scene_id")), reality_layer(shot, logs))
        if current and (key != current_key or len(current) == PAGE_SIZE):
            pages.append(current)
            current = []
        current.append(shot)
        current_key = key
        if is_transition_shot(shot):
            pages.append(current)
            current = []
            current_key = None
    if current:
        pages.append(current)
    return pages


def normalize_state_items(value: Any) -> list[Any]:
    result: list[Any] = []
    for item in as_list(value):
        if isinstance(item, str):
            normalized: Any = clean_text(item)
        elif isinstance(item, dict):
            normalized = {
                clean_text(key): clean_text(field_value) if isinstance(field_value, str) else copy.deepcopy(field_value)
                for key, field_value in item.items()
                if clean_text(key)
            }
        else:
            continue
        if normalized not in result:
            result.append(normalized)
    return sorted(result, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def normalized_continuity_updates(shot: dict[str, Any]) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for item in as_list(shot.get("continuity_updates")):
        if not isinstance(item, dict):
            continue
        normalized = {
            "entity_type": clean_text(item.get("entity_type")),
            "entity": clean_text(item.get("entity")),
            "field": clean_text(item.get("field")),
            "from": clean_text(item.get("from")),
            "to": clean_text(item.get("to")),
            "evidence_fact_ids": normalized_text_list(item.get("evidence_fact_ids")),
        }
        updates.append(normalized)
    return sorted(updates, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def continuity_state_hash(shot: dict[str, Any], log: dict[str, Any], layer: str) -> str:
    """Hash only source facts and registered continuity state, never the derived angle."""
    payload = {
        "scene_id": clean_text(shot.get("scene_id")),
        "reality_layer": layer,
        "beat_ids": normalized_text_list(shot.get("beat_ids")),
        "covered_fact_ids": normalized_text_list(shot.get("covered_fact_ids")),
        "visible_characters": normalized_text_list(shot.get("visible_characters")),
        "offscreen_characters": normalized_text_list(shot.get("offscreen_characters")),
        "visible_props": normalized_text_list(shot.get("visible_props")),
        "continuity_updates": normalized_continuity_updates(shot),
        "scene_state": {
            "spatial_axis": clean_text(log.get("spatial_axis")),
            "fixed_objects": normalize_state_items(log.get("fixed_objects")),
            "characters": normalize_state_items(log.get("characters")),
            "props": normalize_state_items(log.get("props")),
        },
    }
    return canonical_json_hash(payload)


def transition_updates(shot: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in normalized_continuity_updates(shot) if item["field"].lower() in {"position", "facing"}]


def distance_stage_locks(chunk: list[dict[str, Any]]) -> dict[int, str]:
    """Build pre/endpoint locks only from explicit position or facing transitions."""
    parts: dict[int, list[str]] = {int(shot["shot_no"]): [] for shot in chunk}
    for index, shot in enumerate(chunk):
        updates = transition_updates(shot)
        if not updates:
            continue
        endpoint_parts: list[str] = []
        pre_parts: list[str] = []
        for update in updates:
            entity = update["entity"] or update["entity_type"] or "entity"
            field = update["field"]
            evidence = ", ".join(update["evidence_fact_ids"]) or "registered continuity evidence"
            endpoint_parts.append(f"{entity}.{field} {update['from']} -> {update['to']} (evidence: {evidence})")
            pre_parts.append(f"keep {entity}.{field} at {update['from']} before C{int(shot['shot_no']):03d}")
        parts[int(shot["shot_no"])].append("endpoint-transition: " + "; ".join(endpoint_parts))
        if index > 0:
            previous_no = int(chunk[index - 1]["shot_no"])
            parts[previous_no].append("pre-transition: " + "; ".join(pre_parts))
    return {shot_no: "; ".join(values) if values else "none" for shot_no, values in parts.items()}


def distance_stage_locks_for_sequence(
    shots: list[dict[str, Any]],
    logs: dict[str, dict[str, Any]],
) -> dict[int, str]:
    """Keep transition locks continuous across page-capacity splits, but not across time-space boundaries."""
    result: dict[int, str] = {}
    group: list[dict[str, Any]] = []
    group_key: tuple[str, str] | None = None

    def flush() -> None:
        nonlocal group, group_key
        if group:
            result.update(distance_stage_locks(group))
        group = []
        group_key = None

    for shot in shots:
        key = (clean_text(shot.get("scene_id")), reality_layer(shot, logs))
        if group and key != group_key:
            flush()
        group.append(shot)
        group_key = key
        if is_transition_shot(shot):
            flush()
    flush()
    return result


def is_spatial_anchor(shot: dict[str, Any], log: dict[str, Any]) -> bool:
    if is_transition_shot(shot):
        return False
    tag = camera_tag(shot).lower()
    if any(term in tag for term in CLOSE_CAMERA_TERMS):
        return False
    camera_text = str(shot.get("camera_main_image", ""))
    has_structured_placement = "【场景首镜站位】" in camera_text or "【站位位移】" in camera_text
    has_registered_axis = bool(clean_text(log.get("spatial_axis")))
    has_visible_subject = bool(normalized_text_list(shot.get("visible_characters")))
    has_camera_side = "【机位逻辑】" in camera_text
    has_registered_boundary = bool(
        entity_descriptions(log.get("fixed_objects"))
        or entity_descriptions(log.get("characters"), character=True)
        or entity_descriptions(log.get("props"))
    )
    camera_supports_space = any(term in tag for term in ANCHOR_CAMERA_TERMS) or has_structured_placement
    return (
        has_registered_axis
        and has_registered_boundary
        and has_camera_side
        and has_visible_subject
        and camera_supports_space
    )


def shot_summary(shot: dict[str, Any]) -> str:
    prompt = str(shot.get("prompt", ""))
    def field(label: str) -> str:
        match = re.search(rf"{re.escape(label)}：(.+?)(?:\n|$)", prompt)
        return clean_text(match.group(1)) if match else ""

    content = field("画面内容") or clean_text(shot.get("source_paragraph"))
    composition = field("构图")
    movement = field("运镜手法")
    items: list[str] = []
    if composition:
        items.append(f"Composition: {composition}")
    if movement:
        items.append(f"Camera motion idea: {movement}")
    if content:
        items.append(f"Visible action state: {content}")
    return "; ".join(items) or f"Preserve the visible state of source shot C{int(shot['shot_no']):03d}."


def prop_fact_ids(data: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for beat in as_list(data.get("beats")):
        if not isinstance(beat, dict):
            continue
        for fact in as_list(beat.get("facts")):
            if not isinstance(fact, dict):
                continue
            if clean_text(fact.get("type")).lower() == "prop" or clean_text(fact.get("cut_category")).lower() == "prop":
                fact_id = clean_text(fact.get("fact_id"))
                if fact_id:
                    result.add(fact_id)
    return result


def has_dialogue_fact(shot: dict[str, Any], data: dict[str, Any]) -> bool:
    covered = set(normalized_text_list(shot.get("covered_fact_ids")))
    for beat in as_list(data.get("beats")):
        if not isinstance(beat, dict):
            continue
        for fact in as_list(beat.get("facts")):
            if not isinstance(fact, dict):
                continue
            if clean_text(fact.get("fact_id")) in covered and clean_text(fact.get("type")).lower() == "dialogue":
                return True
    return False


def has_action_fact(shot: dict[str, Any], data: dict[str, Any]) -> bool:
    covered = set(normalized_text_list(shot.get("covered_fact_ids")))
    for beat in as_list(data.get("beats")):
        if not isinstance(beat, dict):
            continue
        for fact in as_list(beat.get("facts")):
            if not isinstance(fact, dict):
                continue
            if clean_text(fact.get("fact_id")) in covered and clean_text(fact.get("type")).lower() in {"action", "position"}:
                return True
    return False


def has_prop_fact(shot: dict[str, Any], data: dict[str, Any]) -> bool:
    covered = set(normalized_text_list(shot.get("covered_fact_ids")))
    for beat in as_list(data.get("beats")):
        if not isinstance(beat, dict):
            continue
        for fact in as_list(beat.get("facts")):
            if not isinstance(fact, dict):
                continue
            if clean_text(fact.get("fact_id")) in covered and clean_text(fact.get("type")).lower() == "prop":
                return True
    return False


def narrative_angle_candidates(
    shot: dict[str, Any],
    data: dict[str, Any],
    layer: str,
    registered_prop_fact_ids: set[str] | None = None,
) -> list[tuple[str, str, str, str]]:
    """Return angle specs ordered by narrative relevance for this shot."""
    if is_transition_shot(shot):
        return []

    visible_characters = normalized_text_list(shot.get("visible_characters"))
    visible_props = normalized_text_list(shot.get("visible_props"))
    character_count = len(visible_characters)
    covered_facts = set(normalized_text_list(shot.get("covered_fact_ids")))
    has_prop = bool(visible_props) and bool(covered_facts.intersection(registered_prop_fact_ids or set()))
    insert_priority = clean_text(shot.get("insert_priority")).lower()
    wants_insert = insert_priority in {"must_have", "recommended"} and has_prop

    candidates: list[tuple[str, str, str, str]] = []

    # Dialogue-driven angles
    if has_dialogue_fact(shot, data) or clean_text(shot.get("shot_type")).lower() == "dialogue":
        if character_count >= 2:
            candidates.append(ANGLE_INDEX["over_shoulder"])
            candidates.append(ANGLE_INDEX["speaker_close_up"])
            candidates.append(ANGLE_INDEX["listener_reaction"])
        else:
            candidates.append(ANGLE_INDEX["same_axis_tighter"])

    # Action/position-driven angles
    if has_action_fact(shot, data) or clean_text(shot.get("shot_type")).lower() == "action":
        candidates.append(ANGLE_INDEX["action_start"])
        candidates.append(ANGLE_INDEX["action_process"])
        candidates.append(ANGLE_INDEX["action_end"])
        candidates.append(ANGLE_INDEX["same_side_profile"])

    # Prop-driven angles: include prop_insert whenever a visible prop is backed by a prop fact,
    # even if insert_priority is not explicitly set. Higher priority when insert_priority demands it.
    if has_prop:
        candidates.append(ANGLE_INDEX["prop_insert"])
    if wants_insert:
        candidates.append(ANGLE_INDEX["same_axis_tighter"])

    # Reality-layer hints
    if layer and layer != "现实":
        candidates.append(ANGLE_INDEX["subjective_hint"])

    # Fallback coverage by character count. We need at least 8 candidates for a single-source page.
    if character_count >= 2:
        for key in (
            "over_shoulder",
            "same_side_three_quarter",
            "same_axis_wider",
            "same_axis_tighter",
            "same_side_profile",
            "high_angle",
            "low_angle",
        ):
            if ANGLE_INDEX[key] not in candidates:
                candidates.append(ANGLE_INDEX[key])
    else:
        for key in (
            "same_axis_tighter",
            "same_side_three_quarter",
            "same_axis_wider",
            "high_angle",
            "low_angle",
            "same_side_profile",
        ):
            if ANGLE_INDEX[key] not in candidates:
                candidates.append(ANGLE_INDEX[key])

    # Prop insert is only legal when there is a visible prop and a prop fact
    final: list[tuple[str, str, str, str]] = []
    for spec in candidates:
        if spec[0] == "prop_insert" and not has_prop:
            continue
        if spec[0] in {"speaker_close_up", "listener_reaction"} and character_count < 1:
            continue
        if spec[0] == "over_shoulder" and character_count < 2:
            continue
        final.append(spec)

    return final


def allocate_derived_angles(
    chunk: list[dict[str, Any]],
    data: dict[str, Any],
    logs: dict[str, dict[str, Any]],
    registered_prop_fact_ids: set[str] | None = None,
) -> dict[int, list[tuple[str, str, str, str]]]:
    needed = PAGE_SIZE - len(chunk)
    allocations: dict[int, list[tuple[str, str, str, str]]] = {int(shot["shot_no"]): [] for shot in chunk}
    candidates = {
        int(shot["shot_no"]): narrative_angle_candidates(shot, data, reality_layer(shot, logs), registered_prop_fact_ids)
        for shot in chunk
    }
    candidate_index = 0
    while needed > 0:
        progress = False
        for shot in chunk:
            shot_no = int(shot["shot_no"])
            available = candidates[shot_no]
            if candidate_index >= len(available):
                continue
            allocations[shot_no].append(available[candidate_index])
            needed -= 1
            progress = True
            if needed == 0:
                break
        if not progress:
            break
        candidate_index += 1
    if needed:
        raise DerivationReview(
            "F-SPARSE-COVERAGE",
            f"The page has {len(chunk)} source shots and lacks {needed} fact-preserving derived angles; do not invent story facts to fill nine panels.",
        )
    return allocations


def derive_render_visibility(
    source_visible_characters: list[str],
    source_visible_props: list[str],
    spec_key: str,
) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """Return (primary_focus, must_show, may_show, must_not_show, derived_visible) for a derived panel."""
    all_entities = source_visible_characters + source_visible_props
    if not all_entities:
        return [], [], [], [], [], []

    primary_focus: list[str] = []
    must_show: list[str] = []
    may_show: list[str] = []
    must_not_show: list[str] = []
    derived_visible: list[str] = []

    if spec_key == "prop_insert" and source_visible_props:
        primary_focus = [source_visible_props[0]]
        must_show = [source_visible_props[0]]
        may_show = source_visible_characters[:1]
        must_not_show = source_visible_characters[1:] if len(source_visible_characters) > 1 else []
        derived_visible = [source_visible_props[0]]
    elif spec_key == "speaker_close_up" and source_visible_characters:
        primary_focus = [source_visible_characters[0]]
        must_show = [source_visible_characters[0]]
        may_show = []
        must_not_show = source_visible_characters[1:]
        derived_visible = [source_visible_characters[0]]
    elif spec_key == "listener_reaction" and len(source_visible_characters) >= 2:
        primary_focus = [source_visible_characters[1]]
        must_show = [source_visible_characters[1]]
        may_show = []
        must_not_show = [source_visible_characters[0]]
        derived_visible = [source_visible_characters[1]]
    elif spec_key in {"action_start", "action_process", "action_end"} and source_visible_characters:
        primary_focus = source_visible_characters[:1]
        must_show = source_visible_characters[:1]
        may_show = source_visible_characters[1:] + source_visible_props
        must_not_show = []
        derived_visible = source_visible_characters[:1]
    elif spec_key == "over_shoulder" and len(source_visible_characters) >= 2:
        primary_focus = source_visible_characters[:2]
        must_show = source_visible_characters[:2]
        may_show = source_visible_props
        must_not_show = source_visible_characters[2:]
        derived_visible = source_visible_characters[:2]
    elif spec_key == "subjective_hint" and source_visible_characters:
        primary_focus = source_visible_characters[:1]
        must_show = source_visible_characters[:1]
        may_show = source_visible_props + source_visible_characters[1:]
        must_not_show = []
        derived_visible = source_visible_characters[:1]
    else:
        primary_focus = source_visible_characters[:1] if source_visible_characters else source_visible_props[:1]
        must_show = source_visible_characters[:1] if source_visible_characters else []
        may_show = source_visible_characters[1:] + source_visible_props
        must_not_show = []
        derived_visible = source_visible_characters[:1] if source_visible_characters else source_visible_props[:1]

    return primary_focus, must_show, may_show, must_not_show, derived_visible


def source_panel(
    shot: dict[str, Any],
    panel_number: int,
    log: dict[str, Any],
    layer: str,
    distance_lock: str,
) -> dict[str, Any]:
    shot_no = int(shot["shot_no"])
    tag = camera_tag(shot)
    visible_characters = normalized_text_list(shot.get("visible_characters"))
    visible_props = normalized_text_list(shot.get("visible_props"))
    return {
        "panel": f"PANEL-{panel_number}",
        "panel_kind": "source",
        "source_shot": shot_no,
        "variant_suffix": None,
        "display_label": f"C{shot_no:03d}",
        "source_camera_tag": tag,
        "drawn_camera_tag": tag,
        "beat_ids": normalized_text_list(shot.get("beat_ids")),
        "covered_fact_ids": normalized_text_list(shot.get("covered_fact_ids")),
        "visible_characters": visible_characters,
        "offscreen_characters": normalized_text_list(shot.get("offscreen_characters")),
        "visible_props": visible_props,
        "continuity_state_hash": continuity_state_hash(shot, log, layer),
        "composition_task": shot_summary(shot),
        "distance_stage_lock": distance_lock,
        "fact_delta": "source",
        "primary_focus": visible_characters[:1] + visible_props[:1],
        "must_show": visible_characters + visible_props,
        "may_show": [],
        "must_not_show": normalized_text_list(shot.get("offscreen_characters")),
        "render_delta": "none",
        "story_delta": "none",
        "camera_rationale": "源镜头，保留导演原始构图与可见集合。",
    }


def derived_panel(
    source: dict[str, Any],
    panel_number: int,
    suffix: str,
    spec: tuple[str, str, str, str],
) -> dict[str, Any]:
    panel = copy.deepcopy(source)
    primary_focus, must_show, may_show, must_not_show, derived_visible = derive_render_visibility(
        source["visible_characters"],
        source["visible_props"],
        spec[0],
    )
    # Combine derived_visible back into characters/props based on source membership
    derived_characters = [name for name in derived_visible if name in source["visible_characters"]]
    derived_props = [name for name in derived_visible if name in source["visible_props"]]
    panel.update(
        {
            "panel": f"PANEL-{panel_number}",
            "panel_kind": "derived_angle",
            "variant_suffix": suffix,
            "display_label": f"C{int(source['source_shot']):03d}-{suffix}",
            "drawn_camera_tag": f"{spec[1]} derived from {source['source_camera_tag']}",
            "composition_task": f"{spec[2]} Preserve the source state exactly: {source['composition_task']}",
            "fact_delta": "none",
            "primary_focus": primary_focus,
            "must_show": must_show,
            "may_show": may_show,
            "must_not_show": must_not_show,
            "render_delta": "allowed",
            "story_delta": "none",
            "camera_rationale": spec[3],
        }
    )
    panel["visible_characters"] = derived_characters
    panel["visible_props"] = derived_props
    return panel


def build_page(
    page_number: int,
    chunk: list[dict[str, Any]],
    data: dict[str, Any],
    logs: dict[str, dict[str, Any]],
    registered_prop_fact_ids: set[str] | None = None,
    sequence_distance_locks: dict[int, str] | None = None,
) -> dict[str, Any]:
    page_id = f"PAGE-{page_number:02d}"
    scene_id = clean_text(chunk[0].get("scene_id"))
    layer = reality_layer(chunk[0], logs)
    if any(clean_text(shot.get("scene_id")) != scene_id or reality_layer(shot, logs) != layer for shot in chunk):
        raise ContractViolation([f"{page_id} mixes scene_id or reality_layer values"])
    log = logs[scene_id]
    anchor_shot = next((shot for shot in chunk if is_spatial_anchor(shot, log)), None)
    if anchor_shot is None:
        raise DerivationReview(
            "F-PAGE-ANCHOR",
            "No source shot on this page contains reliable structured spatial information; the original camera compositions cannot be changed to manufacture an anchor.",
            page_id,
        )
    allocations = allocate_derived_angles(chunk, data, logs, registered_prop_fact_ids)
    locks = sequence_distance_locks or distance_stage_locks(chunk)
    panels: list[dict[str, Any]] = []
    for shot in chunk:
        source = source_panel(shot, len(panels) + 1, log, layer, locks[int(shot["shot_no"])])
        panels.append(source)
        for variant_index, spec in enumerate(allocations[int(shot["shot_no"])], 1):
            suffix = chr(ord("A") + variant_index - 1)
            panels.append(derived_panel(source, len(panels) + 1, suffix, spec))
    if len(panels) != PAGE_SIZE:
        raise ContractViolation([f"{page_id} must derive exactly nine panels"])
    anchor_panel = next(
        panel["panel"]
        for panel in panels
        if panel["panel_kind"] == "source" and panel["source_shot"] == int(anchor_shot["shot_no"])
    )
    return {
        "page": page_id,
        "scene_id": scene_id,
        "reality_layer": layer,
        "page_mode": PAGE_MODE,
        "spatial_anchor_panel": anchor_panel,
        "source_shot_nos": [int(shot["shot_no"]) for shot in chunk],
        "completion_mode": COMPLETION_SOURCE_ONLY if len(chunk) == PAGE_SIZE else COMPLETION_DERIVED_ANGLE,
        "panels": panels,
    }


def reference_bindings(data: dict[str, Any]) -> list[Any]:
    return validate_reference_bindings(data)


def validate_binding_targets(
    bindings: list[dict[str, Any]],
    data: dict[str, Any],
    pages: list[dict[str, Any]],
) -> None:
    logs = scene_logs(data)
    character_targets = {
        name
        for shot in data["shots"]
        for name in (
            normalized_text_list(shot.get("visible_characters"))
            + normalized_text_list(shot.get("offscreen_characters"))
        )
    }
    prop_targets = {
        name for shot in data["shots"] for name in normalized_text_list(shot.get("visible_props"))
    }
    for log in logs.values():
        character_targets.update(normalized_text_list(log.get("characters")))
        prop_targets.update(normalized_text_list(log.get("props")))
    space_targets = set(logs)
    panel_targets = {
        f"{page['page']}/{panel['panel']}"
        for page in pages
        for panel in page["panels"]
    }
    targets = {
        "character": character_targets,
        "prop": prop_targets,
        "space": space_targets,
        "panel": panel_targets,
    }
    for binding in bindings:
        if binding["target_id"] not in targets[binding["binding_type"]]:
            raise DerivationReview(
                "F-ASSET",
                f"Reference {binding['asset_id']} target {binding['target_id']} is not present in the signed source or derived page map.",
            )


def bindings_for_page(
    bindings: list[dict[str, Any]],
    page: dict[str, Any],
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    shots_by_no = {int(shot["shot_no"]): shot for shot in data["shots"]}
    shots = [shots_by_no[number] for number in page["source_shot_nos"]]
    visible_characters = {
        name for shot in shots for name in normalized_text_list(shot.get("visible_characters"))
    }
    visible_props = {name for shot in shots for name in normalized_text_list(shot.get("visible_props"))}
    result: list[dict[str, Any]] = []
    for binding in bindings:
        binding_type = binding["binding_type"]
        target = binding["target_id"]
        applies = (
            (binding_type == "character" and target in visible_characters)
            or (binding_type == "prop" and target in visible_props)
            or (binding_type == "space" and target == page["scene_id"])
            or (binding_type == "panel" and target.startswith(f"{page['page']}/"))
        )
        if applies:
            result.append(binding)
    return result


def build_panel_plan(
    data: dict[str, Any],
    pages: list[list[dict[str, Any]]],
    shot_data_path: Path,
    canon_path: Path,
    *,
    release_ready: bool,
) -> dict[str, Any]:
    logs = scene_logs(data)
    sequence_distance_locks = distance_stage_locks_for_sequence(data["shots"], logs)
    report = as_dict(data.get("validation_report"))
    status = clean_text(report.get("status")).upper()
    upstream_version, _upstream_rule_revision = upstream_provenance(data)
    return {
        "skill": "su-image9",
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "source": {
            "file_sha256": source_file_sha256(shot_data_path),
            "content_hash": canonical_data_hash(data),
            "skill_version": upstream_version,
            "validation_status": "PASS" if status == "PASS" else "WARN_ACCEPTED",
            "warning_digest": warning_digest(report),
        },
        "canon": {"version": VERSION, "sha256": canon_file_sha256(canon_path)},
        "reference_bindings": reference_bindings(data),
        "pages": [
            build_page(
                index,
                chunk,
                data,
                logs,
                prop_fact_ids(data),
                sequence_distance_locks,
            )
            for index, chunk in enumerate(pages, 1)
        ],
        "release_ready": release_ready,
    }


def build_page_map(panel_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "skill": "su-image9",
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "source_file_sha256": panel_plan["source"]["file_sha256"],
        "pages": [
            {
                "page_no": int(page["page"].split("-")[1]),
                "page": page["page"],
                "source": f"{page['page']}.png",
                "header": (
                    f"{page['scene_id']} {page['reality_layer']}｜"
                    f"镜头{page['source_shot_nos'][0]:03d}-{page['source_shot_nos'][-1]:03d}"
                ),
                "scene_id": page["scene_id"],
                "reality_layer": page["reality_layer"],
                "spatial_anchor_panel": page["spatial_anchor_panel"],
                "panels": [
                    {
                        "panel_no": int(panel["panel"].split("-")[1]),
                        "panel": panel["panel"],
                        "source_shot": panel["source_shot"],
                        "variant_suffix": panel["variant_suffix"],
                        "display_label": panel["display_label"],
                    }
                    for panel in page["panels"]
                ],
            }
            for page in panel_plan["pages"]
        ],
        "release_ready": panel_plan["release_ready"],
    }


def render_panel_sentence(panel: dict[str, Any], source_shot: dict[str, Any]) -> str:
    visible = "、".join(panel["visible_characters"]) or "none"
    offscreen = "、".join(panel["offscreen_characters"]) or "none"
    props = "、".join(panel["visible_props"]) or "none"
    focus = "、".join(panel.get("primary_focus", [])) or "none"
    must_show = "、".join(panel.get("must_show", [])) or "none"
    may_show = "、".join(panel.get("may_show", [])) or "none"
    must_not_show = "、".join(panel.get("must_not_show", [])) or "none"
    render_delta = panel.get("render_delta", "none")
    story_delta = panel.get("story_delta", "source")
    rationale = panel.get("camera_rationale", "")
    return (
        f"{panel['panel']}: Draw {panel['drawn_camera_tag']}. {panel['composition_task']} "
        f"Visible characters: {visible}. Offscreen characters must remain outside the frame: {offscreen}. "
        f"Visible registered props: {props}. Distance/position stage: {panel['distance_stage_lock']}. "
        f"Primary focus: {focus}. Must show: {must_show}. May show: {may_show}. Must not show: {must_not_show}. "
        f"Render delta: {render_delta}; story delta: {story_delta}. Camera rationale: {rationale} "
        "Do not add another action phase, character, prop, emotion result, or spatial fact."
    )


def registered_vehicle_facts(page: dict[str, Any], shots_by_no: dict[int, dict[str, Any]], log: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for shot_no in page["source_shot_nos"]:
        values.extend(normalized_text_list(shots_by_no[shot_no].get("visible_props")))
    values.extend(normalized_text_list(log.get("fixed_objects")))
    unique = list(dict.fromkeys(values))
    return [
        value
        for value in unique
        if value == "车"
        or any(term in value for term in VEHICLE_TERMS)
        or any(re.search(rf"\b{re.escape(term)}s?\b$", value, flags=re.IGNORECASE) for term in ENGLISH_VEHICLE_TERMS)
    ]


def render_page_prompt(page: dict[str, Any], data: dict[str, Any]) -> str:
    logs = scene_logs(data)
    log = logs[page["scene_id"]]
    shots_by_no = {int(shot["shot_no"]): shot for shot in data["shots"]}
    source_shots = [shots_by_no[number] for number in page["source_shot_nos"]]
    fixed_objects = entity_descriptions(log.get("fixed_objects"))
    characters = entity_descriptions(log.get("characters"), character=True)
    source_visible_characters = list(
        dict.fromkeys(name for shot in source_shots for name in normalized_text_list(shot.get("visible_characters")))
    )
    source_visible_props = list(
        dict.fromkeys(name for shot in source_shots for name in normalized_text_list(shot.get("visible_props")))
    )
    vehicles = registered_vehicle_facts(page, shots_by_no, log)
    bindings = bindings_for_page(validate_reference_bindings(data), page, data)
    binding_lines = [
        (
            f"Bound reference {item['asset_id']} ({item['asset_sha256']}) constrains "
            f"{item['binding_type']} target {item['target_id']} only for "
            f"{', '.join(item['locked_attributes'])}."
        )
        for item in bindings
    ]

    scene_lines = [
        f"Scene {page['scene_id']}; reality layer: {page['reality_layer']}.",
        f"Source scene heading: {clean_text(log.get('scene')) or clean_text(source_shots[0].get('scene'))}.",
        f"Registered spatial axis: {clean_text(log.get('spatial_axis')) or 'no additional axis statement'}.",
        f"Registered fixed geometry: {'; '.join(fixed_objects) if fixed_objects else 'none'}.",
        f"Registered character placement: {'; '.join(characters) if characters else 'none'}.",
    ]
    camera_lines = [
        "Preserve every source shot camera tag and source order; a derived angle may change only angle, shot size, or composition emphasis.",
        *[
            f"C{int(shot['shot_no']):03d}: source camera {camera_tag(shot)}; {shot_summary(shot)}"
            for shot in source_shots
        ],
    ]
    continuity_lines = [
        f"Visible character boundary: {'、'.join(source_visible_characters) if source_visible_characters else 'none'}.",
        f"Visible prop boundary: {'、'.join(source_visible_props) if source_visible_props else 'none'}.",
        "Derived panels inherit the exact Beat, fact, action phase, emotional result, and continuity-state hash of their source panel.",
        "Position and facing transitions follow only continuity_updates; never infer a distance endpoint from action keywords.",
        "Render_delta=allowed means a derived panel may crop, obscure, or frame a subset of the source visible set; story_delta must remain none.",
    ]
    anchor_panel = next(panel for panel in page["panels"] if panel["panel"] == page["spatial_anchor_panel"])
    anchor_lines = [
        f"Use {page['spatial_anchor_panel']} / {anchor_panel['display_label']} as this page's declared spatial anchor.",
        "Panel 1 still preserves its original director-approved source camera and composition; do not widen or redesign it to manufacture an anchor.",
        "All angles remain on the registered side of the axis and may reveal only registered geometry.",
    ]
    geometry_lines = [
        "@CANON(GEOMETRY_BLUEPRINT)",
        f"Source-defined fixed geometry for this page: {'; '.join(fixed_objects) if fixed_objects else 'none registered; do not invent doors, windows, furniture, terrain, boundaries, or effects'}.",
    ]
    vehicle_lines = [
        "Preserve registered eyelines, facing, side-axis relationships, and screen-left/screen-right continuity.",
        (
            f"Registered vehicles or transport objects: {'、'.join(vehicles)}. Preserve their registered positions and states only."
            if vehicles
            else "Do not introduce unregistered transport objects or alter any registered object state."
        ),
    ]
    object_lines = [
        f"Draw only these visible registered props when their source panel calls for them: {'、'.join(source_visible_props) if source_visible_props else 'none'}.",
        "Offscreen voices and characters remain outside the frame unless that source panel lists them as visible.",
    ]
    panel_lines = [render_panel_sentence(panel, shots_by_no[int(panel["source_shot"])]) for panel in page["panels"]]

    sections = [
        ("DELIVERABLE", ["@CANON(HARD_PHRASES)"]),
        ("SYSTEM_STYLE_LAYER", ["@CANON(SYSTEM_STYLE_LAYER)"]),
        (
            "SOURCE_BINDING_LAYER",
            [
                f"This page is bound to source shots {', '.join(f'C{number:03d}' for number in page['source_shot_nos'])}.",
                "The structured panel plan is the only machine fact source; this Prompt must not override it.",
                *(binding_lines or ["Reference asset state: none."]),
            ],
        ),
        ("SCENE_LAYER", scene_lines),
        ("CAMERA_RULE_LAYER", camera_lines),
        ("CONTINUITY_LAYER", continuity_lines),
        ("PAGE_SPATIAL_ANCHOR", anchor_lines),
        ("FIXED_GEOMETRY_LOCK", geometry_lines),
        ("VEHICLE_AND_AXIS_LOCKS", vehicle_lines),
        ("OBJECT_VISIBILITY_AND_BOUNDARIES", object_lines),
        ("PANEL_LAYER", panel_lines),
        ("NEGATIVE_CONSTRAINTS", ["@CANON(NEGATIVE_CONSTRAINTS)"]),
    ]
    lines = [f"# {page['page']}"]
    for heading, content in sections:
        lines.extend(["", f"{heading}:", *content])
    return "\n".join(lines).rstrip()


def render_analysis(
    panel_plan: dict[str, Any],
    data: dict[str, Any],
    semantic_warnings: list[str] | None = None,
) -> str:
    report = as_dict(data.get("validation_report"))
    upstream_version, upstream_rule_revision = upstream_provenance(data)
    lines = [
        f"# su-image9 {VERSION} 分析与锁定",
        "",
        "## 源签发",
        f"- 上游：{UPSTREAM_SKILL} {upstream_version}",
        f"- 上游规则修订：`{upstream_rule_revision}`",
        f"- 文件 SHA-256：`{panel_plan['source']['file_sha256']}`",
        f"- 内容 Hash：`{panel_plan['source']['content_hash']}`",
        f"- 上游状态：`{panel_plan['source']['validation_status']}`",
        f"- WARN 摘要：`{panel_plan['source']['warning_digest']}`",
        "",
        "## 分页与锚点",
    ]
    for page in panel_plan["pages"]:
        derived = [panel["display_label"] for panel in page["panels"] if panel["panel_kind"] == "derived_angle"]
        lines.append(
            f"- {page['page']}：scene `{page['scene_id']}` / layer `{page['reality_layer']}`；"
            f"源镜 {', '.join(f'C{number:03d}' for number in page['source_shot_nos'])}；"
            f"空间锚点 `{page['spatial_anchor_panel']}`；补足 `{page['completion_mode']}`"
            + (f"（{', '.join(derived)}）" if derived else "")
        )
    warnings = [clean_text(item) for item in as_list(report.get("warnings")) if clean_text(item)]
    lines.extend(["", "## 源 WARN", *(f"- {item}" for item in warnings)] if warnings else ["", "## 源 WARN", "- 无"])
    lines.extend(
        [
            "",
            "## 语义风险",
            *(f"- {item}" for item in (semantic_warnings or ["- 无"])),
            "",
            "## 资产风险",
            f"- 参考绑定：{len(panel_plan['reference_bindings'])} 项。未绑定资产不得成为人物、道具或空间事实。",
            "",
            "## 固定成果",
            "- `panel_plan.json`",
            "- `page-map.json`",
            "- `final_image_prompts.md`",
            "- `final_image_prompts.compiled.md`",
            "- `validation_report.json`",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def derive_artifacts(
    data: dict[str, Any],
    shot_data_path: Path,
    canon_path: Path,
    *,
    release_ready: bool = False,
    semantic_warnings: list[str] | None = None,
) -> dict[str, Any]:
    errors = validate_source_contract(data)
    if errors:
        raise ContractViolation(errors)
    logs = scene_logs(data)
    pages = page_chunks(data["shots"], logs)
    panel_plan = build_panel_plan(
        data,
        pages,
        shot_data_path,
        canon_path,
        release_ready=release_ready,
    )
    validate_binding_targets(panel_plan["reference_bindings"], data, panel_plan["pages"])
    page_map = build_page_map(panel_plan)
    prompts = "\n\n".join(render_page_prompt(page, data) for page in panel_plan["pages"]) + "\n"
    return {
        "panel_plan": panel_plan,
        "page_map": page_map,
        "final_prompts": prompts,
        "analysis": render_analysis(panel_plan, data, semantic_warnings),
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_artifacts(out_dir: Path, artifacts: dict[str, Any]) -> None:
    write_json(out_dir / "panel_plan.json", artifacts["panel_plan"])
    write_json(out_dir / "page-map.json", artifacts["page_map"])
    (out_dir / "final_image_prompts.md").write_text(artifacts["final_prompts"], encoding="utf-8")
    (out_dir / "分析与锁定.md").write_text(artifacts["analysis"], encoding="utf-8")


def status_report(
    status: str,
    *,
    errors: list[str] | None = None,
    review_reasons: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "skill": "su-image9",
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "release_ready": False,
        "errors": errors or [],
        "review_required_reasons": review_reasons or [],
    }


def run_validator(
    validator_path: Path,
    canon_path: Path,
    panel_plan_path: Path,
    prompts_path: Path,
    shot_data_path: Path,
    report_path: Path,
    compiled_path: Path,
) -> int:
    command = [
        sys.executable,
        str(validator_path),
        "--canon",
        str(canon_path),
        "--panel-plan",
        str(panel_plan_path),
        "--final-prompts",
        str(prompts_path),
        "--shot-data",
        str(shot_data_path),
        "--report",
        str(report_path),
        "--out",
        str(compiled_path),
    ]
    try:
        process = subprocess.run(command, check=False)
    except OSError as exc:
        print(f"TOOL_ERROR: could not start validator: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    return process.returncode if process.returncode in {0, 1, 2, 3} else EXIT_TOOL_ERROR


def load_source(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("shot_data top level must be a JSON object")
    return value


def write_failure_report(
    out_dir: Path,
    report: dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "validation_report.json", report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shot-data", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--canon",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "references" / "canon-locks.md",
    )
    args = parser.parse_args(argv)

    if args.out_dir.exists():
        print("CONTRACT_FAIL: --out-dir must be absent", file=sys.stderr)
        return EXIT_CONTRACT_FAIL
    try:
        data = load_source(args.shot_data)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        write_failure_report(args.out_dir, status_report("CONTRACT_FAIL", errors=[str(exc)]))
        return EXIT_CONTRACT_FAIL

    validator_path = Path(__file__).with_name("validate_su_image9_prompt.py")
    missing_tools = [str(path) for path in (args.canon, validator_path) if not path.is_file()]
    if missing_tools:
        error = "required tool or canon is missing: " + ", ".join(missing_tools)
        write_failure_report(args.out_dir, status_report("TOOL_ERROR", errors=[error]))
        return EXIT_TOOL_ERROR

    # Run Chinese semantic audit before derivation.
    semantic_warnings = semantic_audit.semantic_conflicts(data)

    try:
        pending = derive_artifacts(data, args.shot_data, args.canon, release_ready=False, semantic_warnings=semantic_warnings)
        candidate = derive_artifacts(data, args.shot_data, args.canon, release_ready=True, semantic_warnings=semantic_warnings)
    except ContractViolation as exc:
        write_failure_report(args.out_dir, status_report("CONTRACT_FAIL", errors=exc.errors))
        return EXIT_CONTRACT_FAIL
    except DerivationReview as exc:
        write_failure_report(args.out_dir, status_report("REVIEW_REQUIRED", review_reasons=[exc.as_reason()]))
        return EXIT_REVIEW_REQUIRED
    except (OSError, UnicodeError) as exc:
        write_failure_report(args.out_dir, status_report("TOOL_ERROR", errors=[str(exc)]))
        return EXIT_TOOL_ERROR

    args.out_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{args.out_dir.name}-v210-", dir=args.out_dir.parent) as temp_name:
        temp_dir = Path(temp_name)
        staging_dir = temp_dir / "package"
        staging_dir.mkdir()
        write_artifacts(staging_dir, pending)
        candidate_plan_path = temp_dir / "panel_plan.json"
        candidate_report_path = temp_dir / "validation_report.json"
        candidate_compiled_path = temp_dir / "final_image_prompts.compiled.md"
        write_json(candidate_plan_path, candidate["panel_plan"])
        return_code = run_validator(
            validator_path,
            args.canon,
            candidate_plan_path,
            staging_dir / "final_image_prompts.md",
            args.shot_data,
            candidate_report_path,
            candidate_compiled_path,
        )
        if return_code == EXIT_PASS:
            try:
                report = load_source(candidate_report_path)
                valid_report = report.get("status") == "PASS" and report.get("release_ready") is True
                if not valid_report or not candidate_compiled_path.is_file():
                    raise ValueError("validator returned PASS without a release-ready report and compiled Prompt")
                write_artifacts(staging_dir, candidate)
                (staging_dir / "final_image_prompts.compiled.md").write_bytes(candidate_compiled_path.read_bytes())
                write_json(staging_dir / "validation_report.json", report)
                staging_dir.rename(args.out_dir)
                return EXIT_PASS
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                write_failure_report(args.out_dir, status_report("TOOL_ERROR", errors=[str(exc)]))
                return EXIT_TOOL_ERROR
        if candidate_report_path.is_file():
            try:
                report = load_source(candidate_report_path)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                report = status_report("TOOL_ERROR", errors=[f"validator report is invalid: {exc}"])
                return_code = EXIT_TOOL_ERROR
        else:
            status = {
                EXIT_REVIEW_REQUIRED: "REVIEW_REQUIRED",
                EXIT_CONTRACT_FAIL: "CONTRACT_FAIL",
                EXIT_TOOL_ERROR: "TOOL_ERROR",
            }.get(return_code, "TOOL_ERROR")
            report = status_report(status, errors=["validator returned without a validation report"])
        write_failure_report(args.out_dir, report)
        return return_code


if __name__ == "__main__":
    raise SystemExit(main())
