from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.data.loaders import load_demo_data
from backend.app.p1.rule_pipeline import run_pipeline_for_inquiry


TOP_LEVEL_FIELDS = ["request_type", "customer_country", "application"]
LINE_ITEM_FIELDS = [
    "product_name",
    "quantity",
    "size",
    "material_grade",
    "pressure_rating",
    "connection_type",
    "certification",
    "requested_delivery_days",
]


def evaluate_all(root_dir: Path | None = None, dataset: str = "default") -> dict[str, Any]:
    # The "default" dataset is a regression harness, not proof of real-world
    # accuracy: its gold labels share the generator's logic, so 100% only means
    # the pipeline reproduces its own synthetic data. The "holdout" dataset is
    # hand-written with human gold to measure generalization, and is expected to
    # score lower; that delta is the signal this harness exists to produce.
    data = load_demo_data(root_dir, dataset=dataset)
    gold_by_id = {gold["inquiry_id"]: gold for gold in data.gold_answers}
    results = []

    for inquiry in data.inquiries:
        inquiry_id = inquiry["inquiry_id"]
        prediction = run_pipeline_for_inquiry(inquiry, data)
        gold = gold_by_id[inquiry_id]
        results.append(evaluate_one(prediction, gold))

    return {
        "dataset": dataset,
        "summary": summarize_results(results),
        "results": results,
    }


def evaluate_one(prediction: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    field_check = compare_fields(
        prediction["extracted_fields"],
        gold["gold_field_extraction"],
    )
    product_check = compare_product_candidates(
        prediction["product_matches"]["primary_candidates"],
        gold["gold_product_match"]["primary_candidates"],
    )
    risk_check = compare_rule_ids(
        prediction["risk_flags"],
        gold["gold_risk_flags"],
        key="rule_id",
    )
    missing_field_check = compare_missing_fields(
        prediction["extracted_fields"],
        gold["gold_field_extraction"],
    )

    # Pass policy: field extraction must be exact; risk flags and missing fields
    # must match exactly (no misses AND no false positives), because over-firing
    # there means crying wolf or hallucinated clarifications. Product candidates
    # are recall-gated only, since the retrieval step is allowed to over-return
    # for human review.
    passed = (
        field_check["accuracy"] == 1
        and product_check["all_gold_present"]
        and risk_check["all_gold_present"]
        and risk_check["no_false_positives"]
        and missing_field_check["all_gold_present"]
        and missing_field_check["no_false_positives"]
    )

    return {
        "inquiry_id": prediction["inquiry_id"],
        "passed": passed,
        "field_check": field_check,
        "product_candidate_check": product_check,
        "risk_flag_check": risk_check,
        "missing_field_check": missing_field_check,
    }


def compare_fields(predicted: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    comparisons = []

    for field in TOP_LEVEL_FIELDS:
        comparisons.append(compare_value(field, predicted.get(field), gold.get(field)))

    predicted_item = first_line_item(predicted)
    gold_item = first_line_item(gold)
    for field in LINE_ITEM_FIELDS:
        comparisons.append(compare_value(field, predicted_item.get(field), gold_item.get(field)))

    correct = sum(1 for item in comparisons if item["match"])
    total = len(comparisons)

    return {
        "correct": correct,
        "total": total,
        "accuracy": safe_ratio(correct, total),
        "failures": [item for item in comparisons if not item["match"]],
    }


def compare_value(field: str, predicted: Any, gold: Any) -> dict[str, Any]:
    return {
        "field": field,
        "predicted": predicted,
        "gold": gold,
        "match": normalize_value(predicted) == normalize_value(gold),
    }


def normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower()
    return value


def first_line_item(fields: dict[str, Any]) -> dict[str, Any]:
    line_items = fields.get("line_items") or []
    return line_items[0] if line_items else {}


def compare_product_candidates(
    predicted_candidates: list[dict[str, Any]],
    gold_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    # Candidate retrieval is recall-oriented by design ("which products might
    # fit"), so precision/false positives are reported for visibility but do not
    # gate pass/fail. See evaluate_one for the pass policy.
    return compare_id_sets(
        [candidate["product_id"] for candidate in predicted_candidates],
        [candidate["product_id"] for candidate in gold_candidates],
    )


def compare_rule_ids(
    predicted_rows: list[dict[str, Any]],
    gold_rows: list[dict[str, Any]],
    key: str,
) -> dict[str, Any]:
    return compare_id_sets(
        [row[key] for row in predicted_rows],
        [row[key] for row in gold_rows],
    )


def compare_missing_fields(predicted: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    return compare_id_sets(
        first_line_item(predicted).get("missing_fields", []),
        first_line_item(gold).get("missing_fields", []),
    )


def compare_id_sets(predicted_ids: list[str], gold_ids: list[str]) -> dict[str, Any]:
    # Shared set comparison for risk flags, product candidates, and missing
    # fields. Unlike the earlier recall-only check, this also exposes precision,
    # F1, and the actual false positives/negatives, so a regression that
    # over-fires (cries wolf) becomes visible instead of silently passing.
    predicted_set = set(predicted_ids)
    gold_set = set(gold_ids)
    true_positives = predicted_set & gold_set
    false_positives = predicted_set - gold_set
    false_negatives = gold_set - predicted_set

    precision = safe_ratio(len(true_positives), len(predicted_set))
    recall = safe_ratio(len(true_positives), len(gold_set))

    return {
        "predicted": list(predicted_ids),
        "gold": list(gold_ids),
        "hit_count": len(true_positives),
        "gold_count": len(gold_set),
        "predicted_count": len(predicted_set),
        "false_positives": sorted(false_positives),
        "false_negatives": sorted(false_negatives),
        "any_hit": len(true_positives) > 0,
        "all_gold_present": not false_negatives,
        "no_false_positives": not false_positives,
        "precision": precision,
        "recall": recall,
        "f1": f1_score(precision, recall),
    }


def f1_score(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    field_correct = sum(result["field_check"]["correct"] for result in results)
    field_total = sum(result["field_check"]["total"] for result in results)
    passed = sum(1 for result in results if result["passed"])
    product_any_hits = sum(1 for result in results if result["product_candidate_check"]["any_hit"])

    product = aggregate_set_metrics(results, "product_candidate_check")
    risk = aggregate_set_metrics(results, "risk_flag_check")
    missing = aggregate_set_metrics(results, "missing_field_check")

    return {
        "total_inquiries": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": safe_ratio(passed, total),
        "field_accuracy": safe_ratio(field_correct, field_total),
        "product_candidate_hit_rate": safe_ratio(product_any_hits, total),
        "product_candidate_precision": product["precision"],
        "product_candidate_recall": product["recall"],
        "product_candidate_f1": product["f1"],
        "risk_flag_precision": risk["precision"],
        "risk_flag_recall": risk["recall"],
        "risk_flag_f1": risk["f1"],
        "risk_false_positive_inquiries": risk["false_positive_inquiries"],
        "missing_field_precision": missing["precision"],
        "missing_field_recall": missing["recall"],
        "missing_field_f1": missing["f1"],
        "missing_field_false_positive_inquiries": missing["false_positive_inquiries"],
    }


def aggregate_set_metrics(results: list[dict[str, Any]], check_key: str) -> dict[str, Any]:
    # Micro-averaged precision/recall across all inquiries for one set-based
    # check, plus how many inquiries had at least one false positive.
    hit = sum(result[check_key]["hit_count"] for result in results)
    gold = sum(result[check_key]["gold_count"] for result in results)
    predicted = sum(result[check_key]["predicted_count"] for result in results)
    precision = safe_ratio(hit, predicted)
    recall = safe_ratio(hit, gold)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1_score(precision, recall),
        "false_positive_inquiries": sum(
            1 for result in results if result[check_key]["false_positives"]
        ),
    }


def safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 4)
