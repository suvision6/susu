#!/usr/bin/env python3
"""Regression tests for the shot-data/2.4.3 delivery contract."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.dont_write_bytecode = True
SCRIPT_DIR = Path(__file__).resolve().parent
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


def refresh_confirmation_digests(draft: dict) -> dict:
    draft["confirmations"]["gate_1"]["stage_digest"] = delivery.stage_digest(draft, 1)
    draft["confirmations"]["gate_2"]["stage_digest"] = delivery.stage_digest(draft, 2)
    return draft


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


def valid_draft() -> dict:
    line_one = "林站在门口，周坐在桌边。"
    line_two = "林：你听见了吗？"
    line_three = "周抬眼，握紧钥匙：听见了。"
    draft = {
        "contract_name": "shot-data",
        "contract_version": "2.4.3",
        "source_skill": "su-fenjingskill",
        "source_skill_version": "2.4.3",
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
                "label": "克制观察",
                "rationale": "贴近反应，但让摄影机少于演员主动。",
                "profile": selected_profile(),
            },
            {
                "option_id": "STYLE-02",
                "label": "空间观察",
                "rationale": "先完整建立人物关系，再让动作改变节奏。",
                "profile": alternative_profile(),
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
                        "presentation_requirement": "must_be_clear",
                        "shot_isolation": "not_required",
                        "isolation_reason": "",
                        "performers": ["林", "周"],
                        "isolation_group_id": None,
                    },
                    {
                        "fact_id": "F002",
                        "type": "dialogue",
                        "text": "你听见了吗？",
                        "speaker": "林",
                        "delivery": "onscreen",
                        "source_spans": [source_span("你听见了吗？")],
                        "presentation_requirement": "must_be_clear",
                        "shot_isolation": "not_required",
                        "isolation_reason": "",
                        "performers": ["林"],
                        "isolation_group_id": None,
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
                        "presentation_requirement": "must_be_clear",
                        "shot_isolation": "not_required",
                        "isolation_reason": "",
                        "performers": ["周"],
                        "isolation_group_id": None,
                    },
                    {
                        "fact_id": "F004",
                        "type": "dialogue",
                        "text": "听见了。",
                        "speaker": "周",
                        "delivery": "onscreen",
                        "source_spans": [source_span("听见了。")],
                        "presentation_requirement": "supporting",
                        "shot_isolation": "not_required",
                        "isolation_reason": "",
                        "performers": ["周"],
                        "isolation_group_id": None,
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
    """Normalize legacy fixture prose into the director-first 2.4.3 contract."""
    draft["contract_version"] = "2.4.3"
    draft["source_skill_version"] = "2.4.3"
    scenes = {scene["scene_id"]: scene for scene in draft.get("scenes", [])}
    for scene in scenes.values():
        scene.setdefault(
            "directing_plan",
            {
                "entry_state": "承接本场开端已经成立的人物、空间与关系状态。",
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
            dict.fromkeys(item["speaker"] for item in dialogue if item.get("delivery") == "onscreen")
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
            camera["movement"] = "缓慢推进后停住"
            camera["end_frame"] = "林问话结束，周肩背仍在前景"
            camera["logic"] = "朝向林，保持林周视线轴同侧"
        elif shot["shot_id"] == "SH002":
            camera["position"] = "周正侧近处"
            camera["logic"] = "朝向周，保持林周视线轴同侧"
        else:
            subjects = "、".join(camera["primary_subjects"]) or "当前空间"
            camera["logic"] = f"朝向{subjects}，保持本场既定观察方向"
        shot["speaker_presentation"] = [
            {
                "fact_id": item["fact_id"],
                "speaker": item["speaker"],
                "presentation": (
                    "primary_face"
                    if item["delivery"] == "onscreen"
                    else ("vo" if item["delivery"] == "vo" else "offscreen")
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
        shot["duration_blocks"][0]["label"] = delivery.TIMING_SYNC_LABEL
        visible_behavior = "；".join(
            shot.get("performance", {}).get("visible_behavior", [])
        )
        spoken_text = "；".join(
            f'{item["speaker"]}以{item.get("delivery", "onscreen")}方式说：“{item["text"]}”'
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
        shot["execution_text"] = (
            f"【画面内容】{environment_text}"
            f"摄影机位于{camera['position']}，{camera['logic']}；"
            f"画面中{camera['composition']}。"
            f"{text}{performance_text}"
            f"动作完成后，{end_state_text}。"
        )
    plan = draft.get("shot_plan", {})
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
                "angle": "平视",
                "position": "走廊侧墙",
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
            "notes": "继承上一场钥匙状态。",
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

    def test_build_declares_contract_and_preserves_handoff_fields(self) -> None:
        built, report, _ = self.build()
        self.assertEqual(built["contract_name"], "shot-data")
        self.assertEqual(built["contract_version"], "2.4.3")
        self.assertEqual(built["source_skill"], "su-fenjingskill")
        self.assertEqual(built["source_skill_version"], "2.4.3")
        self.assertEqual(report["status"], "PASS")
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
        draft["director_profile"] = {
            key: draft["director_profile"][key]
            for key in ("priorities", "natural_language_intent")
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
                for key in ("scene_objective", "progression", "pov_flow")
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
                "speaker_presentation",
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
                )
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
        self.assertEqual(draft["beats"][1]["facts"][0]["shot_isolation"], "not_required")
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
        self.assertLess(len(contract_text.splitlines()), 500)
        self.assertIn("最小结构示例", contract_text)
        self.assertIn("六列渲染示例", contract_text)
        self.assertNotIn("可直接构建的合法 draft", contract_text)
        self.assertNotIn("standard_shot_percentage", contract_text)

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

    def test_duration_uses_parallel_max_then_sequential_sum(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["duration_blocks"].append(
            {
                "block_id": "TB02",
                "label": delivery.TIMING_HOLD_LABEL,
                "action_seconds": 0,
                "dialogue_seconds": 0,
                "performance_seconds": 2,
                "camera_seconds": 0,
            }
        )
        draft["shots"][0]["duration_seconds"] = 5
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)
        draft["shots"][0]["duration_seconds"] = 4
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("DURATION_FORMULA", issue_codes(result))

    def test_duration_rejects_bool_float_and_zero_block(self) -> None:
        for bad_value in (True, 1.5, "2"):
            with self.subTest(value=bad_value):
                draft = valid_draft()
                draft["shots"][0]["duration_blocks"][0]["action_seconds"] = bad_value
                result = delivery.validate_data(self.prepared(draft))
                self.assertIn("DURATION_CHANNEL", issue_codes(result))
        draft = valid_draft()
        block = draft["shots"][0]["duration_blocks"][0]
        for channel in delivery.DURATION_CHANNELS:
            block[channel] = 0
        draft["shots"][0]["duration_seconds"] = 1
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("DURATION_BLOCK_EMPTY", issue_codes(result))

    def test_duration_requires_standard_blocks_and_order(self) -> None:
        draft = valid_draft()
        draft["shots"][0].pop("duration_blocks")
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("DURATION_BLOCKS_REQUIRED", issue_codes(result))

        draft = valid_draft()
        draft["shots"][0]["duration_blocks"][0]["label"] = "自定义计时段"
        result = delivery.validate_data(self.prepared(draft))
        codes = issue_codes(result)
        self.assertIn("DURATION_BLOCK_LABEL", codes)
        self.assertIn("DURATION_SYNC_REQUIRED", codes)

        draft = valid_draft()
        draft["shots"][0]["duration_blocks"].insert(
            0,
            {
                "block_id": "TB00",
                "label": delivery.TIMING_HOLD_LABEL,
                "action_seconds": 0,
                "dialogue_seconds": 0,
                "performance_seconds": 1,
                "camera_seconds": 0,
            },
        )
        draft["shots"][0]["duration_seconds"] = 4
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("DURATION_BLOCK_ORDER", issue_codes(result))

    def test_duration_rejects_channels_that_exceed_their_real_block(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["duration_blocks"][0]["camera_seconds"] = 4
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("DURATION_PARALLEL_OVERFLOW", issue_codes(result))

        draft = valid_draft()
        draft["shots"][0]["duration_blocks"].append(
            {
                "block_id": "TB02",
                "label": delivery.TIMING_ASYNC_LABEL,
                "action_seconds": 2,
                "dialogue_seconds": 1,
                "performance_seconds": 0,
                "camera_seconds": 2,
            }
        )
        draft["shots"][0]["duration_seconds"] = 5
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("DURATION_ASYNC_CHANNEL", issue_codes(result))

    def test_duration_has_no_model_limit(self) -> None:
        draft = valid_draft()
        block = draft["shots"][0]["duration_blocks"][0]
        block.update(
            {
                "action_seconds": 120,
                "dialogue_seconds": 100,
                "performance_seconds": 115,
                "camera_seconds": 120,
            }
        )
        draft["shots"][0]["duration_seconds"] = 120
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)

    def test_long_take_needs_review_is_warning_not_failure(self) -> None:
        draft = valid_draft()
        draft["shot_plan"]["planned_units"][0]["shot_form"] = "long_take"
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
        self.assertEqual(fact["presentation_requirement"], "must_be_clear")
        self.assertEqual(fact["shot_isolation"], "not_required")
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

    def test_formula_prefix_and_special_text_round_trip_as_text(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["notes"] = "=1+1 | 保持\n下一行"
        built, _, paths = self.build(draft)
        expected = delivery.expected_table_rows(built)
        self.assertEqual(delivery.read_markdown_rows(paths["markdown"]), expected)
        self.assertEqual(delivery.read_xlsx_rows(paths["excel"]), expected)
        self.assertEqual(
            expected[1][-1],
            (
                "[时长估算]同步动作2秒；同步台词3秒；非同步动作0秒；"
                "情绪留白0秒；前两项取 max 后再加后两项，共3秒。"
                "[执行提醒]=1+1 | 保持\n下一行"
            ),
        )

    def test_stale_timing_prefix_keeps_its_director_rationale(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["notes"] = (
            "[时长估算]同步动作99秒；同步台词0秒；非同步动作0秒；"
            "情绪留白0秒；前两项取 max 后再加后两项，共99秒。"
            "首镜承担空间和等待状态，不提前切入问答。"
            "[执行提醒]晨雾浓度必须保持连续。"
        )
        built, report, _ = self.build(draft)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(
            built["shots"][0]["notes"],
            (
                "[时长估算]同步动作2秒；同步台词3秒；非同步动作0秒；"
                "情绪留白0秒；前两项取 max 后再加后两项，共3秒。"
                "[执行提醒]首镜承担空间和等待状态，不提前切入问答。"
                "晨雾浓度必须保持连续。"
            ),
        )

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
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("SHOT_PLAN_METRIC", issue_codes(result))

    def test_ordinary_shot_omits_classification_at_any_duration(self) -> None:
        draft = valid_draft()
        draft["shot_plan"]["planned_units"][0][
            "estimated_duration_seconds"
        ] = 120
        refresh_plan_metrics(draft)
        block = draft["shots"][0]["duration_blocks"][0]
        block.update(
            {
                "action_seconds": 120,
                "dialogue_seconds": 100,
                "performance_seconds": 115,
                "camera_seconds": 120,
            }
        )
        draft["shots"][0]["duration_seconds"] = 120
        result = delivery.validate_data(self.prepared(draft))
        self.assertFalse(result.errors)
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
        draft["shot_plan"]["edit_points"][0]["editorial_gain"] = "节奏需要"
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("EDIT_POINT_GENERIC", issue_codes(result))

    def test_sound_rhythm_and_emotion_are_valid_cut_reasons(self) -> None:
        draft = valid_draft()
        edit_point = draft["shot_plan"]["edit_points"][0]
        edit_point["trigger"] = "门外低频声突然中断，沉默开始压住问句。"
        edit_point["editorial_gain"] = "把声音缺失转成周的主观压力，并延迟交出回应。"
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
        self.assertRegex(rows[0][4], r"^【[^，]+，[^，]+，[^】]+】")
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

    def test_performance_chain_break_must_be_declared_at_exact_edit_point(self) -> None:
        draft = valid_draft()
        action_span = source_span("周抬眼，握紧钥匙")
        dialogue_span = source_span("听见了。")
        draft["shot_plan"]["planned_units"][1]["source_spans"] = [action_span]
        draft["shot_plan"]["planned_units"].append(
            {
                "plan_unit_id": "PU003",
                "plan_order": 3,
                "scene_id": "SC001",
                "beat_ids": ["B002"],
                "source_spans": [dialogue_span],
                "estimated_duration_seconds": 1,
                "narrative_purpose": "在动作完成后单独承接周的回答。",
                "source_reuse": None,
            }
        )
        draft["shot_plan"]["edit_points"].append(
            {
                "edit_point_id": "EP002",
                "after_plan_unit_id": "PU002",
                "before_plan_unit_id": "PU003",
                "source_spans": [action_span, dialogue_span],
                "trigger": "周在动作完成后开口回答。",
                "editorial_gain": "把动作落点与语言确认分开强调。",
            }
        )
        original_second = copy.deepcopy(draft["shots"][1])
        draft["shots"][1]["source_spans"] = [action_span]
        draft["shots"][1]["covered_fact_ids"] = ["F003"]
        draft["shots"][1]["coverage_evidence"] = [
            draft["shots"][1]["coverage_evidence"][0]
        ]
        draft["shots"][1]["dialogue"] = []
        draft["shots"][1]["transition_to_next"] = {
            "type": "gaze_cut",
            "edit_point_id": "EP002",
            "notes": "动作完成后进入回答。",
        }
        original_second.update(
            {
                "shot_id": "SH003",
                "shot_order": 3,
                "plan_unit_id": "PU003",
                "source_spans": [dialogue_span],
                "covered_fact_ids": ["F004"],
                "coverage_evidence": [original_second["coverage_evidence"][1]],
                "primary_fact_id": "F004",
                "duration_seconds": 1,
                "duration_blocks": [
                    {
                        "block_id": "TB01",
                        "label": "周回答",
                        "action_seconds": 0,
                        "dialogue_seconds": 1,
                        "performance_seconds": 1,
                        "camera_seconds": 1,
                    }
                ],
                "continuity_updates": [],
                "visible_props": [],
                "end_state": ["周仍坐在桌边并完成回答", "钥匙保持紧握"],
                "transition_to_next": {
                    "type": "scene_end",
                    "edit_point_id": None,
                    "notes": "停在回答后的状态。",
                },
                "rendered_shot_description": "",
            }
        )
        draft["shots"].append(original_second)
        refresh_plan_metrics(draft)
        result = delivery.validate_data(self.prepared(draft))
        self.assertIn("PERFORMANCE_CHAIN_BREAK_UNDECLARED", issue_codes(result))

        draft["shot_plan"]["edit_points"][1]["broken_performance_chain_ids"] = ["PC001"]
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("PERFORMANCE_CHAIN_BREAK_UNDECLARED", issue_codes(result))
        self.assertNotIn("PERFORMANCE_CHAIN_BREAK_UNUSED", issue_codes(result))

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

    def test_actual_ep15_v201_is_rejected_for_known_failure_signatures(self) -> None:
        fixture = Path(
            "/Users/suvision/Documents/The mist/outputs/2026-07-26/"
            "Ep15-d8-v201/outputs/shot_data.json"
        )
        if not fixture.exists():
            self.skipTest("local EP15 v2.0.1 negative fixture is unavailable")
        data = json.loads(fixture.read_text(encoding="utf-8"))
        data["contract_version"] = "2.4.3"
        data["source_skill_version"] = "2.4.3"
        data["performance_chains"] = []
        scene_characters: dict[str, list[str]] = {}
        for scene in data["scenes"]:
            characters = [
                item["name"]
                for item in scene["initial_continuity"]["characters"]
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            ]
            scene_characters[scene["scene_id"]] = characters
        beat_scene = {beat["beat_id"]: beat["scene_id"] for beat in data["beats"]}
        for beat in data["beats"]:
            characters = scene_characters.get(beat_scene[beat["beat_id"]], [])
            for fact in beat["facts"]:
                if fact["type"] == "dialogue":
                    fact["performers"] = [fact.get("speaker", "")]
                elif fact["type"] in {"action", "emotion"}:
                    named = [name for name in characters if name and name in fact.get("text", "")]
                    fact["performers"] = named or characters[:1]
                else:
                    fact["performers"] = []
                fact["isolation_group_id"] = (
                    f"IG{int(fact['fact_id'][1:]):03d}"
                    if fact.get("shot_isolation") == "director_required"
                    else None
                )
        for edit_point in data["shot_plan"]["edit_points"]:
            edit_point["trigger"] = (
                f"来源事件推动观察转入 {edit_point['before_plan_unit_id']}。"
            )
            edit_point["editorial_gain"] = (
                "切换后改变观察重心并承接下一项来源事实。"
            )
        refresh_confirmation_digests(data)
        result = delivery.validate_data(delivery.prepare_data(data))
        codes = issue_codes(result)
        warning_codes = {issue.code for issue in result.warnings}
        self.assertIn("TEMPLATE_PLACEHOLDER", codes)
        self.assertIn("DIALOGUE_ADDRESSEE", codes)
        self.assertIn("SCENE_DURATION_ESTIMATE", codes)
        self.assertIn("SOURCE_METADATA_FACT", codes)
        self.assertNotIn("MECHANICAL_SPLIT_DENSITY", warning_codes)
        self.assertNotIn("CAMERA_TEMPLATE_REPETITION", warning_codes)

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

    def test_three_speaker_design_is_not_forced_into_shared_coverage(self) -> None:
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
        self.assertFalse(result.errors)
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

    def test_continuous_reframe_and_listener_reaction_are_legal(self) -> None:
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
        self.assertNotIn("CAMERA_ANGLE_ROLE_CONFLICT", issue_codes(result))
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
        self.assertNotIn("CAMERA_LOGIC_DUPLICATION", issue_codes(result))
        draft = valid_draft()
        draft["shots"][0]["camera"]["movement"] = "从周肩后拍林正脸"
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("CAMERA_MOVEMENT_ROLE_CONFLICT", issue_codes(result))

    def test_foreground_speaker_is_legal_and_execution_failures_remain_explicit(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["speaker_presentation"][0]["presentation"] = "foreground_back"
        draft["shot_plan"]["planned_units"][0]["dialogue_design"].pop(
            "face_readable_speakers",
            None,
        )
        draft["shots"][0]["camera"]["foreground_characters"] = ["林"]
        draft["shots"][0]["camera"]["primary_subjects"] = ["周"]
        draft["shots"][0]["camera"]["position"] = "林右肩后"
        draft["shots"][0]["camera"]["composition"] = "林肩背在前景，周位于画面深处"
        draft["shots"][0]["camera"]["logic"] = "朝向周，保持林周视线轴同侧"
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
            [{"fact_id": "F001", "speaker": "A", "presentation": "offscreen"}],
            path="$.shot.speaker_presentation",
            dialogue=[{"fact_id": "F001", "speaker": "A", "delivery": "offscreen"}],
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
            dialogue=[{"fact_id": "F001", "speaker": "A", "delivery": "onscreen"}],
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
        fixture = Path(
            "/Users/suvision/Documents/The mist/outputs/2026-07-26/"
            "Ep15-dibati-v210/outputs/shot_data.json"
        )
        if not fixture.exists():
            self.skipTest("local EP15 v2.1.0 negative fixture is unavailable")
        data = json.loads(fixture.read_text(encoding="utf-8"))
        data["contract_version"] = "2.4.3"
        data["source_skill_version"] = "2.4.3"
        result = delivery.validate_data(delivery.prepare_data(data))
        codes = issue_codes(result)
        self.assertIn("SCENE_DIRECTING_PLAN_MISSING", codes)
        self.assertIn("EXECUTION_TEXT_REQUIRED", codes)

    def test_camera_angle_accepts_clear_natural_director_language(self) -> None:
        for natural_angle in (
            "车内平视",
            "远距离平视",
            "长焦平视",
            "背面平视",
            "车窗主观平视",
        ):
            draft = valid_draft()
            draft["shots"][0]["camera"]["angle"] = natural_angle
            result = delivery.validate_data(self.prepared(draft))
            self.assertNotIn("CAMERA_ANGLE_PURITY", issue_codes(result), natural_angle)

        draft = valid_draft()
        draft["shots"][0]["camera"]["angle"] = "略高平视"
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn("CAMERA_ANGLE_PURITY", issue_codes(result))

    def test_renderer_exposes_geometry_and_uses_semantic_framing_labels(self) -> None:
        draft = valid_draft()
        built = self.prepared(draft)
        description = built["shots"][0]["rendered_shot_description"]
        camera = built["shots"][0]["camera"]
        self.assertIn(f"摄影机位于{camera['position']}", description)
        self.assertIn(camera["logic"], description)
        self.assertIn(camera["composition"], description)
        self.assertTrue(description.startswith("【平视，过肩中近景，"))
        self.assertNotIn("过肩过肩", description)

        draft["shots"][0]["camera"]["framing_mode"] = "subjective"
        draft["shots"][0]["camera"]["foreground_characters"] = []
        built = self.prepared(draft)
        self.assertIn("主观中近景", built["shots"][0]["rendered_shot_description"])

    def test_renderer_standardizes_three_elements_without_closing_combinations(self) -> None:
        shot = valid_draft()["shots"][0]
        shot["camera"]["angle"] = "微仰视"
        shot["camera"]["shot_size"] = "中景→特写"
        shot["camera"]["framing_mode"] = "single"
        shot["camera"]["movement"] = "缓慢推进"
        self.assertTrue(
            delivery.render_shot_description(shot).startswith(
                "【微仰视，中景→特写，缓慢推进】\n【画面内容】"
            )
        )
        shot["camera"]["angle"] = "平视"
        shot["camera"]["shot_size"] = "全景"
        shot["camera"]["movement"] = "固定镜头"
        self.assertTrue(
            delivery.render_shot_description(shot).startswith(
                "【平视，全景，固定】\n【画面内容】"
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

    def test_source_only_execution_fails_and_blank_notes_are_compiled(self) -> None:
        draft = valid_draft()
        draft["shots"][0]["execution_text"] = (
            "【画面内容】林站在门口，周坐在桌边。林问：“你听见了吗？”"
        )
        draft["shots"][0]["notes"] = ""
        prepared = self.prepared(draft)
        result = delivery.validate_data(prepared)
        codes = issue_codes(result)
        self.assertIn("EXECUTION_SOURCE_PARAPHRASE_ONLY", codes)
        self.assertNotIn("SHOT_NOTE_EMPTY", codes)
        self.assertTrue(prepared["shots"][0]["notes"].startswith("[时长估算]"))

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
        self.assertNotIn("CAMERA_LOGIC_NON_GEOMETRIC", issue_codes(result))

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
            f"画面中{camera['composition']}。"
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
            f"画面中{camera['composition']}。"
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
            f"画面中{camera['composition']}。"
            "林问：“你听见了吗？”；周不抢答，只让呼吸和目光可见，问题落下后仍未回答。"
        )
        result = delivery.validate_data(self.prepared(draft))
        self.assertNotIn(
            "EXECUTION_META_LANGUAGE",
            {issue.code for issue in result.warnings},
        )

    def test_actual_ep15_v220_is_negative_regression_for_fifth_column(self) -> None:
        fixture = Path(
            "/Users/suvision/Documents/The mist/outputs/2026-07-26/"
            "Ep15-dibati-v220/deliverables/shot_data.json"
        )
        if not fixture.exists():
            self.skipTest("local EP15 v2.2.0 negative fixture is unavailable")
        data = json.loads(fixture.read_text(encoding="utf-8"))
        upgrade_draft_v240(data)
        result = delivery.validate_data(delivery.prepare_data(data))
        codes = issue_codes(result)
        self.assertNotIn("CAMERA_ANGLE_PURITY", codes)
        self.assertIn("VISIBLE_MACHINE_STATE", codes)

    def test_actual_ep15_v230_is_negative_regression_for_visible_camera_language(self) -> None:
        fixture = Path(
            "/Users/suvision/Documents/The mist/outputs/2026-07-26/"
            "Ep15-dibati-v230/deliverables/shot_data.json"
        )
        if not fixture.exists():
            self.skipTest("local EP15 v2.3.0 negative fixture is unavailable")
        data = json.loads(fixture.read_text(encoding="utf-8"))
        upgrade_draft_v240(data)
        result = delivery.validate_data(delivery.prepare_data(data))
        codes = issue_codes(result)
        self.assertIn("VISIBLE_MACHINE_STATE", codes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
