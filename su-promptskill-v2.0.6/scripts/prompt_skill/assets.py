"""su-promptskill internal module: asset, request and generation context."""

from __future__ import annotations

from . import task as _previous

globals().update({
    key: value
    for key, value in vars(_previous).items()
    if not key.startswith("__")
})

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Responsibility module behind scripts/prompt_delivery.py."

def _normalize_asset_context(
    source_document: Any,
    decisions: Any,
    profile: Mapping[str, Any],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[str],
    str,
    list[dict[str, Any]],
    list[dict[str, Any]],
    bool,
]:
    issues: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []
    inventory_raw, assignments_raw = _raw_asset_documents(
        source_document, decisions
    )
    if inventory_raw is None:
        inventory_raw = {"complete": False, "items": []}
    if not isinstance(inventory_raw, dict):
        inventory_raw = {"complete": False, "items": []}
        issues.append(
            _issue(
                "ASSET_INVENTORY_INVALID",
                "ERROR",
                "asset",
                "asset_inventory",
                "asset_inventory 必须是 JSON 对象。",
                ("material_mapping",),
            )
        )
    complete = inventory_raw.get("complete") is True
    items_raw = inventory_raw.get("items", [])
    if not isinstance(items_raw, list):
        items_raw = []
        issues.append(
            _issue(
                "ASSET_INVENTORY_INVALID",
                "ERROR",
                "asset",
                "asset_inventory.items",
                "asset_inventory.items 必须是数组。",
                ("material_mapping",),
            )
        )
    items: list[dict[str, Any]] = []
    by_tag: dict[str, dict[str, Any]] = {}
    for index, raw_item in enumerate(items_raw):
        path = f"asset_inventory.items[{index}]"
        if not isinstance(raw_item, dict):
            issues.append(
                _issue(
                    "ASSET_INVENTORY_INVALID",
                    "ERROR",
                    "asset",
                    path,
                    "素材项必须是 JSON 对象。",
                    ("material_mapping",),
                )
            )
            continue
        tag = _clean_text(raw_item.get("tag"))
        media_type = _clean_text(raw_item.get("media_type")).lower()
        if (
            not tag
            or tag in by_tag
            or media_type not in {"image", "video", "audio"}
        ):
            issues.append(
                _issue(
                    "ASSET_INVENTORY_INVALID",
                    "ERROR",
                    "asset",
                    path,
                    "素材 tag 必须唯一，media_type 必须为 image、video 或 audio。",
                    ("material_mapping",),
                )
            )
            continue
        item = {
            "tag": tag,
            "media_type": media_type,
            "available": raw_item.get("available", True) is not False,
            "core": raw_item.get("core") is True,
            "duration_seconds": copy.deepcopy(
                raw_item.get("duration_seconds")
            ),
            "width": copy.deepcopy(raw_item.get("width")),
            "height": copy.deepcopy(raw_item.get("height")),
            "group_reference": raw_item.get("group_reference") is True,
            "observations": copy.deepcopy(raw_item.get("observations", {})),
        }
        items.append(item)
        by_tag[tag] = item

    assignments_raw = [] if assignments_raw is None else assignments_raw
    if not isinstance(assignments_raw, list):
        assignments_raw = []
        issues.append(
            _issue(
                "ASSET_ASSIGNMENT_INVALID",
                "ERROR",
                "asset",
                "asset_assignments",
                "asset_assignments 必须是数组。",
                ("material_mapping",),
            )
        )
    assignments: list[dict[str, Any]] = []
    targets_by_tag: dict[str, set[str]] = {}
    used_tags: set[str] = set()
    missing_optional: list[str] = []
    missing_core: list[str] = []
    for index, raw_assignment in enumerate(assignments_raw):
        path = f"asset_assignments[{index}]"
        if not isinstance(raw_assignment, dict):
            issues.append(
                _issue(
                    "ASSET_ASSIGNMENT_INVALID",
                    "ERROR",
                    "asset",
                    path,
                    "素材职责必须是 JSON 对象。",
                    ("material_mapping",),
                )
            )
            continue
        tag = _clean_text(raw_assignment.get("tag"))
        target = _clean_text(raw_assignment.get("target_entity"))
        role = _clean_text(raw_assignment.get("role"))
        item = by_tag.get(tag)
        adopted = raw_assignment.get("adopted_dimensions", [])
        rejected = raw_assignment.get("rejected_dimensions", [])
        applies = raw_assignment.get("applies_to_shot_ids", [])
        valid_lists = all(
            isinstance(value, list)
            and all(isinstance(entry, str) and entry.strip() for entry in value)
            for value in (adopted, rejected, applies)
        )
        if (
            item is None
            or not target
            or role not in REFERENCE_ROLE_MEDIA
            or not valid_lists
        ):
            issues.append(
                _issue(
                    "ASSET_ASSIGNMENT_INVALID",
                    "ERROR",
                    "asset",
                    path,
                    "素材职责必须引用库存 tag、目标实体、合法 role 和字符串数组。",
                    ("material_mapping",),
                )
            )
            continue
        targets_by_tag.setdefault(tag, set()).add(target)
        if item["available"]:
            used_tags.add(tag)
            assignments.append(
                {
                    "tag": tag,
                    "media_type": item["media_type"],
                    "target_entity": target,
                    "role": role,
                    "adopted_dimensions": list(adopted),
                    "rejected_dimensions": list(rejected),
                    "applies_to_shot_ids": list(applies),
                    "user_mapped": raw_assignment.get("user_mapped") is True,
                }
            )
        elif item["core"] or role in {"edit_source", "extension_source"}:
            missing_core.append(tag)
        else:
            missing_optional.append(tag)

    for tag, targets in targets_by_tag.items():
        item = by_tag.get(tag, {})
        related = [entry for entry in assignments if entry["tag"] == tag]
        user_mapped = any(entry.get("user_mapped") for entry in related)
        if (
            len(targets) > 1
            and not item.get("group_reference")
            and not user_mapped
        ):
            issues.append(
                _issue(
                    "ASSET_CARDINALITY_CONFLICT",
                    "ERROR",
                    "asset",
                    "asset_assignments",
                    f"素材 {tag} 未声明群体或用户映射，却分配给多个实体。",
                    ("material_mapping",),
                )
            )

    unused = (
        [item["tag"] for item in items if item["available"] and item["tag"] not in used_tags]
        if complete
        else []
    )
    if missing_optional:
        missing_optional_text = "、".join(
            _unique_strings(missing_optional)
        )
        advisories.append(
            {
                "type": "补充建议",
                "code": "OPTIONAL_ASSET_MISSING",
                "message": (
                    "以下非核心素材不可用，Prompt 已移除对应引用："
                    + missing_optional_text
                ),
            }
        )
        issues.append(
            _issue(
                "OPTIONAL_ASSET_MISSING",
                "WARN",
                "asset",
                "asset_inventory",
                f"非核心素材不可用：{missing_optional_text}。",
                ("material_mapping_review",),
            )
        )
    for tag in _unique_strings(missing_core):
        issues.append(
            _issue(
                "CORE_ASSET_MISSING",
                "ERROR",
                "asset",
                "asset_inventory",
                f"唯一核心素材 {tag} 不可用。",
                ("prompt_compilation",),
            )
        )

    submission_ready = not missing_core
    limits = profile.get("capabilities", {}).get("asset_limits", {})
    available_items = [item for item in items if item["available"]]
    limit_messages: list[str] = []
    max_total = limits.get("max_total") if isinstance(limits, dict) else None
    if isinstance(max_total, int) and len(available_items) > max_total:
        limit_messages.append(f"素材总数 {len(available_items)}>{max_total}")
    for media_type in ("image", "video", "audio"):
        media_items = [
            item for item in available_items if item["media_type"] == media_type
        ]
        media_limit = limits.get(media_type, {}) if isinstance(limits, dict) else {}
        max_count = media_limit.get("max_count") if isinstance(media_limit, dict) else None
        if isinstance(max_count, int) and len(media_items) > max_count:
            limit_messages.append(
                f"{media_type} 数量 {len(media_items)}>{max_count}"
            )
        max_duration = (
            media_limit.get("max_total_duration_seconds")
            if isinstance(media_limit, dict)
            else None
        )
        min_item_duration = (
            media_limit.get("min_item_duration_seconds")
            if isinstance(media_limit, dict)
            else None
        )
        max_item_duration = (
            media_limit.get("max_item_duration_seconds")
            if isinstance(media_limit, dict)
            else None
        )
        known_durations: list[Decimal] = []
        for item in media_items:
            try:
                duration = _duration_decimal(item.get("duration_seconds"))
            except InvalidOperation:
                duration = None
            if duration is not None:
                known_durations.append(duration)
                if (
                    isinstance(min_item_duration, (int, float))
                    and duration < Decimal(str(min_item_duration))
                ):
                    limit_messages.append(
                        f"{item['tag']} 时长低于 {min_item_duration} 秒"
                    )
                if (
                    isinstance(max_item_duration, (int, float))
                    and duration > Decimal(str(max_item_duration))
                ):
                    limit_messages.append(
                        f"{item['tag']} 时长超过 {max_item_duration} 秒"
                    )
        if (
            isinstance(max_duration, (int, float))
            and known_durations
            and sum(known_durations, Decimal("0")) > Decimal(str(max_duration))
        ):
            limit_messages.append(
                f"{media_type} 总时长超过 {max_duration} 秒"
            )
    image_limit = limits.get("image", {}) if isinstance(limits, dict) else {}
    min_dimension = image_limit.get("min_dimension_pixels") if isinstance(image_limit, dict) else None
    max_dimension = image_limit.get("max_dimension_pixels") if isinstance(image_limit, dict) else None
    min_total_pixels = image_limit.get("min_total_pixels") if isinstance(image_limit, dict) else None
    max_total_pixels = image_limit.get("max_total_pixels") if isinstance(image_limit, dict) else None
    min_aspect_ratio = image_limit.get("min_aspect_ratio") if isinstance(image_limit, dict) else None
    max_aspect_ratio = image_limit.get("max_aspect_ratio") if isinstance(image_limit, dict) else None
    for item in available_items:
        if item["media_type"] != "image":
            continue
        width = item.get("width")
        height = item.get("height")
        dimensions = [width, height]
        if isinstance(max_dimension, int):
            if any(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value > max_dimension
                for value in dimensions
            ):
                limit_messages.append(
                    f"{item['tag']} 尺寸超过 {max_dimension}px"
                )
        if isinstance(min_dimension, int) and any(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value < min_dimension
            for value in dimensions
        ):
            limit_messages.append(
                f"{item['tag']} 尺寸低于 {min_dimension}px"
            )
        if all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value > 0
            for value in dimensions
        ):
            total_pixels = width * height
            aspect_ratio = width / height
            if (
                isinstance(min_total_pixels, int)
                and total_pixels < min_total_pixels
            ):
                limit_messages.append(
                    f"{item['tag']} 总像素低于 {min_total_pixels}"
                )
            if (
                isinstance(max_total_pixels, int)
                and total_pixels > max_total_pixels
            ):
                limit_messages.append(
                    f"{item['tag']} 总像素超过 {max_total_pixels}"
                )
            if (
                isinstance(min_aspect_ratio, (int, float))
                and aspect_ratio < min_aspect_ratio
            ) or (
                isinstance(max_aspect_ratio, (int, float))
                and aspect_ratio > max_aspect_ratio
            ):
                limit_messages.append(
                    f"{item['tag']} 宽高比不在 0.4 至 2.5"
                )
    if limit_messages:
        submission_ready = False
        advisories.append(
            {
                "type": "素材提示",
                "code": "ASSET_LIMIT_EXCEEDED",
                "message": "；".join(_unique_strings(limit_messages)),
            }
        )
        issues.append(
            _issue(
                "ASSET_LIMIT_EXCEEDED",
                "WARN",
                "asset",
                "asset_inventory",
                "；".join(_unique_strings(limit_messages)),
                ("submission",),
            )
        )

    confidence_raw = _runtime_value(
        source_document, decisions, "mapping_confidence"
    )
    confidence = (
        _clean_text(confidence_raw).lower()
        if isinstance(confidence_raw, str)
        else "high"
    )
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
        issues.append(
            _issue(
                "MAPPING_CONFIDENCE_INVALID",
                "WARN",
                "asset",
                "mapping_confidence",
                "映射置信度必须为 high、medium 或 low。",
                ("material_mapping_review",),
            )
        )
    inventory = {"complete": complete, "items": items}
    return (
        inventory,
        assignments,
        unused,
        confidence,
        issues,
        advisories,
        submission_ready,
    )


def _normalize_request_configuration(
    source_document: Any,
    decisions: Any,
    profile: Mapping[str, Any],
    task: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], bool]:
    issues: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []
    raw = _runtime_value(source_document, decisions, "request_configuration")
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
        issues.append(
            _issue(
                "REQUEST_CONFIGURATION_INVALID",
                "WARN",
                "request",
                "request_configuration",
                "request_configuration 必须是 JSON 对象。",
                ("submission",),
            )
        )
    raw_model_id = raw.get("model_id", profile.get("model_id"))
    raw_ratio = raw.get("ratio")
    raw_duration = raw.get("duration")
    raw_resolution = raw.get("resolution")
    raw_output_format = raw.get("output_format")
    raw_generate_audio = raw.get("generate_audio")
    normalized = {
        "model_id": (
            _clean_text(raw_model_id) if raw_model_id is not None else None
        ),
        "ratio": (
            _clean_text(raw_ratio).lower() if raw_ratio is not None else None
        ),
        "duration": copy.deepcopy(raw_duration),
        "resolution": (
            _clean_text(raw_resolution).lower()
            if raw_resolution is not None
            else None
        ),
        "output_format": (
            _clean_text(raw_output_format).lower()
            if raw_output_format is not None
            else None
        ),
        "generate_audio": copy.deepcopy(raw_generate_audio),
    }
    ready = True
    profile_model_id = profile.get("model_id")
    if (
        raw.get("model_id") is not None
        and profile_model_id is not None
        and raw.get("model_id") != profile_model_id
    ):
        ready = False
        advisories.append(
            {
                "type": "参数提示",
                "code": "MODEL_ID_MISMATCH",
                "message": "请求 model_id 与当前 Model Profile 不一致。",
            }
        )
        issues.append(
            _issue(
                "MODEL_ID_MISMATCH",
                "WARN",
                "request",
                "request_configuration.model_id",
                "请求 model_id 与当前 Model Profile 不一致。",
                ("submission",),
            )
        )
    primary = _clean_text(task.get("primary"))
    modules = set(task.get("modules", []))
    ratio = normalized["ratio"]
    duration = normalized["duration"]
    resolution = normalized["resolution"]
    output_format = normalized["output_format"]
    generate_audio = normalized["generate_audio"]
    request_constraints = profile.get("capabilities", {}).get(
        "request_constraints", {}
    )
    allowed_ratios = request_constraints.get("ratios", [])
    allowed_resolutions = request_constraints.get("resolutions", [])
    allowed_formats = request_constraints.get("output_formats", [])
    conflicts: list[str] = []
    if ratio is not None and (
        not isinstance(allowed_ratios, list) or ratio not in allowed_ratios
    ):
        conflicts.append("ratio 不属于当前模型支持的宽高比")
    if output_format is not None and (
        not isinstance(allowed_formats, list)
        or output_format not in allowed_formats
    ):
        conflicts.append("output_format 不属于当前模型支持的格式")
    if resolution is not None and (
        not isinstance(allowed_resolutions, list)
        or resolution not in allowed_resolutions
    ):
        conflicts.append("resolution 不属于当前模型支持的分辨率")
    if generate_audio is not None and not isinstance(generate_audio, bool):
        conflicts.append("generate_audio 必须是布尔值")
    if primary == "edit":
        if ratio not in (None, "adaptive"):
            conflicts.append("视频编辑 ratio 必须为 adaptive")
        if duration not in (None, -1):
            conflicts.append("视频编辑 duration 必须为 -1")
    elif primary == "extend" or modules.intersection(
        {"first-frame", "last-frame"}
    ):
        if ratio not in (None, "adaptive"):
            conflicts.append("当前任务 ratio 必须为 adaptive")
    if primary != "edit" and duration is not None:
        try:
            duration_value = (
                _duration_decimal(duration)
                if duration != -1
                else Decimal("-1")
            )
        except InvalidOperation:
            duration_value = None
        if duration_value is None or (
            duration_value != Decimal("-1")
            and not Decimal("4") <= duration_value <= _profile_limit(profile)
        ):
            conflicts.append("duration 必须为 -1 或 4 至模型上限秒")
    if conflicts:
        ready = False
        message = "；".join(conflicts)
        advisories.append(
            {
                "type": "参数提示",
                "code": "REQUEST_PARAMETER_CONFLICT",
                "message": message,
            }
        )
        issues.append(
            _issue(
                "REQUEST_PARAMETER_CONFLICT",
                "WARN",
                "request",
                "request_configuration",
                message,
                ("submission",),
            )
        )
    if (
        primary in {"edit", "extend"}
        and output_format in (None, "mp4")
    ):
        advisories.append(
            {
                "type": "参数提示",
                "code": "MOV_RECOMMENDED",
                "message": (
                    "视频编辑和视频延长建议使用 mov 作为输入与输出，"
                    "以改善色彩保真度和声画衔接；此项为建议，不阻断提交。"
                ),
            }
        )
    return {
        "raw": copy.deepcopy(raw),
        "normalized": normalized,
        "prompt_isolation": True,
    }, issues, advisories, ready


def _generation_source(
    source_document: Any, decisions: Any
) -> tuple[Any, str]:
    if isinstance(decisions, dict) and "generation" in decisions:
        raw_decision_generation = decisions.get("generation")
        if not isinstance(raw_decision_generation, dict):
            return copy.deepcopy(raw_decision_generation), "decisions"
    else:
        raw_decision_generation = {}
    if raw_decision_generation:
        raw_source_generation = (
            source_document.get("generation", {})
            if isinstance(source_document, dict)
            else {}
        )
        merged = (
            copy.deepcopy(raw_source_generation)
            if isinstance(raw_source_generation, dict)
            else {}
        )
        merged.update(copy.deepcopy(raw_decision_generation))
        return merged, "decisions"
    if isinstance(source_document, dict) and "generation" in source_document:
        raw_source_generation = source_document.get("generation")
        if not isinstance(raw_source_generation, dict):
            return copy.deepcopy(raw_source_generation), "input"
    else:
        raw_source_generation = {}
    source_generation = (
        copy.deepcopy(raw_source_generation)
        if isinstance(raw_source_generation, dict)
        else {}
    )
    if source_generation:
        return source_generation, "input"
    v2_generation = _generation_from_v2_documents(
        source_document, decisions
    )
    if v2_generation:
        return v2_generation, "task"
    return {"mode": "t2v"}, "default_t2v"


def _validate_generation_context(
    raw_generation: Any,
    source_document: Any,
    shots: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
    *,
    mode_source: str,
    runtime_decisions_hash: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    invalid_shot_ids: set[str] = set()
    global_blocked = False
    if not isinstance(raw_generation, dict):
        global_blocked = True
        issues.append(
            _issue(
                "GENERATION_CONTRACT_INVALID",
                "ERROR",
                "generation",
                "generation",
                "generation 必须是 JSON 对象。",
                ("prompt_compilation",),
            )
        )
    generation = _as_dict(raw_generation)
    mode = _clean_text(generation.get("mode")).lower()
    if mode not in GENERATION_MODES:
        global_blocked = True
        issues.append(
            _issue(
                "MODE_GATE_BLOCKED",
                "ERROR",
                "generation",
                "generation.mode",
                f"未知 generation mode：{mode or '<empty>'}。",
                ("prompt_compilation",),
            )
        )

    supported_modes = profile.get("capabilities", {}).get(
        "supported_generation_modes", []
    )
    if mode in GENERATION_MODES and mode not in supported_modes:
        global_blocked = True
        issues.append(
            _issue(
                "MODE_GATE_BLOCKED",
                "ERROR",
                "generation",
                "generation.mode",
                "当前 Model Profile 不支持所选 generation mode。",
                ("prompt_compilation",),
            )
        )

    available_raw = generation.get("available_reference_tags", [])
    available_tags: list[str] = []
    if not isinstance(available_raw, list) or any(
        not isinstance(tag, str) or not tag for tag in available_raw
    ):
        global_blocked = True
        issues.append(
            _issue(
                "REFERENCE_TAG_INVALID",
                "ERROR",
                "generation",
                "generation.available_reference_tags",
                "available_reference_tags 必须是精确、非空字符串数组。",
                ("prompt_compilation",),
            )
        )
    else:
        available_tags = list(available_raw)
        if len(set(available_tags)) != len(available_tags):
            global_blocked = True
            issues.append(
                _issue(
                    "REFERENCE_TAG_INVALID",
                    "ERROR",
                    "generation",
                    "generation.available_reference_tags",
                    "available_reference_tags 不得重复。",
                    ("prompt_compilation",),
                )
            )

    role_map_raw = generation.get("reference_role_map", [])
    if not isinstance(role_map_raw, list):
        global_blocked = True
        role_map_raw = []
        issues.append(
            _issue(
                "REFERENCE_ROLE_INVALID",
                "ERROR",
                "generation",
                "generation.reference_role_map",
                "reference_role_map 必须是数组。",
                ("prompt_compilation",),
            )
        )

    shot_positions = _shot_id_positions(shots)
    validated_roles: list[dict[str, Any]] = []
    mapped_tags: set[str] = set()
    mapped_role_keys: set[tuple[str, str, tuple[str, ...]]] = set()
    allow_multi_role_per_tag = _clean_text(
        profile.get("capabilities", {})
        .get("reference_tag_convention", {})
        .get("convention_id")
    ) == "preserve-explicit-v1"
    for index, raw_role in enumerate(role_map_raw):
        path = f"generation.reference_role_map[{index}]"
        if not isinstance(raw_role, dict):
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    path,
                    "reference role 必须是对象。",
                    ("prompt_compilation",),
                )
            )
            continue
        tag = _clean_text(raw_role.get("tag"))
        media_type = _clean_text(raw_role.get("media_type")).lower()
        role = _clean_text(raw_role.get("role"))
        applies = raw_role.get("applies_to_shot_ids")
        preserve = raw_role.get("preserve", [])
        valid = True
        candidate_applies = {
            shot_id
            for shot_id in (applies if isinstance(applies, list) else [])
            if isinstance(shot_id, str)
            and (
                shot_id == "*"
                or len(shot_positions.get(shot_id, [])) == 1
            )
        }

        role_key = (
            tag,
            role,
            tuple(applies) if isinstance(applies, list) else (),
        )
        if role_key in mapped_role_keys or (
            tag in mapped_tags and not allow_multi_role_per_tag
        ):
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.tag",
                    (
                        "reference tag 的同一职责不得重复。"
                        if allow_multi_role_per_tag
                        else "每个 reference tag 只能承担一个显式角色。"
                    ),
                    ("prompt_compilation",),
                )
            )
        mapped_tags.add(tag)
        mapped_role_keys.add(role_key)
        if tag not in available_tags:
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_TAG_UNMAPPED",
                    "ERROR",
                    "generation",
                    f"{path}.tag",
                    "role map 的 tag 未列入 available_reference_tags。",
                    ("prompt_compilation",),
                )
            )
        if media_type not in {"image", "video", "audio"}:
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.media_type",
                    "media_type 必须显式为 image、video 或 audio。",
                    ("prompt_compilation",),
                )
            )
        elif not _reference_tag_valid(tag, media_type, profile):
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_TAG_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.tag",
                    "tag 不符合当前 Model Profile 对该 media_type 的 convention。",
                    ("prompt_compilation",),
                )
            )
        if role not in REFERENCE_ROLE_MEDIA:
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.role",
                    "未知 reference role。",
                    ("prompt_compilation",),
                )
            )
        elif media_type not in REFERENCE_ROLE_MEDIA[role]:
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.role",
                    "reference role 与显式 media_type 不兼容。",
                    ("prompt_compilation",),
                )
            )
        if not isinstance(applies, list) or not applies or any(
            not isinstance(shot_id, str)
            or not shot_id.strip()
            or (
                shot_id != "*"
                and len(shot_positions.get(shot_id, [])) != 1
            )
            for shot_id in (applies if isinstance(applies, list) else [])
        ) or (
            isinstance(applies, list)
            and len(set(applies)) != len(applies)
        ):
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.applies_to_shot_ids",
                    "reference 必须限定到唯一存在的 source shot ID。",
                    ("prompt_compilation",),
                )
            )
        if not isinstance(preserve, list) or any(
            not isinstance(item, str) or not item.strip() for item in preserve
        ):
            valid = False
            issues.append(
                _issue(
                    "REFERENCE_ROLE_INVALID",
                    "ERROR",
                    "generation",
                    f"{path}.preserve",
                    "preserve 必须是非空字符串组成的数组。",
                    ("prompt_compilation",),
                )
            )
        preserve_terms = _anti_slop_terms_in_value(preserve)
        if preserve_terms:
            valid = False
            issues.append(
                _issue(
                    "DOWNSTREAM_ANTI_SLOP",
                    "ERROR",
                    "generation",
                    f"{path}.preserve",
                    (
                        "下游 reference preserve 含空泛强化词："
                        f"{', '.join(preserve_terms)}；未改写且不进入正文。"
                    ),
                    ("prompt_compilation",),
                )
            )
        if not valid:
            invalid_shot_ids.update(candidate_applies)
        if valid:
            validated_roles.append(
                {
                    "tag": tag,
                    "media_type": media_type,
                    "role": role,
                    "applies_to_shot_ids": list(applies),
                    "preserve": list(preserve),
                }
            )

    for tag in available_tags:
        if tag not in mapped_tags:
            issues.append(
                _issue(
                    "REFERENCE_TAG_UNMAPPED",
                    "ERROR",
                    "generation",
                    "generation.available_reference_tags",
                    f"available tag {tag} 没有唯一 role map。",
                    ("prompt_compilation",),
                )
            )

    edit_scope_raw = generation.get("edit_scope", [])
    edit_scope_valid = (
        isinstance(edit_scope_raw, list)
        and bool(edit_scope_raw)
        and all(
            isinstance(item, str) and bool(item.strip())
            for item in edit_scope_raw
        )
        and len(set(edit_scope_raw)) == len(edit_scope_raw)
    )
    edit_scope = list(edit_scope_raw) if edit_scope_valid else []
    edit_deltas_raw = generation.get("edit_deltas", [])
    edit_deltas_list = (
        list(edit_deltas_raw)
        if isinstance(edit_deltas_raw, list)
        else []
    )
    edit_deltas: list[dict[str, Any]] = []
    edit_invalid_shot_ids: set[str] = set()
    if mode == "edit" and (
        not edit_scope_valid
        or not isinstance(edit_deltas_raw, list)
        or not edit_deltas_raw
    ):
        edit_invalid_shot_ids.update(shot_positions)
        issues.append(
            _issue(
                "EDIT_SCOPE_INVALID",
                "ERROR",
                "generation",
                "generation.edit_scope",
                "edit 需要非空、不重复的 edit_scope 和 edit_deltas。",
                ("prompt_compilation",),
            )
        )
    for delta_index, delta in enumerate(edit_deltas_list):
        applies = (
            delta.get("applies_to_shot_ids", [])
            if isinstance(delta, dict)
            else []
        )
        candidate_values: Iterable[Any]
        if isinstance(applies, list):
            candidate_values = applies
        elif isinstance(applies, str):
            candidate_values = [applies]
        elif isinstance(applies, dict):
            candidate_values = applies.keys()
        else:
            candidate_values = []
        delta_candidate_shots = {
            shot_id
            for value in candidate_values
            if isinstance(value, str)
            for shot_id in [value]
            if len(shot_positions.get(shot_id, [])) == 1
        }
        if not delta_candidate_shots:
            delta_candidate_shots = set(shot_positions)
        applies_valid = (
            isinstance(applies, list)
            and bool(applies)
            and all(
                isinstance(shot_id, str)
                and bool(shot_id.strip())
                and len(shot_positions.get(shot_id, [])) == 1
                for shot_id in applies
            )
            and len(set(applies)) == len(applies)
        )
        delta_valid = (
            isinstance(delta, dict)
            and _clean_text(delta.get("layer")) in edit_scope
            and bool(_clean_text(delta.get("instruction")))
            and applies_valid
        )
        if not delta_valid:
            if mode == "edit":
                edit_invalid_shot_ids.update(delta_candidate_shots)
            issues.append(
                _issue(
                    "EDIT_SCOPE_INVALID",
                    "ERROR",
                    "generation",
                    f"generation.edit_deltas[{delta_index}]",
                    (
                        "edit delta 必须只修改 edit_scope 声明层、包含明确 "
                        "instruction，并以非空字符串数组限定 "
                        "applies_to_shot_ids。"
                    ),
                    ("prompt_compilation",),
                )
            )
        elif _anti_slop_terms_in_value(delta.get("instruction")):
            if mode == "edit":
                edit_invalid_shot_ids.update(delta_candidate_shots)
            terms = _anti_slop_terms_in_value(delta.get("instruction"))
            issues.append(
                _issue(
                    "DOWNSTREAM_ANTI_SLOP",
                    "ERROR",
                    "generation",
                    f"generation.edit_deltas[{delta_index}].instruction",
                    (
                        "下游 edit delta 含空泛强化词："
                        f"{', '.join(terms)}；未改写且不进入正文。"
                    ),
                    ("prompt_compilation",),
                )
            )
        else:
            edit_deltas.append(
                {
                    "layer": _clean_text(delta.get("layer")),
                    "instruction": _clean_text(delta.get("instruction")),
                    "applies_to_shot_ids": list(applies),
                }
            )
    extend_context = _as_dict(generation.get("extend_context"))
    extend_context_valid = (
        extend_context.get("accepted_material") is True
        and bool(_clean_text(extend_context.get("observed_end_state")))
    )

    def invalidate_shot(shot_id: str, message: str, path: str) -> None:
        invalid_shot_ids.add(shot_id)
        issues.append(
            _issue(
                "MODE_UNIT_REFERENCE_INVALID",
                "ERROR",
                "shot",
                path,
                message,
                ("prompt_compilation",),
            )
        )

    for shot_index, shot in enumerate(shots):
        shot_id = str(shot["source_shot_id"])
        shot_roles = [
            item
            for item in validated_roles
            if "*" in item["applies_to_shot_ids"]
            or shot_id in item["applies_to_shot_ids"]
        ]
        image_roles = [
            item for item in shot_roles if item["media_type"] == "image"
        ]
        video_roles = [
            item for item in shot_roles if item["media_type"] == "video"
        ]
        shot_path = f"shots[{shot_index}]({shot_id})"
        if mode == "t2v" and shot_roles:
            invalidate_shot(
                shot_id,
                "t2v Cut 不接受媒体 reference。",
                shot_path,
            )
        elif mode == "i2v" and not image_roles:
            invalidate_shot(
                shot_id,
                "i2v Cut 缺少适用于该源镜的显式 image reference。",
                shot_path,
            )
        elif mode == "v2v" and not video_roles:
            invalidate_shot(
                shot_id,
                "v2v Cut 缺少适用于该源镜的显式 video reference。",
                shot_path,
            )
        elif mode == "r2v" and not shot_roles:
            invalidate_shot(
                shot_id,
                "r2v Cut 缺少适用于该源镜的精确 role reference。",
                shot_path,
            )
        elif mode == "flf2v":
            first_tags = {
                item["tag"]
                for item in image_roles
                if item["role"] == "first_frame"
            }
            last_tags = {
                item["tag"]
                for item in image_roles
                if item["role"] == "last_frame"
            }
            if (
                len(first_tags) != 1
                or len(last_tags) != 1
                or first_tags == last_tags
            ):
                invalidate_shot(
                    shot_id,
                    "flf2v Cut 需要不同 tag 的唯一 first_frame 与 last_frame。",
                    shot_path,
                )
        elif mode == "edit":
            edit_source_tags = {
                item["tag"]
                for item in shot_roles
                if item["role"] == "edit_source"
            }
            has_applicable_delta = any(
                isinstance(delta, dict)
                and shot_id in delta.get("applies_to_shot_ids", [])
                for delta in edit_deltas
            )
            if (
                len(edit_source_tags) != 1
                or shot_id in edit_invalid_shot_ids
                or not has_applicable_delta
            ):
                invalidate_shot(
                    shot_id,
                    (
                        "edit Cut 需要唯一且适用于该源镜的 edit_source、合法 "
                        "edit_scope 与 edit delta。"
                    ),
                    shot_path,
                )
        elif mode == "extend":
            extension_source_tags = {
                item["tag"]
                for item in shot_roles
                if item["role"] == "extension_source"
            }
            if len(extension_source_tags) != 1 or not extend_context_valid:
                invalidate_shot(
                    shot_id,
                    (
                        "extend Cut 需要唯一且适用于该源镜的 extension_source、"
                        "已接受素材和观测结束状态；不要求回流上游。"
                    ),
                    shot_path,
                )

    context = {
        "mode": mode,
        "mode_source": mode_source,
        "available_reference_tags": available_tags,
        "reference_role_map": validated_roles,
        "edit_scope": edit_scope,
        "edit_deltas": edit_deltas,
        "extend_context": extend_context,
        "runtime_decisions_hash": runtime_decisions_hash,
        "global_blocked": global_blocked,
        "invalid_shot_ids": [
            str(shot["source_shot_id"])
            for shot in shots
            if str(shot["source_shot_id"]) in invalid_shot_ids
        ],
    }
    for key in (
        "asset_assignments",
        "asset_binding",
        "unused_assets",
        "story_contract",
        "task_modules",
        "global_reference_section",
        "operation_dependency",
    ):
        if key in generation:
            context[key] = copy.deepcopy(generation.get(key))
    return context, _deduplicate_issues(issues)
