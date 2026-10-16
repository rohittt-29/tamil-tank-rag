"""Pure text-processing helpers: extraction, cleaning and chunking.

Kept free of database code so they are easy to unit-test.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass
class Chunk:
    page_number: int  # 1-based
    text: str
    section: str = "body"  # "body" or "references"


# A page header/footer is a short line that repeats on many pages
# ("Frontiers in Water", "frontiersin.org", page numbers, running title).
EDGE_LINES = 5            # only look at the first/last N lines of a page
REPEAT_FRACTION = 0.5     # ...and lines that appear on at least half the pages
MIN_PAGES_FOR_REPEATS = 4

REFERENCES_HEADING = re.compile(r"(?i)\s*(references|bibliography|literature cited)\s*")


def extract_pages(pdf_path: Path) -> list[str]:
    """Return the raw text of each page (index 0 = page 1)."""
    with pymupdf.open(pdf_path) as doc:
        return [page.get_text("text") for page in doc]


def _line_key(line: str) -> str:
    """Compare lines ignoring digits, so "Page 3" and "Page 4" count as the same line."""
    return re.sub(r"\d+", "#", line.strip())


def strip_repeated_edges(pages: list[str]) -> list[str]:
    """Remove header/footer lines that repeat at the top or bottom of most pages."""
    if len(pages) < MIN_PAGES_FOR_REPEATS:
        return pages
    split = [[l for l in p.splitlines() if l.strip()] for p in pages]
    seen = Counter()
    for lines in split:
        edges = lines[:EDGE_LINES] + lines[-EDGE_LINES:]
        seen.update({_line_key(l) for l in edges})
    boilerplate = {k for k, n in seen.items() if n >= REPEAT_FRACTION * len(pages)}
    cleaned = []
    for lines in split:
        last = len(lines) - EDGE_LINES
        kept = [
            l for i, l in enumerate(lines)
            if not ((i < EDGE_LINES or i >= last) and _line_key(l) in boilerplate)
        ]
        cleaned.append("\n".join(kept))
    return cleaned


def clean_text(raw: str) -> str:
    """Normalise extracted PDF text without changing its meaning.

    - NFC normalisation (safe for Tamil; NFKC would alter some characters)
    - re-join words hyphenated across line breaks: "irriga-\\ntion" -> "irrigation"
    - collapse runs of whitespace/newlines into single spaces
    """
    text = unicodedata.normalize("NFC", raw)
    text = text.replace("\u00ad", "")  # soft hyphen
    # drop control characters (PDFs sometimes contain e.g. \x08) but keep newlines and tabs
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch) != "Cc")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_page(text: str, page_number: int, size: int, overlap: int, section: str = "body") -> list[Chunk]:
    """Split one page into overlapping word windows.

    Chunks never cross a page boundary, so every chunk cites exactly one page.
    """
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    words = text.split()
    if not words:
        return []
    chunks: list[Chunk] = []
    step = size - overlap
    for start in range(0, len(words), step):
        window = words[start : start + size]
        chunks.append(Chunk(page_number, " ".join(window), section))
        if start + size >= len(words):
            break
    return chunks


def split_references(page: str) -> tuple[str, str | None]:
    """Split a page at a "References" heading line: (text before, text after or None)."""
    lines = page.splitlines()
    for i, line in enumerate(lines):
        if REFERENCES_HEADING.fullmatch(line):
            return "\n".join(lines[:i]), "\n".join(lines[i + 1 :])
    return page, None


def chunk_document(pages: list[str], size: int, overlap: int) -> list[Chunk]:
    """Clean and chunk all pages. Everything after a "References" heading is
    tagged section="references" so search can leave the bibliography out."""
    chunks: list[Chunk] = []
    in_refs = False
    for i, raw in enumerate(strip_repeated_edges(pages), start=1):
        if in_refs:
            chunks.extend(chunk_page(clean_text(raw), i, size, overlap, "references"))
            continue
        body, refs = split_references(raw)
        chunks.extend(chunk_page(clean_text(body), i, size, overlap))
        if refs is not None:
            in_refs = True
            chunks.extend(chunk_page(clean_text(refs), i, size, overlap, "references"))
    return chunks
