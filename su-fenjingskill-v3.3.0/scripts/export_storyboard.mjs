#!/usr/bin/env node
/** su-fenjingskill 3.3.0 — format authored rows; never design or estimate shots. */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

export const VERSION = '3.3.0';
export const COLUMNS = ['镜号', '场景', '原剧本段落', '镜头时长', '运镜＋主画面描述', '备注'];
const WIDTHS = [72, 160, 360, 88, 620, 190];
const FONT = 'Songti SC';
// Installed Skills need not have a node_modules folder: use the task workspace
// dependency link when direct module resolution is unavailable.
let libraryPromise;
function library() {
  return libraryPromise ??= import('@oai/artifact-tool').catch(error => {
    if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error;
    const taskRequire = createRequire(path.join(process.cwd(), 'package.json'));
    return import(pathToFileURL(taskRequire.resolve('@oai/artifact-tool')).href);
  });
}

export function validate(data) {
  if (!data || typeof data !== 'object') throw Error('输入必须是表格对象。');
  for (const key of ['title', 'settings']) {
    if (typeof data[key] !== 'string' || !data[key].trim()) throw Error(`${key}不能为空。`);
  }
  if (!Array.isArray(data.design) || !data.design.length || data.design.some(
    r => !Array.isArray(r) || r.length !== 2 || r.some(c => typeof c !== 'string' || !c.trim())
  )) throw Error('design须为两列非空文本。');
  if (!Array.isArray(data.rows) || !data.rows.length) throw Error('rows不能为空。');
  const ids = new Set();
  let total = 0;
  for (const [i, row] of data.rows.entries()) {
    if (!Array.isArray(row) || row.length !== 6) throw Error(`第${i + 1}行必须有六列。`);
    for (const c of [0, 1, 2, 4, 5]) {
      if (typeof row[c] !== 'string' || (c !== 5 && !row[c].trim())) throw Error(`第${i + 1}行第${c + 1}列须为文本。`);
      if (row[c].length > 32767) throw Error(`第${i + 1}行第${c + 1}列超过Excel文本容量。请分段整理，工具不会截字。`);
    }
    if (ids.has(row[0].trim())) throw Error(`镜号重复：${row[0]}`);
    ids.add(row[0].trim());
    if (!Number.isSafeInteger(row[3]) || row[3] <= 0) throw Error(`镜头${row[0]}须为正整数预计秒数。`);
    total += row[3];
  }
  if (!Number.isSafeInteger(total)) throw Error('预计合计超过安全整数范围。');
  return total;
}

const markdownText = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;').replaceAll('|', '&#124;').replaceAll('\\', '&#92;')
  .replaceAll('*', '&#42;').replaceAll('_', '&#95;').replaceAll('`', '&#96;')
  .replace(/\r\n?|\n/g, '<br>');
const excelText = value => typeof value === 'string' && value.startsWith('=') ? `'${value}` : value;

export function markdown(data) {
  const total = validate(data);
  return `# ${markdownText(data.title)}\n\n分镜版本：su-fenjingskill ${VERSION}\n\n${markdownText(data.settings)}\n\n预计时长：${total}秒，共${data.rows.length}镜。\n\n`
    + '## 导演设计\n\n| 项目 | 设计 |\n| --- | --- |\n'
    + data.design.map(r => `| ${r.map(markdownText).join(' | ')} |`).join('\n')
    + '\n\n## 导演分镜\n\n| ' + COLUMNS.join(' | ') + ' |\n| --- | --- | --- | ---: | --- | --- |\n'
    + data.rows.map(r => `| ${r.map(markdownText).join(' | ')} |`).join('\n') + '\n';
}

function height(row, widths) {
  // Conservative glyph sizing for wrapped Chinese prose at 11pt, including padding.
  const lines = row.map((value, i) => String(value).split(/\r\n?|\n/).reduce((n, line) => {
    const pixels = [...line].reduce((sum, ch) => sum + (ch.codePointAt(0) > 255 ? 15 : 8), 0);
    return n + Math.max(1, Math.ceil(pixels / (widths[i] - 20)));
  }, 0));
  const pixels = Math.max(46, (Math.max(...lines) + 1) * 21);
  if (pixels > 540) throw Error(`行文本超出可读行高，请拆分过长段落或扩大合理列宽：${String(row[0])}`);
  return pixels;
}

export async function makeWorkbook(data) {
  const total = validate(data);
  const { Workbook } = await library();
  const wb = Workbook.create();
  const sheet = wb.worksheets.add('导演分镜');
  const design = wb.worksheets.add('导演设计');
  const last = data.rows.length + 4;
  sheet.showGridLines = false;
  const all = sheet.getRange(`A1:F${last + 1}`);
  all.format.font = { name: FONT, size: 11, color: '#202832' };
  all.format.wrapText = true;
  all.format.verticalAlignment = 'top';
  WIDTHS.forEach((width, i) => sheet.getRangeByIndexes(0, i, last + 1, 1).format.columnWidthPx = width);
  sheet.mergeCells('A1:F1');
  sheet.getRange('A1').values = [[excelText(data.title)]];
  sheet.getRange('A1:F1').format.font = { name: FONT, size: 16, bold: true };
  sheet.getRange('A1:F1').format.rowHeightPx = 38;
  sheet.mergeCells('A2:C2');
  sheet.getRange('A2').values = [['预计时长（秒）']];
  sheet.getRange('D2').formulas = [[`=SUM(D5:D${last})`]];
  sheet.getRange('E2').values = [[`共${data.rows.length}镜；镜长为拍摄与剪辑估算`]];
  sheet.getRange('F2').values = [[`su-fenjingskill ${VERSION}`]];
  sheet.getRange('A2:F2').format.rowHeightPx = 36;
  sheet.mergeCells('A3:F3');
  sheet.getRange('A3').values = [[excelText(data.settings)]];
  sheet.getRange('A3:F3').format.rowHeightPx = height([data.settings], [WIDTHS.reduce((a, b) => a + b, 0)]);
  sheet.getRange('A4:F4').values = [COLUMNS];
  sheet.getRange('A4:F4').format = { fill: '#303E4D', font: { name: FONT, size: 11, bold: true, color: '#FFFFFF' }, rowHeightPx: 34, wrapText: true };
  sheet.getRange(`A5:F${last}`).values = data.rows.map(r => r.map(excelText));
  sheet.getRange(`A5:A${last}`).setNumberFormat('@');
  for (const [i, row] of data.rows.entries()) {
    const r = sheet.getRangeByIndexes(i + 4, 0, 1, 6);
    r.format.rowHeightPx = height(row, WIDTHS);
    if (i % 2 === 0) r.format.fill = '#F1F4F7';
  }
  sheet.getRange(`D5:D${last}`).setNumberFormat('0"秒"');
  sheet.getRange('D2').setNumberFormat('0');
  sheet.freezePanes.freezeRows(4);

  design.showGridLines = false;
  const designRows = [['设置', data.settings], ...data.design];
  design.getRange(`A1:B${designRows.length + 3}`).format.font = { name: FONT, size: 11, color: '#202832' };
  design.getRange(`A1:B${designRows.length + 3}`).format.wrapText = true;
  design.getRange(`A1:B${designRows.length + 3}`).format.verticalAlignment = 'top';
  design.getRange(`A1:A${designRows.length + 3}`).format.columnWidthPx = 145;
  design.getRange(`B1:B${designRows.length + 3}`).format.columnWidthPx = 900;
  design.mergeCells('A1:B1');
  design.getRange('A1').values = [[excelText(`${data.title} 导演设计`)]];
  design.getRange('A1:B1').format.font = { name: FONT, size: 16, bold: true };
  design.getRange('A1:B1').format.rowHeightPx = 38;
  design.getRange('A2').values = [[`版本 ${VERSION}`]];
  design.getRange('B2').values = [['预计时长（秒）']];
  design.getRange('A3').formulas = [["='导演分镜'!D2"]];
  design.getRange('B3').values = [['各镜时长合计；具体执行可在拍摄和剪辑时微调。']];
  design.getRange(`A4:B${designRows.length + 3}`).values = designRows.map(r => r.map(excelText));
  designRows.forEach((row, i) => {
    const r = design.getRangeByIndexes(i + 3, 0, 1, 2);
    r.format.rowHeightPx = height(row, [145, 900]);
    if (i % 2 === 0) r.format.fill = '#F1F4F7';
  });
  if (Number(sheet.getRange('D2').values[0][0]) !== total) throw Error('Excel合计与行数据不一致。');
  return wb;
}

export async function exportFiles(data, outputDir, prefix, previewDir) {
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(prefix)) throw Error('前缀请使用英文、数字、连字符或下划线。');
  await fs.access(outputDir).then(() => { throw Error('输出目录已存在，请指定新目录以保留原文件。'); }, e => { if (e.code !== 'ENOENT') throw e; });
  const wb = await makeWorkbook(data);
  const { SpreadsheetFile } = await library();
  const xlsx = await SpreadsheetFile.exportXlsx(wb);
  const md = markdown(data);
  // The library may save an inspection sidecar. Keep such support files in a
  // task-owned temporary directory; publish only the two requested documents.
  const staging = await fs.mkdtemp(path.join(os.tmpdir(), 'fenjing-export-'));
  try {
    const stagedXlsx = path.join(staging, `${prefix}-storyboard.xlsx`);
    await xlsx.save(stagedXlsx);
    await fs.mkdir(outputDir, { recursive: true });
    await fs.copyFile(stagedXlsx, path.join(outputDir, `${prefix}-storyboard.xlsx`), 1);
    await fs.writeFile(path.join(outputDir, `${prefix}-storyboard.md`), md, { flag: 'wx' });
  } finally {
    await fs.rm(staging, { recursive: true, force: true });
  }
  if (previewDir) {
    await fs.mkdir(previewDir, { recursive: true });
    for (let start = 5, page = 1; start <= data.rows.length + 4; start += 5, page++) {
      const range = page === 1 ? `A1:F${Math.min(start + 4, data.rows.length + 4)}` : `A${start}:F${Math.min(start + 4, data.rows.length + 4)}`;
      const png = await wb.render({ sheetName: '导演分镜', range, scale: 1, format: 'png' });
      await fs.writeFile(path.join(previewDir, `shots-${page}.png`), new Uint8Array(await png.arrayBuffer()));
    }
    const png = await wb.render({ sheetName: '导演设计', autoCrop: 'all', scale: 1, format: 'png' });
    await fs.writeFile(path.join(previewDir, 'design.png'), new Uint8Array(await png.arrayBuffer()));
  }
  return { version: VERSION, shots: data.rows.length, estimated_seconds: validate(data), output_dir: outputDir };
}

async function main() {
  const args = process.argv.slice(2);
  if (args.includes('--help')) {
    console.log(`su-fenjingskill ${VERSION}\nnode export_storyboard.mjs --input rows.json --output-dir NEW_DIR --prefix NAME [--preview-dir DIR]\nnode export_storyboard.mjs --input rows.json --check`);
    return;
  }
  const option = name => args[args.indexOf(name) + 1];
  if (!args.includes('--input')) throw Error('缺少--input。');
  const data = JSON.parse(await fs.readFile(option('--input'), 'utf8'));
  if (args.includes('--check')) { console.log(JSON.stringify({ version: VERSION, shots: data.rows.length, estimated_seconds: validate(data) })); return; }
  if (!args.includes('--output-dir') || !args.includes('--prefix')) throw Error('缺少--output-dir或--prefix。');
  console.log(JSON.stringify(await exportFiles(data, option('--output-dir'), option('--prefix'), args.includes('--preview-dir') ? option('--preview-dir') : null)));
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
