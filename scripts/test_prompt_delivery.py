#!/usr/bin/env python3
"""Regression tests for su-promptskill prompt-plan/1.0.0 delivery."""

from __future__ import annotations

import copy
import importlib.util
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


def group_decision(shot_ids: list[str]) -> dict[str, object]:
    return {
        "source_shot_ids": shot_ids,
        "grouping_reason": "相邻镜头处于同一时空并延续同一动作与叙事意图。",
        "compatibility": {
            "space": True,
            "time": True,
            "reality_layer": True,
            "action_continuity": True,
            "narrative_intent": True,
        },
    }


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


class PromptDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="su-promptskill-test-"
        )
        self.output_dir = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

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
                plan = delivery.build_prompt_plan(
                    source, {"groups": [group_decision(ids)]}
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

    def test_over_ten_defaults_to_single_but_ten_can_group(self) -> None:
        source = make_source([11, 4])
        plan = delivery.build_prompt_plan(
            source,
            {"groups": [group_decision(["SH001", "SH002"])]},
        )
        self.assertEqual(
            [unit["source_shot_ids"] for unit in plan["prompt_units"]],
            [["SH001"], ["SH002"]],
        )
        self.assertEqual(
            plan["prompt_units"][0]["standalone_reason"],
            "source_duration_gt_10_seconds",
        )
        self.assertIn("GROUP_DECISION_INVALID", issue_codes(plan))

        ten_source = make_source([10, 5])
        ten_plan = delivery.build_prompt_plan(
            ten_source,
            {"groups": [group_decision(["SH001", "SH002"])]},
        )
        self.assertEqual(
            ten_plan["prompt_units"][0]["total_duration_seconds"], 15
        )

    def test_short_tail_is_valid_and_never_uses_grouping_blocked(self) -> None:
        plan = delivery.build_prompt_plan(make_source([3]))
        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(len(plan["prompt_units"]), 1)
        self.assertEqual(
            plan["prompt_units"][0]["total_duration_seconds"], 3
        )
        self.assertNotIn("PROMPT_GROUPING_BLOCKED", issue_codes(plan))

    def test_group_total_over_fifteen_is_rejected(self) -> None:
        for durations in ([8, 8], [15, 3], [12, 6]):
            with self.subTest(durations=durations):
                plan = delivery.build_prompt_plan(
                    make_source(durations),
                    {"groups": [group_decision(["SH001", "SH002"])]},
                )
                self.assertEqual(len(plan["prompt_units"]), 2)
                self.assertTrue(
                    all(
                        unit["total_duration_seconds"] <= 15
                        for unit in plan["prompt_units"]
                    )
                )
                self.assertIn(
                    "GROUP_DECISION_INVALID", issue_codes(plan)
                )

    def test_same_space_dialogue_coverage_can_group_across_view_changes(self) -> None:
        source = make_source([3, 3, 3, 3])
        sizes = ("近景", "中景", "特写", "全景")
        for shot, size in zip(source["shots"], sizes):
            shot["camera"]["shot_size"] = size
            shot["dialogue"] = [
                {"speaker": shot["shot_id"], "text": f"{shot['shot_id']}回应"}
            ]
        plan = delivery.build_prompt_plan(
            source,
            {
                "groups": [
                    group_decision(["SH001", "SH002", "SH003", "SH004"])
                ]
            },
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
        plan = delivery.build_prompt_plan(
            source,
            {"groups": [group_decision(["SH002", "SH003"])]},
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
        plan = delivery.build_prompt_plan(
            make_source([4, 4, 4]),
            {
                "groups": [
                    group_decision(["SH001", "SH002", "SH003"])
                ]
            },
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
        plan = delivery.build_prompt_plan(make_source([4]))
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("Cut 1 : 0-4S", prompt)
        self.assertNotIn("来源镜头 SH001", prompt)

    def test_integer_duration_keeps_trailing_zero(self) -> None:
        plan = delivery.build_prompt_plan(
            make_source([5, 5]),
            {"groups": [group_decision(["SH001", "SH002"])]},
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
        plan = delivery.build_prompt_plan(source)
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("场景：赤狐岭 日 外，晨雾覆盖草坡。", prompt)
        self.assertIn(
            "构图：【微仰视，大全景，极缓慢推进】晨雾横过草坡，人物立于树下。",
            prompt,
        )
        self.assertIn(
            "画面内容：摄影机位于草坡低处，朝向树下人物",
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
        plan = delivery.build_prompt_plan(make_source([None]))
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
        prompt = delivery.build_prompt_plan(source)[
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
        prompt = delivery.build_prompt_plan(source)[
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
        plan = delivery.build_prompt_plan(source)
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
        plan = delivery.build_prompt_plan(source, decisions)
        self.assertEqual(plan["validation"]["status"], "PARTIAL")
        self.assertIn("DOWNSTREAM_ANTI_SLOP", issue_codes(plan))
        self.assertNotIn(
            "人物震撼地睁大双眼",
            plan["prompt_units"][0]["prompt_text"],
        )

    def test_validation_rejects_manually_added_downstream_slop(self) -> None:
        source = make_source([4])
        plan = delivery.build_prompt_plan(source)
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
        plan = delivery.build_prompt_plan(source, decisions)
        self.assertEqual(normalized["shots"][0]["visible_behavior"], behavior)
        self.assertIn(behavior[0], plan["prompt_units"][0]["prompt_text"])
        self.assertNotIn("她眨眼一次", plan["prompt_units"][0]["prompt_text"])
        self.assertIn(
            "EMOTION_VISUALIZATION_FORBIDDEN", issue_codes(plan)
        )

    def test_unknown_mode_is_a_global_gate(self) -> None:
        source = make_source([4, 4])
        plan = delivery.build_prompt_plan(
            source,
            generation_decision("unknown", [], []),
        )
        self.assertTrue(plan["generation"]["global_blocked"])
        self.assertEqual(plan["prompt_units"], [])
        self.assertEqual(plan["validation"]["status"], "FAIL")

    def test_formal_upstream_v1_contract_runs(self) -> None:
        source = make_formal_source("1.0.0")
        plan, artifacts = delivery.build_delivery_package(source)
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
        plan, artifacts = delivery.build_delivery_package(source)
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
                plan = delivery.build_prompt_plan(source)
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

        plan, artifacts = delivery.build_delivery_package(source)

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
        plan = delivery.build_prompt_plan(source)
        self.assertEqual(plan["validation"]["status"], "FAIL")
        self.assertEqual(plan["prompt_units"], [])
        self.assertIn("SOURCE_HASH_MISMATCH", issue_codes(plan))

    def test_structured_source_missing_hash_does_not_block_compilation(self) -> None:
        source = make_formal_source("1.0.0")
        source["content_hash"] = ""
        plan = delivery.build_prompt_plan(source)
        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(len(plan["prompt_units"]), 1)
        self.assertNotIn("SOURCE_HASH_INVALID", issue_codes(plan))

    def test_declared_invalid_hash_blocks_prompt_compilation(self) -> None:
        source = make_formal_source("1.0.0")
        source["content_hash"] = "not-a-sha256"
        plan = delivery.build_prompt_plan(source)
        self.assertEqual(plan["validation"]["status"], "FAIL")
        self.assertEqual(plan["prompt_units"], [])
        self.assertIn("SOURCE_HASH_INVALID", issue_codes(plan))

    def test_unknown_source_mode_is_provenance_only(self) -> None:
        plan = delivery.build_prompt_plan(
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
                plan = delivery.build_prompt_plan(
                    make_source([4], source_mode=source_mode)
                )
                self.assertEqual(plan["validation"]["status"], "PASS")
                self.assertEqual(len(plan["prompt_units"]), 1)

    def test_explicit_local_mode_is_not_overridden_by_provenance(self) -> None:
        source = make_source([4], source_mode="partial_storyboard")
        source["contract_name"] = "prompt-source"
        source["contract_version"] = "1.0.0"
        plan = delivery.build_prompt_plan(source)
        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(plan["source"]["source_mode"], "partial_storyboard")

    def test_profile_unsupported_mode_is_a_global_gate(self) -> None:
        profile = delivery.resolve_model_profile("generic-video")
        profile["capabilities"]["supported_generation_modes"] = ["t2v"]
        plan = delivery.build_prompt_plan(
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
        plan = delivery.build_prompt_plan(make_source([4]), decisions)
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
        plan = delivery.build_prompt_plan(
            make_source([4]), decisions, profile
        )
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("img-7", prompt)
        self.assertNotIn("@Image7", prompt)
        self.assertNotIn("Runtime Custom", prompt)
        self.assertEqual(plan["validation"]["status"], "PASS")

    def test_model_profile_metadata_tamper_is_rejected(self) -> None:
        source = make_source([4])
        plan = delivery.build_prompt_plan(source)
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
        plan = delivery.build_prompt_plan(source, decisions)
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
        plan = delivery.build_prompt_plan(source, decisions)
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
        plan = delivery.build_prompt_plan(source, decisions)
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
                plan = delivery.build_prompt_plan(source, decisions)
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
        plan = delivery.build_prompt_plan(make_source([4]), decisions)
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
        flf_plan = delivery.build_prompt_plan(make_source([4]), flf)
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
        edit_plan = delivery.build_prompt_plan(make_source([4]), edit)
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
        extend_plan = delivery.build_prompt_plan(make_source([4]), extend)
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
                plan = delivery.build_prompt_plan(
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
        plan = delivery.build_prompt_plan(source, decisions)
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
        plan = delivery.build_prompt_plan(source)
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
        self.assertNotIn("钥匙停在桌面中央", prompt)
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
        plan = delivery.build_prompt_plan(source)
        self.assertIn("SCENE_CONTEXT_MISSING", issue_codes(plan))
        self.assertEqual(len(plan["prompt_units"]), 1)

    def test_plan_hash_removes_itself_before_single_hash(self) -> None:
        plan = delivery.build_prompt_plan(make_source([4]))
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
        plan, artifacts = delivery.build_delivery_package(source)
        second_plan, second_artifacts = delivery.build_delivery_package(source)
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
            rows,
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
        _, artifacts = delivery.build_delivery_package(source)
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
        plan = delivery.build_prompt_plan(source)
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
        plan = delivery.build_prompt_plan(source)
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
        plan, artifacts = delivery.build_delivery_package(source)
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
        plan = delivery.build_prompt_plan(source)
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
        plan = delivery.build_prompt_plan(source)
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

    def test_real_director_v2_pass_fixture_handoff(self) -> None:
        configured_root = os.environ.get("SU_FENJINGSKILL_ROOT")
        director_root = (
            Path(configured_root)
            if configured_root
            else SCRIPT_DIR.parent.parent / "su-fenjingskill"
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
        plan = delivery.build_prompt_plan(source)

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


if __name__ == "__main__":
    unittest.main()
