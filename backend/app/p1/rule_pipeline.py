from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.app.data.loaders import DemoData, load_demo_data
from backend.app.p1.candidate_retriever import (
    extract_product_group,
    format_candidate,
    product_name_for_group,
    retrieve_product_candidates,
)
from backend.app.p3.evidence_retriever import retrieve_evidence

# TODO: These vocabularies are hardcoded only to make the first manufacturing
# demo deterministic. Later they should come from industry config, customer
# catalogs, synonym dictionaries, and/or structured extraction results.
MATERIALS = ["ductile iron", "SS304", "SS316", "WCB", "brass"]
CONNECTION_TYPES = ["threaded", "flanged", "wafer", "lug"]
CERTIFICATIONS = ["RoHS", "WRAS", "FDA", "UL", "CE"]


def run_inquiry_pipeline(inquiry_id: str, root_dir: Path | None = None) -> dict[str, Any]:
    data = load_demo_data(root_dir or Path.cwd())
    inquiry = find_inquiry(data, inquiry_id)
    return run_pipeline_for_inquiry(inquiry, data)


def run_pipeline_for_inquiry(inquiry: dict[str, Any], data: DemoData) -> dict[str, Any]:
    product_by_id = {product["product_id"]: product for product in data.products}
    rule_by_id = {rule["id"]: rule for rule in data.risk_rules}

    # The pipeline is kept as explicit steps so each stage can be evaluated and
    # replaced independently: parser -> candidates -> evidence -> risks -> reply.
    extracted = extract_fields(inquiry)
    line_item = extracted["line_items"][0]
    candidates = retrieve_product_candidates(line_item, product_by_id)
    evidence = retrieve_evidence(candidates, inquiry, extracted, data.product_docs)
    risk_flags = detect_risks(extracted, line_item, candidates, rule_by_id, inquiry)
    clarification_questions = generate_clarification_questions(line_item, candidates, risk_flags)
    reply_policy = build_reply_policy(risk_flags)

    return {
        "inquiry_id": inquiry["inquiry_id"],
        "input": {
            "subject": inquiry.get("subject"),
            "body": inquiry.get("body"),
        },
        "extracted_fields": extracted,
        "product_matches": {
            "primary_candidates": [format_candidate(product) for product in candidates],
            "should_not_select_final_product_without_clarification": should_not_select_final_product(
                line_item, risk_flags
            ),
        },
        "evidence": evidence,
        "risk_flags": risk_flags,
        "clarification_questions": clarification_questions,
        "reply_policy": reply_policy,
    }


def find_inquiry(data: DemoData, inquiry_id: str) -> dict[str, Any]:
    for inquiry in data.inquiries:
        if inquiry.get("inquiry_id") == inquiry_id:
            return inquiry
    raise ValueError(f"Unknown inquiry_id: {inquiry_id}")


def extract_fields(inquiry: dict[str, Any]) -> dict[str, Any]:
    # TODO: This regex parser is a baseline for synthetic data only. P5 should
    # replace it with structured extraction backed by a model gateway, while P2
    # keeps measuring whether the replacement improves or breaks the workflow.
    text = f"{inquiry.get('subject', '')}\n{inquiry.get('body', '')}"
    product_group = extract_product_group(text)
    product_name = product_name_for_group(product_group)
    size = extract_first(r"\bDN\d+\b", text, flags=re.IGNORECASE)
    material = extract_material(text)
    pressure_rating = extract_first(r"\bPN\d+\b", text, flags=re.IGNORECASE)
    connection_type = extract_connection_type(text)
    certification = extract_certification(text)
    requested_delivery_days = extract_int(r"within\s+(\d+)\s+days", text)
    quantity = extract_int(r"\b(\d+)\s*pcs\b", text)
    application = extract_application(text, inquiry.get("customer_country"))
    missing_fields = required_missing_fields(size, material, pressure_rating, connection_type)

    return {
        "request_type": "quote_request",
        "customer_country": inquiry.get("customer_country"),
        "application": application,
        "line_items": [
            {
                "product_name": product_name,
                "quantity": quantity,
                "size": normalize_upper(size),
                "material_grade": material,
                "pressure_rating": normalize_upper(pressure_rating),
                "connection_type": connection_type,
                "certification": certification,
                "requested_delivery_days": requested_delivery_days,
                "missing_fields": missing_fields,
            }
        ],
    }


def extract_first(pattern: str, text: str, flags: int = 0) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(0) if match else None


def extract_int(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def extract_material(text: str) -> str | None:
    lowered = text.lower()
    for material in MATERIALS:
        if material.lower() in lowered:
            return material
    return None


def extract_connection_type(text: str) -> str | None:
    lowered = text.lower()
    for connection_type in CONNECTION_TYPES:
        if re.search(rf"\b{re.escape(connection_type)}\b", lowered):
            return connection_type
    return None


def extract_certification(text: str) -> str | None:
    lowered = text.lower()
    for certification in CERTIFICATIONS:
        if re.search(rf"\b{re.escape(certification.lower())}\b", lowered):
            return certification
    return None


def extract_application(text: str, country: str | None) -> str | None:
    if not country:
        return None

    # TODO: This only catches phrases like "for a project in Germany". Real
    # emails express application/environment in many places and languages, so
    # this should become part of the structured extractor rather than a regex.
    pattern = rf"for (?:a|an) (.+?) in {re.escape(country)}"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None

    application = clean_space(match.group(1))
    return None if application.lower() == "project" else application


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" .,\n\t")


def normalize_upper(value: str | None) -> str | None:
    return value.upper() if value else None


def required_missing_fields(
    size: str | None,
    material: str | None,
    pressure_rating: str | None,
    connection_type: str | None,
) -> list[str]:
    missing = []
    if not size:
        missing.append("size")
    if not material:
        missing.append("material grade")
    if not pressure_rating:
        missing.append("pressure rating")
    if not connection_type:
        missing.append("connection type")
    return missing


def detect_risks(
    extracted: dict[str, Any],
    line_item: dict[str, Any],
    candidates: list[dict[str, str]],
    rule_by_id: dict[str, dict[str, str]],
    inquiry: dict[str, Any],
) -> list[dict[str, str]]:
    # Risk checks should remain deterministic even after LLM extraction is added:
    # they are approval constraints and safety rails, not model suggestions.
    # TODO: Move scenario-specific thresholds/actions into typed rule config.
    risk_flags: list[dict[str, str]] = []

    if line_item["missing_fields"]:
        add_risk(
            risk_flags,
            rule_by_id,
            "missing_required_specs",
            f"Missing required quotation fields: {', '.join(line_item['missing_fields'])}.",
        )

    if not extracted.get("application"):
        add_risk(
            risk_flags,
            rule_by_id,
            "unclear_application",
            "Application or operating environment is not provided.",
        )

    delivery_days = line_item.get("requested_delivery_days")
    if delivery_days is not None and any(
        delivery_days < int(product["standard_lead_time_days"]) for product in candidates
    ):
        add_risk(
            risk_flags,
            rule_by_id,
            "delivery_shorter_than_standard",
            "Requested delivery time is shorter than at least one matched product's standard lead time.",
        )

    certification = line_item.get("certification")
    if certification and candidates and all(
        certification not in split_certifications(product["certifications"]) for product in candidates
    ):
        add_risk(
            risk_flags,
            rule_by_id,
            "certification_not_supported",
            f"Requested certification {certification} is not listed for the matched product candidates.",
        )

    quantity = line_item.get("quantity")
    if quantity is not None and any(quantity < int(product["moq"]) for product in candidates):
        add_risk(
            risk_flags,
            rule_by_id,
            "quantity_below_moq",
            "Requested quantity is below MOQ for at least one matched product candidate.",
        )

    material = line_item.get("material_grade")
    if material and candidates and all(product["material"].lower() != material.lower() for product in candidates):
        add_risk(
            risk_flags,
            rule_by_id,
            "non_standard_material",
            f"Requested material {material} is outside matched product candidate materials.",
        )

    size = line_item.get("size")
    if size and candidates and all(not size_in_range(size, product["size_range"]) for product in candidates):
        add_risk(
            risk_flags,
            rule_by_id,
            "non_standard_size",
            f"Requested size {size} is outside matched product candidate size ranges.",
        )

    inquiry_text = f"{inquiry.get('subject', '')}\n{inquiry.get('body', '')}"
    if re.search(r"\b(also|alternative)\b", inquiry_text, re.IGNORECASE):
        add_risk(
            risk_flags,
            rule_by_id,
            "multi_product_inquiry",
            "Inquiry includes additional product or alternative product request.",
        )

    add_risk(
        risk_flags,
        rule_by_id,
        "price_commitment_required_approval",
        "AI-generated reply must not commit final price without human approval.",
    )

    return risk_flags


def add_risk(
    risk_flags: list[dict[str, str]],
    rule_by_id: dict[str, dict[str, str]],
    rule_id: str,
    reason: str,
) -> None:
    rule = rule_by_id.get(rule_id, {})
    risk_flags.append(
        {
            "rule_id": rule_id,
            "severity": rule.get("severity", "unknown"),
            "reason": reason,
            "action": rule.get("action", "review"),
        }
    )


def split_certifications(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def size_in_range(size: str, size_range: str) -> bool:
    requested = parse_dn(size)
    bounds = [parse_dn(part) for part in size_range.split("-")]
    if requested is None or len(bounds) != 2 or None in bounds:
        return True
    return bounds[0] <= requested <= bounds[1]


def parse_dn(value: str) -> int | None:
    match = re.search(r"DN(\d+)", value, re.IGNORECASE)
    return int(match.group(1)) if match else None


def generate_clarification_questions(
    line_item: dict[str, Any],
    candidates: list[dict[str, str]],
    risk_flags: list[dict[str, str]],
) -> list[str]:
    # TODO: These English questions are fixed templates for the demo. Future
    # versions should select localized, customer-approved templates by risk type,
    # sales stage, and channel.
    questions = []
    for field in line_item["missing_fields"]:
        if field == "size":
            questions.append("Please confirm the required valve size, for example DN50.")
        elif field == "material grade":
            questions.append(
                "Please confirm the required material grade, such as SS304, SS316, WCB, brass, or ductile iron."
            )
        elif field == "pressure rating":
            questions.append("Please confirm the required pressure rating, such as PN10, PN16, or PN25.")
        elif field == "connection type":
            questions.append(
                "Please confirm the required connection type, such as threaded, flanged, wafer, or lug."
            )

    delivery_days = line_item.get("requested_delivery_days")
    if delivery_days is not None and any(
        flag["rule_id"] == "delivery_shorter_than_standard" for flag in risk_flags
    ):
        questions.append(
            f"Please confirm whether the requested {delivery_days}-day delivery schedule is mandatory or flexible."
        )

    if any(flag["rule_id"] == "certification_not_supported" for flag in risk_flags):
        questions.append("Please confirm the exact certification requirement and target market.")

    if any(flag["rule_id"] == "non_standard_size" for flag in risk_flags):
        questions.append("Please confirm whether an alternative standard size is acceptable.")

    if any(flag["rule_id"] == "non_standard_material" for flag in risk_flags):
        questions.append("Please confirm whether an alternative standard material is acceptable.")

    return questions


def build_reply_policy(risk_flags: list[dict[str, str]]) -> dict[str, bool]:
    # TODO: The policy is intentionally conservative and coarse. A real approval
    # layer should include policy source, severity, approver role, audit status,
    # and fields that are blocked from auto-generation.
    return {
        "can_generate_reply_draft": True,
        "must_not_commit_final_price": True,
        "must_not_commit_requested_delivery": any(
            flag["rule_id"] == "delivery_shorter_than_standard" for flag in risk_flags
        ),
        "must_require_human_approval": True,
    }


def should_not_select_final_product(
    line_item: dict[str, Any],
    risk_flags: list[dict[str, str]],
) -> bool:
    high_risk_flags = [
        flag
        for flag in risk_flags
        if flag["severity"] == "high" and flag["rule_id"] != "price_commitment_required_approval"
    ]
    return bool(line_item["missing_fields"] or high_risk_flags)
