#!/usr/bin/env python3
"""Integration tests for the read-only su-fenjingskill adapter."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import upstream_adapter as adapter


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent


def current_fixture() -> Path:
    explicit = os.environ.get("SU_FENJING_FIXTURE")
    candidates = [
        Path(explicit) if explicit else Path("__missing__"),
        SKILL_DIR.parent / "su-fenjingskill" / "scripts" / "fixtures" / "shot-data-253-positive-draft.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise unittest.SkipTest("current su-fenjingskill fixture is unavailable")


def canonical_content_hash(data: dict) -> str:
    payload = copy.deepcopy(data)
    payload.pop("content_hash", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class UpstreamAdapterTests(unittest.TestCase):
    def test_capability_shape_needs_no_upstream_version_contract_gate_hash_or_beats(self) -> None:
        raw = {
            "scenes": [
                {
                    "scene_id": "SC001",
                    "scene": "书房 日 内",
                    "source_excerpt": "两人在书房对话。",
                    "space_map": {"anchors": ["书案", "门口"], "axis_notes": "保持关系轴。"},
                }
            ],
            "shots": [
                {
                    "shot_id": "SH001",
                    "scene_id": "SC001",
                    "duration_seconds": 3,
                    "camera": {"shot_size": "双人中景", "angle": "平视", "movement": {"type": "fixed"}, "composition": "两人分居书案两侧"},
                    "staging": {"subjects": ["甲", "乙"], "visible_subjects": ["甲", "乙"], "blocking": "两人隔案相对。"},
                    "sound": {"dialogue_segments": [{"dialogue_id": "D001", "text": "开始。", "delivery": "onscreen"}]},
                    "execution_text": "双人中景，隔案相对。",
                    "source_excerpt": "两人隔案相对。",
                }
            ],
        }
        before = copy.deepcopy(raw)
        normalized = adapter.adapt_upstream(raw)
        self.assertEqual(before, raw)
        self.assertEqual(1, normalized["shots"][0]["shot_no"])
        self.assertEqual("双人中景", normalized["shots"][0]["camera"]["shot_size"])
        self.assertEqual("capability-shape-read-only-adapter", normalized[adapter.ADAPTER_KEY]["source_mode"])

    def test_capability_shape_rejects_missing_camera_capability(self) -> None:
        raw = {
            "scenes": [{"scene_id": "SC001", "source_excerpt": "来源"}],
            "shots": [{"shot_id": "SH001", "scene_id": "SC001", "execution_text": "人物出现", "camera": {}}],
        }
        with self.assertRaisesRegex(adapter.UpstreamAdapterError, "shot_size and angle"):
            adapter.adapt_upstream(raw)

    def test_current_contract_is_adapted_without_mutation(self) -> None:
        source = current_fixture()
        before = source.read_bytes()
        raw = json.loads(before)
        normalized = adapter.adapt_upstream(raw)
        self.assertEqual("su-fenjingskill", normalized["metadata"]["skill_name"])
        self.assertEqual(raw["source_skill_version"], normalized["metadata"]["version"])
        expected_numbers = [adapter._shot_number(shot, index) for index, shot in enumerate(raw["shots"], 1)]
        self.assertEqual(expected_numbers, [shot["shot_no"] for shot in normalized["shots"]])
        self.assertEqual(before, source.read_bytes())

    def test_version_is_not_allowlisted(self) -> None:
        raw = json.loads(current_fixture().read_text(encoding="utf-8"))
        raw["source_skill_version"] = "99.7-custom"
        raw["content_hash"] = canonical_content_hash(raw)
        normalized = adapter.adapt_upstream(raw)
        self.assertEqual("99.7-custom", normalized["metadata"]["version"])

    def test_identity_does_not_override_usable_capability_shape(self) -> None:
        raw = json.loads(current_fixture().read_text(encoding="utf-8"))
        raw["source_skill"] = "another-skill"
        normalized = adapter.adapt_upstream(raw)
        self.assertEqual("another-skill", normalized[adapter.ADAPTER_KEY]["identity"])
        self.assertTrue(normalized["shots"])

    def test_end_to_end_derivation_is_read_only(self) -> None:
        source = current_fixture()
        before = source.read_bytes()
        with tempfile.TemporaryDirectory(prefix="su-image9-adapter-test-") as tmp:
            out_dir = Path(tmp) / "package"
            process = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "derive_su_image9_prompt_package.py"),
                    "--shot-data",
                    str(source),
                    "--out-dir",
                    str(out_dir),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, process.returncode, process.stderr)
            report = json.loads((out_dir / "validation_report.json").read_text(encoding="utf-8"))
            self.assertEqual("PASS", report["status"])
            self.assertTrue(report["release_ready"])
        self.assertEqual(before, source.read_bytes())


if __name__ == "__main__":
    unittest.main()
