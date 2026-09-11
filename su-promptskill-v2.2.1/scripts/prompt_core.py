"""Read authored Seedance prompts and check explicit mappings; never write prose.

This module does not infer correct cuts, scenes, acting, reference identity,
or API availability. A successful check is not a semantic or video evaluation.
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from master_io import Document, FormatError, parse_master

VERSION = (Path(__file__).resolve().parents[1] / 'VERSION').read_text().strip()
STANDARD_HEADINGS = ['生成目标', '参考素材职责', '未采用素材', '主体、关系与场景', '镜头脚本', '声音与台词', '保持一致']
TAG = re.compile(r'@(?:图片|视频|音频|Image|Video|Audio)[ \t]*\d+', re.I)
CUT = re.compile(r'^Cut\s+(\d+)(?:[ \t]*[｜|:：].*)?[ \t]*$', re.M)
SOURCE_SPEECH = re.compile(r'(?P<speaker>[\w\u3400-\u9fff·]{1,30})[（(](?P<voice>[^）)\n]+)[）)][：:]\s*(?:“(?P<cn>[^”]*)”|"(?P<en>[^"\n]*)")')
PAYLOAD = re.compile(r'\{([^{}]*)\}', re.S)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def json_bytes(value: Any) -> bytes:
    def encode(x):
        if isinstance(x, Decimal):return str(x)
        raise TypeError(f'Cannot serialize {type(x).__name__}')
    return (json.dumps(value, ensure_ascii=False, indent=2, default=encode)+'\n').encode('utf-8')

def number(value: Any) -> Decimal | None:
    if value is None or str(value).strip() in {'','未知','暂未确定','未定','待定','null'}:
        return None
    if isinstance(value, bool):
        raise FormatError('时长不能使用布尔值。')
    text = re.sub(r'\s*秒$', '', str(value).strip())
    try:n = Decimal(text)
    except InvalidOperation as e:raise FormatError(f'无法读取时长：{value!r}') from e
    if not n.is_finite() or n <= 0:raise FormatError('已知时长必须是有限正数；未知使用null或“暂未确定”。')
    return n

def voiced(body: str) -> list[dict]:
    matches=[(m.start(), {'speaker':m['speaker'], 'voice':m['voice'], 'text':m['cn'] if m['cn'] is not None else m['en']})
             for m in SOURCE_SPEECH.finditer(body)]
    # Plain full-line character cues in event text are explicit; prose quotations
    # without a character cue are not treated as newly discovered dialogue.
    excluded={'场景','地点','时间','动作','画面','镜头','声音','字幕','备注','台词'}
    simple=re.compile(r'^[ \t]*([\w\u3400-\u9fff·]{1,30})[：:][ \t]*(.+?)$',re.M)
    for m in simple.finditer(body):
        if m[1] in excluded:continue
        literal=m[2].strip()
        if len(literal)>=2 and (literal[0],literal[-1]) in {('“','”'),('"','"')}:
            literal=literal[1:-1]
        matches.append((m.start(), {'speaker':m[1], 'voice':'', 'text':literal}))
    return [e for _,e in sorted(matches,key=lambda x:x[0])]

def load_source(path: Path | None) -> dict | None:
    if path is None:return None
    path = Path(path).resolve(); raw=path.read_bytes()
    text=raw.decode('utf-8-sig')
    if path.suffix.lower()=='.json':
        document=json.loads(text, parse_float=Decimal)
        if isinstance(document,list):document={'shots':document}
        if not isinstance(document,dict):raise FormatError('JSON来源必须是对象或镜头数组。')
    elif re.search(r'^### 镜头\s+\S+',text,re.M):
        # Preserve the existing director template; no agent-specific contract migration.
        document=parse_master(path,'director')
    else:document={'text':text,'source_kind':'event'}
    rows=document.get('shots',document.get('source_shots'))
    if rows is None:
        event=document.get('text',document.get('script'))
        if not isinstance(event,str) or not event.strip():raise FormatError('未找到镜头数组或可读text，不能猜未知字段。')
        rows=[{'id':'P001','source_kind':'event','body':event}]
    if not isinstance(rows,list) or not rows:raise FormatError('来源列表为空。')
    items=[];seen=set()
    for i,r in enumerate(rows):
        if not isinstance(r,dict):raise FormatError(f'来源第{i+1}项不是对象。')
        sid=str(r.get('id',r.get('source_shot_id',r.get('shot_id',f'P{i+1:03d}'))))
        if not sid or sid in seen:raise FormatError(f'来源编号为空或重复：{sid}')
        seen.add(sid)
        body=r.get('body',r.get('execution_text',r.get('rendered_shot_description','')))
        if not isinstance(body,str):raise FormatError(f'{sid}执行正文不是文字。')
        explicit=r.get('dialogue',r.get('dialogues'))
        if explicit is None and isinstance(r.get('sound'),dict):explicit=r['sound'].get('dialogue_segments')
        events=None
        if isinstance(explicit,list) and all(isinstance(e,dict) and isinstance(e.get('text'),str) for e in explicit):
            events=[{'speaker':str(e.get('speaker',e.get('character',''))),'voice':str(e.get('position',e.get('delivery',''))),'text':e['text']} for e in explicit]
        if events is None:events=voiced(body)
        # body and source excerpt are intentionally separate. Never speak the excerpt twice.
        items.append({'id':sid,'kind':r.get('source_kind','event' if document.get('source_kind')=='event' else 'shot'),
                      'scene':r.get('scene',r.get('scene_id',r.get('scene_context',''))),
                      'scene_id':r.get('scene_id'),'duration':number(r.get('duration_exact',r.get('duration_seconds',r.get('duration')))),
                      'body':body,'source_text':r.get('source_text',r.get('source_excerpt','')),
                      'dialogue':events,'dialogue_conflict': bool(voiced(body) and explicit is not None and [e['text'] for e in events] != [e['text'] for e in voiced(body)]),
                      'dialogue_basis':'structured_or_explicit_cues_only','raw':r})
    return {'file':str(path),'sha256':sha(raw),'raw_text':text,'document':document,'shots':items,
            'context':document.get('context',''),'source_kind':document.get('source_kind','director')}

def parse_refs(text: str, source: dict | None) -> list[str]:
    text=text.strip()
    if text.startswith('['):
        refs=json.loads(text)
        if not isinstance(refs,list) or not all(isinstance(x,str) and x for x in refs):raise FormatError('来源使用非空字符串数组。')
        return refs
    # A range is resolved against actual source order, NOT arithmetic guesses.
    match=re.fullmatch(r'(?:镜头|源镜|源段)?\s*([\w.-]+)\s*[—–~～至]\s*(?:镜头|源镜|源段)?\s*([\w.-]+)',text)
    if not match:match=re.fullmatch(r'(?:镜头|源镜|源段)\s*(\d+)\s*-\s*(\d+)',text)
    if match:
        if not source:raise FormatError('范围式镜号需要--source；也可改为完整来源数组，不自动漏掉中间镜。')
        ids=[s['id'] for s in source['shots']]
        if match[1] not in ids or match[2] not in ids:raise FormatError('来源范围端点不在实际采用稿中。')
        a,b=ids.index(match[1]),ids.index(match[2])
        if b<a:raise FormatError('来源范围倒序。')
        return ids[a:b+1]
    # Validate the whole list. Do not return only the first prefixed item.
    cleaned=re.sub(r'(?:镜头|源镜|源段)\s*','',text)
    parts=re.split(r'[、,，\s]+',cleaned)
    if parts and all(re.fullmatch(r'[\w.-]+',x) for x in parts):return parts
    raise FormatError(f'来源定位无法无歧义读取：{text}')

def load_master(path: Path, source: dict | None) -> dict:
    raw=Path(path).read_bytes(); doc=Document(raw.decode('utf-8-sig'))
    def field(fragment: str, names: list[str], default: str='') -> str:
        for n in names:
            value=doc.field(fragment,n,'Prompt工作稿',False)
            if value:return value
        return default
    root_info=doc.before_children(doc.root)
    units=[]; seen=set()
    for h in doc.headings:
        m=re.fullmatch(r'(?:单元\s+)?([A-Za-z][A-Za-z0-9_.-]*)',h.title)
        if h.level!=2 or not m:continue
        uid=m[1]
        if uid in seen:raise FormatError(f'重复单元：{uid}')
        seen.add(uid)
        fence_start=next((a for a,b,_ in doc.fences if h.body<=a<h.end),h.end)
        info=doc.text[h.body:min(fence_start,h.end)]
        src=field(info,['来源','对应来源'])
        if not src:raise FormatError(f'{uid}缺来源定位。')
        pnode=doc.find('Prompt',3,h)
        prompt=doc.fenced(pnode or h)
        duration=number(field(info,['预计时长','内容预计时长','时长'],'暂未确定'))
        notes=doc.find('素材与提交说明',3,h)
        units.append({'id':uid,'source_refs':parse_refs(src,source),'source_scope':src,
                      'duration':duration,'mode':field(info,['操作'],'generate'),
                      'operation_id':field(info,['操作ID'],'OP001'),'prompt_text':prompt,
                      'submission_notes':doc.text[notes.body:notes.end].strip() if notes else ''})
    if not units:raise FormatError('未找到单元。使用“## 单元 G01”与一个完整prompt围栏。')
    return {'title':doc.root.title,'master_file':str(Path(path).resolve()),'master_sha256':sha(raw),
            'master_text':doc.text,'source_description':field(root_info,['本轮来源']),
            'scope_text':field(root_info,['本轮范围']),
            'shared_context':doc.raw_section('共用执行依据'),
            'units':units}

def sections(text: str) -> dict[str,str]:
    matches=list(re.finditer(r'^【([^】\n]+)】[ \t]*$',text,re.M));out={}
    for i,m in enumerate(matches):out[m[1]]=text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)].strip()
    return out

def cut_segments(text: str) -> list[str]:
    area=sections(text).get('镜头脚本',text)
    markers=list(CUT.finditer(area))
    return [area[m.end():markers[i+1].start() if i+1<len(markers) else len(area)] for i,m in enumerate(markers)]

def voice_kind(value: str) -> str | None:
    v=value.lower()
    if '内心' in v:return 'inner'
    if '旁白' in v or v in {'vo','voiceover','voice_over'}:return 'narration'
    if '画外' in v or v in {'offscreen','off_screen'}:return 'offscreen'
    if '画内' in v or v in {'onscreen','on_screen'}:return 'onscreen'
    if '媒介' in v:return 'mediated'
    return None

# These are declared uses, not a machine inference of dramatic closure.
HARD_BOUNDARY_KINDS = {'semantic_end', 'scene_change', 'time_break', 'reality_break'}
BOUNDARY_KINDS = HARD_BOUNDARY_KINDS | {'submission_split', 'historical_split'}
SCENE_PREFIX = re.compile(r'^(S\d+[A-Za-z]?|\d+-\d+[A-Za-z]?)(?=$|[\s·｜|:：])')


def _grouping_inputs(master: dict, source: dict | None, context: dict, add):
    """Validate explicit grouping metadata without making directing decisions.

    Source order and explicit scene identity are authoritative. Missing boundary
    classifications stay visible: they are neither semantic locks nor permission
    to silently cross an inherited, potentially intentional split.
    """
    order = [s['id'] for s in source['shots']] if source else []
    positions = {sid: i for i, sid in enumerate(order)}
    operations = list(dict.fromkeys(u['operation_id'] for u in master['units']))

    def scope_ids(value, label):
        if not isinstance(value, list) or not value:
            add('SCOPE_TYPE', label + '必须是非空的原源镜字符串数组。')
            return []
        if any(not isinstance(x, str) or not x or x != x.strip() for x in value):
            add('SCOPE_ID_TYPE', label + '镜号必须是原样字符串；不把数字1猜成01。')
            return []
        if len(value) != len(set(value)):
            add('SCOPE_DUPLICATE', label + '重复引用源镜。')
        if source:
            unknown = [x for x in value if x not in positions]
            if unknown:
                add('SCOPE_UNKNOWN', label + '镜号不在采用来源：' + '、'.join(unknown))
            indices = [positions[x] for x in value if x in positions]
            if indices != sorted(indices):
                add('SCOPE_ORDER', label + '必须是原源序的有序选择，不能用倒序scope替倒序输出背书。')
        return value

    global_scope = scope_ids(context['scope'], 'scope') if 'scope' in context else order
    op_scopes = context.get('operation_scopes', {})
    if not isinstance(op_scopes, dict):
        add('OPERATION_SCOPES_TYPE', 'operation_scopes必须是按实际操作ID索引的对象。')
        op_scopes = {}
    expected = {}
    for op, values in op_scopes.items():
        if op not in operations:
            add('OPERATION_SCOPE_UNKNOWN', 'operation_scopes引用不存在的操作：' + str(op))
        selected = scope_ids(values, 'operation_scopes.' + str(op))
        if 'scope' in context and any(x not in global_scope for x in selected):
            add('OPERATION_SCOPE_OUTSIDE', str(op) + '的范围超出本轮scope。')
        expected[op] = selected
    for op in operations:
        expected.setdefault(op, global_scope)

    mapping = context.get('scene_keys', {})
    if not isinstance(mapping, dict):
        add('SCENE_KEYS_TYPE', 'scene_keys必须是源镜号到场次号的对象。')
        mapping = {}
    for sid, value in mapping.items():
        if not isinstance(sid, str) or not sid or sid != sid.strip():
            add('SCENE_KEY_ID_TYPE', 'scene_keys的键必须是原样源镜字符串。')
        elif source and sid not in positions:
            add('SCENE_KEY_UNKNOWN', 'scene_keys引用不存在的源镜：' + sid)
        if not isinstance(value, str) or not value or value != value.strip():
            add('SCENE_KEY_VALUE', 'scene_keys场次值必须是非空原样字符串：' + str(sid))
    scene_ids = {}
    if source:
        for shot in source['shots']:
            sid = shot['id']
            raw = shot.get('raw', {})
            nested = raw.get('scene_context', {}) if isinstance(raw, dict) else {}
            declarations = [shot.get('scene_id')]
            if isinstance(nested, dict):
                declarations.append(nested.get('scene_id'))
            display = shot.get('scene', '')
            if isinstance(display, str):
                prefix = SCENE_PREFIX.match(display)
                if prefix:
                    declarations.append(prefix[1])
            explicit = []
            for value in declarations:
                if value is None or value == '':
                    continue
                if not isinstance(value, str) or not value.strip() or value != value.strip():
                    add('SOURCE_SCENE_ID_TYPE', '源镜' + sid + '的明确场次号须为原样非空字符串。')
                    continue
                explicit.append(value)
            if len(set(explicit)) > 1:
                add('SOURCE_SCENE_CONFLICT', '源镜' + sid + '的场次字段与显式场标冲突：' + '、'.join(dict.fromkeys(explicit)))
            original = explicit[0] if explicit else None
            supplement = mapping.get(sid)
            supplement = supplement if isinstance(supplement, str) and supplement and supplement == supplement.strip() else None
            if original and supplement and original != supplement:
                add('SCENE_KEY_CONFLICT', '源镜' + sid + '已有场次' + original + '，scene_keys不能覆盖成' + supplement + '。')
            scene_ids[sid] = original or supplement

    records = context.get('boundaries', [])
    if not isinstance(records, list):
        add('BOUNDARIES_TYPE', 'boundaries必须是数组；不能静默忽略其他形状。')
        records = []
    normalized = []
    seen = set()
    for index, record in enumerate(records, 1):
        where = 'boundaries第' + str(index) + '项'
        if not isinstance(record, dict):
            add('BOUNDARY_RECORD_TYPE', where + '必须是对象。')
            continue
        after = record.get('after')
        if not isinstance(after, str) or not after or after != after.strip():
            add('BOUNDARY_ID_TYPE', where + '的after须为原样字符串，不补零、不猜字母O与数字0。')
            continue
        if source and after not in positions:
            add('BOUNDARY_UNKNOWN_ID', where + '的after不在实际来源：' + after)
            continue
        target = record.get('operation_id')
        if target is not None and target not in operations:
            add('BOUNDARY_OPERATION_UNKNOWN', where + '引用不存在的操作：' + str(target))
            continue
        candidates = [target] if target is not None else operations
        applicable = [op for op in candidates if after in expected[op]]
        if source and not applicable:
            add('BOUNDARY_OUT_OF_SCOPE', where + '的after不在其操作的本轮范围：' + after)
            continue
        if not source:
            applicable = candidates
            add('BOUNDARY_SOURCE_NOT_COMPARED', where + '没有独立来源，不能核实边界位置。', level='review')
        duplicate = any((op, after) in seen for op in applicable)
        if duplicate:
            add('BOUNDARY_DUPLICATE', where + '与同一操作的已记录位置重复：' + after)
        seen.update((op, after) for op in applicable)
        kind = record.get('kind')
        if kind is None:
            kind = 'unclassified'
            add('BOUNDARY_CLASSIFICATION_REVIEW', after + '为旧式未分类边界；先区分真实结束、提交分段或历史位置。', level='review')
        elif not isinstance(kind, str) or kind not in BOUNDARY_KINDS:
            add('BOUNDARY_KIND_UNKNOWN', where + '的kind无效，不能忽略该边界。')
            continue
        reason = record.get('reason')
        if kind in HARD_BOUNDARY_KINDS | {'submission_split'} and (not isinstance(reason, str) or not reason.strip()):
            add('BOUNDARY_REASON_MISSING', where + '应简述实际结束依据或提交分段原因；不要求逐边界问卷。')
        normalized.append({'after': after, 'kind': kind, 'operations': applicable,
                           'reason': reason, 'basis': record.get('basis')})
    historical = [b['after'] for b in normalized if b['kind'] == 'historical_split']
    if historical:
        add('HISTORICAL_SPLITS_NOT_SEMANTIC', '仅沿用历史分组位置，不作语义禁合依据：' + '、'.join(dict.fromkeys(historical)), level='review')
    return expected, scene_ids, normalized


def assess(master: dict, source: dict | None, context: dict | None=None) -> dict:
    if context is None:context={}
    if not isinstance(context,dict):raise FormatError('context必须是对象。')
    issues=[]
    def add(code,msg,unit='',level='error'):issues.append({'code':code,'unit':unit,'level':level,'message':msg})
    if source and context.get('source_sha256') and context['source_sha256']!=source['sha256']:
        add('STALE_CONTEXT','执行补充对应另一份来源，不能沿用其映射。')
    order=[s['id'] for s in source['shots']] if source else []
    by_id={s['id']:s for s in source['shots']} if source else {}
    if not source:add('SOURCE_NOT_COMPARED','未传独立来源；保存完整正文，但不认证源镜覆盖。',level='review')
    assets=context.get('assets',[])
    if not isinstance(assets,list):raise FormatError('assets必须是数组。')
    tags={}
    for a in assets:
        if not isinstance(a,dict) or not a.get('tag'):raise FormatError('素材记录缺tag。')
        if a['tag'] in tags:add('DUPLICATE_ASSET_TAG','素材tag重复：'+a['tag'])
        tags[a['tag']]=a
        if a.get('available') and a.get('path') and not Path(a['path']).is_file():add('ASSET_FILE_MISSING','声明可用但实际路径不存在：'+a['tag'])
    grouped=defaultdict(list);per_unit=[]
    expected_scopes, scene_keys, boundary_records = _grouping_inputs(master, source, context, add)
    cap=Decimal(30)
    if context.get('service_limit_seconds') is not None:
        cap=min(cap,number(context['service_limit_seconds']))
    for u in master['units']:
        uid=u['id'];p=u['prompt_text'];cfg=context.get('units',{}).get(uid,{})
        mode=cfg.get('mode',u['mode']);refs=u['source_refs'];grouped[u['operation_id']]+=refs
        if mode not in {'generate','edit','extend'}:add('MODE_UNKNOWN','单条仅使用generate、edit或extend。',uid)
        if len(refs)!=len(set(refs)):add('DUPLICATE_SOURCE','同一单元重复源镜。',uid)
        unknown=[x for x in refs if x not in by_id] if source else []
        if unknown:add('SOURCE_UNKNOWN','未找到源镜：'+','.join(unknown),uid)
        actual=[by_id[x] for x in refs if x in by_id]
        if source and not unknown:
            positions=[order.index(x) for x in refs]
            if positions!=sorted(positions):add('SOURCE_ORDER','源镜倒序。',uid)
            if positions and positions!=list(range(positions[0],positions[-1]+1)):add('NON_ADJACENT','组合跳过中间源镜。',uid)
            if mode=='generate':
                for boundary in boundary_records:
                    if u['operation_id'] not in boundary['operations'] or boundary['after'] not in refs[:-1]:continue
                    if boundary['kind'] in HARD_BOUNDARY_KINDS:
                        add('SEMANTIC_END_CROSSED','组合跨过已声明的'+boundary['kind']+'：'+boundary['after']+'。',uid)
                    elif boundary['kind']=='submission_split':
                        add('SUBMISSION_SPLIT_CROSSED','组合跨过明确的提交分段位置：'+boundary['after']+'；这不代表剧情已结束。',uid)
                    elif boundary['kind']=='unclassified':
                        add('BOUNDARY_CLASSIFICATION_REQUIRED','组合跨过未分类旧边界'+boundary['after']+'；先回读并明确用途，不自动禁合为语义结束，也不静默放行。',uid)
            scene_ids=[scene_keys.get(s['id']) for s in actual]
            if mode=='generate' and len(refs)>1:
                if len({x for x in scene_ids if x})>1:add('CROSS_SCENE','普通组合含两个或更多已知不同场次，未知项不能抵消该冲突。',uid)
                if not all(scene_ids):add('SCENE_REVIEW','场次身份未完整显式指定；不按显示字符串猜主位/席间是否同场。',uid,'review')
            durations=[s['duration'] for s in actual]
            total=sum(durations,Decimal(0)) if all(d is not None for d in durations) else None
            if total is not None and u['duration']!=total:add('DURATION_SUM','主稿预算不等于源镜精确累计。',uid)
            if total is None and len(refs)>1 and mode=='generate':add('UNKNOWN_GROUP_DURATION','含未知时长，不能标为合法多镜组合。',uid)
        else:total=u['duration']
        if mode=='generate' and total is not None and total>cap:add('DURATION_LIMIT',f'预算{total}秒超过当前{cap}秒；保留正文，不加速或私拆源镜。',uid)
        if mode=='generate' and total is None:add('DURATION_UNKNOWN','内容预算未知。',uid,'review')
        required_numbered=mode=='generate' and (not actual or any(s['kind']=='shot' for s in actual))
        sec=sections(p)
        if required_numbered:
            for h in ['生成目标','主体、关系与场景','镜头脚本','保持一致']:
                if not sec.get(h):add('STRUCTURED_BLOCK_MISSING',f'缺少非空【{h}】。',uid)
            found=[m[1] for m in CUT.finditer(sec.get('镜头脚本',''))]
            if found!=[str(i) for i in range(1,len(refs)+1)]:add('CUT_MAPPING','Cut顺序／数量与完整源镜不对应。',uid)
            head=[m[1] for m in re.finditer(r'^【([^】\n]+)】\s*$',p,re.M)]
            standard=[STANDARD_HEADINGS.index(h) for h in head if h in STANDARD_HEADINGS]
            if standard!=sorted(standard) or (head and head[-1]!='保持一致'):add('BLOCK_ORDER','分镜生成使用既定区块顺序，保持一致放最后。',uid)
        for h,body in sec.items():
            if not body or body in {'无','不适用','N/A'}:add('EMPTY_BLOCK','不输出空壳区块：'+h,uid)
        # Literal dialogue payloads are masked before format checks.
        plain=PAYLOAD.sub('{对白}',p)
        if re.search(r'^\s*(?:#{1,6}\s|`{3,}|~{3,})',plain,re.M):add('OUTER_WRAPPER','prompt_text含外层Markdown标题或代码围栏。',uid)
        if re.search(r'(?i)(?:输出画幅|画幅比例|输出比例|总时长|分辨率|帧率|模型版本|source_sha256|submission_ready|语义结束点|素材与提交说明|以来源为准|来源最终状态)',plain):
            add('PROMPT_META_LEAK','存在输出参数、内部记录或空泛来源代称；人工定位，不由脚本删句。',uid)
        if re.search(r'(?i)(?:\b9:16\b|\b16:9\b|\b(?:ratio|resolution|fps)\s*[:=])',plain):add('REQUEST_PARAMETER','页面／接口参数混入正文。',uid)
        if re.search(r'<(?:[^>\n]*(?:占位符|主体A|主体B|角色名|待填|TODO)[^>\n]*)>',p):add('PLACEHOLDER','正文仍有模板占位符。',uid)
        used_section=sec.get('参考素材职责','')+'\n'+sec.get('目标素材职责','')+'\n'+sec.get('原视频职责','')+'\n'+sec.get('目标音频职责','')
        unused_section=sec.get('未采用素材','')
        standard_tags=set(TAG.findall(p)); known_occurrences={t for t in tags if t in p}
        for t in standard_tags|known_occurrences:
            if t not in tags:add('ASSET_NOT_BOUND','正文素材没有可读库存记录：'+t,uid,'review' if not assets else 'error')
            elif not tags[t].get('available',False):add('ASSET_UNAVAILABLE','正文引用不可用素材：'+t,uid)
        assignments=cfg.get('references',[])
        active={r['tag'] for r in assignments if isinstance(r,dict) and r.get('tag')}
        if assignments:
            for r in assignments:
                t=r.get('tag','');role=r.get('role','')
                if t not in tags or not tags[t].get('available',False):add('ASSIGNMENT_UNAVAILABLE','素材职责指向不可用编号：'+t,uid)
                if t not in p:add('ASSIGNMENT_NOT_IN_PROMPT','已采用素材没有进入实际正文：'+t,uid)
                if role in {'first_frame','last_frame'}:
                    exact=t+('作为首帧。' if role=='first_frame' else '作为尾帧。')
                    if exact not in p.splitlines():add('FRAME_ROLE_SENTENCE','缺独立精确职责句：'+exact,uid)
                elif used_section and t not in used_section:add('ASSET_ROLE_NOT_VISIBLE','职责未进入对应区块：'+t,uid)
                if r.get('role')=='storyboard' and not r.get('adopted_panels'):
                    add('STORYBOARD_PANEL_SCOPE','故事板需明确采用格／过程／备选的作用范围；不能每格自动加Cut。',uid,'review')
        if context.get('inventory_complete'):
            available={t for t,a in tags.items() if a.get('available',False)}
            expected=available-active
            listed={t for t in available if t in unused_section}
            if expected!=listed:add('UNUSED_ASSET_SET','未采用素材与实际可用库存减本单元采用集合不一致。',uid)
            for t in active:
                if t in unused_section:add('ASSET_ACTIVE_AND_UNUSED','同一素材同时采用和排除：'+t,uid)
        if mode in {'edit','extend'}:
            role='edit_source' if mode=='edit' else 'extension_source'
            selected=[r for r in assignments if r.get('role')==role]
            if len(selected)!=1:add('MASTER_REQUIRED',f'{mode}需要唯一真实{role}，缺失不冒充可提交。',uid,'review')
            if mode=='extend' and cfg.get('direction') not in {'before','after'}:add('EXTEND_DIRECTION','延长方向须明确before或after。',uid,'review')
        if cfg.get('depends_on') and not cfg.get('dependency_asset_available',False):add('DEPENDENCY_PENDING','前一步真实视频尚未产生；当前仅完成Prompt规划。',uid,'review')
        for needle in cfg.get('required_literals',[]):
            if needle not in p:add('REQUIRED_TEXT_MISSING','显式执行锚未进入Prompt：'+needle,uid)
        if source and mode=='generate' and not unknown:
            segments=cut_segments(p) if required_numbered else [p]
            for s,seg in zip(actual,segments):
                if s.get('dialogue_conflict'):add('SOURCE_DIALOGUE_CONFLICT',f'源镜{s["id"]}正文与结构化对白不一致，不能静默择一。',uid)
                expected=[e['text'] for e in s['dialogue']]
                found=PAYLOAD.findall(seg)
                if expected!=found:add('DIALOGUE_PAYLOAD_SEQUENCE',f'源镜{s["id"]}明确口播片段不一致；以body/明确对白为准，不以原文栏全文兜底。',uid)
                known_names={e['speaker'] for a in actual for e in a['dialogue'] if e['speaker']}
                for event,m in zip(s['dialogue'],PAYLOAD.finditer(seg)):
                    prefix=seg[max(0,m.start()-100):m.start()]
                    hits=[(prefix.rfind(name),name) for name in known_names if name in prefix]
                    if hits and max(hits)[1]!=event['speaker']:add('DIALOGUE_SPEAKER',f'源镜{s["id"]}发言人不符。',uid)
                    elif not hits and event['speaker']:add('SPEAKER_REVIEW',f'源镜{s["id"]}说话人缺乏可确定的近邻标注。',uid,'review')
                    source_voice=voice_kind(event['voice'])
                    positions=re.findall(re.escape(event['speaker'])+r'[（(]([^）)]+)[）)]',prefix) if event['speaker'] else []
                    actual_voice=voice_kind(positions[-1]) if positions else None
                    if source_voice and actual_voice and source_voice!=actual_voice:add('DIALOGUE_VOICE',f'源镜{s["id"]}明确声位不符。',uid)
                    elif source_voice and not actual_voice:add('VOICE_REVIEW',f'源镜{s["id"]}声位无法从近邻文字确定。',uid,'review')
            expected_all=[e['text'] for s in actual for e in s['dialogue']]
            if PAYLOAD.findall(p)!=expected_all:add('DIALOGUE_DUPLICATED_OR_EXTRA','全Prompt中对白次数／顺序不符；跨Cut声音区不得重抄。',uid)
        request=cfg.get('request',{})
        if request.get('duration') is not None:
            requested=number(request['duration'])
            if mode!='edit' and requested>cap:add('REQUEST_DURATION_LIMIT','请求时长超过当前上限。',uid)
            if mode=='generate' and total is not None and requested<total:add('REQUEST_TOO_SHORT','请求时间不足以容纳内容预算；不能靠加速圆数。',uid)
            elif mode=='generate' and total is not None and requested!=total:add('REQUEST_TIMING_REVIEW','请求时间与计划预算不同；不自动增加动作或重分配源镜。',uid,'review')
        elapsed=Decimal(0);timeline=[];known=True
        for sid in refs:
            d=by_id.get(sid,{}).get('duration')
            timeline.append({'source_id':sid,'start':str(elapsed) if known else None,'duration':str(d) if d is not None else None,'end':str(elapsed+d) if known and d is not None else None})
            if d is None:known=False
            elif known:elapsed+=d
        per_unit.append({'id':uid,'source_refs':refs,'mode':mode,'duration_exact':str(total) if total is not None else None,'timeline':timeline})
    if source:
        for op,refs in grouped.items():
            expected=expected_scopes[op]
            if refs!=expected:add('SCOPE_COVERAGE',f'{op}拼接后不等于本轮源序；可能缺镜、重复或重排。')
    errors=[x for x in issues if x['level']=='error']
    for u in per_unit:
        related=[x for x in issues if not x['unit'] or x['unit']==u['id']]
        u['mechanical_status']='issues_found' if any(x['level']=='error' for x in related) else 'checked_with_review' if related else 'checked'
    return {'version':VERSION,'format':'su-prompt-validation/2.2','mechanical_status':'issues_found' if errors else 'checked_with_review' if issues else 'checked',
            'source_comparison':'explicit_ids_durations_and_dialogue_cues' if source else 'not_performed',
            'semantic_review':'not_performed_by_script','platform_validation':'not_performed',
            'model_call':'not_performed','video_review':'not_performed',
            'counts':{'units':len(master['units']),'cuts_or_source_items':sum(len(x['source_refs']) for x in master['units'])},
            'grouping_metadata':{'boundaries':boundary_records,'scope_order_basis':'actual_source_order' if source else 'not_compared',
                                 'boundary_semantics':'declared_by_author_not_verified_by_script'},
            'units':per_unit,'issues':issues}
