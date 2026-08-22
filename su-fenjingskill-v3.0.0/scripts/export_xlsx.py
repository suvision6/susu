#!/usr/bin/env python3
"""Export director-shot-data/3.0.0 to a production-readable XLSX.

The workbook is a delivery surface only. It does not calculate or alter director
choices. artifact_tool is intentionally the sole spreadsheet writer.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path
from typing import Any, Iterable

from storyboard_delivery import load_json, normalize_text, safe_slug

os.environ.setdefault("ARTIFACT_TOOL_RPC_DAEMON_STARTUP_TIMEOUT_S", "120")

try:
    from artifact_tool import SpreadsheetFile, Workbook
except Exception as exc:  # pragma: no cover - exercised only in missing-tool environments
    SpreadsheetFile = None  # type: ignore[assignment]
    Workbook = None  # type: ignore[assignment]
    ARTIFACT_TOOL_ERROR: Exception | None = exc
else:
    ARTIFACT_TOOL_ERROR = None


DESIGN_LABELS = (
    ("场景任务", "scene_purpose"),
    ("戏剧问题", "dramatic_question"),
    ("转折点", "turning_point"),
    ("观众位置", "audience_position"),
    ("视点策略", "pov_strategy"),
    ("情绪弧线", "emotional_arc"),
    ("人物调度", "blocking_strategy"),
    ("摄影策略", "visual_strategy"),
    ("声音策略", "sound_strategy"),
    ("节奏策略", "rhythm_strategy"),
)


def bounded_row_height(row: list[Any]) -> float:
    """Estimate readable wrapped height while avoiding unbounded Excel rows."""
    widths = (8, 18, 38, 10, 70, 24)
    line_counts: list[int] = []
    for value, width in zip(row, widths):
        text = normalize_text(value)
        logical_lines = text.split("\n") if text else [""]
        lines = sum(max(1, math.ceil(len(line) / max(width, 1))) for line in logical_lines)
        line_counts.append(lines)
    return float(min(180, max(28, 16 * max(line_counts) + 8)))


def build_workbook(data: dict[str, Any]):
    if ARTIFACT_TOOL_ERROR is not None or Workbook is None:
        raise RuntimeError(f"artifact_tool 不可用：{ARTIFACT_TOOL_ERROR}")

    wb = Workbook.create()
    storyboard = wb.worksheets.add("导演分镜")
    design_sheet = wb.worksheets.add("导演设计")

    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    title = source.get("title") or "未命名场景"
    scenes = data.get("scenes") if isinstance(data.get("scenes"), list) else []
    scene_names = {
        scene.get("scene_id"): scene.get("scene", "")
        for scene in scenes
        if isinstance(scene, dict)
    }
    shots = data.get("shots") if isinstance(data.get("shots"), list) else []

    storyboard.merge_cells("A1:F1")
    storyboard.get_range("A1").values = [[f"{title}｜导演分镜"]]
    storyboard.merge_cells("A2:F2")
    storyboard.get_range("A2").values = [[
        f"contract: director-shot-data/3.0.0  |  project: {data.get('project_id', '')}  |  shots: {len(shots)}"
    ]]

    headers = [["镜号", "场景", "原剧本段落", "镜头时长", "运镜＋主画面描述", "备注"]]
    storyboard.get_range("A4:F4").values = headers

    rows: list[list[Any]] = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        rows.append(
            [
                shot.get("shot_id", ""),
                scene_names.get(shot.get("scene_id"), shot.get("scene_id", "")),
                shot.get("source_excerpt", ""),
                shot.get("duration_seconds", ""),
                shot.get("execution_text", ""),
                shot.get("notes", ""),
            ]
        )

    if rows:
        end_row = 4 + len(rows)
        storyboard.get_range(f"A5:F{end_row}").values = rows
    else:
        end_row = 5
        storyboard.get_range("A5:F5").values = [["", "", "", "", "", ""]]

    title_format = {
        "fill": "#111827",
        "font": {"bold": True, "color": "#FFFFFF", "size": 16},
        "horizontal_alignment": "left",
        "vertical_alignment": "center",
    }
    subtitle_format = {
        "fill": "#E5E7EB",
        "font": {"color": "#374151", "size": 10},
        "horizontal_alignment": "left",
        "vertical_alignment": "center",
    }
    header_format = {
        "fill": "#374151",
        "font": {"bold": True, "color": "#FFFFFF"},
        "horizontal_alignment": "center",
        "vertical_alignment": "center",
        "wrap_text": True,
    }
    body_format = {
        "font": {"color": "#111827", "size": 10},
        "vertical_alignment": "top",
        "wrap_text": True,
    }

    storyboard.get_range("A1:F1").format = title_format
    storyboard.get_range("A2:F2").format = subtitle_format
    storyboard.get_range("A4:F4").format = header_format
    storyboard.get_range(f"A5:F{end_row}").format = body_format
    storyboard.get_range(f"A5:A{end_row}").format.horizontal_alignment = "center"
    storyboard.get_range(f"D5:D{end_row}").format.horizontal_alignment = "center"
    storyboard.get_range(f"D5:D{end_row}").format.number_format = '0.0"秒"'

    column_widths = {
        "A": 10,
        "B": 22,
        "C": 42,
        "D": 12,
        "E": 78,
        "F": 28,
    }
    for column, width in column_widths.items():
        storyboard.get_range(f"{column}1:{column}{end_row}").format.column_width = width

    storyboard.get_range("A1:F1").format.row_height = 30
    storyboard.get_range("A2:F2").format.row_height = 22
    storyboard.get_range("A4:F4").format.row_height = 26
    for row_number, row in enumerate(rows, start=5):
        storyboard.get_range(f"A{row_number}:F{row_number}").format.row_height = bounded_row_height(row)

    storyboard.freeze_panes.freeze_rows(4)
    storyboard.freeze_panes.freeze_columns(1)

    design_sheet.merge_cells("A1:B1")
    design_sheet.get_range("A1").values = [[f"{title}｜导演设计摘要"]]
    design_sheet.get_range("A3:B3").values = [["维度", "导演设计"]]
    design = data.get("director_design") if isinstance(data.get("director_design"), dict) else {}
    design_rows = [[label, design.get(key, "")] for label, key in DESIGN_LABELS]
    design_end = 3 + len(design_rows)
    design_sheet.get_range(f"A4:B{design_end}").values = design_rows

    assumptions = data.get("assumptions") if isinstance(data.get("assumptions"), list) else []
    assumption_header_row = design_end + 2
    design_sheet.merge_cells(f"A{assumption_header_row}:B{assumption_header_row}")
    design_sheet.get_range(f"A{assumption_header_row}").values = [["假设与待确认项"]]
    if assumptions:
        assumption_rows = [
            [
                f"{item.get('assumption_id', 'A???')} · {item.get('status', 'open')}",
                f"{item.get('statement', '')}\n影响：{item.get('impact', '')}",
            ]
            for item in assumptions
            if isinstance(item, dict)
        ]
    else:
        assumption_rows = [["—", "无开放假设"]]
    assumption_start = assumption_header_row + 1
    assumption_end = assumption_start + len(assumption_rows) - 1
    design_sheet.get_range(f"A{assumption_start}:B{assumption_end}").values = assumption_rows

    design_sheet.get_range("A1:B1").format = title_format
    design_sheet.get_range("A3:B3").format = header_format
    design_sheet.get_range(f"A4:B{design_end}").format = body_format
    design_sheet.get_range(f"A{assumption_header_row}:B{assumption_header_row}").format = header_format
    design_sheet.get_range(f"A{assumption_start}:B{assumption_end}").format = body_format
    design_sheet.get_range(f"A1:A{assumption_end}").format.column_width = 18
    design_sheet.get_range(f"B1:B{assumption_end}").format.column_width = 88
    design_sheet.get_range("A1:B1").format.row_height = 30
    design_sheet.get_range(f"A4:B{assumption_end}").format.wrap_text = True
    design_sheet.get_range(f"A4:B{assumption_end}").format.autofit_rows()
    design_sheet.freeze_panes.freeze_rows(3)

    return wb


def export_xlsx(data: dict[str, Any], output: Path) -> Path:
    if SpreadsheetFile is None:
        raise RuntimeError(f"artifact_tool 不可用：{ARTIFACT_TOOL_ERROR}")
    wb = build_workbook(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    SpreadsheetFile.export_xlsx(wb).save(str(output))
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将 director-shot-data/3.0.0 导出为 XLSX。")
    parser.add_argument("--input", type=Path, required=True, help="输入 JSON 文件。")
    parser.add_argument("--output", type=Path, help="输出 XLSX；省略时按 delivery_slug 命名。")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if ARTIFACT_TOOL_ERROR is not None:
        sys.stderr.write(
            "WARN: artifact_tool 当前不可用，XLSX 未生成；JSON 与 Markdown 交付不受影响。\n"
            f"detail: {ARTIFACT_TOOL_ERROR}\n"
        )
        return 2
    try:
        data = load_json(args.input)
        output = args.output or Path(f"{safe_slug(data)}-storyboard.xlsx")
        export_xlsx(data, output)
    except Exception as exc:
        sys.stderr.write(f"WARN: XLSX 导出失败，其他交付仍可使用。\ndetail: {exc}\n")
        return 2
    sys.stdout.write(f"xlsx: {output}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
