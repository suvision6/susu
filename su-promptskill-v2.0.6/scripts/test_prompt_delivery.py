#!/usr/bin/env python3
"""Compatibility runner for modular su-promptskill regression tests."""

from __future__ import annotations

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Runs unittest discovery for the modular regression package."

from pathlib import Path
import sys
import unittest


def main() -> int:
    skill_root = Path(__file__).resolve().parents[1]
    if str(skill_root) not in sys.path:
        sys.path.insert(0, str(skill_root))
    suite = unittest.defaultTestLoader.discover(
        str(skill_root / "tests"),
        pattern="test_prompt_part_*.py",
        top_level_dir=str(skill_root),
    )
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
