from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

from scripts._execution_text import canonical_execution_text
from scripts._chinese_context import (
    chinese_dialogue_estimated_seconds,
    dialogue_pace_issues,
    load_dialogue_pace_standard,
    resolve_dialogue_pace,
)
from scripts._schema_validation import validate_formal_schema, validate_workspace_schema
from scripts.migrate_contract_3_1_3_to_3_1_4 import build_drafts, main as migrate_main
from scripts.storyboard_delivery import validate_structure
from scripts.storyboard_review import (
    lock_workspace,
    validate_dialogue_edit_plans,
    validate_workspace,
)


class FormatRhythmDuration314Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = json.loads((ROOT / "examples" / "kitchen-farewell-shot-data.json").read_text(encoding="utf-8"))
        self.workspace = json.loads((ROOT / "examples" / "kitchen-farewell-director-workspace.json").read_text(encoding="utf-8"))

    @staticmethod
    def formal_codes(data: dict) -> set[str]:
        for shot in data.get("shots", []):
            shot["execution_text"] = canonical_execution_text(shot)
        return {item["code"] for item in validate_structure(data)["errors"]}

    def workspace_codes(self, workspace: dict, data: dict) -> set[str]:
        return {item["code"] for item in validate_workspace(workspace, data, check_review_states=False)["errors"]}

    def test_contract_and_gate_zero_shapes_are_314(self) -> None:
        self.assertEqual("3.1.4", self.data["contract_version"])
        self.assertEqual("director-workspace/3.1.4", self.workspace["workspace_contract"])
        self.assertEqual("confirmed", self.workspace["gate_0"]["status"])
        self.assertEqual([], validate_formal_schema(self.data))
        self.assertEqual([], validate_workspace_schema(self.workspace))
        self.assertIn("format_brief", self.data)
        self.assertIn("dialogue_edit_plan", self.workspace["scene_strategies"][0])
        self.assertTrue(all("timing_plan" in shot for shot in self.data["shots"]))

    def test_house_standard_has_fixed_profile_ranges(self) -> None:
        standard = load_dialogue_pace_standard()
        observed = {
            key: (value["range_min_cps"], value["range_max_cps"], value["default_cps"])
            for key, value in standard["profiles"].items()
        }
        self.assertEqual(
            {
                "short_drama_under_10m": (4.3, 5.5, 4.8),
                "platform_series_episode": (3.3, 4.3, 3.8),
                "short_film_3_20m": (2.3, 3.3, 2.8),
                "feature_film": (2.7, 3.7, 3.2),
            },
            observed,
        )

    def test_profile_range_cannot_be_silently_changed(self) -> None:
        standard = load_dialogue_pace_standard()["profiles"]["short_drama_under_10m"]
        pace = {
            "standard_id": "su-dialogue-pace/1.0",
            "pace_profile": "fast",
            "rate_basis": "articulation_rate_excluding_pauses",
            "range_min_cps": 3.0,
            "range_max_cps": standard["range_max_cps"],
            "default_cps": standard["default_cps"],
            "selected_cps": standard["default_cps"],
            "strong_pause_seconds": standard["default_strong_pause_seconds"],
            "soft_pause_seconds": standard["default_soft_pause_seconds"],
            "basis": "测试标准范围。",
            "overrides": [],
        }
        codes = {code for code, _, _ in dialogue_pace_issues("short_drama_under_10m", pace)}
        self.assertIn("DIALOGUE_PACE_PROFILE_RANGE_MISMATCH", codes)

    def test_all_four_house_profiles_pass_their_exact_ranges(self) -> None:
        standard = load_dialogue_pace_standard()
        for profile, values in standard["profiles"].items():
            pace = {
                "standard_id": standard["standard_id"],
                "pace_profile": values["pace_profile"],
                "rate_basis": standard["rate_basis"],
                "range_min_cps": values["range_min_cps"],
                "range_max_cps": values["range_max_cps"],
                "default_cps": values["default_cps"],
                "selected_cps": values["default_cps"],
                "strong_pause_seconds": values["default_strong_pause_seconds"],
                "soft_pause_seconds": values["default_soft_pause_seconds"],
                "basis": "内部标准默认值，等待 Gate 0 确认。",
                "overrides": [],
            }
            self.assertEqual([], dialogue_pace_issues(profile, pace), profile)

    def test_explicit_override_can_leave_base_range_but_needs_real_reason(self) -> None:
        pace = copy.deepcopy(self.data["format_brief"]["dialogue_pace"])
        pace["overrides"] = [
            {
                "override_id": "PO001",
                "scope": "dialogue",
                "scope_ref": "D001",
                "selected_cps": 6.0,
                "strong_pause_seconds": 0.1,
                "soft_pause_seconds": 0.05,
                "reason": "角色抢在对方打断前连说完整句，字尾没有停住。",
            }
        ]
        self.assertEqual([], dialogue_pace_issues("custom", pace))
        self.assertEqual(6.0, resolve_dialogue_pace(pace, "PO001")["selected_cps"])
        pace["overrides"][0]["reason"] = "节奏需要"
        codes = {code for code, _, _ in dialogue_pace_issues("custom", pace)}
        self.assertIn("DIALOGUE_PACE_OVERRIDE_REASON_VAGUE", codes)

    def test_format_profile_runtime_and_orientation_are_deterministic(self) -> None:
        data = copy.deepcopy(self.data)
        data["format_brief"]["rhythm_profile"] = "short_drama_under_10m"
        data["format_brief"]["target_runtime_seconds"] = 601
        self.assertIn("RHYTHM_PROFILE_RUNTIME_MISMATCH", self.formal_codes(data))

        data = copy.deepcopy(self.data)
        data["format_brief"]["aspect_ratio"] = "9:16"
        data["format_brief"]["orientation"] = "horizontal"
        self.assertIn("ASPECT_ORIENTATION_MISMATCH", self.formal_codes(data))

    def test_format_change_invalidates_every_review_stage(self) -> None:
        data = copy.deepcopy(self.data)
        workspace = copy.deepcopy(self.workspace)
        data["format_brief"]["aspect_ratio"] = "4:3"
        workspace["format_brief"]["aspect_ratio"] = "4:3"
        changed = lock_workspace(workspace, data)
        self.assertEqual("invalidated", changed["gate_0"]["status"])
        self.assertEqual("invalidated", changed["review_lock"]["gate_0_status"])
        self.assertEqual("invalidated", changed["review_lock"]["gate_1_status"])
        self.assertEqual("invalidated", changed["review_lock"]["gate_2_status"])
        self.assertEqual("invalidated", changed["review_lock"]["alignment_status"])

    def test_timing_or_formal_aspect_change_invalidates_alignment_only(self) -> None:
        data = copy.deepcopy(self.data)
        data["shots"][0]["timing_plan"]["blocks"][0]["action_seconds"] += 0.1
        changed = lock_workspace(copy.deepcopy(self.workspace), data)
        self.assertEqual("confirmed", changed["review_lock"]["gate_0_status"])
        self.assertEqual("passed", changed["review_lock"]["gate_1_status"])
        self.assertEqual("confirmed", changed["review_lock"]["gate_2_status"])
        self.assertEqual("invalidated", changed["review_lock"]["alignment_status"])

    def test_every_source_dialogue_requires_one_edit_plan(self) -> None:
        workspace = copy.deepcopy(self.workspace)
        workspace["scene_strategies"][0]["dialogue_edit_plan"].pop()
        self.assertIn("DIALOGUE_EDIT_COVERAGE_MISMATCH", self.workspace_codes(workspace, copy.deepcopy(self.data)))

    @staticmethod
    def dialogue_fixture(visible_development: str) -> tuple[list[dict], dict, dict]:
        dialogues = {
            "D001": {"dialogue_id": "D001", "speaker": "甲", "text": "你来了。"},
            "D002": {"dialogue_id": "D002", "speaker": "乙", "text": "我来了。"},
        }
        shot_map = {
            "SH001": {
                "staging": {"subjects": ["甲", "乙"]},
                "sound": {
                    "dialogue_segments": [
                        {"dialogue_id": "D001", "text": "你来了。", "delivery": "onscreen"},
                        {"dialogue_id": "D002", "text": "我来了。", "delivery": "os"},
                    ]
                }
            }
        }
        base_step = {
            "topology_unit_id": "TU001",
            "owner_type": "subject",
            "owner_refs": ["甲"],
            "framing_intent": "single",
            "picture_value": "让画面读取甲如何承受乙的回答。",
        }
        strategy = {
            "scene_id": "SC001",
            "topology": [
                {
                    "unit_id": "TU001",
                    "shot_refs": ["SH001"],
                    "intra_shot_operations": [],
                    "viewing_design": {
                        "owner_type": "subject",
                        "owner_refs": ["甲"],
                        "framing_intent": "single",
                    },
                }
            ],
            "dialogue_edit_plan": [
                {
                    "dialogue_id": "D001",
                    "speaker": "甲",
                    "listener_refs": ["乙"],
                    "power_center_refs": ["甲"],
                    "attention_shift": "甲先建立问题。",
                    "picture_steps": [
                        {**base_step, "text_span": "你来了。", "entry_decision": "establish", "cut_phase": "line_start", "visible_development": "甲抬眼确认乙已经进入。"}
                    ],
                },
                {
                    "dialogue_id": "D002",
                    "speaker": "乙",
                    "listener_refs": ["甲"],
                    "power_center_refs": ["乙"],
                    "attention_shift": "乙回答后压力落到甲身上。",
                    "picture_steps": [
                        {**base_step, "text_span": "我来了。", "entry_decision": "hold", "cut_phase": "hold", "visible_development": visible_development}
                    ],
                },
            ],
        }
        return [strategy], shot_map, dialogues

    def test_static_listener_hold_is_a_missed_view_change(self) -> None:
        strategies, shots, dialogues = self.dialogue_fixture("继续反应")
        codes = {item["code"] for item in validate_dialogue_edit_plans(strategies, shots, dialogues)}
        self.assertIn("MISSED_DIALOGUE_VIEW_CHANGE", codes)

    def test_listener_hold_with_new_visible_development_is_valid(self) -> None:
        strategies, shots, dialogues = self.dialogue_fixture("甲握住门把的手松开，视线却仍停在乙身上。")
        self.assertEqual([], validate_dialogue_edit_plans(strategies, shots, dialogues))

    def test_multi_person_dialogue_requires_attention_and_power_centers(self) -> None:
        strategies, shots, dialogues = self.dialogue_fixture("甲握住门把的手松开，视线却仍停在乙身上。")
        shots["SH001"]["staging"]["subjects"].append("丙")
        strategies[0]["dialogue_edit_plan"][0]["listener_refs"] = []
        strategies[0]["dialogue_edit_plan"][0]["power_center_refs"] = []
        codes = {item["code"] for item in validate_dialogue_edit_plans(strategies, shots, dialogues)}
        self.assertIn("MULTIPERSON_ATTENTION_MAP_REQUIRED", codes)

    def test_timing_blocks_recompute_dialogue_and_shot_duration(self) -> None:
        data = copy.deepcopy(self.data)
        data["shots"][1]["timing_plan"]["blocks"][0]["dialogue_seconds"] += 0.5
        self.assertIn("DIALOGUE_TIMING_MISMATCH", self.formal_codes(data))

        data = copy.deepcopy(self.data)
        data["shots"][0]["timing_plan"]["blocks"][0]["mode"] = "sequential"
        self.assertIn("TIMING_BLOCK_SUM_MISMATCH", self.formal_codes(data))

    def test_timing_plan_uses_explicit_pace_override(self) -> None:
        data = copy.deepcopy(self.data)
        pace = data["format_brief"]["dialogue_pace"]
        pace["overrides"] = [
            {
                "override_id": "PO001",
                "scope": "dialogue",
                "scope_ref": "D001",
                "selected_cps": 3.0,
                "strong_pause_seconds": 0.4,
                "soft_pause_seconds": 0.2,
                "reason": "角色说出离开决定时逐字压低声音，并在句号前完成一次换气。",
            }
        ]
        shot = data["shots"][1]
        shot["timing_plan"]["blocks"][0]["pace_ref"] = "PO001"
        text = "".join(segment["text"] for segment in shot["sound"]["dialogue_segments"])
        seconds = round(chinese_dialogue_estimated_seconds(text, resolve_dialogue_pace(pace, "PO001")), 6)
        shot["timing_plan"]["blocks"][0]["dialogue_seconds"] = seconds
        self.assertNotIn("DIALOGUE_TIMING_MISMATCH", self.formal_codes(data))

    def test_pace_override_scope_must_match_timing_block(self) -> None:
        data = copy.deepcopy(self.data)
        data["format_brief"]["dialogue_pace"]["overrides"] = [
            {
                "override_id": "PO001",
                "scope": "dialogue",
                "scope_ref": "D001",
                "selected_cps": 3.0,
                "strong_pause_seconds": 0.4,
                "soft_pause_seconds": 0.2,
                "reason": "角色说出离开决定时逐字压低声音，并在句号前完成一次换气。",
            }
        ]
        data["shots"][2]["timing_plan"]["blocks"][0]["pace_ref"] = "PO001"
        self.assertIn("TIMING_PACE_SCOPE_MISMATCH", self.formal_codes(data))

    def test_vague_aspect_application_is_blocked(self) -> None:
        data = copy.deepcopy(self.data)
        data["shots"][0]["camera"]["aspect_ratio_reason"] = "适配画幅"
        self.assertIn("ASPECT_RATIO_APPLICATION_VAGUE", self.formal_codes(data))

    def test_vertical_format_does_not_ban_motivated_horizontal_movement(self) -> None:
        data = copy.deepcopy(self.data)
        data["format_brief"]["aspect_ratio"] = "9:16"
        data["format_brief"]["orientation"] = "vertical"
        for shot in data["shots"]:
            shot["camera"]["aspect_ratio_reason"] = f"在9:16纵向画框中保持“{shot['staging']['performance'][:12]}”与前后景可读。"
        shot = data["shots"][0]
        shot["camera"]["movement"] = {
            "type": "track",
            "trigger": "人物越过桌沿时",
            "speed": "与步速同步",
            "path": "短距离横移后转入纵深",
            "end_condition": "人物在门框纵轴停住",
            "reason": "横移只用于接住人物离桌动作，随后把关系重新压回9:16纵深轴。",
        }
        shot["shot_flow"].insert(1, {"owner": "movement"})
        block = shot["timing_plan"]["blocks"][0]
        block["flow_end_index"] += 1
        block["camera_seconds"] = shot["duration_seconds"]
        self.assertEqual(set(), self.formal_codes(data))

    def test_313_migration_is_schema_valid_and_does_not_guess_gate_zero(self) -> None:
        old_root = Path("/Users/suvision/Documents/Test/su-fenjingskill-3.1.3/examples")
        old_data = json.loads((old_root / "kitchen-farewell-shot-data.json").read_text(encoding="utf-8"))
        old_workspace = json.loads((old_root / "kitchen-farewell-director-workspace.json").read_text(encoding="utf-8"))
        shot_draft, workspace_draft, report = build_drafts(old_data, old_workspace)
        self.assertEqual([], validate_formal_schema(shot_draft))
        self.assertEqual([], validate_workspace_schema(workspace_draft))
        self.assertEqual("unresolved", shot_draft["format_brief"]["rhythm_profile"])
        self.assertTrue(all(shot["timing_plan"]["status"] == "unresolved" for shot in shot_draft["shots"]))
        self.assertTrue(all(strategy["dialogue_edit_plan"] == [] for strategy in workspace_draft["scene_strategies"]))
        self.assertEqual(["gate_0", "gate_1", "gate_2", "alignment"], report["review_stages_invalidated"])
        semantic_codes = self.workspace_codes(workspace_draft, shot_draft)
        self.assertIn("RHYTHM_PROFILE_INVALID", semantic_codes)
        self.assertIn("DIALOGUE_EDIT_COVERAGE_MISMATCH", semantic_codes)

    def test_313_migration_does_not_preserve_nonstandard_shot_size_wording(self) -> None:
        old_root = Path("/Users/suvision/Documents/Test/su-fenjingskill-3.1.3/examples")
        old_data = json.loads((old_root / "kitchen-farewell-shot-data.json").read_text(encoding="utf-8"))
        old_workspace = json.loads((old_root / "kitchen-farewell-director-workspace.json").read_text(encoding="utf-8"))
        old_data["shots"][0]["camera"]["shot_size"] = "紧中景"
        shot_draft, _, report = build_drafts(old_data, old_workspace)
        self.assertEqual("unresolved", shot_draft["shots"][0]["camera"]["shot_size"])
        self.assertIn("SH001", report["shot_size_term_rebuild_required"])
        self.assertEqual([], validate_formal_schema(shot_draft))

    def test_313_migration_cli_writes_only_three_new_drafts(self) -> None:
        old_root = Path("/Users/suvision/Documents/Test/su-fenjingskill-3.1.3/examples")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "Migrated-314"
            result = migrate_main(
                [
                    "--shot-data", str(old_root / "kitchen-farewell-shot-data.json"),
                    "--workspace", str(old_root / "kitchen-farewell-director-workspace.json"),
                    "--output-dir", str(output),
                ]
            )
            self.assertEqual(0, result)
            self.assertEqual(3, len(list(output.iterdir())))
            report = json.loads((output / "kitchen-farewell-migration-report.json").read_text(encoding="utf-8"))
            self.assertEqual("VALID_MIGRATION_CARRIER", report["schema_status"])

    def test_313_migration_cli_refuses_nonempty_target(self) -> None:
        old_root = Path("/Users/suvision/Documents/Test/su-fenjingskill-3.1.3/examples")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "Migrated-314"
            output.mkdir()
            sentinel = output / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")
            result = migrate_main(
                [
                    "--shot-data", str(old_root / "kitchen-farewell-shot-data.json"),
                    "--workspace", str(old_root / "kitchen-farewell-director-workspace.json"),
                    "--output-dir", str(output),
                ]
            )
            self.assertEqual(1, result)
            self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
