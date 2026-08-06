#!/usr/bin/env python3
"""Visual QA for su-image9 v2.1.2 generated panel images.

Checks machine-verifiable geometry, style, and text rules. Semantic and
continuity checks are reported as a human review checklist rather than auto-
assertions.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zlib
from pathlib import Path
from typing import Any


VERSION = "2.1.2"
SCHEMA_VERSION = "2.1"

EXIT_PASS = 0
EXIT_REVIEW_REQUIRED = 1
EXIT_CONTRACT_FAIL = 2
EXIT_TOOL_ERROR = 3


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} root must be an object")
    return value


def is_grayscale(image) -> bool:
    """Return True if image uses only grayscale pixels."""
    if image.mode == "L":
        return True
    rgb = image.convert("RGB")
    pixels = list(rgb.getdata())
    return all(abs(int(r) - int(g)) <= 2 and abs(int(g) - int(b)) <= 2 for r, g, b in pixels)


def has_internal_text(image, box: tuple[int, int, int, int]) -> bool:
    """Simple OCR-style heuristic: look for high-contrast small shapes inside box."""
    # This is a lightweight placeholder. Real OCR can be swapped in later.
    gray = image.convert("L").crop(box)
    pixels = list(gray.getdata())
    if not pixels:
        return False
    dark_ratio = sum(1 for p in pixels if int(p) < 64) / len(pixels)
    # If a significant portion of the panel is very dark, flag for review.
    # A proper text detector will replace this heuristic.
    return dark_ratio > 0.25


def expected_panel_box(image, panel_no: int) -> tuple[int, int, int, int]:
    """Compute the expected canonical box for a panel within a 3x3 grid."""
    width, height = image.size
    margin_x = round(width * 0.045)
    margin_y = round(height * 0.06)
    gutter_x = round(width * 0.022)
    gutter_y = round(height * 0.03)
    panel_width = (width - margin_x * 2 - gutter_x * 2) // 3
    panel_height = round(panel_width * 9 / 16)
    row = (panel_no - 1) // 3
    col = (panel_no - 1) % 3
    left = margin_x + col * (panel_width + gutter_x)
    top = margin_y + row * (panel_height + gutter_y)
    return (left, top, left + panel_width, top + panel_height)


def open_image(path: Path):
    """Open a PNG image without requiring Pillow, falling back to a tiny parser."""
    try:
        from PIL import Image
        return Image.open(path)
    except Exception:
        pass

    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG file")
    # Minimal PNG parser: expect IHDR then one or more IDAT chunks.
    offset = 8
    width = height = bit_depth = color_type = None
    idat_parts: list[bytes] = []
    while offset < len(data):
        length = int.from_bytes(data[offset:offset + 4], "big")
        chunk_type = data[offset + 4:offset + 8]
        chunk_data = data[offset + 8:offset + 8 + length]
        if chunk_type == b"IHDR":
            width = int.from_bytes(chunk_data[0:4], "big")
            height = int.from_bytes(chunk_data[4:8], "big")
            bit_depth = chunk_data[8]
            color_type = chunk_data[9]
        elif chunk_type == b"IDAT":
            idat_parts.append(chunk_data)
        elif chunk_type == b"IEND":
            break
        offset += 12 + length
    if width is None or not idat_parts:
        raise ValueError("missing IHDR or IDAT")
    decompressed = zlib.decompress(b"".join(idat_parts))

    class SimpleImage:
        def __init__(self, width: int, height: int, mode: str, pixels: bytes):
            self.size = (width, height)
            self.mode = mode
            self._pixels = pixels

        def convert(self, mode: str):
            if mode == "RGB":
                if self.mode == "L":
                    rgb = bytearray()
                    for p in self._pixels:
                        rgb.extend([p, p, p])
                    return SimpleImage(self.size[0], self.size[1], "RGB", bytes(rgb))
                if self.mode == "RGB":
                    return self
            if mode == "L":
                if self.mode == "L":
                    return self
            raise ValueError(f"unsupported conversion to {mode}")

        def crop(self, box: tuple[int, int, int, int]):
            x1, y1, x2, y2 = box
            row_bytes = self.size[0] if self.mode == "L" else self.size[0] * 3
            cropped = bytearray()
            for y in range(y1, y2):
                start = y * row_bytes + (x1 if self.mode == "L" else x1 * 3)
                end = start + (x2 - x1 if self.mode == "L" else (x2 - x1) * 3)
                cropped.extend(self._pixels[start:end])
            return SimpleImage(x2 - x1, y2 - y1, self.mode, bytes(cropped))

        def getdata(self):
            if self.mode == "L":
                return list(self._pixels)
            if self.mode == "RGB":
                return [(self._pixels[i], self._pixels[i + 1], self._pixels[i + 2]) for i in range(0, len(self._pixels), 3)]
            raise ValueError("unsupported mode")

    if color_type == 0 and bit_depth == 8:
        # Grayscale with filter bytes; strip them.
        stride = width + 1
        pixels = bytearray()
        for row in range(height):
            start = row * stride
            pixels.extend(decompressed[start + 1:start + stride])
        return SimpleImage(width, height, "L", bytes(pixels))
    raise ValueError("unsupported PNG format")


def check_page(page_dir: Path, page_record: dict[str, Any], page_plan: dict[str, Any]) -> dict[str, Any]:
    """Run machine checks on one page of generated panels."""
    findings: list[str] = []
    page_id = page_record.get("page")
    panels_record = page_record.get("panels", [])
    # If generation produced single panels, validate each; if a composite page
    # exists, validate the composite geometry as well.
    composite_path = page_dir / f"{page_id}.png"
    composite_image = None
    if composite_path.is_file():
        composite_image = open_image(composite_path)

    for panel_record in panels_record:
        panel_id = panel_record.get("panel")
        panel_path = page_dir / f"{panel_id}.png"
        if panel_record.get("status") != "OK":
            findings.append(f"{page_id}/{panel_id}: generation status is {panel_record.get('status')}")
            continue
        if not panel_path.is_file():
            findings.append(f"{page_id}/{panel_id}: expected panel file missing")
            continue
        try:
            image = open_image(panel_path)
        except Exception as exc:
            findings.append(f"{page_id}/{panel_id}: cannot decode image: {exc}")
            continue
        width, height = image.size
        if width == 0 or height == 0 or abs(width / height - 16 / 9) > 0.05:
            findings.append(f"{page_id}/{panel_id}: dimensions {width}x{height} are not 16:9")
        if not is_grayscale(image):
            findings.append(f"{page_id}/{panel_id}: image is not grayscale")
        # Text detection placeholder.
        box = (round(width * 0.05), round(height * 0.05), round(width * 0.95), round(height * 0.95))
        if has_internal_text(image, box):
            findings.append(f"{page_id}/{panel_id}: possible internal text detected (flag for review)")

    if composite_image is not None:
        width, height = composite_image.size
        for panel_no in range(1, 10):
            box = expected_panel_box(composite_image, panel_no)
            if box[2] > width or box[3] > height:
                findings.append(f"{page_id}: composite panel {panel_no} box exceeds canvas")

    return {
        "page": page_id,
        "findings": findings,
        "composite_checked": composite_image is not None,
    }


def build_review_checklist(panel_plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate human review checklist from panel plan semantics."""
    checklist: list[dict[str, Any]] = []
    for page in panel_plan.get("pages", []):
        if not isinstance(page, dict):
            continue
        page_id = page.get("page")
        for panel in page.get("panels", []):
            if not isinstance(panel, dict):
                continue
            items: list[str] = []
            if panel.get("must_show"):
                items.append(f"must_show: {', '.join(panel['must_show'])}")
            if panel.get("must_not_show"):
                items.append(f"must_not_show: {', '.join(panel['must_not_show'])}")
            if panel.get("render_delta") == "allowed":
                items.append("render_delta=allowed: cropping/obscuring is permitted")
            checklist.append(
                {
                    "page": page_id,
                    "panel": panel.get("panel"),
                    "display_label": panel.get("display_label"),
                    "camera_rationale": panel.get("camera_rationale"),
                    "checklist": items,
                }
            )
    return checklist


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-plan", required=True, type=Path)
    parser.add_argument("--pages-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        panel_plan = load_json(args.panel_plan)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"CONTRACT_FAIL: {exc}", file=sys.stderr)
        return EXIT_CONTRACT_FAIL

    try:
        attempt_log_path = args.pages_dir / "attempt_log.json"
        if not attempt_log_path.is_file():
            raise ValueError(f"attempt_log.json not found in {args.pages_dir}")
        attempt_log = load_json(attempt_log_path)

        page_results: list[dict[str, Any]] = []
        all_findings: list[str] = []
        for page_record in attempt_log.get("pages", []):
            if not isinstance(page_record, dict):
                continue
            page_id = page_record.get("page")
            page_plan = next(
                (page for page in panel_plan.get("pages", []) if isinstance(page, dict) and page.get("page") == page_id),
                {},
            )
            page_dir = args.pages_dir / str(page_id)
            result = check_page(page_dir, page_record, page_plan)
            page_results.append(result)
            all_findings.extend(result["findings"])

        review_checklist = build_review_checklist(panel_plan)
        status = "REVIEW_REQUIRED" if all_findings else "PASS"
        report = {
            "skill": "su-image9",
            "version": VERSION,
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "pages_dir": str(args.pages_dir),
            "page_results": page_results,
            "machine_findings": all_findings,
            "review_checklist": review_checklist,
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return EXIT_REVIEW_REQUIRED if all_findings else EXIT_PASS
    except Exception as exc:
        print(f"TOOL_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
