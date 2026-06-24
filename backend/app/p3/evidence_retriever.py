from __future__ import annotations

import re
from typing import Any


def retrieve_evidence(
    candidates: list[dict[str, str]],
    inquiry: dict[str, Any],
    extracted_fields: dict[str, Any],
    product_docs: dict[str, str],
) -> dict[str, Any]:
    # P3 evidence retrieval explains product candidates with auditable sources.
    # It does not decide the final product; that decision still requires risk
    # checks, missing-field handling, and eventually human approval.
    citations = []
    cited_source_ids = set()

    for product in candidates:
        product_id = product["product_id"]
        doc = product_docs.get(product_id)
        if not doc:
            continue

        citations.append(
            build_citation(
                source_id=product_id,
                text=doc,
                matched_by=["candidate_product"],
                matched_terms=candidate_matched_terms(product, extracted_fields),
                score=1.0,
            )
        )
        cited_source_ids.add(product_id)

    supplemental = retrieve_keyword_citations(
        inquiry=inquiry,
        extracted_fields=extracted_fields,
        product_docs=product_docs,
        excluded_source_ids=cited_source_ids,
        limit=3,
    )
    citations.extend(supplemental)

    return {
        "retrieval_mode": "product_id_and_keyword",
        "citations": citations,
    }


def build_citation(
    source_id: str,
    text: str,
    matched_by: list[str],
    matched_terms: list[str],
    score: float,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source": f"products/product_docs.md#{source_id}",
        "text": normalize_doc_text(text),
        "matched_by": matched_by,
        "matched_terms": matched_terms,
        "score": score,
    }


def normalize_doc_text(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines()]
    content_lines = [line for line in lines if line and not line.startswith("## ")]
    return " ".join(content_lines)


def candidate_matched_terms(product: dict[str, str], extracted_fields: dict[str, Any]) -> list[str]:
    # TODO: These terms are intentionally hardcoded for the product-doc demo.
    # Later we should separate product attributes, inquiry requirements, and
    # citation highlights through a configurable schema instead of one flat list.
    terms = [
        product["product_id"],
        product["product_name"],
        product["material"],
        product["pressure_rating"],
        product["connection_type"],
    ]
    line_item = first_line_item(extracted_fields)
    for field in ["size", "certification"]:
        value = line_item.get(field)
        if value:
            terms.append(str(value))
    return unique_non_empty(terms)


def retrieve_keyword_citations(
    inquiry: dict[str, Any],
    extracted_fields: dict[str, Any],
    product_docs: dict[str, str],
    excluded_source_ids: set[str],
    limit: int,
) -> list[dict[str, Any]]:
    # Keyword citations are supplemental context. They may surface neighboring
    # products, but P4 should prefer candidate_product citations when drafting.
    # TODO: Evolve this into hybrid retrieval: structured filters + BM25/keyword
    # search + vector search + rerank, with source-level access controls.
    keywords = build_keywords(inquiry, extracted_fields)
    scored = []

    for source_id, doc in product_docs.items():
        if source_id in excluded_source_ids:
            continue

        matched_terms = terms_in_text(keywords, doc)
        if len(matched_terms) < 2:
            continue

        scored.append(
            (
                len(matched_terms),
                source_id,
                build_citation(
                    source_id=source_id,
                    text=doc,
                    matched_by=["keyword"],
                    matched_terms=matched_terms,
                    score=round(len(matched_terms) / max(len(keywords), 1), 4),
                ),
            )
        )

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored[:limit]]


def build_keywords(inquiry: dict[str, Any], extracted_fields: dict[str, Any]) -> list[str]:
    line_item = first_line_item(extracted_fields)
    terms: list[str] = []

    for field in [
        "product_name",
        "size",
        "material_grade",
        "pressure_rating",
        "connection_type",
        "certification",
    ]:
        value = line_item.get(field)
        if value:
            terms.append(str(value))

    if extracted_fields.get("application"):
        terms.extend(split_words(str(extracted_fields["application"])))

    terms.extend(split_words(inquiry.get("subject", "")))
    return unique_non_empty(terms)


def split_words(text: str) -> list[str]:
    # TODO: Replace this toy tokenizer with language-aware tokenization and a
    # domain stop-word/synonym config when we handle real multilingual emails.
    stop_words = {
        "for",
        "the",
        "and",
        "with",
        "in",
        "a",
        "an",
        "of",
        "to",
        "we",
        "are",
        "looking",
        "inquiry",
    }
    words = re.findall(r"[A-Za-z0-9-]+", text)
    return [word for word in words if len(word) >= 3 and word.lower() not in stop_words]


def terms_in_text(terms: list[str], text: str) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term.lower() in lowered]


def first_line_item(fields: dict[str, Any]) -> dict[str, Any]:
    line_items = fields.get("line_items") or []
    return line_items[0] if line_items else {}


def unique_non_empty(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value is None:
            continue
        normalized = str(value).strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result
