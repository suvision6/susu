"""Read the three agreed Markdown templates; never rewrite creative prose.

Only the Python standard library is imported here. Spreadsheet support is lazy.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any


class FormatError(ValueError):
    """A local, actionable template error, not a creative judgement."""


@dataclass
class Heading:
    level: int
    title: str
    line: int
    start: int
    body: int
    end: int = 0


class Document:
    def __init__(self, text: str):
        self.text = text.replace('\r\n', '\n').replace('\r', '\n')
        self.lines = self.text.splitlines(keepends=True)
        self.headings: list[Heading] = []
        self.fences: list[tuple[int, int, str]] = []
        offsets, pos = [], 0
        for line in self.lines:
            offsets.append(pos)
            pos += len(line)
        opened = None
        for i, line in enumerate(self.lines):
            raw = line.rstrip('\n')
            if opened is not None:
                start_i, marker, info = opened
                if re.fullmatch(re.escape(marker[0]) + '{' + str(len(marker)) + r',}\s*', raw):
                    payload = ''.join(self.lines[start_i + 1:i])
                    if payload.endswith('\n'):
                        payload = payload[:-1]
                    self.fences.append((offsets[start_i], offsets[i] + len(line), payload))
                    opened = None
                continue
            fm = re.fullmatch(r'(`{3,}|~{3,})([^`~]*)', raw)
            if fm:
                opened = (i, fm.group(1), fm.group(2).strip())
                continue
            hm = re.fullmatch(r'(#{1,6}) +(.+?)\s*', raw)
            if hm:
                self.headings.append(Heading(len(hm.group(1)), hm.group(2), i + 1,
                                             offsets[i], offsets[i] + len(line)))
        if opened:
            raise FormatError(f'第 {opened[0] + 1} 行：正文围栏没有关闭。')
        for i, h in enumerate(self.headings):
            h.end = next((n.start for n in self.headings[i + 1:] if n.level <= h.level), len(self.text))
        roots = [h for h in self.headings if h.level == 1]
        if len(roots) != 1:
            raise FormatError('主稿需有且只有一个一级项目标题；正文中的标题请放在文本围栏内。')
        self.root = roots[0]

    def find(self, title: str, level: int = 2, parent: Heading | None = None,
             required: bool = False) -> Heading | None:
        matches = [h for h in self.headings if h.title == title and h.level == level
                   and (parent is None or parent.body <= h.start < parent.end)]
        if len(matches) > 1:
            raise FormatError(f'第 {matches[1].line} 行：重复栏目 {title}。')
        if not matches:
            if required:
                raise FormatError(f'缺少栏目：{title}。')
            return None
        return matches[0]

    def raw_section(self, title: str) -> str:
        h = self.find(title)
        return self.text[h.body:h.end].strip('\n') if h else ''

    def before_children(self, h: Heading) -> str:
        end = next((x.start for x in self.headings if h.body <= x.start < h.end), h.end)
        return self.text[h.body:end]

    def field(self, fragment: str, label: str, location: str, required: bool = True) -> str:
        matches = re.findall(r'^' + re.escape(label) + r'[：:]([^\n]*)$', fragment, re.M)
        if len(matches) > 1:
            raise FormatError(f'{location}：字段 {label} 重复。')
        if not matches or not matches[0].strip():
            if required:
                raise FormatError(f'{location}：缺少 {label}。')
            return ''
        return matches[0].strip()

    def fenced(self, h: Heading, allow_empty: bool = False) -> str:
        items = [(s, e, p) for s, e, p in self.fences if h.body <= s < h.end]
        if len(items) != 1:
            raise FormatError(f'第 {h.line} 行，{h.title}：需一个完整文本围栏。')
        text = items[0][2]
        if not allow_empty and not text.strip():
            raise FormatError(f'第 {h.line} 行，{h.title}：正文为空。')
        return text


def duration(value: str, where: str) -> int | float | None:
    value = value.strip()
    if value in {'暂未确定', '未定', '未知', '待定'}:
        return None
    numeric = re.sub(r'\s*秒$', '', value)
    if not re.fullmatch(r'\d+(?:\.\d+)?', numeric):
        raise FormatError(f'{where}：时长请写正数秒或“暂未确定”，当前为 {value!r}。')
    number = Decimal(numeric)
    if number <= 0 or not math.isfinite(float(number)) or float(number) == 0:
        raise FormatError(f'{where}：时长必须为有限正数；未知不要填 0。')
    return int(number) if number == number.to_integral() else float(number)


def source_ids(text: str) -> list[str]:
    # Extract ONLY explicit locators; do not interpret arbitrary narrative numbers.
    return re.findall(r'(?:镜头|源镜|源段)\s*([A-Za-z0-9][A-Za-z0-9_.-]*)', text)


def parse_master(path: str | Path, kind: str) -> dict[str, Any]:
    path = Path(path).resolve()
    raw = path.read_bytes()
    try:
        doc = Document(raw.decode('utf-8-sig'))
    except UnicodeDecodeError as exc:
        raise FormatError('主稿必须为 UTF-8 文本。') from exc
    head = doc.before_children(doc.root)
    field = lambda label, req=True: doc.field(head, label, '项目说明', req)
    origin, scope = field('本轮来源'), field('本轮范围')
    links = re.findall(r'\[[^\]]*\]\(([^)]+)\)', origin)
    data: dict[str, Any] = {
        'kind': kind, 'title': doc.root.title, 'master': str(path),
        'master_sha256': hashlib.sha256(raw).hexdigest(),
        'sources': [{'locator': x, 'scope': scope} for x in links],
        'source_description': origin, 'scope': scope,
        'master_text': doc.text, 'warnings': []
    }
    if not links:
        data['sources'] = [{'locator': str(path) + ('#来源依据' if kind == 'director' else ''), 'scope': scope}]
    if kind == 'director':
        context = field('项目条件')
        doc.find('导演设计', required=True)
        data['context'] = '项目条件：' + context + '\n\n' + doc.raw_section('导演设计')
        data['source_basis'] = doc.raw_section('来源依据')
        data['working_notes'] = doc.raw_section('工作续记')
        group = doc.find('分镜', required=True)
        records = [h for h in doc.headings if h.level == 3 and group.body <= h.start < group.end]
        data['shots'] = []
        for h in records:
            m = re.fullmatch(r'镜头\s+(\S+)', h.title)
            if not m:
                raise FormatError(f'第 {h.line} 行：分镜区仅使用“### 镜头 <镜号>”。')
            info, where = doc.before_children(h), f'第 {h.line} 行，{h.title}'
            get = lambda label: doc.field(info, label, where)
            d = get('预计时长')
            parts = {}
            for label, key in [('原剧本段落', 'source_text'), ('运镜＋主画面描述', 'body'), ('备注', 'notes')]:
                node = doc.find(label, 4, h, required=True)
                parts[key] = doc.fenced(node, allow_empty=(key == 'notes'))
            data['shots'].append({'id': m.group(1), 'scene': get('场景'),
                                  'duration_seconds': duration(d, where), 'duration_text': d, **parts})
        rows = data['shots']
    elif kind == 'image':
        data['task'] = field('本次任务')
        doc.find('共用视觉依据', required=True)
        data['context'] = '画幅与媒介：' + field('画幅与媒介') + '\n\n' + doc.raw_section('共用视觉依据')
        data['execution_notes'] = doc.raw_section('执行与选用')
        data['pages'] = []
        for h in doc.headings:
            m = re.fullmatch(r'第\s*(\d+)\s*页', h.title)
            if h.level != 2 or not m:
                continue
            info, where = doc.before_children(h), f'第 {h.line} 行，{h.title}'
            page = {'id': m.group(1), 'source_scope': doc.field(info, '本页范围', where),
                    'body': doc.field(info, '页面说明', where), 'panels': []}
            for p in [x for x in doc.headings if x.level == 3 and h.body <= x.start < h.end]:
                pm = re.fullmatch(r'格\s+(\d+)', p.title)
                if not pm:
                    raise FormatError(f'第 {p.line} 行：页面内使用“### 格 <格号>”。')
                fstart = next((s for s, _, _ in doc.fences if p.body <= s < p.end), p.end)
                info = doc.text[p.body:fstart]
                get = lambda label: doc.field(info, label, f'第 {p.line} 行，{p.title}')
                src = get('对应来源')
                page['panels'].append({'id': pm.group(1), 'source_ref': src,
                    'source_refs': source_ids(src), 'relation': get('画面关系'),
                    'moment': get('所取时点'), 'body': doc.fenced(p)})
            if [x['id'] for x in page['panels']] != [str(i) for i in range(1, 10)]:
                raise FormatError(f'{where}：每页需按 1—9 排列九个非空画面；不自动补图或重排。')
            data['pages'].append(page)
        rows = data['pages']
    elif kind == 'prompt':
        data['task'] = field('本次任务')
        data['context'] = '项目条件：' + field('项目条件') + '\n执行条件：' + field('执行条件')
        data['continuity_notes'] = doc.raw_section('跨单元衔接')
        data['delivery_notes'] = doc.raw_section('交付说明')
        data['units'] = []
        for h in doc.headings:
            m = re.fullmatch(r'单元\s+(\S+)', h.title)
            if h.level != 2 or not m:
                continue
            info, where = doc.before_children(h), f'第 {h.line} 行，{h.title}'
            get = lambda label: doc.field(info, label, where)
            src, d = get('对应来源'), get('内容预计时长')
            note = doc.find('素材与提交说明', 3, h, required=True)
            body = doc.find('Prompt', 3, h, required=True)
            data['units'].append({'id': m.group(1), 'source_refs': source_ids(src),
                'source_scope': src, 'duration_seconds': duration(d, where), 'duration_text': d,
                'submission_notes': doc.text[note.body:note.end].strip('\n'), 'body': doc.fenced(body)})
        rows = data['units']
    else:
        raise FormatError(f'未知主稿类别：{kind}')
    if not rows:
        raise FormatError('主稿没有找到完整的镜头、页或单元。')
    seen = set()
    for row in rows:
        if row['id'] in seen:
            raise FormatError(f'重复编号 {row["id"]}；请局部修正，不重排正文。')
        seen.add(row['id'])
    # Unmapped additions are retained, but are not silently certified as parsed.
    if kind == 'director':
        allowed = {'原剧本段落', '运镜＋主画面描述', '备注'}
        extra = [h for h in doc.headings if h.level == 4 and h.title not in allowed
                 and any(r.body <= h.start < r.end for r in records)]
    elif kind == 'prompt':
        extra = [h for h in doc.headings if h.level == 3 and h.title not in {'素材与提交说明', 'Prompt'}
                 and any(r.level == 2 and r.title.startswith('单元 ') and r.body <= h.start < r.end for r in doc.headings)]
    else:
        extra = []
    for h in extra:
        data['warnings'].append(f'第 {h.line} 行，附加栏目“{h.title}”保存在 master_text 中，未作为独立执行字段解释；由 Agent 回读。')
    data['statistics'] = statistics(data)
    return data


def statistics(data: dict[str, Any]) -> dict[str, Any]:
    if data['kind'] == 'image':
        return {'pages': len(data['pages']), 'panels': sum(len(p['panels']) for p in data['pages'])}
    rows = data.get('shots', data.get('units', []))
    vals = [Decimal(re.sub(r'\s*秒$', '', r['duration_text'])) for r in rows if r['duration_seconds'] is not None]
    total = sum(vals, Decimal(0))
    unknown = len(rows) - len(vals)
    return {'records': len(rows), 'known_duration_seconds': str(total),
            'unknown_duration_count': unknown, 'total_duration_seconds': None if unknown else str(total)}


def save_exclusive(path: Path, content: bytes) -> None:
    """Publish one new file without truncating an existing delivery."""
    if path.exists():
        if path.read_bytes() == content:
            return
        raise FileExistsError(f'已有不同内容文件：{path.name}。使用新前缀，不覆盖人类修改。')
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(handle, 'wb') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        # Hard-link publication is atomic and cannot replace an existing target.
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def cli(kind: str) -> int:
    ap = argparse.ArgumentParser(description='从已保存主稿派生；不重写、估时或判断导演质量。')
    ap.add_argument('--input', required=True, type=Path)
    ap.add_argument('--check', action='store_true', help='仅结构、明确字段与合计；不需要 Excel 库')
    ap.add_argument('--output-dir', type=Path)
    ap.add_argument('--prefix')
    ap.add_argument('--json-only', action='store_true')
    ap.add_argument('--width-px', type=int, default=1480)
    ap.add_argument('--font', default='Noto Sans CJK SC')
    ap.add_argument('--font-size', type=float, default=11)
    ap.add_argument('--preview-dir', type=Path, help='可选排版预览，不是故事板生图')
    args = ap.parse_args()
    try:
        data = parse_master(args.input, kind)
        if args.check:
            print(json.dumps({'structure': 'checked', **data['statistics'],
                              'semantic_review': 'not_performed_by_script', 'template_notes': data['warnings']}, ensure_ascii=False, indent=2))
            return 0
        folder = (args.output_dir or args.input.parent).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        prefix = args.prefix or args.input.stem
        if prefix in {'.', '..'} or any(c in prefix for c in '/\\\x00'):
            raise FormatError('前缀必须是文件名，不能包含目录。')
        data['master'] = os.path.relpath(args.input.resolve(), folder)
        for source in data['sources']:
            if source['locator'].startswith(str(args.input.resolve())):
                source['locator'] = source['locator'].replace(str(args.input.resolve()), data['master'], 1)
        data['source_link_base'] = 'relative to master, not JSON directory'
        target = folder / (prefix + '.json')
        payload = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8') + b'\n'
        save_exclusive(target, payload)
        if json.loads(target.read_text('utf-8')) != data:
            raise ValueError('JSON 回读不一致。')
        result = {'template_notes': data['warnings'], 'json': str(target), 'master_unchanged': str(args.input), **data['statistics']}
        if kind != 'image' and not args.json_only:
            try:
                from reading_xlsx import export_reading
                result['excel'] = export_reading(data, folder / (prefix + '.xlsx'),
                    args.width_px, args.font, args.font_size, args.preview_dir)
            except Exception as exc:
                result['excel'] = {'status': 'not_completed', 'reason': str(exc)}
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(f'未完成派生：{exc}', file=__import__('sys').stderr)
        return 1
