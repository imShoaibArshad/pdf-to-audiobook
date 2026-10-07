"""Tests for chunking — pure logic, no speech engine required."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.chunk import chunk_text, split_sentences  # noqa: E402


# --------------------------------------------------------- split_sentences ---


def test_splits_on_basic_punctuation():
    assert split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]


def test_keeps_abbreviations_intact_enough():
    # Not perfect by design — costs nothing in speech.
    out = split_sentences("See e.g. the results.")
    assert isinstance(out, list)
    assert "".join(out).replace(" ", "") == "Seee.g.theresults.".replace(" ", "")


def test_handles_trailing_text_without_terminal_punct():
    assert split_sentences("One. Two") == ["One.", "Two"]


def test_empty_and_whitespace():
    assert split_sentences("") == []
    assert split_sentences("   \n  ") == []


def test_normalises_internal_whitespace():
    assert split_sentences("One   two.\n\nThree.") == ["One two.", "Three."]


# -------------------------------------------------------------- chunk_text ---


LONG = ("Alpha beta gamma delta. " * 40).strip()


def test_all_chunks_within_limit():
    for chunk in chunk_text(LONG, max_chars=120):
        assert len(chunk) <= 120


def test_no_words_added_or_lost():
    source = LONG
    joined = " ".join(chunk_text(source, max_chars=100))
    assert joined.split() == source.split()


def test_order_preserved():
    source = "First sentence. Second sentence. Third sentence."
    out = chunk_text(source, max_chars=100)
    flat = " ".join(out)
    assert flat.index("First") < flat.index("Second") < flat.index("Third")


def test_no_empty_chunks():
    out = chunk_text("   Hello   \n\n  world.  ", max_chars=50)
    assert out
    assert all(c.strip() for c in out)


def test_short_text_is_one_chunk():
    assert len(chunk_text("Just one short sentence.", max_chars=600)) == 1


def test_empty_text_returns_empty_list():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_max_sentences_cap_splits_long_run_of_tiny_sentences():
    text = ". ".join(["Hi"] * 50) + "."
    out = chunk_text(text, max_chars=10_000, max_sentences=5)
    assert len(out) > 1


def test_single_unbreakable_token_hard_splits():
    blob = "x" * 500
    out = chunk_text(blob, max_chars=100)
    assert all(len(c) <= 100 for c in out)
    assert "".join(out) == blob


def test_long_sentence_split_on_word_boundaries():
    words = " ".join(f"word{i}" for i in range(200))
    out = chunk_text(words, max_chars=80)
    assert all(len(c) <= 80 for c in out)
    assert " ".join(out).split() == words.split()


def test_rejects_invalid_max_chars():
    with pytest.raises(ValueError):
        chunk_text("hello", max_chars=0)


def test_chunk_boundaries_do_not_break_hyphenated_compound():
    # Sentences end at punctuation, so a hyphen stays with its word — and if
    # both sentences fit, they stay in one chunk rather than being split.
    text = "A well-known result. Another one."
    assert chunk_text(text, max_chars=1000) == ["A well-known result. Another one."]
    # Forced apart by a tight limit, still never mid-word.
    split = chunk_text(text, max_chars=20)
    assert all(len(c) <= 20 for c in split)
    assert " ".join(split).split() == text.split()


def test_quotes_and_parens_at_sentence_end_kept_with_sentence():
    text = 'He said "stop." Then he left. (Done.)'
    out = split_sentences(text)
    assert out[0].startswith('He said "stop."')
    assert out[-1] == "(Done.)"


def test_scales_to_document_size():
    text = LONG * 50
    out = chunk_text(text, max_chars=500)
    assert out
    assert all(len(c) <= 500 for c in out)
    assert len(" ".join(out).split()) == len(text.split())
