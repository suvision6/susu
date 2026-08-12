#!/usr/bin/env python3
"""Concurrency and crash-detection helpers for storyboard delivery bundles."""

from __future__ import annotations

import contextlib
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Iterator, Mapping


MANIFEST_FILENAME = ".storyboard-delivery-manifest.json"


def durable_write_bytes(path: Path, payload: bytes) -> None:
    """Write one temporary payload and flush it before publication."""

    with path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def fsync_file(path: Path) -> None:
    """Flush a file produced by a library-managed writer such as zipfile."""

    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def fsync_directory(path: Path) -> None:
    """Persist directory-entry updates where the host filesystem supports it."""

    descriptor = os.open(path, os.O_RDONLY)
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if exc.errno not in {errno.EINVAL, errno.ENOTSUP}:
                raise
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def exclusive_output_lock(output_dir: Path) -> Iterator[None]:
    """Serialize builders targeting one output directory."""

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir.parent / f".{output_dir.name}.storyboard-delivery.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def manifest_payload(
    payloads: Mapping[str, bytes],
    *,
    contract: str,
    gate_2_rule_revision: str,
) -> dict[str, object]:
    return {
        "contract": contract,
        "gate_2_rule_revision": gate_2_rule_revision,
        "status": "complete",
        "files": {
            name: {"sha256": sha256_bytes(payload), "size": len(payload)}
            for name, payload in sorted(payloads.items())
        },
    }


def manifest_bytes(value: dict[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def validate_manifest(
    output_dir: Path,
    named_paths: Mapping[str, Path],
    *,
    contract: str,
    gate_2_rule_revision: str,
) -> tuple[bool, str]:
    manifest_path = output_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return False, "交付事务 manifest 缺失，无法证明四文件来自同一次完整提交。"
    try:
        actual = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return False, f"交付事务 manifest 无法读取：{exc}"
    try:
        payloads = {name: path.read_bytes() for name, path in named_paths.items()}
    except OSError as exc:
        return False, f"交付文件无法用于 manifest 复核：{exc}"
    expected = manifest_payload(
        payloads,
        contract=contract,
        gate_2_rule_revision=gate_2_rule_revision,
    )
    if actual != expected:
        return False, "交付事务 manifest 与当前四文件 hash/size 不一致。"
    return True, ""
