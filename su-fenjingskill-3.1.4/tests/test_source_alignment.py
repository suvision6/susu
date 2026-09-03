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

from migrate_contract_3_1_0_to_3_1_2 import build_drafts  # noqa: E402
from source_alignment import (  # noqa: E402
    materialize_source_excerpts,
    supplemental_reference_approval_hash,
    text_hash,
)
from storyboard_delivery import build_outputs, validate_data  # noqa: E402
from storyboard_review import (  # noqa: E402
    all_expected_hashes,
    append_approval_event,
    gate_1_content_hash,
    gate_2_content_hash,
    lock_workspace,
    validate_workspace,
)


class SourceAlignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = json.loads((ROOT / "examples" / "kitchen-farewell-shot-data.json").read_text(encoding="utf-8"))
        self.workspace = json.loads((ROOT / "examples" / "kitchen-farewell-director-workspace.json").read_text(encoding="utf-8"))

    @staticmethod
    def error_codes(report):
        return {item["code"] for item in report["errors"]}

    @staticmethod
    def warning_codes(report):
        return {item["code"] for item in report["warnings"]}

    def relock(self, workspace, data):
        return lock_workspace(workspace, data)

    def simulate_renewed_review(self, workspace, data=None):
        """Test-only state renewal that still writes hash-bound approval events.

        Some tests intentionally construct semantically invalid data and therefore
        cannot call the public approval commands, which correctly fail preflight.
        """
        data = self.data if data is None else data
        hashes = all_expected_hashes(workspace, data)
        workspace["gate_1"].update(
            {
                "mode": "confirmed",
                "status": "passed",
                "method_hash": hashes["method_hash"],
                "note": "test-only renewed Gate 1",
            }
        )
        workspace["review_lock"].update(
            {
                "gate_1_status": "passed",
                "gate_1_basis": "test-only renewed Gate 1",
                "gate_2_status": "confirmed",
                "gate_2_confirmation_note": "test-only renewed Gate 2",
                "alignment_status": "passed",
                "alignment_note": "test-only renewed semantic review",
            }
        )
        append_approval_event(
            workspace,
            event_type="gate_1_approved",
            content_hash=gate_1_content_hash(hashes),
            reviewer="test",
            note="test-only renewed Gate 1",
        )
        append_approval_event(
            workspace,
            event_type="gate_2_confirmed",
            content_hash=gate_2_content_hash(hashes),
            reviewer="test",
            note="test-only renewed Gate 2",
        )
        append_approval_event(
            workspace,
            event_type="alignment_approved",
            content_hash=hashes["alignment_hash"],
            reviewer="test",
            note="test-only renewed semantic review",
        )
        return workspace

    @staticmethod
    def reference_fact(status="approved"):
        fact = {
            "reference_fact_id": "RF001",
            "statement": "生活声停止后可以保留一个短暂无声反应。",
            "source_excerpt": "参考资料建议在生活声停止后保留短暂无声。",
            "source_hash": "",
            "provenance": {
                "source_type": "user_supplied",
                "source_title": "用户补充的节奏参考",
                "locator": "fixture://kitchen-reference-001",
                "owner": "test reviewer",
            },
            "approval_status": status,
            "approval_hash": "",
            "approval_note": "test-only approval evidence" if status == "approved" else "awaiting reviewer approval",
        }
        fact["source_hash"] = text_hash(fact["source_excerpt"])
        fact["approval_hash"] = supplemental_reference_approval_hash(fact)
        return fact

    def test_workspace_is_required_for_formal_readiness(self) -> None:
        report = validate_data(self.data)
        self.assertEqual("FAIL", report["status"])
        self.assertIn("WORKSPACE_REQUIRED", self.error_codes(report))

    def test_subject_divergence_is_blocking(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["shot_bindings"][0]["fact_realizations"][0]["subject_owners"] = ["陈默"]
        changed = self.relock(changed, self.data)
        report = validate_workspace(changed, self.data)
        self.assertIn("SOURCE_EXECUTION_SUBJECT_DIVERGED", self.error_codes(report))

    def test_action_result_is_required(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["shot_bindings"][0]["fact_realizations"][0]["result_span"] = ""
        changed = self.relock(changed, self.data)
        report = validate_workspace(changed, self.data)
        self.assertIn("SOURCE_ACTION_RESULT_MISSING", self.error_codes(report))

    def test_action_result_cannot_be_downgraded_after_renewed_review(self) -> None:
        changed_data = copy.deepcopy(self.data)
        changed_workspace = copy.deepcopy(self.workspace)
        changed_workspace["source"]["source_facts"][0]["importance"] = "supporting"
        changed_workspace["shot_bindings"][0]["fact_realizations"] = []
        changed_workspace["scene_strategies"][0]["topology"][0]["source_fact_ids"] = []
        changed_data["shots"][0]["execution_text"] = changed_data["shots"][0]["execution_text"].replace("钥匙在木面停稳", "她保持站立")
        changed_workspace = self.simulate_renewed_review(self.relock(changed_workspace, changed_data))
        report = validate_data(changed_data, changed_workspace)
        self.assertIn("SOURCE_PROTECTED_FACT_DOWNGRADED", self.error_codes(report))
        self.assertIn("SOURCE_REQUIRED_FACT_INVENTORY_MISSING", self.error_codes(report))

    def test_causal_link_cannot_be_supporting(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["source"]["source_facts"].append(
            {
                "fact_id": "SF006",
                "passage_id": "SP003",
                "source_unit_ids": ["SU005"],
                "source_span": "陈默：什么时候决定的？",
                "kind": "causal_link",
                "subjects": ["陈默"],
                "predicate": "离开宣告导致追问",
                "objects": [],
                "polarity": "positive",
                "qualifiers": [],
                "importance": "supporting",
                "anchors": ["什么时候决定的？"],
                "cause_fact_ids": ["SF002"],
                "effect_fact_ids": ["SF004"],
            }
        )
        changed = self.simulate_renewed_review(self.relock(changed, self.data))
        report = validate_data(self.data, changed)
        self.assertIn("SOURCE_PROTECTED_FACT_DOWNGRADED", self.error_codes(report))

    def test_world_rule_cannot_be_supporting(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["source"]["source_facts"].append(
            {
                "fact_id": "SF006",
                "passage_id": "SP001",
                "source_unit_ids": ["SU002"],
                "source_span": "林晓彤把一把钥匙放在餐桌上。",
                "kind": "world_rule",
                "subjects": [],
                "predicate": "钥匙代表离开权限",
                "objects": ["钥匙"],
                "polarity": "positive",
                "qualifiers": [],
                "importance": "supporting",
                "anchors": ["钥匙"],
                "cause_fact_ids": [],
                "effect_fact_ids": [],
            }
        )
        changed = self.simulate_renewed_review(self.relock(changed, self.data))
        report = validate_data(self.data, changed)
        self.assertIn("SOURCE_PROTECTED_FACT_DOWNGRADED", self.error_codes(report))

    def test_authority_unit_cannot_be_owned_only_by_supporting_fact(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["source"]["source_facts"][3]["importance"] = "supporting"
        changed = self.simulate_renewed_review(self.relock(changed, self.data))
        report = validate_data(self.data, changed)
        self.assertIn("SOURCE_REQUIRED_FACT_INVENTORY_MISSING", self.error_codes(report))

    def test_negative_fact_cannot_be_reversed(self) -> None:
        changed = copy.deepcopy(self.workspace)
        negative_fact = {
            "fact_id": "SF006",
            "passage_id": "SP003",
            "source_unit_ids": ["SU005"],
            "source_span": "陈默：什么时候决定的？",
            "kind": "negation",
            "subjects": ["陈默"],
            "predicate": "切菜声不恢复",
            "objects": ["切菜声"],
            "polarity": "negative",
            "qualifiers": [],
            "importance": "required",
            "anchors": ["没有", "恢复"],
            "cause_fact_ids": [],
            "effect_fact_ids": [],
        }
        changed["source"]["source_facts"].append(negative_fact)
        changed["shot_bindings"][2]["fact_realizations"].append(
            {
                "fact_id": "SF006",
                "mode": "sound",
                "execution_span": "切菜声没有恢复",
                "subject_owners": ["陈默"],
                "result_span": "",
                "polarity": "positive",
            }
        )
        changed = self.relock(changed, self.data)
        report = validate_workspace(changed, self.data)
        self.assertIn("SOURCE_NEGATION_DROPPED", self.error_codes(report))

    def test_causal_order_is_checked(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["source"]["source_facts"].append(
            {
                "fact_id": "SF006",
                "passage_id": "SP003",
                "source_unit_ids": ["SU005"],
                "source_span": "陈默：什么时候决定的？",
                "kind": "causal_link",
                "subjects": [],
                "predicate": "提问导致离开宣告",
                "objects": [],
                "polarity": "positive",
                "qualifiers": [],
                "importance": "supporting",
                "anchors": [],
                "cause_fact_ids": ["SF004"],
                "effect_fact_ids": ["SF002"],
            }
        )
        changed = self.relock(changed, self.data)
        report = validate_workspace(changed, self.data)
        self.assertIn("SOURCE_CAUSAL_LINK_MISSING", self.error_codes(report))

    def test_reference_language_cannot_enter_authoritative_passage(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["source"]["authority_policy"]["reference_languages"] = ["en"]
        changed["source"]["authority_policy"]["bilingual_relation"] = "adapted_equivalent"
        changed["source"]["scopes"][0]["authority_line_ranges"] = [{"line_start": 1, "line_end": 4}]
        changed["source"]["scopes"][0]["reference_line_ranges"] = [{"line_start": 5, "line_end": 5}]
        changed["source"]["source_units"][4]["language"] = "en"
        changed["source"]["source_units"][4]["authority_role"] = "adapted_reference"
        changed = self.relock(changed, self.data)
        report = validate_workspace(changed, self.data)
        self.assertIn("SOURCE_REFERENCE_RENDERED", self.error_codes(report))

    def test_context_only_passage_fails(self) -> None:
        changed_data = copy.deepcopy(self.data)
        changed_workspace = copy.deepcopy(self.workspace)
        old_lines = changed_workspace["source"]["locked_text"].split("\n")
        old_lines[-1] = "高空。"
        locked = "\n".join(old_lines)
        changed_workspace["source"]["locked_text"] = locked
        changed_workspace["source"]["source_hash"] = text_hash(locked)
        unit = changed_workspace["source"]["source_units"][4]
        unit.update({"kind": "action", "exact_text": "高空。", "semantic_summary": "高空方位片段。"})
        unit.pop("speaker", None)
        unit.pop("voice_type", None)
        unit.pop("dialogue_id", None)
        changed_data["source"]["locked_text"] = locked
        changed_data["source"]["dialogue_lines"] = changed_data["source"]["dialogue_lines"][:1]
        changed_data["shots"][2]["execution_text"] += " 高空。"
        changed_workspace["source"]["source_facts"][3].update(
            {"kind": "state", "subjects": [], "predicate": "高空", "objects": [], "anchors": ["高空"], "source_span": "高空。"}
        )
        changed_workspace["shot_bindings"][2]["fact_realizations"][0].update(
            {"mode": "visual", "execution_span": "高空。", "subject_owners": []}
        )
        changed_workspace = self.relock(changed_workspace, changed_data)
        report = validate_workspace(changed_workspace, changed_data)
        self.assertIn("SOURCE_PASSAGE_CONTEXT_INCOMPLETE", self.error_codes(report))

    def test_manual_excerpt_is_rederived(self) -> None:
        changed = copy.deepcopy(self.data)
        changed["shots"][0]["source_excerpt"] = "任意手写锚点"
        report = validate_data(changed, self.workspace)
        self.assertEqual("READY", report["status"])
        self.assertNotIn("SOURCE_EXCERPT_REDERIVED", self.warning_codes(report))
        built, _ = materialize_source_excerpts(self.workspace, changed)
        self.assertEqual("内景·厨房·夜\n林晓彤把一把钥匙放在餐桌上。", built["shots"][0]["source_excerpt"])

    def test_fail_closed_build_writes_only_validation(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["review_lock"]["gate_2_status"] = "pending"
        with tempfile.TemporaryDirectory() as directory:
            report, paths = build_outputs(self.data, changed, Path(directory), strict=False)
            self.assertEqual("FAIL", report["status"])
            self.assertEqual({}, paths)
            self.assertFalse(Path(directory).joinpath("kitchen-farewell-storyboard-validation.json").exists())

    def test_legacy_migration_is_draft_and_preserves_input(self) -> None:
        legacy = copy.deepcopy(self.data)
        legacy["contract_version"] = "3.1.0"
        legacy["source_skill_version"] = "3.1.1"
        original = copy.deepcopy(legacy)
        shot_draft, workspace_draft, report = build_drafts(legacy, None)
        self.assertEqual(original, legacy)
        self.assertEqual("3.1.2", shot_draft["contract_version"])
        self.assertEqual("draft", shot_draft["validation"]["status"])
        self.assertEqual("director-workspace/3.1.2", workspace_draft["workspace_contract"])
        self.assertEqual("pending", workspace_draft["review_lock"]["alignment_status"])
        self.assertEqual("invalidated", workspace_draft["review_lock"]["gate_2_status"])
        self.assertFalse(report["formal_ready"])

    def test_contracts_are_3_1_4(self) -> None:
        self.assertEqual("3.1.4", self.data["contract_version"])
        self.assertEqual("3.1.4", self.data["source_skill_version"])
        self.assertEqual("director-workspace/3.1.4", self.workspace["workspace_contract"])

    def test_fact_and_realization_cannot_be_deleted_together(self) -> None:
        changed_data = copy.deepcopy(self.data)
        changed_workspace = copy.deepcopy(self.workspace)
        changed_workspace["source"]["source_facts"] = [
            fact for fact in changed_workspace["source"]["source_facts"] if fact["fact_id"] != "SF004"
        ]
        changed_workspace["shot_bindings"][2]["fact_realizations"] = []
        changed_workspace["scene_strategies"][0]["topology"][2]["source_fact_ids"] = []
        changed_data["shots"][2]["execution_text"] = changed_data["shots"][2]["execution_text"].replace("问：“什么时候决定的？”", "保持沉默。")
        changed_workspace = lock_workspace(changed_workspace, changed_data)
        report = validate_data(changed_data, changed_workspace)
        self.assertIn("SOURCE_FACT_INVENTORY_MISSING", self.error_codes(report))
        self.assertIn("SOURCE_REQUIRED_FACT_INVENTORY_MISSING", self.error_codes(report))

    def test_negative_fact_inventory_is_derived_from_locked_unit(self) -> None:
        changed_data = copy.deepcopy(self.data)
        changed_workspace = copy.deepcopy(self.workspace)
        lines = changed_workspace["source"]["locked_text"].split("\n")
        lines[-1] = "没有警告。"
        locked = "\n".join(lines)
        changed_workspace["source"]["locked_text"] = locked
        changed_workspace["source"]["source_hash"] = text_hash(locked)
        unit = changed_workspace["source"]["source_units"][4]
        unit.update({"kind": "action", "exact_text": "没有警告。", "semantic_summary": "明确否定警告。"})
        unit.pop("speaker", None)
        unit.pop("voice_type", None)
        unit.pop("dialogue_id", None)
        changed_workspace["source"]["source_facts"] = [
            fact for fact in changed_workspace["source"]["source_facts"] if fact["fact_id"] != "SF004"
        ]
        changed_workspace["shot_bindings"][2]["fact_realizations"] = []
        changed_workspace["scene_strategies"][0]["topology"][2]["source_fact_ids"] = []
        changed_data["source"]["locked_text"] = locked
        changed_data["source"]["dialogue_lines"] = changed_data["source"]["dialogue_lines"][:1]
        changed_data["shots"][2]["execution_text"] = "【近景｜平视｜固定】\n【画面内容】陈默保持沉默。"
        changed_workspace = lock_workspace(changed_workspace, changed_data)
        report = validate_data(changed_data, changed_workspace)
        self.assertIn("SOURCE_REQUIRED_FACT_INVENTORY_MISSING", self.error_codes(report))

    def test_lock_invalidates_alignment_and_gate_after_execution_change(self) -> None:
        changed_data = copy.deepcopy(self.data)
        changed_data["shots"][0]["execution_text"] += "天空突然下雨，卫兵全部消失。"
        changed_workspace = lock_workspace(self.workspace, changed_data)
        self.assertEqual("invalidated", changed_workspace["review_lock"]["alignment_status"])
        self.assertEqual("confirmed", changed_workspace["review_lock"]["gate_2_status"])
        report = validate_data(changed_data, changed_workspace)
        self.assertEqual("FAIL", report["status"])
        self.assertIn("SOURCE_ALIGNMENT_INVALIDATED", self.error_codes(report))

    def test_shot_flow_change_invalidates_alignment_only(self) -> None:
        changed_data = copy.deepcopy(self.data)
        changed_data["shots"][0]["shot_flow"].append({"owner": "performance"})
        changed_workspace = lock_workspace(self.workspace, changed_data)
        self.assertEqual("confirmed", changed_workspace["review_lock"]["gate_2_status"])
        self.assertEqual("invalidated", changed_workspace["review_lock"]["alignment_status"])

    def test_unregistered_supplemental_reference_is_blocking_after_renewed_review(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["director_inferences"].append(
            {
                "inference_id": "DI001",
                "scope": "SC001",
                "statement": "刀声停止后留短暂无声。",
                "basis_fact_ids": [],
                "reference_fact_ids": ["RF999"],
                "shot_refs": ["SH002"],
                "reversibility": "reversible",
                "status": "approved",
                "conflicts_with_fact_ids": [],
            }
        )
        changed["shot_bindings"][1]["director_inference_ids"] = ["DI001"]
        changed = self.simulate_renewed_review(self.relock(changed, self.data))
        report = validate_data(self.data, changed)
        self.assertIn("DIRECTOR_INFERENCE_REFERENCE_UNKNOWN", self.error_codes(report))

    def test_unapproved_supplemental_reference_is_blocking(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["supplemental_reference_facts"] = [self.reference_fact("pending")]
        changed["director_inferences"].append(
            {
                "inference_id": "DI001",
                "scope": "SC001",
                "statement": "刀声停止后留短暂无声。",
                "basis_fact_ids": [],
                "reference_fact_ids": ["RF001"],
                "shot_refs": ["SH002"],
                "reversibility": "reversible",
                "status": "proposed",
                "conflicts_with_fact_ids": [],
            }
        )
        changed = self.simulate_renewed_review(self.relock(changed, self.data))
        report = validate_data(self.data, changed)
        self.assertIn("DIRECTOR_INFERENCE_REFERENCE_NOT_APPROVED", self.error_codes(report))

    def test_supplemental_reference_hash_change_is_blocking(self) -> None:
        changed = copy.deepcopy(self.workspace)
        reference_fact = self.reference_fact("approved")
        reference_fact["source_excerpt"] += "未重新批准的修改。"
        changed["supplemental_reference_facts"] = [reference_fact]
        changed["director_inferences"].append(
            {
                "inference_id": "DI001",
                "scope": "SC001",
                "statement": "刀声停止后留短暂无声。",
                "basis_fact_ids": [],
                "reference_fact_ids": ["RF001"],
                "shot_refs": ["SH002"],
                "reversibility": "reversible",
                "status": "approved",
                "conflicts_with_fact_ids": [],
            }
        )
        changed = self.simulate_renewed_review(self.relock(changed, self.data))
        report = validate_data(self.data, changed)
        self.assertIn("SUPPLEMENTAL_REFERENCE_HASH_MISMATCH", self.error_codes(report))
        self.assertIn("DIRECTOR_INFERENCE_REFERENCE_HASH_INVALID", self.error_codes(report))

    def test_approved_hash_valid_supplemental_reference_can_ground_inference(self) -> None:
        changed = copy.deepcopy(self.workspace)
        changed["supplemental_reference_facts"] = [self.reference_fact("approved")]
        changed["director_inferences"].append(
            {
                "inference_id": "DI001",
                "scope": "SC001",
                "statement": "刀声停止后留短暂无声。",
                "basis_fact_ids": [],
                "reference_fact_ids": ["RF001"],
                "shot_refs": ["SH002"],
                "reversibility": "reversible",
                "status": "approved",
                "conflicts_with_fact_ids": [],
            }
        )
        changed["shot_bindings"][1]["director_inference_ids"] = ["DI001"]
        changed = self.simulate_renewed_review(self.relock(changed, self.data))
        report = validate_data(self.data, changed)
        self.assertNotEqual("FAIL", report["status"])

    def test_build_refuses_nonempty_output_directory_without_modifying_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            historical = output_dir / "historical-storyboard-validation.json"
            sentinel = b"historical-validation-bytes"
            historical.write_bytes(sentinel)
            report, paths = build_outputs(self.data, self.workspace, output_dir)
            self.assertEqual("FAIL", report["status"])
            self.assertIn("OUTPUT_DIR_NOT_EMPTY", self.error_codes(report))
            self.assertEqual({}, paths)
            self.assertEqual(sentinel, historical.read_bytes())


if __name__ == "__main__":
    unittest.main()
