from __future__ import annotations

from typing import Any


# TODO: PRODUCT_GROUPS is a P1/P3 demo shortcut. In a real POC this should move
# to an industry/product taxonomy with customer-specific synonyms, model aliases,
# multilingual terms, and a retrieval/ranking layer over the product catalog.
PRODUCT_GROUPS = {
    "stainless_ball_valve": {
        "phrases": ["stainless steel ball valves", "stainless steel ball valve"],
        "product_name": "stainless steel ball valve",
        "candidate_ids": ["SV-BV-100", "SV-BV-200"],
    },
    "butterfly_valve": {
        "phrases": ["butterfly valves", "butterfly valve"],
        "product_name": "butterfly valve",
        "candidate_ids": ["SV-BF-100", "SV-BF-200"],
    },
    "check_valve": {
        "phrases": ["check valves", "check valve"],
        "product_name": "check valve",
        "candidate_ids": ["SV-CV-100", "SV-CV-200"],
    },
    "gate_valve": {
        "phrases": ["gate valves", "gate valve"],
        "product_name": "gate valve",
        "candidate_ids": ["SV-GV-100", "SV-GV-200"],
    },
    "solenoid_valve": {
        "phrases": ["solenoid valves", "solenoid valve"],
        "product_name": "solenoid valve",
        "candidate_ids": ["SV-SV-100", "SV-SV-200"],
    },
    "flange": {
        "phrases": ["stainless steel flanges", "stainless steel flange", "flanges", "flange"],
        "product_name": "stainless steel flange",
        "candidate_ids": ["SV-FT-100"],
    },
}


def extract_product_group(text: str) -> str | None:
    lowered = text.lower()
    for group, config in PRODUCT_GROUPS.items():
        for phrase in config["phrases"]:
            if phrase in lowered:
                return group
    return None


def product_name_for_group(group: str | None) -> str | None:
    if not group:
        return None
    return PRODUCT_GROUPS.get(group, {}).get("product_name")


def retrieve_product_candidates(
    line_item: dict[str, Any],
    product_by_id: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    # Candidate retrieval answers "which products might fit", not "which product
    # is final". The current ranking is deterministic and deliberately simple so
    # P2 can measure regressions while we replace pieces later.
    group = product_group_from_name(line_item.get("product_name"))
    if not group:
        return []

    candidate_ids = PRODUCT_GROUPS[group]["candidate_ids"]
    candidates = [product_by_id[product_id] for product_id in candidate_ids if product_id in product_by_id]

    material = line_item.get("material_grade")
    if material:
        # TODO: Keep these filters, but make their behavior catalog-driven.
        # Some real specs are hard constraints while others are preferences or
        # negotiable alternatives; the current demo treats matches too simply.
        material_matches = [
            product for product in candidates if product["material"].lower() == material.lower()
        ]
        if material_matches:
            candidates = material_matches

    connection_type = line_item.get("connection_type")
    if connection_type:
        connection_matches = [
            product
            for product in candidates
            if product["connection_type"].lower() == connection_type.lower()
        ]
        if connection_matches:
            candidates = connection_matches

    return candidates


def product_group_from_name(product_name: str | None) -> str | None:
    if not product_name:
        return None
    for group, config in PRODUCT_GROUPS.items():
        if product_name == config["product_name"]:
            return group
    return None


def format_candidate(product: dict[str, str]) -> dict[str, str]:
    return {
        "product_id": product["product_id"],
        "reason": (
            f"{product['product_name']}, material {product['material']}, "
            f"size range {product['size_range']}, {product['pressure_rating']}, "
            f"{product['connection_type']} connection, certifications {product['certifications']}, "
            f"standard lead time {product['standard_lead_time_days']} days."
        ),
    }
