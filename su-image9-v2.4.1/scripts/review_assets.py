#!/usr/bin/env python3
"""Add image revisions and director decisions to the EXISTING prompt-set manifest.

This is a local bookkeeping tool, not an image generator or semantic reviewer.
It cannot authenticate a human: decision evidence must quote an actual user
instruction, never an Agent's own approval or approval of a Skill upgrade.
Pillow is imported only when an image is registered/decoded.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

from coverage_review import one_source, role, selection_table, state_label, key
from master_io import FormatError, save_exclusive
from prepare_prompt_set import verify_saved_set

REVIEW_FORMAT = 'su-image9-review/1'
ROLE_ZH = {'baseline': '基准', 'process': '过程', 'alternate': '同刻延展'}
STATE_ZH = {'pending': '待审', 'needs_changes': '需改', 'approved': '已确认',
            'missing': '缺图', 'stale': '需重新确认'}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def rel(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path.resolve(), base.resolve())).as_posix()


def resolve(base: Path, locator: str) -> Path:
    return (base / locator).resolve()


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text('utf-8'))
    if data.get('format') != 'su-image9-prompt-set/1':
        raise FormatError('需现有prompt-set-manifest.json，不接受覆盖报告或单页输入。')
    return data


def write_manifest(path: Path, data: dict[str, Any], expected: bytes) -> None:
    """Atomic update with a local lock and original-byte check; keep a history copy."""
    path = path.resolve()
    lock = path.with_name(path.name + '.lock')
    fd = None
    owned = False
    temp = None
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        owned = True
        os.close(fd)
        fd = None
        if path.read_bytes() != expected:
            raise FormatError('清单已被其他任务修改；本次未覆盖，请重新读取。')
        archive = path.parent / 'review-history' / (digest(expected) + '.json')
        save_exclusive(archive, expected)
        sync_summary(path, data)
        raw = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8') + b'\n'
        h, name = tempfile.mkstemp(prefix='.review-', dir=path.parent)
        temp = Path(name)
        with os.fdopen(h, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        temp = None
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
        # Do not remove a lock another process owns if exclusive creation failed.
        if fd is not None:
            os.close(fd)
        if owned:
            lock.unlink(missing_ok=True)


def alphabet(index: int) -> str:
    """0 -> a, 25 -> z, 26 -> aa; presentation only, not a shot renumbering."""
    out = ''
    while True:
        out = chr(97 + index % 26) + out
        index = index // 26 - 1
        if index < 0:
            return out


def parse_ratio(text: str) -> list[float] | None:
    match = re.search(r'(?<![\d.])(\d+(?:\.\d+)?)\s*[:：]\s*(\d+(?:\.\d+)?)(?![\d.])', text)
    if not match:
        return None
    w, h = map(float, match.groups())
    if w <= 0 or h <= 0 or w / h < .05 or w / h > 20:
        raise FormatError('有效画幅必须为合理正数比例。')
    return [w, h]


def load_plan(manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    plan = manifest_path.parent / 'image-plan.json'
    data = json.loads(plan.read_text('utf-8'))
    if data.get('kind') != 'image' or not data.get('pages'):
        raise FormatError('清单同目录缺少完整image-plan.json。')
    if data.get('master_sha256') != manifest['source']['image_master_sha256']:
        raise FormatError('视觉主稿与本Prompt清单不是同一版本。')
    return data


def build_catalog(data: dict[str, Any], namespace: str,
                  director_hash: str | None = None) -> list[dict[str, Any]]:
    """Derive labels from explicitly authored times, not from image recognition."""
    table = selection_table(data['master_text'])
    rows = {key(r['source']): r for r in table or []}
    flattened = []
    for page in data['pages']:
        if [p['id'] for p in page['panels']] != list(map(str, range(1, 10))):
            raise FormatError(f'第{page["id"]}页不是按序完整九格。')
        for panel in page['panels']:
            p = copy.deepcopy(panel)
            p['page'] = str(page['id'])
            # Page prose can contain the effective blocking state for this page.
            # Its content (not page number) must invalidate stale image decisions.
            p['_page_context'] = page.get('body', '')
            p['slot'] = str(p.pop('id'))
            p['source_id'] = one_source(p['source_ref'])
            p['kind'] = role(p['relation'])
            p['moment_key'] = state_label(p['moment'])
            if p['kind'] is None:
                raise FormatError('无法确定基准/过程/同刻延展：' + p['relation'])
            flattened.append(p)
    original_ids = {p['source_id'] for p in flattened}
    times: dict[str, list[str]] = {}
    for p in flattened:
        sid = key(p['source_id'])
        if sid in rows:
            times[sid] = rows[sid]['states']
        elif p['kind'] != 'alternate':
            times.setdefault(sid, [])
            if p['moment_key'] not in times[sid]:
                times[sid].append(p['moment_key'])
    alternatives: dict[tuple[str, str], int] = {}
    result = []
    labels = set()
    uids = set()
    source_identity = data.get('source_description', '')
    for p in flattened:
        sid_key = key(p['source_id'])
        states = times.get(sid_key, [])
        if p['moment_key'] not in states:
            raise FormatError(f'源镜{p["source_id"]}的延展缺明确同刻锚点；先统一所取时点短名。')
        # Display the exact spelling used by the author, including existing suffixes.
        sid = rows[sid_key]['source'] if sid_key in rows else p['source_id']
        if len(states) == 1:
            anchor = sid
        else:
            suffix = alphabet(states.index(p['moment_key']))
            anchor = sid + ('' if sid.isdigit() else '.') + suffix
            if anchor in original_ids:
                anchor = sid + '.' + suffix
        identity = [namespace, source_identity, sid, p['moment_key'],
                    'alternate' if p['kind'] == 'alternate' else 'required']
        label = anchor
        if p['kind'] == 'alternate':
            counter = (sid, p['moment_key'])
            alternatives[counter] = alternatives.get(counter, 0) + 1
            label += '-E' + str(alternatives[counter])
            # Alternate composition is part of its identity, not its page position.
            identity.append(p['body'])
        uid = 'F-' + digest(canonical(identity))[:20]
        if label in labels or uid in uids:
            raise FormatError('重复的画格身份或标签：' + label + '。不能把同一描述重新编号充作另一画格。')
        labels.add(label)
        uids.add(uid)
        ratio = parse_ratio(p['body']) or parse_ratio(data.get('context', ''))
        if ratio is None:
            raise FormatError('找不到有效画幅：' + label + '；在主稿中明确比例，不默选16:9。')
        spec = {k: p[k] for k in ['source_ref', 'relation', 'moment', 'body']}
        spec.update(shared_context=data.get('context', ''), page_context=p['_page_context'], director_sha256=director_hash,
                    frame_ratio=ratio)
        result.append({
            'uid': uid, 'label': label, 'source_id': sid, 'source_ref': p['source_ref'],
            'page': p['page'], 'slot': p['slot'], 'kind': p['kind'],
            'moment_key': p['moment_key'], 'moment': p['moment'], 'body': p['body'],
            'frame_ratio': ratio, 'spec_sha256': digest(canonical(spec)),
            'versions': [], 'selected_revision': None,
        })
    return result


def init_review(path: Path, project: str | None = None, previous: Path | None = None) -> dict[str, Any]:
    manifest = load_manifest(path)
    verify_saved_set(path.parent)
    if 'review' in manifest:
        raise FormatError('本清单已初始化；不能重置已有图片或确认。改稿后用新Prompt目录并携带旧清单。')
    data = load_plan(path, manifest)
    old_manifest = load_manifest(previous) if previous else None
    old_review = old_manifest.get('review') if old_manifest else None
    namespace = project or (old_review or {}).get('project') or data['title']
    catalog = build_catalog(data, namespace, manifest['source'].get('director_sha256'))
    previous_by_uid = {p['uid']: p for p in old_review['panels']} if old_review else {}
    carried = changed = 0
    for p in catalog:
        old = previous_by_uid.get(p['uid'])
        if old is None:
            continue
        p['versions'] = copy.deepcopy(old['versions'])
        p['selected_revision'] = old['selected_revision']
        for version in p['versions']:
            # Reuse files without re-encoding them. New request folder may differ.
            for k in ['path', 'raw_path', 'call_record_path']:
                if version.get(k):
                    version[k] = rel(resolve(previous.parent, version[k]), path.parent)
        if p['spec_sha256'] == old['spec_sha256'] and p['label'] == old['label']:
            carried += 1
        else:
            changed += 1
            for v in p['versions']:
                if v.get('decision', {}).get('status') == 'approved':
                    v.setdefault('decision_history', []).append(copy.deepcopy(v['decision']))
                    v['decision'] = {'status': 'pending', 'reason': '采用描述或标签改变，原确认不沿用'}
    manifest['review'] = {
        'format': REVIEW_FORMAT, 'project': namespace, 'title': data['title'],
        'plan_sha256': manifest['source']['image_master_sha256'],
        'created_at': now(), 'panels': catalog,
        'history': [{'at': now(), 'operation': 'init', 'carried_unchanged': carried,
                     'changed_require_review': changed}],
        'boundary': '标签与文件核对不是语义或视觉认证；用户确认必须来自真实指令。',
    }
    return manifest


def assert_review_current(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    review = manifest.get('review', {})
    if review.get('format') != REVIEW_FORMAT:
        raise FormatError('请先init审阅清单；不能以生成成功代替确认。')
    if review.get('plan_sha256') != manifest['source'].get('image_master_sha256'):
        raise FormatError('清单审阅记录对应旧主稿；改稿后重新初始化并显式携带旧记录。')
    plan = load_plan(path, manifest)
    current = build_catalog(plan, review['project'], manifest['source'].get('director_sha256'))
    expected = [(x['uid'], x['spec_sha256'], x['label'], x['page'], x['slot']) for x in current]
    stored = [(x['uid'], x['spec_sha256'], x['label'], x['page'], x['slot']) for x in review['panels']]
    if expected != stored:
        raise FormatError('当前来源/时点/页面映射与审阅记录不一致；不把旧确认套给新格。')
    return review


def select_panels(review: dict[str, Any], labels: list[str] | None, all_panels: bool = False) -> list[dict[str, Any]]:
    if all_panels:
        if labels:
            raise FormatError('--all与--labels不可同时使用。')
        return review['panels']
    if not labels:
        raise FormatError('需--labels指定实际标签，或在明确批次指令下用--all。')
    requested = set(labels)
    if len(requested) != len(labels):
        raise FormatError('标签重复。')
    found = [p for p in review['panels'] if p['label'] in requested or p['uid'] in requested]
    if len(found) != len(requested):
        raise FormatError('有标签不存在或不唯一；先运行status读取本版标签。')
    return found


def selected_version(panel: dict[str, Any]) -> dict[str, Any] | None:
    matches = [v for v in panel['versions'] if v['revision'] == panel['selected_revision']]
    if len(matches) > 1:
        raise FormatError('修订编号重复。')
    return matches[0] if matches else None


def pillow():
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise FormatError('登记/排版图片需Pillow。按requirements-review.txt安装；文字与Prompt功能不受影响。') from exc
    return Image, ImageOps


def read_image(path: Path):
    Image, ImageOps = pillow()
    with Image.open(path) as im:
        if getattr(im, 'n_frames', 1) != 1:
            raise FormatError('预演画格需单帧图片，不能把动画第一帧静默当完整结果。')
        im.load()
        im = ImageOps.exif_transpose(im)
        if 'A' in im.getbands() or 'transparency' in im.info:
            rgba = im.convert('RGBA')
            base = Image.new('RGBA', rgba.size, (255, 255, 255, 255))
            im = Image.alpha_composite(base, rgba).convert('RGB')
        else:
            im = im.convert('RGB')
        return im.copy()


def store_version(path: Path, panel: dict[str, Any], image, raw_path: Path,
                  model: str | None = None, tool: str | None = None,
                  call_record: Path | None = None, crop_box: list[int] | None = None) -> dict[str, Any]:
    if image.width < 1 or image.height < 1:
        raise FormatError('图片有效区域为空。')
    numbers = [int(v['revision'][1:]) for v in panel['versions']]
    revision = f'r{max(numbers, default=0) + 1:02d}'
    raw = raw_path.read_bytes()
    extension = raw_path.suffix.lower() if re.fullmatch(r'\.[a-z0-9]{1,8}', raw_path.suffix.lower()) else '.bin'
    raw_target = path.parent / 'review-assets' / 'raw' / (digest(raw) + extension)
    save_exclusive(raw_target, raw)
    buf = io.BytesIO()
    image.save(buf, format='PNG')  # Lossless decoded pixels; original bytes are kept above.
    asset = path.parent / 'review-assets' / panel['uid'] / (revision + '.png')
    save_exclusive(asset, buf.getvalue())
    record_path = None
    record_hash = None
    if call_record:
        record_raw = call_record.read_bytes()
        record_target = path.parent / 'review-assets' / 'calls' / (digest(record_raw) + '.txt')
        save_exclusive(record_target, record_raw)
        record_path, record_hash = rel(record_target, path.parent), digest(record_raw)
    item = {
        'revision': revision, 'path': rel(asset, path.parent), 'sha256': digest(buf.getvalue()),
        'width': image.width, 'height': image.height, 'raw_path': rel(raw_target, path.parent),
        'raw_sha256': digest(raw), 'crop_box': crop_box,
        'spec_sha256': panel['spec_sha256'], 'created_at': now(),
        'tool': tool or 'not_reported', 'model_reported': model or 'not_exposed',
        'model_verification': 'operator_report_only' if model else 'not_available',
        'call_record_path': record_path, 'call_record_sha256': record_hash,
        'actual_prompt_verification': 'not_performed_by_script',
        'agent_review': {'status': 'not_reviewed'},
        'decision': {'status': 'pending'}, 'decision_history': [],
    }
    panel['versions'].append(item)
    panel['selected_revision'] = revision
    return item


def register_image(path: Path, manifest: dict[str, Any], label: str, image_path: Path,
                   **kwargs) -> dict[str, Any]:
    review = assert_review_current(path, manifest)
    panel = select_panels(review, [label])[0]
    im = read_image(image_path)
    store_version(path, panel, im, image_path, **kwargs)
    review['history'].append({'at': now(), 'operation': 'register', 'uid': panel['uid'],
                              'revision': panel['selected_revision']})
    return panel


def register_sheet(path: Path, manifest: dict[str, Any], page: str, image_path: Path,
                   boxes: dict[str, list[int]], **kwargs) -> None:
    review = assert_review_current(path, manifest)
    panels = [p for p in review['panels'] if p['page'] == str(page)]
    if len(panels) != 9 or set(boxes) != set(map(str, range(1, 10))):
        raise FormatError('整页登记需九个真实有效区域，box按格1—9给出；不自动三等分。')
    im = read_image(image_path)
    rects = []
    for p in panels:
        box = boxes[p['slot']]
        if (len(box) != 4 or any(isinstance(v, bool) or not isinstance(v, int) for v in box)):
            raise FormatError('box需四个整数left,top,right,bottom；不猜边框和格缝。')
        l, t, r, b = box
        if not (0 <= l < r <= im.width and 0 <= t < b <= im.height):
            raise FormatError('有效画框超出原图或为空：格' + p['slot'])
        for a, c, d, e in rects:
            if min(r, d) > max(l, a) and min(b, e) > max(t, c):
                raise FormatError('有效画框互相重叠，不能把同一区域当两个格。')
        rects.append(box)
    # The provided boxes must follow the actual visual grid's reading order.
    for row in range(3):
        group = rects[row * 3:row * 3 + 3]
        if not all((group[i][0] + group[i][2]) < (group[i+1][0] + group[i+1][2]) for i in range(2)):
            raise FormatError('同一行box未按左到右排列，不以正确标签掩盖交换画面。')
    for col in range(3):
        group = [rects[row * 3 + col] for row in range(3)]
        if not all((group[i][1] + group[i][3]) < (group[i+1][1] + group[i+1][3]) for i in range(2)):
            raise FormatError('box未按上到下排列。')
    for p in panels:
        box = boxes[p['slot']]
        store_version(path, p, im.crop(tuple(box)), image_path, crop_box=box, **kwargs)
    review['history'].append({'at': now(), 'operation': 'register_sheet', 'page': str(page)})


def version_health(path: Path, panel: dict[str, Any], version: dict[str, Any] | None) -> list[str]:
    if version is None:
        return ['missing_image']
    problems = []
    actual = resolve(path.parent, version['path'])
    if not actual.is_file() or digest(actual.read_bytes()) != version['sha256']:
        problems.append('image_file_missing_or_changed')
    if version.get('spec_sha256') != panel['spec_sha256']:
        problems.append('image_based_on_old_plan')
    if version.get('width', 0) <= 0 or version.get('height', 0) <= 0:
        problems.append('invalid_image_dimensions')
    else:
        actual_ratio = version['width'] / version['height']
        expected_ratio = panel['frame_ratio'][0] / panel['frame_ratio'][1]
        # Tolerate one-pixel crop rounding, not arbitrary reformatting.
        tolerance = max(.003, 2 / min(version['width'], version['height']))
        if abs(actual_ratio / expected_ratio - 1) > tolerance:
            problems.append('frame_ratio_mismatch')
    return problems


def effective_status(path: Path, panel: dict[str, Any]) -> str:
    v = selected_version(panel)
    if v is None:
        return 'missing'
    if version_health(path, panel, v):
        return 'stale'
    d = v.get('decision', {})
    if d.get('status') == 'approved':
        if (d.get('image_sha256') != v['sha256'] or d.get('spec_sha256') != panel['spec_sha256']
                or d.get('label') != panel['label'] or not d.get('evidence', '').strip()):
            return 'stale'
    return d.get('status', 'pending')


def make_decision(path: Path, manifest: dict[str, Any], labels: list[str] | None,
                  status: str, evidence: str, all_panels: bool = False) -> None:
    if status not in {'pending', 'needs_changes', 'approved'} or not evidence.strip():
        raise FormatError('需真实用户反馈/确认原话及状态；Agent自检不能生成导演确认。')
    review = assert_review_current(path, manifest)
    panels = select_panels(review, labels, all_panels)
    for p in panels:
        v = selected_version(p)
        if v is None:
            raise FormatError('缺少实际选用图片：' + p['label'])
        health = version_health(path, p, v)
        if status == 'approved' and health:
            raise FormatError(p['label'] + '无法确认陈旧/缺失/错误画幅的文件：' + ','.join(health))
    for p in panels:
        v = selected_version(p)
        v['decision_history'].append(copy.deepcopy(v['decision']))
        v['decision'] = {'status': status, 'evidence': evidence.strip(), 'at': now(),
                         'image_sha256': v['sha256'], 'spec_sha256': p['spec_sha256'],
                         'label': p['label'], 'recorded_by': 'operator',
                         'authentication': 'not_independently_verified'}
    review['history'].append({'at': now(), 'operation': 'user_decision_record',
                              'labels': [p['label'] for p in panels], 'status': status})


def select_revision(path: Path, manifest: dict[str, Any], label: str, revision: str) -> None:
    review = assert_review_current(path, manifest)
    panel = select_panels(review, [label])[0]
    if revision not in {v['revision'] for v in panel['versions']}:
        raise FormatError('所选修订不存在；不会自动选择日期最新文件。')
    panel['selected_revision'] = revision
    review['history'].append({'at': now(), 'operation': 'select_revision',
                              'uid': panel['uid'], 'revision': revision})


def agent_check(path: Path, manifest: dict[str, Any], labels: list[str] | None,
                status: str, note: str, all_panels: bool = False) -> None:
    if status not in {'passed', 'needs_changes', 'not_reviewed'} or not note.strip():
        raise FormatError('Agent检查需要实际观察说明；不能只记PASS。')
    review = assert_review_current(path, manifest)
    panels = select_panels(review, labels, all_panels)
    for p in panels:
        if selected_version(p) is None:
            raise FormatError('缺实际图片，不能填写看图结果：' + p['label'])
    for p in panels:
        v = selected_version(p)
        v['agent_review'] = {'status': status, 'note': note, 'at': now(),
                             'image_sha256': v['sha256'], 'spec_sha256': p['spec_sha256']}
    # Never change director decisions here.


def report(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    review = assert_review_current(path, manifest)
    panels = []
    counts = {s: 0 for s in STATE_ZH}
    for p in review['panels']:
        state = effective_status(path, p)
        counts[state] = counts.get(state, 0) + 1
        panels.append({'label': p['label'], 'uid': p['uid'], 'page': p['page'], 'slot': p['slot'],
                       'kind': p['kind'], 'moment': p['moment_key'], 'revision': p['selected_revision'],
                       'status': state, 'file_problems': version_health(path, p, selected_version(p))})
    return {'project': review['project'], 'counts': counts, 'panels': panels,
            'ready_for_final_pdf': all(p['status'] == 'approved' for p in panels),
            'semantic_review': 'not_performed_by_script',
            'user_authentication': 'not_independently_verified'}


def sync_summary(path: Path, manifest: dict[str, Any]) -> None:
    """Keep the existing page status readable without inventing model-call evidence."""
    review = manifest.get('review')
    if not review:
        return
    manifest.setdefault('planning_status', manifest.get('status'))
    manifest.setdefault('planning_checks', copy.deepcopy(manifest.get('checks', {})))
    selected = [p for p in review['panels'] if selected_version(p) is not None]
    for page in manifest['pages']:
        panels = [p for p in selected if p['page'] == page['page']]
        page.setdefault('planning_model_call', page.get('model_call', 'not_performed'))
        page['image_files'] = [dict(uid=p['uid'], label=p['label'],
                                   path=selected_version(p)['path'],
                                   revision=p['selected_revision'],
                                   sha256=selected_version(p)['sha256'],
                                   user_status=effective_status(path, p)) for p in panels]
        if panels:
            page['model_call'] = 'external_output_registered_call_not_verified_by_script'
            page['actual_call_record'] = [selected_version(p)['call_record_path'] for p in panels
                                          if selected_version(p).get('call_record_path')] or None
            page['image_review'] = 'see_per_image_agent_and_director_records'
    approved = sum(effective_status(path, p) == 'approved' for p in review['panels'])
    manifest['status'] = ('all_selected_images_user_approved' if approved == len(review['panels'])
                          else 'images_registered_review_in_progress' if selected
                          else manifest['planning_status'])
    manifest['checks']['image_review'] = 'per_image_operator_records_not_script_visual_verification'
    if selected:
        manifest['checks']['model_calls'] = 'external_outputs_registered_calls_not_verified_by_script'


def main() -> int:
    ap = argparse.ArgumentParser(description='同一Prompt清单中的镜号、实际图像修订与用户批量选用；不生图。')
    ap.add_argument('action', choices=['init', 'register', 'register-sheet', 'agent-check', 'decide', 'select', 'status'])
    ap.add_argument('--manifest', type=Path, required=True)
    ap.add_argument('--project')
    ap.add_argument('--previous-manifest', type=Path)
    ap.add_argument('--labels', nargs='+')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--page')
    ap.add_argument('--image', type=Path)
    ap.add_argument('--boxes', type=Path, help='原图有效区域JSON，键1—9，像素left,top,right,bottom')
    ap.add_argument('--model')
    ap.add_argument('--tool')
    ap.add_argument('--call-record', type=Path)
    ap.add_argument('--status')
    ap.add_argument('--evidence', help='真实用户确认/反馈原话；本工具不验证发言者身份')
    ap.add_argument('--note')
    ap.add_argument('--revision')
    args = ap.parse_args()
    try:
        path = args.manifest.resolve()
        expected = path.read_bytes()
        data = load_manifest(path)
        if args.action == 'init':
            data = init_review(path, args.project, args.previous_manifest)
        elif args.action == 'register':
            if not args.labels or len(args.labels) != 1 or args.image is None:
                raise FormatError('登记单格需一个--labels和--image。')
            register_image(path, data, args.labels[0], args.image, model=args.model,
                           tool=args.tool, call_record=args.call_record)
        elif args.action == 'register-sheet':
            if not args.page or not args.image or not args.boxes:
                raise FormatError('登记整页需--page、--image、--boxes，不猜有效边界。')
            register_sheet(path, data, args.page, args.image, json.loads(args.boxes.read_text('utf-8')),
                           model=args.model, tool=args.tool, call_record=args.call_record)
        elif args.action == 'select':
            if not args.labels or len(args.labels) != 1 or not args.revision:
                raise FormatError('选用旧修订需一个--labels和--revision。')
            select_revision(path, data, args.labels[0], args.revision)
        elif args.action == 'agent-check':
            agent_check(path, data, args.labels, args.status, args.note or '', args.all)
        elif args.action == 'decide':
            make_decision(path, data, args.labels, args.status, args.evidence or '', args.all)
        result = report(path, data)
        if args.action != 'status':
            write_manifest(path, data, expected)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('未完成审阅登记：' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
