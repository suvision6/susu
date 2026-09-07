"""Mechanical checks and explicitly attributed semantic-review evidence.

No compiler is called to generate its own expected answer. Source bytes, source
positions, dialogue events and final authored text are separate inputs.
"""
from __future__ import annotations
from collections import Counter
import copy
from decimal import Decimal
import re
from .common import DeliveryError, digest, issue, position_label, object_hash
from .master import Master
from .source import Source


def quote_at(text: str, start: int):
    if start >= len(text) or text[start] not in ('“', '"'):
        return None
    opening = text[start]; closing = '”' if opening == '“' else '"'; depth = 1; i = start + 1
    while i < len(text):
        if opening == '"' and text[i] == '\\':
            i += 2; continue
        if opening == '“' and text[i] == opening:
            depth += 1
        elif text[i] == closing:
            depth -= 1
            if depth == 0:
                return i + 1, text[start+1:i]
        i += 1
    return None


def spoken_events(text: str):
    """Read explicit speaker-labelled utterances, including nested quotation.

The normalizer does not require this format upstream. This compact authored
speech syntax gives the exporter a verifiable speaker/event boundary.
"""
    result = []; consumed_until = -1
    pattern = re.compile(r'(?:^|(?<=[。！？；\n]))[ \t]*([^\n：:“”]{1,48}?)[：:][ \t]*', re.M)
    for match in pattern.finditer(text):
        if match.start() < consumed_until:
            continue
        quoted = quote_at(text, match.end())
        if quoted is None:
            continue
        consumed_until = quoted[0]
        prefix = match[1].strip()
        suffix = re.search(r'[（(]([^）)]+)[）)]$', prefix)
        raw_position = suffix[1] if suffix else ""
        speaker = prefix[:suffix.start()].strip() if suffix else prefix
        natural = re.fullmatch(r"画外传来(.+?)的声音", speaker)
        if natural:
            speaker = natural[1]; raw_position = "画外"
        try:
            position = position_label(raw_position)
        except DeliveryError:
            position = raw_position
        result.append({"speaker": speaker, "text": quoted[1], "position": position,
                       "start": match.end(), "end": quoted[0]})
    return result


def _masked_source_literals(text: str, events: list[dict], screens: list[str]):
    chars = list(text)
    remaining = Counter((e["speaker"] or "说话人未提供", e["text"], e["position"]) for e in events)
    for item in spoken_events(text):
        key = (item["speaker"], item["text"], item["position"])
        if remaining[key] > 0:
            remaining[key] -= 1
            chars[item["start"]:item["end"]] = [" "] * (item["end"] - item["start"])
    # Explicit literal screen text is protected only when it matches its source.
    for literal in screens:
        for match in re.finditer(re.escape('“' + literal + '”'), text):
            chars[match.start():match.end()] = [" "] * (match.end() - match.start())
    return "".join(chars)


def unit_blocks(text: str, count: int, protected: str | None = None):
    scan = protected if protected is not None else text
    headings = list(re.finditer(r'^Cut[ \t]+([1-9][0-9]*)(?:[｜:：].*|[ \t]*)\r?$', scan, re.M))
    if not headings:
        return [text] if count == 1 else []
    if [int(h[1]) for h in headings] != list(range(1, count+1)):
        return []
    return [text[h.end():headings[i+1].start() if i+1 < len(headings) else len(text)] for i, h in enumerate(headings)]


def check_master(source: Source, master: Master, context: dict | None = None, review: dict | None = None) -> dict:
    context = context or {}; review = review or {}
    if master.source_sha256 != source.sha256:
        raise DeliveryError("SOURCE_HASH_MISMATCH：主稿与当前来源不是同一版本")
    index = {shot["id"]: shot for shot in source.shots}
    scope = master.scope
    if len(scope) != len(set(scope)) or any(s not in index for s in scope):
        raise DeliveryError("主稿范围存在重复或未知来源 ID")
    expected_scope = context.get("scope", list(index))
    if scope != expected_scope or [s for s in index if s in scope] != scope:
        raise DeliveryError("主稿范围与本次锁定范围不一致，或镜序发生变化")
    operations = context.get("operations", [{"operation_id": "OP001", "primary": "generate"}])
    if not isinstance(operations, list) or not operations:
        raise DeliveryError("operations 必须为非空列表")
    op_ids = [o.get("operation_id") for o in operations if isinstance(o, dict)]
    if len(op_ids) != len(operations) or len(set(op_ids)) != len(op_ids) or any(not x for x in op_ids):
        raise DeliveryError("操作 ID 无效或重复")
    for unit in master.units:
        if unit.operation not in op_ids:
            raise DeliveryError(f"未知操作：{unit.operation}")
    for op in operations:
        covered = [sid for u in master.units if u.operation == op["operation_id"] for sid in u.source_ids]
        op_scope = op.get("source_ids", scope)
        if not isinstance(op_scope, list) or not op_scope or any(s not in scope for s in op_scope) or [s for s in scope if s in op_scope] != op_scope:
            raise DeliveryError(f"{op['operation_id']} 操作范围不是锁定范围的有序子集")
        if covered != op_scope:
            raise DeliveryError(f"{op['operation_id']} 来源必须按序恰好覆盖一次")
    all_ids = set(scope)
    result = {}; master_hash = digest(master.payload)
    review_bound = (review.get("source_sha256") == source.sha256 and review.get("master_sha256") == master_hash
                    and review.get("method") == "source-to-prompt-and-back" and bool(review.get("reviewer")))
    if review and not review_bound:
        raise DeliveryError("REVIEW_HASH_MISMATCH：复核记录缺失绑定或已经过期")
    joins = context.get("joins", [])
    if joins and context.get("source_sha256") != source.sha256:
        raise DeliveryError("GROUPING_SOURCE_HASH_MISMATCH：合镜依据与来源不一致")
    join_set = set()
    for row in joins:
        if not isinstance(row, dict) or not row.get("reason"):
            raise DeliveryError("合镜须包含相邻镜号与具体理由")
        pair = (row.get("left"), row.get("right"))
        if pair[0] not in all_ids or pair[1] not in all_ids or scope.index(pair[1]) != scope.index(pair[0])+1:
            raise DeliveryError("合镜边界不是本次范围内的相邻来源")
        join_set.add(pair)
    # Legacy review is accepted only as explicit evidence, never required for safe single-Cut output.
    legacy = context.get("grouping_review")
    if legacy:
        if context.get("source_sha256") != source.sha256:
            raise DeliveryError("旧合镜审阅需绑定当前原始来源 SHA256；不得把旧 canonical hash 当作原文 hash")
        for row in legacy.get("boundaries", []):
            if row.get("classification") == "prefer_join" and row.get("reason") and all(row.get("compatibility", {}).values()):
                join_set.add((row.get("left_source_shot_id"), row.get("right_source_shot_id")))
    for unit in master.units:
        issues = [x for x in source.issues if not x["source_id"] or x["source_id"] in unit.source_ids]
        shots = copy.deepcopy([index[s] for s in unit.source_ids])
        op = next(o for o in operations if o['operation_id'] == unit.operation)
        primary = op.get('primary', op.get('task', {}).get('primary', 'generate'))
        for edit in context.get('authorized_dialogue_edits', []):
            if edit.get('operation_id') != unit.operation or edit.get('source_id') not in unit.source_ids:
                continue
            if primary != 'edit' or context.get('source_sha256') != source.sha256 or not edit.get('user_instruction'):
                issues.append(issue('DIALOGUE_EDIT_NOT_AUTHORIZED', '对白修改缺少编辑任务、当前来源绑定或明确用户指令', unit.id))
                continue
            matched = False
            for shot in shots:
                if shot['id'] != edit['source_id']:
                    continue
                for event in shot['dialogue']:
                    if event['event_id'] == edit.get('event_id'):
                        if not isinstance(edit.get('text'), str):
                            issues.append(issue('DIALOGUE_EDIT_INVALID', '授权的新对白必须为明确原文', unit.id))
                        else:
                            event['text'] = edit['text']; matched = True
            if not matched:
                issues.append(issue('DIALOGUE_EDIT_TARGET_UNKNOWN', '授权对白事件未找到', unit.id))
        for sid, derivation in context.get('emotion_visualizations', {}).items():
            if sid not in unit.source_ids:
                continue
            raw = index[sid]['raw']; staging = raw.get('staging', {})
            staging = staging if isinstance(staging, dict) else {}
            performance = raw.get('performance', {})
            visible = raw.get('visible_behavior') or staging.get('performance') or (performance.get('visible_behavior') if isinstance(performance, dict) else performance)
            basis = raw.get('emotion_intent') or (performance.get('emotion_intent') if isinstance(performance, dict) else '')
            if visible or not basis or derivation.get('basis_emotion') != basis:
                issues.append(issue('EMOTION_DERIVATION_NOT_ALLOWED', '已有表演或缺少对应情绪依据，不能另造动作', sid))
            elif not derivation.get('text') or derivation['text'] not in unit.text:
                issues.append(issue('EMOTION_DERIVATION_NOT_BOUND', '最小派生未与当前正文对应', sid))
            elif any(derivation.get('guardrails', {}).values()):
                issues.append(issue('EMOTION_DERIVATION_CHANGES_FACTS', '派生声明改变了受保护事实', sid))
        expected_duration = sum((s["duration"] for s in shots), start=Decimal(0)) if all(s["duration"] is not None for s in shots) else None
        if unit.duration != expected_duration:
            issues.append(issue("DURATION_MISMATCH", "主稿时长必须等于来源精确求和；未知仍为空", unit.id))
        for left, right in zip(shots, shots[1:]):
            if (left["id"], right["id"]) not in join_set:
                issues.append(issue("JOIN_REVIEW_REQUIRED", "无合镜证据；拆回单镜即可继续", unit.id))
            def boundary_value(shot, key):
                sc = shot['raw'].get('scene_context', {})
                return shot['raw'].get(key) or (sc.get(key) if isinstance(sc, dict) else None)
            if left["scene"] != right["scene"] or any(boundary_value(left,k) != boundary_value(right,k) for k in ('reality_layer','time','time_of_day')):
                issues.append(issue("JOIN_BOUNDARY_CONFLICT", "来源场景／现实层不连续", unit.id))
            if left["duration"] is None or right["duration"] is None:
                issues.append(issue("JOIN_DURATION_UNKNOWN", "未知时长保持单镜", unit.id))
        if not unit.text.strip():
            issues.append(issue("PROMPT_EMPTY", "本单元没有执行正文", unit.id))
        events = [e for shot in shots for e in shot["dialogue"]]
        screens = [f["text"] for shot in shots for f in shot["facts"] if f["path"].startswith("screen_text")]
        masked = _masked_source_literals(unit.text, events, screens)
        blocks = unit_blocks(unit.text, len(shots), masked)
        if not blocks:
            issues.append(issue("CUT_MAPPING_INVALID", "多镜正文需要与来源逐一对应的 Cut 顺序", unit.id))
        actual = spoken_events(unit.text)
        # Screen labels are not utterance events when their payload is a locked screen literal.
        actual = [e for e in actual if not (e["speaker"] in {"画面文字", "字幕", "屏幕文字"} and e["text"] in screens)]
        expected_keys = [(e["speaker"] or "说话人未提供", e["text"], e["position"]) for e in events]
        actual_keys = [(e["speaker"], e["text"], e["position"]) for e in actual]
        if expected_keys != actual_keys:
            issues.append(issue("DIALOGUE_EVENT_MISMATCH", "对白事件的原文、说话人、声位、次数或顺序不一致", unit.id))
        if blocks:
            for shot, block in zip(shots, blocks):
                keys = [(e["speaker"], e["text"], e["position"]) for e in spoken_events(block) if not (e['speaker'] in {'画面文字','字幕','屏幕文字'} and e['text'] in screens)]
                expected = [(e["speaker"] or "说话人未提供", e["text"], e["position"]) for e in shot["dialogue"]]
                if keys != expected:
                    issues.append(issue("DIALOGUE_CUT_MISMATCH", "对白事件出现在错误 Cut", shot["id"]))
        for pattern in (r"(?:我是|作为)(?:一个)?(?:AI|人工智能|模型)",
                        r"\b(?:ratio|duration|resolution|fps|output_format)\s*[=:：]",
                        r"(?:所有权|时间块|时长依据|source_sha256|submission_ready)\s*[：:=]"):
            if re.search(pattern, masked, re.I):
                issues.append(issue("PROMPT_METADATA_LEAK", "非来源保护载荷中出现元信息／审计说明", unit.id))
        # These are exact source literal checks, NOT a claim of complete semantic coverage.
        for screen in screens:
            if screen not in unit.text:
                issues.append(issue("SCREEN_LITERAL_MISSING", "来源锁定画面文字缺失", unit.id))
        record = review.get("units", {}).get(unit.id, {}) if review_bound else {}
        reviewed = record.get("status") == "reviewed" and bool(record.get("notes"))
        unresolved = record.get("unresolved", [])
        if record.get('status') == 'blocked':
            unresolved = unresolved or ['复核者标记为阻断']
        if unresolved:
            issues.append(issue("SEMANTIC_REVIEW_UNRESOLVED", "来源复核仍有未解决事项", unit.id))
        errors = [x for x in issues if x["severity"] == "ERROR"]
        result[unit.id] = {"mechanical_status": "FAIL" if errors else "PASS",
                           "content_fidelity": "blocked" if errors else "agent_reviewed" if reviewed and not unresolved else "review_required",
                           "semantic_method": "agent-attributed; not a deterministic proof",
                           "review": record, "issues": issues}
    return {"units": result, "source_sha256": source.sha256, "master_sha256": master_hash,
            "independent_source_review_required": True,
            "semantic_coverage_proven_by_code": False}
