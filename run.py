"""PDF -> Audiobook.

    python run.py book.pdf                       # writes book.wav
    python run.py book.pdf -o talk.wav --rate 190
    python run.py book.pdf --text-only           # extract text, no speech
    python run.py book.pdf --max-chunk 300 --voice 3
    python run.py --voices                       # list installed voices
    python run.py book.pdf --preview 800         # show the first 800 chars
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src import audio, chunk, extract  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Convert a PDF into an audiobook (WAV).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("pdf", nargs="?", help="input PDF file")
    p.add_argument("-o", "--output", help="output WAV path (default: <pdf stem>.wav)")
    p.add_argument("--rate", type=int, default=175,
                   help="speech rate, words per minute (default 175)")
    p.add_argument("--volume", type=float, default=1.0, help="0.0 - 1.0 (default 1.0)")
    p.add_argument("--voice", help="voice index from --voices")
    p.add_argument("--max-chunk", type=int, default=600,
                   help="max characters per speech chunk (default 600)")
    p.add_argument("--page-marks", action="store_true",
                   help="insert [Page N] markers into the narration")
    p.add_argument("--text-only", action="store_true",
                   help="write extracted text only; skip speech synthesis")
    p.add_argument("--preview", type=int, default=0, metavar="CHARS",
                   help="print the first N characters of extracted text and exit")
    p.add_argument("--voices", action="store_true", help="list installed voices and exit")
    return p


def _print_progress(done: int, total: int) -> None:
    """Fires during concatenation, once per assembled chunk.

    Synthesis itself runs inside a single blocking pyttsx3 call, so there is
    nothing to observe there — printing a fake per-chunk bar would be a lie.
    """
    if total <= 0:
        return
    pct = done * 100 // total
    width = 30
    filled = width * done // total
    bar = "#" * filled + "-" * (width - filled)
    print(f"\r  [{bar}] {pct:3d}%  chunk {done}/{total}", end="", flush=True)
    if done == total:
        print()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.voices:
        try:
            voices = audio.list_voices()
        except audio.AudioError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if not voices:
            print("no voices installed")
            return 0
        for i, v in enumerate(voices):
            langs = ", ".join(v["languages"]) or "?"
            print(f"  [{i}] {v['name']}  ({langs})")
        print("\nuse --voice <index> to pick one")
        return 0

    if not args.pdf:
        build_parser().error("a PDF path is required (or use --voices)")

    pdf = Path(args.pdf)
    if not pdf.exists():
        print(f"error: file not found: {pdf}", file=sys.stderr)
        return 1
    if pdf.suffix.lower() != ".pdf":
        print(f"error: expected a .pdf, got {pdf.suffix or '(no extension)'}", file=sys.stderr)
        return 1

    print(f"Reading {pdf.name} ...")
    try:
        text = extract.extract(pdf, keep_page_marks=args.page_marks)
    except Exception as exc:  # noqa: BLE001 - report cleanly, pypdf raises many types
        print(f"error: could not read PDF: {exc}", file=sys.stderr)
        return 1

    if not text.strip():
        print("error: no extractable text. This PDF may be a scan/image-only file "
              "(needs OCR, which this tool does not do).", file=sys.stderr)
        return 1

    info = extract.stats(text)
    print(f"  {info['words']:,} words  |  {info['paragraphs']:,} paragraphs  |  "
          f"~{info['est_minutes_150wpm']} min at 150 wpm")

    if args.preview:
        print("\n--- preview ---")
        print(text[: args.preview])
        if len(text) > args.preview:
            print(f"\n... ({len(text) - args.preview:,} more chars)")
        return 0

    if args.text_only:
        out = Path(args.output) if args.output else pdf.with_suffix(".txt")
        out.write_text(text, encoding="utf-8")
        print(f"  wrote {out}")
        return 0

    chunks = chunk.chunk_text(text, max_chars=args.max_chunk)
    if not chunks:
        print("error: nothing to speak after chunking", file=sys.stderr)
        return 1
    print(f"  {len(chunks):,} speech chunks (max {args.max_chunk} chars)")

    output = Path(args.output) if args.output else pdf.with_suffix(".wav")

    voice_id = None
    if args.voice is not None:
        voices = audio.list_voices()
        try:
            voice_id = voices[int(args.voice)]["id"]
        except (ValueError, IndexError):
            print(f"error: --voice {args.voice!r} is not a valid index "
                  f"(0-{len(voices) - 1})", file=sys.stderr)
            return 1

    print(f"Synthesising -> {output}")
    try:
        summary = audio.synthesize(
            chunks, output,
            rate=args.rate, voice_id=voice_id, volume=args.volume,
            on_progress=_print_progress,
        )
    except (audio.AudioError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"  done: {summary['minutes']} min, {summary['chunks']} chunks, "
          f"{summary['bytes'] / 1_048_576:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
