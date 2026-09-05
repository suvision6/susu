#!/usr/bin/env node
/** su-fenjingskill 3.3.1: read authored Markdown; project, never rewrite shots. */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

export const VERSION = '3.3.1';
export const COLUMNS = ['镜号', '场景', '原剧本段落', '镜头时长', '运镜＋主画面描述', '备注'];
const TEXT_FIELDS = [COLUMNS[2], COLUMNS[4], COLUMNS[5]];
const MAX_HEIGHT = 409 * 4 / 3; // Excel points -> pixels; overflow becomes another display row.
const MAX_CHARS = 32760; // Leave room for the literal-text escape.
const PAD = 18;
const graphemes = new Intl.Segmenter('zh', { granularity: 'grapheme' });

async function dependency(name) {
  try { return await import(name); }
  catch (error) {
    if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error;
    const resolve = createRequire(path.join(process.cwd(), 'package.json'));
    return import(pathToFileURL(resolve.resolve(name)).href);
  }
}

export function parseMarkdown(markdown) {
  const lines = markdown.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n').split('\n');
  let i = 0, shot = '';
  const fail = (message, at = i) => { throw Error('第' + (at + 1) + '行' + (shot ? '，镜头' + shot : '') + '：' + message); };
  const blank = () => { while (i < lines.length && !lines[i].trim()) i++; };
  const expect = text => { blank(); if (lines[i] !== text) fail('应为“' + text + '”，请检查缺项、重复字段或顺序。'); i++; };
  const value = prefix => {
    blank();
    if (!lines[i]?.startsWith(prefix)) fail('应为“' + prefix + '…”，请检查缺项、重复字段或顺序。');
    const result = lines[i++].slice(prefix.length);
    if (!result.trim()) fail(prefix + '不能为空。', i - 1);
    return result;
  };
  const fenced = () => {
    blank();
    const start = i, fence = lines[i]?.match(/^(\x60{3,})text$/)?.[1];
    if (!fence) fail('长文本须使用纯文本围栏。');
    i++;
    const begin = i;
    while (i < lines.length && lines[i] !== fence) i++;
    if (i === lines.length) fail('纯文本围栏未闭合。', start);
    return lines.slice(begin, i++).join('\n');
  };
  const data = { title: value('# ') };
  if (value('Skill 版本：') !== VERSION) fail('请使用3.3.1主稿格式。', i - 1);
  data.source = value('原始来源：');
  data.scope = value('本轮范围：');
  data.settings = value('设置：');
  expect('## 导演设计');
  data.design = [];
  const designKeys = new Set();
  blank();
  while (lines[i]?.startsWith('### ')) {
    const key = value('### ');
    if (designKeys.has(key.trim())) fail('导演设计项目重复：' + key, i - 1);
    designKeys.add(key.trim());
    blank();
    let body;
    if (/^\x60{3,}text$/.test(lines[i] ?? '')) body = fenced();
    else {
      const begin = i;
      while (i < lines.length && !/^#{1,4} /.test(lines[i])) i++;
      let end = i;
      while (end > begin && !lines[end - 1].trim()) end--;
      body = lines.slice(begin, end).join('\n');
    }
    if (!body.trim()) fail('导演设计说明不能为空。');
    data.design.push([key, body]);
    blank();
  }
  if (!data.design.length) fail('至少写一项导演设计。');
  expect('## 分镜');
  data.rows = [];
  const ids = new Set();
  blank();
  while (i < lines.length && lines[i] !== '## 工作续记') {
    shot = value('### 镜头 ');
    if (ids.has(shot.trim())) fail('镜号重复：' + shot, i - 1);
    ids.add(shot.trim());
    const scene = value('场景：');
    const seconds = value('镜头时长：');
    if (!/^[1-9]\d*秒$/.test(seconds) || !Number.isSafeInteger(Number(seconds.slice(0, -1)))) fail('镜头时长须为正整数秒。', i - 1);
    const fields = TEXT_FIELDS.map((name, index) => {
      expect('#### ' + name);
      const text = fenced();
      if (index < 2 && !text.trim()) fail(name + '不能为空。');
      return text;
    });
    data.rows.push([shot, scene, fields[0], Number(seconds.slice(0, -1)), fields[1], fields[2]]);
    blank();
  }
  if (!data.rows.length) fail('至少写一个完整镜头。');
  if (i < lines.length) {
    const misplaced = lines.findIndex((line, index) => index > i && /^(?:### 镜头 |## (?:分镜|导演设计|工作续记)$)/.test(line));
    if (misplaced >= 0) fail('工作续记须在所有镜头之后；请将续写的镜头移到工作续记之前。', misplaced);
  }
  data.continuation = i < lines.length ? lines.slice(i + 1).join('\n') : '';
  data.total = data.rows.reduce((sum, row) => sum + row[3], 0);
  if (!Number.isSafeInteger(data.total)) fail('预计合计超过安全整数范围。');
  return data;
}

async function typography(options, warnings) {
  const size = options.fontSize ?? 11;
  if (!Number.isFinite(size) || size < 9 || size > 24) throw Error('字号须在9至24pt之间，以保持正文可读。');
  let font = options.font, ctx;
  try {
    const { createCanvas, GlobalFonts } = await dependency('@napi-rs/canvas');
    if (options.fontFile) {
      font ??= 'Storyboard Font';
      if (!GlobalFonts.registerFromPath(path.resolve(options.fontFile), font)) throw Error('字体文件无法加载。');
    }
    const names = new Set(GlobalFonts.families.map(f => f.family));
    const preferred = ['Noto Sans CJK SC', 'Noto Sans SC', 'Microsoft YaHei', 'PingFang SC', 'Songti SC', 'SimSun'];
    const chinese = preferred.find(name => names.has(name));
    font ??= chinese ?? 'DejaVu Sans';
    if (!names.has(font)) warnings.push('本机未确认字体“' + font + '”，请在阅读环境复核字体与行高。');
    if (!chinese && !options.fontFile) warnings.push('未检测到常用中文字体；中文采用保守宽度，中文视觉验收待完成。');
    ctx = createCanvas(1, 1).getContext('2d');
  } catch (error) {
    if (options.fontFile) throw error;
    font ??= 'Noto Sans CJK SC';
    warnings.push('字体测量不可用，采用保守估计：' + error.message);
  }
  const at = pt => {
    const px = pt * 4 / 3, cache = new Map();
    const measure = text => {
      if (cache.has(text)) return cache.get(text);
      if (ctx) ctx.font = pt + 'pt "' + font.replaceAll('"', '') + '"';
      let width = ctx ? ctx.measureText(text).width : [...text].reduce((n, c) => n + (/[il.,' :;]/.test(c) ? 0.4 : /[MW@]/.test(c) ? 1 : 0.7) * px, 0);
      // Missing CJK glyphs must not be measured as narrow tofu boxes.
      if (/[^\u0000-\u024f]/.test(text)) width = Math.max(width, [...graphemes.segment(text)].filter(g => !/^\p{Mark}+$/u.test(g.segment)).length * px);
      cache.set(text, width);
      return width;
    };
    return { measure, px, line: px * 1.6, font, size: pt };
  };
  return { ...at(size), at };
}

// Word wrapping for Latin words, grapheme wrapping for CJK / overlong tokens.
// Offsets refer to the original string; joining chunks must reproduce it exactly.
function lineEnds(text, width, metric) {
  const available = Math.max(metric.px, width - PAD);
  const tokens = (text.match(/[A-Za-z0-9_]+|[^\S\n]+|\n|[^A-Za-z0-9_\s]+/gu) ?? [])
    .flatMap(token => /^[A-Za-z0-9_\s]+$/.test(token) ? [token] : [...graphemes.segment(token)].map(g => g.segment));
  const ends = [];
  let offset = 0, used = 0;
  for (const token of tokens) {
    if (token === '\n') { offset++; ends.push(offset); used = 0; continue; }
    const tokenWidth = metric.measure(token.replaceAll('\t', '    '));
    if (used && used + tokenWidth > available) { ends.push(offset); used = 0; }
    if (tokenWidth <= available) { used += tokenWidth; offset += token.length; continue; }
    for (const { segment } of graphemes.segment(token)) {
      const w = metric.measure(segment.replaceAll('\t', '    '));
      if (used && used + w > available) { ends.push(offset); used = 0; }
      used += w; offset += segment.length;
    }
  }
  if (ends.at(-1) !== text.length || text.endsWith('\n') || !ends.length) ends.push(text.length);
  return ends;
}

export function splitText(text, width, metric) {
  if (!text) return [''];
  const pieces = [];
  const maxLines = Math.max(1, Math.floor((MAX_HEIGHT - PAD) / metric.line) - 1);
  let rest = text;
  while (rest) {
    // A bounded window prevents rescanning an entire long scene for every row.
    let window = rest.slice(0, MAX_CHARS);
    if (/[\uD800-\uDBFF]$/.test(window)) window = window.slice(0, -1);
    const ends = lineEnds(window, width, metric);
    let end = ends[Math.min(maxLines, ends.length) - 1];
    const newline = window.indexOf('\n', 0);
    if (newline >= 0) {
      let count = 0;
      for (let k = 0; k < end; k++) if (window[k] === '\n' && ++count > 253) { end = k; break; }
    }
    if (end < rest.length) {
      const prefix = window.slice(0, end);
      const boundary = [...prefix.matchAll(/(?:\n|[。！？；.!?;](?:[”’"']|\s)*)/gu)].at(-1);
      const natural = boundary ? boundary.index + boundary[0].length : 0;
      if (natural >= end * 0.6) end = natural;
    }
    if (!end) throw Error('当前字体与宽度无法容纳一个字形，请增加阅读宽度。');
    pieces.push(rest.slice(0, end));
    rest = rest.slice(end);
  }
  if (pieces.join('') !== text) throw Error('续行文本不一致。');
  return pieces;
}

function widthsFor(data, totalWidth, metric) {
  if (!Number.isFinite(totalWidth) || totalWidth < 800 || totalWidth > 6000) throw Error('阅读宽度须在800至6000px之间；长文通过续行容纳。');
  const measure = text => Math.max(...String(text).split('\n').map(line => metric.measure(line)));
  const demand = data.rows[0].map((_, c) => {
    const values = data.rows.map(row => measure(row[c])).filter(w => w > 0).sort((a, b) => a - b);
    return values.length ? values[Math.floor((values.length - 1) * 0.75)] : 0;
  });
  const minimum = COLUMNS.map(name => measure(name) + PAD);
  const widths = minimum.slice();
  // Short fields fit content within their share of the reading viewport.
  for (const c of [0, 1, 3, 5]) widths[c] = Math.max(minimum[c], Math.min(totalWidth * (c === 1 || c === 5 ? 0.14 : 0.1), demand[c] + PAD));
  widths[0] = Math.max(widths[0], Math.min(totalWidth * 0.1, measure('01（续99）') + PAD));
  const remaining = totalWidth - [0, 1, 3, 5].reduce((n, c) => n + widths[c], 0);
  const ratio = Math.max(0.32, Math.min(0.57, Math.sqrt(demand[2] + 1) / (Math.sqrt(demand[2] + 1) + Math.sqrt(demand[4] + 1))));
  widths[2] = remaining * ratio;
  widths[4] = remaining - widths[2];
  // Excel's maximum column width (255 standard characters), in the exporter's pixel units.
  return widths.map(w => Math.min(1780, Math.ceil(w)));
}

function sheetPlan(name, widths, metric) {
  return { name, widths, metric, rows: [], shots: [], header: 0 };
}
function addRow(plan, cells, role = 'body', group = 0, metric = plan.metric, merged = false) {
  const count = merged ? lineEnds(String(cells[0]), plan.widths.reduce((a, b) => a + b, 0), metric).length
    : Math.max(...cells.map((v, c) => lineEnds(v == null ? '' : String(v), plan.widths[c], metric).length));
  const height = Math.max(metric.line + PAD, count * metric.line + PAD);
  if (height > MAX_HEIGHT + 0.1) throw Error('排版内部错误：续行高度仍超出Excel容量。');
  plan.rows.push({ cells, role, group, height, metric, merged });
  return plan.rows.length;
}
function banner(plan, text, role = 'meta', metric = plan.metric) {
  for (const part of splitText(text, plan.widths.reduce((a, b) => a + b, 0), metric)) addRow(plan, [part, ...plan.widths.slice(1).map(() => null)], role, 0, metric, true);
}
function textRows(plan, values, group) {
  const parts = values.map((v, c) => splitText(v, plan.widths[c], plan.metric));
  const count = Math.max(...parts.map(p => p.length));
  for (let j = 0; j < count; j++) addRow(plan, parts.map(p => p[j] ?? ''), 'body', group);
}

export async function makeWorkbook(data, options = {}) {
  const warnings = [];
  const metric = await typography(options, warnings);
  const width = options.widthPx ?? 1480;
  const main = sheetPlan('导演分镜', widthsFor(data, width, metric), metric);
  const designWidth = Math.min(width, 1300);
  const labelWidth = Math.max(metric.measure('原始来源') + PAD, Math.min(designWidth * 0.25, Math.max(...data.design.map(r => metric.measure(r[0]))) + PAD));
  const design = sheetPlan('导演设计', [labelWidth, designWidth - labelWidth], metric);
  banner(main, data.title, 'title', metric.at(metric.size + 5));
  banner(main, 'su-fenjingskill ' + VERSION + ' · 预计时长为拍摄与剪辑计划');
  const totalRow = addRow(main, ['预计总时长', data.total, '秒', null, '逻辑镜头数', data.rows.length], 'summary');
  banner(main, '设置：' + data.settings);
  main.header = addRow(main, COLUMNS, 'header');
  for (const [index, row] of data.rows.entries()) {
    const parts = row.map((v, c) => c === 3 ? [] : splitText(v, main.widths[c], metric));
    const count = Math.max(...parts.map(p => p.length));
    const begin = main.rows.length + 1;
    for (let j = 0; j < count; j++) {
      const values = parts.map(p => p[j] ?? '');
      // Normal IDs repeat as a navigation label. Very long IDs continue as text.
      if (j && parts[0].length === 1) values[0] = row[0] + '（续' + j + '）';
      values[3] = j ? null : row[3];
      addRow(main, values, 'body', index);
    }
    main.shots.push({ begin, count });
  }
  main.summary = { row: totalRow, start: main.header + 1, end: main.rows.length };
  banner(design, data.title, 'title', metric.at(metric.size + 5));
  banner(design, '导演设计 · su-fenjingskill ' + VERSION);
  design.header = addRow(design, ['项目', '内容'], 'header');
  [['原始来源', data.source], ['本轮范围', data.scope], ['设置', data.settings], ...data.design].forEach((r, i) => textRows(design, r, i));
  const { Workbook } = await dependency('@oai/artifact-tool');
  const wb = Workbook.create();
  for (const plan of [main, design]) {
    const sheet = wb.worksheets.add(plan.name);
    sheet.showGridLines = false;
    const all = sheet.getRangeByIndexes(0, 0, plan.rows.length, plan.widths.length);
    all.format.font = { name: metric.font, size: metric.size, color: '#24323F' };
    all.format.wrapText = true;
    all.format.verticalAlignment = 'top';
    all.setNumberFormat('@');
    plan.widths.forEach((w, c) => sheet.getRangeByIndexes(0, c, plan.rows.length, 1).format.columnWidthPx = w);
    all.values = plan.rows.map(r => r.cells.map(v => typeof v === 'string' && v.startsWith('=') ? "'" + v : v));
    for (const [i, row] of plan.rows.entries()) {
      const range = sheet.getRangeByIndexes(i, 0, 1, plan.widths.length);
      if (row.merged) range.merge();
      range.format.rowHeightPx = row.height;
      if (row.role === 'title') range.format.font = { name: metric.font, size: row.metric.size, bold: true };
      if (row.role === 'header') range.format = { fill: '#303E4D', font: { name: metric.font, size: metric.size, color: '#FFFFFF', bold: true }, wrapText: true, rowHeightPx: row.height };
      if (row.role === 'body') {
        range.format.fill = row.group % 2 ? '#FFFFFF' : '#F0F4F7';
        if (i === 0 || plan.rows[i - 1].group !== row.group || plan.rows[i - 1].role !== 'body') range.format.borders = { top: { style: 'thin', color: '#B9C8D4' } };
      }
    }
    sheet.freezePanes.freezeRows(plan.header);
  }
  const sheet = wb.worksheets.getItem(main.name), s = main.summary;
  sheet.getRange('D' + s.start + ':D' + s.end).setNumberFormat('0"秒"');
  sheet.getRange('B' + s.row).setNumberFormat('0');
  sheet.getRange('F' + s.row).setNumberFormat('0');
  sheet.getRange('B' + s.row).formulas = [['=SUM(D' + s.start + ':D' + s.end + ')']];
  sheet.getRange('F' + s.row).formulas = [['=COUNT(D' + s.start + ':D' + s.end + ')']];
  return { wb, plans: [main, design], warnings };
}

export async function verifySaved(file, data, plans) {
  const { SpreadsheetFile, FileBlob } = await dependency('@oai/artifact-tool');
  const saved = await SpreadsheetFile.importXlsx(await FileBlob.load(file));
  for (const plan of plans) {
    const sheet = saved.worksheets.getItem(plan.name);
    const values = sheet.getRangeByIndexes(0, 0, plan.rows.length, plan.widths.length).values;
    for (const [i, row] of plan.rows.entries()) for (const [c, expected] of row.cells.entries()) {
      if (plan.summary && i + 1 === plan.summary.row && [1, 5].includes(c)) continue;
      const actual = values[i]?.[c] ?? '';
      if (actual !== (expected ?? '')) throw Error('保存回读不一致：' + plan.name + '，第' + (i + 1) + '行，第' + (c + 1) + '列。');
    }
    if (plan.summary) {
      const { row, start, end } = plan.summary;
      if (values[row - 1][1] !== data.total || values[row - 1][5] !== data.rows.length) throw Error('保存后的时长或镜数合计不一致。');
      if (sheet.getRange('B' + row).formulas[0][0] !== '=SUM(D' + start + ':D' + end + ')' ||
          sheet.getRange('F' + row).formulas[0][0] !== '=COUNT(D' + start + ':D' + end + ')') throw Error('保存后的合计公式不一致。');
      plan.shots.forEach(({ begin, count }, index) => {
        const rows = values.slice(begin - 1, begin - 1 + count);
        for (const c of [1, 2, 4, 5]) if (rows.map(r => r[c] ?? '').join('') !== data.rows[index][c]) throw Error('同镜续行还原失败：' + data.rows[index][0]);
        if (rows.reduce((n, r) => n + (typeof r[3] === 'number' ? r[3] : 0), 0) !== data.rows[index][3]) throw Error('续行重复计时。');
      });
    }
  }
  return saved;
}

async function preview(wb, plans, directory) {
  await fs.mkdir(directory, { recursive: true });
  for (const [sheetIndex, plan] of plans.entries()) {
    let begin = 0, page = 1;
    while (begin < plan.rows.length) {
      let end = begin, height = 0;
      while (end < plan.rows.length && (height + plan.rows[end].height <= 1100 || end === begin)) height += plan.rows[end++].height;
      const range = 'A' + (begin + 1) + ':' + String.fromCharCode(64 + plan.widths.length) + end;
      const png = await wb.render({ sheetName: plan.name, range, scale: 1, format: 'png' });
      await fs.writeFile(path.join(directory, (sheetIndex ? 'design-' : 'shots-') + page++ + '.png'), new Uint8Array(await png.arrayBuffer()));
      begin = end;
    }
  }
}

const hash = bytes => createHash('sha256').update(bytes).digest('hex');
async function optionalBytes(file) {
  try { return await fs.readFile(file); } catch (e) { if (e.code === 'ENOENT') return null; throw e; }
}
export async function exportFiles(input, outputDir, prefix, options = {}) {
  if (!prefix || /[\/\\\x00-\x1f<>:"|?*]/.test(prefix) || /[. ]$/.test(prefix)) throw Error('文件前缀包含不适用的路径字符。');
  const original = await fs.readFile(input);
  const data = parseMarkdown(original.toString('utf8'));
  await fs.mkdir(outputDir, { recursive: true });
  const mdPath = path.resolve(outputDir, prefix + '-storyboard.md');
  const xlsxPath = path.resolve(outputDir, prefix + '-storyboard.xlsx');
  const existingMd = await optionalBytes(mdPath);
  if (existingMd && !existingMd.equals(original)) throw Error('同名Markdown内容不同，请使用新前缀或先更新该主稿；未覆盖原文件。');
  if (!existingMd) await fs.writeFile(mdPath, original, { flag: 'wx' });
  const oldXlsx = await optionalBytes(xlsxPath);
  if (oldXlsx && !options.replace) throw Error('同名Excel已存在；使用新前缀，或处理完人类修改后使用--replace保留备份再更新。Markdown已保留。');
  const staging = await fs.mkdtemp(path.join(path.resolve(outputDir), '.fenjing-stage-'));
  let backup;
  try {
    const { wb, plans, warnings } = await makeWorkbook(data, options);
    if (options.previewDir) {
      try { await preview(wb, plans, options.previewDir); }
      catch (e) { warnings.push('预览未完成：' + e.message); }
    }
    const { SpreadsheetFile } = await dependency('@oai/artifact-tool');
    const staged = path.join(staging, 'storyboard.xlsx');
    await (await SpreadsheetFile.exportXlsx(wb)).save(staged);
    await verifySaved(staged, data, plans);
    if (!(await fs.readFile(input)).equals(original) || !(await fs.readFile(mdPath)).equals(original)) throw Error('主稿在导出期间发生变化，请从当前主稿重试；未发布过期Excel。');
    const current = await optionalBytes(xlsxPath);
    if (hash(current ?? '') !== hash(oldXlsx ?? '')) throw Error('目标Excel在导出期间发生变化，已保留，请先处理修改。');
    if (oldXlsx) {
      backup = xlsxPath.replace(/\.xlsx$/, '.backup-' + new Date().toISOString().replace(/[:.]/g, '-') + '-' + path.basename(staging).slice(-6) + '.xlsx');
      await fs.copyFile(xlsxPath, backup, 1);
      await fs.rename(staged, xlsxPath);
    } else {
      // Same-filesystem hard link publishes the complete verified file without overwriting.
      await fs.link(staged, xlsxPath);
    }
    return { version: VERSION, shots: data.rows.length, estimated_seconds: data.total, markdown: mdPath, excel: xlsxPath, backup, physical_shot_rows: plans[0].rows.length - plans[0].header, warnings };
  } finally { await fs.rm(staging, { recursive: true, force: true }); }
}

async function main() {
  const argv = process.argv.slice(2), args = {};
  const flags = new Set(['check', 'replace', 'help']);
  const names = new Set(['input', 'output-dir', 'prefix', 'preview-dir', 'width-px', 'font', 'font-size', 'font-file']);
  for (let i = 0; i < argv.length; i++) {
    const name = argv[i].slice(2);
    if (!argv[i].startsWith('--') || (!flags.has(name) && !names.has(name)) || Object.hasOwn(args, name)) throw Error('未知或重复参数：' + argv[i]);
    if (flags.has(name)) args[name] = true;
    else {
      if (!argv[i + 1] || argv[i + 1].startsWith('--')) throw Error('参数缺少值：' + argv[i]);
      args[name] = argv[++i];
    }
  }
  if (args.help) {
    console.log('su-fenjingskill ' + VERSION + '\nnode export_storyboard.mjs --input story.md --check\nnode export_storyboard.mjs --input story.md --output-dir DIR --prefix NAME [--replace] [--preview-dir DIR] [--width-px 1480] [--font NAME] [--font-size 11] [--font-file PATH]');
    return;
  }
  if (!args.input) throw Error('缺少--input。');
  if (args.check) {
    const data = parseMarkdown(await fs.readFile(args.input, 'utf8'));
    console.log(JSON.stringify({ version: VERSION, shots: data.rows.length, estimated_seconds: data.total }));
    return;
  }
  if (!args['output-dir'] || !args.prefix) throw Error('缺少--output-dir或--prefix。');
  console.log(JSON.stringify(await exportFiles(args.input, args['output-dir'], args.prefix, {
    replace: args.replace, previewDir: args['preview-dir'], font: args.font, fontFile: args['font-file'],
    widthPx: args['width-px'] ? Number(args['width-px']) : undefined,
    fontSize: args['font-size'] ? Number(args['font-size']) : undefined,
  })));
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) main().catch(error => { console.error(error.message); process.exitCode = 1; });
