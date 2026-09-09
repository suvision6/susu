#!/usr/bin/env python3
"""Package saved image-plan prose for a host tool; never call a model.

References are optional. This module checks local file/header availability, not
image contents, identity matching, spatial correctness, or provider attachment.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from master_io import FormatError, parse_master, save_exclusive

from drawing_style import PREVIZ_STYLE

FORMAT = 'su-image9-host-input/1'


def file_digest(path: Path) -> str:
    """Hash a regular file without loading the entire asset into memory."""
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def image_type(header: bytes) -> str:
    """Identify a familiar file signature, not decode or visually inspect it."""
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if header.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return 'image/webp'
    if header.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if header.startswith((b'II*\x00', b'MM\x00*')):
        return 'image/tiff'
    if header.startswith(b'BM'):
        return 'image/bmp'
    raise FormatError('参考文件不是本整理工具可识别的图片头部；未执行解码或视觉识别。'
                      '可核对文件，或由Agent直接使用宿主支持的素材接口。')


def relative_path(path: Path, output_directory: Path) -> str:
    return Path(os.path.relpath(path, output_directory)).as_posix()


def reference_records(paths: list[Path], purposes: list[str],
                      output_directory: Path) -> list[dict[str, Any]]:
    if len(paths) != len(purposes):
        raise FormatError('每个显式 --reference 需要一个对应的 --reference-use；无参考时两者都省略。')
    records: list[dict[str, Any]] = []
    for number, (path, purpose) in enumerate(zip(paths, purposes), 1):
        if not purpose.strip():
            raise FormatError(f'参考{number}的用途为空；请说明本次采用的属性。')
        path = path.expanduser().resolve()
        if not path.is_file():
            raise FormatError(f'显式参考无法读取为文件：{path}。仅此依赖未完成，不表示无参考任务不可执行。')
        if path.stat().st_size == 0:
            raise FormatError(f'显式参考是空文件：{path.name}；不能用空文件代表图片。')
        with path.open('rb') as stream:
            mime = image_type(stream.read(32))
        records.append({
            'label': f'R{number}',
            'path': relative_path(path, output_directory),
            'purpose': purpose.strip(),
            'mime_from_signature': mime,
            'bytes': path.stat().st_size,
            'sha256': file_digest(path),
            'content_review': 'not_performed_by_script',
            'provider_attachment': 'not_performed',
        })
    return records


def panel_text(panel: dict[str, Any]) -> str:
    """Labels are input instructions and must not become marks in the picture."""
    return (f'格 {panel["id"]}\n'
            f'对应来源：{panel["source_ref"]}\n'
            f'画面关系：{panel["relation"]}\n'
            f'所取时点：{panel["moment"]}\n'
            f'画面正文：\n{panel["body"]}')


def prepare_request(master: Path, page_id: str, panel_id: str | None,
                    references: list[Path], purposes: list[str],
                    output: Path) -> dict[str, Any]:
    """Preserve authored prose, without deriving story or reference semantics."""
    master = master.expanduser().resolve()
    output = output.expanduser().resolve()
    if output == master or output in {p.expanduser().resolve() for p in references}:
        raise FormatError('输出路径不得是主稿或指定参考文件。')
    data = parse_master(master, 'image')
    matches = [p for p in data['pages'] if p['id'] == str(page_id)]
    if not matches:
        raise FormatError(f'未找到第{page_id}页；可用页号：' + '、'.join(p['id'] for p in data['pages']))
    page = matches[0]
    if panel_id is not None and str(panel_id) not in {p['id'] for p in page['panels']}:
        raise FormatError(f'第{page_id}页没有格{panel_id}；有效格号为1—9。')
    target = [p for p in page['panels'] if panel_id is None or p['id'] == str(panel_id)]
    neighbors = [] if panel_id is None else [p for p in page['panels'] if p['id'] != str(panel_id)]
    assets = reference_records(references, purposes, output.parent)

    if panel_id is None:
        task = '绘制指定页的一张完整3×3九宫格：每格一个画面，严格九格。下方格号仅用于输入定位，不画在图内。'
        output_kind = 'complete_3x3_page'
    else:
        task = (f'只绘制第{page_id}页的格{panel_id}，输出单个完整镜头画面，不画九宫格。'
                '其他格仅为关系与时点上下文，不是额外绘画任务。最终九格拼版另行处理。')
        output_kind = 'single_panel_for_later_3x3_composition'

    parts = [PREVIZ_STYLE, task, '【共用视觉依据，保留原稿文字】\n' + data['context'],
             '【本页范围与关系说明】\n' + page['source_scope'] + '\n' + page['body']]
    if assets:
        parts.append('【实际参考及限定用途】\n' + '\n'.join(
            f'{r["label"]}：{r["purpose"]}' for r in assets) +
            '\n这些标签对应执行说明中的实际文件；Agent须按宿主接口传图，标签本身不是图片。')
    else:
        parts.append('【参考输入】\n本次没有外部参考附件；依据已写明的文字与预演安排绘制，不等待补图。')
    if neighbors:
        # Full same-page context avoids guessed timing dependencies in legacy prose.
        # It is explicitly separated from the sole target drawing below.
        parts.append('【仅供理解的同页上下文，不绘制这些格】\n' +
                     '\n\n'.join(panel_text(p) for p in neighbors))
    parts.append('【本次实际绘制目标】\n' + '\n\n'.join(panel_text(p) for p in target))
    parts.append('遵照目标格的有效画幅与当前状态。净图不写生产编号、字幕、箭头或水印；'
                 '剧情必要的道具文字仍按采用稿处理。保持主体、必要轮廓和遮挡，不为装饰改变摄影。')

    if file_digest(master) != data['master_sha256']:
        raise FormatError('主稿在读取期间发生变化；请对保存后的同一版本重新整理。')
    return {
        'format': FORMAT,
        'operation': 'new_image_generation_brief',
        'source': {
            'master': relative_path(master, output.parent),
            'master_sha256': data['master_sha256'],
            'description': data['source_description'],
            'scope': data['scope'],
            'sources': copy.deepcopy(data['sources']),
            'source_links_relative_to': 'original master file',
        },
        'paths_relative_to': 'this request JSON directory',
        'declared_task': data['task'],
        'target': {'page': page['id'], 'panel': str(panel_id) if panel_id is not None else None,
                   'output_kind': output_kind},
        'shared_context': data['context'],
        'page_context': {'source_scope': page['source_scope'], 'body': page['body']},
        'drawing_panels': copy.deepcopy(target),
        'context_only_panels': copy.deepcopy(neighbors),
        'prompt': '\n\n'.join(parts),
        'input_additions': [{'kind': 'previz_style', 'text': PREVIZ_STYLE}],
        'reference_files': assets,
        'execution_notes': data['execution_notes'],
        'template_notes': data['warnings'],
        'checks': {
            'template_structure': 'checked',
            'reference_file_availability': 'checked' if assets else 'not_required',
            'reference_signature': 'checked_not_decoded' if assets else 'not_required',
            'source_coverage': 'not_verified_by_script',
            'semantic_review': 'not_performed_by_script',
            'model_call': 'not_performed',
            'image_review': 'not_performed',
        },
        'host_action_required': (
            '本文件不是供应商API调用。Agent先读原稿、执行说明和必要来源，确认本次绘制范围；'
            '有参考须实际看图并通过宿主附件接口传入。用户要求出图时才调用真实工具。'
            '本次主稿若只要求计划，不能因已整理此文件自动升级为出图。'
            '如有跨页时点依赖，另附有关页面或明确状态；此工具仅自动带齐当前页。'
            '修改指定旧图请另用实际编辑目标与宿主编辑接口。'
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='整理保存主稿及可选参考供宿主调用；不生图、不认证语义。')
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--page', required=True, help='与主稿中保存的页号完全一致')
    parser.add_argument('--panel', help='省略时整理整页，否则只绘制该格')
    parser.add_argument('--reference', type=Path, action='append', default=[])
    parser.add_argument('--reference-use', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare_request(args.input, args.page, args.panel,
                                 args.reference, args.reference_use, args.output)
        target = args.output.expanduser().resolve()
        payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8') + b'\n'
        save_exclusive(target, payload)
        if json.loads(target.read_text('utf-8')) != result:
            raise ValueError('调用说明JSON回读不一致。')
        print(json.dumps({'saved': str(target), 'target': result['target'],
                          'references': len(result['reference_files']),
                          'drawing_panels': len(result['drawing_panels']),
                          'context_only_panels': len(result['context_only_panels']),
                          'model_call': 'not_performed', 'semantic_review': 'not_performed_by_script'},
                         ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(f'未完成输入整理：{exc}', file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
