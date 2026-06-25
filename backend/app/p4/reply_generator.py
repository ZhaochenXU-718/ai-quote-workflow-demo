from __future__ import annotations

from typing import Any


STANDARD_TEMPLATE = "Standard Quote Reply"
MISSING_SPEC_TEMPLATE = "Missing Specification Clarification"
DELIVERY_TEMPLATE = "Delivery Confirmation Required"
CERTIFICATION_TEMPLATE = "Certification Confirmation Required"
RESTRICTED_CLAIM_TEMPLATE = "Restricted Commitment Review Required"


def generate_reply_draft(
    inquiry: dict[str, Any],
    extracted_fields: dict[str, Any],
    candidates: list[dict[str, str]],
    evidence: dict[str, Any],
    risk_flags: list[dict[str, str]],
    clarification_questions: list[str],
    reply_policy: dict[str, bool],
    email_templates: list[dict[str, str]],
) -> dict[str, Any]:
    # P4 is a controlled template renderer. It consumes upstream facts and
    # policy, but it does not infer new specs, prices, lead times, or approvals.
    template_name = select_template_name(risk_flags)
    template = find_template(email_templates, template_name)
    subject_template, body_template = split_template_subject(template["body"])
    context = build_template_context(
        inquiry=inquiry,
        extracted_fields=extracted_fields,
        candidates=candidates,
        clarification_questions=clarification_questions,
    )

    subject = render_template(
        subject_template or "Re: {original_subject}",
        context,
    )
    body = render_template(body_template, context)
    body = append_policy_guardrails(body, risk_flags, reply_policy)

    return {
        "status": "draft_requires_human_review",
        "template_name": template_name,
        "template_selection_reason": template_selection_reason(template_name, risk_flags),
        "subject": subject,
        "body": body,
        "supporting_citations": supporting_citations(evidence),
        "blocked_commitments": blocked_commitments(risk_flags, reply_policy),
        "safety_notes": safety_notes(risk_flags, reply_policy),
    }


def select_template_name(risk_flags: list[dict[str, str]]) -> str:
    rule_ids = rule_id_set(risk_flags)
    if "missing_required_specs" in rule_ids:
        return MISSING_SPEC_TEMPLATE
    if "certification_not_supported" in rule_ids:
        return CERTIFICATION_TEMPLATE
    if "restricted_claim" in rule_ids:
        return RESTRICTED_CLAIM_TEMPLATE
    if "delivery_shorter_than_standard" in rule_ids:
        return DELIVERY_TEMPLATE
    return STANDARD_TEMPLATE


def find_template(email_templates: list[dict[str, str]], template_name: str) -> dict[str, str]:
    for template in email_templates:
        if template.get("name") == template_name:
            return template
    raise ValueError(f"Missing email template: {template_name}")


def split_template_subject(template_body: str) -> tuple[str | None, str]:
    lines = template_body.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("subject:"):
            subject = stripped.split(":", 1)[1].strip()
            body = "\n".join(lines[index + 1 :]).strip()
            return subject, body
        break
    return None, template_body.strip()


def build_template_context(
    inquiry: dict[str, Any],
    extracted_fields: dict[str, Any],
    candidates: list[dict[str, str]],
    clarification_questions: list[str],
) -> dict[str, str]:
    line_item = first_line_item(extracted_fields)
    missing_fields = line_item.get("missing_fields") or []
    return {
        "customer_name": "Customer",
        "original_subject": str(inquiry.get("subject") or "your inquiry"),
        "product_name": str(line_item.get("product_name") or "your requested product"),
        "matched_product": matched_product_text(candidates),
        "clarification_questions": bullet_list(
            clarification_questions,
            empty_text="No additional clarification questions were identified at this stage.",
        ),
        "missing_fields": bullet_list(
            [missing_field_prompt(field) for field in missing_fields],
            empty_text="No required specification fields are missing.",
        ),
    }


def render_template(template: str, context: dict[str, str]) -> str:
    return template.format_map(SafeContext(context)).strip()


class SafeContext(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def matched_product_text(candidates: list[dict[str, str]]) -> str:
    if not candidates:
        return "no confirmed product candidate yet"
    labels = []
    for product in candidates[:2]:
        labels.append(
            (
                f"{product['product_id']} ({product['product_name']}, "
                f"{product['material']}, {product['size_range']}, "
                f"{product['pressure_rating']}, {product['connection_type']} connection)"
            )
        )
    if len(candidates) > 2:
        labels.append(f"{len(candidates) - 2} additional candidate(s)")
    return "; ".join(labels)


def append_policy_guardrails(
    body: str,
    risk_flags: list[dict[str, str]],
    reply_policy: dict[str, bool],
) -> str:
    paragraphs = []
    rule_ids = rule_id_set(risk_flags)
    lowered_body = body.lower()

    if reply_policy.get("must_not_commit_final_price"):
        paragraphs.append(
            "Please note that any formal price quotation will be subject to final sales review and approval."
        )
    if reply_policy.get("must_not_commit_requested_delivery") and "delivery commitment" not in lowered_body:
        paragraphs.append(
            "The requested delivery schedule will need production confirmation before we can make any delivery commitment."
        )
    if "restricted_claim" in rule_ids and "binding commitment" not in lowered_body:
        paragraphs.append(
            "Any guarantee or binding commitment will require internal review before confirmation."
        )

    if not paragraphs:
        return body.strip()
    return f"{body.strip()}\n\n" + "\n\n".join(paragraphs)


def supporting_citations(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    citations = evidence.get("citations") or []
    primary = [
        citation
        for citation in citations
        if "candidate_product" in citation.get("matched_by", [])
    ]
    # P4 drafts should rely on product-candidate evidence first; keyword matches
    # are supplemental and can be misleading if treated as selected products.
    selected = primary or citations[:2]
    return [
        {
            "source_id": citation.get("source_id"),
            "source": citation.get("source"),
            "matched_by": citation.get("matched_by", []),
            "matched_terms": citation.get("matched_terms", []),
        }
        for citation in selected[:3]
    ]


def blocked_commitments(
    risk_flags: list[dict[str, str]],
    reply_policy: dict[str, bool],
) -> list[str]:
    blocked = []
    rule_ids = rule_id_set(risk_flags)
    if reply_policy.get("must_not_commit_final_price"):
        blocked.append("final_price")
    if reply_policy.get("must_not_commit_requested_delivery"):
        blocked.append("requested_delivery")
    if "certification_not_supported" in rule_ids:
        blocked.append("certification_confirmation")
    if "restricted_claim" in rule_ids:
        blocked.append("guarantee_or_binding_commitment")
    return blocked


def safety_notes(
    risk_flags: list[dict[str, str]],
    reply_policy: dict[str, bool],
) -> list[str]:
    notes = ["Draft only; human review is required before sending."]
    if reply_policy.get("must_not_commit_final_price"):
        notes.append("No final price is included or implied.")
    if reply_policy.get("must_not_commit_requested_delivery"):
        notes.append("Requested delivery is not committed in the draft.")
    if "restricted_claim" in rule_id_set(risk_flags):
        notes.append("Customer requested a guarantee or binding commitment; keep legal/commercial approval in the loop.")
    return notes


def template_selection_reason(template_name: str, risk_flags: list[dict[str, str]]) -> str:
    rule_ids = rule_id_set(risk_flags)
    if template_name == MISSING_SPEC_TEMPLATE:
        return "missing_required_specs risk is present"
    if template_name == CERTIFICATION_TEMPLATE:
        return "certification_not_supported risk is present"
    if template_name == RESTRICTED_CLAIM_TEMPLATE:
        return "restricted_claim risk is present"
    if template_name == DELIVERY_TEMPLATE:
        return "delivery_shorter_than_standard risk is present"
    return "no risk-specific template was required"


def missing_field_prompt(field: str) -> str:
    prompts = {
        "size": "Required size, for example DN50.",
        "material grade": "Required material grade, such as SS304, SS316, WCB, brass, or ductile iron.",
        "pressure rating": "Required pressure rating, such as PN10, PN16, or PN25.",
        "connection type": "Required connection type, such as threaded, flanged, wafer, or lug.",
    }
    return prompts.get(field, field)


def bullet_list(items: list[str], empty_text: str) -> str:
    values = [item.strip() for item in items if item and item.strip()]
    if not values:
        return empty_text
    return "\n".join(f"- {item}" for item in values)


def rule_id_set(risk_flags: list[dict[str, str]]) -> set[str]:
    return {flag["rule_id"] for flag in risk_flags}


def first_line_item(fields: dict[str, Any]) -> dict[str, Any]:
    line_items = fields.get("line_items") or []
    return line_items[0] if line_items else {}
