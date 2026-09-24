"""Small, dependency-free XLSX writer for this package's reading sheets.

This is deliberately not a general spreadsheet engine. It writes text, numeric
values, styles, merged titles, cached summaries, panes and print settings. User
text is never interpreted as a formula. All imports belong to Python's stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
XMLSPACE = '{http://www.w3.org/XML/1998/namespace}space'
ESC = re.compile(r'_x[0-9A-Fa-f]{4}_')
ET.register_namespace('', MAIN)
ET.register_namespace('r', REL)


def tag(name: str) -> str:
    return '{' + MAIN + '}' + name


def node(parent: ET.Element, name: str, attrs: dict | None = None, text: Any = None) -> ET.Element:
    el = ET.SubElement(parent, tag(name), {k: str(v) for k, v in (attrs or {}).items()})
    if text is not None:
        el.text = str(text)
    return el


def xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def encode_text(text: str) -> str:
    # OOXML escape sequences are special even in literal inline strings.
    text = re.sub(r'_(?=x[0-9A-Fa-f]{4}_)', '_x005F_', text)
    return ''.join(f'_x{ord(c):04X}_' if (ord(c) < 32 and c not in '\t\n\r')
                   or c in '\ufffe\uffff' else c for c in text)


def decode_text(text: str) -> str:
    # One pass only: _x005F_x0041_ must recover the literal _x0041_, not A.
    return ESC.sub(lambda m: chr(int(m.group(0)[2:6], 16)), text)


def number(value: int | float | Decimal) -> str:
    n = Decimal(str(value))
    if not n.is_finite():
        raise ValueError('Excel numeric cell must be finite')
    return format(n, 'f')


def col_name(index: int) -> str:
    text = ''
    while index >= 0:
        index, digit = divmod(index, 26)
        text = chr(65 + digit) + text
        index -= 1
    return text


@dataclass(frozen=True)
class Formula:
    expression: str
    cached: int | float | Decimal


class Sheet:
    def __init__(self, name: str, widths_px: list[float]):
        if not name or len(name) > 31 or any(c in name for c in '[]:*?/\\'):
            raise ValueError('Invalid worksheet name')
        self.name, self.widths_px = name, widths_px
        self.rows: dict[int, tuple[list[Any], float, str]] = {}
        self.merges: list[str] = []

    def write(self, row: int, values: list[Any], height_px: float, role: str) -> None:
        if row < 1 or row > 1048576 or len(values) != len(self.widths_px):
            raise ValueError('Reading sheet row/column outside supported range')
        if not math.isfinite(height_px) or not 0 < height_px <= 409 * 96 / 72 + 0.01:
            raise ValueError('Reading row must be split before it exceeds Excel display capacity')
        self.rows[row] = (values, height_px, role)

    @property
    def last_row(self) -> int:
        return max(self.rows, default=1)

    def to_xml(self, styles: 'Styles') -> bytes:
        root = ET.Element(tag('worksheet'))
        pr = node(root, 'sheetPr')
        node(pr, 'pageSetUpPr', {'fitToPage': 1})
        node(root, 'dimension', {'ref': f'A1:{col_name(len(self.widths_px)-1)}{self.last_row}'})
        views = node(root, 'sheetViews')
        view = node(views, 'sheetView', {'workbookViewId': 0, 'showGridLines': 0})
        node(view, 'pane', {'ySplit': 3, 'topLeftCell': 'A4', 'activePane': 'bottomLeft', 'state': 'frozen'})
        node(view, 'selection', {'pane': 'bottomLeft', 'activeCell': 'A4', 'sqref': 'A4'})
        node(root, 'sheetFormatPr', {'defaultRowHeight': 15})
        cols = node(root, 'cols')
        for i, pixels in enumerate(self.widths_px, 1):
            # OOXML stores widths in Normal-style digit units (Calibri 11 here).
            width = min(255., max(1., math.ceil((pixels - 5) / 7 * 256) / 256))
            node(cols, 'col', {'min': i, 'max': i, 'width': width, 'customWidth': 1})
        body = node(root, 'sheetData')
        for row_no, (values, px, role) in sorted(self.rows.items()):
            row = node(body, 'row', {'r': row_no, 'ht': round(px * 72 / 96, 4), 'customHeight': 1})
            for j, value in enumerate(values):
                numeric = isinstance(value, (int, float, Decimal, Formula))
                attrs = {'r': f'{col_name(j)}{row_no}', 's': styles.cell_style(role, numeric)}
                c = node(row, 'c', attrs)
                if isinstance(value, Formula):
                    formula = value.expression.removeprefix('=')
                    if len(formula) > 8192:
                        raise ValueError('Summary formula exceeds Excel formula capacity')
                    node(c, 'f', text=formula)
                    node(c, 'v', text=number(value.cached))
                elif isinstance(value, (int, float, Decimal)):
                    node(c, 'v', text=number(value))
                elif value is not None:
                    text = str(value)
                    if len(text.encode('utf-16-le')) // 2 > 32767 or text.count('\n') > 253:
                        raise ValueError(f'{self.name}!{attrs["r"]}: text must be continued onto another row')
                    c.set('t', 'inlineStr')
                    node(node(c, 'is'), 't', {XMLSPACE: 'preserve'}, encode_text(text))
        if self.merges:
            merges = node(root, 'mergeCells', {'count': len(self.merges)})
            for ref in self.merges:
                node(merges, 'mergeCell', {'ref': ref})
        node(root, 'printOptions', {'horizontalCentered': 1})
        node(root, 'pageMargins', {'left': .25, 'right': .25, 'top': .4, 'bottom': .4, 'header': .2, 'footer': .2})
        # Six-column dense text is given A3 landscape; no forced vertical shrink.
        node(root, 'pageSetup', {'paperSize': 8 if len(self.widths_px) == 6 else 9,
                               'orientation': 'landscape', 'fitToWidth': 1, 'fitToHeight': 0})
        foot = node(root, 'headerFooter')
        node(foot, 'oddFooter', text='&C&P / &N')
        return xml_bytes(root)


class Styles:
    ROLES = ('body0', 'body1', 'note', 'title', 'header', 'total', 'count')

    def __init__(self, family: str, size: float):
        self.family, self.size = family, size
        self.ids = {(role, num): 1 + 2*i + int(num)
                    for i, role in enumerate(self.ROLES) for num in (False, True)}

    def cell_style(self, role: str, numeric: bool) -> int:
        return self.ids[role, numeric]

    def to_xml(self) -> bytes:
        root = ET.Element(tag('styleSheet'))
        fonts = node(root, 'fonts', {'count': 5})
        for name, size, bold, color in [('Calibri', 11, False, 'FF203442'),
                    (self.family, self.size, False, 'FF203442'),
                    (self.family, self.size + 4, True, 'FFFFFFFF'),
                    (self.family, self.size, True, 'FFFFFFFF'),
                    (self.family, self.size, True, 'FF203442')]:
            f = node(fonts, 'font')
            if bold: node(f, 'b')
            node(f, 'sz', {'val': size}); node(f, 'color', {'rgb': color}); node(f, 'name', {'val': name})
            node(f, 'family', {'val': 2})
        fills = node(root, 'fills', {'count': 9})
        for pattern in ('none', 'gray125'):
            node(node(fills, 'fill'), 'patternFill', {'patternType': pattern})
        for color in ('FFF3F6F8', 'FFFFFFFF', 'FFEAF2F4', 'FF182B3A', 'FF2A5366', 'FFD9E8EE', 'FFEDF3F5'):
            p = node(node(fills, 'fill'), 'patternFill', {'patternType': 'solid'})
            node(p, 'fgColor', {'rgb': color}); node(p, 'bgColor', {'indexed': 64})
        borders = node(root, 'borders', {'count': 2})
        for outlined in (False, True):
            border = node(borders, 'border')
            for edge in ('left', 'right', 'top', 'bottom', 'diagonal'):
                e = node(border, edge, {'style': 'hair'} if outlined and edge != 'diagonal' else {})
                if outlined and edge != 'diagonal': node(e, 'color', {'rgb': 'FFD5DEE3'})
        base = node(root, 'cellStyleXfs', {'count': 1})
        node(base, 'xf', {'numFmtId': 0, 'fontId': 0, 'fillId': 0, 'borderId': 0})
        xfs = node(root, 'cellXfs', {'count': 1 + len(self.ids)})
        node(xfs, 'xf', {'numFmtId': 0, 'fontId': 0, 'fillId': 0, 'borderId': 0, 'xfId': 0})
        for i, role in enumerate(self.ROLES):
            for numeric in (False, True):
                font_id = {'title': 2, 'header': 3, 'total': 4}.get(role, 1)
                xf = node(xfs, 'xf', {'numFmtId': 0 if numeric else 49, 'fontId': font_id,
                    'fillId': i+2, 'borderId': 1 if role.startswith('body') or role == 'note' else 0,
                    'xfId': 0, 'applyAlignment': 1, 'applyNumberFormat': 1, 'applyFont': 1, 'applyFill': 1})
                node(xf, 'alignment', {'vertical': 'center' if role in ('title','header','total','count') else 'top',
                                      'horizontal': 'center' if role == 'header' else ('right' if numeric else 'left'),
                                      'wrapText': 1})
        css = node(root, 'cellStyles', {'count': 1})
        node(css, 'cellStyle', {'name': 'Normal', 'xfId': 0, 'builtinId': 0})
        return xml_bytes(root)


def write_workbook(path: Path, sheets: list[Sheet], family: str, size: float) -> None:
    if not sheets or len({s.name for s in sheets}) != len(sheets):
        raise ValueError('Reading workbook needs unique, nonempty worksheets')
    styles = Styles(family, size)
    workbook = ET.Element(tag('workbook'))
    views = node(workbook, 'bookViews'); node(views, 'workbookView', {'activeTab': 0})
    sheet_list = node(workbook, 'sheets')
    rels = ET.Element('Relationships', {'xmlns': PKG})
    for i, sheet in enumerate(sheets, 1):
        node(sheet_list, 'sheet', {'name': sheet.name, 'sheetId': i, '{'+REL+'}id': f'rId{i}'})
        ET.SubElement(rels, 'Relationship', {'Id': f'rId{i}', 'Type': REL+'/worksheet', 'Target': f'worksheets/sheet{i}.xml'})
    ET.SubElement(rels, 'Relationship', {'Id': 'rStyles', 'Type': REL+'/styles', 'Target': 'styles.xml'})
    names = node(workbook, 'definedNames')
    for i, sheet in enumerate(sheets):
        escaped = "'" + sheet.name.replace("'", "''") + "'"
        node(names, 'definedName', {'name': '_xlnm.Print_Titles', 'localSheetId': i}, escaped+'!$3:$3')
        node(names, 'definedName', {'name': '_xlnm.Print_Area', 'localSheetId': i},
             f'{escaped}!$A$1:${col_name(len(sheet.widths_px)-1)}${sheet.last_row}')
    node(workbook, 'calcPr', {'calcId': 191029, 'calcMode': 'auto', 'fullCalcOnLoad': 1, 'forceFullCalc': 1})
    types = ET.Element('Types', {'xmlns': CT})
    for ext, content in [('rels','application/vnd.openxmlformats-package.relationships+xml'),('xml','application/xml')]:
        ET.SubElement(types, 'Default', {'Extension': ext, 'ContentType': content})
    for part, content in [('/xl/workbook.xml','spreadsheetml.sheet.main'),('/xl/styles.xml','spreadsheetml.styles')] + [
            (f'/xl/worksheets/sheet{i}.xml','spreadsheetml.worksheet') for i in range(1,len(sheets)+1)]:
        ET.SubElement(types, 'Override', {'PartName': part, 'ContentType': 'application/vnd.openxmlformats-officedocument.'+content+'+xml'})
    package_rels = ET.Element('Relationships', {'xmlns': PKG})
    ET.SubElement(package_rels, 'Relationship', {'Id': 'rId1', 'Type': REL+'/officeDocument', 'Target': 'xl/workbook.xml'})
    parts = {'[Content_Types].xml': xml_bytes(types), '_rels/.rels': xml_bytes(package_rels),
             'xl/workbook.xml': xml_bytes(workbook), 'xl/_rels/workbook.xml.rels': xml_bytes(rels),
             'xl/styles.xml': styles.to_xml()}
    parts.update({f'xl/worksheets/sheet{i}.xml': s.to_xml(styles) for i,s in enumerate(sheets,1)})
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            entry = zipfile.ZipInfo(name, date_time=(2026,9,8,0,0,0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
