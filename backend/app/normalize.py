"""Query normalisation and evidence-backed spelling variants.

Two separate jobs, both deterministic (same input -> same output):

1. normalize_query(): tidy the text the user typed without changing its meaning
   (Unicode NFC, stray control/zero-width characters, curly quotes, extra spaces).
   Case is NOT changed here: PostgreSQL full-text search already ignores case, and
   the embedding model is given the text as typed.

2. find_variants(): spot a known term in the query and list its other spellings, so
   keyword search can look for all of them. Only groups whose spellings were checked
   in our own documents and mean the same thing are listed. Words that might differ
   in meaning (eri / kanmai / kanmoi / oorani; Neerkatti / Neerpaichi / Kombukatty)
   are deliberately NOT merged; semantic search handles those.
"""

import re
import unicodedata
from dataclasses import dataclass, field

# Curly quotes -> straight, so "exact phrase" search keeps working when text is pasted from Word/PDF.
QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
# Zero-width space and BOM carry no meaning. ZWJ/ZWNJ (U+200D/U+200C) are kept: Tamil text can use them.
INVISIBLE = {"​", "﻿"}


@dataclass(frozen=True)
class VariantGroup:
    name: str
    pattern: re.Pattern       # matches any spelling in the (lower-cased) query
    lexemes: str              # all spellings as a tsquery, already in stemmed form
    spellings: tuple[str, ...]
    evidence: str             # where we verified they mean the same thing


VARIANT_GROUPS = (
    VariantGroup(
        name="kudimaramath",
        pattern=re.compile(r"\bkudimaramat(?:hu|h|u)?\b"),
        lexemes="kudimaramath | kudimaramathu | kudimaramatu | kudimaramat",
        spellings=("Kudimaramath", "Kudimaramathu", "Kudimaramatu", "Kudimaramat"),
        evidence="Mailam 2025 p2 'Kudimaramatu ... voluntary contribution of labour', p18 'Kudimaramathu'; "
                 "DHAN 2004 p14-20 'Kudimaramath', p91 'Kudimaramathu'",
    ),
    VariantGroup(
        name="ayacutdar",
        pattern=re.compile(r"\bayacutdh?ara?s?\b"),
        lexemes="ayacutdar | ayacutdhar | ayacutdara",
        spellings=("ayacutdar", "ayacutdhar", "ayacutdara"),
        evidence="DHAN 2004 p32 uses 'ayacutdhars' and 'ayacutdaras' for the same tank-command farmers",
    ),
    VariantGroup(
        name="tamil nadu",
        pattern=re.compile(r"\btamil\s*nadu\b"),
        lexemes="( tamil & nadu ) | tamilnadu",
        spellings=("Tamil Nadu", "Tamilnadu"),
        evidence="'Tamilnadu' 33 times in DHAN 2004 and Suresh 2021; 'Tamil Nadu' elsewhere; same state",
    ),
)


@dataclass
class NormalizedQuery:
    original: str                       # exactly what the user typed (for display and debugging)
    text: str                           # cleaned text used for searching
    rewrites: list[tuple[str, str]] = field(default_factory=list)  # (word as typed, tsquery of all spellings)
    variants_used: list[str] = field(default_factory=list)          # spellings added beyond the typed one

    @property
    def searchable(self) -> bool:
        return any(ch.isalnum() for ch in self.text)


def clean_query_text(raw: str) -> str:
    text = unicodedata.normalize("NFC", raw).translate(QUOTES)
    text = "".join(
        " " if unicodedata.category(ch) == "Cc" else ch  # tabs, newlines, other control chars -> space
        for ch in text
        if ch not in INVISIBLE
    )
    return re.sub(r"\s+", " ", text).strip()


def find_variants(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    rewrites, added = [], []
    lowered = text.casefold()
    for group in VARIANT_GROUPS:
        typed = {m.group(0) for m in group.pattern.finditer(lowered)}
        for word in sorted(typed):
            rewrites.append((word, group.lexemes))
        if typed:
            def key(w: str) -> str:  # plural typed counts as that spelling: "ayacutdars" ~ "ayacutdar"
                return w.casefold().rstrip("s")

            typed_keys = {key(w) for w in typed}
            added += [s for s in group.spellings if key(s) not in typed_keys]
    return rewrites, added


def normalize_query(raw: str) -> NormalizedQuery:
    text = clean_query_text(raw)
    rewrites, added = find_variants(text)
    return NormalizedQuery(original=raw, text=text, rewrites=rewrites, variants_used=added)
