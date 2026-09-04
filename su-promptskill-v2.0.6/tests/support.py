#!/usr/bin/env python3
"""Regression tests for su-promptskill prompt-plan/2.0.6 delivery."""

from __future__ import annotations

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Imported or executed only for deterministic su-promptskill regression tests."

import copy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
SCRIPT_DIR = SCRIPTS_DIR
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import prompt_delivery as delivery

CURRENT_DIRECTOR_FIXTURE = (
    SKILL_ROOT
    / "tests"
    / "fixtures"
    / "fenjing-3.1.1-kitchen-farewell-shot-data.json"
)
CHINESE_SEMANTICS_DIRECTOR_FIXTURE = (
    SKILL_ROOT
    / "tests"
    / "fixtures"
    / "fenjing-3.1.6-chinese-semantics.json"
)

def make_shot(
    shot_id: str,
    duration: int | float | None,
    *,
    rendered: str | None = None,
    visible_behavior: list[str] | None = None,
    dialogue: list[object] | None = None,
) -> dict[str, object]:
    return {
        "shot_id": shot_id,
        "duration_seconds": duration,
        "camera": {
            "shot_size": "近景",
            "angle": "平视",
            "composition": f"{shot_id} 主体居中",
            "movement": "固定",
        },
        "blocking": [{"subject": "人物", "action": f"完成 {shot_id} 动作"}],
        "performance": {
            "emotion_intent": "克制",
            "visible_behavior": (
                ["人物缓慢抬眼"]
                if visible_behavior is None
                else copy.deepcopy(visible_behavior)
            ),
        },
        "dialogue": [] if dialogue is None else copy.deepcopy(dialogue),
        "continuity": {"reality_layer": "现实"},
        "rendered_shot_description": (
            f"人物在房间内完成 {shot_id} 动作。"
            if rendered is None
            else rendered
        ),
    }


def make_source(
    durations: list[int | float | None],
    *,
    source_mode: str = "standalone_storyboard",
) -> dict[str, object]:
    return {
        "source_mode": source_mode,
        "shots": [
            make_shot(f"SH{index:03d}", duration)
            for index, duration in enumerate(durations, start=1)
        ],
    }


def make_formal_source(contract_version: str) -> dict[str, object]:
    source = {
        "contract_name": "shot-data",
        "contract_version": contract_version,
        "source_skill": "su-fenjingskill",
        "source_skill_version": contract_version,
        "project_id": f"FORMAL-{contract_version}",
        "content_hash": "",
        "scenes": [],
        "shots": [make_shot("SH001", 4)],
    }
    source["content_hash"] = delivery.source_observed_hash(source)
    return source


def rehash_source(source: dict[str, object]) -> dict[str, object]:
    source["content_hash"] = delivery.source_observed_hash(source)
    return source


def copy_decisions(
    decisions: dict[str, object] | None,
) -> dict[str, object]:
    return copy.deepcopy(decisions) if decisions is not None else {}


def build_plan(
    source: dict[str, object],
    decisions: dict[str, object] | None = None,
    model_profile: dict[str, object] | None = None,
    delivery_slug: str | None = None,
) -> dict[str, object]:
    return delivery.build_prompt_plan(
        source,
        decisions=copy_decisions(decisions),
        model_profile=model_profile,
        delivery_slug=delivery_slug,
    )


def build_package(
    source: dict[str, object],
    decisions: dict[str, object] | None = None,
    model_profile: dict[str, object] | None = None,
    delivery_slug: str | None = None,
) -> tuple[dict[str, object], dict[str, bytes]]:
    return delivery.build_delivery_package(
        source,
        decisions=copy_decisions(decisions),
        model_profile=model_profile,
        delivery_slug=delivery_slug,
    )


def grouping_decisions(
    source: dict[str, object],
    joined_groups: list[list[str]] | None = None,
) -> dict[str, object]:
    shots = source.get("shots", [])
    shots = shots if isinstance(shots, list) else []
    joined_edges: set[tuple[str, str]] = set()
    for group in joined_groups or []:
        joined_edges.update(zip(group, group[1:]))
    compatibility_keys = delivery.BOUNDARY_COMPATIBILITY_KEYS
    boundaries: list[dict[str, object]] = []
    for left, right in zip(shots, shots[1:]):
        assert isinstance(left, dict) and isinstance(right, dict)
        left_id = str(left["shot_id"])
        right_id = str(right["shot_id"])
        joined = (left_id, right_id) in joined_edges
        compatibility = {key: True for key in compatibility_keys}
        def raw_has_prompt_content(shot: dict[str, object]) -> bool:
            return bool(
                shot.get("rendered_shot_description")
                or shot.get("blocking")
                or shot.get("dialogue")
                or shot.get("end_state")
                or any(
                    value
                    for value in (
                        shot.get("camera") or {}
                    ).values()
                )
            )
        source_unavailable = not raw_has_prompt_content(left) or not raw_has_prompt_content(right)
        boundaries.append(
            {
                "left_source_shot_id": left_id,
                "right_source_shot_id": right_id,
                "compatibility": compatibility,
                "classification": (
                    "hard_split"
                    if source_unavailable
                    else ("prefer_join" if joined else "prefer_split")
                ),
                "semantic_evidence": [
                    "source_unavailable"
                    if source_unavailable
                    else ("action_continuation" if joined else "narrative_phase_change")
                ],
                "reason": (
                    "同一时空内动作和观看关系连续。"
                    if joined
                    else "测试明确保持边界分离。"
                ),
            }
        )
    return {
        "grouping_review": {
            "contract": delivery.GROUPING_REVIEW_CONTRACT,
            "source_observed_hash": delivery.source_observed_hash(source),
            "partition_policy": delivery.GROUPING_PARTITION_POLICY,
            "boundaries": boundaries,
        }
    }


def merge_grouping_decisions(
    source: dict[str, object],
    decisions: dict[str, object] | None = None,
    joined_groups: list[list[str]] | None = None,
) -> dict[str, object]:
    result = copy.deepcopy(decisions) if decisions is not None else {}
    result.update(grouping_decisions(source, joined_groups))
    return result


def generation_decision(
    mode: str,
    tags: list[str],
    roles: list[dict[str, object]],
    **extra: object,
) -> dict[str, object]:
    generation: dict[str, object] = {
        "mode": mode,
        "available_reference_tags": tags,
        "reference_role_map": roles,
    }
    generation.update(extra)
    return {"generation": generation}


def reference_role(
    tag: str,
    media_type: str,
    role: str,
    shot_ids: list[str],
    preserve: list[str] | None = None,
) -> dict[str, object]:
    return {
        "tag": tag,
        "media_type": media_type,
        "role": role,
        "applies_to_shot_ids": shot_ids,
        "preserve": [] if preserve is None else preserve,
    }


def issue_codes(plan: dict[str, object]) -> set[str]:
    return {
        str(issue.get("code"))
        for issue in plan.get("diagnostics", [])
        if isinstance(issue, dict)
    }


def build_legacy_plan(
    source: object,
    decisions: object = None,
    model_profile: object = None,
    delivery_slug: str | None = None,
) -> dict[str, object]:
    """Run v1 regression cases against the explicit Seedance 2.0 profile."""
    profile = (
        delivery.resolve_model_profile("seedance-2.0-default")
        if model_profile is None
        else model_profile
    )
    if isinstance(source, dict) and len(source.get("shots", [])) > 1:
        if not isinstance(decisions, dict) or "grouping_review" not in decisions:
            decisions = merge_grouping_decisions(
                source,
                decisions if isinstance(decisions, dict) else None,
            )
    return build_plan(
        source,
        decisions=decisions,
        model_profile=profile,
        delivery_slug=delivery_slug,
    )

class BasePromptDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="su-promptskill-test-"
        )
        self.output_dir = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()
