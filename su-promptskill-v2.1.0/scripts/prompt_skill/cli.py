"""Local-only CLI. No network, source writes, paid generation or hidden approval."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from .common import DeliveryError, digest, json_bytes, load_json
from .source import load_source
from .master import draft_master, read_master
from .checks import check_master
from .submission import resolve_profile
from .delivery import compile_delivery, write_delivery, verify_artifacts


def _context(source, path):
    keys = ('task','operations','asset_inventory','asset_assignments','reference_role_map',
            'request_configuration','operation_outputs','scope')
    result = {key:source.document[key] for key in keys if isinstance(source.document, dict) and key in source.document}
    if path:
        supplied = load_json(path.read_bytes())
        if not isinstance(supplied, dict):
            raise DeliveryError('decisions/context 必须为对象')
        result.update(supplied)
    if not result.get('operations') and result.get('task'):
        result['operations'] = [{'operation_id':'OP001','primary':result['task'].get('primary','generate')}]
    return result


def _new_file(path, data, source_path=None):
    path = Path(path)
    if source_path and path.resolve() == Path(source_path).resolve():
        raise DeliveryError('不能覆盖来源')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as handle:
            handle.write(data)
    except FileExistsError as exc:
        raise DeliveryError('输出文件已存在；请使用新文件名') from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description='su-promptskill 2.1.0 · Markdown 主稿与只读交付')
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare', help='从可识别来源生成保守草稿；不冒充中文语义优化')
    prepare.add_argument('--input', type=Path, required=True)
    prepare.add_argument('--output-file', type=Path, required=True)
    build = sub.add_parser('build', help='以主稿为准派生四文件；无主稿时只生成待复核草稿')
    build.add_argument('--input', type=Path, required=True)
    build.add_argument('--master', type=Path)
    build.add_argument('--output-dir', type=Path, required=True)
    build.add_argument('--decisions', type=Path)
    build.add_argument('--review', type=Path)
    profiles = build.add_mutually_exclusive_group()
    profiles.add_argument('--profile-id', default=None)
    profiles.add_argument('--profile-file', type=Path)
    validate = sub.add_parser('validate', help='重新读取来源、主稿、JSON、Excel 与报告')
    validate.add_argument('--input', type=Path, required=True)
    validate.add_argument('--output-dir', type=Path, required=True)
    validate.add_argument('--decisions', type=Path)
    validate.add_argument('--review', type=Path)
    review_parser = sub.add_parser('review-template', help='生成未批准的来源复核记录，不自动通过')
    review_parser.add_argument('--input', type=Path, required=True)
    review_parser.add_argument('--master', type=Path, required=True)
    review_parser.add_argument('--output-file', type=Path, required=True)
    review_parser.add_argument('--decisions', type=Path)
    args = parser.parse_args(argv)
    try:
        source = load_source(args.input)
        if args.command == 'prepare':
            draft = draft_master(source)
            _new_file(args.output_file, draft.payload, args.input)
            output = {'status':'DRAFT','file':str(args.output_file),'source_sha256':source.sha256,
                      'note':'请 Agent 对照原文改写并复核；不是已批准的最终 Prompt'}
        elif args.command == 'review-template':
            master = read_master(args.master.read_bytes())
            context = _context(source, args.decisions)
            check_master(source, master, context)
            review = {'source_sha256':source.sha256,'master_sha256':digest(master.payload),
                      'method':'source-to-prompt-and-back','reviewer':'',
                      'units':{u.id:{'status':'pending','notes':'','unresolved':[]} for u in master.units}}
            _new_file(args.output_file, json_bytes(review), args.input)
            output = {'status':'PENDING_REVIEW','file':str(args.output_file)}
        elif args.command == 'build':
            context = _context(source, args.decisions)
            review = load_json(args.review.read_bytes()) if args.review else {}
            master = read_master(args.master.read_bytes()) if args.master else draft_master(source)
            if args.review and not args.master:
                raise DeliveryError('先写主稿，再复核；不能给自动草稿附加批准标签')
            profile = resolve_profile(args.profile_id or 'seedance-2.5-default', args.profile_file)
            plan, report, artifacts = compile_delivery(source, master, context, review, profile, draft=args.master is None)
            if digest(args.input.read_bytes()) != source.sha256:
                raise DeliveryError('构建期间来源发生变化；停止写交付')
            verified = write_delivery(source, args.output_dir, plan, report, artifacts)
            output = {'status':report['status'],'output_dir':str(args.output_dir),
                      'files':sorted(artifacts),'verification':verified,
                      'submission_ready':plan['submission_ready']}
        else:
            context = load_json(args.decisions.read_bytes()) if args.decisions else None
            review = load_json(args.review.read_bytes()) if args.review else None
            output = verify_artifacts(source, args.output_dir, context=context, review=review)
        if digest(args.input.read_bytes()) != source.sha256:
            raise DeliveryError('执行前后来源内容不一致；已生成文件不得宣称通过')
        print(json_bytes(output).decode('utf-8'), end='')
        return 2 if output.get('status') in {'FAIL','PARTIAL'} else 0
    except (DeliveryError, OSError, KeyError, TypeError, ValueError) as exc:
        print(json_bytes({'status':'FAIL','error':str(exc)}).decode('utf-8'), file=sys.stderr, end='')
        return 2
