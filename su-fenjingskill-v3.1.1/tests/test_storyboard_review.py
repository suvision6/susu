#!/usr/bin/env python3

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from storyboard_review import lock_workspace, validate_workspace


class StoryboardReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = json.loads(
            (ROOT / "examples" / "kitchen-farewell-director-workspace.json").read_text(
                encoding="utf-8"
            )
        )
        self.shot_data = json.loads(
            (ROOT / "examples" / "kitchen-farewell-shot-data.json").read_text(
                encoding="utf-8"
            )
        )

    def codes(self, report):
        return {item["code"] for item in report["errors"]}

    def test_valid_workspace_passes(self) -> None:
        report = validate_workspace(self.workspace, self.shot_data)
        self.assertEqual("PASS", report["status"])
        self.assertEqual([], report["errors"])

    def test_missing_source_unit_fails_reverse_coverage(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["source"]["source_units"].pop()
        changed = lock_workspace(changed)
        report = validate_workspace(changed, self.shot_data)
        self.assertIn("SOURCE_LINES_UNCOVERED", self.codes(report))

    def test_dialogue_not_registered_fails(self) -> None:
        changed_data = copy.deepcopy(self.shot_data)
        changed_data["source"]["dialogue_lines"] = changed_data["source"]["dialogue_lines"][:1]
        report = validate_workspace(self.workspace, changed_data)
        self.assertIn("SOURCE_DIALOGUE_NOT_REGISTERED", self.codes(report))

    def test_source_change_invalidates_both_gates(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["source"]["locked_text"] += "\n门外传来脚步。"
        changed_data = copy.deepcopy(self.shot_data)
        changed_data["source"]["locked_text"] = changed["source"]["locked_text"]
        report = validate_workspace(changed, changed_data)
        self.assertIn("SOURCE_LOCK_INVALIDATED", self.codes(report))
        self.assertIn("GATE_1_INVALIDATED", self.codes(report))

    def test_method_change_invalidates_gate_one_and_gate_two(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["director_method"]["time_model"] = "改为高度压缩的交叉时间。"
        report = validate_workspace(changed, self.shot_data)
        self.assertIn("GATE_1_INVALIDATED", self.codes(report))

    def test_strategy_change_invalidates_gate_two_only(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["scene_strategies"][0]["shot_density_curve"] = "前段密集、后段突然停留。"
        report = validate_workspace(changed, self.shot_data)
        self.assertIn("GATE_2_INVALIDATED", self.codes(report))
        self.assertNotIn("GATE_1_INVALIDATED", self.codes(report))

    def test_topology_change_invalidates_gate_two(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["scene_strategies"][0]["topology"][0]["inter_shot_relation"] = "sound_bridge"
        report = validate_workspace(changed, self.shot_data)
        self.assertIn("GATE_2_INVALIDATED", self.codes(report))

    def test_gate_one_required_blocks_formal_review(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["gate_1"]["mode"] = "required"
        changed["gate_1"]["status"] = "pending"
        changed["review_lock"]["gate_1_status"] = "pending"
        report = validate_workspace(changed, self.shot_data)
        self.assertIn("GATE_1_REQUIRED", self.codes(report))

    def test_gate_two_is_mandatory(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["review_lock"]["gate_2_status"] = "pending"
        report = validate_workspace(changed, self.shot_data)
        self.assertIn("GATE_2_REQUIRED", self.codes(report))

    def test_twenty_second_shot_is_not_an_artistic_failure(self) -> None:
        changed_data = copy.deepcopy(self.shot_data)
        changed_data["shots"][1]["duration_seconds"] = 25
        report = validate_workspace(self.workspace, changed_data)
        self.assertEqual("PASS", report["status"])

    def test_intentional_omission_requires_reason(self) -> None:
        changed = copy.deepcopy(self.workspace)
        unit = changed["source"]["source_units"][1]
        unit["coverage_status"] = "intentionally_omitted"
        unit["shot_refs"] = []
        unit["reason"] = ""
        changed = lock_workspace(changed)
        report = validate_workspace(changed, self.shot_data)
        self.assertIn("SOURCE_OMISSION_REASON_EMPTY", self.codes(report))

    def test_formal_contract_is_3_1_0(self) -> None:
        changed_data = copy.deepcopy(self.shot_data)
        changed_data["contract_version"] = "3.0.0"
        report = validate_workspace(self.workspace, changed_data)
        self.assertIn("FORMAL_CONTRACT_MISMATCH", self.codes(report))

    def test_formal_source_skill_version_is_3_1_1(self) -> None:
        changed_data = copy.deepcopy(self.shot_data)
        changed_data["source_skill_version"] = "3.1.0"
        report = validate_workspace(self.workspace, changed_data)
        self.assertIn("FORMAL_CONTRACT_MISMATCH", self.codes(report))

    def test_every_formal_shot_must_be_in_confirmed_topology(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["scene_strategies"][0]["topology"].pop()
        changed = lock_workspace(changed)
        report = validate_workspace(changed, self.shot_data)
        self.assertIn("FORMAL_SHOTS_OUTSIDE_TOPOLOGY", self.codes(report))


if __name__ == "__main__":
    unittest.main()
