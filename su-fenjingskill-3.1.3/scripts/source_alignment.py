#!/usr/bin/env python3
"""Deterministic source-authority, passage, fact, and shot-alignment helpers.

This module owns no directing decisions. It verifies the internal evidence that
connects locked source text to formal shots and materializes formal excerpts from
that evidence. It performs no network or filesystem writes.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple


WORKSPACE_CONTRACT = "director-workspace/3.1.3"
FORMAL_CONTRACT_NAME = "director-shot-data"
FORMAL_CONTRACT_VERSION = "3.1.3"
FORMAL_SOURCE_SKILL = "su-fenjingskill"
FORMAL_SOURCE_SKILL_VERSION = "3.1.3"
SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Imported by reviewer, formal builder, exporter, and migration tests for deterministic source alignment."

AUTHORITY_ROLES = {"performance_authority", "adapted_reference", "non_narrative"}
BILINGUAL_RELATIONS = {"literal_equivalent", "adapted_equivalent", "independent"}
COVERAGE_STATUSES = {"covered", "intentionally_withheld", "intentionally_omitted"}
FACT_KINDS = {
    "entity_attribute",
    "action",
    "action_result",
    "state",
    "negation",
    "causal_link",
    "relation",
    "source_sound",
    "reality_change",
    "world_rule",
}
PROTECTED_FACT_KINDS = {
    "entity_attribute",
    "action_result",
    "negation",
    "causal_link",
    "source_sound",
    "reality_change",
    "world_rule",
}
PROTECTED_CLASS_KINDS = {
    "identity_technology_level": {"entity_attribute"},
    "action_result": {"action_result"},
    "causal_link": {"causal_link"},
    "world_rule": {"world_rule"},
    "source_sound": {"source_sound"},
    "reality_layer": {"reality_change"},
    "cross_scene_irreversible": {"action_result", "reality_change"},
}
PROTECTED_CLASS_PATTERNS = {
    "identity_technology_level": re.compile(
        r"身份|军衔|职业|阶级|年龄|年轻|年老|衣着|服装|外貌|个体特征|装甲|武器|装备|步枪|"
        r"技术(?:水平|等级)?|先进|落后|型号|制式|identity|rank|technology|advanced|uniform|weapon",
        re.IGNORECASE,
    ),
    "action_result": re.compile(
        r"(?:把|将).{0,48}(?:放|交|递|推|拉|扔|砸|锁|打开|关闭|拿|插|丢|移|贴|写|割|刺|击|杀|烧|毁)|"
        r"停下|倒下|碎裂|打开|关闭|死亡|死去|化为|成为|变成|落下|断裂|熄灭|崩塌|多了|少了|完成|"
        r"result(?:s|ed)?\s+in|turns?\s+into|becomes?|dies?|collapses?",
        re.IGNORECASE,
    ),
    "causal_link": re.compile(r"因为|由于|因此|所以|导致|致使|使得|从而|因而|because|therefore|causes?|results?\s+in", re.IGNORECASE),
    "world_rule": re.compile(r"必须|只能|不得|一旦|每当|凡是|规则|法则|禁忌|永远不能|不允许|唯一.{0,8}方式|must|only\s+when|rule|forbidden", re.IGNORECASE),
    "source_sound": re.compile(r"听见|声音|声响|广播|旁白|脚步声|刀声|枪声|音乐|铃声|耳语|喊声|叫喊|voice|sound|music|whisper", re.IGNORECASE),
    "reality_layer": re.compile(r"现实层|梦境|幻觉|记忆空间|精神世界|时间线|时空切换|另一个世界|reality\s+layer|dream\s+world|timeline", re.IGNORECASE),
    "cross_scene_irreversible": re.compile(r"不可逆|永久|再也无法|从此不再|死亡|死去|化为灰|成为灰|彻底毁灭|irreversible|permanent(?:ly)?", re.IGNORECASE),
}
REALIZATION_MODES = {"visual", "dialogue", "sound", "offscreen"}
INFERENCE_REVERSIBILITY = {"reversible", "confirmation_required"}
INFERENCE_STATUSES = {"proposed", "approved", "rejected"}
REFERENCE_APPROVAL_STATUSES = {"approved", "pending", "rejected"}
NEGATION_MARKERS = ("没有", "不", "未", "无", "不能", "无法", "并非", " no ", " not ", "never")
CONTEXT_ONLY_TEXTS = {
    "另一处",
    "另一处。",
    "抬头",
    "抬头。",
    "高空",
    "高空。",
    "他低头",
    "他低头。",
    "她低头",
    "她低头。",
}
NEGATION_UNIT_RE = re.compile(
    r"(?:没有|并未|未曾|从未|不得|不能|无法|并非|不是|不再|不曾|\bno\b|\bnot\b|\bnever\b)",
    re.IGNORECASE,
)

# A non-empty source line is narrative by default. Only narrow, mechanically
# recognizable document metadata may be excluded without an explicit human
# classification review. This prevents an action or line of dialogue from being
# relabelled as metadata to bypass fact coverage.
NON_NARRATIVE_METADATA_PATTERNS = (
    re.compile(r"^\s*(?:第\s*)?\d+\s*页\s*$", re.IGNORECASE),
    re.compile(r"^\s*page\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:片名|剧名|项目名|作者|编剧|版本|日期|版权|草稿)\s*[：:].+$", re.IGNORECASE),
    re.compile(r"^\s*[-_=*]{3,}\s*$"),
)
SCENE_HEADING_RE = re.compile(
    r"^\s*(?:内景|外景|内外景|INT\.?|EXT\.?|I/E\.?)\s*[·.\-—\s].+",
    re.IGNORECASE,
)
TRANSITION_RE = re.compile(
    r"^\s*(?:切至|切到|淡入|淡出|叠化|黑场|转场|CUT\s+TO:?|FADE\s+IN:?|FADE\s+OUT:?)\s*$",
    re.IGNORECASE,
)
PROBABLE_NARRATIVE_RE = re.compile(
    r"(?:[^：:\n]{1,24}[：:]\s*[^：:\n]+$)|"
    r"(?:说|问|回答|看|望|走|跑|站|坐|拿|放|打开|关上|关闭|停下|继续|听见|发现|进入|离开|醒来|"
    r"转身|抬头|低头|哭|笑|切|落下|握|伸手|推|拉|叫|喊|递|砸|撞|倒下|死去|杀|开口|呼吸|"
    r"says?|asks?|walks?|runs?|opens?|closes?|stops?|continues?|hears?|sees?|finds?|enters?|leaves?|wakes?)",
    re.IGNORECASE,
)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def text_hash(value: Any) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalized_identifier(value: Any) -> str:
    """Normalize an entity label for ownership comparisons without substring matching."""
    return re.sub(r"\s+", "", normalize_text(value)).casefold()


POSSESSIVE_OWNER_SUFFIXES = {
    "手", "双手", "左手", "右手", "脚", "双脚", "左脚", "右脚", "脸", "眼睛", "目光",
    "背影", "身体", "声音", "呼吸", "动作", "衣角", "影子",
}


def owner_matches_subject(subject: Any, owner: Any) -> bool:
    """Return True only for an exact entity or an explicit possessed body/trace.

    This deliberately rejects generic substring matches such as ``林`` -> ``树林``.
    """
    subject_text = normalized_identifier(subject)
    owner_text = normalized_identifier(owner)
    if not subject_text or not owner_text:
        return False
    if subject_text == owner_text:
        return True
    prefix = subject_text + "的"
    if owner_text.startswith(prefix):
        return owner_text[len(prefix):] in POSSESSIVE_OWNER_SUFFIXES
    return False


def is_mechanical_non_narrative_metadata(value: Any) -> bool:
    text = normalize_text(value)
    return bool(text) and any(pattern.fullmatch(text) for pattern in NON_NARRATIVE_METADATA_PATTERNS)


def looks_probably_narrative(value: Any) -> bool:
    text = normalize_text(value)
    return bool(text) and bool(PROBABLE_NARRATIVE_RE.search(text))


def source_kind_matches_text(kind: Any, value: Any) -> bool:
    text = normalize_text(value)
    if kind == "scene_heading":
        return bool(SCENE_HEADING_RE.match(text))
    if kind == "transition":
        return bool(TRANSITION_RE.match(text))
    if kind == "metadata":
        return is_mechanical_non_narrative_metadata(text)
    return True


def classification_review_payload(review: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "unit_id": review.get("unit_id"),
        "decision": review.get("decision"),
        "status": review.get("status"),
        "reason": normalize_text(review.get("reason")),
        "source_text_hash": review.get("source_text_hash"),
        "reviewer": normalize_text(review.get("reviewer")),
    }


def classification_review_hash(review: Mapping[str, Any]) -> str:
    return canonical_hash(classification_review_payload(review))


def supplemental_reference_approval_payload(reference_fact: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "reference_fact_id": reference_fact.get("reference_fact_id"),
        "statement": normalize_text(reference_fact.get("statement")),
        "source_excerpt": normalize_text(reference_fact.get("source_excerpt")),
        "source_hash": reference_fact.get("source_hash"),
        "provenance": copy.deepcopy(reference_fact.get("provenance")),
        "approval_status": reference_fact.get("approval_status"),
        "approval_note": normalize_text(reference_fact.get("approval_note")),
    }


def supplemental_reference_approval_hash(reference_fact: Mapping[str, Any]) -> str:
    return canonical_hash(supplemental_reference_approval_payload(reference_fact))


def derive_unit_protection_requirements(unit: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Derive non-downgrade semantic obligations from the locked unit itself."""
    text = normalize_text(unit.get("exact_text"))
    requirements: Dict[str, Dict[str, Any]] = {}
    if unit.get("kind") == "source_sound":
        requirements["source_sound"] = {"allowed_kinds": ["source_sound"], "anchors": []}
    for class_name, pattern in PROTECTED_CLASS_PATTERNS.items():
        anchors = list(dict.fromkeys(match.group(0) for match in pattern.finditer(text)))
        if anchors:
            requirements[class_name] = {
                "allowed_kinds": sorted(PROTECTED_CLASS_KINDS[class_name]),
                "anchors": anchors,
            }
    return requirements


def issue(code: str, path: str, message: str) -> Dict[str, str]:
    return {"code": code, "path": path, "message": message}


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value: Any, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def line_range(value: Any, line_count: int) -> Tuple[int, int] | None:
    if not isinstance(value, dict):
        return None
    start = value.get("line_start")
    end = value.get("line_end")
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 1
        or end < start
        or end > line_count
    ):
        return None
    return start, end


def source_model_payload(workspace: Mapping[str, Any]) -> Dict[str, Any]:
    source = workspace.get("source") if isinstance(workspace.get("source"), dict) else {}
    return {
        "locked_text": normalize_text(source.get("locked_text")),
        "authority_policy": copy.deepcopy(source.get("authority_policy")),
        "scopes": copy.deepcopy(source.get("scopes")),
        "source_units": copy.deepcopy(source.get("source_units")),
        "classification_reviews": copy.deepcopy(source.get("classification_reviews")),
        "source_gaps": copy.deepcopy(source.get("source_gaps")),
        "source_passages": copy.deepcopy(source.get("source_passages")),
        "source_facts": copy.deepcopy(source.get("source_facts")),
        "supplemental_reference_facts": copy.deepcopy(workspace.get("supplemental_reference_facts")),
        "assumption_obligations": copy.deepcopy(workspace.get("assumption_obligations")),
    }


def alignment_payload(workspace: Mapping[str, Any], shot_data: Mapping[str, Any]) -> Dict[str, Any]:
    shots = shot_data.get("shots") if isinstance(shot_data.get("shots"), list) else []
    scenes = shot_data.get("scenes") if isinstance(shot_data.get("scenes"), list) else []
    formal_execution: List[Dict[str, Any]] = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        formal_execution.append(
            {
                "shot_id": shot.get("shot_id"),
                "scene_id": shot.get("scene_id"),
                "duration_seconds": shot.get("duration_seconds"),
                "duration_basis": normalize_text(shot.get("duration_basis")),
                "motivation": copy.deepcopy(shot.get("motivation")),
                "viewpoint": copy.deepcopy(shot.get("viewpoint")),
                "camera": copy.deepcopy(shot.get("camera")),
                "staging": copy.deepcopy(shot.get("staging")),
                "sound": copy.deepcopy(shot.get("sound")),
                "edit": copy.deepcopy(shot.get("edit")),
                "continuity": copy.deepcopy(shot.get("continuity")),
                "shot_flow": copy.deepcopy(shot.get("shot_flow")),
                "execution_text": normalize_text(shot.get("execution_text")),
                "notes": normalize_text(shot.get("notes")),
            }
        )
    return {
        "source_model": source_model_payload(workspace),
        "shot_bindings": copy.deepcopy(workspace.get("shot_bindings")),
        "director_inferences": copy.deepcopy(workspace.get("director_inferences")),
        "assumptions": copy.deepcopy(shot_data.get("assumptions")),
        "director_design": copy.deepcopy(shot_data.get("director_design")),
        "scenes": [
            {
                "scene_id": scene.get("scene_id"),
                "space_map": copy.deepcopy(scene.get("space_map")),
                "lighting_strategy": normalize_text(scene.get("lighting_strategy")),
                "color_strategy": normalize_text(scene.get("color_strategy")),
            }
            for scene in scenes
            if isinstance(scene, dict)
        ],
        "formal_execution": formal_execution,
    }


def expected_alignment_hashes(
    workspace: Mapping[str, Any], shot_data: Mapping[str, Any]
) -> Dict[str, str]:
    execution_payload = {
        key: value
        for key, value in alignment_payload(workspace, shot_data).items()
        if key in {"assumptions", "director_design", "scenes", "formal_execution"}
    }
    return {
        "source_model_hash": canonical_hash(source_model_payload(workspace)),
        "execution_hash": canonical_hash(execution_payload),
        "alignment_hash": canonical_hash(alignment_payload(workspace, shot_data)),
    }


def _passage_text(
    passage: Mapping[str, Any],
    unit_map: Mapping[str, Mapping[str, Any]],
    source_lines: Sequence[str],
) -> str:
    units = [unit_map.get(unit_id) for unit_id in passage.get("source_unit_ids", [])]
    valid_units = [unit for unit in units if isinstance(unit, dict)]
    if not valid_units:
        return ""
    start = min(int(unit.get("line_start", 0)) for unit in valid_units)
    end = max(int(unit.get("line_end", 0)) for unit in valid_units)
    if start < 1 or end < start or end > len(source_lines):
        return ""
    return normalize_text("\n".join(source_lines[start - 1 : end]))


def validate_source_alignment(
    workspace: Any,
    shot_data: Any,
    *,
    check_lock: bool = True,
) -> Dict[str, Any]:
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    dimensions = {
        "source_integrity": "PASS",
        "source_authority": "PASS",
        "source_coverage": "PASS",
        "source_alignment": "PASS",
    }

    if not isinstance(workspace, dict):
        errors.append(issue("WORKSPACE_NOT_OBJECT", "$", "director workspace 顶层必须是对象。"))
        dimensions = {key: "FAIL" for key in dimensions}
        return _alignment_report(errors, warnings, dimensions, {})
    if not isinstance(shot_data, dict):
        errors.append(issue("SHOT_DATA_NOT_OBJECT", "shot_data", "正式 shot data 顶层必须是对象。"))
        dimensions["source_alignment"] = "FAIL"
        return _alignment_report(errors, warnings, dimensions, {})

    source = workspace.get("source") if isinstance(workspace.get("source"), dict) else {}
    locked_text = normalize_text(source.get("locked_text"))
    source_lines = locked_text.split("\n") if locked_text else []
    formal_source = shot_data.get("source") if isinstance(shot_data.get("source"), dict) else {}
    formal_locked_text = normalize_text(formal_source.get("locked_text"))
    if not locked_text:
        errors.append(issue("LOCKED_TEXT_EMPTY", "source.locked_text", "内部锁定来源为空。"))
        dimensions["source_integrity"] = "FAIL"
    if locked_text != formal_locked_text:
        errors.append(issue("FORMAL_SOURCE_DIVERGED", "shot_data.source.locked_text", "正式数据与 workspace 的 locked_text 不一致。"))
        dimensions["source_integrity"] = "FAIL"
    if source.get("source_hash") != text_hash(locked_text):
        errors.append(issue("SOURCE_LOCK_INVALIDATED", "source.source_hash", "locked_text 已变化，来源锁和 Gate 必须重新审阅。"))
        dimensions["source_integrity"] = "FAIL"

    policy = source.get("authority_policy") if isinstance(source.get("authority_policy"), dict) else {}
    performance_authority = policy.get("performance_authority")
    reference_languages = policy.get("reference_languages")
    bilingual_relation = policy.get("bilingual_relation")
    if not nonempty(performance_authority) or not nonempty(policy.get("authority_basis")):
        errors.append(issue("SOURCE_AUTHORITY_UNRESOLVED", "source.authority_policy", "缺少表演权威语言或其依据。"))
        dimensions["source_authority"] = "FAIL"
    if not string_list(reference_languages, allow_empty=True):
        errors.append(issue("SOURCE_AUTHORITY_UNRESOLVED", "source.authority_policy.reference_languages", "参考语言必须是字符串数组。"))
        dimensions["source_authority"] = "FAIL"
        reference_languages = []
    if bilingual_relation not in BILINGUAL_RELATIONS:
        errors.append(issue("SOURCE_AUTHORITY_UNRESOLVED", "source.authority_policy.bilingual_relation", "双语关系未明确。"))
        dimensions["source_authority"] = "FAIL"
    if reference_languages and bilingual_relation == "independent":
        errors.append(issue("SOURCE_AUTHORITY_UNRESOLVED", "source.authority_policy.bilingual_relation", "存在参考语言时不能用 independent 回避权威关系。"))
        dimensions["source_authority"] = "FAIL"

    formal_scenes = shot_data.get("scenes") if isinstance(shot_data.get("scenes"), list) else []
    formal_shots = shot_data.get("shots") if isinstance(shot_data.get("shots"), list) else []
    scene_ids = {
        item.get("scene_id")
        for item in formal_scenes
        if isinstance(item, dict) and nonempty(item.get("scene_id"))
    }
    shot_map = {
        item.get("shot_id"): item
        for item in formal_shots
        if isinstance(item, dict) and nonempty(item.get("shot_id"))
    }

    scopes = source.get("scopes") if isinstance(source.get("scopes"), list) else []
    scope_map: Dict[str, Mapping[str, Any]] = {}
    scope_authority_lines: Dict[str, Set[int]] = defaultdict(set)
    scope_reference_lines: Dict[str, Set[int]] = defaultdict(set)
    for index, scope in enumerate(scopes):
        path = f"source.scopes[{index}]"
        if not isinstance(scope, dict):
            errors.append(issue("SOURCE_SCOPE_INVALID", path, "source scope 必须是对象。"))
            dimensions["source_integrity"] = "FAIL"
            continue
        scope_id = scope.get("scope_id")
        if not nonempty(scope_id) or scope_id in scope_map:
            errors.append(issue("SOURCE_SCOPE_INVALID", path + ".scope_id", "scope_id 为空或重复。"))
            dimensions["source_integrity"] = "FAIL"
            continue
        if scope_id != "GLOBAL" and scope_id not in scene_ids:
            errors.append(issue("SOURCE_SCOPE_INVALID", path + ".scope_id", "场级 scope 不存在于正式 scenes。"))
            dimensions["source_integrity"] = "FAIL"
        expected_kind = "global" if scope_id == "GLOBAL" else "scene"
        if scope.get("scope_kind") != expected_kind:
            errors.append(issue("SOURCE_SCOPE_INVALID", path + ".scope_kind", "scope_kind 与 scope_id 不一致。"))
            dimensions["source_integrity"] = "FAIL"
        scope_map[scope_id] = scope
        for field, owner in (
            ("authority_line_ranges", scope_authority_lines),
            ("reference_line_ranges", scope_reference_lines),
        ):
            ranges = scope.get(field)
            if not isinstance(ranges, list):
                errors.append(issue("SOURCE_SCOPE_RANGE_INVALID", path + "." + field, "行范围必须是数组。"))
                dimensions["source_integrity"] = "FAIL"
                continue
            for range_index, raw_range in enumerate(ranges):
                parsed = line_range(raw_range, len(source_lines))
                if parsed is None:
                    errors.append(issue("SOURCE_SCOPE_RANGE_INVALID", f"{path}.{field}[{range_index}]", "scope 行范围无效。"))
                    dimensions["source_integrity"] = "FAIL"
                    continue
                start, end = parsed
                for line_number in range(start, end + 1):
                    if line_number in owner[scope_id]:
                        errors.append(issue("SOURCE_SCOPE_RANGE_OVERLAP", f"{path}.{field}[{range_index}]", "scope 行范围内部重叠。"))
                        dimensions["source_integrity"] = "FAIL"
                    owner[scope_id].add(line_number)

    for scope_id in set(scope_authority_lines) | set(scope_reference_lines):
        overlap = sorted(scope_authority_lines[scope_id] & scope_reference_lines[scope_id])
        if overlap:
            errors.append(
                issue(
                    "SOURCE_AUTHORITY_REFERENCE_OVERLAP",
                    f"source.scopes[{scope_id}]",
                    "同一来源行不能同时属于 authority 与 reference 范围：{}。".format(
                        ", ".join(map(str, overlap))
                    ),
                )
            )
            dimensions["source_authority"] = "FAIL"

    classification_reviews_value = source.get("classification_reviews")
    classification_reviews = (
        classification_reviews_value
        if isinstance(classification_reviews_value, list)
        else []
    )
    if not isinstance(classification_reviews_value, list):
        errors.append(
            issue(
                "SOURCE_CLASSIFICATION_REVIEWS_INVALID",
                "source.classification_reviews",
                "classification_reviews 必须是数组。",
            )
        )
        dimensions["source_integrity"] = "FAIL"
    classification_review_map: Dict[str, Mapping[str, Any]] = {}
    for review_index, review in enumerate(classification_reviews):
        review_path = f"source.classification_reviews[{review_index}]"
        if not isinstance(review, dict):
            errors.append(issue("SOURCE_CLASSIFICATION_REVIEW_INVALID", review_path, "分类复核必须是对象。"))
            dimensions["source_integrity"] = "FAIL"
            continue
        unit_id = review.get("unit_id")
        if not nonempty(unit_id) or unit_id in classification_review_map:
            errors.append(issue("SOURCE_CLASSIFICATION_REVIEW_INVALID", review_path + ".unit_id", "分类复核 unit_id 为空或重复。"))
            dimensions["source_integrity"] = "FAIL"
            continue
        classification_review_map[str(unit_id)] = review
        if (
            review.get("decision") != "non_narrative"
            or review.get("status") != "approved"
            or not nonempty(review.get("reason"))
            or not nonempty(review.get("reviewer"))
        ):
            errors.append(issue("SOURCE_CLASSIFICATION_REVIEW_INVALID", review_path, "非叙事分类复核必须明确 approved、理由和复核人。"))
            dimensions["source_integrity"] = "FAIL"
        if review.get("review_hash") != classification_review_hash(review):
            errors.append(issue("SOURCE_CLASSIFICATION_REVIEW_HASH_MISMATCH", review_path + ".review_hash", "分类复核哈希与当前复核内容不匹配。"))
            dimensions["source_integrity"] = "FAIL"

    units = source.get("source_units") if isinstance(source.get("source_units"), list) else []
    unit_map: Dict[str, Mapping[str, Any]] = {}
    line_owners: Dict[int, List[str]] = defaultdict(list)
    previous_start = 0
    authority_unit_ids: Set[str] = set()
    unit_role_counts: Counter[str] = Counter()
    for index, unit in enumerate(units):
        path = f"source.source_units[{index}]"
        if not isinstance(unit, dict):
            errors.append(issue("SOURCE_UNIT_INVALID", path, "source unit 必须是对象。"))
            dimensions["source_integrity"] = "FAIL"
            continue
        unit_id = unit.get("unit_id")
        if not nonempty(unit_id) or unit_id in unit_map:
            errors.append(issue("SOURCE_UNIT_ID_DUPLICATE", path + ".unit_id", "source unit ID 为空或重复。"))
            dimensions["source_integrity"] = "FAIL"
            continue
        unit_map[unit_id] = unit
        scope_id = unit.get("scope_id")
        if scope_id not in scope_map:
            errors.append(issue("SOURCE_UNIT_SCOPE_UNKNOWN", path + ".scope_id", "source unit 引用不存在的 scope。"))
            dimensions["source_integrity"] = "FAIL"
        role = unit.get("authority_role")
        language = unit.get("language")
        if role not in AUTHORITY_ROLES or not nonempty(language):
            errors.append(issue("SOURCE_UNIT_AUTHORITY_INVALID", path, "source unit 缺少合法语言或 authority_role。"))
            dimensions["source_authority"] = "FAIL"
        else:
            unit_role_counts[role] += 1
            if role == "performance_authority":
                authority_unit_ids.add(unit_id)
                if language != performance_authority:
                    errors.append(issue("SOURCE_UNIT_AUTHORITY_INVALID", path + ".language", "权威 unit 语言与 performance_authority 不一致。"))
                    dimensions["source_authority"] = "FAIL"
            elif role == "adapted_reference" and language not in set(reference_languages or []):
                errors.append(issue("SOURCE_UNIT_AUTHORITY_INVALID", path + ".language", "参考 unit 语言未登记在 reference_languages。"))
                dimensions["source_authority"] = "FAIL"
        start = unit.get("line_start")
        end = unit.get("line_end")
        parsed = line_range({"line_start": start, "line_end": end}, len(source_lines))
        if parsed is None:
            errors.append(issue("SOURCE_UNIT_RANGE_INVALID", path, "source unit 行范围无效。"))
            dimensions["source_integrity"] = "FAIL"
            continue
        start, end = parsed
        if start < previous_start:
            errors.append(issue("SOURCE_UNIT_ORDER_DIVERGED", path, "source units 未按 locked_text 行号排序。"))
            dimensions["source_integrity"] = "FAIL"
        previous_start = start
        actual = normalize_text("\n".join(source_lines[start - 1 : end]))
        if normalize_text(unit.get("exact_text")) != actual:
            errors.append(issue("SOURCE_UNIT_TEXT_MISMATCH", path + ".exact_text", "exact_text 与 locked_text 行范围不一致。"))
            dimensions["source_integrity"] = "FAIL"
        kind = unit.get("kind")
        review = classification_review_map.get(str(unit_id))
        reviewed_allowed = bool(
            isinstance(review, dict)
            and review.get("decision") == "non_narrative"
            and review.get("status") == "approved"
            and review.get("source_text_hash") == text_hash(actual)
            and review.get("review_hash") == classification_review_hash(review)
        )
        if kind in {"scene_heading", "transition"} and not source_kind_matches_text(kind, actual):
            errors.append(
                issue(
                    "SOURCE_UNIT_KIND_LAUNDERING",
                    path + ".kind",
                    "该来源文本不符合声明的 scene_heading 或 transition；不得借非事实类 kind 规避 fact inventory。",
                )
            )
            dimensions["source_integrity"] = "FAIL"
        if kind == "metadata" and not is_mechanical_non_narrative_metadata(actual) and looks_probably_narrative(actual):
            errors.append(
                issue(
                    "SOURCE_NARRATIVE_CLASSIFICATION_FORBIDDEN",
                    path + ".kind",
                    "该来源行包含明确对白或动作信号，不能被分类为 metadata/non_narrative；人工复核也不能覆盖这一保护。",
                )
            )
            dimensions["source_integrity"] = "FAIL"
        elif kind == "metadata" and not (is_mechanical_non_narrative_metadata(actual) or reviewed_allowed):
            errors.append(
                issue(
                    "SOURCE_UNIT_KIND_LAUNDERING",
                    path + ".kind",
                    "该来源文本不是机械可识别元数据，且没有有效人工分类复核；不得借 metadata 规避 fact inventory。",
                )
            )
            dimensions["source_integrity"] = "FAIL"
        if role == "non_narrative":
            mechanically_allowed = kind == "metadata" and is_mechanical_non_narrative_metadata(actual)
            if kind != "metadata" or looks_probably_narrative(actual) or not (mechanically_allowed or reviewed_allowed):
                errors.append(
                    issue(
                        "SOURCE_NON_NARRATIVE_CLASSIFICATION_UNAPPROVED",
                        path,
                        "非空来源行默认属于叙事；只有机械可识别元数据或具有有效人工分类复核的 metadata 才能标为 non_narrative。",
                    )
                )
                dimensions["source_integrity"] = "FAIL"
        for line_number in range(start, end + 1):
            if source_lines[line_number - 1].strip():
                line_owners[line_number].append(unit_id)
        expected_lines = (
            scope_authority_lines.get(scope_id, set())
            if role == "performance_authority"
            else scope_reference_lines.get(scope_id, set())
            if role == "adapted_reference"
            else set()
        )
        if role != "non_narrative" and any(number not in expected_lines for number in range(start, end + 1) if source_lines[number - 1].strip()):
            errors.append(issue("SOURCE_SCENE_RANGE_MISMATCH", path, "source unit 行范围不属于声明的 scope/authority 范围。"))
            dimensions["source_authority"] = "FAIL"

    uncovered_lines = [
        number
        for number, line in enumerate(source_lines, start=1)
        if line.strip() and not line_owners.get(number)
    ]
    duplicate_lines = [number for number, owners in line_owners.items() if len(owners) != 1]
    if uncovered_lines:
        errors.append(issue("SOURCE_LINES_UNCOVERED", "source.source_units", "非空来源行未登记：{}。".format(", ".join(map(str, uncovered_lines)))))
        dimensions["source_integrity"] = "FAIL"
    if duplicate_lines:
        errors.append(issue("SOURCE_UNIT_ORDER_DIVERGED", "source.source_units", "非空来源行被重复登记：{}。".format(", ".join(map(str, duplicate_lines)))))
        dimensions["source_integrity"] = "FAIL"

    for reviewed_unit_id, review in classification_review_map.items():
        reviewed_unit = unit_map.get(reviewed_unit_id)
        if reviewed_unit is None:
            errors.append(issue("SOURCE_CLASSIFICATION_REVIEW_INVALID", "source.classification_reviews", f"分类复核引用不存在的 unit {reviewed_unit_id}。"))
            dimensions["source_integrity"] = "FAIL"
            continue
        if reviewed_unit.get("authority_role") != "non_narrative":
            errors.append(issue("SOURCE_CLASSIFICATION_REVIEW_ORPHANED", "source.classification_reviews", f"分类复核 {reviewed_unit_id} 未对应 non_narrative unit。"))
            dimensions["source_integrity"] = "FAIL"

    passages = source.get("source_passages") if isinstance(source.get("source_passages"), list) else []
    passage_map: Dict[str, Mapping[str, Any]] = {}
    unit_passage_counts: Counter[str] = Counter()
    passage_shot_refs: Dict[str, Set[str]] = {}
    coverage_counts: Counter[str] = Counter()
    for index, passage in enumerate(passages):
        path = f"source.source_passages[{index}]"
        if not isinstance(passage, dict):
            errors.append(issue("SOURCE_PASSAGE_INVALID", path, "source passage 必须是对象。"))
            dimensions["source_coverage"] = "FAIL"
            continue
        passage_id = passage.get("passage_id")
        if not nonempty(passage_id) or passage_id in passage_map:
            errors.append(issue("SOURCE_PASSAGE_ID_DUPLICATE", path + ".passage_id", "passage ID 为空或重复。"))
            dimensions["source_coverage"] = "FAIL"
            continue
        passage_map[passage_id] = passage
        scope_id = passage.get("scope_id")
        if scope_id not in scope_map:
            errors.append(issue("SOURCE_PASSAGE_SCOPE_UNKNOWN", path + ".scope_id", "passage 引用不存在的 scope。"))
            dimensions["source_coverage"] = "FAIL"
        unit_ids = passage.get("source_unit_ids")
        if not string_list(unit_ids):
            errors.append(issue("SOURCE_PASSAGE_UNITS_EMPTY", path + ".source_unit_ids", "passage 必须引用权威 source units。"))
            dimensions["source_coverage"] = "FAIL"
            unit_ids = []
        passage_units: List[Mapping[str, Any]] = []
        for unit_id in unit_ids:
            unit = unit_map.get(unit_id)
            if unit is None:
                errors.append(issue("SOURCE_PASSAGE_UNIT_UNKNOWN", path + ".source_unit_ids", f"passage 引用不存在 unit {unit_id}。"))
                dimensions["source_coverage"] = "FAIL"
                continue
            passage_units.append(unit)
            unit_passage_counts[unit_id] += 1
            if unit.get("authority_role") != "performance_authority":
                errors.append(issue("SOURCE_REFERENCE_RENDERED", path + ".source_unit_ids", "参考或非叙事 unit 不得进入权威 passage。"))
                dimensions["source_authority"] = "FAIL"
            if unit.get("scope_id") != scope_id:
                errors.append(issue("SOURCE_SCENE_RANGE_MISMATCH", path + ".scope_id", "passage 与 unit scope 不一致。"))
                dimensions["source_coverage"] = "FAIL"
        sorted_units = sorted(passage_units, key=lambda item: (item.get("line_start", 0), item.get("line_end", 0)))
        if passage_units != sorted_units:
            errors.append(issue("SOURCE_UNIT_ORDER_DIVERGED", path + ".source_unit_ids", "passage 内 units 未按来源顺序排列。"))
            dimensions["source_coverage"] = "FAIL"
        if sorted_units:
            start = int(sorted_units[0].get("line_start", 0))
            end = int(sorted_units[-1].get("line_end", 0))
            included_lines: Set[int] = set()
            for unit in sorted_units:
                included_lines.update(range(int(unit.get("line_start", 0)), int(unit.get("line_end", 0)) + 1))
            missing_nonempty = [
                number
                for number in range(start, end + 1)
                if source_lines[number - 1].strip() and number not in included_lines
            ]
            if missing_nonempty:
                errors.append(issue("SOURCE_PASSAGE_NOT_CONTIGUOUS", path + ".source_unit_ids", "passage 跨过了未引用的非空来源行。"))
                dimensions["source_coverage"] = "FAIL"
        coverage = passage.get("coverage_status")
        if coverage not in COVERAGE_STATUSES:
            errors.append(issue("SOURCE_COVERAGE_STATUS_INVALID", path + ".coverage_status", "passage coverage_status 无效。"))
            dimensions["source_coverage"] = "FAIL"
        else:
            coverage_counts[coverage] += 1
        shot_refs = passage.get("shot_refs")
        if not isinstance(shot_refs, list) or any(not nonempty(item) for item in shot_refs):
            errors.append(issue("SOURCE_PASSAGE_SHOT_REFS_INVALID", path + ".shot_refs", "passage shot_refs 必须是字符串数组。"))
            dimensions["source_coverage"] = "FAIL"
            shot_refs = []
        passage_shot_refs[passage_id] = set(shot_refs)
        unknown_shots = [shot_id for shot_id in shot_refs if shot_id not in shot_map]
        if unknown_shots:
            errors.append(issue("SOURCE_SHOT_REF_UNKNOWN", path + ".shot_refs", "passage 引用不存在镜头：{}。".format(", ".join(unknown_shots))))
            dimensions["source_coverage"] = "FAIL"
        if coverage == "covered" and not shot_refs:
            errors.append(issue("SOURCE_UNIT_UNCOVERED", path + ".shot_refs", "covered passage 必须引用正式镜头。"))
            dimensions["source_coverage"] = "FAIL"
        if coverage in {"intentionally_withheld", "intentionally_omitted"} and not nonempty(passage.get("reason")):
            errors.append(issue("SOURCE_OMISSION_REASON_EMPTY", path + ".reason", "有意隐藏或省略必须说明理由。"))
            dimensions["source_coverage"] = "FAIL"
        passage_text = _passage_text(passage, unit_map, source_lines)
        if normalize_text(passage_text) in CONTEXT_ONLY_TEXTS:
            errors.append(issue("SOURCE_PASSAGE_CONTEXT_INCOMPLETE", path, "passage 只有上下文碎片，必须合并完整主体、动作或结果。"))
            dimensions["source_coverage"] = "FAIL"

    missing_passage_units = sorted(unit_id for unit_id in authority_unit_ids if unit_passage_counts[unit_id] == 0)
    duplicate_passage_units = sorted(unit_id for unit_id in authority_unit_ids if unit_passage_counts[unit_id] > 1)
    if missing_passage_units:
        errors.append(issue("SOURCE_UNITS_WITHOUT_PASSAGE", "source.source_passages", "权威 units 未进入 passage：{}。".format(", ".join(missing_passage_units))))
        dimensions["source_coverage"] = "FAIL"
    if duplicate_passage_units:
        errors.append(issue("SOURCE_UNITS_MULTI_PASSAGE", "source.source_passages", "权威 units 被多个 passage 重复拥有：{}。".format(", ".join(duplicate_passage_units))))
        dimensions["source_coverage"] = "FAIL"

    facts = source.get("source_facts") if isinstance(source.get("source_facts"), list) else []
    fact_map: Dict[str, Mapping[str, Any]] = {}
    passage_fact_counts: Counter[str] = Counter()
    unit_fact_counts: Counter[str] = Counter()
    unit_facts: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    unit_required_fact_counts: Counter[str] = Counter()
    unit_required_negation_counts: Counter[str] = Counter()
    for index, fact in enumerate(facts):
        path = f"source.source_facts[{index}]"
        if not isinstance(fact, dict):
            errors.append(issue("SOURCE_FACT_INVALID", path, "source fact 必须是对象。"))
            dimensions["source_alignment"] = "FAIL"
            continue
        fact_id = fact.get("fact_id")
        if not nonempty(fact_id) or fact_id in fact_map:
            errors.append(issue("SOURCE_FACT_ID_DUPLICATE", path + ".fact_id", "fact ID 为空或重复。"))
            dimensions["source_alignment"] = "FAIL"
            continue
        fact_map[fact_id] = fact
        passage_id = fact.get("passage_id")
        if passage_id not in passage_map:
            errors.append(issue("SOURCE_FACT_PASSAGE_UNKNOWN", path + ".passage_id", "fact 引用不存在 passage。"))
            dimensions["source_alignment"] = "FAIL"
        else:
            passage_fact_counts[passage_id] += 1
        source_unit_ids = fact.get("source_unit_ids")
        if not string_list(source_unit_ids):
            errors.append(issue("SOURCE_FACT_INVALID", path + ".source_unit_ids", "fact 必须引用至少一个权威 source unit。"))
            dimensions["source_alignment"] = "FAIL"
            source_unit_ids = []
        fact_units: List[Mapping[str, Any]] = []
        for unit_id in source_unit_ids:
            source_unit = unit_map.get(unit_id)
            if source_unit is None:
                errors.append(issue("SOURCE_FACT_UNIT_UNKNOWN", path + ".source_unit_ids", f"fact 引用不存在 unit {unit_id}。"))
                dimensions["source_alignment"] = "FAIL"
                continue
            fact_units.append(source_unit)
            unit_fact_counts[unit_id] += 1
            unit_facts[unit_id].append(fact)
            if fact.get("importance") == "required":
                unit_required_fact_counts[unit_id] += 1
                if fact.get("kind") == "negation" and fact.get("polarity") == "negative":
                    unit_required_negation_counts[unit_id] += 1
            if source_unit.get("authority_role") != "performance_authority":
                errors.append(issue("SOURCE_FACT_UNIT_AUTHORITY_INVALID", path + ".source_unit_ids", "source fact 只能引用 performance-authority units。"))
                dimensions["source_alignment"] = "FAIL"
            if passage_id in passage_map and unit_id not in passage_map[passage_id].get("source_unit_ids", []):
                errors.append(issue("SOURCE_FACT_UNIT_PASSAGE_DIVERGED", path + ".source_unit_ids", "fact source unit 不属于其 passage。"))
                dimensions["source_alignment"] = "FAIL"
        source_span = normalize_text(fact.get("source_span"))
        fact_source_text = normalize_text("\n".join(str(unit.get("exact_text", "")) for unit in fact_units))
        if not source_span or source_span not in fact_source_text:
            errors.append(issue("SOURCE_FACT_SPAN_MISMATCH", path + ".source_span", "fact source_span 未逐字出现在其 source units。"))
            dimensions["source_alignment"] = "FAIL"
        meaningful_span = re.sub(r"[\W_]+", "", source_span, flags=re.UNICODE)
        if len(meaningful_span) < 2:
            errors.append(
                issue(
                    "SOURCE_FACT_SPAN_TOO_WEAK",
                    path + ".source_span",
                    "fact source_span 过短，不能用单字或无意义碎片证明语义来源。",
                )
            )
            dimensions["source_alignment"] = "FAIL"
        if fact.get("kind") not in FACT_KINDS or fact.get("importance") not in {"required", "supporting"}:
            errors.append(issue("SOURCE_FACT_INVALID", path, "fact kind 或 importance 无效。"))
            dimensions["source_alignment"] = "FAIL"
        if fact.get("kind") in PROTECTED_FACT_KINDS and fact.get("importance") != "required":
            errors.append(issue("SOURCE_PROTECTED_FACT_DOWNGRADED", path + ".importance", "protected fact kind 不得降级为 supporting。"))
            dimensions["source_alignment"] = "FAIL"
        if not nonempty(fact.get("predicate")):
            errors.append(issue("SOURCE_FACT_INVALID", path + ".predicate", "fact predicate 为空。"))
            dimensions["source_alignment"] = "FAIL"
        for field in ("subjects", "objects", "qualifiers", "anchors", "cause_fact_ids", "effect_fact_ids"):
            if not string_list(fact.get(field), allow_empty=True):
                errors.append(issue("SOURCE_FACT_INVALID", path + "." + field, f"{field} 必须是字符串数组。"))
                dimensions["source_alignment"] = "FAIL"
        if fact.get("kind") in PROTECTED_FACT_KINDS:
            anchors = fact.get("anchors") if isinstance(fact.get("anchors"), list) else []
            if not anchors:
                errors.append(issue("SOURCE_PROTECTED_FACT_ANCHOR_MISSING", path + ".anchors", "protected fact 必须保留至少一个来源语义锚点。"))
                dimensions["source_alignment"] = "FAIL"
            elif not any(normalize_text(anchor) in fact_source_text for anchor in anchors):
                errors.append(issue("SOURCE_PROTECTED_FACT_ANCHOR_MISMATCH", path + ".anchors", "protected fact anchors 未逐字出现在其 source units。"))
                dimensions["source_alignment"] = "FAIL"
        if fact.get("polarity") not in {"positive", "negative"}:
            errors.append(issue("SOURCE_FACT_INVALID", path + ".polarity", "fact polarity 无效。"))
            dimensions["source_alignment"] = "FAIL"
        source_contains_negation = bool(NEGATION_UNIT_RE.search(source_span or fact_source_text))
        if source_contains_negation and fact.get("polarity") != "negative":
            errors.append(
                issue(
                    "SOURCE_NEGATION_POLARITY_MISMATCH",
                    path + ".polarity",
                    "来源 span 含否定结构，fact 必须保持 negative polarity。",
                )
            )
            dimensions["source_alignment"] = "FAIL"

    for passage_id, passage in passage_map.items():
        if passage.get("coverage_status") == "covered" and passage_fact_counts[passage_id] == 0:
            errors.append(issue("SOURCE_FACTS_EMPTY", f"source.source_passages[{passage_id}]", "covered passage 必须至少登记一个来源 fact。"))
            dimensions["source_alignment"] = "FAIL"

    authoritative_narrative_units = {
        unit_id: unit
        for unit_id, unit in unit_map.items()
        if unit.get("authority_role") == "performance_authority"
        and unit.get("kind") not in {"metadata", "scene_heading", "transition"}
    }
    missing_fact_units = sorted(unit_id for unit_id in authoritative_narrative_units if unit_fact_counts[unit_id] == 0)
    if missing_fact_units:
        errors.append(issue("SOURCE_FACT_INVENTORY_MISSING", "source.source_facts", "权威叙事 units 未进入独立 fact inventory：{}。".format(", ".join(missing_fact_units))))
        dimensions["source_alignment"] = "FAIL"

    required_unit_missing = sorted(
        unit_id for unit_id in authoritative_narrative_units if unit_required_fact_counts[unit_id] == 0
    )
    if required_unit_missing:
        errors.append(issue("SOURCE_REQUIRED_FACT_INVENTORY_MISSING", "source.source_facts", "每个权威叙事 unit 必须由至少一个 required fact 持有，supporting 不能独占 unit：{}。".format(", ".join(required_unit_missing))))
        dimensions["source_alignment"] = "FAIL"

    for unit_id, unit in authoritative_narrative_units.items():
        requirements = derive_unit_protection_requirements(unit)
        owned_facts = unit_facts.get(unit_id, [])
        for class_name, requirement in requirements.items():
            allowed_kinds = set(requirement["allowed_kinds"])
            candidates = [
                fact
                for fact in owned_facts
                if fact.get("importance") == "required" and fact.get("kind") in allowed_kinds
            ]
            if not candidates:
                errors.append(issue("SOURCE_PROTECTED_UNIT_REQUIRED_FACT_MISSING", f"source.source_units[{unit_id}]", f"锁定来源 unit 独立派生 {class_name}，必须由 required {sorted(allowed_kinds)} fact 持有。"))
                dimensions["source_alignment"] = "FAIL"

    dialogue_required_missing = sorted(
        unit_id
        for unit_id, unit in authoritative_narrative_units.items()
        if unit.get("kind") == "dialogue" and unit_required_fact_counts[unit_id] == 0
    )
    if dialogue_required_missing:
        errors.append(issue("SOURCE_REQUIRED_FACT_INVENTORY_MISSING", "source.source_facts", "来源对白 units 缺少 required facts：{}。".format(", ".join(dialogue_required_missing))))
        dimensions["source_alignment"] = "FAIL"

    negative_unit_ids = {
        unit_id
        for unit_id, unit in authoritative_narrative_units.items()
        if NEGATION_UNIT_RE.search(normalize_text(unit.get("exact_text")))
    }
    missing_negative_inventory = sorted(unit_id for unit_id in negative_unit_ids if unit_required_negation_counts[unit_id] == 0)
    if missing_negative_inventory:
        errors.append(issue("SOURCE_REQUIRED_FACT_INVENTORY_MISSING", "source.source_facts", "来源否定 units 缺少 required negative facts：{}。".format(", ".join(missing_negative_inventory))))
        dimensions["source_alignment"] = "FAIL"

    ordered_scene_ids = [
        item.get("scene_id")
        for item in formal_scenes
        if isinstance(item, dict) and nonempty(item.get("scene_id"))
    ]
    if ordered_scene_ids:
        final_scene_id = ordered_scene_ids[-1]
        final_units = sorted(
            (
                (unit_id, unit)
                for unit_id, unit in authoritative_narrative_units.items()
                if unit.get("scope_id") == final_scene_id
            ),
            key=lambda item: (item[1].get("line_start", 0), item[1].get("line_end", 0)),
        )
        if final_units:
            final_unit_id = final_units[-1][0]
            if unit_required_fact_counts[final_unit_id] == 0:
                errors.append(issue("SOURCE_REQUIRED_FACT_INVENTORY_MISSING", f"source.source_units[{final_unit_id}]", "最终场最后权威叙事 unit 必须登记 required fact。"))
                dimensions["source_alignment"] = "FAIL"

    supplemental_value = workspace.get("supplemental_reference_facts")
    supplemental_facts = supplemental_value if isinstance(supplemental_value, list) else []
    if not isinstance(supplemental_value, list):
        errors.append(issue("SUPPLEMENTAL_REFERENCE_REGISTRY_INVALID", "supplemental_reference_facts", "workspace 必须显式提供 supplemental reference fact registry 数组。"))
        dimensions["source_alignment"] = "FAIL"
    reference_fact_map: Dict[str, Mapping[str, Any]] = {}
    invalid_reference_fact_ids: Set[str] = set()
    for index, reference_fact in enumerate(supplemental_facts):
        path = f"supplemental_reference_facts[{index}]"
        if not isinstance(reference_fact, dict):
            errors.append(issue("SUPPLEMENTAL_REFERENCE_FACT_INVALID", path, "supplemental reference fact 必须是对象。"))
            dimensions["source_alignment"] = "FAIL"
            continue
        reference_fact_id = reference_fact.get("reference_fact_id")
        if not nonempty(reference_fact_id) or reference_fact_id in reference_fact_map:
            errors.append(issue("SUPPLEMENTAL_REFERENCE_FACT_INVALID", path + ".reference_fact_id", "reference fact ID 为空或重复。"))
            dimensions["source_alignment"] = "FAIL"
            continue
        reference_fact_map[reference_fact_id] = reference_fact
        if not nonempty(reference_fact.get("statement")) or not nonempty(reference_fact.get("source_excerpt")):
            errors.append(issue("SUPPLEMENTAL_REFERENCE_FACT_INVALID", path, "reference fact 必须有 statement 和 source_excerpt。"))
            invalid_reference_fact_ids.add(reference_fact_id)
            dimensions["source_alignment"] = "FAIL"
        provenance = reference_fact.get("provenance")
        if not isinstance(provenance, dict) or any(
            not nonempty(provenance.get(field))
            for field in ("source_type", "source_title", "locator", "owner")
        ):
            errors.append(issue("SUPPLEMENTAL_REFERENCE_FACT_INVALID", path + ".provenance", "provenance 必须记录 source_type、source_title、locator 和 owner。"))
            invalid_reference_fact_ids.add(reference_fact_id)
            dimensions["source_alignment"] = "FAIL"
        expected_source_hash = text_hash(reference_fact.get("source_excerpt"))
        if reference_fact.get("source_hash") != expected_source_hash:
            errors.append(issue("SUPPLEMENTAL_REFERENCE_HASH_MISMATCH", path + ".source_hash", "source_hash 与标准化 source_excerpt 不匹配。"))
            invalid_reference_fact_ids.add(reference_fact_id)
            dimensions["source_alignment"] = "FAIL"
        expected_approval_hash = supplemental_reference_approval_hash(reference_fact)
        if reference_fact.get("approval_hash") != expected_approval_hash:
            errors.append(issue("SUPPLEMENTAL_REFERENCE_APPROVAL_HASH_MISMATCH", path + ".approval_hash", "approval_hash 与 fact 内容、来源哈希及 provenance 不匹配。"))
            invalid_reference_fact_ids.add(reference_fact_id)
            dimensions["source_alignment"] = "FAIL"
        if reference_fact.get("approval_status") not in REFERENCE_APPROVAL_STATUSES or not nonempty(reference_fact.get("approval_note")):
            errors.append(issue("SUPPLEMENTAL_REFERENCE_FACT_INVALID", path + ".approval_status", "approval_status 无效或缺少 approval_note。"))
            invalid_reference_fact_ids.add(reference_fact_id)
            dimensions["source_alignment"] = "FAIL"

    assumptions_value = shot_data.get("assumptions")
    formal_assumptions = assumptions_value if isinstance(assumptions_value, list) else []
    assumption_map: Dict[str, Mapping[str, Any]] = {}
    for assumption_index, assumption in enumerate(formal_assumptions):
        if not isinstance(assumption, dict) or not nonempty(assumption.get("assumption_id")):
            continue
        assumption_id = str(assumption.get("assumption_id"))
        if assumption_id in assumption_map:
            errors.append(issue("ASSUMPTION_ID_DUPLICATE", f"shot_data.assumptions[{assumption_index}].assumption_id", "assumption_id 重复。"))
            dimensions["source_alignment"] = "FAIL"
        assumption_map[assumption_id] = assumption

    source_gaps_value = source.get("source_gaps")
    source_gaps = source_gaps_value if isinstance(source_gaps_value, list) else []
    if not isinstance(source_gaps_value, list):
        errors.append(issue("SOURCE_GAPS_INVALID", "source.source_gaps", "source_gaps 必须是数组。"))
        dimensions["source_integrity"] = "FAIL"
    source_gap_map: Dict[str, Mapping[str, Any]] = {}
    for gap_index, gap in enumerate(source_gaps):
        gap_path = f"source.source_gaps[{gap_index}]"
        if not isinstance(gap, dict):
            errors.append(issue("SOURCE_GAP_INVALID", gap_path, "source gap 必须是对象。"))
            dimensions["source_integrity"] = "FAIL"
            continue
        gap_id = gap.get("gap_id")
        if not nonempty(gap_id) or gap_id in source_gap_map:
            errors.append(issue("SOURCE_GAP_INVALID", gap_path + ".gap_id", "gap_id 为空或重复。"))
            dimensions["source_integrity"] = "FAIL"
            continue
        source_gap_map[str(gap_id)] = gap
        if any(not nonempty(gap.get(field)) for field in ("scope", "statement", "basis")):
            errors.append(issue("SOURCE_GAP_INVALID", gap_path, "source gap 必须明确 scope、statement 与 basis。"))
            dimensions["source_integrity"] = "FAIL"

    obligations_value = workspace.get("assumption_obligations")
    obligations = obligations_value if isinstance(obligations_value, list) else []
    if not isinstance(obligations_value, list):
        errors.append(issue("ASSUMPTION_OBLIGATIONS_INVALID", "assumption_obligations", "workspace 必须显式提供 assumption_obligations 数组。"))
        dimensions["source_alignment"] = "FAIL"
    obligation_ids: Set[str] = set()
    obligation_gap_ids: Set[str] = set()
    obligation_assumption_counts: Counter[str] = Counter()
    for obligation_index, obligation in enumerate(obligations):
        obligation_path = f"assumption_obligations[{obligation_index}]"
        if not isinstance(obligation, dict):
            errors.append(issue("ASSUMPTION_OBLIGATION_INVALID", obligation_path, "assumption obligation 必须是对象。"))
            dimensions["source_alignment"] = "FAIL"
            continue
        obligation_id = obligation.get("obligation_id")
        if not nonempty(obligation_id) or obligation_id in obligation_ids:
            errors.append(issue("ASSUMPTION_OBLIGATION_INVALID", obligation_path + ".obligation_id", "obligation_id 为空或重复。"))
            dimensions["source_alignment"] = "FAIL"
        else:
            obligation_ids.add(str(obligation_id))
        gap_id = obligation.get("gap_id")
        if not nonempty(gap_id) or gap_id not in source_gap_map:
            errors.append(issue("ASSUMPTION_OBLIGATION_GAP_UNKNOWN", obligation_path + ".gap_id", "assumption obligation 必须引用已登记的 source gap。"))
            dimensions["source_alignment"] = "FAIL"
        elif gap_id in obligation_gap_ids:
            errors.append(issue("ASSUMPTION_OBLIGATION_GAP_DUPLICATE", obligation_path + ".gap_id", "同一 source gap 只能有一个关闭义务。"))
            dimensions["source_alignment"] = "FAIL"
        else:
            obligation_gap_ids.add(str(gap_id))

        resolution = obligation.get("resolution")
        assumption_id = obligation.get("assumption_id")
        reference_fact_id = obligation.get("reference_fact_id")
        if resolution == "assumption_required":
            if not nonempty(assumption_id) or assumption_id not in assumption_map:
                errors.append(issue("ASSUMPTION_OBLIGATION_UNRESOLVED", obligation_path + ".assumption_id", "来源缺口要求的 formal assumption 缺失。"))
                dimensions["source_alignment"] = "FAIL"
            else:
                obligation_assumption_counts[str(assumption_id)] += 1
                assumption_status = assumption_map[str(assumption_id)].get("status")
                if assumption_status == "resolved":
                    errors.append(
                        issue(
                            "ASSUMPTION_FALSELY_RESOLVED",
                            obligation_path + ".assumption_id",
                            "source gap 仍以 assumption_required 关闭，formal assumption 不得标为 resolved；应改为 confirmed，或用已批准补充来源关闭缺口。",
                        )
                    )
                    dimensions["source_alignment"] = "FAIL"
            if reference_fact_id is not None:
                errors.append(issue("ASSUMPTION_OBLIGATION_INVALID", obligation_path + ".reference_fact_id", "assumption_required 不得同时引用 supplemental reference。"))
                dimensions["source_alignment"] = "FAIL"
        elif resolution == "supplemental_source_confirmed":
            reference_fact = reference_fact_map.get(reference_fact_id)
            if (
                not nonempty(reference_fact_id)
                or reference_fact is None
                or reference_fact.get("approval_status") != "approved"
                or reference_fact_id in invalid_reference_fact_ids
            ):
                errors.append(issue("ASSUMPTION_OBLIGATION_UNRESOLVED", obligation_path + ".reference_fact_id", "来源缺口声称由补充来源关闭，但没有有效且已批准的 reference fact。"))
                dimensions["source_alignment"] = "FAIL"
            if assumption_id is not None:
                errors.append(issue("ASSUMPTION_OBLIGATION_INVALID", obligation_path + ".assumption_id", "supplemental_source_confirmed 不得同时绑定 formal assumption。"))
                dimensions["source_alignment"] = "FAIL"
        else:
            errors.append(issue("ASSUMPTION_OBLIGATION_INVALID", obligation_path + ".resolution", "resolution 必须是 assumption_required 或 supplemental_source_confirmed。"))
            dimensions["source_alignment"] = "FAIL"

    uncovered_gaps = sorted(set(source_gap_map) - obligation_gap_ids)
    if uncovered_gaps:
        errors.append(issue("SOURCE_GAP_UNRESOLVED", "assumption_obligations", "source gaps 缺少关闭义务：{}。".format(", ".join(uncovered_gaps))))
        dimensions["source_alignment"] = "FAIL"
    unregistered_assumptions = sorted(set(assumption_map) - set(obligation_assumption_counts))
    duplicate_assumptions = sorted(key for key, count in obligation_assumption_counts.items() if count != 1)
    if unregistered_assumptions:
        errors.append(issue("ASSUMPTION_WITHOUT_SOURCE_GAP", "shot_data.assumptions", "formal assumptions 必须由一个 workspace source gap 持有：{}。".format(", ".join(unregistered_assumptions))))
        dimensions["source_alignment"] = "FAIL"
    if duplicate_assumptions:
        errors.append(issue("ASSUMPTION_MULTI_BOUND", "assumption_obligations", "formal assumption 只能关闭一个 source gap：{}。".format(", ".join(duplicate_assumptions))))
        dimensions["source_alignment"] = "FAIL"

    inferences = workspace.get("director_inferences") if isinstance(workspace.get("director_inferences"), list) else []
    inference_map: Dict[str, Mapping[str, Any]] = {}
    inference_declared_shots: Dict[str, Set[str]] = {}
    for index, inference in enumerate(inferences):
        path = f"director_inferences[{index}]"
        if not isinstance(inference, dict):
            errors.append(issue("DIRECTOR_INFERENCE_INVALID", path, "director inference 必须是对象。"))
            dimensions["source_alignment"] = "FAIL"
            continue
        inference_id = inference.get("inference_id")
        if not nonempty(inference_id) or inference_id in inference_map:
            errors.append(issue("DIRECTOR_INFERENCE_INVALID", path + ".inference_id", "inference ID 为空或重复。"))
            dimensions["source_alignment"] = "FAIL"
            continue
        inference_map[inference_id] = inference
        if not nonempty(inference.get("scope")) or not nonempty(inference.get("statement")):
            errors.append(issue("DIRECTOR_INFERENCE_INVALID", path, "inference scope 与 statement 不得为空。"))
            dimensions["source_alignment"] = "FAIL"
        basis = inference.get("basis_fact_ids")
        references = inference.get("reference_fact_ids")
        if not string_list(basis, allow_empty=True) or not string_list(references, allow_empty=True):
            errors.append(issue("DIRECTOR_INFERENCE_INVALID", path, "inference basis/reference IDs 必须是字符串数组。"))
            dimensions["source_alignment"] = "FAIL"
            basis, references = [], []
        if not basis and not references:
            errors.append(issue("DIRECTOR_INFERENCE_BASIS_MISSING", path, "导演推断缺少来源 fact 或批准参考依据。"))
            dimensions["source_alignment"] = "FAIL"
        unknown_basis = [fact_id for fact_id in basis if fact_id not in fact_map]
        if unknown_basis:
            errors.append(issue("DIRECTOR_INFERENCE_BASIS_MISSING", path + ".basis_fact_ids", "导演推断引用不存在的 source fact。"))
            dimensions["source_alignment"] = "FAIL"
        unknown_references = [fact_id for fact_id in references if fact_id not in reference_fact_map]
        if unknown_references:
            errors.append(issue("DIRECTOR_INFERENCE_REFERENCE_UNKNOWN", path + ".reference_fact_ids", "导演推断引用未登记的 supplemental reference fact。"))
            dimensions["source_alignment"] = "FAIL"
        invalid_references = [fact_id for fact_id in references if fact_id in invalid_reference_fact_ids]
        if invalid_references:
            errors.append(issue("DIRECTOR_INFERENCE_REFERENCE_HASH_INVALID", path + ".reference_fact_ids", "导演推断引用的 supplemental reference fact 哈希或 provenance 无效。"))
            dimensions["source_alignment"] = "FAIL"
        unapproved_references = [
            fact_id
            for fact_id in references
            if fact_id in reference_fact_map and reference_fact_map[fact_id].get("approval_status") != "approved"
        ]
        if unapproved_references:
            errors.append(issue("DIRECTOR_INFERENCE_REFERENCE_NOT_APPROVED", path + ".reference_fact_ids", "导演推断只能引用 approval_status=approved 的 supplemental reference facts。"))
            dimensions["source_alignment"] = "FAIL"
        conflicts = inference.get("conflicts_with_fact_ids")
        if not string_list(conflicts, allow_empty=True):
            errors.append(issue("DIRECTOR_INFERENCE_INVALID", path + ".conflicts_with_fact_ids", "冲突 ID 必须是字符串数组。"))
            dimensions["source_alignment"] = "FAIL"
        elif conflicts:
            errors.append(issue("DIRECTOR_INFERENCE_SOURCE_CONFLICT", path + ".conflicts_with_fact_ids", "导演推断与来源事实冲突。"))
            dimensions["source_alignment"] = "FAIL"
        if inference.get("reversibility") not in INFERENCE_REVERSIBILITY or inference.get("status") not in INFERENCE_STATUSES:
            errors.append(issue("DIRECTOR_INFERENCE_INVALID", path, "inference reversibility 或 status 无效。"))
            dimensions["source_alignment"] = "FAIL"
        shot_refs = inference.get("shot_refs")
        if not string_list(shot_refs, allow_empty=True):
            errors.append(issue("DIRECTOR_INFERENCE_INVALID", path + ".shot_refs", "inference shot_refs 必须是字符串数组。"))
            dimensions["source_alignment"] = "FAIL"
            shot_refs = []
        unknown_shot_refs = [shot_id for shot_id in shot_refs if shot_id not in shot_map]
        if unknown_shot_refs:
            errors.append(issue("DIRECTOR_INFERENCE_SHOT_UNKNOWN", path + ".shot_refs", "inference 引用不存在的正式镜头。"))
            dimensions["source_alignment"] = "FAIL"
        inference_declared_shots[str(inference_id)] = set(shot_refs)

    bindings = workspace.get("shot_bindings") if isinstance(workspace.get("shot_bindings"), list) else []
    binding_map: Dict[str, Mapping[str, Any]] = {}
    fact_realizations: Dict[str, List[Tuple[str, Mapping[str, Any]]]] = defaultdict(list)
    inference_bound_shots: Dict[str, Set[str]] = defaultdict(set)
    for index, binding in enumerate(bindings):
        path = f"shot_bindings[{index}]"
        if not isinstance(binding, dict):
            errors.append(issue("SHOT_BINDING_INVALID", path, "shot binding 必须是对象。"))
            dimensions["source_alignment"] = "FAIL"
            continue
        shot_id = binding.get("shot_id")
        if shot_id not in shot_map or shot_id in binding_map:
            errors.append(issue("SHOT_BINDING_INVALID", path + ".shot_id", "shot binding 引用不存在镜头或重复。"))
            dimensions["source_alignment"] = "FAIL"
            continue
        binding_map[shot_id] = binding
        shot = shot_map[shot_id]
        passage_ids = binding.get("passage_ids")
        if not string_list(passage_ids):
            errors.append(issue("SHOT_SOURCE_BINDING_EMPTY", path + ".passage_ids", "正式镜头必须绑定至少一个权威 passage。"))
            dimensions["source_alignment"] = "FAIL"
            passage_ids = []
        for passage_id in passage_ids:
            passage = passage_map.get(passage_id)
            if passage is None:
                errors.append(issue("SHOT_SOURCE_BINDING_UNKNOWN", path + ".passage_ids", f"镜头引用不存在 passage {passage_id}。"))
                dimensions["source_alignment"] = "FAIL"
                continue
            if passage.get("coverage_status") != "covered" or shot_id not in passage_shot_refs.get(passage_id, set()):
                errors.append(issue("SHOT_SOURCE_BINDING_DIVERGED", path + ".passage_ids", "镜头与 passage 的双向 coverage 绑定不一致。"))
                dimensions["source_alignment"] = "FAIL"
            scope_id = passage.get("scope_id")
            if scope_id != "GLOBAL" and scope_id != shot.get("scene_id"):
                errors.append(issue("SOURCE_SCENE_RANGE_MISMATCH", path + ".passage_ids", "场内 passage 绑定到错误场景。"))
                dimensions["source_alignment"] = "FAIL"
        inference_ids = binding.get("director_inference_ids")
        if not string_list(inference_ids, allow_empty=True):
            errors.append(issue("SHOT_BINDING_INVALID", path + ".director_inference_ids", "director_inference_ids 必须是字符串数组。"))
            dimensions["source_alignment"] = "FAIL"
            inference_ids = []
        unknown_inferences = [item for item in inference_ids if item not in inference_map]
        if unknown_inferences:
            errors.append(issue("DIRECTOR_INFERENCE_BASIS_MISSING", path + ".director_inference_ids", "镜头引用不存在的 director inference。"))
            dimensions["source_alignment"] = "FAIL"
        for inference_id in inference_ids:
            inference = inference_map.get(inference_id)
            if inference is None:
                continue
            inference_bound_shots[inference_id].add(str(shot_id))
            if inference.get("status") != "approved":
                errors.append(
                    issue(
                        "DIRECTOR_INFERENCE_NOT_APPROVED",
                        path + ".director_inference_ids",
                        "正式镜头只能引用 status=approved 的 director inference。",
                    )
                )
                dimensions["source_alignment"] = "FAIL"
            if shot_id not in inference_declared_shots.get(inference_id, set()):
                errors.append(
                    issue(
                        "DIRECTOR_INFERENCE_SHOT_BINDING_DIVERGED",
                        path + ".director_inference_ids",
                        "shot binding 与 inference.shot_refs 的双向引用不一致。",
                    )
                )
                dimensions["source_alignment"] = "FAIL"
        realizations = binding.get("fact_realizations")
        if not isinstance(realizations, list):
            errors.append(issue("FACT_REALIZATIONS_INVALID", path + ".fact_realizations", "fact_realizations 必须是数组。"))
            dimensions["source_alignment"] = "FAIL"
            realizations = []
        execution_text = normalize_text(shot.get("execution_text"))
        staging = shot.get("staging") if isinstance(shot.get("staging"), dict) else {}
        staging_subjects = staging.get("subjects") if isinstance(staging.get("subjects"), list) else []
        visible_subjects = staging.get("visible_subjects") if isinstance(staging.get("visible_subjects"), list) else []
        staging_offscreen = staging.get("offscreen_subjects") if isinstance(staging.get("offscreen_subjects"), list) else []
        binding_offscreen = binding.get("offscreen_subjects") if isinstance(binding.get("offscreen_subjects"), list) else []
        if {normalized_identifier(item) for item in staging_offscreen} != {
            normalized_identifier(item) for item in binding_offscreen
        }:
            errors.append(
                issue(
                    "SHOT_BINDING_OFFSCREEN_DIVERGED",
                    path + ".offscreen_subjects",
                    "shot binding 与正式 staging.offscreen_subjects 不一致。",
                )
            )
            dimensions["source_alignment"] = "FAIL"
        available_subjects = [str(item) for item in staging_subjects + visible_subjects + staging_offscreen]
        for realization_index, realization in enumerate(realizations):
            realization_path = f"{path}.fact_realizations[{realization_index}]"
            if not isinstance(realization, dict):
                errors.append(issue("FACT_REALIZATION_INVALID", realization_path, "fact realization 必须是对象。"))
                dimensions["source_alignment"] = "FAIL"
                continue
            fact_id = realization.get("fact_id")
            fact = fact_map.get(fact_id)
            if fact is None:
                errors.append(issue("FACT_REALIZATION_INVALID", realization_path + ".fact_id", "realization 引用不存在 fact。"))
                dimensions["source_alignment"] = "FAIL"
                continue
            if fact.get("passage_id") not in passage_ids:
                errors.append(issue("FACT_REALIZATION_INVALID", realization_path + ".fact_id", "realized fact 不属于本镜绑定 passage。"))
                dimensions["source_alignment"] = "FAIL"
            fact_realizations[fact_id].append((shot_id, realization))
            if realization.get("mode") not in REALIZATION_MODES:
                errors.append(issue("FACT_REALIZATION_INVALID", realization_path + ".mode", "realization mode 无效。"))
                dimensions["source_alignment"] = "FAIL"
            span = normalize_text(realization.get("execution_span"))
            if not span or span not in execution_text:
                code = "SOURCE_FACT_REALIZATION_MISSING"
                if fact.get("kind") == "negation":
                    code = "SOURCE_NEGATION_DROPPED"
                errors.append(issue(code, realization_path + ".execution_span", "事实实现片段未逐字出现在 execution_text。"))
                dimensions["source_alignment"] = "FAIL"
            owners = realization.get("subject_owners")
            if not string_list(owners, allow_empty=True):
                errors.append(issue("FACT_REALIZATION_INVALID", realization_path + ".subject_owners", "subject_owners 必须是字符串数组。"))
                dimensions["source_alignment"] = "FAIL"
                owners = []
            source_subjects = fact.get("subjects") if isinstance(fact.get("subjects"), list) else []
            missing_subjects = [
                subject
                for subject in source_subjects
                if not any(owner_matches_subject(subject, owner) for owner in owners)
            ]
            unavailable_owners = [
                owner
                for owner in owners
                if not any(owner_matches_subject(subject, owner) for subject in available_subjects)
            ]
            if missing_subjects or unavailable_owners:
                errors.append(issue("SOURCE_EXECUTION_SUBJECT_DIVERGED", realization_path + ".subject_owners", "来源主体没有被当前镜 staging 或画外主体正确拥有。"))
                dimensions["source_alignment"] = "FAIL"
            if fact.get("kind") == "action_result":
                result_span = normalize_text(realization.get("result_span"))
                if not result_span or result_span not in execution_text:
                    errors.append(issue("SOURCE_ACTION_RESULT_MISSING", realization_path + ".result_span", "来源动作结果未在 execution_text 中落实。"))
                    dimensions["source_alignment"] = "FAIL"
            if fact.get("kind") == "negation":
                lowered = f" {span.lower()} "
                anchors = fact.get("anchors") if isinstance(fact.get("anchors"), list) else []
                if realization.get("polarity") != "negative" or not any(marker in lowered for marker in NEGATION_MARKERS) or any(anchor not in span for anchor in anchors):
                    errors.append(issue("SOURCE_NEGATION_DROPPED", realization_path, "来源否定被删除、改写为正向或未保留受保护锚点。"))
                    dimensions["source_alignment"] = "FAIL"

    for inference_id, declared_shots in inference_declared_shots.items():
        bound_shots = inference_bound_shots.get(inference_id, set())
        if declared_shots != bound_shots:
            errors.append(
                issue(
                    "DIRECTOR_INFERENCE_SHOT_BINDING_DIVERGED",
                    f"director_inferences[{inference_id}].shot_refs",
                    "inference.shot_refs 与 shot_bindings[].director_inference_ids 不一致。",
                )
            )
            dimensions["source_alignment"] = "FAIL"

    missing_bindings = sorted(set(shot_map) - set(binding_map))
    if missing_bindings:
        errors.append(issue("SHOT_SOURCE_BINDING_EMPTY", "shot_bindings", "正式镜头缺少 source binding：{}。".format(", ".join(missing_bindings))))
        dimensions["source_alignment"] = "FAIL"
    for passage_id, shot_refs in passage_shot_refs.items():
        bound_refs = {
            shot_id
            for shot_id, binding in binding_map.items()
            if passage_id in (binding.get("passage_ids") or [])
        }
        if shot_refs != bound_refs:
            errors.append(issue("SHOT_SOURCE_BINDING_DIVERGED", f"source.source_passages[{passage_id}].shot_refs", "passage 与 shot bindings 的反向引用不一致。"))
            dimensions["source_alignment"] = "FAIL"

    required_fact_ids = {
        fact_id
        for fact_id, fact in fact_map.items()
        if fact.get("importance") == "required"
        and passage_map.get(fact.get("passage_id"), {}).get("coverage_status") == "covered"
    }
    topology_fact_refs: Set[str] = set()
    scene_strategies = workspace.get("scene_strategies") if isinstance(workspace.get("scene_strategies"), list) else []
    for strategy_index, strategy in enumerate(scene_strategies):
        if not isinstance(strategy, dict):
            continue
        topology = strategy.get("topology") if isinstance(strategy.get("topology"), list) else []
        for topology_index, topology_unit in enumerate(topology):
            if not isinstance(topology_unit, dict):
                continue
            path = f"scene_strategies[{strategy_index}].topology[{topology_index}].source_fact_ids"
            source_fact_ids = topology_unit.get("source_fact_ids")
            if not string_list(source_fact_ids, allow_empty=True):
                errors.append(issue("TOPOLOGY_SOURCE_FACTS_INVALID", path, "topology source_fact_ids 必须是字符串数组。"))
                dimensions["source_alignment"] = "FAIL"
                continue
            topology_fact_refs.update(source_fact_ids)
            if any(fact_id not in fact_map for fact_id in source_fact_ids):
                errors.append(issue("TOPOLOGY_SOURCE_FACT_UNKNOWN", path, "topology 引用不存在的 source fact。"))
                dimensions["source_alignment"] = "FAIL"
    missing_topology_required = sorted(required_fact_ids - topology_fact_refs)
    if missing_topology_required:
        errors.append(issue("SOURCE_REQUIRED_FACT_TOPOLOGY_MISSING", "scene_strategies[].topology[].source_fact_ids", "required facts 未进入 Gate 2 topology：{}。".format(", ".join(missing_topology_required))))
        dimensions["source_alignment"] = "FAIL"
    missing_required = sorted(fact_id for fact_id in required_fact_ids if not fact_realizations.get(fact_id))
    if missing_required:
        errors.append(issue("SOURCE_FACT_REALIZATION_MISSING", "shot_bindings[].fact_realizations", "required facts 未实现：{}。".format(", ".join(missing_required))))
        dimensions["source_alignment"] = "FAIL"

    shot_order = {shot_id: index for index, shot_id in enumerate(shot_map)}
    for fact_id, fact in fact_map.items():
        if fact.get("kind") != "causal_link":
            continue
        cause_ids = fact.get("cause_fact_ids") or []
        effect_ids = fact.get("effect_fact_ids") or []
        cause_shots = [shot_order[shot_id] for cause_id in cause_ids for shot_id, _ in fact_realizations.get(cause_id, []) if shot_id in shot_order]
        effect_shots = [shot_order[shot_id] for effect_id in effect_ids for shot_id, _ in fact_realizations.get(effect_id, []) if shot_id in shot_order]
        if not cause_shots or not effect_shots or min(cause_shots) > max(effect_shots):
            errors.append(issue("SOURCE_CAUSAL_LINK_MISSING", f"source.source_facts[{fact_id}]", "因果事实缺少原因、结果或正确播放顺序。"))
            dimensions["source_alignment"] = "FAIL"

    if check_lock:
        review_lock = workspace.get("review_lock") if isinstance(workspace.get("review_lock"), dict) else {}
        hashes = expected_alignment_hashes(workspace, shot_data)
        if review_lock.get("source_model_hash") != hashes["source_model_hash"]:
            errors.append(issue("SOURCE_ALIGNMENT_INVALIDATED", "review_lock.source_model_hash", "来源模型已变化，必须重新审阅 alignment。"))
            dimensions["source_alignment"] = "FAIL"
        if review_lock.get("execution_hash") != hashes["execution_hash"]:
            errors.append(issue("EXECUTION_LOCK_INVALIDATED", "review_lock.execution_hash", "正式摄影、调度、声音、剪辑、连续性、时长或假设已变化，必须重新审阅 alignment。"))
            dimensions["source_alignment"] = "FAIL"
        if review_lock.get("alignment_hash") != hashes["alignment_hash"]:
            errors.append(issue("SOURCE_ALIGNMENT_INVALIDATED", "review_lock.alignment_hash", "镜头语义实现已变化，必须重新审阅 alignment。"))
            dimensions["source_alignment"] = "FAIL"
        if review_lock.get("alignment_status") != "passed" or not nonempty(review_lock.get("alignment_note")):
            errors.append(issue("SOURCE_ALIGNMENT_INVALIDATED", "review_lock.alignment_status", "alignment 未确认通过或缺少说明。"))
            dimensions["source_alignment"] = "FAIL"

    metrics = {
        "source_line_count": len(source_lines),
        "nonempty_source_line_count": sum(1 for line in source_lines if line.strip()),
        "source_unit_count": len(units),
        "source_unit_role_counts": dict(unit_role_counts),
        "source_passage_count": len(passages),
        "coverage_status_counts": dict(coverage_counts),
        "source_fact_count": len(facts),
        "required_fact_count": len(required_fact_ids),
        "realized_required_fact_count": len(required_fact_ids - set(missing_required)),
        "shot_binding_count": len(binding_map),
        "director_inference_count": len(inferences),
        "supplemental_reference_fact_count": len(supplemental_facts),
        "source_gap_count": len(source_gaps),
        "assumption_obligation_count": len(obligations),
        "formal_assumption_count": len(formal_assumptions),
        "approved_supplemental_reference_fact_count": sum(
            1 for item in supplemental_facts if isinstance(item, dict) and item.get("approval_status") == "approved"
        ),
    }
    return _alignment_report(errors, warnings, dimensions, metrics)


def _alignment_report(
    errors: List[Dict[str, str]],
    warnings: List[Dict[str, str]],
    dimensions: Dict[str, str],
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "workspace_contract": WORKSPACE_CONTRACT,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "dimensions": dimensions,
        "metrics": metrics,
    }


def materialize_source_excerpts(
    workspace: Mapping[str, Any],
    shot_data: Mapping[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """Return a formal 3.1.3 copy with canonical scene and shot excerpts."""
    built = copy.deepcopy(dict(shot_data))
    warnings: List[Dict[str, str]] = []
    source = workspace.get("source") if isinstance(workspace.get("source"), dict) else {}
    source_lines = normalize_text(source.get("locked_text")).split("\n")
    units = source.get("source_units") if isinstance(source.get("source_units"), list) else []
    passages = source.get("source_passages") if isinstance(source.get("source_passages"), list) else []
    bindings = workspace.get("shot_bindings") if isinstance(workspace.get("shot_bindings"), list) else []
    unit_map = {
        unit.get("unit_id"): unit
        for unit in units
        if isinstance(unit, dict) and nonempty(unit.get("unit_id"))
    }
    passage_map = {
        passage.get("passage_id"): passage
        for passage in passages
        if isinstance(passage, dict) and nonempty(passage.get("passage_id"))
    }
    passage_order = sorted(
        passage_map,
        key=lambda passage_id: min(
            (
                int(unit_map[unit_id].get("line_start", 0))
                for unit_id in passage_map[passage_id].get("source_unit_ids", [])
                if unit_id in unit_map
            ),
            default=0,
        ),
    )
    order_index = {passage_id: index for index, passage_id in enumerate(passage_order)}
    passage_text = {
        passage_id: _passage_text(passage, unit_map, source_lines)
        for passage_id, passage in passage_map.items()
    }
    binding_map = {
        binding.get("shot_id"): binding
        for binding in bindings
        if isinstance(binding, dict) and nonempty(binding.get("shot_id"))
    }

    shots = built.get("shots") if isinstance(built.get("shots"), list) else []
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        binding = binding_map.get(shot.get("shot_id"), {})
        passage_ids = list(dict.fromkeys(binding.get("passage_ids", []) if isinstance(binding, dict) else []))
        passage_ids.sort(key=lambda item: order_index.get(item, 10**9))
        derived = "\n\n".join(passage_text.get(item, "") for item in passage_ids if passage_text.get(item, ""))
        shot["source_excerpt"] = derived

    scenes = built.get("scenes") if isinstance(built.get("scenes"), list) else []
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        scene_id = scene.get("scene_id")
        passage_ids = [
            passage_id
            for passage_id in passage_order
            if passage_map[passage_id].get("scope_id") == scene_id
            and passage_map[passage_id].get("coverage_status") == "covered"
        ]
        derived = "\n\n".join(passage_text.get(item, "") for item in passage_ids if passage_text.get(item, ""))
        scene["source_excerpt"] = derived
    return built, warnings
