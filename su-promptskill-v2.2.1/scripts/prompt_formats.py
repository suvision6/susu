"""Lossless output views of Agent-authored prompt_text; no prompt compilation."""
from __future__ import annotations
from decimal import Decimal
import html
import json
from pathlib import Path
import re
import tempfile
import unicodedata
from typing import Any
from native_xlsx import Sheet, Formula, write_workbook
from reading_xlsx import TextMeasure, read_xlsx
from prompt_core import VERSION, json_bytes, sha

HEADERS=['Prompt段号','来源镜号','总时长（秒）','Prompt']

def safe_id(value: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',value) or '..' in value:
        raise ValueError('文件前缀／单元号使用ASCII字母、数字、单横线或下划线，不允许路径。')
    return value

def md_cell(value: str) -> str:
    # HTML escaping protects <sound> and Markdown pipes while preserving text.
    return html.escape(value,quote=False).replace('|','&#124;').replace('\n','<br>')

def table_text(units: list[dict]) -> str:
    result=['| '+' | '.join(HEADERS)+' |','|---|---|---:|---|']
    for u in units:
        result.append('| '+' | '.join(md_cell(str(v)) for v in [u['id'],'、'.join(u['source_refs']),str(u['duration']) if u['duration'] is not None else '未定',u['prompt_text']])+' |')
    return '\n'.join(result)+'\n'

def export_xlsx(units: list[dict], path: Path, width: int=2000) -> dict:
    if not 900<=width<=2500:raise ValueError('阅读宽度范围900—2500像素；不限制Prompt长度。')
    tm=TextMeasure('Noto Sans CJK SC',11)
    tm.line_height=11*96/72*1.24  # Prompt prose: readable leading without forcing normal groups into continuation rows.
    # Prefer whole prompt cells. Extra rows are an exceptional, lossless display fallback.
    widths=[125.,240.,140.,min(1785.,float(width-505))]
    sheet=Sheet('Prompt Table',widths)
    sheet.merges.append('A1:D1')
    sheet.write(1,['Seedance Prompt',None,None,None],40,'title')
    sheet.write(3,HEADERS,36,'header')
    row=4;locations=[];first=[]
    for i,u in enumerate(units):
        texts=[u['id'],'、'.join(u['source_refs']),u['duration'],u['prompt_text']]
        def display_chunks(value, available_width):
            if not isinstance(value,str):return [value]
            fits=(tm.height(value,available_width)<=409*96/72
                  and len(value.encode('utf-16-le'))//2<=32000 and value.count('\n')<=250)
            return [value] if fits else tm.chunks(value,available_width)
        chunks=[display_chunks(v,w) for v,w in zip(texts,widths)]
        count=max(map(len,chunks));start=row;first.append(row)
        for j in range(count):
            values=[a[j] if j<len(a) else None for a in chunks]
            if j:values[0]=u['id']+f'（续{j}）';values[2]=None
            h=min(409*96/72,max(32,max(tm.height(str(v) if v is not None else '',w) for v,w in zip(values,widths))))
            sheet.write(row,values,h,f'body{i%2}');row+=1
        locations.append({'id':u['id'],'first_row':start,'row_count':count})
    known=sum((u['duration'] for u in units if u['duration'] is not None),Decimal(0))
    sheet.merges.append(f'A{row+1}:B{row+1}')
    sheet.write(row+1,['已知时长合计',None,Formula(f'SUM(C4:C{row-1})',known),None],32,'total')
    write_workbook(path,[sheet],'Noto Sans CJK SC',11)
    saved=read_xlsx(path)['Prompt Table']['cells']
    for u,loc in zip(units,locations):
        text=''.join(saved.get(f'D{r}',{}).get('value','') for r in range(loc['first_row'],loc['first_row']+loc['row_count']))
        if text!=u['prompt_text']:raise ValueError('Excel正文回读不同：'+u['id'])
        if any(saved.get(f'D{r}',{}).get('formula') for r in range(loc['first_row'],loc['first_row']+loc['row_count'])):raise ValueError('Prompt不能作为公式保存。')
    return {'backend':'bundled-stdlib-ooxml','sheet':'Prompt Table','locations':locations,
            'continuation_rows':sum(x['row_count']-1 for x in locations),'readback':'exact',
            'rendering':'not_performed','font_measurement':'measured' if tm.font else 'conservative_estimate'}

def build(master: dict, source: dict | None, context: dict, report: dict, out: Path, prefix: str, json_only: bool=False,width: int=2000) -> dict:
    safe_id(prefix)
    if out.exists():raise FileExistsError('输出目录已经存在；请使用新目录，保留旧稿和批注。')
    out.parent.mkdir(parents=True,exist_ok=True)
    files=[]
    with tempfile.TemporaryDirectory(prefix='.prompt-build-',dir=out.parent) as temp:
        stage=Path(temp);(stage/'prompts').mkdir()
        units=master['units']
        for u in units:
            safe_id(u['id']);p=stage/'prompts'/f'{u["id"]}.txt'
            p.write_bytes(u['prompt_text'].encode('utf-8'))
        md_name=prefix+'-prompt-table.md';(stage/md_name).write_text(table_text(units),encoding='utf-8')
        media={'status':'not_requested'}
        if not json_only:
            try:media={'status':'saved',**export_xlsx(units,stage/(prefix+'-prompt-table.xlsx'),width)}
            except Exception as exc:
                media={'status':'failed','message':str(exc)}
                partial=stage/(prefix+'-prompt-table.xlsx')
                if partial.exists():partial.unlink()
        source_snapshot=None if source is None else {'sha256':source['sha256'],'file':source['file'],'raw_text':source['raw_text'],'context':source['context'],'source_kind':source['source_kind']}
        plan={'format':'su-prompt-plan/2.2','version':VERSION,'title':master['title'],'source':source_snapshot,
              'authoring':master,'context':context,
              'units':[{'id':u['id'],'source_refs':u['source_refs'],'duration_seconds':u['duration'],'mode':u['mode'],
                        'prompt_text':u['prompt_text'],'prompt_sha256':sha(u['prompt_text'].encode()),'prompt_file':f'prompts/{u["id"]}.txt'} for u in units],
              'xlsx':media,'audit_scope':'Explicit structure and source mapping only; prose authored and reviewed by Agent.'}
        plan_name=prefix+'-prompt-plan.json';(stage/plan_name).write_bytes(json_bytes(plan))
        report={**report,'source_sha256':source['sha256'] if source else None,'master_sha256':master['master_sha256'],
                'content_delivery':'authored_prompt_text_saved','xlsx':media,'file_integrity':'checked','files':[]}
        for path in sorted(stage.rglob('*')):
            if path.is_file():report['files'].append({'path':str(path.relative_to(stage)),'sha256':sha(path.read_bytes())})
        (stage/(prefix+'-prompt-validation.json')).write_bytes(json_bytes(report))
        # Read-back before publishing. Integrity never claims semantic approval.
        check=json.loads((stage/plan_name).read_text())
        for u in check['units']:
            if (stage/u['prompt_file']).read_text()!=u['prompt_text']:raise ValueError('TXT与Plan正文不一致。')
        if (stage/md_name).read_text()!=table_text(units):raise ValueError('Markdown保存错误。')
        stage.chmod(0o755)
        stage.rename(out)
    return report

def validate_delivery(out: Path, source: Path | None=None, master: Path | None=None) -> dict:
    reports=list(out.glob('*-prompt-validation.json'))
    if len(reports)!=1:raise ValueError('目录需含唯一验证文件。')
    report=json.loads(reports[0].read_text());problems=[]
    if source and sha(source.read_bytes())!=report.get('source_sha256'):problems.append('来源文件与交付时不同')
    if master and sha(master.read_bytes())!=report.get('master_sha256'):problems.append('工作稿与交付时不同')
    for f in report.get('files',[]):
        path=out/f['path']
        if not path.is_file() or sha(path.read_bytes())!=f['sha256']:problems.append('文件缺失或改变：'+f['path'])
    plans=list(out.glob('*-prompt-plan.json'))
    if len(plans)!=1:problems.append('Plan不唯一')
    else:
        plan=json.loads(plans[0].read_text())
        for u in plan['units']:
            p=out/u['prompt_file']
            if not p.is_file() or p.read_text()!=u['prompt_text']:problems.append('TXT/Plan不一致：'+u['id'])
        if report.get('xlsx',{}).get('status')=='saved':
            paths=list(out.glob('*-prompt-table.xlsx'))
            if len(paths)!=1:problems.append('Excel缺失或不唯一')
            else:
                saved=read_xlsx(paths[0])['Prompt Table']['cells']
                for u,loc in zip(plan['units'],report['xlsx']['locations']):
                    actual=''.join(saved.get(f'D{r}',{}).get('value','') for r in range(loc['first_row'],loc['first_row']+loc['row_count']))
                    if actual!=u['prompt_text']:problems.append('Excel/Plan不一致：'+u['id'])
    return {'file_integrity':'different' if problems else 'checked','issues':problems,
            'semantic_review':'not_performed_by_script','tamper_resistance':'hash consistency, not a digital signature'}
