import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { parseMarkdown, exportFiles, makeWorkbook } from '../../su-fenjingskill-v3.3.1/scripts/export_storyboard.mjs';

const root = await fs.mkdtemp(path.join(os.tmpdir(), 'su331-regression-'));
const fontOptions = process.env.STORYBOARD_TEST_FONT ? { font: 'Noto Sans SC', fontFile: process.env.STORYBOARD_TEST_FONT } : {};
console.log('TEST OUTPUT ' + root);
const skill = fileURLToPath(new URL('../../su-fenjingskill-v3.3.1/', import.meta.url));
const cli = path.join(skill, 'scripts/export_storyboard.mjs');
const template = await fs.readFile(path.join(skill, 'templates/storyboard.md'), 'utf8');
const fence = text => {
  const runs = text.match(/`+/g) ?? [];
  const f = '`'.repeat(Math.max(3, ...runs.map(x => x.length + 1)));
  return f + 'text\n' + (text ? text + '\n' : '') + f;
};
const block = (id, scene, source, seconds, description, notes = '') => '### 镜头 ' + id + '\n场景：' + scene + '\n镜头时长：' + seconds + '秒\n\n#### 原剧本段落\n' + fence(source) + '\n\n#### 运镜＋主画面描述\n' + fence(description) + '\n\n#### 备注\n' + fence(notes) + '\n';
const header = template.slice(0, template.indexOf('### 镜头 01'));
const passed = [];
const record = name => { passed.push(name); console.log('PASS ' + name); };
const expectFailure = (name, text, pattern) => { assert.throws(() => parseMarkdown(text), pattern); record(name); };

assert.equal(parseMarkdown(template).total, 4);
assert.equal(parseMarkdown(template.replaceAll('\n', '\r\n')).rows[0][2], parseMarkdown(template).rows[0][2]);
record('模板与CRLF读取');
expectFailure('重复镜号定位', template + '\n' + template.slice(template.indexOf('### 镜头 01')), /第\d+行，镜头01：镜号重复/);
expectFailure('重复字段定位', template.replace('场景：厨房·夜·内', '场景：厨房·夜·内\n场景：重复'), /镜头01.*重复字段/);
expectFailure('未闭合围栏定位', template.slice(0, template.lastIndexOf('```')), /镜头01.*未闭合/);
expectFailure('非整数拒绝', template.replace('4秒', '4.5秒'), /正整数秒/);
expectFailure('零秒拒绝', template.replace('4秒', '0秒'), /正整数秒/);
expectFailure('缺少字段拒绝', template.replace('#### 备注', '#### 其他'), /镜头01.*备注/);
expectFailure('不接受JSON主稿', '{"rows":[]}', /第1行/);

const special = '=SUM(A1:A2) | <br> & &#124; \\ "引号"\n\n  前后空格  \n```\n#### 备注\n👨‍👩‍👧‍👦 café e\u0301\n尾文字\n';
const cross = header + block('A-01', '厨房·夜·内', '她说：“不要开门，等我回来。”', 3, '【近景，固定】她按住钥匙，说：“不要开门，”。') + '\n'
  + block('B-01', '走廊·夜·内', '【声源：厨房】\n她说：“不要开门，等我回来。”\n【画面：走廊】\n他停在门口，没有开门。', 4, '【中景，固定】他停在门口；她的声音从上镜续入：“等我回来。”他没有开门。', special) + '\n'
  + block('A-02', '厨房·夜·内', '她关灯，钥匙仍在她手中。', 2, '【中景，固定】她握着钥匙关灯。') + '\n## 工作续记\n已完成A-02；钥匙在她手中。下一步从楼下接续。\n';
const parsed = parseMarkdown(cross);
expectFailure('续记之后追加镜头不可静默遗漏', cross + '\n' + block('B-02', '楼下·夜·内', '他等待。', 3, '【中景，固定】他等待。'), /工作续记须在所有镜头之后/);
assert.deepEqual(parsed.rows.map(r => r[0]), ['A-01', 'B-01', 'A-02']);
assert.equal(parsed.rows[1][5], special);
assert.equal(parsed.total, 9);
record('特殊字符、围栏、空行与A-B-A顺序');
const crossPath = path.join(root, 'cross.md');
await fs.writeFile(crossPath, cross);
const crossOut = path.join(root, 'cross-output-v2');
await fs.mkdir(crossOut, { recursive: true });
await fs.writeFile(path.join(crossOut, 'human-notes.txt'), '保留人类记录');
const result = await exportFiles(crossPath, crossOut, '交叉声画', { previewDir: path.join(root, 'cross-preview-v2'), ...fontOptions });
assert.equal(result.shots, 3); assert.equal(result.estimated_seconds, 9);
assert.equal(await fs.readFile(path.join(crossOut, 'human-notes.txt'), 'utf8'), '保留人类记录');
assert.equal(await fs.readFile(result.markdown, 'utf8'), cross);
record('已有目录、中文前缀、保存回读与两表预览');
const old = await fs.readFile(result.excel);
await assert.rejects(exportFiles(crossPath, crossOut, '交叉声画'), /同名Excel已存在/);
assert.deepEqual(await fs.readFile(result.excel), old);
const replaced = await exportFiles(crossPath, crossOut, '交叉声画', { replace: true, ...fontOptions });
assert.deepEqual(await fs.readFile(replaced.backup), old);
record('同名保护与替换备份');

const longHeader = header.replace('# 厨房告别', '# ' + '标题很长但全文保留。'.repeat(180))
  .replace('设置：16:9；自然口语；无固定总时长', '设置：' + '16:9；设置全文保留。'.repeat(180))
  .replace('切菜声保持日常节拍，钥匙声短暂突显。预计时长随完整表演判断。', '设计说明完整保留。'.repeat(4200));
const source668 = '她没有开门，钥匙仍在手中。'.repeat(60).slice(0, 668);
assert.equal(source668.length, 668);
const long = longHeader + block('01', '场景。'.repeat(220), source668, 180, '动作与声音按次序继续。'.repeat(3200) + '尾文字', '\n'.repeat(300) + '备注完整保留。'.repeat(120)) + '\n'
  + block('02', '厨房·夜·内', '她等候。', 36, '【中景，固定】她等候，没有开门。');
await fs.writeFile(path.join(root, 'long.md'), long);
const longResult = await exportFiles(path.join(root, 'long.md'), path.join(root, 'long-output-v2'), '长文', fontOptions);
assert.equal(longResult.shots, 2); assert.equal(longResult.estimated_seconds, 216);
assert.ok(longResult.physical_shot_rows > 2);
record('668字原文、超32767字单格、300换行、长标题设置设计场景备注');

const built = await makeWorkbook(parseMarkdown(long), fontOptions);
assert.notDeepEqual(built.plans[0].widths, (await makeWorkbook(parseMarkdown(template), fontOptions)).plans[0].widths);
for (const plan of built.plans) assert.ok(plan.rows.every(r => r.height <= 409 * 4 / 3));
for (const [planIndex, plan] of built.plans.entries()) {
  const start = planIndex ? plan.rows.findIndex(r => r.role === 'body' && r.cells[1].length > 500) : plan.shots[0].begin - 1;
  const end = planIndex ? start + 1 : plan.shots[0].begin - 1 + plan.shots[0].count;
  const ranges = [start, end - 1];
  for (const [n, row] of ranges.entries()) {
    const col = planIndex ? 'B' : 'F';
    const blob = await built.wb.render({ sheetName: plan.name, range: 'A' + (row + 1) + ':' + col + (row + 1), scale: 1, format: 'png' });
    await fs.writeFile(path.join(root, 'long-' + planIndex + '-' + n + '.png'), new Uint8Array(await blob.arrayBuffer()));
  }
}
record('内容相关列宽、行高容量与长文首尾预览');

const loader = path.join(root, 'deny-excel.mjs');
await fs.writeFile(loader, "export async function resolve(specifier, context, next) { if (specifier.includes('@oai/artifact-tool')) throw new Error('TEST_EXCEL_UNAVAILABLE'); return next(specifier, context); }\n");
const denied = (extra) => spawnSync(process.execPath, ['--experimental-loader', loader, cli, '--input', crossPath, ...extra], { cwd: root, encoding: 'utf8' });
assert.equal(denied(['--check']).status, 0);
const noExcelDir = path.join(root, 'no-excel');
const failed = denied(['--output-dir', noExcelDir, '--prefix', '保留主稿']);
assert.equal(failed.status, 1); assert.match(failed.stderr, /TEST_EXCEL_UNAVAILABLE/);
assert.equal(await fs.readFile(path.join(noExcelDir, '保留主稿-storyboard.md'), 'utf8'), cross);
assert.ok(!(await fs.readdir(noExcelDir)).some(x => x.endsWith('.xlsx') || x.startsWith('.fenjing-stage-')));
record('真实阻断Excel依赖时检查可用、主稿保留、临时目录清理');

const resume = cross + '\n';
const changed = parseMarkdown(resume.replace('他没有开门。', '他仍没有开门。'));
assert.equal(changed.rows[0][4], parsed.rows[0][4]);
assert.equal(changed.rows[2][4], parsed.rows[2][4]);
assert.equal(changed.continuation.trim(), parsed.continuation.trim());
record('局部编辑保留其余镜头与续记');
console.log('RESULT ' + JSON.stringify({ shots: longResult.shots, seconds: longResult.estimated_seconds, physicalRows: longResult.physical_shot_rows }));
await fs.writeFile(path.join(root, 'results.json'), JSON.stringify({ passed, runtime: process.version, outputs: [result, longResult] }, null, 2));
console.log('PASS TOTAL ' + passed.length);
