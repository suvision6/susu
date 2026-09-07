"""Small, deterministic primitives; no creative or network decisions."""
from __future__ import annotations
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

VERSION = "2.1.0"

class DeliveryError(ValueError):
    pass

def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()

def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")

def object_hash(value: Any) -> str:
    return digest(json_bytes(value))

def load_json(payload: bytes | str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise DeliveryError(f"重复 JSON 字段：{key}")
            result[key] = value
        return result
    def invalid(value):
        raise DeliveryError(f"非有限数值：{value}")
    try:
        return json.loads(payload, object_pairs_hook=pairs, parse_constant=invalid)
    except (ValueError, UnicodeError) as exc:
        raise DeliveryError(f"JSON 无法读取：{exc}") from exc

def seconds(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise DeliveryError("时长不能是布尔值")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise DeliveryError(f"无效时长：{value!r}") from exc
    if not result.is_finite() or result <= 0:
        raise DeliveryError("来源时长必须为有限正数，未知请留空")
    return result

def number_text(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")

def slug_for(name: str, payload: bytes) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", Path(name).stem.casefold()).strip("-")
    return value or "source-" + digest(payload)[:10]

def leaves(value: Any, path: str = ""):
    """Yield every scalar with its exact path; never deduplicate by similarity."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaves(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from leaves(child, f"{path}[{index}]")
    elif value is not None and value != "":
        yield path, value

def text_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    return "；".join(str(v) for _, v in leaves(value))

def issue(code: str, message: str, source_id: str = "", severity: str = "ERROR") -> dict:
    return {"code": code, "message": message, "source_id": source_id, "severity": severity}

POSITIONS = {
    "onscreen": "画内", "on_screen": "画内", "画内": "画内",
    "os": "画外", "offscreen": "画外", "off_screen": "画外", "画外": "画外",
    "vo": "旁白", "voiceover": "旁白", "voice_over": "旁白", "narration": "旁白", "旁白": "旁白",
    "mediated": "媒介声", "mediated_source": "媒介声", "电话": "电话", "媒介声": "媒介声",
}

def position_label(value: Any) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    if raw.casefold() not in POSITIONS:
        raise DeliveryError(f"声位尚未识别：{raw}")
    return POSITIONS[raw.casefold()]
