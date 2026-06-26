from __future__ import annotations

import re
from typing import Any


# Deterministic safety gate for customer-facing reply drafts.
#
# This is intentionally independent of gold answers: these are invariants every
# draft must satisfy, not a match against expected output. P4's template renderer
# must pass it, and P5 must run the SAME gate on any LLM-rewritten draft before
# it can be surfaced — that is the whole point of keeping it reusable here.

# A currency amount must never appear in customer-facing text: the system only
# prepares quotations after human approval, so a number with a currency marker
# in the body means a price leaked in.
CURRENCY_RE = re.compile(
    r"(?:[$€£¥]\s*\d)"
    r"|(?:\b(?:usd|eur|gbp|rmb|cny|dollars?|euros?)\b\s*\d)"
    r"|(?:\d[\d,]*\s*(?:usd|eur|gbp|rmb|cny|dollars?|euros?|/\s*pc|per\s+piece))",
    re.IGNORECASE,
)

# A draft must never assert a first-person commitment. Note the verb must follow
# "we" (optionally via can/will/hereby) directly, so safe phrasings like
# "we will review", "we will need to confirm", or "before we can make any
# delivery commitment" do not trip it.
COMMITMENT_RE = re.compile(
    r"\bwe\s+(?:can\s+|will\s+|hereby\s+)?(?:guarantee|confirm|commit|promise|warrant)\b",
    re.IGNORECASE,
)

# Guardrail keyphrases that append_policy_guardrails injects. We assert presence
# rather than full sentences so wording can evolve without breaking the gate.
PRICE_GUARD_PHRASE = "final sales review"
DELIVERY_GUARD_PHRASE = "delivery commitment"
RESTRICTED_GUARD_PHRASE = "binding commitment"


def check_reply_draft(
    reply_draft: dict[str, Any],
    reply_policy: dict[str, bool],
    risk_flags: list[dict[str, str]],
) -> dict[str, Any]:
    body = str(reply_draft.get("body") or "")
    lowered = body.lower()
    rule_ids = {flag["rule_id"] for flag in risk_flags}
    violations: list[dict[str, str]] = []

    currency = CURRENCY_RE.search(body)
    if currency:
        add_violation(
            violations,
            "price_in_customer_body",
            f"Customer-facing body contains a price/currency amount: {currency.group(0).strip()!r}.",
        )

    commitment = COMMITMENT_RE.search(body)
    if commitment:
        add_violation(
            violations,
            "first_person_commitment",
            f"Customer-facing body asserts a commitment: {commitment.group(0).strip()!r}.",
        )

    if reply_policy.get("must_not_commit_final_price") and PRICE_GUARD_PHRASE not in lowered:
        add_violation(
            violations,
            "missing_price_review_guardrail",
            "Policy forbids committing final price but the price-review guardrail is absent.",
        )

    if reply_policy.get("must_not_commit_requested_delivery") and DELIVERY_GUARD_PHRASE not in lowered:
        add_violation(
            violations,
            "missing_delivery_review_guardrail",
            "Policy forbids committing requested delivery but the delivery-review guardrail is absent.",
        )

    if "restricted_claim" in rule_ids and RESTRICTED_GUARD_PHRASE not in lowered:
        add_violation(
            violations,
            "missing_restricted_claim_guardrail",
            "Inquiry demands a guarantee but the binding-commitment review guardrail is absent.",
        )

    return {"ok": not violations, "violations": violations}


def add_violation(violations: list[dict[str, str]], code: str, detail: str) -> None:
    violations.append({"code": code, "detail": detail})
