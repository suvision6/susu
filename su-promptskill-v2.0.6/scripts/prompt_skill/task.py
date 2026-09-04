"""su-promptskill internal module: Profile, task, story and dialogue contracts."""

from __future__ import annotations

from . import source as _previous

globals().update({
    key: value
    for key, value in vars(_previous).items()
    if not key.startswith("__")
})

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Responsibility module behind scripts/prompt_delivery.py."

def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def validate_model_profile(profile: Any) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(profile, dict):
        return [
            _issue(
                "MODEL_PROFILE_INVALID",
                "ERROR",
                "model_profile",
                "model_profile",
                "Model Profile 必须是 JSON 对象。",
                ("prompt_compilation",),
            )
        ]

    profile_id = _clean_text(profile.get("profile_id"))
    model_name = _clean_text(profile.get("model_name"))
    capabilities = profile.get("capabilities")
    adapter = _clean_text(profile.get("prompt_adapter_id"))
    if not profile_id or not model_name or not isinstance(capabilities, dict):
        issues.append(
            _issue(
                "MODEL_PROFILE_INVALID",
                "ERROR",
                "model_profile",
                "model_profile",
                "Profile 缺少 profile_id、model_name 或 capabilities。",
                ("prompt_compilation",),
            )
        )
        return issues

    try:
        max_duration = _duration_decimal(
            capabilities.get("max_clip_duration_seconds")
        )
    except InvalidOperation:
        max_duration = None
    if max_duration is None:
        issues.append(
            _issue(
                "MODEL_PROFILE_INVALID",
                "ERROR",
                "model_profile",
                "model_profile.capabilities.max_clip_duration_seconds",
                "模型最大时长必须是正有限数。",
                ("prompt_compilation",),
            )
        )

    for key in (
        "supports_multi_cut",
        "supports_explicit_cut_timeline",
        "supports_dialogue",
    ):
        if not isinstance(capabilities.get(key), bool):
            issues.append(
                _issue(
                    "MODEL_PROFILE_INVALID",
                    "ERROR",
                    "model_profile",
                    f"model_profile.capabilities.{key}",
                    f"{key} 必须是布尔值。",
                    ("prompt_compilation",),
                )
            )

    supported_modes = capabilities.get("supported_generation_modes")
    if (
        not isinstance(supported_modes, list)
        or not supported_modes
        or any(mode not in GENERATION_MODES for mode in supported_modes)
        or len(set(supported_modes)) != len(supported_modes)
    ):
        issues.append(
            _issue(
                "MODEL_PROFILE_INVALID",
                "ERROR",
                "model_profile",
                "model_profile.capabilities.supported_generation_modes",
                "supported_generation_modes 必须是非空、无重复的合法 mode enum 数组。",
                ("prompt_compilation",),
            )
        )

    convention = capabilities.get("reference_tag_convention")
    convention_id = (
        _clean_text(convention.get("convention_id"))
        if isinstance(convention, dict)
        else ""
    )
    convention_valid = convention_id in REFERENCE_CONVENTIONS
    if convention_valid and convention_id == "indexed-prefix-v1":
        prefixes = [
            _clean_text(convention.get("image_prefix")),
            _clean_text(convention.get("video_prefix")),
        ]
        convention_valid = (
            all(SAFE_REFERENCE_PREFIX_RE.fullmatch(prefix) for prefix in prefixes)
            and prefixes[0] != prefixes[1]
        )
    if not convention_valid:
        issues.append(
            _issue(
                "MODEL_PROFILE_INVALID",
                "ERROR",
                "model_profile",
                "model_profile.capabilities.reference_tag_convention",
                "reference_tag_convention 必须使用受支持 enum 和安全、不重复的前缀。",
                ("prompt_compilation",),
            )
        )

    if adapter not in SUPPORTED_ADAPTERS:
        issues.append(
            _issue(
                "MODEL_PROFILE_INVALID",
                "ERROR",
                "model_profile",
                "model_profile.prompt_adapter_id",
                f"不支持的 Prompt adapter：{adapter or '<empty>'}。",
                ("prompt_compilation",),
            )
        )

    prohibited = sorted(set(_walk_keys(profile)) & PROFILE_GROUPING_KEYS)
    if prohibited:
        issues.append(
            _issue(
                "MODEL_PROFILE_INVALID",
                "ERROR",
                "model_profile",
                "model_profile",
                f"Model Profile 不得拥有合镜策略字段：{', '.join(prohibited)}。",
                ("prompt_compilation",),
            )
        )
    return issues


def resolve_model_profile(
    profile_id: str | None = None, profile_document: Any = None
) -> dict[str, Any]:
    if profile_document is not None:
        return copy.deepcopy(profile_document)
    selected_id = profile_id or "seedance-2.5-default"
    if selected_id not in BUILTIN_PROFILES:
        raise DeliveryError(f"Unknown built-in profile: {selected_id}")
    return copy.deepcopy(BUILTIN_PROFILES[selected_id])


def _runtime_value(source_document: Any, decisions: Any, key: str) -> Any:
    if isinstance(decisions, dict) and key in decisions:
        return copy.deepcopy(decisions.get(key))
    if isinstance(source_document, dict) and key in source_document:
        return copy.deepcopy(source_document.get(key))
    return None


def _task_from_legacy_mode(mode: str) -> dict[str, Any]:
    primary, topology, modules = LEGACY_MODE_TASK_MAP.get(
        mode, ("", "", ())
    )
    return {
        "primary": primary,
        "input_topology": topology,
        "modules": list(modules),
        "source": "legacy_generation_mode",
    }


def _legacy_mode_from_task(task: Mapping[str, Any]) -> str:
    primary = _clean_text(task.get("primary")).lower()
    topology = _clean_text(task.get("input_topology")).lower()
    modules = {
        _clean_text(item).lower()
        for item in task.get("modules", [])
        if isinstance(item, str)
    }
    if primary == "edit":
        return "edit"
    if primary == "extend":
        return "extend"
    if primary != "generate":
        return ""
    if {"first-frame", "last-frame"}.issubset(modules):
        return "flf2v"
    return {
        "text-only": "t2v",
        "image-reference": "i2v",
        "video-reference": "v2v",
        "audio-reference": "r2v",
        "multimodal": "r2v",
    }.get(topology, "")


def _api_content_role(item: Mapping[str, Any]) -> str:
    """Translate an internal reference responsibility to API content.role."""
    role = _clean_text(item.get("role"))
    media_type = _clean_text(item.get("media_type")).lower()
    if role == "first_frame":
        return "first_frame"
    if role == "last_frame":
        return "last_frame"
    return {
        "image": "reference_image",
        "video": "reference_video",
        "audio": "reference_audio",
    }.get(media_type, "")


def _official_task_routing(
    task: Mapping[str, Any], generation: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve Seedance 2.5's five official task types.

    The API classifies reference generation, editing, and extension from both
    ``content.role`` and prompt intent.  This object keeps those two routing
    signals explicit without placing API parameters in ``prompt_text``.
    """
    issues: list[dict[str, Any]] = []
    primary = _clean_text(task.get("primary")).lower()
    topology = _clean_text(task.get("input_topology")).lower()
    modules = {
        _clean_text(value).lower()
        for value in task.get("modules", [])
        if isinstance(value, str)
    }
    raw_role_rows: list[dict[str, str]] = []
    for item in generation.get("reference_role_map", []):
        if not isinstance(item, dict):
            continue
        content_role = _api_content_role(item)
        tag = _clean_text(item.get("tag"))
        if tag and content_role:
            raw_role_rows.append({"tag": tag, "content_role": content_role})
    role_rows: list[dict[str, str]] = []
    for tag in _unique_strings(item["tag"] for item in raw_role_rows):
        tag_roles = [
            item["content_role"]
            for item in raw_role_rows
            if item["tag"] == tag
        ]
        frame_role = next(
            (
                role
                for role in ("first_frame", "last_frame")
                if role in tag_roles
            ),
            None,
        )
        role_rows.append(
            {"tag": tag, "content_role": frame_role or tag_roles[0]}
        )
    frame_roles = {
        item["content_role"]
        for item in role_rows
        if item["content_role"] in {"first_frame", "last_frame"}
    }
    reference_roles = {
        item["content_role"]
        for item in role_rows
        if item["content_role"].startswith("reference_")
    }
    strict_frame_task = bool(
        frame_roles or modules.intersection({"first-frame", "last-frame"})
    )
    if strict_frame_task and reference_roles:
        issues.append(
            _issue(
                "CONTENT_ROLE_SCENARIO_CONFLICT",
                "ERROR",
                "task",
                "task.official_routing.content_roles",
                (
                    "严格首帧/首尾帧与多模态 reference_* content.role "
                    "是互斥输入场景；需要多参考时应改用 reference_image "
                    "并在 Prompt 中把图片指定为语义关键帧。"
                ),
                ("prompt_compilation", "submission"),
            )
        )
    if "last_frame" in frame_roles and "first_frame" not in frame_roles:
        issues.append(
            _issue(
                "CONTENT_ROLE_SCENARIO_CONFLICT",
                "ERROR",
                "task",
                "task.official_routing.content_roles",
                "last_frame 必须与 first_frame 成对使用。",
                ("prompt_compilation", "submission"),
            )
        )
    if primary == "edit":
        task_type = "video-editing"
        intent = "edit"
    elif primary == "extend":
        task_type = "video-extension"
        intent = "extend"
    elif strict_frame_task:
        task_type = "first-or-first-last-frame"
        intent = "generate-from-locked-frame"
    elif topology == "text-only" and not role_rows:
        task_type = "text-to-video"
        intent = "generate"
    else:
        task_type = "reference-generation"
        intent = "generate-from-reference"
    return {
        "task_type": task_type,
        "prompt_intent": intent,
        "content_roles": role_rows,
        "routing_basis": "content.role + prompt intent",
    }, issues


def _raw_asset_documents(
    source_document: Any, decisions: Any
) -> tuple[Any, Any]:
    inventory = _runtime_value(source_document, decisions, "asset_inventory")
    assignments = _runtime_value(
        source_document, decisions, "asset_assignments"
    )
    return inventory, assignments


def _normalize_asset_binding(
    source_document: Any,
    decisions: Any,
    asset_assignments: Sequence[Mapping[str, Any]],
    generation: Mapping[str, Any],
) -> dict[str, str]:
    raw = _runtime_value(source_document, decisions, "asset_binding")
    has_legacy_mapping = bool(asset_assignments) or bool(
        generation.get("reference_role_map")
    )
    if raw is None:
        return {
            "state": "mapped" if has_legacy_mapping else "unmapped",
            "source": "legacy" if has_legacy_mapping else "none",
        }
    if not isinstance(raw, dict) or _clean_text(raw.get("state")).lower() != "mapped":
        raise AssetBindingError(
            "ASSET_BINDING_INVALID: asset_binding 省略表示无素材；显式提供时 state 必须为 mapped。"
        )
    if not has_legacy_mapping:
        raise AssetBindingError(
            "ASSET_BINDING_INVALID: mapped 状态至少需要一个合法 asset assignment 或 reference role。"
        )
    return {"state": "mapped", "source": "explicit"}


def _generation_from_v2_documents(
    source_document: Any, decisions: Any
) -> dict[str, Any]:
    raw_task = _runtime_value(source_document, decisions, "task")
    inventory_raw, assignments_raw = _raw_asset_documents(
        source_document, decisions
    )
    inventory_items = (
        inventory_raw.get("items", [])
        if isinstance(inventory_raw, dict)
        else []
    )
    inventory_by_tag = {
        _clean_text(item.get("tag")): item
        for item in inventory_items
        if isinstance(item, dict) and _clean_text(item.get("tag"))
    }
    role_map: list[dict[str, Any]] = []
    for assignment in assignments_raw if isinstance(assignments_raw, list) else []:
        if not isinstance(assignment, dict):
            continue
        tag = _clean_text(assignment.get("tag"))
        item = inventory_by_tag.get(tag, {})
        if not tag or item.get("available", True) is False:
            continue
        role = _clean_text(assignment.get("role"))
        media_type = _clean_text(
            assignment.get("media_type") or item.get("media_type")
        ).lower()
        adopted = assignment.get("adopted_dimensions", [])
        preserve = (
            [str(value) for value in adopted]
            if isinstance(adopted, list)
            else []
        )
        role_map.append(
            {
                "tag": tag,
                "media_type": media_type,
                "role": role,
                "applies_to_shot_ids": copy.deepcopy(
                    assignment.get("applies_to_shot_ids", [])
                ),
                "preserve": preserve,
            }
        )
    if isinstance(raw_task, dict):
        mode = _legacy_mode_from_task(raw_task)
    elif role_map:
        roles = {_clean_text(item.get("role")) for item in role_map}
        media_types = {
            _clean_text(item.get("media_type")) for item in role_map
        }
        if "edit_source" in roles:
            mode = "edit"
        elif "extension_source" in roles:
            mode = "extend"
        elif roles.intersection({"first_frame", "last_frame"}):
            mode = "flf2v"
        elif media_types == {"image"}:
            mode = "i2v"
        elif media_types == {"video"}:
            mode = "v2v"
        else:
            mode = "r2v"
    else:
        return {}
    available_tags = _unique_strings(
        [item["tag"] for item in role_map]
    )
    generation: dict[str, Any] = {
        "mode": mode,
        "available_reference_tags": available_tags,
        "reference_role_map": role_map,
    }
    for key in ("edit_scope", "edit_deltas", "extend_context"):
        value = _runtime_value(source_document, decisions, key)
        if value is not None:
            generation[key] = value
    return generation


def _normalize_task(
    source_document: Any,
    decisions: Any,
    generation: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    raw_task = _runtime_value(source_document, decisions, "task")
    if raw_task is None:
        normalized_task = _task_from_legacy_mode(
            _clean_text(generation.get("mode"))
        )
        if profile.get("prompt_adapter_id") == "seedance-2.5-structured-zh-v1":
            official_routing, routing_issues = _official_task_routing(
                normalized_task, generation
            )
            normalized_task["official_routing"] = official_routing
            issues.extend(routing_issues)
        return normalized_task, issues
    if not isinstance(raw_task, dict):
        return {
            "primary": "",
            "input_topology": "",
            "modules": [],
            "source": "invalid",
        }, [
            _issue(
                "TASK_CONTRACT_INVALID",
                "ERROR",
                "task",
                "task",
                "task 必须是 JSON 对象。",
                ("prompt_compilation",),
            )
        ]
    primary = _clean_text(raw_task.get("primary")).lower()
    topology = _clean_text(raw_task.get("input_topology")).lower()
    modules_raw = raw_task.get("modules", [])
    modules = (
        [_clean_text(item).lower() for item in modules_raw]
        if isinstance(modules_raw, list)
        else []
    )
    if primary not in TASK_PRIMARY_VALUES:
        issues.append(
            _issue(
                "TASK_CONTRACT_INVALID",
                "ERROR",
                "task",
                "task.primary",
                "task.primary 必须是 generate、edit 或 extend。",
                ("prompt_compilation",),
            )
        )
    if topology not in INPUT_TOPOLOGY_VALUES:
        issues.append(
            _issue(
                "TASK_CONTRACT_INVALID",
                "ERROR",
                "task",
                "task.input_topology",
                "task.input_topology 不属于受支持 enum。",
                ("prompt_compilation",),
            )
        )
    if (
        not isinstance(modules_raw, list)
        or any(module not in TASK_MODULE_VALUES for module in modules)
        or len(set(modules)) != len(modules)
    ):
        issues.append(
            _issue(
                "TASK_CONTRACT_INVALID",
                "ERROR",
                "task",
                "task.modules",
                "task.modules 必须是无重复、受支持的模块数组。",
                ("prompt_compilation",),
            )
        )
    expected_mode = _legacy_mode_from_task(
        {"primary": primary, "input_topology": topology, "modules": modules}
    )
    actual_mode = _clean_text(generation.get("mode"))
    if expected_mode and actual_mode and expected_mode != actual_mode:
        issues.append(
            _issue(
                "TASK_GENERATION_MISMATCH",
                "ERROR",
                "task",
                "task",
                "task 与兼容 generation.mode 的路由结果不一致。",
                ("prompt_compilation",),
            )
        )
    normalized_task = {
        "primary": primary,
        "input_topology": topology,
        "modules": modules,
        "source": "task",
    }
    if profile.get("prompt_adapter_id") == "seedance-2.5-structured-zh-v1":
        official_routing, routing_issues = _official_task_routing(
            normalized_task, generation
        )
        normalized_task["official_routing"] = official_routing
        issues.extend(routing_issues)
    return normalized_task, issues


def _derive_story_contract(
    normalized: Mapping[str, Any], source_document: Any, decisions: Any
) -> dict[str, Any]:
    raw = _runtime_value(source_document, decisions, "story_contract")
    if isinstance(raw, dict):
        return copy.deepcopy(raw)
    events = []
    for shot in normalized.get("shots", []):
        description = _clean_text(shot.get("rendered_shot_description"))
        if description:
            events.append(
                {
                    "source_shot_id": shot.get("source_shot_id"),
                    "description": description,
                }
            )
    return {
        "subjects": [],
        "events": events,
        "scenes": [],
        "props": [],
        "relationships": [],
        "preserve": [],
        "exclude": [],
        "provenance": "derived_from_locked_source",
    }


def _derive_required_entities(
    normalized: Mapping[str, Any], story_contract: Mapping[str, Any]
) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entity_type, values in (
        ("subject", story_contract.get("subjects", [])),
        ("subject", story_contract.get("characters", [])),
        ("prop", story_contract.get("props", [])),
        ("scene", story_contract.get("scenes", [])),
        ("scene", story_contract.get("locations", [])),
    ):
        for value in values if isinstance(values, list) else []:
            name = _clean_text(value.get("name") if isinstance(value, dict) else value)
            if name and (entity_type, name) not in seen:
                seen.add((entity_type, name))
                entities.append({"entity_type": entity_type, "name": name})
    singular_location = _clean_text(story_contract.get("location"))
    if singular_location and ("scene", singular_location) not in seen:
        seen.add(("scene", singular_location))
        entities.append({"entity_type": "scene", "name": singular_location})
    for shot in normalized.get("shots", []):
        for value in shot.get("subjects", []):
            name = _clean_text(_render_descriptive_value(value))
            if name and ("subject", name) not in seen:
                seen.add(("subject", name))
                entities.append({"entity_type": "subject", "name": name})
        for value in shot.get("visible_props", []):
            name = _clean_text(_render_descriptive_value(value))
            if name and ("prop", name) not in seen:
                seen.add(("prop", name))
                entities.append({"entity_type": "prop", "name": name})
    return entities


def _derive_dialogue_ledger(
    normalized: Mapping[str, Any]
) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    dialogue_id_positions: dict[str, int] = {}
    for shot in normalized.get("shots", []):
        for item in shot.get("dialogue", []):
            if isinstance(item, dict):
                shot_id = shot.get("source_shot_id")
                dialogue_id = _clean_text(item.get("dialogue_id"))
                segment = {
                    "source_shot_id": shot_id,
                    "text": copy.deepcopy(item.get("text")),
                    "position": copy.deepcopy(
                        item.get("position", item.get("on_screen"))
                    ),
                }
                if dialogue_id and dialogue_id in dialogue_id_positions:
                    entry = ledger[dialogue_id_positions[dialogue_id]]
                    if shot_id not in entry["source_shot_ids"]:
                        entry["source_shot_ids"].append(shot_id)
                    entry["segments"].append(segment)
                    continue
                entry = {
                    "dialogue_id": dialogue_id or None,
                    "source_shot_id": shot_id,
                    "source_shot_ids": [shot_id],
                    "speaker": copy.deepcopy(
                        item.get("speaker", item.get("character"))
                    ),
                    "speaking": item.get("speaking", True),
                    "text": copy.deepcopy(
                        item.get("source_text") or item.get("text")
                    ),
                    "audio_role": copy.deepcopy(item.get("audio_role")),
                    "language": copy.deepcopy(item.get("language")),
                    "position": copy.deepcopy(
                        item.get("position", item.get("on_screen"))
                    ),
                    "segments": [segment],
                }
                ledger.append(entry)
                if dialogue_id:
                    dialogue_id_positions[dialogue_id] = len(ledger) - 1
            else:
                ledger.append(
                    {
                        "dialogue_id": None,
                        "source_shot_id": shot.get("source_shot_id"),
                        "source_shot_ids": [shot.get("source_shot_id")],
                        "speaker": None,
                        "speaking": True,
                        "text": copy.deepcopy(item),
                        "audio_role": None,
                        "language": None,
                        "position": None,
                        "segments": [
                            {
                                "source_shot_id": shot.get("source_shot_id"),
                                "text": copy.deepcopy(item),
                                "position": None,
                            }
                        ],
                    }
                )
    return ledger


def _bind_dialogue_assets(
    ledger: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach explicit speaker/audio mappings without inventing dialogue."""
    bound: list[dict[str, Any]] = []
    for raw_entry in ledger:
        entry = copy.deepcopy(dict(raw_entry))
        speaker = _clean_text(entry.get("speaker"))
        shot_ids = {
            _clean_text(value)
            for value in entry.get(
                "source_shot_ids", [entry.get("source_shot_id")]
            )
            if _clean_text(value)
        }
        tags = []
        for assignment in assignments:
            if _clean_text(assignment.get("role")) != "audio_reference":
                continue
            applies = assignment.get("applies_to_shot_ids", [])
            target = _clean_text(assignment.get("target_entity"))
            if "*" not in applies and not shot_ids.intersection(applies):
                continue
            if speaker and target not in {speaker, "对白", "指定说话人"}:
                continue
            tag = _clean_text(assignment.get("tag"))
            if tag:
                tags.append(tag)
        entry["bound_asset_tags"] = _unique_strings(tags)
        bound.append(entry)
    return bound
