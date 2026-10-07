"""Smoke test for audio synthesis.

Separate from the unit tests because it needs a working TTS engine (SAPI5 on
Windows), which CI runners often lack. Run explicitly:  python smoke.py
"""

import sys
import tempfile
import wave
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src import audio, chunk  # noqa: E402

ok = True


def check(label: str, condition: bool, detail: str = "") -> None:
    global ok
    ok = ok and condition
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}"
          f"{(' -> ' + detail) if detail else ''}")


def main() -> int:
    print("Voices")
    try:
        voices = audio.list_voices()
    except audio.AudioError as exc:
        print(f"  [FAIL] list_voices: {exc}")
        return 1
    check("at least one voice", len(voices) > 0, f"{len(voices)} found")
    if voices:
        print(f"       default: {voices[0]['name']}")

    print("Chunking")
    text = "Hello world. This is a smoke test. It has three sentences."
    chunks = chunk.chunk_text(text, max_chars=40)
    # 1st+2nd sentences are 35 chars and fit together; the 3rd overflows,
    # so the correct answer is 2 chunks (not one per sentence).
    check("splits on the limit", len(chunks) == 2, f"{len(chunks)}")
    check("no chunk exceeds the limit", all(len(c) <= 40 for c in chunks))
    check("no words lost", " ".join(chunks).split() == text.split())

    print("Synthesis")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.wav"
        seen: list[tuple[int, int]] = []
        try:
            summary = audio.synthesize(
                chunks, out, rate=175,
                on_progress=lambda d, t: seen.append((d, t)),
            )
        except (audio.AudioError, ValueError) as exc:
            check("synthesize", False, str(exc))
            return 1

        check("output file written", out.exists() and out.stat().st_size > 0,
              f"{summary['bytes']} bytes")
        check("reports chunk count", summary["chunks"] == len(chunks))
        check("progress callback fired per chunk", len(seen) == len(chunks),
              f"{len(seen)}/{len(chunks)}")

        with wave.open(str(out)) as w:
            dur = w.getnframes() / w.getframerate()
        check("audio is non-trivial", dur > 0.3, f"{dur:.2f}s")
        check("sensible sample rate", w.getframerate() >= 8000,
              f"{w.getframerate()}Hz")

    print("Validation")
    try:
        audio.synthesize([], Path(tempfile.gettempdir()) / "x.wav")
        check("rejects empty chunk list", False)
    except audio.AudioError:
        check("rejects empty chunk list", True)

    try:
        audio.synthesize(["hi"], Path(tempfile.gettempdir()) / "x.wav", rate=10)
        check("rejects invalid rate", False)
    except ValueError:
        check("rejects invalid rate", True)

    print("\n" + ("ALL SMOKE CHECKS PASSED" if ok else "SMOKE CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
