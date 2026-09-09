#!/usr/bin/env python3
"""Deterministic 3x3 labelled contact sheets and approved-image PDF export.

No model calls. Pillow is required for raster assets; ReportLab embeds a local
TrueType font into PDF. Font files are never copied to the delivery directory.
Net pictures are never cropped, mirrored, re-posed, or overwritten here.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

from master_io import FormatError, save_exclusive
from prepare_prompt_set import verify_saved_set
from review_assets import (ROLE_ZH, STATE_ZH, assert_review_current, digest, effective_status,
                           load_manifest, read_image, resolve, selected_version, version_health)

PAPER = {'A4': (595.2756, 841.8898), 'A3': (841.8898, 1190.5512)}
FONT_CANDIDATES = [
    '/usr/share/fonts/truetype/arphic/uming.ttc',
    '/usr/share/fonts/truetype/arphic/ukai.ttc',
    '/usr/share/fonts/truetype/arphic-gbsn00lp/gbsn00lp.ttf',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
    '/Library/Fonts/Arial Unicode.ttf',
    '/System/Library/Fonts/STHeiti Light.ttc',
    '/System/Library/Fonts/PingFang.ttc',
    'C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simsun.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
]


def dependencies():
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise FormatError('审阅PNG/PDF需要Pillow和reportlab。请在虚拟环境安装requirements-review.txt；'
                          '不会自动安装，也不影响原有纯文字工具。') from exc
    return pdfmetrics, TTFont, canvas, ImageReader, Image, ImageDraw, ImageFont


def choose_font(text: str, requested: Path | None = None, index: int = 0):
    pdfmetrics, TTFont, *_ = dependencies()
    specific = requested or (Path(os.environ['SU_IMAGE9_FONT']) if os.environ.get('SU_IMAGE9_FONT') else None)
    candidates = [specific] if specific else [Path(p) for p in FONT_CANDIDATES]
    needed = {ord(c) for c in text if not c.isspace()}
    failures = []
    for p in candidates:
        if not p or not p.is_file():
            continue
        try:
            name = 'Image9-' + digest((str(p.resolve()) + ':' + str(index)).encode())[:12]
            f = TTFont(name, str(p), subfontIndex=index)
            absent = [x for x in needed if x not in f.face.charWidths]
            if absent:
                failures.append(p.name + '缺字:' + ''.join(chr(x) for x in sorted(absent)[:8]))
                continue
            pdfmetrics.registerFont(f)
            return name, p.resolve(), index
        except Exception as exc:
            failures.append(p.name + ':' + str(exc)[:100])
    raise FormatError('未找到可嵌入且覆盖本页文字的TrueType中文字体。用--font指定本机可用.ttf/TrueType .ttc，'
                      '必要时用--font-index选字库。不会静默用缺字字体或外部CID替代。' + '; '.join(failures[:4]))


def doctor() -> dict[str, Any]:
    modules = {m: importlib.util.find_spec(m) is not None for m in ['PIL', 'reportlab']}
    result = {'dependencies': modules, 'third_party_required_only_for': 'image_registration_and_layout',
              'font_files_bundled': False, 'auto_install': False}
    if all(modules.values()):
        try:
            name, path, index = choose_font('导演分镜 19c-E1 | 同刻延展 待审 已确认 第1页')
            result['font_check'] = {'status': 'available', 'path': str(path), 'index': index}
        except ValueError as exc:
            result['font_check'] = {'status': 'needs_local_font', 'reason': str(exc)}
    return result


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    from reportlab.pdfbase import pdfmetrics
    lines = []
    for segment in str(text).splitlines() or ['']:
        line = ''
        for char in segment:
            if line and pdfmetrics.stringWidth(line + char, font, size) > width:
                lines.append(line)
                line = char
            else:
                line += char
        lines.append(line)
    return lines or ['']


def page_geometry(paper: str, orientation: str, ratios: list[float]) -> tuple[float, float]:
    w, h = PAPER[paper]
    if orientation == 'auto':
        orientation = 'landscape' if sum(ratios) / len(ratios) > 1 else 'portrait'
    return (h, w) if orientation == 'landscape' else (w, h)


def layout_page(panels, paper, orientation, font, captions=False):
    ratios = [p['frame_ratio'][0] / p['frame_ratio'][1] for p in panels]
    w, h = page_geometry(paper, orientation, ratios)
    margin, gap = 26.0, 12.0
    top, bottom = 78.0, 34.0
    cellw = (w - margin * 2 - gap * 2) / 3
    cellh = (h - top - bottom - gap * 2) / 3
    # Labels never overlap the effective frame. Their space is added outside it.
    label_lines = [wrap(p['label'] + ' | ' + ROLE_ZH[p['kind']], font, 10, cellw) for p in panels]
    label_band = max(30.0, max(len(x) for x in label_lines) * 12 + 16)
    caption_band = 22.0 if captions else 0.0
    maxh = cellh - label_band - caption_band
    if maxh < 40:
        raise FormatError('标签过长，当前纸张无法容纳九格；改用较大纸张或在来源中使用清楚短编号。')
    # Keep labels immediately above their frame, rather than detached in a
    # full-width invisible cell. Homogeneous grids use their natural width.
    if max(ratios) - min(ratios) < .00001:
        for _ in range(3):
            cellw = min(cellw, maxh * ratios[0])
            label_lines = [wrap(p['label'] + ' | ' + ROLE_ZH[p['kind']], font, 10, cellw) for p in panels]
            label_band = max(30.0, max(len(x) for x in label_lines) * 12 + 16)
            maxh = cellh - label_band - caption_band
        if maxh < 40 or cellw < 38:
            raise FormatError('本画幅与标签在当前纸张过窄；请选择A3或调整审阅方向。')
    grid_left = (w - 3 * cellw - 2 * gap) / 2
    boxes = []
    for i, p in enumerate(panels):
        col, row = i % 3, i // 3
        cx = grid_left + col * (cellw + gap)
        cy = h - top - (row + 1) * cellh - row * gap
        v = selected_version(p)
        ratio = v['width'] / v['height']
        ih = min(maxh, cellw / ratio)
        iw = ih * ratio
        fx = cx + (cellw - iw) / 2
        fy = cy + caption_band + (maxh - ih) / 2
        boxes.append({'panel': p, 'cell': [cx, cy, cellw, cellh],
                      'frame': [fx, fy, iw, ih], 'label_lines': label_lines[i],
                      'label_top': cy + cellh - 10,
                      'label_bottom': cy + cellh - label_band + 5,
                      'caption_bottom': cy + 3})
    return w, h, boxes


def collect(path: Path, manifest: dict[str, Any], stage: str,
            pages: list[str] | None = None):
    verify_saved_set(path.parent)
    review = assert_review_current(path, manifest)
    available = list(dict.fromkeys(p['page'] for p in review['panels']))
    selected = available if pages is None else [p for p in available if p in pages]
    if not selected or (pages and (len(set(pages)) != len(pages) or set(pages) - set(available))):
        raise FormatError('页号不存在或重复；不推测子集。')
    all_panels = [p for p in review['panels'] if p['page'] in selected]
    problems = []
    for p in all_panels:
        v = selected_version(p)
        health = version_health(path, p, v)
        blocking = [x for x in health if stage == 'final' or x not in {'frame_ratio_mismatch', 'image_based_on_old_plan'}]
        if blocking:
            problems.append(p['label'] + ':' + ','.join(blocking))
        if stage == 'final' and effective_status(path, p) != 'approved':
            problems.append(p['label'] + ':not_user_approved_current_image')
        if v is not None and not blocking:
            im = read_image(resolve(path.parent, v['path']))
            if im.size != (v['width'], v['height']):
                problems.append(p['label'] + ':decoded_dimensions_changed')
    if problems:
        raise FormatError('未导出；不复制邻格或放占位图补齐：\n' + '\n'.join(problems[:25]))
    groups = [[p for p in all_panels if p['page'] == pg] for pg in selected]
    if any(len(g) != 9 for g in groups):
        raise FormatError('输出页必须真实完整九格。部分范围可选完整页，不能隐去一格。')
    return review, groups, selected, available


def export(path: Path, output_dir: Path, stage: str = 'review', output_format: str = 'both',
           paper: str = 'A4', orientation: str = 'auto', pages: list[str] | None = None,
           font_path: Path | None = None, font_index: int = 0, dpi: int = 180,
           captions: bool = False) -> dict[str, Any]:
    if stage not in {'review', 'final'} or output_format not in {'pdf', 'png', 'both'}:
        raise FormatError('无效导出模式。')
    if paper not in PAPER or orientation not in {'auto', 'portrait', 'landscape'} or not 72 <= dpi <= 600:
        raise FormatError('纸张/方向/DPI参数不支持。')
    path, output_dir = path.resolve(), output_dir.resolve()
    raw_manifest = path.read_bytes()
    manifest = load_manifest(path)
    review, groups, selected, available = collect(path, manifest, stage, pages)
    pdfmetrics, TTFont, canvas, ImageReader, Image, ImageDraw, ImageFont = dependencies()
    # Read the installed package version, not a stale hard-coded footer.
    package_version = (Path(__file__).resolve().parents[1] / 'VERSION').read_text('utf-8').strip()
    if not package_version or len(package_version) > 64 or any(c.isspace() for c in package_version):
        raise FormatError('VERSION缺失或格式不正确，不能输出误导性的版本标签。')
    status_title = '导演确认版' if stage == 'final' else '批量审阅版 - 待确认'
    subset = len(selected) != len(available)
    title = review['title']
    subtitle = status_title + (' | 部分范围' if subset else '')
    all_text = title + subtitle + review['project'] + package_version + '页原图轻笔阴影第共范围' + ''.join(STATE_ZH.values())
    for g in groups:
        for p in g:
            all_text += p['label'] + ROLE_ZH[p['kind']] + p['moment_key'] + 'r0123456789 / | . -'
    font, local_font, f_index = choose_font(all_text, font_path, font_index)
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, invariant=1, pageCompression=1)
    pdf.setTitle(title + ' - ' + status_title)
    pdf.setAuthor('su-image9 | deterministic layout')
    pdf.setSubject('Images and decisions from the selected manifest; not a generative operation.')
    payloads = {}
    page_records = []
    image_uses = defaultdict(list)
    for page_index, g in enumerate(groups, 1):
        w, h, boxes = layout_page(g, paper, orientation, font, captions)
        pdf.setPageSize((w, h))
        scale = dpi / 72
        page_img = Image.new('RGB', (round(w * scale), round(h * scale)), 'white')
        draw = ImageDraw.Draw(page_img)
        fonts = {}
        def text_at(x, y, text, size=10, gray=0.05):
            pdf.setFillGray(gray)
            pdf.setFont(font, size)
            pdf.drawString(x, y, text)
            px_size = max(1, round(size * scale))
            if px_size not in fonts:
                fonts[px_size] = ImageFont.truetype(str(local_font), px_size, index=f_index)
            rgb = round(gray * 255)
            draw.text((round(x * scale), round((h - y) * scale)), text, font=fonts[px_size],
                      fill=(rgb, rgb, rgb), anchor='ls')
        title_lines = wrap(title, font, 13, w - 52)
        if len(title_lines) > 2:
            raise FormatError('页头标题过长。请使用简短项目标题，详情保留主稿；不会静默截断。')
        for n, line in enumerate(title_lines):
            text_at(26, h - 30 - 16 * n, line, 13)
        text_at(26, h - 62, subtitle + ' | ' + paper, 9, .3)
        drawn = []
        for box in boxes:
            p = box['panel']
            v = selected_version(p)
            status = effective_status(path, p)
            im = read_image(resolve(path.parent, v['path']))
            fx, fy, iw, ih = box['frame']
            pdf.drawImage(ImageReader(im), fx, fy, iw, ih, preserveAspectRatio=True,
                          anchor='c', mask='auto')
            x0, y0 = round(fx * scale), round((h - fy - ih) * scale)
            scaled = im.resize((max(1, round(iw * scale)), max(1, round(ih * scale))), Image.Resampling.LANCZOS)
            page_img.paste(scaled, (x0, y0))
            pdf.setStrokeGray(.25)
            pdf.setLineWidth(.3)
            pdf.rect(fx - .2, fy - .2, iw + .4, ih + .4, fill=0, stroke=1)
            draw.rectangle((x0 - 1, y0 - 1, x0 + scaled.width, y0 + scaled.height), outline=(80,80,80), width=1)
            cx, cy, cw, ch = box['cell']
            for n, line in enumerate(box['label_lines']):
                text_at(cx, box['label_top'] - n * 12, line, 10)
            text_at(cx, box['label_bottom'], v['revision'] + ' | ' + STATE_ZH[status], 7.5, .35)
            if captions:
                lines = wrap(p['moment_key'], font, 8, cw)
                if len(lines) > 2:
                    raise FormatError('动作短注超出两行：' + p['label'] + '。取消--captions或缩短时点短名。')
                for n, line in enumerate(lines):
                    text_at(cx, box['caption_bottom'] + (len(lines) - n - 1) * 9, line, 8, .25)
            image_uses[v['sha256']].append(p['label'])
            drawn.append({'label': p['label'], 'uid': p['uid'], 'revision': v['revision'],
                          'image_sha256': v['sha256'], 'frame_box_pt': box['frame'],
                          'label_outside_frame': True, 'status': status,
                          'expected_frame_ratio': p['frame_ratio'],
                          'review_warnings': version_health(path, p, v)})
        pg = g[0]['page']
        footer = f'第 {page_index}/{len(groups)} 页 | 原计划页 {pg}/{len(available)} | su-image9 {package_version}'
        text_at(26, 17, footer, 8, .35)
        if output_format in {'png', 'both'}:
            image_bytes = io.BytesIO()
            page_img.save(image_bytes, format='PNG')
            payloads[f'Page-{int(pg):02d}-{stage}.png'] = image_bytes.getvalue()
        pdf.showPage()
        page_records.append({'page': pg, 'size_pt': [w,h], 'panels': drawn})
    pdf.save()
    if output_format in {'pdf', 'both'}:
        payloads[f'storyboard-{stage}.pdf'] = buf.getvalue()
    result = {
        'package_version': package_version, 'stage': stage, 'scope': 'explicit_subset' if subset else 'all_planned_pages',
        'source_manifest_sha256': digest(raw_manifest), 'source_manifest': str(path),
        'pages': page_records, 'font': {'local_path_used': str(local_font), 'index': f_index,
                                      'embedded_in_pdf': True, 'font_file_delivered': False},
        'suspected_exact_duplicates': [v for v in image_uses.values() if len(v)>1],
        'pixel_policy': 'source pixels preserved in separate net assets; review scaled proportionally; no crop',
        'semantic_review': 'not_performed_by_exporter', 'pdf_visual_review': 'not_performed_by_exporter',
        'user_authentication': 'operator_records_only',
        'outputs': [{'path': n, 'sha256': digest(b)} for n,b in payloads.items()],
    }
    payloads['export-report.json'] = json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    if path.read_bytes() != raw_manifest:
        raise FormatError('排版期间选用清单发生变化；没有发布混合版本。')
    # Preflight ALL files, protect source data, publish only after validation.
    protected = {path}
    protected.update(resolve(path.parent, v['path']) for g in groups for p in g for v in p['versions'])
    protected.update(resolve(path.parent, v['raw_path']) for g in groups for p in g for v in p['versions'])
    for name, content in payloads.items():
        target = output_dir / name
        if target.resolve() in protected:
            raise FormatError('排版输出不可覆盖输入图或清单。')
        if target.exists() and (not target.is_file() or target.read_bytes() != content):
            raise FileExistsError('输出已有不同内容，请使用新版本目录：' + str(target))
    created = []
    try:
        for name, content in payloads.items():
            target = output_dir / name
            existed = target.exists()
            save_exclusive(target, content)
            if not existed:
                created.append(target)
    except Exception:
        for target in reversed(created):
            if target.exists() and target.read_bytes() == payloads[target.name]:
                target.unlink()
        raise
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description='净图保持不变，框外加号；批量审阅PNG及确认版PDF。')
    ap.add_argument('--doctor', action='store_true')
    ap.add_argument('--manifest', type=Path)
    ap.add_argument('--output-dir', type=Path)
    ap.add_argument('--stage', choices=['review','final'], default='review')
    ap.add_argument('--format', choices=['png','pdf','both'], default='png')
    ap.add_argument('--paper', choices=['A4','A3'], default='A4')
    ap.add_argument('--orientation', choices=['auto','portrait','landscape'], default='auto')
    ap.add_argument('--pages', nargs='+')
    ap.add_argument('--font', type=Path)
    ap.add_argument('--font-index', type=int, default=0)
    ap.add_argument('--dpi', type=int, default=180)
    ap.add_argument('--captions', action='store_true')
    args = ap.parse_args()
    try:
        if args.doctor:
            result = doctor()
        else:
            if not args.manifest or not args.output_dir:
                raise FormatError('需--manifest和--output-dir；不扫描最新图片自行选用。')
            result = export(args.manifest, args.output_dir, args.stage, args.format,
                            args.paper, args.orientation, args.pages, args.font, args.font_index,
                            args.dpi, args.captions)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('未完成审阅排版：' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
