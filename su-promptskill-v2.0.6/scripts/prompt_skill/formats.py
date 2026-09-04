"""su-promptskill internal module: Markdown, XLSX and package validation."""

from __future__ import annotations

from . import plan_validation as _previous

globals().update({
    key: value
    for key, value in vars(_previous).items()
    if not key.startswith("__")
})

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Responsibility module behind scripts/prompt_delivery.py."

def stable_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def prompt_table_rows(plan: Mapping[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for unit in plan.get("prompt_units", []):
        if not isinstance(unit, dict):
            continue
        duration = unit.get("total_duration_seconds")
        if duration is None:
            duration_text = ""
        elif isinstance(duration, (int, float)) and not isinstance(
            duration, bool
        ):
            duration_text = json.dumps(duration, allow_nan=False)
        else:
            duration_text = str(duration)
        source_ids = unit.get("source_shot_ids", [])
        rows.append(
            [
                str(unit.get("prompt_unit_id", "")),
                "、".join(str(item) for item in source_ids),
                duration_text,
                str(unit.get("prompt_text", "")),
            ]
        )
    return rows


def prompt_table_xlsx_rows(plan: Mapping[str, Any]) -> list[list[str]]:
    return prompt_table_rows(plan)


def reconstruct_prompt_texts_from_xlsx_rows(
    rows: Sequence[Sequence[str]],
) -> dict[str, str]:
    blocks_by_unit: dict[str, list[str]] = {}
    order: list[str] = []
    for row in rows:
        if len(row) != len(PROMPT_TABLE_COLUMNS):
            raise DeliveryError("Prompt table row does not have four cells")
        unit_id = str(row[0])
        if not unit_id:
            raise DeliveryError("XLSX physical row is missing Prompt 段号")
        if unit_id not in blocks_by_unit:
            blocks_by_unit[unit_id] = []
            order.append(unit_id)
        blocks_by_unit[unit_id].append(str(row[3]))
    return {
        unit_id: "\n\n".join(blocks_by_unit[unit_id])
        for unit_id in order
    }


def _markdown_cell(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    escaped = html.escape(normalized, quote=False).replace("|", "&#124;")
    return escaped.replace("\n", "<br>")


def prompt_table_markdown_bytes(rows: Sequence[Sequence[str]]) -> bytes:
    lines = [
        "| " + " | ".join(PROMPT_TABLE_COLUMNS) + " |",
        "| " + " | ".join("---" for _ in PROMPT_TABLE_COLUMNS) + " |",
    ]
    for row in rows:
        if len(row) != len(PROMPT_TABLE_COLUMNS):
            raise DeliveryError("Prompt table row does not have four cells")
        lines.append("| " + " | ".join(_markdown_cell(str(cell)) for cell in row) + " |")
    return ("\n".join(lines) + "\n").encode("utf-8")


def parse_prompt_table_markdown(payload: bytes) -> list[list[str]]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise DeliveryError(f"prompt_table.md is not UTF-8: {exc}") from exc
    if len(lines) < 2:
        raise DeliveryError("prompt_table.md is missing its header")

    def parse_line(line: str) -> list[str]:
        if not line.startswith("|") or not line.endswith("|"):
            raise DeliveryError("prompt_table.md row is not a pipe table row")
        cells = [cell.strip() for cell in line[1:-1].split("|")]
        return [
            html.unescape(cell.replace("<br>", "\n"))
            for cell in cells
        ]

    if tuple(parse_line(lines[0])) != PROMPT_TABLE_COLUMNS:
        raise DeliveryError("prompt_table.md columns do not match the contract")
    separator = parse_line(lines[1])
    if len(separator) != len(PROMPT_TABLE_COLUMNS) or any(
        cell != "---" for cell in separator
    ):
        raise DeliveryError("prompt_table.md separator is invalid")
    rows = [parse_line(line) for line in lines[2:]]
    if any(len(row) != len(PROMPT_TABLE_COLUMNS) for row in rows):
        raise DeliveryError("prompt_table.md has a non-four-cell row")
    return rows


def _xlsx_cell_reference(column_index: int, row_index: int) -> str:
    value = column_index
    letters = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row_index}"


def _xlsx_inline_cell(
    reference: str, value: str, style_index: int
) -> str:
    escaped = html.escape(value, quote=False)
    return (
        f'<c r="{reference}" t="inlineStr" s="{style_index}">'
        f'<is><t xml:space="preserve">{escaped}</t></is></c>'
    )


def _xlsx_prompt_column_width(rows: Sequence[Sequence[str]]) -> int:
    longest = max(
        (_weighted_text_length(str(row[3])) for row in rows if len(row) == 4),
        default=0.0,
    )
    return max(
        XLSX_PROMPT_WIDTH_MIN,
        min(XLSX_PROMPT_WIDTH_MAX, math.ceil(math.sqrt(longest) * 7)),
    )


def _xlsx_row_height_for_row(
    row: Sequence[str], prompt_width: int
) -> int:
    leading_height = max(
        _estimated_row_height(str(value), width)
        for value, width in zip(row[:3], (14, 24, 16))
    )
    prompt_height = _estimated_row_height(str(row[3]), prompt_width)
    height = max(leading_height, prompt_height)
    return int(min(XLSX_ROW_HEIGHT_LIMIT, max(24, height)))


def prompt_table_xlsx_bytes(rows: Sequence[Sequence[str]]) -> bytes:
    worksheet_rows: list[str] = []
    prompt_width = _xlsx_prompt_column_width(rows)
    all_rows = [list(PROMPT_TABLE_COLUMNS)] + [
        [str(cell) for cell in row] for row in rows
    ]
    previous_unit = ""
    for row_index, row in enumerate(all_rows, start=1):
        cells: list[str] = []
        group_first = row_index > 1 and row[0] != previous_unit
        for column_index, value in enumerate(row, start=1):
            reference = _xlsx_cell_reference(column_index, row_index)
            if row_index > 1 and column_index == 3 and value:
                try:
                    numeric = Decimal(value)
                except InvalidOperation as exc:
                    raise DeliveryError(
                        "Duration cell is not a finite number"
                    ) from exc
                if not numeric.is_finite():
                    raise DeliveryError("Duration cell is not finite")
                style_index = 5 if group_first else 2
                cells.append(f'<c r="{reference}" s="{style_index}"><v>{value}</v></c>')
            else:
                if row_index == 1:
                    style_index = 1
                elif group_first:
                    style_index = 6 if column_index == 4 else 4
                else:
                    style_index = 3 if column_index == 4 else 0
                cells.append(
                    _xlsx_inline_cell(reference, value, style_index)
                )
        row_height = (
            24
            if row_index == 1
            else _xlsx_row_height_for_row(row, prompt_width)
        )
        worksheet_rows.append(
            f'<row r="{row_index}" ht="{row_height}" customHeight="1">'
            f'{"".join(cells)}</row>'
        )
        if row_index > 1:
            previous_unit = row[0]

    last_row = max(1, len(all_rows))
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:D{last_row}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        '<cols>'
        '<col min="1" max="1" width="14" customWidth="1"/>'
        '<col min="2" max="2" width="24" customWidth="1"/>'
        '<col min="3" max="3" width="16" customWidth="1"/>'
        f'<col min="4" max="4" width="{prompt_width}" customWidth="1"/>'
        '</cols>'
        f'<sheetData>{"".join(worksheet_rows)}</sheetData>'
        f'<autoFilter ref="A1:D{last_row}"/>'
        '</worksheet>'
    )
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>'
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Prompt Table" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>'
        ),
        "xl/styles.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Arial"/></font>'
            '<font><b/><sz val="11"/><name val="Arial"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
            '<border><left/><right/><top style="medium"><color rgb="FF808080"/></top>'
            '<bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="7">'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
            '<alignment wrapText="1" vertical="top"/></xf>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
            '<alignment wrapText="1" vertical="top"/></xf>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
            '<alignment wrapText="1" vertical="top"/></xf>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1">'
            '<alignment wrapText="1" vertical="top"/></xf>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1">'
            '<alignment wrapText="1" vertical="top"/></xf>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1">'
            '<alignment wrapText="1" vertical="top"/></xf>'
            '</cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'
        ),
        "xl/worksheets/sheet1.xml": sheet_xml,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o600 << 16
            archive.writestr(info, files[name].encode("utf-8"))
    return buffer.getvalue()


def parse_prompt_table_xlsx(payload: bytes) -> list[list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload), mode="r") as archive:
            sheet_payload = archive.read("xl/worksheets/sheet1.xml")
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise DeliveryError(f"prompt_table.xlsx is unreadable: {exc}") from exc
    try:
        root = ET.fromstring(sheet_payload)
    except ET.ParseError as exc:
        raise DeliveryError(f"prompt_table.xlsx sheet XML is invalid: {exc}") from exc
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    parsed_rows: list[list[str]] = []
    for row in root.findall(".//x:sheetData/x:row", namespace):
        cells = ["", "", "", ""]
        for cell in row.findall("x:c", namespace):
            reference = cell.get("r", "")
            match = re.match(r"([A-Z]+)", reference)
            if match is None:
                continue
            column = 0
            for character in match.group(1):
                column = column * 26 + ord(character) - 64
            if not 1 <= column <= 4:
                continue
            if cell.get("t") == "inlineStr":
                value = "".join(
                    text.text or ""
                    for text in cell.findall(".//x:t", namespace)
                )
            else:
                value_node = cell.find("x:v", namespace)
                value = value_node.text if value_node is not None else ""
            cells[column - 1] = value
        parsed_rows.append(cells)
    if not parsed_rows or tuple(parsed_rows[0]) != PROMPT_TABLE_COLUMNS:
        raise DeliveryError("prompt_table.xlsx columns do not match the contract")
    return parsed_rows[1:]


def inspect_prompt_table_xlsx_layout(payload: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload), mode="r") as archive:
            sheet_payload = archive.read("xl/worksheets/sheet1.xml")
            workbook_payload = archive.read("xl/workbook.xml")
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise DeliveryError(f"prompt_table.xlsx is unreadable: {exc}") from exc
    try:
        sheet_root = ET.fromstring(sheet_payload)
        workbook_root = ET.fromstring(workbook_payload)
    except ET.ParseError as exc:
        raise DeliveryError(f"prompt_table.xlsx XML is invalid: {exc}") from exc
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    prompt_width: float | None = None
    for column in sheet_root.findall(".//x:cols/x:col", namespace):
        if column.get("min") == "4" and column.get("max") == "4":
            try:
                prompt_width = float(column.get("width", ""))
            except ValueError:
                prompt_width = None
            break
    row_heights: list[float] = []
    custom_height_rows = 0
    for row in sheet_root.findall(".//x:sheetData/x:row", namespace):
        try:
            height = float(row.get("ht", ""))
        except ValueError:
            height = math.inf
        row_heights.append(height)
        if row.get("customHeight") == "1":
            custom_height_rows += 1
    sheet_names = [
        sheet.get("name", "")
        for sheet in workbook_root.findall(".//x:sheets/x:sheet", namespace)
    ]
    pane = sheet_root.find(".//x:sheetViews/x:sheetView/x:pane", namespace)
    auto_filter = sheet_root.find(".//x:autoFilter", namespace)
    return {
        "sheet_names": sheet_names,
        "prompt_column_width": prompt_width,
        "row_heights": row_heights,
        "custom_height_rows": custom_height_rows,
        "row_count_including_header": len(row_heights),
        "header_frozen": pane is not None and pane.get("state") == "frozen",
        "auto_filter": auto_filter is not None,
    }


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _formal_validation_report(
    plan: Mapping[str, Any],
    plan_payload: bytes,
    markdown_payload: bytes,
    xlsx_payload: bytes,
    rows: Sequence[Sequence[str]],
    xlsx_rows: Sequence[Sequence[str]],
) -> dict[str, Any]:
    files = _plan_delivery_file_map(plan)
    report: dict[str, Any] = {
        "contract_name": VALIDATION_CONTRACT_NAME,
        "contract_version": VALIDATION_CONTRACT_VERSION,
        "source_plan_content_hash": plan.get("content_hash"),
        "status": plan.get("validation", {}).get("status", "FAIL"),
        "validation": copy.deepcopy(plan.get("validation", {})),
        "table_contract": {
            "columns": list(PROMPT_TABLE_COLUMNS),
            "row_count": len(rows),
            "rows": [list(row) for row in rows],
        },
        "xlsx_table_contract": {
            "columns": list(PROMPT_TABLE_COLUMNS),
            "physical_row_count": len(xlsx_rows),
            "rows": [list(row) for row in xlsx_rows],
            "prompt_reconstruction": "one-row-one-prompt-unit",
            "prompt_column_width_range": [
                XLSX_PROMPT_WIDTH_MIN,
                XLSX_PROMPT_WIDTH_MAX,
            ],
            "maximum_row_height_points": int(XLSX_ROW_HEIGHT_LIMIT),
        },
        "artifact_hashes": {
            files["plan"]: _sha256_bytes(plan_payload),
            files["markdown"]: _sha256_bytes(markdown_payload),
            files["xlsx"]: _sha256_bytes(xlsx_payload),
        },
    }
    report["content_hash"] = sha256_json(report)
    return report


def derive_delivery_artifacts(plan: Mapping[str, Any]) -> dict[str, bytes]:
    files = _plan_delivery_file_map(plan)
    rows = prompt_table_rows(plan)
    xlsx_rows = prompt_table_xlsx_rows(plan)
    plan_payload = stable_json_bytes(plan)
    markdown_payload = prompt_table_markdown_bytes(rows)
    xlsx_payload = prompt_table_xlsx_bytes(xlsx_rows)
    report = _formal_validation_report(
        plan,
        plan_payload,
        markdown_payload,
        xlsx_payload,
        rows,
        xlsx_rows,
    )
    return {
        files["plan"]: plan_payload,
        files["markdown"]: markdown_payload,
        files["xlsx"]: xlsx_payload,
        files["validation"]: stable_json_bytes(report),
    }


def write_delivery_package(
    output_dir: Path | str, artifacts: Mapping[str, bytes]
) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir():
        raise DeliveryError(f"Output path is not a directory: {destination}")
    formal_files = tuple(artifacts)
    if (
        len(formal_files) != 4
        or len(set(formal_files)) != 4
        or any("prompt" not in name for name in formal_files)
    ):
        raise DeliveryError("Delivery package must contain exactly four formal files")
    temporary_paths: dict[str, Path] = {}
    try:
        for name in formal_files:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination,
                prefix=f".{name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_paths[name] = Path(handle.name)
                handle.write(artifacts[name])
                handle.flush()
        for name in formal_files:
            temporary_paths[name].replace(destination / name)
    finally:
        for temporary_path in temporary_paths.values():
            if temporary_path.exists():
                temporary_path.unlink()


def build_delivery_package(
    source_document: Any,
    decisions: Any = None,
    model_profile: Any = None,
    delivery_slug: str | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    plan = build_prompt_plan(
        source_document,
        decisions=decisions,
        model_profile=model_profile,
        delivery_slug=delivery_slug,
    )
    return plan, derive_delivery_artifacts(plan)


def validate_delivery_package(
    source_document: Any,
    output_dir: Path | str,
    delivery_slug: str | None = None,
) -> dict[str, Any]:
    destination = Path(output_dir)
    slug = (
        _ascii_kebab_slug(delivery_slug)
        if delivery_slug is not None
        else derive_delivery_slug(None, source_document)
    )
    files = delivery_file_map(slug)
    formal_files = tuple(files.values())
    package_issues: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    for name in formal_files:
        path = destination / name
        try:
            payloads[name] = path.read_bytes()
        except OSError as exc:
            package_issues.append(
                _issue(
                    "DELIVERY_FILE_MISSING",
                    "ERROR",
                    "package",
                    name,
                    f"正式交付文件不可读：{exc}",
                    ("delivery_integrity",),
                )
            )
    if package_issues:
        return {
            "status": "FAIL",
            "package_errors": package_issues,
            "plan_validation": None,
            "deterministic_checks": {
                "four_files_present": False,
                "plan_bytes": False,
                "markdown_cells": False,
                "xlsx_cells": False,
                "validation_report": False,
            },
        }

    try:
        plan = json.loads(payloads[files["plan"]].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return {
            "status": "FAIL",
            "package_errors": [
                _issue(
                    "DELIVERY_PLAN_UNREADABLE",
                    "ERROR",
                    "package",
                    files["plan"],
                    f"机器事实源不可读：{exc}",
                    ("delivery_integrity",),
                )
            ],
            "plan_validation": None,
            "deterministic_checks": {
                "four_files_present": True,
                "plan_bytes": False,
                "markdown_cells": False,
                "xlsx_cells": False,
                "validation_report": False,
            },
        }

    try:
        declared_files = _plan_delivery_file_map(plan)
    except DeliveryError as exc:
        declared_files = {}
        package_issues.append(
            _issue(
                "DELIVERY_NAMING_INVALID",
                "ERROR",
                "package",
                files["plan"],
                str(exc),
                ("delivery_integrity",),
            )
        )
    if declared_files != files:
        if declared_files:
            package_issues.append(
                _issue(
                    "DELIVERY_NAMING_INVALID",
                    "ERROR",
                    "package",
                    files["plan"],
                    "plan 登记的正式文件名与本次输入文件名派生结果不一致。",
                    ("delivery_integrity",),
                )
            )
        return {
            "status": "FAIL",
            "package_errors": package_issues,
            "plan_validation": None,
            "deterministic_checks": {
                "four_files_present": True,
                "plan_bytes": False,
                "markdown_cells": False,
                "xlsx_cells": False,
                "validation_report": False,
            },
        }

    plan_validation = validate_prompt_plan(source_document, plan)
    rows = prompt_table_rows(plan)
    expected_xlsx_rows = prompt_table_xlsx_rows(plan)
    expected_artifacts = derive_delivery_artifacts(plan)
    plan_bytes_ok = (
        payloads[files["plan"]] == expected_artifacts[files["plan"]]
    )
    if not plan_bytes_ok:
        package_issues.append(
            _issue(
                "DELIVERY_NONDETERMINISTIC",
                "ERROR",
                "package",
                files["plan"],
                "Prompt plan 不是机器事实源的确定性 JSON 字节派生。",
                ("delivery_integrity",),
            )
        )

    markdown_cells_ok = False
    try:
        markdown_rows = parse_prompt_table_markdown(
            payloads[files["markdown"]]
        )
        markdown_cells_ok = (
            markdown_rows == rows
            and payloads[files["markdown"]]
            == expected_artifacts[files["markdown"]]
        )
    except DeliveryError as exc:
        package_issues.append(
            _issue(
                "DELIVERY_TABLE_INVALID",
                "ERROR",
                "package",
                files["markdown"],
                str(exc),
                ("delivery_integrity",),
            )
        )
    if not markdown_cells_ok and not any(
        issue["path"] == files["markdown"] for issue in package_issues
    ):
        package_issues.append(
            _issue(
                "DELIVERY_TABLE_TAMPERED",
                "ERROR",
                "package",
                files["markdown"],
                "Markdown 单元格未逐格匹配机器事实源。",
                ("delivery_integrity",),
            )
        )

    xlsx_cells_ok = False
    try:
        xlsx_rows = parse_prompt_table_xlsx(payloads[files["xlsx"]])
        xlsx_layout = inspect_prompt_table_xlsx_layout(
            payloads[files["xlsx"]]
        )
        reconstructed = reconstruct_prompt_texts_from_xlsx_rows(xlsx_rows)
        expected_reconstructed = {
            str(unit.get("prompt_unit_id", "")): str(
                unit.get("prompt_text", "")
            )
            for unit in plan.get("prompt_units", [])
            if isinstance(unit, dict)
        }
        prompt_width = xlsx_layout.get("prompt_column_width")
        row_heights = xlsx_layout.get("row_heights", [])
        layout_ok = (
            xlsx_layout.get("sheet_names") == ["Prompt Table"]
            and isinstance(prompt_width, (int, float))
            and XLSX_PROMPT_WIDTH_MIN <= prompt_width <= XLSX_PROMPT_WIDTH_MAX
            and bool(row_heights)
            and all(
                isinstance(height, (int, float))
                and math.isfinite(height)
                and height <= float(XLSX_ROW_HEIGHT_LIMIT)
                for height in row_heights
            )
            and xlsx_layout.get("custom_height_rows")
            == xlsx_layout.get("row_count_including_header")
            and xlsx_layout.get("header_frozen") is True
            and xlsx_layout.get("auto_filter") is True
        )
        xlsx_cells_ok = (
            xlsx_rows == expected_xlsx_rows
            and reconstructed == expected_reconstructed
            and layout_ok
            and payloads[files["xlsx"]]
            == expected_artifacts[files["xlsx"]]
        )
    except DeliveryError as exc:
        package_issues.append(
            _issue(
                "DELIVERY_TABLE_INVALID",
                "ERROR",
                "package",
                files["xlsx"],
                str(exc),
                ("delivery_integrity",),
            )
        )
    if not xlsx_cells_ok and not any(
        issue["path"] == files["xlsx"] for issue in package_issues
    ):
        package_issues.append(
            _issue(
                "DELIVERY_TABLE_TAMPERED",
                "ERROR",
                "package",
                files["xlsx"],
                "Excel 单元格未逐格匹配机器事实源。",
                ("delivery_integrity",),
            )
        )

    validation_report_ok = (
        payloads[files["validation"]]
        == expected_artifacts[files["validation"]]
    )
    if not validation_report_ok:
        package_issues.append(
            _issue(
                "DELIVERY_VALIDATION_TAMPERED",
                "ERROR",
                "package",
                files["validation"],
                "验证报告未确定性匹配 plan 与其两个表格派生物。",
                ("delivery_integrity",),
            )
        )

    return {
        "status": (
            "FAIL"
            if package_issues
            else plan_validation.get("status", "FAIL")
        ),
        "package_errors": package_issues,
        "plan_validation": plan_validation,
        "deterministic_checks": {
            "four_files_present": True,
            "plan_bytes": plan_bytes_ok,
            "markdown_cells": markdown_cells_ok,
            "xlsx_cells": xlsx_cells_ok,
            "validation_report": validation_report_ok,
        },
    }
