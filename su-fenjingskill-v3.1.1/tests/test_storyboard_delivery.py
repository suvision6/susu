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

from storyboard_delivery import build_outputs, load_json, validate_data  # noqa: E402


class StoryboardDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.example_path = ROOT / "examples" / "kitchen-farewell-shot-data.json"
        cls.example = load_json(cls.example_path)

    def test_example_is_ready(self) -> None:
        report = validate_data(self.example)
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["warning_count"], 0)
        self.assertEqual(report["summary"]["shot_count"], 3)
        self.assertAlmostEqual(report["summary"]["total_duration_seconds"], 14.5)

    def test_build_writes_three_backend_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report, paths = build_outputs(self.example, Path(directory))
            self.assertEqual(report["status"], "READY")
            self.assertEqual(set(paths), {"json", "markdown", "validation"})
            for path in paths.values():
                self.assertTrue(path.exists(), path)
            markdown = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("## 导演设计摘要", markdown)
            self.assertIn("## 六列导演分镜", markdown)
            self.assertIn("SH003", markdown)
            built = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(built["validation"]["status"], "ready")

    def test_dialogue_mismatch_fails(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["shots"][1]["sound"]["dialogue_segments"][0]["text"] = "我明天就走。"
        report = validate_data(broken)
        self.assertEqual(report["status"], "FAIL")
        codes = {entry["code"] for entry in report["errors"]}
        self.assertIn("DIALOGUE_COVERAGE_MISMATCH", codes)

    def test_dialogue_segment_must_appear_in_fifth_column(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["shots"][1]["execution_text"] = broken["shots"][1]["execution_text"].replace("我明天走。", "她说出离开的决定。")
        report = validate_data(broken)
        self.assertEqual(report["status"], "FAIL")
        codes = {entry["code"] for entry in report["errors"]}
        self.assertIn("DIALOGUE_NOT_IN_EXECUTION_TEXT", codes)

    def test_missing_slug_degrades_to_warning(self) -> None:
        draft = copy.deepcopy(self.example)
        draft["source"]["delivery_slug"] = "厨房告别"
        report = validate_data(draft)
        self.assertEqual(report["status"], "READY_WITH_ASSUMPTIONS")
        self.assertEqual(report["error_count"], 0)
        codes = {entry["code"] for entry in report["warnings"]}
        self.assertIn("DELIVERY_SLUG_FALLBACK_NEEDED", codes)
        with tempfile.TemporaryDirectory() as directory:
            _, paths = build_outputs(draft, Path(directory))
            self.assertEqual(paths["json"].name, "untitled-scene-001-shot-data.json")

    def test_artistic_uniformity_is_review_not_failure(self) -> None:
        draft = copy.deepcopy(self.example)
        base_shot = draft["shots"][0]
        draft["shots"] = []
        for index in range(1, 9):
            shot = copy.deepcopy(base_shot)
            shot["shot_id"] = f"SH{index:03d}"
            shot["source_excerpt"] = "林晓彤把一把钥匙放在餐桌上。"
            shot["sound"]["dialogue_segments"] = []
            draft["shots"].append(shot)
        draft["source"]["dialogue_lines"] = []
        report = validate_data(draft)
        self.assertNotEqual(report["status"], "FAIL")
        codes = {entry["code"] for entry in report["warnings"]}
        self.assertIn("DIRECTOR_UNIFORMITY_REVIEW", codes)

    def test_concept_board_continues_with_assumptions(self) -> None:
        concept = load_json(ROOT / "examples" / "unknown-room-awakening-shot-data.json")
        report = validate_data(concept)
        self.assertEqual(report["status"], "READY_WITH_ASSUMPTIONS")
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["summary"]["open_assumption_count"], 2)
        codes = {entry["code"] for entry in report["warnings"]}
        self.assertEqual(codes, {"OPEN_ASSUMPTION"})

    def test_soft_and_strict_failure_modes(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["shots"][1]["sound"]["dialogue_segments"][0]["text"] = "改写对白"
        with tempfile.TemporaryDirectory() as directory:
            soft_dir = Path(directory) / "soft"
            report, paths = build_outputs(broken, soft_dir, strict=False)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(set(paths), {"json", "markdown", "validation"})
            strict_dir = Path(directory) / "strict"
            strict_report, strict_paths = build_outputs(broken, strict_dir, strict=True)
            self.assertEqual(strict_report["status"], "FAIL")
            self.assertEqual(set(strict_paths), {"validation"})

    def test_contract_identity_is_3_1_0(self) -> None:
        self.assertEqual(self.example["contract_version"], "3.1.0")
        self.assertEqual(self.example["source_skill_version"], "3.1.1")
        legacy = copy.deepcopy(self.example)
        legacy["contract_version"] = "3.0.0"
        legacy["source_skill_version"] = "3.0.0"
        report = validate_data(legacy)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "CONTRACT_IDENTITY_MISMATCH",
            {entry["code"] for entry in report["errors"]},
        )
        schema = json.loads(
            (ROOT / "schemas" / "director-shot-data.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(schema["title"], "director-shot-data/3.1.0")
        self.assertEqual(
            schema["properties"]["contract_version"]["const"],
            "3.1.0",
        )
        self.assertEqual(
            schema["properties"]["source_skill_version"]["const"],
            "3.1.1",
        )

    def test_chinese_dialogue_rejects_speaker_label_contamination(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["source"]["dialogue_lines"][0]["text"] = "林晓彤：我明天走。"
        report = validate_data(broken)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "CHINESE_DIALOGUE_SPEAKER_LABEL",
            {entry["code"] for entry in report["errors"]},
        )

    def test_chinese_dialogue_must_fit_physical_playback_floor(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["shots"][1]["duration_seconds"] = 0.3
        report = validate_data(broken)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "CHINESE_DIALOGUE_UNPLAYABLE",
            {entry["code"] for entry in report["errors"]},
        )

    def test_chinese_execution_text_must_not_leak_internal_enums(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["shots"][0]["execution_text"] += " relationship_accumulation"
        report = validate_data(broken)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "CHINESE_EXECUTION_INTERNAL_ENUM",
            {entry["code"] for entry in report["errors"]},
        )

    def test_chinese_source_requires_chinese_execution_text(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["shots"][0]["execution_text"] = "[MEDIUM] Camera holds on the table."
        report = validate_data(broken)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "CHINESE_EXECUTION_TEXT_REQUIRED",
            {entry["code"] for entry in report["errors"]},
        )

    def test_production_risk_must_not_enter_remarks(self) -> None:
        broken = copy.deepcopy(self.example)
        broken["shots"][0]["notes"] = "车窗反射与收音需要联调。"
        report = validate_data(broken)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "PRODUCTION_RISK_IN_REMARKS",
            {entry["code"] for entry in report["errors"]},
        )

    def test_production_risk_renders_outside_six_column_remarks(self) -> None:
        draft = copy.deepcopy(self.example)
        risk = "桌面反光与钥匙焦点需要现场联调。"
        draft["shots"][0]["production_risks"] = [risk]
        draft["shots"][0]["notes"] = ""
        with tempfile.TemporaryDirectory() as directory:
            report, paths = build_outputs(draft, Path(directory))
            self.assertEqual(report["status"], "READY")
            markdown = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("## 制作风险（不进入备注列）", markdown)
            self.assertIn(f"- **SH001**：{risk}", markdown)


if __name__ == "__main__":
    unittest.main()
