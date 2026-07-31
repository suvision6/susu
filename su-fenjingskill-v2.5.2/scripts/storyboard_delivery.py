#!/usr/bin/env python3
"""Build and validate deterministic six-column director storyboard deliveries."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import math
import os
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from xml.sax.saxutils import escape as xml_escape


SKILL_VERSION = "2.5.2"
CONTRACT_NAME = "shot-data"
CONTRACT_VERSION = "2.5.2"
SOURCE_SKILL_VERSION = "2.5.2"
SOURCE_SKILL = "su-fenjingskill"
GATE_2_RULE_REVISION = "2.5.2-binding-integrity-r1"
ORDINARY_SHOT_MAX_SECONDS = 10
OUTPUT_SUFFIXES = {
    "json": "shot-data.json",
    "markdown": "storyboard.md",
    "excel": "storyboard.xlsx",
    "report": "storyboard-validation.json",
}
HEADERS = [
    "镜号",
    "场景",
    "原剧本段落",
    "镜头时长",
    "运镜＋主画面描述",
    "备注",
]
TOP_LEVEL_KEYS = {
    "contract_name",
    "contract_version",
    "source_skill",
    "source_skill_version",
    "project_id",
    "content_hash",
    "confirmations",
    "source",
    "source_analysis",
    "director_style_options",
    "selected_style_option_id",
    "director_profile",
    "screen_events",
    "shot_plan",
    "scenes",
    "beats",
    "emotion_arcs",
    "performance_chains",
    "shots",
}
TOP_LEVEL_OPTIONAL_KEYS = {
    "director_style_options",
    "selected_style_option_id",
    "emotion_arcs",
    "performance_chains",
}
TOP_LEVEL_REQUIRED_KEYS = TOP_LEVEL_KEYS - TOP_LEVEL_OPTIONAL_KEYS
CONFIRMATION_KEYS = ("gate_1", "gate_2")
CONFIRMATION_ITEM_KEYS = {
    "status",
    "stage_digest",
    "confirmation_order",
    "notes",
}
FORBIDDEN_EXACT_KEYS = {
    "prompt",
    "prompt_text",
    "prompt_units",
    "prompt_unit_id",
    "negative_prompt",
    "video_prompt",
    "model",
    "model_name",
    "model_profile",
    "model_config",
    "model_settings",
    "max_clip_duration_seconds",
    "timeline",
    "cut_label",
    "cut_index",
    "grouping_reason",
    "standalone_reason",
    "source_shot_ids",
    "total_duration_seconds",
    "duration_blocks",
    "delivery",
}
DURATION_CHANNELS = (
    "action_seconds",
    "dialogue_seconds",
    "performance_seconds",
    "camera_seconds",
)
TIMING_SYNC_LABEL = "同步动作、台词与运镜"
TIMING_ASYNC_LABEL = "不能与前段并行的后续动作"
TIMING_HOLD_LABEL = "情绪与观看停留"
TIMING_LABELS = (
    TIMING_SYNC_LABEL,
    TIMING_ASYNC_LABEL,
    TIMING_HOLD_LABEL,
)
PICTURE_CONTENT_LABEL = "画面内容"
FORBIDDEN_EXECUTION_LABELS = (
    "起幅",
    "过程",
    "落幅",
    "机位与构图",
    "站位位移",
    "镜头调度",
    "人物表演与声音",
    "镜头结束",
)
FACT_TYPES = {
    "character",
    "action",
    "dialogue",
    "prop",
    "space",
    "position",
    "emotion",
    "sound",
    "reality",
}
DIALOGUE_TRANSLATION_POLICY_KEYS = {
    "mode",
    "original_language",
    "translation_languages",
    "resolution",
    "evidence",
}
DIALOGUE_MULTILINGUAL_POLICY_KEYS = {
    "mode",
    "spoken_languages",
    "resolution",
    "evidence",
}
DIALOGUE_LANGUAGE_POLICY_KEYS = (
    DIALOGUE_TRANSLATION_POLICY_KEYS | DIALOGUE_MULTILINGUAL_POLICY_KEYS
)
DIALOGUE_LANGUAGE_POLICY_MODES = {
    "original_with_translation",
    "multilingual_actual",
}
DIALOGUE_LANGUAGE_RESOLUTIONS = {"source_explicit", "user_confirmed"}
LANGUAGE_TAG_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
DIALOGUE_LINE_PATTERN = re.compile(
    r"^\s*(?:[-–—]\s*)?(?:\*{1,2})?"
    r"(?P<speaker>[^:：\n]{1,80}?)"
    r"(?:\*{1,2})?(?:（[^）\n]{0,80}）|\([^)\n]{0,80}\))?"
    r"\s*[:：]\s*(?P<text>.+?)\s*\*{0,2}\s*$"
)
DIALOGUE_ROLE_MARKER_PATTERN = re.compile(
    r"(?:原始台词|原文台词|原声台词|英文原声|英语原声|"
    r"译文|翻译|字幕|对照文本|original\s+dialogue|translation|subtitle)",
    re.IGNORECASE,
)
DIRECTOR_ANALYSIS_FIELDS = (
    "narrative_function",
    "dramatic_turn",
    "pov_owner",
    "power_relation",
    "subtext",
    "directorial_intent",
)
DIRECTOR_ANALYSIS_FIELD_SET = set(DIRECTOR_ANALYSIS_FIELDS)
PRESENTATION_REQUIREMENTS = {"must_be_clear", "supporting"}
SHOT_ISOLATION_VALUES = {"director_required", "not_required"}
DIRECTING_PLAN_REQUIRED_KEYS = {
    "scene_objective",
    "progression",
    "pov_flow",
    "entry_strategy",
    "style_anchors",
}
DIRECTING_PLAN_OPTIONAL_KEYS = {
    "entry_state",
    "exit_state",
    "rhythm_curve",
    "dialogue_geometry",
    "protected_processes",
    "visual_turns",
}
ENTRY_STRATEGY_REQUIRED_KEYS = {
    "mode",
    "observer_position",
    "required_spatial_information",
    "withheld_information",
    "reason",
}
ENTRY_STRATEGY_MODES = {
    "spatial_establish",
    "relational_entry",
    "character_entry",
    "subjective_entry",
    "deliberate_withhold",
}
DIALOGUE_DESIGN_REQUIRED_KEYS = {
    "speaker_sequence",
    "justification",
}
DIALOGUE_DESIGN_OPTIONAL_KEYS = {
    "mode",
    "face_readable_speakers",
    "listener_reaction_characters",
    "axis_id",
}
FRAMING_MODES = {
    "single",
    "over_shoulder",
    "two_shot",
    "multi_shot",
    "continuous_reframe",
    "subjective",
    "insert",
    "environment",
}
PURE_CAMERA_ANGLE_PATTERN = re.compile(
    r"^(?:(?:低机位|高机位|眼平高度|肩部高度|胸口高度|腰部高度|"
    r"膝部高度|手腕高度|桌面高度|地面高度|略低|略高|高位|低位))?"
    r"(?:平视|微俯视|俯视|微仰视|仰视|顶视)$"
)
PURE_SHOT_SIZE_PATTERN = re.compile(
    r"^(?:大全景|全景|中远景|中景|中近景|近景|特写|大特写)"
    r"(?:→(?:大全景|全景|中远景|中景|中近景|近景|特写|大特写))*$"
)
CAMERA_MOVEMENT_PUNCTUATION_PATTERN = re.compile(r"[，。；：、,.!?！？；：\n]")
CAMERA_MOVEMENT_ACTION_TERMS = (
    "固定",
    "静止",
    "锁定",
    "推进",
    "推近",
    "拉远",
    "拉出",
    "横移",
    "纵移",
    "跟随",
    "跟拍",
    "摇摄",
    "上摇",
    "下摇",
    "升起",
    "下降",
    "环绕",
    "手持",
    "车载",
    "斯坦尼康",
    "移焦",
)
VISIBLE_ASCII_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?P<token>[A-Za-z](?:[A-Za-z0-9_]*[A-Za-z0-9])?"
    r"(?:[.-][A-Za-z0-9_]+)*\.?)"
    r"(?![A-Za-z0-9_])"
)
VISIBLE_STANDARD_TERMS = {
    "AR",
    "CCTV",
    "CG",
    "CGI",
    "CU",
    "DOP",
    "ECU",
    "EWS",
    "FPS",
    "GPS",
    "HUD",
    "IMAX",
    "ISO",
    "LED",
    "MCU",
    "MLS",
    "MS",
    "OS",
    "OTS",
    "POV",
    "SFX",
    "UI",
    "VFX",
    "VO",
    "VR",
    "WS",
}
VISIBLE_CONTINUITY_VALUE_LABELS = {
    "offscreen": "画外",
    "onscreen": "画内",
}
CAMERA_ANGLE_CONTAMINATION_TERMS = {
    "车内",
    "室内",
    "室外",
    "街面",
    "教室",
    "窗边",
    "车窗",
    "正面",
    "背面",
    "侧面",
    "远距离",
    "近距离",
    "近距",
    "长焦",
    "广角",
    "主观",
    "客观",
}
SPEAKER_PRESENTATIONS = {
    "primary_face",
    "shared_face",
    "foreground_back",
    "onscreen_occluded",
    "not_visible",
    "mediated_source",
}
SCREEN_EVENT_REQUIRED_KEYS = {
    "screen_event_id",
    "scene_id",
    "event_order",
    "beat_ids",
    "source_spans",
    "covered_fact_ids",
    "visual_subjects",
    "visual_action",
    "viewing_requirement",
    "scale_requirement",
    "spatial_zone",
    "temporal_relation",
    "sound_fact_ids",
    "event_role",
    "primary_viewing_subject",
    "focus_scale",
}
SCREEN_EVENT_ROLES = {
    "spatial",
    "dialogue_turn",
    "action",
    "reaction",
    "reveal",
    "object_detail",
    "information_landing",
    "transition",
}
FOCUS_SCALES = {"space", "relation", "body", "face", "detail"}
SCREEN_EVENT_TEMPORAL_RELATIONS = {
    "sequential",
    "simultaneous_with_previous",
    "continuous_from_previous",
}
VIEWING_DECISION_KEYS = {
    "viewing_decision_id",
    "scene_id",
    "from_screen_event_id",
    "to_screen_event_id",
    "mode",
    "trigger",
    "viewing_change",
    "director_reason",
    "reframe_method",
    "non_cut_basis",
}
VIEWING_DECISION_MODES = {"cut", "hold", "reframe"}
REFRAME_METHODS = {"blocking", "camera_move", "focus_shift", "scale_change"}
NON_CUT_BASES = {
    "listener_ownership",
    "offscreen_or_vo",
    "continuous_action",
    "blocking_proof",
    "shared_staging",
    "delayed_reverse",
    "simultaneous_event",
}
MOVEMENT_PLAN_KEYS = {
    "class",
    "trigger",
    "speed",
    "path",
    "end_condition",
    "hold_reason",
}
SPATIAL_STRATEGY_KEYS = {"type", "description"}
SHOT_PHASE_KEYS = {
    "phase_id",
    "phase_order",
    "screen_event_ids",
    "duration_seconds",
    "camera_state",
    "sound_fact_ids",
}
EXECUTION_PASSAGE_KINDS = {
    "performance",
    "dialogue_exchange",
    "visual_state",
    "environment",
}
PERFORMANCE_CHAIN_ROLES = {"action", "reaction", "dialogue"}
SOURCE_REUSE_REASONS = {
    "simultaneous_isolation",
    "indivisible_source_action",
    "unavoidable_overlap",
}
PROFILE_VALUES = {
    "rhythm": {"restrained", "balanced", "kinetic"},
    "camera_energy": {"static", "responsive", "assertive"},
    "visual_distance": {"observational", "intimate", "mixed"},
    "performance_focus": {"body", "face", "blocking", "ensemble", "mixed"},
    "space_strategy": {"establish_then_enter", "embedded_reveal", "subjective", "mixed"},
}
PROFILE_REQUIRED_KEYS = set(PROFILE_VALUES) | {
    "transition_language",
    "priorities",
    "natural_language_intent",
}
TRANSITION_LANGUAGE_TO_TYPE = {
    "hard_cut": "cut",
    "action_cut": "action_cut",
    "gaze_cut": "gaze_cut",
    "sound_bridge": "sound_bridge",
    "long_hold": "hold",
    "dissolve": "dissolve",
    "fade": "fade",
}
TRANSITION_LANGUAGES = set(TRANSITION_LANGUAGE_TO_TYPE)
TRANSITION_TYPES = set(TRANSITION_LANGUAGE_TO_TYPE.values()) | {"scene_end"}
PERFORMANCE_PHASES = {
    "qi",
    "cheng",
    "zhuan",
    "shou",
    "qi_to_cheng",
    "cheng_to_zhuan",
    "zhuan_to_shou",
    "steady",
    "existing_transition",
    "not_applicable",
}
AXIS_TYPES = {"eyeline", "movement", "action", "spatial"}
AXIS_SIDES = {"side_a", "side_b", "on_axis", "not_applicable"}
SCREEN_DIRECTIONS = {
    "screen_left",
    "screen_right",
    "toward_camera",
    "away_camera",
    "neutral",
}
SCREEN_DIRECTION_KINDS = {"facing", "eyeline", "movement"}
CONTINUITY_EXCEPTION_TYPES = {
    "axis_cross",
    "screen_direction_break",
    "eyeline_break",
    "action_discontinuity",
    "state_discontinuity",
}
LONG_TAKE_STATUSES = {"supported", "needs_review"}
SCRIPT_VOICE_TYPES = {"scene_dialogue", "vo", "os", "mediated"}
SHOT_DELIVERIES = {"onscreen", "os", "vo", "mediated"}
INPUT_KINDS = {"full_screenplay", "screenplay_segment", "continuous_text"}
BOUNDARY_LOCKS = {
    "entire_submitted_text",
    "explicit_continuous_range",
    "user_locked_fragment",
}
SHOT_FORMS = {"long_take"}
SOURCE_ANALYSIS_FIELDS = {
    "source_boundary",
    "narrative_function",
    "dramatic_progression",
    "character_relations",
    "source_constraints",
}
STYLE_OPTION_KEYS = {"option_id", "label", "rationale", "profile"}
STYLE_OPTION_COUNTS = {3, 4}
STYLE_RATIONALE_SECTIONS = (
    "适配依据",
    "时间与剪辑",
    "摄影机",
    "空间与调度",
    "表演与观看",
    "主要收益",
    "主要风险",
)
STYLE_ANCHOR_KEYS = {
    "style_anchor_id",
    "profile_basis",
    "scene_application",
    "avoidance",
}
STYLE_PROFILE_BASIS_KEYS = {"field", "value"}
STYLE_PROFILE_BASIS_FIELDS = set(PROFILE_VALUES) | {
    "transition_language",
    "priorities",
    "natural_language_intent",
}
SHOT_PLAN_KEYS = {
    "planned_shot_count",
    "planned_edit_point_count",
    "planned_total_duration_seconds",
    "planned_units",
    "viewing_decisions",
    "edit_points",
    "reorders",
    "visual_uniformity_reviews",
}
PLAN_UNIT_REQUIRED_KEYS = {
    "plan_unit_id",
    "plan_order",
    "scene_id",
    "beat_ids",
    "screen_event_ids",
    "source_spans",
    "estimated_duration_seconds",
    "narrative_purpose",
    "visual_plan",
}
PLAN_UNIT_OPTIONAL_KEYS = {
    "shot_form",
    "source_reuse",
    "dialogue_design",
    "long_take_design",
}
LONG_TAKE_DESIGN_KEYS = {"reason", "supports", "protected_event_ids"}
LONG_TAKE_SUPPORTS = {
    "continuous_action",
    "performance_development",
    "spatial_progression",
    "blocking_proof",
    "real_time_tension",
}
VISUAL_PLAN_REQUIRED_KEYS = {
    "viewpoint_owner",
    "primary_subjects",
    "secondary_subjects",
    "shot_size",
    "angle",
    "camera_position",
    "framing_relation",
    "perspective_intent",
    "focus_plan",
    "spatial_strategy",
    "movement_plan",
    "start_frame",
    "end_frame",
    "motivation",
}
VISUAL_PLAN_OPTIONAL_KEYS = {"style_anchor_ids", "focal_length_mm"}
PERSPECTIVE_INTENTS = {
    "wide_spatial",
    "natural_relation",
    "compressed_distance",
    "detail_isolation",
}
SPATIAL_STRATEGY_TYPES = {
    "foreground_background",
    "deep_focus",
    "compressed_depth",
    "split_focus",
    "blocking_reveal",
    "sequential_reframe",
    "not_applicable",
}
CAMERA_MOVEMENT_CLASSES = {
    "fixed",
    "push",
    "pull",
    "pan_or_tilt",
    "track_or_follow",
    "orbit",
    "crane_or_boom",
    "focus",
    "vehicle_mounted",
    "handheld",
    "compound_move_then_fixed",
}
VISUAL_UNIFORMITY_REVIEW_KEYS = {
    "review_id",
    "scope",
    "scene_id",
    "dimension",
    "dominant_value",
    "reason",
    "style_anchor_ids",
}
VISUAL_UNIFORMITY_SCOPES = {"project", "scene"}
VISUAL_UNIFORMITY_DIMENSIONS = {"angle", "movement_class"}
EDIT_POINT_REQUIRED_KEYS = {
    "edit_point_id",
    "after_plan_unit_id",
    "before_plan_unit_id",
    "source_spans",
    "trigger",
    "editorial_gain",
}
EDIT_POINT_OPTIONAL_KEYS = {
    "broken_performance_chain_ids",
}
SOURCE_REUSE_KEYS = {
    "from_plan_unit_id",
    "reason",
    "justification",
}
REORDER_KEYS = {
    "reorder_id",
    "plan_unit_ids",
    "source_spans",
    "reason",
}
COVERAGE_EVIDENCE_KEYS = {"fact_id", "target_path", "evidence_quote"}
COVERAGE_TARGET_PATTERNS = (
    re.compile(r"^camera\.(?:composition|start_frame|end_frame)$"),
    re.compile(
        r"^blocking\[(?:0|[1-9][0-9]*)\]\."
        r"(?:start_position|action|end_position|facing|eyeline)$"
    ),
    re.compile(r"^performance\.visible_behavior\[(?:0|[1-9][0-9]*)\]$"),
    re.compile(r"^dialogue\[(?:0|[1-9][0-9]*)\]\.text$"),
    re.compile(r"^visible_characters\[(?:0|[1-9][0-9]*)\]$"),
    re.compile(r"^visible_props\[(?:0|[1-9][0-9]*)\]$"),
    re.compile(r"^environment_behavior\[(?:0|[1-9][0-9]*)\]$"),
    re.compile(r"^continuity_updates\[(?:0|[1-9][0-9]*)\]\.to$"),
    re.compile(r"^end_state\[(?:0|[1-9][0-9]*)\]$"),
    re.compile(r"^execution_passages\[(?:0|[1-9][0-9]*)\]\.text$"),
)
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
DELIVERY_SLUG_PATTERN = re.compile(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
)
ID_PATTERNS = {
    "scene": re.compile(r"^SC[0-9]{3,}$"),
    "beat": re.compile(r"^B[0-9]{3,}$"),
    "fact": re.compile(r"^F[0-9]{3,}$"),
    "shot": re.compile(r"^SH[0-9]{3,}$"),
    "emotion_arc": re.compile(r"^EA[0-9]{3,}$"),
    "axis": re.compile(r"^AX[0-9]{3,}$"),
    "style_option": re.compile(r"^STYLE-[0-9]{2,}$"),
    "style_anchor": re.compile(r"^SA[0-9]{3,}$"),
    "visual_review": re.compile(r"^VR[0-9]{3,}$"),
    "plan_unit": re.compile(r"^PU[0-9]{3,}$"),
    "edit_point": re.compile(r"^EP[0-9]{3,}$"),
    "reorder": re.compile(r"^RO[0-9]{3,}$"),
    "performance_chain": re.compile(r"^PC[0-9]{3,}$"),
    "isolation_group": re.compile(r"^IG[0-9]{3,}$"),
    "execution_passage": re.compile(r"^XP[0-9]{3,}$"),
    "screen_event": re.compile(r"^SEV[0-9]{3,}$"),
    "viewing_decision": re.compile(r"^VD[0-9]{3,}$"),
}
XLSX_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

GENERIC_CUT_TERMS = {
    "信息揭示",
    "动作边界",
    "视线变化",
    "关系变化",
    "空间变化",
    "反应",
    "转场",
    "节奏需要",
}
PLACEHOLDER_PHRASES = {
    "原文初态",
    "原文结束",
    "原文目标",
    "场内关系",
    "原文指定",
    "以原文主体、空间关系和关键遮挡构成可读画面",
    "在信息或动作边界处短促响应",
    "结束时停在新状态",
    "所在区域",
    "处于主要观看位置",
}
EXECUTION_SECTION_PLACEHOLDERS = {
    "按原文",
    "同上",
    "原文动作",
    "人物表演",
    "环境声音",
    "完成信息",
    "结束状态",
}
GENERIC_EXECUTION_PADDING = {
    "镜头落在",
    "画面呈现",
    "完成信息",
    "保持连续",
    "作为落点",
    "形成落点",
    "可见状态",
}
VISIBLE_MACHINE_STATE_PATTERN = re.compile(
    r"(?:(?:PU|EP|TB|AX|SC|F)[0-9]{2,}|side_[ab]|not_applicable)"
)
CAMERA_LOGIC_ANALYSIS_TERMS = {
    "为了",
    "用于",
    "承载",
    "呈现",
    "落实",
    "验证",
    "证明",
    "强调",
    "突出",
    "建立",
    "完成",
    "收束",
    "具体化",
    "作为",
    "成为",
}
CAMERA_MOVEMENT_CONTENT_TERMS = {
    "反应",
    "问话",
    "动作停点",
    "等待",
    "亮度",
    "压暗",
    "手腕",
    "手部",
    "面孔",
    "握紧",
    "落座",
    "遮挡",
    "公交",
    "同框",
}
EXECUTION_META_LANGUAGE_PATTERN = re.compile(
    r"(?:承载|落实|验证|作为落点|形成落点|具体化|完成验证|证明不是|成为视觉落点)"
)
EXECUTION_DETAIL_PATTERNS = (
    ("呼吸细节", re.compile(r"(?:轻吸|深吸|吸了?)一口气|呼吸(?:停|放慢|加快|变得)")),
    ("计拍停顿", re.compile(r"停(?:住|下)?半拍|停半拍")),
    ("机械计次", re.compile(r"来回[一二两三四五六七八九十0-9]+次")),
    ("身体重心", re.compile(r"身体重心.{0,8}(?:放松|前移|后移|改变)")),
    ("无来源否定动作", re.compile(r"不(?:向前迎接|因亮光闭眼|因亮光转头)")),
)
SCENE_DURATION_PATTERN = re.compile(
    r"(?:[（(]\s*约?\s*(?:\d+\s*分(?:钟)?(?:\s*\d+\s*秒)?|\d+\s*秒)\s*[）)])"
)
SOURCE_METADATA_PATTERNS = (
    re.compile(r"^第\s*\d+\s*集"),
    re.compile(r"^人物\s*[:：]"),
    re.compile(r"^\d+\s*-\s*\d+\s+.+\s+(?:日|夜)\s+(?:内|外)(?:\s|[（(]|$)"),
    re.compile(r"^片尾彩蛋\s+.+\s+(?:日|夜)\s+(?:内|外)(?:\s|[（(]|$)"),
)


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass
class ValidationResult:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.errors:
            return "FAIL"
        if self.warnings:
            return "WARN"
        return "PASS"

    def error(self, code: str, path: str, message: str) -> None:
        issue = Issue(code, path, message)
        if issue not in self.errors:
            self.errors.append(issue)

    def warn(self, code: str, path: str, message: str) -> None:
        issue = Issue(code, path, message)
        if issue not in self.warnings:
            self.warnings.append(issue)


class UnicodeContractError(ValueError):
    """Stable UTF-8 contract failure; never expose a raw UnicodeEncodeError."""

    def __init__(self, path: str, codepoint: int):
        self.code = "UNICODE_SURROGATE"
        self.path = path
        self.codepoint = codepoint
        super().__init__(
            f"{path} 包含无法编码为 UTF-8 的孤立 surrogate U+{codepoint:04X}。"
        )


def reject_json_constant(token: str) -> None:
    raise ValueError(f"JSON 不允许非标准数值：{token}")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle, parse_constant=reject_json_constant)
    if not isinstance(value, dict):
        raise ValueError("JSON 顶层必须是对象。")
    return value


def safe_path_key(path: str, key: str) -> str:
    return f"{path}[{json.dumps(key, ensure_ascii=True)}]"


def first_surrogate(value: Any, path: str = "$") -> tuple[str, int] | None:
    if isinstance(value, str):
        for character in value:
            codepoint = ord(character)
            if 0xD800 <= codepoint <= 0xDFFF:
                return path, codepoint
        return None
    if isinstance(value, list):
        for index, item in enumerate(value):
            found = first_surrogate(item, f"{path}[{index}]")
            if found:
                return found
        return None
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                found = first_surrogate(key, f"{path}.<key>")
                if found:
                    return found
                item_path = safe_path_key(path, key)
            else:
                item_path = path
            found = first_surrogate(item, item_path)
            if found:
                return found
    return None


def ensure_utf8_encodable(value: Any) -> None:
    found = first_surrogate(value)
    if found:
        raise UnicodeContractError(*found)


def encode_utf8(value: str, *, path: str = "$") -> bytes:
    found = first_surrogate(value, path)
    if found:
        raise UnicodeContractError(*found)
    return value.encode("utf-8")


def json_bytes(value: Any) -> bytes:
    ensure_utf8_encodable(value)
    rendered = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
    return encode_utf8(rendered)


def canonical_json_bytes(value: Any) -> bytes:
    ensure_utf8_encodable(value)
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return encode_utf8(rendered)


def normalize_locked_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.replace("\r\n", "\n").replace("\r", "\n")


def sha256_text(value: str) -> str:
    return hashlib.sha256(encode_utf8(value)).hexdigest()


def content_hash(data: dict[str, Any]) -> str:
    payload = copy.deepcopy(data)
    payload.pop("content_hash", None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def is_json_integer(value: Any, minimum: int | None = None) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return minimum is None or value >= minimum


def clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def camera_movement_class(value: Any) -> str:
    movement = clean_text(value)
    has_fixed = any(token in movement for token in ("固定", "静止", "锁定", "停住"))
    ordered_classes = (
        ("push", ("推进", "推近")),
        ("pull", ("拉远", "拉出")),
        ("pan_or_tilt", ("摇摄", "上摇", "下摇")),
        ("track_or_follow", ("横移", "纵移", "跟随", "跟拍")),
        ("orbit", ("环绕",)),
        ("crane_or_boom", ("升起", "下降")),
        ("focus", ("移焦",)),
        ("vehicle_mounted", ("车载",)),
        ("handheld", ("手持",)),
    )
    moving_classes = [
        class_name
        for class_name, tokens in ordered_classes
        if any(token in movement for token in tokens)
    ]
    if moving_classes and has_fixed:
        return "compound_move_then_fixed"
    if moving_classes:
        return moving_classes[0]
    if has_fixed:
        return "fixed"
    return "other"


def normalize_execution_text(value: Any) -> str:
    return re.sub(
        r"[\s，。！？；：、“”‘’《》【】（）()—…,.!?;:'\"/]+",
        "",
        clean_text(value),
    )


def duration_channel_value(block: dict[str, Any], channel: str) -> int:
    value = block.get(channel)
    return value if is_json_integer(value, 0) else 0


def timing_components(shot: dict[str, Any]) -> tuple[int, int, int, int]:
    by_label = {
        clean_text(block.get("label")): block
        for block in as_list(shot.get("duration_blocks"))
        if isinstance(block, dict)
    }
    sync = by_label.get(TIMING_SYNC_LABEL, {})
    asynchronous = by_label.get(TIMING_ASYNC_LABEL, {})
    hold = by_label.get(TIMING_HOLD_LABEL, {})
    return (
        duration_channel_value(sync, "action_seconds"),
        duration_channel_value(sync, "dialogue_seconds"),
        duration_channel_value(asynchronous, "action_seconds"),
        duration_channel_value(hold, "performance_seconds"),
    )


def canonicalize_shot_notes(shot: dict[str, Any]) -> str:
    return clean_text(shot.get("notes"))


def visible_ascii_tokens(value: Any) -> list[str]:
    return [
        match.group("token")
        for match in VISIBLE_ASCII_TOKEN_PATTERN.finditer(clean_text(value))
    ]


def standard_term_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", value).upper()


def visible_continuity_value(value: Any) -> str:
    cleaned = clean_text(value)
    return VISIBLE_CONTINUITY_VALUE_LABELS.get(cleaned, cleaned)


def validate_picture_language(
    picture_content: str,
    *,
    locked_text: str,
    path: str,
    result: ValidationResult,
) -> None:
    disallowed: list[str] = []
    for token in visible_ascii_tokens(picture_content):
        if standard_term_key(token) in VISIBLE_STANDARD_TERMS:
            continue
        if token in locked_text:
            continue
        if token not in disallowed:
            disallowed.append(token)
    if disallowed:
        result.error(
            "EXECUTION_LANGUAGE_DEFAULT",
            path,
            "除通用标准术语和原剧本逐字内容外，【画面内容】默认使用中文；"
            f"检测到未转换的英文描述词：{', '.join(disallowed)}。",
        )


def execution_detail_delta(
    text: str,
    *,
    facts: list[dict[str, Any]],
) -> str:
    residual = normalize_execution_text(text)
    for fact in sorted(
        facts,
        key=lambda item: len(normalize_execution_text(item.get("text"))),
        reverse=True,
    ):
        fact_text = normalize_execution_text(fact.get("text"))
        if fact_text:
            residual = residual.replace(fact_text, "")
        speaker = normalize_execution_text(fact.get("speaker"))
        if speaker:
            residual = residual.replace(speaker, "")
    for token in ("VO", "画外", "对", "说"):
        residual = residual.replace(token, "")
    for phrase in GENERIC_EXECUTION_PADDING:
        residual = residual.replace(normalize_execution_text(phrase), "")
    return residual


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def id_is_canonical(value: Any, kind: str) -> bool:
    if not isinstance(value, str) or not ID_PATTERNS[kind].fullmatch(value):
        return False
    suffix = re.search(r"([0-9]+)$", value)
    return bool(suffix and int(suffix.group(1)) > 0)


def require_nonempty_string(
    value: Any,
    *,
    path: str,
    result: ValidationResult,
    code: str = "STRING_REQUIRED",
) -> str:
    if not isinstance(value, str) or not value.strip():
        result.error(code, path, "必须是无首尾空白的非空字符串。")
        return ""
    if value != value.strip():
        result.error(code, path, "不得包含首尾空白。")
    return value.strip()


def require_string(
    value: Any,
    *,
    path: str,
    result: ValidationResult,
    code: str = "STRING_REQUIRED",
) -> str:
    if not isinstance(value, str):
        result.error(code, path, "必须是字符串。")
        return ""
    return value


def validate_json_values(value: Any, result: ValidationResult, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, str):
        for character in value:
            codepoint = ord(character)
            if 0xD800 <= codepoint <= 0xDFFF:
                result.error(
                    "UNICODE_SURROGATE",
                    path,
                    f"包含无法编码为 UTF-8 的孤立 surrogate U+{codepoint:04X}。",
                )
                break
            if not (
                codepoint in {0x09, 0x0A, 0x0D}
                or 0x20 <= codepoint <= 0xD7FF
                or 0xE000 <= codepoint <= 0xFFFD
                or 0x10000 <= codepoint <= 0x10FFFF
            ):
                result.error(
                    "XML_CHARACTER",
                    path,
                    f"包含 Excel XML 不允许的字符 U+{codepoint:04X}。",
                )
                break
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            result.error("JSON_NUMBER", path, "不得包含 NaN 或 Infinity。")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_json_values(item, result, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                result.error("JSON_KEY", path, "JSON 对象 key 必须是字符串。")
                continue
            validate_json_values(key, result, f"{path}.<key>")
            validate_json_values(item, result, safe_path_key(path, key))
        return
    result.error("JSON_TYPE", path, f"不支持 JSON 类型：{type(value).__name__}。")


def validate_forbidden_keys(value: Any, result: ValidationResult, path: str = "$") -> None:
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_forbidden_keys(item, result, f"{path}[{index}]")
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        lowered = key.casefold()
        if "prompt" in lowered or lowered in FORBIDDEN_EXACT_KEYS:
            result.error(
                "DOWNSTREAM_FIELD_FORBIDDEN",
                f"{path}.{key}",
                f"导演合同禁止下游字段 `{key}`。",
            )
        validate_forbidden_keys(item, result, f"{path}.{key}")


def list_of_unique_strings(
    value: Any,
    *,
    path: str,
    result: ValidationResult,
    allow_empty: bool = True,
) -> list[str]:
    if not isinstance(value, list):
        result.error("ARRAY_REQUIRED", path, "必须是数组。")
        return []
    if not value and not allow_empty:
        result.error("ARRAY_EMPTY", path, "不得为空。")
    output: list[str] = []
    for index, item in enumerate(value):
        text = require_nonempty_string(
            item,
            path=f"{path}[{index}]",
            result=result,
        )
        if text:
            if text in output:
                result.error("ARRAY_DUPLICATE", f"{path}[{index}]", f"重复值：{text}。")
            output.append(text)
    return output


def validate_director_analysis(
    value: Any,
    *,
    path: str,
    result: ValidationResult,
) -> None:
    """Validate only the nullable structure; never interpret analysis content."""

    if not isinstance(value, dict):
        result.error("DIRECTOR_ANALYSIS", path, "director_analysis 必须是对象。")
        return
    actual_fields = set(value)
    for field_name in sorted(DIRECTOR_ANALYSIS_FIELD_SET - actual_fields):
        result.error(
            "DIRECTOR_ANALYSIS_FIELD_MISSING",
            f"{path}.{field_name}",
            "director_analysis 存在时必须保留全部六个 nullable 字段。",
        )
    for field_name in sorted(actual_fields - DIRECTOR_ANALYSIS_FIELD_SET):
        result.error(
            "DIRECTOR_ANALYSIS_FIELD_UNKNOWN",
            f"{path}.{field_name}",
            "不是 director_analysis/2.5.2 字段。",
        )
    for field_name in DIRECTOR_ANALYSIS_FIELDS:
        if field_name not in value:
            continue
        field_value = value.get(field_name)
        if field_value is None:
            continue
        if (
            not isinstance(field_value, str)
            or not field_value.strip()
            or field_value != field_value.strip()
        ):
            result.error(
                "DIRECTOR_ANALYSIS_VALUE",
                f"{path}.{field_name}",
                "只允许 null 或无首尾空白的非空字符串。",
            )


def reject_director_analysis_in_fact_or_dialogue(
    value: Any,
    *,
    path: str,
    result: ValidationResult,
) -> None:
    """Keep inferred director analysis out of source facts and verbatim dialogue."""

    if isinstance(value, list):
        for index, item in enumerate(value):
            reject_director_analysis_in_fact_or_dialogue(
                item,
                path=f"{path}[{index}]",
                result=result,
            )
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        item_path = f"{path}.{key}"
        if key == "director_analysis" or key in DIRECTOR_ANALYSIS_FIELD_SET:
            result.error(
                "DIRECTOR_ANALYSIS_SCOPE",
                item_path,
                "导演分析字段不得进入 fact 或 dialogue。",
            )
        reject_director_analysis_in_fact_or_dialogue(item, path=item_path, result=result)


def span_texts(
    spans: Any,
    locked_text: str,
    *,
    path: str,
    result: ValidationResult,
) -> list[str]:
    if not isinstance(spans, list) or not spans:
        result.error("SOURCE_SPANS", path, "必须是非空 source span 数组。")
        return []
    output: list[str] = []
    previous_end = -1
    seen: set[tuple[int, int]] = set()
    for index, span in enumerate(spans):
        item_path = f"{path}[{index}]"
        if not isinstance(span, dict):
            result.error("SOURCE_SPAN", item_path, "source span 必须是对象。")
            continue
        start = span.get("start")
        end = span.get("end")
        if not is_json_integer(start, 0) or not is_json_integer(end, 1):
            result.error("SOURCE_SPAN_RANGE", item_path, "start/end 必须是合法 JSON 整数。")
            continue
        assert isinstance(start, int) and isinstance(end, int)
        if start >= end or end > len(locked_text):
            result.error("SOURCE_SPAN_RANGE", item_path, "区间超出 locked_text 或为空。")
            continue
        if start < previous_end:
            result.error("SOURCE_SPAN_ORDER", item_path, "source spans 必须升序且不重叠。")
        if (start, end) in seen:
            result.error("SOURCE_SPAN_DUPLICATE", item_path, "source span 不得重复。")
        previous_end = max(previous_end, end)
        seen.add((start, end))
        text = locked_text[start:end]
        expected_hash = sha256_text(text)
        if span.get("text_hash") != expected_hash:
            result.error("SOURCE_SPAN_HASH", f"{item_path}.text_hash", "span hash 不匹配。")
        output.append(text)
    return output


def populate_span_hashes(spans: Any, locked_text: str) -> None:
    if not isinstance(spans, list):
        return
    for span in spans:
        if not isinstance(span, dict):
            continue
        start = span.get("start")
        end = span.get("end")
        if (
            is_json_integer(start, 0)
            and is_json_integer(end, 1)
            and isinstance(start, int)
            and isinstance(end, int)
            and start < end <= len(locked_text)
        ):
            span["text_hash"] = sha256_text(locked_text[start:end])


def populate_all_span_hashes(data: dict[str, Any], locked_text: str) -> None:
    for beat in as_list(data.get("beats")):
        if not isinstance(beat, dict):
            continue
        populate_span_hashes(beat.get("source_spans"), locked_text)
        for fact in as_list(beat.get("facts")):
            if isinstance(fact, dict):
                populate_span_hashes(fact.get("source_spans"), locked_text)
    for shot in as_list(data.get("shots")):
        if isinstance(shot, dict):
            populate_span_hashes(shot.get("source_spans"), locked_text)
    for event in as_list(data.get("screen_events")):
        if isinstance(event, dict):
            populate_span_hashes(event.get("source_spans"), locked_text)
    shot_plan = as_dict(data.get("shot_plan"))
    for collection in ("planned_units", "edit_points", "reorders"):
        for item in as_list(shot_plan.get(collection)):
            if isinstance(item, dict):
                populate_span_hashes(item.get("source_spans"), locked_text)


def span_coordinates(spans: Any, locked_text: str) -> list[tuple[int, int]]:
    output: list[tuple[int, int]] = []
    if not isinstance(spans, list):
        return output
    for span in spans:
        if not isinstance(span, dict):
            continue
        start = span.get("start")
        end = span.get("end")
        if (
            is_json_integer(start, 0)
            and is_json_integer(end, 1)
            and isinstance(start, int)
            and isinstance(end, int)
            and start < end <= len(locked_text)
        ):
            output.append((start, end))
    return output


def spans_contained(
    inner: list[tuple[int, int]],
    outer: list[tuple[int, int]],
) -> bool:
    return bool(inner) and bool(outer) and all(
        any(outer_start <= start and end <= outer_end for outer_start, outer_end in outer)
        for start, end in inner
    )


def spans_overlap(
    left: list[tuple[int, int]],
    right: list[tuple[int, int]],
) -> bool:
    return any(
        left_start < right_end and right_start < left_end
        for left_start, left_end in left
        for right_start, right_end in right
    )


def span_source_text(spans: Any, locked_text: str) -> str:
    return "\n".join(locked_text[start:end] for start, end in span_coordinates(spans, locked_text))


def normalized_stage_copy(data: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(data)
    derive_edit_points(normalized)
    source = as_dict(normalized.get("source"))
    normalized["source"] = source
    locked_text = normalize_locked_text(source.get("locked_text"))
    source["locked_text"] = locked_text
    source["locked_text_hash"] = sha256_text(locked_text)
    populate_all_span_hashes(normalized, locked_text)
    return normalized


def cut_atomicity_metrics(data: dict[str, Any]) -> dict[str, Any]:
    plan = as_dict(data.get("shot_plan"))
    units = [
        unit for unit in as_list(plan.get("planned_units")) if isinstance(unit, dict)
    ]
    events = [
        event for event in as_list(data.get("screen_events")) if isinstance(event, dict)
    ]
    decisions = [
        item
        for item in as_list(plan.get("viewing_decisions"))
        if isinstance(item, dict)
    ]
    fact_lookup = {
        clean_text(fact.get("fact_id")): fact
        for beat in as_list(data.get("beats"))
        if isinstance(beat, dict)
        for fact in as_list(beat.get("facts"))
        if isinstance(fact, dict) and clean_text(fact.get("fact_id"))
    }
    events_by_scene: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        events_by_scene.setdefault(clean_text(event.get("scene_id")), []).append(event)
    dialogue_handoff_count = 0
    dialogue_handoff_cut_count = 0
    cut_boundaries = {
        (
            clean_text(item.get("from_screen_event_id")),
            clean_text(item.get("to_screen_event_id")),
        )
        for item in decisions
        if item.get("mode") == "cut"
    }
    for scene_events in events_by_scene.values():
        scene_events.sort(key=lambda item: int(item.get("event_order", 0)))
        dialogue_events = [
            (index, event, screen_event_speakers(event, fact_lookup)[0])
            for index, event in enumerate(scene_events)
            if screen_event_speakers(event, fact_lookup)
        ]
        for (left_index, _, left_speaker), (
            right_index,
            _,
            right_speaker,
        ) in zip(dialogue_events, dialogue_events[1:]):
            if left_speaker == right_speaker:
                continue
            dialogue_handoff_count += 1
            intervening_boundaries = {
                (
                    clean_text(scene_events[index].get("screen_event_id")),
                    clean_text(scene_events[index + 1].get("screen_event_id")),
                )
                for index in range(left_index, right_index)
            }
            if cut_boundaries.intersection(intervening_boundaries):
                dialogue_handoff_cut_count += 1
    durations = [
        int(unit.get("estimated_duration_seconds"))
        for unit in units
        if is_json_integer(unit.get("estimated_duration_seconds"), 1)
    ]
    total_duration = sum(durations)
    non_cut_exceptions = [
        {
            "viewing_decision_id": clean_text(item.get("viewing_decision_id")),
            "mode": item.get("mode"),
            "non_cut_basis": item.get("non_cut_basis"),
        }
        for item in decisions
        if item.get("mode") in {"hold", "reframe"}
    ]
    long_takes = [
        {
            "plan_unit_id": clean_text(unit.get("plan_unit_id")),
            "duration_seconds": unit.get("estimated_duration_seconds"),
            "protected_event_ids": as_list(
                as_dict(unit.get("long_take_design")).get("protected_event_ids")
            ),
        }
        for unit in units
        if unit.get("shot_form") == "long_take"
    ]
    return {
        "average_shot_duration_seconds": (
            round(total_duration / len(durations), 3) if durations else 0
        ),
        "edit_points_per_minute": (
            round(len(cut_boundaries) * 60 / total_duration, 3)
            if total_duration
            else 0
        ),
        "ordinary_shots_over_10_seconds": sum(
            is_json_integer(unit.get("estimated_duration_seconds"), 1)
            and int(unit.get("estimated_duration_seconds")) > ORDINARY_SHOT_MAX_SECONDS
            and unit.get("shot_form") != "long_take"
            for unit in units
        ),
        "dialogue_handoffs": dialogue_handoff_count,
        "dialogue_handoffs_with_cuts": dialogue_handoff_cut_count,
        "multi_event_plan_units": sum(
            len(as_list(unit.get("screen_event_ids"))) > 1 for unit in units
        ),
        "non_cut_exceptions": non_cut_exceptions,
        "long_takes": long_takes,
    }


def cut_atomicity_blockers(data: dict[str, Any]) -> list[str]:
    plan = as_dict(data.get("shot_plan"))
    units = [
        unit for unit in as_list(plan.get("planned_units")) if isinstance(unit, dict)
    ]
    events = [
        event for event in as_list(data.get("screen_events")) if isinstance(event, dict)
    ]
    event_lookup = {
        clean_text(event.get("screen_event_id")): event
        for event in events
        if clean_text(event.get("screen_event_id"))
    }
    fact_lookup = {
        clean_text(fact.get("fact_id")): fact
        for beat in as_list(data.get("beats"))
        if isinstance(beat, dict)
        for fact in as_list(beat.get("facts"))
        if isinstance(fact, dict) and clean_text(fact.get("fact_id"))
    }
    event_to_unit = {
        str(event_id): unit
        for unit in units
        for event_id in as_list(unit.get("screen_event_ids"))
    }
    blockers: set[str] = set()
    for event in events:
        if not SCREEN_EVENT_REQUIRED_KEYS.issubset(event):
            blockers.add("SCREEN_EVENT_ATOMICITY_OVERLOAD")
        speakers = screen_event_speakers(event, fact_lookup)
        if len(set(speakers)) > 1:
            blockers.add("SCREEN_EVENT_MULTI_SPEAKER")
        dialogue_count = sum(
            fact_lookup.get(str(fact_id), {}).get("type") == "dialogue"
            for fact_id in as_list(event.get("covered_fact_ids"))
        )
        if dialogue_count > 1:
            blockers.add("SCREEN_EVENT_ATOMICITY_OVERLOAD")
        covered_ids = as_list(event.get("covered_fact_ids"))
        if dialogue_count and dialogue_count != len(covered_ids):
            blockers.add("SCREEN_EVENT_ATOMICITY_OVERLOAD")
        non_dialogue_facts = [
            fact_lookup.get(str(fact_id), {})
            for fact_id in covered_ids
            if fact_lookup.get(str(fact_id), {}).get("type") != "dialogue"
        ]
        if len(non_dialogue_facts) > 1:
            if (
                len(
                    {
                        clean_text(fact.get("type"))
                        for fact in non_dialogue_facts
                    }
                )
                > 1
                or len(
                    {
                        tuple(
                            sorted(
                                clean_text(item)
                                for item in as_list(fact.get("performers"))
                                if clean_text(item)
                            )
                        )
                        for fact in non_dialogue_facts
                    }
                )
                > 1
            ):
                blockers.add("SCREEN_EVENT_ATOMICITY_OVERLOAD")
    for unit in units:
        duration = unit.get("estimated_duration_seconds")
        if (
            is_json_integer(duration, 1)
            and int(duration) > ORDINARY_SHOT_MAX_SECONDS
            and unit.get("shot_form") != "long_take"
        ):
            blockers.add("ORDINARY_SHOT_DURATION_EXCEEDED")
        if unit.get("shot_form") == "long_take" and not isinstance(
            unit.get("long_take_design"), dict
        ):
            blockers.add("LONG_TAKE_DESIGN_REQUIRED")
    for decision in as_list(plan.get("viewing_decisions")):
        if not isinstance(decision, dict):
            continue
        mode = decision.get("mode")
        basis = decision.get("non_cut_basis")
        if (mode == "cut" and basis is not None) or (
            mode in {"hold", "reframe"} and basis not in NON_CUT_BASES
        ):
            blockers.add("NONCUT_BASIS_REQUIRED")
        from_event = event_lookup.get(
            clean_text(decision.get("from_screen_event_id")), {}
        )
        to_event = event_lookup.get(clean_text(decision.get("to_screen_event_id")), {})
        from_speakers = screen_event_speakers(from_event, fact_lookup)
        to_speakers = screen_event_speakers(to_event, fact_lookup)
        if (
            mode != "cut"
            and from_speakers
            and to_speakers
            and from_speakers[-1] != to_speakers[0]
        ):
            unit = event_to_unit.get(
                clean_text(decision.get("from_screen_event_id")), {}
            )
            if not isinstance(unit.get("dialogue_design"), dict):
                blockers.add("DIALOGUE_HANDOFF_CUT_REQUIRED")
        if (
            mode == "hold"
            and clean_text(from_event.get("focus_scale"))
            != clean_text(to_event.get("focus_scale"))
        ):
            blockers.add("NONCUT_VISUAL_PLAN_MISMATCH")
    decision_lookup = {
        (
            clean_text(decision.get("from_screen_event_id")),
            clean_text(decision.get("to_screen_event_id")),
        ): decision
        for decision in as_list(plan.get("viewing_decisions"))
        if isinstance(decision, dict)
    }
    events_by_scene: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        events_by_scene.setdefault(clean_text(event.get("scene_id")), []).append(event)
    for scene_events in events_by_scene.values():
        scene_events.sort(key=lambda item: int(item.get("event_order", 0)))
        dialogue_events = [
            (index, event, screen_event_speakers(event, fact_lookup)[0])
            for index, event in enumerate(scene_events)
            if screen_event_speakers(event, fact_lookup)
        ]
        for (left_index, left_event, left_speaker), (
            right_index,
            _,
            right_speaker,
        ) in zip(dialogue_events, dialogue_events[1:]):
            if left_speaker == right_speaker:
                continue
            boundary_decisions = [
                decision_lookup.get(
                    (
                        clean_text(scene_events[index].get("screen_event_id")),
                        clean_text(
                            scene_events[index + 1].get("screen_event_id")
                        ),
                    ),
                    {},
                )
                for index in range(left_index, right_index)
            ]
            if any(item.get("mode") == "cut" for item in boundary_decisions):
                continue
            owning_unit = event_to_unit.get(
                clean_text(left_event.get("screen_event_id")), {}
            )
            if (
                not isinstance(owning_unit.get("dialogue_design"), dict)
                or not any(
                    item.get("non_cut_basis")
                    in {
                        "listener_ownership",
                        "offscreen_or_vo",
                        "continuous_action",
                        "shared_staging",
                        "delayed_reverse",
                    }
                    for item in boundary_decisions
                )
            ):
                blockers.add("DIALOGUE_HANDOFF_CUT_REQUIRED")
    return sorted(blockers)


def director_readiness_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    events = [
        item for item in as_list(data.get("screen_events")) if isinstance(item, dict)
    ]
    plan = as_dict(data.get("shot_plan"))
    units = [
        item for item in as_list(plan.get("planned_units")) if isinstance(item, dict)
    ]
    decisions = [
        item for item in as_list(plan.get("viewing_decisions")) if isinstance(item, dict)
    ]
    incomplete_units = [
        clean_text(unit.get("plan_unit_id"))
        for unit in units
        if not VISUAL_PLAN_REQUIRED_KEYS.issubset(as_dict(unit.get("visual_plan")))
        or not as_list(unit.get("screen_event_ids"))
    ]
    rhythm = cut_atomicity_metrics(data)
    atomicity_blockers = cut_atomicity_blockers(data)
    status = (
        "READY"
        if events
        and units
        and not incomplete_units
        and rhythm["ordinary_shots_over_10_seconds"] == 0
        and not atomicity_blockers
        else "BLOCKED"
    )
    return {
        "status": status,
        "screen_event_count": len(events),
        "viewing_decision_count": len(decisions),
        "planned_unit_count": len(units),
        "incomplete_plan_unit_ids": incomplete_units,
        "rhythm_metrics": rhythm,
        "blocking_issue_codes": atomicity_blockers,
    }


def stage_payload(data: dict[str, Any], gate: int) -> dict[str, Any]:
    normalized = normalized_stage_copy(data)
    gate_source = copy.deepcopy(as_dict(normalized.get("source")))
    gate_source.pop("delivery_slug", None)
    gate_1_payload = {
        "source": gate_source,
        "source_analysis": normalized.get("source_analysis"),
        "director_profile": normalized.get("director_profile"),
    }
    if "director_style_options" in normalized:
        gate_1_payload["director_style_options"] = normalized.get(
            "director_style_options"
        )
    if "selected_style_option_id" in normalized:
        gate_1_payload["selected_style_option_id"] = normalized.get(
            "selected_style_option_id"
        )
    if gate == 1:
        return gate_1_payload
    if gate == 2:
        scene_plans = [
            {
                "scene_id": scene.get("scene_id"),
                "scene": scene.get("scene"),
                "directing_plan": scene.get("directing_plan"),
            }
            for scene in as_list(normalized.get("scenes"))
            if isinstance(scene, dict)
        ]
        return {
            "gate_2_rule_revision": GATE_2_RULE_REVISION,
            "gate_1_digest": hashlib.sha256(
                canonical_json_bytes(gate_1_payload)
            ).hexdigest(),
            "scene_plans": scene_plans,
            "screen_events": normalized.get("screen_events"),
            "shot_plan": normalized.get("shot_plan"),
            "visual_design": visual_distribution_summary(normalized),
            "director_readiness": director_readiness_snapshot(normalized),
        }
    raise ValueError("gate 必须为 1 或 2。")


def stage_digest(data: dict[str, Any], gate: int) -> str:
    return hashlib.sha256(canonical_json_bytes(stage_payload(data, gate))).hexdigest()


def render_dialogue(item: dict[str, Any]) -> str:
    speaker = clean_text(item.get("speaker"))
    delivery = clean_text(item.get("shot_delivery"))
    addressee = clean_text(item.get("addressee"))
    if delivery == "vo":
        lead = f"{speaker}VO"
    elif delivery == "os":
        lead = f"{speaker}画外"
    elif addressee:
        lead = f"{speaker}对{addressee}说"
    else:
        lead = f"{speaker}说"
    return f"{lead}：“{item.get('text', '')}”"


def framing_display(camera: dict[str, Any]) -> str:
    return clean_text(camera.get("shot_size"))


def movement_display(camera: dict[str, Any]) -> str:
    movement = clean_text(camera.get("movement"))
    if movement in {"固定镜头", "静止镜头", "静止", "锁定镜头"}:
        return "固定"
    return movement


def render_shot_description(shot: dict[str, Any], *, is_first_scene_shot: bool = False) -> str:
    camera = as_dict(shot.get("camera"))
    lines = [
        (
            f"【{framing_display(camera)}｜"
            f"{clean_text(camera.get('angle'))}｜"
            f"{movement_display(camera)}】"
        )
    ]
    execution_text = clean_text(shot.get("execution_text"))
    if execution_text:
        lines.append(execution_text)
    return "\n".join(line for line in lines if line)


def derive_edit_points(data: dict[str, Any]) -> None:
    plan = as_dict(data.get("shot_plan"))
    units = [
        item for item in as_list(plan.get("planned_units")) if isinstance(item, dict)
    ]
    event_to_unit: dict[str, str] = {}
    unit_lookup: dict[str, dict[str, Any]] = {}
    for unit in units:
        unit_id = clean_text(unit.get("plan_unit_id"))
        if unit_id:
            unit_lookup[unit_id] = unit
        for event_id in as_list(unit.get("screen_event_ids")):
            if isinstance(event_id, str):
                event_to_unit[event_id] = unit_id
    event_lookup = {
        clean_text(event.get("screen_event_id")): event
        for event in as_list(data.get("screen_events"))
        if isinstance(event, dict) and clean_text(event.get("screen_event_id"))
    }
    edit_points: list[dict[str, Any]] = []
    for decision in as_list(plan.get("viewing_decisions")):
        if not isinstance(decision, dict) or decision.get("mode") != "cut":
            continue
        from_id = clean_text(decision.get("from_screen_event_id"))
        to_id = clean_text(decision.get("to_screen_event_id"))
        left_id = event_to_unit.get(from_id, "")
        right_id = event_to_unit.get(to_id, "")
        unit_order = {clean_text(unit.get("plan_unit_id")): index for index, unit in enumerate(units)}
        after_id, before_id = (
            (left_id, right_id)
            if unit_order.get(left_id, -1) <= unit_order.get(right_id, -1)
            else (right_id, left_id)
        )
        source_spans: list[dict[str, Any]] = []
        seen: set[tuple[Any, Any]] = set()
        for event_id in (from_id, to_id):
            for span in as_list(as_dict(event_lookup.get(event_id)).get("source_spans")):
                if not isinstance(span, dict):
                    continue
                key = (span.get("start"), span.get("end"))
                if key in seen:
                    continue
                seen.add(key)
                source_spans.append(copy.deepcopy(span))
        source_spans.sort(key=lambda item: (item.get("start", -1), item.get("end", -1)))
        edit_points.append(
            {
                "edit_point_id": f"EP{len(edit_points) + 1:03d}",
                "after_plan_unit_id": after_id,
                "before_plan_unit_id": before_id,
                "source_spans": source_spans,
                "trigger": decision.get("trigger"),
                "editorial_gain": decision.get("director_reason"),
            }
        )
    plan["edit_points"] = edit_points
    plan["planned_shot_count"] = len(units)
    plan["planned_edit_point_count"] = len(edit_points)
    plan["planned_total_duration_seconds"] = sum(
        int(unit.get("estimated_duration_seconds"))
        for unit in units
        if is_json_integer(unit.get("estimated_duration_seconds"), 1)
    )


def prepare_data(raw: dict[str, Any]) -> dict[str, Any]:
    unicode_result = ValidationResult()
    validate_json_values(raw, unicode_result)
    if any(issue.code == "UNICODE_SURROGATE" for issue in unicode_result.errors):
        raise ValidationFailure(make_report(raw, unicode_result))
    data = copy.deepcopy(raw)
    derive_edit_points(data)
    source = as_dict(data.get("source"))
    if source is not data.get("source"):
        data["source"] = source
    locked_text = normalize_locked_text(source.get("locked_text"))
    source["locked_text"] = locked_text
    source["locked_text_hash"] = sha256_text(locked_text)
    populate_all_span_hashes(data, locked_text)
    seen_scene_ids: set[str] = set()
    for shot in as_list(data.get("shots")):
        if isinstance(shot, dict):
            scene_id = clean_text(shot.get("scene_id"))
            shot["notes"] = canonicalize_shot_notes(shot)
            shot["rendered_shot_description"] = render_shot_description(
                shot,
                is_first_scene_shot=scene_id not in seen_scene_ids,
            )
            seen_scene_ids.add(scene_id)
    data["content_hash"] = content_hash(data)
    return data


def validate_contract_identity(data: dict[str, Any], result: ValidationResult) -> None:
    actual_keys = set(data)
    for key in sorted(TOP_LEVEL_REQUIRED_KEYS - actual_keys):
        result.error("TOP_LEVEL_MISSING", f"$.{key}", "缺少顶层必需字段。")
    for key in sorted(actual_keys - TOP_LEVEL_KEYS):
        result.error("TOP_LEVEL_UNKNOWN", f"$.{key}", "顶层存在未定义字段。")
    expected = {
        "contract_name": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "source_skill": SOURCE_SKILL,
        "source_skill_version": SOURCE_SKILL_VERSION,
    }
    for key, value in expected.items():
        if data.get(key) != value:
            result.error("CONTRACT_IDENTITY", f"$.{key}", f"必须为 `{value}`。")
    project_id = data.get("project_id")
    if not isinstance(project_id, str) or not PROJECT_ID_PATTERN.fullmatch(project_id):
        result.error(
            "PROJECT_ID",
            "$.project_id",
            "必须是 ASCII 字母/数字开头且仅含字母、数字、点、下划线或短横线。",
        )
    declared_hash = data.get("content_hash")
    if not isinstance(declared_hash, str) or not HASH_PATTERN.fullmatch(declared_hash):
        result.error(
            "CONTENT_HASH",
            "$.content_hash",
            "必须是 64个小写十六进制字符的 SHA-256。",
        )
    elif declared_hash != content_hash(data):
        result.error("CONTENT_HASH", "$.content_hash", "与 canonical JSON 内容不匹配。")


def validate_confirmations(data: dict[str, Any], result: ValidationResult) -> None:
    confirmations = data.get("confirmations")
    if not isinstance(confirmations, dict):
        result.error("CONFIRMATIONS", "$.confirmations", "必须是恰含 Gate 1 与 Gate 2 的对象。")
        return
    actual = set(confirmations)
    expected_keys = set(CONFIRMATION_KEYS)
    if len(confirmations) != 2:
        result.error("CONFIRMATION_COUNT", "$.confirmations", "人工确认必须恰好为两项。")
    for key in sorted(expected_keys - actual):
        result.error("CONFIRMATION_MISSING", f"$.confirmations.{key}", "缺少人工确认点。")
    for key in sorted(actual - expected_keys):
        result.error("CONFIRMATION_UNKNOWN", f"$.confirmations.{key}", "不是 2.5.2 人工 Gate。")
    for expected_order, key in enumerate(CONFIRMATION_KEYS, start=1):
        if key not in confirmations:
            continue
        item = confirmations.get(key)
        path = f"$.confirmations.{key}"
        if not isinstance(item, dict):
            result.error("CONFIRMATION", path, "必须是对象。")
            continue
        actual_fields = set(item)
        for field_name in sorted(CONFIRMATION_ITEM_KEYS - actual_fields):
            result.error(
                "CONFIRMATION_FIELD_MISSING",
                f"{path}.{field_name}",
                "确认记录缺少必需字段。",
            )
        for field_name in sorted(actual_fields - CONFIRMATION_ITEM_KEYS):
            result.error(
                "CONFIRMATION_FIELD_UNKNOWN",
                f"{path}.{field_name}",
                "确认记录只保存状态、阶段 digest、顺序和备注；不声明身份认证。",
            )
        if item.get("status") != "confirmed":
            result.error("CONFIRMATION_STATUS", f"{path}.status", "正式交付前必须为 confirmed。")
        if item.get("confirmation_order") != expected_order:
            result.error(
                "CONFIRMATION_ORDER",
                f"{path}.confirmation_order",
                f"{key} 的确认顺序必须为 {expected_order}。",
            )
        declared_digest = item.get("stage_digest")
        if not isinstance(declared_digest, str) or not HASH_PATTERN.fullmatch(declared_digest):
            result.error(
                "CONFIRMATION_DIGEST",
                f"{path}.stage_digest",
                "必须是 64个小写十六进制字符的 SHA-256。",
            )
        else:
            try:
                expected_digest = stage_digest(data, expected_order)
            except (ValueError, UnicodeContractError):
                result.error(
                    "CONFIRMATION_DIGEST_INPUT",
                    f"{path}.stage_digest",
                    "当前阶段内容无法形成 canonical digest；先修复上游结构化数据。",
                )
            else:
                if declared_digest != expected_digest:
                    result.error(
                        "CONFIRMATION_DIGEST",
                        f"{path}.stage_digest",
                        "确认 digest 与当前阶段内容不一致；当前确认已失效。",
                    )
        require_string(item.get("notes"), path=f"{path}.notes", result=result)


def dialogue_script_family(text: str) -> str | None:
    han_count = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    if han_count and not latin_count:
        return "han"
    if latin_count and not han_count:
        return "latin"
    if han_count or latin_count:
        return "mixed"
    return None


def normalize_dialogue_speaker(value: str) -> str:
    return re.sub(r"[\s*（(].*$", "", value).strip().casefold()


def bilingual_dialogue_pairs(locked_text: str) -> list[tuple[int, int]]:
    lines = locked_text.splitlines()
    candidates: list[tuple[int, str, str, bool]] = []
    for line_index, line in enumerate(lines):
        match = DIALOGUE_LINE_PATTERN.fullmatch(line)
        if not match:
            continue
        family = dialogue_script_family(match.group("text"))
        if family in {"han", "latin"}:
            stripped = line.strip()
            is_italic_parallel = (
                family == "latin"
                and stripped.startswith("*")
                and stripped.endswith("*")
            )
            candidates.append(
                (
                    line_index,
                    family,
                    normalize_dialogue_speaker(match.group("speaker")),
                    is_italic_parallel,
                )
            )
    pairs: list[tuple[int, int]] = []
    for left, right in zip(candidates, candidates[1:]):
        left_index, left_family, left_speaker, left_parallel = left
        right_index, right_family, right_speaker, right_parallel = right
        only_blank_between = all(
            not line.strip() for line in lines[left_index + 1 : right_index]
        )
        context = "\n".join(
            lines[max(0, left_index - 1) : min(len(lines), right_index + 2)]
        )
        if (
            only_blank_between
            and left_family != right_family
            and (
                left_parallel
                or right_parallel
                or (left_speaker and left_speaker == right_speaker)
                or bool(DIALOGUE_ROLE_MARKER_PATTERN.search(context))
            )
        ):
            pairs.append((left_index, right_index))
    return pairs


def bilingual_pair_has_source_marker(
    locked_text: str,
    pairs: list[tuple[int, int]],
) -> bool:
    lines = locked_text.splitlines()
    for left_index, right_index in pairs:
        context = "\n".join(
            lines[max(0, left_index - 1) : min(len(lines), right_index + 2)]
        )
        if DIALOGUE_ROLE_MARKER_PATTERN.search(context):
            return True
    return False


def validate_dialogue_language_policy(
    source: dict[str, Any],
    locked_text: str,
    result: ValidationResult,
) -> dict[str, Any] | None:
    pairs = bilingual_dialogue_pairs(locked_text)
    policy = source.get("dialogue_language_policy")
    if not pairs:
        if policy is not None:
            result.error(
                "DIALOGUE_LANGUAGE_POLICY_UNUSED",
                "$.source.dialogue_language_policy",
                "只有来源含相邻双语台词候选时才填写该策略。",
            )
        return None
    if not isinstance(policy, dict):
        result.error(
            "DIALOGUE_LANGUAGE_AMBIGUOUS",
            "$.source.dialogue_language_policy",
            "检测到相邻双语台词，但原文与译文主次未锁定；必须先由来源明确标注或取得用户确认。",
        )
        return None
    mode = policy.get("mode")
    expected_keys = (
        DIALOGUE_TRANSLATION_POLICY_KEYS
        if mode == "original_with_translation"
        else DIALOGUE_MULTILINGUAL_POLICY_KEYS
        if mode == "multilingual_actual"
        else DIALOGUE_LANGUAGE_POLICY_KEYS
    )
    actual_keys = set(policy)
    for key in sorted(expected_keys - actual_keys):
        result.error(
            "DIALOGUE_LANGUAGE_POLICY",
            f"$.source.dialogue_language_policy.{key}",
            "缺少双语台词语言策略字段。",
        )
    for key in sorted(actual_keys - expected_keys):
        result.error(
            "DIALOGUE_LANGUAGE_POLICY",
            f"$.source.dialogue_language_policy.{key}",
            "不是双语台词语言策略允许的字段。",
        )
    if mode not in DIALOGUE_LANGUAGE_POLICY_MODES:
        result.error(
            "DIALOGUE_LANGUAGE_POLICY",
            "$.source.dialogue_language_policy.mode",
            "必须为 original_with_translation 或 multilingual_actual。",
        )
    if mode == "multilingual_actual":
        spoken_languages = list_of_unique_strings(
            policy.get("spoken_languages"),
            path="$.source.dialogue_language_policy.spoken_languages",
            result=result,
            allow_empty=False,
        )
        if len(spoken_languages) < 2:
            result.error(
                "DIALOGUE_LANGUAGE_POLICY",
                "$.source.dialogue_language_policy.spoken_languages",
                "multilingual_actual 必须登记至少两种实际说出的语言。",
            )
        for index, language in enumerate(spoken_languages):
            if not LANGUAGE_TAG_PATTERN.fullmatch(language):
                result.error(
                    "DIALOGUE_LANGUAGE_POLICY",
                    f"$.source.dialogue_language_policy.spoken_languages[{index}]",
                    "必须是规范语言标签，例如 en、zh-CN。",
                )
        resolution = policy.get("resolution")
        if resolution not in DIALOGUE_LANGUAGE_RESOLUTIONS:
            result.error(
                "DIALOGUE_LANGUAGE_POLICY",
                "$.source.dialogue_language_policy.resolution",
                "必须为 source_explicit 或 user_confirmed。",
            )
        evidence = require_nonempty_string(
            policy.get("evidence"),
            path="$.source.dialogue_language_policy.evidence",
            result=result,
            code="DIALOGUE_LANGUAGE_POLICY",
        )
        if resolution == "user_confirmed":
            corrections = source.get("approved_corrections")
            confirmed = any(
                isinstance(correction, dict)
                and correction.get("to") == evidence
                and re.search(
                    r"(?:用户|user)",
                    str(correction.get("reason", "")),
                    re.IGNORECASE,
                )
                for correction in as_list(corrections)
            )
            if not confirmed:
                result.error(
                    "DIALOGUE_LANGUAGE_CONFIRMATION",
                    "$.source.dialogue_language_policy.evidence",
                    "user_confirmed 必须以相同 evidence 写入 approved_corrections.to，且 reason 明确记录用户确认。",
                )
        return policy

    original_language = require_nonempty_string(
        policy.get("original_language"),
        path="$.source.dialogue_language_policy.original_language",
        result=result,
        code="DIALOGUE_LANGUAGE_POLICY",
    )
    if original_language and not LANGUAGE_TAG_PATTERN.fullmatch(original_language):
        result.error(
            "DIALOGUE_LANGUAGE_POLICY",
            "$.source.dialogue_language_policy.original_language",
            "必须是规范语言标签，例如 en、zh-CN。",
        )
    translation_languages = list_of_unique_strings(
        policy.get("translation_languages"),
        path="$.source.dialogue_language_policy.translation_languages",
        result=result,
        allow_empty=False,
    )
    for index, language in enumerate(translation_languages):
        if not LANGUAGE_TAG_PATTERN.fullmatch(language):
            result.error(
                "DIALOGUE_LANGUAGE_POLICY",
                f"$.source.dialogue_language_policy.translation_languages[{index}]",
                "必须是规范语言标签，例如 en、zh-CN。",
            )
        if original_language and language.casefold() == original_language.casefold():
            result.error(
                "DIALOGUE_LANGUAGE_POLICY",
                f"$.source.dialogue_language_policy.translation_languages[{index}]",
                "译文语言不得与原始台词语言相同。",
            )
    resolution = policy.get("resolution")
    if resolution not in DIALOGUE_LANGUAGE_RESOLUTIONS:
        result.error(
            "DIALOGUE_LANGUAGE_POLICY",
            "$.source.dialogue_language_policy.resolution",
            "必须为 source_explicit 或 user_confirmed。",
        )
    evidence = require_nonempty_string(
        policy.get("evidence"),
        path="$.source.dialogue_language_policy.evidence",
        result=result,
        code="DIALOGUE_LANGUAGE_POLICY",
    )
    if resolution == "source_explicit" and not bilingual_pair_has_source_marker(
        locked_text,
        pairs,
    ):
        result.error(
            "DIALOGUE_LANGUAGE_EVIDENCE",
            "$.source.dialogue_language_policy.resolution",
            "来源相邻范围没有原文、译文或字幕角色标记，不能声明 source_explicit。",
        )
    if resolution == "user_confirmed":
        corrections = source.get("approved_corrections")
        confirmed = any(
            isinstance(correction, dict)
            and correction.get("to") == evidence
            and re.search(r"(?:用户|user)", str(correction.get("reason", "")), re.IGNORECASE)
            for correction in as_list(corrections)
        )
        if not confirmed:
            result.error(
                "DIALOGUE_LANGUAGE_CONFIRMATION",
                "$.source.dialogue_language_policy.evidence",
                "user_confirmed 必须以相同 evidence 写入 approved_corrections.to，且 reason 明确记录用户确认。",
            )
    return policy


def validate_dialogue_fact_language(
    fact: dict[str, Any],
    *,
    policy: dict[str, Any] | None,
    path: str,
    result: ValidationResult,
) -> None:
    if policy is None or fact.get("type") != "dialogue":
        return
    if policy.get("mode") == "multilingual_actual":
        language = require_nonempty_string(
            fact.get("language"),
            path=f"{path}.language",
            result=result,
            code="DIALOGUE_LANGUAGE_ROLE",
        )
        spoken_languages = {
            value.casefold()
            for value in as_list(policy.get("spoken_languages"))
            if isinstance(value, str)
        }
        if language and language.casefold() not in spoken_languages:
            result.error(
                "DIALOGUE_LANGUAGE_ROLE",
                f"{path}.language",
                "实际多语对白 fact 的 language 必须属于 spoken_languages。",
            )
        if fact.get("source_role") != "spoken_dialogue":
            result.error(
                "DIALOGUE_LANGUAGE_ROLE",
                f"{path}.source_role",
                "multilingual_actual 中的对白 fact 必须标记为 spoken_dialogue。",
            )
        return
    expected_language = policy.get("original_language")
    language = require_nonempty_string(
        fact.get("language"),
        path=f"{path}.language",
        result=result,
        code="DIALOGUE_LANGUAGE_ROLE",
    )
    if (
        language
        and isinstance(expected_language, str)
        and language.casefold() != expected_language.casefold()
    ):
        result.error(
            "DIALOGUE_LANGUAGE_ROLE",
            f"{path}.language",
            "dialogue fact 必须标记为已锁定的原始台词语言。",
        )
    if fact.get("source_role") != "original_dialogue":
        result.error(
            "DIALOGUE_LANGUAGE_ROLE",
            f"{path}.source_role",
            "双语来源中的 dialogue fact 必须标记为 original_dialogue，译文不得成为 fact。",
        )
    fact_text = fact.get("text")
    if not isinstance(fact_text, str) or not isinstance(expected_language, str):
        return
    family = dialogue_script_family(fact_text)
    base_language = expected_language.split("-", 1)[0].casefold()
    mismatch = (
        (base_language == "en" and family != "latin")
        or (base_language == "zh" and family not in {"han", "mixed"})
    )
    if mismatch:
        result.error(
            "DIALOGUE_LANGUAGE_TEXT_MISMATCH",
            f"{path}.text",
            "dialogue fact 的文字体系与已锁定原始台词语言不一致。",
        )


def validate_source(data: dict[str, Any], result: ValidationResult) -> str:
    source = data.get("source")
    if not isinstance(source, dict):
        result.error("SOURCE", "$.source", "必须是对象。")
        return ""
    if source.get("input_kind") not in INPUT_KINDS:
        result.error(
            "SOURCE_INPUT_KIND",
            "$.source.input_kind",
            "必须为 full_screenplay、screenplay_segment 或 continuous_text。",
        )
    if source.get("boundary_lock") not in BOUNDARY_LOCKS:
        result.error(
            "SOURCE_BOUNDARY_LOCK",
            "$.source.boundary_lock",
            "必须明确整份输入、连续范围或用户锁定片段的边界依据。",
        )
    require_nonempty_string(source.get("scope"), path="$.source.scope", result=result)
    delivery_slug = source.get("delivery_slug")
    if (
        not isinstance(delivery_slug, str)
        or not DELIVERY_SLUG_PATTERN.fullmatch(delivery_slug)
    ):
        result.error(
            "DELIVERY_SLUG",
            "$.source.delivery_slug",
            "必须是根据剧本名称、编号和标题生成的纯 ASCII 小写 kebab-case。",
        )
    elif (
        len(delivery_slug) > 80
        or re.search(
            r"(?:^|-)(?:v[0-9]+|final|draft|temp|latest|new)(?:-|$)",
            delivery_slug,
        )
    ):
        result.error(
            "DELIVERY_SLUG",
            "$.source.delivery_slug",
            "不得包含版本号、临时状态词或超过 80 个字符。",
        )
    locked_text = source.get("locked_text")
    if not isinstance(locked_text, str) or not locked_text:
        result.error("LOCKED_TEXT", "$.source.locked_text", "必须是非空字符串。")
        locked_text = ""
    elif "\r" in locked_text:
        result.error("LOCKED_TEXT_NEWLINES", "$.source.locked_text", "必须只使用 LF 换行。")
    expected_hash = sha256_text(locked_text)
    if source.get("locked_text_hash") != expected_hash:
        result.error("LOCKED_TEXT_HASH", "$.source.locked_text_hash", "锁定文本 hash 不匹配。")
    corrections = source.get("approved_corrections")
    if not isinstance(corrections, list):
        result.error("CORRECTIONS", "$.source.approved_corrections", "必须是数组。")
    else:
        for index, correction in enumerate(corrections):
            path = f"$.source.approved_corrections[{index}]"
            if not isinstance(correction, dict):
                result.error("CORRECTION", path, "必须是对象。")
                continue
            for key in ("from", "to", "reason"):
                require_nonempty_string(correction.get(key), path=f"{path}.{key}", result=result)
    validate_dialogue_language_policy(source, locked_text, result)
    return locked_text


def validate_profile(profile: Any, *, path: str, result: ValidationResult) -> None:
    if not isinstance(profile, dict):
        result.error("DIRECTOR_PROFILE", path, "必须是对象。")
        return
    actual_keys = set(profile)
    for key in sorted(PROFILE_REQUIRED_KEYS - actual_keys):
        result.error(
            "DIRECTOR_PROFILE_FIELD_MISSING",
            f"{path}.{key}",
            "director_profile 缺少闭合风格轴。",
        )
    for key in sorted(actual_keys - PROFILE_REQUIRED_KEYS):
        result.error(
            "DIRECTOR_PROFILE_FIELD_UNKNOWN",
            f"{path}.{key}",
            "不是 director_profile/2.5.2 的闭合字段。",
        )
    for key, allowed in PROFILE_VALUES.items():
        if key in profile and profile.get(key) not in allowed:
            result.error(
                "DIRECTOR_PROFILE_VALUE",
                f"{path}.{key}",
                f"必须是：{' | '.join(sorted(allowed))}。",
            )
    languages = []
    if "transition_language" in profile:
        languages = list_of_unique_strings(
            profile.get("transition_language"),
            path=f"{path}.transition_language",
            result=result,
            allow_empty=False,
        )
    for index, value in enumerate(languages):
        if value not in TRANSITION_LANGUAGES:
            result.error(
                "TRANSITION_LANGUAGE",
                f"{path}.transition_language[{index}]",
                "不是允许的导演转场语言。",
            )
    list_of_unique_strings(
        profile.get("priorities"),
        path=f"{path}.priorities",
        result=result,
        allow_empty=False,
    )
    require_nonempty_string(
        profile.get("natural_language_intent"),
        path=f"{path}.natural_language_intent",
        result=result,
    )


def validate_gate_1_material(data: dict[str, Any], result: ValidationResult) -> None:
    analysis = data.get("source_analysis")
    if not isinstance(analysis, dict):
        result.error("SOURCE_ANALYSIS", "$.source_analysis", "Gate 1 源分析必须是对象。")
    else:
        actual_fields = set(analysis)
        required_analysis_fields = {"source_boundary", "source_constraints"}
        for field_name in sorted(required_analysis_fields - actual_fields):
            result.error(
                "SOURCE_ANALYSIS_FIELD_MISSING",
                f"$.source_analysis.{field_name}",
                "源分析缺少必需字段。",
            )
        for field_name in sorted(actual_fields - SOURCE_ANALYSIS_FIELDS):
            result.error(
                "SOURCE_ANALYSIS_FIELD_UNKNOWN",
                f"$.source_analysis.{field_name}",
                "不是 Gate 1 源分析字段。",
            )
        for field_name in ("source_boundary", "narrative_function", "dramatic_progression"):
            if field_name in analysis:
                require_nonempty_string(
                    analysis.get(field_name),
                    path=f"$.source_analysis.{field_name}",
                    result=result,
                )
        if "character_relations" in analysis:
            list_of_unique_strings(
                analysis.get("character_relations"),
                path="$.source_analysis.character_relations",
                result=result,
                allow_empty=True,
            )
        list_of_unique_strings(
            analysis.get("source_constraints"),
            path="$.source_analysis.source_constraints",
            result=result,
            allow_empty=False,
        )

    options = data.get("director_style_options")
    option_lookup: dict[str, dict[str, Any]] = {}
    if options is None:
        options = []
    elif not isinstance(options, list) or not options:
        result.error(
            "STYLE_OPTIONS",
            "$.director_style_options",
            "存在候选风格时必须是非空数组；用户已指定风格时可省略候选。",
        )
        options = []
    elif len(options) not in STYLE_OPTION_COUNTS:
        result.error(
            "STYLE_OPTION_COUNT",
            "$.director_style_options",
            "正式候选数量只能是默认三项，或从更多选择展开后的四项。",
        )
    seen_labels: set[str] = set()
    seen_profiles: set[bytes] = set()
    for index, option in enumerate(options):
        path = f"$.director_style_options[{index}]"
        if not isinstance(option, dict):
            result.error("STYLE_OPTION", path, "风格选项必须是对象。")
            continue
        actual_fields = set(option)
        for field_name in sorted(STYLE_OPTION_KEYS - actual_fields):
            result.error(
                "STYLE_OPTION_FIELD_MISSING",
                f"{path}.{field_name}",
                "风格选项缺少必需字段。",
            )
        for field_name in sorted(actual_fields - STYLE_OPTION_KEYS):
            result.error(
                "STYLE_OPTION_FIELD_UNKNOWN",
                f"{path}.{field_name}",
                "不是导演风格选项字段。",
            )
        option_id = option.get("option_id")
        if not id_is_canonical(option_id, "style_option"):
            result.error("STYLE_OPTION_ID", f"{path}.option_id", "必须是 canonical STYLE-xx。")
            continue
        assert isinstance(option_id, str)
        expected_option_id = f"STYLE-{index + 1:02d}"
        if option_id != expected_option_id:
            result.error(
                "STYLE_OPTION_ORDER",
                f"{path}.option_id",
                f"正式候选必须连续排列；此处应为 {expected_option_id}。",
            )
        if option_id in option_lookup:
            result.error("STYLE_OPTION_ID_DUPLICATE", f"{path}.option_id", "风格选项 ID 重复。")
        option_lookup[option_id] = option
        label = option.get("label")
        require_nonempty_string(label, path=f"{path}.label", result=result)
        if isinstance(label, str) and label.strip():
            normalized_label = label.strip()
            if not re.fullmatch(r".+（参考.+）", normalized_label):
                result.error(
                    "STYLE_OPTION_LABEL",
                    f"{path}.label",
                    "标签必须使用“策略名（参考导演）”格式。",
                )
            if normalized_label in seen_labels:
                result.error(
                    "STYLE_OPTION_LABEL_DUPLICATE",
                    f"{path}.label",
                    "正式候选标签不得重复。",
                )
            seen_labels.add(normalized_label)
        rationale = option.get("rationale")
        require_nonempty_string(rationale, path=f"{path}.rationale", result=result)
        if isinstance(rationale, str) and rationale.strip():
            markers = [f"{section}：" for section in STYLE_RATIONALE_SECTIONS]
            positions = [rationale.find(marker) for marker in markers]
            if any(position < 0 for position in positions) or positions != sorted(positions):
                result.error(
                    "STYLE_OPTION_RATIONALE",
                    f"{path}.rationale",
                    "rationale 必须按固定顺序包含七段：适配依据、时间与剪辑、摄影机、空间与调度、表演与观看、主要收益、主要风险。",
                )
            else:
                for marker_index, (marker, position) in enumerate(
                    zip(markers, positions)
                ):
                    content_start = position + len(marker)
                    content_end = (
                        positions[marker_index + 1]
                        if marker_index + 1 < len(positions)
                        else len(rationale)
                    )
                    if not rationale[content_start:content_end].strip():
                        result.error(
                            "STYLE_OPTION_RATIONALE",
                            f"{path}.rationale",
                            f"{marker[:-1]}段必须包含具体内容。",
                        )
        validate_profile(option.get("profile"), path=f"{path}.profile", result=result)
        profile = option.get("profile")
        if isinstance(profile, dict):
            profile_key = canonical_json_bytes(profile)
            if profile_key in seen_profiles:
                result.error(
                    "STYLE_OPTION_PROFILE_DUPLICATE",
                    f"{path}.profile",
                    "正式候选的完整 profile 不得重复。",
                )
            seen_profiles.add(profile_key)

    selected_id = data.get("selected_style_option_id")
    if option_lookup and selected_id not in option_lookup:
        result.error(
            "STYLE_SELECTION",
            "$.selected_style_option_id",
            "有候选风格时必须明确选择已展示选项。",
        )
    if not option_lookup and selected_id is not None:
        result.error(
            "STYLE_SELECTION",
            "$.selected_style_option_id",
            "未提供候选风格时不要填写 selected_style_option_id。",
        )
    validate_profile(data.get("director_profile"), path="$.director_profile", result=result)
    if selected_id in option_lookup and data.get("director_profile") != option_lookup[selected_id].get("profile"):
        result.error(
            "STYLE_SELECTION_PROFILE",
            "$.director_profile",
            "正式 director_profile 必须与已选择风格选项完全一致。",
        )


def validate_initial_continuity(
    initial: Any,
    *,
    path: str,
    scene_reality_layer: str,
    result: ValidationResult,
) -> tuple[dict[tuple[str, str, str], str], dict[str, set[str]]]:
    if not isinstance(initial, dict):
        result.error("INITIAL_CONTINUITY", path, "必须是对象。")
        return {}, {"character": set(), "prop": set(), "fixed_object": set(), "sound_source": set()}
    state: dict[tuple[str, str, str], str] = {}
    names: dict[str, set[str]] = {
        "character": set(),
        "prop": set(),
        "fixed_object": set(),
        "sound_source": set(),
    }
    collection_types = {
        "characters": "character",
        "props": "prop",
        "fixed_objects": "fixed_object",
        "sound_sources": "sound_source",
    }
    for collection, entity_type in collection_types.items():
        items = initial.get(collection)
        collection_path = f"{path}.{collection}"
        if not isinstance(items, list):
            result.error("CONTINUITY_COLLECTION", collection_path, "必须是数组。")
            continue
        for index, item in enumerate(items):
            item_path = f"{collection_path}[{index}]"
            if not isinstance(item, dict):
                result.error("CONTINUITY_ENTITY", item_path, "必须是对象。")
                continue
            name = require_nonempty_string(item.get("name"), path=f"{item_path}.name", result=result)
            if not name:
                continue
            if name in names[entity_type]:
                result.error("CONTINUITY_ENTITY_DUPLICATE", f"{item_path}.name", f"重复实体：{name}。")
            names[entity_type].add(name)
            tracked_fields = [key for key in item if key != "name"]
            if not tracked_fields:
                result.error("CONTINUITY_ENTITY_EMPTY", item_path, "至少登记一个需要追踪的状态字段。")
            for field_name in tracked_fields:
                value = item.get(field_name)
                if not isinstance(value, str) or not value.strip():
                    result.error(
                        "CONTINUITY_STATE",
                        f"{item_path}.{field_name}",
                        "状态值必须是非空字符串。",
                    )
                    continue
                state[(entity_type, name, field_name)] = value
    reality_layer = initial.get("reality_layer")
    if reality_layer != scene_reality_layer:
        result.error(
            "REALITY_LAYER",
            f"{path}.reality_layer",
            "必须与场景 reality_layer 完全一致。",
        )
    if isinstance(reality_layer, str) and reality_layer:
        state[("reality_layer", "", "value")] = reality_layer
    return state, names


def profile_basis_matches(
    profile: dict[str, Any],
    *,
    field_name: str,
    expected_value: str,
) -> bool:
    actual = profile.get(field_name)
    if field_name in {"transition_language", "priorities"}:
        return expected_value in as_list(actual)
    return actual == expected_value


def validate_style_anchors(
    value: Any,
    *,
    path: str,
    profile: dict[str, Any],
    result: ValidationResult,
) -> set[str]:
    if not isinstance(value, list) or not value:
        result.error(
            "STYLE_ANCHORS",
            path,
            "每场 Gate 2 规划必须把已确认导演 profile 编译为至少一个场级风格锚点。",
        )
        return set()
    anchor_ids: set[str] = set()
    for index, anchor in enumerate(value):
        anchor_path = f"{path}[{index}]"
        if not isinstance(anchor, dict):
            result.error("STYLE_ANCHOR", anchor_path, "风格锚点必须是对象。")
            continue
        validate_exact_fields(
            anchor,
            expected=STYLE_ANCHOR_KEYS,
            path=anchor_path,
            code_prefix="STYLE_ANCHOR",
            result=result,
        )
        anchor_id = anchor.get("style_anchor_id")
        if not id_is_canonical(anchor_id, "style_anchor"):
            result.error(
                "STYLE_ANCHOR_ID",
                f"{anchor_path}.style_anchor_id",
                "必须是 canonical SAxxx。",
            )
        elif anchor_id in anchor_ids:
            result.error(
                "STYLE_ANCHOR_ID_DUPLICATE",
                f"{anchor_path}.style_anchor_id",
                "同场风格锚点 ID 重复。",
            )
        else:
            anchor_ids.add(anchor_id)
        basis_items = anchor.get("profile_basis")
        if not isinstance(basis_items, list) or not basis_items:
            result.error(
                "STYLE_ANCHOR_PROFILE_BASIS",
                f"{anchor_path}.profile_basis",
                "风格锚点必须引用至少一个已确认 director_profile 字段和值。",
            )
        else:
            seen_basis: set[tuple[str, str]] = set()
            for basis_index, basis in enumerate(basis_items):
                basis_path = f"{anchor_path}.profile_basis[{basis_index}]"
                if not isinstance(basis, dict):
                    result.error(
                        "STYLE_ANCHOR_PROFILE_BASIS",
                        basis_path,
                        "profile_basis 项必须是对象。",
                    )
                    continue
                validate_exact_fields(
                    basis,
                    expected=STYLE_PROFILE_BASIS_KEYS,
                    path=basis_path,
                    code_prefix="STYLE_ANCHOR_PROFILE_BASIS",
                    result=result,
                )
                field_name = clean_text(basis.get("field"))
                expected_value = require_nonempty_string(
                    basis.get("value"),
                    path=f"{basis_path}.value",
                    result=result,
                )
                if field_name not in STYLE_PROFILE_BASIS_FIELDS:
                    result.error(
                        "STYLE_ANCHOR_PROFILE_FIELD",
                        f"{basis_path}.field",
                        "field 必须引用 director_profile 的闭合轴、优先级、转场语言或自然语言意图。",
                    )
                    continue
                pair = (field_name, expected_value)
                if pair in seen_basis:
                    result.error(
                        "STYLE_ANCHOR_PROFILE_DUPLICATE",
                        basis_path,
                        "同一 profile 字段和值不得在一个锚点中重复。",
                    )
                seen_basis.add(pair)
                if expected_value and not profile_basis_matches(
                    profile,
                    field_name=field_name,
                    expected_value=expected_value,
                ):
                    result.error(
                        "STYLE_ANCHOR_PROFILE_MISMATCH",
                        basis_path,
                        "风格锚点引用的字段和值必须与 Gate 1 已确认 director_profile 完全一致。",
                    )
        require_nonempty_string(
            anchor.get("scene_application"),
            path=f"{anchor_path}.scene_application",
            result=result,
        )
        require_nonempty_string(
            anchor.get("avoidance"),
            path=f"{anchor_path}.avoidance",
            result=result,
        )
    return anchor_ids


def validate_directing_plan(
    value: Any,
    *,
    path: str,
    profile: dict[str, Any],
    result: ValidationResult,
) -> set[str]:
    if not isinstance(value, dict):
        result.error(
            "SCENE_DIRECTING_PLAN_MISSING",
            path,
            "拆镜前必须先提交该整场戏的 directing_plan。",
        )
        return set()
    validate_required_optional_fields(
        value,
        required=DIRECTING_PLAN_REQUIRED_KEYS,
        optional=DIRECTING_PLAN_OPTIONAL_KEYS,
        path=path,
        code_prefix="SCENE_PLAN",
        result=result,
    )
    incomplete = False
    for key in ("scene_objective",):
        field = value.get(key)
        if not isinstance(field, str) or not field.strip():
            incomplete = True
    for key in ("progression", "pov_flow"):
        field = value.get(key)
        if not isinstance(field, list) or not field or not all(
            isinstance(item, str) and item.strip() for item in field
        ):
            incomplete = True
    for key in ("entry_state", "exit_state"):
        field = value.get(key)
        if field is not None and (not isinstance(field, str) or not field.strip()):
            incomplete = True
    rhythm_curve = value.get("rhythm_curve")
    if rhythm_curve is not None and (
        not isinstance(rhythm_curve, list)
        or not all(isinstance(item, str) and item.strip() for item in rhythm_curve)
    ):
        incomplete = True
    dialogue_geometry = value.get("dialogue_geometry")
    if dialogue_geometry is not None and (
        not isinstance(dialogue_geometry, str) or not dialogue_geometry.strip()
    ):
        incomplete = True
    for key in ("protected_processes", "visual_turns"):
        field = value.get(key)
        if field is not None and (
            not isinstance(field, list)
            or not all(isinstance(item, str) and item.strip() for item in field)
        ):
            incomplete = True
    entry_strategy = value.get("entry_strategy")
    if not isinstance(entry_strategy, dict):
        result.error(
            "SCENE_ENTRY_STRATEGY",
            f"{path}.entry_strategy",
            "每场 Gate 2 规划必须提交结构化 entry_strategy。",
        )
        incomplete = True
    else:
        validate_required_optional_fields(
            entry_strategy,
            required=ENTRY_STRATEGY_REQUIRED_KEYS,
            optional=set(),
            path=f"{path}.entry_strategy",
            code_prefix="SCENE_ENTRY_STRATEGY",
            result=result,
        )
        mode = entry_strategy.get("mode")
        if mode not in ENTRY_STRATEGY_MODES:
            result.error(
                "SCENE_ENTRY_STRATEGY_MODE",
                f"{path}.entry_strategy.mode",
                "入口模式无效。",
            )
        for key in ("observer_position", "reason"):
            require_nonempty_string(
                entry_strategy.get(key),
                path=f"{path}.entry_strategy.{key}",
                result=result,
            )
        required_information = list_of_unique_strings(
            entry_strategy.get("required_spatial_information"),
            path=f"{path}.entry_strategy.required_spatial_information",
            result=result,
            allow_empty=True,
        )
        withheld_information = list_of_unique_strings(
            entry_strategy.get("withheld_information"),
            path=f"{path}.entry_strategy.withheld_information",
            result=result,
            allow_empty=True,
        )
        overlap = set(required_information) & set(withheld_information)
        if overlap:
            result.error(
                "SCENE_ENTRY_STRATEGY_CONFLICT",
                f"{path}.entry_strategy",
                "入口不能同时要求立即建立并暂缓同一信息。",
            )
        if mode == "deliberate_withhold" and not withheld_information:
            result.error(
                "SCENE_ENTRY_STRATEGY_WITHHOLD",
                f"{path}.entry_strategy.withheld_information",
                "deliberate_withhold 必须明确至少一项有意暂缓的信息。",
            )
    style_anchor_ids = validate_style_anchors(
        value.get("style_anchors"),
        path=f"{path}.style_anchors",
        profile=profile,
        result=result,
    )
    if incomplete:
        result.error(
            "SCENE_PLAN_INCOMPLETE",
            path,
            "整场规划必须说明目标、推进、视点与结构化入口；出口、节奏、受保护过程与视觉转折按需填写。",
        )
    return style_anchor_ids


def validate_scenes(
    data: dict[str, Any],
    result: ValidationResult,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, int],
    dict[str, dict[tuple[str, str, str], str]],
    dict[str, dict[str, set[str]]],
    dict[str, set[str]],
]:
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        result.error("SCENES", "$.scenes", "必须是非空数组。")
        return {}, {}, {}, {}, {}
    lookup: dict[str, dict[str, Any]] = {}
    order: dict[str, int] = {}
    initial_states: dict[str, dict[tuple[str, str, str], str]] = {}
    entity_names: dict[str, dict[str, set[str]]] = {}
    axis_ids_by_scene: dict[str, set[str]] = {}
    all_axis_ids: set[str] = set()
    all_style_anchor_ids: set[str] = set()
    profile = as_dict(data.get("director_profile"))
    for index, scene in enumerate(scenes):
        path = f"$.scenes[{index}]"
        if not isinstance(scene, dict):
            result.error("SCENE", path, "场景必须是对象。")
            continue
        scene_id = scene.get("scene_id")
        if not id_is_canonical(scene_id, "scene"):
            result.error("SCENE_ID", f"{path}.scene_id", "必须是正号 canonical SCxxx。")
            continue
        assert isinstance(scene_id, str)
        if scene_id in lookup:
            result.error("SCENE_ID_DUPLICATE", f"{path}.scene_id", f"重复 scene_id：{scene_id}。")
        lookup[scene_id] = scene
        order[scene_id] = index
        scene_display = require_nonempty_string(
            scene.get("scene"),
            path=f"{path}.scene",
            result=result,
        )
        if scene_display and SCENE_DURATION_PATTERN.search(scene_display):
            result.error(
                "SCENE_DURATION_ESTIMATE",
                f"{path}.scene",
                "场景显示名不得包含“约一分钟”“约55秒”等预计场长。",
            )
        scene_style_anchor_ids = validate_directing_plan(
            scene.get("directing_plan"),
            path=f"{path}.directing_plan",
            profile=profile,
            result=result,
        )
        duplicate_anchor_ids = scene_style_anchor_ids & all_style_anchor_ids
        for anchor_id in sorted(duplicate_anchor_ids):
            result.error(
                "STYLE_ANCHOR_ID_DUPLICATE",
                f"{path}.directing_plan.style_anchors",
                f"style_anchor_id `{anchor_id}` 必须在整个项目中唯一。",
            )
        all_style_anchor_ids.update(scene_style_anchor_ids)
        reality_layer = require_nonempty_string(
            scene.get("reality_layer"),
            path=f"{path}.reality_layer",
            result=result,
        )
        if "director_analysis" in scene:
            validate_director_analysis(
                scene.get("director_analysis"),
                path=f"{path}.director_analysis",
                result=result,
            )
        if "initial_continuity" in scene:
            state, names = validate_initial_continuity(
                scene.get("initial_continuity"),
                path=f"{path}.initial_continuity",
                scene_reality_layer=reality_layer,
                result=result,
            )
        else:
            state = (
                {("reality_layer", "", "value"): reality_layer}
                if reality_layer
                else {}
            )
            names = {
                "character": set(),
                "prop": set(),
                "fixed_object": set(),
                "sound_source": set(),
            }
        initial_states[scene_id] = state
        entity_names[scene_id] = names
        axes = scene.get("axes", [])
        local_axes: set[str] = set()
        if not isinstance(axes, list):
            result.error("AXES", f"{path}.axes", "必须是数组。")
        else:
            for axis_index, axis in enumerate(axes):
                axis_path = f"{path}.axes[{axis_index}]"
                if not isinstance(axis, dict):
                    result.error("AXIS", axis_path, "必须是对象。")
                    continue
                axis_id = axis.get("axis_id")
                if not id_is_canonical(axis_id, "axis"):
                    result.error("AXIS_ID", f"{axis_path}.axis_id", "必须是 canonical AXxxx。")
                    continue
                assert isinstance(axis_id, str)
                if axis_id in all_axis_ids:
                    result.error("AXIS_ID_DUPLICATE", f"{axis_path}.axis_id", "axis_id 必须全局唯一。")
                all_axis_ids.add(axis_id)
                local_axes.add(axis_id)
                if axis.get("axis_type") not in AXIS_TYPES:
                    result.error("AXIS_TYPE", f"{axis_path}.axis_type", "不是允许的轴线类型。")
                endpoint_a = require_nonempty_string(
                    axis.get("endpoint_a"),
                    path=f"{axis_path}.endpoint_a",
                    result=result,
                )
                endpoint_b = require_nonempty_string(
                    axis.get("endpoint_b"),
                    path=f"{axis_path}.endpoint_b",
                    result=result,
                )
                if endpoint_a and endpoint_a == endpoint_b:
                    result.error("AXIS_ENDPOINTS", axis_path, "轴线两端不得相同。")
        axis_ids_by_scene[scene_id] = local_axes
        parent = scene.get("inherits_from")
        if parent is not None and not isinstance(parent, str):
            result.error("INHERITS_FROM", f"{path}.inherits_from", "必须为 null 或 scene_id 字符串。")
        inherited = scene.get("inherited_states", [])
        if not isinstance(inherited, list):
            result.error("INHERITED_STATES", f"{path}.inherited_states", "必须是数组。")
        elif parent is None and inherited:
            result.error("INHERITED_STATES", f"{path}.inherited_states", "无父场景时必须为空。")
        else:
            for inherited_index, item in enumerate(inherited):
                item_path = f"{path}.inherited_states[{inherited_index}]"
                if not isinstance(item, dict):
                    result.error("INHERITED_STATE", item_path, "必须是对象。")
                    continue
                for key in ("entity_type", "entity", "field"):
                    if key == "entity" and item.get("entity_type") == "reality_layer":
                        require_string(item.get(key), path=f"{item_path}.{key}", result=result)
                    else:
                        require_nonempty_string(item.get(key), path=f"{item_path}.{key}", result=result)
    for scene_id, scene in lookup.items():
        parent = scene.get("inherits_from")
        if isinstance(parent, str):
            path = f"$.scenes[{order[scene_id]}].inherits_from"
            if parent not in lookup:
                result.error("INHERITS_FROM", path, "父场景不存在。")
            elif order[parent] >= order[scene_id]:
                result.error("INHERITS_FROM", path, "父场景必须早于子场景。")
    return lookup, order, initial_states, entity_names, axis_ids_by_scene


def validate_beats(
    data: dict[str, Any],
    locked_text: str,
    scenes: dict[str, dict[str, Any]],
    entity_names: dict[str, dict[str, set[str]]],
    result: ValidationResult,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, str],
    dict[str, int],
]:
    beats = data.get("beats")
    if not isinstance(beats, list) or not beats:
        result.error("BEATS", "$.beats", "必须是非空数组。")
        return {}, {}, {}, {}
    source = as_dict(data.get("source"))
    raw_language_policy = source.get("dialogue_language_policy")
    language_policy = (
        raw_language_policy
        if isinstance(raw_language_policy, dict)
        and raw_language_policy.get("mode") in DIALOGUE_LANGUAGE_POLICY_MODES
        and bilingual_dialogue_pairs(locked_text)
        else None
    )
    beat_lookup: dict[str, dict[str, Any]] = {}
    fact_lookup: dict[str, dict[str, Any]] = {}
    fact_beat: dict[str, str] = {}
    fact_order: dict[str, int] = {}
    previous_order = 0
    previous_beat_anchor = -1
    previous_fact_anchor = -1
    next_fact_order = 0
    for index, beat in enumerate(beats):
        path = f"$.beats[{index}]"
        if not isinstance(beat, dict):
            result.error("BEAT", path, "Beat 必须是对象。")
            continue
        beat_id = beat.get("beat_id")
        if not id_is_canonical(beat_id, "beat"):
            result.error("BEAT_ID", f"{path}.beat_id", "必须是 canonical Bxxx。")
            continue
        assert isinstance(beat_id, str)
        if beat_id in beat_lookup:
            result.error("BEAT_ID_DUPLICATE", f"{path}.beat_id", f"重复 beat_id：{beat_id}。")
        beat_lookup[beat_id] = beat
        order_value = beat.get("beat_order")
        if not is_json_integer(order_value, 1):
            result.error("BEAT_ORDER", f"{path}.beat_order", "必须是正整数。")
        elif isinstance(order_value, int):
            if order_value <= previous_order:
                result.error("BEAT_ORDER", f"{path}.beat_order", "beats[] 必须严格递增。")
            previous_order = order_value
        scene_id = beat.get("scene_id")
        if scene_id not in scenes:
            result.error("BEAT_SCENE", f"{path}.scene_id", "引用的场景不存在。")
        source_chunks = span_texts(
            beat.get("source_spans"),
            locked_text,
            path=f"{path}.source_spans",
            result=result,
        )
        beat_ranges = span_coordinates(beat.get("source_spans"), locked_text)
        if beat_ranges:
            beat_anchor = min(start for start, _ in beat_ranges)
            if beat_anchor < previous_beat_anchor:
                result.error(
                    "BEAT_SOURCE_ORDER",
                    f"{path}.source_spans",
                    "默认叙事顺序中 Beat source spans 不得倒序。",
                )
            previous_beat_anchor = max(previous_beat_anchor, beat_anchor)
        require_nonempty_string(
            beat.get("dramatic_change"),
            path=f"{path}.dramatic_change",
            result=result,
        )
        if "director_analysis" in beat:
            validate_director_analysis(
                beat.get("director_analysis"),
                path=f"{path}.director_analysis",
                result=result,
            )
        facts = beat.get("facts")
        if not isinstance(facts, list) or not facts:
            result.error("FACTS", f"{path}.facts", "Beat 至少包含一个 fact。")
            continue
        for fact_index, fact in enumerate(facts):
            fact_path = f"{path}.facts[{fact_index}]"
            if not isinstance(fact, dict):
                result.error("FACT", fact_path, "fact 必须是对象。")
                continue
            reject_director_analysis_in_fact_or_dialogue(
                fact,
                path=fact_path,
                result=result,
            )
            fact_id = fact.get("fact_id")
            if not id_is_canonical(fact_id, "fact"):
                result.error("FACT_ID", f"{fact_path}.fact_id", "必须是 canonical Fxxx。")
                continue
            assert isinstance(fact_id, str)
            if fact_id in fact_lookup:
                result.error("FACT_ID_DUPLICATE", f"{fact_path}.fact_id", f"重复 fact_id：{fact_id}。")
            fact_lookup[fact_id] = fact
            fact_beat[fact_id] = beat_id
            fact_order[fact_id] = next_fact_order
            next_fact_order += 1
            fact_type = fact.get("type")
            if fact_type not in FACT_TYPES:
                result.error("FACT_TYPE", f"{fact_path}.type", "不是允许的 fact 类型。")
            fact_text = require_nonempty_string(
                fact.get("text"),
                path=f"{fact_path}.text",
                result=result,
            )
            fact_chunks = span_texts(
                fact.get("source_spans"),
                locked_text,
                path=f"{fact_path}.source_spans",
                result=result,
            )
            fact_ranges = span_coordinates(fact.get("source_spans"), locked_text)
            fact_source = "\n".join(fact_chunks)
            if fact_text and fact_text not in fact_source:
                result.error("FACT_SOURCE", f"{fact_path}.text", "fact.text 必须逐字存在于其 source spans。")
            validate_dialogue_fact_language(
                fact,
                policy=language_policy,
                path=fact_path,
                result=result,
            )
            if any(pattern.search(fact_text) for pattern in SOURCE_METADATA_PATTERNS):
                result.error(
                    "SOURCE_METADATA_FACT",
                    f"{fact_path}.text",
                    "标题、场景头和人物表不是可拆镜剧情 fact。",
                )
            if fact_ranges:
                fact_anchor = min(start for start, _ in fact_ranges)
                if fact_anchor < previous_fact_anchor:
                    result.error(
                        "FACT_SOURCE_ORDER",
                        f"{fact_path}.source_spans",
                        "默认叙事顺序中 facts 不得倒序。",
                    )
                previous_fact_anchor = max(previous_fact_anchor, fact_anchor)
            if beat_ranges and fact_ranges and not spans_contained(fact_ranges, beat_ranges):
                result.error(
                    "FACT_BEAT_SOURCE",
                    f"{fact_path}.source_spans",
                    "fact 的坐标范围必须完全包含于所属 Beat source spans。",
                )
            if (
                "presentation_requirement" in fact
                and fact.get("presentation_requirement") not in PRESENTATION_REQUIREMENTS
            ):
                result.error(
                    "PRESENTATION_REQUIREMENT",
                    f"{fact_path}.presentation_requirement",
                    "必须为 must_be_clear 或 supporting。",
                )
            isolation = fact.get("shot_isolation")
            if isolation is not None and isolation not in SHOT_ISOLATION_VALUES:
                result.error(
                    "SHOT_ISOLATION",
                    f"{fact_path}.shot_isolation",
                    "必须为 director_required 或 not_required。",
                )
            reason = fact.get("isolation_reason", "")
            if "isolation_reason" in fact and not isinstance(reason, str):
                result.error("ISOLATION_REASON", f"{fact_path}.isolation_reason", "必须是字符串。")
            elif isolation == "director_required" and not reason.strip():
                result.error(
                    "ISOLATION_REASON",
                    f"{fact_path}.isolation_reason",
                    "director_required 必须写具体理由。",
                )
            elif isolation == "not_required" and reason.strip():
                result.error(
                    "ISOLATION_REASON",
                    f"{fact_path}.isolation_reason",
                    "not_required 时理由必须为空，避免双重语义。",
                )
            performers = []
            if "performers" in fact:
                performers = list_of_unique_strings(
                    fact.get("performers"),
                    path=f"{fact_path}.performers",
                    result=result,
                    allow_empty=True,
                )
            scene_character_names = entity_names.get(str(scene_id), {}).get("character", set())
            for performer_index, performer in enumerate(performers):
                if scene_character_names and performer not in scene_character_names:
                    result.error(
                        "FACT_PERFORMER",
                        f"{fact_path}.performers[{performer_index}]",
                        "performer 必须属于当前场景人物台账。",
                    )
            isolation_group_id = fact.get("isolation_group_id")
            if isolation_group_id is not None and not id_is_canonical(
                isolation_group_id,
                "isolation_group",
            ):
                result.error(
                    "ISOLATION_GROUP_ID",
                    f"{fact_path}.isolation_group_id",
                    "必须为 null 或 canonical IGxxx。",
                )
            if (
                isolation == "director_required"
                and "isolation_group_id" in fact
                and isolation_group_id is None
            ):
                result.error(
                    "ISOLATION_GROUP_REQUIRED",
                    f"{fact_path}.isolation_group_id",
                    "director_required fact 必须登记同一物理瞬间的 isolation_group_id。",
                )
            if fact_type == "dialogue":
                speaker = require_nonempty_string(
                    fact.get("speaker"),
                    path=f"{fact_path}.speaker",
                    result=result,
                )
                scene_speakers = entity_names.get(str(scene_id), {}).get(
                    "character", set()
                )
                if speaker and scene_speakers and speaker not in scene_speakers:
                    result.error("DIALOGUE_SPEAKER", f"{fact_path}.speaker", "说话者不在场景人物台账。")
                if fact.get("script_voice_type") not in SCRIPT_VOICE_TYPES:
                    result.error(
                        "SCRIPT_VOICE_TYPE",
                        f"{fact_path}.script_voice_type",
                        "对白 script_voice_type 无效。",
                    )
                if "performers" in fact and performers != ([speaker] if speaker else []):
                    result.error(
                        "DIALOGUE_PERFORMERS",
                        f"{fact_path}.performers",
                        "dialogue fact 的 performers 必须恰为说话者。",
                    )
                if (
                    speaker
                    and fact_text
                    and re.match(rf"^{re.escape(speaker)}\s*[:：]", fact_text)
                ):
                    result.error(
                        "DIALOGUE_SPEAKER_PREFIX",
                        f"{fact_path}.text",
                        "对白正文不得包含说话人前缀。",
                    )
    return beat_lookup, fact_lookup, fact_beat, fact_order


def validate_screen_events(
    data: dict[str, Any],
    *,
    locked_text: str,
    scenes: dict[str, dict[str, Any]],
    beat_lookup: dict[str, dict[str, Any]],
    fact_lookup: dict[str, dict[str, Any]],
    fact_beat: dict[str, str],
    result: ValidationResult,
) -> dict[str, dict[str, Any]]:
    events = data.get("screen_events")
    if not isinstance(events, list) or not events:
        result.error("SCREEN_EVENTS", "$.screen_events", "必须是非空屏幕事件数组。")
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    scene_orders: dict[str, int] = {}
    scene_source_anchors: dict[str, int] = {}
    for index, event in enumerate(events):
        path = f"$.screen_events[{index}]"
        if not isinstance(event, dict):
            result.error("SCREEN_EVENT", path, "屏幕事件必须是对象。")
            continue
        validate_exact_fields(
            event,
            expected=SCREEN_EVENT_REQUIRED_KEYS,
            path=path,
            code_prefix="SCREEN_EVENT",
            result=result,
        )
        event_id = event.get("screen_event_id")
        if not id_is_canonical(event_id, "screen_event"):
            result.error("SCREEN_EVENT_ID", f"{path}.screen_event_id", "必须是 canonical SEVxxx。")
            continue
        assert isinstance(event_id, str)
        if event_id in lookup:
            result.error("SCREEN_EVENT_ID_DUPLICATE", f"{path}.screen_event_id", "屏幕事件 ID 重复。")
        lookup[event_id] = event
        scene_id = event.get("scene_id")
        if scene_id not in scenes:
            result.error("SCREEN_EVENT_SCENE", f"{path}.scene_id", "引用的场景不存在。")
        expected_order = scene_orders.get(str(scene_id), 0) + 1
        if event.get("event_order") != expected_order:
            result.error(
                "SCREEN_EVENT_ORDER",
                f"{path}.event_order",
                "同场 screen_events 必须按从 1 开始的 event_order 连续排列。",
            )
        scene_orders[str(scene_id)] = expected_order
        beat_ids = list_of_unique_strings(
            event.get("beat_ids"),
            path=f"{path}.beat_ids",
            result=result,
            allow_empty=False,
        )
        for beat_index, beat_id in enumerate(beat_ids):
            beat = beat_lookup.get(beat_id)
            if not beat:
                result.error("SCREEN_EVENT_BEAT", f"{path}.beat_ids[{beat_index}]", "Beat 不存在。")
            elif beat.get("scene_id") != scene_id:
                result.error(
                    "SCREEN_EVENT_BEAT_SCENE",
                    f"{path}.beat_ids[{beat_index}]",
                    "Beat 与屏幕事件不在同场。",
                )
        span_texts(
            event.get("source_spans"),
            locked_text,
            path=f"{path}.source_spans",
            result=result,
        )
        event_ranges = span_coordinates(event.get("source_spans"), locked_text)
        if event_ranges:
            event_anchor = min(start for start, _ in event_ranges)
            previous_anchor = scene_source_anchors.get(str(scene_id), -1)
            if event_anchor < previous_anchor:
                result.error(
                    "SCREEN_EVENT_SOURCE_ORDER",
                    f"{path}.source_spans",
                    "同场 screen_events 必须保持来源单调顺序；导演性倒序只能在规划单元层声明 reorder。",
                )
            scene_source_anchors[str(scene_id)] = max(previous_anchor, event_anchor)
        fact_ids = list_of_unique_strings(
            event.get("covered_fact_ids"),
            path=f"{path}.covered_fact_ids",
            result=result,
            allow_empty=False,
        )
        for fact_index, fact_id in enumerate(fact_ids):
            fact = fact_lookup.get(fact_id)
            beat = beat_lookup.get(fact_beat.get(fact_id, ""))
            if fact is None:
                result.error("SCREEN_EVENT_FACT", f"{path}.covered_fact_ids[{fact_index}]", "Fact 不存在。")
            elif beat and beat.get("scene_id") != scene_id:
                result.error(
                    "SCREEN_EVENT_FACT_SCENE",
                    f"{path}.covered_fact_ids[{fact_index}]",
                    "Fact 与屏幕事件不在同场。",
                )
            elif not spans_contained(
                span_coordinates(fact.get("source_spans"), locked_text),
                event_ranges,
            ):
                result.error(
                    "SCREEN_EVENT_FACT_SOURCE",
                    f"{path}.covered_fact_ids[{fact_index}]",
                    "屏幕事件 source spans 必须坐标包含其 covered Fact。",
                )
        expected_beat_ids = list(
            dict.fromkeys(
                fact_beat[fact_id]
                for fact_id in fact_ids
                if fact_id in fact_beat
            )
        )
        if beat_ids != expected_beat_ids:
            result.error(
                "SCREEN_EVENT_FACT_BEAT_MISMATCH",
                f"{path}.beat_ids",
                "screen_event.beat_ids 必须按来源顺序精确等于 covered_fact_ids 所属 Beat；不得引用无关 Beat 或遗漏所属 Beat。",
            )
        dialogue_facts = [
            fact_lookup[fact_id]
            for fact_id in fact_ids
            if fact_id in fact_lookup
            and fact_lookup[fact_id].get("type") == "dialogue"
        ]
        dialogue_speakers = {
            clean_text(fact.get("speaker"))
            for fact in dialogue_facts
            if clean_text(fact.get("speaker"))
        }
        if len(dialogue_speakers) > 1:
            result.error(
                "SCREEN_EVENT_MULTI_SPEAKER",
                f"{path}.covered_fact_ids",
                "一个原子屏幕事件最多只能包含一个说话者；发言权转移必须拆成新事件。",
            )
        event_role = event.get("event_role")
        if event_role not in SCREEN_EVENT_ROLES:
            result.error(
                "SCREEN_EVENT_ATOMICITY_OVERLOAD",
                f"{path}.event_role",
                "event_role 必须使用原子观看事件闭合值。",
            )
        focus_scale = event.get("focus_scale")
        if focus_scale not in FOCUS_SCALES:
            result.error(
                "SCREEN_EVENT_ATOMICITY_OVERLOAD",
                f"{path}.focus_scale",
                "focus_scale 必须为 space、relation、body、face 或 detail。",
            )
        require_nonempty_string(
            event.get("primary_viewing_subject"),
            path=f"{path}.primary_viewing_subject",
            result=result,
        )
        if len(dialogue_facts) > 1:
            result.error(
                "SCREEN_EVENT_ATOMICITY_OVERLOAD",
                f"{path}.covered_fact_ids",
                "一个原子事件不得合并多个对白 Fact；完整的一次发言应锁为一个对白 Fact。",
            )
        if dialogue_facts and len(fact_ids) != len(dialogue_facts):
            result.error(
                "SCREEN_EVENT_ATOMICITY_OVERLOAD",
                f"{path}.covered_fact_ids",
                "对白轮次不得与空间建立、物件细节、独立动作或人物反应混在同一原子事件。",
            )
        non_dialogue_facts = [
            fact_lookup[fact_id]
            for fact_id in fact_ids
            if fact_id in fact_lookup
            and fact_lookup[fact_id].get("type") != "dialogue"
        ]
        if len(non_dialogue_facts) > 1:
            fact_types = {
                clean_text(fact.get("type")) for fact in non_dialogue_facts
            }
            performer_sets = {
                tuple(
                    sorted(
                        clean_text(item)
                        for item in as_list(fact.get("performers"))
                        if clean_text(item)
                    )
                )
                for fact in non_dialogue_facts
            }
            if len(fact_types) > 1 or len(performer_sets) > 1:
                result.error(
                    "SCREEN_EVENT_ATOMICITY_OVERLOAD",
                    f"{path}.covered_fact_ids",
                    "多 Fact 只有在同一事实类型、同一动作主体与同一观看尺度下才可合并。",
                )
        if event_role == "dialogue_turn" and len(dialogue_facts) != 1:
            result.error(
                "SCREEN_EVENT_ATOMICITY_OVERLOAD",
                f"{path}.event_role",
                "dialogue_turn 必须且只能绑定一次完整发言。",
            )
        if dialogue_facts and event_role not in {"dialogue_turn", "information_landing"}:
            result.error(
                "SCREEN_EVENT_ATOMICITY_OVERLOAD",
                f"{path}.event_role",
                "含对白的事件必须明确标为 dialogue_turn 或 information_landing，不得藏入动作或关系事件。",
            )
        list_of_unique_strings(
            event.get("visual_subjects"),
            path=f"{path}.visual_subjects",
            result=result,
            allow_empty=True,
        )
        for key in (
            "visual_action",
            "viewing_requirement",
            "scale_requirement",
            "spatial_zone",
        ):
            require_nonempty_string(event.get(key), path=f"{path}.{key}", result=result)
        temporal_relation = event.get("temporal_relation")
        if temporal_relation not in SCREEN_EVENT_TEMPORAL_RELATIONS:
            result.error(
                "SCREEN_EVENT_TEMPORAL_RELATION",
                f"{path}.temporal_relation",
                "temporal_relation 无效。",
            )
        if expected_order == 1 and temporal_relation != "sequential":
            result.error(
                "SCREEN_EVENT_TEMPORAL_RELATION",
                f"{path}.temporal_relation",
                "每场首个屏幕事件必须使用 sequential。",
            )
        sound_ids = list_of_unique_strings(
            event.get("sound_fact_ids"),
            path=f"{path}.sound_fact_ids",
            result=result,
            allow_empty=True,
        )
        for sound_index, fact_id in enumerate(sound_ids):
            fact = fact_lookup.get(fact_id)
            if fact is None or fact.get("type") not in {"dialogue", "sound"}:
                result.error(
                    "SCREEN_EVENT_SOUND_FACT",
                    f"{path}.sound_fact_ids[{sound_index}]",
                    "声音引用必须指向 dialogue 或 sound Fact。",
                )
            if fact_id not in fact_ids:
                result.error(
                    "SCREEN_EVENT_SOUND_COVERAGE",
                    f"{path}.sound_fact_ids[{sound_index}]",
                    "sound_fact_ids 必须同时属于 covered_fact_ids。",
                )
    return lookup


def validate_emotion_arcs(
    data: dict[str, Any],
    beat_lookup: dict[str, dict[str, Any]],
    fact_lookup: dict[str, dict[str, Any]],
    scenes: dict[str, dict[str, Any]],
    result: ValidationResult,
) -> dict[str, dict[str, Any]]:
    arcs = data.get("emotion_arcs")
    if arcs is None:
        return {}
    if not isinstance(arcs, list):
        result.error("EMOTION_ARCS", "$.emotion_arcs", "必须是数组。")
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    scene_characters = {
        name
        for scene in scenes.values()
        for name in {
            item.get("name")
            for item in as_list(as_dict(scene.get("initial_continuity")).get("characters"))
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
    }
    for index, arc in enumerate(arcs):
        path = f"$.emotion_arcs[{index}]"
        if not isinstance(arc, dict):
            result.error("EMOTION_ARC", path, "必须是对象。")
            continue
        arc_id = arc.get("emotion_arc_id")
        if not id_is_canonical(arc_id, "emotion_arc"):
            result.error("EMOTION_ARC_ID", f"{path}.emotion_arc_id", "必须是 canonical EAxxx。")
            continue
        assert isinstance(arc_id, str)
        if arc_id in lookup:
            result.error("EMOTION_ARC_ID_DUPLICATE", f"{path}.emotion_arc_id", "emotion_arc_id 重复。")
        lookup[arc_id] = arc
        character = require_nonempty_string(arc.get("character"), path=f"{path}.character", result=result)
        if scene_characters and character and character not in scene_characters:
            result.error("EMOTION_CHARACTER", f"{path}.character", "人物未在任何场景台账登记。")
        require_nonempty_string(arc.get("baseline"), path=f"{path}.baseline", result=result)
        triggers = list_of_unique_strings(
            arc.get("trigger_fact_ids"),
            path=f"{path}.trigger_fact_ids",
            result=result,
            allow_empty=True,
        )
        for trigger_index, fact_id in enumerate(triggers):
            if fact_id not in fact_lookup:
                result.error("EMOTION_TRIGGER", f"{path}.trigger_fact_ids[{trigger_index}]", "fact 不存在。")
        phases = arc.get("phases")
        if not isinstance(phases, list) or not phases:
            result.error("EMOTION_PHASES", f"{path}.phases", "情绪弧至少包含一个原文支持的阶段。")
            continue
        for phase_index, phase in enumerate(phases):
            phase_path = f"{path}.phases[{phase_index}]"
            if not isinstance(phase, dict):
                result.error("EMOTION_PHASE", phase_path, "阶段必须是对象。")
                continue
            if phase.get("phase") not in PERFORMANCE_PHASES:
                result.error("EMOTION_PHASE", f"{phase_path}.phase", "不是允许阶段。")
            beat_ids = list_of_unique_strings(
                phase.get("beat_ids"),
                path=f"{phase_path}.beat_ids",
                result=result,
                allow_empty=False,
            )
            for beat_index, beat_id in enumerate(beat_ids):
                if beat_id not in beat_lookup:
                    result.error("EMOTION_BEAT", f"{phase_path}.beat_ids[{beat_index}]", "Beat 不存在。")
            require_nonempty_string(phase.get("intent"), path=f"{phase_path}.intent", result=result)
            list_of_unique_strings(
                phase.get("visible_direction"),
                path=f"{phase_path}.visible_direction",
                result=result,
                allow_empty=False,
            )
    return lookup


def validate_exact_fields(
    value: dict[str, Any],
    *,
    expected: set[str],
    path: str,
    code_prefix: str,
    result: ValidationResult,
) -> None:
    actual = set(value)
    for field_name in sorted(expected - actual):
        result.error(
            f"{code_prefix}_FIELD_MISSING",
            f"{path}.{field_name}",
            "缺少必需字段。",
        )
    for field_name in sorted(actual - expected):
        result.error(
            f"{code_prefix}_FIELD_UNKNOWN",
            f"{path}.{field_name}",
            "存在未定义字段。",
        )


def validate_required_optional_fields(
    value: dict[str, Any],
    *,
    required: set[str],
    optional: set[str],
    path: str,
    code_prefix: str,
    result: ValidationResult,
) -> None:
    actual = set(value)
    for field_name in sorted(required - actual):
        result.error(
            f"{code_prefix}_FIELD_MISSING",
            f"{path}.{field_name}",
            "缺少必需字段。",
        )
    for field_name in sorted(actual - required - optional):
        result.error(
            f"{code_prefix}_FIELD_UNKNOWN",
            f"{path}.{field_name}",
            "存在未定义字段。",
        )


def json_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return float(value)


def require_metric(
    value: Any,
    expected: float,
    *,
    path: str,
    result: ValidationResult,
) -> None:
    numeric = json_number(value)
    if numeric is None:
        result.error("SHOT_PLAN_METRIC", path, "规划统计必须是有限 JSON 数值。")
        return
    if not math.isclose(numeric, expected, rel_tol=0.0, abs_tol=0.000001):
        result.error(
            "SHOT_PLAN_METRIC",
            path,
            f"必须等于由 planned_units 与 edit_points 计算的 {expected:g}。",
        )


def dialogue_facts_for_plan_unit(
    unit: dict[str, Any],
    screen_event_lookup: dict[str, dict[str, Any]],
    fact_lookup: dict[str, dict[str, Any]] | str,
) -> list[dict[str, Any]]:
    if isinstance(fact_lookup, str):
        # Legacy fixture normalizer: production validation always uses event-bound Facts.
        unit_ranges = span_coordinates(unit.get("source_spans"), fact_lookup)
        output: list[dict[str, Any]] = []
        for beat_id in as_list(unit.get("beat_ids")):
            for fact in as_list(
                screen_event_lookup.get(str(beat_id), {}).get("facts")
            ):
                if not isinstance(fact, dict) or fact.get("type") != "dialogue":
                    continue
                fact_ranges = span_coordinates(fact.get("source_spans"), fact_lookup)
                if not unit_ranges or spans_contained(fact_ranges, unit_ranges):
                    output.append(fact)
        return output
    output: list[dict[str, Any]] = []
    for event_id in as_list(unit.get("screen_event_ids")):
        event = screen_event_lookup.get(str(event_id), {})
        for fact_id in as_list(event.get("covered_fact_ids")):
            fact = fact_lookup.get(str(fact_id))
            if isinstance(fact, dict) and fact.get("type") == "dialogue":
                output.append(fact)
    return output


def screen_event_speakers(
    event: dict[str, Any],
    fact_lookup: dict[str, dict[str, Any]],
) -> list[str]:
    speakers: list[str] = []
    for fact_id in as_list(event.get("covered_fact_ids")):
        fact = fact_lookup.get(str(fact_id), {})
        if fact.get("type") != "dialogue":
            continue
        speaker = clean_text(fact.get("speaker"))
        if speaker and (not speakers or speakers[-1] != speaker):
            speakers.append(speaker)
    return speakers


def validate_dialogue_design(
    value: Any,
    *,
    path: str,
    dialogue_facts: list[dict[str, Any]],
    scene: dict[str, Any],
    result: ValidationResult,
) -> None:
    if not dialogue_facts:
        if value is not None:
            result.error(
                "DIALOGUE_PLAN_CAMERA_MISMATCH",
                path,
                "没有对白事实的规划单元应使用 dialogue_design=null。",
            )
        return
    if value is None:
        return
    if not isinstance(value, dict):
        result.error(
            "DIALOGUE_FOCUS_HANDOFF_UNPLANNED",
            path,
            "dialogue_design 存在时必须是对象。",
        )
        return
    validate_required_optional_fields(
        value,
        required=DIALOGUE_DESIGN_REQUIRED_KEYS,
        optional=DIALOGUE_DESIGN_OPTIONAL_KEYS,
        path=path,
        code_prefix="DIALOGUE_DESIGN",
        result=result,
    )
    mode = value.get("mode")
    if mode is not None:
        require_nonempty_string(mode, path=f"{path}.mode", result=result)
    expected_sequence: list[str] = []
    for fact in dialogue_facts:
        speaker = clean_text(fact.get("speaker"))
        if speaker and (not expected_sequence or expected_sequence[-1] != speaker):
            expected_sequence.append(speaker)
    raw_sequence = value.get("speaker_sequence")
    if not isinstance(raw_sequence, list) or not raw_sequence or not all(
        isinstance(item, str) and item.strip() for item in raw_sequence
    ):
        result.error(
            "DIALOGUE_FOCUS_HANDOFF_UNPLANNED",
            f"{path}.speaker_sequence",
            "speaker_sequence 必须是按发言权顺序排列的非空人物数组。",
        )
        sequence = []
    else:
        sequence = [clean_text(item) for item in raw_sequence]
    if sequence != expected_sequence:
        result.error(
            "DIALOGUE_FOCUS_HANDOFF_UNPLANNED",
            f"{path}.speaker_sequence",
            "speaker_sequence 必须按本单元真实发言权转移顺序登记。",
        )
    if (
        len(set(expected_sequence)) > 1
        and clean_text(mode) == "single_speaker"
    ):
        result.error(
            "DIALOGUE_PLAN_CAMERA_MISMATCH",
            f"{path}.mode",
            "多个发言轮次不能声明为 single_speaker；必须逐轮登记画面所有权与非切方案。",
        )
    if "face_readable_speakers" in value:
        list_of_unique_strings(
            value.get("face_readable_speakers"),
            path=f"{path}.face_readable_speakers",
            result=result,
            allow_empty=True,
        )
    if "listener_reaction_characters" in value:
        list_of_unique_strings(
            value.get("listener_reaction_characters"),
            path=f"{path}.listener_reaction_characters",
            result=result,
            allow_empty=True,
        )
    scene_axes = {
        clean_text(axis.get("axis_id"))
        for axis in as_list(scene.get("axes"))
        if isinstance(axis, dict)
    }
    axis_id = value.get("axis_id")
    if axis_id is not None and axis_id not in scene_axes:
        result.error("DIALOGUE_PLAN_CAMERA_MISMATCH", f"{path}.axis_id", "axis_id 不属于当前场景。")
    require_nonempty_string(value.get("justification"), path=f"{path}.justification", result=result)


def scene_style_anchor_ids(scene: dict[str, Any]) -> set[str]:
    directing_plan = as_dict(scene.get("directing_plan"))
    return {
        clean_text(anchor.get("style_anchor_id"))
        for anchor in as_list(directing_plan.get("style_anchors"))
        if isinstance(anchor, dict) and clean_text(anchor.get("style_anchor_id"))
    }


def validate_visual_plan(
    value: Any,
    *,
    path: str,
    scene: dict[str, Any],
    result: ValidationResult,
) -> None:
    if not isinstance(value, dict):
        result.error(
            "VISUAL_PLAN",
            path,
            "每个 Gate 2 规划单元必须提交结构化 visual_plan。",
        )
        return
    validate_required_optional_fields(
        value,
        required=VISUAL_PLAN_REQUIRED_KEYS,
        optional=VISUAL_PLAN_OPTIONAL_KEYS,
        path=path,
        code_prefix="VISUAL_PLAN",
        result=result,
    )
    require_nonempty_string(
        value.get("viewpoint_owner"),
        path=f"{path}.viewpoint_owner",
        result=result,
    )
    angle = clean_text(value.get("angle"))
    if (
        not PURE_CAMERA_ANGLE_PATTERN.fullmatch(angle)
        or any(token in angle for token in CAMERA_ANGLE_CONTAMINATION_TERMS)
    ):
        result.error(
            "VISUAL_PLAN_ANGLE",
            f"{path}.angle",
            "Gate 2 angle 只能写纯视角高度／俯仰关系。",
        )
    shot_size = clean_text(value.get("shot_size"))
    if not PURE_SHOT_SIZE_PATTERN.fullmatch(shot_size):
        result.error(
            "VISUAL_PLAN_SHOT_SIZE",
            f"{path}.shot_size",
            "Gate 2 shot_size 只能写纯景别或合法景别变化。",
        )
    primary_subjects = list_of_unique_strings(
        value.get("primary_subjects"),
        path=f"{path}.primary_subjects",
        result=result,
        allow_empty=False,
    )
    secondary_subjects = list_of_unique_strings(
        value.get("secondary_subjects"),
        path=f"{path}.secondary_subjects",
        result=result,
        allow_empty=True,
    )
    if set(primary_subjects) & set(secondary_subjects):
        result.error(
            "VISUAL_PLAN_SUBJECT",
            path,
            "同一主体不能同时列为 primary_subjects 与 secondary_subjects。",
        )
    for key in (
        "camera_position",
        "framing_relation",
        "focus_plan",
        "start_frame",
        "end_frame",
    ):
        require_nonempty_string(value.get(key), path=f"{path}.{key}", result=result)
    if value.get("perspective_intent") not in PERSPECTIVE_INTENTS:
        result.error(
            "VISUAL_PLAN_PERSPECTIVE",
            f"{path}.perspective_intent",
            "perspective_intent 无效。",
        )
    spatial_strategy = value.get("spatial_strategy")
    if not isinstance(spatial_strategy, dict):
        result.error(
            "VISUAL_PLAN_SPATIAL_STRATEGY",
            f"{path}.spatial_strategy",
            "spatial_strategy 必须是对象。",
        )
    else:
        validate_exact_fields(
            spatial_strategy,
            expected=SPATIAL_STRATEGY_KEYS,
            path=f"{path}.spatial_strategy",
            code_prefix="SPATIAL_STRATEGY",
            result=result,
        )
        strategy_type = spatial_strategy.get("type")
        if strategy_type not in SPATIAL_STRATEGY_TYPES:
            result.error(
                "VISUAL_PLAN_SPATIAL_STRATEGY",
                f"{path}.spatial_strategy.type",
                "spatial_strategy.type 无效。",
            )
        description = clean_text(spatial_strategy.get("description"))
        if strategy_type == "not_applicable":
            if description:
                result.error(
                    "VISUAL_PLAN_SPATIAL_STRATEGY",
                    f"{path}.spatial_strategy.description",
                    "not_applicable 时 description 必须为空。",
                )
        else:
            require_nonempty_string(
                spatial_strategy.get("description"),
                path=f"{path}.spatial_strategy.description",
                result=result,
            )
    movement_plan = value.get("movement_plan")
    if not isinstance(movement_plan, dict):
        result.error(
            "VISUAL_PLAN_MOVEMENT_PLAN",
            f"{path}.movement_plan",
            "movement_plan 必须是对象。",
        )
    else:
        validate_exact_fields(
            movement_plan,
            expected=MOVEMENT_PLAN_KEYS,
            path=f"{path}.movement_plan",
            code_prefix="MOVEMENT_PLAN",
            result=result,
        )
        movement_class = movement_plan.get("class")
        if movement_class not in CAMERA_MOVEMENT_CLASSES:
            result.error(
                "VISUAL_PLAN_MOVEMENT_CLASS",
                f"{path}.movement_plan.class",
                "class 必须使用运镜归一化闭合类别。",
            )
        if movement_class == "fixed":
            require_nonempty_string(
                movement_plan.get("hold_reason"),
                path=f"{path}.movement_plan.hold_reason",
                result=result,
            )
            for key in ("trigger", "speed", "path", "end_condition"):
                if clean_text(movement_plan.get(key)):
                    result.error(
                        "MOVEMENT_PLAN_FIXED_FIELDS",
                        f"{path}.movement_plan.{key}",
                        "固定镜头只填写 hold_reason。",
                    )
        elif movement_class in CAMERA_MOVEMENT_CLASSES:
            for key in ("trigger", "speed", "path", "end_condition"):
                require_nonempty_string(
                    movement_plan.get(key),
                    path=f"{path}.movement_plan.{key}",
                    result=result,
                )
            if clean_text(movement_plan.get("hold_reason")):
                result.error(
                    "MOVEMENT_PLAN_MOVING_HOLD",
                    f"{path}.movement_plan.hold_reason",
                    "运动镜头的 hold_reason 必须为空。",
                )
    motivation = require_nonempty_string(
        value.get("motivation"),
        path=f"{path}.motivation",
        result=result,
    )
    if motivation in {"丰富角度", "增加变化", "避免重复", "更有电影感", "风格需要"}:
        result.error(
            "VISUAL_PLAN_MOTIVATION_GENERIC",
            f"{path}.motivation",
            "镜头动机必须说明人物、空间、观看或叙事关系，不能以变化本身作为理由。",
        )
    if "style_anchor_ids" in value:
        style_anchor_ids = list_of_unique_strings(
            value.get("style_anchor_ids"),
            path=f"{path}.style_anchor_ids",
            result=result,
            allow_empty=False,
        )
        allowed_anchor_ids = scene_style_anchor_ids(scene)
        for index, anchor_id in enumerate(style_anchor_ids):
            if anchor_id not in allowed_anchor_ids:
                result.error(
                    "VISUAL_PLAN_STYLE_ANCHOR",
                    f"{path}.style_anchor_ids[{index}]",
                    "规划单元只能引用本场已确认的 style_anchor_id。",
                )
    if "focal_length_mm" in value and (
        isinstance(value.get("focal_length_mm"), bool)
        or not isinstance(value.get("focal_length_mm"), (int, float))
        or value.get("focal_length_mm") <= 0
    ):
        result.error(
            "VISUAL_PLAN_FOCAL_LENGTH",
            f"{path}.focal_length_mm",
            "focal_length_mm 必须是正数。",
        )


def visual_plan_rows(data: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for unit in as_list(as_dict(data.get("shot_plan")).get("planned_units")):
        if not isinstance(unit, dict):
            continue
        visual_plan = as_dict(unit.get("visual_plan"))
        scene_id = clean_text(unit.get("scene_id"))
        angle = clean_text(visual_plan.get("angle"))
        shot_size = clean_text(visual_plan.get("shot_size"))
        movement_class = clean_text(as_dict(visual_plan.get("movement_plan")).get("class"))
        if scene_id and angle and shot_size and movement_class:
            rows.append(
                {
                    "scene_id": scene_id,
                    "angle": angle,
                    "shot_size": shot_size,
                    "movement_class": movement_class,
                }
            )
    return rows


def count_visual_values(
    rows: list[dict[str, str]],
    dimension: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(dimension, "")
        if value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def visual_uniformity_findings(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = visual_plan_rows(data)
    findings: list[dict[str, Any]] = []
    scene_count = len({row["scene_id"] for row in rows})

    def add_scope_findings(
        scope_rows: list[dict[str, str]],
        *,
        scope: str,
        scene_id: str | None,
    ) -> None:
        count = len(scope_rows)
        for dimension in sorted(VISUAL_UNIFORMITY_DIMENSIONS):
            counts = count_visual_values(scope_rows, dimension)
            if not counts:
                continue
            dominant_value, dominant_count = max(
                counts.items(),
                key=lambda item: (item[1], item[0]),
            )
            ratio = dominant_count / count
            hard_collapse = (
                scope == "project"
                and dimension == "angle"
                and scene_count >= 2
                and ratio == 1.0
            )
            if scope == "project":
                triggered = count >= 8 and ratio >= 0.75 or hard_collapse
            else:
                triggered = (
                    count >= 5
                    and ratio >= 0.75
                    or 3 <= count <= 4
                    and ratio == 1.0
                )
            if triggered:
                findings.append(
                    {
                        "scope": scope,
                        "scene_id": scene_id,
                        "dimension": dimension,
                        "dominant_value": dominant_value,
                        "dominant_count": dominant_count,
                        "total_count": count,
                        "ratio": round(ratio, 6),
                        "hard_collapse": hard_collapse,
                    }
                )

    add_scope_findings(rows, scope="project", scene_id=None)
    by_scene: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_scene.setdefault(row["scene_id"], []).append(row)
    for scene_id in sorted(by_scene):
        add_scope_findings(
            by_scene[scene_id],
            scope="scene",
            scene_id=scene_id,
        )
    return findings


def visual_distribution_summary(data: dict[str, Any]) -> dict[str, Any]:
    rows = visual_plan_rows(data)
    by_scene: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_scene.setdefault(row["scene_id"], []).append(row)
    reviews = [
        review
        for review in as_list(
            as_dict(data.get("shot_plan")).get("visual_uniformity_reviews")
        )
        if isinstance(review, dict)
    ]
    return {
        "project": {
            "planned_shots": len(rows),
            "angles": count_visual_values(rows, "angle"),
            "shot_sizes": count_visual_values(rows, "shot_size"),
            "movement_classes": count_visual_values(rows, "movement_class"),
        },
        "scenes": {
            scene_id: {
                "planned_shots": len(scene_rows),
                "angles": count_visual_values(scene_rows, "angle"),
                "shot_sizes": count_visual_values(scene_rows, "shot_size"),
                "movement_classes": count_visual_values(
                    scene_rows,
                    "movement_class",
                ),
            }
            for scene_id, scene_rows in sorted(by_scene.items())
        },
        "uniformity_findings": visual_uniformity_findings(data),
        "confirmed_uniformity_reviews": reviews,
    }


def validate_visual_uniformity_reviews(
    data: dict[str, Any],
    *,
    scenes: dict[str, dict[str, Any]],
    review_mode: bool,
    result: ValidationResult,
) -> None:
    plan = as_dict(data.get("shot_plan"))
    raw_reviews = plan.get("visual_uniformity_reviews")
    if not isinstance(raw_reviews, list):
        result.error(
            "VISUAL_UNIFORMITY_REVIEWS",
            "$.shot_plan.visual_uniformity_reviews",
            "必须是数组；没有高占比统一策略时使用空数组。",
        )
        raw_reviews = []
    all_anchor_ids = {
        anchor_id
        for scene in scenes.values()
        for anchor_id in scene_style_anchor_ids(scene)
    }
    review_keys: dict[tuple[str, str | None, str, str], str] = {}
    seen_review_ids: set[str] = set()
    for index, review in enumerate(raw_reviews):
        path = f"$.shot_plan.visual_uniformity_reviews[{index}]"
        if not isinstance(review, dict):
            result.error("VISUAL_UNIFORMITY_REVIEW", path, "复核记录必须是对象。")
            continue
        validate_exact_fields(
            review,
            expected=VISUAL_UNIFORMITY_REVIEW_KEYS,
            path=path,
            code_prefix="VISUAL_UNIFORMITY_REVIEW",
            result=result,
        )
        review_id = review.get("review_id")
        if not id_is_canonical(review_id, "visual_review"):
            result.error(
                "VISUAL_UNIFORMITY_REVIEW_ID",
                f"{path}.review_id",
                "必须是 canonical VRxxx。",
            )
        elif review_id in seen_review_ids:
            result.error(
                "VISUAL_UNIFORMITY_REVIEW_ID_DUPLICATE",
                f"{path}.review_id",
                "复核记录 ID 重复。",
            )
        else:
            seen_review_ids.add(review_id)
        scope = review.get("scope")
        if scope not in VISUAL_UNIFORMITY_SCOPES:
            result.error(
                "VISUAL_UNIFORMITY_REVIEW_SCOPE",
                f"{path}.scope",
                "scope 必须为 project 或 scene。",
            )
        scene_id = review.get("scene_id")
        if scope == "project" and scene_id is not None:
            result.error(
                "VISUAL_UNIFORMITY_REVIEW_SCENE",
                f"{path}.scene_id",
                "project 范围复核的 scene_id 必须为 null。",
            )
        if scope == "scene" and scene_id not in scenes:
            result.error(
                "VISUAL_UNIFORMITY_REVIEW_SCENE",
                f"{path}.scene_id",
                "scene 范围复核必须引用存在的 scene_id。",
            )
        dimension = review.get("dimension")
        if dimension not in VISUAL_UNIFORMITY_DIMENSIONS:
            result.error(
                "VISUAL_UNIFORMITY_REVIEW_DIMENSION",
                f"{path}.dimension",
                "dimension 必须为 angle 或 movement_class。",
            )
        dominant_value = require_nonempty_string(
            review.get("dominant_value"),
            path=f"{path}.dominant_value",
            result=result,
        )
        reason = require_nonempty_string(
            review.get("reason"),
            path=f"{path}.reason",
            result=result,
        )
        if reason and (
            len(reason) < 12
            or reason in {"统一风格", "风格需要", "保持一致", "导演风格要求"}
        ):
            result.error(
                "VISUAL_UNIFORMITY_REVIEW_REASON",
                f"{path}.reason",
                "保留高占比视觉策略必须说明具体人物、空间、观看或叙事收益。",
            )
        style_anchor_ids = list_of_unique_strings(
            review.get("style_anchor_ids"),
            path=f"{path}.style_anchor_ids",
            result=result,
            allow_empty=False,
        )
        allowed_anchor_ids = (
            scene_style_anchor_ids(scenes.get(str(scene_id), {}))
            if scope == "scene"
            else all_anchor_ids
        )
        for anchor_index, anchor_id in enumerate(style_anchor_ids):
            if anchor_id not in allowed_anchor_ids:
                result.error(
                    "VISUAL_UNIFORMITY_REVIEW_STYLE_ANCHOR",
                    f"{path}.style_anchor_ids[{anchor_index}]",
                    "复核记录必须引用其范围内已确认的风格锚点。",
                )
        key = (
            str(scope),
            str(scene_id) if scene_id is not None else None,
            str(dimension),
            dominant_value,
        )
        if key in review_keys:
            result.error(
                "VISUAL_UNIFORMITY_REVIEW_DUPLICATE",
                path,
                "同一范围、维度和主导值只能登记一次复核。",
            )
        else:
            review_keys[key] = str(review_id)

    finding_keys: set[tuple[str, str | None, str, str]] = set()
    for finding in visual_uniformity_findings(data):
        key = (
            finding["scope"],
            finding["scene_id"],
            finding["dimension"],
            finding["dominant_value"],
        )
        finding_keys.add(key)
        if key in review_keys:
            continue
        path = (
            "$.shot_plan.planned_units[*].visual_plan"
            if finding["scope"] == "project"
            else f"scene:{finding['scene_id']}.visual_plan"
        )
        message = (
            f"{finding['dominant_count']}/{finding['total_count']} 个规划单元的 "
            f"{finding['dimension']} 归一化为 `{finding['dominant_value']}`；"
            "必须调整方案，或提交绑定风格锚点的结构化统一策略复核。"
        )
        if finding["hard_collapse"] or not review_mode:
            result.error("VISUAL_UNIFORMITY_REVIEW_REQUIRED", path, message)
        else:
            result.warn("VISUAL_UNIFORMITY_REVIEW_REQUIRED", path, message)
    for key, review_id in review_keys.items():
        if key not in finding_keys:
            result.error(
                "VISUAL_UNIFORMITY_REVIEW_UNUSED",
                "$.shot_plan.visual_uniformity_reviews",
                f"复核 `{review_id}` 没有对应当前规划中的高占比视觉模式。",
            )


def validate_shot_plan(
    data: dict[str, Any],
    *,
    locked_text: str,
    scenes: dict[str, dict[str, Any]],
    beat_lookup: dict[str, dict[str, Any]],
    fact_lookup: dict[str, dict[str, Any]],
    screen_event_lookup: dict[str, dict[str, Any]],
    review_mode: bool = False,
    result: ValidationResult,
) -> dict[str, Any]:
    plan = data.get("shot_plan")
    empty = {
        "units": [],
        "unit_lookup": {},
        "unit_ranges": {},
        "boundary_edit_ids": {},
        "screen_event_lookup": screen_event_lookup,
    }
    if not isinstance(plan, dict):
        result.error("SHOT_PLAN", "$.shot_plan", "Gate 2 拆镜规划必须是对象。")
        return empty
    validate_exact_fields(
        plan,
        expected=SHOT_PLAN_KEYS,
        path="$.shot_plan",
        code_prefix="SHOT_PLAN",
        result=result,
    )

    units = plan.get("planned_units")
    if not isinstance(units, list) or not units:
        result.error("PLAN_UNITS", "$.shot_plan.planned_units", "必须是非空规划单元数组。")
        units = []
    unit_lookup: dict[str, dict[str, Any]] = {}
    unit_ranges: dict[str, list[tuple[int, int]]] = {}
    unit_anchors: dict[str, int] = {}
    unit_indices: dict[str, int] = {}
    event_to_unit: dict[str, str] = {}
    for index, unit in enumerate(units):
        path = f"$.shot_plan.planned_units[{index}]"
        if not isinstance(unit, dict):
            result.error("PLAN_UNIT", path, "规划单元必须是对象。")
            continue
        validate_required_optional_fields(
            unit,
            required=PLAN_UNIT_REQUIRED_KEYS,
            optional=PLAN_UNIT_OPTIONAL_KEYS,
            path=path,
            code_prefix="PLAN_UNIT",
            result=result,
        )
        unit_id = unit.get("plan_unit_id")
        if not id_is_canonical(unit_id, "plan_unit"):
            result.error("PLAN_UNIT_ID", f"{path}.plan_unit_id", "必须是 canonical PUxxx。")
            continue
        assert isinstance(unit_id, str)
        if unit_id in unit_lookup:
            result.error("PLAN_UNIT_ID_DUPLICATE", f"{path}.plan_unit_id", "规划单元 ID 重复。")
        unit_lookup[unit_id] = unit
        unit_indices[unit_id] = index
        if unit.get("plan_order") != index + 1:
            result.error(
                "PLAN_UNIT_ORDER",
                f"{path}.plan_order",
                "planned_units[] 位置必须与从 1 开始的 plan_order 一致。",
            )
        scene_id = unit.get("scene_id")
        if scene_id not in scenes:
            result.error("PLAN_UNIT_SCENE", f"{path}.scene_id", "引用的场景不存在。")
        beat_ids = list_of_unique_strings(
            unit.get("beat_ids"),
            path=f"{path}.beat_ids",
            result=result,
            allow_empty=False,
        )
        beat_orders: list[int] = []
        beat_ranges: list[tuple[int, int]] = []
        for beat_index, beat_id in enumerate(beat_ids):
            beat = beat_lookup.get(beat_id)
            if not beat:
                result.error("PLAN_UNIT_BEAT", f"{path}.beat_ids[{beat_index}]", "Beat 不存在。")
                continue
            if beat.get("scene_id") != scene_id:
                result.error(
                    "PLAN_UNIT_BEAT_SCENE",
                    f"{path}.beat_ids[{beat_index}]",
                    "Beat 与规划单元不在同场。",
                )
            order_value = beat.get("beat_order")
            if isinstance(order_value, int):
                beat_orders.append(order_value)
            beat_ranges.extend(span_coordinates(beat.get("source_spans"), locked_text))
        if beat_orders != sorted(beat_orders):
            result.error("PLAN_UNIT_BEAT_ORDER", f"{path}.beat_ids", "规划单元内 Beat 不得倒序。")
        screen_event_ids = list_of_unique_strings(
            unit.get("screen_event_ids"),
            path=f"{path}.screen_event_ids",
            result=result,
            allow_empty=False,
        )
        for event_index, event_id in enumerate(screen_event_ids):
            event = screen_event_lookup.get(event_id)
            if event is None:
                result.error(
                    "PLAN_UNIT_SCREEN_EVENT",
                    f"{path}.screen_event_ids[{event_index}]",
                    "屏幕事件不存在。",
                )
                continue
            if event.get("scene_id") != scene_id:
                result.error(
                    "PLAN_UNIT_SCREEN_EVENT_SCENE",
                    f"{path}.screen_event_ids[{event_index}]",
                    "屏幕事件与规划单元不在同场。",
                )
            if event_id in event_to_unit:
                result.error(
                    "PLAN_UNIT_SCREEN_EVENT_DUPLICATE",
                    f"{path}.screen_event_ids[{event_index}]",
                    "同一屏幕事件只能属于一个规划单元。",
                )
            event_to_unit[event_id] = unit_id
        event_orders = [
            screen_event_lookup[event_id].get("event_order")
            for event_id in screen_event_ids
            if event_id in screen_event_lookup
            and is_json_integer(
                screen_event_lookup[event_id].get("event_order"),
                1,
            )
        ]
        if event_orders != sorted(event_orders):
            result.error(
                "PLAN_UNIT_SCREEN_EVENT_ORDER",
                f"{path}.screen_event_ids",
                "规划单元内 screen_event_ids 必须保持该场 event_order；需要导演性倒序时应拆为多个规划单元并用 reorder 声明。",
            )
        span_texts(
            unit.get("source_spans"),
            locked_text,
            path=f"{path}.source_spans",
            result=result,
        )
        ranges = span_coordinates(unit.get("source_spans"), locked_text)
        unit_ranges[unit_id] = ranges
        if ranges:
            unit_anchors[unit_id] = min(start for start, _ in ranges)
        if beat_ranges and ranges:
            if not all(
                any(
                    beat_start <= unit_start
                    and unit_end <= beat_end
                    or unit_start <= beat_start
                    and beat_end <= unit_end
                    or unit_start < beat_end
                    and beat_start < unit_end
                    for beat_start, beat_end in beat_ranges
                )
                for unit_start, unit_end in ranges
            ):
                result.error(
                    "PLAN_UNIT_SOURCE",
                    f"{path}.source_spans",
                    "规划单元 source spans 必须与其 Beat 来源范围有坐标关系。",
                )
        shot_form = unit.get("shot_form")
        if shot_form is not None and shot_form not in SHOT_FORMS:
            result.error(
                "SHOT_FORM",
                f"{path}.shot_form",
                "普通镜头省略 shot_form；只有明确采用长镜头时写 long_take。",
            )
        duration = unit.get("estimated_duration_seconds")
        if not is_json_integer(duration, 1):
            result.error(
                "PLAN_UNIT_DURATION",
                f"{path}.estimated_duration_seconds",
                "规划估算时长必须是正 JSON 整数。",
            )
        elif int(duration) > ORDINARY_SHOT_MAX_SECONDS and shot_form != "long_take":
            result.error(
                "ORDINARY_SHOT_DURATION_EXCEEDED",
                f"{path}.estimated_duration_seconds",
                "普通剧情镜不得超过 10 秒；必须拆镜，或在确有连续时空收益时显式设计 long_take。",
            )
        long_take_design = unit.get("long_take_design")
        if shot_form == "long_take":
            if not isinstance(long_take_design, dict):
                result.error(
                    "LONG_TAKE_DESIGN_REQUIRED",
                    f"{path}.long_take_design",
                    "long_take 必须登记 reason、supports 与 protected_event_ids。",
                )
            else:
                validate_exact_fields(
                    long_take_design,
                    expected=LONG_TAKE_DESIGN_KEYS,
                    path=f"{path}.long_take_design",
                    code_prefix="LONG_TAKE_DESIGN",
                    result=result,
                )
                require_nonempty_string(
                    long_take_design.get("reason"),
                    path=f"{path}.long_take_design.reason",
                    result=result,
                )
                supports = list_of_unique_strings(
                    long_take_design.get("supports"),
                    path=f"{path}.long_take_design.supports",
                    result=result,
                    allow_empty=False,
                )
                for support_index, support in enumerate(supports):
                    if support not in LONG_TAKE_SUPPORTS:
                        result.error(
                            "LONG_TAKE_DESIGN_REQUIRED",
                            f"{path}.long_take_design.supports[{support_index}]",
                            "长镜收益不在允许的导演依据中。",
                        )
                protected_ids = list_of_unique_strings(
                    long_take_design.get("protected_event_ids"),
                    path=f"{path}.long_take_design.protected_event_ids",
                    result=result,
                    allow_empty=False,
                )
                if any(event_id not in screen_event_ids for event_id in protected_ids):
                    result.error(
                        "PROTECTED_PROCESS_SCOPE_OVERREACH",
                        f"{path}.long_take_design.protected_event_ids",
                        "长镜受保护事件必须完全位于当前规划单元内。",
                    )
        elif long_take_design is not None:
            result.error(
                "LONG_TAKE_DESIGN_REQUIRED",
                f"{path}.long_take_design",
                "普通镜头不得携带 long_take_design。",
            )
        require_nonempty_string(
            unit.get("narrative_purpose"),
            path=f"{path}.narrative_purpose",
            result=result,
        )
        validate_visual_plan(
            unit.get("visual_plan"),
            path=f"{path}.visual_plan",
            scene=scenes.get(str(scene_id), {}),
            result=result,
        )
        event_zones = {
            clean_text(screen_event_lookup[event_id].get("spatial_zone"))
            for event_id in screen_event_ids
            if event_id in screen_event_lookup
            and clean_text(screen_event_lookup[event_id].get("spatial_zone"))
        }
        if len(event_zones) >= 2 and as_dict(
            as_dict(unit.get("visual_plan")).get("spatial_strategy")
        ).get("type") == "not_applicable":
            result.error(
                "VISUAL_PLAN_MULTI_ZONE_STRATEGY",
                f"{path}.visual_plan.spatial_strategy",
                "同镜覆盖多个空间区域时必须提供可执行的构图、光学、调度或镜内重构方案。",
            )
        unit_dialogue_facts = dialogue_facts_for_plan_unit(
            unit,
            screen_event_lookup,
            fact_lookup,
        )
        validate_dialogue_design(
            unit.get("dialogue_design"),
            path=f"{path}.dialogue_design",
            dialogue_facts=unit_dialogue_facts,
            scene=scenes.get(str(scene_id), {}),
            result=result,
        )
        speaker_sequence = [
            clean_text(fact.get("speaker"))
            for fact in unit_dialogue_facts
            if clean_text(fact.get("speaker"))
        ]
        if len(speaker_sequence) > 1 and not isinstance(unit.get("dialogue_design"), dict):
            result.error(
                "DIALOGUE_HANDOFF_CUT_REQUIRED",
                f"{path}.dialogue_design",
                "同镜包含多个对白轮次时必须登记 dialogue_design；默认方案应在发言权转移处切镜。",
            )
        if (
            is_json_integer(duration, 1)
            and int(duration) > ORDINARY_SHOT_MAX_SECONDS
            and len(screen_event_ids) > 1
        ):
            event_rows = [
                screen_event_lookup[event_id]
                for event_id in screen_event_ids
                if event_id in screen_event_lookup
            ]
            subjects = {
                clean_text(event.get("primary_viewing_subject"))
                for event in event_rows
            }
            scales = {clean_text(event.get("focus_scale")) for event in event_rows}
            speakers = [
                speaker
                for event in event_rows
                for speaker in screen_event_speakers(event, fact_lookup)
            ]
            overload = (
                len(subjects) > 1
                or len(scales) > 1
                or len(set(speakers)) > 1
                or any(
                    event.get("event_role") == "information_landing"
                    for event in event_rows
                )
                or sum(event.get("event_role") == "action" for event in event_rows) > 1
            )
            if overload:
                result.error(
                    "PROTECTED_PROCESS_SCOPE_OVERREACH",
                    f"{path}.screen_event_ids",
                    "超过 10 秒的镜头不得用长镜理由包住说话者、观看主体、尺度、认知落点或多个顺序动作变化；必须拆镜。",
                )
        reuse = unit.get("source_reuse")
        previous_unit = units[index - 1] if index > 0 and isinstance(units[index - 1], dict) else None
        previous_ranges = (
            span_coordinates(previous_unit.get("source_spans"), locked_text)
            if previous_unit is not None
            else []
        )
        repeats_previous_source = bool(
            previous_unit
            and previous_unit.get("scene_id") == scene_id
            and ranges
            and ranges == previous_ranges
        )
        if reuse is None:
            if repeats_previous_source:
                result.error(
                    "SOURCE_REUSE_UNDECLARED",
                    f"{path}.source_reuse",
                    "相邻规划单元完全复用同一 source spans 时必须登记具体例外。",
                )
        elif not isinstance(reuse, dict):
            result.error(
                "SOURCE_REUSE",
                f"{path}.source_reuse",
                "必须为 null 或 source_reuse 对象。",
            )
        else:
            validate_exact_fields(
                reuse,
                expected=SOURCE_REUSE_KEYS,
                path=f"{path}.source_reuse",
                code_prefix="SOURCE_REUSE",
                result=result,
            )
            expected_previous_id = (
                previous_unit.get("plan_unit_id") if previous_unit is not None else None
            )
            if reuse.get("from_plan_unit_id") != expected_previous_id:
                result.error(
                    "SOURCE_REUSE_PREVIOUS",
                    f"{path}.source_reuse.from_plan_unit_id",
                    "必须精确指向同场上一规划单元。",
                )
            if not repeats_previous_source:
                result.error(
                    "SOURCE_REUSE_SPANS",
                    f"{path}.source_reuse",
                    "source_reuse 只用于相邻同场规划单元完全复用同一 source spans。",
                )
            if reuse.get("reason") not in SOURCE_REUSE_REASONS:
                result.error(
                    "SOURCE_REUSE_REASON",
                    f"{path}.source_reuse.reason",
                    "source_reuse reason 不合法。",
                )
            require_nonempty_string(
                reuse.get("justification"),
                path=f"{path}.source_reuse.justification",
                result=result,
            )

    missing_event_ids = sorted(set(screen_event_lookup) - set(event_to_unit))
    for event_id in missing_event_ids:
        result.error(
            "PLAN_UNIT_SCREEN_EVENT_COVERAGE",
            "$.shot_plan.planned_units",
            f"屏幕事件 `{event_id}` 未分配到规划单元。",
        )

    viewing_decisions = plan.get("viewing_decisions")
    if not isinstance(viewing_decisions, list):
        result.error(
            "VIEWING_DECISIONS",
            "$.shot_plan.viewing_decisions",
            "viewing_decisions 必须是数组。",
        )
        viewing_decisions = []
    expected_event_boundaries: list[tuple[str, str]] = []
    events_by_scene: dict[str, list[dict[str, Any]]] = {}
    for event in screen_event_lookup.values():
        events_by_scene.setdefault(clean_text(event.get("scene_id")), []).append(event)
    for scene_events in events_by_scene.values():
        scene_events.sort(key=lambda item: int(item.get("event_order", 0)))
        expected_event_boundaries.extend(
            (
                clean_text(left.get("screen_event_id")),
                clean_text(right.get("screen_event_id")),
            )
            for left, right in zip(scene_events, scene_events[1:])
        )
    decision_by_boundary: dict[tuple[str, str], dict[str, Any]] = {}
    cut_decisions: list[dict[str, Any]] = []
    decision_ids: set[str] = set()
    for index, decision in enumerate(viewing_decisions):
        path = f"$.shot_plan.viewing_decisions[{index}]"
        if not isinstance(decision, dict):
            result.error("VIEWING_DECISION", path, "观看决策必须是对象。")
            continue
        validate_exact_fields(
            decision,
            expected=VIEWING_DECISION_KEYS,
            path=path,
            code_prefix="VIEWING_DECISION",
            result=result,
        )
        decision_id = decision.get("viewing_decision_id")
        if not id_is_canonical(decision_id, "viewing_decision"):
            result.error(
                "VIEWING_DECISION_ID",
                f"{path}.viewing_decision_id",
                "必须是 canonical VDxxx。",
            )
        elif decision_id in decision_ids:
            result.error(
                "VIEWING_DECISION_ID_DUPLICATE",
                f"{path}.viewing_decision_id",
                "观看决策 ID 重复。",
            )
        else:
            decision_ids.add(str(decision_id))
        from_id = clean_text(decision.get("from_screen_event_id"))
        to_id = clean_text(decision.get("to_screen_event_id"))
        boundary = (from_id, to_id)
        if boundary not in expected_event_boundaries:
            result.error(
                "VIEWING_DECISION_BOUNDARY",
                path,
                "观看决策必须绑定同场相邻屏幕事件。",
            )
        if boundary in decision_by_boundary:
            result.error("VIEWING_DECISION_DUPLICATE", path, "同一事件边界只能有一个决定。")
        decision_by_boundary[boundary] = decision
        from_event = screen_event_lookup.get(from_id, {})
        to_event = screen_event_lookup.get(to_id, {})
        if decision.get("scene_id") != from_event.get("scene_id") or decision.get(
            "scene_id"
        ) != to_event.get("scene_id"):
            result.error(
                "VIEWING_DECISION_SCENE",
                f"{path}.scene_id",
                "观看决策与两个屏幕事件必须在同场。",
            )
        mode = decision.get("mode")
        if mode not in VIEWING_DECISION_MODES:
            result.error("VIEWING_DECISION_MODE", f"{path}.mode", "mode 无效。")
        non_cut_basis = decision.get("non_cut_basis")
        if mode == "cut":
            if non_cut_basis is not None:
                result.error(
                    "NONCUT_BASIS_REQUIRED",
                    f"{path}.non_cut_basis",
                    "cut 的 non_cut_basis 必须为 null。",
                )
        elif non_cut_basis not in NON_CUT_BASES:
            result.error(
                "NONCUT_BASIS_REQUIRED",
                f"{path}.non_cut_basis",
                "hold/reframe 必须登记闭合的 non_cut_basis，证明为何撤销默认切点。",
            )
        for key in ("trigger", "viewing_change", "director_reason"):
            value = require_nonempty_string(decision.get(key), path=f"{path}.{key}", result=result)
            if value in GENERIC_CUT_TERMS:
                result.error(
                    "VIEWING_DECISION_GENERIC",
                    f"{path}.{key}",
                    "类别词不能单独构成观看决策理由。",
                )
        method = decision.get("reframe_method")
        if mode == "reframe":
            if method not in REFRAME_METHODS:
                result.error(
                    "VIEWING_DECISION_REFRAME_METHOD",
                    f"{path}.reframe_method",
                    "reframe 必须说明 blocking、camera_move、focus_shift 或 scale_change。",
                )
        elif method is not None:
            result.error(
                "VIEWING_DECISION_REFRAME_METHOD",
                f"{path}.reframe_method",
                "cut 或 hold 的 reframe_method 必须为 null。",
            )
        from_unit = event_to_unit.get(from_id)
        to_unit = event_to_unit.get(to_id)
        from_speakers = screen_event_speakers(from_event, fact_lookup)
        to_speakers = screen_event_speakers(to_event, fact_lookup)
        speaker_handoff = bool(
            from_speakers
            and to_speakers
            and from_speakers[-1] != to_speakers[0]
        )
        owning_unit = unit_lookup.get(str(from_unit), {})
        owning_visual_plan = as_dict(owning_unit.get("visual_plan"))
        owning_movement = as_dict(owning_visual_plan.get("movement_plan"))
        owning_spatial = as_dict(owning_visual_plan.get("spatial_strategy"))
        boundary_voice_types = {
            fact_lookup.get(str(fact_id), {}).get("script_voice_type")
            for event in (from_event, to_event)
            for fact_id in as_list(event.get("covered_fact_ids"))
            if fact_lookup.get(str(fact_id), {}).get("type") == "dialogue"
        }
        if (
            mode in {"hold", "reframe"}
            and non_cut_basis == "offscreen_or_vo"
            and not boundary_voice_types.intersection({"vo", "os"})
            and not isinstance(owning_unit.get("dialogue_design"), dict)
        ):
            result.error(
                "NONCUT_VISUAL_PLAN_MISMATCH",
                f"{path}.non_cut_basis",
                "offscreen_or_vo 必须由来源 V.O./O.S. 或同镜 dialogue_design 中的画外交付方案证明。",
            )
        if (
            mode in {"hold", "reframe"}
            and non_cut_basis == "continuous_action"
            and to_event.get("temporal_relation") != "continuous_from_previous"
        ):
            result.error(
                "NONCUT_VISUAL_PLAN_MISMATCH",
                f"{path}.non_cut_basis",
                "continuous_action 必须由 continuous_from_previous 时间关系证明。",
            )
        if (
            mode in {"hold", "reframe"}
            and non_cut_basis == "simultaneous_event"
            and to_event.get("temporal_relation") != "simultaneous_with_previous"
        ):
            result.error(
                "NONCUT_VISUAL_PLAN_MISMATCH",
                f"{path}.non_cut_basis",
                "simultaneous_event 必须由 simultaneous_with_previous 时间关系证明。",
            )
        if speaker_handoff and mode != "cut":
            dialogue_design = owning_unit.get("dialogue_design")
            if not isinstance(dialogue_design, dict):
                result.error(
                    "DIALOGUE_HANDOFF_CUT_REQUIRED",
                    path,
                    "发言权已经转移；若不切镜，必须提供 dialogue_design 与明确的非切收益。",
                )
            elif non_cut_basis not in {
                "listener_ownership",
                "offscreen_or_vo",
                "continuous_action",
                "shared_staging",
                "delayed_reverse",
            }:
                result.error(
                    "DIALOGUE_HANDOFF_CUT_REQUIRED",
                    f"{path}.non_cut_basis",
                    "对白交接默认切镜；当前 non_cut_basis 不能证明撤销切点。",
                )
        scale_changed = (
            clean_text(from_event.get("focus_scale"))
            != clean_text(to_event.get("focus_scale"))
        )
        if scale_changed and mode != "cut" and mode != "reframe":
            result.error(
                "NONCUT_VISUAL_PLAN_MISMATCH",
                path,
                "观看尺度变化只能切镜或通过可执行 reframe 完成，普通 hold 不能承担尺度重组。",
            )
        subject_changed = (
            clean_text(from_event.get("primary_viewing_subject"))
            != clean_text(to_event.get("primary_viewing_subject"))
        )
        if (
            subject_changed
            and mode == "hold"
            and non_cut_basis
            not in {
                "listener_ownership",
                "offscreen_or_vo",
                "shared_staging",
                "simultaneous_event",
            }
        ):
            result.error(
                "NONCUT_VISUAL_PLAN_MISMATCH",
                path,
                "主要观看主体改变时默认切镜；保留同镜必须由共享画面所有权证明，或使用可执行 reframe。",
            )
        if scale_changed and mode == "reframe":
            shot_size = clean_text(owning_visual_plan.get("shot_size"))
            executable_scale_reframe = (
                method in {"focus_shift", "scale_change"}
                and (
                    "→" in shot_size
                    or owning_movement.get("class")
                    in {"focus", "push", "pull", "track_or_follow", "compound_move_then_fixed"}
                    or owning_spatial.get("type") == "sequential_reframe"
                )
            )
            if not executable_scale_reframe:
                result.error(
                    "NONCUT_VISUAL_PLAN_MISMATCH",
                    path,
                    "尺度重构的 reframe_method 必须由景别变化、焦点变化、摄影机路径或 sequential_reframe 兑现。",
                )
        if mode in {"hold", "reframe"} and non_cut_basis == "blocking_proof":
            if owning_spatial.get("type") != "blocking_reveal":
                result.error(
                    "NONCUT_VISUAL_PLAN_MISMATCH",
                    f"{path}.non_cut_basis",
                    "blocking_proof 必须由 spatial_strategy=blocking_reveal 及前后构图比对执行。",
                )
            if len(as_list(owning_unit.get("screen_event_ids"))) > 2:
                result.error(
                    "PROTECTED_PROCESS_SCOPE_OVERREACH",
                    f"{path}.non_cut_basis",
                    "遮挡证明只保护遮挡开始至结果显露的核心事件，不得吞并前置关系或后置反应。",
                )
        if mode == "cut":
            cut_decisions.append(decision)
            if not from_unit or not to_unit or from_unit == to_unit:
                result.error(
                    "VIEWING_DECISION_CUT_UNIT",
                    path,
                    "cut 两侧事件必须属于不同的相邻规划单元。",
                )
            elif abs(unit_indices.get(to_unit, -99) - unit_indices.get(from_unit, 99)) != 1:
                result.error(
                    "VIEWING_DECISION_CUT_UNIT",
                    path,
                    "cut 两侧事件必须属于相邻规划单元。",
                )
        elif mode in {"hold", "reframe"} and from_unit != to_unit:
            result.error(
                "VIEWING_DECISION_HOLD_UNIT",
                path,
                "hold 或 reframe 的相邻事件必须属于同一规划单元。",
            )
    dialogue_non_cut_bases = {
        "listener_ownership",
        "offscreen_or_vo",
        "continuous_action",
        "shared_staging",
        "delayed_reverse",
    }
    for scene_events in events_by_scene.values():
        scene_events.sort(key=lambda item: int(item.get("event_order", 0)))
        dialogue_events = [
            (index, event, screen_event_speakers(event, fact_lookup)[0])
            for index, event in enumerate(scene_events)
            if screen_event_speakers(event, fact_lookup)
        ]
        for (left_index, left_event, left_speaker), (
            right_index,
            right_event,
            right_speaker,
        ) in zip(dialogue_events, dialogue_events[1:]):
            if left_speaker == right_speaker:
                continue
            boundaries = [
                (
                    clean_text(scene_events[index].get("screen_event_id")),
                    clean_text(scene_events[index + 1].get("screen_event_id")),
                )
                for index in range(left_index, right_index)
            ]
            boundary_decisions = [
                decision_by_boundary.get(boundary, {}) for boundary in boundaries
            ]
            if any(item.get("mode") == "cut" for item in boundary_decisions):
                continue
            owning_unit = unit_lookup.get(
                event_to_unit.get(
                    clean_text(left_event.get("screen_event_id")), ""
                ),
                {},
            )
            has_basis = any(
                item.get("non_cut_basis") in dialogue_non_cut_bases
                for item in boundary_decisions
            )
            if (
                not has_basis
                or not isinstance(owning_unit.get("dialogue_design"), dict)
            ):
                result.error(
                    "DIALOGUE_HANDOFF_CUT_REQUIRED",
                    "$.shot_plan.viewing_decisions",
                    f"对白从 `{left_speaker}` 转交 `{right_speaker}`；默认切镜，跨越中间动作仍须有明确 non_cut_basis 与 dialogue_design 才能不切。",
                )
    for boundary in expected_event_boundaries:
        if boundary not in decision_by_boundary:
            result.error(
                "VIEWING_DECISION_MISSING",
                "$.shot_plan.viewing_decisions",
                f"相邻屏幕事件 `{boundary[0]}` → `{boundary[1]}` 缺少观看决策。",
            )

    edit_points = plan.get("edit_points")
    if not isinstance(edit_points, list):
        result.error("EDIT_POINTS", "$.shot_plan.edit_points", "必须是数组。")
        edit_points = []
    edit_ids: set[str] = set()
    boundary_edit_ids: dict[tuple[str, str], str] = {}
    for index, edit_point in enumerate(edit_points):
        path = f"$.shot_plan.edit_points[{index}]"
        if not isinstance(edit_point, dict):
            result.error("EDIT_POINT", path, "剪辑点必须是对象。")
            continue
        validate_required_optional_fields(
            edit_point,
            required=EDIT_POINT_REQUIRED_KEYS,
            optional=EDIT_POINT_OPTIONAL_KEYS,
            path=path,
            code_prefix="EDIT_POINT",
            result=result,
        )
        edit_id = edit_point.get("edit_point_id")
        if not id_is_canonical(edit_id, "edit_point"):
            result.error("EDIT_POINT_ID", f"{path}.edit_point_id", "必须是 canonical EPxxx。")
            continue
        assert isinstance(edit_id, str)
        if edit_id in edit_ids:
            result.error("EDIT_POINT_ID_DUPLICATE", f"{path}.edit_point_id", "剪辑点 ID 重复。")
        edit_ids.add(edit_id)
        after_id = edit_point.get("after_plan_unit_id")
        before_id = edit_point.get("before_plan_unit_id")
        cut_decision = (
            cut_decisions[index]
            if index < len(cut_decisions) and isinstance(cut_decisions[index], dict)
            else {}
        )
        left_unit = event_to_unit.get(
            clean_text(cut_decision.get("from_screen_event_id"))
        )
        right_unit = event_to_unit.get(
            clean_text(cut_decision.get("to_screen_event_id"))
        )
        expected_after, expected_before = (
            (left_unit, right_unit)
            if unit_indices.get(str(left_unit), -1)
            <= unit_indices.get(str(right_unit), -1)
            else (right_unit, left_unit)
        )
        if after_id != expected_after or before_id != expected_before:
            result.error(
                "EDIT_POINT_BOUNDARY",
                path,
                "每个剪辑点必须依次绑定相邻规划单元，且不得隐藏或增加剪辑点。",
            )
        if isinstance(after_id, str) and isinstance(before_id, str):
            boundary = (after_id, before_id)
            if boundary in boundary_edit_ids:
                result.error("EDIT_POINT_BOUNDARY_DUPLICATE", path, "相邻规划边界不得重复。")
            boundary_edit_ids[boundary] = edit_id
        trigger = require_nonempty_string(
            edit_point.get("trigger"),
            path=f"{path}.trigger",
            result=result,
        )
        gain = require_nonempty_string(
            edit_point.get("editorial_gain"),
            path=f"{path}.editorial_gain",
            result=result,
        )
        if cut_decision and trigger != cut_decision.get("trigger"):
            result.error(
                "EDIT_POINT_DERIVATION",
                f"{path}.trigger",
                "edit point trigger 必须从对应 cut 观看决策确定性派生。",
            )
        if cut_decision and gain != cut_decision.get("director_reason"):
            result.error(
                "EDIT_POINT_DERIVATION",
                f"{path}.editorial_gain",
                "edit point editorial_gain 必须复制对应 cut 的 director_reason。",
            )
        for key, value in (("trigger", trigger), ("editorial_gain", gain)):
            if value in GENERIC_CUT_TERMS:
                result.error(
                    "EDIT_POINT_GENERIC",
                    f"{path}.{key}",
                    "类别词不能单独构成剪切理由，必须写出具体触发与相对于不剪的收益。",
                )
        if "broken_performance_chain_ids" in edit_point:
            list_of_unique_strings(
                edit_point.get("broken_performance_chain_ids"),
                path=f"{path}.broken_performance_chain_ids",
                result=result,
                allow_empty=True,
            )
        span_texts(
            edit_point.get("source_spans"),
            locked_text,
            path=f"{path}.source_spans",
            result=result,
        )
        ranges = span_coordinates(edit_point.get("source_spans"), locked_text)
        after_ranges = unit_ranges.get(str(after_id), [])
        before_ranges = unit_ranges.get(str(before_id), [])
        if ranges and (
            not any(spans_contained([item], after_ranges) for item in ranges)
            or not any(spans_contained([item], before_ranges) for item in ranges)
        ):
            result.error(
                "EDIT_POINT_SOURCE",
                f"{path}.source_spans",
                "剪辑点必须至少各有一个坐标证据落在前后规划单元来源范围。",
            )

    reorders = plan.get("reorders")
    if not isinstance(reorders, list):
        result.error("REORDERS", "$.shot_plan.reorders", "必须是数组。")
        reorders = []
    reorder_lookup: dict[str, dict[str, Any]] = {}
    reorder_pairs: set[tuple[str, str]] = set()
    for index, reorder in enumerate(reorders):
        path = f"$.shot_plan.reorders[{index}]"
        if not isinstance(reorder, dict):
            result.error("REORDER", path, "导演性重排必须是对象。")
            continue
        validate_exact_fields(
            reorder,
            expected=REORDER_KEYS,
            path=path,
            code_prefix="REORDER",
            result=result,
        )
        reorder_id = reorder.get("reorder_id")
        if not id_is_canonical(reorder_id, "reorder"):
            result.error("REORDER_ID", f"{path}.reorder_id", "必须是 canonical ROxxx。")
            continue
        assert isinstance(reorder_id, str)
        if reorder_id in reorder_lookup:
            result.error("REORDER_ID_DUPLICATE", f"{path}.reorder_id", "reorder_id 重复。")
        reorder_lookup[reorder_id] = reorder
        ids = list_of_unique_strings(
            reorder.get("plan_unit_ids"),
            path=f"{path}.plan_unit_ids",
            result=result,
            allow_empty=False,
        )
        if len(ids) < 2:
            result.error("REORDER_UNITS", f"{path}.plan_unit_ids", "重排至少绑定两个规划单元。")
        indices = [unit_indices[item] for item in ids if item in unit_indices]
        for unit_index, unit_id in enumerate(ids):
            if unit_id not in unit_lookup:
                result.error("REORDER_UNIT", f"{path}.plan_unit_ids[{unit_index}]", "规划单元不存在。")
        if indices and indices != list(range(min(indices), max(indices) + 1)):
            result.error("REORDER_UNITS", f"{path}.plan_unit_ids", "重排单元必须按规划顺序连续列出。")
        span_texts(
            reorder.get("source_spans"),
            locked_text,
            path=f"{path}.source_spans",
            result=result,
        )
        reorder_ranges = span_coordinates(reorder.get("source_spans"), locked_text)
        for unit_id in ids:
            ranges = unit_ranges.get(unit_id, [])
            if ranges and not spans_contained(ranges, reorder_ranges):
                result.error(
                    "REORDER_SOURCE",
                    f"{path}.source_spans",
                    "重排来源范围必须坐标包含每个被重排规划单元。",
                )
        require_nonempty_string(reorder.get("reason"), path=f"{path}.reason", result=result)
        has_inversion = False
        for left, right in zip(ids, ids[1:]):
            reorder_pairs.add((left, right))
            if unit_anchors.get(right, -1) < unit_anchors.get(left, -1):
                has_inversion = True
        if ids and not has_inversion:
            result.error("REORDER_UNUSED", path, "声明的导演性重排没有对应任何来源倒序。")

    unit_ids_in_order = [
        unit.get("plan_unit_id")
        for unit in units
        if isinstance(unit, dict) and isinstance(unit.get("plan_unit_id"), str)
    ]
    for left, right in zip(unit_ids_in_order, unit_ids_in_order[1:]):
        if unit_anchors.get(right, -1) < unit_anchors.get(left, -1) and (left, right) not in reorder_pairs:
            result.error(
                "PLAN_SOURCE_ORDER",
                f"$.shot_plan.planned_units[{unit_indices[right]}]",
                "规划默认必须保持来源单调顺序；倒序必须由已确认且绑定来源范围的 reorder 声明。",
            )

    planned_count = len(units)
    edit_count = len(cut_decisions)
    durations = [
        unit.get("estimated_duration_seconds")
        for unit in units
        if isinstance(unit, dict)
        and is_json_integer(unit.get("estimated_duration_seconds"), 1)
    ]
    total_duration = sum(int(value) for value in durations)
    for field_name in (
        "planned_shot_count",
        "planned_edit_point_count",
        "planned_total_duration_seconds",
    ):
        if not is_json_integer(plan.get(field_name), 0):
            result.error(
                "SHOT_PLAN_COUNT_TYPE",
                f"$.shot_plan.{field_name}",
                "数量统计必须是非负 JSON 整数。",
            )
    require_metric(
        plan.get("planned_shot_count"),
        float(planned_count),
        path="$.shot_plan.planned_shot_count",
        result=result,
    )
    require_metric(
        plan.get("planned_edit_point_count"),
        float(edit_count),
        path="$.shot_plan.planned_edit_point_count",
        result=result,
    )
    require_metric(
        plan.get("planned_total_duration_seconds"),
        float(total_duration),
        path="$.shot_plan.planned_total_duration_seconds",
        result=result,
    )
    if len(edit_points) != edit_count:
        result.error(
            "EDIT_POINT_COUNT",
            "$.shot_plan.edit_points",
            "剪辑点数组必须恰好覆盖每个相邻规划单元边界。",
        )
    validate_visual_uniformity_reviews(
        data,
        scenes=scenes,
        review_mode=review_mode,
        result=result,
    )
    return {
        "units": units,
        "unit_lookup": unit_lookup,
        "unit_ranges": unit_ranges,
        "boundary_edit_ids": boundary_edit_ids,
        "screen_event_lookup": screen_event_lookup,
        "event_to_unit": event_to_unit,
    }


def validate_performance_chains(
    data: dict[str, Any],
    *,
    locked_text: str,
    scenes: dict[str, dict[str, Any]],
    fact_lookup: dict[str, dict[str, Any]],
    fact_beat: dict[str, str],
    fact_order: dict[str, int],
    beat_lookup: dict[str, dict[str, Any]],
    plan_info: dict[str, Any],
    result: ValidationResult,
) -> dict[str, dict[str, Any]]:
    raw_chains = data.get("performance_chains")
    if raw_chains is None:
        return {}
    if not isinstance(raw_chains, list):
        result.error("PERFORMANCE_CHAINS", "$.performance_chains", "必须是数组。")
        return {}
    units = [
        unit for unit in as_list(plan_info.get("units")) if isinstance(unit, dict)
    ]
    unit_ranges = as_dict(plan_info.get("unit_ranges"))
    edit_points = [
        item
        for item in as_list(as_dict(data.get("shot_plan")).get("edit_points"))
        if isinstance(item, dict)
    ]
    boundary_breaks: dict[int, set[str]] = {
        index: set(
            item
            for item in as_list(edit_point.get("broken_performance_chain_ids"))
            if isinstance(item, str)
        )
        for index, edit_point in enumerate(edit_points)
    }
    lookup: dict[str, dict[str, Any]] = {}
    required_boundaries: dict[str, set[int]] = {}
    for index, chain in enumerate(raw_chains):
        path = f"$.performance_chains[{index}]"
        if not isinstance(chain, dict):
            result.error("PERFORMANCE_CHAIN", path, "表演链必须是对象。")
            continue
        validate_exact_fields(
            chain,
            expected={"chain_id", "scene_id", "character", "steps"},
            path=path,
            code_prefix="PERFORMANCE_CHAIN",
            result=result,
        )
        chain_id = chain.get("chain_id")
        if not id_is_canonical(chain_id, "performance_chain"):
            result.error(
                "PERFORMANCE_CHAIN_ID",
                f"{path}.chain_id",
                "必须是 canonical PCxxx。",
            )
            continue
        assert isinstance(chain_id, str)
        if chain_id in lookup:
            result.error(
                "PERFORMANCE_CHAIN_ID_DUPLICATE",
                f"{path}.chain_id",
                "performance chain ID 重复。",
            )
        lookup[chain_id] = chain
        scene_id = chain.get("scene_id")
        if scene_id not in scenes:
            result.error(
                "PERFORMANCE_CHAIN_SCENE",
                f"{path}.scene_id",
                "表演链场景不存在。",
            )
        character = require_nonempty_string(
            chain.get("character"),
            path=f"{path}.character",
            result=result,
        )
        steps = chain.get("steps")
        if not isinstance(steps, list) or len(steps) < 2:
            result.error(
                "PERFORMANCE_CHAIN_STEPS",
                f"{path}.steps",
                "表演链至少包含两个连续步骤。",
            )
            continue
        ordered_facts: list[str] = []
        step_unit_indices: list[int] = []
        for step_index, step in enumerate(steps):
            step_path = f"{path}.steps[{step_index}]"
            if not isinstance(step, dict):
                result.error("PERFORMANCE_CHAIN_STEP", step_path, "步骤必须是对象。")
                continue
            validate_exact_fields(
                step,
                expected={"role", "fact_ids"},
                path=step_path,
                code_prefix="PERFORMANCE_CHAIN_STEP",
                result=result,
            )
            role = step.get("role")
            if role not in PERFORMANCE_CHAIN_ROLES:
                result.error(
                    "PERFORMANCE_CHAIN_ROLE",
                    f"{step_path}.role",
                    "role 必须为 action / reaction / dialogue。",
                )
            fact_ids = list_of_unique_strings(
                step.get("fact_ids"),
                path=f"{step_path}.fact_ids",
                result=result,
                allow_empty=False,
            )
            candidate_indices: set[int] | None = None
            for fact_id in fact_ids:
                fact = fact_lookup.get(fact_id)
                if fact is None:
                    result.error(
                        "PERFORMANCE_CHAIN_FACT",
                        f"{step_path}.fact_ids",
                        f"fact `{fact_id}` 不存在。",
                    )
                    continue
                beat = beat_lookup.get(fact_beat.get(fact_id, ""), {})
                if beat.get("scene_id") != scene_id:
                    result.error(
                        "PERFORMANCE_CHAIN_FACT_SCENE",
                        f"{step_path}.fact_ids",
                        f"fact `{fact_id}` 不属于链所在场景。",
                    )
                fact_type = fact.get("type")
                expected_types = {
                    "action": {"action"},
                    "reaction": {"emotion", "action"},
                    "dialogue": {"dialogue"},
                }.get(str(role), set())
                if fact_type not in expected_types:
                    result.error(
                        "PERFORMANCE_CHAIN_FACT_TYPE",
                        f"{step_path}.fact_ids",
                        f"role={role} 不能引用 `{fact_type}` fact。",
                    )
                if fact_type == "dialogue" and fact.get("speaker") != character:
                    result.error(
                        "PERFORMANCE_CHAIN_CHARACTER",
                        f"{step_path}.fact_ids",
                        "dialogue speaker 必须等于 chain.character。",
                    )
                if fact_type in {"action", "emotion"} and character not in as_list(
                    fact.get("performers")
                ):
                    result.error(
                        "PERFORMANCE_CHAIN_CHARACTER",
                        f"{step_path}.fact_ids",
                        "action / emotion performers 必须包含 chain.character。",
                    )
                ordered_facts.append(fact_id)
                ranges = span_coordinates(fact.get("source_spans"), locked_text)
                containing = {
                    unit_index
                    for unit_index, unit in enumerate(units)
                    if unit.get("scene_id") == scene_id
                    and spans_contained(
                        ranges,
                        unit_ranges.get(str(unit.get("plan_unit_id")), []),
                    )
                }
                candidate_indices = (
                    containing
                    if candidate_indices is None
                    else candidate_indices & containing
                )
            if not candidate_indices:
                result.error(
                    "PERFORMANCE_CHAIN_PLAN_COVERAGE",
                    step_path,
                    "每个表演链步骤必须完整落入至少一个规划单元。",
                )
            else:
                step_unit_indices.append(min(candidate_indices))
        ranks = [fact_order[fact_id] for fact_id in ordered_facts if fact_id in fact_order]
        if ranks != sorted(ranks) or len(ranks) != len(set(ranks)):
            result.error(
                "PERFORMANCE_CHAIN_ORDER",
                f"{path}.steps",
                "表演链 facts 必须按来源叙事顺序严格递增且不重复。",
            )
        if step_unit_indices and step_unit_indices != sorted(step_unit_indices):
            result.error(
                "PERFORMANCE_CHAIN_PLAN_ORDER",
                f"{path}.steps",
                "表演链在规划单元中的承载顺序不得倒序。",
            )
        boundaries = {
            boundary
            for left_index, right_index in zip(
                step_unit_indices,
                step_unit_indices[1:],
            )
            if right_index > left_index
            for boundary in range(left_index, right_index)
        }
        required_boundaries[chain_id] = boundaries
        for boundary in boundaries:
            if chain_id not in boundary_breaks.get(boundary, set()):
                result.error(
                    "PERFORMANCE_CHAIN_BREAK_UNDECLARED",
                    f"$.shot_plan.edit_points[{boundary}].broken_performance_chain_ids",
                    f"{chain_id} 被规划剪切点切断但未明确登记。",
                )
    for boundary, declared_chain_ids in boundary_breaks.items():
        for chain_id in declared_chain_ids:
            if chain_id not in lookup:
                result.error(
                    "PERFORMANCE_CHAIN_BREAK_UNKNOWN",
                    f"$.shot_plan.edit_points[{boundary}].broken_performance_chain_ids",
                    f"引用了不存在的表演链 `{chain_id}`。",
                )
            elif boundary not in required_boundaries.get(chain_id, set()):
                result.error(
                    "PERFORMANCE_CHAIN_BREAK_UNUSED",
                    f"$.shot_plan.edit_points[{boundary}].broken_performance_chain_ids",
                    f"{chain_id} 未在该边界发生真实链断点。",
                )
    return lookup


def shot_phase_ids(shot: dict[str, Any]) -> set[str]:
    return {
        clean_text(phase.get("phase_id"))
        for phase in as_list(shot.get("shot_phases"))
        if isinstance(phase, dict) and clean_text(phase.get("phase_id"))
    }


def validate_shot_phases(
    shot: dict[str, Any],
    *,
    path: str,
    screen_events: dict[str, dict[str, Any]],
    planned_screen_event_ids: list[str],
    result: ValidationResult,
) -> int | None:
    duration = shot.get("duration_seconds")
    if not is_json_integer(duration, 1):
        result.error("DURATION", f"{path}.duration_seconds", "必须是正 JSON 整数。")
        return None
    phases = shot.get("shot_phases")
    if not isinstance(phases, list) or not phases:
        result.error(
            "SHOT_PHASES_REQUIRED",
            f"{path}.shot_phases",
            "2.5.2 每个镜头都必须用有序 shot_phases 说明真实观看进程。",
        )
        return int(duration)
    seen_phase_ids: set[str] = set()
    flattened_events: list[str] = []
    total = 0
    event_phase: dict[str, int] = {}
    for index, phase in enumerate(phases):
        phase_path = f"{path}.shot_phases[{index}]"
        if not isinstance(phase, dict):
            result.error("SHOT_PHASE", phase_path, "镜头阶段必须是对象。")
            continue
        validate_exact_fields(
            phase,
            expected=SHOT_PHASE_KEYS,
            path=phase_path,
            code_prefix="SHOT_PHASE",
            result=result,
        )
        phase_id = require_nonempty_string(
            phase.get("phase_id"),
            path=f"{phase_path}.phase_id",
            result=result,
        )
        if phase_id in seen_phase_ids:
            result.error("SHOT_PHASE_ID", f"{phase_path}.phase_id", "phase_id 重复。")
        seen_phase_ids.add(phase_id)
        if phase.get("phase_order") != index + 1:
            result.error(
                "SHOT_PHASE_ORDER",
                f"{phase_path}.phase_order",
                "shot_phases[] 必须按从 1 开始的 phase_order 排列。",
            )
        phase_duration = phase.get("duration_seconds")
        if not is_json_integer(phase_duration, 1):
            result.error(
                "SHOT_PHASE_DURATION",
                f"{phase_path}.duration_seconds",
                "阶段时长必须是正 JSON 整数。",
            )
        else:
            total += int(phase_duration)
        require_nonempty_string(
            phase.get("camera_state"),
            path=f"{phase_path}.camera_state",
            result=result,
        )
        event_ids = list_of_unique_strings(
            phase.get("screen_event_ids"),
            path=f"{phase_path}.screen_event_ids",
            result=result,
            allow_empty=False,
        )
        flattened_events.extend(event_ids)
        for event_id in event_ids:
            if event_id in event_phase:
                result.error(
                    "SHOT_PHASE_EVENT_DUPLICATE",
                    f"{phase_path}.screen_event_ids",
                    "同一屏幕事件只能属于一个镜头阶段。",
                )
            event_phase[event_id] = index
        list_of_unique_strings(
            phase.get("sound_fact_ids"),
            path=f"{phase_path}.sound_fact_ids",
            result=result,
            allow_empty=True,
        )
    if flattened_events != planned_screen_event_ids:
        result.error(
            "SHOT_PHASE_EVENT_COVERAGE",
            f"{path}.shot_phases",
            "阶段必须按顺序恰好覆盖规划单元的 screen_event_ids。",
        )
    event_orders = [
        screen_events[event_id].get("event_order")
        for event_id in flattened_events
        if event_id in screen_events
        and is_json_integer(screen_events[event_id].get("event_order"), 1)
    ]
    if event_orders != sorted(event_orders):
        result.error(
            "SHOT_PHASE_EVENT_ORDER",
            f"{path}.shot_phases",
            "shot_phases 必须保持该场 screen_event.event_order；不能通过同步倒置规划单元和阶段列表绕过时间顺序。",
        )
    for previous_id, current_id in zip(planned_screen_event_ids, planned_screen_event_ids[1:]):
        current = screen_events.get(current_id, {})
        if (
            current.get("temporal_relation") == "sequential"
            and event_phase.get(previous_id) == event_phase.get(current_id)
        ):
            result.error(
                "SHOT_PHASE_SEQUENTIAL_COLLAPSE",
                f"{path}.shot_phases",
                "明确顺序发生的屏幕事件不能全部塞入同一同步阶段。",
            )
    if duration != total:
        result.error(
            "SHOT_PHASE_DURATION_SUM",
            f"{path}.duration_seconds",
            f"必须等于 shot_phases 阶段时长之和 {total}。",
        )
    return total


def validate_duration_blocks(shot: dict[str, Any], path: str, result: ValidationResult) -> int | None:
    blocks = shot.get("duration_blocks")
    duration = shot.get("duration_seconds")
    if not is_json_integer(duration, 1):
        result.error("DURATION", f"{path}.duration_seconds", "必须是正 JSON 整数。")
        return None
    if not isinstance(blocks, list) or not blocks:
        result.error(
            "DURATION_BLOCKS_REQUIRED",
            f"{path}.duration_blocks",
            "旧 duration_blocks 已由 2.5.2 shot_phases 替代。",
        )
        return duration
    if len(blocks) > len(TIMING_LABELS):
        result.error(
            "DURATION_BLOCK_COUNT",
            f"{path}.duration_blocks",
            "标准时间模型最多包含同步段、非同步后续动作段和情绪停留段各一个。",
        )
    block_ids: set[str] = set()
    labels: list[str] = []
    for index, block in enumerate(blocks):
        block_path = f"{path}.duration_blocks[{index}]"
        if not isinstance(block, dict):
            result.error("DURATION_BLOCK", block_path, "时间块必须是对象。")
            labels.append("")
            continue
        block_id = require_nonempty_string(
            block.get("block_id"),
            path=f"{block_path}.block_id",
            result=result,
        )
        if block_id in block_ids:
            result.error("DURATION_BLOCK_ID", f"{block_path}.block_id", "block_id 重复。")
        block_ids.add(block_id)
        label = require_nonempty_string(
            block.get("label"),
            path=f"{block_path}.label",
            result=result,
        )
        labels.append(label)
        if label not in TIMING_LABELS:
            result.error(
                "DURATION_BLOCK_LABEL",
                f"{block_path}.label",
                f"必须使用标准标签之一：{'、'.join(TIMING_LABELS)}。",
            )
        for channel in DURATION_CHANNELS:
            value = block.get(channel)
            if not is_json_integer(value, 0):
                result.error(
                    "DURATION_CHANNEL",
                    f"{block_path}.{channel}",
                    "必须是非负 JSON 整数，不接受 bool、小数或字符串。",
                )
    if labels:
        if labels[0] != TIMING_SYNC_LABEL:
            result.error(
                "DURATION_BLOCK_ORDER",
                f"{path}.duration_blocks[0].label",
                "首个时间块必须是同步动作、台词与运镜。",
            )
        expected_order = [label for label in TIMING_LABELS if label in labels]
        if labels != expected_order or len(labels) != len(set(labels)):
            result.error(
                "DURATION_BLOCK_ORDER",
                f"{path}.duration_blocks",
                "时间块必须按同步段、可选非同步动作段、可选情绪停留段排列，且不得重复。",
            )

    by_label = {
        clean_text(block.get("label")): block
        for block in blocks
        if isinstance(block, dict)
    }
    sync = by_label.get(TIMING_SYNC_LABEL)
    if not isinstance(sync, dict):
        result.error(
            "DURATION_SYNC_REQUIRED",
            f"{path}.duration_blocks",
            "缺少必需的同步动作、台词与运镜时间块。",
        )
    else:
        sync_action = duration_channel_value(sync, "action_seconds")
        sync_dialogue = duration_channel_value(sync, "dialogue_seconds")
        sync_parallel = max(sync_action, sync_dialogue)
        if sync_parallel <= 0:
            result.error(
                "DURATION_BLOCK_EMPTY",
                f"{path}.duration_blocks[{labels.index(TIMING_SYNC_LABEL)}]",
                "同步段的动作或台词至少一项必须大于零。",
            )
        for channel in ("performance_seconds", "camera_seconds"):
            if duration_channel_value(sync, channel) > sync_parallel:
                result.error(
                    "DURATION_PARALLEL_OVERFLOW",
                    f"{path}.duration_blocks[{labels.index(TIMING_SYNC_LABEL)}].{channel}",
                    "同步表演或运镜不得比动作与台词的并行主段更长。",
                )

    asynchronous = by_label.get(TIMING_ASYNC_LABEL)
    if isinstance(asynchronous, dict):
        async_index = labels.index(TIMING_ASYNC_LABEL)
        async_action = duration_channel_value(asynchronous, "action_seconds")
        if async_action <= 0:
            result.error(
                "DURATION_BLOCK_EMPTY",
                f"{path}.duration_blocks[{async_index}]",
                "非同步后续动作段必须有正动作时长。",
            )
        for channel in ("dialogue_seconds", "performance_seconds"):
            if duration_channel_value(asynchronous, channel) != 0:
                result.error(
                    "DURATION_ASYNC_CHANNEL",
                    f"{path}.duration_blocks[{async_index}].{channel}",
                    "非同步后续动作段只记录动作和与动作同步的运镜。",
                )
        if (
            duration_channel_value(asynchronous, "camera_seconds")
            > async_action
        ):
            result.error(
                "DURATION_PARALLEL_OVERFLOW",
                f"{path}.duration_blocks[{async_index}].camera_seconds",
                "后续运镜不得比其承载的非同步动作更长。",
            )

    hold = by_label.get(TIMING_HOLD_LABEL)
    if isinstance(hold, dict):
        hold_index = labels.index(TIMING_HOLD_LABEL)
        hold_performance = duration_channel_value(hold, "performance_seconds")
        if hold_performance <= 0:
            result.error(
                "DURATION_BLOCK_EMPTY",
                f"{path}.duration_blocks[{hold_index}]",
                "情绪与观看停留段必须有正表演停留时长。",
            )
        for channel in ("action_seconds", "dialogue_seconds", "camera_seconds"):
            if duration_channel_value(hold, channel) != 0:
                result.error(
                    "DURATION_HOLD_CHANNEL",
                    f"{path}.duration_blocks[{hold_index}].{channel}",
                    "情绪与观看停留段只记录表演停留时长。",
                )

    action, dialogue, asynchronous_seconds, hold_seconds = timing_components(shot)
    total = max(action, dialogue) + asynchronous_seconds + hold_seconds
    if duration != total:
        result.error(
            "DURATION_FORMULA",
            f"{path}.duration_seconds",
            f"必须等于 max(同步动作, 同步台词) + 非同步动作 + 情绪留白，即 {total}。",
        )
    movement = clean_text(as_dict(shot.get("camera")).get("movement"))
    has_camera_move = any(
        token in movement
        for token in (
            "推进",
            "推近",
            "拉远",
            "拉出",
            "横移",
            "纵移",
            "跟随",
            "跟拍",
            "摇摄",
            "上摇",
            "下摇",
            "升起",
            "下降",
            "环绕",
            "移焦",
        )
    )
    ends_fixed = any(token in movement for token in ("固定", "停住", "锁定"))
    camera_seconds = sum(
        duration_channel_value(block, "camera_seconds")
        for block in blocks
        if isinstance(block, dict)
    )
    if has_camera_move and ends_fixed and camera_seconds <= 0:
        result.error(
            "DURATION_CAMERA_MOVE_ZERO",
            f"{path}.duration_blocks",
            "先运动后固定的镜头必须为实际摄影机运动记录大于 0 的 camera_seconds。",
        )
    return total


def validate_camera(
    camera: Any,
    path: str,
    result: ValidationResult,
    *,
    scene_characters: set[str] | None = None,
) -> None:
    if not isinstance(camera, dict):
        result.error("CAMERA", path, "camera 必须是对象。")
        return
    required_keys = {
        "shot_size",
        "angle",
        "position",
        "logic",
        "composition",
        "movement",
    }
    optional_keys = {
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
        "framing_mode",
        "foreground_characters",
    }
    validate_required_optional_fields(
        camera,
        required=required_keys,
        optional=optional_keys,
        path=path,
        code_prefix="CAMERA",
        result=result,
    )
    for key in required_keys | (
        optional_keys
        - {
            "primary_subjects",
            "secondary_subjects",
            "spatial_strategy",
            "movement_plan",
            "framing_mode",
            "foreground_characters",
        }
    ):
        if key not in camera:
            continue
        value = require_nonempty_string(
            camera.get(key),
            path=f"{path}.{key}",
            result=result,
        )
        if VISIBLE_MACHINE_STATE_PATTERN.search(value):
            result.error(
                "VISIBLE_MACHINE_STATE",
                f"{path}.{key}",
                "用户可见摄影字段不得包含内部机器状态 ID。",
            )
    if (
        "perspective_intent" in camera
        and camera.get("perspective_intent") not in PERSPECTIVE_INTENTS
    ):
        result.error(
            "CAMERA_PERSPECTIVE_INTENT",
            f"{path}.perspective_intent",
            "perspective_intent 无效。",
        )
    spatial_strategy = camera.get("spatial_strategy")
    if "spatial_strategy" in camera and not isinstance(spatial_strategy, dict):
        result.error(
            "CAMERA_SPATIAL_STRATEGY",
            f"{path}.spatial_strategy",
            "spatial_strategy 必须是对象。",
        )
    elif isinstance(spatial_strategy, dict):
        validate_exact_fields(
            spatial_strategy,
            expected=SPATIAL_STRATEGY_KEYS,
            path=f"{path}.spatial_strategy",
            code_prefix="CAMERA_SPATIAL_STRATEGY",
            result=result,
        )
    movement_plan = camera.get("movement_plan")
    if "movement_plan" in camera and not isinstance(movement_plan, dict):
        result.error(
            "CAMERA_MOVEMENT_PLAN",
            f"{path}.movement_plan",
            "movement_plan 必须是对象。",
        )
    elif isinstance(movement_plan, dict):
        validate_exact_fields(
            movement_plan,
            expected=MOVEMENT_PLAN_KEYS,
            path=f"{path}.movement_plan",
            code_prefix="CAMERA_MOVEMENT_PLAN",
            result=result,
        )
    framing_mode = camera.get("framing_mode")
    if framing_mode is not None and framing_mode not in FRAMING_MODES:
        result.error(
            "CAMERA_FRAMING_MODE",
            f"{path}.framing_mode",
            "framing_mode 无效。",
        )
    primary_subjects: set[str] = set()
    secondary_subjects: set[str] = set()
    foreground: set[str] = set()
    if "primary_subjects" in camera:
        primary_subjects = set(
            list_of_unique_strings(
                camera.get("primary_subjects"),
                path=f"{path}.primary_subjects",
                result=result,
                allow_empty=framing_mode in {"insert", "environment"},
            )
        )
    if "secondary_subjects" in camera:
        secondary_subjects = set(
            list_of_unique_strings(
                camera.get("secondary_subjects"),
                path=f"{path}.secondary_subjects",
                result=result,
                allow_empty=True,
            )
        )
    if "foreground_characters" in camera:
        foreground = set(
            list_of_unique_strings(
                camera.get("foreground_characters"),
                path=f"{path}.foreground_characters",
                result=result,
                allow_empty=True,
            )
        )
    if scene_characters:
        for character in primary_subjects | secondary_subjects | foreground:
            if character not in scene_characters:
                result.error(
                    "CAMERA_SUBJECT",
                    path,
                    f"摄影机人物 `{character}` 不在已登记场景人物中。",
                )
    if primary_subjects & foreground:
        result.error(
            "CAMERA_SUBJECT",
            path,
            "同一人物不能同时是主拍主体和前景肩背。",
        )
    if primary_subjects & secondary_subjects:
        result.error(
            "CAMERA_SUBJECT",
            path,
            "同一主体不能同时登记为 primary_subjects 与 secondary_subjects。",
        )
    if framing_mode == "over_shoulder":
        position = clean_text(camera.get("position"))
        if not foreground or not position:
            result.error(
                "CAMERA_POSITION_FRAMING_MISMATCH",
                path,
                "明确使用过肩镜头时，必须说明前景人物和摄影机位置。",
            )
        for character in foreground:
            if character not in position or not any(
                token in position for token in ("肩后", "肩侧", "肩旁", "过肩")
            ):
                result.error(
                    "CAMERA_POSITION_FRAMING_MISMATCH",
                    f"{path}.position",
                    "明确使用过肩镜头时，机位必须与已登记前景人物一致。",
                )
    movement = clean_text(camera.get("movement"))
    logic = clean_text(camera.get("logic"))
    if camera_movement_class(movement) == "fixed" and any(
        token in logic for token in ("推进", "拉出", "横移", "跟随", "环绕", "摇摄")
    ):
        result.error(
            "CAMERA_LOGIC_CONTRADICTION",
            f"{path}.logic",
            "明确的固定机位与移动观察互相矛盾。",
        )
    for key in (
        "shot_size",
        "angle",
        "position",
        "composition",
        "movement",
        "logic",
    ):
        value = require_nonempty_string(camera.get(key), path=f"{path}.{key}", result=result)
        for phrase in PLACEHOLDER_PHRASES:
            if phrase in value:
                result.error(
                    "TEMPLATE_PLACEHOLDER",
                    f"{path}.{key}",
                    f"检测到模板占位语：{phrase}。",
                )
        if VISIBLE_MACHINE_STATE_PATTERN.search(value):
            result.error(
                "VISIBLE_MACHINE_STATE",
                f"{path}.{key}",
                "用户可见摄影字段不得包含规划单元、转场、时间块、轴线或其他机器状态 ID。",
            )
    for key in ("start_frame", "end_frame"):
        if key not in camera:
            continue
        value = require_nonempty_string(camera.get(key), path=f"{path}.{key}", result=result)
        for phrase in PLACEHOLDER_PHRASES:
            if phrase in value:
                result.error(
                    "TEMPLATE_PLACEHOLDER",
                    f"{path}.{key}",
                    f"检测到模板占位语：{phrase}。",
                )
    framing_mode = camera.get("framing_mode")
    if framing_mode is not None and framing_mode not in FRAMING_MODES:
        result.error("DIALOGUE_PLAN_CAMERA_MISMATCH", f"{path}.framing_mode", "framing_mode 无效。")
    angle = clean_text(camera.get("angle"))
    if any(token in angle for token in ("肩后", "过肩", "肩背")) or any(
        character and character in angle for character in (scene_characters or set())
    ):
        result.error(
            "CAMERA_ANGLE_ROLE_CONFLICT",
            f"{path}.angle",
            "angle 只写视角与高度；人物肩位、主体关系应写入 framing_mode、position 和 logic。",
        )
    if (
        not PURE_CAMERA_ANGLE_PATTERN.fullmatch(angle)
        or any(token in angle for token in CAMERA_ANGLE_CONTAMINATION_TERMS)
    ):
        result.error(
            "CAMERA_ANGLE_PURITY",
            f"{path}.angle",
            "angle 只能写纯摄影机高度与俯仰关系；地点、焦段、距离、主体朝向和主客观关系应写入其他 camera 字段。",
        )
    shot_size = clean_text(camera.get("shot_size"))
    if not PURE_SHOT_SIZE_PATTERN.fullmatch(shot_size):
        result.error(
            "CAMERA_SHOT_SIZE_PURITY",
            f"{path}.shot_size",
            "shot_size 只能写纯景别，或用“→”连接合法景别变化；构图身份、人物、地点和主体关系应写入其他 camera 字段。",
        )
    movement = clean_text(camera.get("movement"))
    if any(
        token in movement
        for token in (
            "肩后拍",
            "过肩拍",
            "正脸主位",
            "前景肩背",
            *CAMERA_MOVEMENT_CONTENT_TERMS,
        )
    ) or any(
        character and character in movement for character in (scene_characters or set())
    ):
        result.error(
            "CAMERA_MOVEMENT_ROLE_CONFLICT",
            f"{path}.movement",
            "movement 只写摄影机运动、焦点或固定状态，不得混入人物、构图、事件结果或说话者覆盖。",
        )
    if (
        CAMERA_MOVEMENT_PUNCTUATION_PATTERN.search(movement)
        or not any(token in movement for token in CAMERA_MOVEMENT_ACTION_TERMS)
    ):
        result.error(
            "CAMERA_MOVEMENT_PURITY",
            f"{path}.movement",
            "movement 只能写纯摄影机行为及必要的速度、方向或承载平台，不得用标点追加画面结果、曝光、对焦结果或执行提醒。",
        )
    logic = clean_text(camera.get("logic"))
    position = clean_text(camera.get("position"))
    composition = clean_text(camera.get("composition"))
    normalized_logic = re.sub(r"\s+", "", logic)
    normalized_position = re.sub(r"\s+", "", position)
    normalized_composition = re.sub(r"\s+", "", composition)
    if (
        position
        and normalized_position == normalized_logic
    ) or (
        composition
        and normalized_composition in normalized_logic
    ):
        result.error(
            "CAMERA_LOGIC_DUPLICATION",
            f"{path}.logic",
            "logic 只写观察方向与必要的自然语言轴线关系，不得复制 position 或 composition。",
        )
    if any(term in logic for term in CAMERA_LOGIC_ANALYSIS_TERMS):
        result.error(
            "CAMERA_LOGIC_NON_GEOMETRIC",
            f"{path}.logic",
            "机位逻辑不得写导演目的、叙事收益或构图解释；只写观察方向与必要的自然语言轴线关系。",
        )
    triad_values = [
        clean_text(camera.get("angle")),
        clean_text(camera.get("shot_size")),
        clean_text(camera.get("movement")),
    ]
    if all(value and value in logic for value in triad_values):
        result.error(
            "CAMERA_LOGIC_DUPLICATION",
            f"{path}.logic",
            "机位逻辑不得复述完整镜头三要素，应只解释观察位置、轴线与主体可读性。",
        )
    static_motion = camera_movement_class(movement) == "fixed"
    moving_motion = any(token in logic for token in ("推进", "拉出", "横移", "跟随", "环绕", "摇"))
    if static_motion and moving_motion:
        result.error(
            "CAMERA_LOGIC_CONTRADICTION",
            f"{path}.logic",
            "机位逻辑与 movement 的静止／运动状态冲突。",
        )
    if framing_mode == "over_shoulder":
        if not foreground:
            result.error(
                "DIALOGUE_PLAN_CAMERA_MISMATCH",
                f"{path}.foreground_characters",
                "过肩镜头必须登记前景肩背人物。",
            )
        shoulder_tokens = ("肩后", "肩侧", "肩旁")
        for character in foreground:
            if character not in position or not any(token in position for token in shoulder_tokens):
                result.error(
                    "CAMERA_POSITION_FRAMING_MISMATCH",
                    f"{path}.position",
                    "过肩镜头的 position 必须写明前景人物及摄影机位于其肩后、肩侧或肩旁。",
                )
        if primary_subjects and not any(
            character in composition or character in logic for character in primary_subjects
        ):
            result.error(
                "CAMERA_POSITION_FRAMING_MISMATCH",
                f"{path}.composition",
                "过肩镜头必须在 composition 或 logic 中明确被观察的主拍主体。",
            )
    if framing_mode in {"insert", "environment"} and any(
        token in position for token in ("肩后", "肩侧", "肩旁", "过肩")
    ):
        result.error(
            "CAMERA_POSITION_FRAMING_MISMATCH",
            f"{path}.position",
            "插入镜头或环境镜头不得使用人物过肩位置。",
        )
    vertical_geometry = position + logic
    if (
        "俯视" in angle or "顶视" in angle or angle == "高位平视"
    ) and not any(
        token in vertical_geometry for token in ("上方", "高处", "向下", "俯看", "顶部", "顶端")
    ):
        result.error(
            "CAMERA_ANGLE_POSITION_MISMATCH",
            f"{path}.position",
            "俯视或高位镜头必须在 position / logic 中写明摄影机位于上方或向下观察。",
        )
    if (
        "仰视" in angle or angle == "低位平视"
    ) and not any(
        token in vertical_geometry for token in ("下方", "低处", "向上", "仰看", "脚边", "枕位", "地面")
    ):
        result.error(
            "CAMERA_ANGLE_POSITION_MISMATCH",
            f"{path}.position",
            "仰视或低位镜头必须在 position / logic 中写明摄影机位于下方或向上观察。",
        )
    if angle in {"平视", "眼平高度平视"} and any(
        token in vertical_geometry for token in ("向下观察", "向下看", "俯看", "垂直向下")
    ):
        result.error(
            "CAMERA_ANGLE_POSITION_MISMATCH",
            f"{path}.angle",
            "position / logic 已明确向下观察，不能仍使用普通平视。",
        )
    if angle in {"平视", "眼平高度平视"} and any(
        token in vertical_geometry for token in ("向上观察", "向上看", "仰看", "贴地朝上")
    ):
        result.error(
            "CAMERA_ANGLE_POSITION_MISMATCH",
            f"{path}.angle",
            "position / logic 已明确向上观察，不能仍使用普通平视。",
        )


def validate_blocking(
    blocking: Any,
    *,
    path: str,
    scene_characters: set[str],
    visible_characters: set[str],
    result: ValidationResult,
) -> None:
    if blocking is None:
        return
    if not isinstance(blocking, list):
        result.error("BLOCKING", path, "blocking 必须是数组。")
        return
    for index, item in enumerate(blocking):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            result.error("BLOCKING_ITEM", item_path, "调度必须是对象。")
            continue
        character = require_nonempty_string(
            item.get("character"),
            path=f"{item_path}.character",
            result=result,
        )
        if character and character not in scene_characters:
            result.error("BLOCKING_CHARACTER", f"{item_path}.character", "人物不在场景台账。")
        if character and character not in visible_characters:
            result.error("BLOCKING_VISIBILITY", f"{item_path}.character", "有画面调度的人物必须可见。")
        for key in ("start_position", "action", "end_position", "facing", "eyeline"):
            require_nonempty_string(item.get(key), path=f"{item_path}.{key}", result=result)
        action = clean_text(item.get("action"))
        facing = clean_text(item.get("facing"))
        eyeline = clean_text(item.get("eyeline"))
        direction_targets: list[str] = []
        for pattern in (
            r"走向([^，。；]+)",
            r"朝([^，。；]+?)(?:走去|走|前行|靠近)",
            r"(?:看向|望向|转向)([^，。；]+)",
        ):
            direction_targets.extend(
                clean_text(match)
                for match in re.findall(pattern, action)
                if clean_text(match)
            )
        for target in direction_targets:
            normalized_target = re.sub(r"\s+", "", target)
            normalized_facing = re.sub(r"\s+", "", facing)
            normalized_eyeline = re.sub(r"\s+", "", eyeline)
            if not any(
                left and right and (left in right or right in left)
                for left, right in (
                    (normalized_target, normalized_facing),
                    (normalized_target, normalized_eyeline),
                )
            ):
                result.error(
                    "BLOCKING_DIRECTION_CONTRADICTION",
                    f"{item_path}.facing",
                    f"动作明确指向 `{target}`，但 facing / eyeline 未兑现该方向。",
                )


def validate_performance(
    performance: Any,
    *,
    path: str,
    emotion_arcs: dict[str, dict[str, Any]],
    result: ValidationResult,
) -> None:
    if performance is None:
        return
    if not isinstance(performance, dict):
        result.error("PERFORMANCE", path, "performance 必须是对象。")
        return
    arc_id = performance.get("emotion_arc_id")
    if arc_id is not None and arc_id not in emotion_arcs:
        result.error("PERFORMANCE_ARC", f"{path}.emotion_arc_id", "引用的 emotion arc 不存在。")
    phase = performance.get("phase")
    if phase is not None and phase not in PERFORMANCE_PHASES:
        result.error("PERFORMANCE_PHASE", f"{path}.phase", "不是允许阶段。")
    intent = require_string(performance.get("emotion_intent"), path=f"{path}.emotion_intent", result=result)
    visible = list_of_unique_strings(
        performance.get("visible_behavior"),
        path=f"{path}.visible_behavior",
        result=result,
        allow_empty=True,
    )
    if intent.strip() and not visible:
        result.error(
            "PERFORMANCE_VISIBLE",
            f"{path}.visible_behavior",
            "有 emotion_intent 时必须提供可见表演行为。",
        )
    if phase not in {None, "not_applicable"} and not intent.strip():
        result.error("PERFORMANCE_INTENT", f"{path}.emotion_intent", "有表演阶段时必须写情绪意图。")


def validate_dialogue(
    dialogue: Any,
    *,
    path: str,
    fact_lookup: dict[str, dict[str, Any]],
    covered_fact_ids: set[str],
    scene_characters: set[str],
    visible_characters: set[str],
    phase_ids: set[str],
    result: ValidationResult,
) -> None:
    if not isinstance(dialogue, list):
        result.error("DIALOGUE", path, "dialogue 必须是数组。")
        return
    represented: list[str] = []
    for index, item in enumerate(dialogue):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            result.error("DIALOGUE_ITEM", item_path, "对白必须是对象。")
            continue
        reject_director_analysis_in_fact_or_dialogue(
            item,
            path=item_path,
            result=result,
        )
        fact_id = require_nonempty_string(item.get("fact_id"), path=f"{item_path}.fact_id", result=result)
        fact = fact_lookup.get(fact_id)
        if not fact or fact.get("type") != "dialogue":
            result.error("DIALOGUE_FACT", f"{item_path}.fact_id", "必须引用 dialogue fact。")
        else:
            represented.append(fact_id)
            if fact_id not in covered_fact_ids:
                result.error("DIALOGUE_COVERAGE", f"{item_path}.fact_id", "对白 fact 未由本镜覆盖。")
            if item.get("text") != fact.get("text"):
                result.error("DIALOGUE_TEXT", f"{item_path}.text", "台词必须与 dialogue fact 逐字一致。")
            if item.get("speaker") != fact.get("speaker"):
                result.error("DIALOGUE_SPEAKER", f"{item_path}.speaker", "说话者与 fact 不一致。")
            source_voice = fact.get("script_voice_type")
            shot_delivery = item.get("shot_delivery")
            if source_voice == "vo" and shot_delivery != "vo":
                result.error(
                    "DIALOGUE_VOICE_IDENTITY",
                    f"{item_path}.shot_delivery",
                    "来源 VO 不能改成现场对白或 O.S.。",
                )
            if source_voice == "scene_dialogue" and shot_delivery == "vo":
                result.error(
                    "DIALOGUE_VOICE_IDENTITY",
                    f"{item_path}.shot_delivery",
                    "来源现场对白不能改写成 VO。",
                )
            if source_voice == "os" and shot_delivery not in {"os", "onscreen"}:
                result.error(
                    "DIALOGUE_VOICE_IDENTITY",
                    f"{item_path}.shot_delivery",
                    "来源 OS 不能改写成 VO 或媒介声音。",
                )
        speaker = item.get("speaker")
        if scene_characters and speaker not in scene_characters:
            result.error("DIALOGUE_SPEAKER", f"{item_path}.speaker", "说话者不在场景台账。")
        delivery = item.get("shot_delivery")
        if delivery not in SHOT_DELIVERIES:
            result.error("SHOT_DELIVERY", f"{item_path}.shot_delivery", "shot_delivery 无效。")
        elif (
            delivery == "onscreen"
            and visible_characters
            and speaker not in visible_characters
        ):
            result.error("DIALOGUE_VISIBILITY", f"{item_path}.speaker", "onscreen 说话者必须可见。")
        timing = ""
        if "timing" in item:
            timing = require_nonempty_string(
                item.get("timing"),
                path=f"{item_path}.timing",
                result=result,
            )
        if timing and phase_ids and timing not in phase_ids:
            result.error("DIALOGUE_TIMING", f"{item_path}.timing", "必须引用本镜 phase_id。")
        addressee = require_string(
            item.get("addressee", ""),
            path=f"{item_path}.addressee",
            result=result,
        )
        if addressee:
            if scene_characters and addressee not in scene_characters:
                result.error(
                    "DIALOGUE_ADDRESSEE",
                    f"{item_path}.addressee",
                    "对白收话对象必须属于当前场景人物台账。",
                )
            if addressee == speaker:
                result.error(
                    "DIALOGUE_ADDRESSEE",
                    f"{item_path}.addressee",
                    "对白收话对象不得与说话者相同。",
                )
    expected = {
        fact_id
        for fact_id in covered_fact_ids
        if fact_lookup.get(fact_id, {}).get("type") == "dialogue"
    }
    if set(represented) != expected:
        result.error("DIALOGUE_COVERAGE", path, "covered dialogue facts 与 dialogue[] 必须一一对应。")
    if len(represented) != len(set(represented)):
        result.error("DIALOGUE_DUPLICATE", path, "同一 dialogue fact 不得重复。")


def validate_speaker_presentation(
    value: Any,
    *,
    path: str,
    dialogue: list[Any],
    camera: dict[str, Any],
    dialogue_design: Any,
    result: ValidationResult,
) -> None:
    if value is None:
        if dialogue:
            result.error(
                "DIALOGUE_PLAN_CAMERA_MISMATCH",
                path,
                "有对白时必须逐条登记 speaker_presentation。",
            )
        return
    if not isinstance(value, list):
        result.error("DIALOGUE_PLAN_CAMERA_MISMATCH", path, "speaker_presentation 必须是数组。")
        return
    presentations: dict[str, str] = {}
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            result.error("DIALOGUE_PLAN_CAMERA_MISMATCH", item_path, "说话者呈现必须是对象。")
            continue
        validate_exact_fields(
            item,
            expected={"fact_id", "speaker", "presentation"},
            path=item_path,
            code_prefix="SPEAKER_PRESENTATION",
            result=result,
        )
        fact_id = require_nonempty_string(item.get("fact_id"), path=f"{item_path}.fact_id", result=result)
        require_nonempty_string(item.get("speaker"), path=f"{item_path}.speaker", result=result)
        presentation = item.get("presentation")
        if presentation not in SPEAKER_PRESENTATIONS:
            result.error("DIALOGUE_PLAN_CAMERA_MISMATCH", f"{item_path}.presentation", "说话者呈现类型无效。")
        if fact_id in presentations:
            result.error("DIALOGUE_PLAN_CAMERA_MISMATCH", item_path, "同一对白 fact 只能登记一次呈现。")
        presentations[fact_id] = str(presentation)
    primary_subjects = set(as_list(camera.get("primary_subjects")))
    foreground = set(as_list(camera.get("foreground_characters")))
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        fact_id = clean_text(item.get("fact_id"))
        speaker = clean_text(item.get("speaker"))
        delivery = item.get("shot_delivery")
        presentation = presentations.get(fact_id)
        if presentation is None:
            result.error(
                "DIALOGUE_PLAN_CAMERA_MISMATCH",
                path,
                f"对白 `{fact_id}` 缺少 speaker_presentation。",
            )
            continue
        if delivery == "onscreen" and presentation in {"not_visible", "mediated_source"}:
            result.error(
                "DIALOGUE_PLAN_CAMERA_MISMATCH",
                path,
                "onscreen 说话者必须在画面中呈现，但不要求正脸可读。",
            )
        if presentation in {"primary_face", "shared_face"} and speaker not in primary_subjects:
            result.error(
                "DIALOGUE_PLAN_CAMERA_MISMATCH",
                path,
                f"{speaker} 被声明为面孔可读，但未列入 camera.primary_subjects。",
            )
        if presentation == "foreground_back" and speaker not in foreground:
            result.error(
                "DIALOGUE_FOREGROUND_SPEAKER",
                path,
                f"{speaker} 被声明为前景肩背，但未列入 camera.foreground_characters。",
            )
        if delivery in {"os", "vo"} and presentation != "not_visible":
            result.error(
                "DIALOGUE_PLAN_CAMERA_MISMATCH",
                path,
                "O.S. 与 V.O. 在当前画面不可见时必须标记 not_visible。",
            )
        if delivery == "mediated" and presentation != "mediated_source":
            result.error(
                "DIALOGUE_PLAN_CAMERA_MISMATCH",
                path,
                "媒介声音必须标记 mediated_source。",
            )
    design = as_dict(dialogue_design)
    face_readable = set(as_list(design.get("face_readable_speakers")))
    if face_readable:
        presented_speakers = {
            clean_text(item.get("speaker"))
            for item in dialogue
            if isinstance(item, dict)
            and presentations.get(clean_text(item.get("fact_id"))) in {"primary_face", "shared_face"}
        }
        if not face_readable.issubset(presented_speakers):
            result.error(
                "DIALOGUE_SHARED_FRAME_UNREADABLE",
                path,
                "规划中明确要求面孔可读的人物未在终稿中兑现。",
            )


def execution_support_corpus(
    shot: dict[str, Any],
    *,
    fact_lookup: dict[str, dict[str, Any]],
    emotion_arcs: dict[str, dict[str, Any]],
    performance_chains: list[Any],
) -> str:
    support: list[str] = []
    covered_fact_ids = set(as_list(shot.get("covered_fact_ids")))
    for fact_id in covered_fact_ids:
        fact = fact_lookup.get(str(fact_id))
        if fact:
            support.append(clean_text(fact.get("text")))
    performance = as_dict(shot.get("performance"))
    support.extend(
        clean_text(item) for item in as_list(performance.get("visible_behavior"))
    )
    arc = emotion_arcs.get(clean_text(performance.get("emotion_arc_id")), {})
    phase_name = clean_text(performance.get("phase"))
    shot_beat_ids = set(as_list(shot.get("beat_ids")))
    for phase in as_list(arc.get("phases")):
        if not isinstance(phase, dict):
            continue
        phase_matches = phase.get("phase") == phase_name
        beat_matches = bool(shot_beat_ids & set(as_list(phase.get("beat_ids"))))
        if phase_matches or beat_matches:
            support.extend(clean_text(item) for item in as_list(phase.get("visible_direction")))
    for chain in performance_chains:
        if not isinstance(chain, dict):
            continue
        chain_fact_ids = {
            clean_text(fact_id)
            for step in as_list(chain.get("steps"))
            if isinstance(step, dict)
            for fact_id in as_list(step.get("fact_ids"))
        }
        if chain_fact_ids & covered_fact_ids:
            for fact_id in chain_fact_ids & covered_fact_ids:
                fact = fact_lookup.get(fact_id)
                if fact:
                    support.append(clean_text(fact.get("text")))
    for update in as_list(shot.get("continuity_updates")):
        if not isinstance(update, dict):
            continue
        evidence_ids = set(as_list(update.get("evidence_fact_ids")))
        if evidence_ids and evidence_ids.issubset(covered_fact_ids):
            support.extend((clean_text(update.get("from")), clean_text(update.get("to"))))
    return "\n".join(item for item in support if item)


def validate_execution_passages(
    value: Any,
    *,
    path: str,
    covered_fact_ids: set[str],
    fact_lookup: dict[str, dict[str, Any]],
    coverage_evidence: list[Any],
    dialogue: list[Any],
    duration_block_ids: set[str],
    performance_chains: list[Any],
    support_corpus: str,
    global_passage_ids: set[str],
    result: ValidationResult,
) -> None:
    if not isinstance(value, list) or not value:
        result.error("EXECUTION_PASSAGE_FACT_MISMATCH", path, "每镜必须至少有一个执行段落。")
        return
    passage_fact_sets: list[set[str]] = []
    seen_ids: set[str] = set()
    seen_texts: set[str] = set()
    represented: set[str] = set()
    evidence_by_fact: dict[str, list[str]] = {}
    for evidence in coverage_evidence:
        if isinstance(evidence, dict):
            evidence_by_fact.setdefault(clean_text(evidence.get("fact_id")), []).append(
                clean_text(evidence.get("evidence_quote"))
            )
    dialogue_by_fact = {
        clean_text(item.get("fact_id")): clean_text(item.get("text"))
        for item in dialogue
        if isinstance(item, dict)
    }
    for index, passage in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(passage, dict):
            result.error("EXECUTION_PASSAGE_FACT_MISMATCH", item_path, "执行段落必须是对象。")
            continue
        validate_exact_fields(
            passage,
            expected={"passage_id", "timing", "kind", "character", "fact_ids", "text"},
            path=item_path,
            code_prefix="EXECUTION_PASSAGE",
            result=result,
        )
        passage_id = passage.get("passage_id")
        if not id_is_canonical(passage_id, "execution_passage"):
            result.error("EXECUTION_PASSAGE_FACT_MISMATCH", f"{item_path}.passage_id", "必须是 canonical XPxxx。")
        elif passage_id in seen_ids or passage_id in global_passage_ids:
            result.error("EXECUTION_PASSAGE_FACT_MISMATCH", f"{item_path}.passage_id", "passage_id 重复。")
        else:
            seen_ids.add(str(passage_id))
            global_passage_ids.add(str(passage_id))
        timing = require_nonempty_string(passage.get("timing"), path=f"{item_path}.timing", result=result)
        if timing and timing not in duration_block_ids:
            result.error("EXECUTION_PASSAGE_FACT_MISMATCH", f"{item_path}.timing", "必须引用本镜时间块。")
        if passage.get("kind") not in EXECUTION_PASSAGE_KINDS:
            result.error("EXECUTION_PASSAGE_FACT_MISMATCH", f"{item_path}.kind", "执行段落 kind 无效。")
        if passage.get("character") is not None:
            require_nonempty_string(passage.get("character"), path=f"{item_path}.character", result=result)
        fact_ids = set(
            list_of_unique_strings(
                passage.get("fact_ids"),
                path=f"{item_path}.fact_ids",
                result=result,
                allow_empty=False,
            )
        )
        passage_fact_sets.append(fact_ids)
        represented.update(fact_ids)
        if not fact_ids.issubset(covered_fact_ids):
            result.error(
                "EXECUTION_PASSAGE_FACT_MISMATCH",
                f"{item_path}.fact_ids",
                "执行段落只能引用本镜 covered facts。",
            )
        text_value = require_nonempty_string(passage.get("text"), path=f"{item_path}.text", result=result)
        normalized_text = re.sub(r"\s+", "", text_value)
        if normalized_text in seen_texts:
            result.error("EXECUTION_TEXT_DUPLICATE", f"{item_path}.text", "同一镜内不得重复执行段落。")
        seen_texts.add(normalized_text)
        for fact_id in fact_ids:
            fact = fact_lookup.get(fact_id)
            if not fact:
                result.error("EXECUTION_PASSAGE_FACT_MISMATCH", f"{item_path}.fact_ids", "执行段落引用不存在 fact。")
                continue
            if fact.get("type") == "dialogue":
                exact = dialogue_by_fact.get(fact_id, clean_text(fact.get("text")))
                if exact not in text_value:
                    result.error(
                        "EXECUTION_DIALOGUE_NOT_VERBATIM",
                        f"{item_path}.text",
                        f"对白 `{fact_id}` 必须逐字出现在执行段落。",
                    )
            else:
                quotes = [quote for quote in evidence_by_fact.get(fact_id, []) if quote]
                if quotes and not any(quote in text_value for quote in quotes):
                    result.error(
                        "EXECUTION_PASSAGE_FACT_MISMATCH",
                        f"{item_path}.text",
                        f"段落未写出 fact `{fact_id}` 的来源证据。",
                    )
    if represented != covered_fact_ids:
        result.error(
            "EXECUTION_PASSAGE_FACT_MISMATCH",
            path,
            "execution_passages 必须且只能完整承接本镜 covered facts。",
        )
    for chain in performance_chains:
        if not isinstance(chain, dict):
            continue
        chain_fact_ids = {
            str(fact_id)
            for step in as_list(chain.get("steps"))
            if isinstance(step, dict)
            for fact_id in as_list(step.get("fact_ids"))
        }
        contained = chain_fact_ids & covered_fact_ids
        if len(contained) >= 2 and not any(contained.issubset(fact_ids) for fact_ids in passage_fact_sets):
            result.error(
                "PERFORMANCE_PASSAGE_FRAGMENTED",
                path,
                f"表演链 `{chain.get('chain_id')}` 在同一镜内被机械拆成多个执行段落。",
            )


def validate_execution_text(
    shot: dict[str, Any],
    *,
    path: str,
    locked_text: str,
    dialogue: list[Any],
    facts: list[dict[str, Any]],
    result: ValidationResult,
) -> bool:
    if "execution_text" not in shot:
        result.error(
            "EXECUTION_TEXT_REQUIRED",
            f"{path}.execution_text",
            "2.5.2 正式镜头必须提供统一的【画面内容】。",
        )
        return False
    text_value = require_nonempty_string(
        shot.get("execution_text"),
        path=f"{path}.execution_text",
        result=result,
    )
    if "execution_passages" in shot:
        result.error(
            "EXECUTION_AUTHORITY",
            path,
            "execution_text 与旧版 execution_passages 只能选择一个权威正文。",
        )
    if VISIBLE_MACHINE_STATE_PATTERN.search(text_value):
        result.error(
            "VISIBLE_MACHINE_STATE",
            f"{path}.execution_text",
            "权威执行正文不得显示内部机器状态 ID。",
        )
    picture_prefix = f"【{PICTURE_CONTENT_LABEL}】"
    if (
        not text_value.startswith(picture_prefix)
        or text_value.count(picture_prefix) != 1
    ):
        result.error(
            "EXECUTION_SECTION_STRUCTURE",
            f"{path}.execution_text",
            "必须且只能以一个【画面内容】作为权威自然语言正文。",
        )
        picture_content = text_value
    else:
        picture_content = clean_text(text_value[len(picture_prefix) :])
    validate_picture_language(
        picture_content,
        locked_text=locked_text,
        path=f"{path}.execution_text",
        result=result,
    )
    normalized_content = normalize_execution_text(picture_content)
    if len(normalized_content) < 12:
        result.error(
            "EXECUTION_SECTION_EMPTY",
            f"{path}.execution_text",
            "【画面内容】必须写出完整、可执行的自然语言镜头过程。",
        )
    for label in FORBIDDEN_EXECUTION_LABELS:
        if f"【{label}】" in text_value:
            result.error(
                "EXECUTION_SECTION_STRUCTURE",
                f"{path}.execution_text",
                f"不得再单列【{label}】。",
            )
    if any(
        normalized_content == normalize_execution_text(placeholder)
        for placeholder in EXECUTION_SECTION_PLACEHOLDERS
    ):
        result.error(
            "EXECUTION_SECTION_PLACEHOLDER",
            f"{path}.execution_text",
            "【画面内容】不得使用表单式占位内容。",
        )
    for phrase in PLACEHOLDER_PHRASES:
        if phrase in text_value:
            result.error(
                "TEMPLATE_PLACEHOLDER",
                f"{path}.execution_text",
                f"检测到模板占位语：{phrase}。",
            )
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        exact = clean_text(item.get("text"))
        if exact and exact not in text_value:
            result.error(
                "EXECUTION_DIALOGUE_NOT_VERBATIM",
                f"{path}.execution_text",
                f"对白 `{item.get('fact_id', '')}` 必须逐字出现在执行正文。",
            )
    if len(execution_detail_delta(picture_content, facts=facts)) < 8:
        result.error(
            "EXECUTION_SOURCE_PARAPHRASE_ONLY",
            f"{path}.execution_text",
            "画面内容不能只转述来源；必须增加不改剧情事实的环境、摄影机关系、可见调度或表演状态。",
        )
    return True


def validate_continuity_object(
    continuity: Any,
    *,
    path: str,
    scene_axis_ids: set[str],
    scene_characters: set[str],
    result: ValidationResult,
) -> None:
    if continuity is None:
        return
    if not isinstance(continuity, dict):
        result.error("CONTINUITY", path, "continuity 必须是对象。")
        return
    axis_id = continuity.get("axis_id")
    axis_side = continuity.get("axis_side")
    if axis_id is None:
        if axis_side != "not_applicable":
            result.error("AXIS_SIDE", f"{path}.axis_side", "axis_id 为 null 时必须为 not_applicable。")
    else:
        if axis_id not in scene_axis_ids:
            result.error("AXIS_REFERENCE", f"{path}.axis_id", "轴线不属于当前场景。")
        if axis_side not in AXIS_SIDES - {"not_applicable"}:
            result.error("AXIS_SIDE", f"{path}.axis_side", "绑定轴线时必须声明合法侧别。")
    eyelines = continuity.get("eyelines")
    if not isinstance(eyelines, list):
        result.error("EYELINES", f"{path}.eyelines", "必须是数组。")
    else:
        for index, item in enumerate(eyelines):
            item_path = f"{path}.eyelines[{index}]"
            if not isinstance(item, dict):
                result.error("EYELINE", item_path, "必须是对象。")
                continue
            character = require_nonempty_string(
                item.get("character"),
                path=f"{item_path}.character",
                result=result,
            )
            if scene_characters and character and character not in scene_characters:
                result.error("EYELINE_CHARACTER", f"{item_path}.character", "人物不在场景台账。")
            require_nonempty_string(item.get("target"), path=f"{item_path}.target", result=result)
            if item.get("direction") not in SCREEN_DIRECTIONS:
                result.error("EYELINE_DIRECTION", f"{item_path}.direction", "画面方向无效。")
    directions = continuity.get("screen_directions")
    if not isinstance(directions, list):
        result.error("SCREEN_DIRECTIONS", f"{path}.screen_directions", "必须是数组。")
    else:
        seen: set[tuple[str, str]] = set()
        for index, item in enumerate(directions):
            item_path = f"{path}.screen_directions[{index}]"
            if not isinstance(item, dict):
                result.error("SCREEN_DIRECTION", item_path, "必须是对象。")
                continue
            entity = require_nonempty_string(item.get("entity"), path=f"{item_path}.entity", result=result)
            kind = item.get("kind")
            if kind not in SCREEN_DIRECTION_KINDS:
                result.error("SCREEN_DIRECTION_KIND", f"{item_path}.kind", "方向 kind 无效。")
            if item.get("direction") not in SCREEN_DIRECTIONS:
                result.error("SCREEN_DIRECTION_VALUE", f"{item_path}.direction", "方向值无效。")
            key = (entity, str(kind))
            if key in seen:
                result.error("SCREEN_DIRECTION_DUPLICATE", item_path, "同一实体与 kind 不得重复。")
            seen.add(key)
    action_match = continuity.get("action_match")
    if not isinstance(action_match, dict):
        result.error("ACTION_MATCH", f"{path}.action_match", "必须是对象。")
    else:
        for key in ("incoming", "outgoing"):
            value = action_match.get(key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                result.error("ACTION_MATCH", f"{path}.action_match.{key}", "必须为 null 或非空字符串。")
    exceptions = continuity.get("intentional_exceptions")
    if not isinstance(exceptions, list):
        result.error("CONTINUITY_EXCEPTIONS", f"{path}.intentional_exceptions", "必须是数组。")
    else:
        seen_types: set[str] = set()
        for index, item in enumerate(exceptions):
            item_path = f"{path}.intentional_exceptions[{index}]"
            if not isinstance(item, dict):
                result.error("CONTINUITY_EXCEPTION", item_path, "必须是对象。")
                continue
            exception_type = item.get("type")
            if exception_type not in CONTINUITY_EXCEPTION_TYPES:
                result.error("CONTINUITY_EXCEPTION_TYPE", f"{item_path}.type", "例外类型无效。")
            elif exception_type in seen_types:
                result.error("CONTINUITY_EXCEPTION_DUPLICATE", item_path, "同类例外不得重复。")
            else:
                seen_types.add(str(exception_type))
            reason = require_nonempty_string(item.get("reason"), path=f"{item_path}.reason", result=result)
            if exception_type in CONTINUITY_EXCEPTION_TYPES and reason:
                result.warn(
                    "CONTINUITY_EXCEPTION_REVIEW",
                    item_path,
                    f"有意连续性例外 `{exception_type}` 需要导演复核。",
                )


def validate_updates_shape(
    updates: Any,
    *,
    path: str,
    covered_fact_ids: set[str],
    result: ValidationResult,
) -> None:
    if updates is None:
        return
    if not isinstance(updates, list):
        result.error("CONTINUITY_UPDATES", path, "必须是数组。")
        return
    for index, update in enumerate(updates):
        item_path = f"{path}[{index}]"
        if not isinstance(update, dict):
            result.error("CONTINUITY_UPDATE", item_path, "必须是对象。")
            continue
        entity_type = require_nonempty_string(
            update.get("entity_type"),
            path=f"{item_path}.entity_type",
            result=result,
        )
        if entity_type == "reality_layer":
            if update.get("entity") != "":
                result.error("CONTINUITY_ENTITY", f"{item_path}.entity", "reality_layer 的 entity 必须为空字符串。")
        else:
            require_nonempty_string(update.get("entity"), path=f"{item_path}.entity", result=result)
        require_nonempty_string(update.get("field"), path=f"{item_path}.field", result=result)
        before = require_nonempty_string(update.get("from"), path=f"{item_path}.from", result=result)
        after = require_nonempty_string(update.get("to"), path=f"{item_path}.to", result=result)
        if before and before == after:
            result.error("CONTINUITY_NOOP", item_path, "from 与 to 不得相同。")
        evidence = list_of_unique_strings(
            update.get("evidence_fact_ids"),
            path=f"{item_path}.evidence_fact_ids",
            result=result,
            allow_empty=False,
        )
        for evidence_index, fact_id in enumerate(evidence):
            if fact_id not in covered_fact_ids:
                result.error(
                    "CONTINUITY_EVIDENCE",
                    f"{item_path}.evidence_fact_ids[{evidence_index}]",
                    "证据 fact 必须由当前镜头覆盖。",
                )


def validate_director_audit(
    audit: Any,
    path: str,
    result: ValidationResult,
    *,
    long_take_required: bool,
) -> None:
    if not long_take_required:
        if audit not in (None, {}):
            result.error(
                "LONG_TAKE_AUDIT_UNNEEDED",
                path,
                "普通镜头不填写 long_take 审计。",
            )
        return
    if not isinstance(audit, dict):
        result.error("DIRECTOR_AUDIT", path, "long_take 镜头必须提供 director_audit。")
        return
    validate_exact_fields(
        audit,
        expected={"long_take"},
        path=path,
        code_prefix="DIRECTOR_AUDIT",
        result=result,
    )
    long_take = audit.get("long_take")
    if not isinstance(long_take, dict):
        result.error("LONG_TAKE_AUDIT", f"{path}.long_take", "必须是对象。")
        return
    validate_exact_fields(
        long_take,
        expected={"status", "reason", "supports"},
        path=f"{path}.long_take",
        code_prefix="LONG_TAKE_AUDIT",
        result=result,
    )
    status = long_take.get("status")
    if status not in LONG_TAKE_STATUSES:
        result.error("LONG_TAKE_STATUS", f"{path}.long_take.status", "长镜审计状态无效。")
    reason = require_string(long_take.get("reason"), path=f"{path}.long_take.reason", result=result)
    supports = list_of_unique_strings(
        long_take.get("supports"),
        path=f"{path}.long_take.supports",
        result=result,
        allow_empty=True,
    )
    if status == "supported" and (not reason.strip() or not supports):
        result.error(
            "LONG_TAKE_SUPPORT",
            f"{path}.long_take",
            "supported 必须同时给出 reason 与 supports。",
        )
    if status == "needs_review":
        result.warn(
            "LONG_TAKE_REVIEW",
            f"{path}.long_take",
            "长镜头有效性需要人工导演审计；不按秒数硬判失败。",
        )


def duration_block_ids(shot: dict[str, Any]) -> set[str]:
    return {
        clean_text(block.get("block_id"))
        for block in as_list(shot.get("duration_blocks"))
        if isinstance(block, dict) and clean_text(block.get("block_id"))
    }


def coverage_target_allowed(path: str) -> bool:
    return any(pattern.fullmatch(path) for pattern in COVERAGE_TARGET_PATTERNS)


def coverage_path_matches_fact_type(fact_type: str, target_path: str) -> bool:
    if target_path.startswith("execution_passages["):
        return fact_type in FACT_TYPES
    allowed_prefixes = {
        "character": ("visible_characters[", "camera.composition", "camera.start_frame", "camera.end_frame"),
        "action": ("blocking[", "camera.start_frame", "camera.end_frame", "environment_behavior["),
        "dialogue": ("dialogue[",),
        "prop": ("visible_props[", "camera.composition", "camera.start_frame", "camera.end_frame", "continuity_updates[", "end_state["),
        "space": ("camera.composition", "camera.start_frame", "camera.end_frame", "end_state["),
        "position": ("blocking[", "camera.composition", "camera.start_frame", "camera.end_frame", "continuity_updates[", "end_state["),
        "emotion": ("performance.visible_behavior[", "camera.start_frame", "camera.end_frame"),
        "sound": ("environment_behavior[",),
        "reality": ("camera.start_frame", "camera.end_frame", "continuity_updates[", "end_state["),
    }
    return any(target_path.startswith(prefix) for prefix in allowed_prefixes.get(fact_type, ()))


def resolve_target_path(value: Any, path: str) -> Any:
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\[(0|[1-9][0-9]*)\]", path)
    if not tokens:
        raise KeyError(path)
    current = value
    position = 0
    for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)|\[(0|[1-9][0-9]*)\]", path):
        if match.start() != position and path[position:match.start()] != ".":
            raise KeyError(path)
        field_name = match.group(1)
        index_text = match.group(2)
        if field_name is not None:
            if not isinstance(current, dict) or field_name not in current:
                raise KeyError(path)
            current = current[field_name]
        else:
            if not isinstance(current, list):
                raise KeyError(path)
            index = int(index_text)
            if index >= len(current):
                raise KeyError(path)
            current = current[index]
        position = match.end()
    if position != len(path):
        raise KeyError(path)
    return current


def validate_coverage_evidence(
    shot: dict[str, Any],
    *,
    path: str,
    covered_fact_ids: set[str],
    fact_lookup: dict[str, dict[str, Any]],
    locked_text: str,
    result: ValidationResult,
) -> set[str]:
    evidence_items = shot.get("coverage_evidence")
    if evidence_items is None:
        return set()
    if not isinstance(evidence_items, list):
        result.error("COVERAGE_EVIDENCE", f"{path}.coverage_evidence", "必须是数组。")
        return set()
    valid_fact_ids: set[str] = set()
    seen: set[tuple[str, str, str]] = set()
    for index, evidence in enumerate(evidence_items):
        item_path = f"{path}.coverage_evidence[{index}]"
        if not isinstance(evidence, dict):
            result.error("COVERAGE_EVIDENCE_ITEM", item_path, "coverage evidence 必须是对象。")
            continue
        validate_exact_fields(
            evidence,
            expected=COVERAGE_EVIDENCE_KEYS,
            path=item_path,
            code_prefix="COVERAGE_EVIDENCE",
            result=result,
        )
        fact_id = require_nonempty_string(
            evidence.get("fact_id"),
            path=f"{item_path}.fact_id",
            result=result,
        )
        target_path = require_nonempty_string(
            evidence.get("target_path"),
            path=f"{item_path}.target_path",
            result=result,
        )
        quote = require_nonempty_string(
            evidence.get("evidence_quote"),
            path=f"{item_path}.evidence_quote",
            result=result,
        )
        signature = (fact_id, target_path, quote)
        if signature in seen:
            result.error("COVERAGE_EVIDENCE_DUPLICATE", item_path, "coverage evidence 不得重复。")
        seen.add(signature)
        item_valid = True
        fact = fact_lookup.get(fact_id)
        if fact_id not in covered_fact_ids or fact is None:
            result.error(
                "COVERAGE_EVIDENCE_FACT",
                f"{item_path}.fact_id",
                "evidence fact 必须存在并由当前镜头覆盖。",
            )
            item_valid = False
        elif not coverage_path_matches_fact_type(
            clean_text(fact.get("type")),
            target_path,
        ):
            result.error(
                "COVERAGE_EVIDENCE_TYPE_MISMATCH",
                f"{item_path}.target_path",
                "coverage 路径与 fact 类型不匹配。",
            )
            item_valid = False
        if not coverage_target_allowed(target_path):
            result.error(
                "COVERAGE_EVIDENCE_PATH",
                f"{item_path}.target_path",
                "目标路径不是允许的可执行画面、对白、物件/状态或确定性渲染字段。",
            )
            item_valid = False
            target_value = None
        else:
            try:
                target_value = resolve_target_path(shot, target_path)
            except (KeyError, ValueError):
                target_value = None
                result.error(
                    "COVERAGE_EVIDENCE_PATH",
                    f"{item_path}.target_path",
                    "目标路径在当前镜头中不存在。",
                )
                item_valid = False
        if not isinstance(target_value, str) or quote not in target_value:
            result.error(
                "COVERAGE_EVIDENCE_QUOTE",
                f"{item_path}.evidence_quote",
                "精确 evidence quote 不存在于声明的目标字段。",
            )
            item_valid = False
        if fact is not None:
            source_text = span_source_text(fact.get("source_spans"), locked_text)
            if quote not in source_text:
                result.error(
                    "COVERAGE_EVIDENCE_SOURCE",
                    f"{item_path}.evidence_quote",
                    "evidence quote 必须逐字来自该 fact 的锁定来源；无来源动作不能冒充 coverage。",
                )
                item_valid = False
        if item_valid:
            valid_fact_ids.add(fact_id)
    return valid_fact_ids


def normalized_string_list(value: Any) -> list[str]:
    return [
        clean_text(item)
        for item in as_list(value)
        if isinstance(item, str) and clean_text(item)
    ]


def validate_visual_plan_execution(
    planned: Any,
    camera: Any,
    *,
    path: str,
    result: ValidationResult,
) -> None:
    plan = as_dict(planned)
    final_camera = as_dict(camera)
    field_map = {
        "angle": "angle",
        "shot_size": "shot_size",
        "position": "camera_position",
        "composition": "framing_relation",
        "viewpoint_owner": "viewpoint_owner",
        "perspective_intent": "perspective_intent",
        "focus_plan": "focus_plan",
        "start_frame": "start_frame",
        "end_frame": "end_frame",
        "motivation": "motivation",
    }
    for final_field, plan_field in field_map.items():
        if final_camera.get(final_field) != plan.get(plan_field):
            result.error(
                "SHOT_VISUAL_PLAN_MISMATCH",
                f"{path}.camera.{final_field}",
                f"终稿 `{final_field}` 必须与 Gate 2 visual_plan.{plan_field} 完全一致。",
            )
    for field_name in ("primary_subjects", "secondary_subjects"):
        if normalized_string_list(final_camera.get(field_name)) != normalized_string_list(
            plan.get(field_name)
        ):
            result.error(
                "SHOT_VISUAL_PLAN_MISMATCH",
                f"{path}.camera.{field_name}",
                f"终稿 `{field_name}` 必须与 Gate 2 已确认 visual_plan 完全一致。",
            )
    for field_name in ("spatial_strategy", "movement_plan"):
        if final_camera.get(field_name) != plan.get(field_name):
            result.error(
                "SHOT_VISUAL_PLAN_MISMATCH",
                f"{path}.camera.{field_name}",
                f"终稿 `{field_name}` 必须与 Gate 2 已确认 visual_plan 完全一致。",
            )
    final_movement_class = camera_movement_class(final_camera.get("movement"))
    if final_movement_class != as_dict(plan.get("movement_plan")).get("class"):
        result.error(
            "SHOT_VISUAL_PLAN_MISMATCH",
            f"{path}.camera.movement",
            "终稿 movement 归一化类别必须与 Gate 2 movement_plan.class 一致。",
        )


def validate_shots(
    data: dict[str, Any],
    locked_text: str,
    scenes: dict[str, dict[str, Any]],
    scene_order: dict[str, int],
    entity_names: dict[str, dict[str, set[str]]],
    axis_ids_by_scene: dict[str, set[str]],
    beat_lookup: dict[str, dict[str, Any]],
    fact_lookup: dict[str, dict[str, Any]],
    fact_beat: dict[str, str],
    fact_order: dict[str, int],
    emotion_arcs: dict[str, dict[str, Any]],
    plan_info: dict[str, Any],
    result: ValidationResult,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, list[str]]]:
    shots = data.get("shots")
    if not isinstance(shots, list) or not shots:
        result.error("SHOTS", "$.shots", "必须是非空数组。")
        return {}, {}, {}
    plan_units = as_list(plan_info.get("units"))
    if len(shots) != len(plan_units):
        result.error(
            "SHOT_PLAN_COUNT",
            "$.shots",
            "最终镜头总数必须与已确认规划完全一致；改变规划必须重新 Gate 2。",
        )
    lookup: dict[str, dict[str, Any]] = {}
    shots_by_scene: dict[str, list[dict[str, Any]]] = {scene_id: [] for scene_id in scenes}
    fact_coverage: dict[str, list[str]] = {fact_id: [] for fact_id in fact_lookup}
    global_passage_ids: set[str] = set()
    previous_scene_rank = -1
    seen_scene_ids: set[str] = set()
    for index, shot in enumerate(shots):
        path = f"$.shots[{index}]"
        if not isinstance(shot, dict):
            result.error("SHOT", path, "镜头必须是对象。")
            continue
        if "director_analysis" in shot:
            result.error(
                "DIRECTOR_ANALYSIS_SCOPE",
                f"{path}.director_analysis",
                "director_analysis 只允许位于 scene 或 Beat。",
            )
        plan_unit = (
            plan_units[index]
            if index < len(plan_units) and isinstance(plan_units[index], dict)
            else {}
        )
        expected_plan_unit_id = plan_unit.get("plan_unit_id")
        if shot.get("plan_unit_id") != expected_plan_unit_id:
            result.error(
                "SHOT_PLAN_UNIT",
                f"{path}.plan_unit_id",
                "最终镜头必须按已确认规划顺序一对一引用 plan_unit_id。",
            )
        if shot.get("shot_form") is not None and shot.get("shot_form") not in SHOT_FORMS:
            result.error(
                "SHOT_FORM",
                f"{path}.shot_form",
                "普通镜头省略 shot_form；只有明确采用长镜头时写 long_take。",
            )
        elif shot.get("shot_form") != plan_unit.get("shot_form"):
            result.error(
                "SHOT_PLAN_FORM",
                f"{path}.shot_form",
                "最终 shot_form 必须与已确认规划一致；改变分类必须重新 Gate 2。",
            )
        if shot.get("duration_seconds") != plan_unit.get(
            "estimated_duration_seconds"
        ):
            result.error(
                "SHOT_PLAN_DURATION",
                f"{path}.duration_seconds",
                "终稿镜头时长必须与 Gate 2 规划估算完全一致；改变时长必须重新审计 Gate 2。",
            )
        shot_id = shot.get("shot_id")
        if not id_is_canonical(shot_id, "shot"):
            result.error("SHOT_ID", f"{path}.shot_id", "必须是 canonical SHxxx。")
            continue
        assert isinstance(shot_id, str)
        if shot_id in lookup:
            result.error("SHOT_ID_DUPLICATE", f"{path}.shot_id", f"重复 shot_id：{shot_id}。")
        lookup[shot_id] = shot
        expected_shot_id = f"SH{index + 1:03d}"
        if shot_id != expected_shot_id:
            result.error(
                "SHOT_ID_ORDER",
                f"{path}.shot_id",
                f"最终镜号必须按规划顺序连续编号为 `{expected_shot_id}`。",
            )
        if shot.get("shot_order") != index + 1:
            result.error(
                "SHOT_ORDER",
                f"{path}.shot_order",
                "shots[] 数组位置必须与从 1 开始的 shot_order 完全一致。",
            )
        scene_id = shot.get("scene_id")
        is_first_scene_shot = isinstance(scene_id, str) and scene_id not in seen_scene_ids
        if scene_id != plan_unit.get("scene_id"):
            result.error(
                "SHOT_PLAN_SCENE",
                f"{path}.scene_id",
                "最终镜头场景必须与已确认规划单元一致。",
            )
        if scene_id not in scenes:
            result.error("SHOT_SCENE", f"{path}.scene_id", "引用场景不存在。")
            scene_characters: set[str] = set()
            scene_props: set[str] = set()
            axis_ids: set[str] = set()
        else:
            assert isinstance(scene_id, str)
            rank = scene_order[scene_id]
            if rank < previous_scene_rank:
                result.error("SHOT_SCENE_ORDER", f"{path}.scene_id", "镜头场景顺序必须遵循 scenes[]。")
            previous_scene_rank = max(previous_scene_rank, rank)
            shots_by_scene[scene_id].append(shot)
            seen_scene_ids.add(scene_id)
            scene_characters = entity_names.get(scene_id, {}).get("character", set())
            scene_props = entity_names.get(scene_id, {}).get("prop", set())
            axis_ids = axis_ids_by_scene.get(scene_id, set())
        beat_ids = list_of_unique_strings(
            shot.get("beat_ids"),
            path=f"{path}.beat_ids",
            result=result,
            allow_empty=False,
        )
        if beat_ids != as_list(plan_unit.get("beat_ids")):
            result.error(
                "SHOT_PLAN_BEATS",
                f"{path}.beat_ids",
                "最终镜头 Beat 范围必须与已确认规划单元一致。",
            )
        beat_order_values = [
            beat_lookup[beat_id].get("beat_order")
            for beat_id in beat_ids
            if beat_id in beat_lookup
        ]
        if beat_order_values != sorted(beat_order_values):
            result.error("SHOT_BEAT_ORDER", f"{path}.beat_ids", "镜头内 Beat 必须保持来源顺序。")
        for beat_index, beat_id in enumerate(beat_ids):
            beat = beat_lookup.get(beat_id)
            if not beat:
                result.error("SHOT_BEAT", f"{path}.beat_ids[{beat_index}]", "Beat 不存在。")
            elif beat.get("scene_id") != scene_id:
                result.error("SHOT_BEAT_SCENE", f"{path}.beat_ids[{beat_index}]", "Beat 与镜头不在同场。")
        span_texts(
            shot.get("source_spans"),
            locked_text,
            path=f"{path}.source_spans",
            result=result,
        )
        shot_ranges = span_coordinates(shot.get("source_spans"), locked_text)
        plan_ranges = span_coordinates(plan_unit.get("source_spans"), locked_text)
        if shot_ranges != plan_ranges:
            result.error(
                "SHOT_PLAN_SOURCE",
                f"{path}.source_spans",
                "最终镜头 source spans 必须与已确认规划单元坐标一致。",
            )
        covered = list_of_unique_strings(
            shot.get("covered_fact_ids"),
            path=f"{path}.covered_fact_ids",
            result=result,
            allow_empty=False,
        )
        covered_set = set(covered)
        covered_ranks = [fact_order[fact_id] for fact_id in covered if fact_id in fact_order]
        if covered_ranks != sorted(covered_ranks):
            result.error(
                "SHOT_FACT_ORDER",
                f"{path}.covered_fact_ids",
                "镜头内 covered facts 必须保持来源单调叙事顺序。",
            )
        for fact_index, fact_id in enumerate(covered):
            fact = fact_lookup.get(fact_id)
            if not fact:
                result.error("SHOT_FACT", f"{path}.covered_fact_ids[{fact_index}]", "fact 不存在。")
                continue
            fact_coverage.setdefault(fact_id, []).append(shot_id)
            beat_id = fact_beat.get(fact_id)
            if beat_id not in beat_ids:
                result.error("SHOT_FACT_BEAT", f"{path}.covered_fact_ids[{fact_index}]", "必须同时登记 fact 所属 Beat。")
            beat = beat_lookup.get(beat_id or "")
            if beat and beat.get("scene_id") != scene_id:
                result.error("SHOT_FACT_SCENE", f"{path}.covered_fact_ids[{fact_index}]", "fact 与镜头不在同场。")
            fact_ranges = span_coordinates(fact.get("source_spans"), locked_text)
            if fact_ranges and shot_ranges and not spans_contained(fact_ranges, shot_ranges):
                result.error(
                    "SHOT_FACT_SOURCE",
                    f"{path}.covered_fact_ids[{fact_index}]",
                    "covered fact 的来源坐标必须完全包含于镜头 source spans。",
                )
        primary_fact_id = shot.get("primary_fact_id")
        if primary_fact_id is not None and primary_fact_id not in covered_set:
            result.error("PRIMARY_FACT", f"{path}.primary_fact_id", "必须属于 covered_fact_ids。")
        cut_design = shot.get("cut_design")
        if not isinstance(cut_design, dict):
            result.error("CUT_DESIGN", f"{path}.cut_design", "必须是对象。")
        else:
            validate_required_optional_fields(
                cut_design,
                required={"entry_trigger", "exit_trigger"},
                optional={"isolation_intent"},
                path=f"{path}.cut_design",
                code_prefix="CUT_DESIGN",
                result=result,
            )
            for key in ("entry_trigger", "exit_trigger"):
                require_nonempty_string(cut_design.get(key), path=f"{path}.cut_design.{key}", result=result)
            if (
                "isolation_intent" in cut_design
                and cut_design.get("isolation_intent")
                not in {"none", "director_required"}
            ):
                result.error(
                    "ISOLATION_INTENT",
                    f"{path}.cut_design.isolation_intent",
                    "必须为 none 或 director_required。",
                )
        validate_shot_phases(
            shot,
            path=path,
            screen_events=as_dict(plan_info.get("screen_event_lookup")),
            planned_screen_event_ids=[
                item
                for item in as_list(plan_unit.get("screen_event_ids"))
                if isinstance(item, str)
            ],
            result=result,
        )
        validate_camera(
            shot.get("camera"),
            f"{path}.camera",
            result,
            scene_characters=scene_characters,
        )
        validate_visual_plan_execution(
            plan_unit.get("visual_plan"),
            shot.get("camera"),
            path=path,
            result=result,
        )
        visible_characters: set[str] = set()
        if "visible_characters" in shot:
            visible_characters = set(
                list_of_unique_strings(
                    shot.get("visible_characters"),
                    path=f"{path}.visible_characters",
                    result=result,
                    allow_empty=True,
                )
            )
        for character in visible_characters:
            if scene_characters and character not in scene_characters:
                result.error("VISIBLE_CHARACTER", f"{path}.visible_characters", f"人物 `{character}` 不在场景台账。")
        planned_visible_subjects = set(
            as_list(as_dict(plan_unit.get("visual_plan")).get("primary_subjects"))
        ) | set(
            as_list(as_dict(plan_unit.get("visual_plan")).get("secondary_subjects"))
        )
        for character in planned_visible_subjects & scene_characters:
            if character not in visible_characters:
                result.error(
                    "VISUAL_PLAN_VISIBLE_SUBJECT_MISMATCH",
                    f"{path}.visible_characters",
                    f"DOP 构图声明人物 `{character}` 可见，但正文可见人物未登记。",
                )
        visible_props: set[str] = set()
        if "visible_props" in shot:
            visible_props = set(
                list_of_unique_strings(
                    shot.get("visible_props"),
                    path=f"{path}.visible_props",
                    result=result,
                    allow_empty=True,
                )
            )
        for prop in visible_props:
            if scene_props and prop not in scene_props:
                result.error("VISIBLE_PROP", f"{path}.visible_props", f"道具 `{prop}` 不在场景台账。")
        validate_blocking(
            shot.get("blocking"),
            path=f"{path}.blocking",
            scene_characters=scene_characters,
            visible_characters=visible_characters,
            result=result,
        )
        validate_performance(
            shot.get("performance"),
            path=f"{path}.performance",
            emotion_arcs=emotion_arcs,
            result=result,
        )
        validate_dialogue(
            shot.get("dialogue"),
            path=f"{path}.dialogue",
            fact_lookup=fact_lookup,
            covered_fact_ids=covered_set,
            scene_characters=scene_characters,
            visible_characters=visible_characters,
            phase_ids=shot_phase_ids(shot),
            result=result,
        )
        validate_speaker_presentation(
            shot.get("speaker_presentation"),
            path=f"{path}.speaker_presentation",
            dialogue=as_list(shot.get("dialogue")),
            camera=as_dict(shot.get("camera")),
            dialogue_design=plan_unit.get("dialogue_design"),
            result=result,
        )
        planned_axis = as_dict(plan_unit.get("dialogue_design")).get("axis_id")
        final_axis = as_dict(shot.get("continuity")).get("axis_id")
        if planned_axis is not None and planned_axis != final_axis:
            result.error(
                "DIALOGUE_PLAN_CAMERA_MISMATCH",
                f"{path}.continuity.axis_id",
                "终稿对白机位必须兑现 Gate 2 规划的轴线。",
            )
        validate_execution_text(
            shot,
            path=path,
            locked_text=locked_text,
            dialogue=as_list(shot.get("dialogue")),
            facts=[
                fact_lookup[fact_id]
                for fact_id in covered_set
                if fact_id in fact_lookup
            ],
            result=result,
        )
        if "environment_behavior" in shot:
            list_of_unique_strings(
                shot.get("environment_behavior"),
                path=f"{path}.environment_behavior",
                result=result,
                allow_empty=True,
            )
        validate_continuity_object(
            shot.get("continuity"),
            path=f"{path}.continuity",
            scene_axis_ids=axis_ids,
            scene_characters=scene_characters,
            result=result,
        )
        validate_updates_shape(
            shot.get("continuity_updates"),
            path=f"{path}.continuity_updates",
            covered_fact_ids=covered_set,
            result=result,
        )
        if "end_state" in shot:
            list_of_unique_strings(
                shot.get("end_state"),
                path=f"{path}.end_state",
                result=result,
                allow_empty=False,
            )
        transition = shot.get("transition_to_next")
        if not isinstance(transition, dict):
            result.error("TRANSITION", f"{path}.transition_to_next", "必须是对象。")
        else:
            validate_required_optional_fields(
                transition,
                required={"type", "edit_point_id"},
                optional={"notes"},
                path=f"{path}.transition_to_next",
                code_prefix="TRANSITION",
                result=result,
            )
            transition_type = transition.get("type")
            if transition_type not in TRANSITION_TYPES:
                result.error("TRANSITION_TYPE", f"{path}.transition_to_next.type", "转场类型无效。")
            expected_edit_id = None
            if index + 1 < len(plan_units):
                next_unit = plan_units[index + 1]
                if isinstance(next_unit, dict):
                    expected_edit_id = as_dict(plan_info.get("boundary_edit_ids")).get(
                        (
                            str(plan_unit.get("plan_unit_id")),
                            str(next_unit.get("plan_unit_id")),
                        )
                    )
            if transition.get("edit_point_id") != expected_edit_id:
                result.error(
                    "SHOT_PLAN_EDIT_POINT",
                    f"{path}.transition_to_next.edit_point_id",
                    "最终镜头边界必须与已确认规划剪辑点一一一致。",
                )
            if "notes" in transition:
                require_string(
                    transition.get("notes"),
                    path=f"{path}.transition_to_next.notes",
                    result=result,
                )
        validate_director_audit(
            shot.get("director_audit"),
            f"{path}.director_audit",
            result,
            long_take_required=shot.get("shot_form") == "long_take",
        )
        expected_description = render_shot_description(
            shot,
            is_first_scene_shot=is_first_scene_shot,
        )
        if shot.get("rendered_shot_description") != expected_description:
            result.error(
                "RENDERED_DESCRIPTION",
                f"{path}.rendered_shot_description",
                "第五列必须由结构化字段确定性渲染。",
            )
        if VISIBLE_MACHINE_STATE_PATTERN.search(expected_description):
            result.error(
                "VISIBLE_MACHINE_STATE",
                f"{path}.rendered_shot_description",
                "第五列不得显示规划单元、转场、时间块、轴线侧别或其他机器状态 ID。",
            )
        if not re.match(
            r"^【[^｜】\n]+｜[^｜】\n]+｜[^】\n]+】\n【画面内容】",
            expected_description,
        ):
            result.error(
                "CAMERA_HEADER_NOT_TRIAD",
                f"{path}.rendered_shot_description",
                "第五列必须为纯净三元素【景别｜角度｜运镜】加一个【画面内容】。",
            )
        for forbidden_label in FORBIDDEN_EXECUTION_LABELS:
            if f"【{forbidden_label}】" in expected_description:
                result.error(
                    "RENDERED_DESCRIPTION_SECTION",
                    f"{path}.rendered_shot_description",
                    f"第五列不得再单列【{forbidden_label}】。",
                )
        normalized_execution = normalize_execution_text(shot.get("execution_text"))
        for update_index, item in enumerate(as_list(shot.get("continuity_updates"))):
            if (
                not isinstance(item, dict)
                or item.get("entity_type") != "character"
                or item.get("field") not in {"position", "facing", "eyeline", "presence"}
            ):
                continue
            required_values = (
                clean_text(item.get("entity")),
                visible_continuity_value(item.get("from")),
                visible_continuity_value(item.get("to")),
            )
            if any(
                normalize_execution_text(value) not in normalized_execution
                for value in required_values
                if value
            ):
                result.error(
                    "CONTINUITY_UPDATE_NOT_VISIBLE",
                    f"{path}.continuity_updates[{update_index}]",
                    "人物位置、朝向、视线或进出画变化必须把主体、起点和落位自然写入【画面内容】。",
                )
        validate_coverage_evidence(
            shot,
            path=path,
            covered_fact_ids=covered_set,
            fact_lookup=fact_lookup,
            locked_text=locked_text,
            result=result,
        )
        note = require_string(
            shot.get("notes"),
            path=f"{path}.notes",
            result=result,
        )
        if note:
            result.error(
                "SHOT_NOTES_RESERVED",
                f"{path}.notes",
                "第六列备注是人工预留列，Skill 正式交付必须留空。",
            )
    for scene_id, scene_shots in shots_by_scene.items():
        if not scene_shots:
            result.error("SCENE_WITHOUT_SHOTS", f"$.scenes[{scene_order[scene_id]}]", "每个场景至少有一个镜头。")
            continue
    isolation_groups: dict[str, list[str]] = {}
    for fact_id, fact in fact_lookup.items():
        coverage = fact_coverage.get(fact_id, [])
        if not coverage:
            result.error("FACT_UNCOVERED", f"fact:{fact_id}", "fact 未被任何镜头覆盖。")
        if fact.get("shot_isolation") == "director_required":
            group_id = clean_text(fact.get("isolation_group_id"))
            if group_id:
                isolation_groups.setdefault(group_id, []).append(fact_id)
    for group_id, group_fact_ids in isolation_groups.items():
        group_beats = {fact_beat.get(fact_id) for fact_id in group_fact_ids}
        if len(group_beats) != 1:
            result.error(
                "ISOLATION_GROUP_MOMENT",
                f"isolation_group:{group_id}",
                "同一 isolation_group_id 只能用于同一 Beat 的同一物理瞬间。",
            )
        isolated = any(
            set(group_fact_ids).issubset(set(as_list(shot.get("covered_fact_ids"))))
            and shot.get("primary_fact_id") in group_fact_ids
            and as_dict(shot.get("cut_design")).get("isolation_intent")
            == "director_required"
            for shot in shots
            if isinstance(shot, dict)
        )
        if not isolated:
            result.error(
                "FACT_ISOLATION",
                f"isolation_group:{group_id}",
                "同一物理瞬间的 director_required facts 必须由一个明确独立镜头共同承接。",
            )
    last_shot = shots[-1] if shots and isinstance(shots[-1], dict) else {}
    if as_dict(last_shot.get("transition_to_next")).get("type") != "scene_end":
        result.error("FINAL_TRANSITION", "$.shots[-1].transition_to_next.type", "最后一镜必须为 scene_end。")
    for index, shot in enumerate(shots[:-1]):
        next_shot = shots[index + 1] if isinstance(shots[index + 1], dict) else {}
        if (
            isinstance(shot, dict)
            and shot.get("scene_id") == next_shot.get("scene_id")
            and as_dict(shot.get("transition_to_next")).get("type") == "scene_end"
        ):
            result.error(
                "NONFINAL_TRANSITION",
                f"$.shots[{index}].transition_to_next.type",
                "非末镜不得使用 scene_end。",
            )
    return lookup, shots_by_scene, fact_coverage


def state_key_from_update(update: dict[str, Any]) -> tuple[str, str, str]:
    return (
        clean_text(update.get("entity_type")),
        clean_text(update.get("entity")),
        clean_text(update.get("field")),
    )


def exception_types(shot: dict[str, Any]) -> set[str]:
    return {
        clean_text(item.get("type"))
        for item in as_list(as_dict(shot.get("continuity")).get("intentional_exceptions"))
        if isinstance(item, dict)
    }


def screen_direction_map(shot: dict[str, Any]) -> dict[tuple[str, str], str]:
    output: dict[tuple[str, str], str] = {}
    for item in as_list(as_dict(shot.get("continuity")).get("screen_directions")):
        if not isinstance(item, dict):
            continue
        entity = clean_text(item.get("entity"))
        kind = clean_text(item.get("kind"))
        direction = clean_text(item.get("direction"))
        if entity and kind and direction:
            output[(entity, kind)] = direction
    return output


def directions_are_opposite(left: str, right: str) -> bool:
    return (left, right) in {
        ("screen_left", "screen_right"),
        ("screen_right", "screen_left"),
        ("toward_camera", "away_camera"),
        ("away_camera", "toward_camera"),
    }


def validate_scene_continuity(
    data: dict[str, Any],
    scenes: dict[str, dict[str, Any]],
    scene_order: dict[str, int],
    initial_states: dict[str, dict[tuple[str, str, str], str]],
    shots_by_scene: dict[str, list[dict[str, Any]]],
    result: ValidationResult,
) -> None:
    final_states: dict[str, dict[tuple[str, str, str], str]] = {}
    for scene_id in sorted(scenes, key=lambda item: scene_order[item]):
        scene = scenes[scene_id]
        scene_path = f"$.scenes[{scene_order[scene_id]}]"
        state = copy.deepcopy(initial_states.get(scene_id, {}))
        parent = scene.get("inherits_from")
        if isinstance(parent, str) and parent in final_states:
            parent_state = final_states[parent]
            inherited_keys: set[tuple[str, str, str]] = set()
            for index, item in enumerate(as_list(scene.get("inherited_states"))):
                if not isinstance(item, dict):
                    continue
                key = (
                    clean_text(item.get("entity_type")),
                    clean_text(item.get("entity")),
                    clean_text(item.get("field")),
                )
                item_path = f"{scene_path}.inherited_states[{index}]"
                if key in inherited_keys:
                    result.error("INHERITED_STATE_DUPLICATE", item_path, "继承状态不得重复。")
                inherited_keys.add(key)
                if key not in parent_state or key not in state:
                    result.error("INHERITED_STATE_MISSING", item_path, "父终态或子初态缺少该字段。")
                elif parent_state[key] != state[key]:
                    result.error("INHERITED_STATE_VALUE", item_path, "子场景初值不等于父场景终值。")
        scene_shots = shots_by_scene.get(scene_id, [])
        for shot_index, shot in enumerate(scene_shots):
            shot_id = clean_text(shot.get("shot_id")) or f"scene-shot-{shot_index + 1}"
            for update_index, update in enumerate(as_list(shot.get("continuity_updates"))):
                if not isinstance(update, dict):
                    continue
                key = state_key_from_update(update)
                path = f"shot:{shot_id}.continuity_updates[{update_index}]"
                if key not in state:
                    if "initial_continuity" not in scene:
                        before = update.get("from")
                        after = update.get("to")
                        if (
                            isinstance(before, str)
                            and before
                            and isinstance(after, str)
                            and after
                            and after != before
                        ):
                            state[key] = after
                        continue
                    result.error(
                        "CONTINUITY_STATE_UNKNOWN",
                        path,
                        "已有场景初态时，更新的实体字段必须先登记。",
                    )
                    continue
                before = update.get("from")
                after = update.get("to")
                if before != state[key]:
                    result.error(
                        "CONTINUITY_FROM",
                        f"{path}.from",
                        f"必须等于当前状态 `{state[key]}`。",
                    )
                    continue
                if isinstance(after, str) and after and after != before:
                    state[key] = after
        final_states[scene_id] = state
        for index in range(1, len(scene_shots)):
            previous = scene_shots[index - 1]
            current = scene_shots[index]
            previous_continuity = as_dict(previous.get("continuity"))
            current_continuity = as_dict(current.get("continuity"))
            previous_axis = previous_continuity.get("axis_id")
            current_axis = current_continuity.get("axis_id")
            previous_side = previous_continuity.get("axis_side")
            current_side = current_continuity.get("axis_side")
            current_exceptions = exception_types(current)
            if (
                previous_axis is not None
                and previous_axis == current_axis
                and {previous_side, current_side} == {"side_a", "side_b"}
                and "axis_cross" not in current_exceptions
            ):
                result.error(
                    "AXIS_CROSS",
                    f"shot:{current.get('shot_id')}.continuity",
                    "同轴直接换侧必须登记有理由的 axis_cross。",
                )
            previous_directions = screen_direction_map(previous)
            current_directions = screen_direction_map(current)
            update_keys = {
                (clean_text(item.get("entity")), clean_text(item.get("field")))
                for item in as_list(current.get("continuity_updates"))
                if isinstance(item, dict)
            }
            for key in sorted(previous_directions.keys() & current_directions.keys()):
                if not directions_are_opposite(previous_directions[key], current_directions[key]):
                    continue
                entity, kind = key
                update_fields = {"position", "facing", "eyeline", "presence"}
                has_update = any(candidate_entity == entity and field_name in update_fields for candidate_entity, field_name in update_keys)
                if not has_update and "screen_direction_break" not in current_exceptions:
                    result.error(
                        "SCREEN_DIRECTION_BREAK",
                        f"shot:{current.get('shot_id')}.continuity.screen_directions",
                        f"{entity} 的 {kind} 银幕方向反转缺少迁移或有理由例外。",
                    )
            previous_transition = as_dict(previous.get("transition_to_next")).get("type")
            if previous_transition == "action_cut":
                outgoing = as_dict(previous_continuity.get("action_match")).get("outgoing")
                incoming = as_dict(current_continuity.get("action_match")).get("incoming")
                if (not outgoing or outgoing != incoming) and "action_discontinuity" not in current_exceptions:
                    result.error(
                        "ACTION_MATCH",
                        f"shot:{current.get('shot_id')}.continuity.action_match.incoming",
                        "action_cut 必须让前镜 outgoing 与后镜 incoming 完全一致。",
                    )


def iter_shot_execution_strings(shot: dict[str, Any]) -> list[tuple[str, str]]:
    output: list[tuple[str, str]] = []
    camera = as_dict(shot.get("camera"))
    for key in ("shot_size", "angle", "position", "composition", "movement", "start_frame", "end_frame"):
        value = camera.get(key)
        if isinstance(value, str):
            output.append((f"camera.{key}", value))
    for index, item in enumerate(as_list(shot.get("blocking"))):
        if not isinstance(item, dict):
            continue
        for key in ("start_position", "action", "end_position", "facing", "eyeline"):
            value = item.get(key)
            if isinstance(value, str):
                output.append((f"blocking[{index}].{key}", value))
    for index, value in enumerate(
        as_list(as_dict(shot.get("performance")).get("visible_behavior"))
    ):
        if isinstance(value, str):
            output.append((f"performance.visible_behavior[{index}]", value))
    for index, value in enumerate(as_list(shot.get("environment_behavior"))):
        if isinstance(value, str):
            output.append((f"environment_behavior[{index}]", value))
    for index, passage in enumerate(as_list(shot.get("execution_passages"))):
        if isinstance(passage, dict) and isinstance(passage.get("text"), str):
            output.append((f"execution_passages[{index}].text", passage["text"]))
    execution_text = shot.get("execution_text")
    if isinstance(execution_text, str):
        output.append(("execution_text", execution_text))
    rendered = shot.get("rendered_shot_description")
    if isinstance(rendered, str):
        output.append(("rendered_shot_description", rendered))
    return output


def detect_repeating_period(values: list[str], *, minimum_repeats: int = 3) -> int | None:
    if len(values) < 6:
        return None
    for period in range(2, min(6, len(values) // minimum_repeats) + 1):
        comparable = len(values) - period
        if comparable <= 0:
            continue
        matches = sum(values[index] == values[index - period] for index in range(period, len(values)))
        if matches / comparable >= 0.85:
            return period
    return None


def validate_scene_entry_execution(
    data: dict[str, Any],
    shots: list[dict[str, Any]],
    result: ValidationResult,
) -> None:
    first_shots: dict[str, dict[str, Any]] = {}
    for shot in shots:
        scene_id = clean_text(shot.get("scene_id"))
        if scene_id and scene_id not in first_shots:
            first_shots[scene_id] = shot
    for scene_index, scene in enumerate(as_list(data.get("scenes"))):
        if not isinstance(scene, dict):
            continue
        scene_id = clean_text(scene.get("scene_id"))
        first_shot = first_shots.get(scene_id)
        if not first_shot:
            continue
        entry = as_dict(as_dict(scene.get("directing_plan")).get("entry_strategy"))
        mode = clean_text(entry.get("mode"))
        camera = as_dict(first_shot.get("camera"))
        position = clean_text(camera.get("position"))
        framing_mode = clean_text(camera.get("framing_mode"))
        primary_subjects = [
            item
            for item in as_list(camera.get("primary_subjects"))
            if isinstance(item, str) and item.strip()
        ]
        sizes = clean_text(camera.get("shot_size")).split("→")
        matched = True
        if mode == "spatial_establish":
            matched = framing_mode == "environment" or any(
                size in {"大全景", "全景", "中远景"} for size in sizes
            )
        elif mode == "relational_entry":
            matched = framing_mode in {"two_shot", "multi_shot", "continuous_reframe"} or len(
                primary_subjects
            ) >= 2
        elif mode == "character_entry":
            matched = (
                framing_mode in {"single", "over_shoulder"}
                and bool(primary_subjects)
            ) or any(
                size in {"中景", "中近景", "近景", "特写", "大特写"}
                for size in sizes
            )
        elif mode == "subjective_entry":
            matched = framing_mode == "subjective"
        elif mode == "deliberate_withhold":
            matched = bool(as_list(entry.get("withheld_information")))
        if mode in ENTRY_STRATEGY_MODES and not matched:
            result.error(
                "SCENE_ENTRY_STRATEGY_MISMATCH",
                f"$.scenes[{scene_index}].directing_plan.entry_strategy",
                f"场景首镜 `{first_shot.get('shot_id')}` 未兑现已确认的 {mode} 入口模式。",
            )
        if "后排中央" in position and not any(
            term in clean_text(entry.get("reason"))
            for term in ("关系", "疏离", "压迫", "隐藏", "延迟", "主观", "视线")
        ):
            result.error(
                "MOVING_CAR_REAR_CENTER_DEFAULT",
                f"shot:{first_shot.get('shot_id')}.camera.position",
                "后排中央不能作为移动汽车场景的通用入口；必须在已确认 entry_strategy 中说明人物关系、疏离、压迫或信息隐藏收益。",
            )


def validate_quality_audits(
    data: dict[str, Any],
    *,
    locked_text: str,
    fact_lookup: dict[str, dict[str, Any]],
    result: ValidationResult,
) -> None:
    shots = [shot for shot in as_list(data.get("shots")) if isinstance(shot, dict)]
    validate_scene_entry_execution(data, shots, result)
    scene_headers: dict[str, list[str]] = {}
    for shot in shots:
        header = clean_text(shot.get("rendered_shot_description")).splitlines()
        if header:
            scene_headers.setdefault(clean_text(shot.get("scene_id")), []).append(
                header[0]
            )
    for scene_id, headers in scene_headers.items():
        if len(headers) >= 3 and len(set(headers)) == 1:
            result.error(
                "CAMERA_PREFIX_SCENE_REPETITION",
                f"scene:{scene_id}.shots",
                "整场镜头重复同一 camera 前缀，必须逐镜重新完成观看与 DOP 设计。",
            )
    if len(shots) >= 8:
        shot_sizes = [
            clean_text(as_dict(shot.get("camera")).get("shot_size")) for shot in shots
        ]
        period = detect_repeating_period(shot_sizes)
        if period is not None:
            result.warn(
                "SHOT_SIZE_PERIODIC_CYCLE",
                "$.shots",
                f"景别序列呈现周期 {period} 的机械循环，请回到剧情节拍和观察位置检查。",
            )
        compositions = [
            clean_text(as_dict(shot.get("camera")).get("composition")) for shot in shots
        ]
        composition_frequencies: dict[str, int] = {}
        for composition in compositions:
            if composition:
                composition_frequencies[composition] = (
                    composition_frequencies.get(composition, 0) + 1
                )
        if composition_frequencies:
            repeated_composition, count = max(
                composition_frequencies.items(), key=lambda item: item[1]
            )
            if count / len(shots) >= 0.50:
                result.warn(
                    "CAMERA_TEMPLATE_REPETITION",
                    "$.shots[*].camera.composition",
                    f"{count}/{len(shots)} 镜重复同一构图模板：{repeated_composition}",
                )
    for shot_index, shot in enumerate(shots):
        for field_path, value in iter_shot_execution_strings(shot):
            for phrase in PLACEHOLDER_PHRASES:
                if phrase in value:
                    result.error(
                        "TEMPLATE_PLACEHOLDER",
                        f"$.shots[{shot_index}].{field_path}",
                        f"检测到模板占位语：{phrase}。",
                    )
    for index, (previous, current) in enumerate(zip(shots, shots[1:]), start=1):
        if previous.get("scene_id") != current.get("scene_id"):
            continue
        previous_dialogue = [
            fact_lookup.get(fact_id, {})
            for fact_id in as_list(previous.get("covered_fact_ids"))
            if fact_lookup.get(fact_id, {}).get("type") == "dialogue"
        ]
        current_dialogue = [
            fact_lookup.get(fact_id, {})
            for fact_id in as_list(current.get("covered_fact_ids"))
            if fact_lookup.get(fact_id, {}).get("type") == "dialogue"
        ]
        if len(previous_dialogue) == 1 and len(current_dialogue) == 1:
            left = previous_dialogue[0]
            right = current_dialogue[0]
            left_ranges = span_coordinates(left.get("source_spans"), locked_text)
            right_ranges = span_coordinates(right.get("source_spans"), locked_text)
            if (
                left.get("speaker") == right.get("speaker")
                and len(left_ranges) == 1
                and len(right_ranges) == 1
                and left_ranges[0][1] <= right_ranges[0][0]
            ):
                separator = locked_text[left_ranges[0][1] : right_ranges[0][0]]
                if "\n" not in separator and re.fullmatch(r"[\s，、：；,;]*", separator):
                    result.error(
                        "DIALOGUE_PUNCTUATION_SPLIT",
                        f"$.shots[{index - 1}:{index + 1}]",
                        "同一人物同一句对白不得因逗号、顿号、冒号或分号拆成相邻两镜。",
                    )


def validate_data(data: dict[str, Any]) -> ValidationResult:
    result = ValidationResult()
    validate_json_values(data, result)
    if any(issue.code == "UNICODE_SURROGATE" for issue in result.errors):
        return result
    validate_forbidden_keys(data, result)
    validate_contract_identity(data, result)
    locked_text = validate_source(data, result)
    validate_gate_1_material(data, result)
    scenes, scene_order, initial_states, entity_names, axis_ids = validate_scenes(data, result)
    beats, facts, fact_beat, fact_order = validate_beats(
        data,
        locked_text,
        scenes,
        entity_names,
        result,
    )
    screen_events = validate_screen_events(
        data,
        locked_text=locked_text,
        scenes=scenes,
        beat_lookup=beats,
        fact_lookup=facts,
        fact_beat=fact_beat,
        result=result,
    )
    emotion_arcs = validate_emotion_arcs(data, beats, facts, scenes, result)
    plan_info = validate_shot_plan(
        data,
        locked_text=locked_text,
        scenes=scenes,
        beat_lookup=beats,
        fact_lookup=facts,
        screen_event_lookup=screen_events,
        result=result,
    )
    validate_performance_chains(
        data,
        locked_text=locked_text,
        scenes=scenes,
        fact_lookup=facts,
        fact_beat=fact_beat,
        fact_order=fact_order,
        beat_lookup=beats,
        plan_info=plan_info,
        result=result,
    )
    validate_confirmations(data, result)
    _, shots_by_scene, _ = validate_shots(
        data,
        locked_text,
        scenes,
        scene_order,
        entity_names,
        axis_ids,
        beats,
        facts,
        fact_beat,
        fact_order,
        emotion_arcs,
        plan_info,
        result,
    )
    validate_scene_continuity(
        data,
        scenes,
        scene_order,
        initial_states,
        shots_by_scene,
        result,
    )
    validate_quality_audits(
        data,
        locked_text=locked_text,
        fact_lookup=facts,
        result=result,
    )
    return result


def validate_gate_1_confirmation_for_review(
    data: dict[str, Any],
    result: ValidationResult,
) -> None:
    confirmations = as_dict(data.get("confirmations"))
    review_copy = copy.deepcopy(data)
    try:
        gate_2_digest = stage_digest(review_copy, 2)
    except (ValueError, UnicodeContractError):
        gate_2_digest = ""
    review_copy["confirmations"] = {
        "gate_1": copy.deepcopy(confirmations.get("gate_1")),
        "gate_2": {
            "status": "confirmed",
            "stage_digest": gate_2_digest,
            "confirmation_order": 2,
            "notes": "Gate 2 只读复核占位，不写回输入。",
        },
    }
    validate_confirmations(review_copy, result)


def review_gate_2_data(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], ValidationResult, str | None]:
    review_input = copy.deepcopy(raw)
    review_input.setdefault("shots", [])
    review_input.setdefault("content_hash", "")
    data = prepare_data(review_input)
    result = ValidationResult()
    validate_json_values(data, result)
    if any(issue.code == "UNICODE_SURROGATE" for issue in result.errors):
        return data, result, None
    validate_forbidden_keys(data, result)
    validate_contract_identity(data, result)
    locked_text = validate_source(data, result)
    validate_gate_1_material(data, result)
    scenes, _, _, entity_names, _ = validate_scenes(data, result)
    beats, facts, fact_beat, fact_order = validate_beats(
        data,
        locked_text,
        scenes,
        entity_names,
        result,
    )
    screen_events = validate_screen_events(
        data,
        locked_text=locked_text,
        scenes=scenes,
        beat_lookup=beats,
        fact_lookup=facts,
        fact_beat=fact_beat,
        result=result,
    )
    validate_emotion_arcs(data, beats, facts, scenes, result)
    plan_info = validate_shot_plan(
        data,
        locked_text=locked_text,
        scenes=scenes,
        beat_lookup=beats,
        fact_lookup=facts,
        screen_event_lookup=screen_events,
        review_mode=True,
        result=result,
    )
    validate_performance_chains(
        data,
        locked_text=locked_text,
        scenes=scenes,
        fact_lookup=facts,
        fact_beat=fact_beat,
        fact_order=fact_order,
        beat_lookup=beats,
        plan_info=plan_info,
        result=result,
    )
    validate_gate_1_confirmation_for_review(data, result)
    digest: str | None = None
    try:
        digest = stage_digest(data, 2)
    except (ValueError, UnicodeContractError):
        result.error(
            "GATE_2_DIGEST_INPUT",
            "$.shot_plan",
            "当前 Gate 2 内容无法形成 canonical digest。",
        )
    return data, result, digest


def clean_source_fragment(value: str) -> str:
    lines = value.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    output: list[str] = []
    previous_blank = False
    for line in lines:
        stripped = line.strip()
        if stripped and any(pattern.search(stripped) for pattern in SOURCE_METADATA_PATTERNS):
            continue
        if not stripped:
            if output and not previous_blank:
                output.append("")
            previous_blank = True
            continue
        output.append(stripped)
        previous_blank = False
    while output and not output[-1]:
        output.pop()
    return "\n".join(output)


def source_paragraph(
    shot: dict[str, Any],
    locked_text: str,
    fact_lookup: dict[str, dict[str, Any]],
    fact_beat: dict[str, str],
) -> str:
    grouped: dict[str, list[tuple[int, int, str]]] = {}
    seen_coordinates: set[tuple[int, int]] = set()
    for fact_id in as_list(shot.get("covered_fact_ids")):
        fact = fact_lookup.get(str(fact_id))
        if not fact:
            continue
        beat_id = fact_beat.get(str(fact_id), "")
        for start, end in span_coordinates(fact.get("source_spans"), locked_text):
            if (start, end) in seen_coordinates:
                continue
            seen_coordinates.add((start, end))
            fragment = clean_source_fragment(locked_text[start:end])
            if fragment:
                grouped.setdefault(beat_id, []).append((start, end, fragment))
    paragraphs: list[str] = []
    for beat_id in as_list(shot.get("beat_ids")):
        fragments = sorted(grouped.get(str(beat_id), []), key=lambda item: (item[0], item[1]))
        if not fragments:
            continue
        body = "\n\n".join(fragment for _, _, fragment in fragments)
        paragraphs.append(f"{beat_id}～{body}")
    return "\n\n".join(paragraphs).strip()


def storyboard_rows(data: dict[str, Any]) -> list[list[Any]]:
    locked_value = as_dict(data.get("source")).get("locked_text")
    locked_text = locked_value if isinstance(locked_value, str) else ""
    scene_names = {
        clean_text(scene.get("scene_id")): clean_text(scene.get("scene"))
        for scene in as_list(data.get("scenes"))
        if isinstance(scene, dict)
    }
    fact_lookup: dict[str, dict[str, Any]] = {}
    fact_beat: dict[str, str] = {}
    for beat in as_list(data.get("beats")):
        if not isinstance(beat, dict):
            continue
        beat_id = clean_text(beat.get("beat_id"))
        for fact in as_list(beat.get("facts")):
            if not isinstance(fact, dict):
                continue
            fact_id = clean_text(fact.get("fact_id"))
            if fact_id:
                fact_lookup[fact_id] = fact
                fact_beat[fact_id] = beat_id
    rows: list[list[Any]] = []
    for shot in as_list(data.get("shots")):
        if not isinstance(shot, dict):
            continue
        rows.append(
            [
                shot.get("shot_id", ""),
                scene_names.get(clean_text(shot.get("scene_id")), ""),
                source_paragraph(shot, locked_text, fact_lookup, fact_beat),
                shot.get("duration_seconds", ""),
                shot.get("rendered_shot_description", ""),
                shot.get("notes", ""),
            ]
        )
    return rows


def markdown_cell(value: Any) -> str:
    text = str(value)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("|", "&#124;")
    return text.replace("\n", "<br>")


def markdown_text(data: dict[str, Any]) -> str:
    lines = [
        "# 导演分镜",
        "",
        f"- 合同：{CONTRACT_NAME}/{CONTRACT_VERSION}",
        f"- 项目：{data.get('project_id', '')}",
        f"- 内容哈希：{data.get('content_hash', '')}",
        "",
        "| " + " | ".join(markdown_cell(item) for item in HEADERS) + " |",
        "| " + " | ".join("---" for _ in HEADERS) + " |",
    ]
    for row in storyboard_rows(data):
        lines.append("| " + " | ".join(markdown_cell(item) for item in row) + " |")
    return "\n".join(lines) + "\n"


def decode_markdown_cell(value: str) -> str:
    if value.startswith(" "):
        value = value[1:]
    if value.endswith(" "):
        value = value[:-1]
    return html.unescape(value.replace("<br>", "\n"))


def read_markdown_rows(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [decode_markdown_cell(cell) for cell in line[1:-1].split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def column_name(index: int) -> str:
    output = ""
    value = index
    while value:
        value, remainder = divmod(value - 1, 26)
        output = chr(65 + remainder) + output
    return output


def xml_text(value: Any) -> str:
    return xml_escape(str(value), {'"': "&quot;"})


def xlsx_cell(reference: str, value: Any, style: int = 0) -> str:
    style_attribute = f' s="{style}"' if style else ""
    if is_json_integer(value):
        return f'<c r="{reference}"{style_attribute}><v>{value}</v></c>'
    return (
        f'<c r="{reference}" t="inlineStr"{style_attribute}>'
        f'<is><t xml:space="preserve">{xml_text(value)}</t></is></c>'
    )


def estimated_excel_row_height(row: list[Any], widths: list[int]) -> int:
    maximum_lines = 1
    for value, width in zip(row, widths):
        text = str(value)
        visual_lines = 0
        for line in text.splitlines() or [""]:
            display_units = sum(2 if ord(character) > 127 else 1 for character in line)
            visual_lines += max(1, math.ceil(display_units / max(width * 2, 1)))
        maximum_lines = max(maximum_lines, visual_lines)
    return min(300, max(42, 18 * maximum_lines + 12))


def worksheet_xml(rows: list[list[Any]]) -> bytes:
    all_rows = [HEADERS, *rows]
    widths = [10, 24, 46, 16, 90, 38]
    row_xml: list[str] = []
    for row_index, row in enumerate(all_rows, start=1):
        height = 28 if row_index == 1 else estimated_excel_row_height(row, widths)
        cells = [
            xlsx_cell(f"{column_name(column_index)}{row_index}", value, 1 if row_index == 1 else 0)
            for column_index, value in enumerate(row, start=1)
        ]
        row_xml.append(
            f'<row r="{row_index}" ht="{height}" customHeight="1">'
            + "".join(cells)
            + "</row>"
        )
    cols = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )
    last_row = len(all_rows)
    payload = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        "</sheetView></sheetViews>"
        f"<cols>{cols}</cols>"
        "<sheetData>"
        + "".join(row_xml)
        + "</sheetData>"
        f'<autoFilter ref="A1:F{last_row}"/>'
        "</worksheet>"
    )
    return encode_utf8(payload, path="$.xlsx.worksheet")


def xlsx_parts(data: dict[str, Any]) -> list[tuple[str, bytes]]:
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="分镜表" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        "</Relationships>"
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Arial"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Arial"/></font></fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF263238"/>'
        '<bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" '
        'applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" '
        'applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        "</cellXfs>"
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )
    return [
        ("[Content_Types].xml", encode_utf8(content_types, path="$.xlsx.content_types")),
        ("_rels/.rels", encode_utf8(root_rels, path="$.xlsx.root_relationships")),
        ("xl/workbook.xml", encode_utf8(workbook, path="$.xlsx.workbook")),
        (
            "xl/_rels/workbook.xml.rels",
            encode_utf8(workbook_rels, path="$.xlsx.workbook_relationships"),
        ),
        ("xl/styles.xml", encode_utf8(styles, path="$.xlsx.styles")),
        ("xl/worksheets/sheet1.xml", worksheet_xml(storyboard_rows(data))),
    ]


def write_deterministic_xlsx(path: Path, data: dict[str, Any]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, payload in xlsx_parts(data):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, payload)


def read_xlsx_rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path, "r") as archive:
        root = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    namespace = {"m": XLSX_NAMESPACE}
    rows: list[list[str]] = []
    for row in root.findall(".//m:sheetData/m:row", namespace):
        values: list[str] = []
        for cell in row.findall("m:c", namespace):
            if cell.find("m:f", namespace) is not None:
                raise ValueError("Excel 中不得包含公式单元格。")
            cell_type = cell.get("t")
            if cell_type == "inlineStr":
                value = "".join(
                    node.text or "" for node in cell.findall(".//m:is//m:t", namespace)
                )
            else:
                node = cell.find("m:v", namespace)
                value = node.text if node is not None and node.text is not None else ""
            values.append(value)
        rows.append(values)
    return rows


def make_report(data: dict[str, Any], result: ValidationResult) -> dict[str, Any]:
    durations = [
        shot.get("duration_seconds")
        for shot in as_list(data.get("shots"))
        if isinstance(shot, dict) and is_json_integer(shot.get("duration_seconds"), 1)
    ]
    declared_hash = data.get("content_hash")
    declared_content_hash = (
        declared_hash
        if isinstance(declared_hash, str) and HASH_PATTERN.fullmatch(declared_hash)
        else None
    )
    locked_text_hash = as_dict(data.get("source")).get("locked_text_hash")
    if not isinstance(locked_text_hash, str) or not HASH_PATTERN.fullmatch(
        locked_text_hash
    ):
        locked_text_hash = None
    shot_plan = as_dict(data.get("shot_plan"))
    total_duration = sum(int(value) for value in durations)
    shot_count = len(as_list(data.get("shots")))
    director_prefixes = (
        "SCREEN_EVENT",
        "VIEWING_DECISION",
        "PLAN_UNIT_SCREEN_EVENT",
        "VISUAL_PLAN",
        "SPATIAL_STRATEGY",
        "MOVEMENT_PLAN",
        "SHOT_PHASE",
        "SHOT_VISUAL",
        "CAMERA",
        "DIALOGUE_VOICE",
        "DIALOGUE_PLAN_CAMERA",
        "DIALOGUE_HANDOFF",
        "NONCUT",
        "ORDINARY_SHOT",
        "LONG_TAKE_DESIGN",
        "PROTECTED_PROCESS",
        "CONTINUITY",
        "EXECUTION",
        "RENDERED_DESCRIPTION",
    )
    director_errors = [
        issue for issue in result.errors if issue.code.startswith(director_prefixes)
    ]
    contract_errors = [
        issue for issue in result.errors if issue not in director_errors
    ]
    contract_status = "FAIL" if contract_errors else "PASS"
    director_readiness = "BLOCKED" if director_errors else "READY"
    return {
        "contract": f"{CONTRACT_NAME}/{CONTRACT_VERSION}",
        "contract_status": contract_status,
        "director_readiness": director_readiness,
        "status": result.status,
        "content_hash": declared_content_hash,
        "locked_text_hash": locked_text_hash,
        "errors": [issue.as_dict() for issue in result.errors],
        "warnings": [issue.as_dict() for issue in result.warnings],
        "visual_design": visual_distribution_summary(data),
        "gate_2_rule_revision": GATE_2_RULE_REVISION,
        "cut_atomicity": cut_atomicity_metrics(data),
        "summary": {
            "scenes": len(as_list(data.get("scenes"))),
            "beats": len(as_list(data.get("beats"))),
            "shots": shot_count,
            "duration_seconds": total_duration,
            "planned_shots": shot_plan.get("planned_shot_count", 0),
            "planned_edit_points": shot_plan.get("planned_edit_point_count", 0),
        },
    }


def expected_table_rows(data: dict[str, Any]) -> list[list[str]]:
    return [[str(value) for value in HEADERS]] + [
        [str(value) for value in row] for row in storyboard_rows(data)
    ]


def compare_markdown(data: dict[str, Any], path: Path, result: ValidationResult) -> None:
    if not path.exists():
        result.error("MARKDOWN_MISSING", str(path), "Markdown 文件不存在。")
        return
    try:
        rows = read_markdown_rows(path)
    except (OSError, UnicodeError) as exc:
        result.error("MARKDOWN_READ", str(path), f"Markdown 无法读取：{exc}")
        return
    if rows != expected_table_rows(data):
        result.error("MARKDOWN_MISMATCH", str(path), "Markdown 六列表与 JSON 派生结果不一致。")


def compare_excel(data: dict[str, Any], path: Path, result: ValidationResult) -> None:
    if not path.exists():
        result.error("EXCEL_MISSING", str(path), "Excel 文件不存在。")
        return
    try:
        rows = read_xlsx_rows(path)
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError, ValueError) as exc:
        result.error("EXCEL_READ", str(path), f"Excel 无法读取或结构非法：{exc}")
        return
    if rows != expected_table_rows(data):
        result.error("EXCEL_MISMATCH", str(path), "Excel 六列表与 JSON 派生结果不一致。")


def compare_report(
    expected_report: dict[str, Any],
    path: Path,
    result: ValidationResult,
) -> None:
    if not path.exists():
        result.error("REPORT_MISSING", str(path), "validation report 不存在。")
        return
    try:
        actual = load_json(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        result.error("REPORT_READ", str(path), f"validation report 无法读取：{exc}")
        return
    if actual != expected_report:
        result.error("REPORT_MISMATCH", str(path), "validation report 与重新计算结果不一致。")


def output_filenames(data: dict[str, Any]) -> dict[str, str]:
    slug = clean_text(as_dict(data.get("source")).get("delivery_slug"))
    return {
        key: f"{slug}-{suffix}"
        for key, suffix in OUTPUT_SUFFIXES.items()
    }


def output_paths(output_dir: Path, data: dict[str, Any]) -> dict[str, Path]:
    return {
        key: output_dir / filename
        for key, filename in output_filenames(data).items()
    }


def temporary_sibling(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=f".tmp{path.suffix}",
        dir=path.parent,
    )
    os.close(descriptor)
    return Path(name)


def write_temp_delivery(
    data: dict[str, Any],
    report: dict[str, Any],
    temporary: dict[str, Path],
) -> None:
    temporary["json"].write_bytes(json_bytes(data))
    temporary["markdown"].write_bytes(
        encode_utf8(markdown_text(data), path="$.delivery.markdown")
    )
    write_deterministic_xlsx(temporary["excel"], data)
    temporary["report"].write_bytes(json_bytes(report))


def self_validate_temporary(
    data: dict[str, Any],
    report: dict[str, Any],
    temporary: dict[str, Path],
) -> None:
    result = ValidationResult()
    try:
        round_trip = load_json(temporary["json"])
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"临时 shot_data 回读失败：{exc}") from exc
    if round_trip != data:
        raise RuntimeError("临时 shot_data 回读内容不一致。")
    semantic = validate_data(round_trip)
    if semantic.errors:
        messages = " | ".join(issue.message for issue in semantic.errors)
        raise RuntimeError(f"临时 shot_data 校验失败：{messages}")
    if make_report(round_trip, semantic) != report:
        raise RuntimeError("临时 report 与语义校验结果不一致。")
    compare_markdown(round_trip, temporary["markdown"], result)
    compare_excel(round_trip, temporary["excel"], result)
    compare_report(report, temporary["report"], result)
    if result.errors:
        messages = " | ".join(issue.message for issue in result.errors)
        raise RuntimeError(f"临时交付文件自检失败：{messages}")


def restore_bytes(path: Path, payload: bytes) -> None:
    temporary = temporary_sibling(path)
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_delivery(
    data: dict[str, Any],
    report: dict[str, Any],
    output_dir: Path,
) -> dict[str, Path]:
    paths = output_paths(output_dir, data)
    resolved = [path.resolve(strict=False) for path in paths.values()]
    if len(set(resolved)) != len(resolved):
        raise ValueError("四个输出路径必须互不相同。")
    existing_json = sorted(output_dir.glob("*-shot-data.json"))
    if any(path != paths["json"] for path in existing_json):
        raise ValueError("输出目录已存在其他命名前缀的正式交付；请使用独立输出目录。")
    legacy_names = {
        "shot_data.json",
        "storyboard.md",
        "storyboard.xlsx",
        "storyboard_validation.json",
    }
    if any((output_dir / name).exists() for name in legacy_names):
        raise ValueError("输出目录含旧版固定文件名；2.5.2 必须使用带剧本前缀的新目录。")
    temporary = {key: temporary_sibling(path) for key, path in paths.items()}
    try:
        write_temp_delivery(data, report, temporary)
        self_validate_temporary(data, report, temporary)
        backups = {
            key: path.read_bytes() if path.exists() else None for key, path in paths.items()
        }
        committed: list[str] = []
        try:
            for key in ("json", "markdown", "excel", "report"):
                os.replace(temporary[key], paths[key])
                committed.append(key)
        except Exception:
            for key in reversed(committed):
                backup = backups[key]
                if backup is None:
                    paths[key].unlink(missing_ok=True)
                else:
                    restore_bytes(paths[key], backup)
            raise
    finally:
        for path in temporary.values():
            path.unlink(missing_ok=True)
    return paths


def build_delivery(input_path: Path, output_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Path]]:
    raw = load_json(input_path)
    data = prepare_data(raw)
    result = validate_data(data)
    report = make_report(data, result)
    if (
        report["contract_status"] != "PASS"
        or report["director_readiness"] != "READY"
        or result.errors
    ):
        raise ValidationFailure(report)
    paths = atomic_write_delivery(data, report, output_dir)
    return data, report, paths


def validate_delivery(output_dir: Path) -> tuple[dict[str, Any] | None, ValidationResult]:
    result = ValidationResult()
    candidates = sorted(output_dir.glob("*-shot-data.json"))
    if len(candidates) != 1:
        result.error(
            "DELIVERY_JSON_DISCOVERY",
            str(output_dir),
            "输出目录必须且只能包含一个 `<delivery-slug>-shot-data.json`。",
        )
        return None, result
    json_path = candidates[0]
    try:
        data = load_json(json_path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        result.error("JSON_READ", str(json_path), f"shot-data 无法读取：{exc}")
        return None, result
    paths = output_paths(output_dir, data)
    if json_path != paths["json"]:
        result.error(
            "DELIVERY_FILENAME",
            str(json_path),
            "JSON 文件名必须与 source.delivery_slug 完全一致。",
        )
    semantic = validate_data(data)
    result.errors.extend(semantic.errors)
    result.warnings.extend(semantic.warnings)
    expected_report = make_report(data, semantic)
    compare_markdown(data, paths["markdown"], result)
    compare_excel(data, paths["excel"], result)
    compare_report(expected_report, paths["report"], result)
    return data, result


class ValidationFailure(RuntimeError):
    def __init__(self, report: dict[str, Any]):
        super().__init__("storyboard validation failed")
        self.report = report


def print_report(report: dict[str, Any], stream: Any = sys.stdout) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stream)


def safe_exception_text(exc: BaseException) -> str:
    return str(exc).encode("utf-8", errors="backslashreplace").decode("utf-8")


def diagnostic_report(code: str, path: str, message: str) -> dict[str, Any]:
    result = ValidationResult()
    result.error(code, path, message)
    return make_report({}, result)


def command_build(args: argparse.Namespace) -> int:
    try:
        _, report, paths = build_delivery(Path(args.input), Path(args.output_dir))
    except ValidationFailure as exc:
        print_report(exc.report, sys.stderr)
        return 1
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        report = diagnostic_report(
            "BUILD_INPUT_READ",
            str(args.input),
            f"draft JSON 无法读取或结构非法：{safe_exception_text(exc)}",
        )
        print_report(report, sys.stderr)
        return 1
    output = {
        "status": report["status"],
        "contract_status": report["contract_status"],
        "director_readiness": report["director_readiness"],
        "content_hash": report["content_hash"],
        "files": {key: str(path) for key, path in paths.items()},
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_validate(args: argparse.Namespace) -> int:
    data, result = validate_delivery(Path(args.output_dir))
    if data is None:
        report = make_report({}, result)
    else:
        report = make_report(data, result)
    print_report(report, sys.stderr if result.errors else sys.stdout)
    if result.errors:
        return 1
    return 2 if result.warnings else 0


def command_review_gate_2(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    try:
        raw = load_json(input_path)
        if not isinstance(raw, dict):
            raise ValueError("Gate 2 draft 顶层必须是 JSON 对象。")
        data, result, digest = review_gate_2_data(raw)
    except ValidationFailure as exc:
        print_report(exc.report, sys.stderr)
        return 1
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "contract": f"{CONTRACT_NAME}/{CONTRACT_VERSION}",
            "contract_status": "FAIL",
            "director_readiness": "BLOCKED",
            "status": "BLOCKED",
            "gate_2_digest": None,
            "errors": [
                Issue(
                    code="GATE_2_INPUT_READ",
                    path=str(input_path),
                    message=f"Gate 2 draft 无法读取或结构非法：{safe_exception_text(exc)}",
                ).as_dict()
            ],
            "warnings": [],
            "visual_design": visual_distribution_summary({}),
        }
        print_report(report, sys.stderr)
        return 1
    status = (
        "BLOCKED"
        if result.errors
        else "REVIEW_REQUIRED"
        if result.warnings
        else "READY"
    )
    report = make_report(data, result)
    report["status"] = status
    report["gate_2_digest"] = digest
    print_report(report, sys.stderr if result.errors else sys.stdout)
    if result.errors:
        return 1
    return 2 if result.warnings else 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build four deterministic delivery files")
    build.add_argument("--input", required=True, help="draft shot-data JSON")
    build.add_argument("--output-dir", required=True, help="directory for the four slug-prefixed files")
    build.set_defaults(func=command_build)
    validate = subparsers.add_parser("validate", help="validate the four slug-prefixed delivery files")
    validate.add_argument("--output-dir", required=True, help="directory containing one delivery set")
    validate.set_defaults(func=command_validate)
    review_gate_2 = subparsers.add_parser(
        "review-gate-2",
        help="review the visible Gate 2 visual plan without writing files or confirming it",
    )
    review_gate_2.add_argument("--input", required=True, help="Gate 2 draft shot-data JSON")
    review_gate_2.set_defaults(func=command_review_gate_2)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        report = diagnostic_report(
            "CLI_FAILURE",
            "$",
            f"命令未完成：{safe_exception_text(exc)}",
        )
        print_report(report, sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
