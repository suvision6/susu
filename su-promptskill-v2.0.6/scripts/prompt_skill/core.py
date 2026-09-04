#!/usr/bin/env python3
"""Build and validate immutable-source prompt-plan/2.0.6 deliveries."""

from __future__ import annotations

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Shared contracts and helpers for the prompt_delivery facade."

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
SKILL_VERSION = "2.0.6"
PLAN_CONTRACT_NAME = "prompt-plan"
PLAN_CONTRACT_VERSION = "2.0.6"
SOURCE_MODES = {
    "upstream_structured",
    "partial_storyboard",
    "standalone_storyboard",
    "direct_material",
}
COMPILER_INPUTS_CONTRACT = "prompt-compiler-inputs/2.0.6"
VALIDATION_CONTRACT_NAME = "prompt-validation"
VALIDATION_CONTRACT_VERSION = "2.0.6"
DIALOGUE_DELIVERY_LABELS = {
    "onscreen": "画内",
    "on_screen": "画内",
    "画内": "画内",
    "os": "画外",
    "offscreen": "画外",
    "off_screen": "画外",
    "画外": "画外",
    "voiceover": "旁白",
    "vo": "旁白",
    "旁白": "旁白",
}
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
    "space_map",
    "lighting_strategy",
    "color_strategy",
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
    raw_delivery = _clean_text(item.get("delivery"))
    delivery = DIALOGUE_DELIVERY_LABELS.get(raw_delivery, "")
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
