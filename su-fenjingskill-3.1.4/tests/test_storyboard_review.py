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

from _execution_text import canonical_execution_text  # noqa: E402
from storyboard_review import approve_alignment, lock_workspace, validate_workspace  # noqa: E402


class StoryboardReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = json.loads((ROOT / "examples" / "kitchen-farewell-director-workspace.json").read_text(encoding="utf-8"))
        self.shot_data = json.loads((ROOT / "examples" / "kitchen-farewell-shot-data.json").read_text(encoding="utf-8"))

    @staticmethod
    def codes(report):
        return {item["code"] for item in report["errors"]}

    def test_valid_workspace_passes(self) -> None:
        report = validate_workspace(self.workspace, self.shot_data)
        self.assertEqual("PASS", report["status"])
        self.assertEqual([], report["errors"])

    def test_missing_source_unit_fails_reverse_coverage(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["source"]["source_units"].pop()
        changed = lock_workspace(changed, self.shot_data)
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
        relocked = lock_workspace(changed, changed_data)
        self.assertEqual("invalidated", relocked["review_lock"]["gate_1_status"])
        self.assertEqual("invalidated", relocked["review_lock"]["gate_2_status"])
        self.assertEqual("invalidated", relocked["review_lock"]["alignment_status"])
        report = validate_workspace(relocked, changed_data)
        self.assertIn("GATE_1_REQUIRED", self.codes(report))

    def test_method_change_invalidates_gate_one_and_gate_two(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["director_method"]["time_model"] = "改为高度压缩的交叉时间。"
        relocked = lock_workspace(changed, self.shot_data)
        self.assertEqual("invalidated", relocked["review_lock"]["gate_1_status"])
        self.assertEqual("invalidated", relocked["review_lock"]["gate_2_status"])

    def test_strategy_change_invalidates_gate_two_only(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["scene_strategies"][0]["shot_density_curve"] = "前段密集、后段突然停留。"
        relocked = lock_workspace(changed, self.shot_data)
        self.assertEqual("passed", relocked["review_lock"]["gate_1_status"])
        self.assertEqual("invalidated", relocked["review_lock"]["gate_2_status"])
        self.assertEqual("invalidated", relocked["review_lock"]["alignment_status"])

    def test_topology_change_invalidates_gate_two(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["scene_strategies"][0]["topology"][0]["boundary_to_next"]["relation"] = "sound_bridge"
        relocked = lock_workspace(changed, self.shot_data)
        self.assertEqual("passed", relocked["review_lock"]["gate_1_status"])
        self.assertEqual("invalidated", relocked["review_lock"]["gate_2_status"])

    def test_execution_change_invalidates_alignment_only(self) -> None:
        changed_data = copy.deepcopy(self.shot_data)
        changed_data["shots"][0]["notes"] = "待确认演员手部动作速度。"
        relocked = lock_workspace(self.workspace, changed_data)
        self.assertEqual("passed", relocked["review_lock"]["gate_1_status"])
        self.assertEqual("confirmed", relocked["review_lock"]["gate_2_status"])
        self.assertEqual("invalidated", relocked["review_lock"]["alignment_status"])

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

    def test_twenty_five_second_shot_is_not_an_artistic_failure(self) -> None:
        changed_data = copy.deepcopy(self.shot_data)
        changed_data["shots"][1]["duration_seconds"] = 25
        changed_data["shots"][1]["execution_text"] = canonical_execution_text(changed_data["shots"][1])
        relocked = lock_workspace(self.workspace, changed_data)
        self.assertEqual("confirmed", relocked["review_lock"]["gate_2_status"])
        reviewed = approve_alignment(relocked, changed_data, reviewer="test", note="镜长执行复核")
        report = validate_workspace(reviewed, changed_data)
        self.assertEqual("PASS", report["status"])

    def test_intentional_omission_requires_reason(self) -> None:
        changed = copy.deepcopy(self.workspace)
        passage = changed["source"]["source_passages"][0]
        passage["coverage_status"] = "intentionally_omitted"
        passage["shot_refs"] = []
        passage["reason"] = ""
        changed = lock_workspace(changed, self.shot_data)
        report = validate_workspace(changed, self.shot_data, check_review_states=False)
        self.assertIn("SOURCE_OMISSION_REASON_EMPTY", self.codes(report))

    def test_formal_contract_is_3_1_4(self) -> None:
        changed_data = copy.deepcopy(self.shot_data)
        changed_data["contract_version"] = "3.1.0"
        report = validate_workspace(self.workspace, changed_data)
        self.assertIn("FORMAL_CONTRACT_MISMATCH", self.codes(report))

    def test_formal_source_skill_version_is_3_1_4(self) -> None:
        changed_data = copy.deepcopy(self.shot_data)
        changed_data["source_skill_version"] = "3.1.1"
        report = validate_workspace(self.workspace, changed_data)
        self.assertIn("FORMAL_CONTRACT_MISMATCH", self.codes(report))

    def test_every_formal_shot_must_be_in_confirmed_topology(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["scene_strategies"][0]["topology"].pop()
        changed = lock_workspace(changed, self.shot_data)
        report = validate_workspace(changed, self.shot_data, check_review_states=False)
        self.assertIn("FORMAL_SHOTS_OUTSIDE_TOPOLOGY", self.codes(report))

    def test_empty_shot_flow_is_blocking(self) -> None:
        changed_data = copy.deepcopy(self.shot_data)
        changed_data["shots"][0]["shot_flow"] = []
        report = validate_workspace(self.workspace, changed_data, check_review_states=False)
        self.assertIn("SHOT_FLOW_REQUIRED", self.codes(report))

    def test_invalid_shot_flow_owner_is_blocking(self) -> None:
        changed_data = copy.deepcopy(self.shot_data)
        changed_data["shots"][0]["shot_flow"] = [{"owner": "free_text"}]
        report = validate_workspace(self.workspace, changed_data, check_review_states=False)
        self.assertIn("SHOT_FLOW_OWNER_INVALID", self.codes(report))

    def test_camera_setup_must_appear_exactly_once(self) -> None:
        changed_data = copy.deepcopy(self.shot_data)
        flow = changed_data["shots"][0]["shot_flow"]
        changed_data["shots"][0]["shot_flow"] = [item for item in flow if item.get("owner") != "camera_setup"]
        report = validate_workspace(self.workspace, changed_data, check_review_states=False)
        self.assertIn("SHOT_FLOW_CAMERA_SETUP_COUNT", self.codes(report))

        changed_data = copy.deepcopy(self.shot_data)
        changed_data["shots"][0]["shot_flow"].append({"owner": "camera_setup"})
        report = validate_workspace(self.workspace, changed_data, check_review_states=False)
        self.assertIn("SHOT_FLOW_CAMERA_SETUP_COUNT", self.codes(report))

    def test_shot_flow_index_must_resolve_backend_array(self) -> None:
        changed_data = copy.deepcopy(self.shot_data)
        changed_data["shots"][0]["shot_flow"].append({"owner": "effect", "index": 999})
        report = validate_workspace(self.workspace, changed_data, check_review_states=False)
        self.assertIn("SHOT_FLOW_INDEX_OUT_OF_RANGE", self.codes(report))

    def test_shot_flow_span_must_be_verbatim(self) -> None:
        changed_data = copy.deepcopy(self.shot_data)
        changed_data["shots"][0]["shot_flow"].append({"owner": "blocking", "span": "后端没有的自由正文"})
        report = validate_workspace(self.workspace, changed_data, check_review_states=False)
        self.assertIn("SHOT_FLOW_SPAN_MISMATCH", self.codes(report))

    def test_dialogue_flow_requires_complete_unique_ordered_playback(self) -> None:
        dialogue_shot_index = next(
            index
            for index, shot in enumerate(self.shot_data["shots"])
            if shot["sound"]["dialogue_segments"]
        )
        changed_data = copy.deepcopy(self.shot_data)
        shot = changed_data["shots"][dialogue_shot_index]
        shot["shot_flow"] = [item for item in shot["shot_flow"] if item.get("owner") != "dialogue_segment"]
        report = validate_workspace(self.workspace, changed_data, check_review_states=False)
        self.assertIn("SHOT_FLOW_DIALOGUE_MISSING", self.codes(report))

        changed_data = copy.deepcopy(self.shot_data)
        shot = changed_data["shots"][dialogue_shot_index]
        shot["shot_flow"].append({"owner": "dialogue_segment", "index": 0})
        report = validate_workspace(self.workspace, changed_data, check_review_states=False)
        self.assertIn("SHOT_FLOW_DIALOGUE_DUPLICATE", self.codes(report))

        changed_data = copy.deepcopy(self.shot_data)
        shot = changed_data["shots"][dialogue_shot_index]
        shot["sound"]["dialogue_segments"].append(copy.deepcopy(shot["sound"]["dialogue_segments"][0]))
        non_dialogue_flow = [item for item in shot["shot_flow"] if item.get("owner") != "dialogue_segment"]
        shot["shot_flow"] = non_dialogue_flow + [
            {"owner": "dialogue_segment", "index": 1},
            {"owner": "dialogue_segment", "index": 0},
        ]
        report = validate_workspace(self.workspace, changed_data, check_review_states=False)
        self.assertIn("SHOT_FLOW_DIALOGUE_ORDER", self.codes(report))

    def test_non_fixed_movement_is_required_once(self) -> None:
        changed_data = copy.deepcopy(self.shot_data)
        shot = changed_data["shots"][0]
        shot["camera"]["movement"]["type"] = "push"
        shot["shot_flow"] = [item for item in shot["shot_flow"] if item.get("owner") != "movement"]
        report = validate_workspace(self.workspace, changed_data, check_review_states=False)
        self.assertIn("SHOT_FLOW_MOVEMENT_REQUIRED", self.codes(report))

        shot["shot_flow"].extend([{"owner": "movement"}, {"owner": "movement"}])
        report = validate_workspace(self.workspace, changed_data, check_review_states=False)
        self.assertIn("SHOT_FLOW_MOVEMENT_DUPLICATE", self.codes(report))

    def test_topology_requires_exactly_n_minus_one_boundaries(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["scene_strategies"][0]["topology"][0].pop("boundary_to_next")
        report = validate_workspace(changed, self.shot_data, check_review_states=False)
        self.assertIn("BOUNDARY_TO_NEXT_MISSING", self.codes(report))

        changed = copy.deepcopy(self.workspace)
        changed["scene_strategies"][0]["topology"][-1]["boundary_to_next"] = {
            "relation": "cut",
            "trigger": "人物转身离开画面。",
            "editorial_gain": "切开后把观看权交给下一场的新空间。",
        }
        report = validate_workspace(changed, self.shot_data, check_review_states=False)
        self.assertIn("TERMINAL_BOUNDARY_FORBIDDEN", self.codes(report))

    def test_boundary_must_name_concrete_trigger_and_gain(self) -> None:
        changed = copy.deepcopy(self.workspace)
        boundary = changed["scene_strategies"][0]["topology"][0]["boundary_to_next"]
        boundary["trigger"] = "动作变化"
        boundary["editorial_gain"] = "增强节奏"
        report = validate_workspace(changed, self.shot_data, check_review_states=False)
        self.assertIn("BOUNDARY_TRIGGER_VAGUE", self.codes(report))
        self.assertIn("BOUNDARY_EDITORIAL_GAIN_VAGUE", self.codes(report))


if __name__ == "__main__":
    unittest.main()
