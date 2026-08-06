#!/usr/bin/env python3
"""Add external Chinese headers and panel labels to text-free 3x3 pages.

v2.1.2 supports two input modes:
- Legacy: --pages points to full-page 3x3 PNGs (detected or canonical grid).
- Per-panel: --pages points to a directory containing PAGE-XX/PANEL-N.png files
  produced by generate_panels.py; the script deterministically composites them
  into a strict 3x3 grid before adding external labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


VERSION = "2.1.2"
SCHEMA_VERSION = "2.1"
HEADER_HEIGHT = 72
LABEL_HEIGHT = 48
FONT_SIZE = 24
WINDOWS_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/msyhbd.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("C:/Windows/Fonts/simsun.ttc"),
)


@dataclass(frozen=True)
class PanelSpec:
    panel_no: int
    display_label: str
    source_shot: int | None


@dataclass(frozen=True)
class PageSpec:
    page_no: int
    source: str
    header: str
    panels: tuple[PanelSpec, ...]


class ToolError(RuntimeError):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Annotate su-image9 pages outside the original image pixels.")
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--page-map", required=True, type=Path)
    parser.add_argument("--pages", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--font-path", type=Path)
    parser.add_argument("--mode", choices=("auto", "per-panel"), default="auto")
    return parser.parse_args(argv)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} root must be an object")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_page_map_contract(page_map: dict[str, Any], data_path: Path) -> None:
    expected_keys = {
        "skill",
        "version",
        "schema_version",
        "source_file_sha256",
        "pages",
        "release_ready",
    }
    if set(page_map) != expected_keys:
        raise ValueError("page-map top-level fields do not match the su-image9 2.1.2 contract")
    if page_map.get("skill") != "su-image9" or page_map.get("version") != VERSION:
        raise ValueError("page-map is legacy or belongs to another skill; regenerate from shot_data")
    if page_map.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("page-map.schema_version must be 2.1")
    if page_map.get("release_ready") is not True:
        raise ValueError("page-map.release_ready must be true before annotation")
    expected_hash = page_map.get("source_file_sha256")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise ValueError("page-map.source_file_sha256 must be a lowercase SHA-256")
    actual_hash = sha256_file(data_path)
    if expected_hash != actual_hash:
        raise ValueError("page-map source hash does not match the current shot_data")


def font_glyph_signature(font: ImageFont.FreeTypeFont, char: str) -> tuple[tuple[int, int], bytes]:
    mask = font.getmask(char, mode="L")
    return mask.size, bytes(mask)


def font_supports_chinese(font: ImageFont.FreeTypeFont) -> bool:
    signatures = [font_glyph_signature(font, char) for char in "中文镜号"]
    if any(not pixels for _, pixels in signatures):
        return False
    return len(set(signatures)) >= 3


def select_font(font_path: Path | None) -> tuple[ImageFont.FreeTypeFont, Path]:
    candidates = [font_path] if font_path is not None else []
    candidates.extend(WINDOWS_FONT_CANDIDATES)
    errors: list[str] = []
    for candidate in candidates:
        if candidate is None or not candidate.is_file():
            continue
        try:
            font = ImageFont.truetype(str(candidate), FONT_SIZE)
        except OSError as exc:
            errors.append(f"{candidate}: {exc}")
            continue
        if font_supports_chinese(font):
            return font, candidate.resolve()
        errors.append(f"{candidate}: Chinese glyph verification failed")
    detail = "; ".join(errors) if errors else "no candidate font exists"
    raise ToolError(f"No reliable Chinese font is available: {detail}")


def parse_page_no(item: dict[str, Any]) -> int:
    raw = item.get("page_no")
    if raw is None:
        match = re.fullmatch(r"PAGE-(\d{2})", str(item.get("page", "")))
        raw = int(match.group(1)) if match else None
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise ValueError("page number must be a positive integer")
    return raw


def parse_panel_no(item: dict[str, Any]) -> int:
    raw = item.get("panel_no")
    if raw is None:
        match = re.fullmatch(r"PANEL-([1-9])", str(item.get("panel", "")))
        raw = int(match.group(1)) if match else None
    if isinstance(raw, bool) or not isinstance(raw, int) or raw not in range(1, 10):
        raise ValueError("panel number must be an integer from 1 to 9")
    return raw


def load_page_specs(page_map: dict[str, Any]) -> list[PageSpec]:
    pages = page_map.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("page-map.pages must be a non-empty array")
    result: list[PageSpec] = []
    source_names: set[str] = set()
    for raw_page in pages:
        if not isinstance(raw_page, dict):
            raise ValueError("each page-map page must be an object")
        page_no = parse_page_no(raw_page)
        raw_panels = raw_page.get("panels")
        if not isinstance(raw_panels, list):
            raise ValueError(f"PAGE-{page_no:02d} panels must be an array")
        panels: list[PanelSpec] = []
        for raw_panel in raw_panels:
            if not isinstance(raw_panel, dict):
                raise ValueError("each page-map panel must be an object")
            panel_no = parse_panel_no(raw_panel)
            label = raw_panel.get("display_label")
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"PAGE-{page_no:02d}/PANEL-{panel_no} display_label is required")
            source_shot = raw_panel.get("source_shot")
            if source_shot is not None and (isinstance(source_shot, bool) or not isinstance(source_shot, int) or source_shot <= 0):
                raise ValueError(f"PAGE-{page_no:02d}/PANEL-{panel_no} source_shot must be a positive integer")
            panels.append(PanelSpec(panel_no, label.strip(), source_shot))
        if [panel.panel_no for panel in panels] != list(range(1, 10)):
            raise ValueError(f"PAGE-{page_no:02d} must contain ordered PANEL-1 through PANEL-9")
        source = raw_page.get("source", f"PAGE-{page_no:02d}.png")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"PAGE-{page_no:02d} source is required")
        source_name = Path(source.strip()).name
        if Path(source_name).suffix.lower() != ".png":
            raise ValueError(f"PAGE-{page_no:02d} source must be a PNG file")
        source_key = source_name.casefold()
        if source_key in source_names:
            raise ValueError(f"annotated output filename is duplicated: {source_name}")
        source_names.add(source_key)
        header = raw_page.get("header", f"PAGE-{page_no:02d}")
        if not isinstance(header, str) or not header.strip():
            raise ValueError(f"PAGE-{page_no:02d} header must be non-empty")
        result.append(PageSpec(page_no, source.strip(), header.strip(), tuple(panels)))
    if [page.page_no for page in result] != list(range(1, len(result) + 1)):
        raise ValueError("page-map page numbers must be continuous from 1")
    return result


def validate_shot_links(data: dict[str, Any], pages: list[PageSpec]) -> None:
    shots = data.get("shots")
    if not isinstance(shots, list):
        raise ValueError("shot_data.shots must be an array")
    known = {shot.get("shot_no") for shot in shots if isinstance(shot, dict)}
    for page in pages:
        for panel in page.panels:
            if panel.source_shot is not None and panel.source_shot not in known:
                raise ValueError(f"PAGE-{page.page_no:02d}/PANEL-{panel.panel_no} references missing shot {panel.source_shot}")


def cluster_positions(values: list[int]) -> list[int]:
    if not values:
        return []
    clusters: list[list[int]] = [[values[0]]]
    for value in values[1:]:
        if value <= clusters[-1][-1] + 2:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [round(sum(cluster) / len(cluster)) for cluster in clusters]


def dark_line_positions(image: Image.Image, axis: str) -> list[int]:
    gray = image.convert("L")
    width, height = gray.size
    pixels = gray.load()
    values: list[int] = []
    if axis == "x":
        for x in range(width):
            if sum(pixels[x, y] < 72 for y in range(height)) / height >= 0.12:
                values.append(x)
    else:
        for y in range(height):
            if sum(pixels[x, y] < 72 for x in range(width)) / width >= 0.12:
                values.append(y)
    return cluster_positions(values)


def select_six_lines(lines: list[int], min_gap: int) -> list[int]:
    filtered: list[int] = []
    for line in lines:
        if not filtered or line - filtered[-1] >= min_gap:
            filtered.append(line)
    if len(filtered) < 6:
        return []
    candidates = [filtered[index:index + 6] for index in range(len(filtered) - 5)]
    return max(candidates, key=lambda item: item[-1] - item[0])


def detect_grid_boxes(image: Image.Image) -> dict[int, tuple[int, int, int, int]] | None:
    width, height = image.size
    xs = select_six_lines(dark_line_positions(image, "x"), max(4, round(width * 0.006)))
    ys = select_six_lines(dark_line_positions(image, "y"), max(4, round(height * 0.006)))
    if len(xs) != 6 or len(ys) != 6:
        return None
    boxes: dict[int, tuple[int, int, int, int]] = {}
    panel_no = 1
    for row in range(3):
        for column in range(3):
            left, right = xs[column * 2], xs[column * 2 + 1]
            top, bottom = ys[row * 2], ys[row * 2 + 1]
            if right <= left or bottom <= top:
                return None
            boxes[panel_no] = (left, top, right, bottom)
            panel_no += 1
    return boxes


def canonical_boxes(width: int, height: int) -> dict[int, tuple[int, int, int, int]]:
    margin_x = round(width * 0.045)
    margin_y = round(height * 0.06)
    gutter_x = round(width * 0.022)
    gutter_y = round(height * 0.03)
    panel_width = (width - margin_x * 2 - gutter_x * 2) // 3
    panel_height = round(panel_width * 9 / 16)
    boxes: dict[int, tuple[int, int, int, int]] = {}
    panel_no = 1
    for row in range(3):
        for column in range(3):
            left = margin_x + column * (panel_width + gutter_x)
            top = margin_y + row * (panel_height + gutter_y)
            boxes[panel_no] = (left, top, left + panel_width, top + panel_height)
            panel_no += 1
    return boxes


def composite_page(
    page_dir: Path,
    page: PageSpec,
    target_width: int = 1920,
    target_height: int = 1080,
) -> Image.Image:
    """Composite nine individual panel PNGs into a strict 3x3 grid."""
    canvas = Image.new("RGB", (target_width, target_height), "white")
    boxes = canonical_boxes(target_width, target_height)
    for panel in page.panels:
        panel_path = page_dir / f"PANEL-{panel.panel_no}.png"
        if not panel_path.is_file():
            raise ValueError(f"per-panel source missing: {panel_path}")
        with Image.open(panel_path) as opened:
            panel_image = opened.convert("RGB")
        box = boxes[panel.panel_no]
        panel_width = box[2] - box[0]
        panel_height = box[3] - box[1]
        resized = panel_image.resize((panel_width, panel_height), Image.Resampling.LANCZOS)
        canvas.paste(resized, (box[0], box[1]))
    return canvas


def centered_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, box: tuple[int, int, int, int]) -> tuple[float, float]:
    text_box = draw.textbbox((0, 0), text, font=font)
    width = text_box[2] - text_box[0]
    height = text_box[3] - text_box[1]
    return box[0] + (box[2] - box[0] - width) / 2, box[1] + (box[3] - box[1] - height) / 2


def render_page(
    page: PageSpec,
    source_path: Path,
    output_path: Path,
    font: ImageFont.FreeTypeFont,
    mode: str,
) -> dict[str, Any]:
    if mode == "per-panel":
        source = composite_page(source_path.parent, page, target_width=1920, target_height=1080)
        box_detection = "per_panel_composite"
        warnings: list[str] = []
    else:
        with Image.open(source_path) as opened:
            source = opened.convert("RGB")
        width, height = source.size
        detected = detect_grid_boxes(source)
        warnings = []
        if detected is None:
            boxes = canonical_boxes(width, height)
            box_detection = "canonical_fallback"
            warnings.append("actual_grid_detection_failed; canonical_boxes_used")
        else:
            boxes = detected
            box_detection = "detected_image_grid"

    width, height = source.size
    canvas_height = HEADER_HEIGHT + height + LABEL_HEIGHT * 3
    canvas = Image.new("RGB", (width, canvas_height), "white")
    canvas.paste(source, (0, HEADER_HEIGHT))
    draw = ImageDraw.Draw(canvas)
    header_box = (20, 0, width - 20, HEADER_HEIGHT)
    draw.text(centered_text(draw, page.header, font, header_box), page.header, fill="#111111", font=font)
    for panel in page.panels:
        row = (panel.panel_no - 1) // 3
        if mode == "per-panel":
            boxes_local = canonical_boxes(width, height)
            left, _, right, _ = boxes_local[panel.panel_no]
        else:
            left, _, right, _ = boxes[panel.panel_no]
        top = HEADER_HEIGHT + height + row * LABEL_HEIGHT
        label_box = (left, top, right, top + LABEL_HEIGHT)
        draw.text(centered_text(draw, panel.display_label, font, label_box), panel.display_label, fill="#111111", font=font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG")
    return {
        "page_no": page.page_no,
        "source": str(source_path),
        "output": str(output_path),
        "source_sha256": sha256_file(source_path),
        "source_size": [width, height],
        "source_pixel_region": [0, HEADER_HEIGHT, width, HEADER_HEIGHT + height],
        "box_detection": box_detection,
        "warnings": warnings,
        "panel_labels": {str(panel.panel_no): panel.display_label for panel in page.panels},
    }


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output.resolve()
    manifest_path = output_dir / "annotation_manifest.json"
    if output_dir.exists():
        print("annotation failed: --output must be absent", file=sys.stderr)
        return 2
    try:
        data_path = args.data.resolve()
        data = load_json(data_path)
        page_map = load_json(args.page_map.resolve())
        validate_page_map_contract(page_map, data_path)
        page_specs = load_page_specs(page_map)
        validate_shot_links(data, page_specs)
        font, selected_font = select_font(args.font_path.resolve() if args.font_path else None)
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f".{output_dir.name}-annotation-",
            dir=output_dir.parent,
        ) as temp_name:
            staging_dir = Path(temp_name) / "output"
            staging_dir.mkdir()
            pages: list[dict[str, Any]] = []
            for page in page_specs:
                source_path = Path(page.source)
                if not source_path.is_absolute():
                    source_path = args.pages.resolve() / source_path
                if args.mode == "per-panel":
                    # source_path is the page directory containing PANEL-N.png
                    if not source_path.is_dir():
                        raise ValueError(f"per-panel source directory is missing: {source_path}")
                else:
                    if not source_path.is_file():
                        raise ValueError(f"source page is missing: {source_path}")
                record = render_page(page, source_path, staging_dir / Path(page.source).name, font, args.mode)
                record["output"] = str(output_dir / Path(page.source).name)
                pages.append(record)
            manifest = {
                "skill": "su-image9",
                "version": VERSION,
                "status": "PASS",
                "code": 0,
                "source_file_sha256": page_map["source_file_sha256"],
                "font_path": str(selected_font),
                "pages": pages,
            }
            write_manifest(staging_dir / "annotation_manifest.json", manifest)
            staging_dir.rename(output_dir)
        return 0
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        try:
            write_manifest(
                manifest_path,
                {"skill": "su-image9", "version": VERSION, "status": "CONTRACT_FAIL", "code": 2, "error": str(exc), "pages": []},
            )
        except OSError as write_exc:
            print(f"annotation tool error: cannot write failure manifest: {write_exc}", file=sys.stderr)
            return 3
        print(f"annotation failed: {exc}", file=sys.stderr)
        return 2
    except (OSError, ToolError) as exc:
        try:
            write_manifest(
                manifest_path,
                {"skill": "su-image9", "version": VERSION, "status": "TOOL_ERROR", "code": 3, "error": str(exc), "pages": []},
            )
        except OSError:
            pass
        print(f"annotation tool error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
