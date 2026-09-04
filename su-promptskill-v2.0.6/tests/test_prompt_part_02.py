"""su-promptskill regression partition 02."""

from .support import *

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Discovered by scripts/test_prompt_delivery.py."


class PromptDeliveryTestsPart02(BasePromptDeliveryTests):
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
        self.assertEqual(plan["contract_version"], "2.0.6")
        self.assertEqual(plan["skill"]["version"], "2.0.6")
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
        self.assertIn("按既定 Cut 顺序推进。收束画面：", prompt)
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
