"""Reproducible generator for the synthetic manufacturing-export dataset.

Ported from the original JavaScript generator (now removed), this version reads
`products/products.csv` through the same loader the runtime uses (so
there is a single CSV parser, not a JS/Python fork) and writes:

    inquiries/synthetic_inquiries.jsonl
    eval/gold_answers.jsonl

It is deliberately an INDEPENDENT codification of the expected answers: it does
not import the pipeline's extraction/risk functions. Gold must stay a fixed
target the pipeline is measured against — if gold were produced by the pipeline
itself, the evaluation could never detect a regression.

Run from anywhere:

    python3 scripts/generate_manufacturing_export_data.py

Note: the gold risk rule `restricted_claim` is kept in sync with
`detect_risks` in backend/app/p1/rule_pipeline.py.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.data.loaders import (  # noqa: E402
    DATASET_PATHS,
    DATA_PATHS,
    PROJECT_ROOT,
    parse_csv,
    read_text,
    resolve_data_path,
)

CANDIDATE_GROUPS = {
    "stainless_ball_valve": ["SV-BV-100", "SV-BV-200"],
    "butterfly_valve": ["SV-BF-100", "SV-BF-200"],
    "check_valve": ["SV-CV-100", "SV-CV-200"],
    "gate_valve": ["SV-GV-100", "SV-GV-200"],
    "solenoid_valve": ["SV-SV-100", "SV-SV-200"],
    "flange": ["SV-FT-100"],
}

PRODUCT_PHRASE = {
    "stainless_ball_valve": "stainless steel ball valves",
    "butterfly_valve": "butterfly valves",
    "check_valve": "check valves",
    "gate_valve": "gate valves",
    "solenoid_valve": "solenoid valves",
    "flange": "stainless steel flanges",
}

# scenario = [group, country, application, quantity, size, material, pressure,
#             connection, certification, delivery_days, (optional) extra]
SCENARIOS = [
    ["stainless_ball_valve", "Germany", "water treatment project", 500, "DN50", None, None, None, "CE", 15],
    ["stainless_ball_valve", "United Arab Emirates", "desalination plant", 80, "DN80", "SS316", "PN25", "flanged", "RoHS", 35],
    ["stainless_ball_valve", "Spain", "industrial water line", 40, "DN25", "SS304", "PN16", "threaded", "CE", 25],
    ["stainless_ball_valve", "Mexico", None, 30, None, None, None, None, "CE", 20],
    ["stainless_ball_valve", "Brazil", "chemical dosing skid", 60, "DN150", "SS316", "PN25", "flanged", "CE", 25],
    ["butterfly_valve", "Saudi Arabia", "HVAC project", 120, "DN150", "ductile iron", "PN16", "wafer", "CE", 30],
    ["butterfly_valve", "South Africa", "municipal water pipeline", 25, "DN350", "ductile iron", "PN16", "lug", "WRAS", 20],
    ["butterfly_valve", "India", None, 60, "DN80", None, "PN16", None, "CE", 25],
    ["butterfly_valve", "Thailand", "cooling water system", 20, "DN450", "ductile iron", "PN16", "lug", "CE", 45],
    ["butterfly_valve", "Chile", "water treatment upgrade", 100, "DN100", "ductile iron", "PN16", "wafer", "FDA", 30],
    ["check_valve", "Germany", "oil pipeline maintenance", 35, "DN100", "WCB", "PN16", "flanged", "CE", 28],
    ["check_valve", "France", "compact pump station", 120, "DN40", "SS304", "PN16", "threaded", "RoHS", 18],
    ["check_valve", "United States", None, 20, "DN200", None, None, "flanged", "CE", 20],
    ["check_valve", "Italy", "food-grade process line", 70, "DN80", "SS304", "PN16", "threaded", "FDA", 25],
    ["check_valve", "Vietnam", "water booster system", 10, "DN50", "WCB", "PN16", "flanged", "CE", 35],
    ["gate_valve", "Turkey", "industrial pipeline shutoff", 24, "DN150", "WCB", "PN16", "flanged", "CE", 45],
    ["gate_valve", "Netherlands", "corrosive media pipeline", 25, "DN100", "SS316", "PN25", "flanged", "RoHS", 30],
    ["gate_valve", "Poland", None, 15, "DN80", None, "PN16", "flanged", "CE", 40],
    ["gate_valve", "Egypt", "irrigation pumping station", 12, "DN350", "WCB", "PN16", "flanged", "CE", 35],
    ["gate_valve", "Canada", "industrial plant expansion", 22, "DN50", "SS304", "PN25", "flanged", "CE", 50],
    ["solenoid_valve", "Singapore", "water control cabinet", 300, "DN25", "brass", "PN10", "threaded", "CE", 20],
    ["solenoid_valve", "Malaysia", "food-grade filling line", 90, "DN50", "SS304", "PN16", "threaded", "RoHS", 18],
    ["solenoid_valve", "Indonesia", None, 50, "DN15", None, None, None, "CE", 10],
    ["solenoid_valve", "Australia", "air control system", 150, "DN40", "brass", "PN10", "threaded", "UL", 25],
    ["solenoid_valve", "Philippines", "clean water dosing line", 70, "DN100", "SS304", "PN16", "threaded", "CE", 30],
    ["flange", "Germany", "pipe installation project", 1000, "DN100", "SS304", "PN16", "flanged", "CE", 20],
    ["flange", "Spain", "stainless steel piping project", 150, "DN150", "SS316", "PN16", "flanged", "CE", 15],
    ["flange", "Mexico", None, 80, None, "SS304", None, "flanged", "CE", 12],
    ["flange", "Saudi Arabia", "pipeline maintenance", 220, "DN250", "SS304", "PN16", "flanged", "CE", 18],
    ["flange", "UAE", "water treatment skid", 50, "DN50", "SS304", "PN16", "flanged", "RoHS", 10],
    ["stainless_ball_valve", "Colombia", "water treatment project", 200, "DN25", "SS304", "PN16", "threaded", "CE", 22],
    ["stainless_ball_valve", "Morocco", "chemical plant utility line", 55, "DN100", "SS316", "PN25", "flanged", "CE", 20],
    ["butterfly_valve", "Peru", "mining water pipeline", 75, "DN200", "ductile iron", "PN16", None, "CE", 25],
    ["butterfly_valve", "Qatar", "district cooling project", 18, "DN300", "ductile iron", "PN16", "lug", "WRAS", 28],
    ["check_valve", "Kenya", "pump station", 45, "DN150", "WCB", "PN16", "flanged", "CE", 14],
    ["check_valve", "Argentina", "clean water system", 90, "DN25", "SS304", "PN16", "threaded", "CE", 30],
    ["gate_valve", "Romania", "industrial pipeline", 18, "DN200", "WCB", "PN16", "flanged", "CE", 42],
    ["gate_valve", "Greece", "marine utility line", 28, "DN100", "SS316", "PN25", "flanged", "RoHS", 25],
    ["solenoid_valve", "New Zealand", "irrigation control", 200, "DN20", "brass", "PN10", "threaded", "CE", 12],
    ["solenoid_valve", "Korea", "food-grade dosing project", 100, "DN65", "SS304", "PN16", "threaded", "RoHS", 35],
    ["stainless_ball_valve", "Germany", "water treatment project", 500, "DN50", "SS304", "PN16", "threaded", "CE", 20, "Please also include 200 pcs stainless steel flanges DN50 PN16."],
    ["butterfly_valve", "Brazil", "municipal pipeline", 100, "DN100", "ductile iron", "PN16", "wafer", "CE", 25, "We may also need swing check valves DN100."],
    ["check_valve", "India", "pump station", 60, "DN100", "WCB", "PN16", "flanged", "CE", 28, "Please offer an alternative stainless steel check valve if available."],
    ["gate_valve", "UAE", "industrial pipeline", 20, "DN150", "WCB", "PN16", "flanged", "CE", 20, "The project owner asks for guaranteed 20-day delivery."],
    ["solenoid_valve", "Spain", "water control cabinet", 250, "DN25", "brass", "PN10", "threaded", "CE", 18, "Please quote with spare coils if available."],
    ["stainless_ball_valve", "France", None, 10, None, None, None, None, None, None],
    ["butterfly_valve", "Germany", None, 10, None, None, None, None, None, None],
    ["check_valve", "Italy", None, 10, None, None, None, None, None, None],
    ["gate_valve", "Netherlands", None, 10, None, None, None, None, None, None],
    ["solenoid_valve", "Poland", None, 10, None, None, None, None, None, None],
]


def parse_dn(value):
    match = re.search(r"DN(\d+)", str(value or ""), re.IGNORECASE)
    return int(match.group(1)) if match else None


def size_in_range(size, size_range):
    requested = parse_dn(size)
    bounds = [parse_dn(part) for part in str(size_range or "").split("-")]
    if not requested or len(bounds) != 2 or None in bounds:
        return True
    return bounds[0] <= requested <= bounds[1]


def split_certs(value):
    return [cert.strip() for cert in str(value or "").split(";") if cert.strip()]


def candidate_products(group, material, connection, product_by_id):
    candidates = [product_by_id[pid] for pid in CANDIDATE_GROUPS[group] if pid in product_by_id]
    if material:
        material_matches = [p for p in candidates if p["material"].lower() == material.lower()]
        if material_matches:
            candidates = material_matches
    if connection:
        connection_matches = [p for p in candidates if p["connection_type"].lower() == connection.lower()]
        if connection_matches:
            candidates = connection_matches
    return candidates


def missing_fields(size, material, pressure, connection):
    missing = []
    if not size:
        missing.append("size")
    if not material:
        missing.append("material grade")
    if not pressure:
        missing.append("pressure rating")
    if not connection:
        missing.append("connection type")
    return missing


def risk_flags(scenario, candidates, missing):
    _, _, application, quantity, size, material, pressure, connection, certification, delivery_days = scenario[:10]
    extra = scenario[10] if len(scenario) > 10 else None
    flags = []
    if missing:
        flags.append({"rule_id": "missing_required_specs", "severity": "high",
                      "reason": f"Missing required quotation fields: {', '.join(missing)}."})
    if not application:
        flags.append({"rule_id": "unclear_application", "severity": "medium",
                      "reason": "Application or operating environment is not provided."})
    if delivery_days is not None and any(delivery_days < int(p["standard_lead_time_days"]) for p in candidates):
        flags.append({"rule_id": "delivery_shorter_than_standard", "severity": "high",
                      "reason": "Requested delivery time is shorter than at least one matched product's standard lead time."})
    if certification and all(certification not in split_certs(p["certifications"]) for p in candidates):
        flags.append({"rule_id": "certification_not_supported", "severity": "high",
                      "reason": f"Requested certification {certification} is not listed for the matched product candidates."})
    if any(quantity < int(p["moq"]) for p in candidates):
        flags.append({"rule_id": "quantity_below_moq", "severity": "medium",
                      "reason": "Requested quantity is below MOQ for at least one matched product candidate."})
    if material and all(p["material"].lower() != material.lower() for p in candidates):
        flags.append({"rule_id": "non_standard_material", "severity": "medium",
                      "reason": f"Requested material {material} is outside matched product candidate materials."})
    if size and all(not size_in_range(size, p["size_range"]) for p in candidates):
        flags.append({"rule_id": "non_standard_size", "severity": "medium",
                      "reason": f"Requested size {size} is outside matched product candidate size ranges."})
    if extra and re.search(r"also|alternative", extra, re.IGNORECASE):
        flags.append({"rule_id": "multi_product_inquiry", "severity": "low",
                      "reason": "Inquiry includes additional product or alternative product request."})
    # Keep in sync with detect_risks in backend/app/p1/rule_pipeline.py.
    if extra and re.search(r"\b(guarantee|guaranteed|guarantees|legally binding|penalty clause)\b", extra, re.IGNORECASE):
        flags.append({"rule_id": "restricted_claim", "severity": "high",
                      "reason": "Customer requests a guaranteed commitment that must not be promised without human approval."})
    flags.append({"rule_id": "price_commitment_required_approval", "severity": "high",
                  "reason": "AI-generated reply must not commit final price without human approval."})
    return flags


def build_body(scenario):
    group, country, application, quantity, size, material, pressure, connection, certification, delivery_days = scenario[:10]
    extra = scenario[10] if len(scenario) > 10 else None
    tail = f" for a {application} in {country}" if application else f" for a project in {country}"
    parts = ["Hi,", f"We are looking for {quantity} pcs {PRODUCT_PHRASE[group]}{tail}."]
    specs = []
    if size:
        specs.append(f"size {size}")
    if material:
        specs.append(f"material {material}")
    if pressure:
        specs.append(f"pressure rating {pressure}")
    if connection:
        specs.append(f"{connection} connection")
    if certification:
        specs.append(f"{certification} certification")
    if specs:
        parts.append(f"Required specifications: {', '.join(specs)}.")
    if delivery_days is not None:
        parts.append(f"Please quote your best price and confirm whether delivery within {delivery_days} days is possible.")
    else:
        parts.append("Please quote your best price and let us know what information you need from our side.")
    if extra:
        parts.append(extra)
    parts.extend(["Best regards,", "Purchasing Team"])
    return "\n\n".join(parts)


def clarification_questions(missing, delivery_days, candidates):
    questions = []
    for field in missing:
        if field == "size":
            questions.append("Please confirm the required valve size, for example DN50.")
        elif field == "material grade":
            questions.append("Please confirm the required material grade, such as SS304, SS316, WCB, brass, or ductile iron.")
        elif field == "pressure rating":
            questions.append("Please confirm the required pressure rating, such as PN10, PN16, or PN25.")
        elif field == "connection type":
            questions.append("Please confirm the required connection type, such as threaded, flanged, wafer, or lug.")
    if delivery_days is not None and any(delivery_days < int(p["standard_lead_time_days"]) for p in candidates):
        questions.append(f"Please confirm whether the requested {delivery_days}-day delivery schedule is mandatory or flexible.")
    return questions


def dumps(obj):
    # Match the original JSON.stringify output: compact, no spaces.
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def main():
    products = parse_csv(read_text(resolve_data_path(PROJECT_ROOT, DATA_PATHS["products"])))
    product_by_id = {p["product_id"]: p for p in products}

    inquiries = []
    gold_answers = []

    for index, scenario in enumerate(SCENARIOS):
        group, country, application, quantity, size, material, pressure, connection, certification, delivery_days = scenario[:10]
        inquiry_id = f"INQ-SYN-{index + 1:03d}"
        candidates = candidate_products(group, material, connection, product_by_id)
        missing = missing_fields(size, material, pressure, connection)
        flags = risk_flags(scenario, candidates, missing)
        should_not_select = bool(missing) or any(
            f["severity"] == "high" and f["rule_id"] != "price_commitment_required_approval" for f in flags
        )

        inquiries.append({
            "inquiry_id": inquiry_id,
            "synthetic": True,
            "language": "en",
            "channel": "email",
            "customer_country": country,
            "subject": f"Inquiry for {PRODUCT_PHRASE[group]}",
            "body": build_body(scenario),
        })

        gold_answers.append({
            "inquiry_id": inquiry_id,
            "gold_field_extraction": {
                "request_type": "quote_request",
                "customer_country": country,
                "application": application,
                "line_items": [{
                    "product_name": re.sub(r"s$", "", PRODUCT_PHRASE[group]),
                    "quantity": quantity,
                    "size": size,
                    "material_grade": material,
                    "pressure_rating": pressure,
                    "connection_type": connection,
                    "certification": certification,
                    "requested_delivery_days": delivery_days,
                    "missing_fields": missing,
                }],
            },
            "gold_product_match": {
                "primary_candidates": [{
                    "product_id": p["product_id"],
                    "reason": (
                        f"{p['product_name']}, material {p['material']}, size range {p['size_range']}, "
                        f"{p['pressure_rating']}, {p['connection_type']} connection, "
                        f"certifications {p['certifications']}, standard lead time {p['standard_lead_time_days']} days."
                    ),
                } for p in candidates],
                "should_not_select_final_product_without_clarification": should_not_select,
            },
            "gold_risk_flags": flags,
            "gold_clarification_questions": clarification_questions(missing, delivery_days, candidates),
            "expected_reply_policy": {
                "can_generate_reply_draft": True,
                "must_not_commit_final_price": True,
                "must_not_commit_requested_delivery": any(f["rule_id"] == "delivery_shorter_than_standard" for f in flags),
                "must_require_human_approval": True,
            },
        })

    inquiries_path = resolve_data_path(PROJECT_ROOT, DATASET_PATHS["default"]["inquiries"])
    gold_path = resolve_data_path(PROJECT_ROOT, DATASET_PATHS["default"]["gold_answers"])
    inquiries_path.write_text("\n".join(dumps(x) for x in inquiries) + "\n", encoding="utf-8")
    gold_path.write_text("\n".join(dumps(x) for x in gold_answers) + "\n", encoding="utf-8")

    print(f"Generated {len(inquiries)} inquiries -> {inquiries_path.relative_to(PROJECT_ROOT)}")
    print(f"Generated {len(gold_answers)} gold answers -> {gold_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
