"""su-promptskill internal module: source locking, shape adapters and normalization."""

from __future__ import annotations

from . import core as _previous

globals().update({
    key: value
    for key, value in vars(_previous).items()
    if not key.startswith("__")
})

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Responsibility module behind scripts/prompt_delivery.py."

def _source_sound_clauses(text: str) -> list[str]:
    clauses: list[str] = []
    for raw_clause in re.split(r"(?<=[。！？])|\n+", text):
        clause = raw_clause.strip()
        if clause and SOURCE_SOUND_CUE_RE.search(clause):
            clauses.append(clause)
    return _unique_strings(clauses)


def _derive_source_audio_by_shot(
    document: Mapping[str, Any],
    raw_shots: Sequence[Any],
) -> list[list[str]]:
    fact_index: dict[str, Mapping[str, Any]] = {}
    for beat in document.get("beats", []):
        if not isinstance(beat, dict):
            continue
        for fact in beat.get("facts", []):
            if not isinstance(fact, dict):
                continue
            fact_id = _clean_text(fact.get("fact_id"))
            if fact_id and fact_id not in fact_index:
                fact_index[fact_id] = fact
    declared_sound_ids = {
        _clean_text(fact_id)
        for event in document.get("screen_events", [])
        if isinstance(event, dict)
        for fact_id in event.get("sound_fact_ids", [])
        if _clean_text(fact_id)
    }
    result: list[list[str]] = []
    for raw_shot in raw_shots:
        if not isinstance(raw_shot, dict):
            result.append([])
            continue
        fact_ids = [
            _clean_text(value)
            for value in raw_shot.get("covered_fact_ids", [])
            if _clean_text(value)
        ]
        for phase in raw_shot.get("shot_phases", []):
            if isinstance(phase, dict):
                fact_ids.extend(
                    _clean_text(value)
                    for value in phase.get("sound_fact_ids", [])
                    if _clean_text(value)
                )
        audio: list[str] = []
        for fact_id in _unique_strings(fact_ids):
            fact = fact_index.get(fact_id)
            if not isinstance(fact, Mapping):
                continue
            if _clean_text(fact.get("type")) == "dialogue":
                continue
            text = _preserve_text(
                _render_descriptive_value(
                    fact.get("text") or fact.get("source_fragment")
                )
            )
            if not text:
                continue
            if fact_id in declared_sound_ids:
                audio.extend(_source_sound_clauses(text) or [text])
            else:
                audio.extend(_source_sound_clauses(text))
        result.append(_unique_strings(audio))
    return result


DIRECTOR_MOVEMENT_LABELS = {
    "fixed": "固定",
    "pan": "横摇",
    "tilt": "俯仰",
    "track": "轨道跟随",
    "follow": "跟随",
    "pull": "轻退",
    "push": "推进",
    "dolly": "轨道移动",
    "crane": "升降",
    "handheld": "手持",
    "vehicle": "车载固定并随车身受控微动",
    "focus": "焦点转移",
    "orbit": "环绕",
    "zoom": "变焦",
    "compound": "复合运动",
    "other": "其他来源运动",
}


def _has_source_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def _adapter_fact_signature(values: Sequence[Any]) -> tuple[str, ...]:
    return tuple(
        re.sub(
            r"\s+",
            " ",
            _preserve_text(_render_descriptive_value(value)),
        ).strip()
        for value in values
        if _preserve_text(_render_descriptive_value(value))
    )


def _dialogue_signature(values: Sequence[Any]) -> tuple[tuple[str, ...], ...]:
    signature: list[tuple[str, ...]] = []
    for value in values:
        if isinstance(value, str):
            signature.append(("", value.strip(), "", ""))
            continue
        if not isinstance(value, dict):
            signature.append(("", canonical_json(value), "", ""))
            continue
        signature.append(
            (
                _clean_text(value.get("speaker") or value.get("character")),
                _clean_text(value.get("text")),
                _clean_text(
                    value.get("shot_delivery")
                    or value.get("delivery")
                    or value.get("position")
                    or value.get("on_screen")
                ),
                _clean_text(value.get("audio_role") or value.get("voice_type")),
            )
        )
    return tuple(signature)


def _select_adapter_items(
    top_level: Sequence[Any],
    nested: Sequence[Any],
    *,
    issues: list[dict[str, Any]],
    path: str,
    label: str,
    dialogue: bool = False,
) -> tuple[list[Any], bool]:
    top = list(copy.deepcopy(top_level))
    projected = list(copy.deepcopy(nested))
    if not top:
        return projected, False
    if not projected:
        return top, False
    top_signature = (
        _dialogue_signature(top)
        if dialogue
        else _adapter_fact_signature(top)
    )
    nested_signature = (
        _dialogue_signature(projected)
        if dialogue
        else _adapter_fact_signature(projected)
    )
    if top_signature == nested_signature:
        return projected, False
    issues.append(
        _issue(
            "UPSTREAM_FIELD_CONFLICT",
            "ERROR",
            "shot",
            path,
            f"{label} 的顶层 canonical 字段与结构化上游字段冲突；不得拼接或静默覆盖。",
            ("prompt_compilation", "source_fidelity"),
        )
    )
    return [], True


def _director_dialogue_index(
    document: Mapping[str, Any], issues: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    source = document.get("source", {})
    source = source if isinstance(source, dict) else {}
    raw_lines = source.get("dialogue_lines", [])
    raw_lines = raw_lines if isinstance(raw_lines, list) else []
    result: dict[str, dict[str, Any]] = {}
    for index, raw_line in enumerate(raw_lines):
        path = f"source.dialogue_lines[{index}]"
        if not isinstance(raw_line, dict):
            issues.append(
                _issue(
                    "UPSTREAM_DIALOGUE_INVALID",
                    "ERROR",
                    "source",
                    path,
                    "来源对白必须是包含 dialogue_id、speaker 和 text 的对象。",
                    ("prompt_compilation", "dialogue_fidelity"),
                )
            )
            continue
        dialogue_id = _clean_text(raw_line.get("dialogue_id"))
        speaker = _clean_text(raw_line.get("speaker"))
        text = _clean_text(raw_line.get("text"))
        if not dialogue_id or not speaker or not text or dialogue_id in result:
            issues.append(
                _issue(
                    "UPSTREAM_DIALOGUE_INVALID",
                    "ERROR",
                    "source",
                    path,
                    "来源对白 ID 必须唯一，speaker 和 text 必须非空。",
                    ("prompt_compilation", "dialogue_fidelity"),
                )
            )
            continue
        result[dialogue_id] = copy.deepcopy(raw_line)
    return result


def _director_invalid_dialogue_ids(
    raw_shots: Sequence[Any],
    dialogue_index: Mapping[str, Mapping[str, Any]],
    issues: list[dict[str, Any]],
) -> set[str]:
    segments_by_id: dict[str, list[str]] = {}
    for shot_index, raw_shot in enumerate(raw_shots):
        if not isinstance(raw_shot, dict):
            continue
        sound = raw_shot.get("sound", {})
        sound = sound if isinstance(sound, dict) else {}
        segments = sound.get("dialogue_segments", [])
        if not isinstance(segments, list):
            issues.append(
                _issue(
                    "UPSTREAM_DIALOGUE_INVALID",
                    "ERROR",
                    "shot",
                    f"shots[{shot_index}].sound.dialogue_segments",
                    "dialogue_segments 必须是数组。",
                    ("prompt_compilation", "dialogue_fidelity"),
                )
            )
            continue
        for segment_index, segment in enumerate(segments):
            path = f"shots[{shot_index}].sound.dialogue_segments[{segment_index}]"
            if not isinstance(segment, dict):
                issues.append(
                    _issue(
                        "UPSTREAM_DIALOGUE_INVALID",
                        "ERROR",
                        "shot",
                        path,
                        "对白片段必须是对象。",
                        ("prompt_compilation", "dialogue_fidelity"),
                    )
                )
                continue
            dialogue_id = _clean_text(segment.get("dialogue_id"))
            text = _clean_text(segment.get("text"))
            if not dialogue_id or dialogue_id not in dialogue_index or not text:
                issues.append(
                    _issue(
                        "UPSTREAM_DIALOGUE_INVALID",
                        "ERROR",
                        "shot",
                        path,
                        "对白片段必须引用唯一存在的来源 dialogue_id 且 text 非空。",
                        ("prompt_compilation", "dialogue_fidelity"),
                    )
                )
                continue
            segments_by_id.setdefault(dialogue_id, []).append(text)

    invalid: set[str] = set()
    for dialogue_id, source_line in dialogue_index.items():
        observed = "".join(segments_by_id.get(dialogue_id, []))
        expected = _clean_text(source_line.get("text"))
        if observed != expected:
            invalid.add(dialogue_id)
            issues.append(
                _issue(
                    "UPSTREAM_DIALOGUE_PLAYBACK_MISMATCH",
                    "ERROR",
                    "source",
                    f"source.dialogue_lines[{dialogue_id}]",
                    "镜头对白片段按来源顺序拼接后未逐字等于来源对白。",
                    ("prompt_compilation", "dialogue_fidelity"),
                )
            )
    return invalid


def _director_dialogue_for_shot(
    raw_shot: Mapping[str, Any],
    dialogue_index: Mapping[str, Mapping[str, Any]],
    invalid_dialogue_ids: set[str],
) -> list[dict[str, Any]]:
    sound = raw_shot.get("sound", {})
    sound = sound if isinstance(sound, dict) else {}
    segments = sound.get("dialogue_segments", [])
    segments = segments if isinstance(segments, list) else []
    result: list[dict[str, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        dialogue_id = _clean_text(segment.get("dialogue_id"))
        if dialogue_id in invalid_dialogue_ids:
            continue
        source_line = dialogue_index.get(dialogue_id)
        if not isinstance(source_line, Mapping):
            continue
        delivery = _clean_text(segment.get("delivery"))
        result.append(
            {
                "dialogue_id": dialogue_id,
                "speaker": _clean_text(source_line.get("speaker")),
                "text": _clean_text(segment.get("text")),
                "source_text": _clean_text(source_line.get("text")),
                "delivery": delivery,
                "shot_delivery": delivery,
                "position": delivery,
                "audio_role": _clean_text(source_line.get("voice_type")),
            }
        )
    return result


def _director_audio_for_shot(raw_shot: Mapping[str, Any]) -> list[str]:
    sound = raw_shot.get("sound", {})
    sound = sound if isinstance(sound, dict) else {}
    result: list[str] = []
    perspective = _clean_text(sound.get("perspective"))
    if perspective:
        result.append(f"声音视点：{perspective}")
    effects = sound.get("effects", [])
    if isinstance(effects, list):
        result.extend(
            _clean_text(value)
            for value in effects
            if _clean_text(value)
        )
    ambience = _clean_text(sound.get("ambience"))
    if ambience:
        result.append(f"环境声：{ambience}")
    music = _clean_text(sound.get("music"))
    if music:
        result.append(f"音乐：{music}")
    return _unique_strings(result)


def _director_camera(raw_camera: Any) -> dict[str, Any]:
    camera = _as_dict(raw_camera)
    movement = camera.get("movement")
    if not isinstance(movement, dict):
        return camera
    movement_type = _clean_text(movement.get("type"))
    camera["movement"] = DIRECTOR_MOVEMENT_LABELS.get(
        movement_type, movement_type
    )
    camera["movement_plan"] = {
        "trigger": copy.deepcopy(movement.get("trigger")),
        "speed": copy.deepcopy(movement.get("speed")),
        "path": copy.deepcopy(movement.get("path")),
        "end_condition": copy.deepcopy(movement.get("end_condition")),
        "hold_reason": copy.deepcopy(movement.get("reason")),
    }
    return camera


def _camera_without_dialogue_literals(
    camera: Mapping[str, Any], dialogue: Sequence[Any]
) -> dict[str, Any]:
    """Keep timing semantics while reserving literal speech for dialogue owner."""
    projected = copy.deepcopy(dict(camera))
    movement_plan = projected.get("movement_plan")
    if not isinstance(movement_plan, dict):
        return projected
    dialogue_texts = _dialogue_texts(dialogue)
    for key in ("trigger", "end_condition", "hold_reason"):
        value = _clean_text(movement_plan.get(key))
        if not value:
            continue
        for dialogue_text in dialogue_texts:
            value = value.replace(dialogue_text, "来源对白")
        value = value.replace("第一次说出来源对白", "第一次发声")
        value = value.replace("第二次说出来源对白", "第二次发声")
        value = value.replace("说出来源对白", "发声")
        movement_plan[key] = value
    projected["movement_plan"] = movement_plan
    return projected


def _director_execution_fallback(
    execution_text: str,
    *,
    camera: Mapping[str, Any],
    blocking: Sequence[Any],
    visible_behavior: Sequence[Any],
    dialogue: Sequence[Any],
    audio: Sequence[Any],
    continuity_updates: Sequence[Any],
) -> tuple[str, dict[str, Any]]:
    if not execution_text:
        return "", {
            "state": "not_provided",
            "source_hash": None,
            "adopted_clauses": [],
        }

    audit_headings = {
        "观看",
        "摄影",
        "调度与表演",
        "声音",
        "剪辑",
        "连续性",
        "时长",
        "镜头动机",
        "制作风险",
    }
    fallback_headings = {"画面", "画面内容", "执行画面"}
    matches = list(re.finditer(r"【([^】]+)】", execution_text))
    candidate_parts: list[str] = []
    unknown_headings: list[str] = []
    if matches:
        preamble = execution_text[: matches[0].start()].strip()
        if preamble:
            candidate_parts.append(preamble)
        for index, match in enumerate(matches):
            heading = _clean_text(match.group(1))
            content_end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(execution_text)
            )
            content = execution_text[match.end() : content_end].strip()
            if "｜" in heading:
                if content and index == len(matches) - 1:
                    candidate_parts.append(content)
                continue
            if heading in fallback_headings:
                if content:
                    candidate_parts.append(content)
                continue
            if heading not in audit_headings:
                unknown_headings.append(heading)
    else:
        candidate_parts.append(execution_text.strip())

    source_hash = sha256_json(execution_text)
    if unknown_headings:
        return "", {
            "state": "blocked",
            "source_hash": source_hash,
            "adopted_clauses": [],
            "unknown_headings": _unique_strings(unknown_headings),
        }
    movement_plan = camera.get("movement_plan", {})
    movement_plan = (
        movement_plan if isinstance(movement_plan, Mapping) else {}
    )
    represented: list[Any] = [
        camera.get("shot_size"),
        camera.get("angle"),
        camera.get("position"),
        camera.get("composition"),
        camera.get("lens_intent"),
        camera.get("movement"),
        camera.get("focus"),
        camera.get("lighting_change"),
        movement_plan.get("trigger"),
        movement_plan.get("speed"),
        movement_plan.get("path"),
        movement_plan.get("end_condition"),
        movement_plan.get("hold_reason"),
    ]
    represented.extend(blocking)
    represented.extend(visible_behavior)
    represented.extend(_dialogue_texts(dialogue))
    represented.extend(audio)
    represented.extend(
        _render_continuity_update(value)
        for value in continuity_updates
    )
    text = "\n".join(candidate_parts)
    text = _remove_owned_dialogue_clauses(text, dialogue)
    clauses = _novel_clauses(text, represented)
    normalized_represented = [
        re.sub(r"[\s\W_]+", "", _render_descriptive_value(value))
        for value in represented
        if _render_descriptive_value(value)
    ]
    unique: list[str] = []
    for clause in clauses:
        normalized_clause = re.sub(r"[\s\W_]+", "", clause)
        if any(
            min(len(normalized_clause), len(fact)) >= 8
            and SequenceMatcher(None, normalized_clause, fact).ratio() >= 0.58
            for fact in normalized_represented
        ):
            continue
        unique.append(clause)
    adopted = _unique_strings(clause.strip() for clause in unique if clause.strip())
    rendered = "".join(adopted).strip()
    return rendered, {
        "state": "fallback_unique_facts" if rendered else "audit_only",
        "source_hash": source_hash,
        "adopted_clauses": adopted,
    }


def _director_shape(raw_shot: Mapping[str, Any]) -> bool:
    staging = raw_shot.get("staging")
    sound = raw_shot.get("sound")
    camera = raw_shot.get("camera")
    continuity = raw_shot.get("continuity")
    return (
        isinstance(staging, dict)
        or (
            isinstance(sound, dict)
            and any(
                key in sound
                for key in (
                    "perspective",
                    "dialogue_segments",
                    "effects",
                    "ambience",
                    "music",
                )
            )
        )
        or (
            isinstance(camera, dict)
            and isinstance(camera.get("movement"), dict)
        )
        or (
            isinstance(continuity, dict)
            and any(
                key in continuity
                for key in ("state_updates", "intentional_breaks")
            )
        )
        or _has_source_value(raw_shot.get("execution_text"))
    )


def normalize_input(document: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize source material without mutating it."""
    issues: list[dict[str, Any]] = []
    if not isinstance(document, dict):
        snapshot = {
            "source": {
                "source_mode": "standalone_storyboard",
                "source_contract": None,
                "source_skill": None,
                "source_skill_version": None,
                "project_id": None,
                "source_content_hash": None,
                "observed_content_hash": None,
                "local_content_hash": sha256_json(document),
                "source_read_only": True,
                "source_shot_count": 0,
            },
            "shots": [],
            "source_global_blocked": True,
        }
        issues.append(
            _issue(
                "INPUT_MATERIAL_UNREADABLE",
                "ERROR",
                "source",
                "$",
                "输入必须先标准化为包含 shots[] 的 JSON 对象。",
                ("prompt_compilation",),
            )
        )
        return snapshot, issues

    source_global_blocked = False
    explicit_source_mode = _clean_text(document.get("source_mode"))
    contract_name = _clean_text(document.get("contract_name"))
    contract_version = _clean_text(document.get("contract_version"))
    source_skill = _clean_text(document.get("source_skill"))
    source_skill_version = _clean_text(document.get("source_skill_version"))
    claims_structured_provenance = (
        explicit_source_mode == "upstream_structured"
        or bool(contract_name)
        or bool(source_skill)
    )

    if explicit_source_mode and explicit_source_mode not in SOURCE_MODES:
        issues.append(
            _issue(
                "SOURCE_MODE_UNRECOGNIZED",
                "WARN",
                "source",
                "source_mode",
                (
                    f"来源声明了未知 source_mode：{explicit_source_mode}；"
                    "该值只作 provenance，按当前材料形状推断运行模式。"
                ),
                (),
            )
        )

    if explicit_source_mode in SOURCE_MODES:
        source_mode = explicit_source_mode
    elif claims_structured_provenance:
        source_mode = "upstream_structured"
    else:
        source_mode = "standalone_storyboard"
    source_contract = (
        f"{contract_name}/{contract_version}"
        if contract_name and contract_version
        else None
    )
    observed_hash = source_observed_hash(document)
    declared_hash = document.get("content_hash")
    local_hash = sha256_json(document)

    if declared_hash not in (None, "") and (
        not isinstance(declared_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", declared_hash) is None
    ):
        source_global_blocked = True
        issues.append(
            _issue(
                "SOURCE_HASH_INVALID",
                "ERROR",
                "source",
                "content_hash",
                (
                    "来源声明了 content_hash，但它不是 64 位小写 "
                    "SHA-256；来源保持只读。"
                ),
                ("prompt_compilation", "source_integrity"),
            )
        )
    elif declared_hash not in (None, "") and declared_hash != observed_hash:
        source_global_blocked = True
        issues.append(
            _issue(
                "SOURCE_HASH_MISMATCH",
                "ERROR",
                "source",
                "content_hash",
                "来源声明的 content_hash 与当前输入内容不一致；来源保持只读。",
                ("prompt_compilation", "source_integrity"),
            )
        )

    raw_shots = document.get("shots")
    if not isinstance(raw_shots, list):
        raw_shots = []
        source_global_blocked = True
        issues.append(
            _issue(
                "INPUT_MATERIAL_UNREADABLE",
                "ERROR",
                "source",
                "shots",
                "输入没有可读取的 shots[] 数组。",
                ("prompt_compilation",),
            )
        )
    elif not raw_shots:
        source_global_blocked = True
        issues.append(
            _issue(
                "SOURCE_SCOPE_EMPTY",
                "ERROR",
                "source",
                "shots",
                "当前输入范围没有可处理镜头。",
                ("prompt_compilation",),
            )
        )

    scene_index: dict[str, dict[str, Any]] = {}
    duplicate_scene_ids: set[str] = set()
    raw_scenes = document.get("scenes", [])
    has_scene_catalog = "scenes" in document and isinstance(raw_scenes, list)
    if has_scene_catalog:
        for scene_index_number, raw_scene in enumerate(raw_scenes):
            if not isinstance(raw_scene, dict):
                continue
            scene_id = _clean_text(raw_scene.get("scene_id"))
            if not scene_id:
                continue
            if scene_id in scene_index:
                duplicate_scene_ids.add(scene_id)
                issues.append(
                    _issue(
                        "SCENE_ID_DUPLICATE",
                        "WARN",
                        "source",
                        f"scenes[{scene_index_number}].scene_id",
                        (
                            f"顶层 scene_id {scene_id} 重复；对应镜头不猜测"
                            "场景关联。"
                        ),
                        (),
                    )
                )
                continue
            scene_index[scene_id] = copy.deepcopy(raw_scene)

    derived_audio_by_shot = _derive_source_audio_by_shot(
        document, raw_shots
    )
    has_director_dialogue_shape = any(
        isinstance(raw_shot, dict)
        and isinstance(raw_shot.get("sound"), dict)
        and "dialogue_segments" in raw_shot.get("sound", {})
        for raw_shot in raw_shots
    )
    director_dialogue_index = (
        _director_dialogue_index(document, issues)
        if has_director_dialogue_shape
        else {}
    )
    invalid_director_dialogue_ids = (
        _director_invalid_dialogue_ids(
            raw_shots, director_dialogue_index, issues
        )
        if has_director_dialogue_shape
        else set()
    )
    normalized_shots: list[dict[str, Any]] = []
    seen_ids: dict[str, int] = {}
    for index, raw_shot in enumerate(raw_shots):
        shot_path = f"shots[{index}]"
        if not isinstance(raw_shot, dict):
            issues.append(
                _issue(
                    "INPUT_MATERIAL_UNREADABLE",
                    "ERROR",
                    "shot",
                    shot_path,
                    "该镜不是 JSON 对象，无法编译。",
                    ("prompt_compilation",),
                )
            )
            continue

        source_anti_slop_terms = _anti_slop_terms_in_value(raw_shot)
        if source_anti_slop_terms:
            issues.append(
                _issue(
                    "SOURCE_ANTI_SLOP_REVIEW",
                    "WARN",
                    "shot",
                    shot_path,
                    (
                        "来源含可能为空泛强化词、也可能是合法对白或实体名的字面："
                        f"{', '.join(source_anti_slop_terms)}；脚本原样保留，需语义审阅。"
                    ),
                    (),
                )
            )

        expected_order = index + 1
        source_shot_id = _clean_text(
            raw_shot.get("shot_id") or raw_shot.get("source_shot_id")
        )
        if not source_shot_id:
            source_shot_id = f"LOCAL-SH{expected_order:03d}"

        if source_shot_id in seen_ids:
            issues.append(
                _issue(
                    "SHOT_ID_DUPLICATE",
                    "ERROR",
                    "shot",
                    f"{shot_path}.shot_id",
                    (
                        f"镜号 {source_shot_id} 与 shots[{seen_ids[source_shot_id]}] "
                        "重复；分组 decisions 不能安全引用重复 ID。"
                    ),
                    ("decision_mapping",),
                )
            )
        else:
            seen_ids[source_shot_id] = index

        declared_order = raw_shot.get("shot_order", raw_shot.get("source_order"))
        if declared_order is not None and (
            isinstance(declared_order, bool)
            or not isinstance(declared_order, int)
            or declared_order != expected_order
        ):
            issues.append(
                _issue(
                    "SHOT_ORDER_INVALID",
                    "ERROR",
                    "shot",
                    f"{shot_path}.shot_order",
                    "shots[] 数组顺序与声明顺序不一致；仍按数组位置处理。",
                    ("grouping",),
                )
            )

        raw_duration = raw_shot.get("duration_seconds")
        duration: Decimal | None
        if raw_duration is None:
            duration = None
            issues.append(
                _issue(
                    "DURATION_MISSING",
                    "ERROR",
                    "shot",
                    f"{shot_path}.duration_seconds",
                    "来源未提供时长；该镜保持单镜且不生成伪时间。",
                    ("multi_shot_grouping", "timed_cut_timeline"),
                )
            )
        else:
            try:
                duration = _duration_decimal(raw_duration)
            except InvalidOperation:
                duration = None
                issues.append(
                    _issue(
                        "DURATION_INVALID",
                        "ERROR",
                        "shot",
                        f"{shot_path}.duration_seconds",
                        "时长必须是正有限数；当前值保持未知且禁止合镜。",
                        ("multi_shot_grouping", "timed_cut_timeline"),
                    )
                )

        uses_director_adapter = _director_shape(raw_shot)
        staging = (
            _as_dict(raw_shot.get("staging"))
            if uses_director_adapter
            else {}
        )
        camera = (
            _director_camera(raw_shot.get("camera"))
            if uses_director_adapter
            else _as_dict(raw_shot.get("camera"))
        )

        top_blocking = _as_list(raw_shot.get("blocking"))
        nested_blocking = _as_items(staging.get("blocking"))
        blocking, blocking_conflict = _select_adapter_items(
            top_blocking,
            nested_blocking,
            issues=issues,
            path=f"{shot_path}.staging.blocking",
            label="blocking",
        )

        top_performance = _as_dict(raw_shot.get("performance"))
        if not top_performance:
            top_performance = {
                "emotion_intent": _clean_text(
                    raw_shot.get("emotion_intent")
                ),
                "visible_behavior": _as_list(
                    raw_shot.get("visible_behavior")
                ),
            }
        top_visible_behavior = _as_list(
            top_performance.get("visible_behavior")
        )
        nested_visible_behavior = _as_items(staging.get("performance"))
        visible_behavior, performance_conflict = _select_adapter_items(
            top_visible_behavior,
            nested_visible_behavior,
            issues=issues,
            path=f"{shot_path}.staging.performance",
            label="performance.visible_behavior",
        )
        emotion_intent = _clean_text(
            top_performance.get("emotion_intent")
        )
        performance = {
            "emotion_intent": emotion_intent,
            "visible_behavior": copy.deepcopy(visible_behavior),
        }

        top_dialogue = _as_list(raw_shot.get("dialogue"))
        nested_dialogue = (
            _director_dialogue_for_shot(
                raw_shot,
                director_dialogue_index,
                invalid_director_dialogue_ids,
            )
            if uses_director_adapter and has_director_dialogue_shape
            else []
        )
        dialogue, dialogue_conflict = _select_adapter_items(
            top_dialogue,
            nested_dialogue,
            issues=issues,
            path=f"{shot_path}.sound.dialogue_segments",
            label="dialogue",
            dialogue=True,
        )
        for dialogue_index, dialogue_item in enumerate(dialogue):
            if not isinstance(dialogue_item, dict):
                continue
            delivery_value = _clean_text(dialogue_item.get("delivery"))
            if delivery_value and delivery_value not in DIALOGUE_DELIVERY_LABELS:
                issues.append(
                    _issue(
                        "DIALOGUE_DELIVERY_UNSUPPORTED",
                        "ERROR",
                        "shot",
                        f"{shot_path}.dialogue[{dialogue_index}].delivery",
                        (
                            f"未知对白声位 {delivery_value}；保留对白原文，"
                            "但不把未知枚举写入中文 Prompt。"
                        ),
                        ("prompt_compilation", "source_fidelity"),
                    )
                )
        if uses_director_adapter and dialogue:
            camera = _camera_without_dialogue_literals(camera, dialogue)

        continuity = _as_dict(raw_shot.get("continuity"))
        top_continuity_updates = _as_list(
            raw_shot.get("continuity_updates")
        )
        nested_continuity_updates = (
            _as_items(continuity.get("state_updates"))
            if uses_director_adapter
            else []
        )
        continuity_updates, continuity_conflict = _select_adapter_items(
            top_continuity_updates,
            nested_continuity_updates,
            issues=issues,
            path=f"{shot_path}.continuity.state_updates",
            label="continuity updates",
        )
        if uses_director_adapter:
            continuity.pop("state_updates", None)
        transition = _as_dict(raw_shot.get("transition_to_next"))
        top_rendered = _clean_text(
            raw_shot.get("rendered_shot_description")
            or raw_shot.get("visual_content")
            or raw_shot.get("description")
        )
        nested_rendered = (
            _clean_text(raw_shot.get("execution_text"))
            if uses_director_adapter
            else ""
        )
        rendered_conflict = bool(
            top_rendered
            and nested_rendered
            and top_rendered != nested_rendered
        )
        if rendered_conflict:
            issues.append(
                _issue(
                    "UPSTREAM_FIELD_CONFLICT",
                    "ERROR",
                    "shot",
                    f"{shot_path}.execution_text",
                    "rendered description 与 execution_text 冲突；不得静默覆盖。",
                    ("prompt_compilation", "source_fidelity"),
                )
            )
            rendered = ""
        else:
            rendered = nested_rendered or top_rendered

        top_subjects = _as_items(
            raw_shot.get("visible_characters", raw_shot.get("subjects"))
        )
        nested_subjects = _as_items(staging.get("subjects"))
        subjects, subjects_conflict = _select_adapter_items(
            top_subjects,
            nested_subjects,
            issues=issues,
            path=f"{shot_path}.staging.subjects",
            label="subjects",
        )
        top_visible_subjects = _as_items(raw_shot.get("visible_subjects"))
        nested_visible_subjects = _as_items(staging.get("visible_subjects"))
        visible_subjects, visible_subjects_conflict = _select_adapter_items(
            top_visible_subjects,
            nested_visible_subjects,
            issues=issues,
            path=f"{shot_path}.staging.visible_subjects",
            label="visible subjects",
        )
        top_offscreen_subjects = _as_items(raw_shot.get("offscreen_subjects"))
        nested_offscreen_subjects = _as_items(staging.get("offscreen_subjects"))
        offscreen_subjects, offscreen_subjects_conflict = _select_adapter_items(
            top_offscreen_subjects,
            nested_offscreen_subjects,
            issues=issues,
            path=f"{shot_path}.staging.offscreen_subjects",
            label="offscreen subjects",
        )
        scene_material = _as_items(
            raw_shot.get(
                "environment_behavior",
                raw_shot.get("scene_material", raw_shot.get("environment")),
            )
        )
        lighting_style = {
            "lighting": copy.deepcopy(raw_shot.get("lighting")),
            "style": copy.deepcopy(
                raw_shot.get("style", raw_shot.get("visual_style"))
            ),
        }
        top_audio = _as_items(raw_shot.get("audio"))
        nested_audio = (
            _director_audio_for_shot(raw_shot)
            if uses_director_adapter
            else []
        )
        if not uses_director_adapter and not top_audio:
            top_audio = _as_items(raw_shot.get("sound"))
        audio, audio_conflict = _select_adapter_items(
            top_audio,
            nested_audio,
            issues=issues,
            path=f"{shot_path}.sound",
            label="audio",
        )
        for derived_audio in derived_audio_by_shot[index]:
            if (
                _adapter_fact_signature([derived_audio])
                not in {
                    _adapter_fact_signature([item]) for item in audio
                }
            ):
                audio.append(derived_audio)
        execution_text_projection = {
            "state": "not_provided",
            "source_hash": None,
            "adopted_clauses": [],
        }
        if uses_director_adapter and nested_rendered and not rendered_conflict:
            rendered, execution_text_projection = _director_execution_fallback(
                nested_rendered,
                camera=camera,
                blocking=blocking,
                visible_behavior=visible_behavior,
                dialogue=dialogue,
                audio=audio,
                continuity_updates=continuity_updates,
            )
            if execution_text_projection["state"] == "blocked":
                issues.append(
                    _issue(
                        "UPSTREAM_FIELD_UNMAPPED",
                        "ERROR",
                        "shot",
                        f"{shot_path}.execution_text",
                        (
                            "execution_text 含无法安全分类的非空区块："
                            + "、".join(
                                execution_text_projection.get(
                                    "unknown_headings", []
                                )
                            )
                            + "；未将其倾倒进 Prompt。"
                        ),
                        ("prompt_compilation", "source_fidelity"),
                    )
                )
        constraints = _as_items(
            raw_shot.get(
                "constraints", raw_shot.get("directorial_constraints")
            )
        )
        delta_text = _clean_text(
            raw_shot.get("prompt_delta")
            or raw_shot.get("motion_delta")
            or raw_shot.get("extension_delta")
        )
        allowed_lighting_changes = _as_items(
            raw_shot.get("allowed_lighting_changes")
        )

        adapter_checks = (
            (
                staging.get("subjects"),
                subjects,
                subjects_conflict,
                "staging.subjects",
            ),
            (
                staging.get("blocking"),
                blocking,
                blocking_conflict,
                "staging.blocking",
            ),
            (
                staging.get("performance"),
                visible_behavior,
                performance_conflict,
                "staging.performance",
            ),
            (
                staging.get("visible_subjects"),
                visible_subjects,
                visible_subjects_conflict,
                "staging.visible_subjects",
            ),
            (
                staging.get("offscreen_subjects"),
                offscreen_subjects,
                offscreen_subjects_conflict,
                "staging.offscreen_subjects",
            ),
        )
        if uses_director_adapter:
            for source_value, projected_value, conflicted, field_name in adapter_checks:
                if (
                    _has_source_value(source_value)
                    and not projected_value
                    and not conflicted
                ):
                    issues.append(
                        _issue(
                            "UPSTREAM_FIELD_UNMAPPED",
                            "ERROR",
                            "shot",
                            f"{shot_path}.{field_name}",
                            "已知上游执行字段非空，但只读投影结果为空。",
                            ("prompt_compilation", "source_fidelity"),
                        )
                    )
        sound = raw_shot.get("sound", {})
        sound = sound if isinstance(sound, dict) else {}
        if (
            uses_director_adapter
            and any(
                _has_source_value(sound.get(key))
                for key in ("perspective", "effects", "ambience", "music")
            )
            and not audio
            and not audio_conflict
        ):
            issues.append(
                _issue(
                    "UPSTREAM_FIELD_UNMAPPED",
                    "ERROR",
                    "shot",
                    f"{shot_path}.sound",
                    "已知上游声音字段非空，但只读投影结果为空。",
                    ("prompt_compilation", "source_fidelity"),
                )
            )
        dialogue_segments = sound.get("dialogue_segments", [])
        if (
            uses_director_adapter
            and _has_source_value(dialogue_segments)
            and not dialogue
            and not dialogue_conflict
            and not invalid_director_dialogue_ids
        ):
            issues.append(
                _issue(
                    "UPSTREAM_FIELD_UNMAPPED",
                    "ERROR",
                    "shot",
                    f"{shot_path}.sound.dialogue_segments",
                    "已知上游对白片段非空，但只读投影结果为空。",
                    ("prompt_compilation", "source_fidelity"),
                )
            )
        if (
            uses_director_adapter
            and _has_source_value(nested_continuity_updates)
            and not continuity_updates
            and not continuity_conflict
        ):
            issues.append(
                _issue(
                    "UPSTREAM_FIELD_UNMAPPED",
                    "ERROR",
                    "shot",
                    f"{shot_path}.continuity.state_updates",
                    "已知上游连续性变化非空，但只读投影结果为空。",
                    ("prompt_compilation", "source_fidelity"),
                )
            )

        cut_design = _as_dict(raw_shot.get("cut_design"))
        edit = raw_shot.get("edit", {})
        edit = edit if isinstance(edit, dict) else {}
        if uses_director_adapter and edit:
            for target_key, source_key in (
                ("entry_trigger", "entry"),
                ("exit_trigger", "exit"),
                ("transition_to_next", "transition_to_next"),
                ("reason", "reason"),
            ):
                if target_key not in cut_design and _has_source_value(
                    edit.get(source_key)
                ):
                    cut_design[target_key] = copy.deepcopy(
                        edit.get(source_key)
                    )
        source_scene_id = _clean_text(raw_shot.get("scene_id"))
        scene_context = _as_dict(raw_shot.get("scene_context"))
        linked_scene = (
            scene_index.get(source_scene_id)
            if source_scene_id not in duplicate_scene_ids
            else None
        )
        if linked_scene is not None:
            scene_context.update(
                {
                    key: copy.deepcopy(linked_scene[key])
                    for key in SCENE_CONTEXT_KEYS
                    if key in linked_scene
                    and linked_scene[key] not in (None, "", [], {})
                }
            )
        elif source_scene_id and has_scene_catalog:
            issues.append(
                _issue(
                    "SCENE_CONTEXT_MISSING",
                    "WARN",
                    "shot",
                    f"{shot_path}.scene_id",
                    (
                        f"scene_id {source_scene_id} 未唯一关联到顶层 scenes[]；"
                        "不编造场景且不回写来源。"
                    ),
                    (),
                )
            )

        normalized = {
            "source_shot_id": source_shot_id,
            "source_order": expected_order,
            "scene_id": copy.deepcopy(raw_shot.get("scene_id")),
            "duration_seconds": _json_number(duration),
            "camera": camera,
            "blocking": blocking,
            "performance": performance,
            "visible_behavior": visible_behavior,
            "emotion_intent": emotion_intent,
            "dialogue": dialogue,
            "continuity": continuity,
            "continuity_updates": continuity_updates,
            "transition_to_next": transition,
            "rendered_shot_description": rendered,
            "subjects": subjects,
            "visible_subjects": visible_subjects,
            "offscreen_subjects": offscreen_subjects,
            "execution_text_projection": execution_text_projection,
            "scene_material": scene_material,
            "scene_context": scene_context,
            "lighting_style": lighting_style,
            "visible_props": _as_items(raw_shot.get("visible_props")),
            "start_state": _as_items(raw_shot.get("start_state")),
            "end_state": _as_items(raw_shot.get("end_state")),
            "cut_design": cut_design,
            "audio": audio,
            "constraints": constraints,
            "delta_text": delta_text,
            "allowed_lighting_changes": allowed_lighting_changes,
            "source_anti_slop_terms": source_anti_slop_terms,
            "source_adapter": (
                "director-shot-data-shape-v2"
                if uses_director_adapter
                else "canonical-source-v1"
            ),
            "source_shot_hash": sha256_json(raw_shot),
            "field_hashes": {
                "camera_hash": sha256_json(camera),
                "blocking_hash": sha256_json(blocking),
                "performance_hash": sha256_json(performance),
                "dialogue_hash": sha256_json(dialogue),
                "continuity_hash": sha256_json(
                    {
                        "continuity": continuity,
                        "continuity_updates": continuity_updates,
                        "transition_to_next": transition,
                    }
                ),
                "rendered_shot_description_hash": sha256_json(
                    rendered
                ),
                "coverage_hash": sha256_json(
                    {
                        "subjects": subjects,
                        "visible_subjects": visible_subjects,
                        "offscreen_subjects": offscreen_subjects,
                        "execution_text_projection": execution_text_projection,
                        "blocking": blocking,
                        "performance": performance,
                        "dialogue": dialogue,
                        "environment_behavior": raw_shot.get(
                            "environment_behavior",
                            raw_shot.get(
                                "scene_material",
                                raw_shot.get("environment", []),
                            ),
                        ),
                        "scene_context": scene_context,
                        "visible_props": raw_shot.get("visible_props", []),
                        "end_state": raw_shot.get("end_state", []),
                        "lighting": raw_shot.get("lighting"),
                        "style": raw_shot.get(
                            "style", raw_shot.get("visual_style")
                        ),
                        "audio": audio,
                        "cut_design": cut_design,
                        "constraints": raw_shot.get(
                            "constraints",
                            raw_shot.get("directorial_constraints"),
                        ),
                        "delta_text": raw_shot.get(
                            "prompt_delta",
                            raw_shot.get(
                                "motion_delta", raw_shot.get("extension_delta")
                            ),
                        ),
                        "allowed_lighting_changes": raw_shot.get(
                            "allowed_lighting_changes"
                        ),
                    }
                ),
            },
        }
        normalized["compilable_source"] = _has_prompt_content(normalized)
        if not normalized["compilable_source"]:
            issues.append(
                _issue(
                    "INPUT_MATERIAL_UNREADABLE",
                    "ERROR",
                    "shot",
                    shot_path,
                    "该镜没有可读取的画面、调度、表演或对白内容。",
                    ("prompt_compilation",),
                )
            )
        normalized_shots.append(normalized)

    source_metadata = {
        "source_mode": source_mode,
        "source_contract": source_contract,
        "source_skill": copy.deepcopy(document.get("source_skill")),
        "source_skill_version": copy.deepcopy(document.get("source_skill_version")),
        "project_id": copy.deepcopy(document.get("project_id")),
        "source_content_hash": copy.deepcopy(declared_hash),
        "observed_content_hash": observed_hash,
        "local_content_hash": local_hash,
        "source_read_only": True,
        "source_shot_count": len(normalized_shots),
    }
    return {
        "source": source_metadata,
        "shots": normalized_shots,
        "source_global_blocked": source_global_blocked,
    }, issues
