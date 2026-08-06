#!/usr/bin/env python3
"""Tests for su-image9 v2.1.2 visual QA."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_panels
import visual_qa


class VisualQATests(unittest.TestCase):
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
                        {"panel": "PANEL-1", "display_label": "C001", "must_show": ["A"], "must_not_show": [], "render_delta": "none", "camera_rationale": "源镜头。"},
                        {"panel": "PANEL-2", "display_label": "C001-A", "must_show": ["A"], "must_not_show": [], "render_delta": "allowed", "camera_rationale": "同轴更紧。"},
                    ],
                }
            ],
        }

    def test_visual_qa_passes_for_stub_panels(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            plan_path = temp_path / "plan.json"
            plan_path.write_text(json.dumps(self.panel_plan), encoding="utf-8")
            compiled_path = temp_path / "final_image_prompts.compiled.md"
            compiled_path.write_text(self.compiled, encoding="utf-8")
            out_dir = temp_path / "panels"
            code = generate_panels.main([
                "--panel-plan", str(plan_path),
                "--out-dir", str(out_dir),
            ])
            self.assertEqual(code, generate_panels.EXIT_PASS)
            report_path = temp_path / "visual_qa_report.json"
            qa_code = visual_qa.main([
                "--panel-plan", str(plan_path),
                "--pages-dir", str(out_dir),
                "--report", str(report_path),
            ])
            self.assertEqual(qa_code, visual_qa.EXIT_PASS)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["machine_findings"], [])
            self.assertTrue(len(report["review_checklist"]) >= 2)

    def test_visual_qa_fails_on_missing_panel(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            plan_path = temp_path / "plan.json"
            plan_path.write_text(json.dumps(self.panel_plan), encoding="utf-8")
            out_dir = temp_path / "panels"
            out_dir.mkdir()
            attempt_log = {
                "pages": [
                    {
                        "page": "PAGE-01",
                        "panels": [
                            {"panel": "PANEL-1", "status": "OK", "output": None},
                            {"panel": "PANEL-2", "status": "OK", "output": None},
                        ],
                    }
                ]
            }
            (out_dir / "attempt_log.json").write_text(json.dumps(attempt_log), encoding="utf-8")
            report_path = temp_path / "visual_qa_report.json"
            qa_code = visual_qa.main([
                "--panel-plan", str(plan_path),
                "--pages-dir", str(out_dir),
                "--report", str(report_path),
            ])
            self.assertEqual(qa_code, visual_qa.EXIT_REVIEW_REQUIRED)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(any("missing" in f for f in report["machine_findings"]))

    def test_visual_qa_checklist_includes_must_show(self) -> None:
        checklist = visual_qa.build_review_checklist(self.panel_plan)
        item = next((c for c in checklist if c["panel"] == "PANEL-1"), {})
        self.assertIn("must_show: A", item.get("checklist", []))


if __name__ == "__main__":
    unittest.main()
