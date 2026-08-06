#!/usr/bin/env python3
"""Generate individual 16:9 panel PNGs from a su-image9 panel_plan.

This script is the image-generation stage of the su-image9 v2.1.2 pipeline.
It reads panel_plan.json and final_image_prompts.compiled.md, extracts each
panel prompt, and delegates to a configurable image backend. In v2.1.2 the
default backend is a stub that writes placeholder PNGs; real model integration
is a follow-up task.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import time
import zlib
from pathlib import Path
from typing import Any


VERSION = "2.1.2"
SCHEMA_VERSION = "2.1"

EXIT_PASS = 0
EXIT_CONTRACT_FAIL = 2
EXIT_TOOL_ERROR = 3


class ToolError(RuntimeError):
    pass


def clean_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\s+", " ", text).strip()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} root must be an object")
    return value


def extract_panel_prompt(compiled_prompts: str, page_id: str, panel_id: str) -> str:
    """Extract the PANEL sentence for a specific panel from compiled prompts."""
    lines = compiled_prompts.splitlines()
    in_page = False
    panel_prefix = f"{panel_id}:"
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and stripped[2:].strip() == page_id:
            in_page = True
            continue
        if in_page and stripped.startswith("# "):
            break
        if in_page and stripped.startswith(panel_prefix):
            return stripped[len(panel_prefix):].strip()
    return ""


def get_backend() -> str:
    """Return the configured image generation backend name."""
    # In v2.1.2 only the stub backend is provided. Future backends can be
    # selected via environment variable SU_IMAGE9_BACKEND.
    import os

    return clean_text(os.environ.get("SU_IMAGE9_BACKEND", "stub"))


def generate_stub(prompt: str, output_path: Path) -> None:
    """Write a valid placeholder 16:9 grayscale PNG without external dependencies."""
    width, height = 1280, 720

    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        return len(data).to_bytes(4, "big") + chunk + zlib.crc32(chunk).to_bytes(4, "big")

    # Grayscale 8-bit image; each scanline starts with filter byte 0 (raw).
    scanline = b"\x00" + bytes(127 for _ in range(width))
    raw = scanline * height
    compressed = zlib.compress(raw)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x00\x00\x00\x00"
    ihdr = png_chunk(b"IHDR", ihdr_data)
    idat = png_chunk(b"IDAT", compressed)
    iend = png_chunk(b"IEND", b"")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(signature + ihdr + idat + iend)

    # Embed the prompt hash in a sidecar txt file for QA/debugging.
    (output_path.parent / f"{output_path.stem}.prompt_hash.txt").write_text(
        sha256_text(prompt), encoding="utf-8"
    )


def generate_panel(prompt: str, output_path: Path, backend: str) -> tuple[bool, str]:
    """Generate a single panel. Returns (success, backend_used)."""
    if backend == "stub":
        try:
            generate_stub(prompt, output_path)
            return True, backend
        except Exception as exc:
            return False, f"stub failed: {exc}"
    return False, f"unknown backend: {backend}"


def generate_panels(
    panel_plan: dict[str, Any],
    compiled_prompts: str,
    out_dir: Path,
    max_retries: int,
) -> dict[str, Any]:
    backend = get_backend()
    pages_records: list[dict[str, Any]] = []
    total_attempts = 0
    failed_panels: list[str] = []

    for page in panel_plan.get("pages", []):
        if not isinstance(page, dict):
            continue
        page_id = page.get("page")
        page_record: dict[str, Any] = {
            "page": page_id,
            "panels": [],
        }
        page_dir = out_dir / str(page_id)
        for panel in page.get("panels", []):
            if not isinstance(panel, dict):
                continue
            panel_id = panel.get("panel")
            display_label = panel.get("display_label", panel_id)
            prompt = extract_panel_prompt(compiled_prompts, str(page_id), str(panel_id))
            if not prompt:
                failed_panels.append(f"{page_id}/{panel_id}")
                page_record["panels"].append(
                    {
                        "panel": panel_id,
                        "display_label": display_label,
                        "status": "FAILED",
                        "reason": "prompt not found in compiled prompts",
                        "attempts": 0,
                        "output": None,
                    }
                )
                continue

            output_path = page_dir / f"{panel_id}.png"
            attempts = 0
            success = False
            last_reason = ""
            while attempts <= max_retries and not success:
                attempts += 1
                total_attempts += 1
                success, reason = generate_panel(prompt, output_path, backend)
                if not success:
                    last_reason = reason
                    if output_path.exists():
                        output_path.unlink()

            if success:
                page_record["panels"].append(
                    {
                        "panel": panel_id,
                        "display_label": display_label,
                        "status": "OK",
                        "attempts": attempts,
                        "output": str(output_path),
                        "prompt_hash": sha256_text(prompt),
                    }
                )
            else:
                failed_panels.append(f"{page_id}/{panel_id}")
                page_record["panels"].append(
                    {
                        "panel": panel_id,
                        "display_label": display_label,
                        "status": "FAILED",
                        "reason": last_reason,
                        "attempts": attempts,
                        "output": None,
                        "prompt_hash": sha256_text(prompt),
                    }
                )
        pages_records.append(page_record)

    status = "PASS" if not failed_panels else "REVIEW_REQUIRED"
    return {
        "skill": "su-image9",
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "backend": backend,
        "total_attempts": total_attempts,
        "failed_panels": failed_panels,
        "pages": pages_records,
    }


def write_outputs(out_dir: Path, manifest: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "attempt_log.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-plan", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--max-retries", type=int, default=2)
    args = parser.parse_args(argv)

    if args.out_dir.exists():
        print("CONTRACT_FAIL: --out-dir must be absent", file=sys.stderr)
        return EXIT_CONTRACT_FAIL

    try:
        panel_plan = load_json(args.panel_plan)
        if panel_plan.get("release_ready") is not True:
            raise ValueError("panel_plan.release_ready must be true before generation")
        compiled_path = args.panel_plan.parent / "final_image_prompts.compiled.md"
        if not compiled_path.is_file():
            raise ValueError(f"compiled prompts not found: {compiled_path}")
        compiled_prompts = compiled_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"CONTRACT_FAIL: {exc}", file=sys.stderr)
        return EXIT_CONTRACT_FAIL

    try:
        out_dir = args.out_dir.resolve()
        out_dir.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f".{out_dir.name}-gen-", dir=out_dir.parent) as temp_name:
            staging_dir = Path(temp_name) / "panels"
            manifest = generate_panels(panel_plan, compiled_prompts, staging_dir, args.max_retries)
            staging_dir.rename(out_dir)
        write_outputs(out_dir, manifest)
        return EXIT_PASS if manifest["status"] == "PASS" else EXIT_CONTRACT_FAIL
    except ToolError as exc:
        print(f"TOOL_ERROR: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    except Exception as exc:
        print(f"TOOL_ERROR: unexpected failure: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
