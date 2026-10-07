# PDF → Audiobook

Turns any text-based PDF into a spoken `.wav`, using the OS's built-in voice
engine. No cloud, no API key, no account — everything runs locally.

```bash
pip install -r requirements.txt
python run.py book.pdf                     # -> book.wav
python run.py book.pdf --rate 190 -o out.wav
python run.py book.pdf --text-only         # extract text only
python run.py book.pdf --preview 800       # inspect extraction first
python run.py --voices                     # list installed voices
```

Verified end-to-end: a 1,053-word CV → **8.88 minutes of audio, 26 chunks,
22.4 MB WAV**.

## The part worth reading: pyttsx3 hangs, and why

The obvious implementation — speak chunk, `runAndWait()`, repeat — **hangs
forever on the second chunk** under Windows/SAPI5. So does creating a fresh
engine per chunk.

I verified this rather than guessed, with a watchdog probe
(`tts_probe.py`, 60s timeout):

| Pattern | Result |
| --- | --- |
| A — one engine, `runAndWait()` per chunk | ❌ hangs at chunk 2 |
| C — fresh engine per chunk | ❌ hangs at chunk 2 |
| **B — queue all `save_to_file`, then one `runAndWait()`** | ✅ completes |

pyttsx3's event loop simply cannot be restarted. `audio._speak_chunks()`
therefore queues every chunk first and calls `runAndWait()` exactly once, then
verifies each expected WAV actually exists and raises `AudioError` if any are
missing.

### A consequence I did not paper over

Because synthesis is a single blocking call, **the progress bar reports
concatenation, not synthesis** — see `synthesize()`'s docstring and the note in
`run.py`. Printing a per-chunk synthesis bar would have been a lie; there is
nothing observable between the call and its return.

## Extraction: PDFs are typeset for the eye, not the ear

`src/extract.py` repairs the things that sound wrong aloud:

- **De-hyphenates** line-broken words — `"exam-\nple"` → `"example"`
- **Drops running headers/footers** that repeat across ≥40% of pages
- **Drops page furniture** — `"Page 7"`, `"3 of 40"`, and bare numbers
- **Collapses layout gutters** — `"Title    Author"` → `"Title Author"`
- **Fixes spacing before punctuation** — `"value . Result"` → `"value. Result"`
- Optional `--page-marks` inserts `[Page N]` for long papers

### A bug the tests caught

My first `is_boilerplate()` matched any 1–4 digit line as a page number. That
would have **silently deleted `1998` from reference lists and table rows**.
Bare tokens are now only trusted at the top/bottom edge of a page; unambiguous
forms (`Page 12`, `3 of 40`) are dropped anywhere. Pinned by
`test_bare_token_only_boilerplate_at_page_edge`.

### An accepted limitation, documented not hidden

Blind de-hyphenation joins `"well-\nknown"` into `"wellknown"`. Typeset line
breaks only hyphenate at syllable boundaries, so joining is right there — but
a legitimate hyphen caught at a wrap point gets mangled. Fixing it needs a
dictionary. The behaviour is pinned in
`test_known_limitation_real_hyphens_get_joined` rather than quietly changed.

## Chunking

Speech engines degrade on very long input (SAPI5 truncates or stalls), so text
is packed into chunks under `--max-chunk` characters (default 600),
sentence-aware where possible. `chunk_text()` is pure string logic with no
dependencies, which is why it carries most of the test suite.

Guarantees, each pinned by a test: every chunk ≤ limit (except a single
unbreakable token, which hard-splits), **no words added or lost**, order
preserved, no empty chunks.

## Layout

```
pdf-to-audiobook/
├── run.py          # CLI
├── demo.py         # short end-to-end run, writes demo_output.wav
├── smoke.py        # voice + synthesis checks (needs a TTS engine)
├── src/
│   ├── extract.py  # PDF -> clean text
│   ├── chunk.py    # text -> speakable chunks (pure, no I/O)
│   └── audio.py    # queue-then-speak, WAV concatenation
└── tests/          # 38 tests, no TTS engine required
```

## Testing

```bash
python -m pytest tests -q   # 38 passed — runs without a TTS engine
python smoke.py              # needs an OS voice; 11 checks
python demo.py               # writes a short WAV you can listen to
```

Unit tests deliberately avoid the speech engine (CI machines often have none);
`extract` and `chunk` are pure functions so that's easy.

## Limitations

- **Image-only/scanned PDFs produce nothing** — there's no OCR, and the CLI
  says so explicitly instead of writing an empty file.
- **One voice, one pass** — no per-chapter files or voice selection by name
  beyond `--voice <index>`.
- **WAV only** — uncompressed, so 8.9 minutes ≈ 22 MB. MP3 needs an encoder
  (`ffmpeg`) which isn't a dependency here.
- **`pyttsx3` voices vary by OS** — tested on Windows/SAPI5; macOS (NSSS) and
  Linux (espeak) should work but were not exercised.
- Abbreviations like `e.g.` occasionally split early; costs nothing in speech.

## Tech

Python (stdlib `wave` for assembly) · pypdf · pyttsx3 · pytest
