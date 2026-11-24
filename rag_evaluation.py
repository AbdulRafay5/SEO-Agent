"""Offline source-level retrieval evaluation over labelled synthetic fixtures."""
import json
import math
from pathlib import Path
from statistics import mean
from evidence_retrieval import retrieve, retrieve_hybrid, validate_sources

FIXTURES = Path(__file__).resolve().parent / "benchmarks" / "rag_cases.json"


def metrics(ranked, relevant, k=3):
    if k < 1:
        raise ValueError("k must be positive")
    unique = list(dict.fromkeys(ranked))[:k]
    relevant = set(relevant)
    hits = [int(source in relevant) for source in unique]
    dcg = sum(hit / math.log2(i + 2) for i, hit in enumerate(hits))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant))))
    return {"precision_at_k": sum(hits) / k,
            "recall_at_k": sum(hits) / len(relevant) if relevant else None,
            "mrr_at_k": next((1 / (i + 1) for i, hit in enumerate(hits) if hit), 0.0) if relevant else None,
            "ndcg_at_k": dcg / ideal if ideal else None,
            "no_match_correct": not unique if not relevant else None}


def evaluate(k=3):
    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        sources = validate_sources([{"text": body} for body in case["texts"]])
        relevant = [f"S{i}" for i in case["relevant"]]
        modes = [("lexical", retrieve(case["topic"], sources))]
        if "mock_vectors" in case:
            passages, method = retrieve_hybrid(case["topic"], sources, lambda _: case["mock_vectors"])
            modes.append(("hybrid_mock", passages))
        for mode, passages in modes:
            ranking = list(dict.fromkeys(row["source_id"] for row in passages))[:k]
            rows.append({"case": case["name"], "mode": mode, "ranked": ranking,
                         "relevant": relevant, **metrics(ranking, relevant, k)})
    summaries = {}
    for mode in sorted({row["mode"] for row in rows}):
        group = [row for row in rows if row["mode"] == mode]
        summary = {}
        for key in ("precision_at_k", "recall_at_k", "mrr_at_k", "ndcg_at_k"):
            values = [row[key] for row in group if row[key] is not None and row["relevant"]]
            summary[key] = round(mean(values), 4) if values else None
        negatives = [row["no_match_correct"] for row in group if row["no_match_correct"] is not None]
        summary["no_match_accuracy"] = mean(negatives) if negatives else None
        summaries[mode] = summary
    return {"k": k, "fixture_count": len(cases), "summary": summaries, "cases": rows,
            "limitations": "Synthetic source-level labels; hybrid vectors are mocked, not real model measurements. Precision uses fixed k. No factual entailment or live generation evaluation."}


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
