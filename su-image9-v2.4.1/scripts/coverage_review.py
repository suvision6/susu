#!/usr/bin/env python3
"""Compare explicit shot/time selections; never infer which process is necessary.

The optional table lives in the SAME image-plan Markdown. It is the author's
pre-pagination sampling decision, not a second creative database. This module
checks its links against panels and, when supplied, an adopted director file.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from master_io import Document, FormatError, source_ids


def key(value: str) -> str:
    value = str(value).strip()
    return str(int(value)) if re.fullmatch(r'\d+', value) else value


def one_source(value: str) -> str:
    if re.search(r'(?:镜头|源镜|源段)\s*\d+\s*(?:—|–|～|~|至|-)\s*\d+', value):
        raise FormatError(f'单格来源不可写为多镜范围：{value}')
    ids = source_ids(value)
    if not ids and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value.strip()):
        ids = [value.strip()]
    distinct = {}
    for sid in ids:
        distinct.setdefault(key(sid), sid)
    if len(distinct) != 1:
        raise FormatError(f'需一个明确源镜编号，不能由范围猜本格来源：{value}')
    return next(iter(distinct.values()))


def selection_table(text: str) -> list[dict[str, Any]] | None:
    """Read three explicit columns, preserving time labels and authored order."""
    doc = Document(text)
    section = doc.raw_section('取帧安排')
    if not section:
        return None
    lines = [line.strip() for line in section.splitlines() if line.strip().startswith('|')]
    if not lines:
        raise FormatError('“取帧安排”存在但没有表格；不可把缺失过程当作0。')
    rows = []
    for line in lines:
        # Escaped literal bars do not act as table separators.
        cells = [c.replace(r'\|', '|').strip() for c in re.split(r'(?<!\\)\|', line.strip().strip('|'))]
        if all(re.fullmatch(r':?-{2,}:?', c or ' ') for c in cells):
            continue
        rows.append(cells)
    if not rows or rows[0] != ['源镜', '必需时点（按镜内时间）', '基准时点']:
        raise FormatError('取帧表列名须为：源镜｜必需时点（按镜内时间）｜基准时点。')
    result, seen = [], set()
    for cells in rows[1:]:
        if len(cells) != 3:
            raise FormatError('取帧表每行需三列；不用额外状态数据库。')
        sid = one_source(cells[0])
        sid_key = key(sid)
        if sid_key in seen:
            raise FormatError(f'取帧安排源镜重复：{sid}')
        seen.add(sid_key)
        states = [s.strip() for s in re.split(r'[；;]', cells[1])]
        baseline = cells[2].strip()
        if any(not s or s in {'无', '—', '-'} or '｜' in s for s in states):
            raise FormatError(f'源镜{sid}必需时点应为非空短名，以分号分隔；不可用“无”代替基准。')
        if len(states) != len(set(states)) or baseline not in states:
            raise FormatError(f'源镜{sid}时点重复或基准不在必需时点中。')
        result.append({'source': sid, 'states': states, 'baseline': baseline})
    if not result:
        raise FormatError('取帧安排不能是空表。')
    return result


def read_director_ids(path: Path) -> tuple[list[str], str]:
    """Read actual IDs, not title, stats, expected count, or user audit wording."""
    raw = path.read_bytes()
    text = raw.decode('utf-8-sig')
    if path.suffix.lower() == '.json':
        data = json.loads(text)
        shots = data.get('shots') if isinstance(data, dict) else None
        if not isinstance(shots, list) or not shots:
            raise FormatError('导演JSON需有实际非空shots列表；核对报告不能代替采用稿。')
        ids = []
        for row in shots:
            if not isinstance(row, dict):
                raise FormatError('导演shots含非对象条目。')
            value = next((row[n] for n in ('id', 'shot_no', 'shot_id') if n in row), None)
            if value is None or isinstance(value, bool) or not isinstance(value, (str, int)):
                raise FormatError('导演镜头缺少明确id/shot_no/shot_id。')
            ids.append(str(value))
    else:
        doc = Document(text)
        ids = [m.group(1) for h in doc.headings
               if h.level == 3 and (m := re.fullmatch(r'镜头\s+(\S+)', h.title))]
        if not ids:
            raise FormatError('未找到采用稿的“### 镜头 编号”；可由Agent读取原材料后提供明确导演JSON，不自动猜镜号。')
    if any(not x.strip() for x in ids) or len({key(x) for x in ids}) != len(ids):
        raise FormatError('导演源镜编号为空或重复（包括前导零等价编号）。')
    return ids, hashlib.sha256(raw).hexdigest()


def role(relation: str) -> str | None:
    text = relation.strip()
    if text.startswith('基准'):
        return 'baseline'
    if text.startswith(('同镜过程', '原镜过程')):
        return 'process'
    if text.startswith(('同刻', '角度延伸', '景别延伸', '备选', '过肩角度延伸', '侧面角度延伸')) or '备选' in text:
        return 'alternate'
    return None


def state_label(moment: str) -> str:
    return moment.split('｜', 1)[0].strip()


def declared_page_ids(text: str) -> list[str] | None:
    """Only understand explicit lists/ranges, never scene prose or vague scopes."""
    text = text.strip()
    if text == '自动':
        return []
    if not re.match(r'^(?:镜头|源镜)\s*[A-Za-z0-9]', text):
        return None
    simple = re.sub(r'(?:镜头|源镜)\s*', '', text)
    out = []
    for token in re.split(r'[、,，]', simple):
        token = token.strip()
        rng = re.fullmatch(r'(\d+)\s*(?:—|–|～|~|至|-)\s*(\d+)', token)
        if rng:
            a, b = map(int, rng.groups())
            if a > b or b - a > 100000:
                raise FormatError('页范围倒序或过大。')
            out.extend(str(n) for n in range(a, b + 1))
        elif re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', token):
            out.append(key(token))
        else:
            return None
    return out


def review_coverage(data: dict[str, Any], director: Path | None = None,
                    source_shots: list[str] | None = None,
                    require_selection: bool = False) -> dict[str, Any]:
    table = selection_table(data['master_text'])
    if require_selection and table is None:
        raise FormatError('全范围交付缺“取帧安排”：先选必需时点，再分页；旧主稿仍可用原入口读取。')
    source_hash, source_all = None, None
    if director is not None:
        source_all, source_hash = read_director_ids(director)
    if source_shots is not None:
        if source_all is None:
            raise FormatError('--source-shots只能在提供--director时选局部范围。')
        selected = [key(x) for x in source_shots]
        available = {key(x): x for x in source_all}
        if len(set(selected)) != len(selected) or any(x not in available for x in selected):
            raise FormatError('选定源镜重复或不在当前导演稿中。')
        expected = [available[x] for x in selected]
        if expected != [x for x in source_all if key(x) in set(selected)]:
            raise FormatError('局部范围必须保留采用稿的播放顺序。')
    else:
        expected = source_all
    if expected is None and table is not None:
        expected = [r['source'] for r in table]
    issues, notes = [], []
    if table and expected and [key(r['source']) for r in table] != [key(x) for x in expected]:
        issues.append({'kind': 'selection_source_mismatch', 'expected': expected,
                       'selected': [r['source'] for r in table]})
    if table is None:
        notes.append('未提供取帧表；不能确认必要过程是否选全。')
    if director is None:
        notes.append('未提供独立导演稿；来源范围仅按本视觉主稿声明，不冒称原片全部覆盖。')
    frames, page_reports = [], []
    page_ids = [p['id'] for p in data['pages']]
    if page_ids != list(map(str, range(1, len(page_ids) + 1))):
        issues.append({'kind': 'page_order_mismatch', 'actual': page_ids})
    for page in data['pages']:
        actual = []
        for p in page['panels']:
            sid = one_source(p['source_ref'])
            if key(sid) not in [key(x) for x in actual]:
                actual.append(sid)
            r = role(p['relation'])
            if r is None:
                issues.append({'kind': 'unknown_panel_relation', 'page': page['id'], 'panel': p['id']})
            frames.append({'page': page['id'], 'panel': p['id'], 'source': sid,
                           'role': r, 'state': state_label(p['moment'])})
        declared = declared_page_ids(page['source_scope'])
        check = 'computed_from_panels' if declared == [] else 'checked' if declared is not None else 'author_text_not_parsed'
        if declared and declared != [key(x) for x in actual]:
            issues.append({'kind': 'page_scope_mismatch', 'page': page['id'],
                           'declared': page['source_scope'], 'actual_source_ids': actual})
        if declared is None:
            notes.append(f'第{page["id"]}页范围说明未按明确编号格式解析；实际来源已从九格计算，不认证原说明。')
        page_reports.append({'page': page['id'], 'source_ids': actual,
                             'source_label': '源镜 ' + '、'.join(actual),
                             'declared_scope_check': check})
    baselines = [p for p in frames if p['role'] == 'baseline']
    if expected is not None:
        expected_keys = [key(x) for x in expected]
        actual_keys = [key(p['source']) for p in baselines]
        if actual_keys != expected_keys:
            issues.append({'kind': 'baseline_coverage_or_order_mismatch', 'expected': expected,
                           'actual': [p['source'] for p in baselines]})
        ranks = {k: i for i, k in enumerate(expected_keys)}
        seq = []
        for p in frames:
            if key(p['source']) not in ranks:
                issues.append({'kind': 'unknown_source', **p})
            else:
                seq.append(ranks[key(p['source'])])
        if seq != sorted(seq):
            issues.append({'kind': 'panels_not_in_source_order'})
    mandatory_count, planned_process, minimum_pages = None, None, None
    if table is not None:
        mandatory_count = sum(len(r['states']) for r in table)
        planned_process = mandatory_count - len(table)
        minimum_pages = (mandatory_count + 8) // 9
        if len(frames) < mandatory_count:
            issues.append({'kind': 'insufficient_page_capacity', 'actual_panels': len(frames),
                           'required_baseline_and_process_panels': mandatory_count})
        for row in table:
            actual = [p for p in frames if key(p['source']) == key(row['source'])]
            required = [p for p in actual if p['role'] in {'baseline', 'process'}]
            if [p['state'] for p in required] != row['states']:
                issues.append({'kind': 'selected_state_coverage_or_order_mismatch', 'source': row['source'],
                               'expected_states': row['states'], 'actual_states': [p['state'] for p in required]})
            for p in required:
                desired = 'baseline' if p['state'] == row['baseline'] else 'process'
                if p['role'] != desired:
                    issues.append({'kind': 'baseline_time_mismatch', **p})
            for p in actual:
                if p['role'] == 'alternate' and p['state'] not in row['states']:
                    issues.append({'kind': 'alternate_time_not_selected', **p})
    return {
        'status': 'explicit_mapping_checked' if not issues else 'review_required',
        'source_check': 'independent_file_ids_checked' if director else 'declared_scope_only',
        'director_sha256': source_hash,
        'director_record_count': len(source_all) if source_all is not None else None,
        'scope_source_ids': expected,
        'counts': {'source_baselines_expected': len(expected) if expected is not None else None,
                   'source_baselines_present': len(baselines), 'selected_process_required': planned_process,
                   'process_present': sum(p['role'] == 'process' for p in frames),
                   'alternates_present': sum(p['role'] == 'alternate' for p in frames),
                   'minimum_capacity_pages': minimum_pages, 'pages': len(data['pages']), 'panels': len(frames)},
        'page_map': page_reports, 'issues': issues, 'notes': notes,
        'selection_semantics': 'not_verified_by_script',
        'semantic_review': 'not_performed_by_script',
        'image_review': 'not_performed',
    }
