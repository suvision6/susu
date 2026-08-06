#!/usr/bin/env python3
"""Tests for su-image9 v2.1.2 panel image generation (stub backend)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_panels


class GeneratePanelsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compiled = """# PAGE-01
DELIVERABLE:
@CANON(HARD_PHRASES)

SYSTEM_STYLE_LAYER:
@CANON(SYSTEM_STYLE_LAYER)

SOURCE_BINDING_LAYER:
Bound to C001.

SCENE_LAYER:
Scene S01; reality layer: 现实.

CAMERA_RULE_LAYER:
C001 source camera.

CONTINUITY_LAYER:
Visible character boundary: A.

PAGE_SPATIAL_ANCHOR:
Use PANEL-1.

FIXED_GEOMETRY_LOCK:
@CANON(GEOMETRY_BLUEPRINT)

VEHICLE_AND_AXIS_LOCKS:
Preserve axis.

OBJECT_VISIBILITY_AND_BOUNDARIES:
Draw only registered props.

PANEL_LAYER:
PANEL-1: Draw source camera. Preserve state. Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: none. Must not show: none. Render delta: none; story delta: none. Camera rationale: 源镜头。
PANEL-2: Draw derived angle. Derived composition. Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: none. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 同轴更紧。
PANEL-3: Draw derived angle. Derived composition. Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: none. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 同侧三分之四。
PANEL-4: Draw derived angle. Derived composition. Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: none. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 同侧侧面。
PANEL-5: Draw derived angle. Derived composition. Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: none. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 同侧高机位。
PANEL-6: Draw derived angle. Derived composition. Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: none. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 同侧低机位。
PANEL-7: Draw derived angle. Derived composition. Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: none. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 动作起点瞬间。
PANEL-8: Draw derived angle. Derived composition. Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: none. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 动作过程瞬间。
PANEL-9: Draw derived angle. Derived composition. Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: none. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 动作终点瞬间。

NEGATIVE_CONSTRAINTS:
@CANON(NEGATIVE_CONSTRAINTS)
"""
        self.panel_plan = {
            "skill": "su-image9",
            "version": "2.1.2",
            "schema_version": "2.1",
            "release_ready": True,
            "pages": [
                {
                    "page": "PAGE-01",
                    "panels": [
                        {"panel": "PANEL-1", "display_label": "C001"},
                        {"panel": "PANEL-2", "display_label": "C001-A"},
                        {"panel": "PANEL-3", "display_label": "C001-B"},
                        {"panel": "PANEL-4", "display_label": "C001-C"},
                        {"panel": "PANEL-5", "display_label": "C001-D"},
                        {"panel": "PANEL-6", "display_label": "C001-E"},
                        {"panel": "PANEL-7", "display_label": "C001-F"},
                        {"panel": "PANEL-8", "display_label": "C001-G"},
                        {"panel": "PANEL-9", "display_label": "C001-H"},
                    ],
                }
            ],
        }

    def test_stub_backend_generates_nine_panels(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out_dir = Path(temp) / "panels"
            manifest = generate_panels.generate_panels(self.panel_plan, self.compiled, out_dir, max_retries=2)
            self.assertEqual(manifest["status"], "PASS")
            self.assertEqual(manifest["backend"], "stub")
            self.assertEqual(len(manifest["pages"]), 1)
            self.assertEqual(len(manifest["pages"][0]["panels"]), 9)
            for panel in manifest["pages"][0]["panels"]:
                self.assertEqual(panel["status"], "OK")
                self.assertTrue(Path(panel["output"]).is_file())

    def test_attempt_log_records_retries_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out_dir = Path(temp) / "panels"
            manifest = generate_panels.generate_panels(self.panel_plan, self.compiled, out_dir, max_retries=2)
            generate_panels.write_outputs(out_dir, manifest)
            log_path = out_dir / "attempt_log.json"
            written = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(written["total_attempts"], 9)
            self.assertEqual(written["failed_panels"], [])
            for panel in written["pages"][0]["panels"]:
                self.assertEqual(panel["attempts"], 1)
                self.assertIsNotNone(panel["prompt_hash"])

    def test_missing_prompt_marks_panel_failed(self) -> None:
        compiled = "# PAGE-01\nPANEL_LAYER:\nPANEL-1: Draw.\n"
        with tempfile.TemporaryDirectory() as temp:
            out_dir = Path(temp) / "panels"
            manifest = generate_panels.generate_panels(self.panel_plan, compiled, out_dir, max_retries=2)
            self.assertEqual(manifest["status"], "REVIEW_REQUIRED")
            self.assertEqual(len(manifest["failed_panels"]), 8)

    def test_out_dir_must_be_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            existing = Path(temp) / "exists"
            existing.mkdir()
            code = generate_panels.main([
                "--panel-plan", str(existing / "plan.json"),
                "--out-dir", str(existing),
            ])
            self.assertEqual(code, generate_panels.EXIT_CONTRACT_FAIL)

    def test_release_ready_required(self) -> None:
        plan = json.loads(json.dumps(self.panel_plan))
        plan["release_ready"] = False
        with tempfile.TemporaryDirectory() as temp:
            plan_path = Path(temp) / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            compiled_path = Path(temp) / "final_image_prompts.compiled.md"
            compiled_path.write_text(self.compiled, encoding="utf-8")
            out_dir = Path(temp) / "out"
            code = generate_panels.main([
                "--panel-plan", str(plan_path),
                "--out-dir", str(out_dir),
            ])
            self.assertEqual(code, generate_panels.EXIT_CONTRACT_FAIL)

    def test_cli_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plan_path = Path(temp) / "plan.json"
            plan_path.write_text(json.dumps(self.panel_plan), encoding="utf-8")
            compiled_path = Path(temp) / "final_image_prompts.compiled.md"
            compiled_path.write_text(self.compiled, encoding="utf-8")
            out_dir = Path(temp) / "out"
            code = generate_panels.main([
                "--panel-plan", str(plan_path),
                "--out-dir", str(out_dir),
            ])
            self.assertEqual(code, generate_panels.EXIT_PASS)
            self.assertTrue((out_dir / "PAGE-01" / "PANEL-1.png").is_file())
            self.assertTrue((out_dir / "attempt_log.json").is_file())


if __name__ == "__main__":
    unittest.main()
