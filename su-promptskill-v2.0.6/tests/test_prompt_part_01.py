"""su-promptskill regression partition 01."""

from .support import *

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Discovered by scripts/test_prompt_delivery.py."


class PromptDeliveryTestsPart01(BasePromptDeliveryTests):
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
        cut_block = delivery._cut_prompt_block(prompt, "Cut 1")
        self.assertEqual(cut_block.count("人物抬眼。"), 1)
        self.assertEqual(cut_block.count("人物转身。"), 1)
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
        self.assertIn("在触发动作时开始固定观察", prompt)
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
