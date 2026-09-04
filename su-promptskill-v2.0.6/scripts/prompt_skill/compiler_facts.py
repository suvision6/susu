"""su-promptskill internal module: camera, scene and fact rendering."""

from __future__ import annotations

from . import grouping as _previous

globals().update({
    key: value
    for key, value in vars(_previous).items()
    if not key.startswith("__")
})

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Responsibility module behind scripts/prompt_delivery.py."

def _camera_prompt_fields(
    camera: Mapping[str, Any], *, include_movement: bool = True
) -> tuple[str, str, str]:
    shot_size = ""
    for key in ("shot_size", "framing", "size"):
        shot_size = _preserve_text(
            _render_descriptive_value(camera.get(key))
        )
        if shot_size:
            break

    angle = _preserve_text(
        _render_descriptive_value(camera.get("angle"))
    )
    movement = _preserve_text(
        _render_descriptive_value(camera.get("movement"))
    )
    composition = _preserve_text(
        _render_descriptive_value(camera.get("composition"))
    )
    camera_elements = [item for item in (angle, shot_size) if item]
    if include_movement and movement:
        camera_elements.append(movement)
    prefix = f"【{'，'.join(camera_elements)}】" if camera_elements else ""
    return prefix + composition, angle, shot_size


def _camera_position_sentence(position: str) -> str:
    if not position:
        return ""
    if position.startswith(
        ("位于", "从", "沿", "贴近", "回到", "复用", "先留")
    ):
        return f"摄影机{position}"
    return f"摄影机位于{position}"


def _strip_rendered_headers(text: str) -> str:
    cleaned = text.strip()
    while cleaned.startswith("【"):
        close = cleaned.find("】")
        if close < 0:
            break
        cleaned = cleaned[close + 1 :].lstrip()
    return cleaned.replace("\r\n", "\n").replace("\r", "\n").strip()


def _split_environment_and_action(
    shot: Mapping[str, Any],
) -> tuple[str, str]:
    rendered = _strip_rendered_headers(
        _clean_text(shot.get("rendered_shot_description"))
    )
    if not rendered:
        return "", ""

    environment = ""
    action = rendered
    camera_match = re.search(
        r"(?:摄影机|机位)(?:从|位于|固定|不换位置|以|设在|落在|处在|保持|沿|在)",
        action,
    )
    if camera_match is not None:
        camera_marker = camera_match.start()
        environment = action[:camera_marker].strip(" \n；。，")
        camera_tail = action[camera_marker:]
        separators = [
            position
            for separator in ("；", "。")
            for position in [camera_tail.find(separator)]
            if position >= 0
        ]
        action = (
            camera_tail[min(separators) + 1 :]
            if separators
            else ""
        )

    composition = _preserve_text(
        _render_descriptive_value(
            shot.get("camera", {}).get("composition")
            if isinstance(shot.get("camera"), dict)
            else None
        )
    )
    if composition:
        action = action.replace(f"画面中{composition}。", "", 1)
        action = action.replace(f"画面中{composition}；", "", 1)
        action = action.replace(f"画面中{composition}", "", 1)

    kept_sentences: list[str] = []
    for sentence in re.split(r"(?<=[。！？])", action):
        sentence = sentence.strip()
        if not sentence:
            continue
        comparable_sentence = re.sub(r"[\W_]+", "", sentence)
        comparable_composition = re.sub(r"[\W_]+", "", composition)
        redundant = False
        if (
            comparable_sentence
            and comparable_composition
            and not QUOTED_TEXT_RE.search(sentence)
        ):
            similarity = SequenceMatcher(
                None, comparable_sentence, comparable_composition
            ).ratio()
            redundant = (
                similarity >= 0.47
                or (
                    min(
                        len(comparable_sentence),
                        len(comparable_composition),
                    )
                    >= 8
                    and (
                        comparable_sentence in comparable_composition
                        or comparable_composition in comparable_sentence
                    )
                )
            )
        if not redundant:
            kept_sentences.append(sentence)
    return environment, "".join(kept_sentences).strip(" \n；")


def _normalized_fact_text(value: Any) -> str:
    return re.sub(
        r"[\s\W_]+",
        "",
        _preserve_text(_render_descriptive_value(value)).casefold(),
    )


def _replace_owned_fact_variant(
    text: str, fact: str, replacement: str
) -> str:
    """Replace an owned fact even when only terminal punctuation differs."""
    candidates = _unique_strings(
        [fact, fact.rstrip(" \t\r\n。！？；，,.!?;")]
    )
    for candidate in sorted(candidates, key=len, reverse=True):
        if candidate and candidate in text:
            return text.replace(candidate, replacement)
    return text


def _novel_clauses(
    text: Any,
    represented_facts: Sequence[Any],
    *,
    drop_camera_clauses: bool = True,
) -> list[str]:
    represented = [
        _normalized_fact_text(value)
        for value in represented_facts
        if _normalized_fact_text(value)
    ]
    seen: set[str] = set()
    result: list[str] = []
    for raw_clause in re.split(
        r"(?<=[。！？；])(?![”’])|\n+", _clean_text(text)
    ):
        clause = raw_clause.strip(" \n；")
        if not clause:
            continue
        if drop_camera_clauses and re.search(r"摄影机", clause):
            for segment in re.split(r"[，,]", clause):
                if not re.search(r"摄影机", segment):
                    result.extend(
                        _novel_clauses(
                            segment,
                            represented_facts,
                            drop_camera_clauses=False,
                        )
                    )
            continue
        comparable = re.sub(
            r"^(?:画面先见|随后|起始状态|终态|状态|画面内容)[：:]?",
            "",
            clause,
        )
        normalized = _normalized_fact_text(comparable)
        if not normalized or normalized in seen:
            continue
        if any(
            normalized == fact
            or (
                min(len(normalized), len(fact)) >= 8
                and (normalized in fact or fact in normalized)
            )
            for fact in represented
        ):
            continue
        if clause.startswith(("焦点始终", "按事件顺序", "最后保持")):
            continue
        seen.add(normalized)
        result.append(clause)
    return result


def _remove_owned_dialogue_clauses(
    text: str, dialogue: Sequence[Any]
) -> str:
    cleaned = text
    for dialogue_text in _dialogue_texts(dialogue):
        for left_quote, right_quote in (("“", "”"), ('"', '"')):
            literal = f"{left_quote}{dialogue_text}{right_quote}"
            cleaned = cleaned.replace(f"：{literal}", "。")
            cleaned = cleaned.replace(f":{literal}", ".")
            cleaned = cleaned.replace(literal, "")
            quoted = (
                re.escape(left_quote)
                + re.escape(dialogue_text)
                + re.escape(right_quote)
            )
            cleaned = re.sub(
                rf"[^。！？；\n]*?(?:说|问|答|喊|道|开口|回应|画外)[^。！？；\n]*?[：:]?\s*{quoted}",
                "",
                cleaned,
            )
    cleaned = re.sub(r"[：:]\s*(?=[^“\"\s])", "；", cleaned)
    cleaned = re.sub(r"[；;]{2,}", "；", cleaned)
    return cleaned.strip(" \n；")


def _camera_detail_without_owned_facts(
    value: Any,
    owned_facts: Sequence[Any],
) -> str:
    clauses: list[str] = []
    normalized_owned = [
        _normalized_fact_text(fact)
        for fact in owned_facts
        if _normalized_fact_text(fact)
    ]
    for segment in re.split(r"[，,]", _clean_text(value)):
        normalized_segment = _normalized_fact_text(segment)
        if any(fact in normalized_segment for fact in normalized_owned):
            continue
        clauses.extend(
            _novel_clauses(
                segment,
                owned_facts,
                drop_camera_clauses=False,
            )
        )
    return "".join(clauses).strip(" \n；")


def _shot_main_state_change(shot: Mapping[str, Any]) -> str:
    """Select exactly one source-backed state change for a Prompt stage."""
    camera = shot.get("camera", {})
    camera = camera if isinstance(camera, dict) else {}
    candidates: list[Any] = list(reversed(shot.get("end_state", [])))
    candidates.append(camera.get("end_frame"))
    candidates.extend(reversed(shot.get("blocking", [])))
    candidates.extend(
        (
            shot.get("delta_text"),
            _split_environment_and_action(shot)[1],
        )
    )
    for value in candidates:
        rendered = _preserve_text(_render_descriptive_value(value))
        if rendered:
            return rendered
    return ""


def _shot_start_state(shot: Mapping[str, Any]) -> str:
    """Select a real opening state without borrowing edit entry metadata."""
    camera = shot.get("camera", {})
    camera = camera if isinstance(camera, dict) else {}
    candidates: list[Any] = [camera.get("start_frame")]
    candidates.extend(shot.get("start_state", []))
    candidates.extend(shot.get("blocking", []))
    candidates.extend(shot.get("visible_behavior", []))
    candidates.append(_shot_main_state_change(shot))
    for value in candidates:
        rendered = _preserve_text(_render_descriptive_value(value))
        if rendered:
            return rendered
    return ""


def _legacy_structured_t2v_prompt_parts(
    parts: list[str], shot: Mapping[str, Any]
) -> None:
    """Keep the established field-oriented compiler for non-2.5 adapters."""
    camera = shot.get("camera", {})
    camera = camera if isinstance(camera, dict) else {}
    position = _preserve_text(
        _render_descriptive_value(camera.get("position"))
    )
    logic = (
        ""
        if position
        else _preserve_text(_render_descriptive_value(camera.get("logic")))
    )
    start_frame = _preserve_text(
        _render_descriptive_value(camera.get("start_frame"))
    )
    end_frame = _preserve_text(
        _render_descriptive_value(camera.get("end_frame"))
    )
    if position:
        _append_unique(parts, position, "摄影机位置")
    if logic:
        _append_unique(parts, logic, "摄影机逻辑")
    _append_unique(
        parts,
        _preserve_text(_render_descriptive_value(camera.get("lens_intent"))),
        "透视意图",
    )
    _append_unique(
        parts,
        _preserve_text(_render_descriptive_value(camera.get("focus"))),
        "焦点",
    )
    _append_unique(
        parts,
        _preserve_text(
            _render_descriptive_value(camera.get("lighting_change"))
        ),
        "光线变化",
    )
    if start_frame and _normalized_fact_text(start_frame) == _normalized_fact_text(end_frame):
        _append_unique(parts, start_frame, "状态")
    elif start_frame:
        _append_unique(parts, start_frame, "起始状态")
    movement_plan = camera.get("movement_plan")
    movement_plan = movement_plan if isinstance(movement_plan, dict) else {}
    movement = _preserve_text(
        _render_descriptive_value(camera.get("movement"))
    )
    movement_parts: list[str] = []
    for label, value in (
        ("方式", movement),
        ("速度", movement_plan.get("speed")),
        ("路径", movement_plan.get("path")),
        ("触发", movement_plan.get("trigger")),
        ("停止", movement_plan.get("end_condition")),
        ("保持", movement_plan.get("hold_reason")),
    ):
        rendered = _preserve_text(_render_descriptive_value(value))
        if rendered:
            movement_parts.append(f"{label}：{rendered}")
    if movement_parts:
        _append_unique(parts, "；".join(movement_parts), "摄影机运动")
    _append_items(parts, shot.get("blocking", []), "动作")
    _append_items(parts, shot.get("visible_behavior", []), "表演")
    represented: list[Any] = [
        position,
        logic,
        start_frame,
        end_frame,
        movement,
    ]
    represented.extend(shot.get("blocking", []))
    represented.extend(shot.get("visible_behavior", []))
    _, rendered_action = _split_environment_and_action(shot)
    rendered_action = _remove_owned_dialogue_clauses(
        rendered_action, shot.get("dialogue", [])
    )
    for clause in _novel_clauses(rendered_action, represented):
        _append_unique(parts, clause, "补充画面")
    if end_frame and _normalized_fact_text(start_frame) != _normalized_fact_text(end_frame):
        _append_unique(parts, end_frame, "终态")
    for state in shot.get("end_state", []):
        if _normalized_fact_text(state) not in {
            _normalized_fact_text(start_frame),
            _normalized_fact_text(end_frame),
        }:
            _append_unique(
                parts,
                _preserve_text(_render_descriptive_value(state)),
                "终态补充",
            )


def _movement_prompt_sentences(
    movement: str,
    speed: str,
    path: str,
    trigger: str,
    end_condition: str,
    hold_reason: str,
) -> list[str]:
    sentences: list[str] = []
    if movement == "固定":
        sentences.append("镜头固定。")
        boundary_bits: list[str] = []
        if trigger:
            boundary_bits.append(f"在{trigger}开始固定观察")
        if end_condition:
            boundary_bits.append(f"至{end_condition}结束")
        if boundary_bits:
            sentences.append(_with_terminal_punctuation("，".join(boundary_bits)))
        if hold_reason.startswith("固定"):
            hold_reason = hold_reason[len("固定") :].lstrip("，,：:；; ")
        if hold_reason:
            sentences.append(_with_terminal_punctuation(hold_reason))
        return sentences

    movement_bits: list[str] = []
    if movement:
        movement_bits.append(f"镜头{movement}")
    if speed:
        movement_bits.append(f"速度{speed}")
    if path:
        movement_bits.append(path)
    if trigger:
        movement_bits.append(f"在{trigger}启动")
    if end_condition:
        movement_bits.append(
            end_condition
            if end_condition.endswith("停止")
            else f"至{end_condition}停止"
        )
    if movement_bits:
        sentences.append(_with_terminal_punctuation("，".join(movement_bits)))
    if hold_reason:
        sentences.append(_with_terminal_punctuation(hold_reason))
    return sentences


def _structured_t2v_prompt_parts(
    parts: list[str], shot: Mapping[str, Any]
) -> None:
    """Compile one Cut as a readable stage instead of a field dump."""
    camera = shot.get("camera", {})
    camera = camera if isinstance(camera, dict) else {}
    position = _preserve_text(
        _render_descriptive_value(camera.get("position"))
    )
    logic = _preserve_text(_render_descriptive_value(camera.get("logic")))
    start_frame = _preserve_text(
        _render_descriptive_value(camera.get("start_frame"))
    )
    end_frame = _preserve_text(
        _render_descriptive_value(camera.get("end_frame"))
    )
    main_change = _shot_main_state_change(shot)

    if start_frame and _normalized_fact_text(start_frame) != _normalized_fact_text(
        main_change
    ):
        _append_unique(parts, start_frame)

    if position:
        _append_unique(parts, _camera_position_sentence(position))
    elif logic:
        _append_unique(parts, logic)

    movement_plan = camera.get("movement_plan")
    movement_plan = movement_plan if isinstance(movement_plan, dict) else {}
    movement = _preserve_text(
        _render_descriptive_value(camera.get("movement"))
    )
    speed = _preserve_text(
        _render_descriptive_value(movement_plan.get("speed"))
    )
    path = _preserve_text(
        _render_descriptive_value(movement_plan.get("path"))
    )
    if position and path:
        path = path.replace(f"从{position}沿", "沿")
        path = path.replace(f"在{position}", "在既定机位")
        path = path.replace(position, "既定机位")
        path = path.replace("从既定机位沿", "沿")
    trigger = _preserve_text(
        _render_descriptive_value(movement_plan.get("trigger"))
    )
    if (
        start_frame
        and _normalized_fact_text(start_frame)
        in _normalized_fact_text(trigger)
    ):
        trigger = "起始动作发生时"
    end_condition = _preserve_text(
        _render_descriptive_value(movement_plan.get("end_condition"))
    )
    if (
        end_frame
        and _normalized_fact_text(end_frame)
        in _normalized_fact_text(end_condition)
    ):
        end_condition = "主要状态形成时停止"
    hold_reason = _preserve_text(
        _render_descriptive_value(movement_plan.get("hold_reason"))
    )
    same_boundary_state = (
        bool(start_frame)
        and _normalized_fact_text(start_frame)
        == _normalized_fact_text(end_frame)
    )
    if hold_reason and same_boundary_state:
        hold_reason = "固定观察直到主要状态形成，并保持动作、声音或表演连续"
    else:
        if end_frame:
            hold_reason = _replace_owned_fact_variant(
                hold_reason, end_frame, "主要状态形成"
            )
        if start_frame:
            hold_reason = _replace_owned_fact_variant(
                hold_reason, start_frame, "起始状态"
            )
    for sentence in _movement_prompt_sentences(
        movement,
        speed,
        path,
        trigger,
        end_condition,
        hold_reason,
    ):
        _append_unique(parts, sentence)

    spatial_strategy = camera.get("spatial_strategy")
    spatial_strategy = (
        spatial_strategy if isinstance(spatial_strategy, dict) else {}
    )
    spatial_description = _camera_detail_without_owned_facts(
        spatial_strategy.get("description"),
        (position, start_frame, end_frame),
    )
    watching_path = re.search(r"(观看先.+)$", spatial_description)
    if watching_path:
        spatial_description = watching_path.group(1)
    if spatial_description and not re.search(
        r"观看先落在(.+?)再转向\1(?:[。；]|$)", spatial_description
    ):
        _append_unique(parts, spatial_description)

    lens_intent = _preserve_text(
        _render_descriptive_value(camera.get("lens_intent"))
    )
    focus = _preserve_text(
        _render_descriptive_value(camera.get("focus"))
    )
    lighting_change = _preserve_text(
        _render_descriptive_value(camera.get("lighting_change"))
    )
    _append_unique(parts, lens_intent)
    _append_unique(parts, focus)
    _append_unique(parts, lighting_change)

    for value in shot.get("blocking", []):
        rendered = _preserve_text(_render_descriptive_value(value))
        if _normalized_fact_text(rendered) != _normalized_fact_text(main_change):
            _append_unique(parts, rendered)
    _append_items(parts, shot.get("visible_behavior", []), "")

    represented_facts: list[Any] = [
        position,
        logic,
        start_frame,
        end_frame,
        movement,
        speed,
        path,
        trigger,
        end_condition,
        hold_reason,
        spatial_description,
        lens_intent,
        focus,
        lighting_change,
        main_change,
    ]
    represented_facts.extend(shot.get("blocking", []))
    represented_facts.extend(shot.get("visible_behavior", []))
    represented_facts.extend(_dialogue_texts(shot.get("dialogue", [])))
    if _clean_text(shot.get("rendered_shot_description")):
        _, rendered_action = _split_environment_and_action(shot)
        rendered_action = _remove_owned_dialogue_clauses(
            rendered_action, shot.get("dialogue", [])
        )
        normalized_represented = [
            _normalized_fact_text(value)
            for value in represented_facts
            if _normalized_fact_text(value)
        ]
        for clause in _novel_clauses(rendered_action, represented_facts):
            normalized_clause = _normalized_fact_text(clause)
            if any(
                len(fact) >= 4 and fact in normalized_clause
                for fact in normalized_represented
            ):
                continue
            _append_unique(parts, clause)

    if main_change:
        _append_unique(parts, main_change, "主要状态变化")
    for state in shot.get("end_state", []):
        if _normalized_fact_text(state) not in {
            _normalized_fact_text(start_frame),
            _normalized_fact_text(main_change),
        }:
            _append_unique(
                parts,
                _preserve_text(_render_descriptive_value(state)),
            )


def _clean_scene_label(scene_context: Any) -> str:
    if not isinstance(scene_context, dict):
        return ""
    label = _preserve_text(
        _render_descriptive_value(scene_context.get("scene"))
    )
    if label:
        return re.sub(
            r"^\s*(?:SC\d+|\d+(?:-\d+)*)(?:\s*[.．、:：-]\s*)?",
            "",
            label,
            flags=re.IGNORECASE,
        ).strip()
    return " ".join(
        item
        for item in (
            _preserve_text(
                _render_descriptive_value(scene_context.get("location"))
            ),
            _preserve_text(
                _render_descriptive_value(
                    scene_context.get("time_of_day")
                    or scene_context.get("time")
                )
            ),
        )
        if item
    )


def _unit_scene_line(shots: Sequence[Mapping[str, Any]]) -> str:
    labels: list[str] = []
    environments: list[str] = []
    for shot in shots:
        scene_context = shot.get("scene_context")
        label = _clean_scene_label(scene_context)
        if label and label not in labels:
            labels.append(label)
        if isinstance(scene_context, dict):
            for key in ("location", "time_of_day", "time"):
                context_value = _preserve_text(
                    _render_descriptive_value(scene_context.get(key))
                )
                if (
                    context_value
                    and context_value not in label
                    and context_value not in labels
                ):
                    labels.append(context_value)
        context_environment = ""
        if isinstance(scene_context, dict):
            context_environment = _preserve_text(
                _render_descriptive_value(
                    scene_context.get("environment_description")
                    or scene_context.get("environment")
                )
            )
        rendered_environment, _ = _split_environment_and_action(shot)
        environment = context_environment or rendered_environment
        if (
            label
            and _normalized_fact_text(label)
            in _normalized_fact_text(environment)
        ):
            environment = ""
        for existing_label in labels:
            if _normalized_fact_text(environment) == _normalized_fact_text(
                existing_label
            ):
                environment = ""
                break
        if environment and environment not in environments:
            environments.append(environment)
        for item in shot.get("scene_material", []):
            rendered_item = _preserve_text(
                _render_descriptive_value(item)
            )
            if rendered_item and rendered_item not in environments:
                environments.append(rendered_item)
    scene_parts = labels + environments
    if not scene_parts:
        return ""
    line = "场景：" + "，".join(scene_parts)
    return _with_terminal_punctuation(line)


def _transition_text(transition: Mapping[str, Any]) -> str:
    transition_type = _clean_text(transition.get("type"))
    notes = _clean_text(transition.get("notes"))
    if transition_type in ("", "cut", "scene_end") and not notes:
        return ""
    if transition_type and notes:
        return f"转场：{transition_type}，{notes}"
    return f"转场：{transition_type or notes}"


def _reference_roles_for_shot(
    generation: Mapping[str, Any], shot_id: str
) -> list[Mapping[str, Any]]:
    return [
        item
        for item in generation.get("reference_role_map", [])
        if isinstance(item, dict)
        and (
            "*" in item.get("applies_to_shot_ids", [])
            or shot_id in item.get("applies_to_shot_ids", [])
        )
    ]


def _all_generation_reference_tags(
    generation: Mapping[str, Any]
) -> list[str]:
    return _unique_strings(
        str(item.get("tag"))
        for item in generation.get("reference_role_map", [])
        if isinstance(item, dict) and _clean_text(item.get("tag"))
    )


def _global_reference_section(profile: Mapping[str, Any]) -> bool:
    return (
        profile.get("prompt_adapter_id")
        == "seedance-2.5-structured-zh-v1"
    )


def _generation_for_unit(
    generation: Mapping[str, Any],
    shots: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    shot_ids = {
        _clean_text(shot.get("source_shot_id")) for shot in shots
    }

    def applies(item: Mapping[str, Any]) -> bool:
        scope = item.get("applies_to_shot_ids", [])
        return isinstance(scope, list) and (
            "*" in scope or bool(shot_ids.intersection(scope))
        )

    result = copy.deepcopy(dict(generation))
    roles = [
        copy.deepcopy(item)
        for item in generation.get("reference_role_map", [])
        if isinstance(item, dict) and applies(item)
    ]
    assignments = [
        copy.deepcopy(item)
        for item in generation.get("asset_assignments", [])
        if isinstance(item, dict) and applies(item)
    ]
    result["reference_role_map"] = roles
    result["asset_assignments"] = assignments
    result["available_reference_tags"] = _unique_strings(
        _clean_text(item.get("tag")) for item in roles
    )
    return result


def _reference_instruction(item: Mapping[str, Any]) -> str:
    tag = str(item["tag"])
    role = str(item["role"])
    if role == "first_frame":
        return f"{tag}作为首帧。"
    if role == "last_frame":
        return f"{tag}作为尾帧。"
    role_label = REFERENCE_ROLE_LABELS.get(role, role)
    qualifier = "仅作" if role in {"motion_reference", "camera_motion"} else "作为"
    preserve = [
        _preserve_text(_clean_text(value))
        for value in item.get("preserve", [])
        if _preserve_text(_clean_text(value))
    ]
    preserve_text = f"，保持 {'、'.join(preserve)}" if preserve else ""
    return f"{tag} {qualifier}{role_label}{preserve_text}"


def _append_unique(parts: list[str], text: str, label: str = "") -> None:
    cleaned = _preserve_text(text)
    if not cleaned:
        return
    rendered = f"{label}：{cleaned}" if label else cleaned
    if cleaned not in "；".join(parts):
        parts.append(rendered)


def _append_items(
    parts: list[str], values: Sequence[Any], label: str
) -> None:
    rendered = [
        _preserve_text(_render_descriptive_value(item))
        for item in values
    ]
    rendered = [item for item in rendered if item]
    for item in rendered:
        _append_unique(parts, item, label)


def _append_visible_subject_sentence(
    parts: list[str], shot: Mapping[str, Any]
) -> None:
    visible_subjects = [
        _preserve_text(_render_descriptive_value(item))
        for item in shot.get("visible_subjects", [])
    ]
    visible_subjects = [item for item in visible_subjects if item]
    if not visible_subjects:
        return
    camera = shot.get("camera", {})
    camera = camera if isinstance(camera, dict) else {}
    existing = _normalized_fact_text(
        "；".join(parts)
        + "；"
        + _preserve_text(_render_descriptive_value(camera.get("composition")))
    )
    missing = [
        item
        for item in visible_subjects
        if _normalized_fact_text(item) not in existing
    ]
    if missing:
        _append_unique(parts, "画面主体：" + "、".join(missing))


def _join_prompt_parts(parts: Sequence[str]) -> str:
    joined = ""
    for part in parts:
        if not joined:
            joined = part
            continue
        separator = "" if _has_terminal_punctuation(joined) else "；"
        joined += separator + part
    return joined


def _append_scene_context(parts: list[str], scene_context: Any) -> None:
    if not isinstance(scene_context, dict):
        return
    labels = (
        ("scene", "场景"),
        ("location", "地点"),
        ("time", "时间"),
        ("time_of_day", "时段"),
        ("reality_layer", "现实层"),
        ("environment", "环境"),
        ("environment_description", "环境"),
    )
    for key, label in labels:
        rendered = _render_descriptive_value(scene_context.get(key))
        if rendered:
            _append_unique(parts, rendered, label)


def _render_continuity_update(value: Any) -> str:
    if not isinstance(value, dict):
        return _render_descriptive_value(value)
    entity_type = _clean_text(value.get("entity_type"))
    entity = _clean_text(value.get("entity"))
    field = _clean_text(value.get("field"))
    before = _clean_text(value.get("from"))
    after = _clean_text(value.get("to"))
    if not any((entity_type, entity, field, before, after)):
        return canonical_json(value)
    subject = "／".join(
        item for item in (entity_type, entity, field) if item
    )
    change = f"{before} → {after}" if before or after else ""
    rendered = "：".join(item for item in (subject, change) if item)
    evidence = value.get("evidence_fact_ids")
    if isinstance(evidence, list) and evidence:
        rendered += "（证据：" + "、".join(str(item) for item in evidence) + "）"
    return rendered


def _append_continuity_updates(parts: list[str], updates: Any) -> None:
    if not isinstance(updates, list):
        return
    rendered = [
        _preserve_text(_render_continuity_update(item))
        for item in updates
    ]
    rendered = [item for item in rendered if item]
    if rendered:
        _append_unique(parts, "；".join(rendered), "连续性变化")


def _has_structured_visual_equivalent(shot: Mapping[str, Any]) -> bool:
    return any(
        (
            bool(shot.get("blocking")),
            bool(shot.get("visible_behavior")),
            bool(shot.get("dialogue")),
            bool(shot.get("delta_text")),
            bool(shot.get("continuity_updates")),
            bool(shot.get("allowed_lighting_changes")),
        )
    )
