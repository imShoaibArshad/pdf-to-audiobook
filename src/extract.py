"""Extract clean, readable text from a PDF.

Most PDFs are typeset for the eye, not the ear: they carry running headers,
page numbers, and words hyphenated across line breaks. Those all sound wrong
when read aloud, so this module removes them before anything reaches the
speech engine.
"""

from __future__ import annotations

import re
from pathlib import Path

# "Page 7" / "PAGE iii" — unambiguous, dropped anywhere.
PAGE_LABEL = re.compile(r"^\s*page\s+(?:[ivxlcdm]+|\d{1,4})\s*$", re.IGNORECASE)
# "7 of 42", "7 / 42", "(7 of 42)".
PAGE_COUNT = re.compile(r"^\s*\(?\d+\s*(?:of|/)\s*\d+\)?\s*$", re.IGNORECASE)
# A bare token that *could* be a page number: "7", "vii", "(3)".
# Ambiguous on its own, so only trusted at a page edge.
BARE_TOKEN = re.compile(r"^\s*\(?\s*(?:[ivxlcdm]+|\d{1,4})\s*\)?\s*$", re.IGNORECASE)
# Two or more spaces, or a space before punctuation — from PDF layout gutters.
RUNNING_SPACE = re.compile(r"[ \t]{2,}|\s+([,.;:!?])")
# A word split across a line break: "exam-\nple" -> "example".
HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
# Blank-line runs longer than one.
BLANKS = re.compile(r"\n{3,}")


def read_pages(path: str | Path) -> list[str]:
    """Return the raw extracted text of each page, in order.

    Imported lazily so `chunk` (which needs no PDF library) stays importable
    in environments without pypdf.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return [(page.extract_text() or "") for page in reader.pages]


def _first_last_lines(page_text: str) -> list[str]:
    lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
    if not lines:
        return []
    out = [lines[0]]
    if len(lines) > 1 and lines[-1] != lines[0]:
        out.append(lines[-1])
    return out


def drop_repeated_lines(pages: list[str], min_ratio: float = 0.4) -> list[str]:
    """Strip running headers/footers that repeat across many pages.

    A line appearing on >= `min_ratio` of the pages (and at least 3 pages)
    is treated as furniture rather than content. Single-page documents are
    left untouched — there's no repetition to detect and a real first line
    must not be deleted.
    """
    if len(pages) < 3:
        return pages

    counts: dict[str, int] = {}
    for page in pages:
        for line in set(_first_last_lines(page)):
            counts[line] = counts.get(line, 0) + 1

    threshold = max(3, int(len(pages) * min_ratio))
    # Page numbers are excluded: they differ per page anyway, and are stripped
    # later by is_boilerplate() at the edge.
    repeated = {line for line, n in counts.items()
                if n >= threshold and not is_boilerplate(line, at_page_edge=True)}

    cleaned = []
    for page in pages:
        kept = [ln for ln in page.splitlines() if ln.strip() and ln.strip() not in repeated]
        cleaned.append("\n".join(kept))
    return cleaned


def normalize(text: str) -> str:
    """Repair PDF layout damage: de-hyphenate, collapse gutters, trim blanks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Join hyphenated words before whitespace is touched.
    while (m := HYPHEN_BREAK.search(text)):
        text = text[: m.start()] + m.group(1) + m.group(2) + text[m.end():]
    text = RUNNING_SPACE.sub(lambda m: m.group(1) or " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = BLANKS.sub("\n\n", text)
    return text.strip()


def is_boilerplate(line: str, at_page_edge: bool = False) -> bool:
    """Should this line be dropped as page furniture?

    `at_page_edge` must be set when the line is the first or last non-empty
    line of a page. A bare "7" is a page number there, but in body text a
    standalone "1998" is a year in a table or reference list and must be
    kept — so bare tokens are only trusted at the edge.
    """
    line = line.strip()
    if not line:
        return True
    if PAGE_LABEL.match(line) or PAGE_COUNT.match(line):
        return True
    return bool(at_page_edge and BARE_TOKEN.match(line))


def extract(path: str | Path, keep_page_marks: bool = False) -> str:
    """PDF -> one readable text blob.

    With `keep_page_marks=True`, a "[Page N]" marker is inserted between
    pages so the listener can tell where they are — useful for papers.
    """
    pages = read_pages(path)
    pages = drop_repeated_lines(pages)

    blocks: list[str] = []
    for i, page in enumerate(pages, start=1):
        # A bare token is only a page number when it sits at the top/bottom of
        # the page — mark those positions before filtering.
        raw = page.splitlines()
        non_empty = [j for j, ln in enumerate(raw) if ln.strip()]
        edges = set()
        if non_empty:
            edges.add(non_empty[0])
            edges.add(non_empty[-1])

        lines = [
            ln for j, ln in enumerate(raw)
            if not is_boilerplate(ln, at_page_edge=(j in edges))
        ]
        body = normalize("\n".join(lines))
        if not body:
            continue
        if keep_page_marks:
            blocks.append(f"[Page {i}]\n{body}")
        else:
            blocks.append(body)

    return "\n\n".join(blocks).strip()


def stats(text: str) -> dict:
    """Word count and a spoken-duration estimate.

    150 wpm is a common conversational rate; the audio engine's own rate
    setting is applied separately.
    """
    words = text.split()
    return {
        "chars": len(text),
        "words": len(words),
        "paragraphs": sum(1 for p in text.split("\n\n") if p.strip()),
        "est_minutes_150wpm": round(len(words) / 150, 1),
    }
