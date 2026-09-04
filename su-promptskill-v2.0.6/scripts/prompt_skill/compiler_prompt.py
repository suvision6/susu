"""su-promptskill internal module: Cut and Prompt compilation."""

from __future__ import annotations

from . import compiler_facts as _previous

globals().update({
    key: value
    for key, value in vars(_previous).items()
    if not key.startswith("__")
})

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Responsibility module behind scripts/prompt_delivery.py."


def _cut_sound_item(value: Any) -> str:
    rendered = _preserve_text(_render_descriptive_value(value))
    while rendered.startswith("声音："):
        rendered = rendered[len("声音：") :].lstrip()
    if rendered.startswith("声音视点："):
        rendered = "视点：" + rendered[len("声音视点：") :]
    return rendered


def _append_consolidated_cut_sound(
    parts: list[str], values: Sequence[Any]
) -> None:
    existing_text = "；".join(parts)
    sound_items: list[str] = []
    seen: set[str] = set()
    for value in values:
        source_text = _preserve_text(_render_descriptive_value(value))
        if not source_text or source_text in existing_text:
            continue
        rendered = _cut_sound_item(value)
        normalized = _normalized_fact_text(rendered)
        if not rendered or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        sound_items.append(rendered)
    if sound_items:
        _append_unique(parts, _join_prompt_parts(sound_items), "声音")


def _shot_prompt_content(
    shot: Mapping[str, Any],
    emotion_visualization: Sequence[Mapping[str, str]],
    generation: Mapping[str, Any],
    *,
    include_reference_roles: bool = True,
) -> str:
    parts: list[str] = []
    mode = str(generation.get("mode", "t2v"))
    shot_id = str(shot["source_shot_id"])
    reference_roles = _reference_roles_for_shot(generation, shot_id)
    camera = shot.get("camera", {})
    camera = camera if isinstance(camera, dict) else {}
    position = _preserve_text(
        _render_descriptive_value(camera.get("position"))
    )
    camera_logic = _preserve_text(
        _render_descriptive_value(camera.get("logic"))
    )
    seedance_generation = (
        mode in {"t2v", "i2v", "v2v", "r2v", "flf2v"}
        and generation.get("global_reference_section") is True
    )
    if mode == "t2v" and not seedance_generation:
        _legacy_structured_t2v_prompt_parts(parts, shot)
        _append_items(parts, shot.get("visible_props", []), "可见道具")
        _append_items(
            parts,
            [
                _render_continuity_update(item)
                for item in shot.get("continuity_updates", [])
            ],
            "",
        )
        lighting_style = shot.get("lighting_style", {})
        if isinstance(lighting_style, dict):
            _append_unique(
                parts,
                _render_descriptive_value(lighting_style.get("lighting")),
            )
            _append_unique(
                parts,
                _render_descriptive_value(lighting_style.get("style")),
            )
    elif seedance_generation:
        _structured_t2v_prompt_parts(parts, shot)
        if not {
            str(item["role"]) for item in reference_roles
        }.intersection({"subject_identity", "appearance"}):
            _append_visible_subject_sentence(parts, shot)
        if include_reference_roles:
            for item in reference_roles:
                parts.append(_reference_instruction(item))
        _append_items(
            parts, shot.get("visible_props", []), "可见道具"
        )
        _append_items(
            parts,
            [
                _render_continuity_update(item)
                for item in shot.get("continuity_updates", [])
            ],
            "",
        )
        lighting_style = shot.get("lighting_style", {})
        if isinstance(lighting_style, dict):
            lighting = _render_descriptive_value(
                lighting_style.get("lighting")
            )
            style = _render_descriptive_value(lighting_style.get("style"))
            _append_unique(parts, lighting)
            _append_unique(parts, style)
    else:
        if position:
            camera_text = _camera_position_sentence(position)
            if camera_logic:
                camera_text += f"，{camera_logic}"
            _append_unique(parts, camera_text)
        elif camera_logic:
            _append_unique(parts, camera_logic)
        if include_reference_roles:
            for item in reference_roles:
                parts.append(_reference_instruction(item))
        reference_role_names = {str(item["role"]) for item in reference_roles}
        if mode == "edit":
            for delta in generation.get("edit_deltas", []):
                if not isinstance(delta, dict):
                    continue
                applies = delta.get("applies_to_shot_ids", [])
                if applies and shot_id not in applies:
                    continue
                instruction = _clean_text(delta.get("instruction"))
                layer = _clean_text(delta.get("layer"))
                _append_unique(parts, instruction, f"仅修改 {layer}")
        if mode == "extend":
            extend_context = generation.get("extend_context", {})
            extend_context = (
                extend_context if isinstance(extend_context, dict) else {}
            )
            direction = _clean_text(extend_context.get("direction"))
            boundary = _clean_text(
                extend_context.get("boundary_state")
                or extend_context.get("observed_end_state")
            )
            parts.append(
                (
                    f"从已接受素材的{boundary}向{direction}连续延长"
                    if direction and boundary
                    else "从已接受素材的观测边界状态连续延长"
                )
            )
            for key, label in (
                ("motion_trend", "保持运动趋势"),
                ("audio_state", "保持边界声音状态"),
                ("single_instance", "保持连续主体"),
            ):
                value = _clean_text(extend_context.get(key))
                if value:
                    _append_unique(parts, value, label)
        if not reference_role_names & {"subject_identity", "appearance"}:
            _append_items(parts, shot.get("subjects", []), "")
        rendered_description = _clean_text(
            shot.get("rendered_shot_description")
        )
        if (
            rendered_description
            and not _has_structured_visual_equivalent(shot)
        ):
            _append_unique(
                parts, _split_environment_and_action(shot)[1]
            )
        _append_unique(parts, _clean_text(shot.get("delta_text")))
        _append_items(parts, shot.get("blocking", []), "")
        _append_items(
            parts, shot.get("visible_behavior", []), ""
        )
        _append_items(
            parts, shot.get("visible_props", []), "可见道具"
        )
        _append_items(
            parts,
            [
                _render_continuity_update(item)
                for item in shot.get("continuity_updates", [])
            ],
            "",
        )
        _append_items(
            parts,
            shot.get("allowed_lighting_changes", []),
            "允许的光线变化",
        )

    for item in shot.get("dialogue", []):
        rendered = _render_dialogue(item)
        text = (
            _clean_text(item.get("text"))
            if isinstance(item, dict)
            else _clean_text(item)
        )
        if rendered and text:
            parts.append(rendered)
    if generation.get("global_reference_section") is True:
        _append_consolidated_cut_sound(parts, shot.get("audio", []))
    else:
        _append_items(parts, shot.get("audio", []), "声音")
    _append_items(parts, shot.get("constraints", []), "约束")

    if mode != "edit":
        for item in emotion_visualization:
            text = _clean_text(item.get("text"))
            if text:
                _append_unique(parts, text, "情绪可视化（下游派生）")

    return _join_prompt_parts(parts)


def _goal_fragment(value: str) -> str:
    fragment = value.strip().rstrip("。！？；")
    fragment = re.sub(r"[。；]+", "，", fragment)
    return re.sub(r"，{2,}", "，", fragment).strip("， ")


def _prompt_goal(
    shots: Sequence[Mapping[str, Any]], generation: Mapping[str, Any]
) -> str:
    story_contract = generation.get("story_contract", {})
    if isinstance(story_contract, dict):
        for key in ("generation_goal", "summary", "logline", "overview"):
            value = _preserve_text(
                _render_descriptive_value(story_contract.get(key))
            )
            if value:
                return _with_terminal_punctuation(value)
    mode = _clean_text(generation.get("mode"))
    if mode == "edit":
        return "只修改唯一编辑母版中明确指定的对象和范围，继承原有时间线。"
    if mode == "extend":
        context = generation.get("extend_context", {})
        context = context if isinstance(context, dict) else {}
        direction = _clean_text(context.get("direction"))
        if direction:
            return f"从唯一延长源的边界向{direction}连续延长，只生成边界之外的新片段。"
        return "从唯一延长源的既定边界连续延长，只生成边界之外的新片段。"

    scenes = _unique_strings(
        _clean_scene_label(shot.get("scene_context")) for shot in shots
    )
    scene_text = "、".join(scenes) or "既定场景"
    first_change = _shot_start_state(shots[0]) if shots else ""
    final_change = _shot_main_state_change(shots[-1]) if shots else ""
    if first_change and final_change:
        first_fragment = _goal_fragment(first_change)
        final_fragment = _goal_fragment(final_change)
        if _normalized_fact_text(first_change) == _normalized_fact_text(
            final_change
        ):
            return _with_terminal_punctuation(
                f"既定场景：{scene_text}。核心画面：{first_fragment}"
            )
        return _with_terminal_punctuation(
            f"既定场景：{scene_text}。开场画面：{first_fragment}。"
            f"按既定 Cut 顺序推进。收束画面：{final_fragment}"
        )
    if first_change or final_change:
        return _with_terminal_punctuation(
            f"在{scene_text}中，{first_change or final_change}"
        )
    return f"在{scene_text}中按既定事件顺序推进并到达来源最终状态。"


def _subject_relationship_lines(
    shots: Sequence[Mapping[str, Any]], generation: Mapping[str, Any]
) -> list[str]:
    story_contract = generation.get("story_contract", {})
    result: list[str] = []
    if isinstance(story_contract, dict):
        for key in ("subjects", "relationships"):
            values = story_contract.get(key, [])
            if isinstance(values, list):
                for value in values:
                    rendered = _preserve_text(
                        _render_descriptive_value(value)
                    )
                    if rendered and rendered not in result:
                        result.append(rendered)
    if result:
        return result
    fallback_subjects: list[str] = []
    for shot in shots:
        for value in shot.get("subjects", []):
            rendered = _preserve_text(_render_descriptive_value(value))
            if rendered and rendered not in fallback_subjects:
                fallback_subjects.append(rendered)
        camera = shot.get("camera", {})
        camera = camera if isinstance(camera, dict) else {}
        primary = camera.get("primary_subjects", [])
        primary = primary if isinstance(primary, list) else []
        for value in primary:
            rendered = _preserve_text(_render_descriptive_value(value))
            if rendered and rendered not in fallback_subjects:
                fallback_subjects.append(rendered)
    if fallback_subjects:
        result.append("本单元核心主体：" + "、".join(fallback_subjects[:10]))
    return result


def _continuity_lines(
    shots: Sequence[Mapping[str, Any]], generation: Mapping[str, Any]
) -> list[str]:
    story_contract = generation.get("story_contract", {})
    preserve = (
        story_contract.get("preserve", [])
        if isinstance(story_contract, dict)
        else []
    )
    result = [
        _preserve_text(_render_descriptive_value(value))
        for value in preserve
        if _preserve_text(_render_descriptive_value(value))
    ]
    if not result:
        result.append(
            "相邻 Cut 只承接来源已经给出的主体、道具、空间、"
            "摄影机与声音状态，不交换主体、道具或对白。"
        )
    return _unique_strings(result)


def _asset_responsibility_lines(
    generation: Mapping[str, Any],
) -> list[str]:
    binding = generation.get("asset_binding", {})
    if not isinstance(binding, dict) or binding.get("state") != "mapped":
        return []
    assignments = [
        item
        for item in generation.get("asset_assignments", [])
        if isinstance(item, dict)
    ]
    lines: list[str] = []
    for item in assignments:
        tag = _clean_text(item.get("tag"))
        target = _clean_text(item.get("target_entity"))
        role = _clean_text(item.get("role"))
        adopted = [
            _clean_text(value)
            for value in item.get("adopted_dimensions", [])
            if _clean_text(value)
        ]
        rejected = [
            _clean_text(value)
            for value in item.get("rejected_dimensions", [])
            if _clean_text(value)
        ]
        if not tag:
            continue
        if role == "first_frame":
            text = f"{tag}作为首帧"
        elif role == "last_frame":
            text = f"{tag}作为尾帧"
        elif role == "edit_source":
            text = f"{tag}作为唯一编辑母版"
            if target:
                text += f"，用于{target}"
        elif role == "extension_source":
            text = f"{tag}作为唯一延长源"
            if target:
                text += f"，用于{target}"
        else:
            text = f"{tag}用于{target}" if target else tag
        if adopted and role not in {"first_frame", "last_frame"}:
            text += f"的{'、'.join(adopted)}"
        if rejected:
            text += f"，不采用{'、'.join(rejected)}"
        lines.append(_with_terminal_punctuation(text))
    if lines:
        return _unique_strings(lines)
    return [
        _with_terminal_punctuation(_reference_instruction(item))
        for item in generation.get("reference_role_map", [])
        if isinstance(item, dict)
    ]


def _subject_relationship_scene_lines(
    shots: Sequence[Mapping[str, Any]], generation: Mapping[str, Any]
) -> list[str]:
    result = _subject_relationship_lines(shots, generation)
    scene_lines: list[str] = []
    prop_values: list[str] = []
    for shot in shots:
        context = shot.get("scene_context", {})
        if isinstance(context, dict):
            values: list[str] = []
            for key in (
                "scene",
                "location",
                "time",
                "time_of_day",
                "environment",
                "environment_description",
            ):
                value = (
                    _clean_scene_label(context)
                    if key == "scene"
                    else _preserve_text(
                        _render_descriptive_value(context.get(key))
                    )
                )
                if value and value not in values:
                    values.append(value)
            if values:
                line = "场景与空间：" + "，".join(values)
                if line not in scene_lines:
                    scene_lines.append(line)
        for raw_prop in shot.get("visible_props", []):
            prop = _preserve_text(_render_descriptive_value(raw_prop))
            if prop and prop not in prop_values:
                prop_values.append(prop)
    result.extend(scene_lines)
    if prop_values:
        result.append("关键道具以来源状态为准：" + "、".join(prop_values))
    return _unique_strings(result) or [
        "本单元主体、关系与场景均以来源事实为准。"
    ]


def _boundary_handoff_line(
    previous_shot: Mapping[str, Any],
    current_shot: Mapping[str, Any],
    previous_cut_label: str,
) -> str:
    previous_camera = previous_shot.get("camera", {})
    previous_camera = previous_camera if isinstance(previous_camera, dict) else {}
    current_camera = current_shot.get("camera", {})
    current_camera = current_camera if isinstance(current_camera, dict) else {}
    previous_end = _preserve_text(
        _render_descriptive_value(previous_camera.get("end_frame"))
    )
    if not previous_end:
        for value in reversed(previous_shot.get("end_state", [])):
            previous_end = _preserve_text(_render_descriptive_value(value))
            if previous_end:
                break
    current_start = _preserve_text(
        _render_descriptive_value(current_camera.get("start_frame"))
    )
    if (
        previous_end
        and current_start
        and _normalized_fact_text(previous_end)
        == _normalized_fact_text(current_start)
    ):
        return _with_terminal_punctuation(
            f"承接 {previous_cut_label} 的{current_start.rstrip('。！？；')}"
        )
    return ""


def _cross_cut_sound_lines(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    generation: Mapping[str, Any],
) -> list[str]:
    if len(shots) < 2:
        return []
    speaker_cuts: dict[str, set[str]] = {}
    sound_cuts: dict[str, set[str]] = {}
    constraint_cuts: dict[str, set[str]] = {}
    for shot, cut in zip(shots, timeline):
        cut_label = str(cut.get("cut_label", "Cut"))
        for item in shot.get("dialogue", []):
            if isinstance(item, dict):
                speaker = _clean_text(
                    item.get("speaker") or item.get("character")
                )
                if speaker:
                    speaker_cuts.setdefault(speaker, set()).add(cut_label)
        for item in shot.get("audio", []):
            rendered = _preserve_text(_render_descriptive_value(item))
            if rendered:
                sound_cuts.setdefault(rendered, set()).add(cut_label)
        for item in shot.get("constraints", []):
            rendered = _preserve_text(_render_descriptive_value(item))
            if rendered:
                constraint_cuts.setdefault(rendered, set()).add(cut_label)

    cross_speakers = {
        speaker for speaker, cuts in speaker_cuts.items() if len(cuts) > 1
    }
    cross_sounds = {
        sound for sound, cuts in sound_cuts.items() if len(cuts) > 1
    }
    cross_constraints = {
        value for value, cuts in constraint_cuts.items() if len(cuts) > 1
    }
    lines: list[str] = []
    for shot, cut in zip(shots, timeline):
        cut_label = str(cut.get("cut_label", "Cut"))
        for item in shot.get("dialogue", []):
            if not isinstance(item, dict):
                continue
            speaker = _clean_text(
                item.get("speaker") or item.get("character")
            )
            if speaker not in cross_speakers:
                continue
            rendered = _render_dialogue(item)
            if not rendered:
                continue
            position = _clean_text(
                item.get("shot_delivery")
                or item.get("position")
                or item.get("on_screen")
            )
            qualifier = f"（{position}）" if position else ""
            lines.append(f"{cut_label}{qualifier}：{rendered}")
    for sound in sorted(cross_sounds):
        cuts = sorted(sound_cuts[sound], key=lambda value: int(re.sub(r"\D", "", value) or 0))
        lines.append(f"{'、'.join(cuts)}保持同一声音来源：{sound}")
    for value in sorted(cross_constraints):
        cuts = sorted(constraint_cuts[value], key=lambda item: int(re.sub(r"\D", "", item) or 0))
        lines.append(f"{'、'.join(cuts)}共同遵守：{value}")
    for assignment in generation.get("asset_assignments", []):
        if not isinstance(assignment, dict) or _clean_text(
            assignment.get("role")
        ) != "audio_reference":
            continue
        scope = assignment.get("applies_to_shot_ids", [])
        applicable = [
            str(cut.get("cut_label"))
            for shot, cut in zip(shots, timeline)
            if "*" in scope or str(shot.get("source_shot_id")) in scope
        ]
        if len(applicable) < 2:
            continue
        tag = _clean_text(assignment.get("tag"))
        target = _clean_text(assignment.get("target_entity"))
        adopted = [
            _clean_text(value)
            for value in assignment.get("adopted_dimensions", [])
            if _clean_text(value)
        ]
        text = f"{tag}用于{target}" if target else tag
        if adopted:
            text += f"的{'、'.join(adopted)}"
        text += f"，适用 {'、'.join(applicable)}"
        lines.append(_with_terminal_punctuation(text))
    return _unique_strings(lines)


def _sound_dialogue_lines(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    generation: Mapping[str, Any],
) -> list[str]:
    lines: list[str] = []
    has_local_sound_or_dialogue = any(
        bool(shot.get("audio")) or bool(shot.get("dialogue"))
        for shot in shots
    )
    voice_positions: dict[tuple[str, str], list[str]] = {}
    speaker_cuts: dict[str, list[str]] = {}
    for shot, cut in zip(shots, timeline):
        cut_label = str(cut.get("cut_label", "Cut"))
        for item in shot.get("dialogue", []):
            if not isinstance(item, dict):
                continue
            speaker = _clean_text(
                item.get("speaker") or item.get("character")
            )
            position = _clean_text(
                item.get("shot_delivery")
                or item.get("position")
                or item.get("on_screen")
            )
            if speaker:
                speaker_cuts.setdefault(speaker, []).append(cut_label)
                if position:
                    voice_positions.setdefault(
                        (speaker, position), []
                    ).append(cut_label)
    position_labels = {
        "onscreen": "画内现场声",
        "on_screen": "画内现场声",
        "画内": "画内现场声",
        "offscreen": "画外声",
        "off_screen": "画外声",
        "os": "画外声",
        "画外": "画外声",
        "mediated": "媒介声",
        "mediated_source": "媒介声",
        "voiceover": "画外音",
        "voice_over": "画外音",
        "vo": "画外音",
        "旁白": "旁白",
        "narration": "旁白",
    }
    for (speaker, position), cut_labels in voice_positions.items():
        applicable = _unique_strings(cut_labels)
        label = position_labels.get(position.casefold(), position)
        if label == "画内现场声" and len(applicable) == 1:
            continue
        lines.append(
            f"声音关系：{speaker}为{label}，适用{'、'.join(applicable)}。"
        )
    for speaker, cut_labels in speaker_cuts.items():
        applicable = _unique_strings(cut_labels)
        has_position_contract = any(
            key[0] == speaker for key in voice_positions
        )
        if len(applicable) > 1 and not has_position_contract:
            lines.append(
                f"声音关系：{speaker}的声音身份跨{'、'.join(applicable)}保持一致。"
            )
    for assignment in generation.get("asset_assignments", []):
        if not isinstance(assignment, dict) or _clean_text(
            assignment.get("role")
        ) != "audio_reference":
            continue
        scope = assignment.get("applies_to_shot_ids", [])
        applicable = [
            str(cut.get("cut_label"))
            for shot, cut in zip(shots, timeline)
            if "*" in scope or str(shot.get("source_shot_id")) in scope
        ]
        if not applicable:
            continue
        tag = _clean_text(assignment.get("tag"))
        target = _clean_text(assignment.get("target_entity"))
        adopted = [
            _clean_text(value)
            for value in assignment.get("adopted_dimensions", [])
            if _clean_text(value)
        ]
        rejected = [
            _clean_text(value)
            for value in assignment.get("rejected_dimensions", [])
            if _clean_text(value)
        ]
        text = f"{tag}用于{target}" if target else tag
        if adopted:
            text += f"的{'、'.join(adopted)}"
        if rejected:
            text += f"，不采用{'、'.join(rejected)}"
        text += f"，适用 {'、'.join(applicable)}"
        lines.append(_with_terminal_punctuation(text))
    unique_lines = _unique_strings(lines)
    if unique_lines:
        return unique_lines
    if has_local_sound_or_dialogue:
        return [
            "本单元的来源声音与台词均已在对应 Cut 内执行，"
            "无额外跨 Cut 声音关系。"
        ]
    return [NO_SOURCE_SOUND_LINE]


def _seedance_consistency_lines(
    shots: Sequence[Mapping[str, Any]],
    generation: Mapping[str, Any],
    *,
    has_assets: bool,
    has_cross_cut_sound: bool,
) -> list[str]:
    lines: list[str] = []
    mode = _clean_text(generation.get("mode"))
    if mode == "edit":
        lines.append(
            "除以上明确修改对象外，原视频中的其他主体、场景、动作、镜头、时间线和声音保持原样。"
        )
    elif mode == "extend":
        lines.append(
            "保持边界画面、主体数量、道具归属、空间方向、运动趋势和声音状态连续，不改写原视频。"
        )
    lines.extend(_continuity_lines(shots, generation))
    if has_assets:
        lines.append(
            "保持每份已采用素材声明的职责一致，不在不同主体、场景、道具、动作或声音之间交换。"
        )
    if has_cross_cut_sound:
        lines.append(
            "保持跨 Cut 的说话人、声音来源、台词原文和画内／画外关系一致。"
        )
    lines.append(
        "不得新增未由来源、用户要求或已确认约束支持的人物、道具、剧情结果和限制。"
    )
    return _unique_strings(lines)


def _seedance_cut_time(
    cut: Mapping[str, Any], integer_timeline: bool
) -> str:
    if not integer_timeline:
        return "顺序阶段"
    return (
        f"{_seconds_text(cut['start_seconds'])}"
        f"-{_seconds_text(cut['end_seconds'])}S"
    )


def _compile_seedance_25_prompt(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    generation: Mapping[str, Any],
) -> str:
    mode = _clean_text(generation.get("mode"))
    goal_heading = {
        "edit": "【编辑目标】",
        "extend": "【延长目标】",
    }.get(mode, "【生成目标】")
    blocks: list[str] = [
        f"{goal_heading}\n{_prompt_goal(shots, generation)}"
    ]
    asset_lines = _asset_responsibility_lines(generation)
    if asset_lines:
        blocks.append("【参考素材职责】\n" + "\n".join(asset_lines))
    subject_lines = _subject_relationship_scene_lines(shots, generation)
    blocks.append("【主体、关系与场景】\n" + "\n".join(
        _with_terminal_punctuation(value) for value in subject_lines
    ))
    blocks.append("【镜头脚本】")
    integer_timeline = bool(timeline) and all(
        cut.get("start_seconds") is not None
        and cut.get("end_seconds") is not None
        and Decimal(str(cut["start_seconds"]))
        == Decimal(str(cut["start_seconds"])).to_integral_value()
        and Decimal(str(cut["end_seconds"]))
        == Decimal(str(cut["end_seconds"])).to_integral_value()
        for cut in timeline
    )
    for index, (shot, cut) in enumerate(zip(shots, timeline)):
        heading = (
            f"{cut['cut_label']}｜"
            f"{_seedance_cut_time(cut, integer_timeline)}"
        )
        composition, _, _ = _camera_prompt_fields(
            shot.get("camera", {}), include_movement=False
        )
        content = _shot_prompt_content(
            shot,
            cut.get("emotion_visualization", []),
            generation,
            include_reference_roles=False,
        )
        lines = [heading]
        if index > 0:
            handoff = _boundary_handoff_line(
                shots[index - 1], shot, str(timeline[index - 1]["cut_label"])
            )
            if handoff:
                lines.append(handoff)
        stage_parts = [value for value in (composition, content) if value]
        if stage_parts:
            lines.append(_with_terminal_punctuation(_join_prompt_parts(stage_parts)))
        blocks.append("\n".join(lines))
    sound_lines = _sound_dialogue_lines(shots, timeline, generation)
    blocks.append("【声音与台词】\n" + "\n".join(
        _with_terminal_punctuation(value) for value in sound_lines
    ))
    cross_cut_sound = bool(
        _cross_cut_sound_lines(shots, timeline, generation)
    )
    consistency = _seedance_consistency_lines(
        shots,
        generation,
        has_assets=bool(asset_lines),
        has_cross_cut_sound=cross_cut_sound,
    )
    blocks.append("【保持一致】\n" + "\n".join(
        _with_terminal_punctuation(value) for value in consistency
    ))
    return "\n\n".join(block for block in blocks if block)


def _compile_prompt(
    shots: Sequence[Mapping[str, Any]],
    timeline: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
    generation: Mapping[str, Any],
) -> str:
    adapter = profile["prompt_adapter_id"]
    if adapter == "seedance-2.5-structured-zh-v1":
        return _compile_seedance_25_prompt(shots, timeline, generation)
    total_duration = timeline[-1].get("end_seconds") if timeline else None
    total_line = (
        f"总时长：{_seconds_text(total_duration)}S"
        if total_duration is not None
        else "总时长：来源未提供"
    )
    lines = [total_line]
    scene_line = _unit_scene_line(shots)
    if scene_line and adapter != "seedance-2.5-structured-zh-v1":
        lines.append(scene_line)
    integer_timeline = bool(timeline) and all(
        cut.get("start_seconds") is not None
        and cut.get("end_seconds") is not None
        and Decimal(str(cut["start_seconds"]))
        == Decimal(str(cut["start_seconds"])).to_integral_value()
        and Decimal(str(cut["end_seconds"]))
        == Decimal(str(cut["end_seconds"])).to_integral_value()
        for cut in timeline
    )
    for shot, cut in zip(shots, timeline):
        if adapter == "seedance-2.5-structured-zh-v1" and not integer_timeline:
            cut_time = "顺序阶段"
        elif cut.get("start_seconds") is None or cut.get("end_seconds") is None:
            cut_time = "时间未提供"
        else:
            cut_time = (
                f"{_seconds_text(cut['start_seconds'])}"
                f"-{_seconds_text(cut['end_seconds'])}S"
            )
        heading = f"{cut['cut_label']} : {cut_time}"
        composition, _, _ = _camera_prompt_fields(
            shot.get("camera", {})
        )
        content = _shot_prompt_content(
            shot,
            cut.get("emotion_visualization", []),
            generation,
            include_reference_roles=(
                adapter != "seedance-2.5-structured-zh-v1"
            ),
        )
        if adapter in {
            "explicit-cut-zh-v1",
            "seedance-2.5-structured-zh-v1",
        }:
            lines.append("")
            lines.append(heading)
            if adapter == "seedance-2.5-structured-zh-v1":
                stage_parts: list[str] = []
                if composition:
                    stage_parts.append(composition)
                if content:
                    stage_parts.append(content)
                stage_text = _join_prompt_parts(stage_parts)
                lines.append(_with_terminal_punctuation(stage_text))
            else:
                if composition:
                    composition_line = f"构图：{composition}"
                    composition_line = _with_terminal_punctuation(
                        composition_line
                    )
                    lines.append(composition_line)
                content_line = f"画面内容：{content}"
                if content:
                    content_line = _with_terminal_punctuation(content_line)
                lines.append(content_line)
        elif adapter == "compact-cut-zh-v1":
            compact_parts = [heading]
            if composition:
                compact_parts.append(f"构图：{composition}")
            compact_parts.append(f"画面内容：{content}")
            lines.extend(("", "\n".join(compact_parts)))
        else:  # Profile validation should make this unreachable.
            raise DeliveryError(f"Unsupported prompt adapter: {adapter}")
    return "\n".join(lines)
