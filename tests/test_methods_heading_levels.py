"""The three top-level methods sections must render as peers.

The English docx marks "Contributors" as Heading 1 but "Data" and "Methods" as
Heading 2, so the renderer emitted h2/h3/h3 and the first section displayed a
size larger than its own peers -- which read as a repeat of the dialog title
rather than as a section heading.

The correction is deliberately narrow: a LONE leading h2 in a document whose
other sections are h3. A document that genuinely uses several h2 sections is
using the level consistently and is left alone.
"""

import importlib

import pytest

ds = importlib.import_module("common.data_sources")

fix = ds._normalise_leading_heading_level


def test_demotes_a_lone_leading_h2_to_match_later_sections():
    html = "<h2>Contributors</h2>\n<p>a</p>\n<h3>Data</h3>\n<h3>Methods</h3>"
    assert fix(html) == "<h3>Contributors</h3>\n<p>a</p>\n<h3>Data</h3>\n<h3>Methods</h3>"


def test_leaves_documents_that_use_h2_consistently():
    html = "<h2>One</h2>\n<h3>Sub</h3>\n<h2>Two</h2>"
    assert fix(html) == html


def test_leaves_a_document_with_no_h3_sections():
    html = "<h2>Only section</h2>\n<p>a</p>\n<h4>Detail</h4>"
    assert fix(html) == html


def test_leaves_a_document_that_already_starts_at_h3():
    html = "<h3>Direction du projet</h3>\n<p>a</p>\n<h3>Sources</h3>"
    assert fix(html) == html


def test_ignores_an_h2_that_is_not_the_first_element():
    html = "<p>Intro.</p>\n<h2>Contributors</h2>\n<h3>Data</h3>"
    assert fix(html) == html


def test_preserves_inline_markup_in_the_demoted_heading():
    html = "<h2>Contributors <em>and friends</em></h2>\n<h3>Data</h3>"
    assert fix(html) == "<h3>Contributors <em>and friends</em></h3>\n<h3>Data</h3>"


def test_real_english_document_renders_peer_sections():
    if not ds.METHODS_DOCX.exists():
        pytest.skip(f"{ds.METHODS_DOCX.name} not in this checkout")
    pytest.importorskip("docx", reason="python-docx not installed")
    import re

    html = ds.load_methods_html()
    levels = {
        re.sub(r"<[^>]+>", "", text).strip(): tag.lower()
        for tag, text in re.findall(r"<(h[234])>(.*?)</\1>", html, re.S)
    }
    for section in ("Contributors", "Data sources", "Methods", "Funding"):
        assert section in levels, f"{section} section heading missing"
    assert len({levels[s] for s in ("Contributors", "Data sources", "Methods", "Funding")}) == 1, (
        f"top-level sections render at mixed levels: {levels}"
    )
