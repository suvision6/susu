from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from storyboard_delivery import build_outputs, load_json, validate_data, validate_structure  # noqa: E402
from storyboard_review import approve_alignment, lock_workspace  # noqa: E402
from _execution_text import canonical_execution_text  # noqa: E402


class StoryboardDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.example_path = ROOT / "examples" / "kitchen-farewell-shot-data.json"
        cls.example = load_json(cls.example_path)
        cls.workspace = load_json(ROOT / "examples" / "kitchen-farewell-director-workspace.json")

    def test_example_is_ready(self) -> None:
        report = validate_data(self.example, self.workspace)
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["warning_count"], 0)
        self.assertEqual(report["summary"]["shot_count"], 3)
        self.assertAlmostEqual(report["summary"]["total_duration_seconds"], 14.5)

    def test_build_writes_atomic_four_file_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "delivery"
            report, paths = build_outputs(self.example, self.workspace, output)
            self.assertEqual(report["status"], "READY")
            self.assertEqual(set(paths), {"json", "markdown", "xlsx", "validation"})
            self.assertEqual(4, len(list(output.iterdir())))
            for path in paths.values():
                self.assertTrue(path.exists(), path)
            markdown = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("## 导演设计摘要", markdown)
            self.assertIn("## 六列导演分镜", markdown)
            self.assertIn("SH003", markdown)
            built = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(built["validation"]["status"], "ready")
            validation = json.loads(paths["validation"].read_text(encoding="utf-8"))
            self.assertEqual("PASS", validation["dimensions"]["export_parity"])
            self.assertEqual({"shot_data_json", "storyboard_markdown", "storyboard_xlsx"}, set(validation["artifacts"]))

    def test_dialogue_mismatch_fails(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["shots"][1]["sound"]["dialogue_segments"][0]["text"] = "我明天就走。"
        report = validate_data(broken, self.workspace)
        self.assertEqual(report["status"], "FAIL")
        codes = {entry["code"] for entry in report["errors"]}
        self.assertIn("DIALOGUE_COVERAGE_MISMATCH", codes)

    def test_dialogue_segment_must_appear_in_backend_execution_text(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["shots"][1]["execution_text"] = broken["shots"][1]["execution_text"].replace(
            "我明天走。", "她说出离开的决定。"
        )
        report = validate_data(broken, self.workspace)
        self.assertEqual(report["status"], "FAIL")
        codes = {entry["code"] for entry in report["errors"]}
        self.assertIn("DIALOGUE_NOT_IN_EXECUTION_TEXT", codes)
        self.assertIn("EXECUTION_TEXT_DIVERGED", codes)

    def test_missing_slug_degrades_to_warning(self) -> None:
        draft = copy.deepcopy(self.example)
        draft["source"]["delivery_slug"] = "厨房告别"
        report = validate_data(draft, self.workspace)
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["error_count"], 0)
        codes = {entry["code"] for entry in report["warnings"]}
        self.assertIn("DELIVERY_SLUG_FALLBACK_NEEDED", codes)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "delivery"
            _, paths = build_outputs(draft, self.workspace, output)
            self.assertEqual(paths["json"].name, "untitled-scene-001-shot-data.json")

    def test_artistic_uniformity_does_not_change_readiness(self) -> None:
        draft = copy.deepcopy(self.example)
        base_shot = draft["shots"][0]
        draft["shots"] = []
        for index in range(1, 9):
            shot = copy.deepcopy(base_shot)
            shot["shot_id"] = f"SH{index:03d}"
            shot["source_excerpt"] = "林晓彤把一把钥匙放在餐桌上。"
            shot["sound"]["dialogue_segments"] = []
            shot["shot_flow"] = [
                item for item in shot["shot_flow"]
                if item["owner"] not in {"ambience", "focus", "edit_exit"}
            ]
            shot["timing_plan"]["blocks"][0]["flow_end_index"] = len(shot["shot_flow"]) - 1
            shot["execution_text"] = canonical_execution_text(shot)
            draft["shots"].append(shot)
        draft["source"]["dialogue_lines"] = []
        report = validate_structure(draft)
        self.assertNotEqual(report["status"], "FAIL")
        codes = {entry["code"] for entry in report["warnings"]}
        self.assertNotIn("DIRECTOR_UNIFORMITY_REVIEW", codes)

    def test_concept_board_continues_with_locked_assumptions(self) -> None:
        concept = load_json(ROOT / "examples" / "unknown-room-awakening-shot-data.json")
        concept_workspace = load_json(ROOT / "examples" / "unknown-room-awakening-director-workspace.json")
        report = validate_data(concept, concept_workspace)
        self.assertEqual(report["status"], "READY_WITH_ASSUMPTIONS")
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["summary"]["open_assumption_count"], 2)
        codes = {entry["code"] for entry in report["warnings"]}
        self.assertEqual(codes, {"OPEN_ASSUMPTION"})

    def test_failed_build_leaves_no_formal_residue(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["shots"][1]["sound"]["dialogue_segments"][0]["text"] = "改写对白"
        with tempfile.TemporaryDirectory() as directory:
            for strict in (False, True):
                output = Path(directory) / ("strict" if strict else "soft")
                report, paths = build_outputs(broken, self.workspace, output, strict=strict)
                self.assertEqual(report["status"], "FAIL")
                self.assertEqual({}, paths)
                self.assertFalse(output.exists())

    def test_contract_identity_is_3_1_4(self) -> None:
        self.assertEqual(self.example["contract_version"], "3.1.4")
        self.assertEqual(self.example["source_skill_version"], "3.1.4")
        legacy = copy.deepcopy(self.example)
        legacy["contract_version"] = "3.1.0"
        legacy["source_skill_version"] = "3.1.1"
        report = validate_data(legacy, self.workspace)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("CONTRACT_IDENTITY_MISMATCH", {entry["code"] for entry in report["errors"]})
        schema = json.loads((ROOT / "schemas" / "director-shot-data.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["title"], "director-shot-data/3.1.4")
        self.assertEqual(schema["properties"]["contract_version"]["const"], "3.1.4")
        self.assertEqual(schema["properties"]["source_skill_version"]["const"], "3.1.4")

    def test_chinese_dialogue_rejects_speaker_label_contamination(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["source"]["dialogue_lines"][0]["text"] = "林晓彤：我明天走。"
        report = validate_data(broken, self.workspace)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("CHINESE_DIALOGUE_SPEAKER_LABEL", {entry["code"] for entry in report["errors"]})

    def test_chinese_dialogue_must_fit_physical_playback_floor(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["shots"][1]["duration_seconds"] = 0.3
        report = validate_data(broken, self.workspace)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("CHINESE_DIALOGUE_UNPLAYABLE", {entry["code"] for entry in report["errors"]})

    def test_chinese_execution_text_must_not_leak_internal_enums(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["shots"][0]["execution_text"] += " camera_reframe"
        report = validate_data(broken, self.workspace)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("CHINESE_EXECUTION_INTERNAL_ENUM", {entry["code"] for entry in report["errors"]})

    def test_chinese_source_requires_chinese_execution_text(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["shots"][0]["execution_text"] = "[MEDIUM] Camera holds on the table."
        report = validate_data(broken, self.workspace)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("CHINESE_EXECUTION_TEXT_REQUIRED", {entry["code"] for entry in report["errors"]})

    def test_removed_field_is_rejected_by_schema(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["shots"][0]["legacy_preparation_registry"] = ["legacy field"]
        report = validate_data(broken, self.workspace)
        self.assertEqual("FAIL", report["status"])
        self.assertIn("FORMAL_SCHEMA_INVALID", {entry["code"] for entry in report["errors"]})

    def test_remarks_have_no_keyword_routing_mechanism(self) -> None:
        changed = copy.deepcopy(self.example)
        changed["shots"][0]["notes"] = "车窗反射与同期收音需由现场部门自行处理。"
        structure_report = validate_structure(changed)
        self.assertEqual([], structure_report["errors"])
        relocked = lock_workspace(self.workspace, changed)
        self.assertEqual("confirmed", relocked["review_lock"]["gate_2_status"])
        reviewed = approve_alignment(relocked, changed, reviewer="test", note="备注变更复核")
        self.assertEqual("READY", validate_data(changed, reviewed)["status"])


if __name__ == "__main__":
    unittest.main()
