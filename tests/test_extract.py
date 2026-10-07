"""Tests for text extraction — the pure-string parts need no PDF at all."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import extract  # noqa: E402


# ------------------------------------------------------------ normalize ------


def test_dehyphenates_word_split_across_lines():
    assert extract.normalize("exam-\nple") == "example"
    assert extract.normalize("inter-\nnational") == "international"


def test_known_limitation_real_hyphens_get_joined():
    """Documents an accepted trade-off.

    A *typeset* line break uses "-" only at syllable boundaries, so joining is
    always safe there. But if the source text legitimately contains
    "well-known" and the PDF wraps it after the hyphen, naive joining yields
    "wellknown". Fixing that would need a dictionary; de-hyphenating blind is
    the standard pragmatic choice, so the behaviour is pinned rather than
    hidden.
    """
    assert extract.normalize("well-\nknown") == "wellknown"


def test_dehyphenates_multiple_occurrences():
    assert extract.normalize("inter-\nna-\ntional") == "international"


def test_collapses_layout_gutters():
    assert extract.normalize("Title    Author") == "Title Author"


def test_strips_space_before_punctuation():
    assert extract.normalize("value .  Result ,") == "value. Result,"


def test_normalises_line_endings():
    assert extract.normalize("a\r\nb\rc") == "a\nb\nc"


def test_collapses_excess_blank_lines():
    out = extract.normalize("para one\n\n\n\n\npara two")
    assert "\n\n\n" not in out


def test_collapses_indentation_around_newlines():
    # A whitespace-only line between content is a paragraph break.
    assert extract.normalize("line one\n   \nline two") == "line one\n\nline two"
    # Trailing indentation around a hard line break is just layout noise.
    assert extract.normalize("line one   \nline two") == "line one\nline two"


def test_empty_text():
    assert extract.normalize("") == ""
    assert extract.normalize("   \n  ") == ""


# ---------------------------------------------------- boilerplate filters ----


def test_page_numbers_detected():
    # Unambiguous forms are dropped anywhere on the page.
    assert extract.is_boilerplate("Page 12")
    assert extract.is_boilerplate("page iii")
    assert extract.is_boilerplate("3 of 40")
    assert extract.is_boilerplate("")


def test_bare_token_only_boilerplate_at_page_edge():
    """A standalone number is a page number at the edge, content in the body."""
    assert extract.is_boilerplate("7", at_page_edge=True)
    assert extract.is_boilerplate("vii", at_page_edge=True)
    assert extract.is_boilerplate("(3)", at_page_edge=True)

    # In body text these are real content — a year in a table or reference
    # list must never be silently deleted.
    assert not extract.is_boilerplate("7")
    assert not extract.is_boilerplate("1998")
    assert not extract.is_boilerplate("(3)")


def test_real_content_not_detected_as_boilerplate():
    assert not extract.is_boilerplate("Introduction")
    assert not extract.is_boilerplate("Results and discussion")
    assert not extract.is_boilerplate("1998")
    assert not extract.is_boilerplate("Chapter 3")
    # Even at the edge, real words are kept.
    assert not extract.is_boilerplate("Introduction", at_page_edge=True)


# ------------------------------------------------ drop_repeated_lines --------


def test_drops_repeated_running_header():
    pages = ["Journal of Things 2024\nreal content line\nmore content",
             "Journal of Things 2024\nsecond page body",
             "Journal of Things 2024\nthird page body",
             "Journal of Things 2024\nfourth page body"]
    out = extract.drop_repeated_lines(pages, min_ratio=0.4)
    assert all("Journal of Things 2024" not in p for p in out)
    assert "second page body" in out[1]


def test_keeps_unique_first_lines():
    pages = ["Chapter One\nbody", "Chapter Two\nbody", "Chapter Three\nbody"]
    out = extract.drop_repeated_lines(pages, min_ratio=0.4)
    assert all(f"Chapter {n}" in out[i]
               for i, n in enumerate(["One", "Two", "Three"]))


def test_leaves_single_page_untouched():
    pages = ["Only Title\nonly body"]
    assert extract.drop_repeated_lines(pages) == pages


def test_page_numbers_removed_even_when_not_repeated():
    pages = ["body one\n7", "body two\n8", "body three\n9", "body four\n10"]
    out = extract.drop_repeated_lines(pages, min_ratio=0.4)
    # Page numbers are stripped by is_boilerplate later; the repeated-line
    # pass must not delete the body lines.
    assert "body one" in out[0]
    assert "body four" in out[3]


def test_empty_pages_harmless():
    assert extract.drop_repeated_lines([]) == []


# ---------------------------------------------------------------- stats ------


def test_stats_counts_words_and_paragraphs():
    s = extract.stats("one two three\n\nfour five")
    assert s["words"] == 5
    assert s["paragraphs"] == 2
    assert s["chars"] == len("one two three\n\nfour five")


def test_stats_estimate_is_proportional():
    words = " ".join(["word"] * 300)
    assert extract.stats(words)["est_minutes_150wpm"] == 2.0


def test_stats_empty_text():
    s = extract.stats("")
    assert s["words"] == 0 and s["est_minutes_150wpm"] == 0.0
