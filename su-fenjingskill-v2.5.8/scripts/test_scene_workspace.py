#!/usr/bin/env python3
"""Integration tests for scene_workspace extract/merge contract."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.dont_write_bytecode = True
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import scene_workspace
import contract_schema
from test_storyboard_delivery import valid_draft, refresh_confirmation_digests


def valid_two_scene_draft() -> dict:
    """Return a two-scene draft for workspace boundary tests."""
    draft = valid_draft()
    draft.setdefault(
        "rhythm_policy", copy.deepcopy(contract_schema.DEFAULT_RHYTHM_POLICY)
    )
    draft["shot_plan"].setdefault("dialogue_playbacks", [])
    draft["shot_plan"].setdefault("rhythm_reviews", [])
    # Ensure a stable second scene that is not entangled with the first.
    draft["scenes"].append(
        {
            "scene_id": "SC002",
            "scene": "第二场：周起身离开",
            "reality_layer": "现实",
            "axes": [
                {
                    "axis_id": "AX002",
                    "axis_type": "eyeline",
                    "endpoint_a": "周",
                    "endpoint_b": "门",
                }
            ],
            "initial_continuity": {
                "characters": [
                    {
                        "name": "周",
                        "position": "桌边",
                        "facing": "门口",
                        "eyeline": "门",
                        "presence": "onscreen",
                        "state": "警觉",
                    },
                    {
                        "name": "林",
                        "position": "门口",
                        "facing": "桌边",
                        "eyeline": "周",
                        "presence": "onscreen",
                        "state": "试探",
                    },
                ],
                "props": [
                    {
                        "name": "钥匙",
                        "position": "周右手",
                        "owner": "周",
                        "state": "紧握",
                    }
                ],
                "fixed_objects": [{"name": "桌", "position": "房间中央", "state": "完好"}],
                "sound_sources": [],
                "reality_layer": "现实",
            },
            "inherits_from": None,
            "inherited_states": [],
        }
    )
    draft["beats"].append(
        {
            "beat_id": "B003",
            "beat_order": 3,
            "scene_id": "SC002",
            "source_spans": [{"start": 22, "end": 30}],
            "dramatic_change": "周起身离开，打破对峙。",
            "facts": [
                {
                    "fact_id": "F005",
                    "type": "action",
                    "text": "周站起身，走向门口。",
                    "source_spans": [{"start": 22, "end": 30}],
                    "performers": ["周"],
                }
            ],
        }
    )
    draft["screen_events"].append(
        {
            "screen_event_id": "SEV005",
            "scene_id": "SC002",
            "event_order": 5,
            "beat_ids": ["B003"],
            "covered_fact_ids": ["F005"],
            "source_spans": [{"start": 22, "end": 30}],
            "spatial_zone": "第二场内部",
            "temporal_relation": "sequential",
            "visual_subjects": ["周"],
            "visual_action": "周站起身，走向门口。",
            "viewing_requirement": "观众看清周起身和移动方向。",
            "scale_requirement": "由当前原子事件的观看尺度决定。",
            "event_role": "action",
            "primary_viewing_subject": "周",
            "focus_scale": "body",
            "sound_fact_ids": [],
        }
    )
    draft["shot_plan"]["planned_units"].append(
        {
            "plan_unit_id": "PU003",
            "plan_order": 3,
            "scene_id": "SC002",
            "beat_ids": ["B003"],
            "screen_event_ids": ["SEV005"],
            "source_spans": [{"start": 22, "end": 30}],
            "estimated_duration_seconds": 4,
            "narrative_purpose": "让周起身离开，打破对峙。",
        }
    )
    draft["shots"].append(
        {
            "shot_id": "SH003",
            "shot_order": 3,
            "plan_unit_id": "PU003",
            "scene_id": "SC002",
            "beat_ids": ["B003"],
            "source_spans": [{"start": 22, "end": 30}],
            "covered_fact_ids": ["F005"],
            "primary_fact_id": "F005",
            "duration_seconds": 4,
            "duration_blocks": [
                {
                    "block_id": "TB01",
                    "label": "同步动作、台词与运镜",
                    "action_seconds": 4,
                    "dialogue_seconds": 0,
                    "performance_seconds": 2,
                    "camera_seconds": 3,
                }
            ],
            "cut_design": {
                "entry_trigger": "承接第二场起点。",
                "exit_trigger": "周停在门口。",
                "isolation_intent": "none",
            },
            "camera": {
                "shot_size": "中景",
                "angle": "平视",
                "position": "侧拍，保持周移动方向可读",
                "composition": "周从画面中央走向左侧门口",
                "movement": "横移跟随",
                "start_frame": "周仍坐在桌边",
                "end_frame": "周站在门口，背对镜头",
            },
            "blocking": [
                {
                    "character": "周",
                    "start_position": "桌边",
                    "action": "起身并走向门口",
                    "end_position": "门口",
                    "facing": "门口",
                    "eyeline": "门",
                }
            ],
            "performance": {
                "emotion_arc_id": "EA001",
                "phase": "existing_transition",
                "emotion_intent": "周从警觉转为离开。",
                "visible_behavior": ["起身时不回头", "步伐稳定"],
            },
            "dialogue": [],
            "visible_characters": ["周", "林"],
            "visible_props": ["钥匙"],
            "environment_behavior": [],
            "continuity": {
                "axis_id": "AX002",
                "axis_side": "side_a",
                "eyelines": [
                    {"character": "周", "target": "门", "direction": "screen_left"},
                    {"character": "林", "target": "周", "direction": "screen_right"},
                ],
                "screen_directions": [
                    {"entity": "周", "kind": "eyeline", "direction": "screen_left"},
                    {"entity": "林", "kind": "eyeline", "direction": "screen_right"},
                ],
                "action_match": {"incoming": None, "outgoing": None},
                "intentional_exceptions": [],
            },
            "continuity_updates": [],
            "end_state": ["周站在门口", "林仍在桌边"],
            "transition_to_next": {
                "type": "scene_end",
                "edit_point_id": None,
            },
            "rendered_shot_description": "",
            "notes": "第二场独立成镜。",
        }
    )
    draft["emotion_arcs"].append(
        {
            "emotion_arc_id": "EA002",
            "character": "周",
            "baseline": "警觉并准备离开。",
            "trigger_fact_ids": ["F005"],
            "phases": [
                {
                    "phase": "existing_transition",
                    "beat_ids": ["B003"],
                    "intent": "从警觉转为离开现场。",
                    "visible_direction": ["起身时不回头", "步伐稳定"],
                }
            ],
        }
    )
    draft["shots"][-1]["performance"]["emotion_arc_id"] = "EA002"
    return draft


class SceneWorkspaceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="su-fenjingskill-workspace-test-"
        )
        self.root = Path(self.temporary_directory.name)
        self.input_path = self.root / "draft.json"
        self.workspace_path = self.root / "workspace.json"
        self.output_path = self.root / "merged.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_json(self, path: Path, value: dict) -> None:
        path.write_bytes(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            + b"\n"
        )

    def prepared_draft(self, draft: dict) -> dict:
        refresh_confirmation_digests(draft)
        # scene_workspace uses locked_text_hash and gate_1_digest directly;
        # refresh_confirmation_digests already populates the source hash.
        return draft

    def test_schema_exposes_258_rhythm_and_playback_contract(self) -> None:
        schema = contract_schema.public_json_schema()
        self.assertEqual(contract_schema.CONTRACT_VERSION, "2.5.8")
        self.assertEqual(contract_schema.SOURCE_SKILL_VERSION, "2.5.8")
        self.assertEqual(
            contract_schema.GATE_2_RULE_REVISION,
            "2.5.8-rhythm-integrity-r1",
        )
        self.assertEqual(
            set(schema["$defs"]["rhythm_policy"]["properties"]),
            contract_schema.RHYTHM_POLICY_KEYS,
        )
        for key, value in contract_schema.DEFAULT_RHYTHM_POLICY.items():
            self.assertEqual(
                schema["$defs"]["rhythm_policy"]["properties"][key],
                {"const": value},
            )
        self.assertEqual(
            set(schema["$defs"]["dialogue_playback"]["properties"]),
            contract_schema.DIALOGUE_PLAYBACK_KEYS,
        )
        self.assertEqual(
            set(schema["$defs"]["dialogue_playback_segment"]["properties"]),
            contract_schema.DIALOGUE_PLAYBACK_SEGMENT_KEYS,
        )
        self.assertEqual(
            set(schema["$defs"]["duration_design"]["properties"]),
            contract_schema.DURATION_DESIGN_KEYS,
        )
        self.assertEqual(
            set(schema["$defs"]["short_shot_design"]["properties"]),
            contract_schema.SHORT_SHOT_DESIGN_KEYS,
        )
        self.assertEqual(
            set(schema["$defs"]["long_take_progression"]["properties"]),
            contract_schema.LONG_TAKE_PROGRESSION_KEYS,
        )
        self.assertEqual(
            set(schema["$defs"]["rhythm_review"]["properties"]),
            contract_schema.RHYTHM_REVIEW_KEYS,
        )
        dialogue_required = set(
            schema["$defs"]["fact"]["allOf"][0]["then"]["required"]
        )
        self.assertTrue(
            {"spoken_source_spans", "stage_direction_fact_ids"}
            <= dialogue_required
        )
        self.assertIn(
            "dialogue_playback_segment_ids",
            schema["$defs"]["shot_phase"]["required"],
        )
        self.assertIn(
            "playback_segment_id",
            schema["$defs"]["dialogue"]["required"],
        )

    def test_static_schema_matches_machine_authority(self) -> None:
        static_path = SCRIPT_DIR.parent / "references" / "shot-data.schema.json"
        self.assertEqual(static_path.read_bytes(), contract_schema.schema_bytes())

    def test_extract_isolates_single_scene_data(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        self.write_json(self.input_path, draft)
        workspace = scene_workspace.extract_scene(draft, "SC001")

        self.assertEqual(workspace["workspace_contract"], "shot-data-scene-workspace/3")
        self.assertEqual(workspace["scene_id"], "SC001")
        self.assertEqual(workspace["project_id"], draft["project_id"])
        self.assertEqual(workspace["locked_text_hash"], draft["source"]["locked_text_hash"])
        # gate_1_digest comes from storyboard_delivery.stage_digest; just verify non-empty.
        self.assertTrue(workspace["gate_1_digest"])
        self.assertRegex(workspace["base_scene_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(workspace["rhythm_policy"], draft["rhythm_policy"])

        scene_ids = {item["scene_id"] for item in workspace["planned_units"]}
        self.assertEqual(scene_ids, {"SC001"})

        for key in ("beats", "screen_events", "shots", "performance_chains"):
            for item in workspace[key]:
                self.assertEqual(item["scene_id"], "SC001")
        self.assertEqual(
            [item["emotion_arc_id"] for item in workspace["emotion_arcs"]],
            ["EA001"],
        )

    def test_extract_missing_scene_raises(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        with self.assertRaisesRegex(ValueError, "scene_id"):
            scene_workspace.extract_scene(draft, "SC999")

    def test_merge_resets_gate_two_and_recomputes_metrics(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        workspace["planned_units"][0]["estimated_duration_seconds"] = 7
        workspace["viewing_decisions"] = []

        merged = scene_workspace.merge_scene(draft, workspace)

        self.assertEqual(merged["confirmations"]["gate_2"]["status"], "pending")
        self.assertEqual(merged["confirmations"]["gate_2"]["stage_digest"], "")
        self.assertEqual(
            merged["confirmations"]["gate_2"]["notes"],
            "场景工作区合并后必须重新展示并确认 Gate 2。",
        )
        self.assertEqual(merged["shot_plan"]["planned_total_duration_seconds"], 13)
        self.assertEqual(merged["shot_plan"]["planned_edit_point_count"], 0)
        self.assertEqual(merged["content_hash"], "")

    def test_merge_rejects_project_id_mismatch(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        workspace["project_id"] = "OTHER"
        with self.assertRaisesRegex(ValueError, "project_id"):
            scene_workspace.merge_scene(draft, workspace)

    def test_merge_rejects_locked_text_hash_mismatch(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        workspace["locked_text_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "来源 hash"):
            scene_workspace.merge_scene(draft, workspace)

    def test_merge_rejects_gate_1_digest_mismatch(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        workspace["gate_1_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Gate 1"):
            scene_workspace.merge_scene(draft, workspace)

    def test_merge_rejects_unsupported_workspace_contract(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        workspace["workspace_contract"] = "shot-data-scene-workspace/0"
        with self.assertRaisesRegex(ValueError, "受支持"):
            scene_workspace.merge_scene(draft, workspace)

    def test_merge_rejects_legacy_workspace_contract(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        workspace["workspace_contract"] = "shot-data-scene-workspace/1"
        workspace.pop("base_scene_digest")
        with self.assertRaisesRegex(ValueError, "重新 extract"):
            scene_workspace.merge_scene(draft, workspace)

    def test_merge_rejects_workspace_contract_two(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        workspace["workspace_contract"] = "shot-data-scene-workspace/2"
        with self.assertRaisesRegex(ValueError, "重新 extract"):
            scene_workspace.merge_scene(draft, workspace)

    def test_merge_rejects_rhythm_policy_mismatch(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        workspace["rhythm_policy"]["hard_max_shot_seconds"] = 20
        with self.assertRaisesRegex(ValueError, "rhythm_policy"):
            scene_workspace.merge_scene(draft, workspace)

    def test_extract_and_merge_scene_playbacks_and_rhythm_reviews(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        draft["shot_plan"]["dialogue_playbacks"] = [
            {
                "playback_id": "DPB001",
                "scene_id": "SC001",
                "fact_id": "F002",
                "speech_min_seconds": 2.0,
                "planned_playback_seconds": 2.5,
                "segments": [],
            },
            {
                "playback_id": "DPB002",
                "scene_id": "SC002",
                "fact_id": "F005",
                "speech_min_seconds": 1.0,
                "planned_playback_seconds": 1.5,
                "segments": [],
            },
        ]
        draft["shot_plan"]["rhythm_reviews"] = [
            {
                "review_id": "RR001",
                "scope": "project",
                "scene_id": None,
                "finding_code": "project-pattern",
                "finding_value": 0.9,
                "decision": "retain",
                "reason": "项目级复核必须保持在主 draft。",
                "affected_plan_unit_ids": ["PU001"],
            },
            {
                "review_id": "RR002",
                "scope": "scene",
                "scene_id": "SC001",
                "finding_code": "scene-pattern",
                "finding_value": 0.2,
                "decision": "rework",
                "reason": "第一场需要重新设计节奏。",
                "affected_plan_unit_ids": ["PU001"],
            },
            {
                "review_id": "RR003",
                "scope": "scene",
                "scene_id": "SC002",
                "finding_code": "scene-pattern",
                "finding_value": 0.1,
                "decision": "retain",
                "reason": "第二场节奏保持。",
                "affected_plan_unit_ids": ["PU003"],
            },
        ]

        workspace = scene_workspace.extract_scene(draft, "SC001")
        self.assertEqual(
            [item["playback_id"] for item in workspace["dialogue_playbacks"]],
            ["DPB001"],
        )
        self.assertEqual(
            [item["review_id"] for item in workspace["rhythm_reviews"]],
            ["RR002"],
        )

        workspace["dialogue_playbacks"][0]["planned_playback_seconds"] = 3.0
        workspace["rhythm_reviews"][0]["reason"] = "第一场节奏已在工作区重做。"
        merged = scene_workspace.merge_scene(draft, workspace)
        self.assertEqual(
            next(
                item
                for item in merged["shot_plan"]["dialogue_playbacks"]
                if item["scene_id"] == "SC001"
            )["planned_playback_seconds"],
            3.0,
        )
        self.assertEqual(
            {item["review_id"] for item in merged["shot_plan"]["rhythm_reviews"]},
            {"RR002", "RR003"},
        )
        self.assertFalse(
            any(
                item["scope"] == "project"
                for item in merged["shot_plan"]["rhythm_reviews"]
            )
        )
        self.assertEqual(
            next(
                item
                for item in merged["shot_plan"]["rhythm_reviews"]
                if item["review_id"] == "RR002"
            )["reason"],
            "第一场节奏已在工作区重做。",
        )

    def test_merge_rejects_tampered_base_scene_digest(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        workspace["base_scene_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "场景基线"):
            scene_workspace.merge_scene(draft, workspace)

    def test_merge_rejects_stale_same_scene(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        draft["shots"][0]["camera"]["composition"] = "同场已由另一工作区改写"
        with self.assertRaisesRegex(ValueError, "同一场景已发生变化"):
            scene_workspace.merge_scene(draft, workspace)

    def test_merge_rejects_stale_same_scene_emotion_arc(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        draft["emotion_arcs"][0]["baseline"] = "同场情绪弧已由另一工作区改写"
        with self.assertRaisesRegex(ValueError, "同一场景已发生变化"):
            scene_workspace.merge_scene(draft, workspace)

    def test_merge_allows_unrelated_scene_change(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        draft["scenes"][1]["scene"] = "第二场已独立修改"
        merged = scene_workspace.merge_scene(draft, workspace)
        self.assertEqual(merged["scenes"][1]["scene"], "第二场已独立修改")

    def test_merge_allows_unrelated_scene_emotion_arc_change(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        draft["emotion_arcs"][1]["baseline"] = "第二场情绪弧已独立修改"
        merged = scene_workspace.merge_scene(draft, workspace)
        second_arc = next(
            item for item in merged["emotion_arcs"] if item["emotion_arc_id"] == "EA002"
        )
        self.assertEqual(second_arc["baseline"], "第二场情绪弧已独立修改")

    def test_merge_ignores_edit_point_renumbering_from_other_scene(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        draft["shot_plan"]["planned_units"].append(
            {
                "plan_unit_id": "PU004",
                "plan_order": 4,
                "scene_id": "SC002",
                "beat_ids": ["B003"],
                "screen_event_ids": ["SEV006"],
                "source_spans": [{"start": 22, "end": 30}],
                "estimated_duration_seconds": 1,
                "narrative_purpose": "第二场内部延续。",
            }
        )
        draft["screen_events"].append(
            {
                **copy.deepcopy(draft["screen_events"][-1]),
                "screen_event_id": "SEV006",
                "event_order": 6,
            }
        )
        draft["shot_plan"]["viewing_decisions"].append({
            "viewing_decision_id": "VD004",
            "scene_id": "SC002",
            "from_screen_event_id": "SEV005",
            "to_screen_event_id": "SEV006",
            "mode": "cut",
            "trigger": "第二场自身边界。",
            "viewing_change": "第二场观看位置改变。",
            "director_reason": "第二场内部切换。",
            "reframe_method": None,
            "non_cut_basis": None,
        })
        scene_workspace.delivery.derive_edit_points(draft)
        workspace = scene_workspace.extract_scene(draft, "SC002")
        self.assertEqual(workspace["edit_points"][0]["edit_point_id"], "EP002")

        draft["shot_plan"]["viewing_decisions"][0]["mode"] = "cut"
        draft["shot_plan"]["viewing_decisions"][0]["reframe_method"] = None
        draft["shot_plan"]["viewing_decisions"][0]["non_cut_basis"] = None
        scene_workspace.delivery.derive_edit_points(draft)
        current_sc002 = scene_workspace._scene_slice(draft, "SC002")
        self.assertEqual(current_sc002["edit_points"][0]["edit_point_id"], "EP003")

        merged = scene_workspace.merge_scene(draft, workspace)
        self.assertEqual(
            next(
                item
                for item in merged["scenes"]
                if item["scene_id"] == "SC002"
            )["scene"],
            "第二场：周起身离开",
        )

    def test_merge_does_not_mutate_other_scenes(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        workspace["scene"]["scene"] = "SC001 已修改"

        merged = scene_workspace.merge_scene(draft, workspace)
        sc002 = next(item for item in merged["scenes"] if item["scene_id"] == "SC002")
        self.assertEqual(sc002["scene"], "第二场：周起身离开")

        original_sc002_shots = [
            item for item in draft["shots"] if item["scene_id"] == "SC002"
        ]
        merged_sc002_shots = [
            item for item in merged["shots"] if item["scene_id"] == "SC002"
        ]
        self.assertEqual(len(merged_sc002_shots), len(original_sc002_shots))

    def test_cli_extract_returns_zero_and_writes_workspace(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        self.write_json(self.input_path, draft)
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "scene_workspace.py"),
                "extract",
                "--input",
                str(self.input_path),
                "--scene-id",
                "SC001",
                "--output",
                str(self.workspace_path),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(self.workspace_path.is_file())
        workspace = json.loads(self.workspace_path.read_text(encoding="utf-8"))
        self.assertEqual(workspace["scene_id"], "SC001")

    def test_cli_extract_missing_scene_returns_nonzero(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        self.write_json(self.input_path, draft)
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "scene_workspace.py"),
                "extract",
                "--input",
                str(self.input_path),
                "--scene-id",
                "SC999",
                "--output",
                str(self.workspace_path),
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL", result.stderr)

    def test_cli_merge_returns_zero_and_writes_merged(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        self.write_json(self.input_path, draft)
        self.write_json(self.workspace_path, workspace)
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "scene_workspace.py"),
                "merge",
                "--input",
                str(self.input_path),
                "--scene-workspace",
                str(self.workspace_path),
                "--output",
                str(self.output_path),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(self.output_path.is_file())
        merged = json.loads(self.output_path.read_text(encoding="utf-8"))
        self.assertEqual(merged["confirmations"]["gate_2"]["status"], "pending")

    def test_cli_merge_rejects_tampered_workspace(self) -> None:
        draft = self.prepared_draft(valid_two_scene_draft())
        workspace = scene_workspace.extract_scene(draft, "SC001")
        workspace["locked_text_hash"] = "0" * 64
        self.write_json(self.input_path, draft)
        self.write_json(self.workspace_path, workspace)
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "scene_workspace.py"),
                "merge",
                "--input",
                str(self.input_path),
                "--scene-workspace",
                str(self.workspace_path),
                "--output",
                str(self.output_path),
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
