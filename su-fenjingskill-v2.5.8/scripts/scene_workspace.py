#!/usr/bin/env python3
"""Extract and merge source-bound per-scene workspaces for long screenplays."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import storyboard_delivery as delivery


WORKSPACE_CONTRACT = "shot-data-scene-workspace/3"
LEGACY_WORKSPACE_CONTRACTS = {
    "shot-data-scene-workspace/1",
    "shot-data-scene-workspace/2",
}


def _items_for_scene(items: Any, scene_id: str) -> list[dict[str, Any]]:
    return [
        copy.deepcopy(item)
        for item in delivery.as_list(items)
        if isinstance(item, dict) and item.get("scene_id") == scene_id
    ]


def _emotion_arc_beat_ids(item: dict[str, Any]) -> set[str]:
    return {
        str(beat_id)
        for phase in delivery.as_list(item.get("phases"))
        if isinstance(phase, dict)
        for beat_id in delivery.as_list(phase.get("beat_ids"))
    }


def _emotion_arcs_for_scene(items: Any, scene_beat_ids: set[str]) -> list[dict[str, Any]]:
    return [
        copy.deepcopy(item)
        for item in delivery.as_list(items)
        if isinstance(item, dict)
        and bool(_emotion_arc_beat_ids(item))
        and _emotion_arc_beat_ids(item) <= scene_beat_ids
    ]


def _scene_slice(data: dict[str, Any], scene_id: str) -> dict[str, Any]:
    scenes = _items_for_scene(data.get("scenes"), scene_id)
    if len(scenes) != 1:
        raise ValueError(f"scene_id `{scene_id}` 必须且只能匹配一个场景。")
    plan = delivery.as_dict(data.get("shot_plan"))
    beat_slice = _items_for_scene(data.get("beats"), scene_id)
    scene_beat_ids = {str(item.get("beat_id")) for item in beat_slice}
    unit_slice = _items_for_scene(plan.get("planned_units"), scene_id)
    unit_ids = {str(item.get("plan_unit_id")) for item in unit_slice}
    decision_slice = [
        copy.deepcopy(item)
        for item in delivery.as_list(plan.get("viewing_decisions"))
        if isinstance(item, dict) and item.get("scene_id") == scene_id
    ]
    edit_slice = [
        copy.deepcopy(item)
        for item in delivery.as_list(plan.get("edit_points"))
        if isinstance(item, dict)
        and item.get("after_plan_unit_id") in unit_ids
        and item.get("before_plan_unit_id") in unit_ids
    ]
    reorder_slice = [
        copy.deepcopy(item)
        for item in delivery.as_list(plan.get("reorders"))
        if isinstance(item, dict)
        and set(map(str, delivery.as_list(item.get("plan_unit_ids")))) <= unit_ids
    ]
    review_slice = [
        copy.deepcopy(item)
        for item in delivery.as_list(plan.get("visual_uniformity_reviews"))
        if isinstance(item, dict) and item.get("scope") == "scene" and item.get("scene_id") == scene_id
    ]
    playback_slice = [
        copy.deepcopy(item)
        for item in delivery.as_list(plan.get("dialogue_playbacks"))
        if isinstance(item, dict) and item.get("scene_id") == scene_id
    ]
    rhythm_review_slice = [
        copy.deepcopy(item)
        for item in delivery.as_list(plan.get("rhythm_reviews"))
        if isinstance(item, dict)
        and item.get("scope") == "scene"
        and item.get("scene_id") == scene_id
    ]
    return {
        "scene_id": scene_id,
        "scene": scenes[0],
        "beats": beat_slice,
        "screen_events": _items_for_scene(data.get("screen_events"), scene_id),
        "planned_units": unit_slice,
        "viewing_decisions": decision_slice,
        "edit_points": edit_slice,
        "reorders": reorder_slice,
        "visual_uniformity_reviews": review_slice,
        "dialogue_playbacks": playback_slice,
        "rhythm_reviews": rhythm_review_slice,
        "emotion_arcs": _emotion_arcs_for_scene(
            data.get("emotion_arcs"), scene_beat_ids
        ),
        "performance_chains": _items_for_scene(data.get("performance_chains"), scene_id),
        "shots": _items_for_scene(data.get("shots"), scene_id),
    }


def _scene_digest(value: dict[str, Any]) -> str:
    canonical_value = copy.deepcopy(value)
    for edit_point in delivery.as_list(canonical_value.get("edit_points")):
        if isinstance(edit_point, dict):
            # IDs are globally numbered derived labels; another scene gaining
            # a cut may renumber this scene without changing its own slice.
            edit_point.pop("edit_point_id", None)
    return hashlib.sha256(delivery.canonical_json_bytes(canonical_value)).hexdigest()


def extract_scene(data: dict[str, Any], scene_id: str) -> dict[str, Any]:
    source = delivery.as_dict(data.get("source"))
    scene_slice = _scene_slice(data, scene_id)
    return {
        "workspace_contract": WORKSPACE_CONTRACT,
        "project_id": data.get("project_id"),
        "locked_text_hash": source.get("locked_text_hash"),
        "gate_1_digest": delivery.stage_digest(data, 1),
        "rhythm_policy": copy.deepcopy(data.get("rhythm_policy")),
        "base_scene_digest": _scene_digest(scene_slice),
        **scene_slice,
    }


def _replace_scene_items(items: Any, replacements: list[dict[str, Any]], scene_id: str) -> list[Any]:
    output: list[Any] = []
    inserted = False
    for item in delivery.as_list(items):
        if isinstance(item, dict) and item.get("scene_id") == scene_id:
            if not inserted:
                output.extend(copy.deepcopy(replacements))
                inserted = True
            continue
        output.append(copy.deepcopy(item))
    if not inserted:
        output.extend(copy.deepcopy(replacements))
    return output


def merge_scene(data: dict[str, Any], workspace: dict[str, Any]) -> dict[str, Any]:
    if workspace.get("workspace_contract") in LEGACY_WORKSPACE_CONTRACTS:
        raise ValueError(
            "scene workspace /1 或 /2 不含 2.5.8 节奏与对白播放合同；"
            "请从当前 draft 重新 extract。"
        )
    if workspace.get("workspace_contract") != WORKSPACE_CONTRACT:
        raise ValueError("不是受支持的 scene workspace 合同。")
    source = delivery.as_dict(data.get("source"))
    if workspace.get("project_id") != data.get("project_id"):
        raise ValueError("scene workspace project_id 与目标 draft 不一致。")
    if workspace.get("locked_text_hash") != source.get("locked_text_hash"):
        raise ValueError("scene workspace 来源 hash 已失效；必须从当前锁源重新导出。")
    if workspace.get("gate_1_digest") != delivery.stage_digest(data, 1):
        raise ValueError("scene workspace Gate 1 风格或来源已失效。")
    if workspace.get("rhythm_policy") != data.get("rhythm_policy"):
        raise ValueError("scene workspace rhythm_policy 与目标 draft 不一致。")
    scene_id = str(workspace.get("scene_id", ""))
    if not scene_id:
        raise ValueError("scene workspace 缺少 scene_id。")
    current_scene_digest = _scene_digest(_scene_slice(data, scene_id))
    if workspace.get("base_scene_digest") != current_scene_digest:
        raise ValueError(
            "scene workspace 场景基线已失效；目标 draft 的同一场景已发生变化。"
        )
    merged = copy.deepcopy(data)
    original_scene_beat_ids = {
        str(item.get("beat_id"))
        for item in _items_for_scene(merged.get("beats"), scene_id)
    }
    merged["scenes"] = _replace_scene_items(
        merged.get("scenes"), [delivery.as_dict(workspace.get("scene"))], scene_id
    )
    for key in ("beats", "screen_events", "performance_chains", "shots"):
        merged[key] = _replace_scene_items(
            merged.get(key),
            [copy.deepcopy(item) for item in delivery.as_list(workspace.get(key)) if isinstance(item, dict)],
            scene_id,
        )
    merged["emotion_arcs"] = [
        copy.deepcopy(item)
        for item in delivery.as_list(merged.get("emotion_arcs"))
        if not (
            isinstance(item, dict)
            and bool(_emotion_arc_beat_ids(item))
            and _emotion_arc_beat_ids(item) <= original_scene_beat_ids
        )
    ] + [
        copy.deepcopy(item)
        for item in delivery.as_list(workspace.get("emotion_arcs"))
        if isinstance(item, dict)
    ]
    plan = delivery.as_dict(merged.get("shot_plan"))
    plan["planned_units"] = _replace_scene_items(
        plan.get("planned_units"),
        [copy.deepcopy(item) for item in delivery.as_list(workspace.get("planned_units")) if isinstance(item, dict)],
        scene_id,
    )
    plan["viewing_decisions"] = _replace_scene_items(
        plan.get("viewing_decisions"),
        [copy.deepcopy(item) for item in delivery.as_list(workspace.get("viewing_decisions")) if isinstance(item, dict)],
        scene_id,
    )
    unit_ids = {
        str(item.get("plan_unit_id"))
        for item in delivery.as_list(plan.get("planned_units"))
        if isinstance(item, dict) and item.get("scene_id") == scene_id
    }
    plan["edit_points"] = [
        copy.deepcopy(item)
        for item in delivery.as_list(plan.get("edit_points"))
        if not (
            isinstance(item, dict)
            and item.get("after_plan_unit_id") in unit_ids
            and item.get("before_plan_unit_id") in unit_ids
        )
    ] + [
        copy.deepcopy(item)
        for item in delivery.as_list(workspace.get("edit_points"))
        if isinstance(item, dict)
    ]
    plan["reorders"] = [
        copy.deepcopy(item)
        for item in delivery.as_list(plan.get("reorders"))
        if not (
            isinstance(item, dict)
            and set(map(str, delivery.as_list(item.get("plan_unit_ids")))) <= unit_ids
        )
    ] + [
        copy.deepcopy(item)
        for item in delivery.as_list(workspace.get("reorders"))
        if isinstance(item, dict)
    ]
    plan["visual_uniformity_reviews"] = [
        copy.deepcopy(item)
        for item in delivery.as_list(plan.get("visual_uniformity_reviews"))
        if not (
            isinstance(item, dict)
            and item.get("scope") == "scene"
            and item.get("scene_id") == scene_id
        )
    ] + [
        copy.deepcopy(item)
        for item in delivery.as_list(workspace.get("visual_uniformity_reviews"))
        if isinstance(item, dict)
    ]
    plan["dialogue_playbacks"] = _replace_scene_items(
        plan.get("dialogue_playbacks"),
        [
            copy.deepcopy(item)
            for item in delivery.as_list(workspace.get("dialogue_playbacks"))
            if isinstance(item, dict)
        ],
        scene_id,
    )
    plan["rhythm_reviews"] = [
        copy.deepcopy(item)
        for item in delivery.as_list(plan.get("rhythm_reviews"))
        if isinstance(item, dict)
        and item.get("scope") == "scene"
        and item.get("scene_id") != scene_id
    ] + [
        copy.deepcopy(item)
        for item in delivery.as_list(workspace.get("rhythm_reviews"))
        if isinstance(item, dict)
        and item.get("scope") == "scene"
        and item.get("scene_id") == scene_id
    ]
    delivery.derive_edit_points(merged)
    units = [item for item in delivery.as_list(plan.get("planned_units")) if isinstance(item, dict)]
    decisions = [item for item in delivery.as_list(plan.get("viewing_decisions")) if isinstance(item, dict)]
    plan["planned_shot_count"] = len(units)
    plan["planned_edit_point_count"] = sum(item.get("mode") == "cut" for item in decisions)
    plan["planned_total_duration_seconds"] = sum(
        int(item.get("estimated_duration_seconds"))
        for item in units
        if delivery.is_json_integer(item.get("estimated_duration_seconds"), 1)
    )
    merged["confirmations"]["gate_2"] = {
        "status": "pending",
        "stage_digest": "",
        "confirmation_order": 2,
        "notes": "场景工作区合并后必须重新展示并确认 Gate 2。",
    }
    merged["content_hash"] = ""
    return merged


def _write_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(delivery.json_bytes(value))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    extract = subparsers.add_parser("extract")
    extract.add_argument("--input", required=True)
    extract.add_argument("--scene-id", required=True)
    extract.add_argument("--output", required=True)
    merge = subparsers.add_parser("merge")
    merge.add_argument("--input", required=True)
    merge.add_argument("--scene-workspace", required=True)
    merge.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        data = delivery.load_json(Path(args.input))
        if args.command == "extract":
            value = extract_scene(data, args.scene_id)
        else:
            workspace = delivery.load_json(Path(args.scene_workspace))
            value = merge_scene(data, workspace)
        _write_new(Path(args.output), value)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
