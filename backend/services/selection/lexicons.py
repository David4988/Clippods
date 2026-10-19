"""
Small per-language word lists for boundary_v1's opening checks (master plan §14.4).

PROPOSED — for owner review. Deliberately short: they only apply a mild penalty
to the FIRST word of a candidate clip, never decide a cut.

  FILLER_STARTS   connectives / fillers that make a clip start mid-flow
                  ("and so…", "but…", "um…")
  CONTEXT_STARTS  pronouns / demonstratives that point back to something the
                  viewer hasn't heard ("he said…", "that is why…")
"""
from __future__ import annotations

import re

FILLER_STARTS = {
    "en": {"and", "but", "so", "because", "um", "uh", "or", "also", "yeah", "like"},
    "hi": {"और", "लेकिन", "तो", "क्योंकि", "मतलब", "कि", "या", "भी"},
    "ta": {"அதனால", "ஆனா", "அப்புறம்", "அப்போ", "மற்றும்", "ஏன்னா"},
}

CONTEXT_STARTS = {
    "en": {"he", "she", "they", "it", "that", "this", "those", "these", "him", "her", "them"},
    "hi": {"वह", "वो", "यह", "ये", "उस", "उन", "इस", "इन"},
    "ta": {"அது", "இது", "அவர்", "அவன்", "அவள்", "அவங்க", "அந்த", "இந்த"},
}


def first_token(text: str) -> str:
    """Lower-cased first word without surrounding punctuation."""
    match = re.match(r"\s*([\wऀ-ॿ஀-௿']+)", text)
    return match.group(1).lower() if match else ""


def is_filler_start(text: str, language: str) -> bool:
    return first_token(text) in FILLER_STARTS.get(language, set())


def is_context_start(text: str, language: str) -> bool:
    return first_token(text) in CONTEXT_STARTS.get(language, set())
