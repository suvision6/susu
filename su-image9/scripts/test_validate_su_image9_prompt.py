#!/usr/bin/env python3
"""Carry-forward regressions adapted from the pre-2.1 validator suite."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import derive_su_image9_prompt_package as derive
import test_derive_su_image9_210 as derive_tests
import test_validate_su_image9_210 as validator_tests
import validate_su_image9_prompt as validator


CANON_PATH = SCRIPT_DIR.parent / "references" / "canon-locks.md"
VALIDATOR_PATH = SCRIPT_DIR / "validate_su_image9_prompt.py"


class ValidatorCarryForwardTests(unittest.TestCase):
    """Keep the original 17 risk categories without restoring removed APIs."""

    def build_case(self, root: Path) -> tuple[validator_tests.Validator210Tests, dict, dict, str, Path]:
        helper = validator_tests.Validator210Tests()
        data, plan, prompt, source = helper.build_case(root)
        return helper, data, plan, prompt, source

    @staticmethod
    def codes(report: dict) -> set[str]:
        return {item["code"] for item in report.get("findings", [])}

    @staticmethod
    def write_source(root: Path, data: dict) -> Path:
        source = root / "sample.shot_data.json"
        source.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return source

    @staticmethod
    def two_scene_two_layer_data() -> dict:
        data = derive_tests.final_signed_data_242()
        first_log = copy.deepcopy(data["continuity_logs"][0])
        first_log["characters"] = [
            {"name": "A", "position": "门口", "facing": "桌边"},
            {"name": "B", "position": "桌边", "facing": "门口"},
        ]
        second_log = copy.deepcopy(first_log)
        second_log["scene_id"] = "S02"
        second_log["scene"] = "2 室内 夜 内"
        second_log["reality_layer"] = "回忆"

        first_page_shots = copy.deepcopy(data["shots"])
        for shot in first_page_shots:
            shot["visible_characters"] = ["A", "B"]
        second_page_shots = copy.deepcopy(first_page_shots)
        for number, shot in enumerate(second_page_shots, 3):
            shot["shot_no"] = number
            shot["scene_id"] = "S02"
            shot["scene"] = "2 室内 夜 内"

        data["continuity_logs"] = [first_log, second_log]
        data["shots"] = first_page_shots + second_page_shots
        validator_tests.refresh_source_hash(data)
        return data

    def test_legacy_v2_package_requires_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            helper, data, plan, prompt, source = self.build_case(root)
            plan["version"] = "2.0.2"
            plan["schema_version"] = "2.0"
            code, report, compiled = helper.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code)
            self.assertIn("F-LEGACY-REGENERATE", self.codes(report))
            self.assertEqual("\n", compiled)

    def test_unknown_canon_marker_leak_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            helper, data, plan, prompt, source = self.build_case(root)
            prompt = prompt.replace("@CANON(HARD_PHRASES)", "@CANON(UNEXPANDED)", 1)
            code, report, compiled = helper.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code)
            self.assertIn("F-PROMPT-CANON", self.codes(report))
            self.assertEqual("\n", compiled)

    def test_missing_required_layer_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            helper, data, plan, prompt, source = self.build_case(root)
            prompt = prompt.replace("CAMERA_RULE_LAYER:\n", "", 1)
            code, report, _ = helper.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code)
            self.assertIn("F-PROMPT-LAYERS", self.codes(report))

    def test_panel_layer_field_skeleton_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            helper, data, plan, prompt, source = self.build_case(root)
            prompt = prompt.replace("PANEL-1:", "PANEL-1: SOURCE SHOT: 1", 1)
            code, report, _ = helper.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code)
            self.assertIn("F-PROMPT-DRIFT", self.codes(report))

    def test_prompt_length_is_metric_not_waiver_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            helper, data, plan, prompt, source = self.build_case(root)
            code, report, _ = helper.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_PASS, code)
            self.assertEqual(len(prompt), report["metrics"]["prompt_characters"])
            self.assertFalse(any("budget" in item["code"].lower() for item in report["findings"]))

    def test_old_panel_tasks_structure_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            helper, data, plan, prompt, source = self.build_case(root)
            plan["pages"][0]["panel_tasks"] = []
            code, report, _ = helper.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code)
            self.assertIn("F-PLAN-SCHEMA", self.codes(report))

    def test_boolean_props_in_source_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            helper, data, plan, prompt, source = self.build_case(root)
            data["shots"][0]["visible_props"] = [True]
            validator_tests.refresh_source_hash(data)
            code, report, _ = helper.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code)
            self.assertIn("F-SOURCE", self.codes(report))

    def test_forbidden_style_injection_fails_exact_render(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            helper, data, plan, prompt, source = self.build_case(root)
            prompt = prompt.replace("SCENE_LAYER:\n", "SCENE_LAYER:\nRender this panel in watercolor.\n", 1)
            code, report, compiled = helper.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code)
            self.assertIn("F-PROMPT-DRIFT", self.codes(report))
            self.assertEqual("\n", compiled)

    def test_text_only_surface_is_removed(self) -> None:
        process = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR_PATH),
                "--canon", "canon",
                "--panel-plan", "plan",
                "--final-prompts", "prompt",
                "--shot-data", "source",
                "--report", "report",
                "--out", "compiled",
                "--mode", "text-only",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(validator.EXIT_CONTRACT_FAIL, process.returncode)
        self.assertIn("unrecognized arguments", process.stderr)

    def test_close_first_panel_keeps_source_and_uses_later_anchor(self) -> None:
        data = derive_tests.final_signed_data_242()
        data["shots"][0]["camera_main_image"] = (
            "[平视, 特写, 固定镜头]\n【机位逻辑】摄影机保持在桌边，只看A的面部。\n"
            "【场景首镜站位】（A站在门口，面向桌边。）\nA站在门口。"
        )
        derive_tests.resign_after_valid_mutation(data)
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = self.write_source(root, data)
            page = derive.derive_artifacts(data, source, CANON_PATH)["panel_plan"]["pages"][0]
            self.assertEqual(page["panels"][0]["source_camera_tag"], page["panels"][0]["drawn_camera_tag"])
            self.assertNotEqual("PANEL-1", page["spatial_anchor_panel"])

    def test_reordered_source_list_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            helper, data, plan, prompt, source = self.build_case(root)
            plan["pages"][0]["source_shot_nos"] = [2, 1]
            code, report, _ = helper.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code)
            self.assertIn("F-SOURCE-COVERAGE", self.codes(report))

    def test_distance_stage_lock_required_before_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            _helper, _data, plan, _prompt, _source = self.build_case(root)
            source_one = next(panel for panel in plan["pages"][0]["panels"] if panel["panel_kind"] == "source" and panel["source_shot"] == 1)
            self.assertIn("pre-transition", source_one["distance_stage_lock"])

    def test_distance_stage_lock_allows_registered_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            helper, data, plan, prompt, source = self.build_case(root)
            source_two = next(panel for panel in plan["pages"][0]["panels"] if panel["panel_kind"] == "source" and panel["source_shot"] == 2)
            self.assertIn("endpoint-transition", source_two["distance_stage_lock"])
            code, report, _ = helper.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_PASS, code, report)

    def test_memory_and_surgery_words_do_not_block_a_structured_page(self) -> None:
        data = derive_tests.final_signed_data_242()
        data["continuity_logs"][0]["reality_layer"] = "手术回忆"
        validator_tests.refresh_source_hash(data)
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = self.write_source(root, data)
            page = derive.derive_artifacts(data, source, CANON_PATH)["panel_plan"]["pages"][0]
            self.assertEqual("手术回忆", page["reality_layer"])
            self.assertRegex(page["spatial_anchor_panel"], r"^PANEL-[1-9]$")

    def test_cross_scene_sources_are_split_not_bridged(self) -> None:
        data = self.two_scene_two_layer_data()
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = self.write_source(root, data)
            pages = derive.derive_artifacts(data, source, CANON_PATH)["panel_plan"]["pages"]
            self.assertEqual(["S01", "S02"], [page["scene_id"] for page in pages])
            self.assertEqual([[1, 2], [3, 4]], [page["source_shot_nos"] for page in pages])

    def test_derive_preserves_source_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            _helper, _data, plan, _prompt, _source = self.build_case(root)
            native = [
                panel["source_shot"]
                for page in plan["pages"]
                for panel in page["panels"]
                if panel["panel_kind"] == "source"
            ]
            self.assertEqual([1, 2], native)

    def test_derive_uses_scene_and_reality_aware_pagination(self) -> None:
        data = self.two_scene_two_layer_data()
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = self.write_source(root, data)
            pages = derive.derive_artifacts(data, source, CANON_PATH)["panel_plan"]["pages"]
            self.assertEqual(
                [("S01", "现实"), ("S02", "回忆")],
                [(page["scene_id"], page["reality_layer"]) for page in pages],
            )
            self.assertTrue(all(page["page_mode"] == "single_scene_single_reality_layer" for page in pages))


if __name__ == "__main__":
    unittest.main()
