#!/usr/bin/env python3
"""Generate complex Chinese script end-to-end fixtures for shot-data/2.5.3."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import contract_schema
import storyboard_delivery as delivery
import test_storyboard_delivery as test_helpers


def span(fragment: str, text: str) -> dict:
    start = text.index(fragment)
    s = {"start": start, "end": start + len(fragment)}
    delivery.populate_span_hashes([s], text)
    return s


def continuous_spans(fragments: list[str], text: str) -> list[dict]:
    starts = [text.index(f) for f in fragments]
    ends = [s + len(f) for s, f in zip(starts, fragments)]
    s = {"start": min(starts), "end": max(ends)}
    delivery.populate_span_hashes([s], text)
    return [s]


def build_execution_text(shot: dict, facts: list[dict], environment: str) -> str:
    camera = shot["camera"]
    fact_lines = []
    for f in facts:
        if f.get("type") == "dialogue":
            fact_lines.append(f'{f["speaker"]}说：“{f["text"]}”')
        else:
            fact_lines.append(f["text"])
    behavior = shot.get("performance", {}).get("emotion_intent", "")
    parts = [
        f"【画面内容】{environment}；",
        f"摄影机位于{camera['position']}，{camera['logic']}；",
        f"画面中{camera['composition']}。",
    ]
    parts.append("。".join(fact_lines) + "。")
    if behavior:
        parts.append(f"{behavior}。")
    parts.append(f"动作完成后，{'；'.join(shot.get('end_state', []))}。")
    return "".join(parts)


def build_coverage_evidence(shot: dict, facts: list[dict]) -> list[dict]:
    evidence = []
    for f in facts:
        fact_id = f["fact_id"]
        text = f["text"]
        fact_type = f.get("type")
        if fact_type == "dialogue":
            idx = next(
                (
                    i
                    for i, d in enumerate(shot.get("dialogue", []))
                    if d.get("fact_id") == fact_id
                ),
                0,
            )
            evidence.append(
                {
                    "fact_id": fact_id,
                    "target_path": f"dialogue[{idx}].text",
                    "evidence_quote": text,
                }
            )
        elif fact_type == "action":
            idx = next(
                (
                    i
                    for i, b in enumerate(shot.get("blocking", []))
                    if b.get("action") == text
                ),
                0,
            )
            evidence.append(
                {
                    "fact_id": fact_id,
                    "target_path": f"blocking[{idx}].action",
                    "evidence_quote": text,
                }
            )
        elif fact_type == "position":
            camera = shot["camera"]
            if text in camera.get("composition", ""):
                target = "camera.composition"
            elif text in camera.get("start_frame", ""):
                target = "camera.start_frame"
            else:
                target = "camera.end_frame"
            evidence.append(
                {
                    "fact_id": fact_id,
                    "target_path": target,
                    "evidence_quote": text,
                }
            )
        else:
            evidence.append(
                {
                    "fact_id": fact_id,
                    "target_path": "blocking[0].action",
                    "evidence_quote": text,
                }
            )
    return evidence


def patch_camera_fields(draft: dict, camera_configs: list[dict]) -> None:
    configs_by_shot = {cfg["shot_id"]: cfg for cfg in camera_configs}
    for shot in draft.get("shots", []):
        cfg = configs_by_shot.get(shot["shot_id"], {})
        camera = shot["camera"]
        for key in (
            "shot_size",
            "angle",
            "position",
            "composition",
            "movement",
            "start_frame",
            "end_frame",
        ):
            if key in cfg:
                camera[key] = cfg[key]
        if "logic" in cfg:
            camera["logic"] = cfg["logic"]
        if "motivation" in cfg:
            camera["motivation"] = cfg["motivation"]


def set_reframe_spatial_strategy(draft: dict) -> None:
    shots_by_unit = {shot["plan_unit_id"]: shot for shot in draft["shots"]}
    for unit in draft["shot_plan"]["planned_units"]:
        if len(unit.get("screen_event_ids", [])) <= 1:
            continue
        strategy = {
            "type": "sequential_reframe",
            "description": "在同一镜头内跟随动作与对白完成观看尺度递进。",
        }
        unit["visual_plan"]["spatial_strategy"] = copy.deepcopy(strategy)
        shot = shots_by_unit.get(unit["plan_unit_id"])
        if shot:
            shot["camera"]["spatial_strategy"] = copy.deepcopy(strategy)


def sync_visual_plan(draft: dict) -> None:
    units_by_id = {u["plan_unit_id"]: u for u in draft["shot_plan"]["planned_units"]}
    for shot in draft.get("shots", []):
        unit = units_by_id.get(shot.get("plan_unit_id"))
        if unit is None:
            continue
        camera = shot["camera"]
        plan = unit.setdefault("visual_plan", {})
        movement = camera.get("movement", "固定")
        movement_class = delivery.camera_movement_class(movement)
        primary = list(camera.get("primary_subjects", ["客观观察"]))
        viewpoint = camera.get("viewpoint_owner") or (
            primary[0] if primary else "客观观察"
        )
        style_anchor_ids = plan.get("style_anchor_ids")
        plan.update(
            {
                "viewpoint_owner": viewpoint,
                "primary_subjects": primary,
                "secondary_subjects": list(camera.get("secondary_subjects", [])),
                "shot_size": camera.get("shot_size", "中景"),
                "angle": camera.get("angle", "平视"),
                "camera_position": camera.get("position", ""),
                "framing_relation": camera.get("composition", ""),
                "perspective_intent": camera.get(
                    "perspective_intent", "natural_relation"
                ),
                "focus_plan": camera.get("focus_plan", "焦点保持在当前主要观看主体上。"),
                "spatial_strategy": copy.deepcopy(
                    camera.get(
                        "spatial_strategy", {"type": "not_applicable", "description": ""}
                    )
                ),
                "movement_plan": {
                    "class": movement_class,
                    "trigger": ""
                    if movement_class == "fixed"
                    else "主体动作或观看关系开始变化。",
                    "speed": "" if movement_class == "fixed" else "缓慢",
                    "path": "" if movement_class == "fixed" else movement,
                    "end_condition": ""
                    if movement_class == "fixed"
                    else camera.get("end_frame", ""),
                    "hold_reason": "保护完整表演与空间关系。"
                    if movement_class == "fixed"
                    else "",
                },
                "start_frame": camera.get("start_frame", ""),
                "end_frame": camera.get("end_frame", ""),
                "motivation": camera.get(
                    "motivation", "让当前主体在既定观察位置中清楚可读。"
                ),
            }
        )
        if style_anchor_ids is not None:
            plan["style_anchor_ids"] = list(style_anchor_ids)
        # Keep the final camera's movement_plan in lock-step as well.
        shot["camera"]["movement_plan"] = copy.deepcopy(plan["movement_plan"])


def add_visual_uniformity_reviews(draft: dict) -> None:
    """Add scene-level visual uniformity reviews for dominant patterns."""
    reviews: list[dict] = []
    for finding in delivery.visual_uniformity_findings(draft):
        scene = next(
            (
                s
                for s in draft.get("scenes", [])
                if s.get("scene_id") == finding.get("scene_id")
            ),
            None,
        )
        anchor_ids = (
            [
                a["style_anchor_id"]
                for a in scene.get("directing_plan", {}).get("style_anchors", [])
                if isinstance(a, dict) and a.get("style_anchor_id")
            ]
            if scene
            else []
        )
        reviews.append(
            {
                "review_id": f"VR{len(reviews) + 1:03d}",
                "scope": finding["scope"],
                "scene_id": finding["scene_id"],
                "dimension": finding["dimension"],
                "dominant_value": finding["dominant_value"],
                "reason": (
                    f"本{'场景' if finding['scope'] == 'scene' else '项目'}以"
                    f"{finding['dimension']}={finding['dominant_value']}作为统一观看策略。"
                ),
                "style_anchor_ids": anchor_ids,
            }
        )
    draft["shot_plan"]["visual_uniformity_reviews"] = reviews


def make_draft(
    *,
    project_id: str,
    delivery_slug: str,
    locked_text: str,
    source_boundary: str,
    narrative_function: str,
    dramatic_progression: str,
    character_relations: list[str],
    source_constraints: list[str],
    director_profile: dict,
    style_options: list[dict],
    scene: dict,
    beat_groups: list[list[dict]],
    camera_configs: list[dict],
) -> dict:
    """Assemble a full draft and normalize it through the v2.5.3 pipeline."""
    draft = contract_schema.draft_scaffold(
        project_id=project_id,
        delivery_slug=delivery_slug,
        locked_text=locked_text,
        input_kind="continuous_text",
        boundary_lock="entire_submitted_text",
        scope=f"{delivery_slug} 端到端 fixture",
    )
    draft["source_analysis"] = {
        "source_boundary": source_boundary,
        "narrative_function": narrative_function,
        "dramatic_progression": dramatic_progression,
        "character_relations": character_relations,
        "source_constraints": source_constraints,
    }
    draft["director_profile"] = director_profile
    draft["director_style_options"] = style_options
    draft["selected_style_option_id"] = style_options[0]["option_id"]
    draft["scenes"] = [scene]

    beats = []
    for idx, group in enumerate(beat_groups, 1):
        fragments = [
            locked_text[f["source_spans"][0]["start"] : f["source_spans"][0]["end"]]
            for f in group
        ]
        beats.append(
            {
                "beat_id": f"B{idx:03d}",
                "beat_order": idx,
                "scene_id": scene["scene_id"],
                "source_spans": continuous_spans(fragments, locked_text),
                "dramatic_change": f"节拍{idx}：推动戏剧动作。",
                "facts": group,
            }
        )
    draft["beats"] = beats

    units = []
    for idx, beat in enumerate(beats, 1):
        units.append(
            {
                "plan_unit_id": f"PU{idx:03d}",
                "plan_order": idx,
                "scene_id": scene["scene_id"],
                "beat_ids": [beat["beat_id"]],
                "source_spans": [copy.deepcopy(beat["source_spans"][0])],
                "estimated_duration_seconds": camera_configs[idx - 1].get(
                    "duration_seconds", 3
                ),
                "narrative_purpose": f"呈现{beat['beat_id']}的戏剧动作。",
            }
        )
    draft["shot_plan"]["planned_units"] = units

    shots = []
    shot_facts: dict[str, list[dict]] = {}
    for idx, (unit, cfg) in enumerate(zip(units, camera_configs), 1):
        beat = beats[idx - 1]
        facts = beat["facts"]
        shot_facts[cfg["shot_id"]] = facts
        dialogue_facts = [f for f in facts if f["type"] == "dialogue"]
        action_facts = [f for f in facts if f["type"] == "action"]
        primary_fact = (
            dialogue_facts[0]
            if dialogue_facts
            else action_facts[0]
            if action_facts
            else facts[0]
        )
        addressee = cfg["addressee"]
        visible_characters = cfg.get("visible_characters", [])
        dialogue = [
            {
                "fact_id": f["fact_id"],
                "speaker": f["speaker"],
                "text": f["text"],
                "delivery": "onscreen",
                "timing": "TB01",
                "addressee": addressee,
            }
            for f in dialogue_facts
        ]
        blocking_actions = cfg.get("blocking_actions", {})
        if not blocking_actions:
            for name in dict.fromkeys(primary_fact.get("performers", [])):
                blocking_actions[name] = "参与当前节拍动作"
        blocking = []
        for name, action in blocking_actions.items():
            blocking.append(
                {
                    "character": name,
                    "start_position": cfg.get("start_position", "原位"),
                    "action": action,
                    "end_position": cfg.get("end_position", "原位"),
                    "facing": cfg.get("facing", addressee),
                    "eyeline": addressee,
                }
            )
        shots.append(
            {
                "shot_id": cfg["shot_id"],
                "shot_order": idx,
                "plan_unit_id": unit["plan_unit_id"],
                "scene_id": scene["scene_id"],
                "beat_ids": [beat["beat_id"]],
                "source_spans": [copy.deepcopy(unit["source_spans"][0])],
                "covered_fact_ids": [f["fact_id"] for f in facts],
                "coverage_evidence": [],
                "primary_fact_id": primary_fact["fact_id"],
                "duration_seconds": unit["estimated_duration_seconds"],
                "duration_blocks": [
                    {
                        "block_id": "TB01",
                        "label": "动作与对白并行",
                        "action_seconds": unit["estimated_duration_seconds"],
                        "dialogue_seconds": unit["estimated_duration_seconds"],
                        "performance_seconds": unit["estimated_duration_seconds"],
                        "camera_seconds": unit["estimated_duration_seconds"],
                    }
                ],
                "cut_design": {
                    "entry_trigger": f"进入{beat['beat_id']}。",
                    "exit_trigger": f"离开{beat['beat_id']}。",
                    "isolation_intent": "none",
                },
                "camera": {
                    "shot_size": cfg["shot_size"],
                    "angle": cfg["angle"],
                    "position": cfg["position"],
                    "composition": cfg["composition"],
                    "movement": cfg["movement"],
                    "logic": cfg["logic"],
                    "start_frame": cfg["start_frame"],
                    "end_frame": cfg["end_frame"],
                },
                "blocking": blocking,
                "performance": {
                    "emotion_arc_id": None,
                    "phase": "steady",
                    "emotion_intent": cfg["visible_behavior"],
                    "visible_behavior": [cfg["visible_behavior"]],
                },
                "dialogue": dialogue,
                "visible_characters": visible_characters,
                "visible_props": cfg.get("visible_props", []),
                "environment_behavior": [],
                "continuity": {
                    "axis_id": "AX001",
                    "axis_side": "side_a",
                    "eyelines": [
                        {"character": name, "target": addressee, "direction": "screen_right"}
                        for name in visible_characters
                    ],
                    "screen_directions": [
                        {"entity": name, "kind": "eyeline", "direction": "screen_right"}
                        for name in visible_characters
                    ],
                    "action_match": {"incoming": None, "outgoing": None},
                    "intentional_exceptions": [],
                },
                "continuity_updates": cfg.get("continuity_updates", []),
                "end_state": cfg["end_state"],
                "transition_to_next": {
                    "type": cfg.get("transition_type")
                    if idx < len(units)
                    else "scene_end",
                    "edit_point_id": None,
                    "notes": "",
                },
                "rendered_shot_description": "",
                "execution_text": "",
                "notes": "",
            }
        )
    draft["shots"] = shots

    draft["shot_plan"]["edit_points"] = []
    draft["shot_plan"]["planned_shot_count"] = len(units)
    draft["shot_plan"]["planned_edit_point_count"] = 0
    draft["shot_plan"]["planned_total_duration_seconds"] = sum(
        u["estimated_duration_seconds"] for u in units
    )

    # Normalize derived fields (screen events, viewing decisions, visual plans, etc.).
    draft = test_helpers.upgrade_draft_v240(draft)

    # Apply the intended camera description over the normalized defaults.
    patch_camera_fields(draft, camera_configs)

    # Support scale reframes for units that contain multiple screen events.
    set_reframe_spatial_strategy(draft)

    # Keep the Gate 2 visual plan in lock-step with the final camera.
    sync_visual_plan(draft)

    # Add visual uniformity reviews before finalization so Gate 2 digests include them.
    add_visual_uniformity_reviews(draft)

    # Build deterministic execution text and coverage evidence from actual fields.
    for shot in draft["shots"]:
        cfg = next(c for c in camera_configs if c["shot_id"] == shot["shot_id"])
        shot["execution_text"] = build_execution_text(
            shot, shot_facts[shot["shot_id"]], cfg.get("environment", "场景环境保持安静")
        )
        shot["coverage_evidence"] = build_coverage_evidence(
            shot, shot_facts[shot["shot_id"]]
        )

    # Confirm gates and compute stage digests before final hashing.
    for gate in ("gate_1", "gate_2"):
        draft["confirmations"][gate]["status"] = "confirmed"
        draft["confirmations"][gate]["notes"] = "fixture 自动确认"
    draft = test_helpers.refresh_confirmation_digests(draft)

    # Finalize hashes and rendered descriptions.
    draft = delivery.prepare_data(draft)
    return draft


def dinner_party_fixture() -> dict:
    locked_text = (
        "包厢内，陈、刘、周三人对坐圆桌。\n"
        "陈举起酒杯：这杯我先敬大家。\n"
        "刘笑着摆手：陈总客气了，我先干为敬。\n"
        "周沉默片刻，端起茶杯：我以茶代酒。\n"
        "陈放下酒杯，看向周：周小姐还是不赏脸？\n"
        "周起身，将茶杯轻轻搁在桌上：我身体不舒服，先告辞。\n"
    )
    profile = {
        "rhythm": "restrained",
        "camera_energy": "responsive",
        "visual_distance": "intimate",
        "performance_focus": "face",
        "space_strategy": "embedded_reveal",
        "transition_language": ["gaze_cut", "long_hold", "action_cut"],
        "priorities": ["捕捉敬酒时的微表情", "让圆桌空间成为关系压力的容器"],
        "natural_language_intent": "摄影机贴近人物表情与动作，用圆桌空间承载权力张力。",
    }
    alt_profile = {
        "rhythm": "balanced",
        "camera_energy": "static",
        "visual_distance": "observational",
        "performance_focus": "body",
        "space_strategy": "establish_then_enter",
        "transition_language": ["hard_cut"],
        "priorities": ["先建立人物空间关系", "让动作承担节奏变化"],
        "natural_language_intent": "保持观察距离，以完整身体动作建立空间。",
    }
    cnt_profile = {
        "rhythm": "kinetic",
        "camera_energy": "assertive",
        "visual_distance": "mixed",
        "performance_focus": "blocking",
        "space_strategy": "subjective",
        "transition_language": ["sound_bridge", "action_cut"],
        "priorities": ["让空间位移牵引观看", "用身体姿态外化情绪"],
        "natural_language_intent": "让摄影机被人物动作牵引，以空间变化放大情绪。",
    }
    style_options = [
        {
            "option_id": "STYLE-01",
            "label": "权力餐桌上的克制压迫（参考大卫·芬奇）",
            "rationale": test_helpers.style_rationale(
                fit="敬酒场景的权力施压由动作与沉默推进。",
                time_edit="在陈举杯与周拒绝之间保留停顿。",
                camera="贴近持杯手势与面部反应，不频繁运动。",
                space="圆桌成为三角权力关系的视觉容器。",
                performance="捕捉陈的控制、刘的逢迎、周的克制。",
                benefit="让观众在敬酒礼仪中感受到关系压力。",
                risk="过度克制可能削弱冲突爆发力。",
            ),
            "profile": profile,
        },
        {
            "option_id": "STYLE-02",
            "label": "家庭饭局中的隐忍距离（参考是枝裕和）",
            "rationale": test_helpers.style_rationale(
                fit="日常饭局的空间与迟到反应可以承载关系。",
                time_edit="让身体动作和沉默自然决定镜头停留。",
                camera="保持观察距离，少于演员主动。",
                space="先建立圆桌共同空间，再进入个人反应。",
                performance="观看举杯、拒绝与起身后的余波。",
                benefit="保留关系的生活质感。",
                risk="可能减弱权力冲突的戏剧压力。",
            ),
            "profile": alt_profile,
        },
        {
            "option_id": "STYLE-03",
            "label": "群像巡游中的情绪失衡（参考保罗·索伦蒂诺）",
            "rationale": test_helpers.style_rationale(
                fit="圆桌与身体动作可以成为情绪巡游的舞台。",
                time_edit="用音乐和空间位移放大拒绝时刻。",
                camera="允许缓慢的环绕与推进。",
                space="让圆桌、酒杯与起身形成几何舞台。",
                performance="观看身体姿态与空间位移的情绪外化。",
                benefit="放大拒绝时刻的仪式感。",
                risk="过度舞台化会损害真实饭局质感。",
            ),
            "profile": cnt_profile,
        },
    ]

    facts = [
        {
            "fact_id": "F001",
            "type": "position",
            "text": "包厢内，陈、刘、周三人对坐圆桌。",
            "performers": ["陈", "刘", "周"],
            "source_fragment": "包厢内，陈、刘、周三人对坐圆桌。",
        },
        {
            "fact_id": "F002",
            "type": "action",
            "text": "陈举起酒杯",
            "performers": ["陈"],
            "source_fragment": "陈举起酒杯：这杯我先敬大家。",
        },
        {
            "fact_id": "F003",
            "type": "dialogue",
            "text": "这杯我先敬大家。",
            "speaker": "陈",
            "performers": ["陈"],
            "source_fragment": "陈举起酒杯：这杯我先敬大家。",
        },
        {
            "fact_id": "F004",
            "type": "action",
            "text": "刘笑着摆手",
            "performers": ["刘"],
            "source_fragment": "刘笑着摆手：陈总客气了，我先干为敬。",
        },
        {
            "fact_id": "F005",
            "type": "dialogue",
            "text": "陈总客气了，我先干为敬。",
            "speaker": "刘",
            "performers": ["刘"],
            "source_fragment": "刘笑着摆手：陈总客气了，我先干为敬。",
        },
        {
            "fact_id": "F006",
            "type": "action",
            "text": "周沉默片刻，端起茶杯",
            "performers": ["周"],
            "source_fragment": "周沉默片刻，端起茶杯：我以茶代酒。",
        },
        {
            "fact_id": "F007",
            "type": "dialogue",
            "text": "我以茶代酒。",
            "speaker": "周",
            "performers": ["周"],
            "source_fragment": "周沉默片刻，端起茶杯：我以茶代酒。",
        },
        {
            "fact_id": "F008",
            "type": "action",
            "text": "陈放下酒杯，看向周",
            "performers": ["陈"],
            "source_fragment": "陈放下酒杯，看向周：周小姐还是不赏脸？",
        },
        {
            "fact_id": "F009",
            "type": "dialogue",
            "text": "周小姐还是不赏脸？",
            "speaker": "陈",
            "performers": ["陈"],
            "source_fragment": "陈放下酒杯，看向周：周小姐还是不赏脸？",
        },
        {
            "fact_id": "F010",
            "type": "action",
            "text": "周起身，将茶杯轻轻搁在桌上",
            "performers": ["周"],
            "source_fragment": "周起身，将茶杯轻轻搁在桌上：我身体不舒服，先告辞。",
        },
        {
            "fact_id": "F011",
            "type": "dialogue",
            "text": "我身体不舒服，先告辞。",
            "speaker": "周",
            "performers": ["周"],
            "source_fragment": "周起身，将茶杯轻轻搁在桌上：我身体不舒服，先告辞。",
        },
    ]
    for fact in facts:
        fact["source_spans"] = [span(fact["source_fragment"], locked_text)]

    scene = {
        "scene_id": "SC001",
        "scene": "饭局包厢",
        "reality_layer": "现实",
        "axes": [
            {
                "axis_id": "AX001",
                "axis_type": "eyeline",
                "endpoint_a": "陈",
                "endpoint_b": "周",
            },
            {
                "axis_id": "AX002",
                "axis_type": "eyeline",
                "endpoint_a": "刘",
                "endpoint_b": "陈",
            },
        ],
        "initial_continuity": {
            "characters": [
                {
                    "name": "陈",
                    "position": "圆桌主位",
                    "facing": "圆桌中央",
                    "eyeline": "周",
                    "presence": "onscreen",
                    "state": "主导",
                },
                {
                    "name": "刘",
                    "position": "陈右侧",
                    "facing": "圆桌中央",
                    "eyeline": "陈",
                    "presence": "onscreen",
                    "state": "逢迎",
                },
                {
                    "name": "周",
                    "position": "陈对面",
                    "facing": "圆桌中央",
                    "eyeline": "陈",
                    "presence": "onscreen",
                    "state": "克制",
                },
            ],
            "props": [
                {
                    "name": "酒杯",
                    "position": "圆桌中央",
                    "owner": "陈",
                    "state": "空置",
                },
                {
                    "name": "茶杯",
                    "position": "周右手边",
                    "owner": "周",
                    "state": "半满",
                },
            ],
            "fixed_objects": [
                {"name": "圆桌", "position": "包厢中央", "state": "完好"},
                {"name": "椅子", "position": "圆桌周围", "state": "有人落座"},
            ],
            "sound_sources": [],
            "reality_layer": "现实",
        },
        "directing_plan": {
            "scene_objective": "通过敬酒与拒绝展示三人权力与亲疏关系。",
            "progression": [
                "建立圆桌权力三角",
                "陈敬酒施压",
                "周以茶代酒抵抗",
                "冲突爆发并退场",
            ],
            "pov_flow": ["先建立三人空间关系", "随敬酒权转移观察位置"],
            "entry_strategy": {
                "mode": "spatial_establish",
                "observer_position": "包厢顶部中央，垂直俯视圆桌",
                "required_spatial_information": ["陈、刘、周三人对坐圆桌"],
                "withheld_information": ["周的真实态度"],
                "reason": "先建立空间与人物关系，为后续权力张力提供容器。",
            },
            "style_anchors": [
                {
                    "style_anchor_id": "SA001",
                    "profile_basis": [
                        {"field": "priorities", "value": "捕捉敬酒时的微表情"}
                    ],
                    "scene_application": "贴近持杯与举杯动作，捕捉面部微表情。",
                    "avoidance": "避免全景固定或景别单调轮换。",
                }
            ],
        },
        "inherits_from": None,
        "inherited_states": [],
    }

    camera_configs = [
        {
            "shot_id": "SH001",
            "duration_seconds": 4,
            "shot_size": "全景→中景",
            "angle": "俯视",
            "position": "包厢顶部中央",
            "composition": "包厢内，陈、刘、周三人对坐圆桌。三人关系清楚可读",
            "movement": "缓慢推进后固定",
            "logic": "从包厢顶部中央垂直向下观察圆桌",
            "start_frame": "三人落座圆桌",
            "end_frame": "陈举起酒杯",
            "motivation": "先建立三人空间关系，让权力三角清楚可读。",
            "visible_behavior": "三人围坐，目光在酒杯间交汇",
            "addressee": "周",
            "visible_characters": ["陈", "刘", "周"],
            "blocking_actions": {
                "陈": "陈举起酒杯",
                "刘": "刘保持坐姿",
                "周": "周保持坐姿",
            },
            "end_state": ["陈举起酒杯", "刘保持坐姿", "周保持坐姿"],
            "environment": "包厢内灯光柔和，圆桌饭局保持安静",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH002",
            "duration_seconds": 3,
            "shot_size": "近景",
            "angle": "平视",
            "position": "陈面前近处",
            "composition": "陈手持酒杯，面部为主位",
            "movement": "固定",
            "logic": "朝陈面部观察，保持陈周轴线同侧",
            "start_frame": "陈举杯说话前",
            "end_frame": "陈说完敬酒词",
            "motivation": "让陈的敬酒姿态与表情成为观看中心。",
            "visible_behavior": "陈举杯，目光扫过圆桌",
            "addressee": "周",
            "visible_characters": ["陈"],
            "blocking_actions": {"陈": "陈举起酒杯"},
            "end_state": ["陈举杯说完"],
            "environment": "圆桌饭局环境保持安静",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH003",
            "duration_seconds": 3,
            "shot_size": "中近景→近景",
            "angle": "平视",
            "position": "陈肩后",
            "composition": "刘面部为主位，陈肩背在前景",
            "movement": "缓慢推进后固定",
            "logic": "从陈肩后朝刘观察，保持陈刘轴线同侧",
            "start_frame": "刘笑着摆手",
            "end_frame": "刘说完敬酒词",
            "motivation": "在过肩关系中捕捉刘的逢迎反应。",
            "visible_behavior": "刘笑着摆手，语气逢迎",
            "addressee": "陈",
            "visible_characters": ["刘", "陈", "周"],
            "blocking_actions": {
                "刘": "刘笑着摆手",
                "陈": "陈保持举杯",
            },
            "end_state": ["刘说完敬酒词", "陈保持举杯"],
            "environment": "圆桌饭局环境保持安静",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH004",
            "duration_seconds": 3,
            "shot_size": "中近景→近景",
            "angle": "平视",
            "position": "周面前近处",
            "composition": "周手持茶杯，面部为主位",
            "movement": "缓慢推进后固定",
            "logic": "朝周面部观察，保持陈周轴线同侧",
            "start_frame": "周沉默片刻",
            "end_frame": "周说完以茶代酒",
            "motivation": "贴近周的克制，让拒绝姿态清楚成立。",
            "visible_behavior": "周垂眼端茶杯，语气平静但坚定",
            "addressee": "陈",
            "visible_characters": ["周"],
            "blocking_actions": {"周": "周沉默片刻，端起茶杯"},
            "end_state": ["周端着茶杯"],
            "environment": "圆桌饭局环境保持安静",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH005",
            "duration_seconds": 3,
            "shot_size": "中近景→近景",
            "angle": "仰视",
            "position": "桌面低处向上",
            "composition": "陈面部在画面高处，手持酒杯",
            "movement": "固定",
            "logic": "从桌面低处向上观察陈",
            "start_frame": "陈放下酒杯",
            "end_frame": "陈说完施压话语",
            "motivation": "以低角度强化陈的压迫性注视。",
            "visible_behavior": "陈放下酒杯，眼神紧盯着周",
            "addressee": "周",
            "visible_characters": ["陈"],
            "blocking_actions": {"陈": "陈放下酒杯，看向周"},
            "end_state": ["陈放下酒杯"],
            "environment": "圆桌饭局环境保持安静",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH006",
            "duration_seconds": 3,
            "shot_size": "中景→近景",
            "angle": "平视",
            "position": "包厢门口朝向周",
            "composition": "周起身离席，向门口走去",
            "movement": "缓慢跟随后固定",
            "logic": "从门口朝周观察，保持陈周轴线同侧",
            "start_frame": "周起身",
            "end_frame": "周走出包厢",
            "motivation": "目送周退场，让拒绝成为可见结果。",
            "visible_behavior": "周将茶杯搁下，起身不回头",
            "addressee": "陈",
            "visible_characters": ["周"],
            "blocking_actions": {"周": "周起身，将茶杯轻轻搁在桌上"},
            "end_state": ["周走出包厢", "陈刘留在桌边"],
            "environment": "包厢门口光线稍暗，圆桌留在背景",
            "transition_type": "scene_end",
            "continuity_updates": [
                {
                    "entity_type": "prop",
                    "entity": "茶杯",
                    "field": "state",
                    "from": "半满",
                    "to": "搁在桌上",
                    "evidence_fact_ids": ["F010"],
                }
            ],
        },
    ]

    return make_draft(
        project_id="P-FIXTURE-253",
        delivery_slug="dinner-party-scene",
        locked_text=locked_text,
        source_boundary="从三人落座到周起身离席。",
        narrative_function="通过敬酒与拒绝展示三人权力与亲疏关系。",
        dramatic_progression="陈主导酒局，刘逢迎，周以茶代酒并最终离席，冲突升级。",
        character_relations=[
            "陈处于权力上位，主动敬酒施压",
            "刘附和陈，缓和气氛",
            "周保持抵抗，最终以身体为由退场",
        ],
        source_constraints=["逐字保留六句对白", "周起身离席必须完整"],
        director_profile=profile,
        style_options=style_options,
        scene=scene,
        beat_groups=[
            [facts[0], facts[1]],
            [facts[2]],
            [facts[3], facts[4]],
            [facts[5], facts[6]],
            [facts[7], facts[8]],
            [facts[9], facts[10]],
        ],
        camera_configs=camera_configs,
    )


def courtroom_fixture() -> dict:
    locked_text = (
        "法庭内，法官、被告、律师、法警各就其位。\n"
        "法官敲响法槌：请保持安静。\n"
        "被告抬头，双手攥紧栏杆：我没有杀人。\n"
        "律师起身：审判长，我方申请出示新证据。\n"
        "法官看向律师：请陈述理由。\n"
        "律师从公文包取出文件：这份笔录可以证明被告不在现场。\n"
        "法警走向被告，按住他的肩：休庭后请随我来。\n"
        "被告挣脱，指向律师：你早就知道！\n"
    )
    profile = {
        "rhythm": "restrained",
        "camera_energy": "responsive",
        "visual_distance": "observational",
        "performance_focus": "face",
        "space_strategy": "establish_then_enter",
        "transition_language": ["hard_cut", "gaze_cut"],
        "priorities": ["保持法庭空间的庄严感", "让面部反应承担戏剧推进"],
        "natural_language_intent": "先建立法庭空间，再用静态与缓推捕捉对峙中的面部反应。",
    }
    alt_profile = {
        "rhythm": "balanced",
        "camera_energy": "static",
        "visual_distance": "observational",
        "performance_focus": "body",
        "space_strategy": "establish_then_enter",
        "transition_language": ["hard_cut"],
        "priorities": ["先建立法庭空间", "让动作承担节奏变化"],
        "natural_language_intent": "保持观察距离，以完整身体动作建立法庭空间。",
    }
    cnt_profile = {
        "rhythm": "kinetic",
        "camera_energy": "assertive",
        "visual_distance": "mixed",
        "performance_focus": "blocking",
        "space_strategy": "subjective",
        "transition_language": ["sound_bridge", "action_cut"],
        "priorities": ["让空间位移牵引观看", "用身体姿态外化情绪"],
        "natural_language_intent": "让摄影机被庭辩动作牵引，以空间变化放大情绪。",
    }
    style_options = [
        {
            "option_id": "STYLE-01",
            "label": "法庭纪实中的克制距离（参考大卫·芬奇）",
            "rationale": test_helpers.style_rationale(
                fit="法庭审判的紧张来自对峙而非运动。",
                time_edit="在发言与反应之间保留停顿。",
                camera="静态机位与缓慢推近捕捉面部表情。",
                space="先建立法庭空间，再进入人物关系。",
                performance="观察法官、被告、律师的细微反应。",
                benefit="让审判压力自然积累。",
                risk="可能显得节奏迟缓。",
            ),
            "profile": profile,
        },
        {
            "option_id": "STYLE-02",
            "label": "社会剧式的隐忍观察（参考是枝裕和）",
            "rationale": test_helpers.style_rationale(
                fit="人物关系比庭辩结果更重要。",
                time_edit="让身体动作和沉默决定镜头长度。",
                camera="保持观察距离，减少侵入。",
                space="先建立法庭共同空间，再进入个人困境。",
                performance="捕捉被告的脆弱与律师的坚定。",
                benefit="保留人物的生活质感。",
                risk="可能削弱庭辩的戏剧张力。",
            ),
            "profile": alt_profile,
        },
        {
            "option_id": "STYLE-03",
            "label": "高度戏剧化的审判舞台（参考保罗·索伦蒂诺）",
            "rationale": test_helpers.style_rationale(
                fit="法庭可以作为情绪爆发的舞台。",
                time_edit="用音乐和机位巡游放大高潮。",
                camera="允许环绕与低角度推进。",
                space="让法庭几何结构成为权力图景。",
                performance="用身体姿态外化情绪。",
                benefit="放大最后爆发的仪式感。",
                risk="过度舞台化会损害真实法庭质感。",
            ),
            "profile": cnt_profile,
        },
    ]

    facts = [
        {
            "fact_id": "F001",
            "type": "position",
            "text": "法庭内，法官、被告、律师、法警各就其位。",
            "performers": ["法官", "被告", "律师", "法警"],
            "source_fragment": "法庭内，法官、被告、律师、法警各就其位。",
        },
        {
            "fact_id": "F002",
            "type": "action",
            "text": "法官敲响法槌",
            "performers": ["法官"],
            "source_fragment": "法官敲响法槌：请保持安静。",
        },
        {
            "fact_id": "F003",
            "type": "dialogue",
            "text": "请保持安静。",
            "speaker": "法官",
            "performers": ["法官"],
            "source_fragment": "法官敲响法槌：请保持安静。",
        },
        {
            "fact_id": "F004",
            "type": "action",
            "text": "被告抬头，双手攥紧栏杆",
            "performers": ["被告"],
            "source_fragment": "被告抬头，双手攥紧栏杆：我没有杀人。",
        },
        {
            "fact_id": "F005",
            "type": "dialogue",
            "text": "我没有杀人。",
            "speaker": "被告",
            "performers": ["被告"],
            "source_fragment": "被告抬头，双手攥紧栏杆：我没有杀人。",
        },
        {
            "fact_id": "F006",
            "type": "action",
            "text": "律师起身",
            "performers": ["律师"],
            "source_fragment": "律师起身：审判长，我方申请出示新证据。",
        },
        {
            "fact_id": "F007",
            "type": "dialogue",
            "text": "审判长，我方申请出示新证据。",
            "speaker": "律师",
            "performers": ["律师"],
            "source_fragment": "律师起身：审判长，我方申请出示新证据。",
        },
        {
            "fact_id": "F008",
            "type": "action",
            "text": "法官看向律师",
            "performers": ["法官"],
            "source_fragment": "法官看向律师：请陈述理由。",
        },
        {
            "fact_id": "F009",
            "type": "dialogue",
            "text": "请陈述理由。",
            "speaker": "法官",
            "performers": ["法官"],
            "source_fragment": "法官看向律师：请陈述理由。",
        },
        {
            "fact_id": "F010",
            "type": "action",
            "text": "律师从公文包取出文件",
            "performers": ["律师"],
            "source_fragment": "律师从公文包取出文件：这份笔录可以证明被告不在现场。",
        },
        {
            "fact_id": "F011",
            "type": "dialogue",
            "text": "这份笔录可以证明被告不在现场。",
            "speaker": "律师",
            "performers": ["律师"],
            "source_fragment": "律师从公文包取出文件：这份笔录可以证明被告不在现场。",
        },
        {
            "fact_id": "F012",
            "type": "action",
            "text": "法警走向被告，按住他的肩",
            "performers": ["法警"],
            "source_fragment": "法警走向被告，按住他的肩：休庭后请随我来。",
        },
        {
            "fact_id": "F013",
            "type": "dialogue",
            "text": "休庭后请随我来。",
            "speaker": "法警",
            "performers": ["法警"],
            "source_fragment": "法警走向被告，按住他的肩：休庭后请随我来。",
        },
        {
            "fact_id": "F014",
            "type": "action",
            "text": "被告挣脱，指向律师",
            "performers": ["被告"],
            "source_fragment": "被告挣脱，指向律师：你早就知道！",
        },
        {
            "fact_id": "F015",
            "type": "dialogue",
            "text": "你早就知道！",
            "speaker": "被告",
            "performers": ["被告"],
            "source_fragment": "被告挣脱，指向律师：你早就知道！",
        },
    ]
    for fact in facts:
        fact["source_spans"] = [span(fact["source_fragment"], locked_text)]

    scene = {
        "scene_id": "SC001",
        "scene": "刑事法庭",
        "reality_layer": "现实",
        "axes": [
            {
                "axis_id": "AX001",
                "axis_type": "eyeline",
                "endpoint_a": "法官",
                "endpoint_b": "被告",
            },
            {
                "axis_id": "AX002",
                "axis_type": "eyeline",
                "endpoint_a": "法官",
                "endpoint_b": "律师",
            },
            {
                "axis_id": "AX003",
                "axis_type": "eyeline",
                "endpoint_a": "法警",
                "endpoint_b": "被告",
            },
        ],
        "initial_continuity": {
            "characters": [
                {
                    "name": "法官",
                    "position": "审判台后",
                    "facing": "被告",
                    "eyeline": "被告",
                    "presence": "onscreen",
                    "state": "主持",
                },
                {
                    "name": "被告",
                    "position": "被告席",
                    "facing": "法官",
                    "eyeline": "法官",
                    "presence": "onscreen",
                    "state": "紧张",
                },
                {
                    "name": "律师",
                    "position": "辩护席",
                    "facing": "法官",
                    "eyeline": "法官",
                    "presence": "onscreen",
                    "state": "辩护",
                },
                {
                    "name": "法警",
                    "position": "法庭侧门",
                    "facing": "被告",
                    "eyeline": "被告",
                    "presence": "onscreen",
                    "state": "待命",
                },
            ],
            "props": [
                {"name": "法槌", "position": "审判台", "owner": "法官", "state": "待用"},
                {"name": "栏杆", "position": "被告席前", "owner": "法庭", "state": "完好"},
                {"name": "公文包", "position": "辩护席", "owner": "律师", "state": "关闭"},
                {"name": "文件", "position": "公文包内", "owner": "律师", "state": "待出示"},
            ],
            "fixed_objects": [
                {"name": "审判台", "position": "法庭前方中央", "state": "完好"},
                {"name": "被告席", "position": "审判台前方", "state": "完好"},
                {"name": "辩护席", "position": "被告席右侧", "state": "完好"},
                {"name": "旁听席", "position": "法庭后方", "state": "空座"},
            ],
            "sound_sources": [],
            "reality_layer": "现实",
        },
        "directing_plan": {
            "scene_objective": "通过法庭对峙展示权力、辩护与被告崩溃的戏剧过程。",
            "progression": [
                "建立法庭四方空间",
                "被告否认杀人",
                "律师申请出示证据",
                "法官质疑证据",
                "律师出示不在场证明",
                "法警控制被告",
                "被告情绪爆发指控律师",
            ],
            "pov_flow": ["先建立法庭空间", "随发言权与控制权转移观察位置"],
            "entry_strategy": {
                "mode": "spatial_establish",
                "observer_position": "法庭旁听席后方高处，俯视审判区",
                "required_spatial_information": ["法官、被告、律师、法警各就其位"],
                "withheld_information": ["被告是否会认罪", "律师证据是否有效"],
                "reason": "先建立法庭庄严空间与四方位置，为后续权力拉扯提供容器。",
            },
            "style_anchors": [
                {
                    "style_anchor_id": "SA001",
                    "profile_basis": [
                        {"field": "priorities", "value": "保持法庭空间的庄严感"}
                    ],
                    "scene_application": "以静态和缓推为主，让面部反应成为戏剧推进力。",
                    "avoidance": "避免手持晃动、快速环绕等破坏庄严感的运动。",
                }
            ],
        },
        "inherits_from": None,
        "inherited_states": [],
    }

    camera_configs = [
        {
            "shot_id": "SH001",
            "duration_seconds": 4,
            "shot_size": "全景→中景",
            "angle": "俯视",
            "position": "法庭旁听席后方高处",
            "composition": "法庭内，法官、被告、律师、法警各就其位。国徽在背景",
            "movement": "缓慢推进后固定",
            "logic": "从法庭后方高处垂直向下观察审判区",
            "start_frame": "四人各就其位",
            "end_frame": "法官敲响法槌前",
            "motivation": "先建立法庭空间与四方位置关系。",
            "visible_behavior": "法庭内肃静，四人各就其位",
            "addressee": "被告",
            "visible_characters": ["法官", "被告", "律师", "法警"],
            "blocking_actions": {
                "法官": "法官敲响法槌",
                "被告": "被告双手攥紧栏杆",
                "律师": "律师坐在辩护席",
                "法警": "法警站在门边",
            },
            "end_state": ["法官敲响法槌", "其余三人保持原位"],
            "environment": "法庭内安静肃穆，国徽高悬",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH002",
            "duration_seconds": 3,
            "shot_size": "中近景→近景",
            "angle": "平视",
            "position": "被告正前方",
            "composition": "被告抬头，双手攥紧栏杆，面部为主位",
            "movement": "缓慢推进后固定",
            "logic": "朝被告面部观察，保持法官被告轴线同侧",
            "start_frame": "被告抬头前",
            "end_frame": "被告说完否认",
            "motivation": "贴近被告的紧张与否认。",
            "visible_behavior": "被告抬头，双手攥紧栏杆",
            "addressee": "法官",
            "visible_characters": ["被告"],
            "blocking_actions": {"被告": "被告抬头，双手攥紧栏杆"},
            "end_state": ["被告说完否认"],
            "environment": "法庭内安静肃穆",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH003",
            "duration_seconds": 3,
            "shot_size": "中近景→近景",
            "angle": "平视",
            "position": "法官肩后",
            "composition": "律师面部为主位，法官肩背在前景",
            "movement": "缓慢推进后固定",
            "logic": "从法官肩后朝律师观察，保持法官律师轴线同侧",
            "start_frame": "律师起身前",
            "end_frame": "律师说完申请",
            "motivation": "在过肩关系中呈现律师的正式申请。",
            "visible_behavior": "律师起身，语气沉稳",
            "addressee": "法官",
            "visible_characters": ["律师", "法官", "被告", "法警"],
            "blocking_actions": {
                "律师": "律师起身",
            },
            "end_state": ["律师说完申请", "法官保持注视"],
            "environment": "法庭内安静肃穆",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH004",
            "duration_seconds": 3,
            "shot_size": "近景",
            "angle": "微仰视",
            "position": "律师席侧前方低处",
            "composition": "法官手持法槌，面部为主位",
            "movement": "固定",
            "logic": "从低处朝法官观察，保持法官律师轴线同侧",
            "start_frame": "法官看向律师",
            "end_frame": "法官说完理由要求",
            "motivation": "以微仰角度强化法官的裁决位置。",
            "visible_behavior": "法官手持法槌，目光审视",
            "addressee": "律师",
            "visible_characters": ["法官"],
            "blocking_actions": {"法官": "法官看向律师"},
            "end_state": ["法官说完理由要求"],
            "environment": "法庭内安静肃穆",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH005",
            "duration_seconds": 3,
            "shot_size": "中景→近景",
            "angle": "平视",
            "position": "律师身侧",
            "composition": "律师从公文包取出文件，文件进入画面",
            "movement": "缓慢推进后固定",
            "logic": "朝律师手部与文件观察，保持法官律师轴线同侧",
            "start_frame": "律师打开公文包",
            "end_frame": "律师出示文件完毕",
            "motivation": "让证据物件成为画面落点。",
            "visible_behavior": "律师从公文包取出文件",
            "addressee": "法官",
            "visible_characters": ["律师"],
            "blocking_actions": {"律师": "律师从公文包取出文件"},
            "end_state": ["律师取出文件"],
            "environment": "法庭内安静肃穆",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH006",
            "duration_seconds": 3,
            "shot_size": "中近景→近景",
            "angle": "平视",
            "position": "被告身后侧",
            "composition": "法警走向被告，按住他的肩",
            "movement": "缓慢跟随后固定",
            "logic": "从被告身后朝法警观察，保持法警被告轴线同侧",
            "start_frame": "法警起步",
            "end_frame": "法警按住被告肩膀",
            "motivation": "记录法警对被告的控制动作。",
            "visible_behavior": "法警走向被告，按住他的肩",
            "addressee": "被告",
            "visible_characters": ["法警", "被告"],
            "blocking_actions": {
                "法警": "法警走向被告，按住他的肩",
                "被告": "被告保持坐姿",
            },
            "end_state": ["法警按住被告肩膀"],
            "environment": "法庭内气氛紧张",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH007",
            "duration_seconds": 3,
            "shot_size": "中近景→近景",
            "angle": "平视",
            "position": "律师席侧后方",
            "composition": "被告挣脱并指向律师，律师在背景",
            "movement": "缓慢推进后固定",
            "logic": "朝被告观察，保持被告律师轴线同侧",
            "start_frame": "被告挣脱",
            "end_frame": "被告喊完指控",
            "motivation": "捕捉被告情绪失控的瞬间。",
            "visible_behavior": "被告挣脱，指向律师",
            "addressee": "律师",
            "visible_characters": ["被告", "律师"],
            "blocking_actions": {"被告": "被告挣脱，指向律师"},
            "end_state": ["被告喊完指控"],
            "environment": "法庭内气氛紧张",
            "transition_type": "scene_end",
        },
    ]

    return make_draft(
        project_id="P-FIXTURE-253",
        delivery_slug="courtroom-scene",
        locked_text=locked_text,
        source_boundary="从四人各就其位到被告喊完指控。",
        narrative_function="通过法庭对峙展示权力、辩护与被告崩溃的戏剧过程。",
        dramatic_progression="法官主持秩序，被告否认，律师申请证据，法官质疑，律师出示证据，法警控制被告，被告情绪爆发指控律师。",
        character_relations=[
            "法官掌控庭审程序与节奏",
            "律师为被告辩护并提交证据",
            "被告处于被审位置，情绪逐渐失控",
            "法警代表强制力，最终控制被告",
        ],
        source_constraints=["逐字保留七句对白", "被告最终情绪爆发完整"],
        director_profile=profile,
        style_options=style_options,
        scene=scene,
        beat_groups=[
            [facts[0], facts[1]],
            [facts[3], facts[4]],
            [facts[5], facts[6]],
            [facts[7], facts[8]],
            [facts[9], facts[10]],
            [facts[11], facts[12]],
            [facts[13], facts[14]],
        ],
        camera_configs=camera_configs,
    )


def chase_fixture() -> dict:
    locked_text = (
        "深夜巷口，逃犯、警察甲、警察乙形成追逐三角。\n"
        "逃犯冲出拐角。\n"
        "警察甲拔腿追去：站住！\n"
        "逃犯翻过矮墙，落地不稳。\n"
        "警察乙从另一侧包抄：别跑！\n"
        "逃犯撞翻货架，水果滚落一地。\n"
        "警察甲扑上前，按住逃犯肩膀：你跑不掉了。\n"
        "逃犯喘息着抬头：我认了。\n"
    )
    profile = {
        "rhythm": "kinetic",
        "camera_energy": "assertive",
        "visual_distance": "mixed",
        "performance_focus": "blocking",
        "space_strategy": "subjective",
        "transition_language": ["action_cut", "sound_bridge"],
        "priorities": ["让空间位移牵引观看", "捕捉喘息与身体失衡"],
        "natural_language_intent": "让摄影机被追逃动作牵引，以空间变化放大惊慌与压迫。",
    }
    alt_profile = {
        "rhythm": "balanced",
        "camera_energy": "responsive",
        "visual_distance": "observational",
        "performance_focus": "body",
        "space_strategy": "establish_then_enter",
        "transition_language": ["hard_cut"],
        "priorities": ["先建立巷道空间", "让奔跑动作承担节奏"],
        "natural_language_intent": "保持观察距离，以完整身体动作建立巷道空间。",
    }
    cnt_profile = {
        "rhythm": "restrained",
        "camera_energy": "static",
        "visual_distance": "intimate",
        "performance_focus": "face",
        "space_strategy": "embedded_reveal",
        "transition_language": ["long_hold", "gaze_cut"],
        "priorities": ["保留追逃后的面部余波", "让环境细节缓慢显露"],
        "natural_language_intent": "以静态与缓推捕捉追逃后的疲惫与认输。",
    }
    style_options = [
        {
            "option_id": "STYLE-01",
            "label": "追逐中的动能紧迫（参考保罗·格林格拉斯）",
            "rationale": test_helpers.style_rationale(
                fit="追逃关系由身体位移和喘息推进。",
                time_edit="在动作边界处快速切换，不拖泥带水。",
                camera="手持与跟拍让摄影机成为追击者。",
                space="让巷道纵深和障碍物制造压迫。",
                performance="捕捉逃犯的惊慌与警察的果断。",
                benefit="让观众在追逐中感受呼吸节奏。",
                risk="过度晃动可能导致空间失读。",
            ),
            "profile": profile,
        },
        {
            "option_id": "STYLE-02",
            "label": "冷静观察下的暴力距离（参考是枝裕和）",
            "rationale": test_helpers.style_rationale(
                fit="追逐作为社会冲突的缩影。",
                time_edit="保留动作之间的沉默间隙。",
                camera="保持观察距离，让动作自行完成。",
                space="先建立巷道空间，再进入人物动作。",
                performance="观看奔跑、翻越与倒地后的余波。",
                benefit="保留事件的纪实质感。",
                risk="可能削弱追逐的紧迫感。",
            ),
            "profile": alt_profile,
        },
        {
            "option_id": "STYLE-03",
            "label": "夜色中的情绪失衡（参考保罗·索伦蒂诺）",
            "rationale": test_helpers.style_rationale(
                fit="巷道可以成为情绪巡游的舞台。",
                time_edit="用音乐和光影位移放大被捕瞬间。",
                camera="允许环绕与慢速推进。",
                space="让路灯、货架与墙壁形成几何舞台。",
                performance="用身体姿态外化惊慌与疲惫。",
                benefit="放大被捕时刻的仪式感。",
                risk="过度风格化会损害真实追逃质感。",
            ),
            "profile": cnt_profile,
        },
    ]

    facts = [
        {
            "fact_id": "F001",
            "type": "position",
            "text": "深夜巷口，逃犯、警察甲、警察乙形成追逐三角。",
            "performers": ["逃犯", "警察甲", "警察乙"],
            "source_fragment": "深夜巷口，逃犯、警察甲、警察乙形成追逐三角。",
        },
        {
            "fact_id": "F002",
            "type": "action",
            "text": "逃犯冲出拐角",
            "performers": ["逃犯"],
            "source_fragment": "逃犯冲出拐角。",
        },
        {
            "fact_id": "F003",
            "type": "action",
            "text": "警察甲拔腿追去",
            "performers": ["警察甲"],
            "source_fragment": "警察甲拔腿追去：站住！",
        },
        {
            "fact_id": "F004",
            "type": "dialogue",
            "text": "站住！",
            "speaker": "警察甲",
            "performers": ["警察甲"],
            "source_fragment": "警察甲拔腿追去：站住！",
        },
        {
            "fact_id": "F005",
            "type": "action",
            "text": "逃犯翻过矮墙，落地不稳",
            "performers": ["逃犯"],
            "source_fragment": "逃犯翻过矮墙，落地不稳。",
        },
        {
            "fact_id": "F006",
            "type": "action",
            "text": "警察乙从另一侧包抄",
            "performers": ["警察乙"],
            "source_fragment": "警察乙从另一侧包抄：别跑！",
        },
        {
            "fact_id": "F007",
            "type": "dialogue",
            "text": "别跑！",
            "speaker": "警察乙",
            "performers": ["警察乙"],
            "source_fragment": "警察乙从另一侧包抄：别跑！",
        },
        {
            "fact_id": "F008",
            "type": "action",
            "text": "逃犯撞翻货架，水果滚落一地",
            "performers": ["逃犯"],
            "source_fragment": "逃犯撞翻货架，水果滚落一地。",
        },
        {
            "fact_id": "F009",
            "type": "action",
            "text": "警察甲扑上前，按住逃犯肩膀",
            "performers": ["警察甲"],
            "source_fragment": "警察甲扑上前，按住逃犯肩膀：你跑不掉了。",
        },
        {
            "fact_id": "F010",
            "type": "dialogue",
            "text": "你跑不掉了。",
            "speaker": "警察甲",
            "performers": ["警察甲"],
            "source_fragment": "警察甲扑上前，按住逃犯肩膀：你跑不掉了。",
        },
        {
            "fact_id": "F011",
            "type": "action",
            "text": "逃犯喘息着抬头",
            "performers": ["逃犯"],
            "source_fragment": "逃犯喘息着抬头：我认了。",
        },
        {
            "fact_id": "F012",
            "type": "dialogue",
            "text": "我认了。",
            "speaker": "逃犯",
            "performers": ["逃犯"],
            "source_fragment": "逃犯喘息着抬头：我认了。",
        },
    ]
    for fact in facts:
        fact["source_spans"] = [span(fact["source_fragment"], locked_text)]

    scene = {
        "scene_id": "SC001",
        "scene": "深夜巷道",
        "reality_layer": "现实",
        "axes": [
            {
                "axis_id": "AX001",
                "axis_type": "eyeline",
                "endpoint_a": "警察甲",
                "endpoint_b": "逃犯",
            },
            {
                "axis_id": "AX002",
                "axis_type": "eyeline",
                "endpoint_a": "警察乙",
                "endpoint_b": "逃犯",
            },
        ],
        "initial_continuity": {
            "characters": [
                {
                    "name": "逃犯",
                    "position": "巷口拐角",
                    "facing": "巷内",
                    "eyeline": "警察甲",
                    "presence": "onscreen",
                    "state": "逃窜",
                },
                {
                    "name": "警察甲",
                    "position": "逃犯身后",
                    "facing": "逃犯",
                    "eyeline": "逃犯",
                    "presence": "onscreen",
                    "state": "追击",
                },
                {
                    "name": "警察乙",
                    "position": "巷口另一侧",
                    "facing": "逃犯",
                    "eyeline": "逃犯",
                    "presence": "onscreen",
                    "state": "包抄",
                },
            ],
            "props": [
                {"name": "矮墙", "position": "巷道尽头", "owner": "环境", "state": "完好"},
                {"name": "货架", "position": "巷口小摊", "owner": "摊贩", "state": "被撞翻"},
                {"name": "水果", "position": "货架上", "owner": "摊贩", "state": "散落"},
            ],
            "fixed_objects": [
                {"name": "路灯", "position": "巷道两侧", "state": "亮着"},
                {"name": "砖墙", "position": "巷道两侧", "state": "完好"},
            ],
            "sound_sources": [],
            "reality_layer": "现实",
        },
        "directing_plan": {
            "scene_objective": "通过巷道追逐展示逃犯惊慌、警察合围与最终认命的过程。",
            "progression": [
                "建立三人追逐空间",
                "警察甲追击并喊停",
                "逃犯翻越矮墙",
                "警察乙包抄拦截",
                "逃犯撞翻货架",
                "警察甲制服逃犯",
                "逃犯喘息认罪",
            ],
            "pov_flow": ["先建立巷道纵深", "随追逃动作切换观察位置"],
            "entry_strategy": {
                "mode": "spatial_establish",
                "observer_position": "巷口二楼，俯视追逐三角",
                "required_spatial_information": ["逃犯、警察甲、警察乙形成追逐三角"],
                "withheld_information": ["逃犯最终是否被制服"],
                "reason": "先建立巷道空间与三人位置，让追逐有清晰的空间容器。",
            },
            "style_anchors": [
                {
                    "style_anchor_id": "SA001",
                    "profile_basis": [
                        {"field": "priorities", "value": "让空间位移牵引观看"}
                    ],
                    "scene_application": "用手持跟拍与快速动作切让摄影机跟随奔跑与翻越。",
                    "avoidance": "避免全场固定或同一景别重复切换。",
                }
            ],
        },
        "inherits_from": None,
        "inherited_states": [],
    }

    camera_configs = [
        {
            "shot_id": "SH001",
            "duration_seconds": 3,
            "shot_size": "全景→中景",
            "angle": "微俯视",
            "position": "巷口二楼向下",
            "composition": "深夜巷口，逃犯、警察甲、警察乙形成追逐三角。巷道纵深",
            "movement": "缓慢推进后固定",
            "logic": "从巷口高处向下观察追逐起点",
            "start_frame": "三人形成追逐三角",
            "end_frame": "逃犯冲出拐角前",
            "motivation": "先建立巷道空间与三人追逐位置。",
            "visible_behavior": "三人形成对峙，逃犯准备冲刺",
            "addressee": "警察甲",
            "visible_characters": ["逃犯", "警察甲", "警察乙"],
            "blocking_actions": {
                "逃犯": "逃犯冲出拐角",
                "警察甲": "警察甲准备追击",
                "警察乙": "警察乙准备包抄",
            },
            "end_state": ["逃犯冲出拐角", "警察甲准备追击", "警察乙准备包抄"],
            "environment": "深夜巷口，路灯昏暗",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH002",
            "duration_seconds": 3,
            "shot_size": "中近景→近景",
            "angle": "平视",
            "position": "警察甲身侧",
            "composition": "警察甲拔腿追去，面部转向逃犯",
            "movement": "手持跟随后固定",
            "logic": "沿警察甲运动方向朝逃犯观察，保持警察甲逃犯轴线同侧",
            "start_frame": "警察甲拔腿追去",
            "end_frame": "警察甲喊完站住",
            "motivation": "让观众与警察甲一同追击逃犯。",
            "visible_behavior": "警察甲拔腿追去，口中高喊",
            "addressee": "逃犯",
            "visible_characters": ["警察甲"],
            "blocking_actions": {"警察甲": "警察甲拔腿追去"},
            "end_state": ["警察甲喊完站住"],
            "environment": "深夜巷道，脚步声回响",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH003",
            "duration_seconds": 3,
            "shot_size": "中景→近景",
            "angle": "低位平视",
            "position": "矮墙下方",
            "composition": "逃犯翻过矮墙，落地不稳",
            "movement": "手持上摇后固定",
            "logic": "从矮墙下方向上观察逃犯翻越动作",
            "start_frame": "逃犯跃起翻墙",
            "end_frame": "逃犯落地不稳",
            "motivation": "以低角度强化逃犯翻越的狼狈。",
            "visible_behavior": "逃犯翻过矮墙，落地不稳",
            "addressee": "警察甲",
            "visible_characters": ["逃犯"],
            "blocking_actions": {"逃犯": "逃犯翻过矮墙，落地不稳"},
            "end_state": ["逃犯落地不稳"],
            "environment": "巷道尽头矮墙，墙后黑暗",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH004",
            "duration_seconds": 3,
            "shot_size": "中近景→近景",
            "angle": "平视",
            "position": "警察乙身后",
            "composition": "警察乙从另一侧包抄，逃犯在背景",
            "movement": "手持跟随后固定",
            "logic": "从警察乙身后朝逃犯观察，保持警察乙逃犯轴线同侧",
            "start_frame": "警察乙从另一侧包抄",
            "end_frame": "警察乙喊完别跑",
            "motivation": "展示合围视角，让逃犯无路可退。",
            "visible_behavior": "警察乙从另一侧包抄，口中高喊",
            "addressee": "逃犯",
            "visible_characters": ["警察乙"],
            "blocking_actions": {"警察乙": "警察乙从另一侧包抄"},
            "end_state": ["警察乙喊完别跑"],
            "environment": "深夜巷道，回声杂乱",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH005",
            "duration_seconds": 3,
            "shot_size": "中景",
            "angle": "平视",
            "position": "货架侧前方",
            "composition": "逃犯撞翻货架，水果滚落一地",
            "movement": "手持横移后固定",
            "logic": "从货架侧前方朝逃犯观察，保持警察甲逃犯轴线同侧",
            "start_frame": "逃犯冲向货架",
            "end_frame": "水果滚落一地",
            "motivation": "捕捉障碍物被撞翻的失控瞬间。",
            "visible_behavior": "逃犯撞翻货架，水果滚落一地",
            "addressee": "警察甲",
            "visible_characters": ["逃犯"],
            "blocking_actions": {"逃犯": "逃犯撞翻货架，水果滚落一地"},
            "end_state": ["水果滚落一地"],
            "environment": "巷口小摊，水果散落",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH006",
            "duration_seconds": 3,
            "shot_size": "中近景→近景",
            "angle": "平视",
            "position": "逃犯身后近处",
            "composition": "警察甲扑上前，按住逃犯肩膀",
            "movement": "手持跟随后固定",
            "logic": "从逃犯身后朝警察甲观察，保持警察甲逃犯轴线同侧",
            "start_frame": "警察甲扑上前",
            "end_frame": "警察甲说完你跑不掉了",
            "motivation": "记录制服逃犯的决定性动作。",
            "visible_behavior": "警察甲扑上前，按住逃犯肩膀",
            "addressee": "逃犯",
            "visible_characters": ["警察甲", "逃犯"],
            "blocking_actions": {
                "警察甲": "警察甲扑上前，按住逃犯肩膀",
                "逃犯": "逃犯被按住",
            },
            "end_state": ["警察甲按住逃犯肩膀"],
            "environment": "巷道地面湿滑",
            "transition_type": "gaze_cut",
        },
        {
            "shot_id": "SH007",
            "duration_seconds": 3,
            "shot_size": "近景",
            "angle": "微俯视",
            "position": "逃犯面前略高处",
            "composition": "逃犯喘息着抬头，面部为主位",
            "movement": "固定",
            "logic": "从略高处向下观察逃犯面部",
            "start_frame": "逃犯喘息抬头",
            "end_frame": "逃犯说完我认了",
            "motivation": "以俯视角度呈现逃犯最终的认输。",
            "visible_behavior": "逃犯喘息着抬头，眼神涣散",
            "addressee": "警察甲",
            "visible_characters": ["逃犯"],
            "blocking_actions": {"逃犯": "逃犯喘息着抬头"},
            "end_state": ["逃犯说完我认了"],
            "environment": "深夜巷道，远处警笛",
            "transition_type": "scene_end",
        },
    ]

    return make_draft(
        project_id="P-FIXTURE-253",
        delivery_slug="chase-scene",
        locked_text=locked_text,
        source_boundary="从三人形成追逐三角到逃犯说完我认了。",
        narrative_function="通过巷道追逐展示逃犯惊慌、警察合围与最终认命的过程。",
        dramatic_progression="逃犯冲出拐角，警察甲追击，逃犯翻墙，警察乙包抄，逃犯撞翻货架，警察甲制服逃犯，逃犯认罪。",
        character_relations=[
            "逃犯处于被动逃窜状态",
            "警察甲正面追击并喊停",
            "警察乙从侧面包抄合围",
        ],
        source_constraints=["逐字保留四句对白", "逃犯最终被制服并认罪"],
        director_profile=profile,
        style_options=style_options,
        scene=scene,
        beat_groups=[
            [facts[0], facts[1]],
            [facts[2], facts[3]],
            [facts[4]],
            [facts[5], facts[6]],
            [facts[7]],
            [facts[8], facts[9]],
            [facts[10], facts[11]],
        ],
        camera_configs=camera_configs,
    )


def positive_253_fixture() -> dict:
    """Return the primary v2.5.3 positive validation draft.

    This reuses the dinner-party fixture as a fully validated complex Chinese
    scene; the three per-scene fixtures remain available as separate examples.
    """
    draft = dinner_party_fixture()
    draft["project_id"] = "P-POSITIVE-253"
    draft["source"]["delivery_slug"] = "positive-253"
    draft["source_analysis"]["source_boundary"] = "v2.5.3 正例：饭局场景完整交付。"
    # Confirm gates before final hashing so digests are included in content_hash.
    for gate in ("gate_1", "gate_2"):
        draft["confirmations"][gate]["status"] = "confirmed"
        draft["confirmations"][gate]["notes"] = "fixture 自动确认"
    draft = test_helpers.refresh_confirmation_digests(draft)
    # Re-finalize hashes because project/delivery metadata changed.
    draft = delivery.prepare_data(draft)
    return draft


if __name__ == "__main__":
    fixtures = [
        ("dinner-party-scene-draft.json", dinner_party_fixture),
        ("courtroom-scene-draft.json", courtroom_fixture),
        ("chase-scene-draft.json", chase_fixture),
        ("shot-data-253-positive-draft.json", positive_253_fixture),
    ]
    for filename, factory in fixtures:
        draft = factory()
        result = delivery.validate_data(draft)
        if result.errors:
            print(f"{filename} errors:", [(i.code, i.path, i.message) for i in result.errors])
        if result.warnings:
            print(f"{filename} warnings:", [(i.code, i.path) for i in result.warnings])
        if result.status == "PASS":
            print(f"{filename}: PASS")
        out = Path(__file__).parent / filename
        out.write_bytes(delivery.json_bytes(draft))
        print("wrote", out)
