"""Offline demo: extract -> chunk -> synthesise a short WAV.

Runs entirely locally (SAPI5/`pyttsx3`), sends nothing anywhere. Kept short on
purpose so it finishes in a few seconds.
"""

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src import audio, chunk  # noqa: E402


SAMPLE = (
    "Chapter one. The sun rose over the quiet town, and the river carried "
    "the morning mist downstream. Nobody stirred until the bell rang twice. "
    "Then the market opened, and the smell of fresh bread drifted through "
    "the square. It was, by every measure, an ordinary morning."
)


def main() -> int:
    chunks = chunk.chunk_text(SAMPLE, max_chars=120)
    print(f"input: {len(SAMPLE)} chars -> {len(chunks)} chunks")
    for i, c in enumerate(chunks, 1):
        print(f"  [{i}] ({len(c):3d} chars) {c}")

    output = Path(__file__).resolve().parent / "demo_output.wav"
    print(f"\nsynthesising -> {output.name}")

    def progress(done: int, total: int) -> None:
        print(f"  chunk {done}/{total}")

    summary = audio.synthesize(chunks, output, rate=175, on_progress=progress)
    print(f"\ndone: {summary['seconds']}s of audio, "
          f"{summary['bytes']} bytes, {summary['rate']} wpm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
