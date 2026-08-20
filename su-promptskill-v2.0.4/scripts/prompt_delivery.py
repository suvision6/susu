#!/usr/bin/env python3
"""Build and validate immutable-source prompt-plan/2.0.4 deliveries."""

from __future__ import annotations

import argparse
import copy
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import hashlib
import html
import io
import json
import math
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence
import unicodedata
import xml.etree.ElementTree as ET
import zipfile


SKILL_NAME = "su-promptskill"
SKILL_VERSION = "2.0.4"
PLAN_CONTRACT_NAME = "prompt-plan"
PLAN_CONTRACT_VERSION = "2.0.4"
SOURCE_MODES = {
    "upstream_structured",
    "partial_storyboard",
    "standalone_storyboard",
    "direct_material",
}
COMPILER_INPUTS_CONTRACT = "prompt-compiler-inputs/2.0.4"
VALIDATION_CONTRACT_NAME = "prompt-validation"
VALIDATION_CONTRACT_VERSION = "2.0.4"
FORMAL_DELIVERY_SUFFIXES = {
    "plan": "prompt-plan.json",
    "markdown": "prompt-table.md",
    "xlsx": "prompt-table.xlsx",
    "validation": "prompt-validation.json",
}
PROMPT_TABLE_COLUMNS = (
    "Prompt 段号",
    "来源镜号",
    "总时长（秒）",
    "Prompt",
)

XLSX_ROW_HEIGHT_LIMIT = Decimal("1000")
XLSX_PROMPT_WIDTH_MIN = 160
XLSX_PROMPT_WIDTH_MAX = 255
NO_SOURCE_SOUND_LINE = (
    "本单元无来源明确的全局音效、环境音、空间混音或特殊声音说明；"
    "各 Cut 仅保留其来源声音事实。"
)

# grouping-rules.md owns these versioned strategy values.
GROUPING_POLICIES: dict[str, dict[str, Decimal | int]] = {
    "seedance-2.5-default": {
        "max_duration_seconds": Decimal("30"),
        "max_cuts": 10,
    },
    "seedance-2.0-default": {
        "max_duration_seconds": Decimal("15"),
        "max_cuts": 5,
    },
    "generic-video": {
        "max_duration_seconds": Decimal("15"),
        "max_cuts": 5,
    },
}
DEFAULT_GROUPING_POLICY = {
    "max_duration_seconds": Decimal("15"),
    "max_cuts": 5,
}
BOUNDARY_COMPATIBILITY_KEYS = (
    "scene",
    "reality_layer",
    "subjects",
    "action",
    "space",
    "time",
    "continuity",
    "dialogue",
    "narrative_intent",
    "camera_state",
)
COMPATIBILITY_KEYS = BOUNDARY_COMPATIBILITY_KEYS
GROUPING_REVIEW_CONTRACT = "grouping-review/2.0.3"
GROUPING_PARTITION_POLICY = "scene-global-dp-v1"
GROUPING_BOUNDARY_CLASSES = {
    "hard_split",
    "prefer_join",
    "prefer_split",
}
GROUPING_HARD_EVIDENCE = {
    "scene_change",
    "reality_layer_change",
    "time_change",
    "source_unavailable",
}
GROUPING_JOIN_EVIDENCE = {
    "same_scene",
    "same_reality_layer",
    "same_time",
    "boundary_state_match",
    "action_continuation",
    "causal_continuation",
    "question_answer",
    "dialogue_exchange",
}
GROUPING_SPLIT_EVIDENCE = {
    "protected_performance",
    "camera_state_discontinuity",
    "subject_focus_reset",
    "narrative_phase_change",
    "information_density",
}
GROUPING_CAPACITY_REASONS = {
    "profile_duration_limit",
    "profile_cut_limit",
}
EMOTION_GUARDRAIL_KEYS = (
    "adds_emotion_stage",
    "changes_goal_or_relationship",
    "changes_location_or_prop_state",
    "changes_plot_result",
    "adds_camera_or_environment_fact",
)
SUPPORTED_ADAPTERS = {
    "explicit-cut-zh-v1",
    "compact-cut-zh-v1",
    "seedance-2.5-structured-zh-v1",
}
GENERATION_MODES = {
    "t2v",
    "i2v",
    "v2v",
    "r2v",
    "flf2v",
    "edit",
    "extend",
}
REFERENCE_STATE_MODES = {
    "i2v",
    "v2v",
    "r2v",
    "flf2v",
    "edit",
    "extend",
}
REFERENCE_CONVENTIONS = {
    "seedance-indexed-at-v1",
    "indexed-prefix-v1",
    "preserve-explicit-v1",
}
TASK_PRIMARY_VALUES = {"generate", "edit", "extend"}
OFFICIAL_TASK_TYPE_VALUES = {
    "text-to-video",
    "reference-generation",
    "video-editing",
    "video-extension",
    "first-or-first-last-frame",
}
CONTENT_ROLE_VALUES = {
    "first_frame",
    "last_frame",
    "reference_image",
    "reference_video",
    "reference_audio",
}
INPUT_TOPOLOGY_VALUES = {
    "text-only",
    "image-reference",
    "video-reference",
    "audio-reference",
    "multimodal",
}
TASK_MODULE_VALUES = {
    "first-frame",
    "last-frame",
    "multi-reference",
    "keyframe",
    "grid-storyboard",
    "blockout",
    "audio-edit",
    "long-form",
    "camera-reference",
    "emotion-reference",
}
LEGACY_MODE_TASK_MAP = {
    "t2v": ("generate", "text-only", ()),
    "i2v": ("generate", "image-reference", ()),
    "v2v": ("generate", "video-reference", ()),
    "r2v": ("generate", "multimodal", ("multi-reference",)),
    "flf2v": (
        "generate",
        "image-reference",
        ("first-frame", "last-frame"),
    ),
    "edit": ("edit", "video-reference", ()),
    "extend": ("extend", "video-reference", ()),
}
SAFE_REFERENCE_PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,15}$")
REFERENCE_ROLE_MEDIA: dict[str, set[str]] = {
    "subject_identity": {"image", "video"},
    "appearance": {"image", "video"},
    "pose": {"image"},
    "scene_state": {"image", "video"},
    "style": {"image", "video"},
    "motion_reference": {"video"},
    "camera_motion": {"video"},
    "audio_reference": {"audio", "video"},
    "first_frame": {"image"},
    "last_frame": {"image"},
    "edit_source": {"image", "video"},
    "extension_source": {"video"},
}
REFERENCE_ROLE_LABELS = {
    "subject_identity": "主体身份参考",
    "appearance": "外观参考",
    "pose": "姿势参考",
    "scene_state": "场景状态参考",
    "style": "风格参考",
    "motion_reference": "运动参考",
    "camera_motion": "摄影机运动参考",
    "audio_reference": "声音参考",
    "first_frame": "首帧",
    "last_frame": "末帧",
    "edit_source": "编辑来源",
    "extension_source": "延展来源",
}
ANTI_SLOP_TERMS = ("电影感", "史诗", "震撼", "大师级", "8K")
QUOTED_TEXT_RE = re.compile(r"“[^”]*”|\"[^\"]*\"|‘[^’]*’|'[^']*'")
PROFILE_GROUPING_KEYS = {
    "standalone_when_duration_gt_seconds",
    "grouping_max_duration_seconds",
    "preferred_group_size",
    "semantic_compatibility",
    "grouping_strategy",
}
CUT_LABELS = tuple(f"Cut {index}" for index in range(1, 11))
SCENE_CONTEXT_KEYS = (
    "scene",
    "location",
    "time",
    "time_of_day",
    "reality_layer",
    "environment",
    "environment_description",
    "initial_continuity",
)

BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
    "seedance-2.5-default": {
        "profile_id": "seedance-2.5-default",
        "model_name": "Seedance 2.5",
        "model_id": "doubao-seedance-2-5-260628",
        "official_evidence": {
            "prompt_guide_updated": "2026-08-07T20:30:16+08:00",
            "prompt_optimizer": "sd25-pe/0.1.0",
            "prompt_optimizer_sha256": (
                "4b3a0e06a035bed32d3599e000e4461f"
                "d147cd2e581c83f96379657501b1b43c"
            ),
        },
        "capabilities": {
            "max_clip_duration_seconds": 30,
            "supports_multi_cut": True,
            "supports_explicit_cut_timeline": True,
            "supports_dialogue": True,
            "supported_generation_modes": [
                "t2v",
                "i2v",
                "v2v",
                "r2v",
                "flf2v",
                "edit",
                "extend",
            ],
            "supported_media_types": ["image", "video", "audio"],
            "reference_tag_convention": {
                "convention_id": "preserve-explicit-v1"
            },
            "asset_limits": {
                "max_total": 50,
                "image": {
                    "max_count": 30,
                    "min_dimension_pixels": 300,
                    "max_dimension_pixels": 6000,
                    "min_total_pixels": 409600,
                    "max_total_pixels": 8295044,
                    "min_aspect_ratio": 0.4,
                    "max_aspect_ratio": 2.5,
                },
                "video": {
                    "max_count": 10,
                    "min_item_duration_seconds": 2,
                    "max_item_duration_seconds": 30,
                    "max_total_duration_seconds": 30,
                },
                "audio": {
                    "max_count": 10,
                    "min_item_duration_seconds": 2,
                    "max_item_duration_seconds": 30,
                    "max_total_duration_seconds": 30,
                },
            },
            "request_constraints": {
                "ratios": ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "adaptive"],
                "resolutions": ["480p", "720p"],
                "output_formats": ["mp4", "mov"],
                "duration_seconds": {"minimum": 4, "maximum": 30, "automatic": -1},
                "content_roles": sorted(CONTENT_ROLE_VALUES),
                "official_task_types": sorted(OFFICIAL_TASK_TYPE_VALUES),
            },
        },
        "prompt_adapter_id": "seedance-2.5-structured-zh-v1",
    },
    "seedance-2.0-default": {
        "profile_id": "seedance-2.0-default",
        "model_name": "Seedance 2.0",
        "model_id": "doubao-seedance-2-0-260128",
        "capabilities": {
            "max_clip_duration_seconds": 15,
            "supports_multi_cut": True,
            "supports_explicit_cut_timeline": True,
            "supports_dialogue": True,
            "supported_generation_modes": [
                "t2v",
                "i2v",
                "v2v",
                "r2v",
                "flf2v",
                "edit",
                "extend",
            ],
            "reference_tag_convention": {
                "convention_id": "seedance-indexed-at-v1"
            },
            "request_constraints": {
                "ratios": ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "adaptive"],
                "output_formats": ["mp4"],
            },
        },
        "prompt_adapter_id": "explicit-cut-zh-v1",
    },
    "generic-video": {
        "profile_id": "generic-video",
        "model_name": "Generic Video Model",
        "capabilities": {
            "max_clip_duration_seconds": 15,
            "supports_multi_cut": True,
            "supports_explicit_cut_timeline": True,
            "supports_dialogue": True,
            "supported_generation_modes": [
                "t2v",
                "i2v",
                "v2v",
                "r2v",
                "flf2v",
                "edit",
                "extend",
            ],
            "reference_tag_convention": {
                "convention_id": "indexed-prefix-v1",
                "image_prefix": "image-",
                "video_prefix": "video-",
            },
            "request_constraints": {
                "ratios": ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "adaptive"],
                "output_formats": ["mp4"],
            },
        },
        "prompt_adapter_id": "explicit-cut-zh-v1",
    },
}


class DeliveryError(ValueError):
    """Raised for unreadable CLI material, not per-unit delivery diagnostics."""


class GroupingReviewError(DeliveryError):
    """Raised before delivery when the mandatory boundary review is invalid."""


class AssetBindingError(DeliveryError):
    """Raised before delivery when an explicit mapped asset contract is invalid."""


def _ascii_kebab_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    known_suffixes = (
        "-shot-data",
        "-shotdata",
        "-storyboard",
        "-screenplay",
        "-script",
        "-source",
    )
    changed = True
    while changed and slug:
        changed = False
        for suffix in known_suffixes:
            if slug.endswith(suffix):
                slug = slug[: -len(suffix)].rstrip("-")
                changed = True
                break
    return slug


def derive_delivery_slug(
    input_name: str | Path | None,
    source_document: Any = None,
) -> str:
    """Derive a deterministic ASCII delivery slug from the actual input."""
    stem = Path(input_name).stem if input_name is not None else ""
    slug = _ascii_kebab_slug(stem)
    if not slug and isinstance(source_document, dict):
        slug = _ascii_kebab_slug(
            _clean_text(source_document.get("project_id"))
        )
    if not slug:
        digest = sha256_json(source_document)[:8]
        slug = f"source-{digest}"
    return slug


def delivery_file_map(delivery_slug: str) -> dict[str, str]:
    slug = _ascii_kebab_slug(delivery_slug)
    if not slug:
        raise DeliveryError("Delivery slug must contain an ASCII identifier")
    return {
        role: f"{slug}-{suffix}"
        for role, suffix in FORMAL_DELIVERY_SUFFIXES.items()
    }


def _plan_delivery_file_map(plan: Mapping[str, Any]) -> dict[str, str]:
    delivery = plan.get("delivery")
    if not isinstance(delivery, dict):
        raise DeliveryError("prompt plan is missing delivery metadata")
    slug = _clean_text(delivery.get("slug"))
    expected = delivery_file_map(slug)
    if delivery.get("files") != expected:
        raise DeliveryError("prompt plan delivery filenames are invalid")
    return expected


def _reject_json_constant(value: str) -> None:
    raise DeliveryError(f"JSON contains non-finite number: {value}")


def load_json(path: Path | str) -> Any:
    """Read strict UTF-8 JSON without accepting NaN or Infinity."""
    json_path = Path(path)
    try:
        with json_path.open("r", encoding="utf-8") as handle:
            return json.load(handle, parse_constant=_reject_json_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeliveryError(f"Cannot read JSON {json_path}: {exc}") from exc


def canonical_json(value: Any) -> str:
    """Return the stable JSON representation used by all hashes."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DeliveryError(f"Value is not canonical JSON: {exc}") from exc


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def source_observed_hash(document: Mapping[str, Any]) -> str:
    without_declared_hash = {
        key: value for key, value in document.items() if key != "content_hash"
    }
    return sha256_json(without_declared_hash)


def _issue(
    code: str,
    severity: str,
    scope: str,
    path: str,
    message: str,
    blocks: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "scope": scope,
        "path": path,
        "message": message,
        "blocks": list(blocks),
    }


def _deduplicate_issues(issues: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for raw_issue in issues:
        issue = dict(raw_issue)
        key = (
            str(issue.get("code", "")),
            str(issue.get("severity", "")),
            str(issue.get("path", "")),
            str(issue.get("message", "")),
        )
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def _duration_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidOperation
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidOperation
    try:
        duration = Decimal(str(value))
    except InvalidOperation as exc:
        raise InvalidOperation from exc
    if not duration.is_finite() or duration <= 0:
        raise InvalidOperation
    return duration


def _json_number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _seconds_text(value: Any) -> str:
    if (
        value is None
        or isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (isinstance(value, float) and not math.isfinite(value))
    ):
        return "来源未提供"
    try:
        duration = Decimal(str(value))
    except InvalidOperation:
        return "来源未提供"
    if not duration.is_finite() or duration < 0:
        return "来源未提供"
    text = format(duration, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _has_terminal_punctuation(text: str) -> bool:
    core = text.rstrip()
    while core.endswith(("”", "’", '"', "'", "）", "】", "》")):
        core = core[:-1].rstrip()
    return core.endswith(("。", "！", "？", "!", "?"))


def _with_terminal_punctuation(text: str) -> str:
    return text if not text or _has_terminal_punctuation(text) else text + "。"


def _as_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _as_items(value: Any) -> list[Any]:
    if value in (None, "", [], {}):
        return []
    return copy.deepcopy(value) if isinstance(value, list) else [copy.deepcopy(value)]


def _clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _map_outside_quotes(text: str, transform: Any) -> str:
    parts: list[str] = []
    cursor = 0
    for match in QUOTED_TEXT_RE.finditer(text):
        parts.append(transform(text[cursor : match.start()]))
        parts.append(match.group(0))
        cursor = match.end()
    parts.append(transform(text[cursor:]))
    return "".join(parts)


def _preserve_text(text: str) -> str:
    """Preserve source/decision wording; anti-slop is audit-only."""
    return text.strip()


def _anti_slop_terms_outside_quotes(text: str) -> list[str]:
    outside = _map_outside_quotes(text, lambda segment: segment)
    outside = QUOTED_TEXT_RE.sub("", outside)
    return [term for term in ANTI_SLOP_TERMS if term in outside]


def _anti_slop_terms_in_value(value: Any) -> list[str]:
    terms: set[str] = set()
    if isinstance(value, str):
        terms.update(term for term in ANTI_SLOP_TERMS if term in value)
    elif isinstance(value, dict):
        for child in value.values():
            terms.update(_anti_slop_terms_in_value(child))
    elif isinstance(value, list):
        for child in value:
            terms.update(_anti_slop_terms_in_value(child))
    return sorted(terms)


def _reference_tag_pattern(
    convention: Mapping[str, Any], media_type: str, anchored: bool
) -> re.Pattern[str] | None:
    convention_id = _clean_text(convention.get("convention_id"))
    if convention_id == "seedance-indexed-at-v1":
        if media_type == "image":
            prefix = "@Image"
        elif media_type == "video":
            prefix = "@Video"
        else:
            return None
    elif convention_id == "indexed-prefix-v1":
        prefix = _clean_text(convention.get(f"{media_type}_prefix"))
        if not prefix:
            return None
    elif convention_id == "preserve-explicit-v1":
        return None
    else:
        return None
    escaped = re.escape(prefix)
    expression = rf"{escaped}[1-9][0-9]*"
    if anchored:
        expression = rf"^{expression}$"
    else:
        expression = rf"(?<![A-Za-z0-9_-]){expression}(?![A-Za-z0-9_-])"
    return re.compile(expression)


def _reference_tag_valid(
    tag: str, media_type: str, profile: Mapping[str, Any]
) -> bool:
    convention = (
        profile.get("capabilities", {}).get("reference_tag_convention", {})
        if isinstance(profile, dict)
        else {}
    )
    if _clean_text(convention.get("convention_id")) == "preserve-explicit-v1":
        return bool(tag.strip()) and not any(
            character in tag for character in ("\n", "\r", "\x00")
        )
    pattern = _reference_tag_pattern(convention, media_type, anchored=True)
    return pattern is not None and pattern.fullmatch(tag) is not None


def _reference_tags(
    text: str,
    profile: Mapping[str, Any],
    known_tags: Sequence[str] = (),
) -> list[str]:
    convention = profile.get("capabilities", {}).get(
        "reference_tag_convention", {}
    )
    if _clean_text(convention.get("convention_id")) == "preserve-explicit-v1":
        matches = [
            (text.find(tag), tag)
            for tag in known_tags
            if tag and text.find(tag) >= 0
        ]
        return [tag for _, tag in sorted(matches)]
    matches: list[tuple[int, str]] = []
    for media_type in ("image", "video", "audio"):
        pattern = _reference_tag_pattern(convention, media_type, anchored=False)
        if pattern is None:
            continue
        matches.extend((match.start(), match.group(0)) for match in pattern.finditer(text))
    return [tag for _, tag in sorted(matches)]


def _render_descriptive_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if not isinstance(value, dict):
        return canonical_json(value) if value is not None else ""

    description = ""
    for key in ("description", "action", "behavior", "text", "notes", "value"):
        candidate = _clean_text(value.get(key))
        if candidate:
            description = candidate
            break
    subject = ""
    for key in ("character", "subject", "actor", "speaker"):
        candidate = _clean_text(value.get(key))
        if candidate:
            subject = candidate
            break
    if description and subject:
        return f"{subject}：{description}"
    if description:
        return description
    return canonical_json(value)


def _dialogue_texts(dialogue: Sequence[Any]) -> list[str]:
    texts: list[str] = []
    for item in dialogue:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = _clean_text(item.get("text"))
        else:
            text = ""
        if text:
            texts.append(text)
    return texts


def _render_dialogue(item: Any) -> str:
    if isinstance(item, str):
        return f"“{item.strip()}”" if item.strip() else ""
    if not isinstance(item, dict):
        return ""
    text = _clean_text(item.get("text"))
    if not text:
        return ""
    speaker = _clean_text(item.get("speaker"))
    delivery = _clean_text(item.get("delivery"))
    prefix = speaker
    if delivery:
        prefix = f"{prefix}（{delivery}）" if prefix else f"（{delivery}）"
    return f"{prefix}：“{text}”" if prefix else f"“{text}”"


def _has_prompt_content(shot: Mapping[str, Any]) -> bool:
    return any(
        (
            _clean_text(shot.get("rendered_shot_description")),
            bool(shot.get("blocking")),
            bool(shot.get("visible_behavior")),
            bool(shot.get("dialogue")),
            bool(shot.get("delta_text")),
            bool(shot.get("subjects")),
            bool(shot.get("scene_material")),
            bool(shot.get("scene_context")),
            bool(shot.get("visible_props")),
            bool(shot.get("end_state")),
            bool(shot.get("continuity")),
            bool(shot.get("continuity_updates")),
            bool(shot.get("audio")),
            bool(shot.get("allowed_lighting_changes")),
            any(
                value not in (None, "", [], {})
                for value in (
                    shot.get("lighting_style", {}).values()
                    if isinstance(shot.get("lighting_style"), dict)
                    else ()
                )
            ),
        )
    )


SOURCE_SOUND_CUE_RE = re.compile(
    r"背景音|传来|声音|声响|低吼|震动|撞击|呼吸|喘气|沉默|无声|"
    r"脚步声|雨声|风声|摩擦声|碰撞声|爆裂声"
)


def _source_sound_clauses(text: str) -> list[str]:
    clauses: list[str] = []
    for raw_clause in re.split(r"(?<=[。！？])|\n+", text):
        clause = raw_clause.strip()
        if clause and SOURCE_SOUND_CUE_RE.search(clause):
            clauses.append(clause)
    return _unique_strings(clauses)


def _derive_source_audio_by_shot(
    document: Mapping[str, Any],
    raw_shots: Sequence[Any],
) -> list[list[str]]:
    fact_index: dict[str, Mapping[str, Any]] = {}
    for beat in document.get("beats", []):
        if not isinstance(beat, dict):
            continue
        for fact in beat.get("facts", []):
            if not isinstance(fact, dict):
                continue
            fact_id = _clean_text(fact.get("fact_id"))
            if fact_id and fact_id not in fact_index:
                fact_index[fact_id] = fact
    declared_sound_ids = {
        _clean_text(fact_id)
        for event in document.get("screen_events", [])
        if isinstance(event, dict)
        for fact_id in event.get("sound_fact_ids", [])
        if _clean_text(fact_id)
    }
    result: list[list[str]] = []
    for raw_shot in raw_shots:
        if not isinstance(raw_shot, dict):
            result.append([])
            continue
        fact_ids = [
            _clean_text(value)
            for value in raw_shot.get("covered_fact_ids", [])
            if _clean_text(value)
        ]
        for phase in raw_shot.get("shot_phases", []):
            if isinstance(phase, dict):
                fact_ids.extend(
                    _clean_text(value)
                    for value in phase.get("sound_fact_ids", [])
                    if _clean_text(value)
                )
        audio: list[str] = []
        for fact_id in _unique_strings(fact_ids):
            fact = fact_index.get(fact_id)
            if not isinstance(fact, Mapping):
                continue
            if _clean_text(fact.get("type")) == "dialogue":
                continue
            text = _preserve_text(
                _render_descriptive_value(
                    fact.get("text") or fact.get("source_fragment")
                )
            )
            if not text:
                continue
            if fact_id in declared_sound_ids:
                audio.extend(_source_sound_clauses(text) or [text])
            else:
                audio.extend(_source_sound_clauses(text))
        result.append(_unique_strings(audio))
    return result


def normalize_input(document: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize source material without mutating it."""
    issues: list[dict[str, Any]] = []
    if not isinstance(document, dict):
        snapshot = {
            "source": {
                "source_mode": "standalone_storyboard",
                "source_contract": None,
                "source_skill": None,
                "source_skill_version": None,
                "project_id": None,
                "source_content_hash": None,
                "observed_content_hash": None,
                "local_content_hash": sha256_json(document),
                "source_read_only": True,
                "source_shot_count": 0,
            },
            "shots": [],
            "source_global_blocked": True,
        }
        issues.append(
            _issue(
                "INPUT_MATERIAL_UNREADABLE",
                "ERROR",
                "source",
                "$",
                "输入必须先标准化为包含 shots[] 的 JSON 对象。",
                ("prompt_compilation",),
            )
        )
        return snapshot, issues

    source_global_blocked = False
    explicit_source_mode = _clean_text(document.get("source_mode"))
    contract_name = _clean_text(document.get("contract_name"))
    contract_version = _clean_text(document.get("contract_version"))
    source_skill = _clean_text(document.get("source_skill"))
    source_skill_version = _clean_text(document.get("source_skill_version"))
    claims_structured_provenance = (
        explicit_source_mode == "upstream_structured"
        or bool(contract_name)
        or bool(source_skill)
    )

    if explicit_source_mode and explicit_source_mode not in SOURCE_MODES:
        issues.append(
            _issue(
                "SOURCE_MODE_UNRECOGNIZED",
                "WARN",
                "source",
                "source_mode",
                (
                    f"来源声明了未知 source_mode：{explicit_source_mode}；"
                    "该值只作 provenance，按当前材料形状推断运行模式。"
                ),
                (),
            )
        )

    if explicit_source_mode in SOURCE_MODES:
        source_mode = explicit_source_mode
    elif claims_structured_provenance:
        source_mode = "upstream_structured"
    else:
        source_mode = "standalone_storyboard"
    source_contract = (
        f"{contract_name}/{contract_version}"
        if contract_name and contract_version
        else None
    )
    observed_hash = source_observed_hash(document)
    declared_hash = document.get("content_hash")
    local_hash = sha256_json(document)

    if declared_hash not in (None, "") and (
        not isinstance(declared_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", declared_hash) is None
    ):
        source_global_blocked = True
        issues.append(
            _issue(
                "SOURCE_HASH_INVALID",
                "ERROR",
                "source",
                "content_hash",
                (
                    "来源声明了 content_hash，但它不是 64 位小写 "
                    "SHA-256；来源保持只读。"
                ),
                ("prompt_compilation", "source_integrity"),
            )
        )
    elif declared_hash not in (None, "") and declared_hash != observed_hash:
        source_global_blocked = True
        issues.append(
            _issue(
                "SOURCE_HASH_MISMATCH",
                "ERROR",
                "source",
                "content_hash",
                "来源声明的 content_hash 与当前输入内容不一致；来源保持只读。",
                ("prompt_compilation", "source_integrity"),
            )
        )

    raw_shots = document.get("shots")
    if not isinstance(raw_shots, list):
        raw_shots = []
        source_global_blocked = True
        issues.append(
            _issue(
                "INPUT_MATERIAL_UNREADABLE",
                "ERROR",
                "source",
                "shots",
                "输入没有可读取的 shots[] 数组。",
                ("prompt_compilation",),
            )
        )
    elif not raw_shots:
        source_global_blocked = True
        issues.append(
            _issue(
                "SOURCE_SCOPE_EMPTY",
                "ERROR",
                "source",
                "shots",
                "当前输入范围没有可处理镜头。",
                ("prompt_compilation",),
            )
        )

    scene_index: dict[str, dict[str, Any]] = {}
    duplicate_scene_ids: set[str] = set()
    raw_scenes = document.get("scenes", [])
    has_scene_catalog = "scenes" in document and isinstance(raw_scenes, list)
    if has_scene_catalog:
        for scene_index_number, raw_scene in enumerate(raw_scenes):
            if not isinstance(raw_scene, dict):
                continue
            scene_id = _clean_text(raw_scene.get("scene_id"))
            if not scene_id:
                continue
            if scene_id in scene_index:
                duplicate_scene_ids.add(scene_id)
                issues.append(
                    _issue(
                        "SCENE_ID_DUPLICATE",
                        "WARN",
                        "source",
                        f"scenes[{scene_index_number}].scene_id",
                        (
                            f"顶层 scene_id {scene_id} 重复；对应镜头不猜测"
                            "场景关联。"
                        ),
                        (),
                    )
                )
                continue
            scene_index[scene_id] = copy.deepcopy(raw_scene)

    derived_audio_by_shot = _derive_source_audio_by_shot(
        document, raw_shots
    )
    normalized_shots: list[dict[str, Any]] = []
    seen_ids: dict[str, int] = {}
    for index, raw_shot in enumerate(raw_shots):
        shot_path = f"shots[{index}]"
        if not isinstance(raw_shot, dict):
            issues.append(
                _issue(
                    "INPUT_MATERIAL_UNREADABLE",
                    "ERROR",
                    "shot",
                    shot_path,
                    "该镜不是 JSON 对象，无法编译。",
                    ("prompt_compilation",),
                )
            )
            continue

        source_anti_slop_terms = _anti_slop_terms_in_value(raw_shot)
        if source_anti_slop_terms:
            issues.append(
                _issue(
                    "SOURCE_ANTI_SLOP_REVIEW",
                    "WARN",
                    "shot",
                    shot_path,
                    (
                        "来源含可能为空泛强化词、也可能是合法对白或实体名的字面："
                        f"{', '.join(source_anti_slop_terms)}；脚本原样保留，需语义审阅。"
                    ),
                    (),
                )
            )

        expected_order = index + 1
        source_shot_id = _clean_text(
            raw_shot.get("shot_id") or raw_shot.get("source_shot_id")
        )
        if not source_shot_id:
            source_shot_id = f"LOCAL-SH{expected_order:03d}"

        if source_shot_id in seen_ids:
            issues.append(
                _issue(
                    "SHOT_ID_DUPLICATE",
                    "ERROR",
                    "shot",
                    f"{shot_path}.shot_id",
                    (
                        f"镜号 {source_shot_id} 与 shots[{seen_ids[source_shot_id]}] "
                        "重复；分组 decisions 不能安全引用重复 ID。"
                    ),
                    ("decision_mapping",),
                )
            )
        else:
            seen_ids[source_shot_id] = index

        declared_order = raw_shot.get("shot_order", raw_shot.get("source_order"))
        if declared_order is not None and (
            isinstance(declared_order, bool)
            or not isinstance(declared_order, int)
            or declared_order != expected_order
        ):
            issues.append(
                _issue(
                    "SHOT_ORDER_INVALID",
                    "ERROR",
                    "shot",
                    f"{shot_path}.shot_order",
                    "shots[] 数组顺序与声明顺序不一致；仍按数组位置处理。",
                    ("grouping",),
                )
            )

        raw_duration = raw_shot.get("duration_seconds")
        duration: Decimal | None
        if raw_duration is None:
            duration = None
            issues.append(
                _issue(
                    "DURATION_MISSING",
                    "ERROR",
                    "shot",
                    f"{shot_path}.duration_seconds",
                    "来源未提供时长；该镜保持单镜且不生成伪时间。",
                    ("multi_shot_grouping", "timed_cut_timeline"),
                )
            )
        else:
            try:
                duration = _duration_decimal(raw_duration)
            except InvalidOperation:
                duration = None
                issues.append(
                    _issue(
                        "DURATION_INVALID",
                        "ERROR",
                        "shot",
                        f"{shot_path}.duration_seconds",
                        "时长必须是正有限数；当前值保持未知且禁止合镜。",
                        ("multi_shot_grouping", "timed_cut_timeline"),
                    )
                )

        camera = _as_dict(raw_shot.get("camera"))
        blocking = _as_list(raw_shot.get("blocking"))
        performance = _as_dict(raw_shot.get("performance"))
        if not performance:
            performance = {
                "emotion_intent": _clean_text(raw_shot.get("emotion_intent")),
                "visible_behavior": _as_list(raw_shot.get("visible_behavior")),
            }
        visible_behavior = _as_list(performance.get("visible_behavior"))
        emotion_intent = _clean_text(performance.get("emotion_intent"))
        dialogue = _as_list(raw_shot.get("dialogue"))
        continuity = _as_dict(raw_shot.get("continuity"))
        continuity_updates = _as_list(raw_shot.get("continuity_updates"))
        transition = _as_dict(raw_shot.get("transition_to_next"))
        rendered = _clean_text(
            raw_shot.get("rendered_shot_description")
            or raw_shot.get("visual_content")
            or raw_shot.get("description")
        )
        subjects = _as_items(
            raw_shot.get("visible_characters", raw_shot.get("subjects"))
        )
        scene_material = _as_items(
            raw_shot.get(
                "environment_behavior",
                raw_shot.get("scene_material", raw_shot.get("environment")),
            )
        )
        lighting_style = {
            "lighting": copy.deepcopy(raw_shot.get("lighting")),
            "style": copy.deepcopy(
                raw_shot.get("style", raw_shot.get("visual_style"))
            ),
        }
        audio = _as_items(raw_shot.get("audio", raw_shot.get("sound")))
        for derived_audio in derived_audio_by_shot[index]:
            if derived_audio not in audio:
                audio.append(derived_audio)
        constraints = _as_items(
            raw_shot.get(
                "constraints", raw_shot.get("directorial_constraints")
            )
        )
        delta_text = _clean_text(
            raw_shot.get("prompt_delta")
            or raw_shot.get("motion_delta")
            or raw_shot.get("extension_delta")
        )
        allowed_lighting_changes = _as_items(
            raw_shot.get("allowed_lighting_changes")
        )
        source_scene_id = _clean_text(raw_shot.get("scene_id"))
        scene_context = _as_dict(raw_shot.get("scene_context"))
        linked_scene = (
            scene_index.get(source_scene_id)
            if source_scene_id not in duplicate_scene_ids
            else None
        )
        if linked_scene is not None:
            scene_context.update(
                {
                    key: copy.deepcopy(linked_scene[key])
                    for key in SCENE_CONTEXT_KEYS
                    if key in linked_scene
                    and linked_scene[key] not in (None, "", [], {})
                }
            )
        elif source_scene_id and has_scene_catalog:
            issues.append(
                _issue(
                    "SCENE_CONTEXT_MISSING",
                    "WARN",
                    "shot",
                    f"{shot_path}.scene_id",
                    (
                        f"scene_id {source_scene_id} 未唯一关联到顶层 scenes[]；"
                        "不编造场景且不回写来源。"
                    ),
                    (),
                )
            )

        normalized = {
            "source_shot_id": source_shot_id,
            "source_order": expected_order,
            "scene_id": copy.deepcopy(raw_shot.get("scene_id")),
            "duration_seconds": _json_number(duration),
            "camera": camera,
            "blocking": blocking,
            "performance": performance,
            "visible_behavior": visible_behavior,
            "emotion_intent": emotion_intent,
            "dialogue": dialogue,
            "continuity": continuity,
            "continuity_updates": continuity_updates,
            "transition_to_next": transition,
            "rendered_shot_description": rendered,
            "subjects": subjects,
            "scene_material": scene_material,
            "scene_context": scene_context,
            "lighting_style": lighting_style,
            "visible_props": _as_items(raw_shot.get("visible_props")),
            "start_state": _as_items(raw_shot.get("start_state")),
            "end_state": _as_items(raw_shot.get("end_state")),
            "cut_design": _as_dict(raw_shot.get("cut_design")),
            "audio": audio,
            "constraints": constraints,
            "delta_text": delta_text,
            "allowed_lighting_changes": allowed_lighting_changes,
            "source_anti_slop_terms": source_anti_slop_terms,
            "source_shot_hash": sha256_json(raw_shot),
            "field_hashes": {
                "camera_hash": sha256_json(raw_shot.get("camera", {})),
                "blocking_hash": sha256_json(raw_shot.get("blocking", [])),
                "performance_hash": sha256_json(raw_shot.get("performance", {})),
                "dialogue_hash": sha256_json(raw_shot.get("dialogue", [])),
                "continuity_hash": sha256_json(
                    {
                        "continuity": raw_shot.get("continuity", {}),
                        "continuity_updates": raw_shot.get(
                            "continuity_updates", []
                        ),
                        "transition_to_next": raw_shot.get(
                            "transition_to_next", {}
                        ),
                    }
                ),
                "rendered_shot_description_hash": sha256_json(
                    raw_shot.get("rendered_shot_description", "")
                ),
                "coverage_hash": sha256_json(
                    {
                        "visible_characters": raw_shot.get(
                            "visible_characters", raw_shot.get("subjects", [])
                        ),
                        "environment_behavior": raw_shot.get(
                            "environment_behavior",
                            raw_shot.get(
                                "scene_material",
                                raw_shot.get("environment", []),
                            ),
                        ),
                        "scene_context": scene_context,
                        "visible_props": raw_shot.get("visible_props", []),
                        "end_state": raw_shot.get("end_state", []),
                        "lighting": raw_shot.get("lighting"),
                        "style": raw_shot.get(
                            "style", raw_shot.get("visual_style")
                        ),
                        "audio": raw_shot.get("audio", raw_shot.get("sound")),
                        "derived_audio": audio,
                        "constraints": raw_shot.get(
                            "constraints",
                            raw_shot.get("directorial_constraints"),
                        ),
                        "delta_text": raw_shot.get(
                            "prompt_delta",
                            raw_shot.get(
                                "motion_delta", raw_shot.get("extension_delta")
                            ),
                        ),
                        "allowed_lighting_changes": raw_shot.get(
                            "allowed_lighting_changes"
                        ),
                    }
                ),
            },
        }
        normalized["compilable_source"] = _has_prompt_content(normalized)
        if not normalized["compilable_source"]:
            issues.append(
                _issue(
                    "INPUT_MATERIAL_UNREADABLE",
                    "ERROR",
                    "shot",
                    shot_path,
                    "该镜没有可读取的画面、调度、表演或对白内容。",
                    ("prompt_compilation",),
                )
            )
        normalized_shots.append(normalized)

    source_metadata = {
        "source_mode": source_mode,
        "source_contract": source_contract,
        "source_skill": copy.deepcopy(document.get("source_skill")),
        "source_skill_version": copy.deepcopy(document.get("source_skill_version")),
        "project_id": copy.deepcopy(document.get("project_id")),
        "source_content_hash": copy.deepcopy(declared_hash),
        "observed_content_hash": observed_hash,
        "local_content_hash": local_hash,
        "source_read_only": True,
        "source_shot_count": len(normalized_shots),
    }
    return {
        "source": source_metadata,
        "shots": normalized_shots,
        "source_global_blocked": source_global_blocked,
    }, issues


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def validate_model_profile(profile: Any) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(profile, dict):
        return [
            _issue(
                "MODEL_PROFILE_INVALID",
                "ERROR",
                "model_profile",
                "model_profile",
                "Model Profile 必须是 JSON 对象。",
                ("prompt_compilation",),
            )
        ]

    profile_id = _clean_text(profile.get("profile_id"))
    model_name = _clean_text(profile.get("model_name"))
    capabilities = profile.get("capabilities")
    adapter = _clean_text(profile.get("prompt_adapter_id"))
    if not profile_id or not model_name or not isinstance(capabilities, dict):
        issues.append(
            _issue(
                "MODEL_PROFILE_INVALID",
                "ERROR",
                "model_profile",
                "model_profile",
                "Profile 缺少 profile_id、model_name 或 capabilities。",
                ("prompt_compilation",),
            )
        )
        return issues

    try:
        max_duration = _duration_decimal(
            capabilities.get("max_clip_duration_seconds")
        )
    except InvalidOperation:
        max_duration = None
    if max_duration is None:
        issues.append(
            _issue(
                "MODEL_PROFILE_INVALID",
                "ERROR",
                "model_profile",
                "model_profile.capabilities.max_clip_duration_seconds",
                "模型最大时长必须是正有限数。",
                ("prompt_compilation",),
            )
        )

    for key in (
        "supports_multi_cut",
        "supports_explicit_cut_timeline",
        "supports_dialogue",
    ):
        if not isinstance(capabilities.get(key), bool):
            issues.append(
                _issue(
                    "MODEL_PROFILE_INVALID",
                    "ERROR",
                    "model_profile",
                    f"model_profile.capabilities.{key}",
                    f"{key} 必须是布尔值。",
                    ("prompt_compilation",),
                )
            )

    supported_modes = capabilities.get("supported_generation_modes")
    if (
        not isinstance(supported_modes, list)
        or not supported_modes
        or any(mode not in GENERATION_MODES for mode in supported_modes)
        or len(set(supported_modes)) != len(supported_modes)
    ):
        issues.append(
            _issue(
                "MODEL_PROFILE_INVALID",
                "ERROR",
                "model_profile",
                "model_profile.capabilities.supported_generation_modes",
                "supported_generation_modes 必须是非空、无重复的合法 mode enum 数组。",
                ("prompt_compilation",),
            )
        )

    convention = capabilities.get("reference_tag_convention")
    convention_id = (
        _clean_text(convention.get("convention_id"))
        if isinstance(convention, dict)
        else ""
    )
    convention_valid = convention_id in REFERENCE_CONVENTIONS
    if convention_valid and convention_id == "indexed-prefix-v1":
        prefixes = [
            _clean_text(convention.get("image_prefix")),
            _clean_text(convention.get("video_prefix")),
        ]
        convention_valid = (
            all(SAFE_REFERENCE_PREFIX_RE.fullmatch(prefix) for prefix in prefixes)
            and prefixes[0] != prefixes[1]
        )
    if not convention_valid:
        issues.append(
            _issue(
                "MODEL_PROFILE_INVALID",
                "ERROR",
                "model_profile",
                "model_profile.capabilities.reference_tag_convention",
                "reference_tag_convention 必须使用受支持 enum 和安全、不重复的前缀。",
                ("prompt_compilation",),
            )
        )

    if adapter not in SUPPORTED_ADAPTERS:
        issues.append(
            _issue(
                "MODEL_PROFILE_INVALID",
                "ERROR",
                "model_profile",
                "model_profile.prompt_adapter_id",
                f"不支持的 Prompt adapter：{adapter or '<empty>'}。",
                ("prompt_compilation",),
            )
        )

    prohibited = sorted(set(_walk_keys(profile)) & PROFILE_GROUPING_KEYS)
    if prohibited:
        issues.append(
            _issue(
                "MODEL_PROFILE_INVALID",
                "ERROR",
                "model_profile",
                "model_profile",
                f"Model Profile 不得拥有合镜策略字段：{', '.join(prohibited)}。",
                ("prompt_compilation",),
            )
        )
    return issues


def resolve_model_profile(
    profile_id: str | None = None, profile_document: Any = None
) -> dict[str, Any]:
    if profile_document is not None:
        return copy.deepcopy(profile_document)
    selected_id = profile_id or "seedance-2.5-default"
    if selected_id not in BUILTIN_PROFILES:
        raise DeliveryError(f"Unknown built-in profile: {selected_id}")
    return copy.deepcopy(BUILTIN_PROFILES[selected_id])


def _runtime_value(source_document: Any, decisions: Any, key: str) -> Any:
    if isinstance(decisions, dict) and key in decisions:
        return copy.deepcopy(decisions.get(key))
    if isinstance(source_document, dict) and key in source_document:
        return copy.deepcopy(source_document.get(key))
    return None


def _task_from_legacy_mode(mode: str) -> dict[str, Any]:
    primary, topology, modules = LEGACY_MODE_TASK_MAP.get(
        mode, ("", "", ())
    )
    return {
        "primary": primary,
        "input_topology": topology,
        "modules": list(modules),
        "source": "legacy_generation_mode",
    }


def _legacy_mode_from_task(task: Mapping[str, Any]) -> str:
    primary = _clean_text(task.get("primary")).lower()
    topology = _clean_text(task.get("input_topology")).lower()
    modules = {
        _clean_text(item).lower()
        for item in task.get("modules", [])
        if isinstance(item, str)
    }
    if primary == "edit":
        return "edit"
    if primary == "extend":
        return "extend"
    if primary != "generate":
        return ""
    if {"first-frame", "last-frame"}.issubset(modules):
        return "flf2v"
    return {
        "text-only": "t2v",
        "image-reference": "i2v",
        "video-reference": "v2v",
        "audio-reference": "r2v",
        "multimodal": "r2v",
    }.get(topology, "")


def _api_content_role(item: Mapping[str, Any]) -> str:
    """Translate an internal reference responsibility to API content.role."""
    role = _clean_text(item.get("role"))
    media_type = _clean_text(item.get("media_type")).lower()
    if role == "first_frame":
        return "first_frame"
    if role == "last_frame":
        return "last_frame"
    return {
        "image": "reference_image",
        "video": "reference_video",
        "audio": "reference_audio",
    }.get(media_type, "")


def _official_task_routing(
    task: Mapping[str, Any], generation: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve Seedance 2.5's five official task types.

    The API classifies reference generation, editing, and extension from both
    ``content.role`` and prompt intent.  This object keeps those two routing
    signals explicit without placing API parameters in ``prompt_text``.
    """
    issues: list[dict[str, Any]] = []
    primary = _clean_text(task.get("primary")).lower()
    topology = _clean_text(task.get("input_topology")).lower()
    modules = {
        _clean_text(value).lower()
        for value in task.get("modules", [])
        if isinstance(value, str)
    }
    raw_role_rows: list[dict[str, str]] = []
    for item in generation.get("reference_role_map", []):
        if not isinstance(item, dict):
            continue
        content_role = _api_content_role(item)
        tag = _clean_text(item.get("tag"))
        if tag and content_role:
            raw_role_rows.append({"tag": tag, "content_role": content_role})
    role_rows: list[dict[str, str]] = []
    for tag in _unique_strings(item["tag"] for item in raw_role_rows):
        tag_roles = [
            item["content_role"]
            for item in raw_role_rows
            if item["tag"] == tag
        ]
        frame_role = next(
            (
                role
                for role in ("first_frame", "last_frame")
                if role in tag_roles
            ),
            None,
        )
        role_rows.append(
            {"tag": tag, "content_role": frame_role or tag_roles[0]}
        )
    frame_roles = {
        item["content_role"]
        for item in role_rows
        if item["content_role"] in {"first_frame", "last_frame"}
    }
    reference_roles = {
        item["content_role"]
        for item in role_rows
        if item["content_role"].startswith("reference_")
    }
    strict_frame_task = bool(
        frame_roles or modules.intersection({"first-frame", "last-frame"})
    )
    if strict_frame_task and reference_roles:
        issues.append(
            _issue(
                "CONTENT_ROLE_SCENARIO_CONFLICT",
                "ERROR",
                "task",
                "task.official_routing.content_roles",
                (
                    "严格首帧/首尾帧与多模态 reference_* content.role "
                    "是互斥输入场景；需要多参考时应改用 reference_image "
                    "并在 Prompt 中把图片指定为语义关键帧。"
                ),
                ("prompt_compilation", "submission"),
            )
        )
    if "last_frame" in frame_roles and "first_frame" not in frame_roles:
        issues.append(
            _issue(
                "CONTENT_ROLE_SCENARIO_CONFLICT",
                "ERROR",
                "task",
                "task.official_routing.content_roles",
                "last_frame 必须与 first_frame 成对使用。",
                ("prompt_compilation", "submission"),
            )
        )
    if primary == "edit":
        task_type = "video-editing"
        intent = "edit"
    elif primary == "extend":
        task_type = "video-extension"
        intent = "extend"
    elif strict_frame_task:
        task_type = "first-or-first-last-frame"
        intent = "generate-from-locked-frame"
    elif topology == "text-only" and not role_rows:
        task_type = "text-to-video"
        intent = "generate"
    else:
        task_type = "reference-generation"
        intent = "generate-from-reference"
    return {
        "task_type": task_type,
        "prompt_intent": intent,
        "content_roles": role_rows,
        "routing_basis": "content.role + prompt intent",
    }, issues


def _raw_asset_documents(
    source_document: Any, decisions: Any
) -> tuple[Any, Any]:
    inventory = _runtime_value(source_document, decisions, "asset_inventory")
    assignments = _runtime_value(
        source_document, decisions, "asset_assignments"
    )
    return inventory, assignments


def _normalize_asset_binding(
    source_document: Any,
    decisions: Any,
    asset_assignments: Sequence[Mapping[str, Any]],
    generation: Mapping[str, Any],
) -> dict[str, str]:
    raw = _runtime_value(source_document, decisions, "asset_binding")
    has_legacy_mapping = bool(asset_assignments) or bool(
        generation.get("reference_role_map")
    )
    if raw is None:
        return {
            "state": "mapped" if has_legacy_mapping else "unmapped",
            "source": "legacy" if has_legacy_mapping else "none",
        }
    if not isinstance(raw, dict) or _clean_text(raw.get("state")).lower() != "mapped":
        raise AssetBindingError(
            "ASSET_BINDING_INVALID: asset_binding 省略表示无素材；显式提供时 state 必须为 mapped。"
        )
    if not has_legacy_mapping:
        raise AssetBindingError(
            "ASSET_BINDING_INVALID: mapped 状态至少需要一个合法 asset assignment 或 reference role。"
        )
    return {"state": "mapped", "source": "explicit"}


def _generation_from_v2_documents(
    source_document: Any, decisions: Any
) -> dict[str, Any]:
    raw_task = _runtime_value(source_document, decisions, "task")
    inventory_raw, assignments_raw = _raw_asset_documents(
        source_document, decisions
    )
    inventory_items = (
        inventory_raw.get("items", [])
        if isinstance(inventory_raw, dict)
        else []
    )
    inventory_by_tag = {
        _clean_text(item.get("tag")): item
        for item in inventory_items
        if isinstance(item, dict) and _clean_text(item.get("tag"))
    }
    role_map: list[dict[str, Any]] = []
    for assignment in assignments_raw if isinstance(assignments_raw, list) else []:
        if not isinstance(assignment, dict):
            continue
        tag = _clean_text(assignment.get("tag"))
        item = inventory_by_tag.get(tag, {})
        if not tag or item.get("available", True) is False:
            continue
        role = _clean_text(assignment.get("role"))
        media_type = _clean_text(
            assignment.get("media_type") or item.get("media_type")
        ).lower()
        adopted = assignment.get("adopted_dimensions", [])
        preserve = (
            [str(value) for value in adopted]
            if isinstance(adopted, list)
            else []
        )
        role_map.append(
            {
                "tag": tag,
                "media_type": media_type,
                "role": role,
                "applies_to_shot_ids": copy.deepcopy(
                    assignment.get("applies_to_shot_ids", [])
                ),
                "preserve": preserve,
            }
        )
    if isinstance(raw_task, dict):
        mode = _legacy_mode_from_task(raw_task)
    elif role_map:
        roles = {_clean_text(item.get("role")) for item in role_map}
        media_types = {
            _clean_text(item.get("media_type")) for item in role_map
        }
        if "edit_source" in roles:
            mode = "edit"
        elif "extension_source" in roles:
            mode = "extend"
        elif roles.intersection({"first_frame", "last_frame"}):
            mode = "flf2v"
        elif media_types == {"image"}:
            mode = "i2v"
        elif media_types == {"video"}:
            mode = "v2v"
        else:
            mode = "r2v"
    else:
        return {}
    available_tags = _unique_strings(
        [item["tag"] for item in role_map]
    )
    generation: dict[str, Any] = {
        "mode": mode,
        "available_reference_tags": available_tags,
        "reference_role_map": role_map,
    }
    for key in ("edit_scope", "edit_deltas", "extend_context"):
        value = _runtime_value(source_document, decisions, key)
        if value is not None:
            generation[key] = value
    return generation


def _normalize_task(
    source_document: Any,
    decisions: Any,
    generation: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    raw_task = _runtime_value(source_document, decisions, "task")
    if raw_task is None:
        normalized_task = _task_from_legacy_mode(
            _clean_text(generation.get("mode"))
        )
        if profile.get("prompt_adapter_id") == "seedance-2.5-structured-zh-v1":
            official_routing, routing_issues = _official_task_routing(
                normalized_task, generation
            )
            normalized_task["official_routing"] = official_routing
            issues.extend(routing_issues)
        return normalized_task, issues
    if not isinstance(raw_task, dict):
        return {
            "primary": "",
            "input_topology": "",
            "modules": [],
            "source": "invalid",
        }, [
            _issue(
                "TASK_CONTRACT_INVALID",
                "ERROR",
                "task",
                "task",
                "task 必须是 JSON 对象。",
                ("prompt_compilation",),
            )
        ]
    primary = _clean_text(raw_task.get("primary")).lower()
    topology = _clean_text(raw_task.get("input_topology")).lower()
    modules_raw = raw_task.get("modules", [])
    modules = (
        [_clean_text(item).lower() for item in modules_raw]
        if isinstance(modules_raw, list)
        else []
    )
    if primary not in TASK_PRIMARY_VALUES:
        issues.append(
            _issue(
                "TASK_CONTRACT_INVALID",
                "ERROR",
                "task",
                "task.primary",
                "task.primary 必须是 generate、edit 或 extend。",
                ("prompt_compilation",),
            )
        )
    if topology not in INPUT_TOPOLOGY_VALUES:
        issues.append(
            _issue(
                "TASK_CONTRACT_INVALID",
                "ERROR",
                "task",
                "task.input_topology",
                "task.input_topology 不属于受支持 enum。",
                ("prompt_compilation",),
            )
        )
    if (
        not isinstance(modules_raw, list)
        or any(module not in TASK_MODULE_VALUES for module in modules)
        or len(set(modules)) != len(modules)
    ):
        issues.append(
            _issue(
                "TASK_CONTRACT_INVALID",
                "ERROR",
                "task",
                "task.modules",
                "task.modules 必须是无重复、受支持的模块数组。",
                ("prompt_compilation",),
            )
        )
    expected_mode = _legacy_mode_from_task(
        {"primary": primary, "input_topology": topology, "modules": modules}
    )
    actual_mode = _clean_text(generation.get("mode"))
    if expected_mode and actual_mode and expected_mode != actual_mode:
        issues.append(
            _issue(
                "TASK_GENERATION_MISMATCH",
                "ERROR",
                "task",
                "task",
                "task 与兼容 generation.mode 的路由结果不一致。",
                ("prompt_compilation",),
            )
        )
    normalized_task = {
        "primary": primary,
        "input_topology": topology,
        "modules": modules,
        "source": "task",
    }
    if profile.get("prompt_adapter_id") == "seedance-2.5-structured-zh-v1":
        official_routing, routing_issues = _official_task_routing(
            normalized_task, generation
        )
        normalized_task["official_routing"] = official_routing
        issues.extend(routing_issues)
    return normalized_task, issues


def _derive_story_contract(
    normalized: Mapping[str, Any], source_document: Any, decisions: Any
) -> dict[str, Any]:
    raw = _runtime_value(source_document, decisions, "story_contract")
    if isinstance(raw, dict):
        return copy.deepcopy(raw)
    events = []
    for shot in normalized.get("shots", []):
        description = _clean_text(shot.get("rendered_shot_description"))
        if description:
            events.append(
                {
                    "source_shot_id": shot.get("source_shot_id"),
                    "description": description,
                }
            )
    return {
        "subjects": [],
        "events": events,
        "scenes": [],
        "props": [],
        "relationships": [],
        "preserve": [],
        "exclude": [],
        "provenance": "derived_from_locked_source",
    }


def _derive_required_entities(
    normalized: Mapping[str, Any], story_contract: Mapping[str, Any]
) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entity_type, values in (
        ("subject", story_contract.get("subjects", [])),
        ("subject", story_contract.get("characters", [])),
        ("prop", story_contract.get("props", [])),
        ("scene", story_contract.get("scenes", [])),
        ("scene", story_contract.get("locations", [])),
    ):
        for value in values if isinstance(values, list) else []:
            name = _clean_text(value.get("name") if isinstance(value, dict) else value)
            if name and (entity_type, name) not in seen:
                seen.add((entity_type, name))
                entities.append({"entity_type": entity_type, "name": name})
    singular_location = _clean_text(story_contract.get("location"))
    if singular_location and ("scene", singular_location) not in seen:
        seen.add(("scene", singular_location))
        entities.append({"entity_type": "scene", "name": singular_location})
    for shot in normalized.get("shots", []):
        for value in shot.get("subjects", []):
            name = _clean_text(_render_descriptive_value(value))
            if name and ("subject", name) not in seen:
                seen.add(("subject", name))
                entities.append({"entity_type": "subject", "name": name})
        for value in shot.get("visible_props", []):
            name = _clean_text(_render_descriptive_value(value))
            if name and ("prop", name) not in seen:
                seen.add(("prop", name))
                entities.append({"entity_type": "prop", "name": name})
    return entities


def _derive_dialogue_ledger(
    normalized: Mapping[str, Any]
) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    for shot in normalized.get("shots", []):
        for item in shot.get("dialogue", []):
            if isinstance(item, dict):
                ledger.append(
                    {
                        "source_shot_id": shot.get("source_shot_id"),
                        "speaker": copy.deepcopy(
                            item.get("speaker", item.get("character"))
                        ),
                        "speaking": item.get("speaking", True),
                        "text": copy.deepcopy(item.get("text")),
                        "audio_role": copy.deepcopy(item.get("audio_role")),
                        "language": copy.deepcopy(item.get("language")),
                        "position": copy.deepcopy(
                            item.get("position", item.get("on_screen"))
                        ),
                    }
                )
            else:
                ledger.append(
                    {
                        "source_shot_id": shot.get("source_shot_id"),
                        "speaker": None,
                        "speaking": True,
                        "text": copy.deepcopy(item),
                        "audio_role": None,
                        "language": None,
                        "position": None,
                    }
                )
    return ledger


def _bind_dialogue_assets(
    ledger: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach explicit speaker/audio mappings without inventing dialogue."""
    bound: list[dict[str, Any]] = []
    for raw_entry in ledger:
        entry = copy.deepcopy(dict(raw_entry))
        speaker = _clean_text(entry.get("speaker"))
        shot_id = _clean_text(entry.get("source_shot_id"))
        tags = []
        for assignment in assignments:
            if _clean_text(assignment.get("role")) != "audio_reference":
                continue
            applies = assignment.get("applies_to_shot_ids", [])
            target = _clean_text(assignment.get("target_entity"))
            if "*" not in applies and shot_id not in applies:
                continue
            if speaker and target not in {speaker, "对白", "指定说话人"}:
                continue
            tag = _clean_text(assignment.get("tag"))
            if tag:
                tags.append(tag)
        entry["bound_asset_tags"] = _unique_strings(tags)
        bound.append(entry)
    return bound


def _normalize_asset_context(
    source_document: Any,
    decisions: Any,
    profile: Mapping[str, Any],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[str],
    str,
    list[dict[str, Any]],
    list[dict[str, Any]],
    bool,
]:
    issues: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []
    inventory_raw, assignments_raw = _raw_asset_documents(
        source_document, decisions
    )
    if inventory_raw is None:
        inventory_raw = {"complete": False, "items": []}
    if not isinstance(inventory_raw, dict):
        inventory_raw = {"complete": False, "items": []}
        issues.append(
            _issue(
                "ASSET_INVENTORY_INVALID",
                "ERROR",
                "asset",
                "asset_inventory",
                "asset_inventory 必须是 JSON 对象。",
                ("material_mapping",),
            )
        )
    complete = inventory_raw.get("complete") is True
    items_raw = inventory_raw.get("items", [])
    if not isinstance(items_raw, list):
        items_raw = []
        issues.append(
            _issue(
                "ASSET_INVENTORY_INVALID",
                "ERROR",
                "asset",
                "asset_inventory.items",
                "asset_inventory.items 必须是数组。",
                ("material_mapping",),
            )
        )
    items: list[dict[str, Any]] = []
    by_tag: dict[str, dict[str, Any]] = {}
    for index, raw_item in enumerate(items_raw):
        path = f"asset_inventory.items[{index}]"
        if not isinstance(raw_item, dict):
            issues.append(
                _issue(
                    "ASSET_INVENTORY_INVALID",
                    "ERROR",
                    "asset",
                    path,
                    "素材项必须是 JSON 对象。",
                    ("material_mapping",),
                )
            )
            continue
        tag = _clean_text(raw_item.get("tag"))
        media_type = _clean_text(raw_item.get("media_type")).lower()
        if (
            not tag
            or tag in by_tag
            or media_type not in {"image", "video", "audio"}
        ):
            issues.append(
                _issue(
                    "ASSET_INVENTORY_INVALID",
                    "ERROR",
                    "asset",
                    path,
                    "素材 tag 必须唯一，media_type 必须为 image、video 或 audio。",
                    ("material_mapping",),
                )
            )
            continue
        item = {
            "tag": tag,
            "media_type": media_type,
            "available": raw_item.get("available", True) is not False,
            "core": raw_item.get("core") is True,
            "duration_seconds": copy.deepcopy(
                raw_item.get("duration_seconds")
            ),
            "width": copy.deepcopy(raw_item.get("width")),
            "height": copy.deepcopy(raw_item.get("height")),
            "group_reference": raw_item.get("group_reference") is True,
            "observations": copy.deepcopy(raw_item.get("observations", {})),
        }
        items.append(item)
        by_tag[tag] = item

    assignments_raw = [] if assignments_raw is None else assignments_raw
    if not isinstance(assignments_raw, list):
        assignments_raw = []
        issues.append(
            _issue(
                "ASSET_ASSIGNMENT_INVALID",
                "ERROR",
                "asset",
                "asset_assignments",
                "asset_assignments 必须是数组。",
                ("material_mapping",),
            )
        )
    assignments: list[dict[str, Any]] = []
    targets_by_tag: dict[str, set[str]] = {}
    used_tags: set[str] = set()
    missing_optional: list[str] = []
    missing_core: list[str] = []
    for index, raw_assignment in enumerate(assignments_raw):
        path = f"asset_assignments[{index}]"
        if not isinstance(raw_assignment, dict):
            issues.append(
                _issue(
                    "ASSET_ASSIGNMENT_INVALID",
                    "ERROR",
                    "asset",
                    path,
                    "素材职责必须是 JSON 对象。",
                    ("material_mapping",),
                )
            )
            continue
        tag = _clean_text(raw_assignment.get("tag"))
        target = _clean_text(raw_assignment.get("target_entity"))
        role = _clean_text(raw_assignment.get("role"))
        item = by_tag.get(tag)
        adopted = raw_assignment.get("adopted_dimensions", [])
        rejected = raw_assignment.get("rejected_dimensions", [])
        applies = raw_assignment.get("applies_to_shot_ids", [])
        valid_lists = all(
            isinstance(value, list)
            and all(isinstance(entry, str) and entry.strip() for entry in value)
            for value in (adopted, rejected, applies)
        )
        if (
            item is None
            or not target
            or role not in REFERENCE_ROLE_MEDIA
            or not valid_lists
        ):
            issues.append(
                _issue(
                    "ASSET_ASSIGNMENT_INVALID",
                    "ERROR",
                    "asset",
                    path,
                    "素材职责必须引用库存 tag、目标实体、合法 role 和字符串数组。",
                    ("material_mapping",),
                )
            )
            continue
        targets_by_tag.setdefault(tag, set()).add(target)
        if item["available"]:
            used_tags.add(tag)
            assignments.append(
                {
                    "tag": tag,
                    "media_type": item["media_type"],
                    "target_entity": target,
                    "role": role,
                    "adopted_dimensions": list(adopted),
                    "rejected_dimensions": list(rejected),
                    "applies_to_shot_ids": list(applies),
                    "user_mapped": raw_assignment.get("user_mapped") is True,
                }
            )
        elif item["core"] or role in {"edit_source", "extension_source"}:
            missing_core.append(tag)
        else:
            missing_optional.append(tag)

    for tag, targets in targets_by_tag.items():
        item = by_tag.get(tag, {})
        related = [entry for entry in assignments if entry["tag"] == tag]
        user_mapped = any(entry.get("user_mapped") for entry in related)
        if (
            len(targets) > 1
            and not item.get("group_reference")
            and not user_mapped
        ):
            issues.append(
                _issue(
                    "ASSET_CARDINALITY_CONFLICT",
                    "ERROR",
                    "asset",
                    "asset_assignments",
                    f"素材 {tag} 未声明群体或用户映射，却分配给多个实体。",
                    ("material_mapping",),
                )
            )

    unused = (
        [item["tag"] for item in items if item["available"] and item["tag"] not in used_tags]
        if complete
        else []
    )
    if missing_optional:
        missing_optional_text = "、".join(
            _unique_strings(missing_optional)
        )
        advisories.append(
            {
                "type": "补充建议",
                "code": "OPTIONAL_ASSET_MISSING",
                "message": (
                    "以下非核心素材不可用，Prompt 已移除对应引用："
                    + missing_optional_text
                ),
            }
        )
        issues.append(
            _issue(
                "OPTIONAL_ASSET_MISSING",
                "WARN",
                "asset",
                "asset_inventory",
                f"非核心素材不可用：{missing_optional_text}。",
                ("material_mapping_review",),
            )
        )
    for tag in _unique_strings(missing_core):
        issues.append(
            _issue(
                "CORE_ASSET_MISSING",
                "ERROR",
                "asset",
                "asset_inventory",
                f"唯一核心素材 {tag} 不可用。",
                ("prompt_compilation",),
            )
        )

    submission_ready = not missing_core
    limits = profile.get("capabilities", {}).get("asset_limits", {})
    available_items = [item for item in items if item["available"]]
    limit_messages: list[str] = []
    max_total = limits.get("max_total") if isinstance(limits, dict) else None
    if isinstance(max_total, int) and len(available_items) > max_total:
        limit_messages.append(f"素材总数 {len(available_items)}>{max_total}")
    for media_type in ("image", "video", "audio"):
        media_items = [
            item for item in available_items if item["media_type"] == media_type
        ]
        media_limit = limits.get(media_type, {}) if isinstance(limits, dict) else {}
        max_count = media_limit.get("max_count") if isinstance(media_limit, dict) else None
        if isinstance(max_count, int) and len(media_items) > max_count:
            limit_messages.append(
                f"{media_type} 数量 {len(media_items)}>{max_count}"
            )
        max_duration = (
            media_limit.get("max_total_duration_seconds")
            if isinstance(media_limit, dict)
            else None
        )
        min_item_duration = (
            media_limit.get("min_item_duration_seconds")
            if isinstance(media_limit, dict)
            else None
        )
        max_item_duration = (
            media_limit.get("max_item_duration_seconds")
            if isinstance(media_limit, dict)
            else None
        )
        known_durations: list[Decimal] = []
        for item in media_items:
            try:
                duration = _duration_decimal(item.get("duration_seconds"))
            except InvalidOperation:
                duration = None
            if duration is not None:
                known_durations.append(duration)
                if (
                    isinstance(min_item_duration, (int, float))
                    and duration < Decimal(str(min_item_duration))
                ):
                    limit_messages.append(
                        f"{item['tag']} 时长低于 {min_item_duration} 秒"
                    )
                if (
                    isinstance(max_item_duration, (int, float))
                    and duration > Decimal(str(max_item_duration))
                ):
                    limit_messages.append(
                        f"{item['tag']} 时长超过 {max_item_duration} 秒"
                    )
        if (
            isinstance(max_duration, (int, float))
            and known_durations
            and sum(known_durations, Decimal("0")) > Decimal(str(max_duration))
        ):
            limit_messages.append(
                f"{media_type} 总时长超过 {max_duration} 秒"
            )
    image_limit = limits.get("image", {}) if isinstance(limits, dict) else {}
    min_dimension = image_limit.get("min_dimension_pixels") if isinstance(image_limit, dict) else None
    max_dimension = image_limit.get("max_dimension_pixels") if isinstance(image_limit, dict) else None
    min_total_pixels = image_limit.get("min_total_pixels") if isinstance(image_limit, dict) else None
    max_total_pixels = image_limit.get("max_total_pixels") if isinstance(image_limit, dict) else None
    min_aspect_ratio = image_limit.get("min_aspect_ratio") if isinstance(image_limit, dict) else None
    max_aspect_ratio = image_limit.get("max_aspect_ratio") if isinstance(image_limit, dict) else None
    for item in available_items:
        if item["media_type"] != "image":
            continue
        width = item.get("width")
        height = item.get("height")
        dimensions = [width, height]
        if isinstance(max_dimension, int):
            if any(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value > max_dimension
                for value in dimensions
            ):
                limit_messages.append(
                    f"{item['tag']} 尺寸超过 {max_dimension}px"
                )
        if isinstance(min_dimension, int) and any(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value < min_dimension
            for value in dimensions
        ):
            limit_messages.append(
                f"{item['tag']} 尺寸低于 {min_dimension}px"
            )
        if all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value > 0
            for value in dimensions
        ):
            total_pixels = width * height
            aspect_ratio = width / height
            if (
                isinstance(min_total_pixels, int)
                and total_pixels < min_total_pixels
            ):
                limit_messages.append(
                    f"{item['tag']} 总像素低于 {min_total_pixels}"
                )
            if (
                isinstance(max_total_pixels, int)
                and total_pixels > max_total_pixels
            ):
                limit_messages.append(
                    f"{item['tag']} 总像素超过 {max_total_pixels}"
                )
            if (
                isinstance(min_aspect_ratio, (int, float))
                and aspect_ratio < min_aspect_ratio
            ) or (
                isinstance(max_aspect_ratio, (int, float))
                and aspect_ratio > max_aspect_ratio
            ):
                limit_messages.append(
                    f"{item['tag']} 宽高比不在 0.4 至 2.5"
                )
    if limit_messages:
        submission_ready = False
        advisories.append(
            {
                "type": "素材提示",
                "code": "ASSET_LIMIT_EXCEEDED",
                "message": "；".join(_unique_strings(limit_messages)),
            }
        )
        issues.append(
            _issue(
                "ASSET_LIMIT_EXCEEDED",
                "WARN",
                "asset",
                "asset_inventory",
                "；".join(_unique_strings(limit_messages)),
                ("submission",),
            )
        )

    confidence_raw = _runtime_value(
        source_document, decisions, "mapping_confidence"
    )
    confidence = (
        _clean_text(confidence_raw).lower()
        if isinstance(confidence_raw, str)
        else "high"
    )
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
        issues.append(
            _issue(
                "MAPPING_CONFIDENCE_INVALID",
                "WARN",
                "asset",
                "mapping_confidence",
                "映射置信度必须为 high、medium 或 low。",
                ("material_mapping_review",),
            )
        )
    inventory = {"complete": complete, "items": items}
    return (
        inventory,
        assignments,
        unused,
        confidence,
        issues,
        advisories,
        submission_ready,
    )


def _normalize_request_configuration(
    source_document: Any,
    decisions: Any,
    profile: Mapping[str, Any],
    task: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], bool]:
    issues: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []
    raw = _runtime_value(source_document, decisions, "request_configuration")
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
        issues.append(
            _issue(
                "REQUEST_CONFIGURATION_INVALID",
                "WARN",
                "request",
                "request_configuration",
                "request_configuration 必须是 JSON 对象。",
                ("submission",),
            )
        )
    raw_model_id = raw.get("model_id", profile.get("model_id"))
    raw_ratio = raw.get("ratio")
    raw_duration = raw.get("duration")
    raw_resolution = raw.get("resolution")
    raw_output_format = raw.get("output_format")
    raw_generate_audio = raw.get("generate_audio")
    normalized = {
        "model_id": (
            _clean_text(raw_model_id) if raw_model_id is not None else None
        ),
        "ratio": (
            _clean_text(raw_ratio).lower() if raw_ratio is not None else None
        ),
        "duration": copy.deepcopy(raw_duration),
        "resolution": (
            _clean_text(raw_resolution).lower()
            if raw_resolution is not None
            else None
        ),
        "output_format": (
            _clean_text(raw_output_format).lower()
            if raw_output_format is not None
            else None
        ),
        "generate_audio": copy.deepcopy(raw_generate_audio),
    }
    ready = True
    profile_model_id = profile.get("model_id")
    if (
        raw.get("model_id") is not None
        and profile_model_id is not None
        and raw.get("model_id") != profile_model_id
    ):
        ready = False
        advisories.append(
            {
                "type": "参数提示",
                "code": "MODEL_ID_MISMATCH",
                "message": "请求 model_id 与当前 Model Profile 不一致。",
            }
        )
        issues.append(
            _issue(
                "MODEL_ID_MISMATCH",
                "WARN",
                "request",
                "request_configuration.model_id",
                "请求 model_id 与当前 Model Profile 不一致。",
                ("submission",),
            )
        )
    primary = _clean_text(task.get("primary"))
    modules = set(task.get("modules", []))
    ratio = normalized["ratio"]
    duration = normalized["duration"]
    resolution = normalized["resolution"]
    output_format = normalized["output_format"]
    generate_audio = normalized["generate_audio"]
    request_constraints = profile.get("capabilities", {}).get(
        "request_constraints", {}
    )
    allowed_ratios = request_constraints.get("ratios", [])
    allowed_resolutions = request_constraints.get("resolutions", [])
    allowed_formats = request_constraints.get("output_formats", [])
    conflicts: list[str] = []
    if ratio is not None and (
        not isinstance(allowed_ratios, list) or ratio not in allowed_ratios
    ):
        conflicts.append("ratio 不属于当前模型支持的宽高比")
    if output_format is not None and (
        not isinstance(allowed_formats, list)
        or output_format not in allowed_formats
    ):
        conflicts.append("output_format 不属于当前模型支持的格式")
    if resolution is not None and (
        not isinstance(allowed_resolutions, list)
        or resolution not in allowed_resolutions
    ):
        conflicts.append("resolution 不属于当前模型支持的分辨率")
    if generate_audio is not None and not isinstance(generate_audio, bool):
        conflicts.append("generate_audio 必须是布尔值")
    if primary == "edit":
        if ratio not in (None, "adaptive"):
            conflicts.append("视频编辑 ratio 必须为 adaptive")
        if duration not in (None, -1):
            conflicts.append("视频编辑 duration 必须为 -1")
    elif primary == "extend" or modules.intersection(
        {"first-frame", "last-frame"}
    ):
        if ratio not in (None, "adaptive"):
            conflicts.append("当前任务 ratio 必须为 adaptive")
    if primary != "edit" and duration is not None:
        try:
            duration_value = (
                _duration_decimal(duration)
                if duration != -1
                else Decimal("-1")
            )
        except InvalidOperation:
            duration_value = None
        if duration_value is None or (
            duration_value != Decimal("-1")
            and not Decimal("4") <= duration_value <= _profile_limit(profile)
        ):
            conflicts.append("duration 必须为 -1 或 4 至模型上限秒")
    if conflicts:
        ready = False
        message = "；".join(conflicts)
        advisories.append(
            {
                "type": "参数提示",
                "code": "REQUEST_PARAMETER_CONFLICT",
                "message": message,
            }
        )
        issues.append(
            _issue(
                "REQUEST_PARAMETER_CONFLICT",
                "WARN",
                "request",
                "request_configuration",
                message,
                ("submission",),
            )
        )
    if (
        primary in {"edit", "extend"}
        and output_format in (None, "mp4")
    ):
        advisories.append(
            {
                "type": "参数提示",
                "code": "MOV_RECOMMENDED",
                "message": (
                    "视频编辑和视频延长建议使用 mov 作为输入与输出，"
                    "以改善色彩保真度和声画衔接；此项为建议，不阻断提交。"
                ),
            }
        )
    return {
        "raw": copy.deepcopy(raw),
        "normalized": normalized,
        "prompt_isolation": True,
    }, issues, advisories, ready


def _generation_source(
    source_document: Any, decisions: Any
) -> tuple[Any, str]:
    if isinstance(decisions, dict) and "generation" in decisions:
        raw_decision_generation = decisions.get("generation")
        if not isinstance(raw_decision_generation, dict):
            return copy.deepcopy(raw_decision_generation), "decisions"
    else:
        raw_decision_generation = {}
    if raw_decision_generation:
        raw_source_generation = (
            source_document.get("generation", {})
            if isinstance(source_document, dict)
            else {}
        )
        merged = (
            copy.deepcopy(raw_source_generation)
            if isinstance(raw_source_generation, dict)
            else {}
        )
        merged.update(copy.deepcopy(raw_decision_generation))
        return merged, "decisions"
    if isinstance(source_document, dict) and "generation" in source_document:
        raw_source_generation = source_document.get("generation")
        if not isinstance(raw_source_generation, dict):
            return copy.deepcopy(raw_source_generation), "input"
    else:
        raw_source_generation = {}
    source_generation = (
        copy.deepcopy(raw_source_generation)
        if isinstance(raw_source_generation, dict)
        else {}
    )
    if source_generation:
        return source_generation, "input"
    v2_generation = _generation_from_v2_documents(
        source_document, decisions
    )
    if v2_generation:
        return v2_generation, "task"
    return {"mode": "t2v"}, "default_t2v"


def _validate_generation_context(
    raw_generation: Any,
    source_document: Any,
    shots: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
    *,
    mode_source: str,
    runtime_decisions_hash: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    invalid_shot_ids: set[str] = set()
    global_blocked = False
    if not isinstance(raw_generation, dict):
        global_blocked = True
        issues.append(
            _issue(
                "GENERATION_CONTRACT_INVALID",
                "ERROR",
                "generation",
                "generation",
                "generation 必须是 JSON 对象。",
                ("prompt_compilation",),
            )
        )
    generation = _as_dict(raw_generation)
    mode = _clean_text(generation.get("mode")).lower()
    if mode not in GENERATION_MODES:
        global_blocked = True
        issues.append(
            _issue(
                "MODE_GATE_BLOCKED",
                "ERROR",
                "generation",
                "generation.mode",
                f"未知 generation mode：{mode or '<empty>'}。",
                ("prompt_compilation",),
            )
        )

    supported_modes = profile.get("capabilities", {}).get(
        "supported_generation_modes", []
    )
    if mode in GENERATION_MODES and mode not in supported_modes:
        global_blocked = True
        issues.append(
            _issue(
                "MODE_GATE_BLOCKED",
                "ERROR",
                "generation",
                "generation.mode",
                "当前 Model Profile 不支持所选 generation mode。",
                ("prompt_compilation",),
            )
        )

    available_raw = generation.get("available_reference_tags", [])
    available_tags: list[str] = []
    if not isinstance(available_raw, list) or any(
        not isinstance(tag, str) or not tag for tag in available_raw
    ):
        global_blocked = True
        issues.append(
            _issue(
                "REFERENCE_TAG_INVALID",
                "ERROR",
                "generation",
                "generation.available_reference_tags",
                "available_reference_tags 必须是精确、非空字符串数组。",
                ("prompt_compilation",),
            )
        )
    else:
        available_tags = list(available_raw)
        if len(set(available_tags)) != len(available_tags):
            global_blocked = True
            issues.append(
                _issue(
                    "REFERENCE_TAG_INVALID",
                    "ERROR",
                    "generation",
                    "generation.available_reference_tags",
                    "available_reference_tags 不得重复。",
                    ("prompt_compilation",),
                )
            )

    role_map_raw = generation.get("reference_role_map", [])
    if not isinstance(role_map_raw, list):
        global_blocked = True
        role_map_raw = []
        issues.append(
            _issue(
                "REFERENCE_ROLE_INVALID",
                "ERROR",
                "generation",
                "generation.reference_role_map",
                "reference_role_map 必须是数组。",
                ("prompt_compilation",),
            )
        )

    shot_positions = _shot_id_positions(shots)
    validated_roles: list[dict[str, Any]] = []
    mapped_tags: set[str] = set()
    mapped_role_keys: set[tuple[str, str, tuple[str, ...]]] = set()
    allow_multi_role_per_tag = _clean_text(
        profile.get("capabilities", {})
        .get("reference_tag_convention", {})
        .get("convention_id")
    ) == "preserve-explicit-v1"
    for index, raw_role in enumerate(role_map_raw):
        path = f"generation.reference_role_map[{index}]"
        if not isinstance(raw_role, dict):
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    path,
                    "reference role 必须是对象。",
                    ("prompt_compilation",),
                )
            )
            continue
        tag = _clean_text(raw_role.get("tag"))
        media_type = _clean_text(raw_role.get("media_type")).lower()
        role = _clean_text(raw_role.get("role"))
        applies = raw_role.get("applies_to_shot_ids")
        preserve = raw_role.get("preserve", [])
        valid = True
        candidate_applies = {
            shot_id
            for shot_id in (applies if isinstance(applies, list) else [])
            if isinstance(shot_id, str)
            and (
                shot_id == "*"
                or len(shot_positions.get(shot_id, [])) == 1
            )
        }

        role_key = (
            tag,
            role,
            tuple(applies) if isinstance(applies, list) else (),
        )
        if role_key in mapped_role_keys or (
            tag in mapped_tags and not allow_multi_role_per_tag
        ):
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.tag",
                    (
                        "reference tag 的同一职责不得重复。"
                        if allow_multi_role_per_tag
                        else "每个 reference tag 只能承担一个显式角色。"
                    ),
                    ("prompt_compilation",),
                )
            )
        mapped_tags.add(tag)
        mapped_role_keys.add(role_key)
        if tag not in available_tags:
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_TAG_UNMAPPED",
                    "ERROR",
                    "generation",
                    f"{path}.tag",
                    "role map 的 tag 未列入 available_reference_tags。",
                    ("prompt_compilation",),
                )
            )
        if media_type not in {"image", "video", "audio"}:
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.media_type",
                    "media_type 必须显式为 image、video 或 audio。",
                    ("prompt_compilation",),
                )
            )
        elif not _reference_tag_valid(tag, media_type, profile):
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_TAG_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.tag",
                    "tag 不符合当前 Model Profile 对该 media_type 的 convention。",
                    ("prompt_compilation",),
                )
            )
        if role not in REFERENCE_ROLE_MEDIA:
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.role",
                    "未知 reference role。",
                    ("prompt_compilation",),
                )
            )
        elif media_type not in REFERENCE_ROLE_MEDIA[role]:
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.role",
                    "reference role 与显式 media_type 不兼容。",
                    ("prompt_compilation",),
                )
            )
        if not isinstance(applies, list) or not applies or any(
            not isinstance(shot_id, str)
            or not shot_id.strip()
            or (
                shot_id != "*"
                and len(shot_positions.get(shot_id, [])) != 1
            )
            for shot_id in (applies if isinstance(applies, list) else [])
        ) or (
            isinstance(applies, list)
            and len(set(applies)) != len(applies)
        ):
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.applies_to_shot_ids",
                    "reference 必须限定到唯一存在的 source shot ID。",
                    ("prompt_compilation",),
                )
            )
        if not isinstance(preserve, list) or any(
            not isinstance(item, str) or not item.strip() for item in preserve
        ):
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.preserve",
                    "preserve 必须是非空字符串组成的数组。",
                    ("prompt_compilation",),
                )
            )
        preserve_terms = _anti_slop_terms_in_value(preserve)
        if preserve_terms:
            valid = False
            issues.append(
                _issue(
                    "DOWNSTREAM_ANTI_SLOP",
                    "ERROR",
                    "generation",
                    f"{path}.preserve",
                    (
                        "下游 reference preserve 含空泛强化词："
                        f"{', '.join(preserve_terms)}；未改写且不进入正文。"
                    ),
                    ("prompt_compilation",),
                )
            )
        if not valid:
            invalid_shot_ids.update(candidate_applies)
        if valid:
            validated_roles.append(
                {
                    "tag": tag,
                    "media_type": media_type,
                    "role": role,
                    "applies_to_shot_ids": list(applies),
                    "preserve": list(preserve),
                }
            )

    for tag in available_tags:
        if tag not in mapped_tags:
            issues.append(
                _issue(
                    "REFERENCE_TAG_UNMAPPED",
                    "ERROR",
                    "generation",
                    "generation.available_reference_tags",
                    f"available tag {tag} 没有唯一 role map。",
                    ("prompt_compilation",),
                )
            )

    edit_scope_raw = generation.get("edit_scope", [])
    edit_scope_valid = (
        isinstance(edit_scope_raw, list)
        and bool(edit_scope_raw)
        and all(
            isinstance(item, str) and bool(item.strip())
            for item in edit_scope_raw
        )
        and len(set(edit_scope_raw)) == len(edit_scope_raw)
    )
    edit_scope = list(edit_scope_raw) if edit_scope_valid else []
    edit_deltas_raw = generation.get("edit_deltas", [])
    edit_deltas_list = (
        list(edit_deltas_raw)
        if isinstance(edit_deltas_raw, list)
        else []
    )
    edit_deltas: list[dict[str, Any]] = []
    edit_invalid_shot_ids: set[str] = set()
    if mode == "edit" and (
        not edit_scope_valid
        or not isinstance(edit_deltas_raw, list)
        or not edit_deltas_raw
    ):
        edit_invalid_shot_ids.update(shot_positions)
        issues.append(
            _issue(
                "EDIT_SCOPE_INVALID",
                "ERROR",
                "generation",
                "generation.edit_scope",
                "edit 需要非空、不重复的 edit_scope 和 edit_deltas。",
                ("prompt_compilation",),
            )
        )
    for delta_index, delta in enumerate(edit_deltas_list):
        applies = (
            delta.get("applies_to_shot_ids", [])
            if isinstance(delta, dict)
            else []
        )
        candidate_values: Iterable[Any]
        if isinstance(applies, list):
            candidate_values = applies
        elif isinstance(applies, str):
            candidate_values = [applies]
        elif isinstance(applies, dict):
            candidate_values = applies.keys()
        else:
            candidate_values = []
        delta_candidate_shots = {
            shot_id
            for value in candidate_values
            if isinstance(value, str)
            for shot_id in [value]
            if len(shot_positions.get(shot_id, [])) == 1
        }
        if not delta_candidate_shots:
            delta_candidate_shots = set(shot_positions)
        applies_valid = (
            isinstance(applies, list)
            and bool(applies)
            and all(
                isinstance(shot_id, str)
                and bool(shot_id.strip())
                and len(shot_positions.get(shot_id, [])) == 1
                for shot_id in applies
            )
            and len(set(applies)) == len(applies)
        )
        delta_valid = (
            isinstance(delta, dict)
            and _clean_text(delta.get("layer")) in edit_scope
            and bool(_clean_text(delta.get("instruction")))
            and applies_valid
        )
        if not delta_valid:
            if mode == "edit":
                edit_invalid_shot_ids.update(delta_candidate_shots)
            issues.append(
                _issue(
                    "EDIT_SCOPE_INVALID",
                    "ERROR",
                    "generation",
                    f"generation.edit_deltas[{delta_index}]",
                    (
                        "edit delta 必须只修改 edit_scope 声明层、包含明确 "
                        "instruction，并以非空字符串数组限定 "
                        "applies_to_shot_ids。"
                    ),
                    ("prompt_compilation",),
                )
            )
        elif _anti_slop_terms_in_value(delta.get("instruction")):
            if mode == "edit":
                edit_invalid_shot_ids.update(delta_candidate_shots)
            terms = _anti_slop_terms_in_value(delta.get("instruction"))
            issues.append(
                _issue(
                    "DOWNSTREAM_ANTI_SLOP",
                    "ERROR",
                    "generation",
                    f"generation.edit_deltas[{delta_index}].instruction",
                    (
                        "下游 edit delta 含空泛强化词："
                        f"{', '.join(terms)}；未改写且不进入正文。"
                    ),
                    ("prompt_compilation",),
                )
            )
        else:
            edit_deltas.append(
                {
                    "layer": _clean_text(delta.get("layer")),
                    "instruction": _clean_text(delta.get("instruction")),
                    "applies_to_shot_ids": list(applies),
                }
            )
    extend_context = _as_dict(generation.get("extend_context"))
    extend_context_valid = (
        extend_context.get("accepted_material") is True
        and bool(_clean_text(extend_context.get("observed_end_state")))
    )

    def invalidate_shot(shot_id: str, message: str, path: str) -> None:
        invalid_shot_ids.add(shot_id)
        issues.append(
            _issue(
                "MODE_UNIT_REFERENCE_INVALID",
                "ERROR",
                "shot",
                path,
                message,
                ("prompt_compilation",),
            )
        )

    for shot_index, shot in enumerate(shots):
        shot_id = str(shot["source_shot_id"])
        shot_roles = [
            item
            for item in validated_roles
            if "*" in item["applies_to_shot_ids"]
            or shot_id in item["applies_to_shot_ids"]
        ]
        image_roles = [
            item for item in shot_roles if item["media_type"] == "image"
        ]
        video_roles = [
            item for item in shot_roles if item["media_type"] == "video"
        ]
        shot_path = f"shots[{shot_index}]({shot_id})"
        if mode == "t2v" and shot_roles:
            invalidate_shot(
                shot_id,
                "t2v Cut 不接受媒体 reference。",
                shot_path,
            )
        elif mode == "i2v" and not image_roles:
            invalidate_shot(
                shot_id,
                "i2v Cut 缺少适用于该源镜的显式 image reference。",
                shot_path,
            )
        elif mode == "v2v" and not video_roles:
            invalidate_shot(
                shot_id,
                "v2v Cut 缺少适用于该源镜的显式 video reference。",
                shot_path,
            )
        elif mode == "r2v" and not shot_roles:
            invalidate_shot(
                shot_id,
                "r2v Cut 缺少适用于该源镜的精确 role reference。",
                shot_path,
            )
        elif mode == "flf2v":
            first_tags = {
                item["tag"]
                for item in image_roles
                if item["role"] == "first_frame"
            }
            last_tags = {
                item["tag"]
                for item in image_roles
                if item["role"] == "last_frame"
            }
            if (
                len(first_tags) != 1
                or len(last_tags) != 1
                or first_tags == last_tags
            ):
                invalidate_shot(
                    shot_id,
                    "flf2v Cut 需要不同 tag 的唯一 first_frame 与 last_frame。",
                    shot_path,
                )
        elif mode == "edit":
            edit_source_tags = {
                item["tag"]
                for item in shot_roles
                if item["role"] == "edit_source"
            }
            has_applicable_delta = any(
                isinstance(delta, dict)
                and shot_id in delta.get("applies_to_shot_ids", [])
                for delta in edit_deltas
            )
            if (
                len(edit_source_tags) != 1
                or shot_id in edit_invalid_shot_ids
                or not has_applicable_delta
            ):
                invalidate_shot(
                    shot_id,
                    (
                        "edit Cut 需要唯一且适用于该源镜的 edit_source、合法 "
                        "edit_scope 与 edit delta。"
                    ),
                    shot_path,
                )
        elif mode == "extend":
            extension_source_tags = {
                item["tag"]
                for item in shot_roles
                if item["role"] == "extension_source"
            }
            if len(extension_source_tags) != 1 or not extend_context_valid:
                invalidate_shot(
                    shot_id,
                    (
                        "extend Cut 需要唯一且适用于该源镜的 extension_source、"
                        "已接受素材和观测结束状态；不要求回流上游。"
                    ),
                    shot_path,
                )

    context = {
        "mode": mode,
        "mode_source": mode_source,
        "available_reference_tags": available_tags,
        "reference_role_map": validated_roles,
        "edit_scope": edit_scope,
        "edit_deltas": edit_deltas,
        "extend_context": extend_context,
        "runtime_decisions_hash": runtime_decisions_hash,
        "global_blocked": global_blocked,
        "invalid_shot_ids": [
            str(shot["source_shot_id"])
            for shot in shots
            if str(shot["source_shot_id"]) in invalid_shot_ids
        ],
    }
    for key in (
        "asset_assignments",
        "asset_binding",
        "unused_assets",
        "story_contract",
        "task_modules",
        "global_reference_section",
        "operation_dependency",
    ):
        if key in generation:
            context[key] = copy.deepcopy(generation.get(key))
    return context, _deduplicate_issues(issues)


def resolve_generation_context(
    source_document: Any,
    decisions: Any,
    shots: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw_generation, mode_source = _generation_source(source_document, decisions)
    runtime_hash = sha256_json(decisions) if decisions is not None else None
    return _validate_generation_context(
        raw_generation,
        source_document,
        shots,
        profile,
        mode_source=mode_source,
        runtime_decisions_hash=runtime_hash,
    )


def _shot_id_positions(
    shots: Sequence[Mapping[str, Any]],
) -> dict[str, list[int]]:
    positions: dict[str, list[int]] = {}
    for index, shot in enumerate(shots):
        positions.setdefault(str(shot["source_shot_id"]), []).append(index)
    return positions


def _grouping_policy(profile: Mapping[str, Any]) -> dict[str, Decimal | int]:
    profile_id = _clean_text(profile.get("profile_id"))
    return copy.deepcopy(
        GROUPING_POLICIES.get(profile_id, DEFAULT_GROUPING_POLICY)
    )


def _validate_emotion_decisions(
    shots: Sequence[Mapping[str, Any]], decisions: Any
) -> tuple[dict[str, list[dict[str, str]]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    accepted: dict[str, list[dict[str, str]]] = {}
    raw_map = (
        decisions.get("emotion_visualizations", {})
        if isinstance(decisions, dict)
        else {}
    )
    if raw_map in (None, {}):
        return accepted, issues
    if not isinstance(raw_map, dict):
        issues.append(
            _issue(
                "EMOTION_VISUALIZATION_INVALID",
                "ERROR",
                "decision",
                "emotion_visualizations",
                "emotion_visualizations 必须是按 source_shot_id 索引的对象。",
                ("emotion_visualization",),
            )
        )
        return accepted, issues

    positions = _shot_id_positions(shots)
    for shot_id, raw_decision in raw_map.items():
        path = f"emotion_visualizations.{shot_id}"
        shot_positions = positions.get(str(shot_id), [])
        if len(shot_positions) != 1:
            issues.append(
                _issue(
                    "EMOTION_VISUALIZATION_INVALID",
                    "ERROR",
                    "decision",
                    path,
                    "情绪派生必须引用一个唯一存在的 source_shot_id。",
                    ("emotion_visualization",),
                )
            )
            continue
        shot = shots[shot_positions[0]]
        if shot.get("visible_behavior"):
            issues.append(
                _issue(
                    "EMOTION_VISUALIZATION_FORBIDDEN",
                    "ERROR",
                    "decision",
                    path,
                    "来源已有 visible_behavior，不允许叠加派生表演。",
                    ("emotion_visualization",),
                )
            )
            continue
        emotion_intent = _clean_text(shot.get("emotion_intent"))
        if not emotion_intent:
            issues.append(
                _issue(
                    "EMOTION_VISUALIZATION_WITHOUT_BASIS",
                    "ERROR",
                    "decision",
                    path,
                    "来源没有明确 emotion_intent，不允许创建情绪。",
                    ("emotion_visualization",),
                )
            )
            continue
        if not isinstance(raw_decision, dict):
            issues.append(
                _issue(
                    "EMOTION_VISUALIZATION_INVALID",
                    "ERROR",
                    "decision",
                    path,
                    "情绪派生必须是包含 basis、text 和 guardrails 的对象。",
                    ("emotion_visualization",),
                )
            )
            continue
        basis = _clean_text(raw_decision.get("basis_emotion"))
        text = _clean_text(raw_decision.get("text"))
        guardrails = raw_decision.get("guardrails")
        guardrails_valid = isinstance(guardrails, dict) and all(
            guardrails.get(key) is False for key in EMOTION_GUARDRAIL_KEYS
        )
        if basis != emotion_intent or not text or not guardrails_valid:
            issues.append(
                _issue(
                    "EMOTION_VISUALIZATION_INVALID",
                    "ERROR",
                    "decision",
                    path,
                    "basis 必须逐字匹配来源情绪，text 非空，且五项 guardrail 显式为 false。",
                    ("emotion_visualization",),
                )
            )
            continue
        downstream_terms = _anti_slop_terms_in_value(text)
        if downstream_terms:
            issues.append(
                _issue(
                    "DOWNSTREAM_ANTI_SLOP",
                    "ERROR",
                    "decision",
                    path,
                    (
                        "下游 emotion visualization 含空泛强化词："
                        f"{', '.join(downstream_terms)}；未改写且不进入正文。"
                    ),
                    ("emotion_visualization",),
                )
            )
            continue
        accepted[str(shot_id)] = [
            {
                "provenance": "derived_emotion_visualization",
                "basis_emotion": basis,
                "text": text,
            }
        ]
    return accepted, issues


def _plan_groups(
    shots: Sequence[Mapping[str, Any]],
    decisions: Any,
    profile: Mapping[str, Any],
    source_observed_hash: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not shots:
        return [], []
    if isinstance(decisions, dict) and "groups" in decisions:
        raise GroupingReviewError(
            "GROUPING_REVIEW_LEGACY_UNSUPPORTED: decisions.groups "
            "不属于 prompt-plan/2.0.4；请提供 grouping_review。"
        )
    review = (
        decisions.get("grouping_review")
        if isinstance(decisions, dict)
        else None
    )
    if len(shots) == 1 and review is None:
        shot = shots[0]
        return [
            {
                "shots": [shot],
                "grouping_reason": None,
                "semantic_compatibility": None,
                "standalone_reason": "single_source_shot",
                "partition_strategy": GROUPING_PARTITION_POLICY,
                "partition_entry_reason": "scope_start",
                "boundary_evidence": [],
            }
        ], []
    if not isinstance(review, dict):
        raise GroupingReviewError(
            "GROUPING_REVIEW_REQUIRED: 多镜输入必须提供完整 grouping_review。"
        )
    if _clean_text(review.get("source_observed_hash")) != _clean_text(
        source_observed_hash
    ):
        raise GroupingReviewError(
            "GROUPING_REVIEW_SOURCE_MISMATCH: source_observed_hash "
            "未匹配当前锁定来源。"
        )
    if _clean_text(review.get("contract")) != GROUPING_REVIEW_CONTRACT:
        raise GroupingReviewError(
            "GROUPING_REVIEW_CONTRACT_INVALID: grouping_review.contract "
            f"必须是 {GROUPING_REVIEW_CONTRACT}。"
        )
    if _clean_text(review.get("partition_policy")) != GROUPING_PARTITION_POLICY:
        raise GroupingReviewError(
            "GROUPING_PARTITION_POLICY_INVALID: partition_policy 必须是 "
            f"{GROUPING_PARTITION_POLICY}。"
        )
    boundaries = review.get("boundaries")
    if not isinstance(boundaries, list) or len(boundaries) != len(shots) - 1:
        raise GroupingReviewError(
            "GROUPING_REVIEW_INCOMPLETE: boundaries 必须按顺序恰好覆盖 "
            f"{len(shots) - 1} 个相邻边界。"
        )

    grouping_policy = _grouping_policy(profile)
    max_cuts = int(grouping_policy["max_cuts"])
    max_group_duration = Decimal(grouping_policy["max_duration_seconds"])
    capabilities = profile.get("capabilities", {})
    if capabilities.get("supports_multi_cut") is not True:
        max_cuts = 1
    model_limit = _duration_decimal(
        capabilities.get("max_clip_duration_seconds")
    )
    if model_limit is not None:
        max_group_duration = min(max_group_duration, model_limit)

    def duration_of(shot: Mapping[str, Any]) -> Decimal | None:
        try:
            return _duration_decimal(shot.get("duration_seconds"))
        except InvalidOperation:
            return None

    def context_value(shot: Mapping[str, Any], *keys: str) -> str:
        for key in keys:
            value = _clean_text(shot.get(key))
            if value:
                return value
        context = shot.get("scene_context", {})
        if isinstance(context, dict):
            for key in keys:
                value = _clean_text(context.get(key))
                if value:
                    return value
        continuity = shot.get("continuity", {})
        if isinstance(continuity, dict):
            for key in keys:
                value = _clean_text(continuity.get(key))
                if value:
                    return value
        return ""

    def observed_evidence(
        left: Mapping[str, Any], right: Mapping[str, Any]
    ) -> tuple[set[str], set[str]]:
        positive: set[str] = set()
        hard: set[str] = set()
        pairs = (
            (("scene_id", "scene", "location"), "same_scene", "scene_change"),
            (("reality_layer",), "same_reality_layer", "reality_layer_change"),
            (("time", "time_of_day"), "same_time", "time_change"),
        )
        for keys, same_code, change_code in pairs:
            left_value = context_value(left, *keys)
            right_value = context_value(right, *keys)
            if left_value and right_value:
                if left_value == right_value:
                    positive.add(same_code)
                else:
                    hard.add(change_code)
        if (
            left.get("compilable_source") is not True
            or right.get("compilable_source") is not True
        ):
            hard.add("source_unavailable")
        left_design = left.get("cut_design", {})
        right_design = right.get("cut_design", {})
        left_exit = _clean_text(
            left_design.get("exit_trigger")
            if isinstance(left_design, dict)
            else ""
        )
        right_entry = _clean_text(
            right_design.get("entry_trigger")
            if isinstance(right_design, dict)
            else ""
        )
        if left_exit and right_entry and SequenceMatcher(
            None, left_exit, right_entry
        ).ratio() >= 0.5:
            positive.add("boundary_state_match")
        return positive, hard

    boundary_records: list[dict[str, Any]] = []

    for index, boundary in enumerate(boundaries):
        path = f"grouping_review.boundaries[{index}]"
        left = shots[index]
        right = shots[index + 1]
        left_id = str(left["source_shot_id"])
        right_id = str(right["source_shot_id"])
        if not isinstance(boundary, dict):
            raise GroupingReviewError(
                f"GROUPING_REVIEW_INVALID: {path} 必须是 JSON 对象。"
            )
        if (
            _clean_text(boundary.get("left_source_shot_id")) != left_id
            or _clean_text(boundary.get("right_source_shot_id")) != right_id
        ):
            raise GroupingReviewError(
                f"GROUPING_REVIEW_ORDER_INVALID: {path} 未匹配相邻镜头 "
                f"{left_id} → {right_id}。"
            )
        if "decision" in boundary or "constraint_reason" in boundary:
            raise GroupingReviewError(
                f"GROUPING_REVIEW_LEGACY_BOUNDARY: {path} 必须分离语义分类与最终分区，"
                "不得再提交 decision 或 constraint_reason。"
            )
        reason = _clean_text(boundary.get("reason"))
        if not reason:
            raise GroupingReviewError(
                f"GROUPING_REVIEW_INVALID: {path}.reason 必须非空。"
            )
        compatibility = boundary.get("compatibility")
        if not isinstance(compatibility, dict) or set(compatibility) != set(
            COMPATIBILITY_KEYS
        ) or any(
            not isinstance(compatibility.get(key), bool)
            for key in COMPATIBILITY_KEYS
        ):
            raise GroupingReviewError(
                f"GROUPING_REVIEW_INVALID: {path}.compatibility 必须完整声明 "
                "十个布尔维度。"
            )
        boundary_class = _clean_text(boundary.get("classification"))
        if boundary_class not in GROUPING_BOUNDARY_CLASSES:
            raise GroupingReviewError(
                f"GROUPING_REVIEW_INVALID: {path}.classification 不受支持。"
            )
        evidence = boundary.get("semantic_evidence")
        allowed_evidence = (
            GROUPING_HARD_EVIDENCE
            | GROUPING_JOIN_EVIDENCE
            | GROUPING_SPLIT_EVIDENCE
        )
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(_clean_text(item) not in allowed_evidence for item in evidence)
            or len({_clean_text(item) for item in evidence}) != len(evidence)
        ):
            raise GroupingReviewError(
                f"GROUPING_REVIEW_INVALID: {path}.semantic_evidence 必须是非空、"
                "无重复的受控证据数组。"
            )
        evidence_codes = {_clean_text(item) for item in evidence}
        observed_positive, observed_hard = observed_evidence(left, right)
        observable_codes = {
            "same_scene",
            "scene_change",
            "same_reality_layer",
            "reality_layer_change",
            "same_time",
            "time_change",
            "boundary_state_match",
            "source_unavailable",
        }
        false_observable = (evidence_codes & observable_codes) - (
            observed_positive | observed_hard
        )
        if false_observable:
            raise GroupingReviewError(
                f"GROUPING_REVIEW_EVIDENCE_CONFLICT: {path} 的来源可观察证据不成立："
                f"{', '.join(sorted(false_observable))}。"
            )
        if observed_hard and boundary_class != "hard_split":
            raise GroupingReviewError(
                f"GROUPING_REVIEW_HARD_SPLIT_REQUIRED: {path} 检测到 "
                f"{', '.join(sorted(observed_hard))}。"
            )
        if observed_hard - evidence_codes:
            raise GroupingReviewError(
                f"GROUPING_REVIEW_EVIDENCE_INCOMPLETE: {path} 未声明来源可验证的硬拆证据。"
            )
        all_compatible = all(
            compatibility.get(key) is True for key in COMPATIBILITY_KEYS
        )
        if boundary_class == "hard_split":
            if not observed_hard:
                raise GroupingReviewError(
                    f"GROUPING_REVIEW_HARD_SPLIT_INVALID: {path} 没有来源可验证的硬拆证据。"
                )
        elif boundary_class == "prefer_join":
            if not all_compatible:
                raise GroupingReviewError(
                    f"GROUPING_REVIEW_PREFER_JOIN_INVALID: {path} 的 prefer_join "
                    "要求十项语义兼容。"
                )
            if not evidence_codes & GROUPING_JOIN_EVIDENCE:
                raise GroupingReviewError(
                    f"GROUPING_REVIEW_PREFER_JOIN_INVALID: {path} 缺少正向承接证据。"
                )
        else:
            if all_compatible and not evidence_codes & GROUPING_SPLIT_EVIDENCE:
                raise GroupingReviewError(
                    f"GROUPING_REVIEW_PREFER_SPLIT_INVALID: {path} 的全兼容边界"
                    "必须说明表演、摄影机、叙事阶段或信息密度理由。"
                )
        boundary_records.append(
            {
                "left_source_shot_id": left_id,
                "right_source_shot_id": right_id,
                "classification": boundary_class,
                "semantic_evidence": sorted(evidence_codes),
                "compatibility": copy.deepcopy(compatibility),
                "reason": reason,
            }
        )

    # Optimize the whole ordered scope. Capacity is evaluated on candidate units,
    # not encoded by falsifying semantic compatibility at a local boundary.
    count = len(shots)
    best: list[tuple[int, int, int, list[tuple[int, int]]] | None] = [None] * (count + 1)
    best[count] = (0, 0, 0, [])
    for start in range(count - 1, -1, -1):
        duration_total = Decimal("0")
        known_duration = True
        for end in range(start, min(count, start + max_cuts)):
            duration = duration_of(shots[end])
            if duration is None:
                known_duration = False
            else:
                duration_total += duration
            if end > start:
                prior_boundary = boundary_records[end - 1]
                prior_compatible = all(
                    prior_boundary["compatibility"].get(key) is True
                    for key in COMPATIBILITY_KEYS
                )
                if (
                    prior_boundary["classification"] == "hard_split"
                    or not prior_compatible
                ):
                    break
            if end > start and (not known_duration or duration_total > max_group_duration):
                break
            if end == start or (known_duration and duration_total <= max_group_duration):
                tail = best[end + 1]
                if tail is None:
                    continue
                score = tail[0]
                for boundary_index in range(start, end):
                    score += (
                        10
                        if boundary_records[boundary_index]["classification"] == "prefer_join"
                        else -6
                    )
                if end < count - 1:
                    split_class = boundary_records[end]["classification"]
                    score += 6 if split_class == "prefer_split" else (
                        -10 if split_class == "prefer_join" else 0
                    )
                candidate = (
                    score,
                    -(1 + -tail[1]),
                    -((1 if end == start else 0) + -tail[2]),
                    [(start, end)] + tail[3],
                )
                current = best[start]
                # Stable tie-break: after score and unit count, prefer the
                # longest earliest unit. This avoids avoidable leading singletons.
                if current is None or candidate > current:
                    best[start] = candidate
    if best[0] is None:
        raise GroupingReviewError(
            "GROUPING_PARTITION_UNAVAILABLE: 来源时长或 Profile 上限无法形成完整分区。"
        )

    planned: list[dict[str, Any]] = []
    selected_ranges = best[0][3]
    for range_index, (start, end) in enumerate(selected_ranges):
        selected = list(shots[start : end + 1])
        joined_boundaries = copy.deepcopy(boundary_records[start:end])
        is_multi = len(selected) > 1
        if is_multi:
            grouping_reason = "；".join(
                f"{item['left_source_shot_id']}→{item['right_source_shot_id']}"
                f"[{item['classification']}]：{item['reason']}"
                for item in joined_boundaries
            )
        else:
            grouping_reason = None
        entry_reason = "scope_start"
        if range_index > 0:
            previous_start, previous_end = selected_ranges[range_index - 1]
            split_boundary = boundary_records[start - 1]
            if split_boundary["classification"] == "hard_split":
                entry_reason = "hard_split"
            elif split_boundary["classification"] == "prefer_split":
                entry_reason = "semantic_preference"
            else:
                previous_durations = [
                    duration_of(item)
                    for item in shots[previous_start : previous_end + 1]
                ]
                next_durations = [
                    duration_of(item) for item in shots[start : end + 1]
                ]
                if (
                    all(item is not None for item in previous_durations)
                    and all(item is not None for item in next_durations)
                    and sum(previous_durations, Decimal("0"))
                    + sum(next_durations, Decimal("0"))
                    > max_group_duration
                ):
                    entry_reason = "profile_duration_limit"
                elif previous_end - previous_start + 2 > max_cuts:
                    entry_reason = "profile_cut_limit"
                else:
                    entry_reason = "global_quality_tradeoff"
        planned.append(
            {
                "shots": selected,
                "grouping_reason": grouping_reason,
                "semantic_compatibility": (
                    {key: True for key in COMPATIBILITY_KEYS} if is_multi else None
                ),
                "standalone_reason": None if is_multi else "global_partition_split",
                "partition_strategy": GROUPING_PARTITION_POLICY,
                "partition_entry_reason": entry_reason,
                "boundary_evidence": joined_boundaries,
            }
        )
    return planned, []


def _camera_prompt_fields(camera: Mapping[str, Any]) -> tuple[str, str, str]:
    shot_size = ""
    for key in ("shot_size", "framing", "size"):
        shot_size = _preserve_text(
            _render_descriptive_value(camera.get(key))
        )
        if shot_size:
            break

    angle = _preserve_text(
        _render_descriptive_value(camera.get("angle"))
    )
    movement = _preserve_text(
        _render_descriptive_value(camera.get("movement"))
    )
    composition = _preserve_text(
        _render_descriptive_value(camera.get("composition"))
    )
    camera_elements = [
        item for item in (angle, shot_size, movement) if item
    ]
    prefix = f"【{'，'.join(camera_elements)}】" if camera_elements else ""
    return prefix + composition, angle, shot_size


def _strip_rendered_headers(text: str) -> str:
    cleaned = text.strip()
    while cleaned.startswith("【"):
        close = cleaned.find("】")
        if close < 0:
            break
        cleaned = cleaned[close + 1 :].lstrip()
    return cleaned.replace("\r\n", "\n").replace("\r", "\n").strip()


def _split_environment_and_action(
    shot: Mapping[str, Any],
) -> tuple[str, str]:
    rendered = _strip_rendered_headers(
        _clean_text(shot.get("rendered_shot_description"))
    )
    if not rendered:
        return "", ""

    environment = ""
    action = rendered
    camera_match = re.search(
        r"(?:摄影机|机位)(?:从|位于|固定|不换位置|以|设在|落在|处在|保持|沿|在)",
        action,
    )
    if camera_match is not None:
        camera_marker = camera_match.start()
        environment = action[:camera_marker].strip(" \n；。，")
        camera_tail = action[camera_marker:]
        separators = [
            position
            for separator in ("；", "。")
            for position in [camera_tail.find(separator)]
            if position >= 0
        ]
        action = (
            camera_tail[min(separators) + 1 :]
            if separators
            else ""
        )

    composition = _preserve_text(
        _render_descriptive_value(
            shot.get("camera", {}).get("composition")
            if isinstance(shot.get("camera"), dict)
            else None
        )
    )
    if composition:
        action = action.replace(f"画面中{composition}。", "", 1)
        action = action.replace(f"画面中{composition}；", "", 1)
        action = action.replace(f"画面中{composition}", "", 1)

    kept_sentences: list[str] = []
    for sentence in re.split(r"(?<=[。！？])", action):
        sentence = sentence.strip()
        if not sentence:
            continue
        comparable_sentence = re.sub(r"[\W_]+", "", sentence)
        comparable_composition = re.sub(r"[\W_]+", "", composition)
        redundant = False
        if (
            comparable_sentence
            and comparable_composition
            and not QUOTED_TEXT_RE.search(sentence)
        ):
            similarity = SequenceMatcher(
                None, comparable_sentence, comparable_composition
            ).ratio()
            redundant = (
                similarity >= 0.47
                or (
                    min(
                        len(comparable_sentence),
                        len(comparable_composition),
                    )
                    >= 8
                    and (
                        comparable_sentence in comparable_composition
                        or comparable_composition in comparable_sentence
                    )
                )
            )
        if not redundant:
            kept_sentences.append(sentence)
    return environment, "".join(kept_sentences).strip(" \n；")


def _normalized_fact_text(value: Any) -> str:
    return re.sub(
        r"[\s\W_]+",
        "",
        _preserve_text(_render_descriptive_value(value)).casefold(),
    )


def _replace_owned_fact_variant(
    text: str, fact: str, replacement: str
) -> str:
    """Replace an owned fact even when only terminal punctuation differs."""
    candidates = _unique_strings(
        [fact, fact.rstrip(" \t\r\n。！？；，,.!?;")]
    )
    for candidate in sorted(candidates, key=len, reverse=True):
        if candidate and candidate in text:
            return text.replace(candidate, replacement)
    return text


def _novel_clauses(
    text: Any,
    represented_facts: Sequence[Any],
    *,
    drop_camera_clauses: bool = True,
) -> list[str]:
    represented = [
        _normalized_fact_text(value)
        for value in represented_facts
        if _normalized_fact_text(value)
    ]
    seen: set[str] = set()
    result: list[str] = []
    for raw_clause in re.split(
        r"(?<=[。！？；])(?![”’])|\n+", _clean_text(text)
    ):
        clause = raw_clause.strip(" \n；")
        if not clause:
            continue
        if drop_camera_clauses and re.search(r"摄影机", clause):
            for segment in re.split(r"[，,]", clause):
                if not re.search(r"摄影机", segment):
                    result.extend(
                        _novel_clauses(
                            segment,
                            represented_facts,
                            drop_camera_clauses=False,
                        )
                    )
            continue
        comparable = re.sub(
            r"^(?:画面先见|随后|起始状态|终态|状态|画面内容)[：:]?",
            "",
            clause,
        )
        normalized = _normalized_fact_text(comparable)
        if not normalized or normalized in seen:
            continue
        if any(
            normalized == fact
            or (
                min(len(normalized), len(fact)) >= 8
                and (normalized in fact or fact in normalized)
            )
            for fact in represented
        ):
            continue
        if clause.startswith(("焦点始终", "按事件顺序", "最后保持")):
            continue
        seen.add(normalized)
        result.append(clause)
    return result


def _camera_detail_without_owned_facts(
    value: Any,
    owned_facts: Sequence[Any],
) -> str:
    clauses: list[str] = []
    normalized_owned = [
        _normalized_fact_text(fact)
        for fact in owned_facts
        if _normalized_fact_text(fact)
    ]
    for segment in re.split(r"[，,]", _clean_text(value)):
        normalized_segment = _normalized_fact_text(segment)
        if any(fact in normalized_segment for fact in normalized_owned):
            continue
        clauses.extend(
            _novel_clauses(
                segment,
                owned_facts,
                drop_camera_clauses=False,
            )
        )
    return "".join(clauses).strip(" \n；")


def _shot_main_state_change(shot: Mapping[str, Any]) -> str:
    """Select exactly one source-backed state change for a Prompt stage."""
    camera = shot.get("camera", {})
    camera = camera if isinstance(camera, dict) else {}
    candidates: list[Any] = [camera.get("end_frame")]
    candidates.extend(reversed(shot.get("end_state", [])))
    candidates.extend(reversed(shot.get("blocking", [])))
    candidates.extend(
        (
            shot.get("delta_text"),
            _split_environment_and_action(shot)[1],
            camera.get("start_frame"),
        )
    )
    for value in candidates:
        rendered = _preserve_text(_render_descriptive_value(value))
        if rendered:
            return rendered
    return ""


def _legacy_structured_t2v_prompt_parts(
    parts: list[str], shot: Mapping[str, Any]
) -> None:
    """Keep the established field-oriented compiler for non-2.5 adapters."""
    camera = shot.get("camera", {})
    camera = camera if isinstance(camera, dict) else {}
    position = _preserve_text(
        _render_descriptive_value(camera.get("position"))
    )
    logic = (
        ""
        if position
        else _preserve_text(_render_descriptive_value(camera.get("logic")))
    )
    start_frame = _preserve_text(
        _render_descriptive_value(camera.get("start_frame"))
    )
    end_frame = _preserve_text(
        _render_descriptive_value(camera.get("end_frame"))
    )
    if position:
        _append_unique(parts, position, "摄影机位置")
    if logic:
        _append_unique(parts, logic, "摄影机逻辑")
    if start_frame and _normalized_fact_text(start_frame) == _normalized_fact_text(end_frame):
        _append_unique(parts, start_frame, "状态")
    elif start_frame:
        _append_unique(parts, start_frame, "起始状态")
    movement_plan = camera.get("movement_plan")
    movement_plan = movement_plan if isinstance(movement_plan, dict) else {}
    movement = _preserve_text(
        _render_descriptive_value(camera.get("movement"))
    )
    movement_parts: list[str] = []
    for label, value in (
        ("方式", movement),
        ("速度", movement_plan.get("speed")),
        ("路径", movement_plan.get("path")),
        ("触发", movement_plan.get("trigger")),
        ("停止", movement_plan.get("end_condition")),
        ("保持", movement_plan.get("hold_reason")),
    ):
        rendered = _preserve_text(_render_descriptive_value(value))
        if rendered:
            movement_parts.append(f"{label}：{rendered}")
    if movement_parts:
        _append_unique(parts, "；".join(movement_parts), "摄影机运动")
    _append_items(parts, shot.get("blocking", []), "动作")
    _append_items(parts, shot.get("visible_behavior", []), "表演")
    represented: list[Any] = [
        position,
        logic,
        start_frame,
        end_frame,
        movement,
    ]
    represented.extend(shot.get("blocking", []))
    represented.extend(shot.get("visible_behavior", []))
    _, rendered_action = _split_environment_and_action(shot)
    for clause in _novel_clauses(rendered_action, represented):
        _append_unique(parts, clause, "补充画面")
    if end_frame and _normalized_fact_text(start_frame) != _normalized_fact_text(end_frame):
        _append_unique(parts, end_frame, "终态")
    for state in shot.get("end_state", []):
        if _normalized_fact_text(state) not in {
            _normalized_fact_text(start_frame),
            _normalized_fact_text(end_frame),
        }:
            _append_unique(
                parts,
                _preserve_text(_render_descriptive_value(state)),
                "终态补充",
            )


def _structured_t2v_prompt_parts(
    parts: list[str], shot: Mapping[str, Any]
) -> None:
    """Compile one Cut as a readable stage instead of a field dump."""
    camera = shot.get("camera", {})
    camera = camera if isinstance(camera, dict) else {}
    position = _preserve_text(
        _render_descriptive_value(camera.get("position"))
    )
    logic = _preserve_text(_render_descriptive_value(camera.get("logic")))
    start_frame = _preserve_text(
        _render_descriptive_value(camera.get("start_frame"))
    )
    end_frame = _preserve_text(
        _render_descriptive_value(camera.get("end_frame"))
    )
    main_change = _shot_main_state_change(shot)

    if start_frame and _normalized_fact_text(start_frame) != _normalized_fact_text(
        main_change
    ):
        _append_unique(parts, start_frame)

    if position:
        _append_unique(parts, f"摄影机位于{position}")
    elif logic:
        _append_unique(parts, logic)

    movement_plan = camera.get("movement_plan")
    movement_plan = movement_plan if isinstance(movement_plan, dict) else {}
    movement = _preserve_text(
        _render_descriptive_value(camera.get("movement"))
    )
    speed = _preserve_text(
        _render_descriptive_value(movement_plan.get("speed"))
    )
    path = _preserve_text(
        _render_descriptive_value(movement_plan.get("path"))
    )
    if position and path:
        path = path.replace(f"从{position}沿", "沿")
        path = path.replace(f"在{position}", "在既定机位")
        path = path.replace(position, "既定机位")
        path = path.replace("从既定机位沿", "沿")
    trigger = _preserve_text(
        _render_descriptive_value(movement_plan.get("trigger"))
    )
    if (
        start_frame
        and _normalized_fact_text(start_frame)
        in _normalized_fact_text(trigger)
    ):
        trigger = "起始动作发生时"
    end_condition = _preserve_text(
        _render_descriptive_value(movement_plan.get("end_condition"))
    )
    if (
        end_frame
        and _normalized_fact_text(end_frame)
        in _normalized_fact_text(end_condition)
    ):
        end_condition = "主要状态形成时停止"
    hold_reason = _preserve_text(
        _render_descriptive_value(movement_plan.get("hold_reason"))
    )
    same_boundary_state = (
        bool(start_frame)
        and _normalized_fact_text(start_frame)
        == _normalized_fact_text(end_frame)
    )
    if hold_reason and same_boundary_state:
        hold_reason = "固定观察直到主要状态形成，并保持动作、声音或表演连续"
    else:
        if end_frame:
            hold_reason = _replace_owned_fact_variant(
                hold_reason, end_frame, "主要状态形成"
            )
        if start_frame:
            hold_reason = _replace_owned_fact_variant(
                hold_reason, start_frame, "起始状态"
            )
    movement_bits: list[str] = []
    if movement:
        movement_bits.append(f"镜头{movement}")
    if speed:
        movement_bits.append(f"速度{speed}")
    if path:
        movement_bits.append(path)
    if trigger:
        movement_bits.append(f"在{trigger}启动")
    if end_condition:
        movement_bits.append(end_condition)
    if hold_reason:
        movement_bits.append(hold_reason)
    if movement_bits:
        _append_unique(parts, "，".join(movement_bits))

    spatial_strategy = camera.get("spatial_strategy")
    spatial_strategy = (
        spatial_strategy if isinstance(spatial_strategy, dict) else {}
    )
    spatial_description = _camera_detail_without_owned_facts(
        spatial_strategy.get("description"),
        (position, start_frame, end_frame),
    )
    watching_path = re.search(r"(观看先.+)$", spatial_description)
    if watching_path:
        spatial_description = watching_path.group(1)
    if spatial_description and not re.search(
        r"观看先落在(.+?)再转向\1(?:[。；]|$)", spatial_description
    ):
        _append_unique(parts, spatial_description)

    for value in shot.get("blocking", []):
        rendered = _preserve_text(_render_descriptive_value(value))
        if _normalized_fact_text(rendered) != _normalized_fact_text(main_change):
            _append_unique(parts, rendered)
    _append_items(parts, shot.get("visible_behavior", []), "")

    represented_facts: list[Any] = [
        position,
        logic,
        start_frame,
        end_frame,
        movement,
        speed,
        path,
        trigger,
        end_condition,
        hold_reason,
        spatial_description,
        main_change,
    ]
    represented_facts.extend(shot.get("blocking", []))
    represented_facts.extend(shot.get("visible_behavior", []))
    represented_facts.extend(_dialogue_texts(shot.get("dialogue", [])))
    if not (position and start_frame and end_frame and movement_plan):
        _, rendered_action = _split_environment_and_action(shot)
        for clause in _novel_clauses(rendered_action, represented_facts):
            _append_unique(parts, clause)

    if main_change:
        _append_unique(parts, main_change, "主要状态变化")
    for state in shot.get("end_state", []):
        if _normalized_fact_text(state) not in {
            _normalized_fact_text(start_frame),
            _normalized_fact_text(main_change),
        }:
            _append_unique(
                parts,
                _preserve_text(_render_descriptive_value(state)),
            )


def _clean_scene_label(scene_context: Any) -> str:
    if not isinstance(scene_context, dict):
        return ""
    label = _preserve_text(
        _render_descriptive_value(scene_context.get("scene"))
    )
    if label:
        return re.sub(
            r"^\s*(?:SC\d+|\d+(?:-\d+)*)\s*",
            "",
            label,
            flags=re.IGNORECASE,
        ).strip()
    return " ".join(
        item
        for item in (
            _preserve_text(
                _render_descriptive_value(scene_context.get("location"))
            ),
            _preserve_text(
                _render_descriptive_value(
                    scene_context.get("time_of_day")
                    or scene_context.get("time")
                )
            ),
        )
        if item
    )


def _unit_scene_line(shots: Sequence[Mapping[str, Any]]) -> str:
    labels: list[str] = []
    environments: list[str] = []
    for shot in shots:
        scene_context = shot.get("scene_context")
        label = _clean_scene_label(scene_context)
        if label and label not in labels:
            labels.append(label)
        if isinstance(scene_context, dict):
            for key in ("location", "time_of_day", "time"):
                context_value = _preserve_text(
                    _render_descriptive_value(scene_context.get(key))
                )
                if (
                    context_value
                    and context_value not in label
                    and context_value not in labels
                ):
                    labels.append(context_value)
        context_environment = ""
        if isinstance(scene_context, dict):
            context_environment = _preserve_text(
                _render_descriptive_value(
                    scene_context.get("environment_description")
                    or scene_context.get("environment")
                )
            )
        rendered_environment, _ = _split_environment_and_action(shot)
        environment = context_environment or rendered_environment
        if (
            label
            and _normalized_fact_text(label)
            in _normalized_fact_text(environment)
        ):
            environment = ""
        for existing_label in labels:
            if _normalized_fact_text(environment) == _normalized_fact_text(
                existing_label
            ):
                environment = ""
                break
        if environment and environment not in environments:
            environments.append(environment)
        for item in shot.get("scene_material", []):
            rendered_item = _preserve_text(
                _render_descriptive_value(item)
            )
            if rendered_item and rendered_item not in environments:
                environments.append(rendered_item)
    scene_parts = labels + environments
    if not scene_parts:
        return ""
    line = "场景：" + "，".join(scene_parts)
    return _with_terminal_punctuation(line)


def _transition_text(transition: Mapping[str, Any]) -> str:
    transition_type = _clean_text(transition.get("type"))
    notes = _clean_text(transition.get("notes"))
    if transition_type in ("", "cut", "scene_end") and not notes:
        return ""
    if transition_type and notes:
        return f"转场：{transition_type}，{notes}"
    return f"转场：{transition_type or notes}"


def _reference_roles_for_shot(
    generation: Mapping[str, Any], shot_id: str
) -> list[Mapping[str, Any]]:
    return [
        item
        for item in generation.get("reference_role_map", [])
        if isinstance(item, dict)
        and (
            "*" in item.get("applies_to_shot_ids", [])
            or shot_id in item.get("applies_to_shot_ids", [])
        )
    ]


def _all_generation_reference_tags(
    generation: Mapping[str, Any]
) -> list[str]:
    return _unique_strings(
        str(item.get("tag"))
        for item in generation.get("reference_role_map", [])
        if isinstance(item, dict) and _clean_text(item.get("tag"))
    )


def _global_reference_section(profile: Mapping[str, Any]) -> bool:
    return (
        profile.get("prompt_adapter_id")
        == "seedance-2.5-structured-zh-v1"
    )


def _generation_for_unit(
    generation: Mapping[str, Any],
    shots: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    shot_ids = {
        _clean_text(shot.get("source_shot_id")) for shot in shots
    }

    def applies(item: Mapping[str, Any]) -> bool:
        scope = item.get("applies_to_shot_ids", [])
        return isinstance(scope, list) and (
            "*" in scope or bool(shot_ids.intersection(scope))
        )

    result = copy.deepcopy(dict(generation))
    roles = [
        copy.deepcopy(item)
        for item in generation.get("reference_role_map", [])
        if isinstance(item, dict) and applies(item)
    ]
    assignments = [
        copy.deepcopy(item)
        for item in generation.get("asset_assignments", [])
        if isinstance(item, dict) and applies(item)
    ]
    result["reference_role_map"] = roles
    result["asset_assignments"] = assignments
    result["available_reference_tags"] = _unique_strings(
        _clean_text(item.get("tag")) for item in roles
    )
    return result


def _reference_instruction(item: Mapping[str, Any]) -> str:
    tag = str(item["tag"])
    role = str(item["role"])
    if role == "first_frame":
        return f"{tag}作为首帧。"
    if role == "last_frame":
        return f"{tag}作为尾帧。"
    role_label = REFERENCE_ROLE_LABELS.get(role, role)
    qualifier = "仅作" if role in {"motion_reference", "camera_motion"} else "作为"
    preserve = [
        _preserve_text(_clean_text(value))
        for value in item.get("preserve", [])
        if _preserve_text(_clean_text(value))
    ]
    preserve_text = f"，保持 {'、'.join(preserve)}" if preserve else ""
    return f"{tag} {qualifier}{role_label}{preserve_text}"


def _append_unique(parts: list[str], text: str, label: str = "") -> None:
    cleaned = _preserve_text(text)
    if not cleaned:
        return
    rendered = f"{label}：{cleaned}" if label else cleaned
    if cleaned not in "；".join(parts):
        parts.append(rendered)


def _append_items(
    parts: list[str], values: Sequence[Any], label: str
) -> None:
    rendered = [
        _preserve_text(_render_descriptive_value(item))
        for item in values
    ]
    rendered = [item for item in rendered if item]
    for item in rendered:
        _append_unique(parts, item, label)


def _join_prompt_parts(parts: Sequence[str]) -> str:
    joined = ""
    for part in parts:
        if not joined:
            joined = part
            continue
        separator = "" if _has_terminal_punctuation(joined) else "；"
        joined += separator + part
    return joined


def _append_scene_context(parts: list[str], scene_context: Any) -> None:
    if not isinstance(scene_context, dict):
        return
    labels = (
        ("scene", "场景"),
        ("location", "地点"),
        ("time", "时间"),
        ("time_of_day", "时段"),
        ("reality_layer", "现实层"),
        ("environment", "环境"),
        ("environment_description", "环境"),
    )
    for key, label in labels:
        rendered = _render_descriptive_value(scene_context.get(key))
        if rendered:
            _append_unique(parts, rendered, label)


def _render_continuity_update(value: Any) -> str:
    if not isinstance(value, dict):
        return _render_descriptive_value(value)
    entity_type = _clean_text(value.get("entity_type"))
    entity = _clean_text(value.get("entity"))
    field = _clean_text(value.get("field"))
    before = _clean_text(value.get("from"))
    after = _clean_text(value.get("to"))
    if not any((entity_type, entity, field, before, after)):
        return canonical_json(value)
    subject = "／".join(
        item for item in (entity_type, entity, field) if item
    )
    change = f"{before} → {after}" if before or after else ""
    rendered = "：".join(item for item in (subject, change) if item)
    evidence = value.get("evidence_fact_ids")
    if isinstance(evidence, list) and evidence:
        rendered += "（证据：" + "、".join(str(item) for item in evidence) + "）"
    return rendered


def _append_continuity_updates(parts: list[str], updates: Any) -> None:
    if not isinstance(updates, list):
        return
    rendered = [
        _preserve_text(_render_continuity_update(item))
        for item in updates
    ]
    rendered = [item for item in rendered if item]
    if rendered:
        _append_unique(parts, "；".join(rendered), "连续性变化")


def _has_structured_visual_equivalent(shot: Mapping[str, Any]) -> bool:
    return any(
        (
            bool(shot.get("blocking")),
            bool(shot.get("visible_behavior")),
            bool(shot.get("dialogue")),
            bool(shot.get("delta_text")),
            bool(shot.get("continuity_updates")),
            bool(shot.get("allowed_lighting_changes")),
        )
    )


def _shot_prompt_content(
    shot: Mapping[str, Any],
    emotion_visualization: Sequence[Mapping[str, str]],
    generation: Mapping[str, Any],
    *,
    include_reference_roles: bool = True,
) -> str:
    parts: list[str] = []
    mode = str(generation.get("mode", "t2v"))
    shot_id = str(shot["source_shot_id"])
    reference_roles = _reference_roles_for_shot(generation, shot_id)
    camera = shot.get("camera", {})
    camera = camera if isinstance(camera, dict) else {}
    position = _preserve_text(
        _render_descriptive_value(camera.get("position"))
    )
    camera_logic = _preserve_text(
        _render_descriptive_value(camera.get("logic"))
    )
    seedance_generation = (
        mode in {"t2v", "i2v", "v2v", "r2v", "flf2v"}
        and generation.get("global_reference_section") is True
    )
    if mode == "t2v" and not seedance_generation:
        _legacy_structured_t2v_prompt_parts(parts, shot)
        _append_items(parts, shot.get("visible_props", []), "可见道具")
        _append_items(
            parts,
            [
                _render_continuity_update(item)
                for item in shot.get("continuity_updates", [])
            ],
            "",
        )
        lighting_style = shot.get("lighting_style", {})
        if isinstance(lighting_style, dict):
            _append_unique(
                parts,
                _render_descriptive_value(lighting_style.get("lighting")),
            )
            _append_unique(
                parts,
                _render_descriptive_value(lighting_style.get("style")),
            )
    elif seedance_generation:
        _structured_t2v_prompt_parts(parts, shot)
        if not {
            str(item["role"]) for item in reference_roles
        }.intersection({"subject_identity", "appearance"}):
            _append_items(parts, shot.get("subjects", []), "")
        if include_reference_roles:
            for item in reference_roles:
                parts.append(_reference_instruction(item))
        _append_items(
            parts, shot.get("visible_props", []), "可见道具"
        )
        _append_items(
            parts,
            [
                _render_continuity_update(item)
                for item in shot.get("continuity_updates", [])
            ],
            "",
        )
        lighting_style = shot.get("lighting_style", {})
        if isinstance(lighting_style, dict):
            lighting = _render_descriptive_value(
                lighting_style.get("lighting")
            )
            style = _render_descriptive_value(lighting_style.get("style"))
            _append_unique(parts, lighting)
            _append_unique(parts, style)
    else:
        if position:
            camera_text = f"摄影机位于{position}"
            if camera_logic:
                camera_text += f"，{camera_logic}"
            _append_unique(parts, camera_text)
        elif camera_logic:
            _append_unique(parts, camera_logic)
        if include_reference_roles:
            for item in reference_roles:
                parts.append(_reference_instruction(item))
        reference_role_names = {str(item["role"]) for item in reference_roles}
        if mode == "edit":
            for delta in generation.get("edit_deltas", []):
                if not isinstance(delta, dict):
                    continue
                applies = delta.get("applies_to_shot_ids", [])
                if applies and shot_id not in applies:
                    continue
                instruction = _clean_text(delta.get("instruction"))
                layer = _clean_text(delta.get("layer"))
                _append_unique(parts, instruction, f"仅修改 {layer}")
        if mode == "extend":
            extend_context = generation.get("extend_context", {})
            extend_context = (
                extend_context if isinstance(extend_context, dict) else {}
            )
            direction = _clean_text(extend_context.get("direction"))
            boundary = _clean_text(
                extend_context.get("boundary_state")
                or extend_context.get("observed_end_state")
            )
            parts.append(
                (
                    f"从已接受素材的{boundary}向{direction}连续延长"
                    if direction and boundary
                    else "从已接受素材的观测边界状态连续延长"
                )
            )
            for key, label in (
                ("motion_trend", "保持运动趋势"),
                ("audio_state", "保持边界声音状态"),
                ("single_instance", "保持连续主体"),
            ):
                value = _clean_text(extend_context.get(key))
                if value:
                    _append_unique(parts, value, label)
        if not reference_role_names & {"subject_identity", "appearance"}:
            _append_items(parts, shot.get("subjects", []), "")
        rendered_description = _clean_text(
            shot.get("rendered_shot_description")
        )
        if (
            rendered_description
            and not _has_structured_visual_equivalent(shot)
        ):
            _append_unique(
                parts, _split_environment_and_action(shot)[1]
            )
        _append_unique(parts, _clean_text(shot.get("delta_text")))
        _append_items(parts, shot.get("blocking", []), "")
        _append_items(
            parts, shot.get("visible_behavior", []), ""
        )
        _append_items(
            parts, shot.get("visible_props", []), "可见道具"
        )
        _append_items(
            parts,
            [
                _render_continuity_update(item)
                for item in shot.get("continuity_updates", [])
            ],
            "",
        )
        _append_items(
            parts,
            shot.get("allowed_lighting_changes", []),
            "允许的光线变化",
        )

    for item in shot.get("dialogue", []):
        rendered = _render_dialogue(item)
        text = (
            _clean_text(item.get("text"))
            if isinstance(item, dict)
            else _clean_text(item)
        )
        if rendered and text and text not in "；".join(parts):
            parts.append(rendered)
    _append_items(parts, shot.get("audio", []), "声音")
    _append_items(parts, shot.get("constraints", []), "约束")

    if mode != "edit":
        for item in emotion_visualization:
            text = _clean_text(item.get("text"))
            if text:
                _append_unique(parts, text, "情绪可视化（下游派生）")

    return _join_prompt_parts(parts)


def _prompt_goal(
    shots: Sequence[Mapping[str, Any]], generation: Mapping[str, Any]
) -> str:
    story_contract = generation.get("story_contract", {})
    if isinstance(story_contract, dict):
        for key in ("generation_goal", "summary", "logline", "overview"):
            value = _preserve_text(
                _render_descriptive_value(story_contract.get(key))
            )
            if value:
                return _with_terminal_punctuation(value)
    mode = _clean_text(generation.get("mode"))
    if mode == "edit":
        return "只修改唯一编辑母版中明确指定的对象和范围，继承原有时间线。"
    if mode == "extend":
        context = generation.get("extend_context", {})
        context = context if isinstance(context, dict) else {}
        direction = _clean_text(context.get("direction"))
        if direction:
            return f"从唯一延长源的边界向{direction}连续延长，只生成边界之外的新片段。"
        return "从唯一延长源的既定边界连续延长，只生成边界之外的新片段。"

    scenes = _unique_strings(
        _clean_scene_label(shot.get("scene_context")) for shot in shots
    )
    scene_text = "、".join(scenes) or "既定场景"
    first_change = _shot_main_state_change(shots[0]) if shots else ""
    final_change = _shot_main_state_change(shots[-1]) if shots else ""
    if first_change and final_change:
        if _normalized_fact_text(first_change) == _normalized_fact_text(
            final_change
        ):
            return _with_terminal_punctuation(
                f"在{scene_text}中，围绕{first_change.rstrip('。！？；')}这一来源事件展开"
            )
        return _with_terminal_punctuation(
            f"在{scene_text}中，以{first_change.rstrip('。！？；')}为起点，"
            f"沿既定事件顺序推进，最终到达{final_change.rstrip('。！？；')}的状态"
        )
    if first_change or final_change:
        return _with_terminal_punctuation(
            f"在{scene_text}中，{first_change or final_change}"
        )
    return f"在{scene_text}中按既定事件顺序推进并到达来源最终状态。"


def _subject_relationship_lines(
    shots: Sequence[Mapping[str, Any]], generation: Mapping[str, Any]
) -> list[str]:
    story_contract = generation.get("story_contract", {})
    result: list[str] = []
    if isinstance(story_contract, dict):
        for key in ("subjects", "relationships"):
            values = story_contract.get(key, [])
            if isinstance(values, list):
                for value in values:
                    rendered = _preserve_text(
                        _render_descriptive_value(value)
                    )
                    if rendered and rendered not in result:
                        result.append(rendered)
    if result:
        return result
    fallback_subjects: list[str] = []
    for shot in shots:
        camera = shot.get("camera", {})
        camera = camera if isinstance(camera, dict) else {}
        primary = camera.get("primary_subjects", [])
        primary = primary if isinstance(primary, list) else []
        for value in primary:
            rendered = _preserve_text(_render_descriptive_value(value))
            if rendered and rendered not in fallback_subjects:
                fallback_subjects.append(rendered)
    if fallback_subjects:
        result.append("本单元核心主体：" + "、".join(fallback_subjects[:10]))
    return result


def _continuity_lines(
    shots: Sequence[Mapping[str, Any]], generation: Mapping[str, Any]
) -> list[str]:
    story_contract = generation.get("story_contract", {})
    preserve = (
        story_contract.get("preserve", [])
        if isinstance(story_contract, dict)
        else []
    )
    result = [
        _preserve_text(_render_descriptive_value(value))
        for value in preserve
        if _preserve_text(_render_descriptive_value(value))
    ]
    if not result:
        result.append(
            "相邻 Cut 只承接来源已经给出的主体、道具、空间、"
            "摄影机与声音状态，不交换主体、道具或对白。"
        )
    return _unique_strings(result)


def _asset_responsibility_lines(
    generation: Mapping[str, Any],
) -> list[str]:
    binding = generation.get("asset_binding", {})
    if not isinstance(binding, dict) or binding.get("state") != "mapped":
        return []
    assignments = [
        item
        for item in generation.get("asset_assignments", [])
        if isinstance(item, dict)
    ]
    lines: list[str] = []
    for item in assignments:
        tag = _clean_text(item.get("tag"))
        target = _clean_text(item.get("target_entity"))
        role = _clean_text(item.get("role"))
        adopted = [
            _clean_text(value)
            for value in item.get("adopted_dimensions", [])
            if _clean_text(value)
        ]
        rejected = [
            _clean_text(value)
            for value in item.get("rejected_dimensions", [])
            if _clean_text(value)
        ]
        if not tag:
            continue
        if role == "first_frame":
            text = f"{tag}作为首帧"
        elif role == "last_frame":
            text = f"{tag}作为尾帧"
        elif role == "edit_source":
            text = f"{tag}作为唯一编辑母版"
            if target:
                text += f"，用于{target}"
        elif role == "extension_source":
            text = f"{tag}作为唯一延长源"
            if target:
                text += f"，用于{target}"
        else:
            text = f"{tag}用于{target}" if target else tag
        if adopted and role not in {"first_frame", "last_frame"}:
            text += f"的{'、'.join(adopted)}"
        if rejected:
            text += f"，不采用{'、'.join(rejected)}"
        lines.append(_with_terminal_punctuation(text))
    if lines:
        return _unique_strings(lines)
    return [
        _with_terminal_punctuation(_reference_instruction(item))
        for item in generation.get("reference_role_map", [])
        if isinstance(item, dict)
    ]


def _subject_relationship_scene_lines(
    shots: Sequence[Mapping[str, Any]], generation: Mapping[str, Any]
) -> list[str]:
    result = _subject_relationship_lines(shots, generation)
    scene_lines: list[str] = []
    prop_values: list[str] = []
    for shot in shots:
        context = shot.get("scene_context", {})
        if isinstance(context, dict):
            values: list[str] = []
            for key in (
                "scene",
                "location",
                "time",
                "time_of_day",
                "environment",
                "environment_description",
            ):
                value = _preserve_text(
                    _render_descriptive_value(context.get(key))
                )
                if value and value not in values:
                    values.append(value)
            if values:
                line = "场景与空间：" + "，".join(values)
                if line not in scene_lines:
                    scene_lines.append(line)
        for raw_prop in shot.get("visible_props", []):
            prop = _preserve_text(_render_descriptive_value(raw_prop))
            if prop and prop not in prop_values:
                prop_values.append(prop)
    result.extend(scene_lines)
    if prop_values:
        result.append("关键道具以来源状态为准：" + "、".join(prop_values))
    return _unique_strings(result) or [
        "本单元主体、关系与场景均以来源事实为准。"
    ]


def _boundary_handoff_line(
    previous_shot: Mapping[str, Any],
    current_shot: Mapping[str, Any],
    previous_cut_label: str,
) -> str:
    previous_camera = previous_shot.get("camera", {})
    previous_camera = previous_camera if isinstance(previous_camera, dict) else {}
    current_camera = current_shot.get("camera", {})
    current_camera = current_camera if isinstance(current_camera, dict) else {}
    previous_end = _preserve_text(
        _render_descriptive_value(previous_camera.get("end_frame"))
    )
    if not previous_end:
        for value in reversed(previous_shot.get("end_state", [])):
            previous_end = _preserve_text(_render_descriptive_value(value))
            if previous_end:
                break
    current_start = _preserve_text(
        _render_descriptive_value(current_camera.get("start_frame"))
    )
    if (
        previous_end
        and current_start
        and _normalized_fact_text(previous_end)
        == _normalized_fact_text(current_start)
    ):
        return _with_terminal_punctuation(
            f"承接 {previous_cut_label} 的{current_start.rstrip('。！？；')}"
        )
    return ""


def _cross_cut_sound_lines(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    generation: Mapping[str, Any],
) -> list[str]:
    if len(shots) < 2:
        return []
    speaker_cuts: dict[str, set[str]] = {}
    sound_cuts: dict[str, set[str]] = {}
    constraint_cuts: dict[str, set[str]] = {}
    for shot, cut in zip(shots, timeline):
        cut_label = str(cut.get("cut_label", "Cut"))
        for item in shot.get("dialogue", []):
            if isinstance(item, dict):
                speaker = _clean_text(
                    item.get("speaker") or item.get("character")
                )
                if speaker:
                    speaker_cuts.setdefault(speaker, set()).add(cut_label)
        for item in shot.get("audio", []):
            rendered = _preserve_text(_render_descriptive_value(item))
            if rendered:
                sound_cuts.setdefault(rendered, set()).add(cut_label)
        for item in shot.get("constraints", []):
            rendered = _preserve_text(_render_descriptive_value(item))
            if rendered:
                constraint_cuts.setdefault(rendered, set()).add(cut_label)

    cross_speakers = {
        speaker for speaker, cuts in speaker_cuts.items() if len(cuts) > 1
    }
    cross_sounds = {
        sound for sound, cuts in sound_cuts.items() if len(cuts) > 1
    }
    cross_constraints = {
        value for value, cuts in constraint_cuts.items() if len(cuts) > 1
    }
    lines: list[str] = []
    for shot, cut in zip(shots, timeline):
        cut_label = str(cut.get("cut_label", "Cut"))
        for item in shot.get("dialogue", []):
            if not isinstance(item, dict):
                continue
            speaker = _clean_text(
                item.get("speaker") or item.get("character")
            )
            if speaker not in cross_speakers:
                continue
            rendered = _render_dialogue(item)
            if not rendered:
                continue
            position = _clean_text(
                item.get("shot_delivery")
                or item.get("position")
                or item.get("on_screen")
            )
            qualifier = f"（{position}）" if position else ""
            lines.append(f"{cut_label}{qualifier}：{rendered}")
    for sound in sorted(cross_sounds):
        cuts = sorted(sound_cuts[sound], key=lambda value: int(re.sub(r"\D", "", value) or 0))
        lines.append(f"{'、'.join(cuts)}保持同一声音来源：{sound}")
    for value in sorted(cross_constraints):
        cuts = sorted(constraint_cuts[value], key=lambda item: int(re.sub(r"\D", "", item) or 0))
        lines.append(f"{'、'.join(cuts)}共同遵守：{value}")
    for assignment in generation.get("asset_assignments", []):
        if not isinstance(assignment, dict) or _clean_text(
            assignment.get("role")
        ) != "audio_reference":
            continue
        scope = assignment.get("applies_to_shot_ids", [])
        applicable = [
            str(cut.get("cut_label"))
            for shot, cut in zip(shots, timeline)
            if "*" in scope or str(shot.get("source_shot_id")) in scope
        ]
        if len(applicable) < 2:
            continue
        tag = _clean_text(assignment.get("tag"))
        target = _clean_text(assignment.get("target_entity"))
        adopted = [
            _clean_text(value)
            for value in assignment.get("adopted_dimensions", [])
            if _clean_text(value)
        ]
        text = f"{tag}用于{target}" if target else tag
        if adopted:
            text += f"的{'、'.join(adopted)}"
        text += f"，适用 {'、'.join(applicable)}"
        lines.append(_with_terminal_punctuation(text))
    return _unique_strings(lines)


def _sound_dialogue_lines(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    generation: Mapping[str, Any],
) -> list[str]:
    lines: list[str] = []
    voice_positions: dict[tuple[str, str], list[str]] = {}
    speaker_cuts: dict[str, list[str]] = {}
    for shot, cut in zip(shots, timeline):
        cut_label = str(cut.get("cut_label", "Cut"))
        for item in shot.get("dialogue", []):
            if not isinstance(item, dict):
                continue
            speaker = _clean_text(
                item.get("speaker") or item.get("character")
            )
            position = _clean_text(
                item.get("shot_delivery")
                or item.get("position")
                or item.get("on_screen")
            )
            if speaker:
                speaker_cuts.setdefault(speaker, []).append(cut_label)
                if position:
                    voice_positions.setdefault(
                        (speaker, position), []
                    ).append(cut_label)
        for item in shot.get("audio", []):
            rendered = _preserve_text(_render_descriptive_value(item))
            if rendered:
                lines.append(f"{cut_label}声音：{rendered}")
    position_labels = {
        "onscreen": "画内现场声",
        "on_screen": "画内现场声",
        "画内": "画内现场声",
        "offscreen": "画外声",
        "off_screen": "画外声",
        "画外": "画外声",
        "mediated": "媒介声",
        "mediated_source": "媒介声",
        "voiceover": "画外音",
        "voice_over": "画外音",
        "旁白": "旁白",
        "narration": "旁白",
    }
    for (speaker, position), cut_labels in voice_positions.items():
        applicable = _unique_strings(cut_labels)
        label = position_labels.get(position.casefold(), position)
        if label == "画内现场声" and len(applicable) == 1:
            continue
        lines.append(
            f"声音关系：{speaker}为{label}，适用{'、'.join(applicable)}。"
        )
    for speaker, cut_labels in speaker_cuts.items():
        applicable = _unique_strings(cut_labels)
        has_position_contract = any(
            key[0] == speaker for key in voice_positions
        )
        if len(applicable) > 1 and not has_position_contract:
            lines.append(
                f"声音关系：{speaker}的声音身份跨{'、'.join(applicable)}保持一致。"
            )
    for assignment in generation.get("asset_assignments", []):
        if not isinstance(assignment, dict) or _clean_text(
            assignment.get("role")
        ) != "audio_reference":
            continue
        scope = assignment.get("applies_to_shot_ids", [])
        applicable = [
            str(cut.get("cut_label"))
            for shot, cut in zip(shots, timeline)
            if "*" in scope or str(shot.get("source_shot_id")) in scope
        ]
        if not applicable:
            continue
        tag = _clean_text(assignment.get("tag"))
        target = _clean_text(assignment.get("target_entity"))
        adopted = [
            _clean_text(value)
            for value in assignment.get("adopted_dimensions", [])
            if _clean_text(value)
        ]
        rejected = [
            _clean_text(value)
            for value in assignment.get("rejected_dimensions", [])
            if _clean_text(value)
        ]
        text = f"{tag}用于{target}" if target else tag
        if adopted:
            text += f"的{'、'.join(adopted)}"
        if rejected:
            text += f"，不采用{'、'.join(rejected)}"
        text += f"，适用 {'、'.join(applicable)}"
        lines.append(_with_terminal_punctuation(text))
    return _unique_strings(lines) or [NO_SOURCE_SOUND_LINE]


def _seedance_consistency_lines(
    shots: Sequence[Mapping[str, Any]],
    generation: Mapping[str, Any],
    *,
    has_assets: bool,
    has_cross_cut_sound: bool,
) -> list[str]:
    lines: list[str] = []
    mode = _clean_text(generation.get("mode"))
    if mode == "edit":
        lines.append(
            "除以上明确修改对象外，原视频中的其他主体、场景、动作、镜头、时间线和声音保持原样。"
        )
    elif mode == "extend":
        lines.append(
            "保持边界画面、主体数量、道具归属、空间方向、运动趋势和声音状态连续，不改写原视频。"
        )
    lines.extend(_continuity_lines(shots, generation))
    if has_assets:
        lines.append(
            "保持每份已采用素材声明的职责一致，不在不同主体、场景、道具、动作或声音之间交换。"
        )
    if has_cross_cut_sound:
        lines.append(
            "保持跨 Cut 的说话人、声音来源、台词原文和画内／画外关系一致。"
        )
    lines.append(
        "不得新增未由来源、用户要求或已确认约束支持的人物、道具、剧情结果和限制。"
    )
    return _unique_strings(lines)


def _seedance_cut_time(
    cut: Mapping[str, Any], integer_timeline: bool
) -> str:
    if not integer_timeline:
        return "顺序阶段"
    return (
        f"{_seconds_text(cut['start_seconds'])}"
        f"-{_seconds_text(cut['end_seconds'])}S"
    )


def _compile_seedance_25_prompt(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    generation: Mapping[str, Any],
) -> str:
    mode = _clean_text(generation.get("mode"))
    goal_heading = {
        "edit": "【编辑目标】",
        "extend": "【延长目标】",
    }.get(mode, "【生成目标】")
    blocks: list[str] = [
        f"{goal_heading}\n{_prompt_goal(shots, generation)}"
    ]
    asset_lines = _asset_responsibility_lines(generation)
    if asset_lines:
        blocks.append("【参考素材职责】\n" + "\n".join(asset_lines))
    subject_lines = _subject_relationship_scene_lines(shots, generation)
    blocks.append("【主体、关系与场景】\n" + "\n".join(
        _with_terminal_punctuation(value) for value in subject_lines
    ))
    blocks.append("【镜头脚本】")
    integer_timeline = bool(timeline) and all(
        cut.get("start_seconds") is not None
        and cut.get("end_seconds") is not None
        and Decimal(str(cut["start_seconds"]))
        == Decimal(str(cut["start_seconds"])).to_integral_value()
        and Decimal(str(cut["end_seconds"]))
        == Decimal(str(cut["end_seconds"])).to_integral_value()
        for cut in timeline
    )
    for index, (shot, cut) in enumerate(zip(shots, timeline)):
        heading = (
            f"{cut['cut_label']}｜"
            f"{_seedance_cut_time(cut, integer_timeline)}"
        )
        composition, _, _ = _camera_prompt_fields(shot.get("camera", {}))
        content = _shot_prompt_content(
            shot,
            cut.get("emotion_visualization", []),
            generation,
            include_reference_roles=False,
        )
        lines = [heading]
        if index > 0:
            handoff = _boundary_handoff_line(
                shots[index - 1], shot, str(timeline[index - 1]["cut_label"])
            )
            if handoff:
                lines.append(handoff)
        stage_parts = [value for value in (composition, content) if value]
        if stage_parts:
            lines.append(_with_terminal_punctuation(_join_prompt_parts(stage_parts)))
        blocks.append("\n".join(lines))
    sound_lines = _sound_dialogue_lines(shots, timeline, generation)
    blocks.append("【声音与台词】\n" + "\n".join(
        _with_terminal_punctuation(value) for value in sound_lines
    ))
    cross_cut_sound = bool(
        _cross_cut_sound_lines(shots, timeline, generation)
    )
    consistency = _seedance_consistency_lines(
        shots,
        generation,
        has_assets=bool(asset_lines),
        has_cross_cut_sound=cross_cut_sound,
    )
    blocks.append("【保持一致】\n" + "\n".join(
        _with_terminal_punctuation(value) for value in consistency
    ))
    return "\n\n".join(block for block in blocks if block)


def _compile_prompt(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
    generation: Mapping[str, Any],
) -> str:
    adapter = profile["prompt_adapter_id"]
    if adapter == "seedance-2.5-structured-zh-v1":
        return _compile_seedance_25_prompt(shots, timeline, generation)
    total_duration = timeline[-1].get("end_seconds") if timeline else None
    total_line = (
        f"总时长：{_seconds_text(total_duration)}S"
        if total_duration is not None
        else "总时长：来源未提供"
    )
    lines = [total_line]
    scene_line = _unit_scene_line(shots)
    if scene_line and adapter != "seedance-2.5-structured-zh-v1":
        lines.append(scene_line)
    integer_timeline = bool(timeline) and all(
        cut.get("start_seconds") is not None
        and cut.get("end_seconds") is not None
        and Decimal(str(cut["start_seconds"]))
        == Decimal(str(cut["start_seconds"])).to_integral_value()
        and Decimal(str(cut["end_seconds"]))
        == Decimal(str(cut["end_seconds"])).to_integral_value()
        for cut in timeline
    )
    for shot, cut in zip(shots, timeline):
        if adapter == "seedance-2.5-structured-zh-v1" and not integer_timeline:
            cut_time = "顺序阶段"
        elif cut.get("start_seconds") is None or cut.get("end_seconds") is None:
            cut_time = "时间未提供"
        else:
            cut_time = (
                f"{_seconds_text(cut['start_seconds'])}"
                f"-{_seconds_text(cut['end_seconds'])}S"
            )
        heading = f"{cut['cut_label']} : {cut_time}"
        composition, _, _ = _camera_prompt_fields(
            shot.get("camera", {})
        )
        content = _shot_prompt_content(
            shot,
            cut.get("emotion_visualization", []),
            generation,
            include_reference_roles=(
                adapter != "seedance-2.5-structured-zh-v1"
            ),
        )
        if adapter in {
            "explicit-cut-zh-v1",
            "seedance-2.5-structured-zh-v1",
        }:
            lines.append("")
            lines.append(heading)
            if adapter == "seedance-2.5-structured-zh-v1":
                stage_parts: list[str] = []
                if composition:
                    stage_parts.append(composition)
                if content:
                    stage_parts.append(content)
                stage_text = _join_prompt_parts(stage_parts)
                lines.append(_with_terminal_punctuation(stage_text))
            else:
                if composition:
                    composition_line = f"构图：{composition}"
                    composition_line = _with_terminal_punctuation(
                        composition_line
                    )
                    lines.append(composition_line)
                content_line = f"画面内容：{content}"
                if content:
                    content_line = _with_terminal_punctuation(content_line)
                lines.append(content_line)
        elif adapter == "compact-cut-zh-v1":
            compact_parts = [heading]
            if composition:
                compact_parts.append(f"构图：{composition}")
            compact_parts.append(f"画面内容：{content}")
            lines.extend(("", "\n".join(compact_parts)))
        else:  # Profile validation should make this unreachable.
            raise DeliveryError(f"Unsupported prompt adapter: {adapter}")
    return "\n".join(lines)


def _weighted_text_length(text: str) -> float:
    return sum(
        1.0
        if unicodedata.east_asian_width(character) in {"W", "F"}
        else 0.55
        for character in text
    )


def _estimated_visual_lines(text: str, column_width: int) -> int:
    capacity = max(1.0, float(column_width) * 0.82)
    return sum(
        max(1, math.ceil(_weighted_text_length(line) / capacity))
        for line in text.split("\n")
    )


def _estimated_row_height(text: str, column_width: int) -> Decimal:
    return Decimal(_estimated_visual_lines(text, column_width) * 16 + 8)


def _split_prompt_block_text(
    text: str, column_width: int = XLSX_PROMPT_WIDTH_MIN
) -> list[str]:
    if _estimated_row_height(text, column_width) <= XLSX_ROW_HEIGHT_LIMIT:
        return [text]
    protected_pattern = re.compile(
        r"<<<.*?>>>|\{.*?\}|（[^（）]*）|\([^()]*\)|“[^”]*”|‘[^’]*’|"
        r"Cut\s+\d+(?:｜|\s*:)[^\n]*",
        flags=re.DOTALL,
    )
    pieces: list[str] = []
    cursor = 0
    for match in protected_pattern.finditer(text):
        if match.start() > cursor:
            pieces.extend(
                piece
                for piece in re.findall(
                    r"[^。！？；，,\n]+[。！？；，,]?|\n",
                    text[cursor : match.start()],
                )
                if piece
            )
        pieces.append(match.group(0))
        cursor = match.end()
    if cursor < len(text):
        pieces.extend(
            piece
            for piece in re.findall(
                r"[^。！？；，,\n]+[。！？；，,]?|\n",
                text[cursor:],
            )
            if piece
        )
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if _estimated_row_height(piece, column_width) > XLSX_ROW_HEIGHT_LIMIT:
            raise DeliveryError(
                "Prompt block contains an indivisible asset tag, quotation, "
                "Cut title, or paired-bracket span exceeding the XLSX row budget"
            )
        candidate = current + piece
        if (
            current
            and _estimated_row_height(candidate, column_width)
            > XLSX_ROW_HEIGHT_LIMIT
        ):
            chunks.append(current.strip("\n"))
            current = piece.lstrip("\n")
        else:
            current = candidate
    if current.strip("\n"):
        chunks.append(current.strip("\n"))
    return chunks or [text]


def _prompt_blocks(
    prompt_text: str,
    timeline: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    timeline_by_label = {
        str(cut.get("cut_label")): cut for cut in timeline
    }
    blocks: list[dict[str, Any]] = []
    for raw_block in prompt_text.split("\n\n"):
        if not raw_block:
            continue
        kind = "section"
        source_ids: list[str] = []
        match = re.match(r"^(Cut\s+\d+)(?:｜|\s*:)", raw_block)
        if match:
            kind = "cut"
            cut = timeline_by_label.get(match.group(1), {})
            shot_id = _clean_text(cut.get("source_shot_id"))
            if shot_id:
                source_ids = [shot_id]
        elif raw_block.startswith(("【生成目标】", "【编辑目标】", "【延长目标】")):
            kind = "goal"
        elif raw_block.startswith("【参考素材职责】"):
            kind = "asset_responsibilities"
        elif raw_block.startswith("【主体、关系与场景】"):
            kind = "subjects_relationships_scene"
        elif raw_block.startswith("【镜头脚本】"):
            kind = "shot_script_header"
        elif raw_block.startswith("【声音与台词】"):
            kind = "sound_dialogue"
        elif raw_block.startswith("【保持一致】"):
            kind = "consistency"
        chunks = [raw_block]
        for chunk in chunks:
            blocks.append(
                {
                    "block_id": f"PB{len(blocks) + 1:03d}",
                    "kind": kind,
                    "source_shot_ids": copy.deepcopy(source_ids),
                    "text": chunk,
                }
            )
    normalized_prompt = "\n\n".join(block["text"] for block in blocks)
    return normalized_prompt, blocks


def _prompt_metadata_leaks(
    prompt_text: str, profile: Mapping[str, Any]
) -> list[str]:
    leaks: list[str] = []
    lower_prompt = prompt_text.casefold()
    for forbidden in (
        _clean_text(profile.get("profile_id")),
        _clean_text(profile.get("model_name")),
        _clean_text(profile.get("model_id")),
        SKILL_NAME,
    ):
        if forbidden and forbidden.casefold() in lower_prompt:
            leaks.append(forbidden)
    self_description_patterns = (
        r"我是\s*(?:一个)?(?:ai|人工智能|模型)",
        r"作为\s*(?:一个)?(?:ai|人工智能|模型)",
        r"\bi\s+am\s+an?\s+ai\b",
        r"\bas\s+an?\s+ai\b",
    )
    if any(
        re.search(pattern, prompt_text, flags=re.IGNORECASE)
        for pattern in self_description_patterns
    ):
        leaks.append("self-description")
    if profile.get("prompt_adapter_id") == "seedance-2.5-structured-zh-v1":
        parameter_patterns = (
            r"总时长\s*[：:]",
            r"\b(?:ratio|duration|resolution|fps|output_format)\s*[=:：]",
            r"输出(?:画幅|分辨率|帧率)\s*[：:]",
        )
        for pattern in parameter_patterns:
            if re.search(pattern, prompt_text, flags=re.IGNORECASE):
                leaks.append(pattern)
    if re.search(
        r"\basset(?:[\s_-]*id)?[\s_:-]*[a-z0-9-]{6,}\b",
        prompt_text,
        flags=re.IGNORECASE,
    ):
        leaks.append("raw Asset ID")
    return _unique_strings(leaks)


def _cut_prompt_block(prompt_text: str, cut_label: str) -> str:
    markers = (f"{cut_label}｜", f"{cut_label} :")
    starts = [prompt_text.find(marker) for marker in markers]
    starts = [value for value in starts if value >= 0]
    start = min(starts) if starts else -1
    if start < 0:
        return ""
    next_positions = [
        prompt_text.find(marker, start + len(cut_label) + 1)
        for label in CUT_LABELS
        for marker in (f"\n{label}｜", f"\n{label} :")
    ]
    next_positions.extend(
        prompt_text.find(f"\n\n{header}", start + len(cut_label) + 1)
        for header in ("【声音与台词】", "【保持一致】")
    )
    next_positions = [position for position in next_positions if position >= 0]
    end = min(next_positions) if next_positions else len(prompt_text)
    return prompt_text[start:end]


def _normalized_occurrences(text: str, fact: Any) -> int:
    normalized_text = _normalized_fact_text(text)
    normalized_fact = _normalized_fact_text(fact)
    if not normalized_fact:
        return 0
    return normalized_text.count(normalized_fact)


def _prompt_redundancy_findings(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    prompt_text: str,
) -> list[str]:
    findings: list[str] = []
    for shot, cut in zip(shots, timeline):
        block = _cut_prompt_block(prompt_text, str(cut["cut_label"]))
        camera = shot.get("camera", {})
        camera = camera if isinstance(camera, dict) else {}
        start_frame = _preserve_text(
            _render_descriptive_value(camera.get("start_frame"))
        )
        end_frame = _preserve_text(
            _render_descriptive_value(camera.get("end_frame"))
        )
        facts: list[tuple[str, Any]] = [
            ("camera.position", camera.get("position")),
            ("start_frame", start_frame),
        ]
        if _normalized_fact_text(end_frame) != _normalized_fact_text(start_frame):
            facts.append(("end_frame", end_frame))
        facts.extend(
            ("dialogue", value)
            for value in _dialogue_texts(shot.get("dialogue", []))
        )
        for label, fact in facts:
            count = _normalized_occurrences(block, fact)
            if fact and count > 1:
                findings.append(
                    f"{cut['cut_label']} {label} 重复 {count} 次"
                )
        seen_clauses: set[str] = set()
        for clause in re.split(r"(?<=[。！？；])(?![”’])|\n+", block):
            normalized_clause = _normalized_fact_text(clause)
            if len(normalized_clause) < 8:
                continue
            if normalized_clause in seen_clauses:
                findings.append(
                    f"{cut['cut_label']} 含重复事实句：{clause.strip()}"
                )
                break
            seen_clauses.add(normalized_clause)

    return _unique_strings(findings)


def _official_prompt_structure_findings(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    prompt_text: str,
    profile: Mapping[str, Any],
    generation: Mapping[str, Any],
) -> list[str]:
    if profile.get("prompt_adapter_id") != "seedance-2.5-structured-zh-v1":
        return []
    mode = _clean_text(generation.get("mode"))
    expected_goal = {
        "edit": "【编辑目标】",
        "extend": "【延长目标】",
    }.get(mode, "【生成目标】")
    findings: list[str] = []
    required_headers = [
        expected_goal,
        "【主体、关系与场景】",
        "【镜头脚本】",
        "【保持一致】",
    ]
    positions = [prompt_text.find(header) for header in required_headers]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        findings.append("官方正文主结构缺失或顺序错误")
    blocks = prompt_text.split("\n\n")
    asset_lines = _asset_responsibility_lines(generation)
    has_asset_header = "【参考素材职责】" in prompt_text
    if bool(asset_lines) != has_asset_header:
        findings.append("参考素材职责区块未按当前单元映射条件出现")
    has_sound_header = "【声音与台词】" in prompt_text
    if not has_sound_header:
        findings.append("声音与台词区块必须稳定存在")
    if not blocks or not blocks[-1].startswith("【保持一致】"):
        findings.append("保持一致必须是正文最后区块")
    if any(
        internal_name in prompt_text
        for internal_name in (
            "asset_binding",
            "consistency_contract",
        )
    ):
        findings.append("正文泄漏内部合同字段名")
    if mode in {"t2v", "i2v", "v2v", "r2v", "flf2v"}:
        for shot, cut in zip(shots, timeline):
            block = _cut_prompt_block(prompt_text, str(cut["cut_label"]))
            expected_change = _shot_main_state_change(shot)
            if expected_change and block.count("主要状态变化：") != 1:
                findings.append(
                    f"{cut['cut_label']} 必须恰好声明一个主要状态变化"
                )
        if "构图：" in prompt_text or "画面内容：" in prompt_text:
            findings.append("普通生成不得退回逐 Cut 字段堆叠格式")
    for cut in timeline:
        if f"{cut['cut_label']}｜" not in prompt_text:
            findings.append(f"{cut['cut_label']} 必须使用竖线分隔时间表达")
    return _unique_strings(findings)


def _cut_source_coverage(
    shot: Mapping[str, Any],
    block: str,
    generation: Mapping[str, Any],
) -> tuple[bool, bool]:
    composition, _, _ = _camera_prompt_fields(shot.get("camera", {}))
    expected_content = _shot_prompt_content(
        shot,
        [],
        generation,
        include_reference_roles=not bool(
            generation.get("global_reference_section")
        ),
    )
    required_tokens = [
        token
        for token in (composition, expected_content)
        if token
    ]
    required_tokens.extend(_dialogue_texts(shot.get("dialogue", [])))
    return all(token in block for token in required_tokens), True


def _build_timeline(
    shots: Sequence[Mapping[str, Any]],
    emotion_map: Mapping[str, Sequence[Mapping[str, str]]],
) -> tuple[list[dict[str, Any]], int | float | None]:
    known_durations: list[Decimal] = []
    all_known = True
    for shot in shots:
        try:
            duration = _duration_decimal(shot.get("duration_seconds"))
        except InvalidOperation:
            duration = None
        if duration is None:
            all_known = False
        else:
            known_durations.append(duration)

    timeline: list[dict[str, Any]] = []
    offset = Decimal("0")
    for index, shot in enumerate(shots):
        duration = (
            _duration_decimal(shot.get("duration_seconds")) if all_known else None
        )
        start = offset if duration is not None else None
        end = offset + duration if duration is not None else None
        if end is not None:
            offset = end
        timeline.append(
            {
                "cut_index": index + 1,
                "cut_label": CUT_LABELS[index],
                "source_shot_id": shot["source_shot_id"],
                "source_order": shot["source_order"],
                "start_seconds": _json_number(start),
                "end_seconds": _json_number(end),
                "duration_seconds": _json_number(duration),
                "source_shot_hash": shot["source_shot_hash"],
                "compiler_provenance": copy.deepcopy(shot["field_hashes"]),
                "emotion_visualization": copy.deepcopy(
                    emotion_map.get(str(shot["source_shot_id"]), [])
                ),
            }
        )
    return timeline, _json_number(offset) if all_known else None


def _unit_prompt_validation(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    prompt_text: str,
    profile: Mapping[str, Any],
    generation: Mapping[str, Any],
    diagnostic_codes: Sequence[str],
) -> dict[str, Any]:
    dialogue_exact = True
    reference_tags_exact = True
    source_visual_action_covered = True
    continuity_covered = True
    all_known_tags = _all_generation_reference_tags(generation)
    for shot, cut in zip(shots, timeline):
        block = _cut_prompt_block(prompt_text, str(cut["cut_label"]))
        if any(
            text not in block for text in _dialogue_texts(shot["dialogue"])
        ):
            dialogue_exact = False
        expected_tags = {
            str(item["tag"])
            for item in _reference_roles_for_shot(
                generation, str(shot["source_shot_id"])
            )
        }
        if not _global_reference_section(profile):
            actual_tags = set(
                _reference_tags(block, profile, all_known_tags)
            )
            if actual_tags != expected_tags:
                reference_tags_exact = False
        visual_covered, cut_continuity_covered = _cut_source_coverage(
            shot, block, generation
        )
        source_visual_action_covered &= visual_covered
        continuity_covered &= cut_continuity_covered
    if _global_reference_section(profile):
        actual_global_tags = set(
            _reference_tags(prompt_text, profile, all_known_tags)
        )
        reference_tags_exact = actual_global_tags == set(all_known_tags)
    metadata_absent = not _prompt_metadata_leaks(prompt_text, profile)
    source_anti_slop_terms = {
        term
        for shot in shots
        for term in shot.get("source_anti_slop_terms", [])
    }
    prompt_anti_slop_terms = set(
        _anti_slop_terms_outside_quotes(prompt_text)
    )
    downstream_anti_slop_absent = not (
        prompt_anti_slop_terms - source_anti_slop_terms
    )
    prompt_redundancy_absent = not _prompt_redundancy_findings(
        shots, timeline, prompt_text
    )
    official_prompt_structure = not _official_prompt_structure_findings(
        shots, timeline, prompt_text, profile, generation
    )
    timed_timeline = all(cut["duration_seconds"] is not None for cut in timeline)
    has_error = (
        bool(diagnostic_codes)
        or not dialogue_exact
        or not metadata_absent
        or not reference_tags_exact
        or not downstream_anti_slop_absent
        or not prompt_redundancy_absent
        or not official_prompt_structure
        or not source_visual_action_covered
        or not continuity_covered
    )
    return {
        "status": "PARTIAL" if has_error else "PASS",
        "checks": {
            "source_mapping": len(shots) == len(timeline),
            "timed_timeline": timed_timeline if timed_timeline else None,
            "dialogue_exact": dialogue_exact,
            "dialogue_handling": "PROMPT_LITERAL",
            "reference_tags_exact": reference_tags_exact,
            "source_visual_action_covered": source_visual_action_covered,
            "continuity_covered": continuity_covered,
            "source_anti_slop": (
                "REVIEW_REQUIRED" if source_anti_slop_terms else "NONE"
            ),
            "downstream_anti_slop_absent": downstream_anti_slop_absent,
            "prompt_redundancy_absent": prompt_redundancy_absent,
            "official_prompt_structure": official_prompt_structure,
            "model_metadata_absent": metadata_absent,
            "semantic_compatibility": (
                "MODEL_ATTESTED" if len(shots) > 1 else "NOT_APPLICABLE"
            ),
            "emotion_visualization": "MODEL_REVIEW_REQUIRED",
        },
        "diagnostic_codes": list(diagnostic_codes),
    }


def _status_from_issues(
    issues: Sequence[Mapping[str, Any]],
    prompt_units: Sequence[Mapping[str, Any]],
    *,
    source_global_blocked: bool,
) -> str:
    errors = [issue for issue in issues if issue.get("severity") == "ERROR"]
    warnings = [issue for issue in issues if issue.get("severity") == "WARN"]
    issue_codes = {str(issue.get("code")) for issue in errors}
    integrity_failure_codes = {
        "COMPILER_INPUTS_INVALID",
        "OUTPUT_CONTRACT_INVALID",
        "OUTPUT_HASH_MISMATCH",
        "PLAN_RECOMPILATION_MISMATCH",
        "PROMPT_REDUNDANCY_DETECTED",
        "PROMPT_RECOMPILE_MISMATCH",
        "SOURCE_PROVENANCE_MISMATCH",
        "TOP_LEVEL_VALIDATION_MISMATCH",
        "UNIT_VALIDATION_LEDGER_MISMATCH",
        "VALIDATION_STATUS_MISMATCH",
    }
    if source_global_blocked or issue_codes & integrity_failure_codes:
        return "FAIL"
    if errors:
        has_executable_prompt = any(
            isinstance(unit, dict)
            and bool(_clean_text(unit.get("prompt_text")))
            for unit in prompt_units
        )
        return "PARTIAL" if has_executable_prompt else "FAIL"
    if warnings:
        return "WARN"
    return "PASS"


def _validation_summary(
    normalized: Mapping[str, Any],
    prompt_units: Sequence[Mapping[str, Any]],
    issues: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    known_duration = Decimal("0")
    for shot in normalized.get("shots", []):
        try:
            duration = _duration_decimal(shot.get("duration_seconds"))
        except InvalidOperation:
            duration = None
        if duration is not None:
            known_duration += duration
    return {
        "source_shots": len(normalized.get("shots", [])),
        "prompt_units": len(prompt_units),
        "cuts": sum(len(unit.get("timeline", [])) for unit in prompt_units),
        "grouped_units": sum(
            1 for unit in prompt_units if len(unit.get("source_shot_ids", [])) > 1
        ),
        "standalone_units": sum(
            1 for unit in prompt_units if len(unit.get("source_shot_ids", [])) == 1
        ),
        "known_source_duration_seconds": _json_number(known_duration),
        "errors": sum(1 for issue in issues if issue.get("severity") == "ERROR"),
        "warnings": sum(1 for issue in issues if issue.get("severity") == "WARN"),
    }


def _validation_object(
    normalized: Mapping[str, Any],
    prompt_units: Sequence[Mapping[str, Any]],
    issues: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    issue_codes = {str(issue.get("code")) for issue in issues}
    return {
        "status": _status_from_issues(
            issues,
            prompt_units,
            source_global_blocked=bool(
                normalized.get("source_global_blocked", False)
            ),
        ),
        "errors": [
            dict(issue) for issue in issues if issue.get("severity") == "ERROR"
        ],
        "warnings": [
            dict(issue) for issue in issues if issue.get("severity") == "WARN"
        ],
        "summary": _validation_summary(normalized, prompt_units, issues),
        "deterministic_checks": {
            "source_read_only": True,
            "source_order": "SHOT_ORDER_INVALID" not in issue_codes,
            "source_hash": not bool(
                issue_codes
                & {
                    "SOURCE_HASH_INVALID",
                    "SOURCE_HASH_MISMATCH",
                }
            ),
            "source_shot_coverage": not bool(
                issue_codes
                & {
                    "SOURCE_SHOT_COVERAGE_INVALID",
                    "CUT_SOURCE_MISMATCH",
                }
            ),
            "group_duration": "GROUP_DURATION_INVALID" not in issue_codes,
            "cut_mapping": not bool(
                issue_codes
                & {
                    "CUT_COUNT_MISMATCH",
                    "CUT_SOURCE_MISMATCH",
                    "CUT_SOURCE_HASH_MISMATCH",
                }
            ),
            "cut_timeline": "CUT_TIMELINE_INVALID" not in issue_codes,
            "prompt_metadata_absent": (
                "PROMPT_MODEL_METADATA_LEAK" not in issue_codes
            ),
            "mode_gate": not bool(
                issue_codes
                & {
                    "MODE_GATE_BLOCKED",
                    "MODE_UNIT_REFERENCE_INVALID",
                    "GENERATION_CONTRACT_INVALID",
                }
            ),
            "reference_scope": not any(
                code.startswith("REFERENCE_") for code in issue_codes
            ),
            "source_visual_action_coverage": (
                "SOURCE_VISUAL_ACTION_MISSING" not in issue_codes
            ),
            "continuity_coverage": (
                "CONTINUITY_COVERAGE_MISSING" not in issue_codes
            ),
            "downstream_anti_slop_absent": not bool(
                issue_codes
                & {
                    "DOWNSTREAM_ANTI_SLOP",
                    "PROMPT_ANTI_SLOP_FAILED",
                }
            ),
            "prompt_redundancy_absent": (
                "PROMPT_REDUNDANCY_DETECTED" not in issue_codes
            ),
        },
        "semantic_limitations": [
            (
                "场景、现实层、时间、来源可用性与边界状态证据由脚本重算；"
                "动作、因果、问答、表演保护与信息密度仍依赖逐边界模型审阅。"
            ),
            (
                "scene-global-dp-v1 在已锁定审阅与 Profile 容量内求唯一分区，"
                "不替代高阶语义审阅。"
            ),
            "情绪可视化是否新增事实依赖模型审阅。",
            "脚本不以词面相似度替代完整事实忠实性判断。",
            "anti-slop 仅做来源限定的字面 provenance 审计，不替代语义判断。",
        ],
    }


def _profile_limit(profile: Mapping[str, Any]) -> Decimal:
    duration = _duration_decimal(
        profile["capabilities"]["max_clip_duration_seconds"]
    )
    if duration is None:
        raise DeliveryError("Validated profile has no duration limit")
    return duration


def _build_unit(
    unit_index: int,
    planned: Mapping[str, Any],
    emotion_map: Mapping[str, Sequence[Mapping[str, str]]],
    profile: Mapping[str, Any],
    generation: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    shots = planned["shots"]
    unit_generation = _generation_for_unit(generation, shots)
    timeline, total_duration = _build_timeline(shots, emotion_map)
    prompt_text = _compile_prompt(
        shots, timeline, profile, unit_generation
    )
    prompt_text, prompt_blocks = _prompt_blocks(
        prompt_text, timeline, profile
    )
    unit_codes: list[str] = []
    model_limit = _profile_limit(profile)
    all_known_tags = _all_generation_reference_tags(unit_generation)
    redundancy_findings = _prompt_redundancy_findings(
        shots, timeline, prompt_text
    )
    if redundancy_findings:
        unit_codes.append("PROMPT_REDUNDANCY_DETECTED")
        issues.append(
            _issue(
                "PROMPT_REDUNDANCY_DETECTED",
                "ERROR",
                "prompt",
                f"prompt_units[{unit_index}].prompt_text",
                "；".join(redundancy_findings),
                ("prompt_delivery",),
            )
        )
    structure_findings = _official_prompt_structure_findings(
        shots, timeline, prompt_text, profile, unit_generation
    )
    if structure_findings:
        unit_codes.append("PROMPT_STRUCTURE_INVALID")
        issues.append(
            _issue(
                "PROMPT_STRUCTURE_INVALID",
                "ERROR",
                "prompt",
                f"prompt_units[{unit_index}].prompt_text",
                "；".join(structure_findings),
                ("prompt_delivery",),
            )
        )
    if _global_reference_section(profile):
        actual_global_tags = set(
            _reference_tags(prompt_text, profile, all_known_tags)
        )
        if actual_global_tags != set(all_known_tags):
            unit_codes.append("REFERENCE_TAG_MISMATCH")
            issues.append(
                _issue(
                    "REFERENCE_TAG_MISMATCH",
                    "ERROR",
                    "prompt",
                    f"prompt_units[{unit_index}].prompt_text",
                    "全局参考素材职责未逐字覆盖 role map 中的全部 tag。",
                    ("prompt_delivery",),
                )
            )

    for shot in shots:
        try:
            duration = _duration_decimal(shot.get("duration_seconds"))
        except InvalidOperation:
            duration = None
        if duration is None:
            unit_codes.append("DURATION_MISSING")
        elif duration > model_limit:
            unit_codes.append("MODEL_DURATION_EXCEEDED")
            issues.append(
                _issue(
                    "MODEL_DURATION_EXCEEDED",
                    "ERROR",
                    "unit",
                    f"prompt_units[{unit_index}]",
                    (
                        f"源镜 {shot['source_shot_id']} 的 {duration} 秒超过 "
                        f"Profile 上限 {model_limit} 秒；未缩短或拆分。"
                    ),
                    ("model_generation",),
                )
            )

    if (
        any(shot.get("dialogue") for shot in shots)
        and not profile["capabilities"].get("supports_dialogue")
    ):
        unit_codes.append("MODEL_DIALOGUE_UNSUPPORTED")
        issues.append(
            _issue(
                "MODEL_DIALOGUE_UNSUPPORTED",
                "ERROR",
                "unit",
                f"prompt_units[{unit_index}]",
                "来源含对白，但当前 Model Profile 声明不支持对白；对白仍原样保留。",
                ("model_generation",),
            )
        )

    leaks = _prompt_metadata_leaks(prompt_text, profile)
    if leaks:
        unit_codes.append("PROMPT_MODEL_METADATA_LEAK")
        issues.append(
            _issue(
                "PROMPT_MODEL_METADATA_LEAK",
                "ERROR",
                "prompt",
                f"prompt_units[{unit_index}].prompt_text",
                f"Prompt 正文包含模型或自我说明 metadata：{', '.join(leaks)}。",
                ("prompt_delivery",),
            )
        )

    source_anti_slop_terms = {
        term
        for shot in shots
        for term in shot.get("source_anti_slop_terms", [])
    }
    prompt_anti_slop_terms = set(
        _anti_slop_terms_outside_quotes(prompt_text)
    )
    downstream_anti_slop_terms = sorted(
        prompt_anti_slop_terms - source_anti_slop_terms
    )
    if downstream_anti_slop_terms:
        unit_codes.append("PROMPT_ANTI_SLOP_FAILED")
        issues.append(
            _issue(
                "PROMPT_ANTI_SLOP_FAILED",
                "ERROR",
                "prompt",
                f"prompt_units[{unit_index}].prompt_text",
                (
                    "正文含无法追溯到来源的空泛强化词："
                    f"{', '.join(downstream_anti_slop_terms)}。"
                ),
                ("prompt_delivery",),
            )
        )

    for shot, cut in zip(shots, timeline):
        block = _cut_prompt_block(prompt_text, str(cut["cut_label"]))
        missing_dialogue = [
            text
            for text in _dialogue_texts(shot["dialogue"])
            if text not in block
        ]
        if missing_dialogue:
            unit_codes.append("DIALOGUE_MISMATCH")
            issues.append(
                _issue(
                    "DIALOGUE_MISMATCH",
                    "ERROR",
                    "prompt",
                    f"prompt_units[{unit_index}].prompt_text",
                    f"Cut {cut['cut_label']} 未逐字保留来源对白。",
                    ("prompt_delivery",),
                )
            )
        cut_added_terms = sorted(
            set(_anti_slop_terms_outside_quotes(block))
            - set(shot.get("source_anti_slop_terms", []))
        )
        if cut_added_terms:
            unit_codes.append("PROMPT_ANTI_SLOP_FAILED")
            issues.append(
                _issue(
                    "PROMPT_ANTI_SLOP_FAILED",
                    "ERROR",
                    "prompt",
                    f"prompt_units[{unit_index}].prompt_text",
                    (
                        f"Cut {cut['cut_label']} 含无法追溯到对应源镜的"
                        f"空泛强化词：{', '.join(cut_added_terms)}。"
                    ),
                    ("prompt_delivery",),
                )
            )
            break
        expected_tags = {
            str(item["tag"])
            for item in _reference_roles_for_shot(
                unit_generation, str(shot["source_shot_id"])
            )
        }
        actual_tags = set(
            _reference_tags(block, profile, all_known_tags)
        )
        if not _global_reference_section(profile) and actual_tags != expected_tags:
            unit_codes.append("REFERENCE_TAG_MISMATCH")
            issues.append(
                _issue(
                    "REFERENCE_TAG_MISMATCH",
                    "ERROR",
                    "prompt",
                    f"prompt_units[{unit_index}].prompt_text",
                    (
                        f"Cut {cut['cut_label']} 的 reference tag 未与 role map "
                        "逐字一致。"
                    ),
                    ("prompt_delivery",),
                )
            )
        visual_covered, continuity_covered = _cut_source_coverage(
            shot, block, unit_generation
        )
        if not visual_covered:
            unit_codes.append("SOURCE_VISUAL_ACTION_MISSING")
            issues.append(
                _issue(
                    "SOURCE_VISUAL_ACTION_MISSING",
                    "ERROR",
                    "prompt",
                    f"prompt_units[{unit_index}].prompt_text",
                    (
                        f"Cut {cut['cut_label']} 未消费来源主要画面动作"
                        "或其忠实结构化等价内容。"
                    ),
                    ("prompt_delivery",),
                )
            )
        if not continuity_covered:
            unit_codes.append("CONTINUITY_COVERAGE_MISSING")
            issues.append(
                _issue(
                    "CONTINUITY_COVERAGE_MISSING",
                    "ERROR",
                    "prompt",
                    f"prompt_units[{unit_index}].prompt_text",
                    (
                        f"Cut {cut['cut_label']} 未消费来源连续性状态、"
                        "变化或目标终态。"
                    ),
                    ("prompt_delivery",),
                )
            )

    unit = {
        "prompt_unit_id": f"PU{unit_index + 1:03d}",
        "source_shot_ids": [shot["source_shot_id"] for shot in shots],
        "source_shot_hashes": [shot["source_shot_hash"] for shot in shots],
        "total_duration_seconds": total_duration,
        "grouping_reason": planned["grouping_reason"],
        "standalone_reason": planned["standalone_reason"],
        "semantic_compatibility": copy.deepcopy(
            planned["semantic_compatibility"]
        ),
        "partition_strategy": planned.get("partition_strategy"),
        "partition_entry_reason": planned.get("partition_entry_reason"),
        "boundary_evidence": copy.deepcopy(
            planned.get("boundary_evidence", [])
        ),
        "timeline": timeline,
        "prompt_blocks": prompt_blocks,
        "prompt_text": prompt_text,
        "prompt_validation": _unit_prompt_validation(
            shots,
            timeline,
            prompt_text,
            profile,
            unit_generation,
            _unique_strings(unit_codes),
        ),
    }
    return unit, issues


def _unique_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _deduplicate_dicts(
    values: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        key = canonical_json(value)
        if key not in seen:
            seen.add(key)
            result.append(copy.deepcopy(dict(value)))
    return result


def _normalized_source_snapshot(
    normalized: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "source": copy.deepcopy(normalized.get("source", {})),
        "shots": copy.deepcopy(normalized.get("shots", [])),
        "source_global_blocked": bool(
            normalized.get("source_global_blocked", False)
        ),
    }


def _compiler_inputs(
    normalized: Mapping[str, Any],
    decisions: Any,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_snapshot = _normalized_source_snapshot(normalized)
    decisions_snapshot = copy.deepcopy(decisions)
    runtime_profile = copy.deepcopy(profile)
    return {
        "contract": COMPILER_INPUTS_CONTRACT,
        "normalized_source": normalized_snapshot,
        "normalized_source_hash": sha256_json(normalized_snapshot),
        "decisions_snapshot": decisions_snapshot,
        "runtime_decisions_hash": (
            sha256_json(decisions_snapshot)
            if decisions_snapshot is not None
            else None
        ),
        "runtime_profile": runtime_profile,
        "runtime_profile_hash": sha256_json(runtime_profile),
    }


def prompt_plan_content_hash(plan: Mapping[str, Any]) -> str:
    """Hash a prompt plan exactly once after removing its own hash field."""
    payload = {
        key: value for key, value in plan.items() if key != "content_hash"
    }
    return sha256_json(payload)


def _split_generation_invalid_groups(
    planned_groups: Sequence[Mapping[str, Any]],
    invalid_shot_ids: set[str],
) -> list[dict[str, Any]]:
    isolated: list[dict[str, Any]] = []
    for planned in planned_groups:
        shots = list(planned["shots"])
        group_has_invalid = any(
            str(shot["source_shot_id"]) in invalid_shot_ids
            for shot in shots
        )
        if len(shots) == 1 or not group_has_invalid:
            item = copy.deepcopy(dict(planned))
            if (
                len(shots) == 1
                and str(shots[0]["source_shot_id"]) in invalid_shot_ids
            ):
                item["grouping_reason"] = None
                item["semantic_compatibility"] = None
                item["standalone_reason"] = "generation_context_invalid"
            isolated.append(item)
            continue
        for shot in shots:
            shot_id = str(shot["source_shot_id"])
            isolated.append(
                {
                    "shots": [shot],
                    "grouping_reason": None,
                    "semantic_compatibility": None,
                    "standalone_reason": (
                        "generation_context_invalid"
                        if shot_id in invalid_shot_ids
                        else "generation_group_split"
                    ),
                }
            )
    return isolated


def _split_unreadable_groups(
    planned_groups: Sequence[Mapping[str, Any]],
    unreadable_shot_ids: set[str],
) -> list[dict[str, Any]]:
    isolated: list[dict[str, Any]] = []
    for planned in planned_groups:
        shots = list(planned["shots"])
        group_has_unreadable = any(
            str(shot["source_shot_id"]) in unreadable_shot_ids
            for shot in shots
        )
        if len(shots) == 1 or not group_has_unreadable:
            item = copy.deepcopy(dict(planned))
            if (
                len(shots) == 1
                and str(shots[0]["source_shot_id"])
                in unreadable_shot_ids
            ):
                item["grouping_reason"] = None
                item["semantic_compatibility"] = None
                item["standalone_reason"] = "input_material_unreadable"
            isolated.append(item)
            continue
        for shot in shots:
            shot_id = str(shot["source_shot_id"])
            isolated.append(
                {
                    "shots": [shot],
                    "grouping_reason": None,
                    "semantic_compatibility": None,
                    "standalone_reason": (
                        "input_material_unreadable"
                        if shot_id in unreadable_shot_ids
                        else "unreadable_group_split"
                    ),
                }
            )
    return isolated


def _build_generation_failed_unit(
    unit_index: int,
    planned: Mapping[str, Any],
) -> dict[str, Any]:
    shots = list(planned["shots"])
    timeline, total_duration = _build_timeline(shots, {})
    return {
        "prompt_unit_id": f"PU{unit_index + 1:03d}",
        "source_shot_ids": [shot["source_shot_id"] for shot in shots],
        "source_shot_hashes": [shot["source_shot_hash"] for shot in shots],
        "total_duration_seconds": total_duration,
        "grouping_reason": None,
        "standalone_reason": "generation_context_invalid",
        "semantic_compatibility": None,
        "timeline": timeline,
        "prompt_blocks": [],
        "prompt_text": "",
        "prompt_validation": {
            "status": "PARTIAL",
            "checks": {
                "source_mapping": len(shots) == len(timeline),
                "timed_timeline": (
                    True
                    if all(
                        cut["duration_seconds"] is not None
                        for cut in timeline
                    )
                    else None
                ),
                "dialogue_exact": None,
                "dialogue_handling": "NOT_COMPILED",
                "reference_tags_exact": None,
                "source_visual_action_covered": None,
                "continuity_covered": None,
                "source_anti_slop": (
                    "REVIEW_REQUIRED"
                    if any(
                        shot.get("source_anti_slop_terms") for shot in shots
                    )
                    else "NONE"
                ),
                "downstream_anti_slop_absent": True,
                "model_metadata_absent": True,
                "semantic_compatibility": "NOT_APPLICABLE",
                "emotion_visualization": "NOT_COMPILED",
            },
            "diagnostic_codes": ["GENERATION_CONTEXT_INVALID"],
        },
    }


def _build_unreadable_failed_unit(
    unit_index: int,
    planned: Mapping[str, Any],
) -> dict[str, Any]:
    shots = list(planned["shots"])
    timeline, total_duration = _build_timeline(shots, {})
    return {
        "prompt_unit_id": f"PU{unit_index + 1:03d}",
        "source_shot_ids": [shot["source_shot_id"] for shot in shots],
        "source_shot_hashes": [shot["source_shot_hash"] for shot in shots],
        "total_duration_seconds": total_duration,
        "grouping_reason": None,
        "standalone_reason": "input_material_unreadable",
        "semantic_compatibility": None,
        "timeline": timeline,
        "prompt_blocks": [],
        "prompt_text": "",
        "prompt_validation": {
            "status": "FAIL",
            "checks": {
                "source_mapping": len(shots) == len(timeline),
                "timed_timeline": (
                    True
                    if all(
                        cut["duration_seconds"] is not None
                        for cut in timeline
                    )
                    else None
                ),
                "dialogue_exact": None,
                "dialogue_handling": "NOT_COMPILED",
                "reference_tags_exact": None,
                "source_visual_action_covered": None,
                "continuity_covered": None,
                "source_anti_slop": (
                    "REVIEW_REQUIRED"
                    if any(
                        shot.get("source_anti_slop_terms") for shot in shots
                    )
                    else "NONE"
                ),
                "downstream_anti_slop_absent": True,
                "model_metadata_absent": True,
                "semantic_compatibility": "NOT_APPLICABLE",
                "emotion_visualization": "NOT_COMPILED",
            },
            "diagnostic_codes": ["INPUT_MATERIAL_UNREADABLE"],
        },
    }


def _build_single_operation_plan(
    source_document: Any,
    decisions: Any = None,
    model_profile: Any = None,
    delivery_slug: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic prompt plan without mutating source_document."""
    normalized, normalization_issues = normalize_input(source_document)
    profile = (
        copy.deepcopy(model_profile)
        if model_profile is not None
        else resolve_model_profile()
    )
    profile_issues = validate_model_profile(profile)
    asset_binding: dict[str, str] = {
        "state": "unmapped",
        "source": "none",
    }
    issues: list[dict[str, Any]] = list(normalization_issues) + profile_issues
    prompt_units: list[dict[str, Any]] = []
    story_contract = _derive_story_contract(
        normalized, source_document, decisions
    )
    required_entities = _derive_required_entities(
        normalized, story_contract
    )
    dialogue_ledger = _derive_dialogue_ledger(normalized)
    asset_inventory: dict[str, Any] = {"complete": False, "items": []}
    asset_assignments: list[dict[str, Any]] = []
    unused_assets: list[str] = []
    mapping_confidence = "high"
    prompt_advisories: list[dict[str, Any]] = []
    request_configuration: dict[str, Any] = {
        "raw": {},
        "normalized": {},
        "prompt_isolation": True,
    }
    submission_ready = True
    task: dict[str, Any] = {
        "primary": "",
        "input_topology": "",
        "modules": [],
        "source": "unresolved",
    }
    generation: dict[str, Any] = {
        "mode": "",
        "mode_source": "unresolved",
        "available_reference_tags": [],
        "reference_role_map": [],
        "edit_scope": [],
        "edit_deltas": [],
        "extend_context": {},
        "runtime_decisions_hash": (
            sha256_json(decisions) if decisions is not None else None
        ),
        "global_blocked": True,
        "invalid_shot_ids": [],
    }

    if not profile_issues:
        generation, generation_issues = resolve_generation_context(
            source_document,
            decisions,
            normalized["shots"],
            profile,
        )
        issues.extend(generation_issues)
        task, task_issues = _normalize_task(
            source_document, decisions, generation, profile
        )
        issues.extend(task_issues)
        (
            asset_inventory,
            asset_assignments,
            unused_assets,
            mapping_confidence,
            asset_issues,
            asset_advisories,
            asset_ready,
        ) = _normalize_asset_context(
            source_document, decisions, profile
        )
        dialogue_ledger = _bind_dialogue_assets(
            dialogue_ledger, asset_assignments
        )
        issues.extend(asset_issues)
        prompt_advisories.extend(asset_advisories)
        submission_ready &= asset_ready
        asset_binding = _normalize_asset_binding(
            source_document,
            decisions,
            asset_assignments,
            generation,
        )
        request_configuration, request_issues, request_advisories, request_ready = (
            _normalize_request_configuration(
                source_document, decisions, profile, task
            )
        )
        issues.extend(request_issues)
        prompt_advisories.extend(request_advisories)
        submission_ready &= request_ready
        generation.update(
            {
                "asset_assignments": copy.deepcopy(asset_assignments),
                "asset_binding": copy.deepcopy(asset_binding),
                "unused_assets": copy.deepcopy(unused_assets),
                "story_contract": copy.deepcopy(story_contract),
                "task_modules": copy.deepcopy(task.get("modules", [])),
                "global_reference_section": _global_reference_section(profile),
            }
        )
        v2_blocking_codes = {
            "TASK_CONTRACT_INVALID",
            "TASK_GENERATION_MISMATCH",
            "CONTENT_ROLE_SCENARIO_CONFLICT",
            "CORE_ASSET_MISSING",
            "ASSET_CARDINALITY_CONFLICT",
        }
        if any(issue.get("code") in v2_blocking_codes for issue in issues):
            generation["global_blocked"] = True
            submission_ready = False
    else:
        generation_issues = []

    profile_has_error = any(
        issue.get("severity") == "ERROR" for issue in profile_issues
    )
    if (
        not profile_has_error
        and not normalized.get("source_global_blocked", False)
        and not generation.get("global_blocked", False)
    ):
        emotion_map, emotion_issues = _validate_emotion_decisions(
            normalized["shots"], decisions
        )
        planned_groups, grouping_issues = _plan_groups(
            normalized["shots"],
            decisions,
            profile,
            _clean_text(
                normalized.get("source", {}).get("observed_content_hash")
            ),
        )
        invalid_shot_ids = {
            str(shot_id)
            for shot_id in generation.get("invalid_shot_ids", [])
        }
        planned_groups = _split_generation_invalid_groups(
            planned_groups, invalid_shot_ids
        )
        unreadable_shot_ids = {
            str(shot["source_shot_id"])
            for shot in normalized["shots"]
            if shot.get("compilable_source") is not True
        }
        planned_groups = _split_unreadable_groups(
            planned_groups, unreadable_shot_ids
        )
        issues.extend(emotion_issues)
        issues.extend(grouping_issues)
        for unit_index, planned in enumerate(planned_groups):
            if any(
                str(shot["source_shot_id"]) in invalid_shot_ids
                for shot in planned["shots"]
            ):
                prompt_units.append(
                    _build_generation_failed_unit(unit_index, planned)
                )
                continue
            if any(
                str(shot["source_shot_id"]) in unreadable_shot_ids
                for shot in planned["shots"]
            ):
                prompt_units.append(
                    _build_unreadable_failed_unit(unit_index, planned)
                )
                continue
            unit, unit_issues = _build_unit(
                unit_index, planned, emotion_map, profile, generation
            )
            prompt_units.append(unit)
            issues.extend(unit_issues)

    for unit in prompt_units:
        unit["operation_id"] = "OP001"
        unit["operation_order"] = 1
        unit["depends_on_operation_id"] = None
        unit["task_primary"] = task.get("primary")

    plan: dict[str, Any] = {
        "contract_name": PLAN_CONTRACT_NAME,
        "contract_version": PLAN_CONTRACT_VERSION,
        "skill": {"name": SKILL_NAME, "version": SKILL_VERSION},
        "delivery": {
            "slug": (
                _ascii_kebab_slug(delivery_slug)
                if delivery_slug is not None
                else derive_delivery_slug(None, source_document)
            ),
            "files": {},
        },
        "compiler_inputs": _compiler_inputs(
            normalized, decisions, profile
        ),
        "source": copy.deepcopy(normalized["source"]),
        "task": copy.deepcopy(task),
        "operations": [
            {
                "operation_id": "OP001",
                "order": 1,
                "depends_on_operation_id": None,
                "task": copy.deepcopy(task),
                "generation": copy.deepcopy(generation),
                "prompt_unit_ids": [
                    unit.get("prompt_unit_id") for unit in prompt_units
                ],
                "submission_ready": submission_ready,
            }
        ],
        "story_contract": copy.deepcopy(story_contract),
        "required_entities": copy.deepcopy(required_entities),
        "dialogue_ledger": copy.deepcopy(dialogue_ledger),
        "asset_binding": copy.deepcopy(asset_binding),
        "asset_inventory": copy.deepcopy(asset_inventory),
        "asset_assignments": copy.deepcopy(asset_assignments),
        "unused_assets": copy.deepcopy(unused_assets),
        "mapping_confidence": mapping_confidence,
        "request_configuration": copy.deepcopy(request_configuration),
        "prompt_advisories": copy.deepcopy(prompt_advisories),
        "submission_ready": submission_ready,
        "generation": copy.deepcopy(generation),
        "model_profile": copy.deepcopy(profile),
        "prompt_units": prompt_units,
        "diagnostics": [],
        "validation": {},
    }
    plan["delivery"]["files"] = delivery_file_map(
        plan["delivery"]["slug"]
    )

    structural_issues = _validate_plan_structure(
        normalized,
        plan,
        check_content_hash=False,
        source_document=source_document,
    )
    issues.extend(structural_issues)
    issues = _deduplicate_issues(issues)
    if any(
        issue.get("code") == "PROMPT_REDUNDANCY_DETECTED"
        for issue in issues
    ):
        plan["submission_ready"] = False
        plan["operations"][0]["submission_ready"] = False
    plan["diagnostics"] = issues
    plan["validation"] = _validation_object(normalized, prompt_units, issues)
    plan["content_hash"] = prompt_plan_content_hash(plan)
    return plan


def _operation_decisions(
    decisions: Any,
    operation: Mapping[str, Any],
    normalized: Mapping[str, Any],
) -> dict[str, Any]:
    result = copy.deepcopy(decisions) if isinstance(decisions, dict) else {}
    result.pop("operations", None)
    if "task" in operation and "generation" not in operation:
        result.pop("generation", None)
    for key in (
        "task",
        "generation",
        "request_configuration",
        "asset_binding",
        "asset_inventory",
        "asset_assignments",
        "mapping_confidence",
        "edit_scope",
        "edit_deltas",
        "extend_context",
        "grouping_review",
    ):
        if key in operation:
            result[key] = copy.deepcopy(operation.get(key))
    dependency = _clean_text(operation.get("depends_on_operation_id"))
    task = operation.get("task")
    if (
        dependency
        and isinstance(task, dict)
        and _clean_text(task.get("primary")).lower() == "extend"
        and "generation" not in operation
    ):
        dependency_tag = f"@{dependency}-output"
        shot_ids = [
            str(shot.get("source_shot_id"))
            for shot in normalized.get("shots", [])
        ]
        inventory = result.get("asset_inventory")
        inventory = copy.deepcopy(inventory) if isinstance(inventory, dict) else {
            "complete": False,
            "items": [],
        }
        inventory_items = inventory.get("items", [])
        inventory_items = list(inventory_items) if isinstance(inventory_items, list) else []
        inventory_items.append(
            {
                "tag": dependency_tag,
                "media_type": "video",
                "available": True,
                "core": True,
            }
        )
        inventory["items"] = inventory_items
        assignments = result.get("asset_assignments")
        assignments = list(assignments) if isinstance(assignments, list) else []
        assignments.append(
            {
                "tag": dependency_tag,
                "target_entity": "前一步输出视频",
                "role": "extension_source",
                "adopted_dimensions": ["边界画面", "运动趋势", "声音状态"],
                "rejected_dimensions": [],
                "applies_to_shot_ids": shot_ids,
                "user_mapped": True,
            }
        )
        result["asset_inventory"] = inventory
        result["asset_assignments"] = assignments
        extend_context = result.get("extend_context")
        extend_context = (
            copy.deepcopy(extend_context)
            if isinstance(extend_context, dict)
            else {}
        )
        extend_context.setdefault("accepted_material", True)
        extend_context.setdefault(
            "observed_end_state", f"{dependency} 输出的结束状态"
        )
        extend_context.setdefault("direction", "后")
        result["extend_context"] = extend_context
    return result


def build_prompt_plan(
    source_document: Any,
    decisions: Any = None,
    model_profile: Any = None,
    delivery_slug: str | None = None,
) -> dict[str, Any]:
    """Build a v2 plan, including deterministic sequential operations."""
    raw_operations = _runtime_value(source_document, decisions, "operations")
    if raw_operations in (None, []):
        return _build_single_operation_plan(
            source_document,
            decisions=decisions,
            model_profile=model_profile,
            delivery_slug=delivery_slug,
        )
    if not isinstance(raw_operations, list) or not raw_operations:
        plan = _build_single_operation_plan(
            source_document,
            decisions=decisions,
            model_profile=model_profile,
            delivery_slug=delivery_slug,
        )
        issue = _issue(
            "OPERATION_CONTRACT_INVALID",
            "ERROR",
            "operation",
            "operations",
            "operations 必须是非空数组。",
            ("prompt_compilation",),
        )
        plan["diagnostics"] = _deduplicate_issues(
            list(plan.get("diagnostics", [])) + [issue]
        )
        normalized, _ = normalize_input(source_document)
        plan["validation"] = _validation_object(
            normalized, plan.get("prompt_units", []), plan["diagnostics"]
        )
        plan["submission_ready"] = False
        plan["content_hash"] = prompt_plan_content_hash(plan)
        return plan

    normalized, _ = normalize_input(source_document)
    profile = (
        copy.deepcopy(model_profile)
        if model_profile is not None
        else resolve_model_profile()
    )
    operation_plans: list[tuple[dict[str, Any], dict[str, Any]]] = []
    operation_issues: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_operation in enumerate(raw_operations):
        path = f"operations[{index}]"
        if not isinstance(raw_operation, dict):
            operation_issues.append(
                _issue(
                    "OPERATION_CONTRACT_INVALID",
                    "ERROR",
                    "operation",
                    path,
                    "operation 必须是 JSON 对象。",
                    ("prompt_compilation",),
                )
            )
            continue
        operation_id = _clean_text(raw_operation.get("operation_id")) or f"OP{index + 1:03d}"
        dependency = _clean_text(raw_operation.get("depends_on_operation_id")) or None
        if (
            operation_id in seen_ids
            or raw_operation.get("order", index + 1) != index + 1
            or (dependency is not None and dependency not in seen_ids)
        ):
            operation_issues.append(
                _issue(
                    "OPERATION_CONTRACT_INVALID",
                    "ERROR",
                    "operation",
                    path,
                    "operation ID、order 或依赖顺序无效。",
                    ("prompt_compilation",),
                )
            )
            continue
        normalized_operation = copy.deepcopy(raw_operation)
        normalized_operation["operation_id"] = operation_id
        normalized_operation["order"] = index + 1
        normalized_operation["depends_on_operation_id"] = dependency
        if (
            len(normalized.get("shots", [])) > 1
            and "grouping_review" not in normalized_operation
        ):
            raise GroupingReviewError(
                "GROUPING_REVIEW_REQUIRED: 显式 operations 中每个 operation "
                f"都必须提供 grouping_review；缺失 {operation_id}。"
            )
        op_decisions = _operation_decisions(
            decisions, normalized_operation, normalized
        )
        op_plan = _build_single_operation_plan(
            source_document,
            decisions=op_decisions,
            model_profile=profile,
            delivery_slug=delivery_slug,
        )
        operation_plans.append((normalized_operation, op_plan))
        seen_ids.add(operation_id)

    if not operation_plans:
        fallback = _build_single_operation_plan(
            source_document,
            decisions=decisions,
            model_profile=profile,
            delivery_slug=delivery_slug,
        )
        fallback["diagnostics"] = _deduplicate_issues(
            list(fallback.get("diagnostics", [])) + operation_issues
        )
        fallback["validation"] = _validation_object(
            normalized,
            fallback.get("prompt_units", []),
            fallback["diagnostics"],
        )
        fallback["submission_ready"] = False
        fallback["content_hash"] = prompt_plan_content_hash(fallback)
        return fallback

    combined = copy.deepcopy(operation_plans[0][1])
    combined_units: list[dict[str, Any]] = []
    combined_operations: list[dict[str, Any]] = []
    combined_issues: list[dict[str, Any]] = list(operation_issues)
    combined_advisories: list[dict[str, Any]] = []
    combined_ready = True
    for raw_operation, op_plan in operation_plans:
        operation_id = raw_operation["operation_id"]
        prompt_unit_ids: list[str] = []
        for unit in op_plan.get("prompt_units", []):
            copied_unit = copy.deepcopy(unit)
            copied_unit["prompt_unit_id"] = f"PU{len(combined_units) + 1:03d}"
            copied_unit["operation_id"] = operation_id
            copied_unit["operation_order"] = raw_operation["order"]
            copied_unit["depends_on_operation_id"] = raw_operation[
                "depends_on_operation_id"
            ]
            copied_unit["task_primary"] = op_plan.get("task", {}).get("primary")
            combined_units.append(copied_unit)
            prompt_unit_ids.append(copied_unit["prompt_unit_id"])
        combined_operations.append(
            {
                "operation_id": operation_id,
                "order": raw_operation["order"],
                "depends_on_operation_id": raw_operation[
                    "depends_on_operation_id"
                ],
                "task": copy.deepcopy(op_plan.get("task", {})),
                "generation": copy.deepcopy(op_plan.get("generation", {})),
                "prompt_unit_ids": prompt_unit_ids,
                "submission_ready": bool(op_plan.get("submission_ready")),
            }
        )
        combined_issues.extend(op_plan.get("diagnostics", []))
        combined_advisories.extend(op_plan.get("prompt_advisories", []))
        combined_ready &= bool(op_plan.get("submission_ready"))

    combined["compiler_inputs"] = _compiler_inputs(
        normalized, decisions, profile
    )
    combined["operations"] = combined_operations
    combined["prompt_units"] = combined_units
    combined["prompt_advisories"] = _deduplicate_dicts(combined_advisories)
    combined["submission_ready"] = combined_ready
    combined["diagnostics"] = _deduplicate_issues(combined_issues)
    combined["validation"] = _validation_object(
        normalized, combined_units, combined["diagnostics"]
    )
    combined["content_hash"] = prompt_plan_content_hash(combined)
    return combined


def _validate_compiler_inputs(
    normalized: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> tuple[Any, Any, list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    compiler_inputs = plan.get("compiler_inputs")
    if not isinstance(compiler_inputs, dict):
        return (
            None,
            None,
            [
                _issue(
                    "COMPILER_INPUTS_INVALID",
                    "ERROR",
                    "plan",
                    "compiler_inputs",
                    "plan 缺少可重编译的 compiler_inputs 快照。",
                    ("prompt_delivery",),
                )
            ],
        )

    normalized_snapshot = compiler_inputs.get("normalized_source")
    expected_normalized_snapshot = _normalized_source_snapshot(normalized)
    if (
        compiler_inputs.get("contract") != COMPILER_INPUTS_CONTRACT
        or normalized_snapshot != expected_normalized_snapshot
        or compiler_inputs.get("normalized_source_hash")
        != sha256_json(expected_normalized_snapshot)
    ):
        issues.append(
            _issue(
                "COMPILER_INPUTS_INVALID",
                "ERROR",
                "plan",
                "compiler_inputs.normalized_source",
                (
                    "normalized source 快照、合同或 hash "
                    "与当前只读来源不一致。"
                ),
                ("prompt_delivery", "source_traceability"),
            )
        )

    decisions_snapshot = copy.deepcopy(
        compiler_inputs.get("decisions_snapshot")
    )
    expected_decisions_hash = (
        sha256_json(decisions_snapshot)
        if decisions_snapshot is not None
        else None
    )
    if (
        compiler_inputs.get("runtime_decisions_hash")
        != expected_decisions_hash
    ):
        issues.append(
            _issue(
                "COMPILER_INPUTS_INVALID",
                "ERROR",
                "plan",
                "compiler_inputs.runtime_decisions_hash",
                "decisions snapshot hash 不一致。",
                ("prompt_delivery",),
            )
        )

    runtime_profile = copy.deepcopy(
        compiler_inputs.get("runtime_profile")
    )
    try:
        expected_profile_hash = sha256_json(runtime_profile)
    except DeliveryError:
        expected_profile_hash = None
    if (
        expected_profile_hash is None
        or compiler_inputs.get("runtime_profile_hash")
        != expected_profile_hash
        or runtime_profile != plan.get("model_profile")
    ):
        issues.append(
            _issue(
                "COMPILER_INPUTS_INVALID",
                "ERROR",
                "plan",
                "compiler_inputs.runtime_profile",
                "runtime Profile 快照、hash 或 plan metadata 不一致。",
                ("prompt_delivery",),
            )
        )
    return decisions_snapshot, runtime_profile, issues


def _validate_plan_structure(
    normalized: Mapping[str, Any],
    plan: Any,
    check_content_hash: bool,
    source_document: Any = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(plan, dict):
        return [
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "$",
                "prompt_plan 必须是 JSON 对象。",
                ("prompt_delivery",),
            )
        ]

    if (
        plan.get("contract_name") != PLAN_CONTRACT_NAME
        or plan.get("contract_version") != PLAN_CONTRACT_VERSION
    ):
        issues.append(
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "contract_name",
                f"输出合同必须是 {PLAN_CONTRACT_NAME}/{PLAN_CONTRACT_VERSION}。",
                ("prompt_delivery",),
            )
        )

    if plan.get("skill") != {"name": SKILL_NAME, "version": SKILL_VERSION}:
        issues.append(
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "skill",
                f"Skill identity 必须是 {SKILL_NAME} {SKILL_VERSION}。",
                ("prompt_delivery",),
            )
        )

    v2_shapes = {
        "task": dict,
        "operations": list,
        "story_contract": dict,
        "required_entities": list,
        "dialogue_ledger": list,
        "asset_binding": dict,
        "asset_inventory": dict,
        "asset_assignments": list,
        "unused_assets": list,
        "request_configuration": dict,
        "prompt_advisories": list,
    }
    for field_name, expected_type in v2_shapes.items():
        if not isinstance(plan.get(field_name), expected_type):
            issues.append(
                _issue(
                    "OUTPUT_CONTRACT_INVALID",
                    "ERROR",
                    "plan",
                    field_name,
                    f"{field_name} 必须是 v2 合同要求的 {expected_type.__name__}。",
                    ("prompt_delivery",),
                )
            )
    if plan.get("mapping_confidence") not in {"high", "medium", "low"}:
        issues.append(
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "mapping_confidence",
                "mapping_confidence 必须为 high、medium 或 low。",
                ("prompt_delivery",),
            )
        )
    if not isinstance(plan.get("submission_ready"), bool):
        issues.append(
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "submission_ready",
                "submission_ready 必须为布尔值。",
                ("prompt_delivery",),
            )
        )
    if isinstance(plan.get("model_profile"), dict):
        asset_binding = plan.get("asset_binding", {})
        if asset_binding.get("state") not in {"mapped", "unmapped"}:
            issues.append(
                _issue(
                    "ASSET_BINDING_INVALID",
                    "ERROR",
                    "plan",
                    "asset_binding",
                    "asset_binding.state 必须为 mapped 或 unmapped。",
                    ("prompt_delivery",),
                )
            )

    delivery = plan.get("delivery")
    if not isinstance(delivery, dict):
        issues.append(
            _issue(
                "DELIVERY_NAMING_INVALID",
                "ERROR",
                "plan",
                "delivery",
                "输出缺少按输入文件名派生的交付命名信息。",
                ("delivery_integrity",),
            )
        )
    else:
        slug = _clean_text(delivery.get("slug"))
        try:
            expected_files = delivery_file_map(slug)
        except DeliveryError:
            expected_files = {}
        actual_files = delivery.get("files")
        if (
            not slug
            or _ascii_kebab_slug(slug) != slug
            or actual_files != expected_files
            or len(set(expected_files.values())) != 4
            or any(
                "prompt" not in name
                for name in expected_files.values()
            )
        ):
            issues.append(
                _issue(
                    "DELIVERY_NAMING_INVALID",
                    "ERROR",
                    "plan",
                    "delivery",
                    "正式文件名必须使用 ASCII kebab-case 输入前缀并包含 prompt。",
                    ("delivery_integrity",),
                )
            )

    _, _, compiler_input_issues = _validate_compiler_inputs(
        normalized, plan
    )
    issues.extend(compiler_input_issues)

    source_metadata = plan.get("source")
    if not isinstance(source_metadata, dict):
        source_metadata = {}
        issues.append(
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "source",
                "输出缺少 source provenance。",
                ("prompt_delivery",),
            )
        )
    else:
        for key in (
            "source_mode",
            "source_contract",
            "source_skill",
            "source_skill_version",
            "project_id",
            "source_content_hash",
            "observed_content_hash",
            "local_content_hash",
            "source_read_only",
            "source_shot_count",
        ):
            if source_metadata.get(key) != normalized["source"].get(key):
                issues.append(
                    _issue(
                        "SOURCE_PROVENANCE_MISMATCH",
                        "ERROR",
                        "plan",
                        f"source.{key}",
                        f"输出 source.{key} 与当前来源不一致。",
                        ("source_traceability",),
                    )
                )

    profile = plan.get("model_profile")
    issues.extend(validate_model_profile(profile))
    profile_valid = not validate_model_profile(profile)
    grouping_policy = (
        _grouping_policy(profile) if profile_valid else DEFAULT_GROUPING_POLICY
    )
    max_group_cuts = int(grouping_policy["max_cuts"])
    max_group_duration = Decimal(grouping_policy["max_duration_seconds"])
    generation = plan.get("generation")
    generation_global_blocked = True
    generation_invalid_shot_ids: set[str] = set()
    if not isinstance(generation, dict):
        generation = {}
        issues.append(
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "generation",
                "输出缺少独立 generation context。",
                ("prompt_delivery",),
            )
        )
    elif profile_valid:
        generation_global_blocked = generation.get("global_blocked") is True
        raw_invalid_shot_ids = generation.get("invalid_shot_ids", [])
        if isinstance(raw_invalid_shot_ids, list):
            generation_invalid_shot_ids = {
                str(shot_id) for shot_id in raw_invalid_shot_ids
            }
        mode_source = _clean_text(generation.get("mode_source"))
        runtime_hash = generation.get("runtime_decisions_hash")
        if mode_source not in {
            "decisions",
            "input",
            "task",
            "default_t2v",
            "unresolved",
        }:
            issues.append(
                _issue(
                    "OUTPUT_CONTRACT_INVALID",
                    "ERROR",
                    "plan",
                    "generation.mode_source",
                    "generation.mode_source 无效。",
                    ("prompt_delivery",),
                )
            )
        if runtime_hash is not None and (
            not isinstance(runtime_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", runtime_hash) is None
        ):
            issues.append(
                _issue(
                    "OUTPUT_CONTRACT_INVALID",
                    "ERROR",
                    "plan",
                    "generation.runtime_decisions_hash",
                    "runtime decisions hash 必须为 null 或小写 SHA-256。",
                    ("prompt_delivery",),
                )
            )
        validated_generation, generation_issues = _validate_generation_context(
            generation,
            source_document if source_document is not None else {},
            normalized.get("shots", []),
            profile,
            mode_source=mode_source,
            runtime_decisions_hash=(
                runtime_hash if isinstance(runtime_hash, str) else None
            ),
        )
        issues.extend(generation_issues)
        if validated_generation != generation:
            issues.append(
                _issue(
                    "OUTPUT_CONTRACT_INVALID",
                    "ERROR",
                    "plan",
                    "generation",
                    "generation context 不是规范化 Mode Gate 结果。",
                    ("prompt_delivery",),
                )
            )
    operations_raw = plan.get("operations")
    operation_generations: dict[str, Mapping[str, Any]] = {
        "OP001": generation
    }
    operation_invalid_shots: dict[str, set[str]] = {
        "OP001": generation_invalid_shot_ids
    }
    operation_global_blocked: dict[str, bool] = {
        "OP001": generation_global_blocked
    }
    operation_order: list[str] = ["OP001"]
    if isinstance(operations_raw, list) and operations_raw:
        operation_generations = {}
        operation_invalid_shots = {}
        operation_global_blocked = {}
        operation_order = []
        seen_operation_ids: set[str] = set()
        for operation_index, operation in enumerate(operations_raw):
            path = f"operations[{operation_index}]"
            if not isinstance(operation, dict):
                issues.append(
                    _issue(
                        "OPERATION_CONTRACT_INVALID",
                        "ERROR",
                        "operation",
                        path,
                        "operation 必须是 JSON 对象。",
                        ("prompt_delivery",),
                    )
                )
                continue
            operation_id = _clean_text(operation.get("operation_id"))
            dependency = _clean_text(
                operation.get("depends_on_operation_id")
            ) or None
            op_generation = operation.get("generation")
            if (
                not operation_id
                or operation_id in seen_operation_ids
                or operation.get("order") != operation_index + 1
                or (dependency is not None and dependency not in seen_operation_ids)
                or not isinstance(op_generation, dict)
            ):
                issues.append(
                    _issue(
                        "OPERATION_CONTRACT_INVALID",
                        "ERROR",
                        "operation",
                        path,
                        "operation ID、order、依赖或 generation 无效。",
                        ("prompt_delivery",),
                    )
                )
                continue
            seen_operation_ids.add(operation_id)
            operation_order.append(operation_id)
            operation_generations[operation_id] = op_generation
            raw_invalid = op_generation.get("invalid_shot_ids", [])
            operation_invalid_shots[operation_id] = {
                str(value)
                for value in raw_invalid
                if isinstance(raw_invalid, list)
            }
            operation_global_blocked[operation_id] = (
                op_generation.get("global_blocked") is True
            )
    elif operations_raw not in (None, []):
        issues.append(
            _issue(
                "OPERATION_CONTRACT_INVALID",
                "ERROR",
                "operation",
                "operations",
                "operations 必须是非空数组。",
                ("prompt_delivery",),
            )
        )
    prompt_units = plan.get("prompt_units")
    if not isinstance(prompt_units, list):
        prompt_units = []
        issues.append(
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "prompt_units",
                "prompt_units 必须是数组。",
                ("prompt_delivery",),
            )
        )
    if (
        len(operation_order) == 1
        and operation_global_blocked.get(operation_order[0], True)
        and prompt_units
    ):
        issues.append(
            _issue(
                "GLOBAL_MODE_GATE_BYPASSED",
                "ERROR",
                "plan",
                "prompt_units",
                "全局 Mode Gate 已阻断，但输出仍包含 Prompt 单元。",
                ("prompt_delivery",),
            )
        )

    source_shots = normalized.get("shots", [])
    flattened_ids_by_operation: dict[str, list[str]] = {
        operation_id: [] for operation_id in operation_order
    }
    source_cursors: dict[str, int] = {
        operation_id: 0 for operation_id in operation_order
    }
    for unit_index, unit in enumerate(prompt_units):
        unit_path = f"prompt_units[{unit_index}]"
        if not isinstance(unit, dict):
            issues.append(
                _issue(
                    "OUTPUT_CONTRACT_INVALID",
                    "ERROR",
                    "unit",
                    unit_path,
                    "Prompt 单元必须是对象。",
                    ("prompt_delivery",),
                )
            )
            continue
        expected_unit_id = f"PU{unit_index + 1:03d}"
        if unit.get("prompt_unit_id") != expected_unit_id:
            issues.append(
                _issue(
                    "OUTPUT_CONTRACT_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.prompt_unit_id",
                    f"单元 ID 必须是 {expected_unit_id}。",
                    ("prompt_delivery",),
                )
            )
        blocks = unit.get("prompt_blocks")
        prompt_text_value = unit.get("prompt_text")
        blocks_invalid = (
            not isinstance(blocks, list)
            or (
                bool(prompt_text_value)
                and (
                    not blocks
                    or any(not isinstance(block, dict) for block in blocks)
                    or [block.get("block_id") for block in blocks]
                    != [f"PB{index + 1:03d}" for index in range(len(blocks))]
                    or "\n\n".join(
                        str(block.get("text", "")) for block in blocks
                    )
                    != prompt_text_value
                )
            )
            or (not prompt_text_value and blocks != [])
        )
        if blocks_invalid:
            issues.append(
                _issue(
                    "PROMPT_BLOCK_CONTRACT_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.prompt_blocks",
                    "prompt_blocks 必须有序且逐字重建 prompt_text。",
                    ("prompt_delivery",),
                )
            )

        unit_operation_id = _clean_text(unit.get("operation_id")) or "OP001"
        if unit_operation_id not in operation_generations:
            issues.append(
                _issue(
                    "OPERATION_CONTRACT_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.operation_id",
                    "Prompt 单元引用了不存在的 operation。",
                    ("prompt_delivery",),
                )
            )
            unit_operation_id = operation_order[0] if operation_order else "OP001"
        unit_operation_generation = operation_generations.get(
            unit_operation_id, generation
        )
        unit_invalid_shot_ids = operation_invalid_shots.get(
            unit_operation_id, set()
        )
        shot_ids = unit.get("source_shot_ids")
        if not isinstance(shot_ids, list) or not shot_ids:
            issues.append(
                _issue(
                    "CUT_SOURCE_MISMATCH",
                    "ERROR",
                    "unit",
                    f"{unit_path}.source_shot_ids",
                    "单元必须引用至少一个来源镜头。",
                    ("prompt_delivery",),
                )
            )
            shot_ids = []
        flattened_ids_by_operation.setdefault(unit_operation_id, []).extend(
            str(item) for item in shot_ids
        )
        source_cursor = source_cursors.get(unit_operation_id, 0)
        expected_shots = source_shots[
            source_cursor : source_cursor + len(shot_ids)
        ]
        unit_generation = _generation_for_unit(
            unit_operation_generation, expected_shots
        )
        expected_ids = [shot["source_shot_id"] for shot in expected_shots]
        if shot_ids != expected_ids:
            issues.append(
                _issue(
                    "CUT_SOURCE_MISMATCH",
                    "ERROR",
                    "unit",
                    f"{unit_path}.source_shot_ids",
                    "单元来源镜号未按 shots[] 连续顺序映射。",
                    ("prompt_delivery",),
                )
            )
        source_cursors[unit_operation_id] = source_cursor + len(shot_ids)

        prompt_validation = (
            unit.get("prompt_validation")
            if isinstance(unit.get("prompt_validation"), dict)
            else {}
        )
        diagnostic_codes = prompt_validation.get("diagnostic_codes", [])
        generation_failed = (
            isinstance(diagnostic_codes, list)
            and "GENERATION_CONTEXT_INVALID" in diagnostic_codes
        )
        unreadable_failed = (
            isinstance(diagnostic_codes, list)
            and "INPUT_MATERIAL_UNREADABLE" in diagnostic_codes
        )
        expected_invalid_ids = {
            str(shot_id)
            for shot_id in expected_ids
            if str(shot_id) in unit_invalid_shot_ids
        }
        if generation_failed and (
            len(expected_ids) != 1 or not expected_invalid_ids
        ):
            issues.append(
                _issue(
                    "GENERATION_FAILURE_SCOPE_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.prompt_validation",
                    "局部 generation 失败单元必须只对应一个已标记无效的源镜。",
                    ("prompt_delivery",),
                )
            )
        if expected_invalid_ids and not generation_failed:
            issues.append(
                _issue(
                    "GENERATION_FAILURE_SCOPE_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.prompt_validation",
                    "无效 reference/mode 源镜未被隔离为局部失败单元。",
                    ("prompt_delivery",),
                )
            )
        expected_unreadable_ids = {
            str(shot["source_shot_id"])
            for shot in expected_shots
            if shot.get("compilable_source") is not True
        }
        if unreadable_failed and (
            len(expected_ids) != 1
            or expected_unreadable_ids != set(expected_ids)
            or prompt_validation.get("status") != "FAIL"
        ):
            issues.append(
                _issue(
                    "UNREADABLE_FAILURE_SCOPE_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.prompt_validation",
                    (
                        "不可读来源单元必须只覆盖一个不可编译源镜，"
                        "并把单元状态标为 FAIL。"
                    ),
                    ("prompt_delivery",),
                )
            )
        if expected_unreadable_ids and not unreadable_failed:
            issues.append(
                _issue(
                    "UNREADABLE_FAILURE_SCOPE_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.prompt_validation",
                    "不可读来源镜头未被隔离为失败单元。",
                    ("prompt_delivery",),
                )
            )

        source_hashes = unit.get("source_shot_hashes")
        expected_hashes = [shot["source_shot_hash"] for shot in expected_shots]
        if source_hashes != expected_hashes:
            issues.append(
                _issue(
                    "CUT_SOURCE_HASH_MISMATCH",
                    "ERROR",
                    "unit",
                    f"{unit_path}.source_shot_hashes",
                    "单元 source shot hash 与实际来源不一致。",
                    ("source_traceability",),
                )
            )

        is_multi = len(shot_ids) > 1
        if is_multi:
            if len(shot_ids) > max_group_cuts:
                issues.append(
                    _issue(
                        "GROUP_DURATION_INVALID",
                        "ERROR",
                        "unit",
                        unit_path,
                        f"多镜单元 Cut 数量超过策略上限 {max_group_cuts}。",
                        ("model_generation",),
                    )
                )
            compatibility = unit.get("semantic_compatibility")
            if not isinstance(compatibility, dict) or any(
                compatibility.get(key) is not True
                for key in COMPATIBILITY_KEYS
            ):
                issues.append(
                    _issue(
                        "GROUP_SEMANTIC_ATTESTATION_MISSING",
                        "ERROR",
                        "unit",
                        f"{unit_path}.semantic_compatibility",
                        "多镜单元缺少完整语义兼容确认。",
                        ("model_generation",),
                    )
                )
            if not _clean_text(unit.get("grouping_reason")):
                issues.append(
                    _issue(
                        "GROUP_SEMANTIC_ATTESTATION_MISSING",
                        "ERROR",
                        "unit",
                        f"{unit_path}.grouping_reason",
                        "多镜单元缺少具体 grouping_reason。",
                        ("model_generation",),
                    )
                )
            if unit.get("partition_strategy") != GROUPING_PARTITION_POLICY:
                issues.append(
                    _issue(
                        "GROUP_PARTITION_ATTESTATION_MISSING",
                        "ERROR",
                        "unit",
                        f"{unit_path}.partition_strategy",
                        "多镜单元缺少确定性场景级分区策略标识。",
                        ("model_generation",),
                    )
                )
            boundary_evidence = unit.get("boundary_evidence")
            if (
                not isinstance(boundary_evidence, list)
                or len(boundary_evidence) != len(shot_ids) - 1
            ):
                issues.append(
                    _issue(
                        "GROUP_BOUNDARY_EVIDENCE_MISSING",
                        "ERROR",
                        "unit",
                        f"{unit_path}.boundary_evidence",
                        "多镜单元必须逐边界携带来源绑定的语义证据。",
                        ("model_generation",),
                    )
                )

        durations: list[Decimal] = []
        for shot in expected_shots:
            try:
                duration = _duration_decimal(shot.get("duration_seconds"))
            except InvalidOperation:
                duration = None
            if duration is not None:
                durations.append(duration)
            if is_multi and duration is None:
                issues.append(
                    _issue(
                        "GROUP_DURATION_INVALID",
                        "ERROR",
                        "unit",
                        unit_path,
                        "多镜单元包含缺时长的来源镜头。",
                        ("model_generation",),
                    )
                )
        expected_total = (
            sum(durations, Decimal("0"))
            if len(durations) == len(expected_shots)
            else None
        )
        actual_total = unit.get("total_duration_seconds")
        if _json_number(expected_total) != actual_total:
            issues.append(
                _issue(
                    "GROUP_DURATION_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.total_duration_seconds",
                    "单元总时长不等于来源时长通用求和。",
                    ("model_generation",),
                )
            )
        if is_multi and expected_total is not None:
            if expected_total > max_group_duration:
                issues.append(
                    _issue(
                        "GROUP_DURATION_INVALID",
                        "ERROR",
                        "unit",
                        unit_path,
                        (
                            "多镜单元总时长超过策略上限 "
                            f"{_seconds_text(max_group_duration)} 秒。"
                        ),
                        ("model_generation",),
                    )
                )
            if profile_valid and expected_total > _profile_limit(profile):
                issues.append(
                    _issue(
                        "GROUP_DURATION_INVALID",
                        "ERROR",
                        "unit",
                        unit_path,
                        "多镜单元总时长超过 Model Profile 上限。",
                        ("model_generation",),
                    )
                )
            if profile_valid and not profile["capabilities"].get(
                "supports_multi_cut"
            ):
                issues.append(
                    _issue(
                        "MODEL_MULTI_CUT_UNSUPPORTED",
                        "ERROR",
                        "unit",
                        unit_path,
                        "Model Profile 不支持多 Cut。",
                        ("model_generation",),
                    )
                )

        timeline = unit.get("timeline")
        if not isinstance(timeline, list):
            timeline = []
        if len(timeline) != len(shot_ids):
            issues.append(
                _issue(
                    "CUT_COUNT_MISMATCH",
                    "ERROR",
                    "unit",
                    f"{unit_path}.timeline",
                    "Cut 数量与来源镜头数量不一致。",
                    ("prompt_delivery",),
                )
            )

        offset = Decimal("0")
        timeline_known = expected_total is not None
        prompt_text = (
            unit.get("prompt_text")
            if isinstance(unit.get("prompt_text"), str)
            else ""
        )
        all_known_tags = _all_generation_reference_tags(unit_generation)
        if (
            profile_valid
            and _global_reference_section(profile)
            and not generation_failed
            and not unreadable_failed
        ):
            actual_global_tags = set(
                _reference_tags(prompt_text, profile, all_known_tags)
            )
            if actual_global_tags != set(all_known_tags):
                issues.append(
                    _issue(
                        "REFERENCE_TAG_MISMATCH",
                        "ERROR",
                        "prompt",
                        f"{unit_path}.prompt_text",
                        "全局参考素材职责未逐字覆盖 role map 中的全部 tag。",
                        ("prompt_delivery",),
                    )
                )
        if (generation_failed or unreadable_failed) and prompt_text:
            issues.append(
                _issue(
                    (
                        "GENERATION_FAILURE_SCOPE_INVALID"
                        if generation_failed
                        else "UNREADABLE_FAILURE_SCOPE_INVALID"
                    ),
                    "ERROR",
                    "prompt",
                    f"{unit_path}.prompt_text",
                    "局部失败单元不得伪造 Prompt 正文。",
                    ("prompt_delivery",),
                )
            )
        if not generation_failed and not unreadable_failed and not prompt_text:
            issues.append(
                _issue(
                    "PROMPT_TEXT_MISSING",
                    "ERROR",
                    "prompt",
                    f"{unit_path}.prompt_text",
                    "可编译单元缺少 Prompt 正文。",
                    ("prompt_delivery",),
                )
            )
        for cut_index, (cut, shot) in enumerate(zip(timeline, expected_shots)):
            cut_path = f"{unit_path}.timeline[{cut_index}]"
            if not isinstance(cut, dict):
                issues.append(
                    _issue(
                        "CUT_SOURCE_MISMATCH",
                        "ERROR",
                        "cut",
                        cut_path,
                        "Cut 必须是对象。",
                        ("prompt_delivery",),
                    )
                )
                continue
            if (
                cut.get("cut_index") != cut_index + 1
                or cut.get("cut_label") != CUT_LABELS[cut_index]
                or cut.get("source_shot_id") != shot["source_shot_id"]
                or cut.get("source_order") != shot["source_order"]
            ):
                issues.append(
                    _issue(
                        "CUT_SOURCE_MISMATCH",
                        "ERROR",
                        "cut",
                        cut_path,
                        "Cut 标签、ID 或来源顺序不一致。",
                        ("prompt_delivery",),
                    )
                )
            if cut.get("source_shot_hash") != shot["source_shot_hash"]:
                issues.append(
                    _issue(
                        "CUT_SOURCE_HASH_MISMATCH",
                        "ERROR",
                        "cut",
                        f"{cut_path}.source_shot_hash",
                        "Cut source hash 与对应来源镜头不一致。",
                        ("source_traceability",),
                    )
                )
            if cut.get("compiler_provenance") != shot["field_hashes"]:
                issues.append(
                    _issue(
                        "CUT_SOURCE_HASH_MISMATCH",
                        "ERROR",
                        "cut",
                        f"{cut_path}.compiler_provenance",
                        "Cut 字段 provenance 与来源字段不一致。",
                        ("source_traceability",),
                    )
                )

            if timeline_known:
                duration = _duration_decimal(shot["duration_seconds"])
                expected_start = offset
                expected_end = offset + duration
                offset = expected_end
                if (
                    cut.get("start_seconds") != _json_number(expected_start)
                    or cut.get("end_seconds") != _json_number(expected_end)
                    or cut.get("duration_seconds") != _json_number(duration)
                ):
                    issues.append(
                        _issue(
                            "CUT_TIMELINE_INVALID",
                            "ERROR",
                            "cut",
                            cut_path,
                            "Cut 时间线与来源时长累计值不一致。",
                            ("prompt_delivery",),
                        )
                    )
            elif any(
                cut.get(key) is not None
                for key in (
                    "start_seconds",
                    "end_seconds",
                    "duration_seconds",
                )
            ):
                issues.append(
                    _issue(
                        "CUT_TIMELINE_INVALID",
                        "ERROR",
                        "cut",
                        cut_path,
                        "缺时长镜头必须保持 null 时间线。",
                        ("prompt_delivery",),
                    )
                )

            emotion_items = cut.get("emotion_visualization", [])
            if not isinstance(emotion_items, list):
                emotion_items = []
                issues.append(
                    _issue(
                        "EMOTION_VISUALIZATION_INVALID",
                        "ERROR",
                        "cut",
                        f"{cut_path}.emotion_visualization",
                        "emotion_visualization 必须是数组。",
                        ("prompt_delivery",),
                    )
                )
            for emotion_item in emotion_items:
                valid_emotion = (
                    isinstance(emotion_item, dict)
                    and emotion_item.get("provenance")
                    == "derived_emotion_visualization"
                    and _clean_text(emotion_item.get("basis_emotion"))
                    == _clean_text(shot.get("emotion_intent"))
                    and bool(_clean_text(emotion_item.get("text")))
                    and not shot.get("visible_behavior")
                    and bool(_clean_text(shot.get("emotion_intent")))
                )
                if not valid_emotion:
                    issues.append(
                        _issue(
                            "EMOTION_VISUALIZATION_INVALID",
                            "ERROR",
                            "cut",
                            f"{cut_path}.emotion_visualization",
                            "派生情绪 provenance、basis 或触发条件无效。",
                            ("prompt_delivery",),
                        )
                    )
                elif _anti_slop_terms_in_value(emotion_item.get("text")):
                    issues.append(
                        _issue(
                            "DOWNSTREAM_ANTI_SLOP",
                            "ERROR",
                            "cut",
                            f"{cut_path}.emotion_visualization",
                            "下游 emotion visualization 含空泛强化词。",
                            ("prompt_delivery",),
                        )
                    )

            block = _cut_prompt_block(prompt_text, CUT_LABELS[cut_index])
            if not generation_failed and not unreadable_failed:
                missing_dialogue = [
                    text
                    for text in _dialogue_texts(shot["dialogue"])
                    if text not in block
                ]
                if missing_dialogue:
                    issues.append(
                        _issue(
                            "DIALOGUE_MISMATCH",
                            "ERROR",
                            "prompt",
                            f"{unit_path}.prompt_text",
                            f"{CUT_LABELS[cut_index]} 未逐字包含对应来源对白。",
                            ("prompt_delivery",),
                        )
                    )
                visual_covered, continuity_covered = (
                    _cut_source_coverage(shot, block, unit_generation)
                )
                if not visual_covered:
                    issues.append(
                        _issue(
                            "SOURCE_VISUAL_ACTION_MISSING",
                            "ERROR",
                            "prompt",
                            f"{unit_path}.prompt_text",
                            (
                                f"{CUT_LABELS[cut_index]} 未消费来源"
                                "主要画面动作或其结构化等价内容。"
                            ),
                            ("prompt_delivery",),
                        )
                    )
                if not continuity_covered:
                    issues.append(
                        _issue(
                            "CONTINUITY_COVERAGE_MISSING",
                            "ERROR",
                            "prompt",
                            f"{unit_path}.prompt_text",
                            (
                                f"{CUT_LABELS[cut_index]} 未消费来源"
                                "连续性变化或目标终态。"
                            ),
                            ("prompt_delivery",),
                        )
                    )
            if profile_valid and not generation_failed and not unreadable_failed:
                expected_tags = {
                    str(item["tag"])
                    for item in _reference_roles_for_shot(
                        unit_generation, str(shot["source_shot_id"])
                    )
                }
                actual_tags = set(
                    _reference_tags(block, profile, all_known_tags)
                )
                if (
                    not _global_reference_section(profile)
                    and actual_tags != expected_tags
                ):
                    issues.append(
                        _issue(
                            "REFERENCE_TAG_MISMATCH",
                            "ERROR",
                            "prompt",
                            f"{unit_path}.prompt_text",
                            (
                                f"{CUT_LABELS[cut_index]} reference tag "
                                "未与 role map 逐字一致。"
                            ),
                            ("prompt_delivery",),
                        )
                    )
                cut_added_terms = sorted(
                    set(_anti_slop_terms_outside_quotes(block))
                    - set(shot.get("source_anti_slop_terms", []))
                )
                if cut_added_terms:
                    issues.append(
                        _issue(
                            "PROMPT_ANTI_SLOP_FAILED",
                            "ERROR",
                            "prompt",
                            f"{unit_path}.prompt_text",
                            (
                                f"{CUT_LABELS[cut_index]} 含无法追溯到"
                                "对应源镜的空泛强化词："
                                f"{', '.join(cut_added_terms)}。"
                            ),
                            ("prompt_delivery",),
                        )
                    )

        if profile_valid and not generation_failed and not unreadable_failed:
            leaks = _prompt_metadata_leaks(prompt_text, profile)
            if leaks:
                issues.append(
                    _issue(
                        "PROMPT_MODEL_METADATA_LEAK",
                        "ERROR",
                        "prompt",
                        f"{unit_path}.prompt_text",
                        f"Prompt 正文包含 metadata：{', '.join(leaks)}。",
                        ("prompt_delivery",),
                    )
                )
            source_terms = {
                term
                for shot in expected_shots
                for term in shot.get("source_anti_slop_terms", [])
            }
            prompt_terms = set(
                _anti_slop_terms_outside_quotes(prompt_text)
            )
            added_terms = sorted(prompt_terms - source_terms)
            if added_terms:
                issues.append(
                    _issue(
                        "PROMPT_ANTI_SLOP_FAILED",
                        "ERROR",
                        "prompt",
                        f"{unit_path}.prompt_text",
                        (
                            "正文含无法追溯到来源的空泛强化词："
                            f"{', '.join(added_terms)}。"
                        ),
                        ("prompt_delivery",),
                    )
                )

    expected_flattened = [
        shot["source_shot_id"] for shot in normalized.get("shots", [])
    ]
    for operation_id in operation_order:
        if (
            not normalized.get("source_global_blocked", False)
            and not operation_global_blocked.get(operation_id, False)
            and flattened_ids_by_operation.get(operation_id, [])
            != expected_flattened
        ):
            issues.append(
                _issue(
                    "SOURCE_SHOT_COVERAGE_INVALID",
                    "ERROR",
                    "plan",
                    "prompt_units",
                    f"operation {operation_id} 未按序恰好覆盖一次来源镜头。",
                    ("prompt_delivery",),
                )
            )

    if check_content_hash:
        declared_content_hash = plan.get("content_hash")
        observed_content_hash = prompt_plan_content_hash(plan)
        if declared_content_hash != observed_content_hash:
            issues.append(
                _issue(
                    "OUTPUT_HASH_MISMATCH",
                    "ERROR",
                    "plan",
                    "content_hash",
                    "prompt_plan content_hash 与实际内容不一致。",
                    ("prompt_delivery",),
                )
            )
    return _deduplicate_issues(issues)


def _plan_recompilation_issues(
    plan: Mapping[str, Any],
    expected_plan: Mapping[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    actual_units = (
        plan.get("prompt_units", [])
        if isinstance(plan.get("prompt_units"), list)
        else []
    )
    expected_units = (
        expected_plan.get("prompt_units", [])
        if isinstance(expected_plan.get("prompt_units"), list)
        else []
    )
    for unit_index in range(max(len(actual_units), len(expected_units))):
        actual_unit = (
            actual_units[unit_index]
            if unit_index < len(actual_units)
            and isinstance(actual_units[unit_index], dict)
            else {}
        )
        expected_unit = (
            expected_units[unit_index]
            if unit_index < len(expected_units)
            and isinstance(expected_units[unit_index], dict)
            else {}
        )
        if actual_unit.get("prompt_text") != expected_unit.get(
            "prompt_text"
        ):
            issues.append(
                _issue(
                    "PROMPT_RECOMPILE_MISMATCH",
                    "ERROR",
                    "prompt",
                    f"prompt_units[{unit_index}].prompt_text",
                    "Prompt 未逐字匹配可信编译输入的确定性重编译结果。",
                    ("prompt_delivery",),
                )
            )
        if actual_unit.get("prompt_validation") != expected_unit.get(
            "prompt_validation"
        ):
            issues.append(
                _issue(
                    "UNIT_VALIDATION_LEDGER_MISMATCH",
                    "ERROR",
                    "unit",
                    f"prompt_units[{unit_index}].prompt_validation",
                    "单元 checks、status 或诊断账本未匹配重算结果。",
                    ("prompt_delivery",),
                )
            )

    if plan.get("validation") != expected_plan.get("validation"):
        issues.append(
            _issue(
                "TOP_LEVEL_VALIDATION_MISMATCH",
                "ERROR",
                "plan",
                "validation",
                "顶层 validation 未匹配从来源与单元重算的结果。",
                ("prompt_delivery",),
            )
        )
    if plan != expected_plan:
        issues.append(
            _issue(
                "PLAN_RECOMPILATION_MISMATCH",
                "ERROR",
                "plan",
                "$",
                (
                    "prompt_plan 未逐字段匹配由只读来源、decisions、"
                    "generation context 与 runtime Profile 重建的 plan。"
                ),
                ("prompt_delivery",),
            )
        )
    return issues


def validate_prompt_plan(
    source_document: Any, plan: Any
) -> dict[str, Any]:
    normalized, normalization_issues = normalize_input(source_document)
    structural_issues = _validate_plan_structure(
        normalized,
        plan,
        check_content_hash=True,
        source_document=source_document,
    )
    expected_plan: dict[str, Any] | None = None
    recompilation_issues: list[dict[str, Any]] = []
    expected_diagnostics: list[dict[str, Any]] = []
    prompt_units: list[dict[str, Any]] = []

    if isinstance(plan, dict):
        decisions_snapshot, runtime_profile, compiler_input_issues = (
            _validate_compiler_inputs(normalized, plan)
        )
        if not compiler_input_issues:
            plan_delivery = plan.get("delivery", {})
            recompile_slug = (
                _clean_text(plan_delivery.get("slug"))
                if isinstance(plan_delivery, dict)
                else None
            )
            expected_plan = build_prompt_plan(
                source_document,
                decisions=decisions_snapshot,
                model_profile=runtime_profile,
                delivery_slug=recompile_slug,
            )
            recompilation_issues = _plan_recompilation_issues(
                plan, expected_plan
            )
            expected_diagnostics = copy.deepcopy(
                expected_plan.get("diagnostics", [])
            )
            prompt_units = copy.deepcopy(
                expected_plan.get("prompt_units", [])
            )

    if expected_plan is None:
        prompt_units = (
            copy.deepcopy(plan.get("prompt_units", []))
            if isinstance(plan, dict)
            and isinstance(plan.get("prompt_units"), list)
            else []
        )

    all_issues = _deduplicate_issues(
        list(normalization_issues)
        + expected_diagnostics
        + structural_issues
        + recompilation_issues
    )
    report = _validation_object(normalized, prompt_units, all_issues)
    declared_status = (
        plan.get("validation", {}).get("status")
        if isinstance(plan, dict) and isinstance(plan.get("validation"), dict)
        else None
    )
    if declared_status != report["status"]:
        mismatch = _issue(
            "VALIDATION_STATUS_MISMATCH",
            "ERROR",
            "plan",
            "validation.status",
            (
                f"plan 声明状态 {declared_status!r} 与重算状态 "
                f"{report['status']!r} 不一致。"
            ),
            ("prompt_delivery",),
        )
        all_issues = _deduplicate_issues(all_issues + [mismatch])
        report = _validation_object(normalized, prompt_units, all_issues)
    return report


def stable_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def prompt_table_rows(plan: Mapping[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for unit in plan.get("prompt_units", []):
        if not isinstance(unit, dict):
            continue
        duration = unit.get("total_duration_seconds")
        if duration is None:
            duration_text = ""
        elif isinstance(duration, (int, float)) and not isinstance(
            duration, bool
        ):
            duration_text = json.dumps(duration, allow_nan=False)
        else:
            duration_text = str(duration)
        source_ids = unit.get("source_shot_ids", [])
        rows.append(
            [
                str(unit.get("prompt_unit_id", "")),
                "、".join(str(item) for item in source_ids),
                duration_text,
                str(unit.get("prompt_text", "")),
            ]
        )
    return rows


def prompt_table_xlsx_rows(plan: Mapping[str, Any]) -> list[list[str]]:
    return prompt_table_rows(plan)


def reconstruct_prompt_texts_from_xlsx_rows(
    rows: Sequence[Sequence[str]],
) -> dict[str, str]:
    blocks_by_unit: dict[str, list[str]] = {}
    order: list[str] = []
    for row in rows:
        if len(row) != len(PROMPT_TABLE_COLUMNS):
            raise DeliveryError("Prompt table row does not have four cells")
        unit_id = str(row[0])
        if not unit_id:
            raise DeliveryError("XLSX physical row is missing Prompt 段号")
        if unit_id not in blocks_by_unit:
            blocks_by_unit[unit_id] = []
            order.append(unit_id)
        blocks_by_unit[unit_id].append(str(row[3]))
    return {
        unit_id: "\n\n".join(blocks_by_unit[unit_id])
        for unit_id in order
    }


def _markdown_cell(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    escaped = html.escape(normalized, quote=False).replace("|", "&#124;")
    return escaped.replace("\n", "<br>")


def prompt_table_markdown_bytes(rows: Sequence[Sequence[str]]) -> bytes:
    lines = [
        "| " + " | ".join(PROMPT_TABLE_COLUMNS) + " |",
        "| " + " | ".join("---" for _ in PROMPT_TABLE_COLUMNS) + " |",
    ]
    for row in rows:
        if len(row) != len(PROMPT_TABLE_COLUMNS):
            raise DeliveryError("Prompt table row does not have four cells")
        lines.append("| " + " | ".join(_markdown_cell(str(cell)) for cell in row) + " |")
    return ("\n".join(lines) + "\n").encode("utf-8")


def parse_prompt_table_markdown(payload: bytes) -> list[list[str]]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise DeliveryError(f"prompt_table.md is not UTF-8: {exc}") from exc
    if len(lines) < 2:
        raise DeliveryError("prompt_table.md is missing its header")

    def parse_line(line: str) -> list[str]:
        if not line.startswith("|") or not line.endswith("|"):
            raise DeliveryError("prompt_table.md row is not a pipe table row")
        cells = [cell.strip() for cell in line[1:-1].split("|")]
        return [
            html.unescape(cell.replace("<br>", "\n"))
            for cell in cells
        ]

    if tuple(parse_line(lines[0])) != PROMPT_TABLE_COLUMNS:
        raise DeliveryError("prompt_table.md columns do not match the contract")
    separator = parse_line(lines[1])
    if len(separator) != len(PROMPT_TABLE_COLUMNS) or any(
        cell != "---" for cell in separator
    ):
        raise DeliveryError("prompt_table.md separator is invalid")
    rows = [parse_line(line) for line in lines[2:]]
    if any(len(row) != len(PROMPT_TABLE_COLUMNS) for row in rows):
        raise DeliveryError("prompt_table.md has a non-four-cell row")
    return rows


def _xlsx_cell_reference(column_index: int, row_index: int) -> str:
    value = column_index
    letters = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row_index}"


def _xlsx_inline_cell(
    reference: str, value: str, style_index: int
) -> str:
    escaped = html.escape(value, quote=False)
    return (
        f'<c r="{reference}" t="inlineStr" s="{style_index}">'
        f'<is><t xml:space="preserve">{escaped}</t></is></c>'
    )


def _xlsx_prompt_column_width(rows: Sequence[Sequence[str]]) -> int:
    longest = max(
        (_weighted_text_length(str(row[3])) for row in rows if len(row) == 4),
        default=0.0,
    )
    return max(
        XLSX_PROMPT_WIDTH_MIN,
        min(XLSX_PROMPT_WIDTH_MAX, math.ceil(math.sqrt(longest) * 7)),
    )


def _xlsx_row_height_for_row(
    row: Sequence[str], prompt_width: int
) -> int:
    leading_height = max(
        _estimated_row_height(str(value), width)
        for value, width in zip(row[:3], (14, 24, 16))
    )
    prompt_height = _estimated_row_height(str(row[3]), prompt_width)
    height = max(leading_height, prompt_height)
    return int(min(XLSX_ROW_HEIGHT_LIMIT, max(24, height)))


def prompt_table_xlsx_bytes(rows: Sequence[Sequence[str]]) -> bytes:
    worksheet_rows: list[str] = []
    prompt_width = _xlsx_prompt_column_width(rows)
    all_rows = [list(PROMPT_TABLE_COLUMNS)] + [
        [str(cell) for cell in row] for row in rows
    ]
    previous_unit = ""
    for row_index, row in enumerate(all_rows, start=1):
        cells: list[str] = []
        group_first = row_index > 1 and row[0] != previous_unit
        for column_index, value in enumerate(row, start=1):
            reference = _xlsx_cell_reference(column_index, row_index)
            if row_index > 1 and column_index == 3 and value:
                try:
                    numeric = Decimal(value)
                except InvalidOperation as exc:
                    raise DeliveryError(
                        "Duration cell is not a finite number"
                    ) from exc
                if not numeric.is_finite():
                    raise DeliveryError("Duration cell is not finite")
                style_index = 5 if group_first else 2
                cells.append(f'<c r="{reference}" s="{style_index}"><v>{value}</v></c>')
            else:
                if row_index == 1:
                    style_index = 1
                elif group_first:
                    style_index = 6 if column_index == 4 else 4
                else:
                    style_index = 3 if column_index == 4 else 0
                cells.append(
                    _xlsx_inline_cell(reference, value, style_index)
                )
        row_height = (
            24
            if row_index == 1
            else _xlsx_row_height_for_row(row, prompt_width)
        )
        worksheet_rows.append(
            f'<row r="{row_index}" ht="{row_height}" customHeight="1">'
            f'{"".join(cells)}</row>'
        )
        if row_index > 1:
            previous_unit = row[0]

    last_row = max(1, len(all_rows))
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:D{last_row}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        '<cols>'
        '<col min="1" max="1" width="14" customWidth="1"/>'
        '<col min="2" max="2" width="24" customWidth="1"/>'
        '<col min="3" max="3" width="16" customWidth="1"/>'
        f'<col min="4" max="4" width="{prompt_width}" customWidth="1"/>'
        '</cols>'
        f'<sheetData>{"".join(worksheet_rows)}</sheetData>'
        f'<autoFilter ref="A1:D{last_row}"/>'
        '</worksheet>'
    )
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>'
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Prompt Table" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>'
        ),
        "xl/styles.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Arial"/></font>'
            '<font><b/><sz val="11"/><name val="Arial"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
            '<border><left/><right/><top style="medium"><color rgb="FF808080"/></top>'
            '<bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="7">'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
            '<alignment wrapText="1" vertical="top"/></xf>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
            '<alignment wrapText="1" vertical="top"/></xf>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
            '<alignment wrapText="1" vertical="top"/></xf>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1">'
            '<alignment wrapText="1" vertical="top"/></xf>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1">'
            '<alignment wrapText="1" vertical="top"/></xf>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1">'
            '<alignment wrapText="1" vertical="top"/></xf>'
            '</cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'
        ),
        "xl/worksheets/sheet1.xml": sheet_xml,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o600 << 16
            archive.writestr(info, files[name].encode("utf-8"))
    return buffer.getvalue()


def parse_prompt_table_xlsx(payload: bytes) -> list[list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload), mode="r") as archive:
            sheet_payload = archive.read("xl/worksheets/sheet1.xml")
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise DeliveryError(f"prompt_table.xlsx is unreadable: {exc}") from exc
    try:
        root = ET.fromstring(sheet_payload)
    except ET.ParseError as exc:
        raise DeliveryError(f"prompt_table.xlsx sheet XML is invalid: {exc}") from exc
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    parsed_rows: list[list[str]] = []
    for row in root.findall(".//x:sheetData/x:row", namespace):
        cells = ["", "", "", ""]
        for cell in row.findall("x:c", namespace):
            reference = cell.get("r", "")
            match = re.match(r"([A-Z]+)", reference)
            if match is None:
                continue
            column = 0
            for character in match.group(1):
                column = column * 26 + ord(character) - 64
            if not 1 <= column <= 4:
                continue
            if cell.get("t") == "inlineStr":
                value = "".join(
                    text.text or ""
                    for text in cell.findall(".//x:t", namespace)
                )
            else:
                value_node = cell.find("x:v", namespace)
                value = value_node.text if value_node is not None else ""
            cells[column - 1] = value
        parsed_rows.append(cells)
    if not parsed_rows or tuple(parsed_rows[0]) != PROMPT_TABLE_COLUMNS:
        raise DeliveryError("prompt_table.xlsx columns do not match the contract")
    return parsed_rows[1:]


def inspect_prompt_table_xlsx_layout(payload: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload), mode="r") as archive:
            sheet_payload = archive.read("xl/worksheets/sheet1.xml")
            workbook_payload = archive.read("xl/workbook.xml")
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise DeliveryError(f"prompt_table.xlsx is unreadable: {exc}") from exc
    try:
        sheet_root = ET.fromstring(sheet_payload)
        workbook_root = ET.fromstring(workbook_payload)
    except ET.ParseError as exc:
        raise DeliveryError(f"prompt_table.xlsx XML is invalid: {exc}") from exc
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    prompt_width: float | None = None
    for column in sheet_root.findall(".//x:cols/x:col", namespace):
        if column.get("min") == "4" and column.get("max") == "4":
            try:
                prompt_width = float(column.get("width", ""))
            except ValueError:
                prompt_width = None
            break
    row_heights: list[float] = []
    custom_height_rows = 0
    for row in sheet_root.findall(".//x:sheetData/x:row", namespace):
        try:
            height = float(row.get("ht", ""))
        except ValueError:
            height = math.inf
        row_heights.append(height)
        if row.get("customHeight") == "1":
            custom_height_rows += 1
    sheet_names = [
        sheet.get("name", "")
        for sheet in workbook_root.findall(".//x:sheets/x:sheet", namespace)
    ]
    pane = sheet_root.find(".//x:sheetViews/x:sheetView/x:pane", namespace)
    auto_filter = sheet_root.find(".//x:autoFilter", namespace)
    return {
        "sheet_names": sheet_names,
        "prompt_column_width": prompt_width,
        "row_heights": row_heights,
        "custom_height_rows": custom_height_rows,
        "row_count_including_header": len(row_heights),
        "header_frozen": pane is not None and pane.get("state") == "frozen",
        "auto_filter": auto_filter is not None,
    }


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _formal_validation_report(
    plan: Mapping[str, Any],
    plan_payload: bytes,
    markdown_payload: bytes,
    xlsx_payload: bytes,
    rows: Sequence[Sequence[str]],
    xlsx_rows: Sequence[Sequence[str]],
) -> dict[str, Any]:
    files = _plan_delivery_file_map(plan)
    report: dict[str, Any] = {
        "contract_name": VALIDATION_CONTRACT_NAME,
        "contract_version": VALIDATION_CONTRACT_VERSION,
        "source_plan_content_hash": plan.get("content_hash"),
        "status": plan.get("validation", {}).get("status", "FAIL"),
        "validation": copy.deepcopy(plan.get("validation", {})),
        "table_contract": {
            "columns": list(PROMPT_TABLE_COLUMNS),
            "row_count": len(rows),
            "rows": [list(row) for row in rows],
        },
        "xlsx_table_contract": {
            "columns": list(PROMPT_TABLE_COLUMNS),
            "physical_row_count": len(xlsx_rows),
            "rows": [list(row) for row in xlsx_rows],
            "prompt_reconstruction": "one-row-one-prompt-unit",
            "prompt_column_width_range": [
                XLSX_PROMPT_WIDTH_MIN,
                XLSX_PROMPT_WIDTH_MAX,
            ],
            "maximum_row_height_points": int(XLSX_ROW_HEIGHT_LIMIT),
        },
        "artifact_hashes": {
            files["plan"]: _sha256_bytes(plan_payload),
            files["markdown"]: _sha256_bytes(markdown_payload),
            files["xlsx"]: _sha256_bytes(xlsx_payload),
        },
    }
    report["content_hash"] = sha256_json(report)
    return report


def derive_delivery_artifacts(plan: Mapping[str, Any]) -> dict[str, bytes]:
    files = _plan_delivery_file_map(plan)
    rows = prompt_table_rows(plan)
    xlsx_rows = prompt_table_xlsx_rows(plan)
    plan_payload = stable_json_bytes(plan)
    markdown_payload = prompt_table_markdown_bytes(rows)
    xlsx_payload = prompt_table_xlsx_bytes(xlsx_rows)
    report = _formal_validation_report(
        plan,
        plan_payload,
        markdown_payload,
        xlsx_payload,
        rows,
        xlsx_rows,
    )
    return {
        files["plan"]: plan_payload,
        files["markdown"]: markdown_payload,
        files["xlsx"]: xlsx_payload,
        files["validation"]: stable_json_bytes(report),
    }


def write_delivery_package(
    output_dir: Path | str, artifacts: Mapping[str, bytes]
) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir():
        raise DeliveryError(f"Output path is not a directory: {destination}")
    formal_files = tuple(artifacts)
    if (
        len(formal_files) != 4
        or len(set(formal_files)) != 4
        or any("prompt" not in name for name in formal_files)
    ):
        raise DeliveryError("Delivery package must contain exactly four formal files")
    temporary_paths: dict[str, Path] = {}
    try:
        for name in formal_files:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination,
                prefix=f".{name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_paths[name] = Path(handle.name)
                handle.write(artifacts[name])
                handle.flush()
        for name in formal_files:
            temporary_paths[name].replace(destination / name)
    finally:
        for temporary_path in temporary_paths.values():
            if temporary_path.exists():
                temporary_path.unlink()


def build_delivery_package(
    source_document: Any,
    decisions: Any = None,
    model_profile: Any = None,
    delivery_slug: str | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    plan = build_prompt_plan(
        source_document,
        decisions=decisions,
        model_profile=model_profile,
        delivery_slug=delivery_slug,
    )
    return plan, derive_delivery_artifacts(plan)


def validate_delivery_package(
    source_document: Any,
    output_dir: Path | str,
    delivery_slug: str | None = None,
) -> dict[str, Any]:
    destination = Path(output_dir)
    slug = (
        _ascii_kebab_slug(delivery_slug)
        if delivery_slug is not None
        else derive_delivery_slug(None, source_document)
    )
    files = delivery_file_map(slug)
    formal_files = tuple(files.values())
    package_issues: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    for name in formal_files:
        path = destination / name
        try:
            payloads[name] = path.read_bytes()
        except OSError as exc:
            package_issues.append(
                _issue(
                    "DELIVERY_FILE_MISSING",
                    "ERROR",
                    "package",
                    name,
                    f"正式交付文件不可读：{exc}",
                    ("delivery_integrity",),
                )
            )
    if package_issues:
        return {
            "status": "FAIL",
            "package_errors": package_issues,
            "plan_validation": None,
            "deterministic_checks": {
                "four_files_present": False,
                "plan_bytes": False,
                "markdown_cells": False,
                "xlsx_cells": False,
                "validation_report": False,
            },
        }

    try:
        plan = json.loads(payloads[files["plan"]].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return {
            "status": "FAIL",
            "package_errors": [
                _issue(
                    "DELIVERY_PLAN_UNREADABLE",
                    "ERROR",
                    "package",
                    files["plan"],
                    f"机器事实源不可读：{exc}",
                    ("delivery_integrity",),
                )
            ],
            "plan_validation": None,
            "deterministic_checks": {
                "four_files_present": True,
                "plan_bytes": False,
                "markdown_cells": False,
                "xlsx_cells": False,
                "validation_report": False,
            },
        }

    try:
        declared_files = _plan_delivery_file_map(plan)
    except DeliveryError as exc:
        declared_files = {}
        package_issues.append(
            _issue(
                "DELIVERY_NAMING_INVALID",
                "ERROR",
                "package",
                files["plan"],
                str(exc),
                ("delivery_integrity",),
            )
        )
    if declared_files != files:
        if declared_files:
            package_issues.append(
                _issue(
                    "DELIVERY_NAMING_INVALID",
                    "ERROR",
                    "package",
                    files["plan"],
                    "plan 登记的正式文件名与本次输入文件名派生结果不一致。",
                    ("delivery_integrity",),
                )
            )
        return {
            "status": "FAIL",
            "package_errors": package_issues,
            "plan_validation": None,
            "deterministic_checks": {
                "four_files_present": True,
                "plan_bytes": False,
                "markdown_cells": False,
                "xlsx_cells": False,
                "validation_report": False,
            },
        }

    plan_validation = validate_prompt_plan(source_document, plan)
    rows = prompt_table_rows(plan)
    expected_xlsx_rows = prompt_table_xlsx_rows(plan)
    expected_artifacts = derive_delivery_artifacts(plan)
    plan_bytes_ok = (
        payloads[files["plan"]] == expected_artifacts[files["plan"]]
    )
    if not plan_bytes_ok:
        package_issues.append(
            _issue(
                "DELIVERY_NONDETERMINISTIC",
                "ERROR",
                "package",
                files["plan"],
                "Prompt plan 不是机器事实源的确定性 JSON 字节派生。",
                ("delivery_integrity",),
            )
        )

    markdown_cells_ok = False
    try:
        markdown_rows = parse_prompt_table_markdown(
            payloads[files["markdown"]]
        )
        markdown_cells_ok = (
            markdown_rows == rows
            and payloads[files["markdown"]]
            == expected_artifacts[files["markdown"]]
        )
    except DeliveryError as exc:
        package_issues.append(
            _issue(
                "DELIVERY_TABLE_INVALID",
                "ERROR",
                "package",
                files["markdown"],
                str(exc),
                ("delivery_integrity",),
            )
        )
    if not markdown_cells_ok and not any(
        issue["path"] == files["markdown"] for issue in package_issues
    ):
        package_issues.append(
            _issue(
                "DELIVERY_TABLE_TAMPERED",
                "ERROR",
                "package",
                files["markdown"],
                "Markdown 单元格未逐格匹配机器事实源。",
                ("delivery_integrity",),
            )
        )

    xlsx_cells_ok = False
    try:
        xlsx_rows = parse_prompt_table_xlsx(payloads[files["xlsx"]])
        xlsx_layout = inspect_prompt_table_xlsx_layout(
            payloads[files["xlsx"]]
        )
        reconstructed = reconstruct_prompt_texts_from_xlsx_rows(xlsx_rows)
        expected_reconstructed = {
            str(unit.get("prompt_unit_id", "")): str(
                unit.get("prompt_text", "")
            )
            for unit in plan.get("prompt_units", [])
            if isinstance(unit, dict)
        }
        prompt_width = xlsx_layout.get("prompt_column_width")
        row_heights = xlsx_layout.get("row_heights", [])
        layout_ok = (
            xlsx_layout.get("sheet_names") == ["Prompt Table"]
            and isinstance(prompt_width, (int, float))
            and XLSX_PROMPT_WIDTH_MIN <= prompt_width <= XLSX_PROMPT_WIDTH_MAX
            and bool(row_heights)
            and all(
                isinstance(height, (int, float))
                and math.isfinite(height)
                and height <= float(XLSX_ROW_HEIGHT_LIMIT)
                for height in row_heights
            )
            and xlsx_layout.get("custom_height_rows")
            == xlsx_layout.get("row_count_including_header")
            and xlsx_layout.get("header_frozen") is True
            and xlsx_layout.get("auto_filter") is True
        )
        xlsx_cells_ok = (
            xlsx_rows == expected_xlsx_rows
            and reconstructed == expected_reconstructed
            and layout_ok
            and payloads[files["xlsx"]]
            == expected_artifacts[files["xlsx"]]
        )
    except DeliveryError as exc:
        package_issues.append(
            _issue(
                "DELIVERY_TABLE_INVALID",
                "ERROR",
                "package",
                files["xlsx"],
                str(exc),
                ("delivery_integrity",),
            )
        )
    if not xlsx_cells_ok and not any(
        issue["path"] == files["xlsx"] for issue in package_issues
    ):
        package_issues.append(
            _issue(
                "DELIVERY_TABLE_TAMPERED",
                "ERROR",
                "package",
                files["xlsx"],
                "Excel 单元格未逐格匹配机器事实源。",
                ("delivery_integrity",),
            )
        )

    validation_report_ok = (
        payloads[files["validation"]]
        == expected_artifacts[files["validation"]]
    )
    if not validation_report_ok:
        package_issues.append(
            _issue(
                "DELIVERY_VALIDATION_TAMPERED",
                "ERROR",
                "package",
                files["validation"],
                "验证报告未确定性匹配 plan 与其两个表格派生物。",
                ("delivery_integrity",),
            )
        )

    return {
        "status": (
            "FAIL"
            if package_issues
            else plan_validation.get("status", "FAIL")
        ),
        "package_errors": package_issues,
        "plan_validation": plan_validation,
        "deterministic_checks": {
            "four_files_present": True,
            "plan_bytes": plan_bytes_ok,
            "markdown_cells": markdown_cells_ok,
            "xlsx_cells": xlsx_cells_ok,
            "validation_report": validation_report_ok,
        },
    }


def write_json_atomic(path: Path | str, value: Any) -> None:
    """Atomically write stable JSON next to the requested output."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.write("\n")
            handle.flush()
        temporary_path.replace(output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def build_failure_delivery(
    message: str,
    source_document: Any = None,
    delivery_slug: str | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    normalized, normalization_issues = normalize_input(source_document)
    profile = resolve_model_profile()
    failure_issue = _issue(
        "GLOBAL_CONTRACT_UNREADABLE",
        "ERROR",
        "source",
        "$",
        message,
        ("prompt_compilation", "delivery"),
    )
    empty_task = {
        "primary": "",
        "input_topology": "",
        "modules": [],
        "source": "unresolved",
    }
    empty_generation = {
        "mode": "",
        "mode_source": "unresolved",
        "available_reference_tags": [],
        "reference_role_map": [],
        "edit_scope": [],
        "edit_deltas": [],
        "extend_context": {},
        "asset_assignments": [],
        "asset_binding": {"state": "unmapped", "source": "none"},
        "unused_assets": [],
        "story_contract": {},
        "task_modules": [],
        "global_reference_section": _global_reference_section(profile),
        "runtime_decisions_hash": None,
        "global_blocked": True,
        "invalid_shot_ids": [],
    }
    plan: dict[str, Any] = {
        "contract_name": PLAN_CONTRACT_NAME,
        "contract_version": PLAN_CONTRACT_VERSION,
        "skill": {"name": SKILL_NAME, "version": SKILL_VERSION},
        "delivery": {
            "slug": (
                _ascii_kebab_slug(delivery_slug)
                if delivery_slug is not None
                else derive_delivery_slug(None, source_document)
            ),
            "files": {},
        },
        "compiler_inputs": _compiler_inputs(normalized, None, profile),
        "source": copy.deepcopy(normalized["source"]),
        "task": copy.deepcopy(empty_task),
        "operations": [
            {
                "operation_id": "OP001",
                "order": 1,
                "depends_on_operation_id": None,
                "task": copy.deepcopy(empty_task),
                "generation": copy.deepcopy(empty_generation),
                "prompt_unit_ids": [],
                "submission_ready": False,
            }
        ],
        "story_contract": {},
        "required_entities": [],
        "dialogue_ledger": [],
        "asset_binding": {"state": "unmapped", "source": "none"},
        "asset_inventory": {"complete": False, "items": []},
        "asset_assignments": [],
        "unused_assets": [],
        "mapping_confidence": "low",
        "request_configuration": {
            "raw": {},
            "normalized": {},
            "prompt_isolation": True,
        },
        "prompt_advisories": [],
        "submission_ready": False,
        "generation": empty_generation,
        "model_profile": profile,
        "prompt_units": [],
        "diagnostics": [],
        "validation": {},
    }
    plan["delivery"]["files"] = delivery_file_map(
        plan["delivery"]["slug"]
    )
    issues = _deduplicate_issues(
        list(normalization_issues) + [failure_issue]
    )
    plan["diagnostics"] = issues
    plan["validation"] = _validation_object(normalized, [], issues)
    plan["content_hash"] = prompt_plan_content_hash(plan)
    return plan, derive_delivery_artifacts(plan)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"Build or validate {PLAN_CONTRACT_NAME}/"
            f"{PLAN_CONTRACT_VERSION} deliveries."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser(
        "build", help="Build the four-file Prompt delivery"
    )
    build_parser.add_argument("--input", required=True, type=Path)
    build_parser.add_argument("--output-dir", required=True, type=Path)
    build_parser.add_argument("--decisions", type=Path)
    profile_group = build_parser.add_mutually_exclusive_group()
    profile_group.add_argument("--profile-id", choices=sorted(BUILTIN_PROFILES))
    profile_group.add_argument("--profile-file", type=Path)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate the four-file delivery against its immutable source",
    )
    validate_parser.add_argument("--input", required=True, type=Path)
    validate_parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    source_document: Any = None
    delivery_slug = derive_delivery_slug(args.input.name)
    try:
        source_document = load_json(args.input)
        delivery_slug = derive_delivery_slug(
            args.input.name, source_document
        )
        if args.command == "build":
            decisions = (
                load_json(args.decisions) if args.decisions is not None else None
            )
            profile_document = (
                load_json(args.profile_file)
                if args.profile_file is not None
                else None
            )
            profile = resolve_model_profile(
                profile_id=args.profile_id,
                profile_document=profile_document,
            )
            plan, artifacts = build_delivery_package(
                source_document,
                decisions=decisions,
                model_profile=profile,
                delivery_slug=delivery_slug,
            )
            write_delivery_package(args.output_dir, artifacts)
            print(
                json.dumps(
                    {
                        "status": plan["validation"]["status"],
                        "output_dir": str(args.output_dir),
                        "files": list(artifacts),
                        "summary": plan["validation"]["summary"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return (
                0
                if plan["validation"]["status"] in {"PASS", "WARN"}
                else 2
            )

        report = validate_delivery_package(
            source_document,
            args.output_dir,
            delivery_slug=delivery_slug,
        )
        print(
            json.dumps(
                report,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0 if report["status"] in {"PASS", "WARN"} else 2
    except (GroupingReviewError, AssetBindingError) as exc:
        print(
            json.dumps(
                {"status": "FAIL", "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except (DeliveryError, InvalidOperation) as exc:
        if args.command == "build":
            try:
                plan, artifacts = build_failure_delivery(
                    str(exc),
                    source_document=source_document,
                    delivery_slug=delivery_slug,
                )
                write_delivery_package(args.output_dir, artifacts)
                print(
                    json.dumps(
                        {
                            "status": "FAIL",
                            "error": str(exc),
                            "output_dir": str(args.output_dir),
                            "files": list(artifacts),
                            "summary": plan["validation"]["summary"],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                return 2
            except (DeliveryError, OSError, InvalidOperation) as write_exc:
                print(
                    json.dumps(
                        {
                            "status": "FAIL",
                            "error": str(exc),
                            "delivery_error": str(write_exc),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                return 2
        print(
            json.dumps(
                {"status": "FAIL", "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
