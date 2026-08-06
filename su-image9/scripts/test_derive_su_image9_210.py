#!/usr/bin/env python3
"""Contract and end-to-end tests for the su-image9 v2.1.2 deriver."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def find_fenjing_script_dir(start: Path) -> Path:
    for parent in (start, *start.parents):
        for candidate in (
            parent / "su-fenjingskill-zh" / "scripts",
            parent / "skills" / "su-fenjingskill-zh" / "scripts",
        ):
            if (candidate / "storyboard_delivery.py").is_file() and (
                candidate / "test_storyboard_delivery.py"
            ).is_file():
                return candidate
    raise RuntimeError("could not locate the su-fenjingskill-zh 2.4.2 scripts")


FENJING_SCRIPT_DIR = find_fenjing_script_dir(SCRIPT_DIR)
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(FENJING_SCRIPT_DIR))

import derive_su_image9_prompt_package as derive
import storyboard_delivery as delivery


fixture_spec = importlib.util.spec_from_file_location(
    "su_fenjing_242_test_fixture",
    FENJING_SCRIPT_DIR / "test_storyboard_delivery.py",
)
if fixture_spec is None or fixture_spec.loader is None:
    raise RuntimeError("could not load the su-fenjingskill-zh 2.4.2 fixture")
upstream_fixture = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(upstream_fixture)

DERIVE_PATH = SCRIPT_DIR / "derive_su_image9_prompt_package.py"
MIGRATE_PATH = SCRIPT_DIR / "migrate_su_image9_16_to_17.py"
CANON_PATH = SCRIPT_DIR.parent / "references" / "canon-locks.md"


def final_signed_data_242() -> dict:
    """Build the real upstream valid_data_242 fixture through final-signoff."""
    data = upstream_fixture.valid_data_242()
    data["human_reviews"].append(
        {
            "gate": "GATE_C",
            "round": 1,
            "status": "approved",
            "reviewer": "user",
            "notes": "final-signoff approved for image derivation",
        }
    )
    delivery.derive_prompts(data)
    preliminary = delivery.validate_data(data, strict_status=False, final_signoff=True)
    if preliminary.errors:
        raise AssertionError(preliminary.errors)
    upstream_fixture.resolve_warnings(data, preliminary)
    final = delivery.validate_data(data, strict_status=False, final_signoff=True)
    if final.errors:
        raise AssertionError(final.errors)
    delivery.update_validation_report(data, final)
    strict = delivery.validate_data(data, strict_status=True, final_signoff=True)
    if strict.errors:
        raise AssertionError(strict.errors)
    return data


def resign_after_valid_mutation(data: dict) -> None:
    """Re-run the real upstream final validator after a contract-preserving mutation."""
    delivery.derive_prompts(data)
    data["warn_resolutions"] = []
    preliminary = delivery.validate_data(data, strict_status=False, final_signoff=True)
    if preliminary.errors:
        raise AssertionError(preliminary.errors)
    upstream_fixture.resolve_warnings(data, preliminary)
    final = delivery.validate_data(data, strict_status=False, final_signoff=True)
    if final.errors:
        raise AssertionError(final.errors)
    delivery.update_validation_report(data, final)
    strict = delivery.validate_data(data, strict_status=True, final_signoff=True)
    if strict.errors:
        raise AssertionError(strict.errors)


class Derive212Tests(unittest.TestCase):
    def write_source(self, root: Path, data: dict) -> Path:
        source = root / "sample.shot_data.json"
        source.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return source

    def run_cli(self, data: dict, *extra: str):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        source = self.write_source(root, data)
        output = root / "package"
        process = subprocess.run(
            [
                sys.executable,
                str(DERIVE_PATH),
                "--shot-data",
                str(source),
                "--out-dir",
                str(output),
                *extra,
            ],
            capture_output=True,
            text=True,
        )
        return temp, source, output, process

    def test_real_242_final_signoff_builds_release_ready_212_package(self) -> None:
        data = final_signed_data_242()
        temp, source, output, process = self.run_cli(data)
        with temp:
            report_text = (output / "validation_report.json").read_text(encoding="utf-8") if output.exists() else ""
            self.assertEqual(derive.EXIT_PASS, process.returncode, process.stderr + report_text)
            expected_outputs = {
                "分析与锁定.md",
                "panel_plan.json",
                "page-map.json",
                "final_image_prompts.md",
                "final_image_prompts.compiled.md",
                "validation_report.json",
            }
            self.assertEqual(expected_outputs, {path.name for path in output.iterdir()})

            plan = json.loads((output / "panel_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(
                {
                    "skill",
                    "version",
                    "schema_version",
                    "source",
                    "canon",
                    "reference_bindings",
                    "pages",
                    "release_ready",
                },
                set(plan),
            )
            self.assertEqual("2.1.2", plan["version"])
            self.assertEqual("2.1", plan["schema_version"])
            self.assertTrue(plan["release_ready"])
            self.assertEqual(derive.source_file_sha256(source), plan["source"]["file_sha256"])
            self.assertEqual(delivery.canonical_data_hash(data), plan["source"]["content_hash"])
            self.assertEqual("2.4.2", plan["source"]["skill_version"])
            self.assertEqual("PASS", plan["source"]["validation_status"])

            page = plan["pages"][0]
            self.assertEqual("PAGE-01", page["page"])
            self.assertEqual("single_scene_single_reality_layer", page["page_mode"])
            self.assertEqual("derived_angle", page["completion_mode"])
            self.assertEqual([1, 2], page["source_shot_nos"])
            self.assertEqual(9, len(page["panels"]))
            self.assertEqual([f"PANEL-{index}" for index in range(1, 10)], [item["panel"] for item in page["panels"]])

            first = page["panels"][0]
            self.assertEqual("source", first["panel_kind"])
            self.assertEqual("C001", first["display_label"])
            self.assertEqual(first["source_camera_tag"], first["drawn_camera_tag"])
            first_derived = page["panels"][1]
            self.assertEqual("derived_angle", first_derived["panel_kind"])
            self.assertEqual("C001-A", first_derived["display_label"])
            self.assertEqual("none", first_derived["fact_delta"])
            self.assertEqual(first["continuity_state_hash"], first_derived["continuity_state_hash"])
            self.assertIn("camera_rationale", first_derived)
            self.assertIn("primary_focus", first_derived)

            page_map = json.loads((output / "page-map.json").read_text(encoding="utf-8"))
            self.assertTrue(page_map["release_ready"])
            self.assertEqual(
                [item["display_label"] for item in page["panels"]],
                [item["display_label"] for item in page_map["pages"][0]["panels"]],
            )
            report = json.loads((output / "validation_report.json").read_text(encoding="utf-8"))
            self.assertEqual("PASS", report["status"])
            self.assertTrue(report["release_ready"])

    def test_arbitrary_upstream_version_is_accepted_and_preserved(self) -> None:
        data = final_signed_data_242()
        data["metadata"]["version"] = "2.4.9"
        data["metadata"]["rule_revision"] = "2.4.9-gate-state-contract-2026-07-21"
        data["script_lock"]["locked_text_hash"] = derive.normalized_script_text_hash(data["script_lock"]["locked_text"])
        data["validation_report"]["source_json_hash"] = derive.upstream_gate_content_hash(data)
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = self.write_source(root, data)
            artifacts = derive.derive_artifacts(data, source, CANON_PATH)
            plan = artifacts["panel_plan"]
            self.assertEqual([], derive.validate_source_contract(data))
            self.assertEqual("2.4.9", plan["source"]["skill_version"])
            self.assertIn("2.4.9-gate-state-contract-2026-07-21", artifacts["analysis"])

    def test_panel_one_preserves_close_camera_while_anchor_moves_later(self) -> None:
        data = final_signed_data_242()
        data["shots"][0]["camera_main_image"] = (
            "[平视, 特写, 固定镜头]\n【机位逻辑】摄影机保持在桌边，只看A的面部。\n"
            "【场景首镜站位】（A站在门口，面向桌边。）\nA站在门口。"
        )
        resign_after_valid_mutation(data)
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = self.write_source(root, data)
            artifacts = derive.derive_artifacts(data, source, CANON_PATH)
            page = artifacts["panel_plan"]["pages"][0]
            first = page["panels"][0]
            self.assertEqual("平视, 特写, 固定镜头", first["source_camera_tag"])
            self.assertEqual(first["source_camera_tag"], first["drawn_camera_tag"])
            self.assertNotEqual("PANEL-1", page["spatial_anchor_panel"])
            anchor = next(item for item in page["panels"] if item["panel"] == page["spatial_anchor_panel"])
            self.assertEqual(2, anchor["source_shot"])
            self.assertEqual("source", anchor["panel_kind"])

    def test_source_and_derived_panel_contract_is_exact(self) -> None:
        data = final_signed_data_242()
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = self.write_source(root, data)
            plan = derive.derive_artifacts(data, source, CANON_PATH)["panel_plan"]
            expected_keys = {
                "panel",
                "panel_kind",
                "source_shot",
                "variant_suffix",
                "display_label",
                "source_camera_tag",
                "drawn_camera_tag",
                "beat_ids",
                "covered_fact_ids",
                "visible_characters",
                "offscreen_characters",
                "visible_props",
                "continuity_state_hash",
                "composition_task",
                "distance_stage_lock",
                "fact_delta",
                "primary_focus",
                "must_show",
                "may_show",
                "must_not_show",
                "render_delta",
                "story_delta",
                "camera_rationale",
            }
            for panel in plan["pages"][0]["panels"]:
                self.assertEqual(expected_keys, set(panel))
                if panel["panel_kind"] == "source":
                    self.assertIsNone(panel["variant_suffix"])
                    self.assertEqual("source", panel["fact_delta"])
                    self.assertEqual(panel["source_camera_tag"], panel["drawn_camera_tag"])
                    self.assertEqual("none", panel["render_delta"])
                else:
                    self.assertRegex(panel["variant_suffix"], r"^[A-H]$")
                    self.assertEqual("none", panel["fact_delta"])
                    self.assertEqual("allowed", panel["render_delta"])
                    self.assertTrue(panel["camera_rationale"])

    def test_derived_angles_are_narrative_driven(self) -> None:
        data = final_signed_data_242()
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = self.write_source(root, data)
            page = derive.derive_artifacts(data, source, CANON_PATH)["panel_plan"]["pages"][0]
            self.assertEqual([1, 1, 1, 1, 1, 2, 2, 2, 2], [panel["source_shot"] for panel in page["panels"]])
            self.assertEqual(
                ["C001", "C001-A", "C001-B", "C001-C", "C001-D", "C002", "C002-A", "C002-B", "C002-C"],
                [panel["display_label"] for panel in page["panels"]],
            )
            # The narrative-driven pool should include angles with rationales.
            rationales = [panel.get("camera_rationale", "") for panel in page["panels"]]
            self.assertTrue(all(rationales))

    def test_sparse_source_without_eight_legal_angles_requires_review(self) -> None:
        data = final_signed_data_242()
        shot = copy.deepcopy(data["shots"][0])
        # Two visible characters but only a prop fact covered, no visible props,
        # no dialogue/action facts. The narrative pool only supplies the seven
        # generic two-character angles, which is insufficient to fill nine panels.
        shot["visible_characters"] = ["A", "B"]
        shot["visible_props"] = []
        shot["beat_ids"] = ["B001"]
        shot["covered_fact_ids"] = ["B001-F02"]
        shot["shot_type"] = "master"
        shot["camera_main_image"] = (
            "[平视, 双人中景, 固定镜头]\n"
            "【机位逻辑】摄影机位于人物关系轴同侧。\n"
            "【场景首镜站位】（A在门口，B在桌边。）\n"
            "A与B保持当前动作阶段。"
        )
        logs = derive.scene_logs(data)
        with self.assertRaises(derive.DerivationReview) as raised:
            derive.build_page(1, [shot], data, logs)
        self.assertEqual("F-SPARSE-COVERAGE", raised.exception.code)

    def test_over_shoulder_and_prop_insert_require_bound_facts(self) -> None:
        shot = copy.deepcopy(final_signed_data_242()["shots"][0])
        base_names = [item[0] for item in derive.narrative_angle_candidates(shot, {}, "现实")]
        self.assertNotIn("over_shoulder", base_names)
        self.assertNotIn("prop_insert", base_names)
        shot["visible_characters"] = ["A", "B"]
        shot["visible_props"] = ["钥匙"]
        expanded_names = [item[0] for item in derive.narrative_angle_candidates(shot, {}, "现实", {"B001-F01"})]
        self.assertIn("over_shoulder", expanded_names)
        self.assertIn("prop_insert", expanded_names)

    def test_distance_stage_uses_only_explicit_position_and_facing_updates(self) -> None:
        data = final_signed_data_242()
        locks = derive.distance_stage_locks(data["shots"])
        self.assertIn("pre-transition", locks[1])
        self.assertIn("A.position", locks[1])
        self.assertIn("endpoint-transition", locks[2])
        self.assertIn("B002-F01", locks[2])

        no_updates = copy.deepcopy(data["shots"])
        no_updates[0]["source_paragraph"] = "A靠近桌边。"
        no_updates[0]["continuity_updates"] = []
        no_updates[1]["continuity_updates"] = []
        self.assertEqual({1: "none", 2: "none"}, derive.distance_stage_locks(no_updates))

    def test_eighteen_shots_keep_distance_lock_across_page_capacity_boundary(self) -> None:
        logs = {
            "S01": {
                "scene_id": "S01",
                "reality_layer": "现实",
            }
        }
        shots = [
            {
                "shot_no": number,
                "scene_id": "S01",
                "camera_main_image": "[平视, 中景, 固定镜头]",
                "continuity_updates": [],
            }
            for number in range(1, 19)
        ]
        shots[9]["continuity_updates"] = [
            {
                "entity_type": "character",
                "entity": "A",
                "field": "position",
                "from": "门口",
                "to": "桌边",
                "evidence_fact_ids": ["B010-F01"],
            }
        ]
        pages = derive.page_chunks(shots, logs)
        self.assertEqual([9, 9], [len(page) for page in pages])
        locks = derive.distance_stage_locks_for_sequence(shots, logs)
        self.assertIn("pre-transition", locks[9])
        self.assertIn("before C010", locks[9])
        self.assertIn("endpoint-transition", locks[10])

    def test_one_through_eighteen_sources_always_cover_once_in_nine_panel_pages(self) -> None:
        log = {
            "scene_id": "S01",
            "scene": "1 测试空间 日 内",
            "reality_layer": "现实",
            "spatial_axis": "A与B保持同侧关系，A从起点移向终点，摄影机不跨轴。",
            "fixed_objects": ["门", "桌子"],
            "characters": [
                {"name": "A", "position": "门口", "facing": "B"},
                {"name": "B", "position": "桌边", "facing": "A"},
            ],
            "props": [{"name": "钥匙", "owner": "A", "state": "握在手中"}],
        }
        logs = {"S01": log}
        data = {"shots": [], "continuity_logs": [log], "beats": []}
        for count in range(1, 19):
            with self.subTest(count=count):
                shots = [
                    {
                        "shot_no": number,
                        "scene_id": "S01",
                        "scene": "1 测试空间 日 内",
                        "camera_main_image": (
                            "[平视, 双人中景, 固定镜头]\n"
                            "【机位逻辑】摄影机位于人物关系轴同侧。\n"
                            "【场景首镜站位】（A在门口，B在桌边。）\n"
                            "A与B保持当前动作阶段。"
                        ),
                        "prompt": "",
                        "source_paragraph": "A与B保持当前动作阶段。",
                        "beat_ids": [f"B{number:03d}"],
                        "covered_fact_ids": [f"B{number:03d}-F01"],
                        "visible_characters": ["A", "B"],
                        "offscreen_characters": [],
                        "visible_props": ["钥匙"],
                        "continuity_updates": [],
                    }
                    for number in range(1, count + 1)
                ]
                data["shots"] = shots
                chunks = derive.page_chunks(shots, logs)
                sequence_locks = derive.distance_stage_locks_for_sequence(shots, logs)
                prop_facts = {f"B{number:03d}-F01" for number in range(1, count + 1)}
                pages = [
                    derive.build_page(index, chunk, data, logs, prop_facts, sequence_locks)
                    for index, chunk in enumerate(chunks, 1)
                ]
                self.assertTrue(all(len(page["panels"]) == 9 for page in pages))
                native = [
                    panel["source_shot"]
                    for page in pages
                    for panel in page["panels"]
                    if panel["panel_kind"] == "source"
                ]
                self.assertEqual(list(range(1, count + 1)), native)

    def test_transition_ends_page_and_cannot_supply_derived_angles(self) -> None:
        data = final_signed_data_242()
        shots = copy.deepcopy(data["shots"])
        shots[0]["shot_type"] = "transition"
        pages = derive.page_chunks(shots, derive.scene_logs(data))
        self.assertEqual([[1], [2]], [[shot["shot_no"] for shot in page] for page in pages])
        self.assertEqual([], derive.narrative_angle_candidates(shots[0], data, "现实"))

    def test_missing_gate_hash_and_nonhuman_warning_fail_closed(self) -> None:
        data = final_signed_data_242()
        data["human_reviews"] = [item for item in data["human_reviews"] if item["gate"] != "GATE_C"]
        data["validation_report"]["source_json_hash"] = derive.canonical_data_hash(data)
        self.assertTrue(any("GATE_C" in error for error in derive.validate_source_contract(data)))

        data = final_signed_data_242()
        data["shots"][0]["notes"] += " changed after sign-off"
        self.assertTrue(any("source_json_hash" in error for error in derive.validate_source_contract(data)))

        data = final_signed_data_242()
        warning = "custom identity conflict"
        warn_id_value = derive.warning_id(warning)
        data["validation_report"]["status"] = "WARN"
        data["validation_report"]["warnings"] = [warning]
        data["warn_resolutions"] = [
            {
                "warn_id": warn_id_value,
                "resolution": "keep",
                "resolved_by": "auto_whitelist",
                "note": "not a whitelist warning",
            }
        ]
        data["validation_report"]["source_json_hash"] = derive.canonical_data_hash(data)
        self.assertTrue(any("must be resolved by human" in error for error in derive.validate_source_contract(data)))
        data["warn_resolutions"][0]["resolved_by"] = "human"
        data["validation_report"]["source_json_hash"] = derive.canonical_data_hash(data)
        self.assertEqual([], derive.validate_source_contract(data))

    def test_warning_digest_algorithm_is_stable_and_sorted(self) -> None:
        first = derive.warning_digest({"warnings": [" B ", "A"]})
        second = derive.warning_digest({"warnings": ["A", "B"]})
        self.assertEqual(first, second)
        self.assertEqual(
            "b64e3448a83a5b86466465080361c1a7e1157a27ddccd4b68069cb18caffb74a",
            first,
        )
        self.assertEqual(
            derive.warning_digest({"warnings": ["A  B"]}),
            derive.warning_digest({"warnings": ["A B"]}),
        )
        self.assertEqual(
            derive.warning_digest({"warnings": ["A\nB"]}),
            derive.warning_digest({"warnings": ["A B"]}),
        )

    def test_bool_and_wrong_typed_source_arrays_are_contract_failures(self) -> None:
        for field in ("beat_ids", "covered_fact_ids", "visible_characters", "offscreen_characters", "visible_props"):
            data = final_signed_data_242()
            data["shots"][0][field] = [True]
            data["validation_report"]["source_json_hash"] = derive.canonical_data_hash(data)
            with self.subTest(field=field):
                self.assertTrue(any(field in error for error in derive.validate_source_contract(data)))
        data = final_signed_data_242()
        data["shots"][0]["continuity_updates"] = [False]
        data["validation_report"]["source_json_hash"] = derive.canonical_data_hash(data)
        self.assertTrue(any("continuity_updates[0]" in error for error in derive.validate_source_contract(data)))

    def test_reference_bindings_are_explicit_and_rendered(self) -> None:
        data = final_signed_data_242()
        data["reference_bindings"] = [
            {
                "asset_id": "REF-001",
                "asset_sha256": "a" * 64,
                "binding_type": "character",
                "target_id": "A",
                "locked_attributes": ["identity", "shape"],
                "status": "bound",
            },
            {
                "asset_id": "REF-002",
                "asset_sha256": "b" * 64,
                "binding_type": "space",
                "target_id": "S01",
                "locked_attributes": ["fixed_geometry"],
                "status": "bound",
            },
        ]
        data["validation_report"]["source_json_hash"] = derive.canonical_data_hash(data)
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = self.write_source(root, data)
            artifacts = derive.derive_artifacts(data, source, CANON_PATH)
            self.assertEqual(data["reference_bindings"], artifacts["panel_plan"]["reference_bindings"])
            self.assertIn("Bound reference REF-001", artifacts["final_prompts"])
            self.assertIn("character target A", artifacts["final_prompts"])
            self.assertIn("space target S01", artifacts["final_prompts"])

        invalid = final_signed_data_242()
        invalid["reference_assets"] = [{"path": "unbound.png"}]
        invalid["validation_report"]["source_json_hash"] = derive.canonical_data_hash(invalid)
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = self.write_source(root, invalid)
            with self.assertRaises(derive.DerivationReview) as raised:
                derive.derive_artifacts(invalid, source, CANON_PATH)
            self.assertEqual("F-ASSET", raised.exception.code)

        wrong_target = final_signed_data_242()
        wrong_target["reference_bindings"] = [
            {
                "asset_id": "REF-003",
                "asset_sha256": "c" * 64,
                "binding_type": "space",
                "target_id": wrong_target["continuity_logs"][0]["scene"],
                "locked_attributes": ["fixed_geometry"],
                "status": "bound",
            }
        ]
        wrong_target["validation_report"]["source_json_hash"] = derive.canonical_data_hash(wrong_target)
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = self.write_source(root, wrong_target)
            with self.assertRaises(derive.DerivationReview) as raised:
                derive.derive_artifacts(wrong_target, source, CANON_PATH)
            self.assertEqual("F-ASSET", raised.exception.code)

    def test_prop_insert_requires_a_covered_prop_fact(self) -> None:
        shot = copy.deepcopy(final_signed_data_242()["shots"][0])
        data = {"beats": []}
        shot["visible_props"] = ["钥匙"]
        self.assertNotIn("prop_insert", [item[0] for item in derive.narrative_angle_candidates(shot, data, "现实", set())])
        self.assertIn("prop_insert", [item[0] for item in derive.narrative_angle_candidates(shot, data, "现实", {"B001-F01"})])

    def test_vehicle_detection_does_not_treat_keys_tickets_or_doors_as_vehicles(self) -> None:
        page = {"source_shot_nos": [1]}
        shots = {
            1: {
                "visible_props": ["车钥匙", "车票", "车门", "轿车", "car key", "red car"],
            }
        }
        self.assertEqual(
            ["轿车", "red car"],
            derive.registered_vehicle_facts(page, shots, {"fixed_objects": []}),
        )

    def test_artifact_derivation_is_byte_deterministic(self) -> None:
        data = final_signed_data_242()
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = self.write_source(root, data)
            first = derive.derive_artifacts(data, source, CANON_PATH)
            second = derive.derive_artifacts(data, source, CANON_PATH)
            self.assertEqual(first, second)
            self.assertEqual(
                json.dumps(first["panel_plan"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                json.dumps(second["panel_plan"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )

    def test_removed_cli_flags_are_rejected(self) -> None:
        for flag in ("--page-size", "--mode", "--skip-validate", "--validator"):
            temp, _source, output, process = self.run_cli(final_signed_data_242(), flag, "9" if flag == "--page-size" else "value")
            with temp, self.subTest(flag=flag):
                self.assertEqual(2, process.returncode)
                self.assertIn("unrecognized arguments", process.stderr)
                self.assertFalse(output.exists())

    def test_nonempty_output_is_not_overwritten(self) -> None:
        data = final_signed_data_242()
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = self.write_source(root, data)
            output = root / "package"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_text("keep", encoding="utf-8")
            process = subprocess.run(
                [sys.executable, str(DERIVE_PATH), "--shot-data", str(source), "--out-dir", str(output)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(derive.EXIT_CONTRACT_FAIL, process.returncode)
            self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))
            self.assertEqual({"keep.txt"}, {path.name for path in output.iterdir()})

    def test_validator_failure_publishes_only_the_report(self) -> None:
        data = final_signed_data_242()
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = self.write_source(root, data)
            output = root / "package"
            bad_canon = root / "bad-canon.md"
            bad_canon.write_text("<!-- canon-version: 2.1.2 -->\n", encoding="utf-8")
            process = subprocess.run(
                [
                    sys.executable,
                    str(DERIVE_PATH),
                    "--shot-data",
                    str(source),
                    "--out-dir",
                    str(output),
                    "--canon",
                    str(bad_canon),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(derive.EXIT_CONTRACT_FAIL, process.returncode)
            self.assertEqual({"validation_report.json"}, {path.name for path in output.iterdir()})
            report = json.loads((output / "validation_report.json").read_text(encoding="utf-8"))
            self.assertFalse(report["release_ready"])

    def test_legacy_detector_recognizes_only_212_as_current(self) -> None:
        for version, expected_code, expected_status in (
            ("2.1.2", 0, "CURRENT_NO_MIGRATION_REQUIRED"),
            ("2.1.1", 1, "F-LEGACY-REGENERATE"),
            ("2.0.3", 1, "F-LEGACY-REGENERATE"),
            ("2.0.2", 1, "F-LEGACY-REGENERATE"),
        ):
            with tempfile.TemporaryDirectory() as temp_name, self.subTest(version=version):
                root = Path(temp_name)
                plan = root / "panel_plan.json"
                prompt = root / "final.md"
                output = root / "must-not-exist"
                plan.write_text(
                    json.dumps({"skill": "su-image9", "version": version}),
                    encoding="utf-8",
                )
                prompt.write_text("@CANON(HARD_PHRASES)\n@CANON(GEOMETRY_BLUEPRINT)\n", encoding="utf-8")
                process = subprocess.run(
                    [
                        sys.executable,
                        str(MIGRATE_PATH),
                        "--panel-plan",
                        str(plan),
                        "--final-prompts",
                        str(prompt),
                        "--out-dir",
                        str(output),
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(expected_code, process.returncode, process.stderr)
                self.assertEqual(expected_status, json.loads(process.stdout)["status"])
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
