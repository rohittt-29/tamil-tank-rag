"""Tests for query normalisation, spelling variants and page-once evaluation scoring.

The database test uses a synthetic fixture PDF (not a real source) and is skipped
when no database is running.
"""

import unicodedata

import psycopg
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app import ingest
from app.db import connect, init_schema
from app.evaluate import score
from app.main import app
from app.normalize import clean_query_text, normalize_query

KEY = "pytest-normalize-fixture"


# ---------- cleaning ----------

def test_whitespace_is_collapsed_and_trimmed():
    assert clean_query_text("  tank \t\n  desilting   ") == "tank desilting"


def test_case_is_kept_because_search_already_ignores_it():
    assert clean_query_text("Tank Desilting") == "Tank Desilting"


def test_tamil_text_is_nfc_normalised():
    decomposed = unicodedata.normalize("NFD", "ஏரி")  # "eri" written as separate code points
    assert clean_query_text(decomposed) == unicodedata.normalize("NFC", "ஏரி")


def test_curly_quotes_become_straight_so_phrase_search_works():
    assert clean_query_text("“tank cascade” farmers’") == "\"tank cascade\" farmers'"


def test_zero_width_space_removed_but_tamil_joiners_kept():
    assert clean_query_text("tank​bed﻿") == "tankbed"
    assert clean_query_text("க‍ஷ") == "க‍ஷ"  # ZWJ can matter in Tamil, so it stays


def test_original_text_is_kept_for_display():
    nq = normalize_query("  Tank  ")
    assert nq.original == "  Tank  " and nq.text == "Tank"


@pytest.mark.parametrize("raw", ["", "   ", "???", "...", "​"])
def test_queries_without_letters_or_digits_are_not_searchable(raw):
    assert not normalize_query(raw).searchable


# ---------- spelling variants ----------

@pytest.mark.parametrize("typed", ["kudimaramath", "Kudimaramathu", "kudimaramatu", "KUDIMARAMAT"])
def test_every_kudimaramath_spelling_expands_to_the_others(typed):
    nq = normalize_query(f"{typed} in tanks")
    assert len(nq.rewrites) == 1
    assert nq.rewrites[0][0] == typed.casefold()
    assert len(nq.variants_used) == 3
    assert typed.casefold() not in [v.casefold() for v in nq.variants_used]


def test_ayacutdar_plural_does_not_list_itself_as_extra():
    assert normalize_query("rights of ayacutdars").variants_used == ["ayacutdhar", "ayacutdara"]


def test_tamil_nadu_both_ways():
    assert normalize_query("tanks in Tamil Nadu").variants_used == ["Tamilnadu"]
    assert normalize_query("tanks in Tamilnadu").variants_used == ["Tamil Nadu"]


def test_unrelated_words_get_no_variants():
    nq = normalize_query("desilting of the supply channel")
    assert nq.rewrites == [] and nq.variants_used == []


@pytest.mark.parametrize("q", ["eri", "kanmai", "oorani", "neerkatti", "kombukatty"])
def test_terms_that_may_differ_in_meaning_are_not_merged(q):
    assert normalize_query(q).variants_used == []


def test_variant_must_be_a_whole_word():
    assert normalize_query("kudimaramathwork").rewrites == []


# ---------- evaluation scoring ----------

def test_repeated_page_counts_once_at_its_first_rank():
    relevant = {("d", 1), ("d", 2)}
    ranked = [("d", 1), ("d", 1), ("x", 9), ("d", 1), ("x", 8), ("d", 2)]
    s = score(ranked, relevant)
    # distinct pages in order: d1, x9, x8, d2 -> 2 relevant in the top 5
    assert s["p_at_5"] == pytest.approx(2 / 5)
    assert s["recall_at_10"] == 1.0
    assert s["rr"] == 1.0


def test_duplicate_before_first_relevant_does_not_push_it_down():
    s = score([("x", 1), ("x", 1), ("d", 1)], {("d", 1)})
    assert s["rr"] == pytest.approx(1 / 2)


# ---------- through the API (database) ----------

@pytest.fixture()
def conn(tmp_path, monkeypatch):
    try:
        c = connect()
    except psycopg.OperationalError:
        pytest.skip("database not available")
    init_schema(c)
    pdf = tmp_path / "fixture.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Synthetic page one: zqvillage Kudimaramathu work on the tank.")
    doc.new_page().insert_text((72, 72), "Synthetic page two: zqvillage ayacutdhars met in Tamilnadu.")
    doc.save(pdf)
    monkeypatch.setattr(ingest, "REPO_ROOT", tmp_path)
    entry = {"source_key": KEY, "file": "fixture.pdf", "title": "Normalize fixture", "authors": ["Nobody"]}
    assert ingest.ingest_entry(c, entry, force=True).startswith("ok")
    yield c
    c.execute("DELETE FROM documents WHERE source_key = %s", (KEY,))
    c.commit()
    c.close()


def pages(body):
    return sorted(h["page_number"] for h in body["hits"] if h["document"]["source_key"] == KEY)


@pytest.mark.parametrize("match", ["all", "any"])
def test_other_spelling_is_found_and_reported(conn, match):
    body = TestClient(app).get("/api/search", params={"q": "zqvillage kudimaramath", "match": match, "limit": 50}).json()
    assert 1 in pages(body)
    assert body["query"] == "zqvillage kudimaramath"
    assert "Kudimaramathu" in body["variants_used"]


def test_all_words_mode_still_requires_the_other_words(conn):
    body = TestClient(app).get("/api/search", params={"q": "zqvillage kudimaramath", "limit": 50}).json()
    assert pages(body) == [1]  # page 2 has zqvillage but no spelling of kudimaramath


def test_multi_word_variant_and_plural(conn):
    client = TestClient(app)
    assert pages(client.get("/api/search", params={"q": "zqvillage Tamil Nadu"}).json()) == [2]
    assert pages(client.get("/api/search", params={"q": "zqvillage ayacutdars"}).json()) == [2]


def test_messy_whitespace_and_quotes_give_same_results(conn):
    client = TestClient(app)
    clean = client.get("/api/search", params={"q": "zqvillage tank"}).json()
    messy = client.get("/api/search", params={"q": "  zqvillage​ \t “tank” "}).json()
    assert pages(clean) == pages(messy) == [1]
    assert messy["normalized_query"] == 'zqvillage "tank"'


def test_punctuation_only_query_is_rejected(conn):
    res = TestClient(app).get("/api/search", params={"q": "???"})
    assert res.status_code == 422 and "letters or numbers" in res.json()["detail"]
