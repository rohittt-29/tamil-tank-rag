"""Evaluate retrieval quality on the hand-labelled query set in eval/queries.json.

Usage (from backend/):
    python -m app.evaluate                 # print a summary table
    python -m app.evaluate --save          # also write eval/results/<method>-<date>.json
    python -m app.evaluate --method all --save   # every method, plus a comparison table

Metrics (computed per query, then averaged over queries):
    Precision@5  share of the top 5 results that are relevant
    Recall@10    share of the relevant pages that appear somewhere in the top 10
    MRR          1 / rank of the first relevant result (0 if none in the top 10)
A result is relevant when its (document, page) is listed for the query.
"""

import argparse
import hashlib
import json
import statistics
import sys
import time
from datetime import date

from .config import REPO_ROOT
from .embeddings import model_source
from .main import search

QUERIES = REPO_ROOT / "eval" / "queries.json"
RESULTS_DIR = REPO_ROOT / "eval" / "results"
K_PRECISION, K_RECALL = 5, 10


def load_queries() -> list[dict]:
    data = json.loads(QUERIES.read_text(encoding="utf-8"))
    alias = data["documents"]  # "M" -> "frontiers-2025-..."
    for q in data["queries"]:
        q["relevant_pages"] = {(alias[r[0]], int(r[1:])) for r in q["relevant"]}
    return data["queries"]


def score(ranked: list[tuple[str, int]], relevant: set[tuple[str, int]]) -> dict:
    is_rel = [r in relevant for r in ranked]
    first = next((i + 1 for i, hit in enumerate(is_rel[:K_RECALL]) if hit), None)
    return {
        "p_at_5": sum(is_rel[:K_PRECISION]) / K_PRECISION,
        "recall_at_10": len(set(ranked[:K_RECALL]) & relevant) / len(relevant),
        "rr": 1 / first if first else 0.0,
    }


METHODS = {
    "keyword-all": {"mode": "keyword", "match": "all"},  # every query word must appear (UI default)
    "keyword-any": {"mode": "keyword", "match": "any"},  # any query word may appear; ranking does the rest
    "semantic": {"mode": "semantic"},                    # multilingual-e5-small embeddings, cosine similarity
    "hybrid": {"mode": "hybrid"},                        # reciprocal rank fusion of keyword-any + semantic
}


def queries_fingerprint() -> str:
    """sha256 of eval/queries.json: proves every method was scored on the same questions and labels."""
    return hashlib.sha256(QUERIES.read_bytes()).hexdigest()


def run(method: str) -> dict:
    per_query = []
    for q in load_queries():
        start = time.perf_counter()
        response = search(q=q["query"], limit=K_RECALL, include_references=False, **METHODS[method])
        latency_ms = (time.perf_counter() - start) * 1000
        ranked = [(h["document"]["source_key"], h["page_number"]) for h in response["hits"]]
        per_query.append({
            "id": q["id"], "type": q["type"], "query": q["query"],
            "results": [f"{k}:p{p}" for k, p in ranked],
            "latency_ms": round(latency_ms, 1),
            **score(ranked, q["relevant_pages"]),
        })

    def mean(rows: list[dict], key: str) -> float:
        return round(statistics.mean(r[key] for r in rows), 3) if rows else 0.0

    summary = {}
    for group in ("all", "term", "paraphrase"):
        rows = per_query if group == "all" else [r for r in per_query if r["type"] == group]
        summary[group] = {
            "queries": len(rows),
            "P@5": mean(rows, "p_at_5"),
            "Recall@10": mean(rows, "recall_at_10"),
            "MRR": mean(rows, "rr"),
            "zero_relevant_in_top10": sum(1 for r in rows if r["rr"] == 0),
        }
    summary["all"]["median_latency_ms"] = round(statistics.median(r["latency_ms"] for r in per_query), 1)
    return {
        "method": method,
        "date": date.today().isoformat(),
        "queries_sha256": queries_fingerprint(),
        "query_ids": [r["id"] for r in per_query],
        "embedding_model": model_source() if METHODS[method]["mode"] != "keyword" else None,
        "summary": summary,
        "per_query": per_query,
    }


def print_per_query(result: dict) -> None:
    print(f"{'id':4} {'type':10} {'P@5':>5} {'R@10':>5} {'RR':>5}  query")
    for r in result["per_query"]:
        print(f"{r['id']:4} {r['type']:10} {r['p_at_5']:5.2f} {r['recall_at_10']:5.2f} {r['rr']:5.2f}  {r['query']}")


def print_comparison(results: list[dict]) -> None:
    fingerprints = {(r["queries_sha256"], tuple(r["query_ids"])) for r in results}
    assert len(fingerprints) == 1, "methods were scored on different query sets"
    print(f"Same {len(results[0]['query_ids'])} questions and labels for every method "
          f"(queries.json sha256 {results[0]['queries_sha256'][:12]}...)\n")
    print(f"{'method':12} {'group':11} {'P@5':>6} {'R@10':>6} {'MRR':>6} {'zero':>5} {'median ms':>10}")
    for res in results:
        for group, s in res["summary"].items():
            ms = s.get("median_latency_ms", "")
            print(f"{res['method']:12} {group:11} {s['P@5']:6.3f} {s['Recall@10']:6.3f} {s['MRR']:6.3f} "
                  f"{s['zero_relevant_in_top10']:5d} {ms:>10}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--save", action="store_true", help="write results JSON to eval/results/")
    parser.add_argument("--method", choices=[*METHODS, "all"], default="keyword-all")
    args = parser.parse_args()

    methods = list(METHODS) if args.method == "all" else [args.method]
    results = [run(m) for m in methods]
    if len(results) == 1:
        print_per_query(results[0])
        print()
        for group, s in results[0]["summary"].items():
            print(f"{group:10} {s}")
    else:
        print_comparison(results)

    if args.save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        for result in results:
            out = RESULTS_DIR / f"{result['method']}-{result['date']}.json"
            out.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(f"saved {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
