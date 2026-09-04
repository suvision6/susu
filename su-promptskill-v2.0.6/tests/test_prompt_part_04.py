"""su-promptskill regression partition 04."""

from .support import *

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Discovered by scripts/test_prompt_delivery.py."


class PromptDeliveryTestsPart04(BasePromptDeliveryTests):
    def test_v206_dialogue_ledger_merges_split_source_line(self):
        normalized = {
            "shots": [
                {
                    "source_shot_id": "SH001",
                    "dialogue": [
                        {
                            "dialogue_id": "D001",
                            "speaker": "人物",
                            "text": "前半句，",
                            "source_text": "前半句，后半句。",
                            "position": "onscreen",
                        }
                    ],
                },
                {
                    "source_shot_id": "SH002",
                    "dialogue": [
                        {
                            "dialogue_id": "D001",
                            "speaker": "人物",
                            "text": "后半句。",
                            "source_text": "前半句，后半句。",
                            "position": "onscreen",
                        }
                    ],
                },
            ]
        }
        ledger = delivery._derive_dialogue_ledger(normalized)
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["text"], "前半句，后半句。")
        self.assertEqual(ledger[0]["source_shot_ids"], ["SH001", "SH002"])
        self.assertEqual(len(ledger[0]["segments"]), 2)

    def test_v206_director_316_projects_subject_roles_and_execution_owner(self):
        source = json.loads(
            CHINESE_SEMANTICS_DIRECTOR_FIXTURE.read_text(encoding="utf-8")
        )
        snapshot = copy.deepcopy(source)
        source_hash = delivery.sha256_json(source)
        normalized, issues = delivery.normalize_input(source)
        self.assertEqual(source, snapshot)
        self.assertEqual(delivery.sha256_json(source), source_hash)
        self.assertFalse(
            {issue["code"] for issue in issues if issue["severity"] == "ERROR"}
        )
        self.assertTrue(
            all(
                shot["source_adapter"] == "director-shot-data-shape-v2"
                for shot in normalized["shots"]
            )
        )
        self.assertEqual(
            normalized["shots"][1]["visible_subjects"],
            ["陈默的手", "菜刀", "砧板"],
        )
        self.assertEqual(
            normalized["shots"][1]["offscreen_subjects"], ["林晓彤"]
        )
        self.assertNotIn("start_frame", normalized["shots"][0]["camera"])
        self.assertNotIn("end_frame", normalized["shots"][0]["camera"])
        self.assertEqual(
            normalized["shots"][0]["cut_design"]["entry_trigger"],
            source["shots"][0]["edit"]["entry"],
        )
        self.assertEqual(
            normalized["shots"][0]["cut_design"]["exit_trigger"],
            source["shots"][0]["edit"]["exit"],
        )
        self.assertEqual(
            [
                shot["execution_text_projection"]["state"]
                for shot in normalized["shots"]
            ],
            ["audit_only", "fallback_unique_facts", "audit_only"],
        )
        self.assertEqual(normalized["shots"][0]["rendered_shot_description"], "")
        self.assertIn(
            "旧伤疤", normalized["shots"][1]["rendered_shot_description"]
        )

    def test_v206_chinese_prompt_is_clean_and_source_faithful(self):
        source = json.loads(
            CHINESE_SEMANTICS_DIRECTOR_FIXTURE.read_text(encoding="utf-8")
        )
        plan = build_plan(source, grouping_decisions(source))
        prompt = "\n".join(
            unit["prompt_text"] for unit in plan["prompt_units"]
        )
        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertIn("林晓彤（画外）：\u201c我明天走。\u201d", prompt)
        self.assertIn("陈默（画内）：\u201c什么时候决定的？\u201d", prompt)
        self.assertEqual(prompt.count("陈默手背的一道旧伤疤"), 1)
        for forbidden in (
            "（onscreen）",
            "（os）",
            "所有权：",
            "时间块：",
            "镜头动机",
            "时长依据：",
            "镜头固定，固定",
        ):
            self.assertNotIn(forbidden, prompt)
        for shot in source["shots"]:
            self.assertNotIn(shot["edit"]["entry"], prompt)
            self.assertNotIn(
                "主要状态变化：" + shot["edit"]["exit"], prompt
            )
        self.assertTrue(
            plan["validation"]["chinese_semantic_checks"][
                "state_role_drift_absent"
            ]
        )
        self.assertTrue(
            plan["validation"]["chinese_semantic_checks"][
                "bare_subject_fragment_absent"
            ]
        )

    def test_v206_unknown_execution_section_fails_closed(self):
        source = json.loads(
            CHINESE_SEMANTICS_DIRECTOR_FIXTURE.read_text(encoding="utf-8")
        )
        source["shots"][0]["execution_text"] = "【未知执行】不得静默采用。"
        normalized, issues = delivery.normalize_input(source)
        self.assertIn("UPSTREAM_FIELD_UNMAPPED", issue_codes({"diagnostics": issues}))
        self.assertEqual(
            normalized["shots"][0]["execution_text_projection"]["state"],
            "blocked",
        )
        self.assertEqual(normalized["shots"][0]["rendered_shot_description"], "")

    def test_v206_unknown_dialogue_delivery_fails_without_enum_leak(self):
        source = json.loads(
            CHINESE_SEMANTICS_DIRECTOR_FIXTURE.read_text(encoding="utf-8")
        )
        source["shots"][1]["sound"]["dialogue_segments"][0][
            "delivery"
        ] = "future-placement"
        normalized, issues = delivery.normalize_input(source)
        self.assertIn("DIALOGUE_DELIVERY_UNSUPPORTED", {i["code"] for i in issues})
        rendered = delivery._render_dialogue(normalized["shots"][1]["dialogue"][0])
        self.assertIn("我明天走。", rendered)
        self.assertNotIn("future-placement", rendered)

    def test_v206_semantic_validator_detects_all_regression_shapes(self):
        source = json.loads(
            CHINESE_SEMANTICS_DIRECTOR_FIXTURE.read_text(encoding="utf-8")
        )
        normalized, _ = delivery.normalize_input(source)
        shots = normalized["shots"][:1]
        timeline, _ = delivery._build_timeline(shots, {})
        bad_prompt = (
            "【生成目标】\n"
            + shots[0]["cut_design"]["exit_trigger"]
            + "\n\n【主体、关系与场景】\n测试。"
            + "\n\n【镜头脚本】\nCut 1｜0-4S\n"
            + shots[0]["cut_design"]["entry_trigger"]
            + "；主要状态变化："
            + shots[0]["cut_design"]["exit_trigger"]
            + "；林晓彤；林晓彤（onscreen）：\u201c测试。\u201d；"
            + "镜头固定，固定观察；【时长】时间块：TB001。"
            + "\n\n【声音与台词】\n无。\n\n【保持一致】\n保持。"
        )
        findings = delivery._prompt_chinese_semantic_findings(
            shots, timeline, bad_prompt
        )
        self.assertEqual(
            set(findings),
            {
                "PROMPT_AUDIT_TEXT_LEAK",
                "PROMPT_CHINESE_ENUM_LEAK",
                "PROMPT_BARE_SUBJECT_FRAGMENT",
                "PROMPT_STATE_ROLE_DRIFT",
                "PROMPT_ADJACENT_LEXICAL_DUPLICATION",
            },
        )

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
        self.assertIn(
            "本单元的来源声音与台词均已在对应 Cut 内执行，"
            "无额外跨 Cut 声音关系。",
            prompt,
        )
        self.assertNotIn(delivery.NO_SOURCE_SOUND_LINE, prompt)
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
        self.assertNotIn(
            "Cut 1声音：拐角处传来金属撞击与低吼。", prompt
        )
        self.assertEqual(prompt.count("拐角处传来金属撞击与低吼。"), 1)
        self.assertIn(
            "本单元的来源声音与台词均已在对应 Cut 内执行，"
            "无额外跨 Cut 声音关系。",
            prompt,
        )

    def test_v205_cut_sound_items_use_one_top_level_label(self) -> None:
        source = make_source([4])
        source["shots"][0]["audio"] = [
            "声音视点：以当前摄影机距离组织现场声。",
            "木门撞墙声。",
            "急促脚步。",
            "环境声：街区交易声和远处风声。",
            "音乐：无预设非叙事配乐。",
        ]
        plan = build_plan(source)
        prompt = plan["prompt_units"][0]["prompt_text"]
        cut = delivery._cut_prompt_block(prompt, "Cut 1")
        sound_section = prompt.split("【声音与台词】", 1)[1]
        self.assertEqual(cut.count("声音："), 1)
        self.assertIn("声音：视点：以当前摄影机距离组织现场声。", cut)
        self.assertNotIn("声音：声音视点：", cut)
        for payload in (
            "木门撞墙声。",
            "急促脚步。",
            "环境声：街区交易声和远处风声。",
            "音乐：无预设非叙事配乐。",
        ):
            self.assertEqual(prompt.count(payload), 1)
        self.assertNotIn("Cut 1声音：", sound_section)
        self.assertEqual(plan["validation"]["status"], "PASS")

    def test_v205_sound_redundancy_crosses_cut_and_sound_section(self) -> None:
        source = make_source([4])
        source["shots"][0]["audio"] = ["门锁咔哒一声。"]
        plan = build_plan(source)
        unit = plan["prompt_units"][0]
        normalized = plan["compiler_inputs"]["normalized_source"]
        tampered = unit["prompt_text"].replace(
            "本单元的来源声音与台词均已在对应 Cut 内执行，"
            "无额外跨 Cut 声音关系。",
            "Cut 1声音：门锁咔哒一声。",
        )
        findings = delivery._prompt_redundancy_findings(
            normalized["shots"], unit["timeline"], tampered
        )
        self.assertTrue(
            any("声音事实在声音区块复抄" in item for item in findings)
        )

    def test_v205_multiple_cut_sound_labels_are_blocking_redundancy(self) -> None:
        source = make_source([4])
        source["shots"][0]["audio"] = ["门锁咔哒一声。"]
        plan = build_plan(source)
        unit = plan["prompt_units"][0]
        normalized = plan["compiler_inputs"]["normalized_source"]
        tampered = unit["prompt_text"].replace(
            "声音：门锁咔哒一声。",
            "声音：门锁咔哒一声。声音：走廊回声。",
        )
        findings = delivery._prompt_redundancy_findings(
            normalized["shots"], unit["timeline"], tampered
        )
        self.assertTrue(
            any("顶层声音说明重复 2 次" in item for item in findings)
        )

    def test_v205_sound_label_inside_dialogue_is_not_a_structure_marker(self) -> None:
        source = make_source([4])
        source["shots"][0]["audio"] = ["门锁咔哒一声。"]
        source["shots"][0]["dialogue"] = [
            {
                "speaker": "人物",
                "text": "这个声音：不对。",
                "position": "画内",
            }
        ]
        plan = build_plan(source)
        prompt = plan["prompt_units"][0]["prompt_text"]
        cut = delivery._cut_prompt_block(prompt, "Cut 1")
        self.assertEqual(cut.count("声音："), 2)
        self.assertEqual(plan["validation"]["status"], "PASS")

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
        baseline_hashes = {
            "seedance-2.0-default": "ec556af4a070f0aacbc7da501261f4c085fbf884f3365ba4247009adc452a402",
            "generic-video": "ec556af4a070f0aacbc7da501261f4c085fbf884f3365ba4247009adc452a402",
        }
        source = make_source([4])
        for profile_id in ("seedance-2.0-default", "generic-video"):
            with self.subTest(profile_id=profile_id):
                candidate_profile = delivery.resolve_model_profile(profile_id)
                candidate_prompt = delivery.build_prompt_plan(
                    source,
                    model_profile=candidate_profile,
                )["prompt_units"][0]["prompt_text"]
                candidate_hash = hashlib.sha256(
                    candidate_prompt.encode("utf-8")
                ).hexdigest()
                self.assertEqual(candidate_hash, baseline_hashes[profile_id])

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
