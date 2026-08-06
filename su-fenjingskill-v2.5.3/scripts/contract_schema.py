#!/usr/bin/env python3
"""Machine-authoritative structural schema for shot-data/2.5.3.

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
CONTRACT_VERSION = "2.5.3"
SOURCE_SKILL = "su-fenjingskill"
SOURCE_SKILL_VERSION = "2.5.3"
GATE_2_RULE_REVISION = "2.5.3-binding-integrity-r1"

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
        {"start", "end", "text_hash"},
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
        "approved_corrections": {"type": "array", "items": {"type": "object"}},
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
    top_properties = {key: {} for key in TOP_LEVEL_KEYS}
    top_properties.update(
        {
            "contract_name": {"const": CONTRACT_NAME},
            "contract_version": {"const": CONTRACT_VERSION},
            "source_skill": {"const": SOURCE_SKILL},
            "source_skill_version": {"const": SOURCE_SKILL_VERSION},
            "project_id": nonempty,
            "content_hash": string,
            "confirmations": _closed_object(
                {"gate_1": confirmation, "gate_2": confirmation},
                set(CONFIRMATION_KEYS),
            ),
            "source": _closed_object(
                source_properties, SOURCE_REQUIRED_KEYS
            ),
            "director_profile": profile,
            "screen_events": {"type": "array", "items": {"type": "object"}},
            "shot_plan": _closed_object(
                {key: {} for key in SHOT_PLAN_KEYS}, SHOT_PLAN_KEYS
            ),
            "scenes": {"type": "array", "items": {"type": "object"}},
            "beats": {"type": "array", "items": {"type": "object"}},
            "shots": {"type": "array", "items": {"type": "object"}},
        }
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://suvision6.github.io/susu/shot-data-2.5.3.schema.json",
        "title": "shot-data/2.5.3 public structure",
        "$comment": (
            "Machine authority for public keys and basic types. Cross-object director "
            "semantics are validated by storyboard_delivery.py."
        ),
        **_closed_object(top_properties, TOP_LEVEL_REQUIRED_KEYS),
        "$defs": {
            "source_span": span,
            "director_profile": profile,
            "dialogue_language_policy": local_policy,
            "project_dialogue_language_policy": project_policy,
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
        },
        "scenes": [],
        "beats": [],
        "shots": [],
    }
