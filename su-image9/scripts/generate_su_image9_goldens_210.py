#!/usr/bin/env python3
"""Regenerate the three checked-in su-image9 2.1.1 golden packages."""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable


SCRIPT_DIR = Path(__file__).resolve().parent


def find_fenjing_script_dir(start: Path) -> Path:
    for parent in (start, *start.parents):
        for candidate in (
            parent / "su-fenjingskill-zh" / "scripts",
            parent / "skills" / "su-fenjingskill-zh" / "scripts",
        ):
            if (candidate / "storyboard_delivery.py").is_file() and (
                candidate / "test_storyboard_delivery.py"
            ).is_file():
                return candidate
    raise RuntimeError("could not locate the su-fenjingskill-zh 2.4.2 scripts")


FENJING_SCRIPT_DIR = find_fenjing_script_dir(SCRIPT_DIR)
GOLDEN_ROOT = SCRIPT_DIR.parent / "tests" / "goldens"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(FENJING_SCRIPT_DIR))

import derive_su_image9_prompt_package as derive
import storyboard_delivery as delivery


fixture_spec = importlib.util.spec_from_file_location(
    "su_fenjing_242_golden_fixture",
    FENJING_SCRIPT_DIR / "test_storyboard_delivery.py",
)
if fixture_spec is None or fixture_spec.loader is None:
    raise RuntimeError("could not load the real su-fenjingskill-zh 2.4.2 fixture")
upstream_fixture = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(upstream_fixture)


LOCKED_FILES = (
    "panel_plan.json",
    "page-map.json",
    "final_image_prompts.md",
    "final_image_prompts.compiled.md",
    "validation_report.json",
)


def source_spans(lines: list[str]) -> tuple[str, list[dict[str, int]]]:
    text = "\n".join(lines)
    spans: list[dict[str, int]] = []
    position = 0
    for line in lines:
        spans.append({"start": position, "end": position + len(line)})
        position += len(line) + 1
    return text, spans


def prop_fact(beat_id: str, number: int, text: str) -> dict:
    fact_id = f"{beat_id}-F{number:02d}"
    return {
        "fact_id": fact_id,
        "type": "prop",
        "text": text,
        "cut_priority": "normal",
        "cut_reasons": [],
        "cut_group": fact_id,
        "cut_category": "prop",
        "cut_moment_id": f"{beat_id}-prop-moment",
    }


def build_rich_source(*, city: bool) -> dict:
    data = upstream_fixture.valid_data_242()
    data["human_reviews"].append(
        {
            "gate": "GATE_C",
            "round": 1,
            "status": "approved",
            "reviewer": "user",
            "notes": "final-signoff approved for image derivation",
        }
    )
    if city:
        title = "金样-城市车辆"
        scene = "1 城市街道 日 外"
        lines = [
            "A和B站在路边轿车旁，A握着车钥匙。",
            "A和B走到驾驶门边，A仍握着车钥匙。",
            "B说：出发。",
        ]
        primary_prop = "轿车"
        hand_prop = "车钥匙"
        start_position = "路边"
        end_position = "驾驶门边"
        fixed_objects = ["道路边线", "路灯"]
        first_camera = (
            "[平视, 双人中景, 固定镜头]\n"
            "【机位逻辑】摄影机位于道路同侧，沿轿车侧面看向A与B。\n"
            "【场景首镜站位】（A在路边轿车驾驶门外，B在车头一侧，两人同处轴线一侧。）\n"
            "A和B站在路边轿车旁，A握着车钥匙。"
        )
        second_camera = (
            "[侧面平视, 双人中景, 横移跟拍]\n"
            "【机位逻辑】摄影机沿道路同侧跟随A移动，不越过车辆轴线。\n"
            "【站位位移】A从路边走到驾驶门边，B留在车头一侧。\n"
            "A到达驾驶门边仍握着车钥匙，B说：“出发。”"
        )
        notes = ("锁定城市车辆与人物起始位置。", "车辆与人物轴线保持不变。")
        dialogue_text = "出发。"
    else:
        title = "金样-双人对话轴线"
        scene = "1 会客室 日 内"
        lines = [
            "A和B站在门口，A握着钥匙。",
            "A和B走到桌边，A仍握着钥匙。",
            "B说：到了。",
        ]
        primary_prop = "钥匙"
        hand_prop = "钥匙"
        start_position = "门口"
        end_position = "桌边"
        fixed_objects = ["门", "桌子"]
        first_camera = (
            "[平视, 双人中景, 固定镜头]\n"
            "【机位逻辑】摄影机位于人物关系轴同侧，从桌边看向门口。\n"
            "【场景首镜站位】（A在门口，B在桌边，两人相对。）\n"
            "A和B站在门口，A握着钥匙。"
        )
        second_camera = (
            "[同侧三分之四, 双人中景, 轻微横移]\n"
            "【机位逻辑】摄影机保持人物关系轴同侧，跟随A走向桌边。\n"
            "【站位位移】A从门口走到桌边，B留在桌边并面向A。\n"
            "A到达桌边仍握着钥匙，B说：“到了。”"
        )
        notes = ("建立双人关系轴和初始站位。", "保持同侧反打方向与眼线。")
        dialogue_text = "到了。"

    locked_text, spans = source_spans(lines)
    data["metadata"]["title"] = title
    data["script_lock"].update(
        {
            "locked_text": locked_text,
            "locked_text_hash": delivery.script_text_hash(locked_text),
            "approved_script_path": f"outputs/2026-07-11/docs/{title}.approved_script.txt",
        }
    )
    prop_names = list(dict.fromkeys((primary_prop, hand_prop)))
    log = data["continuity_logs"][0]
    log.update(
        {
            "scene": scene,
            "spatial_axis": "A与B保持同侧关系，A从起点移向终点，摄影机不跨轴。",
            "fixed_objects": fixed_objects,
            "characters": [
                {"name": "A", "position": start_position, "facing": "B"},
                {"name": "B", "position": "车头一侧" if city else "桌边", "facing": "A"},
            ],
            "props": [
                {"name": name, "owner": "A", "state": "握在手中" if name == hand_prop else "位置锁定"}
                for name in prop_names
            ],
            "reality_layer": "现实",
        }
    )

    for beat, line, span in zip(data["beats"], lines, spans):
        beat.update({"scene": scene, "source_text": line, "source_span": span})
    data["beats"][0]["facts"][0].update({"type": "position", "text": lines[0], "cut_category": "space"})
    data["beats"][0]["facts"].append(prop_fact("B001", 2, hand_prop))
    data["beats"][1]["facts"][0].update({"type": "position", "text": lines[1], "cut_category": "space"})
    data["beats"][1]["facts"].append(prop_fact("B002", 2, hand_prop))
    data["beats"][2]["facts"][0].update({"type": "dialogue", "text": dialogue_text, "cut_category": "dialogue"})

    first, second = data["shots"]
    first.update(
        {
            "scene": scene,
            "source_paragraph": lines[0],
            "source_span": spans[0],
            "covered_fact_ids": ["B001-F01", "B001-F02"],
            "camera_main_image": first_camera,
            "notes": notes[0],
            "visible_characters": ["A", "B"],
            "visible_props": prop_names,
        }
    )
    second.update(
        {
            "scene": scene,
            "source_paragraph": lines[1] + lines[2],
            "source_spans": [spans[1], spans[2]],
            "covered_fact_ids": ["B002-F01", "B002-F02", "B003-F01"],
            "camera_main_image": second_camera,
            "notes": notes[1],
            "visible_characters": ["A", "B"],
            "visible_props": prop_names,
        }
    )
    second["continuity_updates"][0].update({"from": start_position, "to": end_position})
    return data


def finalize_upstream(data: dict) -> dict:
    delivery.derive_prompts(data)
    data["warn_resolutions"] = []
    preliminary = delivery.validate_data(data, strict_status=False, final_signoff=True)
    non_resolution_errors = [
        message for message in preliminary.errors if not message.startswith("WARN 缺少处置记录：")
    ]
    if non_resolution_errors:
        raise RuntimeError(f"upstream golden fixture failed before WARN resolution: {non_resolution_errors}")
    if preliminary.warnings:
        resolved_by = (
            "auto_whitelist"
            if all(delivery.is_auto_whitelist_warning(message) for message in preliminary.warnings)
            else "human"
        )
        upstream_fixture.resolve_warnings(data, preliminary, resolved_by=resolved_by)
    final = delivery.validate_data(data, strict_status=False, final_signoff=True)
    if final.errors:
        raise RuntimeError(f"upstream golden fixture failed: {final.errors}")
    delivery.update_validation_report(data, final)
    strict = delivery.validate_data(data, strict_status=True, final_signoff=True)
    if strict.errors:
        raise RuntimeError(f"upstream signed golden fixture failed: {strict.errors}")
    return data


def city_vehicle() -> dict:
    return finalize_upstream(build_rich_source(city=True))


def dialogue_axis() -> dict:
    data = build_rich_source(city=False)
    first, second = data["shots"]
    merged = copy.deepcopy(first)
    merged.update(
        {
            "beat_ids": ["B001", "B002", "B003"],
            "covered_fact_ids": ["B001-F01", "B001-F02", "B002-F01", "B002-F02", "B003-F01"],
            "source_paragraph": "".join(beat["source_text"] for beat in data["beats"]),
            "source_spans": [beat["source_span"] for beat in data["beats"]],
            "duration_seconds": 5,
            "duration_breakdown": {
                "sync_action_seconds": 3,
                "sync_dialogue_seconds": 1,
                "non_sync_action_seconds": 0,
                "emotional_pause_seconds": 2,
            },
            "camera_main_image": (
                "[同侧三分之四, 双人中景, 轻微横移]\n"
                "【机位逻辑】摄影机保持人物关系轴同侧，从门口方向跟随A走向B。\n"
                "【场景首镜站位】（A在门口，B在桌边，两人相对。）\n"
                "【站位位移】A从门口走到桌边，B留在桌边并面向A。\n"
                "A握着钥匙走到B面前，B说：“到了。”"
            ),
            "notes": "单镜保持双人关系轴、眼线和动作阶段。",
            "continuity_updates": copy.deepcopy(second["continuity_updates"]),
            "shot_type": "master",
            "split_reason": ["spatial_anchor", "performance_continuity", "continuity_migration"],
        }
    )
    merged.pop("source_span", None)
    data["shots"] = [merged]
    return finalize_upstream(data)


def sparse_multi_reality() -> dict:
    data = build_rich_source(city=False)
    data["metadata"]["title"] = "金样-稀疏多现实层"
    data["shots"][0]["reality_layer"] = "现实"
    data["shots"][1]["reality_layer"] = "回忆"
    return finalize_upstream(data)


CASES: tuple[tuple[str, Callable[[], dict]], ...] = (
    ("city-vehicle", city_vehicle),
    ("dialogue-axis", dialogue_axis),
    ("sparse-multi-reality", sparse_multi_reality),
)


def generate_case(slug: str, builder: Callable[[], dict]) -> None:
    case_dir = GOLDEN_ROOT / slug
    case_dir.mkdir(parents=True, exist_ok=True)
    source_path = case_dir / "shot_data.json"
    source_path.write_text(
        json.dumps(builder(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with tempfile.TemporaryDirectory(prefix=f"su-image9-golden-{slug}-") as temp_name:
        out_dir = Path(temp_name) / "package"
        code = derive.main(["--shot-data", str(source_path), "--out-dir", str(out_dir)])
        if code != derive.EXIT_PASS:
            report = out_dir / "validation_report.json"
            detail = report.read_text(encoding="utf-8") if report.is_file() else "no report"
            raise RuntimeError(f"{slug} generation failed with {code}: {detail}")
        for name in LOCKED_FILES:
            shutil.copyfile(out_dir / name, case_dir / name)


def main() -> int:
    for slug, builder in CASES:
        generate_case(slug, builder)
        print(f"updated {slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
