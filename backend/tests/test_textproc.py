import pytest

from app.textproc import chunk_document, chunk_page, clean_text, strip_repeated_edges


def test_clean_text_rejoins_hyphenated_words_and_collapses_space():
    assert clean_text("tank irriga-\ntion  is\n\nold") == "tank irrigation is old"


def test_clean_text_keeps_tamil_characters():
    tamil = "ஏரி பாசனம்"  # "eri irrigation"
    assert clean_text(tamil) == tamil


def test_chunk_page_overlaps_and_covers_all_words():
    words = [f"w{i}" for i in range(25)]
    chunks = chunk_page(" ".join(words), page_number=3, size=10, overlap=2)
    assert [c.text.split()[0] for c in chunks] == ["w0", "w8", "w16"]
    assert chunks[-1].text.split()[-1] == "w24"
    assert all(c.page_number == 3 for c in chunks)


def test_chunk_page_rejects_bad_overlap():
    with pytest.raises(ValueError):
        chunk_page("a b c", 1, size=5, overlap=5)


def test_chunk_document_never_crosses_pages_and_skips_empty_pages():
    chunks = chunk_document(["alpha beta", "", "gamma"], size=10, overlap=2)
    assert [(c.page_number, c.text) for c in chunks] == [(1, "alpha beta"), (3, "gamma")]


def test_clean_text_drops_control_characters():
    assert clean_text("et al.\x08 text") == "et al. text"


def test_strip_repeated_edges_removes_headers_but_keeps_body():
    bodies = ["sluice gates", "supply channels", "tank bunds", "surplus weirs", "tank beds", "field channels"]
    pages = [f"Journal Name\n{i:02d}\nAbout {b}\njournal.org" for i, b in enumerate(bodies, start=1)]
    cleaned = strip_repeated_edges(pages)
    assert cleaned[2] == "About tank bunds"


def test_chunk_document_tags_references_section():
    pages = ["Intro text", "More text\nReferences\nSmith (2001) Tanks.", "Jones (2005) Eri."]
    chunks = chunk_document(pages, size=10, overlap=2)
    assert [(c.page_number, c.section) for c in chunks] == [
        (1, "body"), (2, "body"), (2, "references"), (3, "references")
    ]
