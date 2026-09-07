"""Freeze approved Markdown, derive views, and verify saved content separately."""
from __future__ import annotations
import copy
from pathlib import Path
import shutil
import tempfile
from .common import VERSION, DeliveryError, digest, json_bytes, load_json, object_hash, slug_for
from .source import Source
from .master import Master, read_master, write_master
from .checks import check_master
from .submission import submission_checks
from .formats import xlsx_bytes, read_xlsx


def filenames(slug):
    return {'plan': slug+'-prompt-plan.json', 'markdown': slug+'-prompt-table.md',
            'xlsx': slug+'-prompt-table.xlsx', 'validation': slug+'-prompt-validation.json'}


def report_hash(report):
    value = copy.deepcopy(report); value.pop('report_content_hash', None)
    return object_hash(value)


def plan_hash(plan):
    value = copy.deepcopy(plan); value.pop('content_hash', None)
    return object_hash(value)


def compile_delivery(source: Source, master: Master, context: dict, review: dict, profile: dict, *, draft=False, xlsx_writer=None):
    if not master.payload:
        master.payload = write_master(master)
    # Parse the actual frozen bytes again, not the caller's mutable in-memory object.
    master = read_master(master.payload)
    checks = check_master(source, master, context, review)
    submission = submission_checks(source, master, context, profile, checks)
    slug = slug_for(source.name, source.payload); files = filenames(slug)
    units = []
    for u in master.units:
        units.append({'prompt_unit_id': u.id, 'source_shot_ids': u.source_ids, 'operation_id': u.operation,
                      'total_duration_seconds_exact': None if u.duration is None else format(u.duration, 'f'),
                      'prompt_text': u.text, 'validation': checks['units'][u.id],
                      'submission': submission[u.id]})
    plan = {'contract': 'prompt-plan/'+VERSION, 'skill': {'name':'su-promptskill', 'version':VERSION},
            'authoring': 'literal-compatibility-draft' if draft else 'frozen-markdown-master',
            'source': {'name':source.name, 'sha256':source.sha256,
                       'original_utf8': source.payload.decode('utf-8'), 'document':source.document},
            'master_sha256': digest(master.payload), 'scope':master.scope, 'prompt_units':units,
            'compiler_inputs': {'context':context, 'review':review, 'profile':profile},
            'submission_ready': all(s['submission_ready'] for s in submission.values()) and not draft,
            'delivery': {'files':files}, 'source_field_dispositions': source.issues,
            'validation': checks}
    artifacts = {files['markdown']:master.payload}
    xlsx_error = None
    try:
        artifacts[files['xlsx']] = (xlsx_writer or xlsx_bytes)(master)
    except Exception as exc:
        # Only the reading view is isolated; errors never erase a valid master.
        xlsx_error = f'{type(exc).__name__}: {exc}'
    blocked = sum(u['validation']['mechanical_status'] == 'FAIL' for u in units)
    status = 'FAIL' if blocked == len(units) else 'PARTIAL' if blocked or xlsx_error else 'PASS' if plan['submission_ready'] else 'WARN'
    report = {'contract':'prompt-validation/'+VERSION, 'status':status,
              'source_sha256':source.sha256, 'master_sha256':digest(master.payload),
              'content_fidelity':{u['prompt_unit_id']:u['validation']['content_fidelity'] for u in units},
              'submission_ready':plan['submission_ready'],
              'file_integrity':{'complete':xlsx_error is None, 'saved_file_readback':'pending',
                                'missing_files':[files['xlsx']] if xlsx_error else []},
              'readability':{'status':'not_rendered', 'measurement':'conservative-unicode-estimate',
                             'note':'续行与保存内容已由程序检查；真实客户端视觉效果需要抽检'},
              'limitations':['语义复核是有来源绑定的 Agent 声明，不是程序对任意自然语言的完整证明'],
              'xlsx_error':xlsx_error, 'units':checks['units'], 'submission_conditions':submission}
    plan['delivery']['complete'] = xlsx_error is None
    plan['content_hash'] = plan_hash(plan)
    artifacts[files['plan']] = json_bytes(plan)
    report['plan_sha256'] = digest(artifacts[files['plan']])
    report['artifact_sha256'] = {name:digest(data) for name,data in artifacts.items()}
    report['report_content_hash'] = report_hash(report)
    artifacts[files['validation']] = json_bytes(report)
    return plan, report, artifacts


def _logical(master):
    return [[u.id, u.source_ids, u.duration, u.text] for u in master.units]


def verify_artifacts(source: Source, folder: Path, *, context=None, review=None):
    slug = slug_for(source.name, source.payload); files = filenames(slug)
    try:
        master_payload = (folder/files['markdown']).read_bytes()
        plan_payload = (folder/files['plan']).read_bytes()
        report_payload = (folder/files['validation']).read_bytes()
    except OSError as exc:
        raise DeliveryError(f'正式文件缺失或不可读：{exc}') from exc
    master = read_master(master_payload); plan = load_json(plan_payload); report = load_json(report_payload)
    if plan.get('contract') != 'prompt-plan/'+VERSION or report.get('contract') != 'prompt-validation/'+VERSION:
        raise DeliveryError('交付合同版本不匹配；历史交付使用原版本验证器')
    if report.get('report_content_hash') != report_hash(report):
        raise DeliveryError('REPORT_CONTENT_CHANGED：验证报告内容被修改')
    if plan['source']['document'] != source.document or plan['delivery']['files'] != files:
        raise DeliveryError('来源文档快照或交付文件清单不一致')
    if plan.get('content_hash') != plan_hash(plan):
        raise DeliveryError('PLAN_CONTENT_CHANGED：JSON 内容 hash 不匹配')
    if plan['source']['sha256'] != source.sha256 or plan['source']['original_utf8'].encode('utf-8') != source.payload:
        raise DeliveryError('来源原始内容被替换')
    if master.source_sha256 != source.sha256 or plan['master_sha256'] != digest(master_payload):
        raise DeliveryError('Markdown 主稿已变化，须重新复核和派生')
    inputs = plan['compiler_inputs']
    if context is not None and context != inputs['context']:
        raise DeliveryError('指定 context 与保存快照不一致')
    if review is not None and review != inputs['review']:
        raise DeliveryError('指定 review 与保存快照不一致')
    checked = check_master(source, master, inputs['context'], inputs['review'])
    conditions = submission_checks(source, master, inputs['context'], inputs['profile'], checked)
    if plan['validation'] != checked or report['units'] != checked['units'] or report['submission_conditions'] != conditions:
        raise DeliveryError('验证记录与来源重新核对结果不一致')
    expected_units = [(u.id,u.source_ids,u.operation,u.text,None if u.duration is None else format(u.duration,'f')) for u in master.units]
    actual_units = [(u['prompt_unit_id'],u['source_shot_ids'],u['operation_id'],u['prompt_text'],u['total_duration_seconds_exact']) for u in plan['prompt_units']]
    if actual_units != expected_units:
        raise DeliveryError('JSON 与 Markdown 正文、来源或时长不一致')
    if report['plan_sha256'] != digest(plan_payload):
        raise DeliveryError('验证报告中的 JSON 摘要不一致')
    if report['artifact_sha256'].get(files['markdown']) != digest(master_payload):
        raise DeliveryError('验证报告中的主稿摘要不一致')
    xlsx_path = folder/files['xlsx']; layout_changed = False
    if xlsx_path.exists():
        from decimal import Decimal
        import json
        physical = read_xlsx(xlsx_path.read_bytes())
        logical = [[r[0],json.loads(r[1]),None if not r[2] else Decimal(r[2]),r[3]] for r in physical]
        if logical != _logical(master):
            raise DeliveryError('Excel 内容或续行顺序与主稿不一致')
        layout_changed = report['artifact_sha256'].get(files['xlsx']) != digest(xlsx_path.read_bytes())
    elif plan['delivery']['complete'] or files['xlsx'] not in report['file_integrity']['missing_files']:
        raise DeliveryError('Excel 意外缺失')
    # Regenerate report metadata, NOT prose, to detect altered validation claims.
    blocked = sum(c['mechanical_status'] == 'FAIL' for c in checked['units'].values())
    ready = all(c['submission_ready'] for c in conditions.values()) and plan['authoring'] != 'literal-compatibility-draft'
    expected_status = 'FAIL' if blocked == len(master.units) else 'PARTIAL' if blocked or not xlsx_path.exists() else 'PASS' if ready else 'WARN'
    if plan['submission_ready'] != ready or report['submission_ready'] != ready or report['status'] != expected_status:
        raise DeliveryError('就绪或完成状态被修改')
    if report['readability']['status'] not in {'not_rendered'}:
        raise DeliveryError('自动交付报告不能自报已经进行视觉检查；视觉证据另存维护记录')
    return {'status':expected_status, 'file_integrity':'PASS' if xlsx_path.exists() else 'PARTIAL',
            'layout_changed_only':layout_changed, 'submission_ready':ready,
            'semantic_coverage_proven_by_code':False, 'readability':'not_rendered'}


def write_delivery(source: Source, output_dir: str | Path, plan: dict, report: dict, artifacts: dict):
    output = Path(output_dir).resolve()
    if output.exists():
        raise DeliveryError('输出目录已存在；请使用新目录，禁止覆盖来源或既有交付')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.'+output.name+'-', dir=output.parent))
    try:
        for name, payload in artifacts.items():
            (temporary/name).write_bytes(payload)
        verify_artifacts(source, temporary)
        # File verification status is recorded only after reading the actual saved files.
        report['file_integrity']['saved_file_readback'] = 'passed'
        report['report_content_hash'] = report_hash(report)
        report_name = plan['delivery']['files']['validation']
        (temporary/report_name).write_bytes(json_bytes(report))
        verify_artifacts(source, temporary)
        # mkdir is an exclusive claim; avoids rename overwriting an empty existing directory.
        output.mkdir()
        try:
            for path in temporary.iterdir():
                path.replace(output/path.name)
        except Exception:
            report['file_integrity']['saved_file_readback'] = 'interrupted'
            raise
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return verify_artifacts(source, output)
