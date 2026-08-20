"""Normalisation shared by deduplication and search.

Public because a consumer can share it. In the application this was extracted
from, the same folding backs an authorization boundary — two callers agreeing
on what counts as the same string — and a second copy of these three lines had
already lost two of them once. One implementation, importable, is the only
arrangement where that cannot happen again.
"""

from __future__ import annotations

import unicodedata


def fold_text(raw: str) -> str:
    """Fold Unicode width, whitespace, and case without dropping any content.

    Exactly three axes, chosen so the folded string still stands for the same
    statement: fullwidth and compatibility forms collapse to their canonical
    equivalents, runs of whitespace become single spaces, and case is removed.
    Punctuation, diacritics, and word order survive untouched.

    Every comparison in this package rests on it — two spellings of one
    sentence must fold to one string, or a restatement reads as a new fact and
    the store fills with duplicates.
    """
    return " ".join(unicodedata.normalize("NFKC", raw).split()).casefold()
