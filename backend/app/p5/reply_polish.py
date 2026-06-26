from __future__ import annotations

from typing import Any

from backend.app.p4.draft_safety import check_reply_draft
from backend.app.p4.reply_generator import append_policy_guardrails
from backend.app.p5.model_gateway import ModelGateway

# LLM draft polishing — the first, lowest-risk LLM capability. The model only
# rewrites wording; it never invents facts.
#
# The model polishes ONLY the message body (body_main). The deterministic policy
# guardrails (price/delivery/binding-commitment notes) are re-appended by us
# afterwards, so the LLM is never responsible for preserving safety boilerplate
# verbatim — that removes the false rejections where a paraphrased guardrail
# failed a literal presence check.
#
# Single runtime safety check, on the final (polished + guardrails) draft. Its
# job is the negative invariants: the model must not introduce a price or a
# commitment. The deterministic template draft is trusted by construction and is
# regression-guarded separately in the P2 eval harness.
#
# On a safety failure we do NOT immediately give up: we re-call the model with
# the specific violations appended, asking it to fix them (bounded by
# config.max_repair_attempts). The template draft remains the terminal fallback,
# so an unsafe draft can never be surfaced.

POLISH_SYSTEM_PROMPT = (
    "You are a B2B export sales assistant. Rewrite the message below so it reads "
    "naturally and professionally. Keep it concise.\n"
    "Hard rules you must never break:\n"
    "- Do NOT add or imply any price, amount, or currency.\n"
    "- Do NOT promise or confirm any delivery date.\n"
    "- Do NOT guarantee certification, compliance, or any binding commitment.\n"
    "- Keep every clarification question.\n"
    "- Do NOT add closing disclaimers about price review, delivery confirmation, "
    "or binding commitments — those standard notes are appended automatically.\n"
    "- Preserve the meaning; only improve the wording.\n"
    "Output only the rewritten message, with no preamble or explanation."
)


def polish_reply_draft(
    template_draft: dict[str, Any],
    reply_policy: dict[str, bool],
    risk_flags: list[dict[str, str]],
    gateway: ModelGateway,
) -> dict[str, Any]:
    # Polish only the editable message; fall back to the full body if body_main
    # is unavailable (older drafts).
    main_input = template_draft.get("body_main") or template_draft.get("body", "")
    messages = [
        {"role": "system", "content": POLISH_SYSTEM_PROMPT},
        {"role": "user", "content": main_input},
    ]
    attempts: list[dict[str, Any]] = []
    max_calls = 1 + max(0, getattr(gateway.config, "max_repair_attempts", 0))

    for call_index in range(max_calls):
        response = gateway.complete(messages)
        record = call_record(response)

        if not response.ok or not response.text.strip():
            record["safety_ok"] = None
            attempts.append(record)
            # A broken endpoint won't be fixed by re-prompting; stop and fall back.
            break

        polished_main = response.text.strip()
        # Re-append the deterministic guardrails, then check the final draft.
        candidate_body = append_policy_guardrails(polished_main, risk_flags, reply_policy)
        safety = check_reply_draft({"body": candidate_body}, reply_policy, risk_flags)
        record["safety_ok"] = safety["ok"]
        record["violations"] = [violation["code"] for violation in safety["violations"]]
        attempts.append(record)

        if safety["ok"]:
            polished = dict(template_draft)
            polished["body"] = candidate_body
            polished["body_main"] = polished_main
            polished["safety"] = safety
            polished["polish"] = {"applied": True, "reason": None, "attempts": attempts}
            return polished

        # Failed safety: if we still have budget, ask the model to fix it.
        if call_index < max_calls - 1:
            messages = messages + [
                {"role": "assistant", "content": candidate_body},
                {"role": "user", "content": repair_instruction(safety["violations"])},
            ]

    # Budget exhausted or model error: keep the deterministic template draft.
    fallback = dict(template_draft)
    fallback["polish"] = {
        "applied": False,
        "reason": fallback_reason(attempts),
        "attempts": attempts,
    }
    return fallback


def repair_instruction(violations: list[dict[str, str]]) -> str:
    lines = ["Your previous reply violated these mandatory safety rules:"]
    for violation in violations:
        lines.append(f"- {violation['code']}: {violation['detail']}")
    lines.append(
        "Revise the email body to fix ALL of the above. Do not add any price, "
        "delivery commitment, certification guarantee, or binding commitment. "
        "Keep all clarification questions and review notes. "
        "Output only the corrected email body."
    )
    return "\n".join(lines)


def call_record(response) -> dict[str, Any]:
    return {
        "provider": response.provider,
        "model": response.model,
        "latency_ms": response.latency_ms,
        "usage": response.usage,
        "used_fallback": response.used_fallback,
        "ok": response.ok,
        "error": response.error,
    }


def fallback_reason(attempts: list[dict[str, Any]]) -> str:
    if not attempts:
        return "no_model_response"
    last = attempts[-1]
    if not last["ok"]:
        return f"model_error: {last.get('error')}"
    return "failed_safety_gate_after_repair"
