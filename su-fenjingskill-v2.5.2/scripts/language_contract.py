#!/usr/bin/env python3
"""Unicode-aware helpers for dialogue and Chinese-default execution text."""

from __future__ import annotations

import re
from typing import Iterable


def _family(character: str) -> str | None:
    value = ord(character)
    if (
        0x3400 <= value <= 0x4DBF
        or 0x4E00 <= value <= 0x9FFF
        or 0xF900 <= value <= 0xFAFF
        or 0x20000 <= value <= 0x2FA1F
    ):
        return "han"
    if 0x3040 <= value <= 0x30FF or 0x31F0 <= value <= 0x31FF:
        return "kana"
    if (
        0x1100 <= value <= 0x11FF
        or 0x3130 <= value <= 0x318F
        or 0xAC00 <= value <= 0xD7AF
    ):
        return "hangul"
    if 0x0041 <= value <= 0x005A or 0x0061 <= value <= 0x007A or 0x00C0 <= value <= 0x024F:
        return "latin"
    if 0x0370 <= value <= 0x03FF:
        return "greek"
    if 0x0400 <= value <= 0x052F:
        return "cyrillic"
    if 0x0590 <= value <= 0x05FF:
        return "hebrew"
    if 0x0600 <= value <= 0x06FF or 0x0750 <= value <= 0x077F or 0x08A0 <= value <= 0x08FF:
        return "arabic"
    if 0x0900 <= value <= 0x097F:
        return "devanagari"
    if 0x0E00 <= value <= 0x0E7F:
        return "thai"
    return None


def script_tokens(text: str) -> list[str]:
    """Split alphabetic text whenever its Unicode script family changes.

    Python's Unicode ``\w`` classes treat ``中文POV关系`` as one word.  The
    contract needs three tokens there so a permitted production acronym does
    not make the surrounding Han text look like generated English.
    """

    tokens: list[str] = []
    current: list[str] = []
    current_family: str | None = None
    for character in text:
        family = _family(character) if character.isalpha() else None
        if family is None:
            if current:
                tokens.append("".join(current))
                current = []
                current_family = None
            continue
        if current and family != current_family:
            tokens.append("".join(current))
            current = []
        current.append(character)
        current_family = family
    if current:
        tokens.append("".join(current))
    return tokens


def script_families(text: str) -> set[str]:
    return {
        family
        for character in text
        if character.isalpha() and (family := _family(character)) is not None
    }


def dialogue_script_family(text: str) -> str | None:
    families = script_families(text)
    if not families:
        return None
    if len(families) == 1:
        return next(iter(families))
    return "mixed:" + "+".join(sorted(families))


LANGUAGE_SCRIPT_FAMILIES = {
    "ar": {"arabic"},
    "be": {"cyrillic"},
    "bg": {"cyrillic"},
    "el": {"greek"},
    "en": {"latin"},
    "es": {"latin"},
    "fr": {"latin"},
    "he": {"hebrew"},
    "hi": {"devanagari"},
    "ja": {"han", "kana"},
    "ko": {"hangul", "han"},
    "pt": {"latin"},
    "ru": {"cyrillic"},
    "th": {"thai"},
    "uk": {"cyrillic"},
    "zh": {"han"},
}


def text_matches_language(text: str, language_tag: str) -> bool:
    expected = LANGUAGE_SCRIPT_FAMILIES.get(language_tag.split("-", 1)[0].casefold())
    actual = script_families(text)
    if expected is None or not actual:
        return True
    return bool(actual & expected) and actual <= expected


def disallowed_generated_tokens(
    text: str,
    *,
    locked_text: str,
    standard_terms: Iterable[str],
) -> list[str]:
    """Return non-Han generated words absent from the locked source.

    Chinese Han text is the default generation language. Any Latin, Kana,
    Hangul, Cyrillic, Arabic, or other recognized-script word must either be a
    standard production term or appear verbatim in the locked source.
    """

    allowed_standard = {re.sub(r"[^A-Za-z0-9]+", "", item).upper() for item in standard_terms}
    disallowed: list[str] = []
    for token in script_tokens(text):
        families = script_families(token)
        if not families or families == {"han"}:
            continue
        standard_key = re.sub(r"[^A-Za-z0-9]+", "", token).upper()
        if families == {"latin"} and standard_key in allowed_standard:
            continue
        if token in locked_text:
            continue
        if token not in disallowed:
            disallowed.append(token)
    return disallowed
