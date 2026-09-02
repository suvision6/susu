#!/usr/bin/env python3
"""Tests for the current su-image9 external annotation tool."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

import annotate_storyboard_pages as annotate


SCRIPT = Path(__file__).with_name("annotate_storyboard_pages.py")
FONT = Path("C:/Windows/Fonts/msyh.ttc")


def fixture_payloads(source: str = "PAGE-01.png") -> tuple[dict, dict]:
    data = {"shots": [{"shot_no": index} for index in range(1, 10)]}
    page_map = {
        "pages": [
            {
                "page_no": 1,
                "source": source,
                "header": "山崖平台｜镜头001-009",
                "panels": [
                    {
                        "panel_no": index,
                        "source_shot": index,
                        "display_label": "C005-A｜派生角度" if index == 5 else f"C{index:03d}｜源镜头",
                        "camera_label": "过肩近景" if index == 5 else "中景",
                    }
                    for index in range(1, 10)
                ],
            }
        ]
    }
    return data, page_map


def draw_real_grid(path: Path) -> Image.Image:
    image = Image.new("RGB", (900, 520), "white")
    draw = ImageDraw.Draw(image)
    xs = [(30, 290), (320, 580), (610, 870)]
    ys = [(30, 160), (190, 320), (350, 480)]
    for top, bottom in ys:
        for left, right in xs:
            draw.rectangle((left, top, right, bottom), outline="black", width=3)
    image.save(path)
    return image


class Annotation210Tests(unittest.TestCase):
    def run_tool(
        self,
        root: Path,
        data: dict,
        page_map: dict,
        *,
        font: Path = FONT,
        source_hash: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        data_path = root / "shot_data.json"
        map_path = root / "page-map.json"
        data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        signed_map = copy.deepcopy(page_map)
        signed_map.update(
            {
                "skill": "su-image9",
                "version": annotate.VERSION,
                "schema_version": "2.1",
                "source_file_sha256": source_hash or annotate.sha256_file(data_path),
                "release_ready": True,
            }
        )
        map_path.write_text(json.dumps(signed_map, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--data",
                str(data_path),
                "--page-map",
                str(map_path),
                "--pages",
                str(root / "pages"),
                "--output",
                str(root / "output"),
                "--font-path",
                str(font),
            ],
            text=True,
            capture_output=True,
        )

    def test_detected_grid_labels_and_source_pixels_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = root / "pages"
            pages.mkdir()
            original = draw_real_grid(pages / "PAGE-01.png")
            data, page_map = fixture_payloads()
            result = self.run_tool(root, data, page_map)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((root / "output" / "annotation_manifest.json").read_text(encoding="utf-8"))
            page = manifest["pages"][0]
            self.assertEqual(page["box_detection"], "detected_image_grid")
            self.assertEqual(page["panel_labels"]["5"], "C005-A｜派生角度")
            self.assertEqual(page["camera_labels"]["5"], "过肩近景")
            output = Image.open(root / "output" / "PAGE-01.png").convert("RGB")
            region = tuple(page["source_pixel_region"])
            restored = output.crop(region)
            self.assertEqual(restored.tobytes(), original.convert("RGB").tobytes())
            self.assertEqual(output.width, original.width)
            self.assertGreater(output.height, original.height)

    def test_missing_camera_label_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = root / "pages"
            pages.mkdir()
            draw_real_grid(pages / "PAGE-01.png")
            data, page_map = fixture_payloads()
            page_map["pages"][0]["panels"][0].pop("camera_label")
            result = self.run_tool(root, data, page_map)
            self.assertEqual(2, result.returncode)
            manifest = json.loads((root / "output" / "annotation_manifest.json").read_text(encoding="utf-8"))
            self.assertIn("camera_label is required", manifest["error"])

    def test_long_camera_label_font_fits_one_column(self) -> None:
        image = Image.new("RGB", (600, 100), "white")
        draw = ImageDraw.Draw(image)
        font = annotate.ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", annotate.FONT_SIZE)
        box = (0, 0, 200, 48)
        label = "C022｜双人中近景→双人近景"
        fitted = annotate.fit_font_to_box(draw, label, font, box)
        text_box = draw.textbbox((0, 0), label, font=fitted)
        self.assertLessEqual(text_box[2] - text_box[0], 200 - 32)

    def test_implausibly_narrow_detected_boxes_fall_back(self) -> None:
        image = Image.new("RGB", (900, 520), "white")
        draw = ImageDraw.Draw(image)
        for x in (300, 310, 400, 410, 500, 510):
            draw.line((x, 0, x, 520), fill="black", width=2)
        for y in (100, 110, 200, 210, 300, 310):
            draw.line((0, y, 900, y), fill="black", width=2)
        self.assertIsNone(annotate.detect_grid_boxes(image))

    def test_canonical_fallback_records_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = root / "pages"
            pages.mkdir()
            Image.new("RGB", (900, 520), "white").save(pages / "PAGE-01.png")
            data, page_map = fixture_payloads()
            result = self.run_tool(root, data, page_map)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((root / "output" / "annotation_manifest.json").read_text(encoding="utf-8"))
            page = manifest["pages"][0]
            self.assertEqual(page["box_detection"], "canonical_fallback")
            self.assertIn("actual_grid_detection_failed; canonical_boxes_used", page["warnings"])

    def test_missing_page_fails_with_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pages").mkdir()
            data, page_map = fixture_payloads("MISSING.png")
            result = self.run_tool(root, data, page_map)
            self.assertEqual(result.returncode, 2)
            manifest = json.loads((root / "output" / "annotation_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "CONTRACT_FAIL")
            self.assertEqual(manifest["code"], 2)
            self.assertIn("source page is missing", manifest["error"])

    def test_stale_source_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = root / "pages"
            pages.mkdir()
            draw_real_grid(pages / "PAGE-01.png")
            data, page_map = fixture_payloads()
            result = self.run_tool(root, data, page_map, source_hash="0" * 64)
            self.assertEqual(result.returncode, 2)
            manifest = json.loads((root / "output" / "annotation_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("CONTRACT_FAIL", manifest["status"])
            self.assertIn("source hash does not match", manifest["error"])

    def test_second_page_failure_leaves_no_partial_annotated_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = root / "pages"
            pages.mkdir()
            draw_real_grid(pages / "PAGE-01.png")
            data, page_map = fixture_payloads()
            second = copy.deepcopy(page_map["pages"][0])
            second["page_no"] = 2
            second["source"] = "PAGE-02.png"
            second["header"] = "山崖平台｜第二页"
            page_map["pages"].append(second)
            result = self.run_tool(root, data, page_map)
            self.assertEqual(result.returncode, 2)
            output_names = sorted(path.name for path in (root / "output").iterdir())
            self.assertEqual(["annotation_manifest.json"], output_names)

    def test_font_must_have_verified_chinese_glyphs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "missing.ttf"
            with mock.patch.object(annotate, "WINDOWS_FONT_CANDIDATES", ()):
                with self.assertRaisesRegex(annotate.ToolError, "No reliable Chinese font"):
                    annotate.select_font(bad)

    def test_only_png_pages_and_annotation_manifest_are_emitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = root / "pages"
            pages.mkdir()
            draw_real_grid(pages / "PAGE-01.png")
            data, page_map = fixture_payloads()
            result = self.run_tool(root, data, page_map)
            self.assertEqual(result.returncode, 0, result.stderr)
            names = sorted(path.name for path in (root / "output").iterdir())
            self.assertEqual(names, ["PAGE-01.png", "annotation_manifest.json"])

    def test_per_panel_mode_composites_page_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page_dir = root / "pages" / "PAGE-01"
            page_dir.mkdir(parents=True)
            for panel_no in range(1, 10):
                Image.new("RGB", (160, 90), (panel_no * 20, panel_no * 20, panel_no * 20)).save(
                    page_dir / f"PANEL-{panel_no}.png"
                )
            data, page_map = fixture_payloads()
            data_path = root / "shot_data.json"
            map_path = root / "page-map.json"
            data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            page_map.update(
                {
                    "skill": "su-image9",
                    "version": annotate.VERSION,
                    "schema_version": annotate.SCHEMA_VERSION,
                    "source_file_sha256": annotate.sha256_file(data_path),
                    "release_ready": True,
                }
            )
            map_path.write_text(json.dumps(page_map, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--data",
                    str(data_path),
                    "--page-map",
                    str(map_path),
                    "--pages",
                    str(root / "pages"),
                    "--output",
                    str(root / "output"),
                    "--mode",
                    "per-panel",
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            manifest = json.loads((root / "output" / "annotation_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("per_panel_composite", manifest["pages"][0]["box_detection"])
            self.assertTrue((root / "output" / "PAGE-01.png").is_file())


if __name__ == "__main__":
    unittest.main()
