"""Speech synthesis and WAV assembly.

Each chunk is rendered to its own temporary WAV, then the pieces are
concatenated with the stdlib `wave` module.

All `save_to_file` calls are queued *before* a single `runAndWait()` — see
`_speak_chunks` for why, but the short version is that pyttsx3's event loop
cannot be restarted, and a second `runAndWait()` on the same engine hangs
forever on Windows/SAPI5.

Consequences worth knowing:
  * progress can be reported honestly, but only during concatenation —
    synthesis is one blocking call with nothing observable in between
  * the speech engine never sees a huge single string (SAPI5 stalls on those)
"""

from __future__ import annotations

import shutil
import tempfile
import wave
from pathlib import Path
from typing import Callable


class AudioError(RuntimeError):
    """Raised when the TTS engine cannot produce audio."""


ProgressFn = Callable[[int, int], None]


def list_voices() -> list[dict]:
    """Enumerate installed voices. Requires an engine, so imported lazily."""
    try:
        import pyttsx3
    except ImportError as exc:
        raise AudioError("pyttsx3 is not installed (pip install pyttsx3)") from exc

    engine = pyttsx3.init()
    try:
        return [
            {
                "id": v.id,
                "name": v.name,
                "languages": [b.decode("utf-8", "replace") if isinstance(b, bytes) else b
                              for b in (v.languages or [])],
            }
            for v in engine.getProperty("voices")
        ]
    finally:
        _stop(engine)


def _stop(engine) -> None:
    try:
        engine.stop()
    except Exception:  # noqa: BLE001 - best effort cleanup
        pass


def _speak_chunks(engine, chunks: list[str], work: Path) -> list[Path]:
    """Render every chunk to its own WAV.

    All `save_to_file` calls are queued *first*, then `runAndWait()` is called
    exactly once. pyttsx3's event loop cannot be restarted: calling
    `runAndWait()` a second time on the same engine (or stopping one engine
    and starting another) blocks forever on Windows/SAPI5 — verified with a
    watchdog probe, where per-chunk and fresh-engine-per-chunk both hung on
    chunk 2. Queue-then-run is the only pattern that completes.
    """
    parts: list[Path] = []
    for i, text in enumerate(chunks, start=1):
        if not text.strip():
            continue
        target = work / f"chunk_{i:05d}.wav"
        engine.save_to_file(text, str(target))
        parts.append(target)

    if not parts:
        raise AudioError("no non-empty chunks to speak")

    engine.runAndWait()

    missing = [p.name for p in parts if not p.exists() or p.stat().st_size == 0]
    if missing:
        raise AudioError(
            f"speech engine produced no audio for {len(missing)} chunk(s): "
            f"{', '.join(missing[:5])}"
        )
    return parts


def _concatenate(parts: list[Path], output: Path,
                  on_progress: ProgressFn | None = None) -> None:
    """Join WAV files that share sample rate/width/channels."""
    if not parts:
        raise AudioError("no audio chunks to concatenate")

    output.parent.mkdir(parents=True, exist_ok=True)
    total = len(parts)

    with wave.open(str(parts[0]), "rb") as first:
        params = first.getparams()
        frames = [first.readframes(first.getnframes())]
    # Report the first part too, then number the rest 2..total, so the
    # callback sequence ends exactly on (total, total) and the bar completes.
    if on_progress:
        on_progress(1, total)

    for index, path in enumerate(parts[1:], start=2):
        with wave.open(str(path), "rb") as w:
            if (w.getframerate(), w.getsampwidth(), w.getnchannels()) != (
                params.framerate, params.sampwidth, params.nchannels
            ):
                raise AudioError(
                    f"chunk {path.name} has incompatible format "
                    f"({w.getframerate()}Hz/{w.getsampwidth()}B/{w.getnchannels()}ch "
                    f"vs {params.framerate}Hz/{params.sampwidth}B/{params.nchannels}ch)"
                )
            frames.append(w.readframes(w.getnframes()))
        if on_progress:
            on_progress(index, total)

    with wave.open(str(output), "wb") as out:
        out.setparams(params)
        for block in frames:
            out.writeframes(block)


def synthesize(
    chunks: list[str],
    output: Path,
    rate: int = 175,
    voice_id: str | None = None,
    volume: float = 1.0,
    on_progress: ProgressFn | None = None,
) -> dict:
    """Render `chunks` into a single WAV at `output`. Returns a summary dict.

    `on_progress(done, total)` fires during concatenation, once per assembled
    chunk — not during synthesis. pyttsx3 renders everything inside a single
    blocking `runAndWait()`, so there is no way to observe it chunk by chunk
    without spawning a thread that would only be guessing.
    """
    try:
        import pyttsx3
    except ImportError as exc:
        raise AudioError("pyttsx3 is not installed (pip install pyttsx3)") from exc

    if not chunks:
        raise AudioError("nothing to speak — no chunks were produced")
    if not 50 <= rate <= 500:
        raise ValueError("rate must be between 50 and 500 words per minute")
    if not 0.0 <= volume <= 1.0:
        raise ValueError("volume must be between 0.0 and 1.0")

    work = Path(tempfile.mkdtemp(prefix="pdf2audio_"))
    parts: list[Path] = []

    try:
        engine = pyttsx3.init()
        try:
            engine.setProperty("rate", rate)
            engine.setProperty("volume", volume)
            if voice_id:
                engine.setProperty("voice", voice_id)

            parts = _speak_chunks(engine, chunks, work)
        finally:
            _stop(engine)

        _concatenate(parts, output, on_progress)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    with wave.open(str(output), "rb") as w:
        duration = w.getnframes() / float(w.getframerate())

    return {
        "output": str(output),
        "chunks": len(parts),
        "seconds": round(duration, 2),
        "minutes": round(duration / 60, 2),
        "rate": rate,
        "bytes": output.stat().st_size,
    }
