from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _execution_text import canonical_execution_text  # noqa: E402
from source_alignment import (  # noqa: E402
    classification_review_hash,
    supplemental_reference_approval_hash,
    text_hash,
)
from storyboard_delivery import build_outputs, validate_data, validate_structure  # noqa: E402
from storyboard_review import lock_workspace, validate_workspace  # noqa: E402


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def error_codes(report):
    return {item["code"] for item in report.get("errors", [])}


def resolve_schema(schema, root):
    while isinstance(schema, dict) and "$ref" in schema:
        target = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        schema = target
    return schema


def required_paths(instance, schema, root, path=()):
    """Yield required-property paths exercised by a valid example instance."""
    schema = resolve_schema(schema, root)
    if not isinstance(schema, dict):
        return

    # Apply every compatible composition branch. This is intentionally instance
    # driven, so it probes the actual 3.1.3 examples rather than dead definitions.
    for keyword in ("allOf", "oneOf", "anyOf"):
        branches = schema.get(keyword)
        if isinstance(branches, list):
            for branch in branches:
                resolved = resolve_schema(branch, root)
                if keyword == "allOf" or Draft202012Validator(resolved).is_valid(instance):
                    yield from required_paths(instance, resolved, root, path)

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key in instance:
                yield path + (key,)
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, value in instance.items():
                child_schema = properties.get(key)
                if child_schema is not None:
                    yield from required_paths(value, child_schema, root, path + (key,))
    elif isinstance(instance, list):
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, value in enumerate(instance):
                yield from required_paths(value, item_schema, root, path + (index,))


def delete_path(value, path):
    target = value
    for part in path[:-1]:
        target = target[part]
    del target[path[-1]]


class P0RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_json(ROOT / "examples" / "kitchen-farewell-shot-data.json")
        cls.workspace = load_json(ROOT / "examples" / "kitchen-farewell-director-workspace.json")
        cls.concept_data = load_json(ROOT / "examples" / "unknown-room-awakening-shot-data.json")
        cls.concept_workspace = load_json(ROOT / "examples" / "unknown-room-awakening-director-workspace.json")
        cls.formal_schema = load_json(ROOT / "schemas" / "director-shot-data.schema.json")
        cls.workspace_schema = load_json(ROOT / "schemas" / "director-workspace.schema.json")

    def test_p0_01_narrative_line_cannot_be_laundered_as_metadata(self):
        changed = copy.deepcopy(self.workspace)
        target_unit = next(unit for unit in changed["source"]["source_units"] if unit["unit_id"] == "SU004")
        target_unit["kind"] = "metadata"
        target_unit["authority_role"] = "non_narrative"

        # Remove the associated facts and realizations exactly as the original
        # bypass attempted. The ledger classification itself must still block.
        removed_fact_ids = {"SF003", "SF005"}
        changed["source"]["source_facts"] = [
            fact for fact in changed["source"]["source_facts"] if fact["fact_id"] not in removed_fact_ids
        ]
        for passage in changed["source"]["source_passages"]:
            passage["source_unit_ids"] = [unit_id for unit_id in passage["source_unit_ids"] if unit_id != "SU004"]
        for strategy in changed["scene_strategies"]:
            for topology in strategy["topology"]:
                topology["source_fact_ids"] = [
                    fact_id for fact_id in topology["source_fact_ids"] if fact_id not in removed_fact_ids
                ]
        for binding in changed["shot_bindings"]:
            binding["fact_realizations"] = [
                realization
                for realization in binding["fact_realizations"]
                if realization["fact_id"] not in removed_fact_ids
            ]

        report = validate_workspace(changed, self.data, check_review_states=False)
        self.assertEqual("FAIL", report["status"])
        self.assertTrue(
            {"SOURCE_NARRATIVE_CLASSIFICATION_FORBIDDEN", "SOURCE_NON_NARRATIVE_CLASSIFICATION_UNAPPROVED"}
            & error_codes(report)
        )


    def test_p0_01_forged_classification_review_cannot_override_probable_narrative(self):
        changed = copy.deepcopy(self.workspace)
        target_unit = next(unit for unit in changed["source"]["source_units"] if unit["unit_id"] == "SU004")
        target_unit["kind"] = "metadata"
        target_unit["authority_role"] = "non_narrative"
        review = {
            "unit_id": "SU004",
            "decision": "non_narrative",
            "status": "approved",
            "reason": "test-only forged review",
            "source_text_hash": text_hash(target_unit["exact_text"]),
            "reviewer": "test",
        }
        review["review_hash"] = classification_review_hash(review)
        changed["source"]["classification_reviews"] = [review]
        report = validate_workspace(changed, self.data, check_review_states=False)
        self.assertEqual("FAIL", report["status"])
        self.assertIn("SOURCE_NARRATIVE_CLASSIFICATION_FORBIDDEN", error_codes(report))

    def test_p0_02_every_exercised_formal_required_field_is_runtime_enforced(self):
        paths = sorted(set(required_paths(self.data, self.formal_schema, self.formal_schema)), key=str)
        self.assertGreaterEqual(len(paths), 90)
        missed = []
        for path in paths:
            mutated = copy.deepcopy(self.data)
            delete_path(mutated, path)
            report = validate_structure(mutated)
            if "FORMAL_SCHEMA_INVALID" not in error_codes(report):
                missed.append(path)
        self.assertEqual([], missed, f"runtime missed formal required paths: {missed}")

    def test_p0_02_every_exercised_workspace_required_field_is_runtime_enforced(self):
        paths = sorted(set(required_paths(self.workspace, self.workspace_schema, self.workspace_schema)), key=str)
        self.assertGreaterEqual(len(paths), 115)
        missed = []
        for path in paths:
            mutated = copy.deepcopy(self.workspace)
            delete_path(mutated, path)
            report = validate_workspace(mutated, self.data, check_review_states=False)
            if "WORKSPACE_SCHEMA_INVALID" not in error_codes(report):
                missed.append(path)
        self.assertEqual([], missed, f"runtime missed workspace required paths: {missed}")

    def test_p0_03_all_formal_execution_fields_are_locked(self):
        mutations = {
            "camera": lambda data: data["shots"][0]["camera"].__setitem__("position", "越过既定轴线到反侧"),
            "edit": lambda data: data["shots"][0]["edit"].__setitem__("transition_to_next", "jump_cut"),
            "continuity": lambda data: data["shots"][0]["continuity"].__setitem__("axis", "反向轴线"),
            "motivation": lambda data: data["shots"][0]["motivation"].__setitem__("reason", "与当前戏剧任务无关"),
            "duration": lambda data: data["shots"][0].__setitem__("duration_seconds", 99),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed_data = copy.deepcopy(self.data)
                mutate(changed_data)
                changed_data["shots"][0]["execution_text"] = canonical_execution_text(changed_data["shots"][0])

                # Using the old lock must expose execution-hash drift.
                old_lock_report = validate_data(changed_data, self.workspace)
                self.assertEqual("FAIL", old_lock_report["status"])
                self.assertIn("EXECUTION_LOCK_INVALIDATED", error_codes(old_lock_report))

                # Re-locking applies the dependency matrix: Gate 2 survives an
                # execution-only change, while alignment is invalidated.
                relocked = lock_workspace(self.workspace, changed_data)
                self.assertEqual("confirmed", relocked["review_lock"]["gate_2_status"])
                self.assertEqual("invalidated", relocked["review_lock"]["alignment_status"])
                self.assertEqual("FAIL", validate_data(changed_data, relocked)["status"])

    def test_p0_03_execution_text_must_equal_canonical_model(self):
        changed = copy.deepcopy(self.data)
        changed["shots"][0]["execution_text"] += "\n另写一套与结构化字段不同的机位。"
        report = validate_structure(changed)
        self.assertEqual("FAIL", report["status"])
        self.assertIn("EXECUTION_TEXT_DIVERGED", error_codes(report))

    def test_p0_04_assumptions_cannot_be_deleted_while_gap_obligations_remain(self):
        changed = copy.deepcopy(self.concept_data)
        changed["assumptions"] = []
        report = validate_data(changed, self.concept_workspace)
        self.assertEqual("FAIL", report["status"])
        self.assertIn("ASSUMPTION_OBLIGATION_UNRESOLVED", error_codes(report))

    def test_p0_05_topology_passage_and_fact_bindings_are_bidirectional(self):
        changed = copy.deepcopy(self.workspace)
        first = changed["scene_strategies"][0]["topology"][0]
        last = changed["scene_strategies"][0]["topology"][-1]
        first["source_passage_ids"], last["source_passage_ids"] = (
            last["source_passage_ids"],
            first["source_passage_ids"],
        )
        first["source_fact_ids"], last["source_fact_ids"] = (
            last["source_fact_ids"],
            first["source_fact_ids"],
        )
        report = validate_workspace(changed, self.data, check_review_states=False)
        self.assertEqual("FAIL", report["status"])
        self.assertIn("TOPOLOGY_PASSAGE_BINDING_DIVERGED", error_codes(report))
        self.assertIn("TOPOLOGY_FACT_BINDING_DIVERGED", error_codes(report))

    def test_p0_06_failed_renderer_rolls_back_entire_formal_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "delivery"
            with patch("storyboard_delivery._write_xlsx", side_effect=RuntimeError("injected XLSX failure")):
                report, paths = build_outputs(self.data, self.workspace, output)
            self.assertEqual("FAIL", report["status"])
            self.assertEqual("ROLLED_BACK", report["build_transaction"])
            self.assertEqual({}, paths)
            self.assertFalse(output.exists())
            self.assertEqual([], list(Path(directory).iterdir()))

    def test_p0_06_validation_is_written_only_after_all_three_artifacts_verify(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "delivery"
            report, paths = build_outputs(self.data, self.workspace, output)
            self.assertEqual("COMMITTED", report["build_transaction"])
            validation = load_json(paths["validation"])
            self.assertEqual("PASS", validation["dimensions"]["export_parity"])
            self.assertEqual({"json", "markdown", "xlsx"}, set(validation["artifact_sha256"]))
            for label in ("json", "markdown", "xlsx"):
                self.assertTrue(paths[label].exists())

    def test_p0_07_gate_invalidation_dependency_matrix(self):
        cases = []

        source_changed = copy.deepcopy(self.workspace)
        source_changed["source"]["source_units"][1]["semantic_summary"] += "补充说明"
        cases.append(("source-model", source_changed, self.data, ("invalidated", "invalidated", "invalidated")))

        method_changed = copy.deepcopy(self.workspace)
        method_changed["director_method"]["time_model"] += "并延长余波"
        cases.append(("method", method_changed, self.data, ("invalidated", "invalidated", "invalidated")))

        strategy_changed = copy.deepcopy(self.workspace)
        strategy_changed["scene_strategies"][0]["shot_density_curve"] += "，结尾留白"
        cases.append(("strategy", strategy_changed, self.data, ("passed", "invalidated", "invalidated")))

        topology_changed = copy.deepcopy(self.workspace)
        topology_changed["scene_strategies"][0]["topology"][0]["boundary_to_next"]["relation"] = "sound_bridge"
        cases.append(("topology", topology_changed, self.data, ("passed", "invalidated", "invalidated")))

        execution_data = copy.deepcopy(self.data)
        execution_data["shots"][0]["notes"] = "待确认演员手部速度。"
        cases.append(("execution", self.workspace, execution_data, ("passed", "confirmed", "invalidated")))

        for label, workspace, data, expected in cases:
            with self.subTest(label=label):
                relocked = lock_workspace(workspace, data)
                actual = (
                    relocked["review_lock"]["gate_1_status"],
                    relocked["review_lock"]["gate_2_status"],
                    relocked["review_lock"]["alignment_status"],
                )
                self.assertEqual(expected, actual)


    def test_mid_line_negation_is_not_lost(self):
        changed_data = copy.deepcopy(self.data)
        changed_workspace = copy.deepcopy(self.workspace)
        lines = changed_workspace["source"]["locked_text"].splitlines()
        lines[1] = "林晓彤没有把钥匙放在餐桌上。"
        locked = "\n".join(lines)
        changed_workspace["source"]["locked_text"] = locked
        changed_workspace["source"]["source_hash"] = text_hash(locked)
        changed_workspace["source"]["source_units"][1]["exact_text"] = lines[1]
        changed_workspace["source"]["source_facts"][0]["source_span"] = lines[1]
        changed_data["source"]["locked_text"] = locked
        report = validate_workspace(changed_workspace, changed_data, check_review_states=False)
        self.assertIn("SOURCE_NEGATION_POLARITY_MISMATCH", error_codes(report))
        self.assertIn("SOURCE_REQUIRED_FACT_INVENTORY_MISSING", error_codes(report))

    def test_entity_owner_matching_never_uses_substring(self):
        changed = copy.deepcopy(self.workspace)
        changed["source"]["source_facts"][0]["subjects"] = ["林"]
        changed["shot_bindings"][0]["fact_realizations"][0]["subject_owners"] = ["树林"]
        report = validate_workspace(changed, self.data, check_review_states=False)
        self.assertIn("SOURCE_EXECUTION_SUBJECT_DIVERGED", error_codes(report))

    def test_formal_shot_rejects_unapproved_and_one_way_inferences(self):
        changed = copy.deepcopy(self.workspace)
        inference = {
            "inference_id": "DI001",
            "scope": "SC001",
            "statement": "刀声停止后增加一段主观幻觉。",
            "basis_fact_ids": ["SF003"],
            "reference_fact_ids": [],
            "shot_refs": ["SH002"],
            "reversibility": "reversible",
            "status": "rejected",
            "conflicts_with_fact_ids": [],
        }
        changed["director_inferences"].append(inference)
        changed["shot_bindings"][1]["director_inference_ids"] = ["DI001"]
        report = validate_workspace(changed, self.data, check_review_states=False)
        self.assertIn("DIRECTOR_INFERENCE_NOT_APPROVED", error_codes(report))

        changed["director_inferences"][0]["status"] = "approved"
        changed["director_inferences"][0]["shot_refs"] = ["SH003"]
        report = validate_workspace(changed, self.data, check_review_states=False)
        self.assertIn("DIRECTOR_INFERENCE_SHOT_BINDING_DIVERGED", error_codes(report))

    def test_supplemental_approval_hash_covers_status_and_note(self):
        fact = {
            "reference_fact_id": "RF001",
            "statement": "参考事实。",
            "source_excerpt": "参考事实原文。",
            "source_hash": text_hash("参考事实原文。"),
            "provenance": {
                "source_type": "user_supplied",
                "source_title": "测试",
                "locator": "fixture://reference",
                "owner": "test",
            },
            "approval_status": "pending",
            "approval_note": "待审批",
        }
        pending = supplemental_reference_approval_hash(fact)
        fact["approval_status"] = "approved"
        approved = supplemental_reference_approval_hash(fact)
        fact["approval_note"] = "已复核"
        noted = supplemental_reference_approval_hash(fact)
        self.assertNotEqual(pending, approved)
        self.assertNotEqual(approved, noted)

    def test_failed_report_never_claims_all_dimensions_pass(self):
        changed = copy.deepcopy(self.workspace)
        changed["scene_strategies"][0]["topology"][0]["intra_shot_operations"] = ["illegal_operation"]
        report = validate_workspace(changed, self.data, check_review_states=False)
        self.assertEqual("FAIL", report["status"])
        self.assertIn("FAIL", set(report["dimensions"].values()))


if __name__ == "__main__":
    unittest.main()
