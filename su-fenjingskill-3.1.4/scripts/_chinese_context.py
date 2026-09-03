"""Internal deterministic Chinese-context helpers for su-fenjingskill 3.1.4."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = (
    "Imported by storyboard_delivery.py for deterministic Chinese-language checks."
)

CJK_RE = re.compile(r"[\u3400-\u9fff]")
CJK_STRONG_PUNCTUATION = ("。", "！", "？", "!", "?", "…", "—")
CJK_SOFT_PUNCTUATION = ("，", "、", "；", "：", ",", ";", ":")
PACE_STANDARD_PATH = Path(__file__).resolve().parents[1] / "references" / "dialogue-pace-standard.json"
GENERIC_PACE_OVERRIDE_REASONS = {"节奏需要", "剧情需要", "人物很急", "人物很慢", "更有电影感", "类型需要"}

# Keep this list synchronized with all internal enum vocabularies that may be
# accidentally copied into the Chinese Agent-facing execution record.
INTERNAL_ENUM_TERMS = (
    "relationship_accumulation",
    "information_suspense",
    "offscreen_threat",
    "comedy_setup_payoff",
    "action_causality",
    "ensemble_power",
    "ritual_repetition",
    "montage_music_concept",
    "subjective_memory",
    "spectacle_discovery",
    "hold",
    "blocking_recompose",
    "camera_reframe",
    "focus_shift",
    "light_shift",
    "sound_shift",
    "reaction_cut",
    "action_cut",
    "gaze_cut",
    "match_cut",
    "jump_cut",
    "ellipsis",
    "intercut",
    "montage",
    "sound_lead",
    "sound_lag",
    "sound_bridge",
    "sound_break",
    "dissolve",
    "fade",
    "scene_transition",
    "scene_end",
    "horizontal",
    "vertical",
    "depth",
    "layered",
    "centered",
    "diagonal",
    "sequential",
    "parallel",
)

ALLOWED_REMARK_MARKERS = (
    "待确认",
    "待定",
    "暂定",
    "未锁定",
    "假设",
    "有意",
    "连续性违例",
    "越轴",
)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def contains_cjk(value: Any) -> bool:
    return bool(CJK_RE.search(normalize_text(value)))


def chinese_dialogue_minimum_seconds(value: Any) -> float:
    """Return a deliberately permissive physical floor, not an artistic target."""
    text = normalize_text(value)
    han_count = len(CJK_RE.findall(text))
    strong_pause = sum(text.count(mark) for mark in CJK_STRONG_PUNCTUATION)
    soft_pause = sum(text.count(mark) for mark in CJK_SOFT_PUNCTUATION)
    return han_count / 8.0 + strong_pause * 0.12 + soft_pause * 0.06


@lru_cache(maxsize=1)
def load_dialogue_pace_standard() -> dict[str, Any]:
    value = json.loads(PACE_STANDARD_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("standard_id") != "su-dialogue-pace/1.0":
        raise ValueError("dialogue pace standard identity is invalid")
    return value


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _same_number(left: Any, right: Any, tolerance: float = 0.001) -> bool:
    left_number = _number(left)
    right_number = _number(right)
    return left_number is not None and right_number is not None and abs(left_number - right_number) <= tolerance


def dialogue_pace_issues(rhythm_profile: Any, pace: Any) -> list[tuple[str, str, str]]:
    """Return deterministic house-standard issues as code, relative path and message."""
    issues: list[tuple[str, str, str]] = []
    pace = pace if isinstance(pace, Mapping) else {}
    standard = load_dialogue_pace_standard()
    if pace.get("standard_id") != standard["standard_id"]:
        issues.append(("DIALOGUE_PACE_STANDARD_INVALID", "standard_id", "必须使用 su-dialogue-pace/1.0。"))
    if pace.get("rate_basis") != standard["rate_basis"]:
        issues.append(("DIALOGUE_PACE_BASIS_INVALID", "rate_basis", "基础字速必须排除停顿，避免与标点停顿重复计算。"))
    fields = ("range_min_cps", "range_max_cps", "default_cps", "selected_cps", "strong_pause_seconds", "soft_pause_seconds")
    numbers = {field: _number(pace.get(field)) for field in fields}
    if any(value is None or value < 0 for value in numbers.values()):
        issues.append(("DIALOGUE_PACE_NUMERIC_INVALID", "", "语速区间、选值和停顿必须是非负数。"))
        return issues
    range_min = numbers["range_min_cps"] or 0.0
    range_max = numbers["range_max_cps"] or 0.0
    default = numbers["default_cps"] or 0.0
    selected = numbers["selected_cps"] or 0.0
    if not (0 < range_min <= default <= range_max and range_min <= selected <= range_max):
        issues.append(("DIALOGUE_PACE_RANGE_INVALID", "", "必须满足 0 < min ≤ default/selected ≤ max。"))

    profiles = standard.get("profiles") if isinstance(standard.get("profiles"), Mapping) else {}
    expected = profiles.get(rhythm_profile)
    if isinstance(expected, Mapping):
        if pace.get("pace_profile") != expected.get("pace_profile"):
            issues.append(("DIALOGUE_PACE_PROFILE_LABEL_MISMATCH", "pace_profile", f"{rhythm_profile} 必须使用 {expected.get('pace_profile')} pace profile。"))
        for field in ("range_min_cps", "range_max_cps", "default_cps"):
            if not _same_number(pace.get(field), expected.get(field)):
                issues.append(("DIALOGUE_PACE_PROFILE_RANGE_MISMATCH", field, f"{rhythm_profile} 的 {field} 必须等于内部标准 {expected.get(field)}。"))
        for field, range_field in (
            ("soft_pause_seconds", "soft_pause_range_seconds"),
            ("strong_pause_seconds", "strong_pause_range_seconds"),
        ):
            allowed = expected.get(range_field)
            value = numbers[field]
            if not isinstance(allowed, list) or len(allowed) != 2 or value is None or not float(allowed[0]) <= value <= float(allowed[1]):
                issues.append(("DIALOGUE_PAUSE_PROFILE_RANGE_MISMATCH", field, f"{field} 必须位于 {allowed}。"))
    elif rhythm_profile == "custom":
        if pace.get("pace_profile") != "custom":
            issues.append(("DIALOGUE_PACE_PROFILE_LABEL_MISMATCH", "pace_profile", "custom rhythm 必须明确使用 custom pace profile。"))
    else:
        issues.append(("DIALOGUE_PACE_PROFILE_UNRESOLVED", "", "非 custom 项目必须使用四种内部标准之一。"))

    overrides = pace.get("overrides")
    if not isinstance(overrides, list):
        issues.append(("DIALOGUE_PACE_OVERRIDES_INVALID", "overrides", "overrides 必须是数组。"))
        return issues
    seen: set[str] = set()
    for index, override in enumerate(overrides):
        path = f"overrides[{index}]"
        if not isinstance(override, Mapping):
            issues.append(("DIALOGUE_PACE_OVERRIDE_INVALID", path, "override 必须是对象。"))
            continue
        override_id = normalize_text(override.get("override_id"))
        if not re.fullmatch(r"PO[0-9]{3,}", override_id) or override_id in seen:
            issues.append(("DIALOGUE_PACE_OVERRIDE_ID_INVALID", path + ".override_id", "override ID 为空、重复或格式无效。"))
        seen.add(override_id)
        if override.get("scope") not in {"scene", "character", "dialogue"} or not normalize_text(override.get("scope_ref")):
            issues.append(("DIALOGUE_PACE_OVERRIDE_SCOPE_INVALID", path, "override 必须明确 scene、character 或 dialogue scope。"))
        for field in ("selected_cps", "strong_pause_seconds", "soft_pause_seconds"):
            value = _number(override.get(field))
            if value is None or value < 0 or (field == "selected_cps" and value == 0):
                issues.append(("DIALOGUE_PACE_OVERRIDE_NUMERIC_INVALID", path + "." + field, "override 数值无效。"))
        reason = normalize_text(override.get("reason"))
        if len("".join(reason.split())) < 8 or reason in GENERIC_PACE_OVERRIDE_REASONS:
            issues.append(("DIALOGUE_PACE_OVERRIDE_REASON_VAGUE", path + ".reason", "越过基础区间必须说明可表演、可听见的具体原因。"))
    return issues


def resolve_dialogue_pace(pace: Any, pace_ref: Any) -> dict[str, Any] | None:
    pace = pace if isinstance(pace, Mapping) else {}
    if pace_ref == "BASE":
        return {
            "pace_ref": "BASE",
            "scope": "project",
            "scope_ref": "BASE",
            "selected_cps": pace.get("selected_cps"),
            "strong_pause_seconds": pace.get("strong_pause_seconds"),
            "soft_pause_seconds": pace.get("soft_pause_seconds"),
        }
    for override in pace.get("overrides", []) if isinstance(pace.get("overrides"), list) else []:
        if isinstance(override, Mapping) and override.get("override_id") == pace_ref:
            return {
                "pace_ref": override.get("override_id"),
                "scope": override.get("scope"),
                "scope_ref": override.get("scope_ref"),
                "selected_cps": override.get("selected_cps"),
                "strong_pause_seconds": override.get("strong_pause_seconds"),
                "soft_pause_seconds": override.get("soft_pause_seconds"),
            }
    return None


def chinese_dialogue_estimated_seconds(value: Any, pace: Any) -> float:
    """Calculate a confirmed-project dialogue estimate; no global artistic rate is assumed."""
    text = normalize_text(value)
    pace = pace if isinstance(pace, dict) else {}
    try:
        characters_per_second = float(pace.get("selected_cps"))
        strong_pause_seconds = float(pace.get("strong_pause_seconds"))
        soft_pause_seconds = float(pace.get("soft_pause_seconds"))
    except (TypeError, ValueError):
        return 0.0
    if characters_per_second <= 0 or strong_pause_seconds < 0 or soft_pause_seconds < 0:
        return 0.0
    han_count = len(CJK_RE.findall(text))
    strong_pause = sum(text.count(mark) for mark in CJK_STRONG_PUNCTUATION)
    soft_pause = sum(text.count(mark) for mark in CJK_SOFT_PUNCTUATION)
    return han_count / characters_per_second + strong_pause * strong_pause_seconds + soft_pause * soft_pause_seconds


def dialogue_label_issue(text: Any, speaker: Any) -> str:
    normalized_text = normalize_text(text)
    normalized_speaker = normalize_text(speaker)
    if not contains_cjk(normalized_text) or not normalized_speaker:
        return ""
    speaker_label = re.compile(
        rf"^\s*{re.escape(normalized_speaker)}(?:（[^）]*）)?[：:]"
    )
    if speaker_label.search(normalized_text):
        return "speaker-label"
    if re.match(r"^\s*（[^）]+）", normalized_text):
        return "performance-direction"
    return ""


def leaked_internal_enums(execution_text: Any, locked_text: Any) -> list[str]:
    execution = normalize_text(execution_text)
    source = normalize_text(locked_text)
    return [
        term
        for term in INTERNAL_ENUM_TERMS
        if term in execution and term not in source
    ]


def remarks_policy(notes: Any) -> str:
    """Classify remarks as empty, explicitly scoped, or requiring human review.

    Remarks are only a human-review surface for genuine pending items or an
    intentional continuity exception. Other non-empty notes remain review
    warnings and are never routed into a separate subsystem.
    """
    text = normalize_text(notes)
    if not text:
        return "empty"
    if any(marker in text for marker in ALLOWED_REMARK_MARKERS):
        return "allowed"
    return "review"
