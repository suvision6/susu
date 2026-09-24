#!/usr/bin/env python3
"""Check explicit speech, not cinematic semantics. Standard library only.

Input: the director Markdown template (or its JSON derivative). Source dialogue
must have clear line-start speaker cues. Playback is anchored inside existing
body prose as Speaker(voice):“literal fragment”. No extra creative database.
Unsupported source/layout/reading is reported for review, never guessed.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from master_io import Document, FormatError, parse_master, save_exclusive

CUE_START = re.compile(r'^(?P<name>[^：:\n（）()]{1,60}?)(?=\s*[（(:：])')
VOICE = re.compile(r'(?:O\.?S\.?|V\.?O\.?)', re.IGNORECASE)
HAN = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U000323af]')
WORD = re.compile(r"[A-Za-z]+(?:['’\-][A-Za-z]+)*")
NON_SPEAKERS = {'人物','场景','字幕','片名','标题','日期','来源','本轮来源','本轮范围','项目条件','预计时长'}


def _parenthesis_end(text: str, start: int) -> int | None:
    """Return the index after a balanced direction; accept ASCII/fullwidth nesting."""
    pairs = {'（': '）', '(': ')'}
    stack: list[str] = []
    for index in range(start, len(text)):
        char = text[index]
        if char in pairs:
            stack.append(pairs[char])
        elif char in {'）', ')'}:
            if not stack or char != stack.pop():
                return None
            if not stack:
                return index + 1
    return None


def _source_quote_end(text: str, start: int) -> int | None:
    """Protect literal speech inside quotes. Do not strip its parentheses or colon."""
    pairs = {'“': '”', '‘': '’', '"': '"'}
    stack = [pairs[text[start]]]
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == '\\' and stack[-1] == '"':
            index += 2
            continue
        if char == stack[-1]:
            stack.pop()
            if not stack:
                return index + 1
        elif char in {'“', '‘'}:
            stack.append(pairs[char])
        index += 1
    return None


def parse_source(text: str) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Read explicit cue syntax, not all screenplay semantics.

    Recognize balanced leading directions and an unquoted '(direction):'
    immediately following a sentence boundary. Store excluded syntax verbatim.
    Parentheses in quoted speech or ordinary sentence content remain literal;
    ambiguous or incomplete syntax stays review_required, not silently repaired.
    One line-start speaker cue is one source event; an internal direction is not
    a second speaker cue. Source files and playback text are never edited here.
    """
    events: list[dict[str, str]] = []
    annotations: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not any(char in line for char in ':：'):
            continue
        annotation_start = len(annotations)
        header = CUE_START.match(line)
        if header is None:
            continue
        name = header['name'].strip()
        if name in NON_SPEAKERS or name.startswith('#'):
            continue
        base = len(raw_line) - len(raw_line.lstrip())

        def problem(kind: str, position: int) -> None:
            problems.append({'kind': kind, 'source_line': line_no,
                             'source_column': base + position + 1, 'speaker': name,
                             'message': '来源标注结构不完整或有歧义；保留原文并人工回读，不用删除括号使对白通过。'})

        def annotate(start: int, end: int, position: str) -> None:
            annotations.append({'source_line': line_no,
                                'source_column': base + start + 1,
                                'speaker': name, 'position': position,
                                'text': line[start:end], 'handling': 'excluded_from_spoken_text_only'})

        cursor = header.end()
        while cursor < len(line) and line[cursor].isspace():
            cursor += 1
        invalid = False
        while cursor < len(line) and line[cursor] in {'（', '('}:
            end = _parenthesis_end(line, cursor)
            if end is None:
                problem('unclosed_source_direction', cursor)
                invalid = True
                break
            annotate(cursor, end, 'speaker_header')
            cursor = end
            while cursor < len(line) and line[cursor].isspace():
                cursor += 1
        if invalid:
            continue
        voice = ''
        token = VOICE.match(line, cursor)
        if token is not None:
            voice = token.group(0)
            cursor = token.end()
            while cursor < len(line) and line[cursor].isspace():
                cursor += 1
        if cursor >= len(line) or line[cursor] not in {'：', ':'}:
            # Parentheses in an ordinary action line do not make it a cue.
            del annotations[annotation_start:]
            continue
        # Match the old suffix convention for Chinese-name+OS and spaced English cues.
        if not voice:
            suffix = re.search(r'(?<=[\u3400-\u9fff\s])((?:O\.?S\.?|V\.?O\.?))$', name, re.I)
            if suffix:
                voice = suffix.group(1)
                name = name[:suffix.start()].rstrip()
        cursor += 1
        while cursor < len(line) and line[cursor].isspace():
            cursor += 1
        payload_start = cursor
        if cursor == len(line):
            problem('empty_source_utterance', cursor)
            continue
        # A fully quoted utterance is wholly literal, including bracketed words.
        if line[cursor] in {'“', '"'} and _source_quote_end(line, cursor) == len(line):
            payload = line[cursor+1:-1]
        else:
            pieces: list[str] = []
            while cursor < len(line):
                char = line[cursor]
                if char in {'“', '‘', '"'}:
                    end = _source_quote_end(line, cursor)
                    if end is None:
                        problem('unclosed_source_quote', cursor)
                        pieces.append(line[cursor:])
                        break
                    pieces.append(line[cursor:end])
                    cursor = end
                    continue
                if char in {'（', '('}:
                    end = _parenthesis_end(line, cursor)
                    if end is None:
                        problem('unclosed_source_parenthesis', cursor)
                        pieces.append(line[cursor:])
                        break
                    tail = end
                    while tail < len(line) and line[tail].isspace():
                        tail += 1
                    has_colon = tail < len(line) and line[tail] in {'：', ':'}
                    previous = line[payload_start:cursor].rstrip()
                    boundary = not previous or previous[-1] in '。！？!?；;.'
                    if has_colon and boundary:
                        annotate(cursor, tail + 1, 'inline_performance')
                        cursor = tail + 1
                        while cursor < len(line) and line[cursor].isspace():
                            cursor += 1
                        if cursor == len(line):
                            problem('empty_inline_utterance', cursor)
                        continue
                    if has_colon:
                        problem('ambiguous_inline_parenthesis', cursor)
                    pieces.append(line[cursor:end])
                    cursor = end
                    continue
                pieces.append(char)
                cursor += 1
            payload = ''.join(pieces)
        events.append({'speaker': name, 'text': payload, 'source_voice': voice})
    return events, annotations, problems


def source_events(text: str) -> list[dict[str, str]]:
    """Compatibility helper; review() uses parse_source() to retain warnings."""
    return parse_source(text)[0]


def unwrap_source(data: dict[str, Any]) -> str:
    """Only one explicit source fence is auto-read; file sources use --source."""
    text=data.get('source_basis','')
    try:
        doc=Document('# source\n'+text)
    except FormatError:
        return ''
    return doc.fences[0][2] if len(doc.fences)==1 else ''


def read_quote(body: str, pos: int) -> tuple[str, int] | None:
    opener=body[pos]; closer='”' if opener=='“' else '"'; depth=1
    cursor=pos+1
    while cursor < len(body):
        ch=body[cursor]
        if ch=='\\' and opener=='"':
            cursor+=2; continue
        if opener=='“' and ch=='“': depth+=1
        if ch==closer:
            depth-=1
            if depth==0: return body[pos+1:cursor],cursor+1
        cursor+=1
    return None


def playback(body: str, names: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    # No scanning all quotations as speech: the speaker must be explicitly attached.
    if not names: return [],[]
    pattern=re.compile(r'(?<![\w\u3400-\u9fff])(?P<name>'+ '|'.join(re.escape(n) for n in sorted(names,key=len,reverse=True))+
                       r')\s*(?:[（(](?P<voice>[^）)\n]*)[）)])?\s*[：:]\s*(?P<open>[“"])')
    records=[]; issues=[]; skip_to=0
    for m in pattern.finditer(body):
        if m.start()<skip_to: continue
        result=read_quote(body,m.start('open'))
        if result is None:
            issues.append('unclosed_playback_quote');continue
        text,skip_to=result
        records.append({'speaker':m['name'],'voice':m['voice'] or '', 'text':text})
    return records,issues


def amount(text: str, cpm: Decimal | None, wpm: Decimal | None) -> dict[str, Any]:
    zh=len(HAN.findall(text)); en=len(WORD.findall(text)); unknown=False
    residue=WORD.sub('',HAN.sub('',text))
    # Numeric/letter-by-letter/other-language readings need an actual reading plan.
    if any(ch.isalnum() for ch in residue) or re.search(r'\b(?:[A-Z]\.){2,}|\b[A-Z]{2,}\b',text): unknown=True
    reasons=[]
    if zh and cpm is None: reasons.append('missing_cpm')
    if en and wpm is None: reasons.append('missing_wpm')
    if unknown: reasons.append('reading_needs_review')
    value=None if reasons else (Decimal(60)*zh/cpm if zh else Decimal(0))+(Decimal(60)*en/wpm if en else Decimal(0))
    return {'han_count':zh,'word_count':en,'basis_seconds':str(value) if value is not None else None,'review_reasons':reasons}


def review(data: dict[str,Any], source: str, cpm: Decimal | None=None,
           wpm: Decimal | None=None) -> dict[str,Any]:
    expected, source_annotations, source_parse_issues = parse_source(source)
    names=list(dict.fromkeys(e['speaker'] for e in expected))
    issues=list(source_parse_issues); segments=[]; shot_reports=[]
    if not expected:
        issues.append({'kind':'source_reading_required','message':'没有识别到逐行角色发言；不能据此认证没有对白。请回读无对白来源或提供有明确发言行的原文。'})
    # Also report precise, clearly labelled source-fragment hints in legacy bodies.
    hints=[]
    for shot in data.get('shots',[]):
        parsed,err=playback(shot['body'],names)
        for code in err:issues.append({'kind':code,'shot':shot['id']})
        for hinted in source_events(shot.get('source_text','')):
            if (hinted['speaker'] in names and hinted['text'] not in shot['body']
                    and not any(seg['speaker'] == hinted['speaker'] for seg in parsed)):
                hints.append({'shot':shot['id'],'speaker':hinted['speaker'],'text':hinted['text'],
                              'finding':'source_fragment_not_exact_in_body',
                              'note':'只说明原文栏这个明确片段没有在正文完整复现；不把一般引用自动认定为演出。'})
        d=shot.get('duration_seconds'); estimates=[]
        for seg in parsed:
            seg={'shot':shot['id'],**seg};calc=amount(seg['text'],cpm,wpm)
            seg.update(calc);segments.append(seg);estimates.append(calc)
            if calc['review_reasons']: issues.append({'kind':'timing_reading_required','shot':shot['id'],'reasons':calc['review_reasons']})
        if len(parsed)>1:
            issues.append({'kind':'multi_segment_timing_review','shot':shot['id'],
                           'message':'同镜多段声音的先后／重叠由Agent判断；工具不自动累加为镜长。'})
        if parsed and d is None:
            issues.append({'kind':'unknown_shot_duration','shot':shot['id']})
        # Every individual fragment must fit; multi-speaker overlap is not summed.
        for calc in estimates:
            if d is not None and calc['basis_seconds'] is not None and Decimal(str(d))<Decimal(calc['basis_seconds']):
                issues.append({'kind':'fragment_short_under_selected_rate','shot':shot['id'],
                               'duration_seconds':str(d),'basis_seconds':calc['basis_seconds'],
                               'deficit_seconds':str(Decimal(calc['basis_seconds'])-Decimal(str(d))),
                               'message':'按本次选定的均匀估算口径片段不足；调整切点／时长或有依据的局部口径，不能借邻镜余量自动通过。'})
        shot_reports.append({'shot':shot['id'],'playback_segments':len(parsed),'duration_seconds':d})
    # Consume exact text against original occurrences, not a set of distinct strings.
    event_index=0;offset=0;matched=True
    for seg in segments:
        if event_index>=len(expected):
            issues.append({'kind':'extra_playback','shot':seg['shot'],'text':seg['text']});matched=False;break
        event=expected[event_index];remaining=event['text'][offset:]
        if seg['speaker']!=event['speaker'] or not seg['text'] or not remaining.startswith(seg['text']):
            issues.append({'kind':'playback_sequence_or_text_mismatch','shot':seg['shot'],
                           'expected_speaker':event['speaker'],'expected_remaining':remaining,'actual':seg});matched=False;break
        if event['source_voice'] and event['source_voice'].replace('.','').upper() not in seg['voice'].replace('.','').upper():
            issues.append({'kind':'explicit_source_voice_not_retained','shot':seg['shot'],'expected':event['source_voice'],'actual':seg['voice']})
        offset+=len(seg['text'])
        if offset==len(event['text']):event_index+=1;offset=0
    if event_index<len(expected):
        issues.append({'kind':'source_playback_not_fully_confirmed','event_index':event_index+1,
                       'remaining_events':len(expected)-event_index,
                       'message':'缺明确播放锚点、缺词、错序或旧式表达都可能导致未核实；先回读，不自动把旧正文中的引语全判为遗漏。'})
        matched=False
    if hints and not matched:issues.append({'kind':'source_fragment_hints','items':hints})
    return {'status':'checked_explicit_dialogue' if expected and matched and not issues else 'review_required',
            'source_scope':'line_start_speaker_cues_only; source completeness must be reviewed by Agent',
            'source_sha256':hashlib.sha256(source.encode('utf-8')).hexdigest(),
            'master_sha256':data.get('master_sha256'),
            'rate':{'cpm':str(cpm) if cpm else None,'wpm':str(wpm) if wpm else None,
                    'basis':'user_selected_estimation; no physiology or recorded timing claim'},
            'source_events':len(expected),
            'event_count_basis':'recognized_line_start_speaker_cues; inline performance markers do not create new speaker events',
            'source_han_count':sum(len(HAN.findall(x['text'])) for x in expected),
            'playback_han_count':sum(seg['han_count'] for seg in segments),
            'source_annotations':source_annotations,'source_parse_issues':source_parse_issues,
            'playback_segments':len(segments),'matched_complete_events':event_index,
            'literal_reconstruction':bool(expected and matched and not source_parse_issues),'segments':segments,'shots':shot_reports,
            'issues':issues,'semantic_review':'not_performed_by_script',
            'notes':'只核对已明确发言及选定速率下的片段数值。不估动作、环境、额外停顿，不判摄影美学，不修改文件；自然复述不冒充明确播放。'}


def positive(value: str) -> Decimal:
    try:
        number=Decimal(value)
    except InvalidOperation as e: raise argparse.ArgumentTypeError('速度需为正数') from e
    if not number.is_finite() or number<=0:raise argparse.ArgumentTypeError('速度需为有限正数')
    return number


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True);parser.add_argument('--source',help='有明确角色发言行的采用原文；省略时只读主稿来源区的唯一围栏')
    parser.add_argument('--cpm',type=positive);parser.add_argument('--wpm',type=positive)
    parser.add_argument('--output',help='可选包外核对记录；不覆盖不同内容')
    args=parser.parse_args()
    try:
        p=Path(args.input)
        if p.suffix.lower()=='.json':
            data=json.loads(p.read_text('utf-8-sig'))
            if data.get('kind')!='director':raise ValueError('需要原Markdown或含完整正文的director JSON；对白核对报告不是导演主稿，不能据它重建或复验整场。')
        else:data=parse_master(p,'director')
        source=Path(args.source).read_text('utf-8-sig') if args.source else unwrap_source(data)
        result=review(data,source,args.cpm,args.wpm)
        payload=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        if args.output:save_exclusive(Path(args.output),payload)
        print(payload.decode('utf-8'),end='')
        return 0 if result['status']=='checked_explicit_dialogue' else 2
    except (OSError,ValueError,KeyError,TypeError) as e:
        print(json.dumps({'status':'input_error','message':str(e)},ensure_ascii=False));return 1

if __name__=='__main__':raise SystemExit(main())
