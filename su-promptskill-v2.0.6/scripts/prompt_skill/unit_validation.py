"""su-promptskill internal module: unit timelines and validation."""

from __future__ import annotations

from . import compiler_prompt as _previous

globals().update({
    key: value
    for key, value in vars(_previous).items()
    if not key.startswith("__")
})

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Responsibility module behind scripts/prompt_delivery.py."

def _weighted_text_length(text: str) -> float:
    return sum(
        1.0
        if unicodedata.east_asian_width(character) in {"W", "F"}
        else 0.55
        for character in text
    )


def _estimated_visual_lines(text: str, column_width: int) -> int:
    capacity = max(1.0, float(column_width) * 0.82)
    return sum(
        max(1, math.ceil(_weighted_text_length(line) / capacity))
        for line in text.split("\n")
    )


def _estimated_row_height(text: str, column_width: int) -> Decimal:
    return Decimal(_estimated_visual_lines(text, column_width) * 16 + 8)


def _split_prompt_block_text(
    text: str, column_width: int = XLSX_PROMPT_WIDTH_MIN
) -> list[str]:
    if _estimated_row_height(text, column_width) <= XLSX_ROW_HEIGHT_LIMIT:
        return [text]
    protected_pattern = re.compile(
        r"<<<.*?>>>|\{.*?\}|（[^（）]*）|\([^()]*\)|“[^”]*”|‘[^’]*’|"
        r"Cut\s+\d+(?:｜|\s*:)[^\n]*",
        flags=re.DOTALL,
    )
    pieces: list[str] = []
    cursor = 0
    for match in protected_pattern.finditer(text):
        if match.start() > cursor:
            pieces.extend(
                piece
                for piece in re.findall(
                    r"[^。！？；，,\n]+[。！？；，,]?|\n",
                    text[cursor : match.start()],
                )
                if piece
            )
        pieces.append(match.group(0))
        cursor = match.end()
    if cursor < len(text):
        pieces.extend(
            piece
            for piece in re.findall(
                r"[^。！？；，,\n]+[。！？；，,]?|\n",
                text[cursor:],
            )
            if piece
        )
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if _estimated_row_height(piece, column_width) > XLSX_ROW_HEIGHT_LIMIT:
            raise DeliveryError(
                "Prompt block contains an indivisible asset tag, quotation, "
                "Cut title, or paired-bracket span exceeding the XLSX row budget"
            )
        candidate = current + piece
        if (
            current
            and _estimated_row_height(candidate, column_width)
            > XLSX_ROW_HEIGHT_LIMIT
        ):
            chunks.append(current.strip("\n"))
            current = piece.lstrip("\n")
        else:
            current = candidate
    if current.strip("\n"):
        chunks.append(current.strip("\n"))
    return chunks or [text]


def _prompt_blocks(
    prompt_text: str,
    timeline: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    timeline_by_label = {
        str(cut.get("cut_label")): cut for cut in timeline
    }
    blocks: list[dict[str, Any]] = []
    for raw_block in prompt_text.split("\n\n"):
        if not raw_block:
            continue
        kind = "section"
        source_ids: list[str] = []
        match = re.match(r"^(Cut\s+\d+)(?:｜|\s*:)", raw_block)
        if match:
            kind = "cut"
            cut = timeline_by_label.get(match.group(1), {})
            shot_id = _clean_text(cut.get("source_shot_id"))
            if shot_id:
                source_ids = [shot_id]
        elif raw_block.startswith(("【生成目标】", "【编辑目标】", "【延长目标】")):
            kind = "goal"
        elif raw_block.startswith("【参考素材职责】"):
            kind = "asset_responsibilities"
        elif raw_block.startswith("【主体、关系与场景】"):
            kind = "subjects_relationships_scene"
        elif raw_block.startswith("【镜头脚本】"):
            kind = "shot_script_header"
        elif raw_block.startswith("【声音与台词】"):
            kind = "sound_dialogue"
        elif raw_block.startswith("【保持一致】"):
            kind = "consistency"
        chunks = [raw_block]
        for chunk in chunks:
            blocks.append(
                {
                    "block_id": f"PB{len(blocks) + 1:03d}",
                    "kind": kind,
                    "source_shot_ids": copy.deepcopy(source_ids),
                    "text": chunk,
                }
            )
    normalized_prompt = "\n\n".join(block["text"] for block in blocks)
    return normalized_prompt, blocks


def _prompt_metadata_leaks(
    prompt_text: str, profile: Mapping[str, Any]
) -> list[str]:
    leaks: list[str] = []
    lower_prompt = prompt_text.casefold()
    for forbidden in (
        _clean_text(profile.get("profile_id")),
        _clean_text(profile.get("model_name")),
        _clean_text(profile.get("model_id")),
        SKILL_NAME,
    ):
        if forbidden and forbidden.casefold() in lower_prompt:
            leaks.append(forbidden)
    self_description_patterns = (
        r"我是\s*(?:一个)?(?:ai|人工智能|模型)",
        r"作为\s*(?:一个)?(?:ai|人工智能|模型)",
        r"\bi\s+am\s+an?\s+ai\b",
        r"\bas\s+an?\s+ai\b",
    )
    if any(
        re.search(pattern, prompt_text, flags=re.IGNORECASE)
        for pattern in self_description_patterns
    ):
        leaks.append("self-description")
    if profile.get("prompt_adapter_id") == "seedance-2.5-structured-zh-v1":
        parameter_patterns = (
            r"总时长\s*[：:]",
            r"\b(?:ratio|duration|resolution|fps|output_format)\s*[=:：]",
            r"输出(?:画幅|分辨率|帧率)\s*[：:]",
        )
        for pattern in parameter_patterns:
            if re.search(pattern, prompt_text, flags=re.IGNORECASE):
                leaks.append(pattern)
    if re.search(
        r"\basset(?:[\s_-]*id)?[\s_:-]*[a-z0-9-]{6,}\b",
        prompt_text,
        flags=re.IGNORECASE,
    ):
        leaks.append("raw Asset ID")
    return _unique_strings(leaks)


def _cut_prompt_block(prompt_text: str, cut_label: str) -> str:
    markers = (f"{cut_label}｜", f"{cut_label} :")
    starts = [prompt_text.find(marker) for marker in markers]
    starts = [value for value in starts if value >= 0]
    start = min(starts) if starts else -1
    if start < 0:
        return ""
    next_positions = [
        prompt_text.find(marker, start + len(cut_label) + 1)
        for label in CUT_LABELS
        for marker in (f"\n{label}｜", f"\n{label} :")
    ]
    next_positions.extend(
        prompt_text.find(f"\n\n{header}", start + len(cut_label) + 1)
        for header in ("【声音与台词】", "【保持一致】")
    )
    next_positions = [position for position in next_positions if position >= 0]
    end = min(next_positions) if next_positions else len(prompt_text)
    return prompt_text[start:end]


def _normalized_occurrences(text: str, fact: Any) -> int:
    normalized_text = _normalized_fact_text(text)
    normalized_fact = _normalized_fact_text(fact)
    if not normalized_fact:
        return 0
    return normalized_text.count(normalized_fact)


def _prompt_redundancy_findings(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    prompt_text: str,
) -> list[str]:
    findings: list[str] = []
    sound_section = ""
    sound_header = "【声音与台词】"
    if sound_header in prompt_text:
        sound_section = prompt_text.split(sound_header, 1)[1]
        if "【保持一致】" in sound_section:
            sound_section = sound_section.split("【保持一致】", 1)[0]
    normalized_sound_section = _normalized_fact_text(sound_section)
    for shot, cut in zip(shots, timeline):
        block = _cut_prompt_block(prompt_text, str(cut["cut_label"]))
        sound_label_count = QUOTED_TEXT_RE.sub("", block).count("声音：")
        if sound_label_count > 1:
            findings.append(
                f"{cut['cut_label']} 顶层声音说明重复 {sound_label_count} 次"
            )
        for item in shot.get("audio", []):
            normalized_audio = _normalized_fact_text(
                _render_descriptive_value(item)
            )
            if normalized_audio and normalized_audio in normalized_sound_section:
                findings.append(
                    f"{cut['cut_label']} 声音事实在声音区块复抄："
                    f"{_preserve_text(_render_descriptive_value(item))}"
                )
        camera = shot.get("camera", {})
        camera = camera if isinstance(camera, dict) else {}
        start_frame = _preserve_text(
            _render_descriptive_value(camera.get("start_frame"))
        )
        end_frame = _preserve_text(
            _render_descriptive_value(camera.get("end_frame"))
        )
        facts: list[tuple[str, Any]] = [
            ("camera.position", camera.get("position")),
            ("start_frame", start_frame),
        ]
        if _normalized_fact_text(end_frame) != _normalized_fact_text(start_frame):
            facts.append(("end_frame", end_frame))
        for label, fact in facts:
            count = _normalized_occurrences(block, fact)
            if fact and count > 1:
                findings.append(
                    f"{cut['cut_label']} {label} 重复 {count} 次"
                )
        rendered_dialogue = [
            _render_dialogue(item) for item in shot.get("dialogue", [])
        ]
        rendered_dialogue = [item for item in rendered_dialogue if item]
        for dialogue_text in _unique_strings(rendered_dialogue):
            expected_count = rendered_dialogue.count(dialogue_text)
            actual_count = block.count(dialogue_text)
            if actual_count != expected_count:
                findings.append(
                    f"{cut['cut_label']} dialogue 数量应为 {expected_count}，实际为 {actual_count}"
                )
        literal_dialogue = _dialogue_texts(shot.get("dialogue", []))
        for dialogue_text in _unique_strings(literal_dialogue):
            expected_count = literal_dialogue.count(dialogue_text)
            actual_count = block.count(dialogue_text)
            if actual_count != expected_count:
                findings.append(
                    f"{cut['cut_label']} dialogue literal 数量应为 "
                    f"{expected_count}，实际为 {actual_count}"
                )
        allowed_dialogue_clauses = {
            _normalized_fact_text(dialogue_text): rendered_dialogue.count(
                dialogue_text
            )
            for dialogue_text in _unique_strings(rendered_dialogue)
        }
        seen_dialogue_clauses: dict[str, int] = {}
        seen_clauses: set[str] = set()
        for clause in re.split(r"(?<=[。！？；])(?![”’])|\n+", block):
            normalized_clause = _normalized_fact_text(clause)
            if len(normalized_clause) < 8:
                continue
            if normalized_clause in allowed_dialogue_clauses:
                seen_dialogue_clauses[normalized_clause] = (
                    seen_dialogue_clauses.get(normalized_clause, 0) + 1
                )
                if (
                    seen_dialogue_clauses[normalized_clause]
                    <= allowed_dialogue_clauses[normalized_clause]
                ):
                    continue
            if normalized_clause in seen_clauses:
                findings.append(
                    f"{cut['cut_label']} 含重复事实句：{clause.strip()}"
                )
                break
            seen_clauses.add(normalized_clause)

    return _unique_strings(findings)


def _official_prompt_structure_findings(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    prompt_text: str,
    profile: Mapping[str, Any],
    generation: Mapping[str, Any],
) -> list[str]:
    if profile.get("prompt_adapter_id") != "seedance-2.5-structured-zh-v1":
        return []
    mode = _clean_text(generation.get("mode"))
    expected_goal = {
        "edit": "【编辑目标】",
        "extend": "【延长目标】",
    }.get(mode, "【生成目标】")
    findings: list[str] = []
    required_headers = [
        expected_goal,
        "【主体、关系与场景】",
        "【镜头脚本】",
        "【保持一致】",
    ]
    positions = [prompt_text.find(header) for header in required_headers]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        findings.append("官方正文主结构缺失或顺序错误")
    blocks = prompt_text.split("\n\n")
    asset_lines = _asset_responsibility_lines(generation)
    has_asset_header = "【参考素材职责】" in prompt_text
    if bool(asset_lines) != has_asset_header:
        findings.append("参考素材职责区块未按当前单元映射条件出现")
    has_sound_header = "【声音与台词】" in prompt_text
    if not has_sound_header:
        findings.append("声音与台词区块必须稳定存在")
    if not blocks or not blocks[-1].startswith("【保持一致】"):
        findings.append("保持一致必须是正文最后区块")
    if any(
        internal_name in prompt_text
        for internal_name in (
            "asset_binding",
            "consistency_contract",
        )
    ):
        findings.append("正文泄漏内部合同字段名")
    if mode in {"t2v", "i2v", "v2v", "r2v", "flf2v"}:
        for shot, cut in zip(shots, timeline):
            block = _cut_prompt_block(prompt_text, str(cut["cut_label"]))
            expected_change = _shot_main_state_change(shot)
            if expected_change and block.count("主要状态变化：") != 1:
                findings.append(
                    f"{cut['cut_label']} 必须恰好声明一个主要状态变化"
                )
        if "构图：" in prompt_text or "画面内容：" in prompt_text:
            findings.append("普通生成不得退回逐 Cut 字段堆叠格式")
    for cut in timeline:
        if f"{cut['cut_label']}｜" not in prompt_text:
            findings.append(f"{cut['cut_label']} 必须使用竖线分隔时间表达")
    return _unique_strings(findings)


def _cut_source_coverage(
    shot: Mapping[str, Any],
    block: str,
    generation: Mapping[str, Any],
) -> tuple[bool, bool]:
    composition, _, _ = _camera_prompt_fields(
        shot.get("camera", {}),
        include_movement=not bool(generation.get("global_reference_section")),
    )
    expected_content = _shot_prompt_content(
        shot,
        [],
        generation,
        include_reference_roles=not bool(
            generation.get("global_reference_section")
        ),
    )
    required_tokens = [
        token
        for token in (composition, expected_content)
        if token
    ]
    required_tokens.extend(_dialogue_texts(shot.get("dialogue", [])))
    return all(token in block for token in required_tokens), True


def _build_timeline(
    shots: Sequence[Mapping[str, Any]],
    emotion_map: Mapping[str, Sequence[Mapping[str, str]]],
) -> tuple[list[dict[str, Any]], int | float | None]:
    known_durations: list[Decimal] = []
    all_known = True
    for shot in shots:
        try:
            duration = _duration_decimal(shot.get("duration_seconds"))
        except InvalidOperation:
            duration = None
        if duration is None:
            all_known = False
        else:
            known_durations.append(duration)

    timeline: list[dict[str, Any]] = []
    offset = Decimal("0")
    for index, shot in enumerate(shots):
        duration = (
            _duration_decimal(shot.get("duration_seconds")) if all_known else None
        )
        start = offset if duration is not None else None
        end = offset + duration if duration is not None else None
        if end is not None:
            offset = end
        timeline.append(
            {
                "cut_index": index + 1,
                "cut_label": CUT_LABELS[index],
                "source_shot_id": shot["source_shot_id"],
                "source_order": shot["source_order"],
                "start_seconds": _json_number(start),
                "end_seconds": _json_number(end),
                "duration_seconds": _json_number(duration),
                "source_shot_hash": shot["source_shot_hash"],
                "compiler_provenance": copy.deepcopy(shot["field_hashes"]),
                "emotion_visualization": copy.deepcopy(
                    emotion_map.get(str(shot["source_shot_id"]), [])
                ),
            }
        )
    return timeline, _json_number(offset) if all_known else None


def _unit_prompt_validation(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    prompt_text: str,
    profile: Mapping[str, Any],
    generation: Mapping[str, Any],
    diagnostic_codes: Sequence[str],
) -> dict[str, Any]:
    dialogue_exact = True
    reference_tags_exact = True
    source_visual_action_covered = True
    continuity_covered = True
    all_known_tags = _all_generation_reference_tags(generation)
    for shot, cut in zip(shots, timeline):
        block = _cut_prompt_block(prompt_text, str(cut["cut_label"]))
        dialogue_texts = _dialogue_texts(shot["dialogue"])
        if any(
            block.count(text) != dialogue_texts.count(text)
            for text in _unique_strings(dialogue_texts)
        ):
            dialogue_exact = False
        expected_tags = {
            str(item["tag"])
            for item in _reference_roles_for_shot(
                generation, str(shot["source_shot_id"])
            )
        }
        if not _global_reference_section(profile):
            actual_tags = set(
                _reference_tags(block, profile, all_known_tags)
            )
            if actual_tags != expected_tags:
                reference_tags_exact = False
        visual_covered, cut_continuity_covered = _cut_source_coverage(
            shot, block, generation
        )
        source_visual_action_covered &= visual_covered
        continuity_covered &= cut_continuity_covered
    if _global_reference_section(profile):
        actual_global_tags = set(
            _reference_tags(prompt_text, profile, all_known_tags)
        )
        reference_tags_exact = actual_global_tags == set(all_known_tags)
    metadata_absent = not _prompt_metadata_leaks(prompt_text, profile)
    source_anti_slop_terms = {
        term
        for shot in shots
        for term in shot.get("source_anti_slop_terms", [])
    }
    prompt_anti_slop_terms = set(
        _anti_slop_terms_outside_quotes(prompt_text)
    )
    downstream_anti_slop_absent = not (
        prompt_anti_slop_terms - source_anti_slop_terms
    )
    prompt_redundancy_absent = not _prompt_redundancy_findings(
        shots, timeline, prompt_text
    )
    official_prompt_structure = not _official_prompt_structure_findings(
        shots, timeline, prompt_text, profile, generation
    )
    timed_timeline = all(cut["duration_seconds"] is not None for cut in timeline)
    chinese_codes = {
        "PROMPT_AUDIT_TEXT_LEAK",
        "PROMPT_CHINESE_ENUM_LEAK",
        "PROMPT_BARE_SUBJECT_FRAGMENT",
        "PROMPT_STATE_ROLE_DRIFT",
        "PROMPT_ADJACENT_LEXICAL_DUPLICATION",
    }
    has_error = (
        bool(diagnostic_codes)
        or not dialogue_exact
        or not metadata_absent
        or not reference_tags_exact
        or not downstream_anti_slop_absent
        or not prompt_redundancy_absent
        or not official_prompt_structure
        or not source_visual_action_covered
        or not continuity_covered
    )
    return {
        "status": "PARTIAL" if has_error else "PASS",
        "checks": {
            "source_mapping": len(shots) == len(timeline),
            "timed_timeline": timed_timeline if timed_timeline else None,
            "dialogue_exact": dialogue_exact,
            "dialogue_handling": "PROMPT_LITERAL",
            "reference_tags_exact": reference_tags_exact,
            "source_visual_action_covered": source_visual_action_covered,
            "continuity_covered": continuity_covered,
            "source_anti_slop": (
                "REVIEW_REQUIRED" if source_anti_slop_terms else "NONE"
            ),
            "downstream_anti_slop_absent": downstream_anti_slop_absent,
            "prompt_redundancy_absent": prompt_redundancy_absent,
            "official_prompt_structure": official_prompt_structure,
            "model_metadata_absent": metadata_absent,
            "chinese_semantic_checks": not bool(
                set(diagnostic_codes) & chinese_codes
            ),
            "semantic_compatibility": (
                "MODEL_ATTESTED" if len(shots) > 1 else "NOT_APPLICABLE"
            ),
            "emotion_visualization": "MODEL_REVIEW_REQUIRED",
        },
        "diagnostic_codes": list(diagnostic_codes),
    }


def _prompt_chinese_semantic_findings(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    prompt_text: str,
) -> dict[str, list[str]]:
    findings: dict[str, list[str]] = {}
    outside_dialogue = QUOTED_TEXT_RE.sub("", prompt_text)
    audit_terms = [
        term
        for term in (
            "【观看】",
            "【时长】",
            "【镜头动机】",
            "【制作风险】",
            "所有权：",
            "时间块：",
            "置信度：",
            "时长依据：",
        )
        if term in outside_dialogue
    ]
    if audit_terms:
        findings["PROMPT_AUDIT_TEXT_LEAK"] = audit_terms

    enum_values = sorted(
        set(
            re.findall(
                r"（(onscreen|on_screen|os|offscreen|off_screen|voiceover|vo)）",
                outside_dialogue,
            )
        )
    )
    if enum_values:
        findings["PROMPT_CHINESE_ENUM_LEAK"] = enum_values

    bare_subjects: list[str] = []
    for subject in _unique_strings(
        _preserve_text(_render_descriptive_value(item))
        for shot in shots
        for item in shot.get("subjects", [])
    ):
        if not subject:
            continue
        if re.search(
            rf"(?:^|[\n；。])\s*{re.escape(subject)}\s*[；。]",
            outside_dialogue,
        ):
            bare_subjects.append(subject)
    if bare_subjects:
        findings["PROMPT_BARE_SUBJECT_FRAGMENT"] = bare_subjects

    role_drifts: list[str] = []
    goal_text = prompt_text.split("【主体、关系与场景】", 1)[0]
    for shot, cut in zip(shots, timeline):
        block = _cut_prompt_block(prompt_text, str(cut["cut_label"]))
        cut_design = shot.get("cut_design", {})
        cut_design = cut_design if isinstance(cut_design, dict) else {}
        entry = _clean_text(cut_design.get("entry_trigger"))
        exit_text = _clean_text(cut_design.get("exit_trigger"))
        if entry and re.search(r"切入|切到|切回|承接|动作切|反应切", entry):
            if entry in block:
                role_drifts.append(f"{cut['cut_label']} 使用 edit.entry")
        if exit_text and f"主要状态变化：{exit_text}" in block:
            role_drifts.append(f"{cut['cut_label']} 使用 edit.exit")
    if shots:
        first_design = shots[0].get("cut_design", {})
        first_design = first_design if isinstance(first_design, dict) else {}
        first_exit = _clean_text(first_design.get("exit_trigger"))
        if first_exit and first_exit in goal_text:
            role_drifts.append("单元目标使用第一镜 edit.exit")
    if role_drifts:
        findings["PROMPT_STATE_ROLE_DRIFT"] = role_drifts

    adjacent_repetitions = [
        pattern
        for pattern in (
            "镜头固定，固定",
            "镜头固定；固定",
            "摄影机位于位于",
            "停止停止",
        )
        if pattern in outside_dialogue
    ]
    if adjacent_repetitions:
        findings["PROMPT_ADJACENT_LEXICAL_DUPLICATION"] = adjacent_repetitions
    return findings


def _status_from_issues(
    issues: Sequence[Mapping[str, Any]],
    prompt_units: Sequence[Mapping[str, Any]],
    *,
    source_global_blocked: bool,
) -> str:
    errors = [issue for issue in issues if issue.get("severity") == "ERROR"]
    warnings = [issue for issue in issues if issue.get("severity") == "WARN"]
    issue_codes = {str(issue.get("code")) for issue in errors}
    integrity_failure_codes = {
        "COMPILER_INPUTS_INVALID",
        "OUTPUT_CONTRACT_INVALID",
        "OUTPUT_HASH_MISMATCH",
        "PLAN_RECOMPILATION_MISMATCH",
        "PROMPT_REDUNDANCY_DETECTED",
        "PROMPT_RECOMPILE_MISMATCH",
        "SOURCE_PROVENANCE_MISMATCH",
        "TOP_LEVEL_VALIDATION_MISMATCH",
        "UNIT_VALIDATION_LEDGER_MISMATCH",
        "VALIDATION_STATUS_MISMATCH",
    }
    if source_global_blocked or issue_codes & integrity_failure_codes:
        return "FAIL"
    if errors:
        has_executable_prompt = any(
            isinstance(unit, dict)
            and bool(_clean_text(unit.get("prompt_text")))
            for unit in prompt_units
        )
        return "PARTIAL" if has_executable_prompt else "FAIL"
    if warnings:
        return "WARN"
    return "PASS"


def _validation_summary(
    normalized: Mapping[str, Any],
    prompt_units: Sequence[Mapping[str, Any]],
    issues: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    known_duration = Decimal("0")
    for shot in normalized.get("shots", []):
        try:
            duration = _duration_decimal(shot.get("duration_seconds"))
        except InvalidOperation:
            duration = None
        if duration is not None:
            known_duration += duration
    return {
        "source_shots": len(normalized.get("shots", [])),
        "prompt_units": len(prompt_units),
        "cuts": sum(len(unit.get("timeline", [])) for unit in prompt_units),
        "grouped_units": sum(
            1 for unit in prompt_units if len(unit.get("source_shot_ids", [])) > 1
        ),
        "standalone_units": sum(
            1 for unit in prompt_units if len(unit.get("source_shot_ids", [])) == 1
        ),
        "known_source_duration_seconds": _json_number(known_duration),
        "errors": sum(1 for issue in issues if issue.get("severity") == "ERROR"),
        "warnings": sum(1 for issue in issues if issue.get("severity") == "WARN"),
    }


def _validation_object(
    normalized: Mapping[str, Any],
    prompt_units: Sequence[Mapping[str, Any]],
    issues: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    issue_codes = {str(issue.get("code")) for issue in issues}
    return {
        "status": _status_from_issues(
            issues,
            prompt_units,
            source_global_blocked=bool(
                normalized.get("source_global_blocked", False)
            ),
        ),
        "errors": [
            dict(issue) for issue in issues if issue.get("severity") == "ERROR"
        ],
        "warnings": [
            dict(issue) for issue in issues if issue.get("severity") == "WARN"
        ],
        "summary": _validation_summary(normalized, prompt_units, issues),
        "deterministic_checks": {
            "source_read_only": True,
            "source_order": "SHOT_ORDER_INVALID" not in issue_codes,
            "source_hash": not bool(
                issue_codes
                & {
                    "SOURCE_HASH_INVALID",
                    "SOURCE_HASH_MISMATCH",
                }
            ),
            "source_shot_coverage": not bool(
                issue_codes
                & {
                    "SOURCE_SHOT_COVERAGE_INVALID",
                    "CUT_SOURCE_MISMATCH",
                }
            ),
            "group_duration": "GROUP_DURATION_INVALID" not in issue_codes,
            "cut_mapping": not bool(
                issue_codes
                & {
                    "CUT_COUNT_MISMATCH",
                    "CUT_SOURCE_MISMATCH",
                    "CUT_SOURCE_HASH_MISMATCH",
                }
            ),
            "cut_timeline": "CUT_TIMELINE_INVALID" not in issue_codes,
            "prompt_metadata_absent": (
                "PROMPT_MODEL_METADATA_LEAK" not in issue_codes
            ),
            "mode_gate": not bool(
                issue_codes
                & {
                    "MODE_GATE_BLOCKED",
                    "MODE_UNIT_REFERENCE_INVALID",
                    "GENERATION_CONTRACT_INVALID",
                }
            ),
            "reference_scope": not any(
                code.startswith("REFERENCE_") for code in issue_codes
            ),
            "source_visual_action_coverage": (
                "SOURCE_VISUAL_ACTION_MISSING" not in issue_codes
            ),
            "continuity_coverage": (
                "CONTINUITY_COVERAGE_MISSING" not in issue_codes
            ),
            "downstream_anti_slop_absent": not bool(
                issue_codes
                & {
                    "DOWNSTREAM_ANTI_SLOP",
                    "PROMPT_ANTI_SLOP_FAILED",
                }
            ),
            "prompt_redundancy_absent": (
                "PROMPT_REDUNDANCY_DETECTED" not in issue_codes
            ),
        },
        "chinese_semantic_checks": {
            "audit_text_absent": "PROMPT_AUDIT_TEXT_LEAK" not in issue_codes,
            "english_delivery_enum_absent": (
                "PROMPT_CHINESE_ENUM_LEAK" not in issue_codes
            ),
            "bare_subject_fragment_absent": (
                "PROMPT_BARE_SUBJECT_FRAGMENT" not in issue_codes
            ),
            "state_role_drift_absent": (
                "PROMPT_STATE_ROLE_DRIFT" not in issue_codes
            ),
            "adjacent_lexical_duplication_absent": (
                "PROMPT_ADJACENT_LEXICAL_DUPLICATION" not in issue_codes
            ),
            "goal_start_source": "camera.start_frame → start_state → blocking → visible_behavior",
            "goal_end_source": "end_state → camera.end_frame → blocking → delta_text → execution fallback",
        },
        "semantic_limitations": [
            (
                "场景、现实层、时间、来源可用性与边界状态证据由脚本重算；"
                "动作、因果、问答、表演保护与信息密度仍依赖逐边界模型审阅。"
            ),
            (
                "scene-global-dp-v1 在已锁定审阅与 Profile 容量内求唯一分区，"
                "不替代高阶语义审阅。"
            ),
            "情绪可视化是否新增事实依赖模型审阅。",
            "脚本不以词面相似度替代完整事实忠实性判断。",
            "anti-slop 仅做来源限定的字面 provenance 审计，不替代语义判断。",
        ],
    }


def _profile_limit(profile: Mapping[str, Any]) -> Decimal:
    duration = _duration_decimal(
        profile["capabilities"]["max_clip_duration_seconds"]
    )
    if duration is None:
        raise DeliveryError("Validated profile has no duration limit")
    return duration


def _build_unit(
    unit_index: int,
    planned: Mapping[str, Any],
    emotion_map: Mapping[str, Sequence[Mapping[str, str]]],
    profile: Mapping[str, Any],
    generation: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    shots = planned["shots"]
    unit_generation = _generation_for_unit(generation, shots)
    timeline, total_duration = _build_timeline(shots, emotion_map)
    prompt_text = _compile_prompt(
        shots, timeline, profile, unit_generation
    )
    prompt_text, prompt_blocks = _prompt_blocks(
        prompt_text, timeline, profile
    )
    unit_codes: list[str] = []
    model_limit = _profile_limit(profile)
    all_known_tags = _all_generation_reference_tags(unit_generation)
    redundancy_findings = _prompt_redundancy_findings(
        shots, timeline, prompt_text
    )
    if redundancy_findings:
        unit_codes.append("PROMPT_REDUNDANCY_DETECTED")
        issues.append(
            _issue(
                "PROMPT_REDUNDANCY_DETECTED",
                "ERROR",
                "prompt",
                f"prompt_units[{unit_index}].prompt_text",
                "；".join(redundancy_findings),
                ("prompt_delivery",),
            )
        )
    structure_findings = _official_prompt_structure_findings(
        shots, timeline, prompt_text, profile, unit_generation
    )
    if structure_findings:
        unit_codes.append("PROMPT_STRUCTURE_INVALID")
        issues.append(
            _issue(
                "PROMPT_STRUCTURE_INVALID",
                "ERROR",
                "prompt",
                f"prompt_units[{unit_index}].prompt_text",
                "；".join(structure_findings),
                ("prompt_delivery",),
            )
        )
    chinese_findings = _prompt_chinese_semantic_findings(
        shots, timeline, prompt_text
    )
    chinese_messages = {
        "PROMPT_AUDIT_TEXT_LEAK": "Prompt 正文泄漏审计字段",
        "PROMPT_CHINESE_ENUM_LEAK": "中文 Prompt 泄漏英文对白声位枚举",
        "PROMPT_BARE_SUBJECT_FRAGMENT": "Prompt 含孤立主体残片",
        "PROMPT_STATE_ROLE_DRIFT": "剪辑入口或出口被误作画面状态",
        "PROMPT_ADJACENT_LEXICAL_DUPLICATION": "Prompt 含相邻词语机械重复",
    }
    for code, details in chinese_findings.items():
        unit_codes.append(code)
        issues.append(
            _issue(
                code,
                "ERROR",
                "prompt",
                f"prompt_units[{unit_index}].prompt_text",
                f"{chinese_messages[code]}：{'、'.join(details)}。",
                ("prompt_delivery",),
            )
        )
    if _global_reference_section(profile):
        actual_global_tags = set(
            _reference_tags(prompt_text, profile, all_known_tags)
        )
        if actual_global_tags != set(all_known_tags):
            unit_codes.append("REFERENCE_TAG_MISMATCH")
            issues.append(
                _issue(
                    "REFERENCE_TAG_MISMATCH",
                    "ERROR",
                    "prompt",
                    f"prompt_units[{unit_index}].prompt_text",
                    "全局参考素材职责未逐字覆盖 role map 中的全部 tag。",
                    ("prompt_delivery",),
                )
            )

    for shot in shots:
        try:
            duration = _duration_decimal(shot.get("duration_seconds"))
        except InvalidOperation:
            duration = None
        if duration is None:
            unit_codes.append("DURATION_MISSING")
        elif duration > model_limit:
            unit_codes.append("MODEL_DURATION_EXCEEDED")
            issues.append(
                _issue(
                    "MODEL_DURATION_EXCEEDED",
                    "ERROR",
                    "unit",
                    f"prompt_units[{unit_index}]",
                    (
                        f"源镜 {shot['source_shot_id']} 的 {duration} 秒超过 "
                        f"Profile 上限 {model_limit} 秒；未缩短或拆分。"
                    ),
                    ("model_generation",),
                )
            )

    if (
        any(shot.get("dialogue") for shot in shots)
        and not profile["capabilities"].get("supports_dialogue")
    ):
        unit_codes.append("MODEL_DIALOGUE_UNSUPPORTED")
        issues.append(
            _issue(
                "MODEL_DIALOGUE_UNSUPPORTED",
                "ERROR",
                "unit",
                f"prompt_units[{unit_index}]",
                "来源含对白，但当前 Model Profile 声明不支持对白；对白仍原样保留。",
                ("model_generation",),
            )
        )

    leaks = _prompt_metadata_leaks(prompt_text, profile)
    if leaks:
        unit_codes.append("PROMPT_MODEL_METADATA_LEAK")
        issues.append(
            _issue(
                "PROMPT_MODEL_METADATA_LEAK",
                "ERROR",
                "prompt",
                f"prompt_units[{unit_index}].prompt_text",
                f"Prompt 正文包含模型或自我说明 metadata：{', '.join(leaks)}。",
                ("prompt_delivery",),
            )
        )

    source_anti_slop_terms = {
        term
        for shot in shots
        for term in shot.get("source_anti_slop_terms", [])
    }
    prompt_anti_slop_terms = set(
        _anti_slop_terms_outside_quotes(prompt_text)
    )
    downstream_anti_slop_terms = sorted(
        prompt_anti_slop_terms - source_anti_slop_terms
    )
    if downstream_anti_slop_terms:
        unit_codes.append("PROMPT_ANTI_SLOP_FAILED")
        issues.append(
            _issue(
                "PROMPT_ANTI_SLOP_FAILED",
                "ERROR",
                "prompt",
                f"prompt_units[{unit_index}].prompt_text",
                (
                    "正文含无法追溯到来源的空泛强化词："
                    f"{', '.join(downstream_anti_slop_terms)}。"
                ),
                ("prompt_delivery",),
            )
        )

    for shot, cut in zip(shots, timeline):
        block = _cut_prompt_block(prompt_text, str(cut["cut_label"]))
        dialogue_texts = _dialogue_texts(shot["dialogue"])
        dialogue_count_mismatch = {
            text: {
                "expected": dialogue_texts.count(text),
                "actual": block.count(text),
            }
            for text in _unique_strings(dialogue_texts)
            if block.count(text) != dialogue_texts.count(text)
        }
        if dialogue_count_mismatch:
            unit_codes.append("DIALOGUE_MISMATCH")
            issues.append(
                _issue(
                    "DIALOGUE_MISMATCH",
                    "ERROR",
                    "prompt",
                    f"prompt_units[{unit_index}].prompt_text",
                    f"Cut {cut['cut_label']} 未按来源次数逐字保留对白："
                    f"{dialogue_count_mismatch}。",
                    ("prompt_delivery",),
                )
            )
        cut_added_terms = sorted(
            set(_anti_slop_terms_outside_quotes(block))
            - set(shot.get("source_anti_slop_terms", []))
        )
        if cut_added_terms:
            unit_codes.append("PROMPT_ANTI_SLOP_FAILED")
            issues.append(
                _issue(
                    "PROMPT_ANTI_SLOP_FAILED",
                    "ERROR",
                    "prompt",
                    f"prompt_units[{unit_index}].prompt_text",
                    (
                        f"Cut {cut['cut_label']} 含无法追溯到对应源镜的"
                        f"空泛强化词：{', '.join(cut_added_terms)}。"
                    ),
                    ("prompt_delivery",),
                )
            )
            break
        expected_tags = {
            str(item["tag"])
            for item in _reference_roles_for_shot(
                unit_generation, str(shot["source_shot_id"])
            )
        }
        actual_tags = set(
            _reference_tags(block, profile, all_known_tags)
        )
        if not _global_reference_section(profile) and actual_tags != expected_tags:
            unit_codes.append("REFERENCE_TAG_MISMATCH")
            issues.append(
                _issue(
                    "REFERENCE_TAG_MISMATCH",
                    "ERROR",
                    "prompt",
                    f"prompt_units[{unit_index}].prompt_text",
                    (
                        f"Cut {cut['cut_label']} 的 reference tag 未与 role map "
                        "逐字一致。"
                    ),
                    ("prompt_delivery",),
                )
            )
        visual_covered, continuity_covered = _cut_source_coverage(
            shot, block, unit_generation
        )
        if not visual_covered:
            unit_codes.append("SOURCE_VISUAL_ACTION_MISSING")
            issues.append(
                _issue(
                    "SOURCE_VISUAL_ACTION_MISSING",
                    "ERROR",
                    "prompt",
                    f"prompt_units[{unit_index}].prompt_text",
                    (
                        f"Cut {cut['cut_label']} 未消费来源主要画面动作"
                        "或其忠实结构化等价内容。"
                    ),
                    ("prompt_delivery",),
                )
            )
        if not continuity_covered:
            unit_codes.append("CONTINUITY_COVERAGE_MISSING")
            issues.append(
                _issue(
                    "CONTINUITY_COVERAGE_MISSING",
                    "ERROR",
                    "prompt",
                    f"prompt_units[{unit_index}].prompt_text",
                    (
                        f"Cut {cut['cut_label']} 未消费来源连续性状态、"
                        "变化或目标终态。"
                    ),
                    ("prompt_delivery",),
                )
            )

    unit = {
        "prompt_unit_id": f"PU{unit_index + 1:03d}",
        "source_shot_ids": [shot["source_shot_id"] for shot in shots],
        "source_shot_hashes": [shot["source_shot_hash"] for shot in shots],
        "total_duration_seconds": total_duration,
        "grouping_reason": planned["grouping_reason"],
        "standalone_reason": planned["standalone_reason"],
        "semantic_compatibility": copy.deepcopy(
            planned["semantic_compatibility"]
        ),
        "partition_strategy": planned.get("partition_strategy"),
        "partition_entry_reason": planned.get("partition_entry_reason"),
        "boundary_evidence": copy.deepcopy(
            planned.get("boundary_evidence", [])
        ),
        "timeline": timeline,
        "prompt_blocks": prompt_blocks,
        "prompt_text": prompt_text,
        "prompt_validation": _unit_prompt_validation(
            shots,
            timeline,
            prompt_text,
            profile,
            unit_generation,
            _unique_strings(unit_codes),
        ),
    }
    return unit, issues


def _unique_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _deduplicate_dicts(
    values: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        key = canonical_json(value)
        if key not in seen:
            seen.add(key)
            result.append(copy.deepcopy(dict(value)))
    return result


def _normalized_source_snapshot(
    normalized: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "source": copy.deepcopy(normalized.get("source", {})),
        "shots": copy.deepcopy(normalized.get("shots", [])),
        "source_global_blocked": bool(
            normalized.get("source_global_blocked", False)
        ),
    }


def _compiler_inputs(
    normalized: Mapping[str, Any],
    decisions: Any,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_snapshot = _normalized_source_snapshot(normalized)
    decisions_snapshot = copy.deepcopy(decisions)
    runtime_profile = copy.deepcopy(profile)
    return {
        "contract": COMPILER_INPUTS_CONTRACT,
        "normalized_source": normalized_snapshot,
        "normalized_source_hash": sha256_json(normalized_snapshot),
        "decisions_snapshot": decisions_snapshot,
        "runtime_decisions_hash": (
            sha256_json(decisions_snapshot)
            if decisions_snapshot is not None
            else None
        ),
        "runtime_profile": runtime_profile,
        "runtime_profile_hash": sha256_json(runtime_profile),
    }


def prompt_plan_content_hash(plan: Mapping[str, Any]) -> str:
    """Hash a prompt plan exactly once after removing its own hash field."""
    payload = {
        key: value for key, value in plan.items() if key != "content_hash"
    }
    return sha256_json(payload)


def _split_generation_invalid_groups(
    planned_groups: Sequence[Mapping[str, Any]],
    invalid_shot_ids: set[str],
) -> list[dict[str, Any]]:
    isolated: list[dict[str, Any]] = []
    for planned in planned_groups:
        shots = list(planned["shots"])
        group_has_invalid = any(
            str(shot["source_shot_id"]) in invalid_shot_ids
            for shot in shots
        )
        if len(shots) == 1 or not group_has_invalid:
            item = copy.deepcopy(dict(planned))
            if (
                len(shots) == 1
                and str(shots[0]["source_shot_id"]) in invalid_shot_ids
            ):
                item["grouping_reason"] = None
                item["semantic_compatibility"] = None
                item["standalone_reason"] = "generation_context_invalid"
            isolated.append(item)
            continue
        for shot in shots:
            shot_id = str(shot["source_shot_id"])
            isolated.append(
                {
                    "shots": [shot],
                    "grouping_reason": None,
                    "semantic_compatibility": None,
                    "standalone_reason": (
                        "generation_context_invalid"
                        if shot_id in invalid_shot_ids
                        else "generation_group_split"
                    ),
                }
            )
    return isolated


def _split_unreadable_groups(
    planned_groups: Sequence[Mapping[str, Any]],
    unreadable_shot_ids: set[str],
) -> list[dict[str, Any]]:
    isolated: list[dict[str, Any]] = []
    for planned in planned_groups:
        shots = list(planned["shots"])
        group_has_unreadable = any(
            str(shot["source_shot_id"]) in unreadable_shot_ids
            for shot in shots
        )
        if len(shots) == 1 or not group_has_unreadable:
            item = copy.deepcopy(dict(planned))
            if (
                len(shots) == 1
                and str(shots[0]["source_shot_id"])
                in unreadable_shot_ids
            ):
                item["grouping_reason"] = None
                item["semantic_compatibility"] = None
                item["standalone_reason"] = "input_material_unreadable"
            isolated.append(item)
            continue
        for shot in shots:
            shot_id = str(shot["source_shot_id"])
            isolated.append(
                {
                    "shots": [shot],
                    "grouping_reason": None,
                    "semantic_compatibility": None,
                    "standalone_reason": (
                        "input_material_unreadable"
                        if shot_id in unreadable_shot_ids
                        else "unreadable_group_split"
                    ),
                }
            )
    return isolated


def _build_generation_failed_unit(
    unit_index: int,
    planned: Mapping[str, Any],
) -> dict[str, Any]:
    shots = list(planned["shots"])
    timeline, total_duration = _build_timeline(shots, {})
    return {
        "prompt_unit_id": f"PU{unit_index + 1:03d}",
        "source_shot_ids": [shot["source_shot_id"] for shot in shots],
        "source_shot_hashes": [shot["source_shot_hash"] for shot in shots],
        "total_duration_seconds": total_duration,
        "grouping_reason": None,
        "standalone_reason": "generation_context_invalid",
        "semantic_compatibility": None,
        "timeline": timeline,
        "prompt_blocks": [],
        "prompt_text": "",
        "prompt_validation": {
            "status": "PARTIAL",
            "checks": {
                "source_mapping": len(shots) == len(timeline),
                "timed_timeline": (
                    True
                    if all(
                        cut["duration_seconds"] is not None
                        for cut in timeline
                    )
                    else None
                ),
                "dialogue_exact": None,
                "dialogue_handling": "NOT_COMPILED",
                "reference_tags_exact": None,
                "source_visual_action_covered": None,
                "continuity_covered": None,
                "source_anti_slop": (
                    "REVIEW_REQUIRED"
                    if any(
                        shot.get("source_anti_slop_terms") for shot in shots
                    )
                    else "NONE"
                ),
                "downstream_anti_slop_absent": True,
                "model_metadata_absent": True,
                "semantic_compatibility": "NOT_APPLICABLE",
                "emotion_visualization": "NOT_COMPILED",
            },
            "diagnostic_codes": ["GENERATION_CONTEXT_INVALID"],
        },
    }


def _build_unreadable_failed_unit(
    unit_index: int,
    planned: Mapping[str, Any],
) -> dict[str, Any]:
    shots = list(planned["shots"])
    timeline, total_duration = _build_timeline(shots, {})
    return {
        "prompt_unit_id": f"PU{unit_index + 1:03d}",
        "source_shot_ids": [shot["source_shot_id"] for shot in shots],
        "source_shot_hashes": [shot["source_shot_hash"] for shot in shots],
        "total_duration_seconds": total_duration,
        "grouping_reason": None,
        "standalone_reason": "input_material_unreadable",
        "semantic_compatibility": None,
        "timeline": timeline,
        "prompt_blocks": [],
        "prompt_text": "",
        "prompt_validation": {
            "status": "FAIL",
            "checks": {
                "source_mapping": len(shots) == len(timeline),
                "timed_timeline": (
                    True
                    if all(
                        cut["duration_seconds"] is not None
                        for cut in timeline
                    )
                    else None
                ),
                "dialogue_exact": None,
                "dialogue_handling": "NOT_COMPILED",
                "reference_tags_exact": None,
                "source_visual_action_covered": None,
                "continuity_covered": None,
                "source_anti_slop": (
                    "REVIEW_REQUIRED"
                    if any(
                        shot.get("source_anti_slop_terms") for shot in shots
                    )
                    else "NONE"
                ),
                "downstream_anti_slop_absent": True,
                "model_metadata_absent": True,
                "semantic_compatibility": "NOT_APPLICABLE",
                "emotion_visualization": "NOT_COMPILED",
            },
            "diagnostic_codes": ["INPUT_MATERIAL_UNREADABLE"],
        },
    }
