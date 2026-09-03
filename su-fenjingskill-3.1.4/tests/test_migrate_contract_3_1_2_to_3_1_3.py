#!/usr/bin/env python3

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

from migrate_contract_3_1_2_to_3_1_3 import build_drafts, main  # noqa: E402
from _schema_validation import validate_formal_schema, validate_workspace_schema  # noqa: E402
from storyboard_delivery import validate_structure  # noqa: E402
from storyboard_review import validate_workspace  # noqa: E402


class ContractMigration313Tests(unittest.TestCase):
    def setUp(self) -> None:
        current_data = json.loads(
            (ROOT / "examples" / "kitchen-farewell-shot-data.json").read_text(encoding="utf-8")
        )
        current_workspace = json.loads(
            (ROOT / "examples" / "kitchen-farewell-director-workspace.json").read_text(encoding="utf-8")
        )
        self.old_data = copy.deepcopy(current_data)
        self.old_data["contract_version"] = "3.1.2"
        self.old_data["source_skill_version"] = "3.1.2"
        for shot in self.old_data["shots"]:
            shot.pop("shot_flow", None)
            shot.pop("viewpoint", None)
            for key in (
                "framing_mode",
                "primary_subjects",
                "foreground_subjects",
                "shot_size_reason",
                "angle_reason",
            ):
                shot["camera"].pop(key, None)
            shot["staging"].pop("visible_subjects", None)
            shot["staging"].pop("offscreen_subjects", None)
            shot["motivation"]["cut_or_hold_reason"] = "3.1.2 legacy boundary proof"
            shot["edit"]["reason"] = "3.1.2 legacy edit proof"

        self.old_workspace = copy.deepcopy(current_workspace)
        self.old_workspace["workspace_contract"] = "director-workspace/3.1.2"
        for strategy in self.old_workspace["scene_strategies"]:
            strategy.pop("camera_grammar", None)
            topology = strategy["topology"]
            for index, unit in enumerate(topology):
                unit.pop("viewing_design", None)
                boundary = unit.pop("boundary_to_next", None)
                unit["inter_shot_relation"] = (
                    boundary.get("relation", "cut") if isinstance(boundary, dict) else "scene_end"
                )
                unit["boundary_reason"] = {
                    "source_change": "3.1.2 legacy source change",
                    "mechanism_need": "3.1.2 legacy mechanism need",
                    "method_basis": "3.1.2 legacy method basis",
                    "alternative_rejected": "3.1.2 legacy alternative",
                }

    def test_build_drafts_preserves_input_and_invalidates_reviews(self) -> None:
        old_data_before = copy.deepcopy(self.old_data)
        old_workspace_before = copy.deepcopy(self.old_workspace)
        shot_draft, workspace_draft, report = build_drafts(self.old_data, self.old_workspace)

        self.assertEqual(old_data_before, self.old_data)
        self.assertEqual(old_workspace_before, self.old_workspace)
        self.assertEqual("3.1.3", shot_draft["contract_version"])
        self.assertEqual("3.1.3", shot_draft["source_skill_version"])
        self.assertEqual("draft", shot_draft["validation"]["status"])
        self.assertTrue(all(shot["shot_flow"] == [] for shot in shot_draft["shots"]))
        self.assertTrue(all("cut_or_hold_reason" not in shot["motivation"] for shot in shot_draft["shots"]))
        self.assertTrue(all("reason" not in shot["edit"] for shot in shot_draft["shots"]))
        for shot in shot_draft["shots"]:
            self.assertEqual("unresolved", shot["viewpoint"]["owner_type"])
            self.assertEqual("unresolved", shot["viewpoint"]["reading_priority"])
            self.assertEqual("unresolved", shot["viewpoint"]["camera_response"])
            self.assertEqual([], shot["viewpoint"]["owner_refs"])
            self.assertEqual("", shot["viewpoint"]["reason"])
            self.assertEqual("unresolved", shot["camera"]["framing_mode"])
            self.assertEqual([], shot["camera"]["primary_subjects"])
            self.assertEqual([], shot["camera"]["foreground_subjects"])
            self.assertEqual("", shot["camera"]["shot_size_reason"])
            self.assertEqual("", shot["camera"]["angle_reason"])
            self.assertEqual([], shot["staging"]["visible_subjects"])
            self.assertEqual([], shot["staging"]["offscreen_subjects"])

        self.assertEqual("director-workspace/3.1.3", workspace_draft["workspace_contract"])
        for strategy in workspace_draft["scene_strategies"]:
            self.assertEqual(
                {
                    "dominant_principle": "",
                    "change_triggers": [],
                    "progression": "",
                    "uniformity_intent": "",
                },
                strategy["camera_grammar"],
            )
            for unit in strategy["topology"]:
                self.assertEqual("unresolved", unit["viewing_design"]["owner_type"])
                self.assertEqual("unresolved", unit["viewing_design"]["framing_intent"])
                self.assertEqual("unresolved", unit["viewing_design"]["camera_response"])
                self.assertEqual([], unit["viewing_design"]["visible_subjects"])
                self.assertEqual([], unit["viewing_design"]["offscreen_subjects"])
                self.assertNotIn("inter_shot_relation", unit)
                self.assertNotIn("boundary_reason", unit)
                self.assertNotIn("boundary_to_next", unit)
        self.assertEqual("invalidated", workspace_draft["gate_1"]["status"])
        self.assertEqual("invalidated", workspace_draft["review_lock"]["gate_1_status"])
        self.assertEqual("invalidated", workspace_draft["review_lock"]["gate_2_status"])
        self.assertEqual("invalidated", workspace_draft["review_lock"]["alignment_status"])
        self.assertFalse(report["formal_ready"])
        self.assertEqual("VALID_MIGRATION_CARRIER", report["schema_status"])
        self.assertEqual(len(shot_draft["shots"]), len(report["shot_viewing_rebuild_required"]))
        self.assertEqual(
            len(workspace_draft["scene_strategies"]),
            len(report["workspace_camera_grammar_rebuild_required"]),
        )
        self.assertEqual(
            sum(len(item["topology"]) for item in workspace_draft["scene_strategies"]),
            len(report["workspace_viewing_design_rebuild_required"]),
        )
        expected_boundaries = sum(
            max(0, len(strategy["topology"]) - 1)
            for strategy in self.old_workspace["scene_strategies"]
        )
        self.assertEqual(expected_boundaries, len(report["boundary_to_next_rebuild_required"]))
        self.assertEqual("3.1.3", shot_draft["contract_version"])
        self.assertEqual("director-workspace/3.1.3", workspace_draft["workspace_contract"])
        self.assertTrue(all(shot["viewpoint"]["owner_type"] == "unresolved" for shot in shot_draft["shots"]))
        self.assertIn("CONTRACT_IDENTITY_MISMATCH", {item["code"] for item in validate_structure(shot_draft)["errors"]})

    def test_migration_strips_mixed_new_camera_fields_instead_of_guessing(self) -> None:
        mixed_data = copy.deepcopy(self.old_data)
        mixed_workspace = copy.deepcopy(self.old_workspace)
        mixed_data["shots"][0]["viewpoint"] = {
            "owner_type": "subject",
            "owner_refs": ["陈默"],
            "reading_priority": "face",
            "camera_response": "isolate",
            "reason": "未经 3.1.3 Gate 2 确认的混入字段。",
        }
        mixed_data["shots"][0]["camera"].update(
            {
                "framing_mode": "single",
                "primary_subjects": ["陈默"],
                "foreground_subjects": [],
                "shot_size_reason": "混入字段",
                "angle_reason": "混入字段",
            }
        )
        mixed_data["shots"][0]["staging"].update(
            {"visible_subjects": ["陈默"], "offscreen_subjects": ["林晓彤"]}
        )
        mixed_workspace["scene_strategies"][0]["camera_grammar"] = {
            "dominant_principle": "混入字段",
            "change_triggers": ["混入字段"],
            "progression": "混入字段",
            "uniformity_intent": "",
        }
        mixed_workspace["scene_strategies"][0]["topology"][0]["viewing_design"] = {
            "owner_type": "subject",
            "owner_refs": ["陈默"],
            "visible_subjects": ["陈默"],
            "offscreen_subjects": ["林晓彤"],
            "reading_priority": "face",
            "framing_intent": "single",
            "camera_response": "isolate",
            "reason": "混入字段",
        }

        shot_draft, workspace_draft, _ = build_drafts(mixed_data, mixed_workspace)
        self.assertEqual("unresolved", shot_draft["shots"][0]["viewpoint"]["owner_type"])
        self.assertEqual("unresolved", shot_draft["shots"][0]["camera"]["framing_mode"])
        self.assertEqual([], shot_draft["shots"][0]["staging"]["visible_subjects"])
        self.assertEqual(
            "",
            workspace_draft["scene_strategies"][0]["camera_grammar"]["dominant_principle"],
        )
        self.assertEqual(
            "unresolved",
            workspace_draft["scene_strategies"][0]["topology"][0]["viewing_design"]["owner_type"],
        )

    def test_source_mismatch_is_rejected(self) -> None:
        changed_workspace = copy.deepcopy(self.old_workspace)
        changed_workspace["source"]["locked_text"] += "\n未经确认的新增来源。"
        with self.assertRaisesRegex(ValueError, "locked_text 不一致"):
            build_drafts(self.old_data, changed_workspace)

    def test_cli_writes_three_new_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shot_path = root / "old-shot-data.json"
            workspace_path = root / "old-workspace.json"
            shot_path.write_text(json.dumps(self.old_data, ensure_ascii=False), encoding="utf-8")
            workspace_path.write_text(json.dumps(self.old_workspace, ensure_ascii=False), encoding="utf-8")
            output = root / "Migrated"
            code = main(
                [
                    "--shot-data",
                    str(shot_path),
                    "--workspace",
                    str(workspace_path),
                    "--output-dir",
                    str(output),
                ]
            )
            self.assertEqual(0, code)
            self.assertEqual(3, len(list(output.iterdir())))

    def test_cli_refuses_nonempty_directory_without_touching_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shot_path = root / "old-shot-data.json"
            workspace_path = root / "old-workspace.json"
            shot_path.write_text(json.dumps(self.old_data, ensure_ascii=False), encoding="utf-8")
            workspace_path.write_text(json.dumps(self.old_workspace, ensure_ascii=False), encoding="utf-8")
            output = root / "Migrated"
            output.mkdir()
            sentinel = output / "historical.json"
            original_bytes = b"historical-bytes"
            sentinel.write_bytes(original_bytes)
            code = main(
                [
                    "--shot-data",
                    str(shot_path),
                    "--workspace",
                    str(workspace_path),
                    "--output-dir",
                    str(output),
                ]
            )
            self.assertEqual(2, code)
            self.assertEqual(original_bytes, sentinel.read_bytes())


if __name__ == "__main__":
    unittest.main()
