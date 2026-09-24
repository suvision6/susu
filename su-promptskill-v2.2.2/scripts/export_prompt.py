#!/usr/bin/env python3
"""CLI for an Agent-authored standard Seedance Prompt; no model/API calls."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from prompt_core import load_source, load_master, assess, json_bytes, VERSION
from prompt_formats import build, validate_delivery

def main(argv: list[str] | None=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,help='Agent完成的内部Markdown工作稿；不作为最终Prompt外壳输出')
    p.add_argument('--source',type=Path,help='实际采用导演MD/JSON或事件文字；只读')
    p.add_argument('--context',type=Path,help='可选场次/结束点/素材职责/请求设置，不由用户手填')
    p.add_argument('--check',action='store_true')
    p.add_argument('--output-dir',type=Path)
    p.add_argument('--prefix',default='project')
    p.add_argument('--json-only',action='store_true',help='保存TXT、MD与JSON，不导出Excel')
    p.add_argument('--width-px',type=int,default=2000)
    p.add_argument('--validate',type=Path,help='只复验已交付目录')
    p.add_argument('--version',action='version',version=VERSION)
    args=p.parse_args(argv)
    try:
        if args.validate:
            result=validate_delivery(args.validate,args.source,args.input)
            print(json_bytes(result).decode(),end='');return 1 if result['issues'] else 0
        if args.input is None:p.error('需要--input或--validate')
        source=load_source(args.source)
        master=load_master(args.input,source)
        context=json.loads(args.context.read_text(encoding='utf-8')) if args.context else {}
        report=assess(master,source,context)
        if args.check:
            print(json_bytes(report).decode(),end='');return 1 if report['mechanical_status']=='issues_found' else 0
        if args.output_dir is None:p.error('导出需要--output-dir；仅检查使用--check')
        report=build(master,source,context,report,args.output_dir,args.prefix,args.json_only,args.width_px)
        print(json_bytes({'output':str(args.output_dir),'counts':report['counts'],
                          'mechanical_status':report['mechanical_status'],'issues':report['issues'],
                          'xlsx':report['xlsx'],'semantic_review':'not_performed_by_script'}).decode(),end='')
        if report['xlsx'].get('status')=='failed':return 2
        return 1 if report['mechanical_status']=='issues_found' else 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'error':str(exc),'version':VERSION},ensure_ascii=False),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
