#!/usr/bin/env python3
"""Tests for su-image9 v2.1.2 semantic audit."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hashlib

import semantic_audit


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SemanticAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_data = {
            "metadata": {"skill_name": "su-fenjingskill-zh", "version": "2.4.2", "rule_revision": "r"},
            "script_lock": {
                "status": "locked",
                "approved_script_path": "/tmp/script.txt",
                "locked_text": "A和B。",
                "locked_text_hash": sha256_text("A和B。"),
            },
            "human_reviews": [
                {"gate": "GATE_A", "status": "approved", "reviewer": "r"},
                {"gate": "GATE_B", "status": "approved", "reviewer": "r"},
                {"gate": "GATE_C", "status": "approved", "reviewer": "r"},
            ],
            "validation_report": {"status": "PASS", "errors": [], "warnings": []},
            "warn_resolutions": [],
            "continuity_logs": [
                {
                    "scene_id": "S01",
                    "reality_layer": "现实",
                    "fixed_objects": [],
                    "characters": [],
                    "props": [],
                }
            ],
            "beats": [
                {
                    "beat_id": "B001",
                    "facts": [
                        {"fact_id": "B001-F01", "type": "dialogue", "text": "出发。"},
                        {"fact_id": "B001-F02", "type": "prop", "text": "钥匙"},
                    ],
                }
            ],
            "shots": [
                {
                    "shot_no": 1,
                    "scene_id": "S01",
                    "beat_ids": ["B001"],
                    "covered_fact_ids": ["B001-F01", "B001-F02"],
                    "source_paragraph": "A说：出发。",
                    "camera_main_image": "[平视, 双人中景] A和B相对站立。",
                    "notes": "",
                    "visible_characters": ["A", "B"],
                    "offscreen_characters": [],
                    "visible_props": ["钥匙"],
                    "continuity_updates": [],
                    "shot_type": "dialogue",
                    "insert_priority": "none",
                    "duration_seconds": 3,
                    "duration_breakdown": {
                        "sync_action_seconds": 0,
                        "sync_dialogue_seconds": 2,
                        "non_sync_action_seconds": 0,
                        "emotional_pause_seconds": 1,
                    },
                }
            ],
            "reference_bindings": [],
        }

    def test_clean_data_has_no_conflicts(self) -> None:
        self.assertEqual(semantic_audit.semantic_conflicts(self.base_data), [])

    def test_position_update_same_from_to(self) -> None:
        data = json.loads(json.dumps(self.base_data))
        data["shots"][0]["continuity_updates"] = [
            {
                "entity_type": "character",
                "entity": "A",
                "field": "position",
                "from": "路边",
                "to": "路边",
                "evidence_fact_ids": ["B001-F01"],
            }
        ]
        conflicts = semantic_audit.semantic_conflicts(data)
        self.assertTrue(any("起点与终点相同" in m for m in conflicts))

    def test_action_performer_mismatch(self) -> None:
        data = json.loads(json.dumps(self.base_data))
        data["shots"][0]["source_paragraph"] = "B走出门。"
        data["shots"][0]["continuity_updates"] = [
            {
                "entity_type": "character",
                "entity": "A",
                "field": "position",
                "from": "门内",
                "to": "门外",
                "evidence_fact_ids": ["B001-F01"],
            }
        ]
        conflicts = semantic_audit.semantic_conflicts(data)
        self.assertTrue(any("主语" in m and "continuity_updates" in m for m in conflicts))

    def test_overloaded_single_shot(self) -> None:
        data = json.loads(json.dumps(self.base_data))
        data["shots"][0]["beat_ids"] = ["B001", "B002", "B003"]
        data["shots"][0]["duration_breakdown"]["sync_action_seconds"] = 0
        data["shots"][0]["duration_breakdown"]["sync_dialogue_seconds"] = 1
        conflicts = semantic_audit.semantic_conflicts(data)
        self.assertTrue(any("覆盖 3 个 Beat" in m for m in conflicts))

    def test_must_have_insert_without_prop_fact(self) -> None:
        data = json.loads(json.dumps(self.base_data))
        data["shots"][0]["insert_priority"] = "must_have"
        data["shots"][0]["covered_fact_ids"] = ["B001-F01"]
        conflicts = semantic_audit.semantic_conflicts(data)
        self.assertTrue(any("insert_priority" in m and "prop fact" in m for m in conflicts))

    def test_must_have_insert_without_visible_prop(self) -> None:
        data = json.loads(json.dumps(self.base_data))
        data["shots"][0]["insert_priority"] = "must_have"
        data["shots"][0]["visible_props"] = []
        conflicts = semantic_audit.semantic_conflicts(data)
        self.assertTrue(any("insert_priority" in m and "visible_props" in m for m in conflicts))

    def test_non_reality_layer_missing_visual_cue(self) -> None:
        data = json.loads(json.dumps(self.base_data))
        data["continuity_logs"][0]["reality_layer"] = "回忆"
        conflicts = semantic_audit.semantic_conflicts(data)
        self.assertTrue(any("缺少可视化线索" in m for m in conflicts))

    def test_non_reality_layer_with_visual_cue_is_clean(self) -> None:
        data = json.loads(json.dumps(self.base_data))
        data["continuity_logs"][0]["reality_layer"] = "回忆"
        data["shots"][0]["notes"] = "使用虚化留白暗示回忆。"
        self.assertEqual(semantic_audit.semantic_conflicts(data), [])

    def test_contradictory_directional_terms(self) -> None:
        data = json.loads(json.dumps(self.base_data))
        data["shots"][0]["camera_main_image"] = "[平视] A从左向右走，同时从右向左看。"
        conflicts = semantic_audit.semantic_conflicts(data)
        self.assertTrue(any("同时出现" in m and "左" in m and "右" in m for m in conflicts))

    def test_cli_returns_exit_one_on_conflict(self) -> None:
        data = json.loads(json.dumps(self.base_data))
        data["shots"][0]["camera_main_image"] = "[平视] 上下移动。"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
            path = handle.name
        report_path = Path(path)
        try:
            code = semantic_audit.main([str(report_path)])
            self.assertEqual(code, 1)
        finally:
            report_path.unlink(missing_ok=True)

    def test_cli_returns_exit_zero_when_clean(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(self.base_data, handle, ensure_ascii=False)
            path = handle.name
        report_path = Path(path)
        try:
            code = semantic_audit.main([str(report_path)])
            self.assertEqual(code, 0)
        finally:
            report_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
