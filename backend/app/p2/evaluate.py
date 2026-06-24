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


def evaluate_all(root_dir: Path | None = None) -> dict[str, Any]:
    # This is a regression harness, not proof of real-world accuracy. Current
    # gold labels were built for the same synthetic scenario, so future work must
    # add perturbed samples and customer-deidentified examples before judging fit.
    data = load_demo_data(root_dir or Path.cwd())
    gold_by_id = {gold["inquiry_id"]: gold for gold in data.gold_answers}
    results = []

    for inquiry in data.inquiries:
        inquiry_id = inquiry["inquiry_id"]
        prediction = run_pipeline_for_inquiry(inquiry, data)
        gold = gold_by_id[inquiry_id]
        results.append(evaluate_one(prediction, gold))

    return {
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

    passed = (
        field_check["accuracy"] == 1
        and product_check["all_gold_present"]
        and risk_check["all_gold_present"]
        and missing_field_check["all_gold_present"]
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
    predicted_ids = [candidate["product_id"] for candidate in predicted_candidates]
    gold_ids = [candidate["product_id"] for candidate in gold_candidates]
    predicted_set = set(predicted_ids)
    gold_set = set(gold_ids)
    hit_count = len(predicted_set & gold_set)

    return {
        "predicted": predicted_ids,
        "gold": gold_ids,
        "hit_count": hit_count,
        "gold_count": len(gold_ids),
        "any_hit": hit_count > 0,
        "all_gold_present": gold_set.issubset(predicted_set),
        "recall": safe_ratio(hit_count, len(gold_set)),
    }


def compare_rule_ids(
    predicted_rows: list[dict[str, Any]],
    gold_rows: list[dict[str, Any]],
    key: str,
) -> dict[str, Any]:
    predicted_ids = [row[key] for row in predicted_rows]
    gold_ids = [row[key] for row in gold_rows]
    predicted_set = set(predicted_ids)
    gold_set = set(gold_ids)
    hit_count = len(predicted_set & gold_set)

    return {
        "predicted": predicted_ids,
        "gold": gold_ids,
        "hit_count": hit_count,
        "gold_count": len(gold_set),
        "all_gold_present": gold_set.issubset(predicted_set),
        "recall": safe_ratio(hit_count, len(gold_set)),
    }


def compare_missing_fields(predicted: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    predicted_fields = first_line_item(predicted).get("missing_fields", [])
    gold_fields = first_line_item(gold).get("missing_fields", [])
    predicted_set = set(predicted_fields)
    gold_set = set(gold_fields)
    hit_count = len(predicted_set & gold_set)

    return {
        "predicted": predicted_fields,
        "gold": gold_fields,
        "hit_count": hit_count,
        "gold_count": len(gold_set),
        "all_gold_present": gold_set.issubset(predicted_set),
        "recall": safe_ratio(hit_count, len(gold_set)),
    }


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    field_correct = sum(result["field_check"]["correct"] for result in results)
    field_total = sum(result["field_check"]["total"] for result in results)
    passed = sum(1 for result in results if result["passed"])
    product_any_hits = sum(1 for result in results if result["product_candidate_check"]["any_hit"])
    product_hit_count = sum(result["product_candidate_check"]["hit_count"] for result in results)
    product_gold_count = sum(result["product_candidate_check"]["gold_count"] for result in results)
    risk_hit_count = sum(result["risk_flag_check"]["hit_count"] for result in results)
    risk_gold_count = sum(result["risk_flag_check"]["gold_count"] for result in results)
    missing_hit_count = sum(result["missing_field_check"]["hit_count"] for result in results)
    missing_gold_count = sum(result["missing_field_check"]["gold_count"] for result in results)

    return {
        "total_inquiries": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": safe_ratio(passed, total),
        "field_accuracy": safe_ratio(field_correct, field_total),
        "product_candidate_hit_rate": safe_ratio(product_any_hits, total),
        "product_candidate_recall": safe_ratio(product_hit_count, product_gold_count),
        "risk_flag_recall": safe_ratio(risk_hit_count, risk_gold_count),
        "missing_field_recall": safe_ratio(missing_hit_count, missing_gold_count),
    }


def safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 4)
