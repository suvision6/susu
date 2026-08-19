#!/usr/bin/env python3
"""Regression tests for su-fenjingskill 2.5.5 and shot-data/2.5.3."""

from __future__ import annotations

import argparse
import copy
import io
import importlib.util
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


sys.dont_write_bytecode = True
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import contract_schema
import language_contract
import scene_workspace

EP15_FAILURE_FIXTURE = SCRIPT_DIR / "fixtures" / "ep15-v251-failure-cases.json"
# Historical filename compatibility sample: the file name is evidence of its
# origin, while its contents are the current contract's minimal positive case.
HISTORICALLY_NAMED_MINIMAL_POSITIVE_FIXTURE = (
    SCRIPT_DIR / "fixtures" / "shot-data-252-positive-draft.json"
)
SKILL_ROOT = SCRIPT_DIR.parent
MODULE_PATH = SCRIPT_DIR / "storyboard_delivery.py"
SPEC = importlib.util.spec_from_file_location("su_fenjingskill_storyboard_delivery", MODULE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("Unable to load storyboard_delivery.py")
delivery = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = delivery
SPEC.loader.exec_module(delivery)


SOURCE_TEXT = (
    "林站在门口，周坐在桌边。\n"
    "林：你听见了吗？\n"
    "周抬眼，握紧钥匙：听见了。\n"
)


def source_span(fragment: str) -> dict[str, object]:
    start = SOURCE_TEXT.index(fragment)
    return {"start": start, "end": start + len(fragment)}


def director_analysis(dramatic_turn: str | None = None) -> dict[str, str | None]:
    return {
        "narrative_function": "建立并延长两人的试探。",
        "dramatic_turn": dramatic_turn,
        "pov_owner": "跟随周的观察位置。",
        "power_relation": None,
        "subtext": "双方都不愿先点破声音来源。",
        "directorial_intent": "让观众先注意沉默里的权力拉扯。",
    }


def selected_profile() -> dict:
    return {
        "rhythm": "restrained",
        "camera_energy": "responsive",
        "visual_distance": "intimate",
        "performance_focus": "face",
        "space_strategy": "embedded_reveal",
        "transition_language": ["gaze_cut", "long_hold", "action_cut"],
        "priorities": ["保留问话后的停顿", "让空间在人物关系中显露"],
        "natural_language_intent": "摄影机克制靠近人物，不抢表演。",
    }


def alternative_profile() -> dict:
    return {
        "rhythm": "balanced",
        "camera_energy": "static",
        "visual_distance": "observational",
        "performance_focus": "body",
        "space_strategy": "establish_then_enter",
        "transition_language": ["hard_cut"],
        "priorities": ["先建立人物空间关系", "让动作承担节奏变化"],
        "natural_language_intent": "保持观察距离，以完整身体动作建立空间。",
    }


def counterpoint_profile() -> dict:
    return {
        "rhythm": "kinetic",
        "camera_energy": "assertive",
        "visual_distance": "mixed",
        "performance_focus": "blocking",
        "space_strategy": "subjective",
        "transition_language": ["sound_bridge", "action_cut"],
        "priorities": ["让声源牵引观看位置", "用人物走位重组空间压力"],
        "natural_language_intent": "让摄影机被未知声源牵引，以空间变化放大试探。",
    }


def style_rationale(
    *,
    fit: str,
    time_edit: str,
    camera: str,
    space: str,
    performance: str,
    benefit: str,
    risk: str,
) -> str:
    return "\n".join(
        (
            f"适配依据：{fit}",
            f"时间与剪辑：{time_edit}",
            f"摄影机：{camera}",
            f"空间与调度：{space}",
            f"表演与观看：{performance}",
            f"主要收益：{benefit}",
            f"主要风险：{risk}",
        )
    )


def refresh_confirmation_digests(draft: dict) -> dict:
    delivery.derive_edit_points(draft)

    draft["confirmations"]["gate_1"]["stage_digest"] = delivery.stage_digest(draft, 1)
    draft["confirmations"]["gate_2"]["stage_digest"] = delivery.stage_digest(draft, 2)
    return draft


def sync_transitions_to_plan(draft: dict) -> None:
    edit_ids = {
        (item["after_plan_unit_id"], item["before_plan_unit_id"]): item[
            "edit_point_id"
        ]
        for item in draft["shot_plan"]["edit_points"]
    }
    for index, shot in enumerate(draft.get("shots", [])):
        next_shot = (
            draft["shots"][index + 1]
            if index + 1 < len(draft.get("shots", []))
            else None
        )
        if next_shot is None or next_shot.get("scene_id") != shot.get("scene_id"):
            shot["transition_to_next"]["type"] = "scene_end"
            shot["transition_to_next"]["edit_point_id"] = None
        else:
            shot["transition_to_next"]["edit_point_id"] = edit_ids.get(
                (shot.get("plan_unit_id"), next_shot.get("plan_unit_id"))
            )


def refresh_plan_metrics(draft: dict) -> dict:
    plan = draft["shot_plan"]
    units = plan["planned_units"]
    edit_points = plan["edit_points"]
    durations = [unit["estimated_duration_seconds"] for unit in units]
    total = sum(durations)
    count = len(units)
    plan.update(
        {
            "planned_shot_count": count,
            "planned_edit_point_count": len(edit_points),
            "planned_total_duration_seconds": total,
        }
    )
    return draft


def merge_dialogue_turns_for_gate_2(
    draft: dict,
    *,
    mode: str,
    non_cut_basis: str | None,
    reframe_method: str | None = None,
) -> dict:
    plan = draft["shot_plan"]
    left, right = plan["planned_units"][:2]
    left["beat_ids"] = ["B001", "B002"]
    left["screen_event_ids"] = ["SEV001", "SEV002", "SEV003", "SEV004"]
    left["source_spans"] = (
        copy.deepcopy(draft["screen_events"][0]["source_spans"])
        + copy.deepcopy(draft["screen_events"][1]["source_spans"])
    )
    left["estimated_duration_seconds"] = 5
    left["dialogue_design"] = {
        "mode": "hold_on_listener",
        "speaker_sequence": ["林", "周"],
        "face_readable_speakers": ["林", "周"],
        "listener_reaction_characters": ["周"],
        "axis_id": "AX001",
        "justification": "发言权交接仍留在周的倾听反应，并保持既定轴线和视线方向。",
    }
    plan["planned_units"] = [left]
    decision = plan["viewing_decisions"][1]
    decision["mode"] = mode
    decision["non_cut_basis"] = non_cut_basis
    decision["reframe_method"] = reframe_method
    delivery.derive_edit_points(draft)
    refresh_plan_metrics(draft)
    return draft


def visual_audit_fixture(
    angles: list[str],
    *,
    scene_ids: list[str] | None = None,
    movement_classes: list[str] | None = None,
) -> tuple[dict, dict[str, dict]]:
    if scene_ids is None:
        scene_ids = ["SC001"] * len(angles)
    if movement_classes is None:
        movement_classes = [
            "fixed" if index % 2 == 0 else "push"
            for index in range(len(angles))
        ]
    unique_scene_ids = list(dict.fromkeys(scene_ids))
    scenes = {
        scene_id: {
            "scene_id": scene_id,
            "directing_plan": {
                "style_anchors": [
                    {
                        "style_anchor_id": f"SA{index + 1:03d}",
                    }
                ]
            },
        }
        for index, scene_id in enumerate(unique_scene_ids)
    }
    data = {
        "shot_plan": {
            "planned_units": [
                {
                    "scene_id": scene_id,
                    "visual_plan": {
                        "angle": angle,
                        "shot_size": "中景",
                        "movement_plan": {"class": movement_class},
                    },
                }
                for angle, scene_id, movement_class in zip(
                    angles,
                    scene_ids,
                    movement_classes,
                )
            ],
            "visual_uniformity_reviews": [],
        }
    }
    return data, scenes


def valid_draft() -> dict:
    line_one = "林站在门口，周坐在桌边。"
    line_two = "林：你听见了吗？"
    line_three = "周抬眼，握紧钥匙：听见了。"
    draft = {
        "contract_name": "shot-data",
        "contract_version": "2.5.3",
        "source_skill": "su-fenjingskill",
        "source_skill_version": "2.5.5",
        "project_id": "PROJECT-001",
        "content_hash": "",
        "confirmations": {
            "gate_1": {
                "status": "confirmed",
                "stage_digest": "",
                "confirmation_order": 1,
                "notes": "已查看源分析并明确选择克制观察风格。",
            },
            "gate_2": {
                "status": "confirmed",
                "stage_digest": "",
                "confirmation_order": 2,
                "notes": "已确认两单元、一剪辑点的拆镜规划。",
            },
        },
        "source": {
            "input_kind": "continuous_text",
            "boundary_lock": "entire_submitted_text",
            "scope": "用户明确提交并锁定的未编号连续场景片段",
            "delivery_slug": "lin-zhou-shiting",
            "locked_text": SOURCE_TEXT,
            "locked_text_hash": "",
            "approved_corrections": [],
        },
        "source_analysis": {
            "source_boundary": "从林、周站位开始，到周明确回应结束。",
            "narrative_function": "建立两人围绕未知声源的试探关系。",
            "dramatic_progression": "问话施压，周以动作和短答承认听见。",
            "character_relations": ["林主动发问，周控制回应时机"],
            "source_constraints": ["逐字保留两句对白", "钥匙由松握变为紧握"],
        },
        "director_style_options": [
            {
                "option_id": "STYLE-01",
                "label": "行为控制下的心理压迫（参考大卫·芬奇）",
                "rationale": style_rationale(
                    fit="两人的试探由可见行为和信息控制推进。",
                    time_edit="保留问句后的停顿，在周抬眼时转移观看权。",
                    camera="克制响应动作，不用运动替代压力。",
                    space="在门口与桌边的距离中显露控制关系。",
                    performance="贴近周抬眼和握钥匙的微小行为。",
                    benefit="让心理压力落到可见证据。",
                    risk="过度冷控可能削弱未知声源的不安。",
                ),
                "profile": selected_profile(),
            },
            {
                "option_id": "STYLE-02",
                "label": "家庭日常中的反应余波（参考是枝裕和）",
                "rationale": style_rationale(
                    fit="日常空间和迟到反应可以承载关系。",
                    time_edit="让完整身体动作自然决定停留与切点。",
                    camera="保持观察距离，少于演员主动。",
                    space="先建立门口与桌边的共同空间。",
                    performance="观看倾听、抬眼和握紧后的余波。",
                    benefit="保留关系的生活质感。",
                    risk="可能减弱来源里的悬疑压力。",
                ),
                "profile": alternative_profile(),
            },
            {
                "option_id": "STYLE-03",
                "label": "日常裂缝中的梦境恐惧（参考大卫·林奇）",
                "rationale": style_rationale(
                    fit="未知声源可让普通室内逐渐失去安全感。",
                    time_edit="延迟解释，用停顿和声音维持不适。",
                    camera="允许被声源牵引的缓慢、主观响应。",
                    space="让门口、桌边与画外声源形成断裂。",
                    performance="观看周的迟疑和身体紧缩。",
                    benefit="放大无法解释的恐惧。",
                    risk="若过度神秘化会损害事件清楚度。",
                ),
                "profile": counterpoint_profile(),
            },
        ],
        "selected_style_option_id": "STYLE-01",
        "director_profile": selected_profile(),
        "shot_plan": {
            "planned_shot_count": 2,
            "planned_edit_point_count": 1,
            "planned_total_duration_seconds": 5,
            "planned_units": [
                {
                    "plan_unit_id": "PU001",
                    "plan_order": 1,
                    "scene_id": "SC001",
                    "beat_ids": ["B001"],
                    "source_spans": [source_span(line_one), source_span(line_two)],
                    "estimated_duration_seconds": 3,
                    "narrative_purpose": "建立站位并让林的问句形成压力。",
                },
                {
                    "plan_unit_id": "PU002",
                    "plan_order": 2,
                    "scene_id": "SC001",
                    "beat_ids": ["B002"],
                    "source_spans": [source_span(line_three)],
                    "estimated_duration_seconds": 2,
                    "narrative_purpose": "保留周抬眼、握紧钥匙与回应的连续过程。",
                },
            ],
            "edit_points": [
                {
                    "edit_point_id": "EP001",
                    "after_plan_unit_id": "PU001",
                    "before_plan_unit_id": "PU002",
                    "source_spans": [
                        source_span("你听见了吗？"),
                        source_span("周抬眼，握紧钥匙"),
                    ],
                    "trigger": "周抬眼并握紧钥匙，回应权由林转向周。",
                    "editorial_gain": "把问句形成的压力与周的连续回应分到两个明确观察位置。",
                }
            ],
            "reorders": [],
        },
        "scenes": [
            {
                "scene_id": "SC001",
                "scene": "未编号连续片段（内部 SC001）",
                "reality_layer": "现实",
                "axes": [
                    {
                        "axis_id": "AX001",
                        "axis_type": "eyeline",
                        "endpoint_a": "林",
                        "endpoint_b": "周",
                    }
                ],
                "initial_continuity": {
                    "characters": [
                        {
                            "name": "林",
                            "position": "门口",
                            "facing": "桌边",
                            "eyeline": "周",
                            "presence": "onscreen",
                            "state": "试探",
                        },
                        {
                            "name": "周",
                            "position": "桌边",
                            "facing": "门口",
                            "eyeline": "林",
                            "presence": "onscreen",
                            "state": "警觉",
                        },
                    ],
                    "props": [
                        {
                            "name": "钥匙",
                            "position": "周右手",
                            "owner": "周",
                            "state": "松握",
                        }
                    ],
                    "fixed_objects": [{"name": "桌", "position": "房间中央", "state": "完好"}],
                    "sound_sources": [],
                    "reality_layer": "现实",
                },
                "inherits_from": None,
                "inherited_states": [],
            }
        ],
        "beats": [
            {
                "beat_id": "B001",
                "beat_order": 1,
                "scene_id": "SC001",
                "source_spans": [source_span(line_one), source_span(line_two)],
                "dramatic_change": "试探在稳定压力中推进。",
                "facts": [
                    {
                        "fact_id": "F001",
                        "type": "position",
                        "text": line_one,
                        "source_spans": [source_span(line_one)],
                        "performers": ["林", "周"],
                    },
                    {
                        "fact_id": "F002",
                        "type": "dialogue",
                        "text": "你听见了吗？",
                        "speaker": "林",
                        "delivery": "onscreen",
                        "source_spans": [source_span("你听见了吗？")],
                        "performers": ["林"],
                    },
                ],
            },
            {
                "beat_id": "B002",
                "beat_order": 2,
                "scene_id": "SC001",
                "source_spans": [source_span(line_three)],
                "dramatic_change": "周从既有警觉进入明确回应。",
                "facts": [
                    {
                        "fact_id": "F003",
                        "type": "action",
                        "text": "周抬眼，握紧钥匙",
                        "source_spans": [source_span("周抬眼，握紧钥匙")],
                        "performers": ["周"],
                    },
                    {
                        "fact_id": "F004",
                        "type": "dialogue",
                        "text": "听见了。",
                        "speaker": "周",
                        "delivery": "onscreen",
                        "source_spans": [source_span("听见了。")],
                        "performers": ["周"],
                    },
                ],
            },
        ],
        "emotion_arcs": [
            {
                "emotion_arc_id": "EA001",
                "character": "周",
                "baseline": "警觉但克制。",
                "trigger_fact_ids": ["F002"],
                "phases": [
                    {
                        "phase": "steady",
                        "beat_ids": ["B001"],
                        "intent": "维持警觉，不先暴露判断。",
                        "visible_direction": ["视线停在林身上", "呼吸保持浅而稳"],
                    },
                    {
                        "phase": "existing_transition",
                        "beat_ids": ["B002"],
                        "intent": "从警觉转为承认自己已经听见。",
                        "visible_direction": ["手指收紧钥匙", "抬眼后才回应"],
                    },
                ],
            }
        ],
        "performance_chains": [
            {
                "chain_id": "PC001",
                "scene_id": "SC001",
                "character": "周",
                "steps": [
                    {"role": "action", "fact_ids": ["F003"]},
                    {"role": "dialogue", "fact_ids": ["F004"]},
                ],
            }
        ],
        "shots": [
            {
                "shot_id": "SH001",
                "shot_order": 1,
                "plan_unit_id": "PU001",
                "scene_id": "SC001",
                "beat_ids": ["B001"],
                "source_spans": [source_span(line_one), source_span(line_two)],
                "covered_fact_ids": ["F001", "F002"],
                "coverage_evidence": [
                    {
                        "fact_id": "F001",
                        "target_path": "camera.start_frame",
                        "evidence_quote": "林站在门口，周坐在桌边",
                    },
                    {
                        "fact_id": "F002",
                        "target_path": "dialogue[0].text",
                        "evidence_quote": "你听见了吗？",
                    },
                ],
                "primary_fact_id": "F002",
                "duration_seconds": 3,
                "duration_blocks": [
                    {
                        "block_id": "TB01",
                        "label": "站位与问话并行",
                        "action_seconds": 2,
                        "dialogue_seconds": 3,
                        "performance_seconds": 2,
                        "camera_seconds": 2,
                    }
                ],
                "cut_design": {
                    "entry_trigger": "从门口关系开始。",
                    "exit_trigger": "问题落下，保留周的反应入口。",
                    "isolation_intent": "none",
                },
                "camera": {
                    "shot_size": "中近景",
                    "angle": "平视",
                    "position": "林肩后，保持林周视线轴同侧",
                    "composition": "林在前景左侧，周在背景右侧",
                    "movement": "缓慢推进后停住",
                    "start_frame": "林站在门口，周坐在桌边",
                    "end_frame": "周的目光停在林身上",
                },
                "blocking": [
                    {
                        "character": "林",
                        "start_position": "门口",
                        "action": "站定并向周发问",
                        "end_position": "门口",
                        "facing": "桌边",
                        "eyeline": "周",
                    },
                    {
                        "character": "周",
                        "start_position": "桌边",
                        "action": "保持坐姿听问",
                        "end_position": "桌边",
                        "facing": "门口",
                        "eyeline": "林",
                    },
                ],
                "performance": {
                    "emotion_arc_id": "EA001",
                    "phase": "steady",
                    "emotion_intent": "周维持警觉，不先暴露判断。",
                    "visible_behavior": ["周的视线停在林身上", "呼吸保持浅而稳"],
                },
                "dialogue": [
                    {
                        "fact_id": "F002",
                        "speaker": "林",
                        "text": "你听见了吗？",
                        "delivery": "onscreen",
                        "timing": "TB01",
                        "addressee": "周",
                    }
                ],
                "visible_characters": ["林", "周"],
                "visible_props": [],
                "environment_behavior": [],
                "continuity": {
                    "axis_id": "AX001",
                    "axis_side": "side_a",
                    "eyelines": [
                        {"character": "林", "target": "周", "direction": "screen_right"},
                        {"character": "周", "target": "林", "direction": "screen_left"},
                    ],
                    "screen_directions": [
                        {"entity": "林", "kind": "eyeline", "direction": "screen_right"},
                        {"entity": "周", "kind": "eyeline", "direction": "screen_left"},
                    ],
                    "action_match": {"incoming": None, "outgoing": None},
                    "intentional_exceptions": [],
                },
                "continuity_updates": [],
                "end_state": ["林仍在门口", "周仍坐在桌边并注视林"],
                "transition_to_next": {
                    "type": "gaze_cut",
                    "edit_point_id": "EP001",
                    "notes": "沿周的目光进入回应。",
                },
                "rendered_shot_description": "",
                "notes": "首镜有意贴近关系，不补全景。",
            },
            {
                "shot_id": "SH002",
                "shot_order": 2,
                "plan_unit_id": "PU002",
                "scene_id": "SC001",
                "beat_ids": ["B002"],
                "source_spans": [source_span(line_three)],
                "covered_fact_ids": ["F003", "F004"],
                "coverage_evidence": [
                    {
                        "fact_id": "F003",
                        "target_path": "blocking[0].action",
                        "evidence_quote": "握紧钥匙",
                    },
                    {
                        "fact_id": "F004",
                        "target_path": "dialogue[0].text",
                        "evidence_quote": "听见了。",
                    },
                ],
                "primary_fact_id": "F003",
                "duration_seconds": 2,
                "duration_blocks": [
                    {
                        "block_id": "TB01",
                        "label": "抬眼、握紧与回应并行",
                        "action_seconds": 2,
                        "dialogue_seconds": 2,
                        "performance_seconds": 2,
                        "camera_seconds": 1,
                    }
                ],
                "cut_design": {
                    "entry_trigger": "承接周的目光。",
                    "exit_trigger": "回应结束并停在紧握钥匙的新状态。",
                    "isolation_intent": "none",
                },
                "camera": {
                    "shot_size": "近景",
                    "angle": "平视",
                    "position": "周正侧，保持林周视线轴同侧",
                    "composition": "周的脸与握钥匙的右手同处画面",
                    "movement": "缓慢拉出后停住",
                    "start_frame": "周保持坐姿，目光仍对着林",
                    "end_frame": "周的右手紧握钥匙，脸和手同框",
                },
                "blocking": [
                    {
                        "character": "周",
                        "start_position": "桌边",
                        "action": "抬眼并握紧钥匙后回应",
                        "end_position": "桌边",
                        "facing": "门口",
                        "eyeline": "林",
                    }
                ],
                "performance": {
                    "emotion_arc_id": "EA001",
                    "phase": "existing_transition",
                    "emotion_intent": "周从警觉转为承认自己已经听见。",
                    "visible_behavior": ["周抬眼后手指收紧钥匙", "回应前短暂停住呼吸"],
                },
                "dialogue": [
                    {
                        "fact_id": "F004",
                        "speaker": "周",
                        "text": "听见了。",
                        "delivery": "onscreen",
                        "timing": "TB01",
                        "addressee": "林",
                    }
                ],
                "visible_characters": ["周"],
                "visible_props": ["钥匙"],
                "environment_behavior": [],
                "continuity": {
                    "axis_id": "AX001",
                    "axis_side": "side_a",
                    "eyelines": [{"character": "周", "target": "林", "direction": "screen_left"}],
                    "screen_directions": [
                        {"entity": "周", "kind": "eyeline", "direction": "screen_left"}
                    ],
                    "action_match": {"incoming": None, "outgoing": None},
                    "intentional_exceptions": [],
                },
                "continuity_updates": [
                    {
                        "entity_type": "prop",
                        "entity": "钥匙",
                        "field": "state",
                        "from": "松握",
                        "to": "紧握",
                        "evidence_fact_ids": ["F003"],
                    }
                ],
                "end_state": ["周仍坐在桌边", "钥匙由松握变为紧握"],
                "transition_to_next": {
                    "type": "scene_end",
                    "edit_point_id": None,
                    "notes": "停在回应后的新状态。",
                },
                "rendered_shot_description": "",
                "notes": "推进后接拉出有明确构图目的，不视为自动错误。",
            },
        ],
    }
    return refresh_confirmation_digests(upgrade_draft_v240(draft))


def upgrade_draft_v240(draft: dict) -> dict:
    """Normalize legacy fixture prose into the director-and-DOP 2.5.3 contract."""
    draft["contract_version"] = "2.5.3"
    draft["source_skill_version"] = "2.5.5"
    scenes = {scene["scene_id"]: scene for scene in draft.get("scenes", [])}
    for scene_index, scene in enumerate(scenes.values(), start=1):
        scene.setdefault(
            "directing_plan",
            {
                "entry_state": "承接本场开端已经成立的人物、空间与关系状态。",
                "entry_strategy": {
                    "mode": "character_entry",
                    "observer_position": "周右肩后，先贴近林的问话与周的受压关系",
                    "required_spatial_information": ["林在门口，周在桌边"],
                    "withheld_information": [],
                    "reason": "先贴近问话关系，同时由过肩位置保留两人的空间联系",
                },
                "scene_objective": "让本场核心行动和信息变化形成完整、连续的导演过程。",
                "progression": ["建立关系与空间", "推动行动或对白", "停在新的可见状态"],
                "exit_state": "人物、道具与信息停在可供下一场继承的明确状态。",
                "pov_flow": ["先建立主要观察位置", "只在发言权或视觉转折真实改变时转移"],
                "dialogue_geometry": "对白按说话权和面孔可读性规划；共享构图必须同时容纳发言者。",
                "rhythm_curve": ["进入", "推进", "停顿或收束"],
                "protected_processes": ["同一人物连续动作、反应与台词不作机械切分"],
                "visual_turns": ["以来源中的动作、信息或关系变化作为视觉转折"],
            },
        )
        profile_priorities = draft.get("director_profile", {}).get("priorities", [])
        basis_value = (
            profile_priorities[0]
            if profile_priorities
            else draft.get("director_profile", {}).get(
                "natural_language_intent",
                "按已确认导演意图组织观看",
            )
        )
        basis_field = "priorities" if profile_priorities else "natural_language_intent"
        scene["directing_plan"].setdefault(
            "style_anchors",
            [
                {
                    "style_anchor_id": f"SA{scene_index:03d}",
                    "profile_basis": [
                        {
                            "field": basis_field,
                            "value": basis_value,
                        }
                    ],
                    "scene_application": "让观察位置随本场关系与信息变化，而不是按模板轮换镜头。",
                    "avoidance": "避免把风格简化为全场固定、平视或同一景别。",
                }
            ],
        )
    beats = {beat["beat_id"]: beat for beat in draft.get("beats", [])}
    locked_text = draft.get("source", {}).get("locked_text", "")
    for unit in draft.get("shot_plan", {}).get("planned_units", []):
        dialogue_facts = delivery.dialogue_facts_for_plan_unit(unit, beats, locked_text)
        if not dialogue_facts:
            unit["dialogue_design"] = None
            continue
        sequence: list[str] = []
        for fact in dialogue_facts:
            speaker = fact["speaker"]
            if not sequence or sequence[-1] != speaker:
                sequence.append(speaker)
        unique_speakers = list(dict.fromkeys(sequence))
        if len(unique_speakers) == 1:
            mode = "single_speaker"
        elif len(unique_speakers) == 2:
            mode = "shared_two_shot"
        else:
            mode = "shared_multi_shot"
        scene = scenes[unit["scene_id"]]
        scene_characters = [
            item["name"]
            for item in scene["initial_continuity"]["characters"]
            if isinstance(item, dict)
        ]
        unit["dialogue_design"] = {
            "mode": mode,
            "speaker_sequence": sequence,
            "face_readable_speakers": unique_speakers,
            "listener_reaction_characters": [
                name for name in scene_characters if name not in unique_speakers
            ],
            "axis_id": scene["axes"][0]["axis_id"] if scene.get("axes") else None,
            "justification": "按本单元真实说话权安排可读面孔，并保持既定轴线。",
        }
    units = {
        unit["plan_unit_id"]: unit
        for unit in draft.get("shot_plan", {}).get("planned_units", [])
    }
    fact_lookup = {
        fact["fact_id"]: fact
        for beat in draft.get("beats", [])
        for fact in beat.get("facts", [])
    }
    for shot in draft.get("shots", []):
        unit = units.get(shot.get("plan_unit_id"), {})
        design = unit.get("dialogue_design")
        camera = shot["camera"]
        dialogue = shot.get("dialogue", [])
        speakers = list(
            dict.fromkeys(
                item["speaker"]
                for item in dialogue
                if item.get("delivery", item.get("shot_delivery")) == "onscreen"
            )
        )
        scene_characters = [
            item["name"]
            for item in scenes[shot["scene_id"]]["initial_continuity"]["characters"]
            if isinstance(item, dict)
        ]
        mode = design.get("mode") if isinstance(design, dict) else None
        if mode == "single_speaker":
            visible = set(shot.get("visible_characters", []))
            camera["framing_mode"] = (
                "over_shoulder"
                if len(scene_characters) >= 2 and set(scene_characters).issubset(visible)
                else "single"
            )
            camera["primary_subjects"] = speakers
            camera["foreground_characters"] = (
                [name for name in scene_characters if name not in speakers][:1]
                if camera["framing_mode"] == "over_shoulder"
                else []
            )
        elif mode == "shared_two_shot":
            camera["framing_mode"] = "two_shot"
            camera["primary_subjects"] = speakers
            camera["foreground_characters"] = []
        elif mode == "shared_multi_shot":
            camera["framing_mode"] = "multi_shot"
            camera["primary_subjects"] = speakers
            camera["foreground_characters"] = []
        else:
            camera["framing_mode"] = "single"
            camera["primary_subjects"] = shot.get("visible_characters", [])[:1]
            camera["foreground_characters"] = []
        if shot["shot_id"] == "SH001":
            camera["position"] = "周右肩后"
            camera["composition"] = "周肩背在前景，林正脸为主位"
            camera["movement"] = "缓慢推进后固定"
            camera["end_frame"] = "林问话结束，周肩背仍在前景"
            camera["logic"] = "朝向林，保持林周视线轴同侧"
        elif shot["shot_id"] == "SH002":
            camera["position"] = "周正侧近处"
            camera["logic"] = "朝向周，保持林周视线轴同侧"
            camera["movement"] = "缓慢拉出后固定"
        else:
            subjects = "、".join(camera["primary_subjects"]) or "当前空间"
            camera["logic"] = f"朝向{subjects}，保持本场既定观察方向"
        camera["movement"] = camera["movement"].replace("后停住", "后固定")
        shot["speaker_presentation"] = [
            {
                "fact_id": item["fact_id"],
                "speaker": item["speaker"],
                "presentation": (
                    "primary_face"
                    if item.get("delivery", item.get("shot_delivery")) == "onscreen"
                    else (
                        "vo"
                        if item.get("delivery", item.get("shot_delivery")) == "vo"
                        else "offscreen"
                    )
                ),
            }
            for item in dialogue
        ]
        fact_ids = list(shot.get("covered_fact_ids", []))
        evidence_quotes = [
            item.get("evidence_quote", "")
            for item in shot.get("coverage_evidence", [])
            if item.get("fact_id") in fact_ids
        ]
        pieces = [quote for quote in evidence_quotes if quote]
        for item in dialogue:
            quoted = f'{item["speaker"]}说：“{item["text"]}”'
            if item["text"] not in "。".join(pieces):
                pieces.append(quoted)
        text = "。".join(piece.rstrip("。") for piece in pieces if piece).rstrip("。") + "。"
        if shot["shot_id"] == "SH001":
            text = "林站在门口，周坐在桌边。林问：“你听见了吗？”"
        elif shot["shot_id"] == "SH002":
            text = "周抬眼，握紧钥匙，对林说：“听见了。”"
        character = None
        performers = [
            name
            for fact_id in fact_ids
            for name in fact_lookup.get(fact_id, {}).get("performers", [])
        ]
        if performers:
            character = performers[0]
        if shot.get("duration_blocks"):
            shot["duration_blocks"][0]["label"] = "同步动作、台词与运镜"
        visible_behavior = "；".join(
            shot.get("performance", {}).get("visible_behavior", [])
        )
        delivery_labels = {
            "onscreen": "现场",
            "os": "画外",
            "vo": "旁白",
            "mediated": "媒介",
        }
        spoken_text = "；".join(
            f'{item["speaker"]}以'
            f'{delivery_labels.get(item.get("delivery", item.get("shot_delivery", "onscreen")), "现场")}'
            f'方式说：{item["text"]}'
            for item in dialogue
        )
        performance_text = "；".join(
            item
            for item in (
                visible_behavior,
                spoken_text,
                "现场声保持在人物动作与停顿之间，不另造剧情信息。",
            )
            if item
        )
        environment_text = "室内环境保持安静，人物之间只保留现场底噪。"
        end_state_text = "；".join(shot.get("end_state", []))
        position = camera["position"]
        logic = camera["logic"]
        camera_text = (
            f"摄影机{logic}；"
            if delivery.normalize_execution_text(position)
            in delivery.normalize_execution_text(logic)
            else f"摄影机位于{position}，{logic}；"
        )
        composition_text = (
            camera["composition"]
            .replace("面部为主位", "面部清晰可读")
            .replace("为主位", "占据画面")
            .replace("主位", "主要位置")
            .replace("次要层", "背景层")
        )
        shot["execution_text"] = (
            f"【画面内容】{environment_text}"
            f"{camera_text}"
            f"{composition_text}。"
            f"{text}{performance_text}"
            f"最后停在{end_state_text}。"
        )
        shot["notes"] = ""
    plan = draft.get("shot_plan", {})
    shots_by_plan_unit = {
        shot.get("plan_unit_id"): shot
        for shot in draft.get("shots", [])
        if isinstance(shot, dict)
    }
    for unit in plan.get("planned_units", []):
        shot = shots_by_plan_unit.get(unit.get("plan_unit_id"), {})
        camera = shot.get("camera", {})
        scene = scenes.get(unit.get("scene_id"), {})
        style_anchor_ids = [
            anchor["style_anchor_id"]
            for anchor in scene.get("directing_plan", {}).get("style_anchors", [])
            if isinstance(anchor, dict) and anchor.get("style_anchor_id")
        ]
        unit["visual_plan"] = {
            "angle": camera.get("angle", "平视"),
            "shot_size": camera.get("shot_size", "中景"),
            "framing_mode": camera.get("framing_mode", "single"),
            "primary_subjects": camera.get("primary_subjects") or ["当前空间"],
            "position": camera.get("position", "场景既定观察位置"),
            "movement_class": delivery.camera_movement_class(
                camera.get("movement", "固定")
            ),
            "motivation_type": "eye_relation",
            "motivation": "让当前人物、空间与观看权的变化在这一观察位置中清楚成立。",
            "style_anchor_ids": style_anchor_ids,
        }
        if camera.get("foreground_characters"):
            unit["visual_plan"]["foreground_characters"] = list(
                camera["foreground_characters"]
            )
    plan.setdefault("visual_uniformity_reviews", [])
    for key in (
        "average_shot_duration_seconds",
        "edit_points_per_minute",
        "standard_shot_count",
        "standard_shot_percentage",
        "long_take_count",
        "long_take_percentage",
        "abstract_edit_point_basis",
    ):
        plan.pop(key, None)
    for unit in plan.get("planned_units", []):
        if unit.get("shot_form") == "standard":
            unit.pop("shot_form", None)
    for edit_point in plan.get("edit_points", []):
        evidence = edit_point.pop("cut_evidence", None)
        legacy_basis = edit_point.pop("basis", None)
        if isinstance(evidence, dict):
            edit_point["trigger"] = evidence.get("trigger_event") or legacy_basis
            edit_point["editorial_gain"] = evidence.get("editorial_gain")
        else:
            edit_point.setdefault("trigger", legacy_basis)
        if not edit_point.get("broken_performance_chain_ids"):
            edit_point.pop("broken_performance_chain_ids", None)
    for scene in draft.get("scenes", []):
        scene.pop("first_shot_anchor_type", None)
    for shot in draft.get("shots", []):
        if shot.get("shot_form") == "standard":
            shot.pop("shot_form", None)
        cut_design = shot.get("cut_design")
        if isinstance(cut_design, dict):
            for key in ("cut_reason", "rhythm_role", "director_choice"):
                cut_design.pop(key, None)
        if shot.get("shot_form") != "long_take":
            shot.pop("director_audit", None)
    for beat in draft.get("beats", []):
        for fact in beat.get("facts", []):
            if fact.get("type") != "dialogue":
                continue
            legacy_delivery = fact.pop("delivery", None)
            fact["script_voice_type"] = {
                "onscreen": "scene_dialogue",
                "offscreen": "os",
                "vo": "vo",
            }.get(legacy_delivery, fact.get("script_voice_type", "scene_dialogue"))
    units_by_id = {
        unit.get("plan_unit_id"): unit
        for unit in draft.get("shot_plan", {}).get("planned_units", [])
        if isinstance(unit, dict)
    }
    shots_by_unit = {
        shot.get("plan_unit_id"): shot
        for shot in draft.get("shots", [])
        if isinstance(shot, dict)
    }
    screen_events = []
    scene_event_orders = {}
    event_ids_by_unit = {}
    unit_id_by_event = {}
    for unit in draft.get("shot_plan", {}).get("planned_units", []):
        scene_id = unit.get("scene_id")
        shot = shots_by_unit.get(unit.get("plan_unit_id"), {})
        covered_fact_ids = list(shot.get("covered_fact_ids", []))
        primary_subjects = list(
            shot.get("camera", {}).get("primary_subjects")
            or shot.get("visible_characters", [])
            or shot.get("visible_props", [])
        )
        event_ids_by_unit[unit.get("plan_unit_id")] = []
        for fact_index, fact_id in enumerate(covered_fact_ids):
            fact = fact_lookup.get(fact_id, {})
            fact_type = fact.get("type")
            scene_event_orders[scene_id] = scene_event_orders.get(scene_id, 0) + 1
            event_id = f"SEV{len(screen_events) + 1:03d}"
            event_ids_by_unit[unit.get("plan_unit_id")].append(event_id)
            unit_id_by_event[event_id] = unit.get("plan_unit_id")
            performers = list(fact.get("performers", []))
            primary_subject = (
                fact.get("speaker")
                if fact_type == "dialogue"
                else performers[0]
                if performers
                else primary_subjects[0]
                if primary_subjects
                else "当前空间"
            )
            event_role = {
                "dialogue": "dialogue_turn",
                "position": "spatial",
                "space": "spatial",
                "prop": "object_detail",
                "emotion": "reaction",
            }.get(fact_type, "action")
            focus_scale = {
                "dialogue": "face",
                "position": "relation",
                "space": "space",
                "prop": "detail",
                "emotion": "face",
            }.get(fact_type, "body")
            screen_events.append(
                {
                    "screen_event_id": event_id,
                    "scene_id": scene_id,
                    "event_order": scene_event_orders[scene_id],
                    "beat_ids": [
                        beat_id
                        for beat_id in unit.get("beat_ids", [])
                        if any(
                            item.get("fact_id") == fact_id
                            for item in beats.get(beat_id, {}).get("facts", [])
                        )
                    ],
                    "source_spans": copy.deepcopy(fact.get("source_spans", [])),
                    "covered_fact_ids": [fact_id],
                    "visual_subjects": [primary_subject],
                    "visual_action": fact.get(
                        "text",
                        unit.get("narrative_purpose", "让当前来源行动清楚发生。"),
                    ),
                    "viewing_requirement": "观众能辨认当前主体、行动及其关系变化。",
                    "scale_requirement": "由当前原子事件的观看尺度决定。",
                    "spatial_zone": scenes.get(
                        scene_id, {}
                    ).get("scene", "当前场景区域"),
                    "temporal_relation": (
                        "sequential"
                        if scene_event_orders[scene_id] == 1 or fact_index == 0
                        else "continuous_from_previous"
                    ),
                    "sound_fact_ids": (
                        [fact_id] if fact_type in {"dialogue", "sound"} else []
                    ),
                    "event_role": event_role,
                    "primary_viewing_subject": primary_subject,
                    "focus_scale": focus_scale,
                }
            )
        unit["screen_event_ids"] = event_ids_by_unit[unit.get("plan_unit_id")]
    draft["screen_events"] = screen_events
    legacy_edits = {
        (
            item.get("after_plan_unit_id"),
            item.get("before_plan_unit_id"),
        ): item
        for item in draft.get("shot_plan", {}).get("edit_points", [])
        if isinstance(item, dict)
    }
    viewing_decisions = []
    ordered_units = [
        unit
        for unit in draft.get("shot_plan", {}).get("planned_units", [])
        if isinstance(unit, dict)
    ]
    ordered_events = [
        event for event in screen_events if isinstance(event, dict)
    ]
    for left_event, right_event in zip(ordered_events, ordered_events[1:]):
        if left_event.get("scene_id") != right_event.get("scene_id"):
            continue
        left_unit_id = unit_id_by_event[left_event["screen_event_id"]]
        right_unit_id = unit_id_by_event[right_event["screen_event_id"]]
        legacy = legacy_edits.get(
            (left_unit_id, right_unit_id),
            {},
        )
        is_cut = left_unit_id != right_unit_id
        scale_changed = left_event["focus_scale"] != right_event["focus_scale"]
        viewing_decisions.append(
            {
                "viewing_decision_id": f"VD{len(viewing_decisions) + 1:03d}",
                "scene_id": left_event.get("scene_id"),
                "from_screen_event_id": left_event["screen_event_id"],
                "to_screen_event_id": right_event["screen_event_id"],
                "mode": "cut" if is_cut else "reframe" if scale_changed else "hold",
                "trigger": legacy.get("trigger", "观看主体与关系重心发生明确变化。"),
                "viewing_change": "观看从前一主体转移到后一主体或新的信息落点。",
                "director_reason": legacy.get(
                    "editorial_gain",
                    "切开让新的观看重心获得独立且清楚的画面位置。",
                ),
                "reframe_method": (
                    None if is_cut else "scale_change" if scale_changed else None
                ),
                "non_cut_basis": (
                    None
                    if is_cut
                    else "continuous_action"
                    if right_event["temporal_relation"] == "continuous_from_previous"
                    else "shared_staging"
                ),
            }
        )
    draft["shot_plan"]["viewing_decisions"] = viewing_decisions
    for unit in ordered_units:
        shot = shots_by_unit.get(unit.get("plan_unit_id"), {})
        camera = shot.get("camera", {})
        camera.setdefault("start_frame", camera.get("composition", "初始主体关系清楚可读。"))
        camera.setdefault("end_frame", shot.get("end_state", ["动作结束"])[-1])
        movement_class = delivery.camera_movement_class(camera.get("movement", "固定"))
        primary_subjects = list(camera.get("primary_subjects") or ["当前主体"])
        secondary_subjects = [
            name
            for name in shot.get("visible_characters", [])
            if name not in primary_subjects
        ]
        old_plan = unit.get("visual_plan", {})
        unit["visual_plan"] = {
            "viewpoint_owner": primary_subjects[0] if primary_subjects else "客观观察",
            "primary_subjects": primary_subjects,
            "secondary_subjects": secondary_subjects,
            "shot_size": camera.get("shot_size", "中景"),
            "angle": camera.get("angle", "平视"),
            "camera_position": camera.get("position", "既定观察位置"),
            "framing_relation": camera.get("composition", "主体关系清楚可读"),
            "perspective_intent": (
                "detail_isolation"
                if "特写" in camera.get("shot_size", "")
                else "wide_spatial"
                if "全景" in camera.get("shot_size", "")
                else "natural_relation"
            ),
            "focus_plan": "焦点保持在当前主要观看主体及其动作上。",
            "spatial_strategy": {"type": "not_applicable", "description": ""},
            "movement_plan": {
                "class": movement_class,
                "trigger": "" if movement_class == "fixed" else "主体动作或观看关系开始变化。",
                "speed": "" if movement_class == "fixed" else "缓慢",
                "path": "" if movement_class == "fixed" else camera.get("movement", "沿观看方向移动"),
                "end_condition": "" if movement_class == "fixed" else camera.get("end_frame"),
                "hold_reason": "保护完整表演与空间关系。" if movement_class == "fixed" else "",
            },
            "start_frame": camera.get("start_frame"),
            "end_frame": camera.get("end_frame"),
            "motivation": old_plan.get(
                "motivation",
                "让当前人物、空间与观看权的变化清楚成立。",
            ),
        }
        if old_plan.get("style_anchor_ids"):
            unit["visual_plan"]["style_anchor_ids"] = list(old_plan["style_anchor_ids"])
        camera.update(
            {
                "viewpoint_owner": unit["visual_plan"]["viewpoint_owner"],
                "primary_subjects": copy.deepcopy(
                    unit["visual_plan"]["primary_subjects"]
                ),
                "secondary_subjects": copy.deepcopy(
                    unit["visual_plan"]["secondary_subjects"]
                ),
                "perspective_intent": unit["visual_plan"][
                    "perspective_intent"
                ],
                "focus_plan": unit["visual_plan"]["focus_plan"],
                "spatial_strategy": copy.deepcopy(
                    unit["visual_plan"]["spatial_strategy"]
                ),
                "movement_plan": copy.deepcopy(
                    unit["visual_plan"]["movement_plan"]
                ),
                "start_frame": unit["visual_plan"]["start_frame"],
                "end_frame": unit["visual_plan"]["end_frame"],
                "motivation": unit["visual_plan"]["motivation"],
            }
        )
        event_ids = event_ids_by_unit[unit.get("plan_unit_id")]
        legacy_blocks = shot.pop("duration_blocks", [])
        for item in shot.get("dialogue", []):
            legacy_delivery = item.pop("delivery", None)
            item["shot_delivery"] = {
                "onscreen": "onscreen",
                "offscreen": "os",
                "vo": "vo",
            }.get(legacy_delivery, item.get("shot_delivery", "onscreen"))
            event_index = next(
                (
                    index
                    for index, event_id in enumerate(event_ids)
                    if item["fact_id"]
                    in next(
                        event["covered_fact_ids"]
                        for event in screen_events
                        if event["screen_event_id"] == event_id
                    )
                ),
                0,
            )
            item["timing"] = (
                f"PH{shot.get('shot_order', 1):03d}-{event_index + 1:02d}"
            )
        shot["speaker_presentation"] = [
            {
                "fact_id": item["fact_id"],
                "speaker": item["speaker"],
                "presentation": (
                    "not_visible"
                    if item["shot_delivery"] in {"os", "vo"}
                    else "primary_face"
                ),
            }
            for item in shot.get("dialogue", [])
        ]
        phase_count = len(event_ids)
        total_duration = shot.get("duration_seconds", phase_count)
        base_duration, remainder = divmod(total_duration, phase_count)
        shot["shot_phases"] = []
        for phase_index, event_id in enumerate(event_ids):
            shot["shot_phases"].append(
                {
                    "phase_id": (
                        f"PH{shot.get('shot_order', 1):03d}-{phase_index + 1:02d}"
                    ),
                    "phase_order": phase_index + 1,
                    "screen_event_ids": [event_id],
                    "duration_seconds": base_duration + (
                        1 if phase_index >= phase_count - remainder else 0
                    ),
                    "camera_state": (
                        f"第{phase_index + 1}阶段从既定画面继续，执行"
                        f"{camera.get('movement')}，并朝{camera.get('end_frame')}收束。"
                    ),
                    "sound_fact_ids": list(
                        next(
                            event["sound_fact_ids"]
                            for event in screen_events
                            if event["screen_event_id"] == event_id
                        )
                    ),
                }
            )
    delivery.derive_edit_points(draft)
    sync_transitions_to_plan(draft)
    return draft


def draft_with_inherited_scene() -> dict:
    draft = valid_draft()
    extra_text = "周走入走廊。\n"
    draft["source"]["locked_text"] += extra_text
    locked_text = draft["source"]["locked_text"]
    fragment = "周走入走廊。"
    start = locked_text.index(fragment)
    span = {"start": start, "end": start + len(fragment)}
    draft["scenes"].append(
        {
            "scene_id": "SC002",
            "scene": "未编号连续片段（内部 SC002）",
            "reality_layer": "现实",
            "axes": [],
            "initial_continuity": {
                "characters": [
                    {
                        "name": "周",
                        "position": "走廊入口",
                        "facing": "走廊深处",
                        "eyeline": "走廊深处",
                        "presence": "onscreen",
                        "state": "警觉",
                    }
                ],
                "props": [
                    {
                        "name": "钥匙",
                        "position": "周右手",
                        "owner": "周",
                        "state": "紧握",
                    }
                ],
                "fixed_objects": [],
                "sound_sources": [],
                "reality_layer": "现实",
            },
            "inherits_from": "SC001",
            "inherited_states": [
                {"entity_type": "prop", "entity": "钥匙", "field": "state"}
            ],
        }
    )
    draft["beats"].append(
        {
            "beat_id": "B003",
            "beat_order": 3,
            "scene_id": "SC002",
            "source_spans": [copy.deepcopy(span)],
            "dramatic_change": "周带着既有状态进入新空间。",
            "facts": [
                {
                    "fact_id": "F005",
                    "type": "action",
                    "text": fragment,
                    "source_spans": [copy.deepcopy(span)],
                    "presentation_requirement": "must_be_clear",
                    "shot_isolation": "not_required",
                    "isolation_reason": "",
                    "performers": ["周"],
                    "isolation_group_id": None,
                }
            ],
        }
    )
    draft["director_profile"]["transition_language"].append("hard_cut")
    draft["director_style_options"][0]["profile"]["transition_language"].append("hard_cut")
    draft["shot_plan"]["planned_shot_count"] = 3
    draft["shot_plan"]["planned_edit_point_count"] = 2
    draft["shot_plan"]["planned_total_duration_seconds"] = 7
    draft["shot_plan"]["planned_units"].append(
        {
            "plan_unit_id": "PU003",
            "plan_order": 3,
            "scene_id": "SC002",
            "beat_ids": ["B003"],
            "source_spans": [copy.deepcopy(span)],
            "estimated_duration_seconds": 2,
            "narrative_purpose": "保持人物与钥匙状态进入走廊。",
        }
    )
    draft["shot_plan"]["edit_points"].append(
        {
            "edit_point_id": "EP002",
            "after_plan_unit_id": "PU002",
            "before_plan_unit_id": "PU003",
            "source_spans": [
                source_span("听见了。"),
                copy.deepcopy(span),
            ],
            "trigger": "周跨出原空间进入走廊。",
            "editorial_gain": "以空间边界完成场景切换，同时保留人物和钥匙状态。",
        }
    )
    draft["shots"][-1]["transition_to_next"] = {
        "type": "cut",
        "edit_point_id": "EP002",
        "notes": "进入走廊。",
    }
    draft["shots"].append(
        {
            "shot_id": "SH003",
            "shot_order": 3,
            "plan_unit_id": "PU003",
            "scene_id": "SC002",
            "beat_ids": ["B003"],
            "source_spans": [copy.deepcopy(span)],
            "covered_fact_ids": ["F005"],
            "coverage_evidence": [
                {
                    "fact_id": "F005",
                    "target_path": "blocking[0].action",
                    "evidence_quote": "走入走廊",
                }
            ],
            "primary_fact_id": "F005",
            "duration_seconds": 2,
            "duration_blocks": [
                {
                    "block_id": "TB01",
                    "label": "进入走廊",
                    "action_seconds": 2,
                    "dialogue_seconds": 0,
                    "performance_seconds": 1,
                    "camera_seconds": 2,
                }
            ],
            "cut_design": {
                "entry_trigger": "周进入新的空间。",
                "exit_trigger": "人物在走廊内站稳。",
                "isolation_intent": "none",
            },
            "camera": {
                "shot_size": "中景",
                "angle": "微仰视",
                "position": "走廊侧墙低位，略向上观察周",
                "composition": "周与走廊纵深同框",
                "movement": "横移跟随后停住",
                "start_frame": "周出现在走廊入口",
                "end_frame": "周站在走廊内，钥匙仍在右手",
            },
            "blocking": [
                {
                    "character": "周",
                    "start_position": "走廊入口",
                    "action": "走入走廊",
                    "end_position": "走廊内",
                    "facing": "走廊深处",
                    "eyeline": "走廊深处",
                }
            ],
            "performance": {
                "emotion_arc_id": None,
                "phase": "not_applicable",
                "emotion_intent": "",
                "visible_behavior": [],
            },
            "dialogue": [],
            "visible_characters": ["周"],
            "visible_props": ["钥匙"],
            "environment_behavior": [],
            "continuity": {
                "axis_id": None,
                "axis_side": "not_applicable",
                "eyelines": [],
                "screen_directions": [
                    {"entity": "周", "kind": "movement", "direction": "screen_right"}
                ],
                "action_match": {"incoming": None, "outgoing": None},
                "intentional_exceptions": [],
            },
            "continuity_updates": [],
            "end_state": ["周站在走廊内", "钥匙仍由周紧握"],
            "transition_to_next": {
                "type": "scene_end",
                "edit_point_id": None,
                "notes": "停在走廊纵深。",
            },
            "rendered_shot_description": "",
            "notes": "",
        }
    )
    return refresh_confirmation_digests(upgrade_draft_v240(draft))


def all_keys(value: object) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            keys.append(key)
            keys.extend(all_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.extend(all_keys(item))
    return keys


def issue_codes(result: object) -> set[str]:
    return {issue.code for issue in result.errors}


class StoryboardDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="su-fenjingskill-test-"
        )
        self.root = Path(self.temporary_directory.name)
        self.output_dir = self.root / "delivery"
        self.draft_path = self.root / "draft.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_draft(self, data: dict) -> None:
        self.draft_path.write_bytes(delivery.json_bytes(data))

    def build(self, data: dict | None = None) -> tuple[dict, dict, dict]:
        draft = valid_draft() if data is None else data
        self.write_draft(draft)
        return delivery.build_delivery(self.draft_path, self.output_dir)

    def prepared(self, data: dict | None = None) -> dict:
        draft = valid_draft() if data is None else data
        refresh_confirmation_digests(draft)
        return delivery.prepare_data(draft)

    def changed_delivery_bundle(self) -> tuple[dict, dict]:
        draft = valid_draft()
        draft["scenes"][0]["scene"] = "同一 slug 的合法更新场景"
        data = self.prepared(draft)
        result = delivery.validate_data(data)
        self.assertFalse(result.errors)
        return data, delivery.make_report(data, result)

    def test_director_catalog_has_exactly_fifteen_normalized_mappings(self) -> None:
        references = SKILL_ROOT / "references"
        router_path = references / "director-style-reference.md"
        router = router_path.read_text(encoding="utf-8")
        rows = re.findall(
            r"^\| [A-O] \| ([^|]+) \| ([^|]+) \| "
            r"\[[^\]]+\]\((director-[^)]+\.md)\) \|",
            router,
            flags=re.MULTILINE,
        )
        self.assertEqual(len(rows), 15)
        strategies = [strategy.strip() for strategy, _, _ in rows]
        self.assertEqual(len(strategies), len(set(strategies)))
        aliases = [
            alias.strip().casefold()
            for _, alias_cell, _ in rows
            for alias in alias_cell.split("/")
        ]
        self.assertEqual(len(aliases), len(set(aliases)))
        mapped_files = [filename for _, _, filename in rows]
        self.assertEqual(len(mapped_files), len(set(mapped_files)))
        required_sections = (
            "## 适用场景",
            "## 时间与剪辑",
            "## 切点逻辑",
            "## 摄影机人格",
            "## 空间构图与调度",
            "## 表演观看",
            "## 主要收益",
            "## 误用风险",
            "## 禁止事项",
            "## Profile 默认建议",
        )
        for filename in mapped_files:
            card = (references / filename)
            self.assertTrue(card.is_file(), filename)
            text = card.read_text(encoding="utf-8")
            for section in required_sections:
                self.assertIn(section, text, f"{filename}: {section}")
            self.assertNotRegex(text, r"(?:评分|score)\s*[:：]?\s*[1-5]", filename)
            self.assertNotRegex(text, r"[1-5]\s*/\s*5", filename)
        integrated_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(references.glob("director-*.md"))
        )
        self.assertNotIn("侯孝贤", integrated_text)
        self.assertIn("所有卡片共同遵守", router)
        self.assertEqual(integrated_text.count("## 典型入口"), 0)
        self.assertEqual(integrated_text.count("## 对白调度偏好"), 0)
        self.assertFalse((references / "director-hou-hsiao-hsien.md").exists())
        self.assertFalse((references / "shot-design-checklist.md").exists())

    def test_director_router_has_stable_three_role_scenario_anchors(self) -> None:
        router = (SKILL_ROOT / "references" / "director-style-reference.md").read_text(
            encoding="utf-8"
        )
        anchors = {
            "倒计时、多线任务与物理因果并行": (
                "物理任务的交叉压力（参考克里斯托弗·诺兰）",
                "镜头内部的冒险发现（参考史蒂文·斯皮尔伯格）",
                "宏大空间中的静默压力（参考丹尼斯·维伦纽瓦）",
            ),
            "精密对话、审讯或心理控制": (
                "行为控制下的心理压迫（参考大卫·芬奇）",
                "制度空间的中心秩序（参考斯坦利·库布里克）",
                "欲望空间的概念切割（参考朴赞郁）",
            ),
            "家庭日常、隐忍反应与生活余波": (
                "家庭日常中的反应余波（参考是枝裕和）",
                "镜头内部的冒险发现（参考史蒂文·斯皮尔伯格）",
                "记忆时间里的亲密错位（参考王家卫）",
            ),
            "梦境、身份裂缝与无法解释的恐惧": (
                "日常裂缝中的梦境恐惧（参考大卫·林奇）",
                "宏大空间中的静默压力（参考丹尼斯·维伦纽瓦）",
                "记忆时间里的亲密错位（参考王家卫）",
            ),
            "冒险、奇观与镜头内部逐步发现": (
                "镜头内部的冒险发现（参考史蒂文·斯皮尔伯格）",
                "物理任务的交叉压力（参考克里斯托弗·诺兰）",
                "类型转向中的社会空间（参考奉俊昊）",
            ),
        }
        for scene_task, candidates in anchors.items():
            self.assertEqual(len(candidates), len(set(candidates)))
            self.assertIn(
                f"| {scene_task} | {candidates[0]} | {candidates[1]} | {candidates[2]} |",
                router,
            )

    def test_gate_1_default_three_candidates_are_valid(self) -> None:
        draft = valid_draft()
        self.assertEqual(
            [option["option_id"] for option in draft["director_style_options"]],
            ["STYLE-01", "STYLE-02", "STYLE-03"],
        )
        self.assertFalse(delivery.validate_data(self.prepared(draft)).errors)

    def test_gate_1_more_selection_expands_to_style_04(self) -> None:
        draft = valid_draft()
        expanded_profile = {
            "rhythm": "balanced",
            "camera_energy": "responsive",
            "visual_distance": "mixed",
            "performance_focus": "ensemble",
            "space_strategy": "mixed",
            "transition_language": ["sound_bridge", "dissolve"],
            "priorities": ["让公共秩序衬出私人孤独", "用群体调度改变观看重心"],
            "natural_language_intent": "以主动巡游建立公共表面，再停在人物的私人空洞上。",
        }
        draft["director_style_options"].append(
            {
                "option_id": "STYLE-04",
                "label": "巴洛克巡游与情绪蒙太奇（参考保罗·索伦蒂诺）",
                "rationale": style_rationale(
                    fit="公共空间与私人沉默可形成反差。",
                    time_edit="在群体节奏与人物停顿之间转换。",
                    camera="主动巡游后稳定凝视。",
                    space="用公共动线重组人物关系。",
                    performance="从群体姿态切入个体停顿。",
                    benefit="显出公共表面下的孤独。",
                    risk="摄影机过强可能压过微小表演。",
                ),
                "profile": expanded_profile,
            }
        )
        draft["selected_style_option_id"] = "STYLE-04"
        draft["director_profile"] = copy.deepcopy(expanded_profile)
        draft["scenes"][0]["directing_plan"]["style_anchors"][0][
            "profile_basis"
        ] = [
            {
                "field": "priorities",
                "value": expanded_profile["priorities"][0],
            }
        ]
        refresh_confirmation_digests(draft)
        self.assertFalse(delivery.validate_data(self.prepared(draft)).errors)

    def test_gate_1_rejects_wrong_count_order_rationale_and_duplicates(self) -> None:
        cases: tuple[tuple[str, object, str], ...] = (
            (
                "count",
                lambda draft: draft["director_style_options"].pop(),
                "STYLE_OPTION_COUNT",
            ),
            (
                "order",
                lambda draft: draft["director_style_options"][1].update(
                    {"option_id": "STYLE-03"}
                ),
                "STYLE_OPTION_ORDER",
            ),
            (
                "rationale",
                lambda draft: draft["director_style_options"][1].update(
                    {"rationale": "适配依据：只有一段。"}
                ),
                "STYLE_OPTION_RATIONALE",
            ),
            (
                "empty rationale section",
                lambda draft: draft["director_style_options"][1].update(
                    {
                        "rationale": style_rationale(
                            fit="适配。",
                            time_edit="",
                            camera="稳定。",
                            space="清楚。",
                            performance="完整。",
                            benefit="明确。",
                            risk="可控。",
                        )
                    }
                ),
                "STYLE_OPTION_RATIONALE",
            ),
            (
                "label",
                lambda draft: draft["director_style_options"][1].update(
                    {"label": draft["director_style_options"][0]["label"]}
                ),
                "STYLE_OPTION_LABEL_DUPLICATE",
            ),
            (
                "profile",
                lambda draft: draft["director_style_options"][1].update(
                    {"profile": copy.deepcopy(draft["director_style_options"][0]["profile"])}
                ),
                "STYLE_OPTION_PROFILE_DUPLICATE",
            ),
        )
        for label, mutate, expected_code in cases:
            with self.subTest(case=label):
                draft = valid_draft()
                mutate(draft)
                result = delivery.validate_data(self.prepared(draft))
                self.assertIn(expected_code, issue_codes(result))

    def test_gate_1_selection_is_not_confirmation(self) -> None:
        draft = valid_draft()
        draft["confirmations"]["gate_1"]["status"] = "pending"
        draft["confirmations"]["gate_1"]["stage_digest"] = ""
        prepared = delivery.prepare_data(draft)
        result = delivery.validate_data(prepared)
        gate_1_status_paths = {
            issue.path
            for issue in result.errors
            if issue.code == "CONFIRMATION_STATUS"
        }
        self.assertIn("$.confirmations.gate_1.status", gate_1_status_paths)

    def test_gate_1_candidate_or_selection_change_invalidates_digest(self) -> None:
        candidate_changed = valid_draft()
        candidate_changed["director_style_options"][2]["rationale"] += "\n"
        candidate_result = delivery.validate_data(
            delivery.prepare_data(candidate_changed)
        )
        self.assertIn("CONFIRMATION_DIGEST", issue_codes(candidate_result))

        selection_changed = valid_draft()
        selection_changed["selected_style_option_id"] = "STYLE-02"
        selection_changed["director_profile"] = copy.deepcopy(alternative_profile())
        selection_result = delivery.validate_data(
            delivery.prepare_data(selection_changed)
        )
        self.assertIn("CONFIRMATION_DIGEST", issue_codes(selection_result))

    def test_explicit_director_can_bypass_default_candidates(self) -> None:
        draft = valid_draft()
        draft.pop("director_style_options")
        draft.pop("selected_style_option_id")
        self.assertFalse(delivery.validate_data(self.prepared(draft)).errors)

    def test_static_front_center_is_legal_but_camera_contradiction_fails(self) -> None:
        camera = {
            "shot_size": "中景",
            "angle": "平视",
            "position": "人物正前方",
            "logic": "朝向人物并维持既定轴线",
            "composition": "人物正面居中",
            "movement": "固定镜头",
        }
        result = delivery.ValidationResult()
        delivery.validate_camera(camera, "$.camera", result)
        self.assertFalse(result.errors)
        camera["logic"] = "沿既定轴线推进到人物正脸"
        result = delivery.ValidationResult()
        delivery.validate_camera(camera, "$.camera", result)
        self.assertIn("CAMERA_LOGIC_CONTRADICTION", issue_codes(result))

    def test_build_declares_contract_and_preserves_handoff_fields(self) -> None:
        built, report, _ = self.build()
        self.assertEqual(built["contract_name"], "shot-data")
        self.assertEqual(built["contract_version"], "2.5.3")
        self.assertEqual(built["source_skill"], "su-fenjingskill")
        self.assertEqual(built["source_skill_version"], "2.5.5")
        self.assertEqual(report["contract_status"], "PASS")
        self.assertEqual(report["director_readiness"], "READY")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["content_hash"], built["content_hash"])
        self.assertEqual(
            report["locked_text_hash"],
            built["source"]["locked_text_hash"],
        )
        self.assertNotIn("source_content_hash", report)
        self.assertEqual([shot["shot_id"] for shot in built["shots"]], ["SH001", "SH002"])
        required = {
            "duration_seconds",
            "plan_unit_id",
            "coverage_evidence",
            "camera",
            "blocking",
            "performance",
            "dialogue",
            "continuity",
            "continuity_updates",
            "rendered_shot_description",
        }
        for shot in built["shots"]:
            self.assertTrue(required.issubset(shot))
            self.assertIn("visible_behavior", shot["performance"])
            self.assertNotIn("shot_form", shot)
            self.assertNotIn("director_audit", shot)
        forbidden = {"prompt", "prompt_text", "model_profile", "timeline", "prompt_units"}
        self.assertTrue(forbidden.isdisjoint(all_keys(built)))

    def test_director_first_minimal_contract_omits_optional_proof_structures(self) -> None:
        draft = valid_draft()
        draft["source_analysis"] = {
            key: draft["source_analysis"][key]
            for key in ("source_boundary", "source_constraints")
        }
        for key in (
            "director_style_options",
            "selected_style_option_id",
            "emotion_arcs",
            "performance_chains",
        ):
            draft.pop(key, None)

        for scene in draft["scenes"]:
            scene["directing_plan"] = {
                key: scene["directing_plan"][key]
                for key in (
                    "scene_objective",
                    "progression",
                    "pov_flow",
                    "entry_strategy",
                    "style_anchors",
                )
            }
            for key in (
                "initial_continuity",
                "axes",
                "inherits_from",
                "inherited_states",
            ):
                scene.pop(key, None)

        for beat in draft["beats"]:
            for fact in beat["facts"]:
                for key in (
                    "presentation_requirement",
                    "shot_isolation",
                    "isolation_reason",
                    "isolation_group_id",
                    "performers",
                ):
                    fact.pop(key, None)

        for unit in draft["shot_plan"]["planned_units"]:
            unit.pop("dialogue_design", None)

        for shot in draft["shots"]:
            for key in (
                "coverage_evidence",
                "primary_fact_id",
                "blocking",
                "performance",
                "visible_characters",
                "visible_props",
                "environment_behavior",
                "continuity",
                "continuity_updates",
                "end_state",
            ):
                shot.pop(key, None)
            shot["camera"] = {
                key: shot["camera"][key]
                for key in (
                    "shot_size",
                    "angle",
                    "position",
                    "logic",
                    "composition",
                    "movement",
                    "framing_mode",
                    "viewpoint_owner",
                    "primary_subjects",
                    "secondary_subjects",
                    "perspective_intent",
                    "focus_plan",
                    "spatial_strategy",
                    "movement_plan",
                    "start_frame",
                    "end_frame",
                    "motivation",
                    "foreground_characters",
                )
                if key in shot["camera"]
            }
            shot["cut_design"].pop("isolation_intent", None)
            shot["transition_to_next"].pop("notes", None)
            for dialogue in shot["dialogue"]:
                dialogue.pop("timing", None)
                dialogue.pop("addressee", None)

        refresh_confirmation_digests(draft)
        built, report, _ = self.build(draft)
        self.assertEqual(report["status"], "PASS")
        self.assertNotIn("director_style_options", built)
        self.assertNotIn("performance_chains", built)
        self.assertNotIn("coverage_evidence", built["shots"][0])
        self.assertIn("execution_text", built["shots"][0])
        self.assertIn("【画面内容】", built["shots"][0]["rendered_shot_description"])
        self.assertNotIn("【机位与构图】", built["shots"][0]["rendered_shot_description"])

    def test_director_analysis_is_optional_and_preserved_without_rendering(self) -> None:
        draft = valid_draft()
        draft["scenes"][0]["director_analysis"] = director_analysis(None)
        draft["beats"][0]["director_analysis"] = director_analysis("steady")
        refresh_confirmation_digests(draft)
        built, report, paths = self.build(draft)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(built["scenes"][0]["director_analysis"]["dramatic_turn"], None)
        self.assertEqual(built["beats"][0]["director_analysis"]["dramatic_turn"], "steady")
        analysis_values = {
            value
            for analysis in (
                built["scenes"][0]["director_analysis"],
                built["beats"][0]["director_analysis"],
            )
            for value in analysis.values()
            if isinstance(value, str)
        }
        rendered = "\n".join(
            shot["rendered_shot_description"] for shot in built["shots"]
        )
        markdown = paths["markdown"].read_text(encoding="utf-8")
        for value in analysis_values:
            self.assertNotIn(value, rendered)
            self.assertNotIn(value, markdown)

    def test_director_analysis_accepts_null_and_steady_dramatic_turn(self) -> None:
        for dramatic_turn in (None, "steady"):
            with self.subTest(dramatic_turn=dramatic_turn):
                draft = valid_draft()
                draft["beats"][0]["director_analysis"] = director_analysis(dramatic_turn)
                result = delivery.validate_data(self.prepared(draft))
                self.assertFalse(result.errors)

    def test_director_analysis_does_not_create_isolation_rule(self) -> None:
        draft = valid_draft()
        draft["beats"][1]["director_analysis"] = director_analysis("回应使信息状态改变。")
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)
        self.assertNotIn("FACT_ISOLATION", issue_codes(result))
        self.assertEqual(draft["shots"][1]["cut_design"]["isolation_intent"], "none")

    def test_director_analysis_fields_are_rejected_in_facts(self) -> None:
        for key, value in (
            ("subtext", "周其实早已知道答案。"),
            ("director_analysis", director_analysis("steady")),
        ):
            with self.subTest(key=key):
                draft = valid_draft()
                draft["beats"][0]["facts"][0][key] = value
                result = delivery.validate_data(self.prepared(draft))
                self.assertIn("DIRECTOR_ANALYSIS_SCOPE", issue_codes(result))

    def test_director_analysis_fields_are_rejected_in_dialogue(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["dialogue"][0]["directorial_intent"] = "让观众怀疑林。"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("DIRECTOR_ANALYSIS_SCOPE", issue_codes(result))

    def test_director_analysis_structure_is_fail_closed(self) -> None:
        cases = (
            ("missing", lambda value: value.pop("subtext"), "DIRECTOR_ANALYSIS_FIELD_MISSING"),
            (
                "unknown",
                lambda value: value.update({"camera_rule": "必须切近景。"}),
                "DIRECTOR_ANALYSIS_FIELD_UNKNOWN",
            ),
            (
                "empty",
                lambda value: value.update({"pov_owner": "   "}),
                "DIRECTOR_ANALYSIS_VALUE",
            ),
            (
                "wrong_type",
                lambda value: value.update({"power_relation": ["林", "周"]}),
                "DIRECTOR_ANALYSIS_VALUE",
            ),
        )
        for label, mutate, expected_code in cases:
            with self.subTest(case=label):
                draft = valid_draft()
                analysis = director_analysis(None)
                mutate(analysis)
                draft["scenes"][0]["director_analysis"] = analysis
                result = delivery.validate_data(self.prepared(draft))
                self.assertIn(expected_code, issue_codes(result))

    def test_director_analysis_is_rejected_at_shot_scope(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["director_analysis"] = director_analysis("steady")
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("DIRECTOR_ANALYSIS_SCOPE", issue_codes(result))

    def test_build_writes_exact_six_column_markdown_and_excel(self) -> None:
        built, _, paths = self.build()
        expected = delivery.expected_table_rows(built)
        self.assertEqual(delivery.read_markdown_rows(paths["markdown"]), expected)
        self.assertEqual(delivery.read_xlsx_rows(paths["excel"]), expected)
        self.assertEqual(expected[0], delivery.HEADERS)
        self.assertEqual(len(expected[0]), 6)

    def test_output_contract_is_concise_and_avoids_coverage_bias(self) -> None:
        contract_path = SCRIPT_DIR.parent / "references" / "output-contract.md"
        contract_text = contract_path.read_text(encoding="utf-8")
        self.assertLess(len(contract_text.splitlines()), 620)
        self.assertIn("最小结构示例", contract_text)
        self.assertIn("六列渲染示例", contract_text)
        self.assertNotIn("可直接构建的合法 draft", contract_text)
        self.assertNotIn("standard_shot_percentage", contract_text)

    def test_gate_2_display_requires_exact_visual_contract_values(self) -> None:
        shot_design = (
            SCRIPT_DIR.parent / "references" / "shot-design.md"
        ).read_text(encoding="utf-8")
        self.assertIn("屏幕事件、切／留／重构地图、DOP 镜头表", shot_design)
        self.assertIn("完整 `movement_plan`", shot_design)
        self.assertIn("全部场次结束后只确认一次", shot_design)
        self.assertIn("不得再称为“抽象规划”", shot_design)

    def test_validate_delivery_passes_built_files(self) -> None:
        self.build()
        _, result = delivery.validate_delivery(self.output_dir)
        self.assertEqual(result.status, "PASS")
        self.assertFalse(result.errors)

    def test_delivery_slug_drives_all_output_filenames(self) -> None:
        draft = valid_draft()
        draft["source"]["delivery_slug"] = "ep15-dibati"
        _, report, paths = self.build(draft)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(
            {key: path.name for key, path in paths.items()},
            {
                "json": "ep15-dibati-shot-data.json",
                "markdown": "ep15-dibati-storyboard.md",
                "excel": "ep15-dibati-storyboard.xlsx",
                "report": "ep15-dibati-storyboard-validation.json",
            },
        )

    def test_delivery_slug_follows_ascii_kebab_naming_standard(self) -> None:
        for invalid_slug in (
            "第15集-第八天",
            "EP15-dibati",
            "ep15_dibati",
            "ep15-dibati-v243",
            "ep15-dibati-final",
        ):
            with self.subTest(slug=invalid_slug):
                draft = valid_draft()
                draft["source"]["delivery_slug"] = invalid_slug
                result = delivery.validate_data(self.prepared(draft))
                self.assertIn("DELIVERY_SLUG", issue_codes(result))

    def test_cli_build_and_validate_end_to_end(self) -> None:
        self.write_draft(valid_draft())
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        build = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "build",
                "--input",
                str(self.draft_path),
                "--output-dir",
                str(self.output_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        validate = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "validate",
                "--output-dir",
                str(self.output_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(validate.returncode, 0, validate.stderr)

    def test_build_is_byte_deterministic(self) -> None:
        _, _, paths = self.build()
        first = {
            key: path.read_bytes()
            for key, path in paths.items()
        }
        _, _, paths = self.build()
        second = {
            key: path.read_bytes()
            for key, path in paths.items()
        }
        self.assertEqual(first, second)

    def test_duration_is_sum_of_ordered_shot_phases(self) -> None:
        draft = valid_draft()
        draft["shot_plan"]["planned_units"][0]["estimated_duration_seconds"] = 5
        refresh_plan_metrics(draft)
        draft["shots"][0]["shot_phases"][0]["duration_seconds"] = 3
        draft["shots"][0]["duration_seconds"] = 5
        refresh_confirmation_digests(draft)
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)
        draft["shots"][0]["duration_seconds"] = 4
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("SHOT_PHASE_DURATION_SUM", issue_codes(result))

    def test_shot_phase_duration_rejects_bool_float_string_and_zero(self) -> None:
        for bad_value in (True, 1.5, "2", 0):
            with self.subTest(value=bad_value):
                draft = valid_draft()
                draft["shots"][0]["shot_phases"][0]["duration_seconds"] = bad_value
                result = delivery.validate_data(self.prepared(draft))
                self.assertIn("SHOT_PHASE_DURATION", issue_codes(result))

    def test_duration_requires_ordered_shot_phases(self) -> None:
        draft = valid_draft()
        draft["shots"][0].pop("shot_phases")
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("SHOT_PHASES_REQUIRED", issue_codes(result))

        draft = valid_draft()
        draft["shots"][0]["shot_phases"][0]["phase_order"] = 2
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("SHOT_PHASE_ORDER", issue_codes(result))

    def test_shot_phase_requires_camera_state_and_exact_event_coverage(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["shot_phases"][0]["camera_state"] = ""
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("STRING_REQUIRED", issue_codes(result))

        draft = valid_draft()
        draft["shots"][0]["shot_phases"][0]["screen_event_ids"] = ["SEV002"]
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("SHOT_PHASE_EVENT_COVERAGE", issue_codes(result))

    def test_final_duration_cannot_bypass_gate_2_duration_audit(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["shot_phases"][0]["duration_seconds"] = 120
        draft["shots"][0]["duration_seconds"] = 120
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("SHOT_PLAN_DURATION", issue_codes(result))

    def test_long_take_needs_review_is_warning_not_failure(self) -> None:
        draft = valid_draft()
        draft["shot_plan"]["planned_units"][0]["shot_form"] = "long_take"
        draft["shot_plan"]["planned_units"][0]["long_take_design"] = {
            "reason": "保护周在倾听中逐渐承受压力的连续表演。",
            "supports": ["performance_development"],
            "protected_event_ids": ["SEV001"],
        }
        draft["shots"][0]["shot_form"] = "long_take"
        draft["shots"][0]["director_audit"] = {
            "long_take": {
                "status": "needs_review",
                "reason": "",
                "supports": [],
            }
        }
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)
        self.assertEqual(result.status, "WARN")
        self.assertIn("LONG_TAKE_REVIEW", {issue.code for issue in result.warnings})

    def test_close_first_shot_and_push_then_pull_are_valid(self) -> None:
        result = delivery.validate_data(self.prepared())
        self.assertFalse(result.errors)
        self.assertEqual(valid_draft()["shots"][0]["camera"]["shot_size"], "中近景")
        self.assertIn("推进", valid_draft()["shots"][0]["camera"]["movement"])
        self.assertIn("拉出", valid_draft()["shots"][1]["camera"]["movement"])

    def test_stable_arc_does_not_require_all_four_stages(self) -> None:
        result = delivery.validate_data(self.prepared())
        self.assertFalse(result.errors)
        phases = [phase["phase"] for phase in valid_draft()["emotion_arcs"][0]["phases"]]
        self.assertEqual(phases, ["steady", "existing_transition"])

    def test_must_be_clear_does_not_force_isolation(self) -> None:
        data = self.prepared()
        fact = data["beats"][1]["facts"][0]
        self.assertNotIn("presentation_requirement", fact)
        self.assertNotIn("shot_isolation", fact)
        result = delivery.validate_data(data)
        self.assertFalse(result.errors)

    def test_explicit_director_required_needs_explicit_shot_intent(self) -> None:
        draft = valid_draft()
        fact = draft["beats"][1]["facts"][0]
        fact["shot_isolation"] = "director_required"
        fact["isolation_reason"] = "钥匙状态改变必须获得独立视觉重心。"
        fact["isolation_group_id"] = "IG001"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("FACT_ISOLATION", issue_codes(result))
        draft["shots"][1]["cut_design"]["isolation_intent"] = "director_required"
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

    def test_abstract_emotion_requires_visible_behavior(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["performance"]["visible_behavior"] = []
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("PERFORMANCE_VISIBLE", issue_codes(result))

    def test_dialogue_must_match_fact_verbatim(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["dialogue"][0]["text"] = "你听到了吗？"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("DIALOGUE_TEXT", issue_codes(result))

    def test_original_english_dialogue_stays_english_without_translation(self) -> None:
        draft = valid_draft()
        draft["source"]["locked_text"] = draft["source"]["locked_text"].replace(
            "你听见了吗？",
            "Ready?",
        )
        draft["source"]["dialogue_language_policy"] = {
            "mode": "multilingual_actual",
            "spoken_languages": ["en", "zh-CN"],
            "resolution": "user_confirmed",
            "evidence": "本段对白中英混用，两种语言均为实际说出。",
        }
        draft["source"]["approved_corrections"] = [
            {
                "from": "双语台词语言策略未锁定",
                "to": "本段对白中英混用，两种语言均为实际说出。",
                "reason": "用户确认：林以英文发问，周以中文回应，均为实际对白。",
            }
        ]
        draft["beats"][0]["facts"][1]["text"] = "Ready?"
        draft["beats"][0]["facts"][1]["language"] = "en"
        draft["beats"][0]["facts"][1]["source_role"] = "spoken_dialogue"
        draft["beats"][1]["facts"][1]["language"] = "zh-CN"
        draft["beats"][1]["facts"][1]["source_role"] = "spoken_dialogue"
        draft["shots"][0]["dialogue"][0]["text"] = "Ready?"
        draft["shots"][0]["coverage_evidence"][1]["evidence_quote"] = "Ready?"
        draft["shots"][0]["execution_text"] = draft["shots"][0][
            "execution_text"
        ].replace("你听见了吗？", "Ready?")
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

        translated = copy.deepcopy(draft)
        translated["source"].pop("dialogue_language_policy", None)
        translated["source"].pop("approved_corrections", None)
        translated["beats"][0]["facts"][1]["text"] = "准备好了吗？"
        translated["beats"][0]["facts"][1]["language"] = "zh-CN"
        translated["shots"][0]["dialogue"][0]["text"] = "准备好了吗？"
        translated["shots"][0]["coverage_evidence"][1]["evidence_quote"] = "准备好了吗？"
        translated["shots"][0]["execution_text"] = translated["shots"][0][
            "execution_text"
        ].replace("Ready?", "准备好了吗？")
        result = delivery.validate_data(self.prepared(translated))
        self.assertIn("FACT_SOURCE", issue_codes(result))

    def test_bilingual_dialogue_requires_explicit_language_role_lock(self) -> None:
        locked_text = (
            "**哈珀**（含泪）：因为我爱上了你。\n\n"
            "*HARPER: Because I fell in love.*"
        )
        source = {
            "locked_text": locked_text,
            "approved_corrections": [],
        }
        result = delivery.ValidationResult()
        policy = delivery.validate_dialogue_language_policy(
            source,
            locked_text,
            result,
        )
        self.assertIsNone(policy)
        self.assertIn("DIALOGUE_LANGUAGE_AMBIGUOUS", issue_codes(result))

    def test_plain_same_speaker_bilingual_pair_is_detected(self) -> None:
        locked_text = (
            "哈珀：因为我爱上了你。\n"
            "哈珀：Because I fell in love."
        )
        result = delivery.ValidationResult()
        policy = delivery.validate_dialogue_language_policy(
            {"locked_text": locked_text, "approved_corrections": []},
            locked_text,
            result,
        )
        self.assertIsNone(policy)
        self.assertIn("DIALOGUE_LANGUAGE_AMBIGUOUS", issue_codes(result))

    def test_multilingual_actual_policy_preserves_both_spoken_languages(
        self,
    ) -> None:
        locked_text = "哈珀：你好。\n哈珀：Hello."
        evidence = "两行都是角色实际说出的台词，不是互译"
        source = {
            "locked_text": locked_text,
            "approved_corrections": [
                {
                    "from": "相邻双语台词身份未明确",
                    "to": evidence,
                    "reason": "用户明确确认",
                }
            ],
            "dialogue_language_policy": {
                "mode": "multilingual_actual",
                "spoken_languages": ["zh-CN", "en"],
                "resolution": "user_confirmed",
                "evidence": evidence,
            },
        }
        result = delivery.ValidationResult()
        policy = delivery.validate_dialogue_language_policy(
            source,
            locked_text,
            result,
        )
        self.assertFalse(result.errors)
        self.assertIsNotNone(policy)
        for text, language in (("你好。", "zh-CN"), ("Hello.", "en")):
            fact_result = delivery.ValidationResult()
            delivery.validate_dialogue_fact_language(
                {
                    "type": "dialogue",
                    "text": text,
                    "language": language,
                    "source_role": "spoken_dialogue",
                },
                policy=policy,
                path="$.beats[0].facts[0]",
                result=fact_result,
            )
            self.assertFalse(fact_result.errors)

    def test_user_confirmed_bilingual_policy_binds_original_english(self) -> None:
        locked_text = (
            "**哈珀**（含泪）：因为我爱上了你。\n\n"
            "*HARPER: Because I fell in love.*"
        )
        evidence = "英文为原始台词，中文为对照译文"
        source = {
            "locked_text": locked_text,
            "approved_corrections": [
                {
                    "from": "中英文并列台词的原文身份未明确",
                    "to": evidence,
                    "reason": "用户明确确认",
                }
            ],
            "dialogue_language_policy": {
                "mode": "original_with_translation",
                "original_language": "en",
                "translation_languages": ["zh-CN"],
                "resolution": "user_confirmed",
                "evidence": evidence,
            },
        }
        result = delivery.ValidationResult()
        policy = delivery.validate_dialogue_language_policy(
            source,
            locked_text,
            result,
        )
        self.assertFalse(result.errors)
        self.assertIsNotNone(policy)

        fact_result = delivery.ValidationResult()
        delivery.validate_dialogue_fact_language(
            {
                "type": "dialogue",
                "text": "Because I fell in love.",
                "language": "en",
                "source_role": "original_dialogue",
            },
            policy=policy,
            path="$.beats[0].facts[0]",
            result=fact_result,
        )
        self.assertFalse(fact_result.errors)

        translated_result = delivery.ValidationResult()
        delivery.validate_dialogue_fact_language(
            {
                "type": "dialogue",
                "text": "因为我爱上了你。",
                "language": "en",
                "source_role": "original_dialogue",
            },
            policy=policy,
            path="$.beats[0].facts[0]",
            result=translated_result,
        )
        self.assertIn(
            "DIALOGUE_LANGUAGE_TEXT_MISMATCH",
            issue_codes(translated_result),
        )

    def test_bilingual_source_explicit_requires_nearby_role_marker(self) -> None:
        locked_text = "哈珀：因为我爱上了你。\n*HARPER: Because I fell in love.*"
        source = {
            "locked_text": locked_text,
            "approved_corrections": [],
            "dialogue_language_policy": {
                "mode": "original_with_translation",
                "original_language": "en",
                "translation_languages": ["zh-CN"],
                "resolution": "source_explicit",
                "evidence": "英文为原始台词",
            },
        }
        result = delivery.ValidationResult()
        delivery.validate_dialogue_language_policy(source, locked_text, result)
        self.assertIn("DIALOGUE_LANGUAGE_EVIDENCE", issue_codes(result))

    def test_user_confirmed_bilingual_policy_requires_correction_record(self) -> None:
        locked_text = "哈珀：因为我爱上了你。\n*HARPER: Because I fell in love.*"
        source = {
            "locked_text": locked_text,
            "approved_corrections": [],
            "dialogue_language_policy": {
                "mode": "original_with_translation",
                "original_language": "en",
                "translation_languages": ["zh-CN"],
                "resolution": "user_confirmed",
                "evidence": "英文为原始台词，中文为对照译文",
            },
        }
        result = delivery.ValidationResult()
        delivery.validate_dialogue_language_policy(source, locked_text, result)
        self.assertIn("DIALOGUE_LANGUAGE_CONFIRMATION", issue_codes(result))

    def test_picture_content_defaults_to_chinese_but_allows_standard_and_source_terms(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["execution_text"] += "摄影机保持POV关系。"
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("EXECUTION_LANGUAGE_DEFAULT", issue_codes(result))

        draft = valid_draft()
        draft["shots"][0]["execution_text"] += "透视采用wide_spatial。"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("EXECUTION_LANGUAGE_DEFAULT", issue_codes(result))

        draft = valid_draft()
        draft["shots"][0]["execution_text"] += "人物保持mood。"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("EXECUTION_LANGUAGE_DEFAULT", issue_codes(result))

        draft = valid_draft()
        draft["source"]["locked_text"] += "Walkman放在桌边。\n"
        draft["shots"][0]["execution_text"] += "桌边保留Walkman。"
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("EXECUTION_LANGUAGE_DEFAULT", issue_codes(result))

    def test_source_span_hash_and_range_are_validated(self) -> None:
        data = self.prepared()
        data["shots"][0]["source_spans"][0]["text_hash"] = "0" * 64
        data["content_hash"] = delivery.content_hash(data)
        result = delivery.validate_data(data)
        self.assertIn("SOURCE_SPAN_HASH", issue_codes(result))
        data = self.prepared()
        data["shots"][0]["source_spans"][0]["end"] = len(SOURCE_TEXT) + 1
        data["content_hash"] = delivery.content_hash(data)
        result = delivery.validate_data(data)
        self.assertIn("SOURCE_SPAN_RANGE", issue_codes(result))

    def test_rendered_description_tamper_is_rejected(self) -> None:
        data = self.prepared()
        data["shots"][0]["rendered_shot_description"] += "新增画面。"
        data["content_hash"] = delivery.content_hash(data)
        result = delivery.validate_data(data)
        self.assertIn("RENDERED_DESCRIPTION", issue_codes(result))

    def test_downstream_fields_are_recursively_forbidden(self) -> None:
        for key in (
            "prompt",
            "prompt_text",
            "prompt_units",
            "model_profile",
            "model_config",
            "max_clip_duration_seconds",
            "timeline",
        ):
            with self.subTest(key=key):
                data = self.prepared()
                data["shots"][0]["camera"]["nested"] = {key: "forbidden"}
                data["content_hash"] = delivery.content_hash(data)
                result = delivery.validate_data(data)
                self.assertIn("DOWNSTREAM_FIELD_FORBIDDEN", issue_codes(result))

    def test_invalid_excel_xml_control_character_is_rejected(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["notes"] = "非法控制字符\u0001"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("XML_CHARACTER", issue_codes(result))

    def test_shots_array_order_is_machine_fact(self) -> None:
        data = self.prepared()
        data["shots"][0]["shot_order"] = 2
        data["shots"][1]["shot_order"] = 1
        data["content_hash"] = delivery.content_hash(data)
        result = delivery.validate_data(data)
        self.assertIn("SHOT_ORDER", issue_codes(result))
        data = self.prepared()
        data["shots"][0]["shot_id"] = "SH002"
        data["shots"][1]["shot_id"] = "SH001"
        data["content_hash"] = delivery.content_hash(data)
        result = delivery.validate_data(data)
        self.assertIn("SHOT_ID_ORDER", issue_codes(result))

    def test_axis_cross_requires_reason_and_becomes_warning(self) -> None:
        draft = valid_draft()
        draft["shots"][1]["continuity"]["axis_side"] = "side_b"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("AXIS_CROSS", issue_codes(result))
        draft["shots"][1]["continuity"]["intentional_exceptions"] = [
            {"type": "axis_cross", "reason": "在回应时主动翻转权力关系。"}
        ]
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)
        self.assertEqual(result.status, "WARN")

    def test_action_cut_requires_matching_action_id_or_reason(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["transition_to_next"]["type"] = "action_cut"
        draft["shots"][0]["continuity"]["action_match"]["outgoing"] = "AM001"
        draft["shots"][1]["continuity"]["action_match"]["incoming"] = "AM002"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("ACTION_MATCH", issue_codes(result))
        draft["shots"][1]["continuity"]["action_match"]["incoming"] = "AM001"
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

    def test_continuity_update_from_must_match_current_state(self) -> None:
        draft = valid_draft()
        draft["shots"][1]["continuity_updates"][0]["from"] = "未握"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("CONTINUITY_FROM", issue_codes(result))

    def test_cross_scene_inheritance_uses_parent_final_state(self) -> None:
        draft = draft_with_inherited_scene()
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)
        draft["scenes"][1]["initial_continuity"]["props"][0]["state"] = "松握"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("INHERITED_STATE_VALUE", issue_codes(result))

    def test_shot_notes_are_blank_reserved_column(self) -> None:
        draft = valid_draft()
        built, _, paths = self.build(draft)
        expected = delivery.expected_table_rows(built)
        self.assertEqual(delivery.read_markdown_rows(paths["markdown"]), expected)
        self.assertEqual(delivery.read_xlsx_rows(paths["excel"]), expected)
        self.assertTrue(all(row[-1] == "" for row in expected[1:]))

        draft = valid_draft()
        draft["shots"][0]["notes"] = "人工预留列不应由 Skill 自动填写。"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("SHOT_NOTES_RESERVED", issue_codes(result))

    def test_any_generated_shot_note_is_rejected(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["notes"] = (
            "[时长估算]同步动作99秒；同步台词0秒；非同步动作0秒；"
            "情绪留白0秒；前两项取 max 后再加后两项，共99秒。"
            "[执行提醒]晨雾浓度必须保持连续。"
        )
        prepared = self.prepared(draft)
        result = delivery.validate_data(prepared)
        self.assertIn("SHOT_NOTES_RESERVED", issue_codes(result))
        self.assertEqual(prepared["shots"][0]["notes"], draft["shots"][0]["notes"])

    def test_prepare_data_does_not_mutate_draft(self) -> None:
        draft = valid_draft()
        snapshot = copy.deepcopy(draft)
        prepared = delivery.prepare_data(draft)
        self.assertEqual(draft, snapshot)
        self.assertNotEqual(prepared["content_hash"], "")
        self.assertNotEqual(prepared["shots"][0]["rendered_shot_description"], "")

    def test_tampered_markdown_is_detected(self) -> None:
        _, _, paths = self.build()
        text = paths["markdown"].read_text(encoding="utf-8")
        paths["markdown"].write_text(text.replace("你听见了吗？", "你听到了吗？", 1), encoding="utf-8")
        _, result = delivery.validate_delivery(self.output_dir)
        self.assertIn("MARKDOWN_MISMATCH", issue_codes(result))

    def test_exactly_two_ordered_confirmations_are_required(self) -> None:
        draft = valid_draft()
        draft["confirmations"]["gate_2"]["status"] = "pending"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("CONFIRMATION_STATUS", issue_codes(result))

    def test_confirmation_count_order_and_identity_claims_fail_closed(self) -> None:
        draft = valid_draft()
        draft["confirmations"]["final_storyboard"] = {
            "status": "confirmed",
            "stage_digest": "0" * 64,
            "confirmation_order": 3,
            "notes": "",
        }
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("CONFIRMATION_COUNT", issue_codes(result))
        self.assertIn("CONFIRMATION_UNKNOWN", issue_codes(result))

        draft = valid_draft()
        draft["confirmations"]["gate_1"]["confirmation_order"] = 2
        draft["confirmations"]["gate_2"]["confirmation_order"] = 1
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("CONFIRMATION_ORDER", issue_codes(result))

        draft = valid_draft()
        draft["confirmations"]["gate_1"]["confirmed_by"] = "someone"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("CONFIRMATION_FIELD_UNKNOWN", issue_codes(result))

    def test_gate_1_digest_invalidates_on_source_analysis_or_style_change(self) -> None:
        cases = (
            (
                "source",
                lambda draft: draft["source"].update(
                    {"scope": "同一文本的新边界说明"}
                ),
            ),
            (
                "analysis",
                lambda draft: draft["source_analysis"].update(
                    {"narrative_function": "修改后的叙事功能"}
                ),
            ),
            (
                "style",
                lambda draft: (
                    draft["director_profile"].update({"rhythm": "balanced"}),
                    draft["director_style_options"][0]["profile"].update(
                        {"rhythm": "balanced"}
                    ),
                ),
            ),
        )
        for label, mutate in cases:
            with self.subTest(case=label):
                draft = valid_draft()
                mutate(draft)
                prepared = delivery.prepare_data(draft)
                result = delivery.validate_data(prepared)
                paths = {
                    issue.path
                    for issue in result.errors
                    if issue.code == "CONFIRMATION_DIGEST"
                }
                self.assertIn("$.confirmations.gate_1.stage_digest", paths)

    def test_delivery_slug_does_not_invalidate_director_gate_digests(self) -> None:
        draft = valid_draft()
        gate_1_digest = delivery.stage_digest(draft, 1)
        gate_2_digest = delivery.stage_digest(draft, 2)
        draft["source"]["delivery_slug"] = "ep15-dibati"
        self.assertEqual(gate_1_digest, delivery.stage_digest(draft, 1))
        self.assertEqual(gate_2_digest, delivery.stage_digest(draft, 2))

    def test_director_profile_does_not_require_priority_count_filling(self) -> None:
        draft = valid_draft()
        draft["director_style_options"][0]["profile"]["priorities"] = [
            "保留问话后的停顿"
        ]
        draft["director_profile"] = copy.deepcopy(
            draft["director_style_options"][0]["profile"]
        )
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

    def test_gate_2_digest_invalidates_when_plan_changes(self) -> None:
        draft = valid_draft()
        draft["shot_plan"]["planned_units"][0][
            "narrative_purpose"
        ] = "修改后的规划意图。"
        prepared = delivery.prepare_data(draft)
        result = delivery.validate_data(prepared)
        digest_paths = {
            issue.path
            for issue in result.errors
            if issue.code == "CONFIRMATION_DIGEST"
        }
        self.assertNotIn("$.confirmations.gate_1.stage_digest", digest_paths)
        self.assertIn("$.confirmations.gate_2.stage_digest", digest_paths)

    def test_final_shots_must_match_confirmed_plan(self) -> None:
        cases = (
            (
                "count",
                lambda draft: draft["shots"].pop(),
                "SHOT_PLAN_COUNT",
            ),
            (
                "order",
                lambda draft: draft["shots"][0].update(
                    {"plan_unit_id": "PU002"}
                ),
                "SHOT_PLAN_UNIT",
            ),
            (
                "form",
                lambda draft: draft["shots"][0].update(
                    {"shot_form": "long_take"}
                ),
                "SHOT_PLAN_FORM",
            ),
            (
                "edit_point",
                lambda draft: draft["shots"][0]["transition_to_next"].update(
                    {"edit_point_id": "EP999"}
                ),
                "SHOT_PLAN_EDIT_POINT",
            ),
        )
        for label, mutate, expected_code in cases:
            with self.subTest(case=label):
                draft = valid_draft()
                mutate(draft)
                result = delivery.validate_data(self.prepared(draft))
                self.assertIn(expected_code, issue_codes(result))

    def test_plan_change_requires_new_gate_2_even_when_final_matches(self) -> None:
        draft = valid_draft()
        draft["shot_plan"]["planned_units"][0]["shot_form"] = "long_take"
        refresh_plan_metrics(draft)
        draft["shots"][0]["shot_form"] = "long_take"
        draft["shots"][0]["director_audit"] = {
            "long_take": {
                "status": "supported",
                "reason": "表演过程持续变化。",
                "supports": ["performance_development"],
            }
        }
        prepared = delivery.prepare_data(draft)
        result = delivery.validate_data(prepared)
        digest_paths = {
            issue.path
            for issue in result.errors
            if issue.code == "CONFIRMATION_DIGEST"
        }
        self.assertEqual(
            digest_paths,
            {"$.confirmations.gate_2.stage_digest"},
        )

    def test_unnumbered_continuous_text_uses_stable_internal_ids(self) -> None:
        draft = valid_draft()
        self.assertNotIn("SCENE", draft["source"]["locked_text"])
        self.assertEqual(draft["source"]["input_kind"], "continuous_text")
        self.assertEqual(draft["scenes"][0]["scene_id"], "SC001")
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

    def test_all_three_legal_input_kinds_do_not_require_external_numbering(self) -> None:
        cases = (
            ("full_screenplay", "entire_submitted_text"),
            ("screenplay_segment", "explicit_continuous_range"),
            ("continuous_text", "user_locked_fragment"),
        )
        for input_kind, boundary_lock in cases:
            with self.subTest(input_kind=input_kind):
                draft = valid_draft()
                draft["source"]["input_kind"] = input_kind
                draft["source"]["boundary_lock"] = boundary_lock
                result = delivery.validate_data(self.prepared(draft))
                self.assertFalse(result.errors)

    def test_fact_span_must_be_coordinate_contained_in_its_beat(self) -> None:
        draft = valid_draft()
        duplicate = "林站在门口，周坐在桌边。"
        draft["source"]["locked_text"] += duplicate + "\n"
        start = draft["source"]["locked_text"].rindex(duplicate)
        draft["beats"][0]["facts"][0]["source_spans"] = [
            {"start": start, "end": start + len(duplicate)}
        ]
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("FACT_BEAT_SOURCE", issue_codes(result))

    def test_shot_source_must_coordinate_cover_each_covered_fact(self) -> None:
        draft = valid_draft()
        replacement = [source_span("林：你听见了吗？")]
        draft["shot_plan"]["planned_units"][0]["source_spans"] = copy.deepcopy(
            replacement
        )
        draft["shots"][0]["source_spans"] = copy.deepcopy(replacement)
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("SHOT_FACT_SOURCE", issue_codes(result))

    def test_implicit_plan_reversal_is_rejected(self) -> None:
        draft = valid_draft()
        first, second = draft["shot_plan"]["planned_units"]
        draft["shot_plan"]["planned_units"] = [second, first]
        draft["shot_plan"]["planned_units"][0]["plan_order"] = 1
        draft["shot_plan"]["planned_units"][1]["plan_order"] = 2
        edit_point = draft["shot_plan"]["edit_points"][0]
        edit_point["after_plan_unit_id"] = "PU002"
        edit_point["before_plan_unit_id"] = "PU001"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("PLAN_SOURCE_ORDER", issue_codes(result))

    def test_explicit_source_bound_reorder_can_be_confirmed(self) -> None:
        draft = valid_draft()
        first, second = draft["shot_plan"]["planned_units"]
        draft["shot_plan"]["planned_units"] = [second, first]
        for index, unit in enumerate(draft["shot_plan"]["planned_units"], start=1):
            unit["plan_order"] = index
        edit_point = draft["shot_plan"]["edit_points"][0]
        edit_point["after_plan_unit_id"] = "PU002"
        edit_point["before_plan_unit_id"] = "PU001"
        draft["shot_plan"]["reorders"] = [
            {
                "reorder_id": "RO001",
                "plan_unit_ids": ["PU002", "PU001"],
                "source_spans": [
                    source_span("林站在门口，周坐在桌边。"),
                    source_span("林：你听见了吗？"),
                    source_span("周抬眼，握紧钥匙：听见了。"),
                ],
                "reason": "先给出回应，再回到问题以形成主观记忆重排。",
            }
        ]
        shot_one, shot_two = draft["shots"]
        draft["shots"] = [shot_two, shot_one]
        for index, shot in enumerate(draft["shots"], start=1):
            shot["shot_order"] = index
            shot["shot_id"] = f"SH{index:03d}"
        draft["shots"][0]["transition_to_next"] = {
            "type": "gaze_cut",
            "edit_point_id": "EP001",
            "notes": "按已确认重排回到问题。",
        }
        draft["shots"][1]["transition_to_next"] = {
            "type": "scene_end",
            "edit_point_id": None,
            "notes": "结束重排。",
        }
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

    def test_covered_facts_do_not_require_repeated_path_evidence(self) -> None:
        draft = valid_draft()
        draft["shots"][1]["coverage_evidence"] = [
            draft["shots"][1]["coverage_evidence"][1]
        ]
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

    def test_coverage_evidence_rejects_wrong_path(self) -> None:
        draft = valid_draft()
        draft["shots"][1]["coverage_evidence"][0]["target_path"] = "notes"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("COVERAGE_EVIDENCE_PATH", issue_codes(result))

    def test_coverage_evidence_rejects_missing_quote(self) -> None:
        draft = valid_draft()
        draft["shots"][1]["coverage_evidence"][0][
            "evidence_quote"
        ] = "周抬眼"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("COVERAGE_EVIDENCE_QUOTE", issue_codes(result))

    def test_unsourced_action_cannot_pretend_to_cover_fact(self) -> None:
        draft = valid_draft()
        draft["shots"][1]["blocking"][0]["action"] = "转身后握紧钥匙"
        draft["shots"][1]["coverage_evidence"][0]["evidence_quote"] = "转身"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("COVERAGE_EVIDENCE_SOURCE", issue_codes(result))

    def test_dialogue_body_rejects_speaker_prefix(self) -> None:
        draft = valid_draft()
        full_line = "林：你听见了吗？"
        fact = draft["beats"][0]["facts"][1]
        fact["text"] = full_line
        fact["source_spans"] = [source_span(full_line)]
        draft["shots"][0]["dialogue"][0]["text"] = full_line
        draft["shots"][0]["coverage_evidence"][1]["evidence_quote"] = full_line
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("DIALOGUE_SPEAKER_PREFIX", issue_codes(result))

    def test_transition_language_mapping_is_closed(self) -> None:
        self.assertEqual(
            delivery.TRANSITION_LANGUAGE_TO_TYPE,
            {
                "hard_cut": "cut",
                "action_cut": "action_cut",
                "gaze_cut": "gaze_cut",
                "sound_bridge": "sound_bridge",
                "long_hold": "hold",
                "dissolve": "dissolve",
                "fade": "fade",
            },
        )
        self.assertEqual(
            set(delivery.TRANSITION_LANGUAGE_TO_TYPE.values()) | {"scene_end"},
            delivery.TRANSITION_TYPES,
        )

    def test_hard_cut_and_long_hold_map_to_cut_and_hold(self) -> None:
        draft = valid_draft()
        draft["director_profile"]["transition_language"].append("hard_cut")
        draft["director_style_options"][0]["profile"][
            "transition_language"
        ].append("hard_cut")
        draft["shots"][0]["transition_to_next"]["type"] = "cut"
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

        draft = valid_draft()
        draft["shots"][0]["transition_to_next"]["type"] = "hold"
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

    def test_transition_type_does_not_require_profile_whitelist(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["transition_to_next"]["type"] = "fade"
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

    def test_surrogate_returns_structured_validation_issue(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["notes"] = "\ud800"
        result = delivery.validate_data(draft)
        self.assertEqual(issue_codes(result), {"UNICODE_SURROGATE"})
        with self.assertRaises(delivery.UnicodeContractError):
            delivery.sha256_text("\ud800")

    def test_cli_build_reports_surrogate_without_unicodeencodeerror(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["notes"] = "\ud800"
        self.draft_path.write_text(
            json.dumps(draft, ensure_ascii=True, allow_nan=False),
            encoding="ascii",
        )
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(MODULE_PATH),
                "build",
                "--input",
                str(self.draft_path),
                "--output-dir",
                str(self.output_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(completed.returncode, 1)
        report = json.loads(completed.stderr)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "UNICODE_SURROGATE",
            {issue["code"] for issue in report["errors"]},
        )
        self.assertNotIn("UnicodeEncodeError", completed.stderr)

    def test_cli_validate_reports_surrogate_without_unicodeencodeerror(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["notes"] = "\udfff"
        self.output_dir.mkdir()
        filename = delivery.output_filenames(draft)["json"]
        (self.output_dir / filename).write_text(
            json.dumps(draft, ensure_ascii=True, allow_nan=False),
            encoding="ascii",
        )
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(MODULE_PATH),
                "validate",
                "--output-dir",
                str(self.output_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(completed.returncode, 1)
        report = json.loads(completed.stderr)
        self.assertIn(
            "UNICODE_SURROGATE",
            {issue["code"] for issue in report["errors"]},
        )
        self.assertNotIn("UnicodeEncodeError", completed.stderr)

    def test_plan_rejects_final_storyboard_details(self) -> None:
        draft = valid_draft()
        draft["shot_plan"]["planned_units"][0]["camera"] = {
            "composition": "不应提前出现"
        }
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("PLAN_UNIT_FIELD_UNKNOWN", issue_codes(result))

    def test_plan_metrics_are_derived_not_self_declared(self) -> None:
        draft = valid_draft()
        draft["shot_plan"]["planned_edit_point_count"] = 99
        prepared = self.prepared(draft)
        self.assertEqual(prepared["shot_plan"]["planned_edit_point_count"], 1)
        self.assertFalse(delivery.validate_data(prepared).errors)

    def test_ordinary_shot_over_ten_seconds_is_blocked(self) -> None:
        draft = valid_draft()
        draft["shot_plan"]["planned_units"][0][
            "estimated_duration_seconds"
        ] = 120
        refresh_plan_metrics(draft)
        draft["shots"][0]["shot_phases"][0]["duration_seconds"] = 120
        draft["shots"][0]["duration_seconds"] = 120
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("ORDINARY_SHOT_DURATION_EXCEEDED", issue_codes(result))
        self.assertNotIn("shot_form", draft["shots"][0])
        self.assertNotIn("shot_form", draft["shot_plan"]["planned_units"][0])

    def test_gate_2_digest_binds_visible_plan_not_hidden_performance_chains(self) -> None:
        draft = valid_draft()
        prepared = delivery.prepare_data(draft)
        draft["performance_chains"][0]["steps"][0]["role"] = "reaction"
        stale = delivery.prepare_data(draft)
        self.assertEqual(
            prepared["confirmations"]["gate_2"]["stage_digest"],
            delivery.stage_digest(stale, 2),
        )

        draft = valid_draft()
        draft["shot_plan"]["viewing_decisions"][0]["director_reason"] = "节奏需要"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("VIEWING_DECISION_GENERIC", issue_codes(result))

    def test_sound_rhythm_and_emotion_are_valid_cut_reasons(self) -> None:
        draft = valid_draft()
        decision = draft["shot_plan"]["viewing_decisions"][0]
        decision["trigger"] = "门外低频声突然中断，沉默开始压住问句。"
        decision["director_reason"] = "把声音缺失转成周的主观压力，并延迟交出回应。"
        refresh_confirmation_digests(draft)
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

    def test_no_dialogue_scene_omits_optional_planning_fields(self) -> None:
        draft = draft_with_inherited_scene()
        scene = draft["scenes"][1]
        for key in ("dialogue_geometry", "protected_processes", "visual_turns"):
            scene["directing_plan"].pop(key, None)
        draft["shot_plan"]["planned_units"][2].pop("dialogue_design", None)
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

    def test_renderer_uses_reference_six_column_idiom_without_prompt(self) -> None:
        built, _, _ = self.build()
        rows = delivery.storyboard_rows(built)
        self.assertEqual(len(rows[0]), 6)
        self.assertTrue(rows[0][2].startswith("B001～"))
        self.assertNotIn("人物：", rows[0][2])
        self.assertRegex(rows[0][4], r"^【[^｜]+｜[^｜]+｜[^】]+】")
        self.assertIn("\n【画面内容】", rows[0][4])
        self.assertNotIn("\n【机位与构图】", rows[0][4])
        self.assertNotIn("\n【镜头结束】", rows[0][4])
        self.assertNotIn("\n【场景首镜站位】", rows[0][4])
        self.assertNotIn("duration", rows[0][4].casefold())
        self.assertNotIn("coverage", rows[0][4].casefold())
        self.assertNotIn("side_a", rows[0][4])
        self.assertFalse(any("prompt" in key.casefold() for key in built))

    def test_scene_duration_metadata_and_wrong_addressee_are_hard_failures(self) -> None:
        draft = valid_draft()
        draft["scenes"][0]["scene"] = "15-1 房间 日 内（约1分钟）"
        draft["shots"][0]["dialogue"][0]["addressee"] = "陌生人"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("SCENE_DURATION_ESTIMATE", issue_codes(result))
        self.assertIn("DIALOGUE_ADDRESSEE", issue_codes(result))

    def test_coverage_evidence_must_match_fact_type(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["coverage_evidence"][1] = {
            "fact_id": "F002",
            "target_path": "camera.start_frame",
            "evidence_quote": "你听见了吗？",
        }
        draft["shots"][0]["camera"]["start_frame"] += "你听见了吗？"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("COVERAGE_EVIDENCE_TYPE_MISMATCH", issue_codes(result))

    def test_viewing_decision_must_match_planned_unit_boundary(self) -> None:
        draft = valid_draft()
        draft["shot_plan"]["viewing_decisions"][1]["mode"] = "hold"
        draft["shot_plan"]["viewing_decisions"][1]["reframe_method"] = None
        draft["shot_plan"]["viewing_decisions"][1][
            "non_cut_basis"
        ] = "listener_ownership"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("VIEWING_DECISION_HOLD_UNIT", issue_codes(result))

        draft = valid_draft()
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("VIEWING_DECISION_CUT_UNIT", issue_codes(result))

    def test_same_moment_director_required_facts_share_one_isolation_group(self) -> None:
        draft = valid_draft()
        for fact in draft["beats"][1]["facts"]:
            fact["shot_isolation"] = "director_required"
            fact["isolation_reason"] = "动作与回答发生在同一物理瞬间，需要共同获得独立视觉重心。"
            fact["isolation_group_id"] = "IG001"
        draft["shots"][1]["cut_design"]["isolation_intent"] = "director_required"
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("FACT_ISOLATION", issue_codes(result))
        self.assertNotIn("ISOLATION_GROUP_MOMENT", issue_codes(result))

    def test_source_reuse_requires_exact_adjacent_structural_declaration(self) -> None:
        draft = valid_draft()
        repeated = copy.deepcopy(draft["shot_plan"]["planned_units"][0]["source_spans"])
        draft["shot_plan"]["planned_units"][1]["source_spans"] = repeated
        draft["shot_plan"]["planned_units"][1]["source_reuse"] = {
            "from_plan_unit_id": "PU001",
            "reason": "simultaneous_isolation",
            "justification": "同一瞬间有两个无法在同一构图中同时清楚呈现的独立事实。",
        }
        result = delivery.validate_data(self.prepared(draft))
        reuse_codes = {
            "SOURCE_REUSE_UNDECLARED",
            "SOURCE_REUSE_PREVIOUS",
            "SOURCE_REUSE_SPANS",
            "SOURCE_REUSE_REASON",
        }
        self.assertFalse(issue_codes(result) & reuse_codes)

    def test_dialogue_punctuation_split_is_detected_without_full_contract(self) -> None:
        locked_text = "你听见了，为什么不说？"
        left = {"type": "dialogue", "speaker": "林", "source_spans": [{"start": 0, "end": 4}]}
        right = {
            "type": "dialogue",
            "speaker": "林",
            "source_spans": [{"start": 5, "end": len(locked_text)}],
        }
        data = {
            "shots": [
                {
                    "scene_id": "SC001",
                    "source_spans": left["source_spans"],
                    "covered_fact_ids": ["F001"],
                    "visible_characters": ["林"],
                    "camera": {
                        "shot_size": "近景",
                        "position": "门边",
                        "composition": "林在画面左侧",
                        "movement": "固定镜头",
                    },
                },
                {
                    "scene_id": "SC001",
                    "source_spans": right["source_spans"],
                    "covered_fact_ids": ["F002"],
                    "visible_characters": ["林"],
                    "camera": {
                        "shot_size": "中近景",
                        "position": "门边正侧",
                        "composition": "林在画面右侧",
                        "movement": "固定镜头",
                    },
                },
            ]
        }
        result = delivery.ValidationResult()
        delivery.validate_quality_audits(
            data,
            locked_text=locked_text,
            fact_lookup={"F001": left, "F002": right},
            result=result,
        )
        self.assertIn("DIALOGUE_PUNCTUATION_SPLIT", issue_codes(result))

    def test_first_shot_strategy_is_open_and_carried_by_scene_plan(self) -> None:
        draft = valid_draft()
        self.assertNotIn("first_shot_anchor_type", draft["scenes"][0])
        draft["scenes"][0]["directing_plan"]["pov_flow"] = [
            "先让门外声音建立威胁",
            "延迟交代完整空间",
        ]
        draft["shot_plan"]["planned_units"][0][
            "narrative_purpose"
        ] = "以声音和门口细节先行，延迟揭示两人关系。"
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

    def test_portable_ep15_fixture_locks_shenye_vo_identity(self) -> None:
        fixture = json.loads(EP15_FAILURE_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["voice_identity"]["speaker"], "沈夜")
        self.assertEqual(fixture["voice_identity"]["script_voice_type"], "vo")
        self.assertEqual(fixture["voice_identity"]["text"], "晓彤——")

    def test_tests_use_system_temp_and_leave_no_skill_artifacts(self) -> None:
        skill_root = SCRIPT_DIR.parent
        self.assertFalse(str(self.root).startswith(str(skill_root)))
        self.assertEqual(list(skill_root.glob(".test-*")), [])
        self.assertEqual(list(skill_root.rglob("__pycache__")), [])

    def test_final_shot_requires_scene_end(self) -> None:
        draft = valid_draft()
        draft["shots"][-1]["transition_to_next"]["type"] = "cut"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("FINAL_TRANSITION", issue_codes(result))

    def test_v240_allows_over_shoulder_and_same_axis_reply(self) -> None:
        prepared = self.prepared()
        first, second = prepared["shots"]
        self.assertEqual(first["camera"]["framing_mode"], "over_shoulder")
        self.assertEqual(first["speaker_presentation"][0]["presentation"], "primary_face")
        self.assertEqual(first["camera"]["foreground_characters"], ["周"])
        self.assertEqual(second["speaker_presentation"][0]["speaker"], "周")
        self.assertEqual(
            first["continuity"]["axis_side"],
            second["continuity"]["axis_side"],
        )
        result = delivery.validate_data(prepared)
        self.assertFalse(result.errors)

    def test_face_readability_is_optional_director_choice(self) -> None:
        facts = [
            {"speaker": "A", "delivery": "onscreen"},
            {"speaker": "B", "delivery": "onscreen"},
        ]
        scene = {"axes": [{"axis_id": "AX001"}]}
        design = {
            "mode": "shared_two_shot",
            "speaker_sequence": ["A", "B"],
            "face_readable_speakers": ["A", "B"],
            "listener_reaction_characters": [],
            "axis_id": "AX001",
            "justification": "双人中景同时保留两张可读面孔。",
        }
        result = delivery.ValidationResult()
        delivery.validate_dialogue_design(
            design,
            path="$.unit.dialogue_design",
            dialogue_facts=facts,
            scene=scene,
            result=result,
        )
        self.assertFalse(result.errors)
        broken = copy.deepcopy(design)
        broken["face_readable_speakers"] = ["A"]
        result = delivery.ValidationResult()
        delivery.validate_dialogue_design(
            broken,
            path="$.unit.dialogue_design",
            dialogue_facts=facts,
            scene=scene,
            result=result,
        )
        self.assertFalse(result.errors)

    def test_dialogue_mode_is_open_and_can_describe_delayed_reverse(self) -> None:
        result = delivery.ValidationResult()
        delivery.validate_dialogue_design(
            {
                "mode": "delay_reverse_until_silence_breaks",
                "speaker_sequence": ["A", "B"],
                "justification": "A 发言时留在 B；B 的沉默结束后才改变观察位置。",
            },
            path="$.unit.dialogue_design",
            dialogue_facts=[
                {"speaker": "A", "delivery": "onscreen"},
                {"speaker": "B", "delivery": "onscreen"},
            ],
            scene={"axes": []},
            result=result,
        )
        self.assertFalse(result.errors)

    def test_three_speaker_design_rejects_single_speaker_cover_claim(self) -> None:
        facts = [
            {"speaker": "A", "delivery": "onscreen"},
            {"speaker": "B", "delivery": "onscreen"},
            {"speaker": "C", "delivery": "onscreen"},
        ]
        scene = {"axes": [{"axis_id": "AX001"}]}
        invalid = {
            "mode": "single_speaker",
            "speaker_sequence": ["A", "B", "C"],
            "face_readable_speakers": ["A"],
            "listener_reaction_characters": ["B", "C"],
            "axis_id": "AX001",
            "justification": "错误地用单一近景承载三人发言。",
        }
        result = delivery.ValidationResult()
        delivery.validate_dialogue_design(
            invalid,
            path="$.unit.dialogue_design",
            dialogue_facts=facts,
            scene=scene,
            result=result,
        )
        self.assertIn("DIALOGUE_PLAN_CAMERA_MISMATCH", issue_codes(result))
        valid = copy.deepcopy(invalid)
        valid["mode"] = "shared_multi_shot"
        valid["face_readable_speakers"] = ["A", "B", "C"]
        valid["listener_reaction_characters"] = []
        valid["justification"] = "多人中景同时保持三张可读面孔。"
        result = delivery.ValidationResult()
        delivery.validate_dialogue_design(
            valid,
            path="$.unit.dialogue_design",
            dialogue_facts=facts,
            scene=scene,
            result=result,
        )
        self.assertFalse(result.errors)

    def test_continuous_reframe_metadata_is_valid_but_not_a_cut_authority(self) -> None:
        facts = [
            {"speaker": "A", "delivery": "onscreen"},
            {"speaker": "B", "delivery": "onscreen"},
            {"speaker": "C", "delivery": "onscreen"},
        ]
        design = {
            "mode": "continuous_reframe",
            "speaker_sequence": ["A", "B", "C"],
            "face_readable_speakers": ["A", "B", "C"],
            "listener_reaction_characters": ["A", "B"],
            "axis_id": "AX001",
            "justification": "镜内移动依次把三位说话者置于可读主位。",
        }
        result = delivery.ValidationResult()
        delivery.validate_dialogue_design(
            design,
            path="$.unit.dialogue_design",
            dialogue_facts=facts,
            scene={"axes": [{"axis_id": "AX001"}]},
            result=result,
        )
        self.assertFalse(result.errors)
        self.assertIn(
            "周",
            valid_draft()["shot_plan"]["planned_units"][0]["dialogue_design"][
                "listener_reaction_characters"
            ],
        )

    def test_formal_execution_text_rejects_legacy_parallel_authority(self) -> None:
        draft = valid_draft()
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("EXECUTION_AUTHORITY", issue_codes(result))
        shot = draft["shots"][1]
        shot["execution_passages"] = [
            {
                "passage_id": "XP002",
                "timing": "TB01",
                "kind": "performance",
                "character": "周",
                "fact_ids": ["F003"],
                "text": "周抬眼，握紧钥匙。",
            },
            {
                "passage_id": "XP003",
                "timing": "TB01",
                "kind": "dialogue_exchange",
                "character": "周",
                "fact_ids": ["F004"],
                "text": "周对林说：“听见了。”",
            },
        ]
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("EXECUTION_AUTHORITY", issue_codes(result))

    def test_scene_plan_is_required_but_camera_language_stays_directorial(self) -> None:
        draft = valid_draft()
        del draft["scenes"][0]["directing_plan"]
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("SCENE_DIRECTING_PLAN_MISSING", issue_codes(result))
        draft = valid_draft()
        draft["shots"][0]["camera"]["angle"] = "周肩后平视"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("CAMERA_ANGLE_ROLE_CONFLICT", issue_codes(result))
        draft = valid_draft()
        draft["shots"][0]["camera"]["movement"] = "固定镜头"
        draft["shots"][0]["camera"]["logic"] = "沿既定轴线推进到林的正脸。"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("CAMERA_LOGIC_CONTRADICTION", issue_codes(result))
        draft = valid_draft()
        camera = draft["shots"][0]["camera"]
        camera["logic"] = (
            f"{camera['angle']}，{camera['shot_size']}，{camera['movement']}；"
            "从周肩后同轴观察林。"
        )
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("CAMERA_LOGIC_DUPLICATION", issue_codes(result))
        draft = valid_draft()
        draft["shots"][0]["camera"]["movement"] = "从周肩后拍林正脸"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("CAMERA_MOVEMENT_ROLE_CONFLICT", issue_codes(result))

    def test_foreground_speaker_is_legal_and_execution_failures_remain_explicit(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["speaker_presentation"][0]["presentation"] = "foreground_back"
        draft["shot_plan"]["planned_units"][0]["dialogue_design"].pop(
            "face_readable_speakers",
            None,
        )
        draft["shots"][0]["camera"]["foreground_characters"] = ["林"]
        draft["shots"][0]["camera"]["primary_subjects"] = ["周"]
        draft["shots"][0]["camera"]["secondary_subjects"] = ["林"]
        draft["shots"][0]["camera"]["position"] = "林右肩后"
        draft["shots"][0]["camera"]["composition"] = "林肩背在前景，周位于画面深处"
        draft["shots"][0]["camera"]["logic"] = "朝向周，保持林周视线轴同侧"
        draft["shot_plan"]["planned_units"][0]["visual_plan"].update(
            {
                "primary_subjects": ["周"],
                "secondary_subjects": ["林"],
                "camera_position": "林右肩后",
                "framing_relation": "林肩背在前景，周位于画面深处",
            }
        )
        refresh_confirmation_digests(draft)
        draft["shots"][0]["execution_text"] = (
            "【画面内容】室内安静，摄影机位于林右肩后，朝向周，保持林周视线轴同侧；"
            "画面中林肩背在前景，周位于画面深处。林问：“你听见了吗？”，"
            "周维持警觉，呼吸浅而稳。"
        )
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)
        draft = valid_draft()
        draft["shots"][0]["execution_text"] = (
            "【画面内容】室内安静，摄影机位于周左肩后，朝向林，保持林周视线轴同侧；"
            "画面中林在门口，周肩背在前景。周维持警觉，呼吸浅而稳。"
        )
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("EXECUTION_DIALOGUE_NOT_VERBATIM", issue_codes(result))
        draft = valid_draft()
        draft["shots"][0]["execution_text"] = (
            "【画面内容】室内安静，摄影机位于周左肩后，朝向林，保持林周视线轴同侧；"
            "画面中林在门口，周肩背在前景。林问：“你听见了吗？”\n"
            "【画面内容】周保持警觉。"
        )
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("EXECUTION_SECTION_STRUCTURE", issue_codes(result))

    def test_offscreen_speaker_can_hold_on_listener(self) -> None:
        result = delivery.ValidationResult()
        delivery.validate_speaker_presentation(
            [{"fact_id": "F001", "speaker": "A", "presentation": "not_visible"}],
            path="$.shot.speaker_presentation",
            dialogue=[{"fact_id": "F001", "speaker": "A", "shot_delivery": "os"}],
            camera={
                "framing_mode": "single",
                "primary_subjects": ["B"],
                "foreground_characters": [],
            },
            dialogue_design={
                "speaker_sequence": ["A"],
                "justification": "留在 B 的倾听反应，让 A 的声音从画外施压。",
            },
            result=result,
        )
        self.assertFalse(result.errors)

    def test_onscreen_occluded_speaker_can_hold_on_listener(self) -> None:
        result = delivery.ValidationResult()
        delivery.validate_speaker_presentation(
            [
                {
                    "fact_id": "F001",
                    "speaker": "A",
                    "presentation": "onscreen_occluded",
                }
            ],
            path="$.shot.speaker_presentation",
            dialogue=[{"fact_id": "F001", "speaker": "A", "shot_delivery": "onscreen"}],
            camera={
                "framing_mode": "single",
                "primary_subjects": ["B"],
                "foreground_characters": [],
            },
            dialogue_design={
                "mode": "hold_on_listener",
                "speaker_sequence": ["A"],
                "justification": "A 留在遮挡中发言，观看重点维持在 B。",
            },
            result=result,
        )
        self.assertFalse(result.errors)

    def test_actual_ep15_v210_cannot_pass_v240_contract(self) -> None:
        data = valid_draft()
        data["contract_version"] = "2.5.0"
        data["source_skill_version"] = "2.5.0"
        result = delivery.validate_data(delivery.prepare_data(data))
        self.assertIn("CONTRACT_IDENTITY", issue_codes(result))

    def test_camera_angle_rejects_context_contamination(self) -> None:
        for contaminated_angle in (
            "车内平视",
            "远距离平视",
            "长焦平视",
            "背面平视",
            "车窗主观平视",
        ):
            draft = valid_draft()
            draft["shots"][0]["camera"]["angle"] = contaminated_angle
            result = delivery.validate_data(self.prepared(draft))
            self.assertIn(
                "CAMERA_ANGLE_PURITY",
                issue_codes(result),
                contaminated_angle,
            )

        for pure_angle in ("平视", "略高平视", "微俯视", "低机位平视"):
            draft = valid_draft()
            draft["shots"][0]["camera"]["angle"] = pure_angle
            result = delivery.validate_data(self.prepared(draft))
            self.assertNotIn("CAMERA_ANGLE_PURITY", issue_codes(result), pure_angle)

    def test_renderer_exposes_geometry_without_injecting_framing_mode(self) -> None:
        draft = valid_draft()
        built = self.prepared(draft)
        description = built["shots"][0]["rendered_shot_description"]
        camera = built["shots"][0]["camera"]
        self.assertNotIn(camera["composition"], description.splitlines()[0])
        self.assertIn("周肩背在前景", description)
        self.assertIn("林正脸占据画面", description)
        self.assertNotIn("主位", description)
        self.assertTrue(description.startswith("【中近景｜平视｜缓慢推进后固定】"))
        self.assertNotIn("过肩中近景", description)

        draft["shots"][0]["camera"]["framing_mode"] = "subjective"
        draft["shots"][0]["camera"]["foreground_characters"] = []
        built = self.prepared(draft)
        self.assertTrue(
            built["shots"][0]["rendered_shot_description"].startswith(
                "【中近景｜平视｜"
            )
        )
        self.assertNotIn("主观中近景", built["shots"][0]["rendered_shot_description"])

    def test_renderer_standardizes_pure_three_part_camera_header(self) -> None:
        shot = valid_draft()["shots"][0]
        shot["camera"]["angle"] = "微仰视"
        shot["camera"]["shot_size"] = "中景→特写"
        shot["camera"]["framing_mode"] = "single"
        shot["camera"]["movement"] = "缓慢推进"
        self.assertTrue(
            delivery.render_shot_description(shot).startswith(
                "【中景→特写｜微仰视｜缓慢推进】\n【画面内容】"
            )
        )
        shot["camera"]["angle"] = "平视"
        shot["camera"]["shot_size"] = "全景"
        shot["camera"]["movement"] = "固定镜头"
        self.assertTrue(
            delivery.render_shot_description(shot).startswith(
                "【全景｜平视｜固定】\n【画面内容】"
            )
        )

    def test_station_move_is_integrated_into_picture_content(self) -> None:
        draft = valid_draft()
        shot = draft["shots"][0]
        shot["continuity_updates"] = [
            {
                "entity_type": "character",
                "entity": "林",
                "field": "position",
                "from": "门口",
                "to": "桌边",
                "evidence_fact_ids": ["F001"],
            }
        ]
        shot["blocking"][0]["end_position"] = "桌边"
        shot["execution_text"] = (
            "【画面内容】室内安静，摄影机位于周左肩后，朝向林，保持林周视线轴同侧；"
            "画面中林在门口，周肩背在前景。林问：“你听见了吗？”，随后林从门口走到桌边，"
            "落位后仍面向周；周保持坐姿，目光跟随林的移动。"
        )
        prepared = delivery.prepare_data(draft)
        description = prepared["shots"][0]["rendered_shot_description"]
        result = delivery.validate_data(prepared)
        self.assertIn("林从门口走到桌边", description)
        self.assertNotIn("【站位位移】", description)
        self.assertNotIn("周仍在", description)
        self.assertNotIn("CONTINUITY_UPDATE_NOT_VISIBLE", issue_codes(result))

    def test_source_only_execution_fails_but_blank_optional_notes_are_valid(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["execution_text"] = (
            "【画面内容】林站在门口，周坐在桌边。林问：“你听见了吗？”"
        )
        draft["shots"][0]["notes"] = ""
        prepared = self.prepared(draft)
        result = delivery.validate_data(prepared)
        codes = issue_codes(result)
        self.assertIn("EXECUTION_SOURCE_PARAPHRASE_ONLY", codes)
        self.assertNotIn("SHOT_NOTE_REQUIRED", codes)
        self.assertEqual(prepared["shots"][0]["notes"], "")

    def test_visible_machine_id_is_rejected_even_next_to_chinese(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["camera"]["position"] = "周右肩后、AX001同侧"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("VISIBLE_MACHINE_STATE", issue_codes(result))

    def test_camera_logic_accepts_geometry_and_director_intent_language(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["camera"]["logic"] = "朝向林，保持林周视线轴同侧"
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("CAMERA_LOGIC_NON_GEOMETRIC", issue_codes(result))

        draft["shots"][0]["camera"]["logic"] = "为了强调林的反应，让周只作为前景。"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("CAMERA_LOGIC_NON_GEOMETRIC", issue_codes(result))

    def test_over_shoulder_position_must_match_foreground_character(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["camera"]["position"] = "林正侧近处"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("CAMERA_POSITION_FRAMING_MISMATCH", issue_codes(result))

    def test_reversible_performance_is_allowed_without_source_proof(self) -> None:
        draft = valid_draft()
        camera = draft["shots"][0]["camera"]
        draft["shots"][0]["execution_text"] = (
            "【画面内容】室内安静，"
            f"摄影机位于{camera['position']}，{camera['logic']}；"
            f"画面中{camera['composition'].replace('为主位', '占据画面')}。"
            "林先吸一口气，再问：“你听见了吗？”；周保持坐姿倾听，现场声压低，"
            "问题落下后周接住林的视线。"
        )
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("EXECUTION_UNSOURCED_DETAIL", issue_codes(result))
        self.assertFalse(result.errors)

        draft = valid_draft()
        draft["shots"][0]["performance"]["visible_behavior"].append("周的呼吸放慢")
        camera = draft["shots"][0]["camera"]
        draft["shots"][0]["execution_text"] = (
            "【画面内容】室内安静，"
            f"摄影机位于{camera['position']}，{camera['logic']}；"
            f"画面中{camera['composition'].replace('为主位', '占据画面')}。"
            "周的呼吸放慢，视线停在林身上；林问：“你听见了吗？”，"
            "周尚未回答，沉默停留在两人之间。"
        )
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("EXECUTION_UNSOURCED_DETAIL", issue_codes(result))
        self.assertFalse(result.errors)

        draft = valid_draft()
        camera = draft["shots"][0]["camera"]
        draft["shots"][0]["execution_text"] = (
            "【画面内容】室内安静，"
            f"摄影机位于{camera['position']}，{camera['logic']}；"
            f"画面中{camera['composition'].replace('为主位', '占据画面')}。"
            "林问：“你听见了吗？”；周不抢答，只让呼吸和目光可见，问题落下后仍未回答。"
        )
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn(
            "EXECUTION_META_LANGUAGE",
            {issue.code for issue in result.warnings},
        )

    def test_actual_ep15_v220_is_negative_regression_for_fifth_column(self) -> None:
        fixture = json.loads(EP15_FAILURE_FIXTURE.read_text(encoding="utf-8"))
        draft = valid_draft()
        draft["shots"][0]["execution_text"] += fixture["known_template_phrases"][0]
        result = delivery.validate_data(delivery.prepare_data(draft))
        self.assertIn("TEMPLATE_PLACEHOLDER", issue_codes(result))

    def test_actual_ep15_v230_is_negative_regression_for_visible_camera_language(self) -> None:
        fixture = json.loads(EP15_FAILURE_FIXTURE.read_text(encoding="utf-8"))
        draft = valid_draft()
        draft["shots"][0]["execution_text"] += fixture["known_template_phrases"][1]
        result = delivery.validate_data(delivery.prepare_data(draft))
        self.assertIn("TEMPLATE_PLACEHOLDER", issue_codes(result))

    def test_gate_flow_has_only_two_confirmations_and_auto_advances(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        profile_text = (SKILL_ROOT / "references" / "director-profile.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("绑定成功后自动进入并展示 Gate 2，不等待“继续”", skill_text)
        self.assertIn("并自动生成最终交付，不等待“继续”", skill_text)
        self.assertIn("正常流程不得插入“继续”或第三次确认", skill_text)
        self.assertIn("候选选择不是 Gate，Gate 1 只确认一次", profile_text)

    def test_entry_strategy_is_required_and_bound_to_gate_2_digest(self) -> None:
        draft = valid_draft()
        original_digest = delivery.stage_digest(draft, 2)
        draft["scenes"][0]["directing_plan"]["entry_strategy"]["reason"] = (
            "改为让人物关系先于空间信息进入。"
        )
        self.assertNotEqual(original_digest, delivery.stage_digest(draft, 2))
        result = delivery.validate_data(delivery.prepare_data(draft))
        self.assertIn("CONFIRMATION_DIGEST", issue_codes(result))

        draft = valid_draft()
        del draft["scenes"][0]["directing_plan"]["entry_strategy"]
        refresh_confirmation_digests(draft)
        result = delivery.validate_data(delivery.prepare_data(draft))
        self.assertIn("SCENE_ENTRY_STRATEGY", issue_codes(result))

    def test_entry_strategy_semantics_remain_agent_and_gate_review(self) -> None:
        draft = valid_draft()
        entry = draft["scenes"][0]["directing_plan"]["entry_strategy"]
        entry.update(
            {
                "mode": "spatial_establish",
                "observer_position": "房间外部，先看清门口与桌边关系",
                "required_spatial_information": ["门口与桌边的完整空间关系"],
                "withheld_information": [],
                "reason": "问话前必须先让两人的距离可读",
            }
        )
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("SCENE_ENTRY_STRATEGY_MISMATCH", issue_codes(result))

        draft["shots"][0]["camera"]["shot_size"] = "全景"
        draft["shots"][0]["camera"]["framing_mode"] = "environment"
        draft["shots"][0]["camera"]["primary_subjects"] = []
        draft["shots"][0]["camera"]["foreground_characters"] = []
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("SCENE_ENTRY_STRATEGY_MISMATCH", issue_codes(result))

    def test_rear_center_car_entry_has_no_keyword_gate(self) -> None:
        draft = valid_draft()
        entry = draft["scenes"][0]["directing_plan"]["entry_strategy"]
        entry.update(
            {
                "mode": "relational_entry",
                "observer_position": "汽车后排中央",
                "required_spatial_information": ["驾驶者与副驾驶的座位关系"],
                "withheld_information": [],
                "reason": "同时看到两人和背景",
            }
        )
        camera = draft["shots"][0]["camera"]
        camera["position"] = "后排中央略偏副驾驶一侧"
        camera["framing_mode"] = "two_shot"
        camera["primary_subjects"] = ["林", "周"]
        camera["foreground_characters"] = []
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("MOVING_CAR_REAR_CENTER_DEFAULT", issue_codes(result))

        entry["reason"] = "利用后排距离制造两人关系的疏离感。"
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("MOVING_CAR_REAR_CENTER_DEFAULT", issue_codes(result))

    def test_camera_triad_rejects_mixed_size_and_movement_content(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["camera"]["shot_size"] = "车内双人中景"
        draft["shots"][0]["camera"]["movement"] = "固定车载机位，背景自然流动"
        result = delivery.validate_data(self.prepared(draft))
        codes = issue_codes(result)
        self.assertIn("CAMERA_SHOT_SIZE_PURITY", codes)
        self.assertIn("CAMERA_MOVEMENT_PURITY", codes)

        description = self.prepared(valid_draft())["shots"][0][
            "rendered_shot_description"
        ].splitlines()[0]
        self.assertEqual(description.count("｜"), 2)

    def test_moving_plan_requires_trigger_path_and_end_condition(self) -> None:
        draft = valid_draft()
        movement_plan = draft["shot_plan"]["planned_units"][0]["visual_plan"][
            "movement_plan"
        ]
        movement_plan["path"] = ""
        refresh_confirmation_digests(draft)
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("STRING_REQUIRED", issue_codes(result))

    def test_multiscene_single_angle_requires_structured_review(self) -> None:
        scenes = {}
        planned_units = []
        for scene_index in range(2):
            scene_id = f"SC{scene_index + 1:03d}"
            scenes[scene_id] = {
                "scene_id": scene_id,
                "directing_plan": {
                    "style_anchors": [
                        {
                            "style_anchor_id": f"SA{scene_index + 1:03d}",
                        }
                    ]
                },
            }
            for shot_index in range(1):
                planned_units.append(
                    {
                        "scene_id": scene_id,
                        "visual_plan": {
                            "angle": "平视",
                            "shot_size": "中景",
                            "movement_plan": {"class": "fixed"},
                        },
                    }
                )
        result = delivery.ValidationResult()
        delivery.validate_visual_uniformity_reviews(
            {
                "shot_plan": {
                    "planned_units": planned_units,
                    "visual_uniformity_reviews": [],
                }
            },
            scenes=scenes,
            review_mode=False,
            result=result,
        )
        self.assertIn(
            "VISUAL_UNIFORMITY_REVIEW_REQUIRED",
            issue_codes(result),
        )

    def test_visual_plan_is_required_and_rejects_unknown_fields(self) -> None:
        draft = valid_draft()
        del draft["shot_plan"]["planned_units"][0]["visual_plan"]
        refresh_confirmation_digests(draft)
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("PLAN_UNIT_FIELD_MISSING", issue_codes(result))

        draft = valid_draft()
        draft["shot_plan"]["planned_units"][0]["visual_plan"][
            "composition"
        ] = "最终构图不应在规划结构中另设第二权威"
        refresh_confirmation_digests(draft)
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("VISUAL_PLAN_FIELD_UNKNOWN", issue_codes(result))

    def test_style_anchor_must_match_confirmed_director_profile(self) -> None:
        draft = valid_draft()
        draft["scenes"][0]["directing_plan"]["style_anchors"][0][
            "profile_basis"
        ][0]["value"] = "不存在于已确认 profile 的优先级"
        refresh_confirmation_digests(draft)
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("STYLE_ANCHOR_PROFILE_MISMATCH", issue_codes(result))

        draft = valid_draft()
        draft["scenes"][0]["directing_plan"]["style_anchors"][0][
            "surface_imitation"
        ] = "未定义的风格捷径"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("STYLE_ANCHOR_FIELD_UNKNOWN", issue_codes(result))

        draft = valid_draft()
        draft["shot_plan"]["planned_units"][0]["visual_plan"][
            "style_anchor_ids"
        ] = ["SA999"]
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("VISUAL_PLAN_STYLE_ANCHOR", issue_codes(result))

    def test_visual_plan_change_invalidates_gate_2_digest(self) -> None:
        draft = valid_draft()
        draft["shot_plan"]["planned_units"][0]["visual_plan"]["angle"] = "微俯视"
        result = delivery.validate_data(delivery.prepare_data(draft))
        self.assertIn("CONFIRMATION_DIGEST", issue_codes(result))

    def test_final_camera_must_match_confirmed_visual_plan(self) -> None:
        mutations = (
            ("angle", "微俯视"),
            ("shot_size", "近景"),
            ("position", "林正前方"),
            ("composition", "林单人居中"),
            ("viewpoint_owner", "客观观察"),
            ("primary_subjects", ["周"]),
            ("secondary_subjects", []),
            ("perspective_intent", "compressed_distance"),
            ("focus_plan", "焦点只停在背景门框。"),
            (
                "spatial_strategy",
                {
                    "type": "compressed_depth",
                    "description": "压缩门口与桌边距离。",
                },
            ),
            (
                "movement_plan",
                {
                    "class": "fixed",
                    "trigger": "",
                    "speed": "",
                    "path": "",
                    "end_condition": "",
                    "hold_reason": "保持完整问话。",
                },
            ),
            ("start_frame", "只见门框，不见人物。"),
            ("end_frame", "切到空房间。"),
            ("motivation", "增加变化。"),
            ("movement", "固定"),
        )
        for field_name, value in mutations:
            with self.subTest(field=field_name):
                draft = valid_draft()
                draft["shots"][0]["camera"][field_name] = value
                result = delivery.validate_data(self.prepared(draft))
                self.assertIn(
                    "SHOT_VISUAL_PLAN_MISMATCH",
                    issue_codes(result),
                )

    def test_director_profile_requires_every_closed_axis(self) -> None:
        for field_name in (
            "rhythm",
            "camera_energy",
            "visual_distance",
            "performance_focus",
            "space_strategy",
            "transition_language",
        ):
            with self.subTest(field=field_name):
                draft = valid_draft()
                del draft["director_profile"][field_name]
                del draft["director_style_options"][0]["profile"][field_name]
                refresh_confirmation_digests(draft)
                result = delivery.validate_data(self.prepared(draft))
                self.assertIn(
                    "DIRECTOR_PROFILE_FIELD_MISSING",
                    issue_codes(result),
                )

    def test_event_and_phase_lists_cannot_be_reversed_together(self) -> None:
        draft = valid_draft()
        unit = draft["shot_plan"]["planned_units"][0]
        unit["screen_event_ids"].reverse()
        phases = draft["shots"][0]["shot_phases"]
        phases.reverse()
        for index, phase in enumerate(phases, start=1):
            phase["phase_order"] = index
        refresh_confirmation_digests(draft)
        result = delivery.validate_data(self.prepared(draft))
        codes = issue_codes(result)
        self.assertIn("PLAN_UNIT_SCREEN_EVENT_ORDER", codes)
        self.assertIn("SHOT_PHASE_EVENT_ORDER", codes)

    def test_screen_event_beats_must_match_covered_fact_ownership(self) -> None:
        draft = valid_draft()
        draft["screen_events"][0]["beat_ids"] = ["B002"]
        refresh_confirmation_digests(draft)
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn(
            "SCREEN_EVENT_FACT_BEAT_MISMATCH",
            issue_codes(result),
        )

    def test_dominance_thresholds_catch_near_collapse(self) -> None:
        cases = {
            "eight_of_nine": ["平视"] * 8 + ["微仰视"],
            "nine_of_eleven": ["平视"] * 9 + ["微俯视", "微仰视"],
            "four_of_four": ["平视"] * 4,
            "forty_three_of_fifty_four": ["平视"] * 43 + ["微俯视"] * 11,
        }
        for label, angles in cases.items():
            with self.subTest(case=label):
                data, _ = visual_audit_fixture(angles)
                findings = [
                    finding
                    for finding in delivery.visual_uniformity_findings(data)
                    if finding["dimension"] == "angle"
                ]
                self.assertTrue(findings)
                self.assertTrue(
                    any(
                        finding["dominant_value"] == "平视"
                        for finding in findings
                    )
                )
        data, _ = visual_audit_fixture(
            ["平视", "微俯视", "微仰视"] * 3,
            movement_classes=["fixed"] * 8 + ["push"],
        )
        movement_findings = [
            finding
            for finding in delivery.visual_uniformity_findings(data)
            if finding["scope"] == "project"
            and finding["dimension"] == "movement_class"
        ]
        self.assertEqual(movement_findings[0]["dominant_value"], "fixed")
        self.assertEqual(movement_findings[0]["dominant_count"], 8)
        self.assertEqual(movement_findings[0]["total_count"], 9)

    def test_structured_uniformity_review_allows_intentional_angle_language(self) -> None:
        data, scenes = visual_audit_fixture(
            ["平视"] * 4,
            movement_classes=["fixed", "push", "pull", "handheld"],
        )
        data["shot_plan"]["visual_uniformity_reviews"] = [
            {
                "review_id": "VR001",
                "scope": "scene",
                "scene_id": "SC001",
                "dimension": "angle",
                "dominant_value": "平视",
                "reason": "保持人物眼线平等，让压迫只由停顿和距离变化产生。",
                "style_anchor_ids": ["SA001"],
            }
        ]
        result = delivery.ValidationResult()
        delivery.validate_visual_uniformity_reviews(
            data,
            scenes=scenes,
            review_mode=False,
            result=result,
        )
        self.assertFalse(result.errors)
        summary = delivery.visual_distribution_summary(data)
        self.assertEqual(
            summary["confirmed_uniformity_reviews"][0]["review_id"],
            "VR001",
        )

    def test_unused_or_generic_uniformity_review_is_rejected(self) -> None:
        data, scenes = visual_audit_fixture(
            ["平视", "微俯视", "微仰视", "仰视"],
            movement_classes=["fixed", "push", "pull", "handheld"],
        )
        data["shot_plan"]["visual_uniformity_reviews"] = [
            {
                "review_id": "VR001",
                "scope": "scene",
                "scene_id": "SC001",
                "dimension": "angle",
                "dominant_value": "平视",
                "reason": "风格需要",
                "style_anchor_ids": ["SA001"],
            }
        ]
        result = delivery.ValidationResult()
        delivery.validate_visual_uniformity_reviews(
            data,
            scenes=scenes,
            review_mode=False,
            result=result,
        )
        codes = issue_codes(result)
        self.assertIn("VISUAL_UNIFORMITY_REVIEW_REASON", codes)
        self.assertIn("VISUAL_UNIFORMITY_REVIEW_UNUSED", codes)

    def test_gate_2_review_is_read_only_and_returns_digest(self) -> None:
        draft = valid_draft()
        before = copy.deepcopy(draft)
        reviewed, result, digest = delivery.review_gate_2_data(draft)
        self.assertFalse(result.errors)
        self.assertFalse(result.warnings)
        self.assertRegex(digest or "", r"^[0-9a-f]{64}$")
        self.assertEqual(draft, before)
        visual_design = delivery.make_report(reviewed, result)["visual_design"]
        self.assertEqual(visual_design["project"]["planned_shots"], 2)
        self.assertIn("shot_sizes", visual_design["project"])
        self.assertEqual(
            delivery.stage_payload(draft, 2)["visual_design"],
            visual_design,
        )

    def test_review_gate_2_cli_is_read_only_and_reports_ready(self) -> None:
        draft = valid_draft()
        self.write_draft(draft)
        before = self.draft_path.read_bytes()
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "review-gate-2",
                "--input",
                str(self.draft_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "READY")
        self.assertRegex(report["gate_2_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(self.draft_path.read_bytes(), before)
        self.assertFalse(self.output_dir.exists())

    def test_review_gate_2_cli_returns_two_when_review_is_required(self) -> None:
        draft = valid_draft()
        self.write_draft(draft)
        result = delivery.ValidationResult()
        result.warn(
            "VISUAL_UNIFORMITY_REVIEW_REQUIRED",
            "$.shot_plan.visual_uniformity_reviews",
            "需要人工复核。",
        )
        output = io.StringIO()
        with mock.patch.object(
            delivery,
            "review_gate_2_data",
            return_value=(self.prepared(draft), result, "a" * 64),
        ), redirect_stdout(output):
            return_code = delivery.command_review_gate_2(
                argparse.Namespace(input=str(self.draft_path))
            )
        self.assertEqual(return_code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "REVIEW_REQUIRED")

    def test_gate_2_review_reports_unresolved_dominance_as_review_required(
        self,
    ) -> None:
        data, scenes = visual_audit_fixture(["平视"] * 8 + ["微仰视"])
        result = delivery.ValidationResult()
        delivery.validate_visual_uniformity_reviews(
            data,
            scenes=scenes,
            review_mode=True,
            result=result,
        )
        self.assertFalse(result.errors)
        self.assertIn(
            "VISUAL_UNIFORMITY_REVIEW_REQUIRED",
            {issue.code for issue in result.warnings},
        )

    def test_actual_ep15_v246_flat_angle_distribution_is_negative_regression(
        self,
    ) -> None:
        fixture = json.loads(EP15_FAILURE_FIXTURE.read_text(encoding="utf-8"))
        self.assertTrue(fixture["legal_corridor_closeups"]["space_established"])
        for shot in fixture["legal_corridor_closeups"]["shots"]:
            camera = {
                "shot_size": shot["shot_size"],
                "angle": "平视",
                "position": "走廊远端",
                "logic": "保持既定轴线同侧并匹配对方视线",
                "composition": "人物面孔单独占据画面",
                "movement": "固定",
            }
            result = delivery.ValidationResult()
            delivery.validate_camera(camera, "$.camera", result)
            self.assertNotIn("CAMERA_SCALE_POSITION_TENSION", issue_codes(result))

    def test_actual_ep15_v245_is_negative_fixture_for_250_contract(self) -> None:
        fixture = json.loads(EP15_FAILURE_FIXTURE.read_text(encoding="utf-8"))
        draft = valid_draft()
        draft["screen_events"][0]["spatial_zone"] = fixture["blocked_single_shot"][
            "spatial_zones"
        ][0]
        draft["screen_events"][1]["spatial_zone"] = fixture["blocked_single_shot"][
            "spatial_zones"
        ][1]
        draft["shot_plan"]["planned_units"][0]["screen_event_ids"] = [
            "SEV001",
            "SEV002",
        ]
        draft["shot_plan"]["viewing_decisions"][0]["mode"] = "hold"
        draft["shot_plan"]["viewing_decisions"][0]["reframe_method"] = None
        result = delivery.validate_data(delivery.prepare_data(draft))
        self.assertIn("VISUAL_PLAN_MULTI_ZONE_STRATEGY", issue_codes(result))

    def test_source_vo_identity_cannot_be_rewritten_by_shot_delivery(self) -> None:
        fact = {
            "fact_id": "F001",
            "type": "dialogue",
            "speaker": "沈夜",
            "text": "晓彤——",
            "script_voice_type": "vo",
        }
        valid = delivery.ValidationResult()
        delivery.validate_dialogue(
            [
                {
                    "fact_id": "F001",
                    "speaker": "沈夜",
                    "text": "晓彤——",
                    "shot_delivery": "vo",
                }
            ],
            path="$.dialogue",
            fact_lookup={"F001": fact},
            covered_fact_ids={"F001"},
            scene_characters={"沈夜"},
            visible_characters=set(),
            phase_ids=set(),
            result=valid,
        )
        self.assertFalse(valid.errors)

        rewritten = delivery.ValidationResult()
        delivery.validate_dialogue(
            [
                {
                    "fact_id": "F001",
                    "speaker": "沈夜",
                    "text": "晓彤——",
                    "shot_delivery": "os",
                }
            ],
            path="$.dialogue",
            fact_lookup={"F001": fact},
            covered_fact_ids={"F001"},
            scene_characters={"沈夜"},
            visible_characters=set(),
            phase_ids=set(),
            result=rewritten,
        )
        self.assertIn("DIALOGUE_VOICE_IDENTITY", issue_codes(rewritten))

    def test_scene_dialogue_may_be_os_but_cannot_become_vo(self) -> None:
        fact = {
            "fact_id": "F001",
            "type": "dialogue",
            "speaker": "林景行",
            "text": "回去吧，晓彤。",
            "script_voice_type": "scene_dialogue",
        }
        os_result = delivery.ValidationResult()
        delivery.validate_dialogue(
            [
                {
                    "fact_id": "F001",
                    "speaker": "林景行",
                    "text": "回去吧，晓彤。",
                    "shot_delivery": "os",
                }
            ],
            path="$.dialogue",
            fact_lookup={"F001": fact},
            covered_fact_ids={"F001"},
            scene_characters={"林景行"},
            visible_characters=set(),
            phase_ids=set(),
            result=os_result,
        )
        self.assertFalse(os_result.errors)

        vo_result = delivery.ValidationResult()
        delivery.validate_dialogue(
            [
                {
                    "fact_id": "F001",
                    "speaker": "林景行",
                    "text": "回去吧，晓彤。",
                    "shot_delivery": "vo",
                }
            ],
            path="$.dialogue",
            fact_lookup={"F001": fact},
            covered_fact_ids={"F001"},
            scene_characters={"林景行"},
            visible_characters=set(),
            phase_ids=set(),
            result=vo_result,
        )
        self.assertIn("DIALOGUE_VOICE_IDENTITY", issue_codes(vo_result))

    def test_reframe_requires_executable_method(self) -> None:
        draft = valid_draft()
        draft["shot_plan"]["viewing_decisions"][0]["mode"] = "reframe"
        draft["shot_plan"]["viewing_decisions"][0]["reframe_method"] = None
        result = delivery.validate_data(delivery.prepare_data(draft))
        self.assertIn("VIEWING_DECISION_REFRAME_METHOD", issue_codes(result))

    def test_every_cognitive_event_boundary_requires_a_viewing_decision(self) -> None:
        fixture = json.loads(EP15_FAILURE_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["cognitive_landings"], ["八天", "谁？"])
        draft = valid_draft()
        draft["shot_plan"]["viewing_decisions"] = []
        result = delivery.validate_data(delivery.prepare_data(draft))
        self.assertIn("VIEWING_DECISION_MISSING", issue_codes(result))

    def test_sequential_screen_events_cannot_collapse_into_one_phase(self) -> None:
        draft = valid_draft()
        draft["screen_events"][1]["temporal_relation"] = "sequential"
        draft["shots"][0]["shot_phases"][0]["screen_event_ids"] = [
            "SEV001",
            "SEV002",
        ]
        draft["shots"][0]["shot_phases"][0]["duration_seconds"] = 3
        draft["shots"][0]["shot_phases"] = draft["shots"][0]["shot_phases"][:1]
        result = delivery.validate_data(delivery.prepare_data(draft))
        self.assertIn("SHOT_PHASE_SEQUENTIAL_COLLAPSE", issue_codes(result))

    def test_visual_plan_requires_start_and_end_frames(self) -> None:
        for field_name in ("start_frame", "end_frame"):
            with self.subTest(field=field_name):
                draft = valid_draft()
                del draft["shot_plan"]["planned_units"][0]["visual_plan"][field_name]
                result = delivery.validate_data(delivery.prepare_data(draft))
                self.assertIn("VISUAL_PLAN_FIELD_MISSING", issue_codes(result))

    def test_ep15_fixture_covers_every_named_failure_shot_and_issue_code(self) -> None:
        fixture = json.loads(EP15_FAILURE_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(
            [item["shot_id"] for item in fixture["failed_shots"]],
            [
                "SH003",
                "SH004",
                "SH007",
                "SH013",
                "SH016",
                "SH018",
                "SH022",
                "SH026",
                "SH028",
                "SH029",
                "SH033",
                "SH035",
                "SH041",
            ],
        )
        self.assertEqual(
            set(fixture["required_issue_codes"]),
            {
                "SCREEN_EVENT_MULTI_SPEAKER",
                "SCREEN_EVENT_ATOMICITY_OVERLOAD",
                "DIALOGUE_HANDOFF_CUT_REQUIRED",
                "NONCUT_BASIS_REQUIRED",
                "NONCUT_VISUAL_PLAN_MISMATCH",
                "ORDINARY_SHOT_DURATION_EXCEEDED",
                "LONG_TAKE_DESIGN_REQUIRED",
                "PROTECTED_PROCESS_SCOPE_OVERREACH",
                "CAMERA_HEADER_NOT_TRIAD",
            },
        )

    def test_screen_event_rejects_multiple_speakers(self) -> None:
        draft = valid_draft()
        event = draft["screen_events"][0]
        event["beat_ids"] = ["B001", "B002"]
        event["covered_fact_ids"] = ["F002", "F004"]
        event["sound_fact_ids"] = ["F002", "F004"]
        event["source_spans"] += copy.deepcopy(
            draft["screen_events"][1]["source_spans"]
        )
        result = delivery.validate_data(self.prepared(draft))
        codes = issue_codes(result)
        self.assertIn("SCREEN_EVENT_MULTI_SPEAKER", codes)
        self.assertIn("SCREEN_EVENT_ATOMICITY_OVERLOAD", codes)

    def test_screen_event_requires_atomic_role_subject_and_scale(self) -> None:
        for field_name in ("event_role", "primary_viewing_subject", "focus_scale"):
            with self.subTest(field=field_name):
                draft = valid_draft()
                draft["screen_events"][0].pop(field_name)
                result = delivery.validate_data(self.prepared(draft))
                self.assertIn("SCREEN_EVENT_FIELD_MISSING", issue_codes(result))

    def test_non_dialogue_event_rejects_subject_and_fact_type_overload(self) -> None:
        draft = valid_draft()
        event = draft["screen_events"][0]
        event["beat_ids"] = ["B001", "B002"]
        event["covered_fact_ids"] = ["F001", "F003"]
        event["source_spans"] += copy.deepcopy(
            draft["screen_events"][2]["source_spans"]
        )
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("SCREEN_EVENT_ATOMICITY_OVERLOAD", issue_codes(result))

    def test_dialogue_handoff_defaults_to_cut(self) -> None:
        result = delivery.validate_data(self.prepared(valid_draft()))
        self.assertFalse(result.errors)
        metrics = delivery.cut_atomicity_metrics(self.prepared(valid_draft()))
        self.assertEqual(metrics["dialogue_handoffs"], 1)
        self.assertEqual(metrics["dialogue_handoffs_with_cuts"], 1)

    def test_three_speaker_sequence_reports_two_default_cut_handoffs(self) -> None:
        data = {
            "beats": [
                {
                    "facts": [
                        {
                            "fact_id": f"F{index:03d}",
                            "type": "dialogue",
                            "speaker": speaker,
                        }
                        for index, speaker in enumerate(("A", "B", "C"), start=1)
                    ]
                }
            ],
            "screen_events": [
                {
                    "screen_event_id": f"SEV{index:03d}",
                    "scene_id": "SC001",
                    "event_order": index,
                    "covered_fact_ids": [f"F{index:03d}"],
                }
                for index in range(1, 4)
            ],
            "shot_plan": {
                "planned_units": [
                    {
                        "plan_unit_id": f"PU{index:03d}",
                        "screen_event_ids": [f"SEV{index:03d}"],
                        "estimated_duration_seconds": 2,
                    }
                    for index in range(1, 4)
                ],
                "viewing_decisions": [
                    {
                        "viewing_decision_id": f"VD{index:03d}",
                        "from_screen_event_id": f"SEV{index:03d}",
                        "to_screen_event_id": f"SEV{index + 1:03d}",
                        "mode": "cut",
                        "non_cut_basis": None,
                    }
                    for index in range(1, 3)
                ],
            },
        }
        metrics = delivery.cut_atomicity_metrics(data)
        self.assertEqual(metrics["dialogue_handoffs"], 2)
        self.assertEqual(metrics["dialogue_handoffs_with_cuts"], 2)

    def test_dialogue_handoff_noncut_requires_basis(self) -> None:
        draft = merge_dialogue_turns_for_gate_2(
            valid_draft(),
            mode="hold",
            non_cut_basis=None,
        )
        _, result, _ = delivery.review_gate_2_data(draft)
        self.assertIn("NONCUT_BASIS_REQUIRED", issue_codes(result))

    def test_listener_ownership_can_justify_dialogue_noncut(self) -> None:
        draft = merge_dialogue_turns_for_gate_2(
            valid_draft(),
            mode="reframe",
            non_cut_basis="listener_ownership",
            reframe_method="scale_change",
        )
        _, result, _ = delivery.review_gate_2_data(draft)
        codes = issue_codes(result)
        self.assertNotIn("DIALOGUE_HANDOFF_CUT_REQUIRED", codes)
        self.assertNotIn("NONCUT_BASIS_REQUIRED", codes)
        self.assertNotIn("NONCUT_VISUAL_PLAN_MISMATCH", codes)

    def test_focus_scale_change_cannot_hide_inside_hold(self) -> None:
        draft = merge_dialogue_turns_for_gate_2(
            valid_draft(),
            mode="hold",
            non_cut_basis="listener_ownership",
        )
        draft["screen_events"][1]["focus_scale"] = "detail"
        _, result, _ = delivery.review_gate_2_data(draft)
        self.assertIn("NONCUT_VISUAL_PLAN_MISMATCH", issue_codes(result))

    def test_focus_scale_change_can_use_executable_reframe(self) -> None:
        draft = merge_dialogue_turns_for_gate_2(
            valid_draft(),
            mode="reframe",
            non_cut_basis="listener_ownership",
            reframe_method="scale_change",
        )
        draft["screen_events"][1]["focus_scale"] = "detail"
        visual = draft["shot_plan"]["planned_units"][0]["visual_plan"]
        visual["shot_size"] = "中近景→特写"
        _, result, _ = delivery.review_gate_2_data(draft)
        self.assertNotIn("NONCUT_VISUAL_PLAN_MISMATCH", issue_codes(result))

    def test_blocking_proof_requires_blocking_reveal_strategy(self) -> None:
        draft = merge_dialogue_turns_for_gate_2(
            valid_draft(),
            mode="hold",
            non_cut_basis="blocking_proof",
        )
        _, result, _ = delivery.review_gate_2_data(draft)
        self.assertIn("NONCUT_VISUAL_PLAN_MISMATCH", issue_codes(result))

    def test_blocking_proof_fixture_protects_only_occlusion_core(self) -> None:
        fixture = json.loads(EP15_FAILURE_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(len(fixture["blocking_proof_cases"]), 2)
        for case in fixture["blocking_proof_cases"]:
            self.assertEqual(case["non_cut_basis"], "blocking_proof")
            self.assertEqual(case["spatial_strategy"], "blocking_reveal")
            self.assertTrue(case["pre_relation_requires_own_decision"])
            self.assertTrue(case["post_reaction_requires_own_decision"])

    def test_long_take_requires_structured_design(self) -> None:
        draft = valid_draft()
        draft["shot_plan"]["planned_units"][0]["shot_form"] = "long_take"
        draft["shots"][0]["shot_form"] = "long_take"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("LONG_TAKE_DESIGN_REQUIRED", issue_codes(result))

    def test_supported_long_take_design_is_valid(self) -> None:
        draft = valid_draft()
        unit = draft["shot_plan"]["planned_units"][0]
        unit["shot_form"] = "long_take"
        unit["long_take_design"] = {
            "reason": "完整保留一次持续发展的面部表演。",
            "supports": ["performance_development"],
            "protected_event_ids": ["SEV001"],
        }
        draft["shots"][0]["shot_form"] = "long_take"
        draft["shots"][0]["director_audit"] = {
            "long_take": {
                "status": "supported",
                "reason": "完整保留一次持续发展的面部表演。",
                "supports": ["performance_development"],
            }
        }
        refresh_confirmation_digests(draft)
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

    def test_long_take_over_ten_cannot_absorb_viewing_changes(self) -> None:
        draft = merge_dialogue_turns_for_gate_2(
            valid_draft(),
            mode="hold",
            non_cut_basis="listener_ownership",
        )
        unit = draft["shot_plan"]["planned_units"][0]
        unit["estimated_duration_seconds"] = 14
        unit["shot_form"] = "long_take"
        unit["long_take_design"] = {
            "reason": "错误地用长镜包住发言权与观看主体变化。",
            "supports": ["performance_development"],
            "protected_event_ids": ["SEV001", "SEV002"],
        }
        refresh_plan_metrics(draft)
        _, result, _ = delivery.review_gate_2_data(draft)
        self.assertIn("PROTECTED_PROCESS_SCOPE_OVERREACH", issue_codes(result))

    def test_gate_2_digest_binds_integrity_revision(self) -> None:
        draft = self.prepared(valid_draft())
        payload = delivery.stage_payload(draft, 2)
        self.assertEqual(
            payload["gate_2_rule_revision"],
            "2.5.4-binding-integrity-r1",
        )
        original = delivery.GATE_2_RULE_REVISION
        try:
            before = delivery.stage_digest(draft, 2)
            delivery.GATE_2_RULE_REVISION = "2.5.4-binding-integrity-r0"
            self.assertNotEqual(before, delivery.stage_digest(draft, 2))
        finally:
            delivery.GATE_2_RULE_REVISION = original

    def test_review_report_exposes_cut_atomicity_metrics(self) -> None:
        data = self.prepared(valid_draft())
        report = delivery.make_report(data, delivery.validate_data(data))
        metrics = report["cut_atomicity"]
        self.assertEqual(metrics["dialogue_handoffs"], 1)
        self.assertEqual(metrics["dialogue_handoffs_with_cuts"], 1)
        self.assertEqual(metrics["ordinary_shots_over_10_seconds"], 0)
        self.assertEqual(metrics["multi_event_plan_units"], 2)

    def test_gate_2_snapshot_blocks_atomicity_error_even_when_fields_exist(self) -> None:
        draft = merge_dialogue_turns_for_gate_2(
            valid_draft(),
            mode="hold",
            non_cut_basis=None,
        )
        readiness = delivery.director_readiness_snapshot(draft)
        self.assertEqual(readiness["status"], "BLOCKED")
        self.assertIn("NONCUT_BASIS_REQUIRED", readiness["blocking_issue_codes"])

    def test_camera_header_fixture_is_exact_triad(self) -> None:
        fixture = json.loads(EP15_FAILURE_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["camera_header"]["format"], "【景别｜角度｜运镜】")
        header = self.prepared(valid_draft())["shots"][0][
            "rendered_shot_description"
        ].splitlines()[0]
        self.assertEqual(header.count("｜"), 2)
        self.assertNotIn(
            self.prepared(valid_draft())["shots"][0]["camera"]["composition"],
            header,
        )

    def test_scene_style_anchor_required_but_per_shot_references_are_optional(self) -> None:
        draft = valid_draft()
        for unit in draft["shot_plan"]["planned_units"]:
            unit["visual_plan"].pop("style_anchor_ids", None)
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

        draft = valid_draft()
        draft["scenes"][0]["directing_plan"]["style_anchors"] = []
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("STYLE_ANCHORS", issue_codes(result))

    def test_director_priorities_accept_one_to_three_and_reject_four(self) -> None:
        for count in (1, 2, 3):
            with self.subTest(count=count):
                draft = valid_draft()
                values = [f"场景优先级{index}" for index in range(1, count + 1)]
                draft["director_style_options"][0]["profile"]["priorities"] = values
                draft["director_profile"] = copy.deepcopy(
                    draft["director_style_options"][0]["profile"]
                )
                result = delivery.validate_data(self.prepared(draft))
                self.assertNotIn(
                    "DIRECTOR_PROFILE_PRIORITIES_COUNT", issue_codes(result)
                )

        draft = valid_draft()
        values = [f"场景优先级{index}" for index in range(1, 5)]
        draft["director_style_options"][0]["profile"]["priorities"] = values
        draft["director_profile"] = copy.deepcopy(
            draft["director_style_options"][0]["profile"]
        )
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("DIRECTOR_PROFILE_PRIORITIES_COUNT", issue_codes(result))

    def test_build_warn_writes_bundle_and_returns_two(self) -> None:
        draft = valid_draft()
        draft["shot_plan"]["planned_units"][0]["shot_form"] = "long_take"
        draft["shot_plan"]["planned_units"][0]["long_take_design"] = {
            "reason": "保护周在倾听中逐渐承受压力的连续表演。",
            "supports": ["performance_development"],
            "protected_event_ids": ["SEV001"],
        }
        draft["shots"][0]["shot_form"] = "long_take"
        draft["shots"][0]["director_audit"] = {
            "long_take": {"status": "needs_review", "reason": "", "supports": []}
        }
        refresh_confirmation_digests(draft)
        self.write_draft(draft)
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "build",
                "--input",
                str(self.draft_path),
                "--output-dir",
                str(self.output_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertTrue(list(self.output_dir.glob("*-shot-data.json")))
        self.assertTrue(
            (self.output_dir / ".storyboard-delivery-manifest.json").is_file()
        )

    def test_public_schema_is_static_deterministic_and_cli_export_is_no_overwrite(self) -> None:
        static_path = SKILL_ROOT / "references" / "shot-data.schema.json"
        self.assertEqual(static_path.read_bytes(), contract_schema.schema_bytes())
        schema = json.loads(static_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(
            set(schema["properties"]), contract_schema.TOP_LEVEL_KEYS
        )
        output = self.root / "schema.json"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            first_status = delivery.main(["schema", "--output", str(output)])
        self.assertEqual(first_status, 0)
        self.assertEqual(output.read_bytes(), static_path.read_bytes())
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            second_status = delivery.main(["schema", "--output", str(output)])
        self.assertEqual(second_status, 1)

    def test_schema_and_validator_share_closed_public_structures(self) -> None:
        schema = contract_schema.public_json_schema()
        structure_keys = {
            "source_span": contract_schema.SOURCE_SPAN_KEYS,
            "director_profile": contract_schema.PROFILE_REQUIRED_KEYS,
            "correction": contract_schema.CORRECTION_KEYS,
            "director_analysis": contract_schema.DIRECTOR_ANALYSIS_KEYS,
            "source_analysis": contract_schema.SOURCE_ANALYSIS_REQUIRED_KEYS
            | contract_schema.SOURCE_ANALYSIS_OPTIONAL_KEYS,
            "style_option": contract_schema.STYLE_OPTION_KEYS,
            "entry_strategy": contract_schema.ENTRY_STRATEGY_REQUIRED_KEYS,
            "style_profile_basis": contract_schema.STYLE_PROFILE_BASIS_KEYS,
            "style_anchor": contract_schema.STYLE_ANCHOR_KEYS,
            "directing_plan": contract_schema.DIRECTING_PLAN_REQUIRED_KEYS
            | contract_schema.DIRECTING_PLAN_OPTIONAL_KEYS,
            "initial_continuity": contract_schema.INITIAL_CONTINUITY_KEYS,
            "axis": contract_schema.AXIS_KEYS,
            "inherited_state": contract_schema.INHERITED_STATE_KEYS
            | contract_schema.INHERITED_STATE_OPTIONAL_KEYS,
            "scene": contract_schema.SCENE_REQUIRED_KEYS
            | contract_schema.SCENE_OPTIONAL_KEYS,
            "fact": contract_schema.FACT_REQUIRED_KEYS
            | contract_schema.FACT_OPTIONAL_KEYS,
            "beat": contract_schema.BEAT_REQUIRED_KEYS
            | contract_schema.BEAT_OPTIONAL_KEYS,
            "screen_event": contract_schema.SCREEN_EVENT_REQUIRED_KEYS,
            "spatial_strategy": contract_schema.SPATIAL_STRATEGY_KEYS,
            "movement_plan": contract_schema.MOVEMENT_PLAN_KEYS,
            "visual_plan": contract_schema.VISUAL_PLAN_REQUIRED_KEYS
            | contract_schema.VISUAL_PLAN_OPTIONAL_KEYS,
            "dialogue_design": contract_schema.DIALOGUE_DESIGN_REQUIRED_KEYS
            | contract_schema.DIALOGUE_DESIGN_OPTIONAL_KEYS,
            "source_reuse": contract_schema.SOURCE_REUSE_KEYS,
            "long_take_design": contract_schema.LONG_TAKE_DESIGN_KEYS,
            "plan_unit": contract_schema.PLAN_UNIT_REQUIRED_KEYS
            | contract_schema.PLAN_UNIT_OPTIONAL_KEYS,
            "viewing_decision": contract_schema.VIEWING_DECISION_KEYS,
            "edit_point": contract_schema.EDIT_POINT_REQUIRED_KEYS
            | contract_schema.EDIT_POINT_OPTIONAL_KEYS,
            "reorder": contract_schema.REORDER_KEYS,
            "visual_uniformity_review": contract_schema.VISUAL_UNIFORMITY_REVIEW_KEYS,
            "shot_plan": contract_schema.SHOT_PLAN_KEYS,
            "emotion_phase": contract_schema.EMOTION_PHASE_KEYS,
            "emotion_arc": contract_schema.EMOTION_ARC_KEYS,
            "performance_chain_step": contract_schema.PERFORMANCE_CHAIN_STEP_KEYS,
            "performance_chain": contract_schema.PERFORMANCE_CHAIN_KEYS,
            "shot_phase": contract_schema.SHOT_PHASE_KEYS,
            "cut_design": contract_schema.CUT_DESIGN_REQUIRED_KEYS
            | contract_schema.CUT_DESIGN_OPTIONAL_KEYS,
            "camera": contract_schema.CAMERA_REQUIRED_KEYS
            | contract_schema.CAMERA_OPTIONAL_KEYS,
            "blocking": contract_schema.BLOCKING_KEYS,
            "performance": contract_schema.PERFORMANCE_REQUIRED_KEYS
            | contract_schema.PERFORMANCE_OPTIONAL_KEYS,
            "dialogue": contract_schema.DIALOGUE_REQUIRED_KEYS
            | contract_schema.DIALOGUE_OPTIONAL_KEYS,
            "speaker_presentation": contract_schema.SPEAKER_PRESENTATION_KEYS,
            "eyeline": contract_schema.EYELINE_KEYS,
            "screen_direction": contract_schema.SCREEN_DIRECTION_KEYS,
            "action_match": contract_schema.ACTION_MATCH_KEYS,
            "continuity_exception": contract_schema.CONTINUITY_EXCEPTION_KEYS,
            "continuity": contract_schema.CONTINUITY_KEYS,
            "continuity_update": contract_schema.CONTINUITY_UPDATE_KEYS,
            "coverage_evidence": contract_schema.COVERAGE_EVIDENCE_KEYS,
            "long_take_audit": contract_schema.LONG_TAKE_AUDIT_KEYS,
            "director_audit": contract_schema.DIRECTOR_AUDIT_KEYS,
            "transition": contract_schema.TRANSITION_REQUIRED_KEYS
            | contract_schema.TRANSITION_OPTIONAL_KEYS,
            "shot": contract_schema.SHOT_REQUIRED_KEYS
            | contract_schema.SHOT_OPTIONAL_KEYS,
        }
        for definition, expected_keys in structure_keys.items():
            self.assertFalse(schema["$defs"][definition]["additionalProperties"])
            self.assertEqual(
                set(schema["$defs"][definition]["properties"]),
                expected_keys,
                definition,
            )

        mutations = (
            ("SCENE_FIELD_UNKNOWN", lambda draft: draft["scenes"][0].update(extra=True)),
            ("BEAT_FIELD_UNKNOWN", lambda draft: draft["beats"][0].update(extra=True)),
            (
                "FACT_FIELD_UNKNOWN",
                lambda draft: draft["beats"][0]["facts"][0].update(extra=True),
            ),
            ("SHOT_FIELD_UNKNOWN", lambda draft: draft["shots"][0].update(extra=True)),
            (
                "SOURCE_SPAN_FIELD_UNKNOWN",
                lambda draft: draft["beats"][0]["source_spans"][0].update(extra=True),
            ),
            (
                "INITIAL_CONTINUITY_FIELD_UNKNOWN",
                lambda draft: draft["scenes"][0]["initial_continuity"].update(extra=True),
            ),
        )
        for expected_code, mutate in mutations:
            with self.subTest(code=expected_code):
                draft = valid_draft()
                mutate(draft)
                result = delivery.validate_data(self.prepared(draft))
                self.assertIn(expected_code, issue_codes(result))

        self.assertEqual(
            set(schema["$defs"]["camera"]["properties"]),
            contract_schema.CAMERA_REQUIRED_KEYS
            | contract_schema.CAMERA_OPTIONAL_KEYS,
        )
        self.assertEqual(
            set(schema["$defs"]["fact"]["properties"]["type"]["enum"]),
            contract_schema.FACT_TYPES,
        )
        for metric in (
            "planned_shot_count",
            "planned_edit_point_count",
            "planned_total_duration_seconds",
        ):
            self.assertEqual(
                schema["$defs"]["shot_plan"]["properties"][metric]["type"],
                "integer",
            )
        self.assertEqual(
            schema["$defs"]["shot_phase"]["properties"]["phase_id"],
            {"type": "string", "minLength": 1},
        )
        self.assertEqual(
            schema["$defs"]["spatial_strategy"]["properties"]["description"],
            {"type": "string"},
        )
        self.assertEqual(
            schema["$defs"]["long_take_audit"]["properties"]["reason"],
            {"type": "string"},
        )
        self.assertEqual(
            schema["$defs"]["long_take_audit"]["properties"]["supports"]["minItems"],
            0,
        )
        dialogue_design_schema = schema["$defs"]["plan_unit"]["properties"][
            "dialogue_design"
        ]
        self.assertIn({"type": "null"}, dialogue_design_schema["anyOf"])

        non_integer_metric = self.prepared(valid_draft())
        non_integer_metric["shot_plan"]["planned_shot_count"] = 1.5
        non_integer_metric["content_hash"] = delivery.content_hash(
            non_integer_metric
        )
        result = delivery.validate_data(non_integer_metric)
        self.assertIn("SHOT_PLAN_COUNT_TYPE", issue_codes(result))

    def test_report_status_matrix_uses_explicit_issue_authority(self) -> None:
        data = self.prepared()

        contract_error = delivery.ValidationResult()
        contract_error.error("CONTRACT_IDENTITY", "$.contract_version", "bad")
        report = delivery.make_report(data, contract_error)
        self.assertEqual(
            (report["contract_status"], report["director_readiness"], report["status"]),
            ("FAIL", "BLOCKED", "FAIL"),
        )

        director_error = delivery.ValidationResult()
        director_error.error("CAMERA_LOGIC_CONTRADICTION", "$.shots[0].camera", "bad")
        report = delivery.make_report(data, director_error)
        self.assertEqual(
            (report["contract_status"], report["director_readiness"], report["status"]),
            ("PASS", "BLOCKED", "FAIL"),
        )

        warning = delivery.ValidationResult()
        warning.warn("LONG_TAKE_REVIEW", "$.shots[0]", "review")
        report = delivery.make_report(data, warning)
        self.assertEqual(
            (report["contract_status"], report["director_readiness"], report["status"]),
            ("PASS", "READY", "WARN"),
        )

        report = delivery.make_report(data, delivery.ValidationResult())
        self.assertEqual(
            (report["contract_status"], report["director_readiness"], report["status"]),
            ("PASS", "READY", "PASS"),
        )

    def test_unowned_hidden_threshold_issue_codes_are_removed(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        for issue_code in (
            "CAMERA_PREFIX_SCENE_REPETITION",
            "SHOT_SIZE_PERIODIC_CYCLE",
            "CAMERA_TEMPLATE_REPETITION",
            "SCENE_ENTRY_STRATEGY_MISMATCH",
            "MOVING_CAR_REAR_CENTER_DEFAULT",
        ):
            self.assertNotIn(issue_code, source)

    def test_init_draft_is_source_bound_pending_and_never_overwrites(self) -> None:
        source_path = self.root / "source.txt"
        source_path.write_text(SOURCE_TEXT, encoding="utf-8")
        output = self.root / "new-draft.json"
        arguments = [
            "init-draft",
            "--source-file",
            str(source_path),
            "--project-id",
            "project-01",
            "--delivery-slug",
            "episode-one",
            "--input-kind",
            "screenplay_segment",
            "--boundary-lock",
            "entire_submitted_text",
            "--scope",
            "本轮完整输入",
            "--output",
            str(output),
        ]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            first_status = delivery.main(arguments)
        self.assertEqual(first_status, 0)
        draft = delivery.load_json(output)
        self.assertEqual(draft["source"]["locked_text_hash"], delivery.sha256_text(SOURCE_TEXT))
        self.assertEqual(draft["confirmations"]["gate_1"]["status"], "pending")
        self.assertEqual(draft["confirmations"]["gate_2"]["status"], "pending")
        before = output.read_bytes()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            second_status = delivery.main(arguments)
        self.assertEqual(second_status, 1)
        self.assertEqual(output.read_bytes(), before)

    def test_project_language_policy_is_reused_and_episode_exception_is_reconfirmed(self) -> None:
        locked_text = "哈珀：因为我爱上了你。\n哈珀：Because I fell in love."
        project_policy = {
            "mode": "original_with_translation",
            "original_language": "en",
            "translation_languages": ["zh-CN"],
            "resolution": "user_confirmed",
            "evidence": "本项目英文为原始台词，中文为对照译文",
            "scope": "project",
            "exceptions_require_confirmation": True,
        }
        source = {
            "locked_text": locked_text,
            "approved_corrections": [],
            "project_dialogue_language_policy": project_policy,
        }
        result = delivery.ValidationResult()
        policy = delivery.validate_dialogue_language_policy(source, locked_text, result)
        self.assertFalse(result.errors)
        self.assertEqual(policy, project_policy)

        exception = {
            "mode": "multilingual_actual",
            "spoken_languages": ["zh-CN", "en"],
            "resolution": "source_explicit",
            "evidence": "本集两行均为实际发言",
        }
        source["dialogue_language_policy"] = exception
        result = delivery.ValidationResult()
        delivery.validate_dialogue_language_policy(source, locked_text, result)
        self.assertIn(
            "DIALOGUE_LANGUAGE_EXCEPTION_CONFIRMATION", issue_codes(result)
        )

        exception["resolution"] = "user_confirmed"
        source["approved_corrections"] = [
            {
                "from": "未锁定",
                "to": exception["evidence"],
                "reason": "用户确认本集语言例外",
            }
        ]
        result = delivery.ValidationResult()
        delivery.validate_dialogue_language_policy(source, locked_text, result)
        self.assertFalse(result.errors)

    def test_unicode_language_detection_and_mixed_script_tokenization(self) -> None:
        cases = {
            "안녕하세요": "hangul",
            "こんにちは": "kana",
            "مرحبا": "arabic",
            "Привет": "cyrillic",
        }
        for text_value, family in cases.items():
            with self.subTest(family=family):
                self.assertIn(family, language_contract.script_families(text_value))
        self.assertEqual(
            language_contract.script_tokens("摄影机保持POV关系"),
            ["摄影机保持", "POV", "关系"],
        )
        self.assertEqual(
            language_contract.disallowed_generated_tokens(
                "摄影机保持POV关系， затем停止。",
                locked_text=SOURCE_TEXT,
                standard_terms={"POV"},
            ),
            ["затем"],
        )

    def test_separate_speaker_line_bilingual_pair_is_detected(self) -> None:
        self.assertTrue(
            delivery.bilingual_dialogue_pairs(
                "HARPER\nBecause I fell in love.\n因为我爱上了你。"
            )
        )
        self.assertTrue(
            delivery.bilingual_dialogue_pairs(
                "HARPER\nBecause I fell in love.\nHARPER\n因为我爱上了你。"
            )
        )

    def test_scene_and_cut_to_labels_do_not_create_bilingual_dialogue(self) -> None:
        locked_text = (
            "【CUT TO】\n\n"
            "【SCENE 2】雨夜·江城CBD · 外景 · 1:00-2:00\n\n"
            "雨丝很细，霓虹灯在湿漉漉的柏油路上流淌。\n\n"
            "【CUT TO 黑屏】\n\n"
            "白字浮出：“距离渊兽完全降临，还有49天。”\n\n"
            "【CUT TO】\n\n"
            "【SCENE 3】地下管道 · 内景 · 2:00-2:50\n\n"
            "镜头从黑暗的管道俯冲而下。"
        )
        self.assertEqual(delivery.bilingual_dialogue_pairs(locked_text), [])
        result = delivery.ValidationResult()
        policy = delivery.validate_dialogue_language_policy(
            {"locked_text": locked_text, "approved_corrections": []},
            locked_text,
            result,
        )
        self.assertIsNone(policy)
        self.assertNotIn("DIALOGUE_LANGUAGE_AMBIGUOUS", issue_codes(result))

    def test_scene_workspace_merge_is_bound_and_resets_gate_two(self) -> None:
        data = self.prepared(valid_draft())
        workspace = scene_workspace.extract_scene(data, "SC001")
        workspace["scene"]["directing_plan"]["scene_objective"] = "修改后的场景目标。"
        merged = scene_workspace.merge_scene(data, workspace)
        self.assertEqual(
            merged["scenes"][0]["directing_plan"]["scene_objective"],
            "修改后的场景目标。",
        )
        self.assertEqual(merged["confirmations"]["gate_2"]["status"], "pending")
        self.assertEqual(merged["confirmations"]["gate_2"]["stage_digest"], "")
        stale = copy.deepcopy(workspace)
        stale["locked_text_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "来源 hash"):
            scene_workspace.merge_scene(data, stale)

    def test_derive_edit_points_preserves_declared_performance_chain_break(self) -> None:
        draft = valid_draft()
        draft["performance_chains"][0]["character"] = "林"
        draft["performance_chains"][0]["steps"] = [
            {"role": "dialogue", "fact_ids": ["F002"]},
            {"role": "reaction", "fact_ids": ["F003"]},
        ]
        draft["beats"][1]["facts"][0]["performers"].append("林")
        draft["shot_plan"]["edit_points"][0][
            "broken_performance_chain_ids"
        ] = ["PC001"]
        refresh_confirmation_digests(draft)
        confirmed_digest = delivery.stage_digest(draft, 2)
        without_break = copy.deepcopy(draft)
        without_break["shot_plan"]["edit_points"][0].pop(
            "broken_performance_chain_ids"
        )
        self.assertNotEqual(
            confirmed_digest,
            delivery.stage_digest(without_break, 2),
        )
        prepared = delivery.prepare_data(draft)
        self.assertEqual(
            prepared["shot_plan"]["edit_points"][0][
                "broken_performance_chain_ids"
            ],
            ["PC001"],
        )
        self.assertFalse(delivery.validate_data(prepared).errors)

    def test_manifest_detects_bundle_tampering(self) -> None:
        _, _, paths = self.build()
        paths["markdown"].write_text(
            paths["markdown"].read_text(encoding="utf-8") + "\n篡改\n",
            encoding="utf-8",
        )
        _, result = delivery.validate_delivery(self.output_dir)
        self.assertIn("DELIVERY_MANIFEST", issue_codes(result))

    def test_build_and_validate_wait_for_the_same_output_lock(self) -> None:
        self.build()
        entered_commit = threading.Event()
        release_commit = threading.Event()
        build_errors: list[BaseException] = []
        real_replace = delivery.os.replace

        def paused_replace(source: object, destination: object) -> None:
            target = Path(destination)
            if target.parent == self.output_dir and not entered_commit.is_set():
                entered_commit.set()
                if not release_commit.wait(timeout=10):
                    raise RuntimeError("test commit pause timed out")
            real_replace(source, destination)

        def rebuild() -> None:
            try:
                with mock.patch.object(delivery.os, "replace", side_effect=paused_replace):
                    delivery.build_delivery(self.draft_path, self.output_dir)
            except BaseException as exc:  # exercise and surface interrupt-safe code
                build_errors.append(exc)

        worker = threading.Thread(target=rebuild, daemon=True)
        worker.start()
        self.assertTrue(entered_commit.wait(timeout=5))
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        build_process = subprocess.Popen(
            [
                sys.executable,
                str(MODULE_PATH),
                "build",
                "--input",
                str(self.draft_path),
                "--output-dir",
                str(self.output_dir),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        validate_process = subprocess.Popen(
            [
                sys.executable,
                str(MODULE_PATH),
                "validate",
                "--output-dir",
                str(self.output_dir),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        try:
            with self.assertRaises(subprocess.TimeoutExpired):
                build_process.wait(timeout=0.25)
            with self.assertRaises(subprocess.TimeoutExpired):
                validate_process.wait(timeout=0.25)
        finally:
            release_commit.set()
            worker.join(timeout=10)
        build_stdout, build_stderr = build_process.communicate(timeout=10)
        validate_stdout, validate_stderr = validate_process.communicate(timeout=10)
        self.assertFalse(build_errors)
        self.assertEqual(build_process.returncode, 0, build_stderr or build_stdout)
        self.assertEqual(
            validate_process.returncode, 0, validate_stderr or validate_stdout
        )

    def test_all_five_commit_failures_restore_previous_bundle(self) -> None:
        _, _, paths = self.build()
        data, report = self.changed_delivery_bundle()
        manifest_path = self.output_dir / delivery.MANIFEST_FILENAME
        official_paths = [
            paths["json"],
            paths["markdown"],
            paths["excel"],
            paths["report"],
            manifest_path,
        ]
        baseline = {path.name: path.read_bytes() for path in official_paths}
        new_output = self.root / "changed-delivery"
        new_paths = delivery.atomic_write_delivery(data, report, new_output)
        new_bundle = {
            path.name: path.read_bytes()
            for path in [
                new_paths["json"],
                new_paths["markdown"],
                new_paths["excel"],
                new_paths["report"],
                new_output / delivery.MANIFEST_FILENAME,
            ]
        }
        self.assertTrue(
            all(new_bundle[name] != payload for name, payload in baseline.items())
        )
        real_replace = delivery.os.replace

        for failure_position in range(1, 6):
            with self.subTest(position=failure_position):
                commit_count = 0

                def failing_replace(source: object, destination: object) -> None:
                    nonlocal commit_count
                    target = Path(destination)
                    if target in official_paths:
                        commit_count += 1
                        if commit_count == failure_position:
                            real_replace(source, destination)
                            raise RuntimeError(
                                f"fail after commit {failure_position}"
                            )
                    real_replace(source, destination)

                with mock.patch.object(
                    delivery.os, "replace", side_effect=failing_replace
                ):
                    with self.assertRaises(RuntimeError):
                        delivery.atomic_write_delivery(data, report, self.output_dir)
                self.assertEqual(
                    {path.name: path.read_bytes() for path in official_paths},
                    baseline,
                )

    def test_all_five_post_replace_fsync_failures_restore_previous_bundle(self) -> None:
        _, _, paths = self.build()
        data, report = self.changed_delivery_bundle()
        official_paths = [
            paths["json"],
            paths["markdown"],
            paths["excel"],
            paths["report"],
            self.output_dir / delivery.MANIFEST_FILENAME,
        ]
        baseline = {path.name: path.read_bytes() for path in official_paths}
        real_fsync_directory = delivery.fsync_directory

        for failure_position in range(1, 6):
            with self.subTest(position=failure_position):
                fsync_count = 0

                def failing_fsync(path: Path) -> None:
                    nonlocal fsync_count
                    fsync_count += 1
                    if fsync_count == failure_position:
                        raise OSError(f"fail after fsync position {failure_position}")
                    real_fsync_directory(path)

                with mock.patch.object(
                    delivery, "fsync_directory", side_effect=failing_fsync
                ):
                    with self.assertRaises(OSError):
                        delivery.atomic_write_delivery(data, report, self.output_dir)
                self.assertEqual(
                    {path.name: path.read_bytes() for path in official_paths},
                    baseline,
                )

    def test_interrupt_and_system_exit_also_restore_previous_bundle(self) -> None:
        _, _, paths = self.build()
        data, report = self.changed_delivery_bundle()
        official_paths = [
            paths["json"],
            paths["markdown"],
            paths["excel"],
            paths["report"],
            self.output_dir / delivery.MANIFEST_FILENAME,
        ]
        baseline = {path.name: path.read_bytes() for path in official_paths}
        real_replace = delivery.os.replace

        for exception_type in (KeyboardInterrupt, SystemExit):
            for failure_position in range(1, 6):
                with self.subTest(
                    exception=exception_type.__name__, position=failure_position
                ):
                    commit_count = 0

                    def interrupted_replace(source: object, destination: object) -> None:
                        nonlocal commit_count
                        target = Path(destination)
                        if target in official_paths:
                            commit_count += 1
                            if commit_count == failure_position:
                                real_replace(source, destination)
                                raise exception_type()
                        real_replace(source, destination)

                    with mock.patch.object(
                        delivery.os, "replace", side_effect=interrupted_replace
                    ):
                        with self.assertRaises(exception_type):
                            delivery.atomic_write_delivery(data, report, self.output_dir)
                    self.assertEqual(
                        {path.name: path.read_bytes() for path in official_paths},
                        baseline,
                    )

    def test_historically_named_minimal_positive_fixture_builds_and_validates(self) -> None:
        draft = delivery.load_json(HISTORICALLY_NAMED_MINIMAL_POSITIVE_FIXTURE)
        self.write_draft(draft)
        built, report, _ = delivery.build_delivery(self.draft_path, self.output_dir)
        self.assertEqual(report["contract_status"], "PASS")
        self.assertEqual(report["director_readiness"], "READY")
        self.assertFalse(delivery.validate_data(built).errors)
        _, result = delivery.validate_delivery(self.output_dir)
        self.assertFalse(result.errors)

    def test_unicode_source_span_hash_property(self) -> None:
        generator = random.Random(252)
        alphabet = "林周钥匙ABCПриветمرحباこんにちは안녕"
        for _ in range(100):
            text_value = "".join(
                generator.choice(alphabet) for _ in range(generator.randint(2, 40))
            )
            start = generator.randrange(0, len(text_value) - 1)
            end = generator.randrange(start + 1, len(text_value) + 1)
            span = {"start": start, "end": end}
            delivery.populate_span_hashes([span], text_value)
            self.assertEqual(
                span["text_hash"], delivery.sha256_text(text_value[start:end])
            )


class FenjingSkillV253RegressionTests(unittest.TestCase):
    """Targeted regression tests introduced by the v2.5.3 upgrade."""

    def prepared(self, draft: dict | None = None) -> dict:
        data = valid_draft() if draft is None else draft
        refresh_confirmation_digests(data)
        return delivery.prepare_data(data)

    def test_embedded_foreign_words_do_not_break_chinese_language_match(self) -> None:
        cases = [
            ("你带 iPhone 了吗？", True),
            ("这件事有 100% 把握。", True),
            ("他点了点头：OK。", True),
            ("我们去 Starbucks 喝咖啡。", True),
            ("My name is John, 我是中国人。", False),
            ("Because I fell in love.", False),
            ("纯中文对白没有外来词。", True),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    language_contract.text_matches_language(text, "zh-CN"),
                    expected,
                )

    def test_internal_enums_in_execution_text_are_rejected(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["execution_text"] = "画面采用 wide_spatial，突出 viewpoint_owner。"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("EXECUTION_INTERNAL_ENUM", issue_codes(result))
        issues = [i for i in result.errors if i.code == "EXECUTION_INTERNAL_ENUM"]
        self.assertIn("wide_spatial", issues[0].message)
        self.assertIn("viewpoint_owner", issues[0].message)

    def test_internal_enums_allowed_when_in_locked_text(self) -> None:
        draft = valid_draft()
        draft["source"]["locked_text"] += "wide_spatial"
        draft["shots"][0]["execution_text"] += "wide_spatial"
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("EXECUTION_INTERNAL_ENUM", issue_codes(result))

    def test_execution_analysis_language_is_rejected_but_source_fact_is_exempt(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["execution_text"] += "画面以林为主位，周为次要层。"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("EXECUTION_ANALYSIS_LEAK", issue_codes(result))
        report = delivery.make_report(self.prepared(draft), result)
        self.assertEqual(report["contract_status"], "PASS")
        self.assertEqual(report["director_readiness"], "BLOCKED")

        direct_result = delivery.ValidationResult()
        delivery.validate_execution_text(
            {
                "execution_text": (
                    "【画面内容】室内灯光稳定，机位在桌侧平视林；"
                    "墙上原有“观看权”三个字，林从门口走到桌边后停住。"
                    "林说：你听见了吗？最后焦点停在林的侧脸。"
                ),
                "camera": {
                    "position": "桌侧",
                    "viewpoint_owner": "林",
                    "primary_subjects": ["林"],
                },
            },
            path="$.shot",
            locked_text="观看权\n你听见了吗？",
            dialogue=[{"fact_id": "F002", "speaker": "林", "text": "你听见了吗？"}],
            facts=[
                {"fact_id": "F001", "type": "prop", "text": "观看权"},
                {
                    "fact_id": "F002",
                    "type": "dialogue",
                    "text": "你听见了吗？",
                    "speaker": "林",
                },
            ],
            result=direct_result,
        )
        self.assertNotIn(
            "EXECUTION_ANALYSIS_LEAK",
            {issue.code for issue in direct_result.errors},
        )

    def test_redundant_camera_direction_is_rejected(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["execution_text"] = (
            "【画面内容】室内安静，摄影机位于周右肩后，朝向林；"
            "林走到门口时摄影机仍朝向林，周肩背留在前景。"
            "林问：你听见了吗？最后焦点停在周的反应。"
        )
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn(
            "EXECUTION_REDUNDANT_CAMERA_DIRECTION",
            issue_codes(result),
        )

    def test_repeated_execution_content_is_rejected(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["execution_text"] = (
            "【画面内容】室内安静，机位在周右肩后平视林；"
            "窗外雨声压低，林的手指停在门框边。"
            "窗外雨声压低，林的手指停在门框边。"
            "林问：你听见了吗？最后焦点停在周的反应。"
        )
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("EXECUTION_REPEATED_CONTENT", issue_codes(result))

    def test_single_camera_process_and_referential_end_state_pass(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["execution_text"] = (
            "【画面内容】室内安静，机位在周右肩后平视林，周肩背留在前景；"
            "林从门口向桌边迈近一步时，摄影机缓慢推近，到林停步时停住。"
            "林问：你听见了吗？周保持坐姿，最后焦点停在周握住钥匙的右手。"
        )
        result = delivery.validate_data(self.prepared(draft))
        codes = issue_codes(result)
        self.assertNotIn("EXECUTION_ANALYSIS_LEAK", codes)
        self.assertNotIn("EXECUTION_REDUNDANT_CAMERA_DIRECTION", codes)
        self.assertNotIn("EXECUTION_REPEATED_CONTENT", codes)
        self.assertFalse(result.errors)

    def test_ep01_repeated_camera_fragment_is_blocked(self) -> None:
        result = delivery.ValidationResult()
        delivery.validate_execution_text(
            {
                "execution_text": (
                    "【画面内容】漱玉斋内，摄影机从窗台与调香桌外缘，"
                    "朝向陆听澜并保留主要行动方向朝向陆听澜；"
                    "半枯桂花留在前景，陆听澜完成最后一滴调香后停住。"
                ),
                "camera": {
                    "position": "窗台与调香桌外缘，朝向陆听澜",
                    "viewpoint_owner": "陆听澜",
                    "primary_subjects": ["陆听澜"],
                },
            },
            path="$.shot",
            locked_text="陆听澜完成最后一滴调香后停住。",
            dialogue=[],
            facts=[
                {
                    "fact_id": "F001",
                    "type": "action",
                    "text": "陆听澜完成最后一滴调香后停住。",
                }
            ],
            result=result,
        )
        codes = {issue.code for issue in result.errors}
        self.assertIn("EXECUTION_ANALYSIS_LEAK", codes)
        self.assertIn("EXECUTION_REDUNDANT_CAMERA_DIRECTION", codes)

    def test_execution_template_collapse_warns_at_eight_shot_threshold(self) -> None:
        shots = [
            {
                "shot_id": f"SH{index + 1:03d}",
                "scene_id": "SC001",
                "covered_fact_ids": [],
                "dialogue": [],
                "execution_text": (
                    f"【画面内容】第{index + 1}个空间建立独立人物动作。"
                    "摄影机停住后，人物与道具保持清楚的前后关系。"
                ),
            }
            for index in range(8)
        ]
        result = delivery.ValidationResult()
        delivery.validate_quality_audits(
            {"shots": shots},
            locked_text="",
            fact_lookup={},
            result=result,
        )
        self.assertIn(
            "EXECUTION_TEMPLATE_COLLAPSE",
            {issue.code for issue in result.warnings},
        )
        self.assertEqual(result.status, "WARN")

    def test_execution_template_collapse_ignores_below_threshold_and_short_terms(self) -> None:
        result = delivery.ValidationResult()
        delivery.validate_quality_audits(
            {
                "shots": [
                    {
                        "shot_id": f"SH{index + 1:03d}",
                        "scene_id": "SC001",
                        "covered_fact_ids": [],
                        "dialogue": [],
                        "execution_text": (
                            f"【画面内容】摄影机固定。人物{index + 1}完成独立且不同的动作路径。"
                        ),
                    }
                    for index in range(8)
                ]
            },
            locked_text="",
            fact_lookup={},
            result=result,
        )
        self.assertNotIn(
            "EXECUTION_TEMPLATE_COLLAPSE",
            {issue.code for issue in result.warnings},
        )

        below = delivery.ValidationResult()
        delivery.validate_quality_audits(
            {
                "shots": [
                    {
                        "shot_id": f"SH{index + 1:03d}",
                        "scene_id": "SC001",
                        "covered_fact_ids": [],
                        "dialogue": [],
                        "execution_text": (
                            "【画面内容】摄影机停住后，人物与道具保持清楚的前后关系。"
                        ),
                    }
                    for index in range(7)
                ]
            },
            locked_text="",
            fact_lookup={},
            result=below,
        )
        self.assertNotIn(
            "EXECUTION_TEMPLATE_COLLAPSE",
            {issue.code for issue in below.warnings},
        )

    def test_execution_only_revision_preserves_gate_digests(self) -> None:
        original = delivery.prepare_data(valid_draft())
        revised_draft = copy.deepcopy(original)
        revised_draft["shots"][0]["execution_text"] = (
            "【画面内容】室内安静，机位在周右肩后平视林，周肩背留在前景；"
            "林从门口向桌边迈近一步时，摄影机缓慢推近，到林停步时停住。"
            "林问：你听见了吗？周保持坐姿，最后焦点停在周握住钥匙的右手。"
        )
        revised = delivery.prepare_data(revised_draft)
        self.assertEqual(
            delivery.stage_digest(original, 1),
            delivery.stage_digest(revised, 1),
        )
        self.assertEqual(
            delivery.stage_digest(original, 2),
            delivery.stage_digest(revised, 2),
        )
        self.assertNotEqual(original["content_hash"], revised["content_hash"])

    def test_short_dialogue_rhythm_can_hold(self) -> None:
        draft = merge_dialogue_turns_for_gate_2(
            valid_draft(),
            mode="hold",
            non_cut_basis="dialogue_rhythm",
        )
        _, result, _ = delivery.review_gate_2_data(draft)
        codes = issue_codes(result)
        self.assertNotIn("NONCUT_BASIS_REQUIRED", codes)
        self.assertNotIn("DIALOGUE_HANDOFF_CUT_REQUIRED", codes)

    def test_short_dialogue_rhythm_requires_justification(self) -> None:
        draft = merge_dialogue_turns_for_gate_2(
            valid_draft(),
            mode="hold",
            non_cut_basis="dialogue_rhythm",
        )
        # The hold decision is the boundary inside the merged unit (SEV002 -> SEV003).
        decision = draft["shot_plan"]["viewing_decisions"][1]
        decision["trigger"] = "发言者由林转为周。"
        decision["viewing_change"] = "保持在周的倾听反应。"
        decision["director_reason"] = "保持流畅"
        _, result, _ = delivery.review_gate_2_data(draft)
        self.assertIn("VIEWING_DECISION_GENERIC", issue_codes(result))

    def test_negation_intent_switches_to_cut(self) -> None:
        draft = merge_dialogue_turns_for_gate_2(
            valid_draft(),
            mode="cut",
            non_cut_basis=None,
        )
        # When user says "要切/切开/换镜" the mode must be cut and non_cut_basis null.
        # This test verifies a cut decision with null basis passes.
        _, result, _ = delivery.review_gate_2_data(draft)
        codes = issue_codes(result)
        self.assertNotIn("NONCUT_BASIS_REQUIRED", codes)
        self.assertNotIn("DIALOGUE_HANDOFF_CUT_REQUIRED", codes)

    def test_gate_1_confirmation_intent_recognizes_equivalent_expressions(self) -> None:
        confirmed = [
            "确认", "确定", "OK", "同意", "就这个", "可以", "没问题", "是的",
            "用 STYLE-01",
        ]
        not_confirmed = [
            "继续", "先往下", "看看", "比较一下", "再想想", "待定",
        ]
        for text in confirmed:
            with self.subTest(text=text):
                self.assertFalse(
                    delivery.is_gate_1_confirmation_intent(
                        text, final_profile_displayed=False
                    ),
                    f"'{text}' must not confirm before the final profile is displayed",
                )
                self.assertTrue(
                    delivery.is_gate_1_confirmation_intent(
                        text, final_profile_displayed=True
                    ),
                    f"'{text}' should be treated as confirmation intent",
                )
        for text in not_confirmed:
            with self.subTest(text=text):
                self.assertFalse(
                    delivery.is_gate_1_confirmation_intent(
                        text, final_profile_displayed=True
                    ),
                    f"'{text}' should not be treated as confirmation intent",
                )
        self.assertFalse(
            delivery.is_gate_1_confirmation_intent(
                "STYLE-01", final_profile_displayed=True
            )
        )
        self.assertFalse(
            delivery.is_gate_1_confirmation_intent(
                "选第二个看看", final_profile_displayed=True
            )
        )

    def test_bilingual_two_column_dialogue_requires_user_confirmation(self) -> None:
        locked_text = (
            "哈珀：因为我爱上了你。\n"
            "HARPER: Because I fell in love."
        )
        source = {"locked_text": locked_text, "approved_corrections": []}
        result = delivery.ValidationResult()
        policy = delivery.validate_dialogue_language_policy(
            source, locked_text, result
        )
        self.assertIsNone(policy)
        self.assertIn("DIALOGUE_LANGUAGE_AMBIGUOUS", issue_codes(result))

    def test_long_take_monologue_delivery_is_valid(self) -> None:
        draft = valid_draft()
        # Collapse to a single monologue event/unit so the long take only covers one speaker.
        locked_text = "林：我曾以为自己永远不会回到这里。"
        locked_text_hash = delivery.sha256_text(locked_text)
        source_span = {"start": 0, "end": len(locked_text), "text_hash": locked_text_hash}
        dialogue_span = {"start": 2, "end": len(locked_text), "text_hash": locked_text_hash}
        draft["source"]["locked_text"] = locked_text
        draft["source"]["locked_text_hash"] = locked_text_hash
        draft["source_analysis"]["source_boundary"] = "林独白的完整片段。"
        draft["source_analysis"]["narrative_function"] = "林以独白坦陈内心决定。"
        draft["source_analysis"]["dramatic_progression"] = "独白推进情绪。"
        draft["source_analysis"]["character_relations"] = []
        draft["source_analysis"]["source_constraints"] = ["逐字保留独白台词"]
        draft["director_style_options"] = None
        draft["selected_style_option_id"] = None
        draft["director_profile"] = {
            "rhythm": "restrained",
            "camera_energy": "responsive",
            "visual_distance": "intimate",
            "performance_focus": "face",
            "space_strategy": "embedded_reveal",
            "transition_language": ["long_hold"],
            "priorities": ["保留独白完整性"],
            "natural_language_intent": "摄影机缓慢靠近独白者，不干扰情绪推进。",
        }
        draft["beats"] = [
            {
                "beat_id": "B001",
                "beat_order": 1,
                "scene_id": "SC001",
                "source_spans": [copy.deepcopy(source_span)],
                "dramatic_change": "林以独白袒露内心决定。",
                "facts": [
                    {
                        "fact_id": "F001",
                        "type": "dialogue",
                        "text": "我曾以为自己永远不会回到这里。",
                        "speaker": "林",
                        "script_voice_type": "scene_dialogue",
                        "source_spans": [copy.deepcopy(dialogue_span)],
                        "performers": ["林"],
                    }
                ],
            }
        ]
        draft["screen_events"] = [
            {
                "screen_event_id": "SEV001",
                "scene_id": "SC001",
                "event_order": 1,
                "beat_ids": ["B001"],
                "covered_fact_ids": ["F001"],
                "source_spans": [copy.deepcopy(source_span)],
                "spatial_zone": "SC001",
                "temporal_relation": "sequential",
                "visual_subjects": ["林"],
                "visual_action": "林独白，情绪层层推进。",
                "viewing_requirement": "观众持续注视林的表情变化。",
                "scale_requirement": "由当前原子事件的观看尺度决定。",
                "event_role": "dialogue_turn",
                "primary_viewing_subject": "林",
                "focus_scale": "face",
                "sound_fact_ids": [],
            }
        ]
        visual = {
            "viewpoint_owner": "林",
            "primary_subjects": ["林"],
            "secondary_subjects": [],
            "shot_size": "近景",
            "angle": "平视",
            "camera_position": "林正前方略偏",
            "framing_relation": "林面部占据主位，背景虚化",
            "perspective_intent": "detail_isolation",
            "focus_plan": "焦点锁定林的面部。",
            "spatial_strategy": {"type": "not_applicable", "description": ""},
            "movement_plan": {
                "class": "push",
                "trigger": "独白开始。",
                "speed": "缓慢",
                "path": "从近景推向面部特写。",
                "end_condition": "台词结束停在特写。",
                "hold_reason": "",
            },
            "start_frame": "林站在门口，直视镜头。",
            "end_frame": "林面部特写，台词结束。",
            "motivation": "缓慢推近放大独白情绪压力。",
        }
        unit = {
            "plan_unit_id": "PU001",
            "plan_order": 1,
            "scene_id": "SC001",
            "beat_ids": ["B001"],
            "screen_event_ids": ["SEV001"],
            "source_spans": [copy.deepcopy(source_span)],
            "estimated_duration_seconds": 45,
            "narrative_purpose": "完整保留林向镜头的长段独白。",
            "shot_form": "long_take",
            "long_take_design": {
                "reason": "完整保留人物向镜头的长段独白，情绪推进不可切。",
                "supports": ["monologue_delivery"],
                "protected_event_ids": ["SEV001"],
            },
            "dialogue_design": {
                "speaker_sequence": ["林"],
                "justification": "独白仅由林一人完成，画面持续注视其面部情绪变化。",
            },
            "visual_plan": visual,
        }
        draft["shot_plan"]["planned_units"] = [unit]
        draft["shot_plan"]["planned_shot_count"] = 1
        draft["shot_plan"]["planned_edit_point_count"] = 0
        draft["shot_plan"]["planned_total_duration_seconds"] = 45
        draft["shot_plan"]["edit_points"] = []
        draft["shot_plan"]["viewing_decisions"] = []
        draft["shot_plan"]["reorders"] = []
        draft["scenes"] = [
            {
                "scene_id": "SC001",
                "scene": "林独白",
                "reality_layer": "现实",
                "axes": [],
                "initial_continuity": {
                    "characters": [
                        {
                            "name": "林",
                            "position": "门口",
                            "facing": "镜头",
                            "eyeline": "镜头",
                            "presence": "onscreen",
                            "state": "决绝",
                        }
                    ],
                    "props": [],
                    "fixed_objects": [],
                    "sound_sources": [],
                    "reality_layer": "现实",
                },
                "directing_plan": {
                    "scene_objective": "完整保留林向镜头的独白。",
                    "progression": ["建立面对镜头的独处状态", "推进独白情绪", "停在特写"],
                    "pov_flow": ["摄影机从近景缓慢推向面部特写"],
                    "entry_strategy": {
                        "mode": "character_entry",
                        "observer_position": "林正前方略偏",
                        "required_spatial_information": ["林在门口", "林直视镜头"],
                        "withheld_information": [],
                        "reason": "先建立人物独处状态，再推进情绪。",
                    },
                    "style_anchors": [
                        {
                            "style_anchor_id": "SA001",
                            "profile_basis": [{"field": "priorities", "value": "保留独白完整性"}],
                            "scene_application": "用长镜头完整保留独白。",
                            "avoidance": "避免切镜打断情绪。",
                        }
                    ],
                },
                "inherits_from": None,
                "inherited_states": [],
            }
        ]
        shot = {
            "shot_id": "SH001",
            "shot_order": 1,
            "plan_unit_id": "PU001",
            "scene_id": "SC001",
            "beat_ids": ["B001"],
            "source_spans": [copy.deepcopy(source_span)],
            "covered_fact_ids": ["F001"],
            "primary_fact_id": "F001",
            "duration_seconds": 45,
            "shot_phases": [
                {
                    "phase_id": "PH001-01",
                    "phase_order": 1,
                    "screen_event_ids": ["SEV001"],
                    "duration_seconds": 45,
                    "camera_state": "从近景缓慢推向林面部特写。",
                    "sound_fact_ids": [],
                }
            ],
            "cut_design": {
                "entry_trigger": "从林的独处状态开始。",
                "exit_trigger": "独白结束，停在特写。",
                "isolation_intent": "none",
            },
            "camera": {
                "shot_size": "近景",
                "angle": "平视",
                "position": "林正前方略偏",
                "composition": "林面部占据主位，背景虚化",
                "movement": "缓慢推进",
                "logic": "朝向林，缓慢推近以放大独白情绪。",
                "viewpoint_owner": "林",
                "primary_subjects": ["林"],
                "secondary_subjects": [],
                "perspective_intent": "detail_isolation",
                "focus_plan": "焦点锁定林的面部。",
                "spatial_strategy": {"type": "not_applicable", "description": ""},
                "movement_plan": {
                    "class": "push",
                    "trigger": "独白开始。",
                    "speed": "缓慢",
                    "path": "从近景推向面部特写。",
                    "end_condition": "台词结束停在特写。",
                    "hold_reason": "",
                },
                "start_frame": "林站在门口，直视镜头。",
                "end_frame": "林面部特写，台词结束。",
                "motivation": "缓慢推近放大独白情绪压力。",
            },
            "blocking": [
                {
                    "character": "林",
                    "start_position": "门口",
                    "action": "面向镜头独白",
                    "end_position": "门口",
                    "facing": "镜头",
                    "eyeline": "镜头",
                }
            ],
            "performance": {
                "emotion_arc_id": None,
                "phase": "steady",
                "emotion_intent": "林在独白中坦陈内心。",
                "visible_behavior": ["眼神从回避转为直视镜头", "语速渐慢"],
            },
            "dialogue": [
                {
                    "fact_id": "F001",
                    "speaker": "林",
                    "text": "我曾以为自己永远不会回到这里。",
                    "shot_delivery": "onscreen",
                    "timing": "PH001-01",
                    "addressee": "",
                }
            ],
            "speaker_presentation": [
                {"fact_id": "F001", "speaker": "林", "presentation": "primary_face"}
            ],
            "visible_characters": ["林"],
            "visible_props": [],
            "environment_behavior": [],
            "continuity": {
                "axis_id": None,
                "axis_side": "not_applicable",
                "eyelines": [{"character": "林", "target": "镜头", "direction": "toward_camera"}],
                "screen_directions": [{"entity": "林", "kind": "eyeline", "direction": "toward_camera"}],
                "action_match": {"incoming": None, "outgoing": None},
                "intentional_exceptions": [],
            },
            "continuity_updates": [],
            "end_state": ["林仍站在门口，直视镜头"],
            "coverage_evidence": [
                {
                    "fact_id": "F001",
                    "target_path": "dialogue[0].text",
                    "evidence_quote": "我曾以为自己永远不会回到这里。",
                }
            ],
            "transition_to_next": {
                "type": "scene_end",
                "edit_point_id": None,
            },
            "rendered_shot_description": "",
            "execution_text": "【画面内容】室内安静，背景虚化；摄影机位于林正前方略偏，缓慢推近；林的面部占据画面中央；林面向镜头独白：我曾以为自己永远不会回到这里。林眼神从回避转为直视镜头，语速渐慢；最后停在林仍站在门口、直视镜头的面部特写。",
            "notes": "",
            "shot_form": "long_take",
            "director_audit": {
                "long_take": {
                    "status": "supported",
                    "reason": "独白完整性优先。",
                    "supports": ["monologue_delivery"],
                }
            },
        }
        draft["shots"] = [shot]
        draft["emotion_arcs"] = []
        draft["performance_chains"] = []
        refresh_confirmation_digests(draft)
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

    def test_long_take_testimony_statement_requires_single_speaker(self) -> None:
        draft = merge_dialogue_turns_for_gate_2(
            valid_draft(),
            mode="hold",
            non_cut_basis="dialogue_rhythm",
        )
        unit = draft["shot_plan"]["planned_units"][0]
        unit["estimated_duration_seconds"] = 30
        unit["shot_form"] = "long_take"
        unit["long_take_design"] = {
            "reason": "法庭陈述需要连续权威感。",
            "supports": ["testimony_statement"],
            "protected_event_ids": ["SEV001", "SEV002"],
        }
        refresh_plan_metrics(draft)
        _, result, _ = delivery.review_gate_2_data(draft)
        # Two speakers in a testimony_statement long take violates the rule.
        self.assertIn("PROTECTED_PROCESS_SCOPE_OVERREACH", issue_codes(result))


class ChineseSceneFixtureTests(unittest.TestCase):
    """End-to-end tests for current scene positives and the 2.5.3 golden."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="su-fenjingskill-fixture-test-"
        )
        self.root = Path(self.temporary_directory.name)
        self.output_dir = self.root / "delivery"
        self.draft_path = self.root / "draft.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _load_fixture_module(self):
        spec = importlib.util.spec_from_file_location(
            "chinese_scene_fixtures",
            SCRIPT_DIR / "fixtures" / "chinese_scene_fixtures.py",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def _assert_fixture_builds(self, factory) -> None:
        draft = factory()
        self.draft_path.write_bytes(delivery.json_bytes(draft))
        built, report, _ = delivery.build_delivery(self.draft_path, self.output_dir)
        self.assertEqual(report["contract_status"], "PASS")
        self.assertEqual(report["director_readiness"], "READY")
        self.assertFalse(delivery.validate_data(built).errors)
        _, result = delivery.validate_delivery(self.output_dir)
        self.assertFalse(result.errors)

    def test_dinner_party_fixture_builds_and_validates(self) -> None:
        module = self._load_fixture_module()
        self._assert_fixture_builds(module.dinner_party_fixture)

    def test_courtroom_fixture_builds_and_validates(self) -> None:
        module = self._load_fixture_module()
        self._assert_fixture_builds(module.courtroom_fixture)

    def test_chase_fixture_builds_and_validates(self) -> None:
        module = self._load_fixture_module()
        self._assert_fixture_builds(module.chase_fixture)

    def test_positive_253_golden_fixture_builds_and_validates(self) -> None:
        draft = delivery.load_json(
            SCRIPT_DIR / "fixtures" / "shot-data-253-positive-draft.json"
        )
        self._assert_fixture_builds(lambda: draft)


if __name__ == "__main__":
    unittest.main(verbosity=2)
