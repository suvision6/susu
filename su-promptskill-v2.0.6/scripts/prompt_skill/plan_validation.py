"""su-promptskill internal module: plan recompilation validation."""

from __future__ import annotations

from . import plan as _previous

globals().update({
    key: value
    for key, value in vars(_previous).items()
    if not key.startswith("__")
})

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Responsibility module behind scripts/prompt_delivery.py."

def _validate_compiler_inputs(
    normalized: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> tuple[Any, Any, list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    compiler_inputs = plan.get("compiler_inputs")
    if not isinstance(compiler_inputs, dict):
        return (
            None,
            None,
            [
                _issue(
                    "COMPILER_INPUTS_INVALID",
                    "ERROR",
                    "plan",
                    "compiler_inputs",
                    "plan 缺少可重编译的 compiler_inputs 快照。",
                    ("prompt_delivery",),
                )
            ],
        )

    normalized_snapshot = compiler_inputs.get("normalized_source")
    expected_normalized_snapshot = _normalized_source_snapshot(normalized)
    if (
        compiler_inputs.get("contract") != COMPILER_INPUTS_CONTRACT
        or normalized_snapshot != expected_normalized_snapshot
        or compiler_inputs.get("normalized_source_hash")
        != sha256_json(expected_normalized_snapshot)
    ):
        issues.append(
            _issue(
                "COMPILER_INPUTS_INVALID",
                "ERROR",
                "plan",
                "compiler_inputs.normalized_source",
                (
                    "normalized source 快照、合同或 hash "
                    "与当前只读来源不一致。"
                ),
                ("prompt_delivery", "source_traceability"),
            )
        )

    decisions_snapshot = copy.deepcopy(
        compiler_inputs.get("decisions_snapshot")
    )
    expected_decisions_hash = (
        sha256_json(decisions_snapshot)
        if decisions_snapshot is not None
        else None
    )
    if (
        compiler_inputs.get("runtime_decisions_hash")
        != expected_decisions_hash
    ):
        issues.append(
            _issue(
                "COMPILER_INPUTS_INVALID",
                "ERROR",
                "plan",
                "compiler_inputs.runtime_decisions_hash",
                "decisions snapshot hash 不一致。",
                ("prompt_delivery",),
            )
        )

    runtime_profile = copy.deepcopy(
        compiler_inputs.get("runtime_profile")
    )
    try:
        expected_profile_hash = sha256_json(runtime_profile)
    except DeliveryError:
        expected_profile_hash = None
    if (
        expected_profile_hash is None
        or compiler_inputs.get("runtime_profile_hash")
        != expected_profile_hash
        or runtime_profile != plan.get("model_profile")
    ):
        issues.append(
            _issue(
                "COMPILER_INPUTS_INVALID",
                "ERROR",
                "plan",
                "compiler_inputs.runtime_profile",
                "runtime Profile 快照、hash 或 plan metadata 不一致。",
                ("prompt_delivery",),
            )
        )
    return decisions_snapshot, runtime_profile, issues


def _validate_plan_structure(
    normalized: Mapping[str, Any],
    plan: Any,
    check_content_hash: bool,
    source_document: Any = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(plan, dict):
        return [
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "$",
                "prompt_plan 必须是 JSON 对象。",
                ("prompt_delivery",),
            )
        ]

    if (
        plan.get("contract_name") != PLAN_CONTRACT_NAME
        or plan.get("contract_version") != PLAN_CONTRACT_VERSION
    ):
        issues.append(
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "contract_name",
                f"输出合同必须是 {PLAN_CONTRACT_NAME}/{PLAN_CONTRACT_VERSION}。",
                ("prompt_delivery",),
            )
        )

    if plan.get("skill") != {"name": SKILL_NAME, "version": SKILL_VERSION}:
        issues.append(
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "skill",
                f"Skill identity 必须是 {SKILL_NAME} {SKILL_VERSION}。",
                ("prompt_delivery",),
            )
        )

    v2_shapes = {
        "task": dict,
        "operations": list,
        "story_contract": dict,
        "required_entities": list,
        "dialogue_ledger": list,
        "asset_binding": dict,
        "asset_inventory": dict,
        "asset_assignments": list,
        "unused_assets": list,
        "request_configuration": dict,
        "prompt_advisories": list,
    }
    for field_name, expected_type in v2_shapes.items():
        if not isinstance(plan.get(field_name), expected_type):
            issues.append(
                _issue(
                    "OUTPUT_CONTRACT_INVALID",
                    "ERROR",
                    "plan",
                    field_name,
                    f"{field_name} 必须是 v2 合同要求的 {expected_type.__name__}。",
                    ("prompt_delivery",),
                )
            )
    if plan.get("mapping_confidence") not in {"high", "medium", "low"}:
        issues.append(
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "mapping_confidence",
                "mapping_confidence 必须为 high、medium 或 low。",
                ("prompt_delivery",),
            )
        )
    if not isinstance(plan.get("submission_ready"), bool):
        issues.append(
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "submission_ready",
                "submission_ready 必须为布尔值。",
                ("prompt_delivery",),
            )
        )
    if isinstance(plan.get("model_profile"), dict):
        asset_binding = plan.get("asset_binding", {})
        if asset_binding.get("state") not in {"mapped", "unmapped"}:
            issues.append(
                _issue(
                    "ASSET_BINDING_INVALID",
                    "ERROR",
                    "plan",
                    "asset_binding",
                    "asset_binding.state 必须为 mapped 或 unmapped。",
                    ("prompt_delivery",),
                )
            )

    delivery = plan.get("delivery")
    if not isinstance(delivery, dict):
        issues.append(
            _issue(
                "DELIVERY_NAMING_INVALID",
                "ERROR",
                "plan",
                "delivery",
                "输出缺少按输入文件名派生的交付命名信息。",
                ("delivery_integrity",),
            )
        )
    else:
        slug = _clean_text(delivery.get("slug"))
        try:
            expected_files = delivery_file_map(slug)
        except DeliveryError:
            expected_files = {}
        actual_files = delivery.get("files")
        if (
            not slug
            or _ascii_kebab_slug(slug) != slug
            or actual_files != expected_files
            or len(set(expected_files.values())) != 4
            or any(
                "prompt" not in name
                for name in expected_files.values()
            )
        ):
            issues.append(
                _issue(
                    "DELIVERY_NAMING_INVALID",
                    "ERROR",
                    "plan",
                    "delivery",
                    "正式文件名必须使用 ASCII kebab-case 输入前缀并包含 prompt。",
                    ("delivery_integrity",),
                )
            )

    _, _, compiler_input_issues = _validate_compiler_inputs(
        normalized, plan
    )
    issues.extend(compiler_input_issues)

    source_metadata = plan.get("source")
    if not isinstance(source_metadata, dict):
        source_metadata = {}
        issues.append(
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "source",
                "输出缺少 source provenance。",
                ("prompt_delivery",),
            )
        )
    else:
        for key in (
            "source_mode",
            "source_contract",
            "source_skill",
            "source_skill_version",
            "project_id",
            "source_content_hash",
            "observed_content_hash",
            "local_content_hash",
            "source_read_only",
            "source_shot_count",
        ):
            if source_metadata.get(key) != normalized["source"].get(key):
                issues.append(
                    _issue(
                        "SOURCE_PROVENANCE_MISMATCH",
                        "ERROR",
                        "plan",
                        f"source.{key}",
                        f"输出 source.{key} 与当前来源不一致。",
                        ("source_traceability",),
                    )
                )

    profile = plan.get("model_profile")
    issues.extend(validate_model_profile(profile))
    profile_valid = not validate_model_profile(profile)
    grouping_policy = (
        _grouping_policy(profile) if profile_valid else DEFAULT_GROUPING_POLICY
    )
    max_group_cuts = int(grouping_policy["max_cuts"])
    max_group_duration = Decimal(grouping_policy["max_duration_seconds"])
    generation = plan.get("generation")
    generation_global_blocked = True
    generation_invalid_shot_ids: set[str] = set()
    if not isinstance(generation, dict):
        generation = {}
        issues.append(
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "generation",
                "输出缺少独立 generation context。",
                ("prompt_delivery",),
            )
        )
    elif profile_valid:
        generation_global_blocked = generation.get("global_blocked") is True
        raw_invalid_shot_ids = generation.get("invalid_shot_ids", [])
        if isinstance(raw_invalid_shot_ids, list):
            generation_invalid_shot_ids = {
                str(shot_id) for shot_id in raw_invalid_shot_ids
            }
        mode_source = _clean_text(generation.get("mode_source"))
        runtime_hash = generation.get("runtime_decisions_hash")
        if mode_source not in {
            "decisions",
            "input",
            "task",
            "default_t2v",
            "unresolved",
        }:
            issues.append(
                _issue(
                    "OUTPUT_CONTRACT_INVALID",
                    "ERROR",
                    "plan",
                    "generation.mode_source",
                    "generation.mode_source 无效。",
                    ("prompt_delivery",),
                )
            )
        if runtime_hash is not None and (
            not isinstance(runtime_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", runtime_hash) is None
        ):
            issues.append(
                _issue(
                    "OUTPUT_CONTRACT_INVALID",
                    "ERROR",
                    "plan",
                    "generation.runtime_decisions_hash",
                    "runtime decisions hash 必须为 null 或小写 SHA-256。",
                    ("prompt_delivery",),
                )
            )
        validated_generation, generation_issues = _validate_generation_context(
            generation,
            source_document if source_document is not None else {},
            normalized.get("shots", []),
            profile,
            mode_source=mode_source,
            runtime_decisions_hash=(
                runtime_hash if isinstance(runtime_hash, str) else None
            ),
        )
        issues.extend(generation_issues)
        if validated_generation != generation:
            issues.append(
                _issue(
                    "OUTPUT_CONTRACT_INVALID",
                    "ERROR",
                    "plan",
                    "generation",
                    "generation context 不是规范化 Mode Gate 结果。",
                    ("prompt_delivery",),
                )
            )
    operations_raw = plan.get("operations")
    operation_generations: dict[str, Mapping[str, Any]] = {
        "OP001": generation
    }
    operation_invalid_shots: dict[str, set[str]] = {
        "OP001": generation_invalid_shot_ids
    }
    operation_global_blocked: dict[str, bool] = {
        "OP001": generation_global_blocked
    }
    operation_order: list[str] = ["OP001"]
    if isinstance(operations_raw, list) and operations_raw:
        operation_generations = {}
        operation_invalid_shots = {}
        operation_global_blocked = {}
        operation_order = []
        seen_operation_ids: set[str] = set()
        for operation_index, operation in enumerate(operations_raw):
            path = f"operations[{operation_index}]"
            if not isinstance(operation, dict):
                issues.append(
                    _issue(
                        "OPERATION_CONTRACT_INVALID",
                        "ERROR",
                        "operation",
                        path,
                        "operation 必须是 JSON 对象。",
                        ("prompt_delivery",),
                    )
                )
                continue
            operation_id = _clean_text(operation.get("operation_id"))
            dependency = _clean_text(
                operation.get("depends_on_operation_id")
            ) or None
            op_generation = operation.get("generation")
            if (
                not operation_id
                or operation_id in seen_operation_ids
                or operation.get("order") != operation_index + 1
                or (dependency is not None and dependency not in seen_operation_ids)
                or not isinstance(op_generation, dict)
            ):
                issues.append(
                    _issue(
                        "OPERATION_CONTRACT_INVALID",
                        "ERROR",
                        "operation",
                        path,
                        "operation ID、order、依赖或 generation 无效。",
                        ("prompt_delivery",),
                    )
                )
                continue
            seen_operation_ids.add(operation_id)
            operation_order.append(operation_id)
            operation_generations[operation_id] = op_generation
            raw_invalid = op_generation.get("invalid_shot_ids", [])
            operation_invalid_shots[operation_id] = {
                str(value)
                for value in raw_invalid
                if isinstance(raw_invalid, list)
            }
            operation_global_blocked[operation_id] = (
                op_generation.get("global_blocked") is True
            )
    elif operations_raw not in (None, []):
        issues.append(
            _issue(
                "OPERATION_CONTRACT_INVALID",
                "ERROR",
                "operation",
                "operations",
                "operations 必须是非空数组。",
                ("prompt_delivery",),
            )
        )
    prompt_units = plan.get("prompt_units")
    if not isinstance(prompt_units, list):
        prompt_units = []
        issues.append(
            _issue(
                "OUTPUT_CONTRACT_INVALID",
                "ERROR",
                "plan",
                "prompt_units",
                "prompt_units 必须是数组。",
                ("prompt_delivery",),
            )
        )
    if (
        len(operation_order) == 1
        and operation_global_blocked.get(operation_order[0], True)
        and prompt_units
    ):
        issues.append(
            _issue(
                "GLOBAL_MODE_GATE_BYPASSED",
                "ERROR",
                "plan",
                "prompt_units",
                "全局 Mode Gate 已阻断，但输出仍包含 Prompt 单元。",
                ("prompt_delivery",),
            )
        )

    source_shots = normalized.get("shots", [])
    flattened_ids_by_operation: dict[str, list[str]] = {
        operation_id: [] for operation_id in operation_order
    }
    source_cursors: dict[str, int] = {
        operation_id: 0 for operation_id in operation_order
    }
    for unit_index, unit in enumerate(prompt_units):
        unit_path = f"prompt_units[{unit_index}]"
        if not isinstance(unit, dict):
            issues.append(
                _issue(
                    "OUTPUT_CONTRACT_INVALID",
                    "ERROR",
                    "unit",
                    unit_path,
                    "Prompt 单元必须是对象。",
                    ("prompt_delivery",),
                )
            )
            continue
        expected_unit_id = f"PU{unit_index + 1:03d}"
        if unit.get("prompt_unit_id") != expected_unit_id:
            issues.append(
                _issue(
                    "OUTPUT_CONTRACT_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.prompt_unit_id",
                    f"单元 ID 必须是 {expected_unit_id}。",
                    ("prompt_delivery",),
                )
            )
        blocks = unit.get("prompt_blocks")
        prompt_text_value = unit.get("prompt_text")
        blocks_invalid = (
            not isinstance(blocks, list)
            or (
                bool(prompt_text_value)
                and (
                    not blocks
                    or any(not isinstance(block, dict) for block in blocks)
                    or [block.get("block_id") for block in blocks]
                    != [f"PB{index + 1:03d}" for index in range(len(blocks))]
                    or "\n\n".join(
                        str(block.get("text", "")) for block in blocks
                    )
                    != prompt_text_value
                )
            )
            or (not prompt_text_value and blocks != [])
        )
        if blocks_invalid:
            issues.append(
                _issue(
                    "PROMPT_BLOCK_CONTRACT_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.prompt_blocks",
                    "prompt_blocks 必须有序且逐字重建 prompt_text。",
                    ("prompt_delivery",),
                )
            )

        unit_operation_id = _clean_text(unit.get("operation_id")) or "OP001"
        if unit_operation_id not in operation_generations:
            issues.append(
                _issue(
                    "OPERATION_CONTRACT_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.operation_id",
                    "Prompt 单元引用了不存在的 operation。",
                    ("prompt_delivery",),
                )
            )
            unit_operation_id = operation_order[0] if operation_order else "OP001"
        unit_operation_generation = operation_generations.get(
            unit_operation_id, generation
        )
        unit_invalid_shot_ids = operation_invalid_shots.get(
            unit_operation_id, set()
        )
        shot_ids = unit.get("source_shot_ids")
        if not isinstance(shot_ids, list) or not shot_ids:
            issues.append(
                _issue(
                    "CUT_SOURCE_MISMATCH",
                    "ERROR",
                    "unit",
                    f"{unit_path}.source_shot_ids",
                    "单元必须引用至少一个来源镜头。",
                    ("prompt_delivery",),
                )
            )
            shot_ids = []
        flattened_ids_by_operation.setdefault(unit_operation_id, []).extend(
            str(item) for item in shot_ids
        )
        source_cursor = source_cursors.get(unit_operation_id, 0)
        expected_shots = source_shots[
            source_cursor : source_cursor + len(shot_ids)
        ]
        unit_generation = _generation_for_unit(
            unit_operation_generation, expected_shots
        )
        expected_ids = [shot["source_shot_id"] for shot in expected_shots]
        if shot_ids != expected_ids:
            issues.append(
                _issue(
                    "CUT_SOURCE_MISMATCH",
                    "ERROR",
                    "unit",
                    f"{unit_path}.source_shot_ids",
                    "单元来源镜号未按 shots[] 连续顺序映射。",
                    ("prompt_delivery",),
                )
            )
        source_cursors[unit_operation_id] = source_cursor + len(shot_ids)

        prompt_validation = (
            unit.get("prompt_validation")
            if isinstance(unit.get("prompt_validation"), dict)
            else {}
        )
        diagnostic_codes = prompt_validation.get("diagnostic_codes", [])
        generation_failed = (
            isinstance(diagnostic_codes, list)
            and "GENERATION_CONTEXT_INVALID" in diagnostic_codes
        )
        unreadable_failed = (
            isinstance(diagnostic_codes, list)
            and "INPUT_MATERIAL_UNREADABLE" in diagnostic_codes
        )
        expected_invalid_ids = {
            str(shot_id)
            for shot_id in expected_ids
            if str(shot_id) in unit_invalid_shot_ids
        }
        if generation_failed and (
            len(expected_ids) != 1 or not expected_invalid_ids
        ):
            issues.append(
                _issue(
                    "GENERATION_FAILURE_SCOPE_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.prompt_validation",
                    "局部 generation 失败单元必须只对应一个已标记无效的源镜。",
                    ("prompt_delivery",),
                )
            )
        if expected_invalid_ids and not generation_failed:
            issues.append(
                _issue(
                    "GENERATION_FAILURE_SCOPE_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.prompt_validation",
                    "无效 reference/mode 源镜未被隔离为局部失败单元。",
                    ("prompt_delivery",),
                )
            )
        expected_unreadable_ids = {
            str(shot["source_shot_id"])
            for shot in expected_shots
            if shot.get("compilable_source") is not True
        }
        if unreadable_failed and (
            len(expected_ids) != 1
            or expected_unreadable_ids != set(expected_ids)
            or prompt_validation.get("status") != "FAIL"
        ):
            issues.append(
                _issue(
                    "UNREADABLE_FAILURE_SCOPE_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.prompt_validation",
                    (
                        "不可读来源单元必须只覆盖一个不可编译源镜，"
                        "并把单元状态标为 FAIL。"
                    ),
                    ("prompt_delivery",),
                )
            )
        if expected_unreadable_ids and not unreadable_failed:
            issues.append(
                _issue(
                    "UNREADABLE_FAILURE_SCOPE_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.prompt_validation",
                    "不可读来源镜头未被隔离为失败单元。",
                    ("prompt_delivery",),
                )
            )

        source_hashes = unit.get("source_shot_hashes")
        expected_hashes = [shot["source_shot_hash"] for shot in expected_shots]
        if source_hashes != expected_hashes:
            issues.append(
                _issue(
                    "CUT_SOURCE_HASH_MISMATCH",
                    "ERROR",
                    "unit",
                    f"{unit_path}.source_shot_hashes",
                    "单元 source shot hash 与实际来源不一致。",
                    ("source_traceability",),
                )
            )

        is_multi = len(shot_ids) > 1
        if is_multi:
            if len(shot_ids) > max_group_cuts:
                issues.append(
                    _issue(
                        "GROUP_DURATION_INVALID",
                        "ERROR",
                        "unit",
                        unit_path,
                        f"多镜单元 Cut 数量超过策略上限 {max_group_cuts}。",
                        ("model_generation",),
                    )
                )
            compatibility = unit.get("semantic_compatibility")
            if not isinstance(compatibility, dict) or any(
                compatibility.get(key) is not True
                for key in COMPATIBILITY_KEYS
            ):
                issues.append(
                    _issue(
                        "GROUP_SEMANTIC_ATTESTATION_MISSING",
                        "ERROR",
                        "unit",
                        f"{unit_path}.semantic_compatibility",
                        "多镜单元缺少完整语义兼容确认。",
                        ("model_generation",),
                    )
                )
            if not _clean_text(unit.get("grouping_reason")):
                issues.append(
                    _issue(
                        "GROUP_SEMANTIC_ATTESTATION_MISSING",
                        "ERROR",
                        "unit",
                        f"{unit_path}.grouping_reason",
                        "多镜单元缺少具体 grouping_reason。",
                        ("model_generation",),
                    )
                )
            if unit.get("partition_strategy") != GROUPING_PARTITION_POLICY:
                issues.append(
                    _issue(
                        "GROUP_PARTITION_ATTESTATION_MISSING",
                        "ERROR",
                        "unit",
                        f"{unit_path}.partition_strategy",
                        "多镜单元缺少确定性场景级分区策略标识。",
                        ("model_generation",),
                    )
                )
            boundary_evidence = unit.get("boundary_evidence")
            if (
                not isinstance(boundary_evidence, list)
                or len(boundary_evidence) != len(shot_ids) - 1
            ):
                issues.append(
                    _issue(
                        "GROUP_BOUNDARY_EVIDENCE_MISSING",
                        "ERROR",
                        "unit",
                        f"{unit_path}.boundary_evidence",
                        "多镜单元必须逐边界携带来源绑定的语义证据。",
                        ("model_generation",),
                    )
                )

        durations: list[Decimal] = []
        for shot in expected_shots:
            try:
                duration = _duration_decimal(shot.get("duration_seconds"))
            except InvalidOperation:
                duration = None
            if duration is not None:
                durations.append(duration)
            if is_multi and duration is None:
                issues.append(
                    _issue(
                        "GROUP_DURATION_INVALID",
                        "ERROR",
                        "unit",
                        unit_path,
                        "多镜单元包含缺时长的来源镜头。",
                        ("model_generation",),
                    )
                )
        expected_total = (
            sum(durations, Decimal("0"))
            if len(durations) == len(expected_shots)
            else None
        )
        actual_total = unit.get("total_duration_seconds")
        if _json_number(expected_total) != actual_total:
            issues.append(
                _issue(
                    "GROUP_DURATION_INVALID",
                    "ERROR",
                    "unit",
                    f"{unit_path}.total_duration_seconds",
                    "单元总时长不等于来源时长通用求和。",
                    ("model_generation",),
                )
            )
        if is_multi and expected_total is not None:
            if expected_total > max_group_duration:
                issues.append(
                    _issue(
                        "GROUP_DURATION_INVALID",
                        "ERROR",
                        "unit",
                        unit_path,
                        (
                            "多镜单元总时长超过策略上限 "
                            f"{_seconds_text(max_group_duration)} 秒。"
                        ),
                        ("model_generation",),
                    )
                )
            if profile_valid and expected_total > _profile_limit(profile):
                issues.append(
                    _issue(
                        "GROUP_DURATION_INVALID",
                        "ERROR",
                        "unit",
                        unit_path,
                        "多镜单元总时长超过 Model Profile 上限。",
                        ("model_generation",),
                    )
                )
            if profile_valid and not profile["capabilities"].get(
                "supports_multi_cut"
            ):
                issues.append(
                    _issue(
                        "MODEL_MULTI_CUT_UNSUPPORTED",
                        "ERROR",
                        "unit",
                        unit_path,
                        "Model Profile 不支持多 Cut。",
                        ("model_generation",),
                    )
                )

        timeline = unit.get("timeline")
        if not isinstance(timeline, list):
            timeline = []
        if len(timeline) != len(shot_ids):
            issues.append(
                _issue(
                    "CUT_COUNT_MISMATCH",
                    "ERROR",
                    "unit",
                    f"{unit_path}.timeline",
                    "Cut 数量与来源镜头数量不一致。",
                    ("prompt_delivery",),
                )
            )

        offset = Decimal("0")
        timeline_known = expected_total is not None
        prompt_text = (
            unit.get("prompt_text")
            if isinstance(unit.get("prompt_text"), str)
            else ""
        )
        all_known_tags = _all_generation_reference_tags(unit_generation)
        if (
            profile_valid
            and _global_reference_section(profile)
            and not generation_failed
            and not unreadable_failed
        ):
            actual_global_tags = set(
                _reference_tags(prompt_text, profile, all_known_tags)
            )
            if actual_global_tags != set(all_known_tags):
                issues.append(
                    _issue(
                        "REFERENCE_TAG_MISMATCH",
                        "ERROR",
                        "prompt",
                        f"{unit_path}.prompt_text",
                        "全局参考素材职责未逐字覆盖 role map 中的全部 tag。",
                        ("prompt_delivery",),
                    )
                )
        if (generation_failed or unreadable_failed) and prompt_text:
            issues.append(
                _issue(
                    (
                        "GENERATION_FAILURE_SCOPE_INVALID"
                        if generation_failed
                        else "UNREADABLE_FAILURE_SCOPE_INVALID"
                    ),
                    "ERROR",
                    "prompt",
                    f"{unit_path}.prompt_text",
                    "局部失败单元不得伪造 Prompt 正文。",
                    ("prompt_delivery",),
                )
            )
        if not generation_failed and not unreadable_failed and not prompt_text:
            issues.append(
                _issue(
                    "PROMPT_TEXT_MISSING",
                    "ERROR",
                    "prompt",
                    f"{unit_path}.prompt_text",
                    "可编译单元缺少 Prompt 正文。",
                    ("prompt_delivery",),
                )
            )
        for cut_index, (cut, shot) in enumerate(zip(timeline, expected_shots)):
            cut_path = f"{unit_path}.timeline[{cut_index}]"
            if not isinstance(cut, dict):
                issues.append(
                    _issue(
                        "CUT_SOURCE_MISMATCH",
                        "ERROR",
                        "cut",
                        cut_path,
                        "Cut 必须是对象。",
                        ("prompt_delivery",),
                    )
                )
                continue
            if (
                cut.get("cut_index") != cut_index + 1
                or cut.get("cut_label") != CUT_LABELS[cut_index]
                or cut.get("source_shot_id") != shot["source_shot_id"]
                or cut.get("source_order") != shot["source_order"]
            ):
                issues.append(
                    _issue(
                        "CUT_SOURCE_MISMATCH",
                        "ERROR",
                        "cut",
                        cut_path,
                        "Cut 标签、ID 或来源顺序不一致。",
                        ("prompt_delivery",),
                    )
                )
            if cut.get("source_shot_hash") != shot["source_shot_hash"]:
                issues.append(
                    _issue(
                        "CUT_SOURCE_HASH_MISMATCH",
                        "ERROR",
                        "cut",
                        f"{cut_path}.source_shot_hash",
                        "Cut source hash 与对应来源镜头不一致。",
                        ("source_traceability",),
                    )
                )
            if cut.get("compiler_provenance") != shot["field_hashes"]:
                issues.append(
                    _issue(
                        "CUT_SOURCE_HASH_MISMATCH",
                        "ERROR",
                        "cut",
                        f"{cut_path}.compiler_provenance",
                        "Cut 字段 provenance 与来源字段不一致。",
                        ("source_traceability",),
                    )
                )

            if timeline_known:
                duration = _duration_decimal(shot["duration_seconds"])
                expected_start = offset
                expected_end = offset + duration
                offset = expected_end
                if (
                    cut.get("start_seconds") != _json_number(expected_start)
                    or cut.get("end_seconds") != _json_number(expected_end)
                    or cut.get("duration_seconds") != _json_number(duration)
                ):
                    issues.append(
                        _issue(
                            "CUT_TIMELINE_INVALID",
                            "ERROR",
                            "cut",
                            cut_path,
                            "Cut 时间线与来源时长累计值不一致。",
                            ("prompt_delivery",),
                        )
                    )
            elif any(
                cut.get(key) is not None
                for key in (
                    "start_seconds",
                    "end_seconds",
                    "duration_seconds",
                )
            ):
                issues.append(
                    _issue(
                        "CUT_TIMELINE_INVALID",
                        "ERROR",
                        "cut",
                        cut_path,
                        "缺时长镜头必须保持 null 时间线。",
                        ("prompt_delivery",),
                    )
                )

            emotion_items = cut.get("emotion_visualization", [])
            if not isinstance(emotion_items, list):
                emotion_items = []
                issues.append(
                    _issue(
                        "EMOTION_VISUALIZATION_INVALID",
                        "ERROR",
                        "cut",
                        f"{cut_path}.emotion_visualization",
                        "emotion_visualization 必须是数组。",
                        ("prompt_delivery",),
                    )
                )
            for emotion_item in emotion_items:
                valid_emotion = (
                    isinstance(emotion_item, dict)
                    and emotion_item.get("provenance")
                    == "derived_emotion_visualization"
                    and _clean_text(emotion_item.get("basis_emotion"))
                    == _clean_text(shot.get("emotion_intent"))
                    and bool(_clean_text(emotion_item.get("text")))
                    and not shot.get("visible_behavior")
                    and bool(_clean_text(shot.get("emotion_intent")))
                )
                if not valid_emotion:
                    issues.append(
                        _issue(
                            "EMOTION_VISUALIZATION_INVALID",
                            "ERROR",
                            "cut",
                            f"{cut_path}.emotion_visualization",
                            "派生情绪 provenance、basis 或触发条件无效。",
                            ("prompt_delivery",),
                        )
                    )
                elif _anti_slop_terms_in_value(emotion_item.get("text")):
                    issues.append(
                        _issue(
                            "DOWNSTREAM_ANTI_SLOP",
                            "ERROR",
                            "cut",
                            f"{cut_path}.emotion_visualization",
                            "下游 emotion visualization 含空泛强化词。",
                            ("prompt_delivery",),
                        )
                    )

            block = _cut_prompt_block(prompt_text, CUT_LABELS[cut_index])
            if not generation_failed and not unreadable_failed:
                missing_dialogue = [
                    text
                    for text in _dialogue_texts(shot["dialogue"])
                    if text not in block
                ]
                if missing_dialogue:
                    issues.append(
                        _issue(
                            "DIALOGUE_MISMATCH",
                            "ERROR",
                            "prompt",
                            f"{unit_path}.prompt_text",
                            f"{CUT_LABELS[cut_index]} 未逐字包含对应来源对白。",
                            ("prompt_delivery",),
                        )
                    )
                visual_covered, continuity_covered = (
                    _cut_source_coverage(shot, block, unit_generation)
                )
                if not visual_covered:
                    issues.append(
                        _issue(
                            "SOURCE_VISUAL_ACTION_MISSING",
                            "ERROR",
                            "prompt",
                            f"{unit_path}.prompt_text",
                            (
                                f"{CUT_LABELS[cut_index]} 未消费来源"
                                "主要画面动作或其结构化等价内容。"
                            ),
                            ("prompt_delivery",),
                        )
                    )
                if not continuity_covered:
                    issues.append(
                        _issue(
                            "CONTINUITY_COVERAGE_MISSING",
                            "ERROR",
                            "prompt",
                            f"{unit_path}.prompt_text",
                            (
                                f"{CUT_LABELS[cut_index]} 未消费来源"
                                "连续性变化或目标终态。"
                            ),
                            ("prompt_delivery",),
                        )
                    )
            if profile_valid and not generation_failed and not unreadable_failed:
                expected_tags = {
                    str(item["tag"])
                    for item in _reference_roles_for_shot(
                        unit_generation, str(shot["source_shot_id"])
                    )
                }
                actual_tags = set(
                    _reference_tags(block, profile, all_known_tags)
                )
                if (
                    not _global_reference_section(profile)
                    and actual_tags != expected_tags
                ):
                    issues.append(
                        _issue(
                            "REFERENCE_TAG_MISMATCH",
                            "ERROR",
                            "prompt",
                            f"{unit_path}.prompt_text",
                            (
                                f"{CUT_LABELS[cut_index]} reference tag "
                                "未与 role map 逐字一致。"
                            ),
                            ("prompt_delivery",),
                        )
                    )
                cut_added_terms = sorted(
                    set(_anti_slop_terms_outside_quotes(block))
                    - set(shot.get("source_anti_slop_terms", []))
                )
                if cut_added_terms:
                    issues.append(
                        _issue(
                            "PROMPT_ANTI_SLOP_FAILED",
                            "ERROR",
                            "prompt",
                            f"{unit_path}.prompt_text",
                            (
                                f"{CUT_LABELS[cut_index]} 含无法追溯到"
                                "对应源镜的空泛强化词："
                                f"{', '.join(cut_added_terms)}。"
                            ),
                            ("prompt_delivery",),
                        )
                    )

        if profile_valid and not generation_failed and not unreadable_failed:
            leaks = _prompt_metadata_leaks(prompt_text, profile)
            if leaks:
                issues.append(
                    _issue(
                        "PROMPT_MODEL_METADATA_LEAK",
                        "ERROR",
                        "prompt",
                        f"{unit_path}.prompt_text",
                        f"Prompt 正文包含 metadata：{', '.join(leaks)}。",
                        ("prompt_delivery",),
                    )
                )
            source_terms = {
                term
                for shot in expected_shots
                for term in shot.get("source_anti_slop_terms", [])
            }
            prompt_terms = set(
                _anti_slop_terms_outside_quotes(prompt_text)
            )
            added_terms = sorted(prompt_terms - source_terms)
            if added_terms:
                issues.append(
                    _issue(
                        "PROMPT_ANTI_SLOP_FAILED",
                        "ERROR",
                        "prompt",
                        f"{unit_path}.prompt_text",
                        (
                            "正文含无法追溯到来源的空泛强化词："
                            f"{', '.join(added_terms)}。"
                        ),
                        ("prompt_delivery",),
                    )
                )

    expected_flattened = [
        shot["source_shot_id"] for shot in normalized.get("shots", [])
    ]
    for operation_id in operation_order:
        if (
            not normalized.get("source_global_blocked", False)
            and not operation_global_blocked.get(operation_id, False)
            and flattened_ids_by_operation.get(operation_id, [])
            != expected_flattened
        ):
            issues.append(
                _issue(
                    "SOURCE_SHOT_COVERAGE_INVALID",
                    "ERROR",
                    "plan",
                    "prompt_units",
                    f"operation {operation_id} 未按序恰好覆盖一次来源镜头。",
                    ("prompt_delivery",),
                )
            )

    if check_content_hash:
        declared_content_hash = plan.get("content_hash")
        observed_content_hash = prompt_plan_content_hash(plan)
        if declared_content_hash != observed_content_hash:
            issues.append(
                _issue(
                    "OUTPUT_HASH_MISMATCH",
                    "ERROR",
                    "plan",
                    "content_hash",
                    "prompt_plan content_hash 与实际内容不一致。",
                    ("prompt_delivery",),
                )
            )
    return _deduplicate_issues(issues)


def _plan_recompilation_issues(
    plan: Mapping[str, Any],
    expected_plan: Mapping[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    actual_units = (
        plan.get("prompt_units", [])
        if isinstance(plan.get("prompt_units"), list)
        else []
    )
    expected_units = (
        expected_plan.get("prompt_units", [])
        if isinstance(expected_plan.get("prompt_units"), list)
        else []
    )
    for unit_index in range(max(len(actual_units), len(expected_units))):
        actual_unit = (
            actual_units[unit_index]
            if unit_index < len(actual_units)
            and isinstance(actual_units[unit_index], dict)
            else {}
        )
        expected_unit = (
            expected_units[unit_index]
            if unit_index < len(expected_units)
            and isinstance(expected_units[unit_index], dict)
            else {}
        )
        if actual_unit.get("prompt_text") != expected_unit.get(
            "prompt_text"
        ):
            issues.append(
                _issue(
                    "PROMPT_RECOMPILE_MISMATCH",
                    "ERROR",
                    "prompt",
                    f"prompt_units[{unit_index}].prompt_text",
                    "Prompt 未逐字匹配可信编译输入的确定性重编译结果。",
                    ("prompt_delivery",),
                )
            )
        if actual_unit.get("prompt_validation") != expected_unit.get(
            "prompt_validation"
        ):
            issues.append(
                _issue(
                    "UNIT_VALIDATION_LEDGER_MISMATCH",
                    "ERROR",
                    "unit",
                    f"prompt_units[{unit_index}].prompt_validation",
                    "单元 checks、status 或诊断账本未匹配重算结果。",
                    ("prompt_delivery",),
                )
            )

    if plan.get("validation") != expected_plan.get("validation"):
        issues.append(
            _issue(
                "TOP_LEVEL_VALIDATION_MISMATCH",
                "ERROR",
                "plan",
                "validation",
                "顶层 validation 未匹配从来源与单元重算的结果。",
                ("prompt_delivery",),
            )
        )
    if plan != expected_plan:
        issues.append(
            _issue(
                "PLAN_RECOMPILATION_MISMATCH",
                "ERROR",
                "plan",
                "$",
                (
                    "prompt_plan 未逐字段匹配由只读来源、decisions、"
                    "generation context 与 runtime Profile 重建的 plan。"
                ),
                ("prompt_delivery",),
            )
        )
    return issues


def validate_prompt_plan(
    source_document: Any, plan: Any
) -> dict[str, Any]:
    normalized, normalization_issues = normalize_input(source_document)
    structural_issues = _validate_plan_structure(
        normalized,
        plan,
        check_content_hash=True,
        source_document=source_document,
    )
    expected_plan: dict[str, Any] | None = None
    recompilation_issues: list[dict[str, Any]] = []
    expected_diagnostics: list[dict[str, Any]] = []
    prompt_units: list[dict[str, Any]] = []

    if isinstance(plan, dict):
        decisions_snapshot, runtime_profile, compiler_input_issues = (
            _validate_compiler_inputs(normalized, plan)
        )
        if not compiler_input_issues:
            plan_delivery = plan.get("delivery", {})
            recompile_slug = (
                _clean_text(plan_delivery.get("slug"))
                if isinstance(plan_delivery, dict)
                else None
            )
            expected_plan = build_prompt_plan(
                source_document,
                decisions=decisions_snapshot,
                model_profile=runtime_profile,
                delivery_slug=recompile_slug,
            )
            recompilation_issues = _plan_recompilation_issues(
                plan, expected_plan
            )
            expected_diagnostics = copy.deepcopy(
                expected_plan.get("diagnostics", [])
            )
            prompt_units = copy.deepcopy(
                expected_plan.get("prompt_units", [])
            )

    if expected_plan is None:
        prompt_units = (
            copy.deepcopy(plan.get("prompt_units", []))
            if isinstance(plan, dict)
            and isinstance(plan.get("prompt_units"), list)
            else []
        )

    all_issues = _deduplicate_issues(
        list(normalization_issues)
        + expected_diagnostics
        + structural_issues
        + recompilation_issues
    )
    report = _validation_object(normalized, prompt_units, all_issues)
    declared_status = (
        plan.get("validation", {}).get("status")
        if isinstance(plan, dict) and isinstance(plan.get("validation"), dict)
        else None
    )
    if declared_status != report["status"]:
        mismatch = _issue(
            "VALIDATION_STATUS_MISMATCH",
            "ERROR",
            "plan",
            "validation.status",
            (
                f"plan 声明状态 {declared_status!r} 与重算状态 "
                f"{report['status']!r} 不一致。"
            ),
            ("prompt_delivery",),
        )
        all_issues = _deduplicate_issues(all_issues + [mismatch])
        report = _validation_object(normalized, prompt_units, all_issues)
    return report
