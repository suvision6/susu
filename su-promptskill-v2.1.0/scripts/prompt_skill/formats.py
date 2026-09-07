"""Portable OOXML reading view, evolved from the prior stdlib exporter.

A logical Prompt can occupy several physical rows. Fragment concatenation is
exact (no added separator); duration is numeric once, never per continuation.
"""
from __future__ import annotations
import html
import io
import json
import math
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal
from .common import DeliveryError
from .master import Master

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
COLUMNS = ["Prompt 段号", "来源镜号／源段", "总时长（秒）", "Prompt"]


def _width(text):
    return sum(0 if unicodedata.combining(c) or c == '\u200d' else 2 if unicodedata.east_asian_width(c) in {'W', 'F'} else 1 for c in text)


def _lines(text, width):
    capacity = max(4, width - 3)
    return sum(max(1, math.ceil(_width(line) / capacity)) for line in text.split('\n'))


def _chunks(text: str, width: int):
    if not text:
        return [""]
    result = []; start = 0; line_width = 0; line_count = 1; units = 0
    capacity = max(4, width - 3)
    for i, char in enumerate(text):
        w = _width(char); new_line = char == '\n' or line_width + w > capacity
        next_lines = line_count + int(new_line)
        next_units = units + (2 if ord(char) > 0xFFFF else 1)
        # Split only the view. These are physical display budgets, not content limits.
        if i > start and (next_lines > 16 or next_units > 30000):
            result.append(text[start:i]); start = i; line_count = 1; line_width = 0; units = 0
            new_line = char == '\n'; next_lines = 1 + int(new_line)
        line_count = next_lines
        line_width = 0 if char == '\n' else w if new_line else line_width + w
        units += 2 if ord(char) > 0xFFFF else 1
    result.append(text[start:])
    assert ''.join(result) == text
    return result


def _encode(text):
    text = re.sub(r'_x[0-9A-Fa-f]{4}_', lambda m: '_x005F_' + m[0][1:], text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\r]', lambda m: f'_x{ord(m[0]):04X}_', text)
    return html.escape(text, quote=False)


def _decode(text):
    return re.sub(r'_x([0-9A-Fa-f]{4})_', lambda m: chr(int(m[1], 16)), text)


def table_rows(master: Master):
    logical = [[u.id, json.dumps(u.source_ids, ensure_ascii=False), '' if u.duration is None else format(u.duration, 'f'), u.text] for u in master.units]
    widths = [max(14, min(24, max((_width(r[0]) for r in logical), default=10)+3)),
              max(18, min(38, max((_width(r[1]) for r in logical), default=15)+3)),
              max(18, min(26, max((_width(r[2]) for r in logical), default=8)+3)),
              max(62, min(116, math.ceil(math.sqrt(max((len(r[3]) for r in logical), default=1)) * 3)))]
    rows = []
    for uid, source_ids, duration, text in logical:
        source_fragments = _chunks(source_ids, widths[1]); prompt_fragments = _chunks(text, widths[3])
        count = max(len(source_fragments), len(prompt_fragments))
        for i in range(count):
            rows.append([uid if i == 0 else f'{uid} ·续{i+1}',
                         source_fragments[i] if i < len(source_fragments) else '',
                         duration if i == 0 else '', prompt_fragments[i] if i < len(prompt_fragments) else ''])
    return rows, widths


def xlsx_bytes(master: Master) -> bytes:
    rows, widths = table_rows(master)
    worksheet_rows = []
    for ri, row in enumerate([COLUMNS] + rows, 1):
        cells = []
        continuation = ri > 1 and ' ·续' in row[0]
        for ci, value in enumerate(row, 1):
            ref = f'{chr(64+ci)}{ri}'
            style = 1 if ri == 1 else 2 if not continuation else 0
            # More than Excel's numeric precision is stored as text, without rounding.
            numeric = ci == 3 and ri > 1 and value and len(Decimal(value).as_tuple().digits) <= 15
            if numeric:
                cells.append(f'<c r="{ref}" s="{style}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{_encode(value)}</t></is></c>')
        height = 30 if ri == 1 else max(26, max(_lines(value, widths[i]) for i, value in enumerate(row))*18+12)
        if height > 409:
            raise DeliveryError('阅读分块仍超过单行显示上限；正文不会被截断')
        worksheet_rows.append(f'<row r="{ri}" ht="{height}" customHeight="1">{"".join(cells)}</row>')
    last = len(rows)+1
    namespace = NS['s']
    worksheet = (f'<worksheet xmlns="{namespace}"><dimension ref="A1:D{last}"/>'
                 '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
                 '<cols>' + ''.join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i,w in enumerate(widths,1)) + '</cols>'
                 '<sheetData>' + ''.join(worksheet_rows) + '</sheetData>'
                 + (f'<autoFilter ref="A1:D{last}"/>' if all(' ·续' not in r[0] for r in rows) else '')
                 + '<printOptions horizontalCentered="0"/><pageMargins left="0.25" right="0.25" top="0.4" bottom="0.4" header="0.2" footer="0.2"/></worksheet>')
    styles = (f'<styleSheet xmlns="{namespace}"><fonts count="2">'
              '<font><sz val="11"/><name val="Microsoft YaHei"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Microsoft YaHei"/></font></fonts>'
              '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF243746"/><bgColor indexed="64"/></patternFill></fill></fills>'
              '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left/><right/><top style="thin"><color rgb="FFB9C6CF"/></top><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3">'
              '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
              '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>'
              '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
              '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    files = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': f'<workbook xmlns="{namespace}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Prompt Table" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        'xl/styles.xml': styles, 'xl/worksheets/sheet1.xml': worksheet,
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (1980,1,1,0,0,0)); info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + files[name]).encode('utf-8'))
    return out.getvalue()


def read_xlsx(payload: bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 100_000_000:
                raise DeliveryError('XLSX 解压内容超出读取预算')
            shared = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
                shared = [_decode(''.join(x.itertext())) for x in root]
            root = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
            rows = []
            for row in root.findall('s:sheetData/s:row', NS):
                values = ['']*4
                for cell in row.findall('s:c', NS):
                    if cell.find('s:f', NS) is not None:
                        raise DeliveryError('阅读正文或时长不能被替换为公式')
                    ref = cell.get('r',''); match = re.fullmatch(r'([A-D])[0-9]+', ref)
                    if not match:
                        if ''.join(cell.itertext()).strip():
                            raise DeliveryError('阅读表出现非预期内容列')
                        continue
                    v = cell.find('s:v', NS)
                    if cell.get('t') == 'inlineStr':
                        node = cell.find('s:is', NS); value = _decode(''.join(node.itertext())) if node is not None else ''
                    elif cell.get('t') == 's':
                        value = shared[int(v.text)]
                    else:
                        value = v.text or '' if v is not None else ''
                    values[ord(match[1])-65] = value
                rows.append(values)
            if not rows or rows.pop(0) != COLUMNS:
                raise DeliveryError('阅读表表头与合同不一致')
    except (KeyError, ValueError, ET.ParseError, zipfile.BadZipFile, IndexError) as exc:
        if isinstance(exc, DeliveryError):
            raise
        raise DeliveryError(f'XLSX 无法读取：{exc}') from exc
    logical = []; current = None; number = 1
    for uid, refs, duration, text in rows:
        if ' ·续' in uid:
            number += 1
            if current is None or uid != f'{current[0]} ·续{number}' or duration:
                raise DeliveryError('续行被重排、脱离单元或重复计算时长')
            current[1] += refs; current[3] += text
        else:
            number = 1; current = [uid, refs, duration, text]; logical.append(current)
    return logical
