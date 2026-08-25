#!/usr/bin/env python3
"""Export director-shot-data/3.1.0 to a production-readable XLSX.

The workbook is a delivery surface only. It does not calculate or alter director
choices. artifact_tool is intentionally the sole spreadsheet writer.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

from storyboard_delivery import load_json, normalize_text, safe_slug

os.environ.setdefault("ARTIFACT_TOOL_RPC_DAEMON_STARTUP_TIMEOUT_S", "120")

try:
    from artifact_tool import SpreadsheetFile, Workbook as ArtifactWorkbook
except Exception as exc:  # pragma: no cover - exercised only in missing-tool environments
    SpreadsheetFile = None  # type: ignore[assignment]
    ArtifactWorkbook = None  # type: ignore[assignment]
    ARTIFACT_TOOL_ERROR: Optional[Exception] = exc
else:
    ARTIFACT_TOOL_ERROR = None

try:
    from openpyxl import Workbook as OpenpyxlWorkbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except Exception as exc:  # pragma: no cover - exercised only in minimal runtimes
    OpenpyxlWorkbook = None  # type: ignore[assignment]
    OPENPYXL_ERROR: Optional[Exception] = exc
else:
    OPENPYXL_ERROR = None


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


def production_risk_rows(data: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    scenes = data.get("scenes") if isinstance(data.get("scenes"), list) else []
    shots = data.get("shots") if isinstance(data.get("shots"), list) else []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        for risk in scene.get("production_risks", []):
            text = normalize_text(risk)
            if text:
                rows.append([str(scene.get("scene_id", "SC???")), text])
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        for risk in shot.get("production_risks", []):
            text = normalize_text(risk)
            if text:
                rows.append([str(shot.get("shot_id", "SH???")), text])
    return rows


def build_workbook(data: dict[str, Any]):
    if ARTIFACT_TOOL_ERROR is not None or ArtifactWorkbook is None:
        raise RuntimeError(f"artifact_tool 不可用：{ARTIFACT_TOOL_ERROR}")

    wb = ArtifactWorkbook.create()
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
        f"contract: director-shot-data/3.1.0  |  project: {data.get('project_id', '')}  |  shots: {len(shots)}"
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

    risk_header_row = assumption_end + 2
    design_sheet.merge_cells(f"A{risk_header_row}:B{risk_header_row}")
    design_sheet.get_range(f"A{risk_header_row}").values = [["制作风险（不进入备注列）"]]
    risk_rows = production_risk_rows(data) or [["—", "无制作风险"]]
    risk_start = risk_header_row + 1
    risk_end = risk_start + len(risk_rows) - 1
    design_sheet.get_range(f"A{risk_start}:B{risk_end}").values = risk_rows

    design_sheet.get_range("A1:B1").format = title_format
    design_sheet.get_range("A3:B3").format = header_format
    design_sheet.get_range(f"A4:B{design_end}").format = body_format
    design_sheet.get_range(f"A{assumption_header_row}:B{assumption_header_row}").format = header_format
    design_sheet.get_range(f"A{assumption_start}:B{assumption_end}").format = body_format
    design_sheet.get_range(f"A{risk_header_row}:B{risk_header_row}").format = header_format
    design_sheet.get_range(f"A{risk_start}:B{risk_end}").format = body_format
    design_sheet.get_range(f"A1:A{risk_end}").format.column_width = 18
    design_sheet.get_range(f"B1:B{risk_end}").format.column_width = 88
    design_sheet.get_range("A1:B1").format.row_height = 30
    design_sheet.get_range(f"A4:B{risk_end}").format.wrap_text = True
    design_sheet.get_range(f"A4:B{risk_end}").format.autofit_rows()
    design_sheet.freeze_panes.freeze_rows(3)

    return wb


def build_openpyxl_workbook(data: dict[str, Any]):
    if OPENPYXL_ERROR is not None or OpenpyxlWorkbook is None:
        raise RuntimeError(f"openpyxl 不可用：{OPENPYXL_ERROR}")

    wb = OpenpyxlWorkbook()
    storyboard = wb.active
    storyboard.title = "导演分镜"
    design_sheet = wb.create_sheet("导演设计")

    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    title = source.get("title") or "未命名场景"
    scenes = data.get("scenes") if isinstance(data.get("scenes"), list) else []
    scene_names = {
        scene.get("scene_id"): scene.get("scene", "")
        for scene in scenes
        if isinstance(scene, dict)
    }
    shots = data.get("shots") if isinstance(data.get("shots"), list) else []

    title_fill = PatternFill("solid", fgColor="111827")
    subtitle_fill = PatternFill("solid", fgColor="E5E7EB")
    header_fill = PatternFill("solid", fgColor="374151")
    cjk_font = "Hiragino Sans GB"
    title_font = Font(name=cjk_font, bold=True, color="FFFFFF", size=16)
    header_font = Font(name=cjk_font, bold=True, color="FFFFFF")
    body_font = Font(name=cjk_font, size=10, color="111827")
    body_alignment = Alignment(vertical="top", wrap_text=True)
    center_alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)

    storyboard.merge_cells("A1:F1")
    storyboard["A1"] = f"{title}｜导演分镜"
    storyboard["A1"].fill = title_fill
    storyboard["A1"].font = title_font
    storyboard["A1"].alignment = Alignment(horizontal="left", vertical="center")

    storyboard.merge_cells("A2:F2")
    storyboard["A2"] = (
        f"contract: director-shot-data/3.1.0  |  project: {data.get('project_id', '')}"
        f"  |  shots: {len(shots)}"
    )
    storyboard["A2"].fill = subtitle_fill
    storyboard["A2"].font = body_font
    storyboard["A2"].alignment = Alignment(horizontal="left", vertical="center")

    headers = ["镜号", "场景", "原剧本段落", "镜头时长", "运镜＋主画面描述", "备注"]
    for column, value in enumerate(headers, start=1):
        cell = storyboard.cell(row=4, column=column, value=value)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_alignment

    rows: list[list[Any]] = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        row = [
            shot.get("shot_id", ""),
            scene_names.get(shot.get("scene_id"), shot.get("scene_id", "")),
            shot.get("source_excerpt", ""),
            shot.get("duration_seconds", ""),
            shot.get("execution_text", ""),
            shot.get("notes", ""),
        ]
        rows.append(row)
        storyboard.append(row)

    if not rows:
        storyboard.append(["", "", "", "", "", ""])

    for row_number in range(5, storyboard.max_row + 1):
        for column in range(1, 7):
            storyboard.cell(row=row_number, column=column).alignment = body_alignment
            storyboard.cell(row=row_number, column=column).font = body_font
        storyboard.cell(row=row_number, column=1).alignment = center_alignment
        storyboard.cell(row=row_number, column=4).alignment = center_alignment
        storyboard.cell(row=row_number, column=4).number_format = '0.0"秒"'
        source_row = rows[row_number - 5] if row_number - 5 < len(rows) else [""] * 6
        storyboard.row_dimensions[row_number].height = bounded_row_height(source_row)

    widths = [9, 18, 34, 11, 64, 22]
    for index, width in enumerate(widths, start=1):
        storyboard.column_dimensions[get_column_letter(index)].width = width
    storyboard.row_dimensions[1].height = 30
    storyboard.row_dimensions[2].height = 22
    storyboard.row_dimensions[4].height = 26
    storyboard.freeze_panes = "A5"
    storyboard.auto_filter.ref = f"A4:F{storyboard.max_row}"
    storyboard.sheet_view.showGridLines = False
    storyboard.sheet_properties.pageSetUpPr.fitToPage = True
    storyboard.page_setup.orientation = "landscape"
    storyboard.page_setup.paperSize = storyboard.PAPERSIZE_A4
    storyboard.page_setup.fitToWidth = 1
    storyboard.page_setup.fitToHeight = 0
    storyboard.print_title_rows = "1:4"
    storyboard.print_area = f"A1:F{storyboard.max_row}"
    storyboard.page_margins.left = 0.2
    storyboard.page_margins.right = 0.2
    storyboard.page_margins.top = 0.3
    storyboard.page_margins.bottom = 0.3

    design_sheet.merge_cells("A1:B1")
    design_sheet["A1"] = f"{title}｜导演设计摘要"
    design_sheet["A1"].fill = title_fill
    design_sheet["A1"].font = title_font
    design_sheet["A1"].alignment = Alignment(horizontal="left", vertical="center")
    design_sheet["A3"] = "维度"
    design_sheet["B3"] = "导演设计"
    for cell in design_sheet[3]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_alignment

    design = data.get("director_design") if isinstance(data.get("director_design"), dict) else {}
    for label, key in DESIGN_LABELS:
        design_sheet.append([label, design.get(key, "")])

    assumptions = data.get("assumptions") if isinstance(data.get("assumptions"), list) else []
    assumption_header_row = design_sheet.max_row + 2
    design_sheet.merge_cells(
        start_row=assumption_header_row,
        start_column=1,
        end_row=assumption_header_row,
        end_column=2,
    )
    design_sheet.cell(row=assumption_header_row, column=1, value="假设与待确认项")
    header_cell = design_sheet.cell(row=assumption_header_row, column=1)
    header_cell.fill = header_fill
    header_cell.font = header_font
    header_cell.alignment = center_alignment

    if assumptions:
        for item in assumptions:
            if not isinstance(item, dict):
                continue
            design_sheet.append(
                [
                    f"{item.get('assumption_id', 'A???')} · {item.get('status', 'open')}",
                    f"{item.get('statement', '')}\n影响：{item.get('impact', '')}",
                ]
            )
    else:
        design_sheet.append(["—", "无开放假设"])

    risk_header_row = design_sheet.max_row + 2
    design_sheet.merge_cells(
        start_row=risk_header_row,
        start_column=1,
        end_row=risk_header_row,
        end_column=2,
    )
    design_sheet.cell(
        row=risk_header_row,
        column=1,
        value="制作风险（不进入备注列）",
    )
    risk_header = design_sheet.cell(row=risk_header_row, column=1)
    risk_header.fill = header_fill
    risk_header.font = header_font
    risk_header.alignment = center_alignment
    for risk_row in production_risk_rows(data) or [["—", "无制作风险"]]:
        design_sheet.append(risk_row)

    for row in design_sheet.iter_rows(min_row=4, max_row=design_sheet.max_row, min_col=1, max_col=2):
        for cell in row:
            if cell.row in {assumption_header_row, risk_header_row}:
                continue
            cell.alignment = body_alignment
            cell.font = body_font
    design_sheet.column_dimensions["A"].width = 18
    design_sheet.column_dimensions["B"].width = 88
    design_sheet.row_dimensions[1].height = 30
    design_sheet.freeze_panes = "A4"
    design_sheet.sheet_view.showGridLines = False
    design_sheet.sheet_properties.pageSetUpPr.fitToPage = True
    design_sheet.page_setup.orientation = "portrait"
    design_sheet.page_setup.paperSize = design_sheet.PAPERSIZE_A4
    design_sheet.page_setup.fitToWidth = 1
    design_sheet.page_setup.fitToHeight = 0
    design_sheet.print_title_rows = "1:3"
    design_sheet.print_area = f"A1:B{design_sheet.max_row}"
    design_sheet.page_margins.left = 0.3
    design_sheet.page_margins.right = 0.3

    if wb.sheetnames != ["导演分镜", "导演设计"]:
        raise RuntimeError(f"正式 XLSX 工作表漂移：{wb.sheetnames}")
    return wb


def export_xlsx(data: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    if SpreadsheetFile is not None and ARTIFACT_TOOL_ERROR is None:
        wb = build_workbook(data)
        SpreadsheetFile.export_xlsx(wb).save(str(output))
    elif OpenpyxlWorkbook is not None and OPENPYXL_ERROR is None:
        wb = build_openpyxl_workbook(data)
        wb.save(output)
    else:
        raise RuntimeError(
            f"artifact_tool 与 openpyxl 均不可用：artifact_tool={ARTIFACT_TOOL_ERROR}; "
            f"openpyxl={OPENPYXL_ERROR}"
        )
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将 director-shot-data/3.1.0 导出为 XLSX。")
    parser.add_argument("--input", type=Path, required=True, help="输入 JSON 文件。")
    parser.add_argument("--output", type=Path, help="输出 XLSX；省略时按 delivery_slug 命名。")
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if ARTIFACT_TOOL_ERROR is not None and OPENPYXL_ERROR is not None:
        sys.stderr.write(
            "WARN: artifact_tool 与 openpyxl 当前均不可用，XLSX 未生成；"
            "JSON 与 Markdown 交付不受影响。\n"
            f"artifact_tool: {ARTIFACT_TOOL_ERROR}\nopenpyxl: {OPENPYXL_ERROR}\n"
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
