from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.data.loaders import DATA_PATHS, load_demo_data


REQUIRED_PRODUCT_FIELDS = [
    "product_id",
    "product_name",
    "category",
    "material",
    "size_range",
    "pressure_rating",
    "connection_type",
    "certifications",
    "moq",
    "standard_lead_time_days",
    "price_band_usd",
    "source_type",
]

REQUIRED_INQUIRY_FIELDS = [
    "inquiry_id",
    "synthetic",
    "language",
    "channel",
    "customer_country",
    "subject",
    "body",
]


def validate_demo_data(root_dir: Path | None = None) -> dict[str, Any]:
    data = load_demo_data(root_dir or Path.cwd())
    errors: list[str] = []
    warnings: list[str] = []

    product_ids = collect_unique_ids(data.products, "product_id", "products", errors)
    risk_rule_ids = collect_unique_ids(data.risk_rules, "id", "risk rules", errors)
    inquiry_ids = collect_unique_ids(data.inquiries, "inquiry_id", "inquiries", errors)
    gold_ids = collect_unique_ids(data.gold_answers, "inquiry_id", "gold answers", errors)

    validate_required_fields(data.products, REQUIRED_PRODUCT_FIELDS, "product", "product_id", errors)
    validate_required_fields(data.inquiries, REQUIRED_INQUIRY_FIELDS, "inquiry", "inquiry_id", errors)
    validate_product_docs(data.product_docs, product_ids, errors, warnings)
    validate_inquiry_gold_alignment(data.inquiries, data.gold_answers, inquiry_ids, gold_ids, errors)
    validate_gold_references(data.gold_answers, product_ids, risk_rule_ids, errors)
    validate_risk_rules(data.risk_rules, errors)

    return {
        "files": {key: str(value) for key, value in DATA_PATHS.items()},
        "counts": {
            "products": len(data.products),
            "product_docs": len(data.product_docs),
            "risk_rules": len(data.risk_rules),
            "inquiries": len(data.inquiries),
            "gold_answers": len(data.gold_answers),
            "email_templates": len(data.email_templates),
        },
        "id_alignment": {
            "inquiries_and_gold_answers_match": same_ordered_ids(data.inquiries, data.gold_answers),
            "first_inquiry_id": data.inquiries[0].get("inquiry_id") if data.inquiries else None,
            "last_inquiry_id": data.inquiries[-1].get("inquiry_id") if data.inquiries else None,
        },
        "warnings": warnings,
        "errors": errors,
        "ok": not errors,
    }


def collect_unique_ids(
    rows: list[dict[str, Any]],
    field: str,
    label: str,
    errors: list[str],
) -> set[str]:
    ids: set[str] = set()
    for index, row in enumerate(rows, start=1):
        row_id = row.get(field)
        if not row_id:
            errors.append(f"{label} row {index} is missing {field}")
            continue
        if row_id in ids:
            errors.append(f"{label} has duplicate {field}: {row_id}")
        ids.add(str(row_id))
    return ids


def validate_required_fields(
    rows: list[dict[str, Any]],
    fields: list[str],
    label: str,
    id_field: str,
    errors: list[str],
) -> None:
    for index, row in enumerate(rows, start=1):
        row_id = row.get(id_field) or f"row {index}"
        for field in fields:
            if field not in row:
                errors.append(f"{label} {row_id} is missing field {field}")


def validate_product_docs(
    product_docs: dict[str, str],
    product_ids: set[str],
    errors: list[str],
    warnings: list[str],
) -> None:
    for product_id in product_ids:
        if product_id not in product_docs:
            errors.append(f"product_docs.md is missing section for product_id {product_id}")

    for doc_product_id in product_docs:
        if doc_product_id not in product_ids:
            warnings.append(f"product_docs.md has section {doc_product_id} not present in products.csv")


def validate_inquiry_gold_alignment(
    inquiries: list[dict[str, Any]],
    gold_answers: list[dict[str, Any]],
    inquiry_ids: set[str],
    gold_ids: set[str],
    errors: list[str],
) -> None:
    if len(inquiries) != len(gold_answers):
        errors.append(
            f"Inquiry count ({len(inquiries)}) does not match gold answer count ({len(gold_answers)})"
        )

    for inquiry_id in inquiry_ids:
        if inquiry_id not in gold_ids:
            errors.append(f"Missing gold answer for inquiry_id {inquiry_id}")

    for gold_id in gold_ids:
        if gold_id not in inquiry_ids:
            errors.append(f"Gold answer has no matching inquiry_id {gold_id}")

    if not same_ordered_ids(inquiries, gold_answers):
        errors.append("Inquiry and gold answer files contain different ordered inquiry_id sequences")


def same_ordered_ids(inquiries: list[dict[str, Any]], gold_answers: list[dict[str, Any]]) -> bool:
    if len(inquiries) != len(gold_answers):
        return False
    return all(
        inquiry.get("inquiry_id") == gold_answers[index].get("inquiry_id")
        for index, inquiry in enumerate(inquiries)
    )


def validate_gold_references(
    gold_answers: list[dict[str, Any]],
    product_ids: set[str],
    risk_rule_ids: set[str],
    errors: list[str],
) -> None:
    for gold in gold_answers:
        inquiry_id = gold.get("inquiry_id")
        candidates = gold.get("gold_product_match", {}).get("primary_candidates", [])
        for candidate in candidates:
            product_id = candidate.get("product_id")
            if product_id not in product_ids:
                errors.append(f"Gold answer {inquiry_id} references unknown product_id {product_id}")

        for risk_flag in gold.get("gold_risk_flags", []):
            rule_id = risk_flag.get("rule_id")
            if rule_id not in risk_rule_ids:
                errors.append(f"Gold answer {inquiry_id} references unknown rule_id {rule_id}")


def validate_risk_rules(risk_rules: list[dict[str, str]], errors: list[str]) -> None:
    for rule in risk_rules:
        rule_id = rule.get("id", "<missing-id>")
        if not rule.get("description"):
            errors.append(f"Risk rule {rule_id} is missing description")
        if not rule.get("severity"):
            errors.append(f"Risk rule {rule_id} is missing severity")
        if not rule.get("action"):
            errors.append(f"Risk rule {rule_id} is missing action")

