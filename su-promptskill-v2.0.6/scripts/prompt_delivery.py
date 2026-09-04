#!/usr/bin/env python3
"""Compatibility facade for modular prompt-plan/2.0.6 delivery implementation."""

from __future__ import annotations

SCRIPT_INTERFACE = "cli"
SCRIPT_INTERFACE_REASON = "Public build/validate CLI and import-compatible API facade."

import sys
import types
import argparse as _argparse

import prompt_skill as _implementation
from prompt_skill import *


class _LinkedFacade(types.ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        for module in _implementation._modules:
            if hasattr(module, name):
                setattr(module, name, value)


sys.modules[__name__].__class__ = _LinkedFacade


if __name__ == "__main__":
    raise SystemExit(main())
