#!/usr/bin/env python3
"""Regression tests for su-promptskill prompt-plan/2.0.4 delivery."""

from __future__ import annotations

import copy
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

import prompt_delivery as delivery


SCRIPT_DIR = Path(__file__).resolve().parent


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


class PromptDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="su-promptskill-test-"
        )
        self.output_dir = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_multi_shot_requires_complete_grouping_review(self) -> None:
        source = make_source([4, 4])
        with self.assertRaisesRegex(
            delivery.GroupingReviewError, "GROUPING_REVIEW_REQUIRED"
        ):
            build_plan(source)
        with self.assertRaisesRegex(
            delivery.GroupingReviewError,
            "GROUPING_REVIEW_LEGACY_UNSUPPORTED",
        ):
            build_plan(source, {"groups": []})

    def test_grouping_review_rejects_stale_incomplete_and_wrong_order(
        self,
    ) -> None:
        source = make_source([4, 4, 4])
        valid = grouping_decisions(source)
        stale = copy.deepcopy(valid)
        stale["grouping_review"]["source_observed_hash"] = "0" * 64
        incomplete = copy.deepcopy(valid)
        incomplete["grouping_review"]["boundaries"].pop()
        wrong_order = copy.deepcopy(valid)
        wrong_order["grouping_review"]["boundaries"][0][
            "right_source_shot_id"
        ] = "SH003"
        for decisions, code in (
            (stale, "GROUPING_REVIEW_SOURCE_MISMATCH"),
            (incomplete, "GROUPING_REVIEW_INCOMPLETE"),
            (wrong_order, "GROUPING_REVIEW_ORDER_INVALID"),
        ):
            with self.subTest(code=code):
                with self.assertRaisesRegex(
                    delivery.GroupingReviewError, code
                ):
                    build_plan(source, decisions)

    def test_grouping_review_uniquely_derives_join_and_split_units(self) -> None:
        source = make_source([4, 4, 4])
        decisions = grouping_decisions(source, [["SH001", "SH002"]])
        plan = build_plan(source, decisions)
        self.assertEqual(
            [unit["source_shot_ids"] for unit in plan["prompt_units"]],
            [["SH001", "SH002"], ["SH003"]],
        )
        self.assertEqual(plan["validation"]["summary"]["grouped_units"], 1)

    def test_grouping_review_recomputes_observable_hard_split_evidence(self) -> None:
        source = make_source([4, 4])
        source["shots"][0]["scene_id"] = "SC001"
        source["shots"][1]["scene_id"] = "SC002"
        decisions = grouping_decisions(source, [["SH001", "SH002"]])
        with self.assertRaisesRegex(
            delivery.GroupingReviewError,
            "GROUPING_REVIEW_HARD_SPLIT_REQUIRED",
        ):
            build_plan(source, decisions)

        boundary = decisions["grouping_review"]["boundaries"][0]
        boundary["classification"] = "hard_split"
        boundary["semantic_evidence"] = ["scene_change"]
        boundary["compatibility"]["scene"] = False
        plan = build_plan(source, decisions)
        self.assertEqual(
            [unit["source_shot_ids"] for unit in plan["prompt_units"]],
            [["SH001"], ["SH002"]],
        )
        self.assertEqual(
            plan["prompt_units"][1]["partition_entry_reason"], "hard_split"
        )

    def test_scene_global_partition_prefers_semantic_break_over_local_greedy_fill(self) -> None:
        source = make_source([12, 12, 6])
        decisions = grouping_decisions(
            source, [["SH001", "SH002", "SH003"]]
        )
        second = decisions["grouping_review"]["boundaries"][1]
        second["classification"] = "prefer_split"
        second["semantic_evidence"] = ["information_density"]
        plan = build_plan(source, decisions)
        self.assertEqual(
            [unit["source_shot_ids"] for unit in plan["prompt_units"]],
            [["SH001", "SH002"], ["SH003"]],
        )
        self.assertEqual(
            plan["prompt_units"][1]["partition_entry_reason"],
            "semantic_preference",
        )

    def test_capacity_split_keeps_semantics_and_records_profile_reason(self) -> None:
        source = make_source([18, 8, 8])
        decisions = grouping_decisions(
            source, [["SH001", "SH002", "SH003"]]
        )
        plan = build_plan(source, decisions)
        self.assertEqual(
            [unit["source_shot_ids"] for unit in plan["prompt_units"]],
            [["SH001", "SH002"], ["SH003"]],
        )
        self.assertEqual(
            plan["prompt_units"][1]["partition_entry_reason"],
            "profile_duration_limit",
        )

    def test_grouping_review_rejects_contradictory_boundary(self) -> None:
        source = make_source([4, 4])
        decisions = grouping_decisions(source)
        boundary = decisions["grouping_review"]["boundaries"][0]
        boundary["classification"] = "prefer_join"
        boundary["compatibility"]["action"] = False
        boundary["semantic_evidence"] = ["action_continuation"]
        with self.assertRaisesRegex(
            delivery.GroupingReviewError, "GROUPING_REVIEW_PREFER_JOIN_INVALID"
        ):
            build_plan(source, decisions)

    def test_explicit_operations_each_require_grouping_review(self) -> None:
        source = make_source([4, 4])
        decisions = {
            "operations": [
                {
                    "operation_id": "OP001",
                    "order": 1,
                    "task": {
                        "primary": "generate",
                        "input_topology": "text-only",
                        "modules": [],
                    },
                }
            ]
        }
        with self.assertRaisesRegex(
            delivery.GroupingReviewError, "GROUPING_REVIEW_REQUIRED"
        ):
            build_plan(source, decisions)

    def test_grouping_failure_cli_writes_no_delivery_files(self) -> None:
        root = Path(self.temporary_directory.name)
        source_path = root / "source.json"
        output_dir = root / "missing-review-output"
        delivery.write_json_atomic(source_path, make_source([4, 4]))
        with contextlib.redirect_stderr(io.StringIO()):
            result = delivery.main(
                [
                    "build",
                    "--input",
                    str(source_path),
                    "--output-dir",
                    str(output_dir),
                ]
            )
        self.assertEqual(result, 2)
        self.assertFalse(output_dir.exists())

    def test_structured_prompt_removes_source_fact_repetition(self) -> None:
        source = make_source([4])
        source["scenes"] = [
            {
                "scene_id": "SC001",
                "scene": "房间·夜·内景",
                "reality_layer": "现实",
            }
        ]
        shot = source["shots"][0]
        shot["scene_id"] = "SC001"
        shot["camera"].update(
            {
                "position": "窗边外缘",
                "logic": "摄影机位于主体上方，由窗边外缘朝向人物",
                "start_frame": "人物抬眼。",
                "end_frame": "人物转身。",
                "movement": "缓慢推进",
                "movement_plan": {
                    "speed": "缓慢",
                    "path": "从窗边外缘沿人物视线推进",
                    "trigger": "人物抬眼。开始发生时",
                    "end_condition": "人物转身。成为清楚落点时停止",
                },
                "spatial_strategy": {
                    "description": "观看从窗边转向人物",
                },
            }
        )
        shot["rendered_shot_description"] = (
            "房间·夜·内景，摄影机从窗边外缘朝向人物。"
            "画面先见人物抬眼。人物抬眼。"
            "摄影机缓慢推进，到人物转身。随后人物转身。"
            "最后保持人物转身。"
        )
        plan = build_plan(source)
        unit = plan["prompt_units"][0]
        prompt = unit["prompt_text"]
        self.assertEqual(prompt.count("房间·夜·内景"), 2)
        self.assertEqual(prompt.count("窗边外缘"), 1)
        self.assertEqual(prompt.count("人物抬眼。"), 1)
        self.assertEqual(prompt.count("人物转身。"), 1)
        self.assertTrue(
            unit["prompt_validation"]["checks"][
                "prompt_redundancy_absent"
            ]
        )
        self.assertNotIn("PROMPT_REDUNDANCY_DETECTED", issue_codes(plan))

    def test_structured_camera_phrasing_uses_clean_state_terms(self) -> None:
        source = make_source([4])
        shot = source["shots"][0]
        shot["camera"].update(
            {
                "position": "桌边外缘",
                "start_frame": "人物保持站立。",
                "end_frame": "人物保持站立。",
                "movement": "固定",
                "movement_plan": {
                    "trigger": "触发动作时",
                    "hold_reason": (
                        "保持桌边外缘的观察位置，直到人物保持站立。，"
                        "让观众主动读取变化。"
                    ),
                },
            }
        )
        prompt = build_plan(source)["prompt_units"][0][
            "prompt_text"
        ]
        self.assertIn("在触发动作时启动", prompt)
        self.assertIn("直到主要状态形成", prompt)
        self.assertNotIn("触发：触发动作时", prompt)
        self.assertNotIn("直到起始状态", prompt)

    def test_validator_strictly_rejects_2_0_1_plan_contract(self) -> None:
        source = make_source([4])
        plan = build_plan(source)
        plan["contract_version"] = "2.0.1"
        plan["content_hash"] = delivery.prompt_plan_content_hash(plan)
        report = delivery.validate_prompt_plan(source, plan)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "OUTPUT_CONTRACT_INVALID",
            {issue["code"] for issue in report["errors"]},
        )

    def test_validator_strictly_rejects_2_0_3_plan_contract(self) -> None:
        source = make_source([4])
        plan = build_plan(source)
        plan["contract_version"] = "2.0.3"
        plan["content_hash"] = delivery.prompt_plan_content_hash(plan)
        report = delivery.validate_prompt_plan(source, plan)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "OUTPUT_CONTRACT_INVALID",
            {issue["code"] for issue in report["errors"]},
        )

    def test_required_grouping_duration_examples(self) -> None:
        examples = (
            ([8, 3, 4], 15, 3),
            ([9, 4], 13, 2),
            ([10, 5], 15, 2),
        )
        for durations, expected_total, expected_cuts in examples:
            with self.subTest(durations=durations):
                source = make_source(durations)
                ids = [
                    str(shot["shot_id"])
                    for shot in source["shots"]
                ]
                plan = build_legacy_plan(
                    source, grouping_decisions(source, [ids])
                )
                self.assertEqual(len(plan["prompt_units"]), 1)
                unit = plan["prompt_units"][0]
                self.assertEqual(
                    unit["total_duration_seconds"], expected_total
                )
                self.assertEqual(len(unit["timeline"]), expected_cuts)
                self.assertNotIn(
                    "GROUP_DURATION_INVALID", issue_codes(plan)
                )

    def test_profile_capacity_replaces_false_single_shot_fifteen_second_gate(self) -> None:
        source = make_source([16, 4])
        legacy_plan = build_legacy_plan(
            source,
            grouping_decisions(source, [["SH001", "SH002"]]),
        )
        self.assertEqual(
            [unit["source_shot_ids"] for unit in legacy_plan["prompt_units"]],
            [["SH001"], ["SH002"]],
        )
        seedance_25_plan = build_plan(
            source,
            grouping_decisions(source, [["SH001", "SH002"]]),
        )
        self.assertEqual(
            [unit["source_shot_ids"] for unit in seedance_25_plan["prompt_units"]],
            [["SH001", "SH002"]],
        )
        self.assertEqual(seedance_25_plan["prompt_units"][0]["total_duration_seconds"], 20)

        fifteen_source = make_source([15, 4])
        fifteen_plan = build_plan(
            fifteen_source,
            grouping_decisions(
                fifteen_source, [["SH001", "SH002"]]
            ),
        )
        self.assertEqual(
            fifteen_plan["prompt_units"][0]["total_duration_seconds"], 19
        )

    def test_short_tail_is_valid_and_never_uses_grouping_blocked(self) -> None:
        plan = build_legacy_plan(make_source([3]))
        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(len(plan["prompt_units"]), 1)
        self.assertEqual(
            plan["prompt_units"][0]["total_duration_seconds"], 3
        )
        self.assertNotIn("PROMPT_GROUPING_BLOCKED", issue_codes(plan))

    def test_group_total_over_fifteen_is_partitioned_for_seedance_20(self) -> None:
        for durations in ([8, 8], [15, 3], [12, 6]):
            with self.subTest(durations=durations):
                source = make_source(durations)
                plan = build_legacy_plan(
                    source,
                    grouping_decisions(source, [["SH001", "SH002"]]),
                )
                self.assertEqual(len(plan["prompt_units"]), 2)

    def test_same_space_dialogue_coverage_can_group_across_view_changes(self) -> None:
        source = make_source([3, 3, 3, 3])
        sizes = ("近景", "中景", "特写", "全景")
        for shot, size in zip(source["shots"], sizes):
            shot["camera"]["shot_size"] = size
            shot["dialogue"] = [
                {"speaker": shot["shot_id"], "text": f"{shot['shot_id']}回应"}
            ]
        plan = build_legacy_plan(
            source,
            grouping_decisions(
                source, [["SH001", "SH002", "SH003", "SH004"]]
            ),
        )
        self.assertEqual(len(plan["prompt_units"]), 1)
        self.assertEqual(len(plan["prompt_units"][0]["timeline"]), 4)
        for shot in source["shots"]:
            self.assertIn(
                shot["dialogue"][0]["text"],
                plan["prompt_units"][0]["prompt_text"],
            )

    def test_missing_duration_stays_single_while_other_group_continues(self) -> None:
        source = make_source([None, 5, 4])
        plan = build_legacy_plan(
            source,
            grouping_decisions(source, [["SH002", "SH003"]]),
        )
        self.assertEqual(plan["validation"]["status"], "PARTIAL")
        self.assertEqual(
            [unit["source_shot_ids"] for unit in plan["prompt_units"]],
            [["SH001"], ["SH002", "SH003"]],
        )
        self.assertIsNone(
            plan["prompt_units"][0]["timeline"][0]["duration_seconds"]
        )
        self.assertEqual(
            plan["prompt_units"][1]["total_duration_seconds"], 9
        )

    def test_one_source_shot_is_exactly_one_ordered_cut(self) -> None:
        source = make_source([4, 4, 4])
        plan = build_legacy_plan(
            source,
            grouping_decisions(source, [["SH001", "SH002", "SH003"]]),
        )
        timeline = plan["prompt_units"][0]["timeline"]
        self.assertEqual(
            [cut["source_shot_id"] for cut in timeline],
            ["SH001", "SH002", "SH003"],
        )
        self.assertEqual(
            [cut["cut_label"] for cut in timeline],
            ["Cut 1", "Cut 2", "Cut 3"],
        )

    def test_known_first_cut_prompt_starts_at_zero_seconds(self) -> None:
        plan = build_legacy_plan(make_source([4]))
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("Cut 1 : 0-4S", prompt)
        self.assertNotIn("来源镜头 SH001", prompt)

    def test_integer_duration_keeps_trailing_zero(self) -> None:
        source = make_source([5, 5])
        plan = build_legacy_plan(
            source,
            grouping_decisions(source, [["SH001", "SH002"]]),
        )
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("总时长：10S", prompt)
        self.assertIn("Cut 2 : 5-10S", prompt)
        self.assertNotIn("总时长：1S", prompt)

    def test_prompt_uses_single_compact_camera_and_content_lines(self) -> None:
        source = make_source([4])
        source["scenes"] = [
            {
                "scene_id": "SC001",
                "scene": "15-1 赤狐岭 日 外",
                "reality_layer": "现实",
            }
        ]
        source["shots"][0]["scene_id"] = "SC001"
        source["shots"][0]["camera"].update(
            {
                "angle": "微仰视",
                "shot_size": "大全景",
                "movement": "极缓慢推进",
                "composition": "晨雾横过草坡，人物立于树下",
                "position": "草坡低处",
                "logic": "朝向树下人物",
            }
        )
        source["shots"][0]["rendered_shot_description"] = (
            "晨雾覆盖草坡。摄影机位于草坡低处，朝向树下人物；"
            "画面中晨雾横过草坡，人物立于树下。人物保持安静站姿。"
        )
        plan = build_legacy_plan(source)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("场景：赤狐岭 日 外，晨雾覆盖草坡。", prompt)
        self.assertIn(
            "构图：【微仰视，大全景，极缓慢推进】晨雾横过草坡，人物立于树下。",
            prompt,
        )
        self.assertIn(
            "画面内容：摄影机位置：草坡低处；摄影机运动：方式：极缓慢推进",
            prompt,
        )
        for forbidden in (
            "来源镜头",
            "现实层",
            "镜头结束状态",
            "\n景别：",
            "\n角度：",
            "\n运镜手法：",
        ):
            self.assertNotIn(forbidden, prompt)
        self.assertEqual(prompt.count("画面内容："), 1)

    def test_unknown_duration_prompt_keeps_time_unprovided(self) -> None:
        plan = build_legacy_plan(make_source([None]))
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("总时长：来源未提供", prompt)
        self.assertIn("Cut 1 : 时间未提供", prompt)
        self.assertNotIn("Cut 1 : 0-", prompt)

    def test_quoted_question_does_not_gain_extra_period(self) -> None:
        source = make_source(
            [4],
        )
        source["shots"][0]["rendered_shot_description"] = (
            "人物望向黑暗处问：“谁在那里？”"
        )
        source["shots"][0]["performance"]["visible_behavior"] = []
        prompt = build_legacy_plan(source)[
            "prompt_units"
        ][0]["prompt_text"]
        self.assertIn("谁在那里？”", prompt)
        self.assertNotIn("谁在那里？”。", prompt)

    def test_repeated_visible_props_are_not_appended_as_a_group(self) -> None:
        source = make_source([4])
        source["shots"][0]["rendered_shot_description"] = (
            "人物推着药品推车经过，玻璃药瓶轻碰。"
        )
        source["shots"][0]["visible_props"] = [
            "输液架",
            "药品推车",
            "玻璃药瓶",
        ]
        prompt = build_legacy_plan(source)[
            "prompt_units"
        ][0]["prompt_text"]
        self.assertEqual(prompt.count("药品推车"), 1)
        self.assertEqual(prompt.count("玻璃药瓶"), 1)
        self.assertEqual(prompt.count("输液架"), 1)
        self.assertNotIn("。；", prompt)

    def test_source_anti_slop_words_are_preserved_and_only_warned(self) -> None:
        source = make_source([4])
        source["shots"][0]["rendered_shot_description"] = (
            "人物拿起8K摄像机，查看机身编号。"
        )
        source["shots"][0]["dialogue"] = [
            {"speaker": "甲", "text": "这是一部史诗"}
        ]
        source["shots"][0]["performance"]["visible_behavior"] = [
            "人物指着“史诗”标题后放下手"
        ]
        snapshot = copy.deepcopy(source)
        plan = build_legacy_plan(source)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("人物拿起8K摄像机，查看机身编号。", prompt)
        self.assertIn("这是一部史诗", prompt)
        self.assertIn("人物指着“史诗”标题后放下手", prompt)
        self.assertEqual(source, snapshot)
        self.assertIn("SOURCE_ANTI_SLOP_REVIEW", issue_codes(plan))
        self.assertNotIn("PROMPT_ANTI_SLOP_FAILED", issue_codes(plan))

    def test_downstream_emotion_slop_is_rejected_without_rewriting(self) -> None:
        source = make_source([4])
        source["shots"][0]["performance"]["visible_behavior"] = []
        decisions = {
            "emotion_visualizations": {
                "SH001": {
                    "basis_emotion": "克制",
                    "text": "人物震撼地睁大双眼",
                    "guardrails": {
                        key: False
                        for key in delivery.EMOTION_GUARDRAIL_KEYS
                    },
                }
            }
        }
        plan = build_legacy_plan(source, decisions)
        self.assertEqual(plan["validation"]["status"], "PARTIAL")
        self.assertIn("DOWNSTREAM_ANTI_SLOP", issue_codes(plan))
        self.assertNotIn(
            "人物震撼地睁大双眼",
            plan["prompt_units"][0]["prompt_text"],
        )

    def test_validation_rejects_manually_added_downstream_slop(self) -> None:
        source = make_source([4])
        plan = build_legacy_plan(source)
        plan["prompt_units"][0]["prompt_text"] += "\n大师级电影感"
        plan["content_hash"] = delivery.prompt_plan_content_hash(plan)
        report = delivery.validate_prompt_plan(source, plan)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "PROMPT_ANTI_SLOP_FAILED",
            {issue["code"] for issue in report["errors"]},
        )

    def test_existing_visible_behavior_is_never_rewritten_or_augmented(self) -> None:
        behavior = ["她停住呼吸，右手仍压在桌沿"]
        source = make_source([4])
        source["shots"][0]["performance"]["visible_behavior"] = behavior
        decisions = {
            "emotion_visualizations": {
                "SH001": {
                    "basis_emotion": "克制",
                    "text": "她眨眼一次",
                    "guardrails": {
                        key: False
                        for key in delivery.EMOTION_GUARDRAIL_KEYS
                    },
                }
            }
        }
        normalized, _ = delivery.normalize_input(source)
        plan = build_legacy_plan(source, decisions)
        self.assertEqual(normalized["shots"][0]["visible_behavior"], behavior)
        self.assertIn(behavior[0], plan["prompt_units"][0]["prompt_text"])
        self.assertNotIn("她眨眼一次", plan["prompt_units"][0]["prompt_text"])
        self.assertIn(
            "EMOTION_VISUALIZATION_FORBIDDEN", issue_codes(plan)
        )

    def test_unknown_mode_is_a_global_gate(self) -> None:
        source = make_source([4, 4])
        plan = build_legacy_plan(
            source,
            generation_decision("unknown", [], []),
        )
        self.assertTrue(plan["generation"]["global_blocked"])
        self.assertEqual(plan["prompt_units"], [])
        self.assertEqual(plan["validation"]["status"], "FAIL")

    def test_formal_upstream_v1_contract_runs(self) -> None:
        source = make_formal_source("1.0.0")
        plan, artifacts = build_package(
            source, decisions=grouping_decisions(source)
        )
        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(plan["source"]["source_mode"], "upstream_structured")
        self.assertEqual(plan["source"]["source_contract"], "shot-data/1.0.0")
        self.assertEqual(len(plan["prompt_units"]), 1)
        output_dir = self.output_dir / "formal-v1"
        delivery.write_delivery_package(output_dir, artifacts)
        self.assertEqual(
            delivery.validate_delivery_package(source, output_dir)[
                "status"
            ],
            "PASS",
        )

    def test_formal_upstream_v2_contract_runs(self) -> None:
        source = make_formal_source("2.0.0")
        plan, artifacts = build_package(source)
        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(plan["source"]["source_mode"], "upstream_structured")
        self.assertEqual(plan["source"]["source_contract"], "shot-data/2.0.0")
        self.assertEqual(len(plan["prompt_units"]), 1)
        output_dir = self.output_dir / "formal-v2"
        delivery.write_delivery_package(output_dir, artifacts)
        self.assertEqual(
            delivery.validate_delivery_package(source, output_dir)[
                "status"
            ],
            "PASS",
        )

    def test_structured_source_identity_is_provenance_not_a_gate(self) -> None:
        compatible_sources = []
        wrong_skill = make_formal_source("1.0.0")
        wrong_skill["source_skill"] = "other-director"
        compatible_sources.append(rehash_source(wrong_skill))

        wrong_v1_skill_version = make_formal_source("1.0.0")
        wrong_v1_skill_version["source_skill_version"] = "2.0.0"
        compatible_sources.append(rehash_source(wrong_v1_skill_version))

        wrong_v2_skill_version = make_formal_source("2.0.0")
        wrong_v2_skill_version["source_skill_version"] = "1.0.0"
        compatible_sources.append(rehash_source(wrong_v2_skill_version))

        unknown_contract = make_formal_source("2.0.0")
        unknown_contract["contract_version"] = "3.0.0"
        unknown_contract["source_skill_version"] = "3.0.0"
        compatible_sources.append(rehash_source(unknown_contract))

        wrong_contract_name = make_formal_source("1.0.0")
        wrong_contract_name["contract_name"] = "story-data"
        wrong_contract_name["source_mode"] = "upstream_structured"
        compatible_sources.append(rehash_source(wrong_contract_name))

        for source in compatible_sources:
            with self.subTest(
                contract_version=source["contract_version"],
                source_skill=source["source_skill"],
                source_skill_version=source["source_skill_version"],
            ):
                plan = build_legacy_plan(source)
                self.assertEqual(plan["validation"]["status"], "PASS")
                self.assertEqual(len(plan["prompt_units"]), 1)
                self.assertEqual(
                    plan["source"]["source_skill_version"],
                    source["source_skill_version"],
                )

    def test_structured_243_contract_runs_without_version_gate(self) -> None:
        source = make_formal_source("2.4.3")
        source["scenes"] = [
            {
                "scene_id": "SC001",
                "location": "赤狐岭",
                "time_of_day": "清晨",
                "reality_layer": "现实",
            }
        ]
        source["shots"][0]["scene_id"] = "SC001"
        source["shots"][0]["blocking"] = None
        source["shots"][0]["performance"] = None
        rehash_source(source)

        plan, artifacts = build_package(source)

        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(plan["source"]["source_contract"], "shot-data/2.4.3")
        self.assertEqual(plan["source"]["source_skill_version"], "2.4.3")
        self.assertEqual(
            plan["compiler_inputs"]["normalized_source"]["shots"][0][
                "scene_context"
            ]["location"],
            "赤狐岭",
        )
        self.assertEqual(len(plan["prompt_units"]), 1)
        output_dir = self.output_dir / "formal-v243"
        delivery.write_delivery_package(output_dir, artifacts)
        self.assertEqual(
            delivery.validate_delivery_package(source, output_dir)["status"],
            "PASS",
        )

    def test_formal_upstream_hash_mismatch_blocks_prompt_compilation(self) -> None:
        source = make_formal_source("2.0.0")
        source["shots"][0]["rendered_shot_description"] = "篡改后的动作。"
        plan = build_legacy_plan(source)
        self.assertEqual(plan["validation"]["status"], "FAIL")
        self.assertEqual(plan["prompt_units"], [])
        self.assertIn("SOURCE_HASH_MISMATCH", issue_codes(plan))

    def test_structured_source_missing_hash_does_not_block_compilation(self) -> None:
        source = make_formal_source("1.0.0")
        source["content_hash"] = ""
        plan = build_legacy_plan(source)
        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(len(plan["prompt_units"]), 1)
        self.assertNotIn("SOURCE_HASH_INVALID", issue_codes(plan))

    def test_declared_invalid_hash_blocks_prompt_compilation(self) -> None:
        source = make_formal_source("1.0.0")
        source["content_hash"] = "not-a-sha256"
        plan = build_legacy_plan(source)
        self.assertEqual(plan["validation"]["status"], "FAIL")
        self.assertEqual(plan["prompt_units"], [])
        self.assertIn("SOURCE_HASH_INVALID", issue_codes(plan))

    def test_unknown_source_mode_is_provenance_only(self) -> None:
        plan = build_legacy_plan(
            make_source([4], source_mode="mystery_mode")
        )
        self.assertEqual(plan["validation"]["status"], "WARN")
        self.assertEqual(len(plan["prompt_units"]), 1)
        self.assertEqual(
            plan["source"]["source_mode"], "standalone_storyboard"
        )
        self.assertIn("SOURCE_MODE_UNRECOGNIZED", issue_codes(plan))

    def test_independent_source_modes_remain_available(self) -> None:
        for source_mode in (
            "partial_storyboard",
            "standalone_storyboard",
            "direct_material",
        ):
            with self.subTest(source_mode=source_mode):
                plan = build_legacy_plan(
                    make_source([4], source_mode=source_mode)
                )
                self.assertEqual(plan["validation"]["status"], "PASS")
                self.assertEqual(len(plan["prompt_units"]), 1)

    def test_explicit_local_mode_is_not_overridden_by_provenance(self) -> None:
        source = make_source([4], source_mode="partial_storyboard")
        source["contract_name"] = "prompt-source"
        source["contract_version"] = "1.0.0"
        plan = build_legacy_plan(source)
        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(plan["source"]["source_mode"], "partial_storyboard")

    def test_profile_unsupported_mode_is_a_global_gate(self) -> None:
        profile = delivery.resolve_model_profile("generic-video")
        profile["capabilities"]["supported_generation_modes"] = ["t2v"]
        plan = build_legacy_plan(
            make_source([4]),
            generation_decision(
                "i2v",
                ["image-1"],
                [
                    reference_role(
                        "image-1", "image", "scene_state", ["SH001"]
                    )
                ],
            ),
            profile,
        )
        self.assertTrue(plan["generation"]["global_blocked"])
        self.assertEqual(plan["prompt_units"], [])

    def test_seedance_rejects_nonconforming_tag_without_rewriting(self) -> None:
        decisions = generation_decision(
            "i2v",
            ["image-1"],
            [
                reference_role(
                    "image-1", "image", "scene_state", ["SH001"]
                )
            ],
        )
        plan = build_legacy_plan(make_source([4]), decisions)
        self.assertEqual(plan["validation"]["status"], "FAIL")
        self.assertEqual(plan["prompt_units"][0]["prompt_text"], "")
        self.assertIn("REFERENCE_TAG_INVALID", issue_codes(plan))
        self.assertNotIn("@Image1", json.dumps(plan, ensure_ascii=False))

    def test_custom_profile_accepts_exact_custom_tag(self) -> None:
        profile = delivery.resolve_model_profile("generic-video")
        profile["profile_id"] = "custom-prefix"
        profile["model_name"] = "Runtime Custom"
        profile["capabilities"]["reference_tag_convention"] = {
            "convention_id": "indexed-prefix-v1",
            "image_prefix": "img-",
            "video_prefix": "vid-",
        }
        decisions = generation_decision(
            "i2v",
            ["img-7"],
            [
                reference_role(
                    "img-7", "image", "scene_state", ["SH001"]
                )
            ],
        )
        plan = build_legacy_plan(
            make_source([4]), decisions, profile
        )
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("img-7", prompt)
        self.assertNotIn("@Image7", prompt)
        self.assertNotIn("Runtime Custom", prompt)
        self.assertEqual(plan["validation"]["status"], "PASS")

    def test_model_profile_metadata_tamper_is_rejected(self) -> None:
        source = make_source([4])
        plan = build_legacy_plan(source)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertNotIn(plan["model_profile"]["model_name"], prompt)
        self.assertNotIn(plan["model_profile"]["profile_id"], prompt)
        self.assertNotIn("su-promptskill", prompt)

        tampered = copy.deepcopy(plan)
        tampered["prompt_units"][0]["prompt_text"] += "\nSeedance 2.0"
        tampered["content_hash"] = delivery.prompt_plan_content_hash(
            tampered
        )
        report = delivery.validate_prompt_plan(source, tampered)
        self.assertIn(
            "PROMPT_MODEL_METADATA_LEAK",
            {issue["code"] for issue in report["errors"]},
        )

    def test_i2v_uses_state_delta_and_does_not_restate_image(self) -> None:
        source = make_source([4])
        source["shots"][0]["rendered_shot_description"] = (
            "红衣人物站在蓝墙前，左侧有一盏落地灯。"
        )
        source["shots"][0]["prompt_delta"] = "人物从静止转为向右迈一步"
        decisions = generation_decision(
            "i2v",
            ["@Image1"],
            [
                reference_role(
                    "@Image1", "image", "scene_state", ["SH001"]
                )
            ],
        )
        plan = build_legacy_plan(source, decisions)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("@Image1", prompt)
        self.assertIn("人物从静止转为向右迈一步", prompt)
        self.assertNotIn(
            "红衣人物站在蓝墙前，左侧有一盏落地灯。", prompt
        )

    def test_i2v_keeps_action_found_only_in_rendered_description(self) -> None:
        source = make_source([4])
        source["shots"][0]["rendered_shot_description"] = (
            "人物突然后退一步并抬起双手。"
        )
        source["shots"][0]["blocking"] = []
        source["shots"][0]["performance"]["visible_behavior"] = []
        source["shots"][0]["dialogue"] = []
        decisions = generation_decision(
            "i2v",
            ["@Image1"],
            [
                reference_role(
                    "@Image1", "image", "scene_state", ["SH001"]
                )
            ],
        )
        plan = build_legacy_plan(source, decisions)
        self.assertIn(
            "人物突然后退一步并抬起双手。",
            plan["prompt_units"][0]["prompt_text"],
        )

    def test_reference_mode_carries_continuity_delta_and_target_end_state(
        self,
    ) -> None:
        source = make_source([4])
        source["shots"][0]["continuity_updates"] = [
            {
                "entity_type": "character",
                "entity": "人物",
                "field": "hand_state",
                "from": "放松",
                "to": "指节发白",
                "evidence_fact_ids": ["LOCAL-F001"],
            }
        ]
        source["shots"][0]["end_state"] = ["人物最终按住桌沿"]
        decisions = generation_decision(
            "i2v",
            ["@Image1"],
            [
                reference_role(
                    "@Image1", "image", "scene_state", ["SH001"]
                )
            ],
        )
        plan = build_legacy_plan(source, decisions)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("指节发白", prompt)
        self.assertNotIn("镜头结束状态", prompt)
        self.assertNotIn("人物最终按住桌沿", prompt)

    def test_every_reference_mode_consumes_source_visual_action(self) -> None:
        action = "人物从门边冲到桌前并按住信封。"
        cases = {
            "i2v": generation_decision(
                "i2v",
                ["@Image1"],
                [
                    reference_role(
                        "@Image1", "image", "scene_state", ["SH001"]
                    )
                ],
            ),
            "v2v": generation_decision(
                "v2v",
                ["@Video1"],
                [
                    reference_role(
                        "@Video1",
                        "video",
                        "motion_reference",
                        ["SH001"],
                    )
                ],
            ),
            "r2v": generation_decision(
                "r2v",
                ["@Image1"],
                [
                    reference_role(
                        "@Image1",
                        "image",
                        "subject_identity",
                        ["SH001"],
                    )
                ],
            ),
            "flf2v": generation_decision(
                "flf2v",
                ["@Image1", "@Image2"],
                [
                    reference_role(
                        "@Image1", "image", "first_frame", ["SH001"]
                    ),
                    reference_role(
                        "@Image2", "image", "last_frame", ["SH001"]
                    ),
                ],
            ),
            "edit": generation_decision(
                "edit",
                ["@Video1"],
                [
                    reference_role(
                        "@Video1", "video", "edit_source", ["SH001"]
                    )
                ],
                edit_scope=["lighting"],
                edit_deltas=[
                    {
                        "layer": "lighting",
                        "instruction": "把主光改为冷色",
                        "applies_to_shot_ids": ["SH001"],
                    }
                ],
            ),
            "extend": generation_decision(
                "extend",
                ["@Video1"],
                [
                    reference_role(
                        "@Video1",
                        "video",
                        "extension_source",
                        ["SH001"],
                    )
                ],
                extend_context={
                    "accepted_material": True,
                    "observed_end_state": "人物停在门边",
                },
            ),
        }
        for mode, decisions in cases.items():
            with self.subTest(mode=mode):
                source = make_source([4])
                source["shots"][0]["rendered_shot_description"] = action
                source["shots"][0]["blocking"] = []
                source["shots"][0]["performance"]["visible_behavior"] = []
                source["shots"][0]["dialogue"] = []
                plan = build_legacy_plan(source, decisions)
                self.assertEqual(plan["validation"]["status"], "PASS")
                self.assertIn(action, plan["prompt_units"][0]["prompt_text"])

    def test_v2v_motion_reference_is_not_identity(self) -> None:
        decisions = generation_decision(
            "v2v",
            ["@Video1"],
            [
                reference_role(
                    "@Video1",
                    "video",
                    "motion_reference",
                    ["SH001"],
                )
            ],
        )
        plan = build_legacy_plan(make_source([4]), decisions)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("@Video1 仅作运动参考", prompt)
        self.assertNotIn("@Video1 作为主体身份参考", prompt)

    def test_flf_edit_and_extend_gates_are_per_cut(self) -> None:
        flf = generation_decision(
            "flf2v",
            ["@Image1", "@Image2"],
            [
                reference_role(
                    "@Image1", "image", "first_frame", ["SH001"]
                ),
                reference_role(
                    "@Image2", "image", "last_frame", ["SH001"]
                ),
            ],
        )
        flf_plan = build_legacy_plan(make_source([4]), flf)
        self.assertEqual(flf_plan["validation"]["status"], "PASS")
        self.assertIn(
            "@Image1", flf_plan["prompt_units"][0]["prompt_text"]
        )
        self.assertIn(
            "@Image2", flf_plan["prompt_units"][0]["prompt_text"]
        )

        edit = generation_decision(
            "edit",
            ["@Video1"],
            [
                reference_role(
                    "@Video1", "video", "edit_source", ["SH001"]
                )
            ],
            edit_scope=["lighting"],
            edit_deltas=[
                {
                    "layer": "lighting",
                    "instruction": "改成震撼电影感",
                    "applies_to_shot_ids": ["SH001"],
                }
            ],
        )
        edit_plan = build_legacy_plan(make_source([4]), edit)
        self.assertEqual(edit_plan["prompt_units"][0]["prompt_text"], "")
        self.assertIn("DOWNSTREAM_ANTI_SLOP", issue_codes(edit_plan))

        extend = generation_decision(
            "extend",
            ["@Video1"],
            [
                reference_role(
                    "@Video1",
                    "video",
                    "extension_source",
                    ["SH001"],
                )
            ],
        )
        extend_plan = build_legacy_plan(make_source([4]), extend)
        self.assertEqual(
            extend_plan["prompt_units"][0]["prompt_text"], ""
        )
        self.assertIn(
            "MODE_UNIT_REFERENCE_INVALID", issue_codes(extend_plan)
        )

    def test_edit_delta_scope_rejects_non_array_applies_to_shot_ids(self) -> None:
        for invalid_scope in ("SH001", {"SH001": True}):
            with self.subTest(invalid_scope=invalid_scope):
                decisions = generation_decision(
                    "edit",
                    ["@Video1"],
                    [
                        reference_role(
                            "@Video1",
                            "video",
                            "edit_source",
                            ["SH001"],
                        )
                    ],
                    edit_scope=["lighting"],
                    edit_deltas=[
                        {
                            "layer": "lighting",
                            "instruction": "非法 delta 不得进入正文",
                            "applies_to_shot_ids": invalid_scope,
                        }
                    ],
                )
                plan = build_legacy_plan(
                    make_source([4]), decisions
                )
                self.assertEqual(plan["validation"]["status"], "FAIL")
                self.assertEqual(
                    plan["prompt_units"][0]["prompt_text"], ""
                )
                self.assertIn("EDIT_SCOPE_INVALID", issue_codes(plan))
                self.assertNotIn(
                    "非法 delta 不得进入正文",
                    json.dumps(plan["prompt_units"], ensure_ascii=False),
                )

    def test_one_invalid_reference_unit_does_not_block_valid_unit(self) -> None:
        source = make_source([4, 5])
        decisions = generation_decision(
            "i2v",
            ["bad-tag", "@Image2"],
            [
                reference_role(
                    "bad-tag", "image", "scene_state", ["SH001"]
                ),
                reference_role(
                    "@Image2", "image", "scene_state", ["SH002"]
                ),
            ],
        )
        plan = build_legacy_plan(source, decisions)
        self.assertEqual(plan["validation"]["status"], "PARTIAL")
        self.assertEqual(
            [unit["source_shot_ids"] for unit in plan["prompt_units"]],
            [["SH001"], ["SH002"]],
        )
        self.assertEqual(plan["prompt_units"][0]["prompt_text"], "")
        self.assertIn(
            "GENERATION_CONTEXT_INVALID",
            plan["prompt_units"][0]["prompt_validation"][
                "diagnostic_codes"
            ],
        )
        self.assertIn("@Image2", plan["prompt_units"][1]["prompt_text"])
        self.assertEqual(
            [
                cut["source_shot_id"]
                for unit in plan["prompt_units"]
                for cut in unit["timeline"]
            ],
            ["SH001", "SH002"],
        )
        self.assertTrue(
            plan["validation"]["deterministic_checks"][
                "source_shot_coverage"
            ]
        )

    def test_top_level_scene_props_and_end_state_are_preserved(self) -> None:
        source = {
            "contract_name": "shot-data",
            "contract_version": "1.0.0",
            "source_skill": "su-fenjingskill",
            "source_skill_version": "1.0.0",
            "project_id": "P-001",
            "content_hash": "",
            "scenes": [
                {
                    "scene_id": "SC001",
                    "scene": "厨房 夜 内",
                    "location": "旧公寓厨房",
                    "time": "午夜",
                    "reality_layer": "现实",
                    "environment": "窗外下雨",
                }
            ],
            "shots": [
                {
                    **make_shot(
                        "SH001",
                        5,
                        rendered="人物走到桌边。",
                    ),
                    "scene_id": "SC001",
                    "visible_props": ["银色钥匙"],
                    "end_state": ["钥匙停在桌面中央"],
                }
            ],
        }
        rehash_source(source)
        snapshot = copy.deepcopy(source)
        normalized, issues = delivery.normalize_input(source)
        self.assertFalse(
            any(issue["code"] == "SCENE_CONTEXT_MISSING" for issue in issues)
        )
        self.assertEqual(
            normalized["shots"][0]["scene_context"]["scene"],
            "厨房 夜 内",
        )
        plan = build_legacy_plan(source)
        prompt = plan["prompt_units"][0]["prompt_text"]
        for text in (
            "厨房 夜 内",
            "旧公寓厨房",
            "午夜",
            "窗外下雨",
            "银色钥匙",
        ):
            self.assertIn(text, prompt)
        self.assertNotIn("现实层", prompt)
        self.assertIn("终态补充：钥匙停在桌面中央", prompt)
        self.assertEqual(source, snapshot)

    def test_missing_scene_link_is_local_warning(self) -> None:
        source = {
            "contract_name": "shot-data",
            "contract_version": "1.0.0",
            "source_skill": "su-fenjingskill",
            "source_skill_version": "1.0.0",
            "project_id": "P-404",
            "content_hash": "",
            "scenes": [],
            "shots": [{**make_shot("SH001", 4), "scene_id": "SC404"}],
        }
        rehash_source(source)
        plan = build_legacy_plan(source)
        self.assertIn("SCENE_CONTEXT_MISSING", issue_codes(plan))
        self.assertEqual(len(plan["prompt_units"]), 1)

    def test_plan_hash_removes_itself_before_single_hash(self) -> None:
        plan = build_legacy_plan(make_source([4]))
        without_hash = {
            key: value
            for key, value in plan.items()
            if key != "content_hash"
        }
        self.assertEqual(
            plan["content_hash"], delivery.sha256_json(without_hash)
        )
        self.assertEqual(
            plan["content_hash"], delivery.prompt_plan_content_hash(plan)
        )

    def test_four_file_delivery_has_fixed_columns_and_is_deterministic(self) -> None:
        source = make_source([4, 5])
        decisions = grouping_decisions(source)
        plan, artifacts = build_package(
            source, decisions=decisions
        )
        second_plan, second_artifacts = build_package(
            source, decisions=decisions
        )
        self.assertEqual(plan, second_plan)
        self.assertEqual(artifacts, second_artifacts)
        delivery.write_delivery_package(self.output_dir, artifacts)
        files = plan["delivery"]["files"]
        self.assertEqual(
            {path.name for path in self.output_dir.iterdir()},
            set(files.values()),
        )
        rows = delivery.prompt_table_rows(plan)
        self.assertEqual(
            delivery.parse_prompt_table_markdown(
                (self.output_dir / files["markdown"]).read_bytes()
            ),
            rows,
        )
        self.assertEqual(
            delivery.parse_prompt_table_xlsx(
                (self.output_dir / files["xlsx"]).read_bytes()
            ),
            delivery.prompt_table_xlsx_rows(plan),
        )
        self.assertEqual(
            delivery.reconstruct_prompt_texts_from_xlsx_rows(
                delivery.parse_prompt_table_xlsx(
                    (self.output_dir / files["xlsx"]).read_bytes()
                )
            ),
            {
                unit["prompt_unit_id"]: unit["prompt_text"]
                for unit in plan["prompt_units"]
            },
        )
        report = json.loads(
            (self.output_dir / files["validation"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            report["table_contract"]["columns"],
            list(delivery.PROMPT_TABLE_COLUMNS),
        )
        report_without_hash = {
            key: value
            for key, value in report.items()
            if key != "content_hash"
        }
        self.assertEqual(
            report["content_hash"],
            delivery.sha256_json(report_without_hash),
        )
        validation = delivery.validate_delivery_package(
            source, self.output_dir
        )
        self.assertEqual(validation["status"], "PASS")
        self.assertTrue(
            all(validation["deterministic_checks"].values())
        )

    def test_delivery_filenames_derive_from_input_and_include_prompt(self) -> None:
        slug = delivery.derive_delivery_slug(
            "ep15-dibati-shot-data.json",
            make_source([4]),
        )
        self.assertEqual(slug, "ep15-dibati")
        files = delivery.delivery_file_map(slug)
        self.assertEqual(
            files,
            {
                "plan": "ep15-dibati-prompt-plan.json",
                "markdown": "ep15-dibati-prompt-table.md",
                "xlsx": "ep15-dibati-prompt-table.xlsx",
                "validation": "ep15-dibati-prompt-validation.json",
            },
        )

    def test_delivery_detects_markdown_and_excel_tampering(self) -> None:
        source = make_source([4])
        _, artifacts = build_package(source)
        delivery.write_delivery_package(self.output_dir, artifacts)
        files = delivery.delivery_file_map(
            delivery.derive_delivery_slug(None, source)
        )
        markdown_path = self.output_dir / files["markdown"]
        markdown_path.write_bytes(
            markdown_path.read_bytes().replace(
                "人物".encode("utf-8"), "他人".encode("utf-8"), 1
            )
        )
        markdown_result = delivery.validate_delivery_package(
            source, self.output_dir
        )
        self.assertEqual(markdown_result["status"], "FAIL")
        self.assertFalse(
            markdown_result["deterministic_checks"]["markdown_cells"]
        )

        delivery.write_delivery_package(self.output_dir, artifacts)
        xlsx_path = self.output_dir / files["xlsx"]
        xlsx_path.write_bytes(xlsx_path.read_bytes() + b"tamper")
        xlsx_result = delivery.validate_delivery_package(
            source, self.output_dir
        )
        self.assertEqual(xlsx_result["status"], "FAIL")
        self.assertFalse(
            xlsx_result["deterministic_checks"]["xlsx_cells"]
        )

    def test_validation_recompiles_prompt_and_rejects_forged_ledgers(
        self,
    ) -> None:
        source = make_source([4])
        plan = build_legacy_plan(source)
        plan["prompt_units"][0]["prompt_text"] = (
            "画面内容：来源未提供"
        )
        plan["prompt_units"][0]["prompt_validation"] = {
            "status": "PASS",
            "checks": {
                "source_mapping": True,
                "timed_timeline": True,
                "dialogue_exact": True,
                "reference_tags_exact": True,
                "model_metadata_absent": True,
            },
            "diagnostic_codes": [],
        }
        plan["source"]["source_read_only"] = True
        plan["diagnostics"] = []
        plan["validation"] = {
            "status": "PASS",
            "errors": [],
            "warnings": [],
            "summary": copy.deepcopy(
                plan["validation"]["summary"]
            ),
            "deterministic_checks": {
                "source_read_only": True,
                "source_order": True,
                "source_hash": True,
                "source_shot_coverage": True,
                "group_duration": True,
                "cut_mapping": True,
                "cut_timeline": True,
                "prompt_metadata_absent": True,
                "mode_gate": True,
                "reference_scope": True,
                "downstream_anti_slop_absent": True,
            },
            "semantic_limitations": [],
        }
        plan["content_hash"] = delivery.prompt_plan_content_hash(plan)
        artifacts = delivery.derive_delivery_artifacts(plan)
        delivery.write_delivery_package(self.output_dir, artifacts)

        result = delivery.validate_delivery_package(
            source, self.output_dir
        )
        self.assertEqual(result["status"], "FAIL")
        error_codes = {
            issue["code"]
            for issue in result["plan_validation"]["errors"]
        }
        self.assertTrue(
            error_codes
            & {
                "PROMPT_RECOMPILE_MISMATCH",
                "PLAN_RECOMPILATION_MISMATCH",
                "UNIT_VALIDATION_LEDGER_MISMATCH",
            }
        )

    def test_validation_rejects_forged_source_read_only_claim(self) -> None:
        source = make_source([4])
        plan = build_legacy_plan(source)
        plan["source"]["source_read_only"] = "caller-attested"
        plan["content_hash"] = delivery.prompt_plan_content_hash(plan)
        report = delivery.validate_prompt_plan(source, plan)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "SOURCE_PROVENANCE_MISMATCH",
            {issue["code"] for issue in report["errors"]},
        )

    def test_partial_delivery_still_writes_consistent_four_files(self) -> None:
        source = make_source([None, 4])
        plan, artifacts = build_package(
            source, decisions=grouping_decisions(source)
        )
        self.assertEqual(plan["validation"]["status"], "PARTIAL")
        delivery.write_delivery_package(self.output_dir, artifacts)
        files = plan["delivery"]["files"]
        self.assertTrue(
            all(
                (self.output_dir / name).is_file()
                for name in files.values()
            )
        )
        report = json.loads(
            (self.output_dir / files["validation"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["status"], "PARTIAL")
        validated = delivery.validate_delivery_package(
            source, self.output_dir
        )
        self.assertEqual(validated["status"], "PARTIAL")
        self.assertTrue(
            all(validated["deterministic_checks"].values())
        )

    def test_unreadable_shot_has_empty_failed_unit_while_valid_shot_runs(
        self,
    ) -> None:
        source = make_source([4])
        source["shots"].append(
            {
                "shot_id": "SH002",
                "duration_seconds": 3,
                "camera": {},
                "blocking": [],
                "performance": {
                    "emotion_intent": "",
                    "visible_behavior": [],
                },
                "dialogue": [],
                "continuity": {},
                "continuity_updates": [],
                "rendered_shot_description": "",
            }
        )
        plan = build_legacy_plan(source)
        self.assertEqual(plan["validation"]["status"], "PARTIAL")
        self.assertNotEqual(
            plan["prompt_units"][0]["prompt_text"], ""
        )
        unreadable_unit = plan["prompt_units"][1]
        self.assertEqual(unreadable_unit["source_shot_ids"], ["SH002"])
        self.assertEqual(unreadable_unit["prompt_text"], "")
        self.assertEqual(
            unreadable_unit["prompt_validation"]["status"], "FAIL"
        )
        self.assertIn(
            "INPUT_MATERIAL_UNREADABLE",
            unreadable_unit["prompt_validation"]["diagnostic_codes"],
        )
        self.assertNotIn(
            "画面内容：来源未提供",
            json.dumps(unreadable_unit, ensure_ascii=False),
        )

    def test_only_unreadable_shot_makes_plan_fail_without_fake_prompt(
        self,
    ) -> None:
        source = {
            "source_mode": "direct_material",
            "shots": [
                {
                    "shot_id": "SH001",
                    "duration_seconds": 3,
                    "camera": {},
                    "blocking": [],
                    "performance": {
                        "emotion_intent": "",
                        "visible_behavior": [],
                    },
                    "dialogue": [],
                    "continuity": {},
                    "continuity_updates": [],
                    "rendered_shot_description": "",
                }
            ],
        }
        plan = build_legacy_plan(source)
        self.assertEqual(plan["validation"]["status"], "FAIL")
        self.assertEqual(plan["prompt_units"][0]["prompt_text"], "")
        self.assertEqual(
            plan["prompt_units"][0]["prompt_validation"]["status"],
            "FAIL",
        )

    def test_test_hygiene_leaves_no_skill_local_artifacts(self) -> None:
        skill_root = SCRIPT_DIR.parent
        forbidden = [
            path
            for path in skill_root.rglob("*")
            if path.name == "__pycache__"
            or path.name == ".test-output"
            or path.name.startswith(".test-")
        ]
        self.assertEqual(forbidden, [])

    def test_fully_unreadable_failure_still_has_four_consistent_files(self) -> None:
        plan, artifacts = delivery.build_failure_delivery(
            "source JSON cannot be parsed"
        )
        self.assertEqual(plan["validation"]["status"], "FAIL")
        self.assertEqual(plan["prompt_units"], [])
        self.assertEqual(
            set(artifacts), set(plan["delivery"]["files"].values())
        )
        delivery.write_delivery_package(self.output_dir, artifacts)
        self.assertTrue(
            all(
                (self.output_dir / name).is_file()
                for name in plan["delivery"]["files"].values()
            )
        )
        report = json.loads(
            (
                self.output_dir
                / plan["delivery"]["files"]["validation"]
            ).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["status"], "FAIL")

    def test_v2_default_profile_contract_and_parameter_free_prompt(self) -> None:
        plan = build_plan(
            make_source([4]),
            decisions={
                "request_configuration": {
                    "model_id": "doubao-seedance-2-5-260628",
                    "ratio": "16:9",
                    "duration": 30,
                    "output_format": "mov",
                }
            },
        )
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertEqual(plan["contract_version"], "2.0.4")
        self.assertEqual(plan["skill"]["version"], "2.0.4")
        self.assertEqual(
            plan["model_profile"]["profile_id"],
            "seedance-2.5-default",
        )
        self.assertEqual(
            plan["model_profile"]["model_id"],
            "doubao-seedance-2-5-260628",
        )
        self.assertNotIn("总时长：", prompt)
        self.assertNotIn("16:9", prompt)
        self.assertNotIn("output_format", prompt)
        self.assertEqual(plan["validation"]["status"], "PASS")

    def test_v203_official_prompt_structure_and_one_change_per_cut(self) -> None:
        source = make_source([4, 5])
        plan = build_plan(
            source,
            grouping_decisions(source, [["SH001", "SH002"]]),
        )
        prompt = plan["prompt_units"][0]["prompt_text"]
        headers = [
            "【生成目标】",
            "【主体、关系与场景】",
            "【镜头脚本】",
            "【保持一致】",
        ]
        self.assertEqual(
            [prompt.find(header) for header in headers],
            sorted(prompt.find(header) for header in headers),
        )
        self.assertEqual(prompt.count("主要状态变化："), 2)
        self.assertNotIn("连续呈现各 Cut", prompt)
        self.assertIn("沿既定事件顺序推进，最终到达", prompt)
        self.assertNotIn("构图：", prompt)
        self.assertNotIn("画面内容：", prompt)
        self.assertTrue(
            plan["prompt_units"][0]["prompt_validation"]["checks"][
                "official_prompt_structure"
            ]
        )

    def test_v203_official_task_routing_exposes_roles_and_intent(self) -> None:
        decisions = generation_decision(
            "i2v",
            ["@图片1"],
            [reference_role("@图片1", "image", "subject_identity", ["SH001"])],
        )
        plan = build_plan(make_source([4]), decisions)
        routing = plan["task"]["official_routing"]
        self.assertEqual(routing["task_type"], "reference-generation")
        self.assertEqual(routing["prompt_intent"], "generate-from-reference")
        self.assertEqual(
            routing["content_roles"],
            [{"tag": "@图片1", "content_role": "reference_image"}],
        )

    def test_v203_strict_frame_roles_reject_reference_role_mixing(self) -> None:
        decisions = generation_decision(
            "r2v",
            ["@图片1", "@图片2"],
            [
                reference_role("@图片1", "image", "first_frame", ["SH001"]),
                reference_role("@图片2", "image", "subject_identity", ["SH001"]),
            ],
        )
        plan = build_plan(make_source([4]), decisions)
        self.assertIn("CONTENT_ROLE_SCENARIO_CONFLICT", issue_codes(plan))
        self.assertEqual(plan["prompt_units"], [])

    def test_v203_request_resolution_and_mov_recommendation(self) -> None:
        decisions = generation_decision(
            "extend",
            ["@视频1"],
            [reference_role("@视频1", "video", "extension_source", ["SH001"])],
            extend_context={
                "accepted_material": True,
                "observed_end_state": "人物停在门口",
                "direction": "后",
            },
        )
        decisions["request_configuration"] = {
            "ratio": "adaptive",
            "duration": 6,
            "resolution": "1080p",
            "output_format": "mp4",
        }
        plan = build_plan(make_source([4]), decisions)
        self.assertIn("REQUEST_PARAMETER_CONFLICT", issue_codes(plan))
        self.assertTrue(
            any(
                item.get("code") == "MOV_RECOMMENDED"
                for item in plan["prompt_advisories"]
            )
        )

    def test_v203_official_image_pixel_range_accepts_above_4096(self) -> None:
        plan = build_plan(
            make_source([4]),
            {
                "asset_inventory": {
                    "complete": True,
                    "items": [
                        {
                            "tag": "@图片1",
                            "media_type": "image",
                            "available": True,
                            "width": 4500,
                            "height": 1800,
                        }
                    ],
                }
            },
        )
        self.assertNotIn("ASSET_LIMIT_EXCEEDED", issue_codes(plan))

    def test_v2_seedance_25_allows_thirty_seconds_and_ten_cuts(self) -> None:
        source = make_source([3] * 10)
        ids = [str(shot["shot_id"]) for shot in source["shots"]]
        plan = build_plan(
            source,
            grouping_decisions(source, [ids]),
        )
        self.assertEqual(len(plan["prompt_units"]), 1)
        self.assertEqual(plan["prompt_units"][0]["total_duration_seconds"], 30)
        self.assertEqual(len(plan["prompt_units"][0]["timeline"]), 10)
        self.assertEqual(plan["validation"]["status"], "PASS")

    def test_v2_seedance_20_keeps_fifteen_seconds_and_five_cuts(self) -> None:
        source = make_source([3] * 6)
        ids = [str(shot["shot_id"]) for shot in source["shots"]]
        plan = build_plan(
            source,
            grouping_decisions(source, [ids]),
            delivery.resolve_model_profile("seedance-2.0-default"),
        )
        self.assertEqual([len(unit["timeline"]) for unit in plan["prompt_units"]], [4, 2])

    def test_v2_non_integer_timeline_is_not_rounded_in_prompt(self) -> None:
        source = make_source([1.5, 2.5])
        plan = build_plan(
            source,
            grouping_decisions(source, [["SH001", "SH002"]]),
        )
        unit = plan["prompt_units"][0]
        self.assertEqual(unit["timeline"][0]["end_seconds"], 1.5)
        self.assertEqual(unit["timeline"][1]["end_seconds"], 4)
        self.assertIn("Cut 1｜顺序阶段", unit["prompt_text"])
        self.assertNotIn("0-2S", unit["prompt_text"])
        self.assertNotIn("2-4S", unit["prompt_text"])

    def test_v2_audio_reference_and_unused_assets_are_explicit(self) -> None:
        source = make_source([4])
        decisions = {
            "task": {
                "primary": "generate",
                "input_topology": "audio-reference",
                "modules": ["multi-reference"],
            },
            "asset_inventory": {
                "complete": True,
                "items": [
                    {
                        "tag": "@音频 1",
                        "media_type": "audio",
                        "available": True,
                        "duration_seconds": 4,
                    },
                    {
                        "tag": "@图片 2",
                        "media_type": "image",
                        "available": True,
                    },
                ],
            },
            "asset_assignments": [
                {
                    "tag": "@音频 1",
                    "target_entity": "人物",
                    "role": "audio_reference",
                    "adopted_dimensions": ["音色"],
                    "rejected_dimensions": ["背景音乐"],
                    "applies_to_shot_ids": ["SH001"],
                    "user_mapped": True,
                }
            ],
        }
        plan = build_plan(source, decisions)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("@音频 1用于人物的音色", prompt)
        self.assertNotIn("【未采用素材】", prompt)
        self.assertNotIn("@图片 2", prompt)
        self.assertEqual(plan["unused_assets"], ["@图片 2"])
        self.assertEqual(plan["validation"]["status"], "PASS")

    def test_v2_asset_hard_limit_blocks_submission_not_prompt(self) -> None:
        decisions = {
            "asset_inventory": {
                "complete": True,
                "items": [
                    {
                        "tag": f"@图片{index}",
                        "media_type": "image",
                        "available": True,
                    }
                    for index in range(1, 32)
                ],
            }
        }
        plan = build_plan(make_source([4]), decisions)
        self.assertFalse(plan["submission_ready"])
        self.assertTrue(plan["prompt_units"][0]["prompt_text"])
        self.assertIn("ASSET_LIMIT_EXCEEDED", issue_codes(plan))
        self.assertEqual(plan["validation"]["status"], "WARN")

    def test_v2_optional_missing_asset_degrades_but_core_missing_blocks(self) -> None:
        optional = {
            "task": {
                "primary": "generate",
                "input_topology": "text-only",
                "modules": [],
            },
            "asset_inventory": {
                "complete": True,
                "items": [
                    {
                        "tag": "@图片1",
                        "media_type": "image",
                        "available": False,
                        "core": False,
                    }
                ],
            },
            "asset_assignments": [
                {
                    "tag": "@图片1",
                    "target_entity": "普通背景",
                    "role": "scene_state",
                    "adopted_dimensions": ["布局"],
                    "rejected_dimensions": [],
                    "applies_to_shot_ids": ["SH001"],
                }
            ],
        }
        optional_plan = build_plan(make_source([4]), optional)
        self.assertTrue(optional_plan["prompt_units"][0]["prompt_text"])
        self.assertEqual(optional_plan["validation"]["status"], "WARN")
        self.assertEqual(
            optional_plan["prompt_advisories"][0]["type"], "补充建议"
        )
        self.assertNotIn(
            "@图片1", optional_plan["prompt_units"][0]["prompt_text"]
        )

        core = copy.deepcopy(optional)
        core["task"]["input_topology"] = "image-reference"
        core["asset_inventory"]["items"][0]["core"] = True
        core["asset_assignments"][0]["role"] = "subject_identity"
        core_plan = build_plan(make_source([4]), core)
        self.assertFalse(core_plan["submission_ready"])
        self.assertEqual(core_plan["prompt_units"], [])
        self.assertIn("CORE_ASSET_MISSING", issue_codes(core_plan))

    def test_v2_cardinality_conflict_blocks_ambiguous_reuse(self) -> None:
        decisions = {
            "task": {
                "primary": "generate",
                "input_topology": "image-reference",
                "modules": ["multi-reference"],
            },
            "asset_inventory": {
                "complete": True,
                "items": [
                    {
                        "tag": "@图片1",
                        "media_type": "image",
                        "available": True,
                    }
                ],
            },
            "asset_assignments": [
                {
                    "tag": "@图片1",
                    "target_entity": target,
                    "role": "subject_identity",
                    "adopted_dimensions": ["五官"],
                    "rejected_dimensions": [],
                    "applies_to_shot_ids": ["SH001"],
                }
                for target in ("人物A", "人物B")
            ],
        }
        plan = build_plan(make_source([4]), decisions)
        self.assertIn("ASSET_CARDINALITY_CONFLICT", issue_codes(plan))
        self.assertEqual(plan["prompt_units"], [])

    def test_v2_story_contract_dialogue_ledger_and_number_literal(self) -> None:
        source = make_source([4])
        source["shots"][0]["rendered_shot_description"] = (
            "镜头45中，人物看向门口后说出原句。"
        )
        source["shots"][0]["dialogue"] = [
            {"speaker": "人物", "text": "你一个外人"}
        ]
        plan = build_plan(source)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("镜头45", prompt)
        self.assertNotIn("45度", prompt)
        self.assertIn("你一个外人", prompt)
        self.assertEqual(plan["dialogue_ledger"][0]["speaker"], "人物")
        self.assertEqual(plan["dialogue_ledger"][0]["text"], "你一个外人")

    def test_v2_first_last_frames_use_exact_role_sentences(self) -> None:
        decisions = generation_decision(
            "flf2v",
            ["@图片1", "@图片2"],
            [
                reference_role(
                    "@图片1", "image", "first_frame", ["SH001"]
                ),
                reference_role(
                    "@图片2", "image", "last_frame", ["SH001"]
                ),
            ],
        )
        plan = build_plan(make_source([4]), decisions)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("@图片1作为首帧。", prompt)
        self.assertIn("@图片2作为尾帧。", prompt)
        self.assertNotIn("仅作首帧参考", prompt)

    def test_v2_edit_has_range_closure_and_parameter_advisory(self) -> None:
        decisions = generation_decision(
            "edit",
            ["@视频1"],
            [
                reference_role(
                    "@视频1", "video", "edit_source", ["SH001"]
                )
            ],
            edit_scope=["lighting"],
            edit_deltas=[
                {
                    "layer": "lighting",
                    "instruction": "把主光改为冷色",
                    "applies_to_shot_ids": ["SH001"],
                }
            ],
        )
        decisions["request_configuration"] = {
            "ratio": "16:9",
            "duration": 20,
        }
        plan = build_plan(make_source([4]), decisions)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("除以上明确修改对象外", prompt)
        self.assertNotIn("16:9", prompt)
        self.assertFalse(plan["submission_ready"])
        self.assertIn("REQUEST_PARAMETER_CONFLICT", issue_codes(plan))

    def test_v2_edit_then_extend_is_two_dependent_prompt_units(self) -> None:
        source = make_source([4])
        decisions = {
            "operations": [
                {
                    "operation_id": "OP001",
                    "order": 1,
                    "task": {
                        "primary": "edit",
                        "input_topology": "video-reference",
                        "modules": [],
                    },
                    "asset_inventory": {
                        "complete": True,
                        "items": [
                            {
                                "tag": "@视频1",
                                "media_type": "video",
                                "available": True,
                                "core": True,
                            }
                        ],
                    },
                    "asset_assignments": [
                        {
                            "tag": "@视频1",
                            "target_entity": "原视频",
                            "role": "edit_source",
                            "adopted_dimensions": ["画面和时间线"],
                            "rejected_dimensions": [],
                            "applies_to_shot_ids": ["SH001"],
                            "user_mapped": True,
                        }
                    ],
                    "edit_scope": ["lighting"],
                    "edit_deltas": [
                        {
                            "layer": "lighting",
                            "instruction": "把主光改为冷色",
                            "applies_to_shot_ids": ["SH001"],
                        }
                    ],
                    "request_configuration": {
                        "ratio": "adaptive",
                        "duration": -1,
                    },
                },
                {
                    "operation_id": "OP002",
                    "order": 2,
                    "depends_on_operation_id": "OP001",
                    "task": {
                        "primary": "extend",
                        "input_topology": "video-reference",
                        "modules": ["long-form"],
                    },
                    "asset_inventory": {"complete": False, "items": []},
                    "asset_assignments": [],
                    "extend_context": {
                        "accepted_material": True,
                        "observed_end_state": "第一步结束状态",
                        "direction": "后",
                    },
                    "request_configuration": {
                        "ratio": "adaptive",
                        "duration": 6,
                    },
                },
            ]
        }
        plan = build_plan(source, decisions)
        self.assertEqual(len(plan["operations"]), 2)
        self.assertEqual(len(plan["prompt_units"]), 2)
        self.assertEqual(plan["prompt_units"][0]["operation_id"], "OP001")
        self.assertEqual(plan["prompt_units"][1]["operation_id"], "OP002")
        self.assertEqual(
            plan["prompt_units"][1]["depends_on_operation_id"], "OP001"
        )
        self.assertIn(
            "@OP001-output",
            plan["prompt_units"][1]["prompt_text"],
        )
        report = delivery.validate_prompt_plan(source, plan)
        self.assertEqual(report["status"], "PASS")

    def test_v2_blockout_video_routes_to_generate_not_edit(self) -> None:
        decisions = {
            "task": {
                "primary": "generate",
                "input_topology": "video-reference",
                "modules": ["blockout", "camera-reference"],
            },
            "asset_inventory": {
                "complete": True,
                "items": [
                    {
                        "tag": "@视频1",
                        "media_type": "video",
                        "available": True,
                    }
                ],
            },
            "asset_assignments": [
                {
                    "tag": "@视频1",
                    "target_entity": "白模运动骨架",
                    "role": "motion_reference",
                    "adopted_dimensions": ["动作路径", "运镜"],
                    "rejected_dimensions": ["白模外观", "制作标记"],
                    "applies_to_shot_ids": ["SH001"],
                    "user_mapped": True,
                }
            ],
        }
        plan = build_plan(make_source([4]), decisions)
        self.assertEqual(plan["task"]["primary"], "generate")
        self.assertEqual(plan["generation"]["mode"], "v2v")
        self.assertIn("白模运动骨架", plan["prompt_units"][0]["prompt_text"])

    def test_v2_audio_edit_keeps_visual_and_unmodified_audio_scope(self) -> None:
        decisions = {
            "task": {
                "primary": "edit",
                "input_topology": "multimodal",
                "modules": ["audio-edit"],
            },
            "asset_inventory": {
                "complete": True,
                "items": [
                    {
                        "tag": "@视频1",
                        "media_type": "video",
                        "available": True,
                        "core": True,
                    },
                    {
                        "tag": "@音频1",
                        "media_type": "audio",
                        "available": True,
                    },
                ],
            },
            "asset_assignments": [
                {
                    "tag": "@视频1",
                    "target_entity": "原视频",
                    "role": "edit_source",
                    "adopted_dimensions": ["全部画面", "口型时点", "时间线"],
                    "rejected_dimensions": [],
                    "applies_to_shot_ids": ["SH001"],
                    "user_mapped": True,
                },
                {
                    "tag": "@音频1",
                    "target_entity": "指定说话人",
                    "role": "audio_reference",
                    "adopted_dimensions": ["替换音色"],
                    "rejected_dimensions": ["其他人物声音", "环境声"],
                    "applies_to_shot_ids": ["SH001"],
                    "user_mapped": True,
                },
            ],
            "edit_scope": ["audio"],
            "edit_deltas": [
                {
                    "layer": "audio",
                    "instruction": "只替换指定说话人的音色",
                    "applies_to_shot_ids": ["SH001"],
                }
            ],
            "request_configuration": {"ratio": "adaptive", "duration": -1},
        }
        plan = build_plan(make_source([4]), decisions)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("只替换指定说话人的音色", prompt)
        self.assertIn("口型时点", prompt)
        self.assertIn("其他主体、场景、动作、镜头、时间线和声音保持原样", prompt)

    def test_v2_extend_preserves_direction_and_boundary_state(self) -> None:
        decisions = {
            "task": {
                "primary": "extend",
                "input_topology": "video-reference",
                "modules": ["long-form"],
            },
            "asset_inventory": {
                "complete": True,
                "items": [
                    {
                        "tag": "@视频1",
                        "media_type": "video",
                        "available": True,
                        "core": True,
                    }
                ],
            },
            "asset_assignments": [
                {
                    "tag": "@视频1",
                    "target_entity": "延长源视频",
                    "role": "extension_source",
                    "adopted_dimensions": ["结束画面", "运动趋势", "声音状态"],
                    "rejected_dimensions": [],
                    "applies_to_shot_ids": ["SH001"],
                    "user_mapped": True,
                }
            ],
            "extend_context": {
                "accepted_material": True,
                "observed_end_state": "人物右脚落地、环境声持续",
                "boundary_state": "人物右脚落地、环境声持续",
                "direction": "后",
                "motion_trend": "人物继续向前行走",
                "audio_state": "环境声连续",
                "single_instance": "人物始终只有一个实例",
            },
            "request_configuration": {"ratio": "adaptive", "duration": 6},
        }
        plan = build_plan(make_source([4]), decisions)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("向后连续延长", prompt)
        self.assertIn("人物继续向前行走", prompt)
        self.assertIn("人物始终只有一个实例", prompt)
        self.assertIn("不改写原视频", prompt)

    def test_v2_unknown_task_blocks_compilation(self) -> None:
        plan = build_plan(
            make_source([4]),
            {
                "task": {
                    "primary": "remix",
                    "input_topology": "text-only",
                    "modules": [],
                }
            },
        )
        self.assertIn("TASK_CONTRACT_INVALID", issue_codes(plan))
        self.assertFalse(plan["submission_ready"])
        self.assertEqual(plan["prompt_units"], [])

    def test_v2_legacy_modes_convert_deterministically(self) -> None:
        expected = {
            "t2v": ("generate", "text-only"),
            "i2v": ("generate", "image-reference"),
            "v2v": ("generate", "video-reference"),
            "r2v": ("generate", "multimodal"),
            "flf2v": ("generate", "image-reference"),
            "edit": ("edit", "video-reference"),
            "extend": ("extend", "video-reference"),
        }
        for mode, (primary, topology) in expected.items():
            with self.subTest(mode=mode):
                task = delivery._task_from_legacy_mode(mode)
                self.assertEqual(task["primary"], primary)
                self.assertEqual(task["input_topology"], topology)

    def test_v2_api_duration_does_not_create_prompt_timestamps(self) -> None:
        plan = build_plan(
            make_source([None]),
            {
                "request_configuration": {
                    "ratio": "16:9",
                    "duration": 12,
                    "output_format": "mp4",
                }
            },
        )
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("Cut 1｜顺序阶段", prompt)
        self.assertNotIn("12", prompt)
        self.assertNotIn("总时长", prompt)

    def test_v2_incomplete_inventory_never_invents_unused_assets(self) -> None:
        decisions = {
            "asset_inventory": {
                "complete": False,
                "items": [
                    {
                        "tag": "@未映射图片",
                        "media_type": "image",
                        "available": True,
                    }
                ],
            }
        }
        plan = build_plan(make_source([4]), decisions)
        self.assertEqual(plan["unused_assets"], [])
        self.assertNotIn(
            "【未采用素材】", plan["prompt_units"][0]["prompt_text"]
        )

    def test_v2_all_official_asset_limits_set_submission_not_ready(self) -> None:
        cases = {
            "image-dimension": [
                {
                    "tag": "@图1",
                    "media_type": "image",
                    "available": True,
                    "width": 4097,
                    "height": 2160,
                }
            ],
            "video-count": [
                {
                    "tag": f"@视频{index}",
                    "media_type": "video",
                    "available": True,
                    "duration_seconds": 1,
                }
                for index in range(11)
            ],
            "video-duration": [
                {
                    "tag": "@视频长片",
                    "media_type": "video",
                    "available": True,
                    "duration_seconds": 31,
                }
            ],
            "audio-count": [
                {
                    "tag": f"@音频{index}",
                    "media_type": "audio",
                    "available": True,
                    "duration_seconds": 1,
                }
                for index in range(11)
            ],
            "audio-duration": [
                {
                    "tag": "@音频长段",
                    "media_type": "audio",
                    "available": True,
                    "duration_seconds": 31,
                }
            ],
            "total-count": [
                {
                    "tag": f"@混合{index}",
                    "media_type": "image" if index < 30 else "video",
                    "available": True,
                }
                for index in range(51)
            ],
        }
        for label, items in cases.items():
            with self.subTest(label=label):
                plan = build_plan(
                    make_source([4]),
                    {
                        "asset_inventory": {
                            "complete": True,
                            "items": items,
                        }
                    },
                )
                self.assertFalse(plan["submission_ready"])
                self.assertIn("ASSET_LIMIT_EXCEEDED", issue_codes(plan))
                self.assertTrue(plan["prompt_units"][0]["prompt_text"])

    def test_v2_same_asset_can_hold_compatible_roles_for_one_entity(self) -> None:
        decisions = {
            "task": {
                "primary": "generate",
                "input_topology": "image-reference",
                "modules": ["first-frame", "multi-reference"],
            },
            "asset_inventory": {
                "complete": True,
                "items": [
                    {
                        "tag": "@林首帧",
                        "media_type": "image",
                        "available": True,
                    }
                ],
            },
            "asset_assignments": [
                {
                    "tag": "@林首帧",
                    "target_entity": "林",
                    "role": role,
                    "adopted_dimensions": dimensions,
                    "rejected_dimensions": [],
                    "applies_to_shot_ids": ["SH001"],
                    "user_mapped": True,
                }
                for role, dimensions in (
                    ("first_frame", ["首帧构图"]),
                    ("subject_identity", ["五官", "发型"]),
                )
            ],
        }
        plan = build_plan(make_source([4]), decisions)
        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(len(plan["generation"]["reference_role_map"]), 2)
        self.assertEqual(
            plan["generation"]["available_reference_tags"], ["@林首帧"]
        )
        self.assertIn("@林首帧作为首帧。", plan["prompt_units"][0]["prompt_text"])

    def test_v2_explicit_user_mapping_allows_declared_cross_entity_reuse(self) -> None:
        decisions = {
            "task": {
                "primary": "generate",
                "input_topology": "image-reference",
                "modules": ["multi-reference"],
            },
            "asset_inventory": {
                "complete": True,
                "items": [
                    {
                        "tag": "@双人合照",
                        "media_type": "image",
                        "available": True,
                    }
                ],
            },
            "asset_assignments": [
                {
                    "tag": "@双人合照",
                    "target_entity": target,
                    "role": "subject_identity",
                    "adopted_dimensions": ["身份"],
                    "rejected_dimensions": [],
                    "applies_to_shot_ids": ["SH001"],
                    "user_mapped": True,
                }
                for target in ("林", "周")
            ],
        }
        plan = build_plan(make_source([4]), decisions)
        self.assertNotIn("ASSET_CARDINALITY_CONFLICT", issue_codes(plan))
        self.assertEqual(plan["mapping_confidence"], "high")

    def test_v2_bare_asset_id_is_rejected_from_prompt(self) -> None:
        source = make_source([4])
        source["shots"][0]["rendered_shot_description"] = (
            "人物查看 asset_id_abcdef 后转身。"
        )
        source["shots"][0]["blocking"] = [
            {"subject": "人物", "action": "查看 asset_id_abcdef"}
        ]
        source["shots"][0]["performance"]["visible_behavior"] = []
        plan = build_plan(source)
        self.assertIn("PROMPT_MODEL_METADATA_LEAK", issue_codes(plan))
        self.assertEqual(plan["validation"]["status"], "PARTIAL")

    def test_v2_no_source_dialogue_means_no_invented_dialogue(self) -> None:
        source = make_source([4])
        source["shots"][0]["dialogue"] = []
        plan = build_plan(source)
        self.assertEqual(plan["dialogue_ledger"], [])
        self.assertNotIn("：“", plan["prompt_units"][0]["prompt_text"])

    def test_v2_audio_assignment_binds_to_exact_dialogue_speaker(self) -> None:
        source = make_source([4])
        source["shots"][0]["dialogue"] = [
            {"speaker": "林", "text": "原句"}
        ]
        decisions = {
            "task": {
                "primary": "generate",
                "input_topology": "audio-reference",
                "modules": [],
            },
            "asset_inventory": {
                "complete": True,
                "items": [
                    {
                        "tag": "@林音色",
                        "media_type": "audio",
                        "available": True,
                    }
                ],
            },
            "asset_assignments": [
                {
                    "tag": "@林音色",
                    "target_entity": "林",
                    "role": "audio_reference",
                    "adopted_dimensions": ["音色"],
                    "rejected_dimensions": [],
                    "applies_to_shot_ids": ["SH001"],
                    "user_mapped": True,
                }
            ],
        }
        plan = build_plan(source, decisions)
        self.assertEqual(
            plan["dialogue_ledger"][0]["bound_asset_tags"], ["@林音色"]
        )
        self.assertIn("原句", plan["prompt_units"][0]["prompt_text"])

    def test_v2_request_configuration_validates_all_public_fields(self) -> None:
        plan = build_plan(
            make_source([4]),
            {
                "request_configuration": {
                    "model_id": "wrong-model",
                    "ratio": "2:1",
                    "duration": 31,
                    "output_format": "avi",
                }
            },
        )
        self.assertFalse(plan["submission_ready"])
        self.assertIn("MODEL_ID_MISMATCH", issue_codes(plan))
        self.assertIn("REQUEST_PARAMETER_CONFLICT", issue_codes(plan))
        prompt = plan["prompt_units"][0]["prompt_text"]
        for leaked in ("wrong-model", "2:1", "31", "avi"):
            self.assertNotIn(leaked, prompt)

    def test_v2_edit_and_extend_require_exactly_one_master(self) -> None:
        for primary, role in (
            ("edit", "edit_source"),
            ("extend", "extension_source"),
        ):
            with self.subTest(primary=primary):
                decisions = {
                    "task": {
                        "primary": primary,
                        "input_topology": "video-reference",
                        "modules": [],
                    },
                    "asset_inventory": {
                        "complete": True,
                        "items": [
                            {
                                "tag": tag,
                                "media_type": "video",
                                "available": True,
                                "core": True,
                            }
                            for tag in ("@母版A", "@母版B")
                        ],
                    },
                    "asset_assignments": [
                        {
                            "tag": tag,
                            "target_entity": "原视频",
                            "role": role,
                            "adopted_dimensions": ["时间线"],
                            "rejected_dimensions": [],
                            "applies_to_shot_ids": ["SH001"],
                            "user_mapped": True,
                        }
                        for tag in ("@母版A", "@母版B")
                    ],
                    "edit_scope": ["lighting"],
                    "edit_deltas": [
                        {
                            "layer": "lighting",
                            "instruction": "只改主光",
                            "applies_to_shot_ids": ["SH001"],
                        }
                    ],
                    "extend_context": {
                        "accepted_material": True,
                        "observed_end_state": "原片结束状态",
                    },
                }
                plan = build_plan(make_source([4]), decisions)
                self.assertIn("MODE_UNIT_REFERENCE_INVALID", issue_codes(plan))
                self.assertEqual(plan["prompt_units"][0]["prompt_text"], "")

    def test_v2_four_file_package_is_deterministic(self) -> None:
        source = make_source([4, 5])
        decisions = grouping_decisions(source)
        plan_a, artifacts_a = build_package(
            source, decisions=decisions
        )
        plan_b, artifacts_b = build_package(
            source, decisions=decisions
        )
        self.assertEqual(plan_a, plan_b)
        self.assertEqual(artifacts_a, artifacts_b)
        delivery.write_delivery_package(self.output_dir, artifacts_a)
        report = delivery.validate_delivery_package(
            source,
            self.output_dir,
            delivery_slug=plan_a["delivery"]["slug"],
        )
        self.assertEqual(report["status"], "PASS")

    def test_real_director_v2_pass_fixture_handoff(self) -> None:
        configured_root = os.environ.get("SU_FENJINGSKILL_ROOT")
        director_root = (
            Path(configured_root)
            if configured_root
            else next(
                path
                for path in (
                    Path.cwd() / "su-fenjingskill-v2.5.6",
                    Path.home()
                    / "Documents"
                    / "Test"
                    / "su-fenjingskill-v2.5.6",
                )
                if path.is_dir()
            )
        )
        test_path = director_root / "scripts" / "test_storyboard_delivery.py"
        if not test_path.is_file():
            self.fail(
                "真实 su-fenjingskill sibling fixture 缺失；"
                "不能把交接测试静默跳过。"
            )
        spec = importlib.util.spec_from_file_location(
            "su_promptskill_cross_director_fixture", test_path
        )
        if spec is None or spec.loader is None:
            self.fail("Unable to load director fixture")
        director_tests = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(director_tests)
        draft = director_tests.valid_draft()
        draft["scenes"][0]["initial_continuity"]["characters"][1][
            "state"
        ] = "手部放松"
        draft["shots"][1]["continuity_updates"].append(
            {
                "entity_type": "character",
                "entity": "周",
                "field": "state",
                "from": "手部放松",
                "to": "指节发白",
                "evidence_fact_ids": ["F003"],
            }
        )
        director_tests.refresh_confirmation_digests(draft)
        source = director_tests.delivery.prepare_data(draft)
        upstream_validation = director_tests.delivery.validate_data(source)
        self.assertEqual(upstream_validation.errors, [])

        snapshot = copy.deepcopy(source)
        source_hash = delivery.sha256_json(source)
        source_ids = [shot["shot_id"] for shot in source["shots"]]
        source_durations = [
            shot["duration_seconds"] for shot in source["shots"]
        ]
        expected_scene = source["scenes"][0]["scene"]
        normalized, _ = delivery.normalize_input(source)
        plan = build_legacy_plan(source)

        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(source, snapshot)
        self.assertEqual(delivery.sha256_json(source), source_hash)
        self.assertEqual(
            [shot["source_shot_id"] for shot in normalized["shots"]],
            source_ids,
        )
        self.assertEqual(
            [shot["duration_seconds"] for shot in normalized["shots"]],
            source_durations,
        )
        self.assertTrue(
            all(
                shot["scene_context"].get("scene") == expected_scene
                for shot in normalized["shots"]
            )
        )
        self.assertTrue(
            any(shot["visible_props"] for shot in normalized["shots"])
        )
        self.assertTrue(
            all(shot["end_state"] for shot in normalized["shots"])
        )
        prompt_text = "\n".join(
            unit["prompt_text"] for unit in plan["prompt_units"]
        )
        self.assertIn(expected_scene, prompt_text)
        self.assertIn("钥匙", prompt_text)
        self.assertEqual(
            json.dumps(source, ensure_ascii=False).count("指节发白"),
            1,
        )
        continuity_unit = next(
            unit
            for unit in plan["prompt_units"]
            if unit["source_shot_ids"] == ["SH002"]
        )
        self.assertIn("指节发白", continuity_unit["prompt_text"])
        self.assertNotIn(
            "指节发白",
            next(
                unit
                for unit in plan["prompt_units"]
                if unit["source_shot_ids"] == ["SH001"]
            )["prompt_text"],
        )
        self.assertEqual(
            [
                cut["source_shot_id"]
                for unit in plan["prompt_units"]
                for cut in unit["timeline"]
            ],
            source_ids,
        )
        self.assertEqual(
            plan["source"]["observed_content_hash"],
            delivery.source_observed_hash(source),
        )

    def test_v204_visual_style_prompt_is_fully_removed(self) -> None:
        source = make_source([4])
        plan = delivery.build_prompt_plan(source)
        prompt = plan["prompt_units"][0]["prompt_text"]
        blocks = plan["prompt_units"][0]["prompt_blocks"]
        self.assertNotIn("画面风格", prompt)
        self.assertNotIn("电影风格", prompt)
        self.assertNotIn("style_binding", prompt)
        self.assertNotIn("external_style", [block["kind"] for block in blocks])
        self.assertNotIn("【参考素材职责】", prompt)
        self.assertIn("【声音与台词】", prompt)
        self.assertIn(delivery.NO_SOURCE_SOUND_LINE, prompt)
        self.assertNotIn("背景音乐", prompt)
        self.assertNotIn("字幕", prompt)
        self.assertNotIn("禁言", prompt)
        self.assertNotIn("口型", prompt)
        self.assertTrue(prompt.split("\n\n")[-1].startswith("【保持一致】"))
        for internal_name in (
            "asset_binding",
            "consistency_contract",
        ):
            self.assertNotIn(internal_name, prompt)
        self.assertTrue(plan["submission_ready"])
        self.assertEqual(plan["validation"]["status"], "PASS")

    def test_v204_asset_module_uses_only_explicit_mapping(self) -> None:
        source = make_source([4])
        decisions = {
            "asset_binding": {"state": "mapped"},
            "asset_inventory": {
                "complete": True,
                "items": [
                    {
                        "tag": "<<<image_1>>>",
                        "media_type": "image",
                        "available": True,
                    },
                    {
                        "tag": "<<<image_unused>>>",
                        "media_type": "image",
                        "available": True,
                    },
                ],
            },
            "asset_assignments": [
                {
                    "tag": "<<<image_1>>>",
                    "target_entity": "占星师",
                    "role": "subject_identity",
                    "adopted_dimensions": ["身份", "完整面容", "服装"],
                    "rejected_dimensions": ["海报文字", "平面排版"],
                    "applies_to_shot_ids": ["*"],
                    "user_mapped": True,
                }
            ],
        }
        plan = delivery.build_prompt_plan(source, decisions=decisions)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("【参考素材职责】", prompt)
        self.assertIn(
            "<<<image_1>>>用于占星师的身份、完整面容、服装，"
            "不采用海报文字、平面排版。",
            prompt,
        )
        self.assertNotIn("职责为", prompt)
        self.assertNotIn("<<<image_unused>>>", prompt)
        self.assertNotIn("【未采用素材】", prompt)
        self.assertEqual(plan["generation"]["mode"], "i2v")
        self.assertEqual(plan["asset_binding"]["state"], "mapped")
        self.assertEqual(plan["validation"]["status"], "PASS")

    def test_v204_explicit_mapped_asset_contract_must_be_valid(self) -> None:
        with self.assertRaisesRegex(
            delivery.AssetBindingError, "ASSET_BINDING_INVALID"
        ):
            delivery.build_prompt_plan(
                make_source([4]),
                decisions={
                    "asset_binding": {"state": "mapped"},
                },
            )

    def test_v204_single_cut_dialogue_is_not_repeated_in_sound_ledger(self) -> None:
        source = make_source(
            [4],
        )
        source["shots"][0]["dialogue"] = [
            {
                "speaker": "人物",
                "text": "你来了。",
                "position": "画内",
            }
        ]
        plan = build_plan(source)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertEqual(prompt.count("你来了。"), 1)
        self.assertIn("【声音与台词】", prompt)
        self.assertIn(delivery.NO_SOURCE_SOUND_LINE, prompt)
        self.assertEqual(plan["validation"]["status"], "PASS")

    def test_v204_source_sound_facts_are_restored_into_their_cut(self) -> None:
        source = make_source([4])
        source["beats"] = [
            {
                "beat_id": "B001",
                "facts": [
                    {
                        "fact_id": "F-SOUND",
                        "type": "reality",
                        "text": "拐角处传来金属撞击与低吼。",
                    }
                ],
            }
        ]
        source["shots"][0]["covered_fact_ids"] = ["F-SOUND"]
        normalized, _ = delivery.normalize_input(source)
        self.assertEqual(
            normalized["shots"][0]["audio"],
            ["拐角处传来金属撞击与低吼。"],
        )
        plan = build_plan(source)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("声音：拐角处传来金属撞击与低吼。", prompt)
        self.assertIn("【声音与台词】", prompt)
        self.assertIn(
            "Cut 1声音：拐角处传来金属撞击与低吼。", prompt
        )

    def test_v204_real_ep01_recovers_non_dialogue_sound_cues(self) -> None:
        source_path = (
            Path.home()
            / "Documents"
            / "Test"
            / "Project-003-12huashen-ep01-storyboard"
            / "outputs"
            / "12huashen-ep01"
            / "12huashen-ep01-shot-data.json"
        )
        source = json.loads(source_path.read_text(encoding="utf-8"))
        normalized, _ = delivery.normalize_input(source)
        by_id = {
            shot["source_shot_id"]: shot for shot in normalized["shots"]
        }
        self.assertIn(
            "背景音里，下水道深处传来一声低沉的震动。",
            by_id["SH016"]["audio"],
        )
        self.assertIn(
            "拐角处传来爬行的声响。",
            by_id["SH023"]["audio"],
        )

    def test_v204_real_ep01_xlsx_rows_fit_complete_prompt_cells(self) -> None:
        project_root = (
            Path.home()
            / "Documents"
            / "Test"
            / "Project-003-12huashen-ep01-storyboard"
        )
        source = json.loads(
            (
                project_root
                / "outputs"
                / "12huashen-ep01"
                / "12huashen-ep01-shot-data.json"
            ).read_text(encoding="utf-8")
        )
        decisions = json.loads(
            (
                project_root
                / "temp"
                / "12huashen-ep01-grouping-review-v203.json"
            ).read_text(encoding="utf-8")
        )
        plan, artifacts = build_package(source, decisions=decisions)
        xlsx_payload = artifacts[plan["delivery"]["files"]["xlsx"]]
        rows = delivery.parse_prompt_table_xlsx(xlsx_payload)
        layout = delivery.inspect_prompt_table_xlsx_layout(xlsx_payload)
        width = int(layout["prompt_column_width"])
        self.assertEqual(len(rows), len(plan["prompt_units"]))
        self.assertEqual(len({row[0] for row in rows}), len(rows))
        for index, (row, unit) in enumerate(
            zip(rows, plan["prompt_units"]), start=1
        ):
            required = delivery._xlsx_row_height_for_row(
                row, width
            )
            self.assertGreaterEqual(layout["row_heights"][index], required)
            self.assertEqual(row[3], unit["prompt_text"])

    def test_v204_cross_cut_dialogue_extends_stable_sound_ledger(self) -> None:
        source = make_source([4, 4])
        source["shots"][0]["dialogue"] = [
            {"speaker": "人物", "text": "第一句。", "position": "画内"}
        ]
        source["shots"][1]["dialogue"] = [
            {"speaker": "人物", "text": "第二句。", "position": "画外"}
        ]
        plan = build_plan(
            source,
            grouping_decisions(source, [["SH001", "SH002"]]),
        )
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("【声音与台词】", prompt)
        self.assertNotIn("Cut 1（画内）：人物：“第一句。”", prompt)
        self.assertNotIn("Cut 2（画外）：人物：“第二句。”", prompt)
        self.assertIn(
            "声音关系：人物为画外声，适用Cut 2。", prompt
        )
        self.assertEqual(prompt.count("第一句。"), 1)
        self.assertEqual(prompt.count("第二句。"), 1)
        self.assertEqual(plan["validation"]["status"], "PASS")

    def test_v204_boundary_handoff_requires_matching_source_states(self) -> None:
        source = make_source([4, 4])
        source["shots"][0]["camera"]["end_frame"] = "人物右手停在桌沿。"
        source["shots"][0]["end_state"] = ["人物右手停在桌沿。"]
        source["shots"][1]["camera"]["start_frame"] = "人物右手停在桌沿。"
        plan = build_plan(
            source,
            grouping_decisions(source, [["SH001", "SH002"]]),
        )
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn(
            "承接 Cut 1 的人物右手停在桌沿。", prompt
        )

    def test_v204_seedance20_and_generic_keep_v203_prompt_behavior(self) -> None:
        global_path = (
            Path.home()
            / ".codex"
            / "skills"
            / "su-promptskill"
            / "scripts"
            / "prompt_delivery.py"
        )
        spec = importlib.util.spec_from_file_location(
            "su_promptskill_v203_compat", global_path
        )
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        source = make_source([4])
        for profile_id in ("seedance-2.0-default", "generic-video"):
            with self.subTest(profile_id=profile_id):
                baseline_profile = baseline.resolve_model_profile(profile_id)
                candidate_profile = delivery.resolve_model_profile(profile_id)
                baseline_prompt = baseline.build_prompt_plan(
                    source, model_profile=baseline_profile
                )["prompt_units"][0]["prompt_text"]
                candidate_prompt = delivery.build_prompt_plan(
                    source,
                    model_profile=candidate_profile,
                )["prompt_units"][0]["prompt_text"]
                self.assertEqual(candidate_prompt, baseline_prompt)

    def test_v204_long_nine_cut_xlsx_layout_and_reconstruction(self) -> None:
        source = make_source([3] * 9)
        for shot in source["shots"]:
            shot["performance"]["visible_behavior"] = [
                "人物以克制动作完成当前阶段，衣袖与发丝按惯性自然回落。"
                * 4
            ]
        ids = [f"SH{index:03d}" for index in range(1, 10)]
        decisions = grouping_decisions(source, [ids])
        plan_a, artifacts_a = build_package(source, decisions=decisions)
        plan_b, artifacts_b = build_package(source, decisions=decisions)
        self.assertEqual(plan_a, plan_b)
        self.assertEqual(artifacts_a, artifacts_b)
        self.assertEqual(len(plan_a["prompt_units"][0]["timeline"]), 9)
        files = plan_a["delivery"]["files"]
        xlsx_payload = artifacts_a[files["xlsx"]]
        rows = delivery.parse_prompt_table_xlsx(xlsx_payload)
        layout = delivery.inspect_prompt_table_xlsx_layout(xlsx_payload)
        self.assertEqual(layout["sheet_names"], ["Prompt Table"])
        self.assertGreaterEqual(
            layout["prompt_column_width"], delivery.XLSX_PROMPT_WIDTH_MIN
        )
        self.assertLessEqual(
            layout["prompt_column_width"], delivery.XLSX_PROMPT_WIDTH_MAX
        )
        self.assertTrue(
            all(
                height <= float(delivery.XLSX_ROW_HEIGHT_LIMIT)
                for height in layout["row_heights"]
            )
        )
        self.assertTrue(layout["header_frozen"])
        self.assertTrue(layout["auto_filter"])
        self.assertEqual(
            delivery.reconstruct_prompt_texts_from_xlsx_rows(rows),
            {"PU001": plan_a["prompt_units"][0]["prompt_text"]},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "PU001")
        self.assertEqual(rows[0][1], "、".join(ids))
        self.assertEqual(rows[0][2], "27")
        self.assertEqual(rows[0][3], plan_a["prompt_units"][0]["prompt_text"])

    def test_v204_xlsx_writes_each_prompt_unit_exactly_once(self) -> None:
        source = make_source([4, 4])
        plan, artifacts = build_package(
            source,
            decisions=grouping_decisions(source),
        )
        xlsx_payload = artifacts[plan["delivery"]["files"]["xlsx"]]
        rows = delivery.parse_prompt_table_xlsx(xlsx_payload)
        self.assertEqual(len(rows), len(plan["prompt_units"]))
        self.assertEqual(
            [row[0] for row in rows],
            [unit["prompt_unit_id"] for unit in plan["prompt_units"]],
        )
        self.assertEqual(len({row[0] for row in rows}), len(rows))
        for row, unit in zip(rows, plan["prompt_units"]):
            self.assertEqual(
                row[1], "、".join(unit["source_shot_ids"])
            )
            self.assertEqual(row[3], unit["prompt_text"])

    def test_v204_real_ep01_without_grouping_creates_no_output(self) -> None:
        configured_source = os.environ.get("SU_PROMPT_EP01_SOURCE")
        source_path = (
            Path(configured_source)
            if configured_source
            else Path.home()
            / "Documents"
            / "Test"
            / "Project-003-12huashen-ep01-storyboard"
            / "outputs"
            / "12huashen-ep01"
            / "12huashen-ep01-shot-data.json"
        )
        self.assertTrue(source_path.is_file())
        output_dir = self.output_dir / "ep01-grouping-blocked"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = delivery.main(
                [
                    "build",
                    "--input",
                    str(source_path),
                    "--output-dir",
                    str(output_dir),
                ]
            )
        self.assertEqual(result, 2)
        self.assertIn("GROUPING_REVIEW_REQUIRED", stderr.getvalue())
        self.assertFalse(output_dir.exists())

    def test_split_environment_accepts_current_director_camera_marker(self):
        shot = {
            "rendered_shot_description": (
                "【大全景→中景｜平视｜跟随】\n"
                "【画面内容】漱玉斋·黄昏·内景。"
                "机位设在窗台与调香桌之间，机位与人物视线近似等高；"
                "陆听澜完成调香。"
            ),
            "camera": {"composition": ""},
        }
        environment, action = delivery._split_environment_and_action(shot)
        self.assertEqual(environment, "漱玉斋·黄昏·内景")
        self.assertEqual(action, "陆听澜完成调香。")

    def test_structured_camera_owns_punctuation_variant_boundaries(self):
        shot = {
            "source_shot_id": "SH001",
            "camera": {
                "position": "窗台与调香桌之间",
                "start_frame": "半枯桂花树建立日常空间。",
                "end_frame": "陆听澜完成调香。",
                "movement": "跟随",
                "movement_plan": {
                    "trigger": "主体因“半枯桂花树建立日常空间”开始位移",
                    "end_condition": "人物完成“陆听澜完成调香”并稳定时停止",
                    "hold_reason": (
                        "保护“半枯桂花树建立日常空间”至"
                        "“陆听澜完成调香”的连续性"
                    ),
                },
            },
            "blocking": [],
            "visible_behavior": [],
            "dialogue": [],
            "end_state": ["陆听澜完成调香。"],
            "rendered_shot_description": "",
        }
        parts = []
        delivery._structured_t2v_prompt_parts(parts, shot)
        prompt = "；".join(parts)
        self.assertEqual(
            delivery._normalized_occurrences(
                prompt, "半枯桂花树建立日常空间。"
            ),
            1,
        )
        self.assertEqual(
            delivery._normalized_occurrences(prompt, "陆听澜完成调香。"),
            1,
        )
        self.assertIn("在起始动作发生时启动", prompt)
        self.assertIn("主要状态形成时停止", prompt)


if __name__ == "__main__":
    unittest.main()
