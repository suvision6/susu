#!/usr/bin/env python3
"""Unicode-aware helpers for dialogue and Chinese-default execution text."""

from __future__ import annotations

import re
from typing import Iterable


# Embedded foreign-script thresholds for Chinese-default generation.
# A short Latin word like "OK", "iPhone", "100%" inside Chinese text should not
# invalidate the zh-CN language tag.
EMBEDDED_LATIN_MAX_LENGTH = 6
EMBEDDED_FOREIGN_RATIO = 0.15
EMBEDDED_FOREIGN_TOTAL_LENGTH = 8


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

    Python's Unicode ``\\w`` classes treat ``中文POV关系`` as one word.  The
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


# Common global brand/product names that are effectively loanwords in Chinese
# text and should not invalidate the zh-CN tag regardless of length.
EMBEDDED_BRAND_NAMES = {
    "starbucks", "iphone", "ipad", "macbook", "airpods", "huawei", "xiaomi",
    "wechat", "alipay", "tiktok", "sony", "canon", "nike", "adidas",
}


def _token_alpha_only(token: str) -> str:
    """Return lowercase alphabetic characters only, stripping digits and marks."""
    return re.sub(r"[^A-Za-z]", "", token).casefold()


def _is_embedded_foreign(token: str, *, primary_family: str | None) -> bool:
    """Return True if a foreign-script token is short enough to be treated as
    embedded inside a primary-language text (e.g. "OK", "iPhone", "100%").
    """

    families = script_families(token)
    if not families:
        return True
    if families == {"latin"}:
        # Short Latin acronyms, brand names, percentages are treated as embedded.
        alpha_len = sum(1 for c in token if c.isalpha())
        if alpha_len <= EMBEDDED_LATIN_MAX_LENGTH:
            return True
        alpha_only = _token_alpha_only(token)
        if alpha_only in EMBEDDED_BRAND_NAMES:
            return True
    # If the token's families are a subset of the expected language families,
    # treat it as embedded (e.g. kana in Japanese, hangul in Korean).
    if primary_family is not None:
        expected = LANGUAGE_SCRIPT_FAMILIES.get(primary_family.casefold().split("-")[0])
        if expected is not None and families <= expected:
            return True
    return False


def _foreign_alpha_blocks(text: str) -> list[tuple[str, int]]:
    """Return contiguous alphabetic blocks that are not the primary script,
    merging adjacent Latin words separated only by whitespace/punctuation.
    Each tuple contains the block text and its alphabetic character count.
    """

    blocks: list[tuple[str, int]] = []
    current: list[str] = []
    current_family: str | None = None

    def flush() -> None:
        nonlocal current, current_family
        if current:
            block = "".join(current)
            blocks.append((block, sum(1 for c in block if c.isalpha())))
            current = []
            current_family = None

    for index, character in enumerate(text):
        family = _family(character) if character.isalpha() else None
        if family is None:
            # Whitespace and common punctuation between Latin words keep the
            # block open so that "My name is John" is treated as one phrase.
            if current_family == "latin" and character in " \t\n.,;:!?\"'()-":
                current.append(character)
                continue
            flush()
            continue
        if current_family is None:
            current_family = family
            current = [character]
        elif family == current_family:
            current.append(character)
        else:
            flush()
            current_family = family
            current = [character]
    flush()
    return blocks


def text_matches_language(text: str, language_tag: str) -> bool:
    """Check whether ``text`` is compatible with ``language_tag``.

    Small embedded foreign words (brand names, acronyms, percentages) do not
    invalidate a Chinese (or other primary-language) tag.  Only when a
    substantial portion of the text is in an unexpected script does the check
    return False.
    """

    expected = LANGUAGE_SCRIPT_FAMILIES.get(language_tag.split("-", 1)[0].casefold())
    actual = script_families(text)
    if expected is None or not actual:
        return True

    # Pure primary language: fast path.
    if actual <= expected:
        return True

    # Mixed scripts.  First, detect any contiguous foreign block that is long
    # enough to be an independent phrase/sentence in an unexpected language.
    total_foreign_alpha = 0
    total_alpha = 0
    for block, alpha_len in _foreign_alpha_blocks(text):
        total_alpha += alpha_len
        block_families = script_families(block)
        if not block_families or block_families <= expected:
            continue
        if _is_embedded_foreign(block, primary_family=language_tag):
            continue
        # A long contiguous foreign block invalidates the tag immediately.
        if alpha_len >= EMBEDDED_FOREIGN_TOTAL_LENGTH:
            return False
        total_foreign_alpha += alpha_len

    if total_alpha == 0:
        return True
    # Also fail when the aggregate unexpected foreign script exceeds the ratio.
    if total_foreign_alpha / total_alpha <= EMBEDDED_FOREIGN_RATIO:
        return True
    return False


def disallowed_generated_tokens(
    text: str,
    *,
    locked_text: str,
    standard_terms: Iterable[str],
) -> list[str]:
    """Return non-Han generated words absent from the locked source.

    Chinese Han text is the default generation language. Any Latin, Kana,
    Hangul, Cyrillic, Arabic, or other recognized-script word must either be a
    standard production term or appear verbatim in the locked source.  Unlike
    source-dialogue language checks, generated picture language has no generic
    short-token exemption.
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


# Internal enum/field names that must never leak into the Chinese execution text.
# These are validator concepts, not natural-language direction.
DISALLOWED_INTERNAL_ENUMS = {
    "wide_spatial",
    "natural_relation",
    "compressed_distance",
    "detail_isolation",
    "viewpoint_owner",
    "primary_subjects",
    "secondary_subjects",
    "spatial_strategy",
    "focus_plan",
    "movement_plan",
    "state",
    "position",
    "facing",
    "eyeline",
    "presence",
    "screen_left",
    "screen_right",
    "toward_camera",
    "away_camera",
    "dialogue_design",
    "non_cut_basis",
    "reframe_method",
    "plan_unit_id",
    "screen_event_id",
    "style_anchor_id",
    "axis_id",
    "fact_id",
    "beat_id",
    "scene_id",
    "shot_id",
}


def disallowed_internal_enums(
    text: str,
    *,
    locked_text: str = "",
    standard_terms: Iterable[str] | None = None,
) -> list[str]:
    """Return internal enum/field tokens that appear in user-facing text.

    Machine-facing concepts such as ``wide_spatial`` or ``viewpoint_owner``
    must be translated into Chinese in the rendered shot description.  Tokens
    that appear verbatim in ``locked_text`` or in ``standard_terms`` are
    allowed.
    """

    allowed_standard: set[str] = set()
    if standard_terms is not None:
        allowed_standard = {
            re.sub(r"[^A-Za-z0-9]+", "", item).upper() for item in standard_terms
        }
    disallowed: list[str] = []
    # Match snake_case / camelCase identifiers that correspond to internal
    # enum or field names.  Keep the original casing for reporting.
    for match in re.finditer(r"[A-Za-z][A-Za-z0-9_]*", text):
        token = match.group(0)
        normalized = token.lower()
        if normalized not in DISALLOWED_INTERNAL_ENUMS:
            continue
        if token in locked_text:
            continue
        standard_key = re.sub(r"[^A-Za-z0-9]+", "", token).upper()
        if standard_key in allowed_standard:
            continue
        if token not in disallowed:
            disallowed.append(token)
    return disallowed
