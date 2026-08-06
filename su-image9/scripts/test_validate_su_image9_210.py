#!/usr/bin/env python3
"""Adversarial tests for the su-image9 2.1.1 fail-closed validator."""

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
import validate_su_image9_prompt as validator


fixture_spec = importlib.util.spec_from_file_location(
    "su_fenjing_242_validator_fixture",
    FENJING_SCRIPT_DIR / "test_storyboard_delivery.py",
)
if fixture_spec is None or fixture_spec.loader is None:
    raise RuntimeError("could not load the real su-fenjingskill-zh 2.4.2 fixture")
upstream_fixture = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(upstream_fixture)

VALIDATOR_PATH = SCRIPT_DIR / "validate_su_image9_prompt.py"
CANON_PATH = SCRIPT_DIR.parent / "references" / "canon-locks.md"


def final_signed_data_242() -> dict:
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


def refresh_source_hash(data: dict) -> None:
    data["validation_report"]["source_json_hash"] = derive.canonical_data_hash(data)


class Validator210Tests(unittest.TestCase):
    def build_case(self, root: Path) -> tuple[dict, dict, str, Path]:
        data = final_signed_data_242()
        source = root / "sample.shot_data.json"
        source.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        canon = root / "canon-locks.md"
        canon.write_bytes(CANON_PATH.read_bytes())
        artifacts = derive.derive_artifacts(data, source, canon, release_ready=True)
        return data, artifacts["panel_plan"], artifacts["final_prompts"], source

    def run_case(
        self,
        root: Path,
        data: dict,
        plan: dict,
        prompt: str,
        source: Path,
        *,
        canon_text: str | None = None,
        raw_plan: str | None = None,
        raw_source: str | None = None,
    ) -> tuple[int, dict, str]:
        source.write_text(
            raw_source if raw_source is not None else json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        plan_path = root / "panel_plan.json"
        plan_path.write_text(
            raw_plan if raw_plan is not None else json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        prompt_path = root / "final_image_prompts.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        canon_path = root / "canon-locks.md"
        if canon_text is not None:
            canon_path.write_bytes(canon_text.encode("utf-8"))
        report_path = root / "validation_report.json"
        compiled_path = root / "compiled.md"
        code = validator.main(
            [
                "--canon",
                str(canon_path),
                "--panel-plan",
                str(plan_path),
                "--final-prompts",
                str(prompt_path),
                "--shot-data",
                str(source),
                "--report",
                str(report_path),
                "--out",
                str(compiled_path),
            ]
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        compiled = compiled_path.read_text(encoding="utf-8")
        return code, report, compiled

    @staticmethod
    def codes(report: dict) -> set[str]:
        return {item["code"] for item in report.get("findings", [])}

    def test_real_242_package_passes_exact_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, plan, prompt, source = self.build_case(root)
            code, report, compiled = self.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_PASS, code, report)
            self.assertEqual("PASS", report["status"])
            self.assertTrue(report["release_ready"])
            self.assertFalse(report["findings"])
            self.assertNotIn("@CANON(", compiled)
            self.assertEqual(plan["source"], report["source"])

    def test_cli_has_no_mode_or_text_only_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            process = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR_PATH),
                    "--canon",
                    str(root / "canon"),
                    "--panel-plan",
                    str(root / "plan"),
                    "--final-prompts",
                    str(root / "prompt"),
                    "--shot-data",
                    str(root / "source"),
                    "--report",
                    str(root / "report"),
                    "--out",
                    str(root / "compiled"),
                    "--mode",
                    "text-only",
                ],
                capture_output=True,
                text=True,
            )
        self.assertEqual(validator.EXIT_CONTRACT_FAIL, process.returncode)
        self.assertIn("unrecognized arguments", process.stderr)

    def test_plan_and_prompt_are_whole_artifact_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, plan, prompt, source = self.build_case(root)
            plan["pages"][0]["panels"][1]["composition_task"] += " injected result"
            prompt = prompt.replace("PANEL-2:", "PANEL-2: injected result ", 1)
            code, report, _ = self.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
            self.assertTrue({"F-PLAN-DRIFT", "F-PROMPT-DRIFT"}.issubset(self.codes(report)), report)

    def test_page_and_panel_ids_have_no_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, plan, prompt, source = self.build_case(root)
            plan["pages"][0]["page"] = "PAGE-02"
            plan["pages"][0]["panels"][0]["panel"] = "BANANA"
            prompt = prompt.replace("PANEL-1:", "PANEL-BANANA:", 1)
            code, report, _ = self.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
            self.assertTrue({"F-PAGE", "F-PANEL", "F-PROMPT-PANELS"}.issubset(self.codes(report)), report)

    def test_missing_source_panel_and_wrong_source_order_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, plan, prompt, source = self.build_case(root)
            page = plan["pages"][0]
            source_two = next(item for item in page["panels"] if item["panel_kind"] == "source" and item["source_shot"] == 2)
            source_two["panel_kind"] = "derived_angle"
            source_two["variant_suffix"] = "D"
            source_two["display_label"] = "C002-D"
            source_two["fact_delta"] = "none"
            page["source_shot_nos"] = [1]
            code, report, _ = self.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
            self.assertIn("F-SOURCE-COVERAGE", self.codes(report))

    def test_derived_panel_cannot_change_fact_or_continuity_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, plan, prompt, source = self.build_case(root)
            derived = next(item for item in plan["pages"][0]["panels"] if item["panel_kind"] == "derived_angle")
            derived["beat_ids"] = ["B999"]
            derived["covered_fact_ids"] = ["B999-F01"]
            derived["visible_characters"] = ["OTHER"]
            derived["continuity_state_hash"] = "0" * 64
            derived["fact_delta"] = "source"
            code, report, _ = self.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
            self.assertTrue({"F-DERIVED-FACT", "F-PLAN-DRIFT"}.issubset(self.codes(report)), report)

    def test_continuity_hash_is_independently_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, plan, prompt, source = self.build_case(root)
            source_panel = next(item for item in plan["pages"][0]["panels"] if item["panel_kind"] == "source")
            source_panel["continuity_state_hash"] = "f" * 64
            for item in plan["pages"][0]["panels"]:
                if item["source_shot"] == source_panel["source_shot"]:
                    item["continuity_state_hash"] = "f" * 64
            code, report, _ = self.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
            self.assertIn("F-CONTINUITY-HASH", self.codes(report))

    def test_prop_insert_requires_visible_prop_and_prop_fact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, plan, prompt, source = self.build_case(root)
            derived = next(item for item in plan["pages"][0]["panels"] if item["panel_kind"] == "derived_angle")
            derived["drawn_camera_tag"] = "registered-prop insert derived from " + derived["source_camera_tag"]
            code, report, _ = self.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
            self.assertIn("F-DERIVED-FACT", self.codes(report))

    def test_bool_and_numeric_source_fields_are_not_normalized_away(self) -> None:
        mutations = (
            lambda data: data["shots"][0].__setitem__("beat_ids", [True, "B001"]),
            lambda data: data["shots"][0].__setitem__("visible_props", [7]),
            lambda data: data["shots"][1]["continuity_updates"][0].__setitem__("to", True),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temp_name:
                root = Path(temp_name)
                data, plan, prompt, source = self.build_case(root)
                mutate(data)
                refresh_source_hash(data)
                code, report, _ = self.run_case(root, data, plan, prompt, source)
                self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
                self.assertIn("F-SOURCE", self.codes(report))

    def test_source_gate_rejects_version_gate_hash_and_status_failures(self) -> None:
        mutations = (
            lambda data: data["metadata"].__setitem__("version", ""),
            lambda data: data.__setitem__("human_reviews", [item for item in data["human_reviews"] if item["gate"] != "GATE_C"]),
            lambda data: data["validation_report"].__setitem__("source_json_hash", "0" * 64),
            lambda data: data["validation_report"].__setitem__("status", "NOT_RUN"),
        )
        expected_codes = ("F-SOURCE-VERSION", "F-SOURCE-GATE", "F-SOURCE-HASH", "F-SOURCE-VALIDATION")
        for mutate, expected in zip(mutations, expected_codes):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_name:
                root = Path(temp_name)
                data, plan, prompt, source = self.build_case(root)
                mutate(data)
                if expected not in {"F-SOURCE-HASH"}:
                    refresh_source_hash(data)
                code, report, _ = self.run_case(root, data, plan, prompt, source)
                self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
                self.assertIn(expected, self.codes(report))

    def test_source_gate_accepts_arbitrary_nonempty_upstream_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, plan, prompt, source = self.build_case(root)
            data["metadata"]["version"] = "2.4.9"
            data["metadata"]["rule_revision"] = "2.4.9-gate-state-contract-2026-07-21"
            data["script_lock"]["locked_text_hash"] = derive.normalized_script_text_hash(
                data["script_lock"]["locked_text"]
            )
            data["validation_report"]["source_json_hash"] = derive.upstream_gate_content_hash(data)
            source.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            plan["source"].update(
                {
                    "file_sha256": derive.source_file_sha256(source),
                    "content_hash": derive.canonical_data_hash(data),
                    "skill_version": "2.4.9",
                }
            )
            code, report, _ = self.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_PASS, code, report)
            self.assertEqual("2.4.9", report["source"]["skill_version"])

    def test_warn_set_requires_exact_human_resolution_when_not_whitelisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, plan, prompt, source = self.build_case(root)
            message = "custom identity conflict"
            data["validation_report"]["status"] = "WARN"
            data["validation_report"]["warnings"] = [message]
            data["warn_resolutions"] = [
                {
                    "warn_id": derive.warning_id(message),
                    "resolution": "keep",
                    "resolved_by": "auto_whitelist",
                    "note": "invalid auto resolution",
                }
            ]
            refresh_source_hash(data)
            code, report, _ = self.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
            self.assertIn("F-SOURCE-WARN", self.codes(report))

    def test_reference_assets_cannot_be_dropped_or_left_unbound(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, plan, prompt, source = self.build_case(root)
            data["assets"] = ["reference.png"]
            refresh_source_hash(data)
            source.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            plan["source"].update(
                {
                    "file_sha256": derive.source_file_sha256(source),
                    "content_hash": derive.canonical_data_hash(data),
                }
            )
            code, report, _ = self.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_REVIEW_REQUIRED, code, report)
            self.assertIn("F-ASSET", self.codes(report))

        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data = final_signed_data_242()
            data["reference_bindings"] = [
                {
                    "asset_id": "REF-001",
                    "asset_sha256": "a" * 64,
                    "binding_type": "character",
                    "target_id": "A",
                    "locked_attributes": ["identity"],
                    "status": "bound",
                }
            ]
            refresh_source_hash(data)
            source = root / "sample.shot_data.json"
            source.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            canon = root / "canon-locks.md"
            canon.write_bytes(CANON_PATH.read_bytes())
            artifacts = derive.derive_artifacts(data, source, canon, release_ready=True)
            plan = artifacts["panel_plan"]
            prompt = artifacts["final_prompts"]
            plan["reference_bindings"] = []
            code, report, _ = self.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
            self.assertIn("F-ASSET", self.codes(report))

    def test_canon_corruption_and_hash_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, plan, prompt, source = self.build_case(root)
            original = CANON_PATH.read_text(encoding="utf-8")
            corruptions = {
                "truncated": "<!-- canon-version: 2.1.2 -->\n### canon:HARD_PHRASES\n```text\nbroken",
                "wrong_version": original.replace("canon-version: 2.1.2", "canon-version: 9.9.9"),
                "duplicate": original + "\n### canon:HARD_PHRASES\n\n```text\nduplicate\n```\n",
                "unknown": original + "\n### canon:INJECTED\n\n```text\ninjected\n```\n",
                "hash_drift": original.replace("Generate one wide horizontal", "Generate one altered wide horizontal", 1),
            }
            for name, canon_text in corruptions.items():
                with self.subTest(name=name):
                    code, report, _ = self.run_case(root, data, copy.deepcopy(plan), prompt, source, canon_text=canon_text)
                    self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
                    self.assertTrue({"F-CANON", "F-CANON-HASH"} & self.codes(report), report)

    def test_prompt_layer_order_extra_layer_and_marker_injection_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, plan, prompt, source = self.build_case(root)
            injected = prompt.replace(
                "SCENE_LAYER:\n",
                "UNKNOWN_DYNAMIC_LAYER:\ninjected\n\nSCENE_LAYER:\n",
                1,
            ).replace("@CANON(HARD_PHRASES)", "@CANON(INJECTED)", 1)
            code, report, compiled = self.run_case(root, data, plan, injected, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
            self.assertTrue({"F-PROMPT-LAYERS", "F-PROMPT-CANON", "F-PROMPT-DRIFT"}.issubset(self.codes(report)), report)
            self.assertEqual("\n", compiled)

            extra_whitelisted = prompt.replace(
                "SCENE_LAYER:\n",
                "SCENE_LAYER:\n@CANON(HARD_PHRASES)\n",
                1,
            )
            code, report, compiled = self.run_case(root, data, plan, extra_whitelisted, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
            self.assertIn("F-PROMPT-CANON", self.codes(report))
            self.assertEqual("\n", compiled)

    def test_legacy_package_returns_regenerate_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, plan, prompt, source = self.build_case(root)
            plan["version"] = "2.0.2"
            plan["schema_version"] = "2.0"
            code, report, _ = self.run_case(root, data, plan, prompt, source)
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
            self.assertIn("F-LEGACY-REGENERATE", self.codes(report))

    def test_malformed_json_is_contract_fail_and_never_green(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, plan, prompt, source = self.build_case(root)
            code, report, _ = self.run_case(root, data, plan, prompt, source, raw_plan="{broken")
            self.assertEqual(validator.EXIT_CONTRACT_FAIL, code, report)
            self.assertEqual("CONTRACT_FAIL", report["status"])
            self.assertFalse(report["release_ready"])
            self.assertIn("F-INPUT", self.codes(report))

    def test_derivation_review_maps_to_exit_one(self) -> None:
        class ReviewDeriver:
            @staticmethod
            def validate_source_contract(_data):
                return []

            @staticmethod
            def derive_artifacts(*_args, **_kwargs):
                raise derive.DerivationReview("F-SPARSE-COVERAGE", "not enough legal angles", "PAGE-01")

        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "source.json"
            source.write_text("{}", encoding="utf-8")
            audit = validator.Audit()
            result = validator.rebuild_expected(ReviewDeriver(), {}, source, CANON_PATH, audit)
            self.assertIsNone(result)
            self.assertEqual(validator.EXIT_REVIEW_REQUIRED, audit.exit_code)
            self.assertEqual({"F-SPARSE-COVERAGE"}, {item.code for item in audit.findings})


if __name__ == "__main__":
    unittest.main()
