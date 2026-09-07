"""Lossless Markdown authoring boundary. Export never rewrites these strings."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
import json
import re
from .common import DeliveryError, number_text, seconds
from .source import Source

CONTRACT = "prompt-master/2.1.0"

@dataclass
class Unit:
    id: str
    source_ids: list[str]
    text: str
    duration: Decimal | None = None
    operation: str = "OP001"

@dataclass
class Master:
    source_sha256: str
    scope: list[str]
    units: list[Unit]
    payload: bytes = b""


def _array(value: str) -> list[str]:
    try:
        result = json.loads(value)
    except ValueError as exc:
        raise DeliveryError("来源范围必须是 JSON 字符串数组") from exc
    if not isinstance(result, list) or not result or any(not isinstance(x, str) or not x for x in result):
        raise DeliveryError("来源范围必须是非空字符串数组")
    return result


def write_master(master: Master) -> bytes:
    lines = ["# Prompt 主稿", "合同：" + CONTRACT, "来源SHA256：" + master.source_sha256,
             "范围：" + json.dumps(master.scope, ensure_ascii=False), ""]
    for unit in master.units:
        run = max((len(x) for x in re.findall(r"`+", unit.text)), default=0)
        fence = "`" * max(3, run + 1)
        lines.extend(["## " + unit.id, "来源：" + json.dumps(unit.source_ids, ensure_ascii=False),
                      "时长：" + number_text(unit.duration), "操作：" + unit.operation,
                      fence + "prompt", unit.text, fence, ""])
    return ("\n".join(lines) + "\n").encode("utf-8")


def read_master(payload: bytes) -> Master:
    try:
        lines = payload.decode("utf-8-sig").splitlines(keepends=True)
    except UnicodeError as exc:
        raise DeliveryError("Markdown 主稿不是 UTF-8") from exc
    root = {}; current = None; units = []; seen = set(); index = 0
    while index < len(lines):
        line = lines[index].rstrip("\r\n")
        index += 1
        if not line.strip() or line == "# Prompt 主稿":
            continue
        if line.startswith("## "):
            if current is not None:
                raise DeliveryError("上一单元缺少完整 prompt 围栏")
            uid = line[3:]
            if not re.fullmatch(r"[A-Za-z0-9_-]+", uid) or uid in seen:
                raise DeliveryError(f"段号无效或重复：{uid}")
            seen.add(uid); current = {"id": uid}; continue
        match = re.fullmatch(r"(`{3,})prompt", line)
        if match:
            if current is None:
                raise DeliveryError("prompt 围栏缺少段号")
            required = {"id", "来源", "时长", "操作"}
            if set(current) != required:
                raise DeliveryError(f"{current['id']} 元信息缺失或有未知字段")
            fence = match[1]; body = []
            while index < len(lines) and lines[index].rstrip("\r\n") != fence:
                body.append(lines[index]); index += 1
            if index >= len(lines):
                raise DeliveryError(f"{current['id']} 围栏未闭合")
            index += 1
            text = "".join(body)
            # Remove the one structural newline added before the closing fence.
            if text.endswith("\r\n"):
                text = text[:-2]
            elif text.endswith("\n"):
                text = text[:-1]
            units.append(Unit(current["id"], _array(current["来源"]), text,
                              seconds(current["时长"]), current["操作"]))
            current = None; continue
        if "：" not in line:
            raise DeliveryError(f"无法识别主稿第 {index} 行；正文须放在 prompt 围栏内")
        key, value = line.split("：", 1)
        target = root if current is None else current
        allowed = {"合同", "来源SHA256", "范围"} if current is None else {"来源", "时长", "操作"}
        if key not in allowed or key in target:
            raise DeliveryError(f"重复或未知主稿字段：{key}")
        target[key] = value
    if current is not None or set(root) != {"合同", "来源SHA256", "范围"} or not units:
        raise DeliveryError("主稿不完整")
    if root["合同"] != CONTRACT or not re.fullmatch(r"[a-f0-9]{64}", root["来源SHA256"]):
        raise DeliveryError("主稿合同或来源 SHA256 无效")
    if any(not u.operation for u in units):
        raise DeliveryError("操作 ID 不能为空")
    return Master(root["来源SHA256"], _array(root["范围"]), units, payload)


def _dialogue_line(event: dict) -> str:
    label = event["speaker"] or "说话人未提供"
    if event["position"]:
        label += "（" + event["position"] + "）"
    return f"{label}：“{event['text']}”"


def draft_master(source: Source) -> Master:
    """Conservative compatibility draft, explicitly NOT a semantic rewrite.

No global logline, inferred timing, merge, camera or acting decisions are added.
Every sourced fact stays intact; the Agent writes the final natural-language master.
"""
    units = []
    for shot in source.shots:
        parts = []
        if shot["scene"]:
            parts.append(shot["scene"])
        heading = "Cut 1" if shot["kind"] == "shot" else "事件阶段"
        parts.append(heading)
        for fact in shot["facts"]:
            text = fact["text"]
            path = fact["path"]
            # These labels translate enums, not performance or timing facts.
            if path.endswith("movement.type"):
                text = {"fixed": "镜头固定。", "static": "镜头固定。"}.get(text, text)
            if path.startswith(("subjects", "visible_subjects", "offscreen_subjects", "staging.subjects", "staging.visible_subjects", "staging.offscreen_subjects")):
                continue
            parts.append(text)
        parts.extend(_dialogue_line(e) for e in shot["dialogue"])
        units.append(Unit(f"PU{len(units)+1:03d}", [shot["id"]], "\n".join(parts), shot["duration"]))
    master = Master(source.sha256, [s["id"] for s in source.shots], units)
    master.payload = write_master(master)
    return master
