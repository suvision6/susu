"""Internal deterministic Chinese-context helpers for su-fenjingskill 3.1.1."""

from __future__ import annotations

import re
from typing import Any


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = (
    "Imported by storyboard_delivery.py for deterministic Chinese-language checks."
)

CJK_RE = re.compile(r"[\u3400-\u9fff]")
CJK_STRONG_PUNCTUATION = ("。", "！", "？", "!", "?", "…", "—")
CJK_SOFT_PUNCTUATION = ("，", "、", "；", "：", ",", ";", ":")
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
    "sound_bridge",
    "reaction_cut",
    "action_cut",
)
PRODUCTION_RISK_REMARK_MARKERS = (
    "制作风险",
    "生产风险",
    "拍摄风险",
    "安全风险",
    "反射",
    "收音",
    "设备",
    "预演",
    "体力",
    "衣摆",
    "亲密动作",
    "特效",
    "场地联调",
    "机位空间",
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


def production_risk_issues(value: Any, path: str) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        return [
            {
                "code": "PRODUCTION_RISKS_NOT_ARRAY",
                "path": path,
                "message": "production_risks 必须是数组。",
            }
        ]
    issues: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not normalize_text(item):
            issues.append(
                {
                    "code": "PRODUCTION_RISK_EMPTY",
                    "path": f"{path}[{index}]",
                    "message": "制作风险必须是非空文字。",
                }
            )
    return issues


def remarks_policy(notes: Any) -> str:
    text = normalize_text(notes)
    if not text:
        return "empty"
    allowed = any(marker in text for marker in ALLOWED_REMARK_MARKERS)
    if not allowed and any(
        marker in text for marker in PRODUCTION_RISK_REMARK_MARKERS
    ):
        return "production-risk"
    if not allowed:
        return "review"
    return "allowed"
