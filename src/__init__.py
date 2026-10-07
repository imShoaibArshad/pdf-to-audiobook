"""PDF -> Audiobook package.

Deliberately does NOT re-export `extract` — doing so binds the name to the
function and shadows the `src.extract` submodule, breaking every
`extract.stats(...)` style call. Import submodules explicitly instead:

    from src import extract, chunk, audio
"""

from .chunk import chunk_text, split_sentences  # noqa: F401
