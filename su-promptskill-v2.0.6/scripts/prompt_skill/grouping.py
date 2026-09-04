"""su-promptskill internal module: emotion decisions and global grouping."""

from __future__ import annotations

from . import assets as _previous

globals().update({
    key: value
    for key, value in vars(_previous).items()
    if not key.startswith("__")
})

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Responsibility module behind scripts/prompt_delivery.py."

def resolve_generation_context(
    source_document: Any,
    decisions: Any,
    shots: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw_generation, mode_source = _generation_source(source_document, decisions)
    runtime_hash = sha256_json(decisions) if decisions is not None else None
    return _validate_generation_context(
        raw_generation,
        source_document,
        shots,
        profile,
        mode_source=mode_source,
        runtime_decisions_hash=runtime_hash,
    )


def _shot_id_positions(
    shots: Sequence[Mapping[str, Any]],
) -> dict[str, list[int]]:
    positions: dict[str, list[int]] = {}
    for index, shot in enumerate(shots):
        positions.setdefault(str(shot["source_shot_id"]), []).append(index)
    return positions


def _grouping_policy(profile: Mapping[str, Any]) -> dict[str, Decimal | int]:
    profile_id = _clean_text(profile.get("profile_id"))
    return copy.deepcopy(
        GROUPING_POLICIES.get(profile_id, DEFAULT_GROUPING_POLICY)
    )


def _validate_emotion_decisions(
    shots: Sequence[Mapping[str, Any]], decisions: Any
) -> tuple[dict[str, list[dict[str, str]]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    accepted: dict[str, list[dict[str, str]]] = {}
    raw_map = (
        decisions.get("emotion_visualizations", {})
        if isinstance(decisions, dict)
        else {}
    )
    if raw_map in (None, {}):
        return accepted, issues
    if not isinstance(raw_map, dict):
        issues.append(
            _issue(
                "EMOTION_VISUALIZATION_INVALID",
                "ERROR",
                "decision",
                "emotion_visualizations",
                "emotion_visualizations 必须是按 source_shot_id 索引的对象。",
                ("emotion_visualization",),
            )
        )
        return accepted, issues

    positions = _shot_id_positions(shots)
    for shot_id, raw_decision in raw_map.items():
        path = f"emotion_visualizations.{shot_id}"
        shot_positions = positions.get(str(shot_id), [])
        if len(shot_positions) != 1:
            issues.append(
                _issue(
                    "EMOTION_VISUALIZATION_INVALID",
                    "ERROR",
                    "decision",
                    path,
                    "情绪派生必须引用一个唯一存在的 source_shot_id。",
                    ("emotion_visualization",),
                )
            )
            continue
        shot = shots[shot_positions[0]]
        if shot.get("visible_behavior"):
            issues.append(
                _issue(
                    "EMOTION_VISUALIZATION_FORBIDDEN",
                    "ERROR",
                    "decision",
                    path,
                    "来源已有 visible_behavior，不允许叠加派生表演。",
                    ("emotion_visualization",),
                )
            )
            continue
        emotion_intent = _clean_text(shot.get("emotion_intent"))
        if not emotion_intent:
            issues.append(
                _issue(
                    "EMOTION_VISUALIZATION_WITHOUT_BASIS",
                    "ERROR",
                    "decision",
                    path,
                    "来源没有明确 emotion_intent，不允许创建情绪。",
                    ("emotion_visualization",),
                )
            )
            continue
        if not isinstance(raw_decision, dict):
            issues.append(
                _issue(
                    "EMOTION_VISUALIZATION_INVALID",
                    "ERROR",
                    "decision",
                    path,
                    "情绪派生必须是包含 basis、text 和 guardrails 的对象。",
                    ("emotion_visualization",),
                )
            )
            continue
        basis = _clean_text(raw_decision.get("basis_emotion"))
        text = _clean_text(raw_decision.get("text"))
        guardrails = raw_decision.get("guardrails")
        guardrails_valid = isinstance(guardrails, dict) and all(
            guardrails.get(key) is False for key in EMOTION_GUARDRAIL_KEYS
        )
        if basis != emotion_intent or not text or not guardrails_valid:
            issues.append(
                _issue(
                    "EMOTION_VISUALIZATION_INVALID",
                    "ERROR",
                    "decision",
                    path,
                    "basis 必须逐字匹配来源情绪，text 非空，且五项 guardrail 显式为 false。",
                    ("emotion_visualization",),
                )
            )
            continue
        downstream_terms = _anti_slop_terms_in_value(text)
        if downstream_terms:
            issues.append(
                _issue(
                    "DOWNSTREAM_ANTI_SLOP",
                    "ERROR",
                    "decision",
                    path,
                    (
                        "下游 emotion visualization 含空泛强化词："
                        f"{', '.join(downstream_terms)}；未改写且不进入正文。"
                    ),
                    ("emotion_visualization",),
                )
            )
            continue
        accepted[str(shot_id)] = [
            {
                "provenance": "derived_emotion_visualization",
                "basis_emotion": basis,
                "text": text,
            }
        ]
    return accepted, issues


def _plan_groups(
    shots: Sequence[Mapping[str, Any]],
    decisions: Any,
    profile: Mapping[str, Any],
    source_observed_hash: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not shots:
        return [], []
    if isinstance(decisions, dict) and "groups" in decisions:
        raise GroupingReviewError(
            "GROUPING_REVIEW_LEGACY_UNSUPPORTED: decisions.groups "
            "不属于 prompt-plan/2.0.6；请提供 grouping_review。"
        )
    review = (
        decisions.get("grouping_review")
        if isinstance(decisions, dict)
        else None
    )
    if len(shots) == 1 and review is None:
        shot = shots[0]
        return [
            {
                "shots": [shot],
                "grouping_reason": None,
                "semantic_compatibility": None,
                "standalone_reason": "single_source_shot",
                "partition_strategy": GROUPING_PARTITION_POLICY,
                "partition_entry_reason": "scope_start",
                "boundary_evidence": [],
            }
        ], []
    if not isinstance(review, dict):
        raise GroupingReviewError(
            "GROUPING_REVIEW_REQUIRED: 多镜输入必须提供完整 grouping_review。"
        )
    if _clean_text(review.get("source_observed_hash")) != _clean_text(
        source_observed_hash
    ):
        raise GroupingReviewError(
            "GROUPING_REVIEW_SOURCE_MISMATCH: source_observed_hash "
            "未匹配当前锁定来源。"
        )
    if _clean_text(review.get("contract")) != GROUPING_REVIEW_CONTRACT:
        raise GroupingReviewError(
            "GROUPING_REVIEW_CONTRACT_INVALID: grouping_review.contract "
            f"必须是 {GROUPING_REVIEW_CONTRACT}。"
        )
    if _clean_text(review.get("partition_policy")) != GROUPING_PARTITION_POLICY:
        raise GroupingReviewError(
            "GROUPING_PARTITION_POLICY_INVALID: partition_policy 必须是 "
            f"{GROUPING_PARTITION_POLICY}。"
        )
    boundaries = review.get("boundaries")
    if not isinstance(boundaries, list) or len(boundaries) != len(shots) - 1:
        raise GroupingReviewError(
            "GROUPING_REVIEW_INCOMPLETE: boundaries 必须按顺序恰好覆盖 "
            f"{len(shots) - 1} 个相邻边界。"
        )

    grouping_policy = _grouping_policy(profile)
    max_cuts = int(grouping_policy["max_cuts"])
    max_group_duration = Decimal(grouping_policy["max_duration_seconds"])
    capabilities = profile.get("capabilities", {})
    if capabilities.get("supports_multi_cut") is not True:
        max_cuts = 1
    model_limit = _duration_decimal(
        capabilities.get("max_clip_duration_seconds")
    )
    if model_limit is not None:
        max_group_duration = min(max_group_duration, model_limit)

    def duration_of(shot: Mapping[str, Any]) -> Decimal | None:
        try:
            return _duration_decimal(shot.get("duration_seconds"))
        except InvalidOperation:
            return None

    def context_value(shot: Mapping[str, Any], *keys: str) -> str:
        for key in keys:
            value = _clean_text(shot.get(key))
            if value:
                return value
        context = shot.get("scene_context", {})
        if isinstance(context, dict):
            for key in keys:
                value = _clean_text(context.get(key))
                if value:
                    return value
        continuity = shot.get("continuity", {})
        if isinstance(continuity, dict):
            for key in keys:
                value = _clean_text(continuity.get(key))
                if value:
                    return value
        return ""

    def observed_evidence(
        left: Mapping[str, Any], right: Mapping[str, Any]
    ) -> tuple[set[str], set[str]]:
        positive: set[str] = set()
        hard: set[str] = set()
        pairs = (
            (("scene_id", "scene", "location"), "same_scene", "scene_change"),
            (("reality_layer",), "same_reality_layer", "reality_layer_change"),
            (("time", "time_of_day"), "same_time", "time_change"),
        )
        for keys, same_code, change_code in pairs:
            left_value = context_value(left, *keys)
            right_value = context_value(right, *keys)
            if left_value and right_value:
                if left_value == right_value:
                    positive.add(same_code)
                else:
                    hard.add(change_code)
        if (
            left.get("compilable_source") is not True
            or right.get("compilable_source") is not True
        ):
            hard.add("source_unavailable")
        left_design = left.get("cut_design", {})
        right_design = right.get("cut_design", {})
        left_exit = _clean_text(
            left_design.get("exit_trigger")
            if isinstance(left_design, dict)
            else ""
        )
        right_entry = _clean_text(
            right_design.get("entry_trigger")
            if isinstance(right_design, dict)
            else ""
        )
        if left_exit and right_entry and SequenceMatcher(
            None, left_exit, right_entry
        ).ratio() >= 0.5:
            positive.add("boundary_state_match")
        return positive, hard

    boundary_records: list[dict[str, Any]] = []

    for index, boundary in enumerate(boundaries):
        path = f"grouping_review.boundaries[{index}]"
        left = shots[index]
        right = shots[index + 1]
        left_id = str(left["source_shot_id"])
        right_id = str(right["source_shot_id"])
        if not isinstance(boundary, dict):
            raise GroupingReviewError(
                f"GROUPING_REVIEW_INVALID: {path} 必须是 JSON 对象。"
            )
        if (
            _clean_text(boundary.get("left_source_shot_id")) != left_id
            or _clean_text(boundary.get("right_source_shot_id")) != right_id
        ):
            raise GroupingReviewError(
                f"GROUPING_REVIEW_ORDER_INVALID: {path} 未匹配相邻镜头 "
                f"{left_id} → {right_id}。"
            )
        if "decision" in boundary or "constraint_reason" in boundary:
            raise GroupingReviewError(
                f"GROUPING_REVIEW_LEGACY_BOUNDARY: {path} 必须分离语义分类与最终分区，"
                "不得再提交 decision 或 constraint_reason。"
            )
        reason = _clean_text(boundary.get("reason"))
        if not reason:
            raise GroupingReviewError(
                f"GROUPING_REVIEW_INVALID: {path}.reason 必须非空。"
            )
        compatibility = boundary.get("compatibility")
        if not isinstance(compatibility, dict) or set(compatibility) != set(
            COMPATIBILITY_KEYS
        ) or any(
            not isinstance(compatibility.get(key), bool)
            for key in COMPATIBILITY_KEYS
        ):
            raise GroupingReviewError(
                f"GROUPING_REVIEW_INVALID: {path}.compatibility 必须完整声明 "
                "十个布尔维度。"
            )
        boundary_class = _clean_text(boundary.get("classification"))
        if boundary_class not in GROUPING_BOUNDARY_CLASSES:
            raise GroupingReviewError(
                f"GROUPING_REVIEW_INVALID: {path}.classification 不受支持。"
            )
        evidence = boundary.get("semantic_evidence")
        allowed_evidence = (
            GROUPING_HARD_EVIDENCE
            | GROUPING_JOIN_EVIDENCE
            | GROUPING_SPLIT_EVIDENCE
        )
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(_clean_text(item) not in allowed_evidence for item in evidence)
            or len({_clean_text(item) for item in evidence}) != len(evidence)
        ):
            raise GroupingReviewError(
                f"GROUPING_REVIEW_INVALID: {path}.semantic_evidence 必须是非空、"
                "无重复的受控证据数组。"
            )
        evidence_codes = {_clean_text(item) for item in evidence}
        observed_positive, observed_hard = observed_evidence(left, right)
        observable_codes = {
            "same_scene",
            "scene_change",
            "same_reality_layer",
            "reality_layer_change",
            "same_time",
            "time_change",
            "boundary_state_match",
            "source_unavailable",
        }
        false_observable = (evidence_codes & observable_codes) - (
            observed_positive | observed_hard
        )
        if false_observable:
            raise GroupingReviewError(
                f"GROUPING_REVIEW_EVIDENCE_CONFLICT: {path} 的来源可观察证据不成立："
                f"{', '.join(sorted(false_observable))}。"
            )
        if observed_hard and boundary_class != "hard_split":
            raise GroupingReviewError(
                f"GROUPING_REVIEW_HARD_SPLIT_REQUIRED: {path} 检测到 "
                f"{', '.join(sorted(observed_hard))}。"
            )
        if observed_hard - evidence_codes:
            raise GroupingReviewError(
                f"GROUPING_REVIEW_EVIDENCE_INCOMPLETE: {path} 未声明来源可验证的硬拆证据。"
            )
        all_compatible = all(
            compatibility.get(key) is True for key in COMPATIBILITY_KEYS
        )
        if boundary_class == "hard_split":
            if not observed_hard:
                raise GroupingReviewError(
                    f"GROUPING_REVIEW_HARD_SPLIT_INVALID: {path} 没有来源可验证的硬拆证据。"
                )
        elif boundary_class == "prefer_join":
            if not all_compatible:
                raise GroupingReviewError(
                    f"GROUPING_REVIEW_PREFER_JOIN_INVALID: {path} 的 prefer_join "
                    "要求十项语义兼容。"
                )
            if not evidence_codes & GROUPING_JOIN_EVIDENCE:
                raise GroupingReviewError(
                    f"GROUPING_REVIEW_PREFER_JOIN_INVALID: {path} 缺少正向承接证据。"
                )
        else:
            if all_compatible and not evidence_codes & GROUPING_SPLIT_EVIDENCE:
                raise GroupingReviewError(
                    f"GROUPING_REVIEW_PREFER_SPLIT_INVALID: {path} 的全兼容边界"
                    "必须说明表演、摄影机、叙事阶段或信息密度理由。"
                )
        boundary_records.append(
            {
                "left_source_shot_id": left_id,
                "right_source_shot_id": right_id,
                "classification": boundary_class,
                "semantic_evidence": sorted(evidence_codes),
                "compatibility": copy.deepcopy(compatibility),
                "reason": reason,
            }
        )

    # Optimize the whole ordered scope. Capacity is evaluated on candidate units,
    # not encoded by falsifying semantic compatibility at a local boundary.
    count = len(shots)
    best: list[tuple[int, int, int, list[tuple[int, int]]] | None] = [None] * (count + 1)
    best[count] = (0, 0, 0, [])
    for start in range(count - 1, -1, -1):
        duration_total = Decimal("0")
        known_duration = True
        for end in range(start, min(count, start + max_cuts)):
            duration = duration_of(shots[end])
            if duration is None:
                known_duration = False
            else:
                duration_total += duration
            if end > start:
                prior_boundary = boundary_records[end - 1]
                prior_compatible = all(
                    prior_boundary["compatibility"].get(key) is True
                    for key in COMPATIBILITY_KEYS
                )
                if (
                    prior_boundary["classification"] == "hard_split"
                    or not prior_compatible
                ):
                    break
            if end > start and (not known_duration or duration_total > max_group_duration):
                break
            if end == start or (known_duration and duration_total <= max_group_duration):
                tail = best[end + 1]
                if tail is None:
                    continue
                score = tail[0]
                for boundary_index in range(start, end):
                    score += (
                        10
                        if boundary_records[boundary_index]["classification"] == "prefer_join"
                        else -6
                    )
                if end < count - 1:
                    split_class = boundary_records[end]["classification"]
                    score += 6 if split_class == "prefer_split" else (
                        -10 if split_class == "prefer_join" else 0
                    )
                candidate = (
                    score,
                    -(1 + -tail[1]),
                    -((1 if end == start else 0) + -tail[2]),
                    [(start, end)] + tail[3],
                )
                current = best[start]
                # Stable tie-break: after score and unit count, prefer the
                # longest earliest unit. This avoids avoidable leading singletons.
                if current is None or candidate > current:
                    best[start] = candidate
    if best[0] is None:
        raise GroupingReviewError(
            "GROUPING_PARTITION_UNAVAILABLE: 来源时长或 Profile 上限无法形成完整分区。"
        )

    planned: list[dict[str, Any]] = []
    selected_ranges = best[0][3]
    for range_index, (start, end) in enumerate(selected_ranges):
        selected = list(shots[start : end + 1])
        joined_boundaries = copy.deepcopy(boundary_records[start:end])
        is_multi = len(selected) > 1
        if is_multi:
            grouping_reason = "；".join(
                f"{item['left_source_shot_id']}→{item['right_source_shot_id']}"
                f"[{item['classification']}]：{item['reason']}"
                for item in joined_boundaries
            )
        else:
            grouping_reason = None
        entry_reason = "scope_start"
        if range_index > 0:
            previous_start, previous_end = selected_ranges[range_index - 1]
            split_boundary = boundary_records[start - 1]
            if split_boundary["classification"] == "hard_split":
                entry_reason = "hard_split"
            elif split_boundary["classification"] == "prefer_split":
                entry_reason = "semantic_preference"
            else:
                previous_durations = [
                    duration_of(item)
                    for item in shots[previous_start : previous_end + 1]
                ]
                next_durations = [
                    duration_of(item) for item in shots[start : end + 1]
                ]
                if (
                    all(item is not None for item in previous_durations)
                    and all(item is not None for item in next_durations)
                    and sum(previous_durations, Decimal("0"))
                    + sum(next_durations, Decimal("0"))
                    > max_group_duration
                ):
                    entry_reason = "profile_duration_limit"
                elif previous_end - previous_start + 2 > max_cuts:
                    entry_reason = "profile_cut_limit"
                else:
                    entry_reason = "global_quality_tradeoff"
        planned.append(
            {
                "shots": selected,
                "grouping_reason": grouping_reason,
                "semantic_compatibility": (
                    {key: True for key in COMPATIBILITY_KEYS} if is_multi else None
                ),
                "standalone_reason": None if is_multi else "global_partition_split",
                "partition_strategy": GROUPING_PARTITION_POLICY,
                "partition_entry_reason": entry_reason,
                "boundary_evidence": joined_boundaries,
            }
        )
    return planned, []
