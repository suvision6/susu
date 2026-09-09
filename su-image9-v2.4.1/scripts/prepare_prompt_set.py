#!/usr/bin/env python3
"""Save EVERY authored page's full prompt and explicit coverage evidence.

No AI call, no automatic frame selection, no implicit semantic/visual pass.
Existing single-request and legacy plan-export entry points stay unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from coverage_review import review_coverage
from master_io import FormatError, parse_master, save_exclusive
from prepare_image_request import file_digest, prepare_request, relative_path

FORMAT = 'su-image9-prompt-set/1'
from drawing_style import PREVIZ_STYLE


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8') + b'\n'


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fence_for(text: str) -> str:
    return '`' * max(4, max((len(m.group()) + 1 for m in re.finditer(r'`+', text)), default=0))


def bundle_payloads(master: Path, output_dir: Path, director: Path | None = None,
                    source_shots: list[str] | None = None,
                    references: list[Path] | None = None, purposes: list[str] | None = None,
                    require_selection: bool = False) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Build bytes before writing, so a failed page does not masquerade as a set."""
    master, output_dir = master.expanduser().resolve(), output_dir.expanduser().resolve()
    director = director.expanduser().resolve() if director else None
    references, purposes = references or [], purposes or []
    data = parse_master(master, 'image')
    review = review_coverage(data, director, source_shots, require_selection)
    if review['issues']:
        raise FormatError('未生成Prompt集：明确覆盖或页范围不一致。\n' +
                          json.dumps(review, ensure_ascii=False, indent=2))
    outputs: dict[str, bytes] = {}
    entries = []
    pages_doc = [f'# {data["title"]}｜全部页生成Prompt',
                 '以下各页正文为完整保存的生成说明，不是摘要。只代表输入已经保存；'
                 '未调用模型，未验收图像。用户要求先看Prompt时，在继续生图前展示本文件全部页内容。',
                 '各页TXT与对应JSON的prompt字段逐字相同。适配宿主接口不能再次省略或改写画面；'
                 '实质改动须先更新采用的输入并重新展示。',
                 '本次声明任务：' + data['task']]
    for page, mapped in zip(data['pages'], review['page_map']):
        stem = f'Page-{int(page["id"]):02d}'
        request_name, prompt_name = stem + '-input.json', stem + '-prompt.txt'
        packet = prepare_request(master, page['id'], None, references, purposes,
                                 output_dir / request_name)
        # The actual page source list is a derived view, not an edit of the author.
        old_scope = '【本页范围与关系说明】\n' + page['source_scope'] + '\n' + page['body']
        new_scope = '【本页范围与关系说明】\n' + mapped['source_label'] + '\n' + page['body']
        if packet['prompt'].count(old_scope) != 1:
            raise FormatError(f'第{page["id"]}页输入范围块不能唯一定位。')
        packet['prompt'] = packet['prompt'].replace(old_scope, new_scope, 1)
        packet['page_context']['author_source_scope'] = page['source_scope']
        packet['page_context']['source_scope'] = mapped['source_label']
        packet['page_context']['source_ids'] = mapped['source_ids']
        packet['input_additions'] = [{'kind': 'previz_style', 'text': PREVIZ_STYLE}]
        packet['checks']['source_coverage'] = review['source_check']
        packet['checks']['selected_state_mapping'] = (
            'checked_against_authored_selection' if review['counts']['selected_process_required'] is not None
            else 'not_provided')
        raw = packet['prompt'].encode('utf-8')
        packet['prompt_sha256'] = digest(raw)
        packet['source']['director'] = relative_path(director, output_dir) if director else None
        packet['source']['director_sha256'] = review['director_sha256']
        outputs[request_name] = json_bytes(packet)
        outputs[prompt_name] = raw
        entries.append({'page': page['id'], 'source_ids': mapped['source_ids'],
                        'request_file': request_name, 'prompt_file': prompt_name,
                        'prompt_sha256': digest(raw), 'prompt_characters': len(packet['prompt']),
                        'panel_count': len(packet['drawing_panels']),
                        'model_call': 'not_performed', 'actual_call_record': None,
                        'image_files': [], 'image_review': 'not_performed'})
        fence = fence_for(packet['prompt'])
        pages_doc.extend([f'## 第 {page["id"]} 页｜{mapped["source_label"]}',
                          f'正文校验：`{digest(raw)}`；{len(packet["prompt"])}字符。',
                          fence + 'text\n' + packet['prompt'] + '\n' + fence])
    outputs['all-page-prompts.md'] = ('\n\n'.join(pages_doc) + '\n').encode('utf-8')
    outputs['coverage-report.json'] = json_bytes(review)
    # Persist the saved visual plan as a derived bus; never create another authored story.
    data['master'] = relative_path(master, output_dir)
    data['source_link_base'] = 'relative to master, not JSON directory'
    outputs['image-plan.json'] = json_bytes(data)
    manifest = {
        'format': FORMAT,
        'status': 'all_authored_page_prompts_prepared_not_generated',
        'source': {'image_master': relative_path(master, output_dir),
                   'image_master_sha256': data['master_sha256'],
                   'director': relative_path(director, output_dir) if director else None,
                   'director_sha256': review['director_sha256']},
        'counts': review['counts'], 'pages': entries,
        'files': [{'path': name, 'sha256': digest(content), 'bytes': len(content)}
                  for name, content in outputs.items()],
        'checks': {'source_ids': review['source_check'],
                   'declared_state_mapping': 'checked' if review['counts']['selected_process_required'] is not None
                                             else 'not_provided',
                   'selection_semantics': 'not_verified_by_script',
                   'semantic_review': 'not_performed_by_script', 'model_calls': 'not_performed',
                   'image_review': 'not_performed'},
        'notes': review['notes'],
        'completion_boundary': '仅全主稿各页Prompt与明确映射已整理；不能据此宣称过程选全、空间正确、'
                               '已传入模型或图像通过。未提供独立采用稿时不认证原片覆盖。',
    }
    outputs['prompt-set-manifest.json'] = json_bytes(manifest)
    # Ensure caller cannot target original input bytes through generated file names.
    protected = {master} | {p.expanduser().resolve() for p in references}
    if director:
        protected.add(director)
    if any((output_dir / name).resolve() in protected for name in outputs):
        raise FormatError('输出文件与采用稿、视觉主稿或参考路径相同。使用独立输出目录。')
    if file_digest(master) != manifest['source']['image_master_sha256']:
        raise FormatError('视觉主稿在整理期间改变，未保存混合版本Prompt集。')
    if director and file_digest(director) != review['director_sha256']:
        raise FormatError('导演稿在整理期间改变，未保存混合版本Prompt集。')
    return outputs, manifest


def verify_saved_set(folder: Path) -> dict[str, Any]:
    """Mechanical artifact comparison only; missing page is never a complete set."""
    manifest = json.loads((folder / 'prompt-set-manifest.json').read_text('utf-8'))
    if manifest.get('format') != FORMAT:
        raise FormatError('不是本入口的Prompt集；不把单页JSON当全页交付。')
    for item in manifest['files']:
        rel = Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise FormatError('清单文件路径越界。')
        p = folder / rel
        if not p.is_file() or digest(p.read_bytes()) != item['sha256']:
            raise FormatError(f'Prompt集文件缺失或已变化：{item["path"]}')
    text = (folder / 'all-page-prompts.md').read_text('utf-8')
    if len(manifest['pages']) != manifest['counts']['pages']:
        raise FormatError('清单页数不一致。')
    if [p['page'] for p in manifest['pages']] != list(map(str, range(1, len(manifest['pages']) + 1))):
        raise FormatError('清单页序不一致。')
    for item in manifest['pages']:
        packet = json.loads((folder / item['request_file']).read_text('utf-8'))
        raw = (folder / item['prompt_file']).read_bytes()
        if raw != packet['prompt'].encode('utf-8') or digest(raw) != item['prompt_sha256']:
            raise FormatError(f'第{item["page"]}页TXT与实际输入字段不一致。')
        if packet['target']['page'] != item['page'] or len(packet['drawing_panels']) != 9:
            raise FormatError('页面和目标九格不一致。')
        if packet['prompt'] not in text:
            raise FormatError('完整阅读文档缺少实际页Prompt。')
    return {'status': 'saved_all_authored_pages_read_back', 'pages': len(manifest['pages']),
            'source_id_check': manifest['checks']['source_ids'],
            'selection_semantics': 'not_verified_by_script',
            'model_call': 'not_performed', 'image_review': 'not_performed'}


def save_bundle(folder: Path, payloads: dict[str, bytes]) -> dict[str, Any]:
    """Preflight everything, publish completion manifest last, protect old work."""
    folder = folder.resolve()
    if folder.exists() and not folder.is_dir():
        raise FormatError('输出目录不是目录。')
    for name, content in payloads.items():
        p = folder / name
        if p.exists() and (not p.is_file() or p.read_bytes() != content):
            raise FileExistsError(f'已有不同内容：{p}。请使用新输出目录，不覆盖旧计划。')
    if folder.exists():
        unexpected = [p.name for p in folder.iterdir()
                      if re.fullmatch(r'Page-\d+-(?:input\.json|prompt\.txt)', p.name)
                      and p.name not in payloads]
        if unexpected:
            raise FormatError('目录含本计划以外的旧页，需新目录：' + '、'.join(unexpected))
    created = []
    try:
        for name, content in payloads.items():
            p = folder / name
            existed = p.exists()
            save_exclusive(p, content)
            if not existed:
                created.append(p)
            if p.read_bytes() != content:
                raise FormatError(f'保存回读不一致：{name}')
        return verify_saved_set(folder)
    except Exception:
        # Only roll back bytes this invocation created, never a pre-existing file.
        for p in reversed(created):
            if p.is_file() and p.read_bytes() == payloads[p.name]:
                p.unlink()
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description='全部页完整Prompt及明确覆盖核对；不生图、不判断过程必要性。')
    ap.add_argument('--input', type=Path)
    ap.add_argument('--director', type=Path, help='实际采用导演MD或含shots的JSON，只核对ID与顺序，不改写')
    ap.add_argument('--source-shots', help='仅局部任务：逗号分隔的明确源镜ID，按采用稿原序')
    ap.add_argument('--require-coverage', action='store_true', help='要求同一主稿内的取帧安排完整对应，非语义认证')
    ap.add_argument('--check', action='store_true', help='只输出明确映射核对，不写Prompt文件')
    ap.add_argument('--reference', type=Path, action='append', default=[])
    ap.add_argument('--reference-use', action='append', default=[])
    ap.add_argument('--output-dir', type=Path)
    ap.add_argument('--verify-dir', type=Path, help='只复核已经保存的全页Prompt集')
    args = ap.parse_args()
    try:
        if args.verify_dir:
            result = verify_saved_set(args.verify_dir)
        else:
            if args.input is None:
                raise FormatError('需--input视觉主稿。')
            shots = [s.strip() for s in args.source_shots.split(',')] if args.source_shots else None
            data = parse_master(args.input, 'image')
            review = review_coverage(data, args.director, shots, args.require_coverage)
            if args.check:
                print(json.dumps(review, ensure_ascii=False, indent=2))
                return 1 if review['issues'] else 0
            if args.output_dir is None:
                raise FormatError('需--output-dir新交付目录。')
            payloads, _ = bundle_payloads(args.input, args.output_dir, args.director, shots,
                                         args.reference, args.reference_use, args.require_coverage)
            result = save_bundle(args.output_dir, payloads)
            result['full_prompt_document'] = str((args.output_dir / 'all-page-prompts.md').resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'未完成全页Prompt整理：{exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
