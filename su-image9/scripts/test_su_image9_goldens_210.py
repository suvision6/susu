#!/usr/bin/env python3
"""Byte-for-byte golden regressions for su-image9 2.1."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path


import derive_su_image9_prompt_package as derive
import generate_su_image9_goldens_210 as goldens


class Golden210Tests(unittest.TestCase):
    def test_sources_pass_real_upstream_final_signoff(self) -> None:
        for slug, _builder in goldens.CASES:
            with self.subTest(slug=slug):
                source_path = goldens.GOLDEN_ROOT / slug / "shot_data.json"
                data = json.loads(source_path.read_text(encoding="utf-8"))
                result = goldens.delivery.validate_data(data, strict_status=True, final_signoff=True)
                self.assertFalse(result.errors, result.errors)
                self.assertIn(data["validation_report"]["status"], {"PASS", "WARN"})
                self.assertEqual(
                    goldens.delivery.canonical_data_hash(data),
                    data["validation_report"]["source_json_hash"],
                )

    def test_locked_artifacts_rebuild_byte_for_byte(self) -> None:
        for slug, _builder in goldens.CASES:
            with self.subTest(slug=slug), tempfile.TemporaryDirectory() as temp_name:
                root = Path(temp_name)
                source = root / "shot_data.json"
                shutil.copyfile(goldens.GOLDEN_ROOT / slug / "shot_data.json", source)
                out_dir = root / "package"
                code = derive.main(["--shot-data", str(source), "--out-dir", str(out_dir)])
                self.assertEqual(derive.EXIT_PASS, code)
                for name in goldens.LOCKED_FILES:
                    self.assertEqual(
                        (goldens.GOLDEN_ROOT / slug / name).read_bytes(),
                        (out_dir / name).read_bytes(),
                        f"{slug}/{name} drifted",
                    )

    def test_city_vehicle_has_no_unregistered_default_facts(self) -> None:
        root = goldens.GOLDEN_ROOT / "city-vehicle"
        prompt = (root / "final_image_prompts.compiled.md").read_text(encoding="utf-8")
        self.assertIn("轿车", prompt)
        self.assertIn("车钥匙", prompt)
        vehicle_line = next(
            line for line in prompt.splitlines() if line.startswith("Registered vehicles or transport objects:")
        )
        self.assertIn("轿车", vehicle_line)
        self.assertNotIn("车钥匙", vehicle_line)
        for forbidden in ("洞穴岩壁", "地裂", "雾核", "No vehicle appears"):
            self.assertNotIn(forbidden, prompt)

    def test_dialogue_and_multi_reality_semantics_are_locked(self) -> None:
        dialogue = json.loads(
            (goldens.GOLDEN_ROOT / "dialogue-axis" / "panel_plan.json").read_text(encoding="utf-8")
        )
        self.assertEqual("WARN_ACCEPTED", dialogue["source"]["validation_status"])
        dialogue_panels = dialogue["pages"][0]["panels"]
        self.assertEqual("C001", dialogue_panels[0]["display_label"])
        self.assertEqual("C001-H", dialogue_panels[-1]["display_label"])
        drawn_tags = {panel["drawn_camera_tag"] for panel in dialogue_panels}
        self.assertTrue(any("over-shoulder" in tag for tag in drawn_tags))
        self.assertTrue(any("registered-prop insert" in tag for tag in drawn_tags))

        sparse = json.loads(
            (goldens.GOLDEN_ROOT / "sparse-multi-reality" / "panel_plan.json").read_text(encoding="utf-8")
        )
        self.assertEqual(["现实", "回忆"], [page["reality_layer"] for page in sparse["pages"]])
        self.assertEqual([[1], [2]], [page["source_shot_nos"] for page in sparse["pages"]])
        for page in sparse["pages"]:
            self.assertEqual(9, len(page["panels"]))
            source = page["panels"][0]
            for panel in page["panels"][1:]:
                self.assertEqual("none", panel["fact_delta"])
                for field in (
                    "beat_ids",
                    "covered_fact_ids",
                    "visible_characters",
                    "offscreen_characters",
                    "visible_props",
                    "continuity_state_hash",
                ):
                    self.assertEqual(source[field], panel[field])


if __name__ == "__main__":
    unittest.main()
