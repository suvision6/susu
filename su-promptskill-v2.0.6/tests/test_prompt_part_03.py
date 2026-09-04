"""su-promptskill regression partition 03."""

from .support import *

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Discovered by scripts/test_prompt_delivery.py."


class PromptDeliveryTestsPart03(BasePromptDeliveryTests):
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

    def test_real_director_v310_fixture_handoff(self) -> None:
        source = json.loads(CURRENT_DIRECTOR_FIXTURE.read_text(encoding="utf-8"))
        snapshot = copy.deepcopy(source)
        source_hash = delivery.sha256_json(source)
        normalized, issues = delivery.normalize_input(source)
        self.assertEqual(source, snapshot)
        self.assertEqual(delivery.sha256_json(source), source_hash)
        self.assertEqual(
            {issue["code"] for issue in issues if issue["severity"] == "ERROR"},
            set(),
        )
        self.assertTrue(
            all(
                shot["source_adapter"] == "director-shot-data-shape-v2"
                for shot in normalized["shots"]
            )
        )
        self.assertTrue(all(shot["subjects"] for shot in normalized["shots"]))
        self.assertTrue(all(shot["blocking"] for shot in normalized["shots"]))
        self.assertTrue(
            all(shot["visible_behavior"] for shot in normalized["shots"])
        )
        self.assertEqual(
            [item["text"] for shot in normalized["shots"] for item in shot["dialogue"]],
            ["我明天走。", "什么时候决定的？"],
        )
        self.assertTrue(
            all(
                all(not isinstance(item, dict) for item in shot["audio"])
                for shot in normalized["shots"]
            )
        )
        source_ids = [shot["shot_id"] for shot in source["shots"]]
        decisions = grouping_decisions(source, [source_ids])
        plan = build_plan(source, decisions)
        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(
            [
                cut["source_shot_id"]
                for unit in plan["prompt_units"]
                for cut in unit["timeline"]
            ],
            source_ids,
        )
        prompt = "\n".join(
            unit["prompt_text"] for unit in plan["prompt_units"]
        )
        self.assertEqual(prompt.count("我明天走。"), 1)
        self.assertEqual(prompt.count("什么时候决定的？"), 1)
        self.assertIn("林晓彤（画外）：\u201c我明天走。\u201d", prompt)
        self.assertIn("声音关系：林晓彤为画外声", prompt)

    def test_v205_director_shape_ignores_missing_or_unknown_provenance(self) -> None:
        fixture = json.loads(CURRENT_DIRECTOR_FIXTURE.read_text(encoding="utf-8"))
        variants = []

        missing = copy.deepcopy(fixture)
        for key in (
            "source_mode",
            "contract_name",
            "contract_version",
            "source_skill",
            "source_skill_version",
        ):
            missing.pop(key, None)
        missing.pop("content_hash", None)
        variants.append(missing)

        unknown = copy.deepcopy(fixture)
        unknown["contract_name"] = "future-director-contract"
        unknown["contract_version"] = "999.0.0"
        unknown["source_skill"] = "user-authored-storyboard-tool"
        unknown["source_skill_version"] = "future"
        unknown["source_mode"] = "future-structured-source"
        unknown.pop("content_hash", None)
        variants.append(unknown)

        for source in variants:
            with self.subTest(
                contract_name=source.get("contract_name"),
                source_skill=source.get("source_skill"),
            ):
                snapshot = copy.deepcopy(source)
                normalized, issues = delivery.normalize_input(source)
                self.assertEqual(source, snapshot)
                self.assertFalse(
                    {
                        issue["code"]
                        for issue in issues
                        if issue["severity"] == "ERROR"
                    }
                )
                self.assertTrue(
                    all(
                        shot["source_adapter"]
                        == "director-shot-data-shape-v2"
                        for shot in normalized["shots"]
                    )
                )
                self.assertTrue(all(shot["subjects"] for shot in normalized["shots"]))
                self.assertTrue(all(shot["blocking"] for shot in normalized["shots"]))
                self.assertTrue(
                    all(shot["visible_behavior"] for shot in normalized["shots"])
                )

    def test_v205_partial_director_shapes_route_without_identity_gate(self) -> None:
        cases = []

        sound_only = make_source([4])
        sound_only.pop("source_skill", None)
        sound_only.pop("source_skill_version", None)
        sound_only["shots"][0].pop("audio", None)
        sound_only["shots"][0]["sound"] = {
            "effects": ["门锁咔哒一声。"],
            "ambience": "走廊保持安静。",
        }
        cases.append((sound_only, "audio", ["门锁咔哒一声。", "环境声：走廊保持安静。"]))

        camera_only = make_source([4])
        camera_only.pop("source_skill", None)
        camera_only.pop("source_skill_version", None)
        camera_only["shots"][0]["camera"]["movement"] = {
            "type": "push",
            "trigger": "门打开时",
            "speed": "缓慢",
            "path": "沿走廊推进",
            "end_condition": "人物停下时",
            "reason": "保持来源运动",
        }
        cases.append((camera_only, "camera", "推进"))

        continuity_only = make_source([4])
        continuity_only.pop("source_skill", None)
        continuity_only.pop("source_skill_version", None)
        continuity_only["shots"][0].pop("continuity_updates", None)
        continuity_only["shots"][0]["continuity"] = {
            "state_updates": [
                {
                    "entity": "门",
                    "field": "state",
                    "from": "关闭",
                    "to": "打开",
                }
            ]
        }
        cases.append((continuity_only, "continuity_updates", "打开"))

        for source, field, expected in cases:
            with self.subTest(field=field):
                normalized, issues = delivery.normalize_input(source)
                self.assertFalse(
                    {
                        issue["code"]
                        for issue in issues
                        if issue["severity"] == "ERROR"
                    }
                )
                shot = normalized["shots"][0]
                self.assertEqual(
                    shot["source_adapter"], "director-shot-data-shape-v2"
                )
                if field == "audio":
                    self.assertEqual(shot[field], expected)
                elif field == "camera":
                    self.assertEqual(shot[field]["movement"], expected)
                    self.assertEqual(
                        shot[field]["movement_plan"]["trigger"], "门打开时"
                    )
                else:
                    self.assertEqual(shot[field][0]["to"], expected)

    def test_v205_execution_text_cannot_duplicate_owned_dialogue(self) -> None:
        source = json.loads(CURRENT_DIRECTOR_FIXTURE.read_text(encoding="utf-8"))
        dialogue_shot = next(
            shot
            for shot in source["shots"]
            if shot.get("sound", {}).get("dialogue_segments")
        )
        literal = dialogue_shot["sound"]["dialogue_segments"][0]["text"]
        dialogue_shot["execution_text"] = (
            f"【中景｜平视｜固定】\n【画面内容】她先停下动作，说：“{literal}”随后转身。"
        )
        plan = build_plan(source, grouping_decisions(source))
        prompt = "\n".join(
            unit["prompt_text"] for unit in plan["prompt_units"]
        )
        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(prompt.count(literal), 1)

    def test_v205_repeated_identical_dialogue_preserves_event_count(self) -> None:
        source = json.loads(CURRENT_DIRECTOR_FIXTURE.read_text(encoding="utf-8"))
        source["source"]["dialogue_lines"].extend(
            [
                {
                    "dialogue_id": "D900",
                    "speaker": "陈默",
                    "text": "再见。",
                    "voice_type": "scene_dialogue",
                },
                {
                    "dialogue_id": "D901",
                    "speaker": "陈默",
                    "text": "再见。",
                    "voice_type": "scene_dialogue",
                },
            ]
        )
        target = source["shots"][-1]
        target["sound"]["dialogue_segments"].extend(
            [
                {"dialogue_id": "D900", "text": "再见。", "delivery": "onscreen"},
                {"dialogue_id": "D901", "text": "再见。", "delivery": "onscreen"},
            ]
        )
        target["camera"]["movement"] = {
            "type": "focus",
            "trigger": "第一次说出再见。",
            "speed": "缓慢",
            "path": "从眼睛转到手部",
            "end_condition": "第二次发声结束",
            "reason": "保持两次发声的动作顺序",
        }
        plan = build_plan(source, grouping_decisions(source))
        prompt = "\n".join(
            unit["prompt_text"] for unit in plan["prompt_units"]
        )
        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(prompt.count("再见。"), 2)
        self.assertIn("第一次发声", prompt)
        self.assertNotIn("第一次说出再见。", prompt)

    def test_v205_director_subjects_and_scene_label_reach_subject_block(self) -> None:
        source = json.loads(CURRENT_DIRECTOR_FIXTURE.read_text(encoding="utf-8"))
        source["scenes"][0]["scene"] = "1. 外景·测试走廊—日"
        plan = build_plan(source, grouping_decisions(source))
        prompt = plan["prompt_units"][0]["prompt_text"]
        subject_block = prompt.split("【主体、关系与场景】\n", 1)[1].split(
            "\n\n【镜头脚本】", 1
        )[0]
        self.assertIn("本单元核心主体：", subject_block)
        self.assertIn("林晓彤", subject_block)
        self.assertIn("外景·测试走廊—日", subject_block)
        self.assertNotIn(". 外景·测试走廊—日", subject_block)

    def test_v205_camera_position_and_movement_labels_are_natural_chinese(self) -> None:
        source = json.loads(CURRENT_DIRECTOR_FIXTURE.read_text(encoding="utf-8"))
        source["shots"][0]["camera"]["position"] = "位于门外正侧面"
        source["shots"][0]["camera"]["movement"] = {
            "type": "focus",
            "trigger": "人物抬眼时",
            "speed": "缓慢",
            "path": "从门锁转到人物眼睛",
            "end_condition": "视线稳定时",
            "reason": "保持来源焦点转移",
        }
        plan = build_plan(source, grouping_decisions(source))
        prompt = plan["prompt_units"][0]["prompt_text"]
        self.assertIn("摄影机位于门外正侧面", prompt)
        self.assertNotIn("摄影机位于位于", prompt)
        self.assertIn("镜头焦点转移", prompt)
        self.assertNotIn("镜头focus", prompt)

    def test_v205_nested_and_top_level_conflict_is_rejected(self) -> None:
        source = json.loads(CURRENT_DIRECTOR_FIXTURE.read_text(encoding="utf-8"))
        source["shots"][0]["blocking"] = ["与上游调度冲突的顶层动作。"]
        normalized, issues = delivery.normalize_input(source)
        self.assertIn(
            "UPSTREAM_FIELD_CONFLICT",
            {issue["code"] for issue in issues},
        )
        self.assertEqual(normalized["shots"][0]["blocking"], [])

    def test_v205_dialogue_playback_mismatch_is_rejected(self) -> None:
        source = json.loads(CURRENT_DIRECTOR_FIXTURE.read_text(encoding="utf-8"))
        source["shots"][1]["sound"]["dialogue_segments"][0]["text"] = (
            "我明天就走。"
        )
        normalized, issues = delivery.normalize_input(source)
        self.assertIn(
            "UPSTREAM_DIALOGUE_PLAYBACK_MISMATCH",
            {issue["code"] for issue in issues},
        )
        self.assertEqual(normalized["shots"][1]["dialogue"], [])

    def test_v205_upstream_performance_blocks_emotion_augmentation(self) -> None:
        source = json.loads(CURRENT_DIRECTOR_FIXTURE.read_text(encoding="utf-8"))
        source["shots"] = [source["shots"][0]]
        source["source"]["dialogue_lines"] = []
        decisions = {
            "emotion_visualizations": {
                "SH001": {
                    "basis_emotion": "克制",
                    "text": "她额外眨眼一次。",
                    "guardrails": {
                        key: False for key in delivery.EMOTION_GUARDRAIL_KEYS
                    },
                }
            }
        }
        plan = build_plan(source, decisions)
        self.assertIn("EMOTION_VISUALIZATION_FORBIDDEN", issue_codes(plan))
        self.assertNotIn(
            "她额外眨眼一次。", plan["prompt_units"][0]["prompt_text"]
        )

    def test_v205_known_nested_sound_cannot_disappear_silently(self) -> None:
        source = json.loads(CURRENT_DIRECTOR_FIXTURE.read_text(encoding="utf-8"))
        with mock.patch.object(delivery, "_director_audio_for_shot", return_value=[]):
            _, issues = delivery.normalize_input(source)
        self.assertIn(
            "UPSTREAM_FIELD_UNMAPPED",
            {issue["code"] for issue in issues},
        )

    def test_v205_director_adapter_adds_no_unapproved_defaults(self) -> None:
        source = json.loads(CURRENT_DIRECTOR_FIXTURE.read_text(encoding="utf-8"))
        source_ids = [shot["shot_id"] for shot in source["shots"]]
        plan = build_plan(source, grouping_decisions(source, [source_ids]))
        prompt = "\n".join(
            unit["prompt_text"] for unit in plan["prompt_units"]
        )
        for forbidden in (
            "47°",
            "84°",
            "Kodak",
            "Deakins",
            "No subtitles",
            "No music",
            "catchlight",
            "100% matches",
        ):
            self.assertNotIn(forbidden, prompt)

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
