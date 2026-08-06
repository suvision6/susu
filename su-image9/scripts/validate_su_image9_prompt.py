#!/usr/bin/env python3
"""Fail-closed validator/compiler for the su-image9 2.1.2 prompt package."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any


EXIT_PASS = 0
EXIT_REVIEW_REQUIRED = 1
EXIT_CONTRACT_FAIL = 2
EXIT_TOOL_ERROR = 3

SKILL_NAME = "su-image9"
SKILL_VERSION = "2.1.2"
SCHEMA_VERSION = "2.1"
UPSTREAM_SKILL = "su-fenjingskill-zh"

CANON_NAMES = (
    "HARD_PHRASES",
    "GEOMETRY_BLUEPRINT",
    "SYSTEM_STYLE_LAYER",
    "NEGATIVE_CONSTRAINTS",
)
CANON_NAME_SET = frozenset(CANON_NAMES)
PROMPT_CANON_MARKER_ORDER = (
    "HARD_PHRASES",
    "SYSTEM_STYLE_LAYER",
    "GEOMETRY_BLUEPRINT",
    "NEGATIVE_CONSTRAINTS",
)
LAYER_ORDER = (
    "DELIVERABLE",
    "SYSTEM_STYLE_LAYER",
    "SOURCE_BINDING_LAYER",
    "SCENE_LAYER",
    "CAMERA_RULE_LAYER",
    "CONTINUITY_LAYER",
    "PAGE_SPATIAL_ANCHOR",
    "FIXED_GEOMETRY_LOCK",
    "VEHICLE_AND_AXIS_LOCKS",
    "OBJECT_VISIBILITY_AND_BOUNDARIES",
    "PANEL_LAYER",
    "NEGATIVE_CONSTRAINTS",
)

TOP_KEYS = {
    "skill",
    "version",
    "schema_version",
    "source",
    "canon",
    "reference_bindings",
    "pages",
    "release_ready",
}
SOURCE_KEYS = {
    "file_sha256",
    "content_hash",
    "skill_version",
    "validation_status",
    "warning_digest",
}
CANON_KEYS = {"version", "sha256"}
PAGE_KEYS = {
    "page",
    "scene_id",
    "reality_layer",
    "page_mode",
    "spatial_anchor_panel",
    "source_shot_nos",
    "completion_mode",
    "panels",
}
# 2.1.2 extends the panel contract with narrative-driven visibility fields.
PANEL_KEYS = {
    "panel",
    "panel_kind",
    "source_shot",
    "variant_suffix",
    "display_label",
    "source_camera_tag",
    "drawn_camera_tag",
    "beat_ids",
    "covered_fact_ids",
    "visible_characters",
    "offscreen_characters",
    "visible_props",
    "continuity_state_hash",
    "composition_task",
    "distance_stage_lock",
    "fact_delta",
    "primary_focus",
    "must_show",
    "may_show",
    "must_not_show",
    "render_delta",
    "story_delta",
    "camera_rationale",
}
REFERENCE_BINDING_KEYS = {
    "asset_id",
    "asset_sha256",
    "binding_type",
    "target_id",
    "locked_attributes",
    "status",
}
CONTINUITY_UPDATE_KEYS = {
    "entity_type",
    "entity",
    "field",
    "from",
    "to",
    "evidence_fact_ids",
}
# With render_delta=allowed, visible_characters/visible_props are render visibility,
# not continuity facts; they are validated separately as subsets of the source panel.
INHERITED_PANEL_FIELDS = (
    "source_camera_tag",
    "beat_ids",
    "covered_fact_ids",
    "offscreen_characters",
    "continuity_state_hash",
    "distance_stage_lock",
)
# Narrative fields can differ between source and derived panels.
NARRATIVE_INHERITED_FIELDS = (
    "primary_focus",
    "must_show",
    "may_show",
    "must_not_show",
    "camera_rationale",
)
RENDER_VISIBILITY_FIELDS = (
    "visible_characters",
    "visible_props",
    "primary_focus",
    "must_show",
    "may_show",
    "must_not_show",
)
AUTO_WARNING_TOKENS = (
    "reference missing",
    "[reference missing]",
    "[合理补足]",
    "节奏",
    "cut/min",
    "短镜比例",
)
REVIEW_CODES = {"F-ASSET", "F-PAGE-ANCHOR", "F-SPARSE-COVERAGE", "F-SEMANTIC-CONFLICT"}


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    field: str
    message: str
    expected: Any = None
    actual: Any = None

    def as_dict(self) -> dict[str, Any]:
        value = {
            "code": self.code,
            "severity": self.severity,
            "field": self.field,
            "message": self.message,
        }
        if self.expected is not None:
            value["expected"] = self.expected
        if self.actual is not None:
            value["actual"] = self.actual
        return value


@dataclass
class Audit:
    findings: list[Finding] = field(default_factory=list)
    tool_error: bool = False

    def fail(
        self,
        code: str,
        field_name: str,
        message: str,
        *,
        expected: Any = None,
        actual: Any = None,
    ) -> None:
        self.findings.append(Finding(code, "FAIL", field_name, message, expected, actual))

    def review(self, code: str, field_name: str, message: str) -> None:
        self.findings.append(Finding(code, "REVIEW", field_name, message))

    def tool(self, field_name: str, message: str) -> None:
        self.tool_error = True
        self.findings.append(Finding("F-TOOL", "FAIL", field_name, message))

    @property
    def has_failures(self) -> bool:
        return any(item.severity == "FAIL" for item in self.findings)

    @property
    def has_reviews(self) -> bool:
        return any(item.severity == "REVIEW" for item in self.findings)

    @property
    def exit_code(self) -> int:
        if self.tool_error:
            return EXIT_TOOL_ERROR
        if self.has_failures:
            return EXIT_CONTRACT_FAIL
        if self.has_reviews:
            return EXIT_REVIEW_REQUIRED
        return EXIT_PASS

    @property
    def status(self) -> str:
        return {
            EXIT_PASS: "PASS",
            EXIT_REVIEW_REQUIRED: "REVIEW_REQUIRED",
            EXIT_CONTRACT_FAIL: "CONTRACT_FAIL",
            EXIT_TOOL_ERROR: "TOOL_ERROR",
        }[self.exit_code]


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def normalize_markdown(value: str) -> str:
    return "\n".join(line.rstrip() for line in normalize_text(value).split("\n")).strip()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_data_hash(data: dict[str, Any]) -> str:
    value = copy.deepcopy(data)
    value.pop("validation_report", None)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(payload.encode("utf-8"))


def upstream_gate_content_hash(data: dict[str, Any]) -> str:
    value = copy.deepcopy(data)
    value.pop("validation_report", None)
    value.pop("human_reviews", None)
    metadata = value.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("revision_log", None)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(payload.encode("utf-8"))


def script_hash_candidates(value: str) -> set[str]:
    legacy = re.sub(r"\s+", "", normalize_text(value).strip())
    normalized = normalize_text(value)
    return {
        sha256_bytes(legacy.encode("utf-8")),
        sha256_bytes(normalized.encode("utf-8")),
    }


def source_hash_candidates(data: dict[str, Any]) -> set[str]:
    return {canonical_data_hash(data), upstream_gate_content_hash(data)}


def warning_id(message: str) -> str:
    clean = clean_one_line(message)
    return "W-" + hashlib.sha1(clean.encode("utf-8")).hexdigest()[:12]


def warning_digest(warnings: list[Any]) -> str:
    values = sorted(clean_one_line(item) for item in warnings)
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return sha256_bytes(payload.encode("utf-8"))


def read_version(skill_dir: Path, audit: Audit) -> str:
    path = skill_dir / "VERSION"
    try:
        version = path.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError) as exc:
        audit.fail("F-VERSION", "VERSION", f"cannot read VERSION: {exc}")
        return ""
    if version != SKILL_VERSION:
        audit.fail(
            "F-VERSION",
            "VERSION",
            "validator only implements the 2.1.2 contract",
            expected=SKILL_VERSION,
            actual=version,
        )
    return version


def load_json_object(path: Path, label: str, audit: Audit) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        audit.fail("F-INPUT", label, f"required input does not exist: {path}")
        return None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        audit.fail("F-INPUT", label, f"required input is unreadable or invalid JSON: {exc}")
        return None
    if not isinstance(value, dict):
        audit.fail("F-INPUT", label, "top-level JSON value must be an object", actual=type(value).__name__)
        return None
    return value


def load_text(path: Path, label: str, audit: Audit) -> str | None:
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        audit.fail("F-INPUT", label, f"required input does not exist: {path}")
    except (OSError, UnicodeError) as exc:
        audit.fail("F-INPUT", label, f"required input is unreadable: {exc}")
    return None


def load_deriver(path: Path, audit: Audit) -> ModuleType | None:
    try:
        spec = importlib.util.spec_from_file_location("_su_image9_deriver_212", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot create module spec for {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    except Exception as exc:  # An unavailable deterministic builder is a tool failure.
        audit.tool("deriver", f"cannot load deterministic deriver: {type(exc).__name__}: {exc}")
        return None
    for name in ("derive_artifacts", "validate_source_contract", "canonical_data_hash"):
        if not callable(getattr(module, name, None)):
            audit.tool("deriver", f"deterministic deriver is missing callable {name}")
            return None
    return module


def parse_canon(path: Path, required_version: str, audit: Audit) -> tuple[dict[str, str], str]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
    except FileNotFoundError:
        audit.fail("F-CANON", "canon", f"canon file does not exist: {path}")
        return {}, ""
    except (OSError, UnicodeError) as exc:
        audit.fail("F-CANON", "canon", f"canon file is unreadable: {exc}")
        return {}, ""

    versions = re.findall(r"<!--\s*canon-version:\s*([^\s]+)\s*-->", text)
    if versions != [required_version]:
        audit.fail(
            "F-CANON",
            "canon.version",
            "canon must declare exactly one version matching VERSION",
            expected=[required_version],
            actual=versions,
        )

    headings = re.findall(r"(?m)^###\s+canon:([^\s]+)\s*$", text)
    counts = {name: headings.count(name) for name in set(headings)}
    unknown = sorted(set(headings) - CANON_NAME_SET)
    if unknown:
        audit.fail("F-CANON", "canon.blocks", "unknown canon blocks are forbidden", actual=unknown)
    for name in CANON_NAMES:
        if counts.get(name, 0) != 1:
            audit.fail(
                "F-CANON",
                f"canon.{name}",
                "each whitelisted canon block must occur exactly once",
                expected=1,
                actual=counts.get(name, 0),
            )

    block_pattern = re.compile(
        r"(?ms)^###\s+canon:([^\s]+)\s*\n\s*```text\s*\n(.*?)\n```\s*(?=^###\s+canon:|^##\s+|\Z)"
    )
    parsed: dict[str, list[str]] = {}
    for match in block_pattern.finditer(text):
        parsed.setdefault(match.group(1), []).append(normalize_text(match.group(2)).strip())
    blocks: dict[str, str] = {}
    for name in CANON_NAMES:
        values = parsed.get(name, [])
        if len(values) != 1 or not values[0]:
            audit.fail(
                "F-CANON",
                f"canon.{name}",
                "canon block must contain one non-empty, complete ```text payload",
                actual=len(values),
            )
        else:
            blocks[name] = values[0]
    for name, values in parsed.items():
        if name not in CANON_NAME_SET or len(values) != 1:
            audit.fail("F-CANON", f"canon.{name}", "malformed or duplicate canon payload", actual=len(values))
    for name, block in blocks.items():
        if re.search(r"@CANON\(", block):
            audit.fail("F-CANON", f"canon.{name}", "canon blocks may not contain nested canon markers")
    return blocks, sha256_bytes(raw)


def compile_prompt(raw_prompt: str, blocks: dict[str, str], audit: Audit) -> str:
    marker_names = re.findall(r"@CANON\(([^)]+)\)", raw_prompt)
    unknown = sorted(set(marker_names) - CANON_NAME_SET)
    if unknown:
        audit.fail("F-PROMPT-CANON", "final_prompts", "prompt contains non-whitelisted canon markers", actual=unknown)

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return blocks.get(name, match.group(0))

    compiled = re.sub(r"@CANON\(([^)]+)\)", replace, raw_prompt)
    if re.search(r"@CANON\(", compiled):
        audit.fail("F-PROMPT-CANON", "compiled_prompt", "compiled prompt contains unexpanded canon markers")
    return normalize_text(compiled)


def require_exact_keys(value: Any, keys: set[str], field_name: str, audit: Audit) -> bool:
    if not isinstance(value, dict):
        audit.fail("F-PLAN-SCHEMA", field_name, "value must be an object", actual=type(value).__name__)
        return False
    actual = set(value)
    if actual != keys:
        audit.fail(
            "F-PLAN-SCHEMA",
            field_name,
            "object keys do not match the public 2.1.2 schema",
            expected=sorted(keys),
            actual=sorted(actual),
        )
        return False
    return True


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def require_string_list(value: Any, field_name: str, audit: Audit) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        audit.fail(
            "F-PLAN-SCHEMA",
            field_name,
            "value must be an array of non-empty strings; booleans and compressed values are forbidden",
        )
        return None
    return value


def normalized_source_names(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    result: list[str] = []
    for item in value:
        if isinstance(item, bool):
            return None
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
            continue
        if isinstance(item, dict):
            name = next(
                (str(item.get(key)).strip() for key in ("name", "entity", "id", "label") if str(item.get(key) or "").strip()),
                "",
            )
            if not name:
                return None
            result.append(name)
            continue
        return None
    return result


def clean_one_line(value: Any) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(value or ""))).strip()


def normalized_strict_text_list(value: Any) -> list[str]:
    result: list[str] = []
    if not isinstance(value, list):
        return result
    for item in value:
        if isinstance(item, str):
            text = clean_one_line(item)
            if text and text not in result:
                result.append(text)
    return result


def normalized_state_items(value: Any) -> list[Any]:
    result: list[Any] = []
    if not isinstance(value, list):
        return result
    for item in value:
        if isinstance(item, str):
            normalized: Any = clean_one_line(item)
        elif isinstance(item, dict):
            normalized = {
                clean_one_line(key): clean_one_line(field_value) if isinstance(field_value, str) else copy.deepcopy(field_value)
                for key, field_value in item.items()
                if clean_one_line(key)
            }
        else:
            continue
        if normalized not in result:
            result.append(normalized)
    return sorted(result, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def normalized_updates(shot: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    updates = shot.get("continuity_updates")
    if not isinstance(updates, list):
        return result
    for item in updates:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "entity_type": clean_one_line(item.get("entity_type")),
                "entity": clean_one_line(item.get("entity")),
                "field": clean_one_line(item.get("field")),
                "from": clean_one_line(item.get("from")),
                "to": clean_one_line(item.get("to")),
                "evidence_fact_ids": normalized_strict_text_list(item.get("evidence_fact_ids")),
            }
        )
    return sorted(result, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def expected_continuity_hash(shot: dict[str, Any], log: dict[str, Any], layer: str) -> str:
    payload = {
        "scene_id": clean_one_line(shot.get("scene_id")),
        "reality_layer": layer,
        "beat_ids": normalized_strict_text_list(shot.get("beat_ids")),
        "covered_fact_ids": normalized_strict_text_list(shot.get("covered_fact_ids")),
        "visible_characters": normalized_strict_text_list(shot.get("visible_characters")),
        "offscreen_characters": normalized_strict_text_list(shot.get("offscreen_characters")),
        "visible_props": normalized_strict_text_list(shot.get("visible_props")),
        "continuity_updates": normalized_updates(shot),
        "scene_state": {
            "spatial_axis": clean_one_line(log.get("spatial_axis")),
            "fixed_objects": normalized_state_items(log.get("fixed_objects")),
            "characters": normalized_state_items(log.get("characters")),
            "props": normalized_state_items(log.get("props")),
        },
    }
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(payload_text.encode("utf-8"))


def scalar_state_is_valid(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return all(scalar_state_is_valid(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and key.strip() and scalar_state_is_valid(item) for key, item in value.items())
    return False


def validate_reference_bindings(data: dict[str, Any], plan: dict[str, Any] | None, audit: Audit) -> None:
    bindings = data.get("reference_bindings", [])
    if not isinstance(bindings, list):
        audit.fail("F-ASSET", "shot_data.reference_bindings", "reference_bindings must be an array")
        bindings = []
    assets_present = any(bool(data.get(key)) for key in ("reference_assets", "assets"))
    if assets_present and not bindings:
        audit.review("F-ASSET", "shot_data.reference_bindings", "provided reference assets must be explicitly bound")
    character_targets: set[str] = set()
    prop_targets: set[str] = set()
    scene_targets: set[str] = set()
    for shot in data.get("shots", []) if isinstance(data.get("shots"), list) else []:
        if not isinstance(shot, dict):
            continue
        character_targets.update(normalized_source_names(shot.get("visible_characters")) or [])
        character_targets.update(normalized_source_names(shot.get("offscreen_characters")) or [])
        prop_targets.update(normalized_source_names(shot.get("visible_props")) or [])
        if isinstance(shot.get("scene_id"), str):
            scene_targets.add(shot["scene_id"])
    for log in data.get("continuity_logs", []) if isinstance(data.get("continuity_logs"), list) else []:
        if not isinstance(log, dict):
            continue
        character_targets.update(normalized_source_names(log.get("characters")) or [])
        prop_targets.update(normalized_source_names(log.get("props")) or [])
        if isinstance(log.get("scene_id"), str):
            scene_targets.add(log["scene_id"])
    panel_targets = {
        f"{page.get('page')}/{panel.get('panel')}"
        for page in plan.get("pages", [])
        if isinstance(plan, dict) and isinstance(plan.get("pages"), list) and isinstance(page, dict)
        for panel in page.get("panels", [])
        if isinstance(page.get("panels"), list) and isinstance(panel, dict)
    } if isinstance(plan, dict) else set()
    allowed_attributes = {"identity", "shape", "ownership", "fixed_geometry"}
    seen_assets: set[str] = set()
    for index, item in enumerate(bindings):
        path = f"shot_data.reference_bindings[{index}]"
        if not isinstance(item, dict):
            audit.fail("F-ASSET", path, "each reference binding must be an object")
            continue
        if set(item) != REFERENCE_BINDING_KEYS:
            audit.fail(
                "F-ASSET",
                path,
                "reference binding keys must match the public asset contract",
                expected=sorted(REFERENCE_BINDING_KEYS),
                actual=sorted(item),
            )
        if item.get("status") != "bound":
            audit.fail("F-ASSET", f"{path}.status", "non-empty bindings must have status=bound", actual=item.get("status"))
        for field_name in ("asset_id", "target_id"):
            if not isinstance(item.get(field_name), str) or not item[field_name].strip():
                audit.fail("F-ASSET", f"{path}.{field_name}", f"{field_name} must be a non-empty string")
        asset_id = item.get("asset_id")
        if isinstance(asset_id, str) and asset_id in seen_assets:
            audit.fail("F-ASSET", f"{path}.asset_id", "asset_id must be unique", actual=asset_id)
        elif isinstance(asset_id, str):
            seen_assets.add(asset_id)
        asset_hash = item.get("asset_sha256")
        if not isinstance(asset_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", asset_hash):
            audit.fail("F-ASSET", f"{path}.asset_sha256", "asset_sha256 must be a lowercase 64-character SHA-256")
        if item.get("binding_type") not in {"character", "prop", "space", "panel"}:
            audit.fail("F-ASSET", f"{path}.binding_type", "binding_type must be character, prop, space, or panel")
        locked = item.get("locked_attributes")
        if not isinstance(locked, list) or not locked or any(not isinstance(value, str) or not value.strip() for value in locked):
            audit.fail("F-ASSET", f"{path}.locked_attributes", "locked_attributes must be a non-empty string array")
        elif any(value not in allowed_attributes for value in locked):
            audit.fail("F-ASSET", f"{path}.locked_attributes", "locked_attributes contains an unsupported value", actual=locked)
        if item.get("binding_type") == "panel" and (
            not isinstance(item.get("target_id"), str)
            or not re.fullmatch(r"PAGE-\d{2}/PANEL-[1-9]", item["target_id"])
        ):
            audit.fail("F-ASSET", f"{path}.target_id", "panel bindings must target PAGE-XX/PANEL-N")
        target_sets = {
            "character": character_targets,
            "prop": prop_targets,
            "space": scene_targets,
            "panel": panel_targets,
        }
        binding_type = item.get("binding_type")
        target_id = item.get("target_id")
        if binding_type in target_sets and isinstance(target_id, str) and target_id not in target_sets[binding_type]:
            audit.fail(
                "F-ASSET",
                f"{path}.target_id",
                "reference target is not registered by shot_data or panel_plan",
                actual=target_id,
            )
    if plan is not None and plan.get("reference_bindings") != bindings:
        audit.fail(
            "F-ASSET",
            "panel_plan.reference_bindings",
            "reference bindings were dropped, reordered, or changed during derivation",
            expected=bindings,
            actual=plan.get("reference_bindings"),
        )


def validate_strict_source_arrays(data: dict[str, Any], audit: Audit) -> None:
    logs = data.get("continuity_logs")
    if not isinstance(logs, list):
        audit.fail("F-SOURCE", "shot_data.continuity_logs", "continuity_logs must be an array")
        logs = []
    seen_scenes: set[str] = set()
    for index, log in enumerate(logs):
        path = f"shot_data.continuity_logs[{index}]"
        if not isinstance(log, dict):
            audit.fail("F-SOURCE", path, "continuity log must be an object")
            continue
        scene_id = log.get("scene_id")
        if not isinstance(scene_id, str) or not scene_id.strip() or scene_id in seen_scenes:
            audit.fail("F-SOURCE", f"{path}.scene_id", "scene_id must be non-empty and unique", actual=scene_id)
        elif isinstance(scene_id, str):
            seen_scenes.add(scene_id)
        for field_name in ("fixed_objects", "characters", "props"):
            value = log.get(field_name)
            if not isinstance(value, list) or any(not scalar_state_is_valid(item) for item in value):
                audit.fail("F-SOURCE", f"{path}.{field_name}", "state arrays may contain only non-empty strings or structured string objects")

    beats = data.get("beats")
    if not isinstance(beats, list) or not beats:
        audit.fail("F-SOURCE", "shot_data.beats", "beats must be a non-empty array")
        beats = []
    for beat_index, beat in enumerate(beats):
        beat_path = f"shot_data.beats[{beat_index}]"
        if not isinstance(beat, dict):
            audit.fail("F-SOURCE", beat_path, "beat must be an object")
            continue
        if not isinstance(beat.get("beat_id"), str) or not beat["beat_id"].strip():
            audit.fail("F-SOURCE", f"{beat_path}.beat_id", "beat_id must be a non-empty string")
        facts = beat.get("facts")
        if not isinstance(facts, list) or not facts:
            audit.fail("F-SOURCE", f"{beat_path}.facts", "facts must be a non-empty array")
            continue
        for fact_index, fact in enumerate(facts):
            fact_path = f"{beat_path}.facts[{fact_index}]"
            if not isinstance(fact, dict):
                audit.fail("F-SOURCE", fact_path, "fact must be an object")
                continue
            for field_name in ("fact_id", "type", "text"):
                if not isinstance(fact.get(field_name), str) or not fact[field_name].strip():
                    audit.fail("F-SOURCE", f"{fact_path}.{field_name}", f"{field_name} must be a non-empty string")

    shots = data.get("shots")
    if not isinstance(shots, list):
        return
    for index, shot in enumerate(shots):
        path = f"shot_data.shots[{index}]"
        if not isinstance(shot, dict):
            continue
        for field_name in ("beat_ids", "covered_fact_ids"):
            value = shot.get(field_name)
            if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
                audit.fail("F-SOURCE", f"{path}.{field_name}", "field must be a non-empty string array; scalar coercion is forbidden")
        for field_name in ("visible_characters", "offscreen_characters", "visible_props"):
            value = shot.get(field_name)
            if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
                audit.fail("F-SOURCE", f"{path}.{field_name}", "field must be a string array; booleans and numeric compression are forbidden")
        updates = shot.get("continuity_updates")
        if not isinstance(updates, list):
            audit.fail("F-SOURCE", f"{path}.continuity_updates", "continuity_updates must be an array")
            continue
        for update_index, item in enumerate(updates):
            update_path = f"{path}.continuity_updates[{update_index}]"
            if not isinstance(item, dict):
                audit.fail("F-SOURCE", update_path, "continuity update must be an object")
                continue
            if set(item) != CONTINUITY_UPDATE_KEYS:
                audit.fail(
                    "F-SOURCE",
                    update_path,
                    "continuity update keys must not be dropped or expanded",
                    expected=sorted(CONTINUITY_UPDATE_KEYS),
                    actual=sorted(item),
                )
            for field_name in ("entity_type", "entity", "field", "to"):
                if not isinstance(item.get(field_name), str) or not item[field_name].strip():
                    audit.fail("F-SOURCE", f"{update_path}.{field_name}", f"{field_name} must be a non-empty string")
            if not isinstance(item.get("from"), str):
                audit.fail("F-SOURCE", f"{update_path}.from", "from must be a string")
            evidence = item.get("evidence_fact_ids")
            if not isinstance(evidence, list) or not evidence or any(not isinstance(value, str) or not value.strip() for value in evidence):
                audit.fail("F-SOURCE", f"{update_path}.evidence_fact_ids", "evidence_fact_ids must be a non-empty string array")


def source_gate(data: dict[str, Any], source_path: Path, plan: dict[str, Any] | None, audit: Audit) -> None:
    validate_strict_source_arrays(data, audit)
    validate_reference_bindings(data, plan, audit)
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        audit.fail("F-SOURCE", "shot_data.metadata", "metadata must be an object")
        metadata = {}
    if metadata.get("skill_name") != UPSTREAM_SKILL:
        audit.fail("F-SOURCE", "shot_data.metadata.skill_name", "unsupported upstream skill", expected=UPSTREAM_SKILL, actual=metadata.get("skill_name"))
    upstream_version = metadata.get("version")
    upstream_rule_revision = metadata.get("rule_revision")
    if not isinstance(upstream_version, str) or not upstream_version.strip():
        audit.fail("F-SOURCE-VERSION", "shot_data.metadata.version", "upstream version must be a non-empty string; any upstream version is accepted", actual=upstream_version)
    if not isinstance(upstream_rule_revision, str) or not upstream_rule_revision.strip():
        audit.fail("F-SOURCE", "shot_data.metadata.rule_revision", "upstream rule revision must be a non-empty string; any upstream rule revision is accepted", actual=upstream_rule_revision)

    lock = data.get("script_lock")
    if not isinstance(lock, dict):
        audit.fail("F-SOURCE-LOCK", "shot_data.script_lock", "script_lock must be an object")
    else:
        if lock.get("status") != "locked":
            audit.fail("F-SOURCE-LOCK", "shot_data.script_lock.status", "script must be locked", expected="locked", actual=lock.get("status"))
        for key in ("approved_script_path", "locked_text", "locked_text_hash"):
            if not isinstance(lock.get(key), str) or not lock[key].strip():
                audit.fail("F-SOURCE-LOCK", f"shot_data.script_lock.{key}", f"{key} must be a non-empty string")
        locked_text = lock.get("locked_text")
        locked_hash = lock.get("locked_text_hash")
        if isinstance(locked_text, str) and isinstance(locked_hash, str):
            if locked_hash.strip() not in script_hash_candidates(locked_text):
                audit.fail("F-SOURCE-LOCK", "shot_data.script_lock.locked_text_hash", "locked script hash does not match a supported upstream text-hash contract", actual=locked_hash)

    reviews = data.get("human_reviews")
    if not isinstance(reviews, list):
        audit.fail("F-SOURCE-GATE", "shot_data.human_reviews", "human_reviews must be an array")
        reviews = []
    approved_gates: set[str] = set()
    for index, item in enumerate(reviews):
        if not isinstance(item, dict):
            audit.fail("F-SOURCE-GATE", f"shot_data.human_reviews[{index}]", "review must be an object")
            continue
        if item.get("status") == "approved" and isinstance(item.get("gate"), str):
            approved_gates.add(item["gate"])
    for gate in ("GATE_A", "GATE_B", "GATE_C"):
        if gate not in approved_gates:
            audit.fail("F-SOURCE-GATE", "shot_data.human_reviews", f"missing approved {gate}")

    report = data.get("validation_report")
    if not isinstance(report, dict):
        audit.fail("F-SOURCE-VALIDATION", "shot_data.validation_report", "validation_report must be an object")
        return
    status = report.get("status")
    if status not in {"PASS", "WARN"}:
        audit.fail("F-SOURCE-VALIDATION", "shot_data.validation_report.status", "FAIL, NOT_RUN, missing, and unknown statuses are rejected", actual=status)
    errors = report.get("errors", [])
    if not isinstance(errors, list) or errors:
        audit.fail("F-SOURCE-VALIDATION", "shot_data.validation_report.errors", "accepted upstream reports must contain no errors", actual=errors)
    warnings = report.get("warnings", [])
    if not isinstance(warnings, list) or any(not isinstance(item, str) or not item.strip() for item in warnings):
        audit.fail("F-SOURCE-WARN", "shot_data.validation_report.warnings", "warnings must be an array of non-empty strings")
        warnings = []
    if status == "PASS" and warnings:
        audit.fail("F-SOURCE-WARN", "shot_data.validation_report", "PASS report may not carry warnings")
    if status == "WARN" and not warnings:
        audit.fail("F-SOURCE-WARN", "shot_data.validation_report", "WARN report must carry at least one warning")

    expected_content_hash = canonical_data_hash(data)
    source_json_hash = report.get("source_json_hash")
    if not isinstance(source_json_hash, str) or source_json_hash.strip() not in source_hash_candidates(data):
        audit.fail("F-SOURCE-HASH", "shot_data.validation_report.source_json_hash", "source_json_hash does not match a supported upstream content-hash contract", actual=source_json_hash)

    resolutions = data.get("warn_resolutions", [])
    if not isinstance(resolutions, list):
        audit.fail("F-SOURCE-WARN", "shot_data.warn_resolutions", "warn_resolutions must be an array")
        resolutions = []
    by_id: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    for index, item in enumerate(resolutions):
        if not isinstance(item, dict):
            audit.fail("F-SOURCE-WARN", f"shot_data.warn_resolutions[{index}]", "resolution must be an object")
            continue
        item_id = item.get("warn_id")
        if not isinstance(item_id, str) or not item_id:
            audit.fail("F-SOURCE-WARN", f"shot_data.warn_resolutions[{index}].warn_id", "warn_id is required")
            continue
        if item_id in by_id:
            duplicate_ids.add(item_id)
        by_id[item_id] = item
    if duplicate_ids:
        audit.fail("F-SOURCE-WARN", "shot_data.warn_resolutions", "duplicate WARN resolutions are forbidden", actual=sorted(duplicate_ids))

    expected_ids = {warning_id(message) for message in warnings}
    if set(by_id) != expected_ids:
        audit.fail(
            "F-SOURCE-WARN",
            "shot_data.warn_resolutions",
            "WARN resolution set must exactly match the current warning set",
            expected=sorted(expected_ids),
            actual=sorted(by_id),
        )
    for message in warnings:
        item_id = warning_id(message)
        item = by_id.get(item_id)
        if not item:
            continue
        if item.get("resolution") not in {"keep", "revise", "accepted_without_change"}:
            audit.fail("F-SOURCE-WARN", f"shot_data.warn_resolutions.{item_id}.resolution", "invalid WARN resolution")
        resolved_by = item.get("resolved_by")
        if resolved_by not in {"human", "auto_whitelist"}:
            audit.fail("F-SOURCE-WARN", f"shot_data.warn_resolutions.{item_id}.resolved_by", "resolved_by must be human or auto_whitelist")
        if resolved_by == "auto_whitelist" and not any(token in message for token in AUTO_WARNING_TOKENS):
            audit.fail("F-SOURCE-WARN", f"shot_data.warn_resolutions.{item_id}.resolved_by", "non-whitelisted WARN must be resolved by human")
        if not isinstance(item.get("note"), str) or not item["note"].strip():
            audit.fail("F-SOURCE-WARN", f"shot_data.warn_resolutions.{item_id}.note", "WARN resolution note is required")

    if plan is None or not isinstance(plan.get("source"), dict):
        return
    summary = plan["source"]
    try:
        file_hash = sha256_bytes(source_path.read_bytes())
    except OSError as exc:
        audit.fail("F-SOURCE-HASH", "shot_data", f"cannot hash source file: {exc}")
        return
    expected_status = "PASS" if status == "PASS" else "WARN_ACCEPTED"
    expected_summary = {
        "file_sha256": file_hash,
        "content_hash": expected_content_hash,
        "skill_version": upstream_version.strip() if isinstance(upstream_version, str) else "",
        "validation_status": expected_status,
        "warning_digest": warning_digest(warnings),
    }
    if summary != expected_summary:
        audit.fail("F-SOURCE-HASH", "panel_plan.source", "source provenance summary is stale or inconsistent", expected=expected_summary, actual=summary)


def source_reality_layer(data: dict[str, Any], shot: dict[str, Any]) -> str:
    value = shot.get("reality_layer")
    if isinstance(value, str) and value.strip():
        return value.strip()
    scene_id = shot.get("scene_id")
    logs = data.get("continuity_logs")
    if isinstance(logs, list):
        for item in logs:
            if isinstance(item, dict) and item.get("scene_id") == scene_id:
                layer = item.get("reality_layer")
                return layer.strip() if isinstance(layer, str) else ""
    return ""


def source_camera_tag(shot: dict[str, Any]) -> str:
    match = re.match(r"\s*\[([^\]]+)\]", str(shot.get("camera_main_image", "")))
    return clean_one_line(match.group(1)) if match else ""


def source_is_transition(shot: dict[str, Any]) -> bool:
    shot_type = clean_one_line(shot.get("shot_type")).lower()
    tag = source_camera_tag(shot).lower()
    return shot_type in {"transition", "black", "blackout", "audio", "sound_only"} or any(
        term in tag for term in ("黑场", "纯声音", "纯音", "black frame", "blackout", "sound only", "audio only")
    )


def source_is_spatial_anchor(shot: dict[str, Any], log: dict[str, Any]) -> bool:
    if source_is_transition(shot):
        return False
    tag = source_camera_tag(shot).lower()
    if any(term in tag for term in ("特写", "大特写", "近景", "close-up", "close up", "extreme close", "insert", "插入")):
        return False
    if any(term in tag for term in ("大全景", "大远景", "全景", "远景", "wide", "full", "master", "establishing")):
        return True
    camera_text = str(shot.get("camera_main_image", ""))
    structured_placement = "【场景首镜站位】" in camera_text or "【站位位移】" in camera_text
    registered_axis = bool(clean_one_line(log.get("spatial_axis")))
    visible_subject = bool(normalized_strict_text_list(shot.get("visible_characters")))
    return registered_axis and (structured_placement or visible_subject)


def validate_panel_plan(plan: dict[str, Any], shot_data: dict[str, Any], canon_hash: str, audit: Audit) -> None:
    if not require_exact_keys(plan, TOP_KEYS, "panel_plan", audit):
        return
    if plan.get("skill") != SKILL_NAME or plan.get("version") != SKILL_VERSION or plan.get("schema_version") != SCHEMA_VERSION:
        audit.fail(
            "F-PLAN-SCHEMA",
            "panel_plan.identity",
            "plan identity does not match the 2.1.2 contract",
            expected=[SKILL_NAME, SKILL_VERSION, SCHEMA_VERSION],
            actual=[plan.get("skill"), plan.get("version"), plan.get("schema_version")],
        )
    require_exact_keys(plan.get("source"), SOURCE_KEYS, "panel_plan.source", audit)
    if require_exact_keys(plan.get("canon"), CANON_KEYS, "panel_plan.canon", audit):
        canon = plan["canon"]
        if canon.get("version") != SKILL_VERSION or canon.get("sha256") != canon_hash:
            audit.fail("F-CANON-HASH", "panel_plan.canon", "plan canon provenance is stale", expected={"version": SKILL_VERSION, "sha256": canon_hash}, actual=canon)
    if not isinstance(plan.get("reference_bindings"), list):
        audit.fail("F-PLAN-SCHEMA", "panel_plan.reference_bindings", "reference_bindings must be an array")
    if not isinstance(plan.get("release_ready"), bool):
        audit.fail("F-PLAN-SCHEMA", "panel_plan.release_ready", "release_ready must be a boolean")

    shots_value = shot_data.get("shots")
    shots = shots_value if isinstance(shots_value, list) else []
    logs_by_scene = {
        str(item.get("scene_id")): item
        for item in shot_data.get("continuity_logs", [])
        if isinstance(item, dict) and isinstance(item.get("scene_id"), str)
    } if isinstance(shot_data.get("continuity_logs"), list) else {}
    facts_by_id = {
        str(fact.get("fact_id")): fact
        for beat in shot_data.get("beats", [])
        if isinstance(beat, dict) and isinstance(beat.get("facts"), list)
        for fact in beat["facts"]
        if isinstance(fact, dict) and isinstance(fact.get("fact_id"), str)
    } if isinstance(shot_data.get("beats"), list) else {}
    source_lookup: dict[int, dict[str, Any]] = {}
    source_order: list[int] = []
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict) or not is_int(shot.get("shot_no")):
            audit.fail("F-SOURCE", f"shot_data.shots[{index}]", "each source shot must have an integer shot_no")
            continue
        number = shot["shot_no"]
        if number in source_lookup:
            audit.fail("F-SOURCE", f"shot_data.shots[{index}].shot_no", "duplicate source shot number", actual=number)
            continue
        source_lookup[number] = shot
        source_order.append(number)

    pages_value = plan.get("pages")
    if not isinstance(pages_value, list) or not pages_value:
        audit.fail("F-PAGE", "panel_plan.pages", "pages must be a non-empty array")
        return
    pages = pages_value
    native_order: list[int] = []
    all_page_ids: set[str] = set()

    for page_index, page in enumerate(pages, 1):
        page_path = f"panel_plan.pages[{page_index - 1}]"
        if not require_exact_keys(page, PAGE_KEYS, page_path, audit):
            continue
        expected_page_id = f"PAGE-{page_index:02d}"
        page_id = page.get("page")
        if page_id != expected_page_id or page_id in all_page_ids:
            audit.fail("F-PAGE", f"{page_path}.page", "page IDs must be unique and continuous", expected=expected_page_id, actual=page_id)
        if isinstance(page_id, str):
            all_page_ids.add(page_id)
        if page.get("page_mode") != "single_scene_single_reality_layer":
            audit.fail("F-PAGE", f"{page_path}.page_mode", "unsupported page mode", expected="single_scene_single_reality_layer", actual=page.get("page_mode"))
        if page.get("completion_mode") not in {"source_only", "derived_angle"}:
            audit.fail("F-PAGE", f"{page_path}.completion_mode", "invalid completion mode", actual=page.get("completion_mode"))
        if not isinstance(page.get("scene_id"), str) or not page["scene_id"].strip():
            audit.fail("F-PAGE", f"{page_path}.scene_id", "scene_id must be a non-empty string")
        if not isinstance(page.get("reality_layer"), str) or not page["reality_layer"].strip():
            audit.fail("F-PAGE", f"{page_path}.reality_layer", "reality_layer must be a non-empty string")

        source_nos = page.get("source_shot_nos")
        if not isinstance(source_nos, list) or not source_nos or len(source_nos) > 9 or any(not is_int(item) for item in source_nos):
            audit.fail("F-PAGE", f"{page_path}.source_shot_nos", "source_shot_nos must contain 1-9 integer shot numbers")
            source_nos = []
        panels_value = page.get("panels")
        if not isinstance(panels_value, list) or len(panels_value) != 9:
            audit.fail("F-PANEL", f"{page_path}.panels", "every page must contain exactly nine panels", expected=9, actual=len(panels_value) if isinstance(panels_value, list) else type(panels_value).__name__)
            panels = panels_value if isinstance(panels_value, list) else []
        else:
            panels = panels_value

        page_native: list[int] = []
        panel_by_source: dict[int, dict[str, Any]] = {}
        sequence: list[int] = []
        suffixes: dict[int, list[str]] = {}
        panel_ids: set[str] = set()
        for panel_index, panel in enumerate(panels, 1):
            panel_path = f"{page_path}.panels[{panel_index - 1}]"
            if not require_exact_keys(panel, PANEL_KEYS, panel_path, audit):
                continue
            expected_panel_id = f"PANEL-{panel_index}"
            panel_id = panel.get("panel")
            if panel_id != expected_panel_id or panel_id in panel_ids:
                audit.fail("F-PANEL", f"{panel_path}.panel", "panel IDs must be PANEL-1 through PANEL-9 in order", expected=expected_panel_id, actual=panel_id)
            if isinstance(panel_id, str):
                panel_ids.add(panel_id)
            kind = panel.get("panel_kind")
            if kind not in {"source", "derived_angle"}:
                audit.fail("F-PANEL", f"{panel_path}.panel_kind", "panel_kind must be source or derived_angle", actual=kind)
            number = panel.get("source_shot")
            if not is_int(number) or number not in source_lookup:
                audit.fail("F-PANEL", f"{panel_path}.source_shot", "panel must point to one existing integer source shot", actual=number)
                continue
            sequence.append(number)
            source = source_lookup[number]
            for field_name in ("beat_ids", "covered_fact_ids", "visible_characters", "offscreen_characters", "visible_props"):
                require_string_list(panel.get(field_name), f"{panel_path}.{field_name}", audit)
            state_hash = panel.get("continuity_state_hash")
            if not isinstance(state_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", state_hash):
                audit.fail("F-PANEL", f"{panel_path}.continuity_state_hash", "continuity_state_hash must be a lowercase SHA-256")
            for field_name in ("source_camera_tag", "drawn_camera_tag", "composition_task", "distance_stage_lock", "display_label", "camera_rationale"):
                if not isinstance(panel.get(field_name), str) or not panel[field_name].strip():
                    audit.fail("F-PANEL", f"{panel_path}.{field_name}", f"{field_name} must be a non-empty string")
            for field_name in ("primary_focus", "must_show", "may_show", "must_not_show"):
                if not isinstance(panel.get(field_name), list) or any(not isinstance(item, str) for item in panel[field_name]):
                    audit.fail("F-PANEL", f"{panel_path}.{field_name}", f"{field_name} must be a string array")
            render_delta = panel.get("render_delta")
            if render_delta not in {"none", "allowed"}:
                audit.fail("F-PANEL", f"{panel_path}.render_delta", "render_delta must be none or allowed", actual=render_delta)
            story_delta = panel.get("story_delta")
            if story_delta != "none":
                audit.fail("F-PANEL", f"{panel_path}.story_delta", "story_delta must be none", actual=story_delta)

            if kind == "source":
                page_native.append(number)
                native_order.append(number)
                if number in panel_by_source:
                    audit.fail("F-SOURCE-COVERAGE", panel_path, "source shot has more than one native source panel", actual=number)
                panel_by_source[number] = panel
                if panel.get("variant_suffix") is not None or panel.get("display_label") != f"C{number:03d}" or panel.get("fact_delta") != "source":
                    audit.fail("F-PANEL", panel_path, "source label, suffix, or fact_delta is invalid")
                if panel.get("drawn_camera_tag") != panel.get("source_camera_tag"):
                    audit.fail("F-CAMERA", f"{panel_path}.drawn_camera_tag", "source panels must preserve the original director camera tag")
                expected_camera_tag = source_camera_tag(source)
                if panel.get("source_camera_tag") != expected_camera_tag:
                    audit.fail(
                        "F-CAMERA",
                        f"{panel_path}.source_camera_tag",
                        "source camera tag does not match camera_main_image",
                        expected=expected_camera_tag,
                        actual=panel.get("source_camera_tag"),
                    )
                log = logs_by_scene.get(str(source.get("scene_id")), {})
                layer = source_reality_layer(shot_data, source)
                expected_state_hash = expected_continuity_hash(source, log, layer)
                if panel.get("continuity_state_hash") != expected_state_hash:
                    audit.fail(
                        "F-CONTINUITY-HASH",
                        f"{panel_path}.continuity_state_hash",
                        "continuity hash does not match the source facts and registered state",
                        expected=expected_state_hash,
                        actual=panel.get("continuity_state_hash"),
                    )
                for plan_field, source_field in (
                    ("beat_ids", "beat_ids"),
                    ("covered_fact_ids", "covered_fact_ids"),
                    ("visible_characters", "visible_characters"),
                    ("offscreen_characters", "offscreen_characters"),
                    ("visible_props", "visible_props"),
                ):
                    expected_value = normalized_source_names(source.get(source_field))
                    if expected_value is None:
                        audit.fail("F-SOURCE", f"shot_data.shots.{number}.{source_field}", "source fact/entity fields must be arrays, never booleans")
                    elif panel.get(plan_field) != expected_value:
                        audit.fail("F-SOURCE-BINDING", f"{panel_path}.{plan_field}", "source panel does not preserve source facts/entities", expected=expected_value, actual=panel.get(plan_field))
                # Source panels must have render_delta=none and must_show equal to visible set.
                if panel.get("render_delta") != "none":
                    audit.fail("F-PANEL", f"{panel_path}.render_delta", "source panel render_delta must be none", expected="none", actual=panel.get("render_delta"))
                expected_must_show = sorted(
                    (normalized_source_names(source.get("visible_characters")) or [])
                    + (normalized_source_names(source.get("visible_props")) or [])
                )
                if sorted(panel.get("must_show", [])) != expected_must_show:
                    audit.fail("F-PANEL", f"{panel_path}.must_show", "source panel must_show must equal visible characters plus visible props", expected=expected_must_show, actual=sorted(panel.get("must_show", [])))
            elif kind == "derived_angle":
                suffix = panel.get("variant_suffix")
                if not isinstance(suffix, str) or not re.fullmatch(r"[A-Z]", suffix):
                    audit.fail("F-DERIVED", f"{panel_path}.variant_suffix", "derived suffix must be one uppercase letter")
                else:
                    suffixes.setdefault(number, []).append(suffix)
                    if panel.get("display_label") != f"C{number:03d}-{suffix}":
                        audit.fail("F-DERIVED", f"{panel_path}.display_label", "derived display label must copy the source shot and suffix")
                if panel.get("fact_delta") != "none":
                    audit.fail("F-DERIVED-FACT", f"{panel_path}.fact_delta", "derived panels may not add facts", expected="none", actual=panel.get("fact_delta"))
                native = panel_by_source.get(number)
                if native is None:
                    audit.fail("F-DERIVED", panel_path, "derived panel must be adjacent after its native source panel")
                else:
                    for field_name in INHERITED_PANEL_FIELDS:
                        if panel.get(field_name) != native.get(field_name):
                            audit.fail("F-DERIVED-FACT", f"{panel_path}.{field_name}", "derived panel changed inherited factual or continuity state", expected=native.get(field_name), actual=panel.get(field_name))
                    # render_delta visibility can shrink but must not invent entities
                    for field_name in ("visible_characters", "visible_props"):
                        source_names = set(native.get(field_name, []))
                        derived_names = set(panel.get(field_name, []))
                        if not derived_names.issubset(source_names):
                            audit.fail("F-DERIVED-FACT", f"{panel_path}.{field_name}", "derived panel introduced entities not in source", expected=sorted(source_names), actual=sorted(derived_names))
                    # must_show must be a subset of source visible set and present in derived visible set
                    for entity in panel.get("must_show", []):
                        if entity not in native.get("visible_characters", []) and entity not in native.get("visible_props", []):
                            audit.fail("F-DERIVED-FACT", f"{panel_path}.must_show", "must_show entity is not visible in source panel", actual=entity)
                        if entity not in panel.get("visible_characters", []) and entity not in panel.get("visible_props", []):
                            audit.fail("F-DERIVED-FACT", f"{panel_path}.must_show", "must_show entity is missing from derived visible set", actual=entity)
                    # must_not_show must not appear in derived visible set
                    for entity in panel.get("must_not_show", []):
                        if entity in panel.get("visible_characters", []) or entity in panel.get("visible_props", []):
                            audit.fail("F-DERIVED-FACT", f"{panel_path}.must_not_show", "must_not_show entity appears in derived visible set", actual=entity)
                if panel.get("drawn_camera_tag") == panel.get("source_camera_tag"):
                    audit.fail("F-DERIVED", f"{panel_path}.drawn_camera_tag", "derived angle must make a real camera/framing change")
                if isinstance(panel.get("drawn_camera_tag"), str) and "registered-prop insert" in panel["drawn_camera_tag"]:
                    prop_facts = [
                        facts_by_id.get(fact_id)
                        for fact_id in panel.get("covered_fact_ids", [])
                        if isinstance(fact_id, str)
                    ]
                    has_prop_fact = any(
                        isinstance(fact, dict)
                        and (fact.get("type") == "prop" or fact.get("cut_category") == "prop")
                        for fact in prop_facts
                    )
                    if not panel.get("visible_props") or not has_prop_fact:
                        audit.fail(
                            "F-DERIVED-FACT",
                            panel_path,
                            "prop insert requires a visible prop and a covered prop fact",
                        )
                if (
                    isinstance(panel.get("drawn_camera_tag"), str)
                    and "over-shoulder" in panel["drawn_camera_tag"]
                    and len(panel.get("visible_characters", [])) < 2
                ):
                    audit.fail("F-DERIVED-FACT", panel_path, "over-shoulder derivation requires at least two visible characters")

        if sequence != sorted(sequence):
            audit.fail("F-PANEL", f"{page_path}.panels", "panel source-shot sequence must be nondecreasing", actual=sequence)
        if source_nos != page_native:
            audit.fail("F-SOURCE-COVERAGE", f"{page_path}.source_shot_nos", "source_shot_nos must exactly list native panels", expected=page_native, actual=source_nos)
        for number, values in suffixes.items():
            expected_suffixes = [chr(ord("A") + index) for index in range(len(values))]
            if values != expected_suffixes:
                audit.fail("F-DERIVED", f"{page_path}.source_shot.{number}.variant_suffix", "derived suffixes must be continuous in order", expected=expected_suffixes, actual=values)

        page_shots = [source_lookup[number] for number in page_native if number in source_lookup]
        scene_ids = {shot.get("scene_id") for shot in page_shots}
        layers = {source_reality_layer(shot_data, shot) for shot in page_shots}
        if scene_ids != {page.get("scene_id")}:
            audit.fail("F-PAGE", f"{page_path}.scene_id", "one page may contain exactly one source scene", expected=sorted(str(item) for item in scene_ids), actual=page.get("scene_id"))
        if layers != {page.get("reality_layer")}:
            audit.fail("F-PAGE", f"{page_path}.reality_layer", "one page may contain exactly one reality layer", expected=sorted(str(item) for item in layers), actual=page.get("reality_layer"))
        for shot_index, shot in enumerate(page_shots[:-1]):
            if source_is_transition(shot):
                audit.fail(
                    "F-PAGE",
                    f"{page_path}.source_shot_nos[{shot_index}]",
                    "black/sound transition may only end its scene/reality page",
                    actual=shot.get("shot_no"),
                )

        anchor = page.get("spatial_anchor_panel")
        anchor_match = re.fullmatch(r"PANEL-([1-9])", anchor) if isinstance(anchor, str) else None
        if not anchor_match:
            audit.fail("F-PAGE-ANCHOR", f"{page_path}.spatial_anchor_panel", "spatial anchor must identify one panel on this page")
        else:
            anchor_index = int(anchor_match.group(1)) - 1
            if anchor_index >= len(panels) or not isinstance(panels[anchor_index], dict) or panels[anchor_index].get("panel_kind") != "source":
                audit.fail("F-PAGE-ANCHOR", f"{page_path}.spatial_anchor_panel", "spatial anchor must point to a source panel")
            else:
                anchor_source = source_lookup.get(panels[anchor_index].get("source_shot"), {})
                log = logs_by_scene.get(str(anchor_source.get("scene_id")), {})
                if not source_is_spatial_anchor(anchor_source, log):
                    audit.fail("F-PAGE-ANCHOR", f"{page_path}.spatial_anchor_panel", "declared source panel lacks reliable structured spatial evidence")
                reliable_source_numbers = [
                    int(shot["shot_no"])
                    for shot in page_shots
                    if is_int(shot.get("shot_no"))
                    and source_is_spatial_anchor(shot, logs_by_scene.get(str(shot.get("scene_id")), {}))
                ]
                if reliable_source_numbers and panels[anchor_index].get("source_shot") != reliable_source_numbers[0]:
                    audit.fail(
                        "F-PAGE-ANCHOR",
                        f"{page_path}.spatial_anchor_panel",
                        "spatial_anchor_panel must point to the first reliable source panel",
                        expected=reliable_source_numbers[0],
                        actual=panels[anchor_index].get("source_shot"),
                    )

        expected_completion = "source_only" if len(page_native) == 9 else "derived_angle"
        if page.get("completion_mode") != expected_completion:
            audit.fail("F-PAGE", f"{page_path}.completion_mode", "completion mode does not match page composition", expected=expected_completion, actual=page.get("completion_mode"))

    if native_order != source_order:
        audit.fail("F-SOURCE-COVERAGE", "panel_plan.pages", "every source shot must have exactly one native panel in source order", expected=source_order, actual=native_order)


def validate_prompt_structure(prompt: str, expected_page_count: int, audit: Audit) -> None:
    text = normalize_markdown(prompt)
    page_matches = list(re.finditer(r"(?m)^# (PAGE-[^\s]+)\s*$", text))
    ids = [match.group(1) for match in page_matches]
    expected_ids = [f"PAGE-{index:02d}" for index in range(1, expected_page_count + 1)]
    if ids != expected_ids:
        audit.fail("F-PROMPT-PAGE", "final_prompts.pages", "prompt pages must be unique, continuous, and match panel_plan", expected=expected_ids, actual=ids)
    if not page_matches:
        return
    if text[: page_matches[0].start()].strip():
        audit.fail("F-PROMPT-PAGE", "final_prompts.preamble", "text before PAGE-01 is forbidden")
    layer_pattern = re.compile(r"(?m)^(" + "|".join(re.escape(name) for name in LAYER_ORDER) + r"):\s*$")
    for index, match in enumerate(page_matches):
        end = page_matches[index + 1].start() if index + 1 < len(page_matches) else len(text)
        body = text[match.end():end]
        marker_names = re.findall(r"@CANON\(([^)]+)\)", body)
        if marker_names != list(PROMPT_CANON_MARKER_ORDER):
            audit.fail(
                "F-PROMPT-CANON",
                f"final_prompts.{match.group(1)}.canon_markers",
                "each page must contain the four canon markers exactly once in their fixed positions",
                expected=list(PROMPT_CANON_MARKER_ORDER),
                actual=marker_names,
            )
        layers = [item.group(1) for item in layer_pattern.finditer(body)]
        if layers != list(LAYER_ORDER):
            audit.fail("F-PROMPT-LAYERS", f"final_prompts.{match.group(1)}", "layers must occur exactly once in the fixed order", expected=list(LAYER_ORDER), actual=layers)
        panel_ids = re.findall(r"(?m)^PANEL-([^:\s]+):\s*", body)
        expected_panels = [str(number) for number in range(1, 10)]
        if panel_ids != expected_panels:
            audit.fail("F-PROMPT-PANELS", f"final_prompts.{match.group(1)}.panels", "panel IDs must be PANEL-1 through PANEL-9 in order", expected=expected_panels, actual=panel_ids)
        known_spans = {(item.start(), item.end()) for item in layer_pattern.finditer(body)}
        for candidate in re.finditer(r"(?m)^([A-Z][A-Z0-9_ /-]{2,}):\s*$", body):
            if (candidate.start(), candidate.end()) in known_spans:
                continue
            name = candidate.group(1)
            if re.fullmatch(r"PANEL-[1-9]", name):
                continue
            if re.search(r"(?:LAYER|LOCK|ANCHOR|CONSTRAINTS|DELIVERABLE)$", name):
                audit.fail("F-PROMPT-LAYERS", f"final_prompts.{match.group(1)}.{name}", "unknown top-level layer-like heading is forbidden")


def deep_differences(expected: Any, actual: Any, path: str = "panel_plan", limit: int = 80) -> list[tuple[str, Any, Any]]:
    differences: list[tuple[str, Any, Any]] = []

    def walk(left: Any, right: Any, current: str) -> None:
        if len(differences) >= limit:
            return
        if type(left) is not type(right):
            differences.append((current, left, right))
            return
        if isinstance(left, dict):
            for key in sorted(set(left) | set(right)):
                child = f"{current}.{key}"
                if key not in left:
                    differences.append((child, "<absent>", right[key]))
                elif key not in right:
                    differences.append((child, left[key], "<absent>"))
                else:
                    walk(left[key], right[key], child)
                if len(differences) >= limit:
                    return
            return
        if isinstance(left, list):
            if len(left) != len(right):
                differences.append((f"{current}.length", len(left), len(right)))
            for index, (left_item, right_item) in enumerate(zip(left, right)):
                walk(left_item, right_item, f"{current}[{index}]")
                if len(differences) >= limit:
                    return
            return
        if left != right:
            differences.append((current, left, right))

    walk(expected, actual, path)
    return differences


def rebuild_expected(
    deriver: ModuleType,
    shot_data: dict[str, Any],
    shot_path: Path,
    canon_path: Path,
    audit: Audit,
) -> dict[str, Any] | None:
    try:
        source_errors = deriver.validate_source_contract(shot_data)
    except Exception as exc:
        audit.tool("deriver.validate_source_contract", f"source contract checker crashed: {type(exc).__name__}: {exc}")
        return None
    if not isinstance(source_errors, list):
        audit.tool("deriver.validate_source_contract", "source contract checker must return a list")
        return None
    for message in source_errors:
        audit.fail("F-SOURCE-CONTRACT", "shot_data", str(message))
    if source_errors:
        return None
    try:
        artifacts = deriver.derive_artifacts(shot_data, shot_path, canon_path, release_ready=True)
    except Exception as exc:
        code = str(getattr(exc, "code", ""))
        message = str(exc)
        if code in REVIEW_CODES:
            audit.review(code, str(getattr(exc, "page", "derivation")), message)
        elif code:
            audit.fail(code, str(getattr(exc, "page", "derivation")), message)
        elif isinstance(getattr(exc, "errors", None), list):
            for error in exc.errors:
                audit.fail("F-SOURCE-CONTRACT", "shot_data", str(error))
        else:
            audit.tool("deriver.derive_artifacts", f"deterministic rebuild crashed: {type(exc).__name__}: {message}")
        return None
    if not isinstance(artifacts, dict):
        audit.tool("deriver.derive_artifacts", "deterministic rebuild must return an artifact object")
        return None
    for key in ("panel_plan", "final_prompts"):
        if key not in artifacts:
            audit.tool("deriver.derive_artifacts", f"deterministic rebuild omitted {key}")
            return None
    return artifacts


def is_legacy_plan(plan: dict[str, Any]) -> bool:
    version = plan.get("version")
    schema = plan.get("schema_version")
    if plan.get("skill") == SKILL_NAME and (version != SKILL_VERSION or schema != SCHEMA_VERSION):
        return True
    return False


def build_report(
    audit: Audit,
    plan: dict[str, Any] | None,
    canon_version: str,
    canon_hash: str,
    prompt_text: str | None,
) -> dict[str, Any]:
    pages = plan.get("pages", []) if isinstance(plan, dict) else []
    source = plan.get("source", {}) if isinstance(plan, dict) else {}
    return {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "schema_version": SCHEMA_VERSION,
        "status": audit.status,
        "exit_code": audit.exit_code,
        "release_ready": audit.exit_code == EXIT_PASS and bool(plan and plan.get("release_ready") is True),
        "source": source if isinstance(source, dict) else {},
        "canon": {"version": canon_version, "sha256": canon_hash},
        "metrics": {
            "page_count": len(pages) if isinstance(pages, list) else 0,
            "prompt_characters": len(normalize_text(prompt_text or "")),
        },
        "findings": [item.as_dict() for item in audit.findings],
    }


def validate_files(args: argparse.Namespace) -> tuple[int, dict[str, Any], str]:
    audit = Audit()
    panel_path = Path(args.panel_plan)
    prompt_path = Path(args.final_prompts)
    shot_path = Path(args.shot_data)
    canon_path = Path(args.canon)
    skill_dir = Path(__file__).resolve().parents[1]
    active_version = read_version(skill_dir, audit)
    canon_blocks, canon_hash = parse_canon(canon_path, active_version or SKILL_VERSION, audit)
    plan = load_json_object(panel_path, "panel_plan", audit)
    shot_data = load_json_object(shot_path, "shot_data", audit)
    prompt = load_text(prompt_path, "final_prompts", audit)
    compiled = compile_prompt(prompt or "", canon_blocks, audit) if prompt is not None else ""

    legacy = bool(plan and is_legacy_plan(plan))
    if legacy:
        audit.fail(
            "F-LEGACY-REGENERATE",
            "panel_plan.version",
            "legacy su-image9 packages are read-only; regenerate from original shot_data",
            expected=SKILL_VERSION,
            actual=plan.get("version"),
        )
    if shot_data is not None:
        source_gate(shot_data, shot_path, plan, audit)
    if plan is not None and shot_data is not None and not legacy:
        validate_panel_plan(plan, shot_data, canon_hash, audit)
    if prompt is not None and plan is not None and not legacy:
        pages = plan.get("pages")
        validate_prompt_structure(prompt, len(pages) if isinstance(pages, list) else 0, audit)

    deriver = load_deriver(Path(__file__).with_name("derive_su_image9_prompt_package.py"), audit)
    if deriver is not None and plan is not None and shot_data is not None and prompt is not None and not legacy:
        artifacts = rebuild_expected(deriver, shot_data, shot_path, canon_path, audit)
        if artifacts is not None:
            expected_plan = artifacts.get("panel_plan")
            expected_prompt = artifacts.get("final_prompts")
            if not isinstance(expected_plan, dict) or not isinstance(expected_prompt, str):
                audit.tool("deriver.derive_artifacts", "deterministic rebuild returned invalid panel_plan/final_prompts types")
            else:
                for path, expected, actual in deep_differences(expected_plan, plan):
                    audit.fail("F-PLAN-DRIFT", path, "panel_plan differs from deterministic shot_data derivation", expected=expected, actual=actual)
                expected_normalized = normalize_markdown(expected_prompt)
                actual_normalized = normalize_markdown(prompt)
                if actual_normalized != expected_normalized:
                    audit.fail(
                        "F-PROMPT-DRIFT",
                        "final_prompts",
                        "final prompt differs from deterministic panel_plan rendering",
                        expected=sha256_bytes(expected_normalized.encode("utf-8")),
                        actual=sha256_bytes(actual_normalized.encode("utf-8")),
                    )

    report = build_report(audit, plan, active_version or SKILL_VERSION, canon_hash, prompt)
    return audit.exit_code, report, compiled


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canon", required=True, type=Path)
    parser.add_argument("--panel-plan", required=True, type=Path)
    parser.add_argument("--final-prompts", required=True, type=Path)
    parser.add_argument("--shot-data", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args(argv)


def write_outputs(report_path: Path, out_path: Path, report: dict[str, Any], compiled: str) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_path.write_text(normalize_text(compiled).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        code, report, compiled = validate_files(args)
    except Exception as exc:  # Last-resort reporting: an unexpected crash is never PASS.
        code = EXIT_TOOL_ERROR
        report = {
            "skill": SKILL_NAME,
            "version": SKILL_VERSION,
            "schema_version": SCHEMA_VERSION,
            "status": "TOOL_ERROR",
            "exit_code": code,
            "release_ready": False,
            "source": {},
            "canon": {"version": "", "sha256": ""},
            "metrics": {"page_count": 0, "prompt_characters": 0},
            "findings": [
                Finding("F-TOOL", "FAIL", "validator", f"unexpected validator failure: {type(exc).__name__}: {exc}").as_dict()
            ],
        }
        compiled = ""
    try:
        write_outputs(Path(args.report), Path(args.out), report, compiled if code == EXIT_PASS else "")
    except Exception as exc:
        print(f"TOOL_ERROR: cannot write validator outputs: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    print(f"{report['status']}: su-image9 validation finished with exit code {code}.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
