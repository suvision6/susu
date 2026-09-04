"""su-promptskill internal module: plan and operation construction."""

from __future__ import annotations

from . import unit_validation as _previous

globals().update({
    key: value
    for key, value in vars(_previous).items()
    if not key.startswith("__")
})

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Responsibility module behind scripts/prompt_delivery.py."

def _build_single_operation_plan(
    source_document: Any,
    decisions: Any = None,
    model_profile: Any = None,
    delivery_slug: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic prompt plan without mutating source_document."""
    normalized, normalization_issues = normalize_input(source_document)
    profile = (
        copy.deepcopy(model_profile)
        if model_profile is not None
        else resolve_model_profile()
    )
    profile_issues = validate_model_profile(profile)
    asset_binding: dict[str, str] = {
        "state": "unmapped",
        "source": "none",
    }
    issues: list[dict[str, Any]] = list(normalization_issues) + profile_issues
    prompt_units: list[dict[str, Any]] = []
    story_contract = _derive_story_contract(
        normalized, source_document, decisions
    )
    required_entities = _derive_required_entities(
        normalized, story_contract
    )
    dialogue_ledger = _derive_dialogue_ledger(normalized)
    asset_inventory: dict[str, Any] = {"complete": False, "items": []}
    asset_assignments: list[dict[str, Any]] = []
    unused_assets: list[str] = []
    mapping_confidence = "high"
    prompt_advisories: list[dict[str, Any]] = []
    request_configuration: dict[str, Any] = {
        "raw": {},
        "normalized": {},
        "prompt_isolation": True,
    }
    submission_ready = True
    task: dict[str, Any] = {
        "primary": "",
        "input_topology": "",
        "modules": [],
        "source": "unresolved",
    }
    generation: dict[str, Any] = {
        "mode": "",
        "mode_source": "unresolved",
        "available_reference_tags": [],
        "reference_role_map": [],
        "edit_scope": [],
        "edit_deltas": [],
        "extend_context": {},
        "runtime_decisions_hash": (
            sha256_json(decisions) if decisions is not None else None
        ),
        "global_blocked": True,
        "invalid_shot_ids": [],
    }

    if not profile_issues:
        generation, generation_issues = resolve_generation_context(
            source_document,
            decisions,
            normalized["shots"],
            profile,
        )
        issues.extend(generation_issues)
        task, task_issues = _normalize_task(
            source_document, decisions, generation, profile
        )
        issues.extend(task_issues)
        (
            asset_inventory,
            asset_assignments,
            unused_assets,
            mapping_confidence,
            asset_issues,
            asset_advisories,
            asset_ready,
        ) = _normalize_asset_context(
            source_document, decisions, profile
        )
        dialogue_ledger = _bind_dialogue_assets(
            dialogue_ledger, asset_assignments
        )
        issues.extend(asset_issues)
        prompt_advisories.extend(asset_advisories)
        submission_ready &= asset_ready
        asset_binding = _normalize_asset_binding(
            source_document,
            decisions,
            asset_assignments,
            generation,
        )
        request_configuration, request_issues, request_advisories, request_ready = (
            _normalize_request_configuration(
                source_document, decisions, profile, task
            )
        )
        issues.extend(request_issues)
        prompt_advisories.extend(request_advisories)
        submission_ready &= request_ready
        generation.update(
            {
                "asset_assignments": copy.deepcopy(asset_assignments),
                "asset_binding": copy.deepcopy(asset_binding),
                "unused_assets": copy.deepcopy(unused_assets),
                "story_contract": copy.deepcopy(story_contract),
                "task_modules": copy.deepcopy(task.get("modules", [])),
                "global_reference_section": _global_reference_section(profile),
            }
        )
        v2_blocking_codes = {
            "TASK_CONTRACT_INVALID",
            "TASK_GENERATION_MISMATCH",
            "CONTENT_ROLE_SCENARIO_CONFLICT",
            "CORE_ASSET_MISSING",
            "ASSET_CARDINALITY_CONFLICT",
        }
        if any(issue.get("code") in v2_blocking_codes for issue in issues):
            generation["global_blocked"] = True
            submission_ready = False
    else:
        generation_issues = []

    profile_has_error = any(
        issue.get("severity") == "ERROR" for issue in profile_issues
    )
    if (
        not profile_has_error
        and not normalized.get("source_global_blocked", False)
        and not generation.get("global_blocked", False)
    ):
        emotion_map, emotion_issues = _validate_emotion_decisions(
            normalized["shots"], decisions
        )
        planned_groups, grouping_issues = _plan_groups(
            normalized["shots"],
            decisions,
            profile,
            _clean_text(
                normalized.get("source", {}).get("observed_content_hash")
            ),
        )
        invalid_shot_ids = {
            str(shot_id)
            for shot_id in generation.get("invalid_shot_ids", [])
        }
        planned_groups = _split_generation_invalid_groups(
            planned_groups, invalid_shot_ids
        )
        unreadable_shot_ids = {
            str(shot["source_shot_id"])
            for shot in normalized["shots"]
            if shot.get("compilable_source") is not True
        }
        planned_groups = _split_unreadable_groups(
            planned_groups, unreadable_shot_ids
        )
        issues.extend(emotion_issues)
        issues.extend(grouping_issues)
        for unit_index, planned in enumerate(planned_groups):
            if any(
                str(shot["source_shot_id"]) in invalid_shot_ids
                for shot in planned["shots"]
            ):
                prompt_units.append(
                    _build_generation_failed_unit(unit_index, planned)
                )
                continue
            if any(
                str(shot["source_shot_id"]) in unreadable_shot_ids
                for shot in planned["shots"]
            ):
                prompt_units.append(
                    _build_unreadable_failed_unit(unit_index, planned)
                )
                continue
            unit, unit_issues = _build_unit(
                unit_index, planned, emotion_map, profile, generation
            )
            prompt_units.append(unit)
            issues.extend(unit_issues)

    for unit in prompt_units:
        unit["operation_id"] = "OP001"
        unit["operation_order"] = 1
        unit["depends_on_operation_id"] = None
        unit["task_primary"] = task.get("primary")

    plan: dict[str, Any] = {
        "contract_name": PLAN_CONTRACT_NAME,
        "contract_version": PLAN_CONTRACT_VERSION,
        "skill": {"name": SKILL_NAME, "version": SKILL_VERSION},
        "delivery": {
            "slug": (
                _ascii_kebab_slug(delivery_slug)
                if delivery_slug is not None
                else derive_delivery_slug(None, source_document)
            ),
            "files": {},
        },
        "compiler_inputs": _compiler_inputs(
            normalized, decisions, profile
        ),
        "source": copy.deepcopy(normalized["source"]),
        "task": copy.deepcopy(task),
        "operations": [
            {
                "operation_id": "OP001",
                "order": 1,
                "depends_on_operation_id": None,
                "task": copy.deepcopy(task),
                "generation": copy.deepcopy(generation),
                "prompt_unit_ids": [
                    unit.get("prompt_unit_id") for unit in prompt_units
                ],
                "submission_ready": submission_ready,
            }
        ],
        "story_contract": copy.deepcopy(story_contract),
        "required_entities": copy.deepcopy(required_entities),
        "dialogue_ledger": copy.deepcopy(dialogue_ledger),
        "asset_binding": copy.deepcopy(asset_binding),
        "asset_inventory": copy.deepcopy(asset_inventory),
        "asset_assignments": copy.deepcopy(asset_assignments),
        "unused_assets": copy.deepcopy(unused_assets),
        "mapping_confidence": mapping_confidence,
        "request_configuration": copy.deepcopy(request_configuration),
        "prompt_advisories": copy.deepcopy(prompt_advisories),
        "submission_ready": submission_ready,
        "generation": copy.deepcopy(generation),
        "model_profile": copy.deepcopy(profile),
        "prompt_units": prompt_units,
        "diagnostics": [],
        "validation": {},
    }
    plan["delivery"]["files"] = delivery_file_map(
        plan["delivery"]["slug"]
    )

    structural_issues = _validate_plan_structure(
        normalized,
        plan,
        check_content_hash=False,
        source_document=source_document,
    )
    issues.extend(structural_issues)
    issues = _deduplicate_issues(issues)
    if any(
        issue.get("code") == "PROMPT_REDUNDANCY_DETECTED"
        for issue in issues
    ):
        plan["submission_ready"] = False
        plan["operations"][0]["submission_ready"] = False
    plan["diagnostics"] = issues
    plan["validation"] = _validation_object(normalized, prompt_units, issues)
    plan["content_hash"] = prompt_plan_content_hash(plan)
    return plan


def _operation_decisions(
    decisions: Any,
    operation: Mapping[str, Any],
    normalized: Mapping[str, Any],
) -> dict[str, Any]:
    result = copy.deepcopy(decisions) if isinstance(decisions, dict) else {}
    result.pop("operations", None)
    if "task" in operation and "generation" not in operation:
        result.pop("generation", None)
    for key in (
        "task",
        "generation",
        "request_configuration",
        "asset_binding",
        "asset_inventory",
        "asset_assignments",
        "mapping_confidence",
        "edit_scope",
        "edit_deltas",
        "extend_context",
        "grouping_review",
    ):
        if key in operation:
            result[key] = copy.deepcopy(operation.get(key))
    dependency = _clean_text(operation.get("depends_on_operation_id"))
    task = operation.get("task")
    if (
        dependency
        and isinstance(task, dict)
        and _clean_text(task.get("primary")).lower() == "extend"
        and "generation" not in operation
    ):
        dependency_tag = f"@{dependency}-output"
        shot_ids = [
            str(shot.get("source_shot_id"))
            for shot in normalized.get("shots", [])
        ]
        inventory = result.get("asset_inventory")
        inventory = copy.deepcopy(inventory) if isinstance(inventory, dict) else {
            "complete": False,
            "items": [],
        }
        inventory_items = inventory.get("items", [])
        inventory_items = list(inventory_items) if isinstance(inventory_items, list) else []
        inventory_items.append(
            {
                "tag": dependency_tag,
                "media_type": "video",
                "available": True,
                "core": True,
            }
        )
        inventory["items"] = inventory_items
        assignments = result.get("asset_assignments")
        assignments = list(assignments) if isinstance(assignments, list) else []
        assignments.append(
            {
                "tag": dependency_tag,
                "target_entity": "前一步输出视频",
                "role": "extension_source",
                "adopted_dimensions": ["边界画面", "运动趋势", "声音状态"],
                "rejected_dimensions": [],
                "applies_to_shot_ids": shot_ids,
                "user_mapped": True,
            }
        )
        result["asset_inventory"] = inventory
        result["asset_assignments"] = assignments
        extend_context = result.get("extend_context")
        extend_context = (
            copy.deepcopy(extend_context)
            if isinstance(extend_context, dict)
            else {}
        )
        extend_context.setdefault("accepted_material", True)
        extend_context.setdefault(
            "observed_end_state", f"{dependency} 输出的结束状态"
        )
        extend_context.setdefault("direction", "后")
        result["extend_context"] = extend_context
    return result


def build_prompt_plan(
    source_document: Any,
    decisions: Any = None,
    model_profile: Any = None,
    delivery_slug: str | None = None,
) -> dict[str, Any]:
    """Build a v2 plan, including deterministic sequential operations."""
    raw_operations = _runtime_value(source_document, decisions, "operations")
    if raw_operations in (None, []):
        return _build_single_operation_plan(
            source_document,
            decisions=decisions,
            model_profile=model_profile,
            delivery_slug=delivery_slug,
        )
    if not isinstance(raw_operations, list) or not raw_operations:
        plan = _build_single_operation_plan(
            source_document,
            decisions=decisions,
            model_profile=model_profile,
            delivery_slug=delivery_slug,
        )
        issue = _issue(
            "OPERATION_CONTRACT_INVALID",
            "ERROR",
            "operation",
            "operations",
            "operations 必须是非空数组。",
            ("prompt_compilation",),
        )
        plan["diagnostics"] = _deduplicate_issues(
            list(plan.get("diagnostics", [])) + [issue]
        )
        normalized, _ = normalize_input(source_document)
        plan["validation"] = _validation_object(
            normalized, plan.get("prompt_units", []), plan["diagnostics"]
        )
        plan["submission_ready"] = False
        plan["content_hash"] = prompt_plan_content_hash(plan)
        return plan

    normalized, _ = normalize_input(source_document)
    profile = (
        copy.deepcopy(model_profile)
        if model_profile is not None
        else resolve_model_profile()
    )
    operation_plans: list[tuple[dict[str, Any], dict[str, Any]]] = []
    operation_issues: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_operation in enumerate(raw_operations):
        path = f"operations[{index}]"
        if not isinstance(raw_operation, dict):
            operation_issues.append(
                _issue(
                    "OPERATION_CONTRACT_INVALID",
                    "ERROR",
                    "operation",
                    path,
                    "operation 必须是 JSON 对象。",
                    ("prompt_compilation",),
                )
            )
            continue
        operation_id = _clean_text(raw_operation.get("operation_id")) or f"OP{index + 1:03d}"
        dependency = _clean_text(raw_operation.get("depends_on_operation_id")) or None
        if (
            operation_id in seen_ids
            or raw_operation.get("order", index + 1) != index + 1
            or (dependency is not None and dependency not in seen_ids)
        ):
            operation_issues.append(
                _issue(
                    "OPERATION_CONTRACT_INVALID",
                    "ERROR",
                    "operation",
                    path,
                    "operation ID、order 或依赖顺序无效。",
                    ("prompt_compilation",),
                )
            )
            continue
        normalized_operation = copy.deepcopy(raw_operation)
        normalized_operation["operation_id"] = operation_id
        normalized_operation["order"] = index + 1
        normalized_operation["depends_on_operation_id"] = dependency
        if (
            len(normalized.get("shots", [])) > 1
            and "grouping_review" not in normalized_operation
        ):
            raise GroupingReviewError(
                "GROUPING_REVIEW_REQUIRED: 显式 operations 中每个 operation "
                f"都必须提供 grouping_review；缺失 {operation_id}。"
            )
        op_decisions = _operation_decisions(
            decisions, normalized_operation, normalized
        )
        op_plan = _build_single_operation_plan(
            source_document,
            decisions=op_decisions,
            model_profile=profile,
            delivery_slug=delivery_slug,
        )
        operation_plans.append((normalized_operation, op_plan))
        seen_ids.add(operation_id)

    if not operation_plans:
        fallback = _build_single_operation_plan(
            source_document,
            decisions=decisions,
            model_profile=profile,
            delivery_slug=delivery_slug,
        )
        fallback["diagnostics"] = _deduplicate_issues(
            list(fallback.get("diagnostics", [])) + operation_issues
        )
        fallback["validation"] = _validation_object(
            normalized,
            fallback.get("prompt_units", []),
            fallback["diagnostics"],
        )
        fallback["submission_ready"] = False
        fallback["content_hash"] = prompt_plan_content_hash(fallback)
        return fallback

    combined = copy.deepcopy(operation_plans[0][1])
    combined_units: list[dict[str, Any]] = []
    combined_operations: list[dict[str, Any]] = []
    combined_issues: list[dict[str, Any]] = list(operation_issues)
    combined_advisories: list[dict[str, Any]] = []
    combined_ready = True
    for raw_operation, op_plan in operation_plans:
        operation_id = raw_operation["operation_id"]
        prompt_unit_ids: list[str] = []
        for unit in op_plan.get("prompt_units", []):
            copied_unit = copy.deepcopy(unit)
            copied_unit["prompt_unit_id"] = f"PU{len(combined_units) + 1:03d}"
            copied_unit["operation_id"] = operation_id
            copied_unit["operation_order"] = raw_operation["order"]
            copied_unit["depends_on_operation_id"] = raw_operation[
                "depends_on_operation_id"
            ]
            copied_unit["task_primary"] = op_plan.get("task", {}).get("primary")
            combined_units.append(copied_unit)
            prompt_unit_ids.append(copied_unit["prompt_unit_id"])
        combined_operations.append(
            {
                "operation_id": operation_id,
                "order": raw_operation["order"],
                "depends_on_operation_id": raw_operation[
                    "depends_on_operation_id"
                ],
                "task": copy.deepcopy(op_plan.get("task", {})),
                "generation": copy.deepcopy(op_plan.get("generation", {})),
                "prompt_unit_ids": prompt_unit_ids,
                "submission_ready": bool(op_plan.get("submission_ready")),
            }
        )
        combined_issues.extend(op_plan.get("diagnostics", []))
        combined_advisories.extend(op_plan.get("prompt_advisories", []))
        combined_ready &= bool(op_plan.get("submission_ready"))

    combined["compiler_inputs"] = _compiler_inputs(
        normalized, decisions, profile
    )
    combined["operations"] = combined_operations
    combined["prompt_units"] = combined_units
    combined["prompt_advisories"] = _deduplicate_dicts(combined_advisories)
    combined["submission_ready"] = combined_ready
    combined["diagnostics"] = _deduplicate_issues(combined_issues)
    combined["validation"] = _validation_object(
        normalized, combined_units, combined["diagnostics"]
    )
    combined["content_hash"] = prompt_plan_content_hash(combined)
    return combined
