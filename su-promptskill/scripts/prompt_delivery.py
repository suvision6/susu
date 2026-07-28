#!/usr/bin/env python3
"""Build and validate immutable-source prompt-plan/1.0.0 deliveries."""

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
import xml.etree.ElementTree as ET
import zipfile


SKILL_NAME = "su-promptskill"
SKILL_VERSION = "1.3.1"
PLAN_CONTRACT_NAME = "prompt-plan"
PLAN_CONTRACT_VERSION = "1.0.0"
SOURCE_MODES = {
    "upstream_structured",
    "partial_storyboard",
    "standalone_storyboard",
    "direct_material",
}
COMPILER_INPUTS_CONTRACT = "prompt-compiler-inputs/1.0.0"
VALIDATION_CONTRACT_NAME = "prompt-validation"
VALIDATION_CONTRACT_VERSION = "1.0.0"
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

# grouping-rules.md owns these v1.0.0 strategy values.
GROUPING_MAX_DURATION_SECONDS = Decimal("15")
STANDALONE_WHEN_DURATION_GT_SECONDS = Decimal("10")
MAX_CUTS_PER_GROUP = 5

COMPATIBILITY_KEYS = (
    "space",
    "time",
    "reality_layer",
    "action_continuity",
    "narrative_intent",
)
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
    "audio_reference": {"video"},
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
CUT_LABELS = tuple(f"Cut {index}" for index in range(1, 6))
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
    "seedance-2.0-default": {
        "profile_id": "seedance-2.0-default",
        "model_name": "Seedance 2.0",
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
        },
        "prompt_adapter_id": "explicit-cut-zh-v1",
    },
}


class DeliveryError(ValueError):
    """Raised for unreadable CLI material, not per-unit delivery diagnostics."""


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
        prefix = "@Image" if media_type == "image" else "@Video"
    elif convention_id == "indexed-prefix-v1":
        prefix = _clean_text(convention.get(f"{media_type}_prefix"))
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
    pattern = _reference_tag_pattern(convention, media_type, anchored=True)
    return pattern is not None and pattern.fullmatch(tag) is not None


def _reference_tags(text: str, profile: Mapping[str, Any]) -> list[str]:
    convention = profile.get("capabilities", {}).get(
        "reference_tag_convention", {}
    )
    matches: list[tuple[int, str]] = []
    for media_type in ("image", "video"):
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
            "end_state": _as_items(raw_shot.get("end_state")),
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
    selected_id = profile_id or "seedance-2.0-default"
    if selected_id not in BUILTIN_PROFILES:
        raise DeliveryError(f"Unknown built-in profile: {selected_id}")
    return copy.deepcopy(BUILTIN_PROFILES[selected_id])


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
            and len(shot_positions.get(shot_id, [])) == 1
        }

        if tag in mapped_tags:
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.tag",
                    "每个 reference tag 只能承担一个显式角色。",
                    ("prompt_compilation",),
                )
            )
        mapped_tags.add(tag)
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
        if media_type not in {"image", "video"}:
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.media_type",
                    "media_type 必须显式为 image 或 video。",
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
            or len(shot_positions.get(shot_id, [])) != 1
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
            if shot_id in item["applies_to_shot_ids"]
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
            has_edit_source = any(
                item["role"] == "edit_source" for item in shot_roles
            )
            has_applicable_delta = any(
                isinstance(delta, dict)
                and shot_id in delta.get("applies_to_shot_ids", [])
                for delta in edit_deltas
            )
            if (
                not has_edit_source
                or shot_id in edit_invalid_shot_ids
                or not has_applicable_delta
            ):
                invalidate_shot(
                    shot_id,
                    (
                        "edit Cut 需要适用于该源镜的 edit_source、合法 "
                        "edit_scope 与 edit delta。"
                    ),
                    shot_path,
                )
        elif mode == "extend":
            has_extension_source = any(
                item["role"] == "extension_source" for item in shot_roles
            )
            if not has_extension_source or not extend_context_valid:
                invalidate_shot(
                    shot_id,
                    (
                        "extend Cut 需要适用于该源镜的 extension_source、"
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


def _validate_group_decision(
    raw_group: Any,
    group_index: int,
    shots: Sequence[Mapping[str, Any]],
    positions: Mapping[str, Sequence[int]],
    accepted_indices: set[int],
    profile: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, list[str], set[int]]:
    reasons: list[str] = []
    involved_indices: set[int] = set()
    if not isinstance(raw_group, dict):
        return None, ["group 必须是 JSON 对象"], involved_indices

    shot_ids = raw_group.get("source_shot_ids")
    if not isinstance(shot_ids, list) or len(shot_ids) < 2:
        return None, ["source_shot_ids 必须包含至少两个镜号"], involved_indices
    if any(not isinstance(shot_id, str) or not shot_id.strip() for shot_id in shot_ids):
        return None, ["source_shot_ids 只能包含非空字符串"], involved_indices
    if len(shot_ids) > MAX_CUTS_PER_GROUP:
        reasons.append(f"Cut 数量超过 {MAX_CUTS_PER_GROUP}")

    resolved_indices: list[int] = []
    for shot_id in shot_ids:
        candidates = positions.get(shot_id, ())
        if len(candidates) != 1:
            reasons.append(f"镜号 {shot_id} 不存在或不唯一")
            continue
        resolved_indices.append(candidates[0])
        involved_indices.add(candidates[0])

    if len(resolved_indices) == len(shot_ids):
        expected = list(
            range(resolved_indices[0], resolved_indices[0] + len(resolved_indices))
        )
        if resolved_indices != expected:
            reasons.append("源镜必须相邻且保持 shots[] 顺序")
        if involved_indices & accepted_indices:
            reasons.append("与先前已接受分组重复覆盖")

    grouping_reason = _clean_text(raw_group.get("grouping_reason"))
    if not grouping_reason:
        reasons.append("缺少具体 grouping_reason")
    compatibility = raw_group.get("compatibility")
    if not isinstance(compatibility, dict) or any(
        compatibility.get(key) is not True for key in COMPATIBILITY_KEYS
    ):
        reasons.append("五个语义兼容维度必须全部显式为 true")

    durations: list[Decimal] = []
    for index in resolved_indices:
        try:
            duration = _duration_decimal(shots[index].get("duration_seconds"))
        except InvalidOperation:
            duration = None
        if duration is None:
            reasons.append(
                f"{shots[index]['source_shot_id']} 缺少合法 duration_seconds"
            )
        else:
            durations.append(duration)
            if duration > STANDALONE_WHEN_DURATION_GT_SECONDS:
                reasons.append(
                    f"{shots[index]['source_shot_id']} 时长 > 10 秒，当前策略要求单镜"
                )

    capabilities = profile.get("capabilities", {})
    if capabilities.get("supports_multi_cut") is not True:
        reasons.append("当前 Model Profile 不支持多 Cut")
    if len(durations) == len(resolved_indices) == len(shot_ids):
        total_duration = sum(durations, Decimal("0"))
        try:
            model_limit = _duration_decimal(
                capabilities.get("max_clip_duration_seconds")
            )
        except InvalidOperation:
            model_limit = None
        if total_duration > GROUPING_MAX_DURATION_SECONDS:
            reasons.append("分组总时长超过 15 秒")
        if model_limit is not None and total_duration > model_limit:
            reasons.append("分组总时长超过当前模型能力上限")
    else:
        total_duration = None

    if reasons:
        return None, reasons, involved_indices
    return (
        {
            "source_shot_ids": list(shot_ids),
            "indices": resolved_indices,
            "grouping_reason": grouping_reason,
            "compatibility": {
                key: True for key in COMPATIBILITY_KEYS
            },
            "total_duration": total_duration,
            "decision_index": group_index,
        },
        reasons,
        involved_indices,
    )


def _plan_groups(
    shots: Sequence[Mapping[str, Any]],
    decisions: Any,
    profile: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    raw_groups = decisions.get("groups", []) if isinstance(decisions, dict) else []
    if raw_groups is None:
        raw_groups = []
    if not isinstance(raw_groups, list):
        issues.append(
            _issue(
                "GROUP_DECISION_INVALID",
                "ERROR",
                "decision",
                "groups",
                "groups 必须是数组；所有源镜安全降为单镜。",
                ("requested_grouping",),
            )
        )
        raw_groups = []

    positions = _shot_id_positions(shots)
    accepted_indices: set[int] = set()
    accepted_by_start: dict[int, dict[str, Any]] = {}
    invalid_fallback_indices: set[int] = set()
    for group_index, raw_group in enumerate(raw_groups):
        accepted, reasons, involved = _validate_group_decision(
            raw_group,
            group_index,
            shots,
            positions,
            accepted_indices,
            profile,
        )
        if accepted is None:
            invalid_fallback_indices.update(involved)
            issues.append(
                _issue(
                    "GROUP_DECISION_INVALID",
                    "ERROR",
                    "group",
                    f"groups[{group_index}]",
                    "；".join(reasons) or "分组决策无效",
                    ("requested_grouping",),
                )
            )
            continue
        group_indices = set(accepted["indices"])
        accepted_indices.update(group_indices)
        accepted_by_start[accepted["indices"][0]] = accepted

    planned: list[dict[str, Any]] = []
    index = 0
    while index < len(shots):
        if index in accepted_by_start:
            group = accepted_by_start[index]
            planned.append(
                {
                    "shots": [shots[item] for item in group["indices"]],
                    "grouping_reason": group["grouping_reason"],
                    "semantic_compatibility": group["compatibility"],
                    "standalone_reason": None,
                }
            )
            index += len(group["indices"])
            continue

        shot = shots[index]
        try:
            duration = _duration_decimal(shot.get("duration_seconds"))
        except InvalidOperation:
            duration = None
        model_limit = _duration_decimal(
            profile["capabilities"]["max_clip_duration_seconds"]
        )
        if duration is None:
            standalone_reason = "duration_missing_or_invalid"
        elif duration > model_limit:
            standalone_reason = "model_duration_exceeded"
        elif duration > STANDALONE_WHEN_DURATION_GT_SECONDS:
            standalone_reason = "source_duration_gt_10_seconds"
        elif index in invalid_fallback_indices:
            standalone_reason = "invalid_group_fallback"
        else:
            standalone_reason = "no_compatible_group_selected"
        planned.append(
            {
                "shots": [shot],
                "grouping_reason": None,
                "semantic_compatibility": None,
                "standalone_reason": standalone_reason,
            }
        )
        index += 1
    return planned, issues


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
    camera_marker = action.find("摄影机位于")
    if camera_marker >= 0:
        environment = action[:camera_marker].strip(" \n；。")
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
        and shot_id in item.get("applies_to_shot_ids", [])
    ]


def _reference_instruction(item: Mapping[str, Any]) -> str:
    tag = str(item["tag"])
    role = str(item["role"])
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
    if position:
        camera_text = f"摄影机位于{position}"
        if camera_logic:
            camera_text += f"，{camera_logic}"
        _append_unique(parts, camera_text)
    elif camera_logic:
        _append_unique(parts, camera_logic)

    _, rendered_action = _split_environment_and_action(shot)

    if mode == "t2v":
        _append_unique(parts, rendered_action)
        if not rendered_action:
            _append_items(parts, shot.get("blocking", []), "")
        _append_items(parts, shot.get("visible_behavior", []), "")
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
            parts.append("从已接受素材的观测结束状态继续")
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


def _compile_prompt(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
    generation: Mapping[str, Any],
) -> str:
    total_duration = (
        timeline[-1].get("end_seconds") if timeline else None
    )
    total_line = (
        f"总时长：{_seconds_text(total_duration)}S"
        if total_duration is not None
        else "总时长：来源未提供"
    )
    adapter = profile["prompt_adapter_id"]
    lines = [total_line]
    scene_line = _unit_scene_line(shots)
    if scene_line:
        lines.append(scene_line)
    for shot, cut in zip(shots, timeline):
        if cut.get("start_seconds") is None or cut.get("end_seconds") is None:
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
        )
        if adapter == "explicit-cut-zh-v1":
            lines.append("")
            lines.append(heading)
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


def _prompt_metadata_leaks(
    prompt_text: str, profile: Mapping[str, Any]
) -> list[str]:
    leaks: list[str] = []
    lower_prompt = prompt_text.casefold()
    for forbidden in (
        _clean_text(profile.get("profile_id")),
        _clean_text(profile.get("model_name")),
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
    return leaks


def _cut_prompt_block(prompt_text: str, cut_label: str) -> str:
    marker = f"{cut_label} :"
    start = prompt_text.find(marker)
    if start < 0:
        return ""
    next_positions = [
        prompt_text.find(f"\n{label} :", start + len(marker))
        for label in CUT_LABELS
    ]
    next_positions = [position for position in next_positions if position >= 0]
    end = min(next_positions) if next_positions else len(prompt_text)
    return prompt_text[start:end]


def _cut_source_coverage(
    shot: Mapping[str, Any],
    block: str,
    generation: Mapping[str, Any],
) -> tuple[bool, bool]:
    composition, _, _ = _camera_prompt_fields(shot.get("camera", {}))
    expected_content = _shot_prompt_content(
        shot, [], generation
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
        actual_tags = set(_reference_tags(block, profile))
        if actual_tags != expected_tags:
            reference_tags_exact = False
        visual_covered, cut_continuity_covered = _cut_source_coverage(
            shot, block, generation
        )
        source_visual_action_covered &= visual_covered
        continuity_covered &= cut_continuity_covered
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
    timed_timeline = all(cut["duration_seconds"] is not None for cut in timeline)
    has_error = (
        bool(diagnostic_codes)
        or not dialogue_exact
        or not metadata_absent
        or not reference_tags_exact
        or not downstream_anti_slop_absent
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
        },
        "semantic_limitations": [
            "空间、时间、现实层、动作链与叙事意图兼容性依赖模型审阅。",
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
    timeline, total_duration = _build_timeline(shots, emotion_map)
    prompt_text = _compile_prompt(shots, timeline, profile, generation)
    unit_codes: list[str] = []
    model_limit = _profile_limit(profile)

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
                generation, str(shot["source_shot_id"])
            )
        }
        actual_tags = set(_reference_tags(block, profile))
        if actual_tags != expected_tags:
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
            shot, block, generation
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
        "timeline": timeline,
        "prompt_text": prompt_text,
        "prompt_validation": _unit_prompt_validation(
            shots,
            timeline,
            prompt_text,
            profile,
            generation,
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


def build_prompt_plan(
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
    issues: list[dict[str, Any]] = list(normalization_issues) + profile_issues
    prompt_units: list[dict[str, Any]] = []
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
            normalized["shots"], decisions, profile
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
    plan["diagnostics"] = issues
    plan["validation"] = _validation_object(normalized, prompt_units, issues)
    plan["content_hash"] = prompt_plan_content_hash(plan)
    return plan


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
                "输出合同必须是 prompt-plan/1.0.0。",
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
    if generation_global_blocked and prompt_units:
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
    flattened_ids: list[str] = []
    source_cursor = 0
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
        flattened_ids.extend(str(item) for item in shot_ids)
        expected_shots = source_shots[
            source_cursor : source_cursor + len(shot_ids)
        ]
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
        source_cursor += len(shot_ids)

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
            if str(shot_id) in generation_invalid_shot_ids
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
            if len(shot_ids) > MAX_CUTS_PER_GROUP:
                issues.append(
                    _issue(
                        "GROUP_DURATION_INVALID",
                        "ERROR",
                        "unit",
                        unit_path,
                        "多镜单元 Cut 数量超过 v1 策略上限。",
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

        durations: list[Decimal] = []
        for shot in expected_shots:
            try:
                duration = _duration_decimal(shot.get("duration_seconds"))
            except InvalidOperation:
                duration = None
            if duration is not None:
                durations.append(duration)
            if is_multi and (
                duration is None
                or duration > STANDALONE_WHEN_DURATION_GT_SECONDS
            ):
                issues.append(
                    _issue(
                        "GROUP_DURATION_INVALID",
                        "ERROR",
                        "unit",
                        unit_path,
                        "多镜单元包含缺时长或 >10 秒的来源镜头。",
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
            if expected_total > GROUPING_MAX_DURATION_SECONDS:
                issues.append(
                    _issue(
                        "GROUP_DURATION_INVALID",
                        "ERROR",
                        "unit",
                        unit_path,
                        "多镜单元总时长超过 15 秒。",
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
                    _cut_source_coverage(shot, block, generation)
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
                        generation, str(shot["source_shot_id"])
                    )
                }
                actual_tags = set(_reference_tags(block, profile))
                if actual_tags != expected_tags:
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
    if (
        not normalized.get("source_global_blocked", False)
        and not generation_global_blocked
        and flattened_ids != expected_flattened
    ):
        issues.append(
            _issue(
                "SOURCE_SHOT_COVERAGE_INVALID",
                "ERROR",
                "plan",
                "prompt_units",
                "来源镜头未按序恰好覆盖一次。",
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


def prompt_table_xlsx_bytes(rows: Sequence[Sequence[str]]) -> bytes:
    worksheet_rows: list[str] = []
    all_rows = [list(PROMPT_TABLE_COLUMNS)] + [
        [str(cell) for cell in row] for row in rows
    ]
    for row_index, row in enumerate(all_rows, start=1):
        cells: list[str] = []
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
                cells.append(f'<c r="{reference}" s="2"><v>{value}</v></c>')
            else:
                style_index = 1 if row_index == 1 else (3 if column_index == 4 else 0)
                cells.append(
                    _xlsx_inline_cell(reference, value, style_index)
                )
        worksheet_rows.append(
            f'<row r="{row_index}">{"".join(cells)}</row>'
        )

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
        '<col min="4" max="4" width="100" customWidth="1"/>'
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
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="4">'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
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


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _formal_validation_report(
    plan: Mapping[str, Any],
    plan_payload: bytes,
    markdown_payload: bytes,
    xlsx_payload: bytes,
    rows: Sequence[Sequence[str]],
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
    plan_payload = stable_json_bytes(plan)
    markdown_payload = prompt_table_markdown_bytes(rows)
    xlsx_payload = prompt_table_xlsx_bytes(rows)
    report = _formal_validation_report(
        plan, plan_payload, markdown_payload, xlsx_payload, rows
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
        xlsx_cells_ok = (
            xlsx_rows == rows
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
        "generation": {
            "mode": "",
            "mode_source": "unresolved",
            "available_reference_tags": [],
            "reference_role_map": [],
            "edit_scope": [],
            "edit_deltas": [],
            "extend_context": {},
            "runtime_decisions_hash": None,
            "global_blocked": True,
            "invalid_shot_ids": [],
        },
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
        description="Build or validate prompt-plan/1.0.0 deliveries."
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
