"""Content-sized reading sheets; this module does not interpret film language.

XLSX serialization uses the bundled standard-library writer. Font measurement
and a requested PNG preview are optional enhancements, never export dependencies.
"""
from __future__ import annotations

from functools import lru_cache
import math
from pathlib import Path
import subprocess
import tempfile
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

from master_io import save_exclusive
from native_xlsx import Sheet, Formula, write_workbook, decode_text
from decimal import Decimal
import posixpath


class TextMeasure:
    def __init__(self, family: str, size: float):
        self.size, self.font, self.font_path = size, None, None
        try:
            from PIL import ImageFont
            result = subprocess.run(['fc-match', '-f', '%{file}', family], capture_output=True,
                                    text=True, timeout=5, check=True)
            path = result.stdout.strip()
            if not Path(path).is_file():
                raise FileNotFoundError(path)
            self.font = ImageFont.truetype(path, round(size * 96 / 72 * 2))
            self.font_path = path
        except (ImportError, OSError, subprocess.SubprocessError):
            pass
        self.line_height = size * 96 / 72 * 1.48

    @lru_cache(maxsize=8192)
    def width(self, char: str) -> float:
        if char == '\t':
            return self.width(' ') * 4
        if self.font:
            return float(self.font.getlength(char)) / 2 * 1.08
        if unicodedata.combining(char):
            return 0
        return self.size * 96 / 72 * (1.08 if unicodedata.east_asian_width(char) in 'WF' else .63)

    def length(self, text: str) -> float:
        return sum(self.width(c) for c in text)

    def segments(self, text: str, width: float) -> list[tuple[int, int]]:
        """Source offsets for estimated display lines; never insert a newline."""
        if not text:
            return [(0, 0)]
        spans, start, used = [], 0, 0.
        available = max(width - 24, self.size * 3)
        for i, c in enumerate(text):
            if c == '\n':
                spans.append((start, i + 1))
                start, used = i + 1, 0.
            else:
                n = self.width(c)
                if used + n > available and i > start and not unicodedata.combining(c):
                    spans.append((start, i))
                    start, used = i, 0.
                used += n
        if start < len(text):
            spans.append((start, len(text)))
        # A trailing newline leaves a final empty display line.
        if text.endswith('\n'):
            spans.append((len(text), len(text)))
        return spans

    def height(self, text: str, width: float) -> float:
        return max(30, len(self.segments(text, width)) * self.line_height + 16)

    def chunks(self, text: str, width: float) -> list[str]:
        if not text:
            return ['']
        lines = self.segments(text, width)
        # 409pt is a file-format display boundary, not a creative text limit.
        max_lines = max(1, math.floor((409 * 96 / 72 - 20) / self.line_height))
        result, start, count, newlines = [], 0, 0, 0
        for left, right in lines:
            fragment = text[left:right]
            # UTF-16 conservative capacity also handles non-BMP characters.
            candidate = text[start:right]
            units = len(candidate.encode('utf-16-le')) // 2
            if count and (count >= max_lines or units > 32000 or newlines + fragment.count('\n') > 250):
                result.append(text[start:left])
                start, count, newlines = left, 0, 0
            count += 1
            newlines += fragment.count('\n')
        if start < len(text):
            result.append(text[start:])
        return result or ['']


def column_widths(headers: list[str], records: list[list[Any]], budget: int, tm: TextMeasure) -> list[float]:
    minima = [max(70., tm.length(h) + 30) for h in headers]
    budget = max(budget, math.ceil(sum(minima)))
    needs = []
    for j, header in enumerate(headers):
        lengths = sorted(tm.length(line) for row in records for line in str(row[j] or '').split('\n'))
        q = lengths[min(len(lengths) - 1, int(len(lengths) * .8))] if lengths else 0
        needs.append(max(minima[j], min(q + 24, budget * 0.8)))
    excess = [max(0., n - m) for n, m in zip(needs, minima)]
    available = budget - sum(minima)
    # Keep short columns compact; allocate the rest according to actual text.
    if sum(excess) <= available:
        widths = needs[:]
        remaining = budget - sum(widths)
        longest = max(range(len(needs)), key=lambda i: needs[i])
        widths[longest] += remaining
        return widths
    weights = [math.sqrt(x) for x in excess]
    denominator = sum(weights) or 1
    return [m + available * w / denominator for m, w in zip(minima, weights)]


def read_xlsx(path: Path) -> dict[str, Any]:
    """Read saved XML for literal text, numbers, formulas and cached results."""
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            strings = [decode_text(''.join(t.text or '' for t in x.findall('.//m:t', ns))) for x in root.findall('m:si', ns)]
        wb = ET.fromstring(archive.read('xl/workbook.xml'))
        relns = {'p': 'http://schemas.openxmlformats.org/package/2006/relationships'}
        relations = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        targets = {x.get('Id'): x.get('Target') for x in relations.findall('p:Relationship', relns)}
        result = {}
        for index, sheet in enumerate(wb.findall('m:sheets/m:sheet', ns), 1):
            rid = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
            target = targets[rid]
            part = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
            root = ET.fromstring(archive.read(part))
            cells = {}
            for cell in root.findall('.//m:sheetData/m:row/m:c', ns):
                value = cell.find('m:v', ns)
                kind = cell.get('t')
                if kind == 'inlineStr':
                    value = decode_text(''.join(x.text or '' for x in cell.findall('m:is//m:t', ns)))
                elif kind == 's':
                    value = strings[int(value.text)] if value is not None else ''
                else:
                    value = value.text if value is not None and value.text is not None else ''
                formula = cell.find('m:f', ns)
                cells[cell.get('r')] = {'value': value, 'type': kind,
                                      'formula': formula.text if formula is not None else None}
            result[sheet.get('name')] = {
                'cells': cells,
                'heights_pt': [float(x.get('ht')) for x in root.findall('m:sheetData/m:row', ns) if x.get('ht')],
                'widths': [float(x.get('width')) for x in root.findall('m:cols/m:col', ns)],
                'freeze_saved': root.find('m:sheetViews/m:sheetView/m:pane', ns) is not None,
                'print_titles': next((x.text for x in wb.findall('m:definedNames/m:definedName', ns)
                                      if x.get('name') == '_xlnm.Print_Titles' and x.get('localSheetId') == str(index-1)), None)
            }
        return result


def _count_formula(first_rows: list[int]) -> str:
    """Compress consecutive record rows; limit each COUNTA to 200 arguments."""
    ranges = []
    for row in first_rows:
        if ranges and row == ranges[-1][1] + 1:
            ranges[-1][1] = row
        else:
            ranges.append([row, row])
    refs = [f'A{a}' if a == b else f'A{a}:A{b}' for a,b in ranges]
    return '+'.join('COUNTA(' + ','.join(refs[i:i+200]) + ')' for i in range(0,len(refs),200))


def export_reading(data: dict[str, Any], target: Path, budget: int = 1480,
                   family: str = 'Noto Sans CJK SC', size: float = 11,
                   preview_dir: Path | None = None) -> dict[str, Any]:
    if target.exists():
        raise FileExistsError(f'{target.name} 已存在。保留人类修改，请使用新前缀。')
    if budget < 720 or budget > 5000 or not math.isfinite(size) or size < 9 or size > 20:
        raise ValueError('阅读宽度请在 720—5000px、字号在 9—20pt 范围选择；不限制正文长度。')
    tm = TextMeasure(family, size)
    evidence: dict[str, Any] = {'status': 'saved_and_read_back', 'backend': 'stdlib-ooxml',
                               'required_third_party_packages': [], 'warnings': [], 'preview': 'not_requested'}
    if not tm.font:
        evidence['warnings'].append('未取得字体测量；使用保守宽度估计。Excel 已完成，目标软件字体与换行仍需复核。')
    kind = data['kind']
    if kind == 'director':
        rows = data['shots']
        headers = ['镜号', '场景', '原剧本段落', '预计时长（秒）', '运镜＋主画面描述', '备注']
        content = [[r['id'], r['scene'], r['source_text'], r['duration_seconds'], r['body'], r['notes']] for r in rows]
        names, dcol = ['导演分镜', '导演设计'], 3
    elif kind == 'prompt':
        rows = data['units']
        headers = ['段号', '来源镜头或源段', '内容预计时长（秒）', 'Prompt']
        content = [[r['id'], r['source_scope'], r['duration_seconds'], r['body']] for r in rows]
        names, dcol = ['视频提示词', '执行说明'], 2
    else:
        raise ValueError('图像计划不派生 Excel；图像 JSON 不代替九宫格。')
    expected: dict[str, dict[str, Any]] = {}
    sheets, displays, groups = [], [], []

    def col(index: int) -> str:
        return chr(65 + index)

    def write(sheet, r, values, height, role):
        sheet.write(r, values, min(409 * 96 / 72, height), role)
        for j, value in enumerate(values):
            if value is not None:
                expected[sheet.name][f'{col(j)}{r}'] = value

    def sheet_base(name, hs, values, title):
        widths = column_widths(hs, values, budget, tm)
        # A single column cannot exceed Excel's physical width. Long prose wraps.
        widths = [min(w, 255*7+5) for w in widths]
        if tm.height(title, sum(widths)) * (size+4)/size > 409*96/72:
            title = name + '｜完整项目标题见说明页'
        sheet = Sheet(name, widths)
        sheets.append(sheet); expected[name] = {}
        sheet.merges.append(f'A1:{col(len(hs)-1)}1')
        write(sheet, 1, [title]+[None]*(len(hs)-1),
              max(44,tm.height(title,sum(widths))*(size+4)/size), 'title')
        write(sheet, 3, hs, max(38, max(tm.height(h,w) for h,w in zip(hs,widths))), 'header')
        return sheet, widths

    def write_rows(sheet, widths, entries, first=4):
        for offset, (values, group, is_note) in enumerate(entries):
            height = max(tm.height(str(v) if v is not None else '',w) for v,w in zip(values,widths))
            write(sheet, first+offset, values, height, 'note' if is_note else f'body{group%2}')
        return first + len(entries)

    sheet, widths = sheet_base(names[0], headers, content, data['title'])
    entries = []
    for index, (source, values) in enumerate(zip(rows, content)):
        chunks = [tm.chunks(v,w) if isinstance(v,str) else [v] for v,w in zip(values,widths)]
        start, count = 4+len(entries), max(map(len,chunks))
        for n in range(count):
            row = [ch[n] if n<len(ch) else None for ch in chunks]
            if n:
                row[0], row[dcol] = source['id']+f'（续{n}）', None
            entries.append((row,index,False))
        groups.append((names[0], start,count,values,dcol))
        if kind=='prompt' and source['submission_notes']:
            for n,chunk in enumerate(tm.chunks(source['submission_notes'],widths[-1])):
                entries.append((['说明' if n==0 else '说明（续）',source['id'],None,chunk],index,True))
    after = write_rows(sheet,widths,entries)
    end, dletter = col(len(headers)-1), col(dcol)
    formula_range = f'{dletter}4:{dletter}{after-1}'
    formula = f'SUM({formula_range})'
    # Cache the actual serialized durations; no general formula evaluator is used.
    cached_total = sum((Decimal(str(v[dcol])) for v in content if v[dcol] is not None), Decimal(0))
    total_values = [None]*len(headers)
    total_values[0], total_values[dcol] = '已知时长合计（秒）', Formula(formula, cached_total)
    sheet.merges.append(f'A{after+1}:{col(dcol-1)}{after+1}')
    write(sheet,after+1,total_values,40,'total')
    count_row=after+2
    count_values=[None]*len(headers)
    count_values[0],count_values[dcol]='逻辑镜头／单元数',Formula(_count_formula([g[1] for g in groups]),len(rows))
    sheet.merges.append(f'A{count_row}:{col(dcol-1)}{count_row}')
    write(sheet,count_row,count_values,38,'count')
    displays.append((names[0],f'A1:{end}{min(after+1,6)}'))

    meta=[['项目标题',data['title']], ['本轮来源',data['source_description']], ['本轮范围',data['scope']],
          ['共用依据',data['context']], ['统计说明',f"{len(rows)} 个{'导演镜头' if kind=='director' else '执行单元'}；未知时长 {data['statistics']['unknown_duration_count']} 项。未知不计为零；存在未知时，已知合计不是完整总时长。"]]
    for key,label in [('source_basis','来源依据'),('continuity_notes','跨单元衔接'),('delivery_notes','交付说明')]:
        if data.get(key): meta.append([label,data[key]])
    meta.append(['阅读提示','内容由已保存主稿直接派生。续行不增加镜头或执行单元；各列续行只表示文字延续，不表示新的同步关系。实际客户端字体可能影响换行。'])
    info,iw=sheet_base(names[1],['项目','说明'],meta,names[1])
    note_entries=[]
    for i,(label,text) in enumerate(meta):
        for n,chunk in enumerate(tm.chunks(text,iw[1])):
            note_entries.append(([label if n==0 else label+'（续）',chunk],i,False))
    info_end=write_rows(info,iw,note_entries)
    displays.append((names[1],f'A1:B{min(info_end-1,7)}'))

    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.reading-',dir=target.parent) as temporary:
        stage=Path(temporary)/target.name
        write_workbook(stage,sheets,family,size)
        saved=read_xlsx(stage)
        checked=0
        for name, cellmap in expected.items():
            for address,value in cellmap.items():
                actual=saved[name]['cells'].get(address,{})
                if isinstance(value,Formula):
                    if actual.get('formula')!=value.expression or Decimal(actual.get('value','NaN'))!=Decimal(str(value.cached)):
                        raise ValueError(f'Excel 公式或缓存不同：{name}!{address}')
                elif isinstance(value,(int,float,Decimal)):
                    if Decimal(actual.get('value','NaN'))!=Decimal(str(value)):
                        raise ValueError(f'Excel 回读数值不同：{name}!{address}')
                elif actual.get('value','')!=value:
                    raise ValueError(f'Excel 回读文字不同：{name}!{address}，未发布文件。')
                if isinstance(value,str) and actual.get('formula') is not None:
                    raise ValueError('正文不能成为 Excel 公式。')
                checked+=1
        for name,start,count,original,dc in groups:
            for j,text in enumerate(original):
                if isinstance(text,str) and j!=0:
                    combined=''.join(saved[name]['cells'].get(f'{col(j)}{r}',{}).get('value','') for r in range(start,start+count))
                    if combined!=text:
                        raise ValueError(f'Excel 续行拼接不同：{name} / {original[0]}')
            if any(saved[name]['cells'].get(f'{col(dc)}{r}',{}).get('value','')!='' for r in range(start+1,start+count)):
                raise ValueError('续行重复出现时长。')
        for name,values in saved.items():
            if any(h>409.01 for h in values['heights_pt']): raise ValueError('保存行高超过 Excel 容量。')
            if not values['freeze_saved'] or not values['print_titles']:
                raise ValueError('冻结表头或打印重复表头未保存。')
            if any(c['type']=='e' for c in values['cells'].values()): raise ValueError('Excel 存在错误类型单元格。')
        save_exclusive(target,stage.read_bytes())
    evidence.update({'path':str(target),'font_measurement':'measured_with_margin' if tm.font else 'estimated',
        'record_count':len(rows),'continuation_rows':sum(g[2]-1 for g in groups),
        'checked_cells':checked,'summary_formulas_verified':True,'error_cells':0,
        'freeze_headers_saved':True,'print_titles_saved':True})
    if preview_dir:
        # Rendering is optional. It cannot prevent JSON/XLSX delivery on a Mac.
        try:
            from artifact_tool import Blob, SpreadsheetFile
            workbook=SpreadsheetFile.import_xlsx(Blob.load(str(target)))
            preview_dir.mkdir(parents=True,exist_ok=True)
            previews=[]
            for name,area in displays:
                preview=preview_dir/(target.stem+'-'+name+'.png')
                workbook.render({'sheet_name':name,'range':area,'scale':1.4}).save(str(preview))
                previews.append(str(preview))
            evidence['preview']=previews
        except Exception as exc:
            evidence['preview']='not_completed: '+str(exc)
            evidence['warnings'].append('可选 PNG 预览未完成；已生成并回读核对的 Excel 不受影响。')
    return evidence
