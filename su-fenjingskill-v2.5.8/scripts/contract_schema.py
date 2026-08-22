#!/usr/bin/env python3
"""Machine-authoritative structural schema for shot-data/2.5.8.

Domain meaning remains in references/*.md.  This module owns public object keys,
required/optional structure, and deterministic JSON Schema export so prose and
the validator do not maintain competing structural definitions.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


CONTRACT_NAME = "shot-data"
CONTRACT_VERSION = "2.5.8"
SOURCE_SKILL = "su-fenjingskill"
SOURCE_SKILL_VERSION = "2.5.8"
GATE_2_RULE_REVISION = "2.5.8-rhythm-integrity-r1"
LEGACY_CONTRACT_VERSIONS = {"2.5.3", "2.5.4"}
LEGACY_CONTRACT_VERSION = "2.5.3"
PREVIOUS_CONTRACT_VERSION = "2.5.4"

TOP_LEVEL_KEYS = {
    "contract_name",
    "contract_version",
    "source_skill",
    "source_skill_version",
    "project_id",
    "content_hash",
    "duration_policy",
    "rhythm_policy",
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
SOURCE_SPAN_KEYS = {"start", "end", "text_hash"}
DURATION_POLICY_KEYS = {
    "zh_chars_per_second",
    "en_words_per_second",
    "comma_pause_seconds",
    "sentence_pause_seconds",
    "ellipsis_dash_pause_seconds",
}
RHYTHM_POLICY_KEYS = {
    "min_sample_shots",
    "micro_shot_seconds",
    "short_shot_seconds",
    "micro_shot_density_review_ratio",
    "short_shot_density_review_ratio",
    "short_shot_cluster_count",
    "ordinary_shot_max_seconds",
    "hard_max_shot_seconds",
    "long_take_density_review_ratio",
    "floor_lock_review_ratio",
    "mechanical_pattern_review_ratio",
    "template_collapse_ratio",
    "scene_variance_review_ratio",
    "scene_overrun_block_ratio",
}
DEFAULT_RHYTHM_POLICY = {
    "min_sample_shots": 8,
    "micro_shot_seconds": 1,
    "short_shot_seconds": 2,
    "micro_shot_density_review_ratio": 0.10,
    "short_shot_density_review_ratio": 0.20,
    "short_shot_cluster_count": 3,
    "ordinary_shot_max_seconds": 10,
    "hard_max_shot_seconds": 19,
    "long_take_density_review_ratio": 0.20,
    "floor_lock_review_ratio": 0.90,
    "mechanical_pattern_review_ratio": 0.90,
    "template_collapse_ratio": 0.75,
    "scene_variance_review_ratio": 0.10,
    "scene_overrun_block_ratio": 0.50,
}

CONFIRMATION_KEYS = ("gate_1", "gate_2")
CONFIRMATION_ITEM_KEYS = {
    "status",
    "stage_digest",
    "confirmation_order",
    "notes",
}

SOURCE_REQUIRED_KEYS = {
    "input_kind",
    "boundary_lock",
    "scope",
    "delivery_slug",
    "locked_text",
    "locked_text_hash",
    "approved_corrections",
}
SOURCE_OPTIONAL_KEYS = {
    "dialogue_language_policy",
    "project_dialogue_language_policy",
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
PROJECT_LANGUAGE_POLICY_EXTRA_KEYS = {
    "scope",
    "exceptions_require_confirmation",
}

PROFILE_VALUE_KEYS = {
    "rhythm",
    "camera_energy",
    "visual_distance",
    "performance_focus",
    "space_strategy",
}
PROFILE_VALUES = {
    "rhythm": {"restrained", "balanced", "kinetic"},
    "camera_energy": {"static", "responsive", "assertive"},
    "visual_distance": {"observational", "intimate", "mixed"},
    "performance_focus": {"body", "face", "blocking", "ensemble", "mixed"},
    "space_strategy": {
        "establish_then_enter",
        "embedded_reveal",
        "subjective",
        "mixed",
    },
}
PROFILE_REQUIRED_KEYS = PROFILE_VALUE_KEYS | {
    "transition_language",
    "priorities",
    "natural_language_intent",
}

DIRECTING_PLAN_REQUIRED_KEYS = {
    "scene_objective",
    "progression",
    "pov_flow",
    "entry_strategy",
    "style_anchors",
    "duration_review",
    "rhythm_design",
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
STYLE_OPTION_KEYS = {"option_id", "label", "rationale", "profile"}
STYLE_ANCHOR_KEYS = {
    "style_anchor_id",
    "profile_basis",
    "scene_application",
    "avoidance",
}
STYLE_PROFILE_BASIS_KEYS = {"field", "value"}
DURATION_REVIEW_KEYS = {
    "source_target_seconds",
    "speech_floor_seconds",
    "action_reaction_floor_seconds",
    "minimum_playable_seconds",
    "planned_seconds",
    "variance_seconds",
    "variance_ratio",
    "unavoidable_overrun_seconds",
    "discretionary_extension_seconds",
    "resolution",
    "reason",
}
RHYTHM_DESIGN_KEYS = {"scene_pacing_intent", "sections"}
RHYTHM_SECTION_KEYS = {
    "rhythm_section_id",
    "plan_unit_ids",
    "tempo_role",
    "target_shot_duration_min_seconds",
    "target_shot_duration_max_seconds",
    "cut_density_intent",
    "reason",
}
CORRECTION_KEYS = {"from", "to", "reason"}
DIRECTOR_ANALYSIS_KEYS = {
    "narrative_function",
    "dramatic_turn",
    "pov_owner",
    "power_relation",
    "subtext",
    "directorial_intent",
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
SHOT_PLAN_KEYS = {
    "planned_shot_count",
    "planned_edit_point_count",
    "planned_total_duration_seconds",
    "planned_units",
    "viewing_decisions",
    "edit_points",
    "reorders",
    "visual_uniformity_reviews",
    "dialogue_playbacks",
    "rhythm_reviews",
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
    "duration_design",
}
PLAN_UNIT_OPTIONAL_KEYS = {
    "shot_form",
    "source_reuse",
    "dialogue_design",
    "long_take_design",
    "short_shot_design",
}
DURATION_DESIGN_KEYS = {
    "playback_segment_ids",
    "action_segments",
    "reaction_holds",
    "speech_min_seconds",
    "action_min_seconds",
    "reaction_hold_seconds",
    "overlap_mode",
    "minimum_total_seconds",
    "editorial_target_seconds",
    "pacing_role",
    "duration_rationale",
}
ACTION_TIMING_SEGMENT_KEYS = {
    "timing_segment_id",
    "screen_event_ids",
    "start_condition",
    "end_condition",
    "minimum_seconds",
    "overlap_group",
}
REACTION_HOLD_KEYS = {
    "reaction_hold_id",
    "screen_event_id",
    "character",
    "visible_change",
    "minimum_seconds",
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
    "dialogue_playback_segment_ids",
}
CUT_DESIGN_REQUIRED_KEYS = {"entry_trigger", "exit_trigger"}
CUT_DESIGN_OPTIONAL_KEYS = {"isolation_intent"}
DIALOGUE_DESIGN_REQUIRED_KEYS = {"speaker_sequence", "justification"}
DIALOGUE_DESIGN_OPTIONAL_KEYS = {
    "mode",
    "face_readable_speakers",
    "listener_reaction_characters",
    "axis_id",
}
SHORT_SHOT_DESIGN_KEYS = {
    "timing_intent",
    "viewing_value",
    "entry_trigger",
    "exit_trigger",
    "readability_reason",
}
LONG_TAKE_DESIGN_KEYS = {
    "reason",
    "supports",
    "protected_event_ids",
    "temporal_progression",
}
LONG_TAKE_PROGRESSION_KEYS = {
    "progression_id",
    "phase_order",
    "screen_event_ids",
    "start_condition",
    "visible_development",
    "end_condition",
    "duration_seconds",
}
RHYTHM_REVIEW_KEYS = {
    "review_id",
    "scope",
    "scene_id",
    "finding_code",
    "finding_value",
    "decision",
    "reason",
    "affected_plan_unit_ids",
}
DIALOGUE_PLAYBACK_KEYS = {
    "playback_id",
    "scene_id",
    "fact_id",
    "speech_min_seconds",
    "planned_playback_seconds",
    "segments",
}
DIALOGUE_PLAYBACK_SEGMENT_KEYS = {
    "playback_segment_id",
    "segment_order",
    "plan_unit_id",
    "text_start",
    "text_end",
    "unit_start_seconds",
    "planned_speech_seconds",
    "shot_delivery",
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
EDIT_POINT_REQUIRED_KEYS = {
    "edit_point_id",
    "after_plan_unit_id",
    "before_plan_unit_id",
    "source_spans",
    "trigger",
    "editorial_gain",
}
EDIT_POINT_OPTIONAL_KEYS = {"broken_performance_chain_ids"}
SOURCE_REUSE_KEYS = {"from_plan_unit_id", "reason", "justification"}
REORDER_KEYS = {"reorder_id", "plan_unit_ids", "source_spans", "reason"}
COVERAGE_EVIDENCE_KEYS = {"fact_id", "target_path", "evidence_quote"}

SOURCE_ANALYSIS_REQUIRED_KEYS = {"source_boundary", "source_constraints"}
SOURCE_ANALYSIS_OPTIONAL_KEYS = {
    "narrative_function",
    "dramatic_progression",
    "character_relations",
}
SCENE_REQUIRED_KEYS = {"scene_id", "scene", "reality_layer", "directing_plan"}
SCENE_OPTIONAL_KEYS = {
    "director_analysis",
    "initial_continuity",
    "axes",
    "inherits_from",
    "inherited_states",
}
AXIS_KEYS = {"axis_id", "axis_type", "endpoint_a", "endpoint_b"}
INITIAL_CONTINUITY_KEYS = {
    "characters",
    "props",
    "fixed_objects",
    "sound_sources",
    "reality_layer",
}
INHERITED_STATE_KEYS = {"entity_type", "entity", "field"}
INHERITED_STATE_OPTIONAL_KEYS = {"value"}
BEAT_REQUIRED_KEYS = {
    "beat_id",
    "beat_order",
    "scene_id",
    "source_spans",
    "dramatic_change",
    "facts",
}
BEAT_OPTIONAL_KEYS = {"director_analysis"}
FACT_REQUIRED_KEYS = {"fact_id", "type", "text", "source_spans"}
FACT_OPTIONAL_KEYS = {
    "source_fragment",
    "performers",
    "speaker",
    "script_voice_type",
    "language",
    "source_role",
    "presentation_note",
    "presentation_requirement",
    "shot_isolation",
    "isolation_reason",
    "isolation_group_id",
    "spoken_source_spans",
    "stage_direction_fact_ids",
}
EMOTION_ARC_KEYS = {
    "emotion_arc_id",
    "character",
    "baseline",
    "trigger_fact_ids",
    "phases",
}
EMOTION_PHASE_KEYS = {"phase", "beat_ids", "intent", "visible_direction"}
CAMERA_REQUIRED_KEYS = {
    "shot_size",
    "angle",
    "position",
    "logic",
    "composition",
    "movement",
}
CAMERA_OPTIONAL_KEYS = {
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
BLOCKING_KEYS = {
    "character",
    "start_position",
    "action",
    "end_position",
    "facing",
    "eyeline",
}
PERFORMANCE_REQUIRED_KEYS = {"emotion_intent", "visible_behavior"}
PERFORMANCE_OPTIONAL_KEYS = {"emotion_arc_id", "phase"}
DIALOGUE_REQUIRED_KEYS = {
    "fact_id",
    "speaker",
    "text",
    "shot_delivery",
    "playback_segment_id",
}
DIALOGUE_OPTIONAL_KEYS = {"timing", "addressee"}
SPEAKER_PRESENTATION_KEYS = {"fact_id", "speaker", "presentation"}
CONTINUITY_KEYS = {
    "axis_id",
    "axis_side",
    "eyelines",
    "screen_directions",
    "action_match",
    "intentional_exceptions",
}
EYELINE_KEYS = {"character", "target", "direction"}
SCREEN_DIRECTION_KEYS = {"entity", "kind", "direction"}
ACTION_MATCH_KEYS = {"incoming", "outgoing"}
CONTINUITY_EXCEPTION_KEYS = {"type", "reason"}
CONTINUITY_UPDATE_KEYS = {
    "entity_type",
    "entity",
    "field",
    "from",
    "to",
    "evidence_fact_ids",
}
TRANSITION_REQUIRED_KEYS = {"type", "edit_point_id"}
TRANSITION_OPTIONAL_KEYS = {"notes"}
DIRECTOR_AUDIT_KEYS = {"long_take"}
LONG_TAKE_AUDIT_KEYS = {"status", "reason", "supports"}
SHOT_REQUIRED_KEYS = {
    "shot_id",
    "shot_order",
    "plan_unit_id",
    "scene_id",
    "beat_ids",
    "source_spans",
    "covered_fact_ids",
    "duration_seconds",
    "shot_phases",
    "cut_design",
    "camera",
    "execution_text",
    "dialogue",
    "transition_to_next",
    "rendered_shot_description",
    "notes",
}
SHOT_OPTIONAL_KEYS = {
    "shot_form",
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
    "coverage_evidence",
    "director_audit",
}

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
INPUT_KINDS = {"full_screenplay", "screenplay_segment", "continuous_text"}
BOUNDARY_LOCKS = {
    "entire_submitted_text",
    "explicit_continuous_range",
    "user_locked_fragment",
}
DIALOGUE_LANGUAGE_POLICY_MODES = {
    "original_with_translation",
    "multilingual_actual",
}
DIALOGUE_LANGUAGE_RESOLUTIONS = {"source_explicit", "user_confirmed"}
PRESENTATION_REQUIREMENTS = {"must_be_clear", "supporting"}
SHOT_ISOLATION_VALUES = {"director_required", "not_required"}
ENTRY_STRATEGY_MODES = {
    "spatial_establish",
    "relational_entry",
    "character_entry",
    "subjective_entry",
    "deliberate_withhold",
}
SCREEN_EVENT_ROLES = {
    "spatial",
    "dialogue_turn",
    "dialogue_continuation",
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
    "dialogue_rhythm",
}
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
TRANSITION_LANGUAGES = {
    "hard_cut",
    "action_cut",
    "gaze_cut",
    "sound_bridge",
    "long_hold",
    "dissolve",
    "fade",
}
TRANSITION_TYPES = {
    "cut",
    "action_cut",
    "gaze_cut",
    "sound_bridge",
    "hold",
    "dissolve",
    "fade",
    "scene_end",
}
SCRIPT_VOICE_TYPES = {"scene_dialogue", "vo", "os", "mediated", "unresolved"}
SHOT_DELIVERIES = {"onscreen", "os", "vo", "mediated", "unresolved"}
SPEAKER_PRESENTATIONS = {
    "primary_face",
    "shared_face",
    "foreground_back",
    "onscreen_occluded",
    "not_visible",
    "mediated_source",
}
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
PERFORMANCE_CHAIN_ROLES = {"action", "reaction", "dialogue"}
PERFORMANCE_CHAIN_KEYS = {"chain_id", "scene_id", "character", "steps"}
PERFORMANCE_CHAIN_STEP_KEYS = {"role", "fact_ids"}
SHOT_FORMS = {"long_take"}
SOURCE_REUSE_REASONS = {
    "simultaneous_isolation",
    "indivisible_source_action",
    "unavoidable_overlap",
    "continuous_dialogue_audio",
}
VISUAL_UNIFORMITY_SCOPES = {"project", "scene"}
VISUAL_UNIFORMITY_DIMENSIONS = {"angle", "movement_class"}
LONG_TAKE_STATUSES = {"supported", "needs_review"}
LONG_TAKE_SUPPORTS = {
    "continuous_action",
    "performance_development",
    "spatial_progression",
    "blocking_proof",
    "real_time_tension",
    "monologue_delivery",
    "testimony_statement",
}


def _closed_object(
    properties: dict[str, dict[str, Any]], required: set[str] | tuple[str, ...]
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": sorted(required),
        "additionalProperties": False,
    }


def _string_array(*, minimum: int = 0, maximum: int | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
        "minItems": minimum,
        "uniqueItems": True,
    }
    if maximum is not None:
        value["maxItems"] = maximum
    return value


def public_json_schema() -> dict[str, Any]:
    """Return the deterministic public structural schema.

    The delivery validator remains responsible for coordinate containment,
    digest validity, continuity, and other cross-object semantics.
    """

    string = {"type": "string"}
    nonempty = {"type": "string", "minLength": 1}
    span = _closed_object(
        {
            "start": {"type": "integer", "minimum": 0},
            "end": {"type": "integer", "minimum": 1},
            "text_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        },
        SOURCE_SPAN_KEYS,
    )
    base_policy_properties = {
        "mode": {
            "enum": ["original_with_translation", "multilingual_actual"]
        },
        "original_language": nonempty,
        "translation_languages": _string_array(minimum=1),
        "spoken_languages": _string_array(minimum=2),
        "resolution": {"enum": ["source_explicit", "user_confirmed"]},
        "evidence": nonempty,
    }
    policy_conditionals = [
        {
            "if": {
                "properties": {
                    "mode": {"const": "original_with_translation"}
                }
            },
            "then": {
                "required": ["original_language", "translation_languages"]
            },
        },
        {
            "if": {
                "properties": {"mode": {"const": "multilingual_actual"}}
            },
            "then": {"required": ["spoken_languages"]},
        },
    ]
    local_policy = {
        "type": "object",
        "properties": base_policy_properties,
        "required": ["mode", "resolution", "evidence"],
        "additionalProperties": False,
        "allOf": policy_conditionals,
    }
    project_policy_properties = {
        **base_policy_properties,
        "scope": {"const": "project"},
        "exceptions_require_confirmation": {"const": True},
    }
    project_policy = {
        "type": "object",
        "properties": project_policy_properties,
        "required": [
            "mode",
            "resolution",
            "evidence",
            "scope",
            "exceptions_require_confirmation",
        ],
        "additionalProperties": False,
        "allOf": policy_conditionals,
    }
    profile = _closed_object(
        {
            "rhythm": {"enum": ["restrained", "balanced", "kinetic"]},
            "camera_energy": {"enum": ["static", "responsive", "assertive"]},
            "visual_distance": {"enum": ["observational", "intimate", "mixed"]},
            "performance_focus": {
                "enum": ["body", "face", "blocking", "ensemble", "mixed"]
            },
            "space_strategy": {
                "enum": [
                    "establish_then_enter",
                    "embedded_reveal",
                    "subjective",
                    "mixed",
                ]
            },
            "transition_language": _string_array(minimum=1),
            "priorities": _string_array(minimum=1, maximum=3),
            "natural_language_intent": nonempty,
        },
        PROFILE_REQUIRED_KEYS,
    )
    source_properties = {
        "input_kind": {
            "enum": ["full_screenplay", "screenplay_segment", "continuous_text"]
        },
        "boundary_lock": {
            "enum": [
                "entire_submitted_text",
                "explicit_continuous_range",
                "user_locked_fragment",
            ]
        },
        "scope": nonempty,
        "delivery_slug": {
            "type": "string",
            "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
            "maxLength": 80,
        },
        "locked_text": {"type": "string", "minLength": 1},
        "locked_text_hash": {"type": "string"},
        "approved_corrections": {
            "type": "array",
            "items": {"$ref": "#/$defs/correction"},
        },
        "dialogue_language_policy": local_policy,
        "project_dialogue_language_policy": project_policy,
    }
    confirmation = _closed_object(
        {
            "status": {"enum": ["pending", "confirmed"]},
            "stage_digest": string,
            "confirmation_order": {"type": "integer", "minimum": 1, "maximum": 2},
            "notes": string,
        },
        CONFIRMATION_ITEM_KEYS,
    )
    nullable_string = {"type": ["string", "null"]}
    nullable_nonempty = {
        "anyOf": [nonempty, {"type": "null"}],
    }
    span_array = {
        "type": "array",
        "items": {"$ref": "#/$defs/source_span"},
        "minItems": 1,
    }
    correction = _closed_object(
        {"from": nonempty, "to": nonempty, "reason": nonempty},
        CORRECTION_KEYS,
    )
    director_analysis = _closed_object(
        {
            key: nullable_string
            for key in DIRECTOR_ANALYSIS_KEYS
        },
        DIRECTOR_ANALYSIS_KEYS,
    )
    source_analysis = _closed_object(
        {
            "source_boundary": nonempty,
            "narrative_function": nonempty,
            "dramatic_progression": nonempty,
            "character_relations": _string_array(),
            "source_constraints": _string_array(minimum=1),
        },
        SOURCE_ANALYSIS_REQUIRED_KEYS,
    )
    style_option = _closed_object(
        {
            "option_id": {"type": "string", "pattern": "^STYLE-0[1-4]$"},
            "label": nonempty,
            "rationale": nonempty,
            "profile": {"$ref": "#/$defs/director_profile"},
        },
        STYLE_OPTION_KEYS,
    )
    entry_strategy = _closed_object(
        {
            "mode": {"enum": sorted(ENTRY_STRATEGY_MODES)},
            "observer_position": nonempty,
            "required_spatial_information": _string_array(),
            "withheld_information": _string_array(),
            "reason": nonempty,
        },
        ENTRY_STRATEGY_REQUIRED_KEYS,
    )
    style_profile_basis = _closed_object(
        {
            "field": {
                "enum": sorted(
                    PROFILE_VALUE_KEYS
                    | {"transition_language", "priorities", "natural_language_intent"}
                )
            },
            "value": nonempty,
        },
        STYLE_PROFILE_BASIS_KEYS,
    )
    style_anchor = _closed_object(
        {
            "style_anchor_id": {"type": "string", "pattern": "^SA[0-9]{3,}$"},
            "profile_basis": {
                "type": "array",
                "items": {"$ref": "#/$defs/style_profile_basis"},
                "minItems": 1,
            },
            "scene_application": nonempty,
            "avoidance": nonempty,
        },
        STYLE_ANCHOR_KEYS,
    )
    duration_review = _closed_object(
        {
            "source_target_seconds": {
                "anyOf": [
                    {"type": "integer", "minimum": 0},
                    {"type": "null"},
                ]
            },
            "speech_floor_seconds": {"type": "number", "minimum": 0},
            "action_reaction_floor_seconds": {
                "type": "number",
                "minimum": 0,
            },
            "minimum_playable_seconds": {"type": "number", "minimum": 0},
            "planned_seconds": {"type": "integer", "minimum": 0},
            "variance_seconds": {"type": "integer"},
            "variance_ratio": {
                "anyOf": [
                    {"type": "number"},
                    {"type": "null"},
                ]
            },
            "unavoidable_overrun_seconds": {"type": "number", "minimum": 0},
            "discretionary_extension_seconds": {
                "type": "number",
                "minimum": 0,
            },
            "resolution": {
                "enum": [
                    "match",
                    "source_target_unplayable",
                    "intentional_extension",
                    "intentional_shortening",
                    "mixed",
                ]
            },
            "reason": nonempty,
        },
        DURATION_REVIEW_KEYS,
    )
    rhythm_section = _closed_object(
        {
            "rhythm_section_id": {
                "type": "string",
                "pattern": "^RS[0-9]{3,}$",
            },
            "plan_unit_ids": _string_array(minimum=1),
            "tempo_role": {
                "enum": [
                    "establish",
                    "build",
                    "accelerate",
                    "sustain",
                    "turn",
                    "release",
                ]
            },
            "target_shot_duration_min_seconds": {
                "type": "number",
                "exclusiveMinimum": 0,
            },
            "target_shot_duration_max_seconds": {
                "type": "number",
                "exclusiveMinimum": 0,
            },
            "cut_density_intent": nonempty,
            "reason": nonempty,
        },
        RHYTHM_SECTION_KEYS,
    )
    rhythm_design = _closed_object(
        {
            "scene_pacing_intent": nonempty,
            "sections": {
                "type": "array",
                "items": {"$ref": "#/$defs/rhythm_section"},
                "minItems": 1,
            },
        },
        RHYTHM_DESIGN_KEYS,
    )
    directing_plan = _closed_object(
        {
            "scene_objective": nonempty,
            "progression": _string_array(minimum=1),
            "pov_flow": _string_array(minimum=1),
            "entry_strategy": {"$ref": "#/$defs/entry_strategy"},
            "style_anchors": {
                "type": "array",
                "items": {"$ref": "#/$defs/style_anchor"},
                "minItems": 1,
            },
            "duration_review": {"$ref": "#/$defs/duration_review"},
            "rhythm_design": {"$ref": "#/$defs/rhythm_design"},
            "entry_state": nonempty,
            "exit_state": nonempty,
            "rhythm_curve": _string_array(),
            "dialogue_geometry": nonempty,
            "protected_processes": _string_array(),
            "visual_turns": _string_array(),
        },
        DIRECTING_PLAN_REQUIRED_KEYS,
    )
    continuity_entity = {
        "type": "object",
        "properties": {"name": nonempty},
        "required": ["name"],
        "additionalProperties": {"type": "string", "minLength": 1},
    }
    initial_continuity = _closed_object(
        {
            "characters": {"type": "array", "items": continuity_entity},
            "props": {"type": "array", "items": continuity_entity},
            "fixed_objects": {"type": "array", "items": continuity_entity},
            "sound_sources": {"type": "array", "items": continuity_entity},
            "reality_layer": nonempty,
        },
        INITIAL_CONTINUITY_KEYS,
    )
    axis = _closed_object(
        {
            "axis_id": {"type": "string", "pattern": "^AX[0-9]{3,}$"},
            "axis_type": {"enum": sorted(AXIS_TYPES)},
            "endpoint_a": nonempty,
            "endpoint_b": nonempty,
        },
        AXIS_KEYS,
    )
    inherited_state = _closed_object(
        {
            "entity_type": nonempty,
            "entity": string,
            "field": nonempty,
            "value": nonempty,
        },
        INHERITED_STATE_KEYS,
    )
    scene = _closed_object(
        {
            "scene_id": {"type": "string", "pattern": "^SC[0-9]{3,}$"},
            "scene": nonempty,
            "reality_layer": nonempty,
            "directing_plan": {"$ref": "#/$defs/directing_plan"},
            "director_analysis": {"$ref": "#/$defs/director_analysis"},
            "initial_continuity": {"$ref": "#/$defs/initial_continuity"},
            "axes": {"type": "array", "items": {"$ref": "#/$defs/axis"}},
            "inherits_from": nullable_nonempty,
            "inherited_states": {
                "type": "array",
                "items": {"$ref": "#/$defs/inherited_state"},
            },
        },
        SCENE_REQUIRED_KEYS,
    )
    fact = _closed_object(
        {
            "fact_id": {"type": "string", "pattern": "^F[0-9]{3,}$"},
            "type": {"enum": sorted(FACT_TYPES)},
            "text": nonempty,
            "source_spans": span_array,
            "source_fragment": string,
            "performers": _string_array(),
            "speaker": nonempty,
            "script_voice_type": {"enum": sorted(SCRIPT_VOICE_TYPES)},
            "language": nonempty,
            "source_role": {"enum": ["original_dialogue", "spoken_dialogue"]},
            "presentation_note": string,
            "presentation_requirement": {"enum": ["must_be_clear", "supporting"]},
            "shot_isolation": {"enum": ["director_required", "not_required"]},
            "isolation_reason": string,
            "isolation_group_id": {
                "anyOf": [
                    {"type": "string", "pattern": "^IG[0-9]{3,}$"},
                    {"type": "null"},
                ]
            },
            "spoken_source_spans": span_array,
            "stage_direction_fact_ids": _string_array(),
        },
        FACT_REQUIRED_KEYS,
    )
    fact["allOf"] = [
        {
            "if": {"properties": {"type": {"const": "dialogue"}}, "required": ["type"]},
            "then": {
                "required": [
                    "speaker",
                    "script_voice_type",
                    "spoken_source_spans",
                    "stage_direction_fact_ids",
                ]
            },
        }
    ]
    beat = _closed_object(
        {
            "beat_id": {"type": "string", "pattern": "^B[0-9]{3,}$"},
            "beat_order": {"type": "integer", "minimum": 1},
            "scene_id": {"type": "string", "pattern": "^SC[0-9]{3,}$"},
            "source_spans": span_array,
            "dramatic_change": nonempty,
            "facts": {"type": "array", "items": {"$ref": "#/$defs/fact"}, "minItems": 1},
            "director_analysis": {"$ref": "#/$defs/director_analysis"},
        },
        BEAT_REQUIRED_KEYS,
    )
    screen_event = _closed_object(
        {
            "screen_event_id": {"type": "string", "pattern": "^SEV[0-9]{3,}$"},
            "scene_id": {"type": "string", "pattern": "^SC[0-9]{3,}$"},
            "event_order": {"type": "integer", "minimum": 1},
            "beat_ids": _string_array(minimum=1),
            "source_spans": span_array,
            "covered_fact_ids": _string_array(minimum=1),
            "visual_subjects": _string_array(minimum=1),
            "visual_action": nonempty,
            "viewing_requirement": nonempty,
            "scale_requirement": nonempty,
            "spatial_zone": nonempty,
            "temporal_relation": {"enum": sorted(SCREEN_EVENT_TEMPORAL_RELATIONS)},
            "sound_fact_ids": _string_array(),
            "event_role": {"enum": sorted(SCREEN_EVENT_ROLES)},
            "primary_viewing_subject": nonempty,
            "focus_scale": {"enum": sorted(FOCUS_SCALES)},
        },
        SCREEN_EVENT_REQUIRED_KEYS,
    )
    spatial_strategy = _closed_object(
        {"type": {"enum": sorted(SPATIAL_STRATEGY_TYPES)}, "description": string},
        SPATIAL_STRATEGY_KEYS,
    )
    movement_plan = _closed_object(
        {
            "class": {"enum": sorted(CAMERA_MOVEMENT_CLASSES)},
            "trigger": string,
            "speed": string,
            "path": string,
            "end_condition": string,
            "hold_reason": string,
        },
        MOVEMENT_PLAN_KEYS,
    )
    visual_plan = _closed_object(
        {
            "viewpoint_owner": nonempty,
            "primary_subjects": _string_array(minimum=1),
            "secondary_subjects": _string_array(),
            "shot_size": nonempty,
            "angle": nonempty,
            "camera_position": nonempty,
            "framing_relation": nonempty,
            "perspective_intent": {"enum": sorted(PERSPECTIVE_INTENTS)},
            "focus_plan": nonempty,
            "spatial_strategy": {"$ref": "#/$defs/spatial_strategy"},
            "movement_plan": {"$ref": "#/$defs/movement_plan"},
            "start_frame": nonempty,
            "end_frame": nonempty,
            "motivation": nonempty,
            "style_anchor_ids": _string_array(minimum=1),
            "focal_length_mm": {"type": "number", "exclusiveMinimum": 0},
        },
        VISUAL_PLAN_REQUIRED_KEYS,
    )
    dialogue_design = _closed_object(
        {
            "speaker_sequence": _string_array(minimum=1),
            "justification": nonempty,
            "mode": nonempty,
            "face_readable_speakers": _string_array(),
            "listener_reaction_characters": _string_array(),
            "axis_id": nullable_nonempty,
        },
        {"speaker_sequence", "justification"},
    )
    source_reuse = _closed_object(
        {
            "from_plan_unit_id": nonempty,
            "reason": {"enum": sorted(SOURCE_REUSE_REASONS)},
            "justification": nonempty,
        },
        {"from_plan_unit_id", "reason", "justification"},
    )
    long_take_design = _closed_object(
        {
            "reason": nonempty,
            "supports": {
                "type": "array",
                "items": {"enum": sorted(LONG_TAKE_SUPPORTS)},
                "minItems": 1,
                "uniqueItems": True,
            },
            "protected_event_ids": _string_array(minimum=1),
            "temporal_progression": {
                "type": "array",
                "items": {"$ref": "#/$defs/long_take_progression"},
                "minItems": 2,
            },
        },
        LONG_TAKE_DESIGN_KEYS,
    )
    short_shot_design = _closed_object(
        {
            "timing_intent": nonempty,
            "viewing_value": nonempty,
            "entry_trigger": nonempty,
            "exit_trigger": nonempty,
            "readability_reason": nonempty,
        },
        SHORT_SHOT_DESIGN_KEYS,
    )
    long_take_progression = _closed_object(
        {
            "progression_id": {
                "type": "string",
                "pattern": "^LTP[0-9]{3,}$",
            },
            "phase_order": {"type": "integer", "minimum": 1},
            "screen_event_ids": _string_array(minimum=1),
            "start_condition": nonempty,
            "visible_development": nonempty,
            "end_condition": nonempty,
            "duration_seconds": {"type": "number", "exclusiveMinimum": 0},
        },
        LONG_TAKE_PROGRESSION_KEYS,
    )
    action_timing_segment = _closed_object(
        {
            "timing_segment_id": {
                "type": "string",
                "pattern": "^ATS[0-9]{3,}$",
            },
            "screen_event_ids": _string_array(minimum=1),
            "start_condition": nonempty,
            "end_condition": nonempty,
            "minimum_seconds": {"type": "number", "minimum": 0},
            "overlap_group": nullable_nonempty,
        },
        ACTION_TIMING_SEGMENT_KEYS,
    )
    reaction_hold = _closed_object(
        {
            "reaction_hold_id": {
                "type": "string",
                "pattern": "^RH[0-9]{3,}$",
            },
            "screen_event_id": nonempty,
            "character": nonempty,
            "visible_change": nonempty,
            "minimum_seconds": {"type": "number", "minimum": 0},
        },
        REACTION_HOLD_KEYS,
    )
    duration_design = _closed_object(
        {
            "playback_segment_ids": _string_array(),
            "action_segments": {
                "type": "array",
                "items": {"$ref": "#/$defs/action_timing_segment"},
            },
            "reaction_holds": {
                "type": "array",
                "items": {"$ref": "#/$defs/reaction_hold"},
            },
            "speech_min_seconds": {"type": "number", "minimum": 0},
            "action_min_seconds": {"type": "number", "minimum": 0},
            "reaction_hold_seconds": {"type": "number", "minimum": 0},
            "overlap_mode": {"enum": ["sequential", "parallel"]},
            "minimum_total_seconds": {"type": "number", "minimum": 0},
            "editorial_target_seconds": {"type": "number", "minimum": 0},
            "pacing_role": {
                "enum": [
                    "establish",
                    "build",
                    "accelerate",
                    "sustain",
                    "turn",
                    "release",
                ]
            },
            "duration_rationale": nonempty,
        },
        DURATION_DESIGN_KEYS,
    )
    plan_unit = _closed_object(
        {
            "plan_unit_id": {"type": "string", "pattern": "^PU[0-9]{3,}$"},
            "plan_order": {"type": "integer", "minimum": 1},
            "scene_id": {"type": "string", "pattern": "^SC[0-9]{3,}$"},
            "beat_ids": _string_array(minimum=1),
            "screen_event_ids": _string_array(minimum=1),
            "source_spans": span_array,
            "estimated_duration_seconds": {"type": "integer", "minimum": 1},
            "narrative_purpose": nonempty,
            "visual_plan": {"$ref": "#/$defs/visual_plan"},
            "duration_design": {"$ref": "#/$defs/duration_design"},
            "shot_form": {"const": "long_take"},
            "source_reuse": {"$ref": "#/$defs/source_reuse"},
            "dialogue_design": {
                "anyOf": [
                    {"$ref": "#/$defs/dialogue_design"},
                    {"type": "null"},
                ]
            },
            "long_take_design": {"$ref": "#/$defs/long_take_design"},
            "short_shot_design": {"$ref": "#/$defs/short_shot_design"},
        },
        PLAN_UNIT_REQUIRED_KEYS,
    )
    viewing_decision = _closed_object(
        {
            "viewing_decision_id": {"type": "string", "pattern": "^VD[0-9]{3,}$"},
            "scene_id": {"type": "string", "pattern": "^SC[0-9]{3,}$"},
            "from_screen_event_id": nonempty,
            "to_screen_event_id": nonempty,
            "mode": {"enum": sorted(VIEWING_DECISION_MODES)},
            "trigger": nonempty,
            "viewing_change": nonempty,
            "director_reason": nonempty,
            "reframe_method": {
                "anyOf": [{"enum": sorted(REFRAME_METHODS)}, {"type": "null"}]
            },
            "non_cut_basis": {
                "anyOf": [{"enum": sorted(NON_CUT_BASES)}, {"type": "null"}]
            },
        },
        VIEWING_DECISION_KEYS,
    )
    edit_point = _closed_object(
        {
            "edit_point_id": {"type": "string", "pattern": "^EP[0-9]{3,}$"},
            "after_plan_unit_id": nonempty,
            "before_plan_unit_id": nonempty,
            "source_spans": span_array,
            "trigger": nonempty,
            "editorial_gain": nonempty,
            "broken_performance_chain_ids": _string_array(),
        },
        {
            "edit_point_id",
            "after_plan_unit_id",
            "before_plan_unit_id",
            "source_spans",
            "trigger",
            "editorial_gain",
        },
    )
    reorder = _closed_object(
        {
            "reorder_id": {"type": "string", "pattern": "^RO[0-9]{3,}$"},
            "plan_unit_ids": _string_array(minimum=2),
            "source_spans": span_array,
            "reason": nonempty,
        },
        {"reorder_id", "plan_unit_ids", "source_spans", "reason"},
    )
    visual_uniformity_review = _closed_object(
        {
            "review_id": {"type": "string", "pattern": "^VR[0-9]{3,}$"},
            "scope": {"enum": ["project", "scene"]},
            "scene_id": nullable_nonempty,
            "dimension": {"enum": ["angle", "movement_class"]},
            "dominant_value": nonempty,
            "reason": nonempty,
            "style_anchor_ids": _string_array(minimum=1),
        },
        {
            "review_id",
            "scope",
            "scene_id",
            "dimension",
            "dominant_value",
            "reason",
            "style_anchor_ids",
        },
    )
    dialogue_playback_segment = _closed_object(
        {
            "playback_segment_id": {
                "type": "string",
                "pattern": "^DPS[0-9]{3,}$",
            },
            "segment_order": {"type": "integer", "minimum": 1},
            "plan_unit_id": nonempty,
            "text_start": {"type": "integer", "minimum": 0},
            "text_end": {"type": "integer", "minimum": 1},
            "unit_start_seconds": {"type": "number", "minimum": 0},
            "planned_speech_seconds": {
                "type": "number",
                "exclusiveMinimum": 0,
            },
            "shot_delivery": {"enum": sorted(SHOT_DELIVERIES)},
        },
        DIALOGUE_PLAYBACK_SEGMENT_KEYS,
    )
    dialogue_playback = _closed_object(
        {
            "playback_id": {
                "type": "string",
                "pattern": "^DPB[0-9]{3,}$",
            },
            "scene_id": {"type": "string", "pattern": "^SC[0-9]{3,}$"},
            "fact_id": {"type": "string", "pattern": "^F[0-9]{3,}$"},
            "speech_min_seconds": {"type": "number", "minimum": 0},
            "planned_playback_seconds": {
                "type": "number",
                "exclusiveMinimum": 0,
            },
            "segments": {
                "type": "array",
                "items": {"$ref": "#/$defs/dialogue_playback_segment"},
                "minItems": 1,
            },
        },
        DIALOGUE_PLAYBACK_KEYS,
    )
    rhythm_review = _closed_object(
        {
            "review_id": {"type": "string", "pattern": "^RR[0-9]{3,}$"},
            "scope": {"enum": ["project", "scene"]},
            "scene_id": nullable_nonempty,
            "finding_code": nonempty,
            "finding_value": {"type": "number"},
            "decision": {"enum": ["retain", "rework"]},
            "reason": nonempty,
            "affected_plan_unit_ids": _string_array(minimum=1),
        },
        RHYTHM_REVIEW_KEYS,
    )
    shot_plan = _closed_object(
        {
            "planned_shot_count": {"type": "integer", "minimum": 0},
            "planned_edit_point_count": {"type": "integer", "minimum": 0},
            "planned_total_duration_seconds": {"type": "integer", "minimum": 0},
            "planned_units": {
                "type": "array",
                "items": {"$ref": "#/$defs/plan_unit"},
                "minItems": 1,
            },
            "viewing_decisions": {
                "type": "array",
                "items": {"$ref": "#/$defs/viewing_decision"},
            },
            "edit_points": {"type": "array", "items": {"$ref": "#/$defs/edit_point"}},
            "reorders": {"type": "array", "items": {"$ref": "#/$defs/reorder"}},
            "visual_uniformity_reviews": {
                "type": "array",
                "items": {"$ref": "#/$defs/visual_uniformity_review"},
            },
            "dialogue_playbacks": {
                "type": "array",
                "items": {"$ref": "#/$defs/dialogue_playback"},
            },
            "rhythm_reviews": {
                "type": "array",
                "items": {"$ref": "#/$defs/rhythm_review"},
            },
        },
        SHOT_PLAN_KEYS,
    )
    emotion_phase = _closed_object(
        {
            "phase": {"enum": sorted(PERFORMANCE_PHASES)},
            "beat_ids": _string_array(minimum=1),
            "intent": nonempty,
            "visible_direction": _string_array(minimum=1),
        },
        {"phase", "beat_ids", "intent", "visible_direction"},
    )
    emotion_arc = _closed_object(
        {
            "emotion_arc_id": {"type": "string", "pattern": "^EA[0-9]{3,}$"},
            "character": nonempty,
            "baseline": nonempty,
            "trigger_fact_ids": _string_array(),
            "phases": {
                "type": "array",
                "items": {"$ref": "#/$defs/emotion_phase"},
                "minItems": 1,
            },
        },
        {"emotion_arc_id", "character", "baseline", "trigger_fact_ids", "phases"},
    )
    performance_chain_step = _closed_object(
        {
            "role": {"enum": sorted(PERFORMANCE_CHAIN_ROLES)},
            "fact_ids": _string_array(minimum=1),
        },
        PERFORMANCE_CHAIN_STEP_KEYS,
    )
    performance_chain = _closed_object(
        {
            "chain_id": {"type": "string", "pattern": "^PC[0-9]{3,}$"},
            "scene_id": {"type": "string", "pattern": "^SC[0-9]{3,}$"},
            "character": nonempty,
            "steps": {
                "type": "array",
                "items": {"$ref": "#/$defs/performance_chain_step"},
                "minItems": 2,
            },
        },
        PERFORMANCE_CHAIN_KEYS,
    )
    shot_phase = _closed_object(
        {
            "phase_id": nonempty,
            "phase_order": {"type": "integer", "minimum": 1},
            "screen_event_ids": _string_array(minimum=1),
            "duration_seconds": {"type": "integer", "minimum": 1},
            "camera_state": nonempty,
            "sound_fact_ids": _string_array(),
            "dialogue_playback_segment_ids": _string_array(),
        },
        SHOT_PHASE_KEYS,
    )
    cut_design = _closed_object(
        {
            "entry_trigger": nonempty,
            "exit_trigger": nonempty,
            "isolation_intent": {"enum": ["none", "director_required"]},
        },
        CUT_DESIGN_REQUIRED_KEYS,
    )
    camera = _closed_object(
        {
            "shot_size": nonempty,
            "angle": nonempty,
            "position": nonempty,
            "logic": nonempty,
            "composition": nonempty,
            "movement": nonempty,
            "viewpoint_owner": nonempty,
            "primary_subjects": _string_array(),
            "secondary_subjects": _string_array(),
            "perspective_intent": {"enum": sorted(PERSPECTIVE_INTENTS)},
            "focus_plan": nonempty,
            "spatial_strategy": {"$ref": "#/$defs/spatial_strategy"},
            "movement_plan": {"$ref": "#/$defs/movement_plan"},
            "start_frame": nonempty,
            "end_frame": nonempty,
            "motivation": nonempty,
            "framing_mode": {"enum": sorted(FRAMING_MODES)},
            "foreground_characters": _string_array(),
        },
        CAMERA_REQUIRED_KEYS,
    )
    blocking = _closed_object(
        {
            "character": nonempty,
            "start_position": nonempty,
            "action": nonempty,
            "end_position": nonempty,
            "facing": nonempty,
            "eyeline": nonempty,
        },
        {"character", "start_position", "action", "end_position", "facing", "eyeline"},
    )
    performance = _closed_object(
        {
            "emotion_arc_id": nullable_nonempty,
            "phase": {"enum": sorted(PERFORMANCE_PHASES)},
            "emotion_intent": string,
            "visible_behavior": _string_array(),
        },
        {"emotion_intent", "visible_behavior"},
    )
    dialogue = _closed_object(
        {
            "fact_id": nonempty,
            "speaker": nonempty,
            "text": nonempty,
            "shot_delivery": {"enum": sorted(SHOT_DELIVERIES)},
            "playback_segment_id": {
                "type": "string",
                "pattern": "^DPS[0-9]{3,}$",
            },
            "timing": nonempty,
            "addressee": string,
        },
        DIALOGUE_REQUIRED_KEYS,
    )
    speaker_presentation = _closed_object(
        {
            "fact_id": nonempty,
            "speaker": nonempty,
            "presentation": {"enum": sorted(SPEAKER_PRESENTATIONS)},
        },
        {"fact_id", "speaker", "presentation"},
    )
    eyeline = _closed_object(
        {
            "character": nonempty,
            "target": nonempty,
            "direction": {"enum": sorted(SCREEN_DIRECTIONS)},
        },
        {"character", "target", "direction"},
    )
    screen_direction = _closed_object(
        {
            "entity": nonempty,
            "kind": {"enum": sorted(SCREEN_DIRECTION_KINDS)},
            "direction": {"enum": sorted(SCREEN_DIRECTIONS)},
        },
        {"entity", "kind", "direction"},
    )
    action_match = _closed_object(
        {"incoming": nullable_nonempty, "outgoing": nullable_nonempty},
        {"incoming", "outgoing"},
    )
    continuity_exception = _closed_object(
        {"type": {"enum": sorted(CONTINUITY_EXCEPTION_TYPES)}, "reason": nonempty},
        {"type", "reason"},
    )
    continuity = _closed_object(
        {
            "axis_id": nullable_nonempty,
            "axis_side": {"enum": sorted(AXIS_SIDES)},
            "eyelines": {"type": "array", "items": {"$ref": "#/$defs/eyeline"}},
            "screen_directions": {
                "type": "array",
                "items": {"$ref": "#/$defs/screen_direction"},
            },
            "action_match": {"$ref": "#/$defs/action_match"},
            "intentional_exceptions": {
                "type": "array",
                "items": {"$ref": "#/$defs/continuity_exception"},
            },
        },
        {
            "axis_id",
            "axis_side",
            "eyelines",
            "screen_directions",
            "action_match",
            "intentional_exceptions",
        },
    )
    continuity_update = _closed_object(
        {
            "entity_type": nonempty,
            "entity": string,
            "field": nonempty,
            "from": nonempty,
            "to": nonempty,
            "evidence_fact_ids": _string_array(minimum=1),
        },
        {"entity_type", "entity", "field", "from", "to", "evidence_fact_ids"},
    )
    coverage_evidence = _closed_object(
        {"fact_id": nonempty, "target_path": nonempty, "evidence_quote": nonempty},
        {"fact_id", "target_path", "evidence_quote"},
    )
    long_take_audit = _closed_object(
        {
            "status": {"enum": ["supported", "needs_review"]},
            "reason": string,
            "supports": _string_array(),
        },
        LONG_TAKE_AUDIT_KEYS,
    )
    director_audit = _closed_object(
        {"long_take": {"$ref": "#/$defs/long_take_audit"}},
        DIRECTOR_AUDIT_KEYS,
    )
    transition = _closed_object(
        {
            "type": {"enum": sorted(TRANSITION_TYPES)},
            "edit_point_id": nullable_nonempty,
            "notes": string,
        },
        TRANSITION_REQUIRED_KEYS,
    )
    shot = _closed_object(
        {
            "shot_id": {"type": "string", "pattern": "^SH[0-9]{3,}$"},
            "shot_order": {"type": "integer", "minimum": 1},
            "plan_unit_id": nonempty,
            "scene_id": {"type": "string", "pattern": "^SC[0-9]{3,}$"},
            "beat_ids": _string_array(minimum=1),
            "source_spans": span_array,
            "covered_fact_ids": _string_array(minimum=1),
            "duration_seconds": {"type": "integer", "minimum": 1},
            "shot_phases": {
                "type": "array",
                "items": {"$ref": "#/$defs/shot_phase"},
                "minItems": 1,
            },
            "cut_design": {"$ref": "#/$defs/cut_design"},
            "camera": {"$ref": "#/$defs/camera"},
            "execution_text": nonempty,
            "dialogue": {"type": "array", "items": {"$ref": "#/$defs/dialogue"}},
            "transition_to_next": {"$ref": "#/$defs/transition"},
            "rendered_shot_description": nonempty,
            "notes": string,
            "shot_form": {"const": "long_take"},
            "primary_fact_id": nullable_nonempty,
            "blocking": {"type": "array", "items": {"$ref": "#/$defs/blocking"}},
            "performance": {"$ref": "#/$defs/performance"},
            "speaker_presentation": {
                "type": "array",
                "items": {"$ref": "#/$defs/speaker_presentation"},
            },
            "visible_characters": _string_array(),
            "visible_props": _string_array(),
            "environment_behavior": _string_array(),
            "continuity": {"$ref": "#/$defs/continuity"},
            "continuity_updates": {
                "type": "array",
                "items": {"$ref": "#/$defs/continuity_update"},
            },
            "end_state": _string_array(minimum=1),
            "coverage_evidence": {
                "type": "array",
                "items": {"$ref": "#/$defs/coverage_evidence"},
            },
            "director_audit": {"$ref": "#/$defs/director_audit"},
        },
        SHOT_REQUIRED_KEYS,
    )
    top_properties = {key: {} for key in TOP_LEVEL_KEYS}
    top_properties.update(
        {
            "contract_name": {"const": CONTRACT_NAME},
            "contract_version": {"const": CONTRACT_VERSION},
            "source_skill": {"const": SOURCE_SKILL},
            "source_skill_version": {"const": SOURCE_SKILL_VERSION},
            "project_id": {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
            },
            "content_hash": string,
            "duration_policy": {
                "$ref": "#/$defs/duration_policy"
            },
            "rhythm_policy": {"$ref": "#/$defs/rhythm_policy"},
            "confirmations": _closed_object(
                {"gate_1": confirmation, "gate_2": confirmation},
                set(CONFIRMATION_KEYS),
            ),
            "source": _closed_object(
                source_properties, SOURCE_REQUIRED_KEYS
            ),
            "director_profile": profile,
            "source_analysis": {"$ref": "#/$defs/source_analysis"},
            "director_style_options": {
                "type": "array",
                "items": {"$ref": "#/$defs/style_option"},
                "minItems": 3,
                "maxItems": 4,
            },
            "selected_style_option_id": {
                "type": "string",
                "pattern": "^STYLE-0[1-4]$",
            },
            "screen_events": {
                "type": "array",
                "items": {"$ref": "#/$defs/screen_event"},
                "minItems": 1,
            },
            "shot_plan": {"$ref": "#/$defs/shot_plan"},
            "scenes": {
                "type": "array",
                "items": {"$ref": "#/$defs/scene"},
                "minItems": 1,
            },
            "beats": {
                "type": "array",
                "items": {"$ref": "#/$defs/beat"},
                "minItems": 1,
            },
            "emotion_arcs": {
                "type": "array",
                "items": {"$ref": "#/$defs/emotion_arc"},
            },
            "performance_chains": {
                "type": "array",
                "items": {"$ref": "#/$defs/performance_chain"},
            },
            "shots": {
                "type": "array",
                "items": {"$ref": "#/$defs/shot"},
                "minItems": 1,
            },
        }
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://suvision6.github.io/susu/shot-data-2.5.8.schema.json",
        "title": "shot-data/2.5.8 public structure",
        "$comment": (
            "Machine authority for public keys and basic types. Cross-object director "
            "semantics are validated by storyboard_delivery.py."
        ),
        **_closed_object(top_properties, TOP_LEVEL_REQUIRED_KEYS),
        "$defs": {
            "source_span": span,
            "duration_policy": _closed_object(
                {
                    "zh_chars_per_second": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                    },
                    "en_words_per_second": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                    },
                    "comma_pause_seconds": {"type": "number", "minimum": 0},
                    "sentence_pause_seconds": {"type": "number", "minimum": 0},
                    "ellipsis_dash_pause_seconds": {"type": "number", "minimum": 0},
                },
                DURATION_POLICY_KEYS,
            ),
            "rhythm_policy": _closed_object(
                {
                    key: {"const": value}
                    for key, value in DEFAULT_RHYTHM_POLICY.items()
                },
                RHYTHM_POLICY_KEYS,
            ),
            "director_profile": profile,
            "dialogue_language_policy": local_policy,
            "project_dialogue_language_policy": project_policy,
            "correction": correction,
            "director_analysis": director_analysis,
            "source_analysis": source_analysis,
            "style_option": style_option,
            "entry_strategy": entry_strategy,
            "style_profile_basis": style_profile_basis,
            "style_anchor": style_anchor,
            "duration_review": duration_review,
            "rhythm_section": rhythm_section,
            "rhythm_design": rhythm_design,
            "directing_plan": directing_plan,
            "initial_continuity": initial_continuity,
            "axis": axis,
            "inherited_state": inherited_state,
            "scene": scene,
            "fact": fact,
            "beat": beat,
            "screen_event": screen_event,
            "spatial_strategy": spatial_strategy,
            "movement_plan": movement_plan,
            "visual_plan": visual_plan,
            "dialogue_design": dialogue_design,
            "source_reuse": source_reuse,
            "short_shot_design": short_shot_design,
            "long_take_progression": long_take_progression,
            "long_take_design": long_take_design,
            "action_timing_segment": action_timing_segment,
            "reaction_hold": reaction_hold,
            "duration_design": duration_design,
            "plan_unit": plan_unit,
            "viewing_decision": viewing_decision,
            "edit_point": edit_point,
            "reorder": reorder,
            "visual_uniformity_review": visual_uniformity_review,
            "dialogue_playback_segment": dialogue_playback_segment,
            "dialogue_playback": dialogue_playback,
            "rhythm_review": rhythm_review,
            "shot_plan": shot_plan,
            "emotion_phase": emotion_phase,
            "emotion_arc": emotion_arc,
            "performance_chain_step": performance_chain_step,
            "performance_chain": performance_chain,
            "shot_phase": shot_phase,
            "cut_design": cut_design,
            "camera": camera,
            "blocking": blocking,
            "performance": performance,
            "dialogue": dialogue,
            "speaker_presentation": speaker_presentation,
            "eyeline": eyeline,
            "screen_direction": screen_direction,
            "action_match": action_match,
            "continuity_exception": continuity_exception,
            "continuity": continuity,
            "continuity_update": continuity_update,
            "coverage_evidence": coverage_evidence,
            "long_take_audit": long_take_audit,
            "director_audit": director_audit,
            "transition": transition,
            "shot": shot,
        },
    }


def schema_bytes() -> bytes:
    return (
        json.dumps(public_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def write_schema(path: Path) -> None:
    path.write_bytes(schema_bytes())


def draft_scaffold(
    *,
    project_id: str,
    delivery_slug: str,
    locked_text: str,
    input_kind: str,
    boundary_lock: str,
    scope: str,
    project_language_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a complete top-level scaffold without pretending Gates are confirmed."""

    source: dict[str, Any] = {
        "input_kind": input_kind,
        "boundary_lock": boundary_lock,
        "scope": scope,
        "delivery_slug": delivery_slug,
        "locked_text": locked_text.replace("\r\n", "\n").replace("\r", "\n"),
        "locked_text_hash": "",
        "approved_corrections": [],
    }
    if project_language_policy is not None:
        source["project_dialogue_language_policy"] = copy.deepcopy(
            project_language_policy
        )
    return {
        "contract_name": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "source_skill": SOURCE_SKILL,
        "source_skill_version": SOURCE_SKILL_VERSION,
        "project_id": project_id,
        "content_hash": "",
        "duration_policy": {
            "zh_chars_per_second": 3.5,
            "en_words_per_second": 2.5,
            "comma_pause_seconds": 0.2,
            "sentence_pause_seconds": 0.4,
            "ellipsis_dash_pause_seconds": 0.6,
        },
        "rhythm_policy": copy.deepcopy(DEFAULT_RHYTHM_POLICY),
        "confirmations": {
            "gate_1": {
                "status": "pending",
                "stage_digest": "",
                "confirmation_order": 1,
                "notes": "",
            },
            "gate_2": {
                "status": "pending",
                "stage_digest": "",
                "confirmation_order": 2,
                "notes": "",
            },
        },
        "source": source,
        "source_analysis": {
            "source_boundary": scope,
            "source_constraints": [],
        },
        "director_profile": {},
        "screen_events": [],
        "shot_plan": {
            "planned_shot_count": 0,
            "planned_edit_point_count": 0,
            "planned_total_duration_seconds": 0,
            "planned_units": [],
            "viewing_decisions": [],
            "edit_points": [],
            "reorders": [],
            "visual_uniformity_reviews": [],
            "dialogue_playbacks": [],
            "rhythm_reviews": [],
        },
        "scenes": [],
        "beats": [],
        "shots": [],
    }
