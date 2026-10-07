"""Split text into speakable chunks.

Pure string logic, no I/O and no speech engine — so it can be tested
thoroughly.

Why chunks at all: speech engines degrade on very long input (SAPI5 will
silently truncate or stall), and chunking gives progress reporting and lets
already-spoken parts survive if the run is interrupted.
"""

from __future__ import annotations

import re

SENTENCE_END = re.compile(r"([.!?…]+[\"')\]]*)(\s+|$)")
MAX_SENTENCE = 1000


def split_sentences(text: str) -> list[str]:
    """Split on sentence-ending punctuation.

    Deliberately simple rather than a full NLP parse: abbreviations like
    "e.g." occasionally split early, which costs nothing in speech, whereas
    mis-handling quoted or parenthesised text costs a lot.
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    parts: list[str] = []
    last = 0
    for m in SENTENCE_END.finditer(text):
        candidate = text[last:m.end()].strip()
        if candidate:
            parts.append(candidate)
        last = m.end()
    tail = text[last:].strip()
    if tail:
        parts.append(tail)
    return parts


def _split_long(sentence: str, max_chars: int) -> list[str]:
    """Break one oversized sentence on word boundaries, keeping punctuation."""
    if len(sentence) <= max_chars:
        return [sentence]

    words = sentence.split()
    pieces: list[str] = []
    current: list[str] = []
    for word in words:
        # A single token longer than the limit gets hard-split, otherwise the
        # chunk could never shrink.
        while len(word) > max_chars:
            if current:
                pieces.append(" ".join(current))
                current = []
            pieces.append(word[:max_chars])
            word = word[max_chars:]

        candidate = " ".join(current + [word])
        if current and len(candidate) > max_chars:
            pieces.append(" ".join(current))
            current = [word]
        else:
            current.append(word)

    if current:
        pieces.append(" ".join(current))
    return [p for p in pieces if p]


def chunk_text(text: str, max_chars: int = 600, max_sentences: int = 8) -> list[str]:
    """Pack sentences into chunks no longer than `max_chars`.

    Guarantees (all pinned by tests):
      * every chunk is <= max_chars, except a single unbreakable token
      * no words added or lost
      * order preserved
      * no empty chunks
    """
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")

    sentences = split_sentences(text)
    if not sentences:
        return []

    chunks: list[str] = []
    buffer: list[str] = []
    size = 0

    def flush() -> None:
        nonlocal buffer, size
        if buffer:
            chunks.append(" ".join(buffer))
            buffer, size = [], 0

    for sentence in sentences:
        if len(sentence) > MAX_SENTENCE or len(sentence) > max_chars:
            # Oversized: flush what we hold, then emit it as standalone pieces
            # so it never inflates a neighbouring chunk.
            flush()
            for piece in _split_long(sentence, max_chars):
                if piece:
                    chunks.append(piece)
            continue

        added = len(sentence) + (1 if buffer else 0)
        if buffer and size + added > max_chars:
            flush()
            added = len(sentence)

        buffer.append(sentence)
        size += added

        if len(buffer) >= max_sentences:
            flush()

    flush()

    # Belt and braces: guarantee the contract even if a rule above regresses.
    final: list[str] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if len(chunk) > max_chars:
            final.extend(_split_long(chunk, max_chars))
        else:
            final.append(chunk)
    return final
