from __future__ import annotations

import argparse
import json
import sys

from backend.app.p0.validate_data import validate_demo_data
from backend.app.p1.rule_pipeline import run_inquiry_pipeline
from backend.app.p2.evaluate import evaluate_all
from backend.app.p5.model_gateway import build_gateway


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manufacturing export demo CLI")
    subparsers = parser.add_subparsers(dest="command")
    holdout_help = "Use the hand-written holdout dataset instead of the synthetic default"
    for name, help_text in (
        ("p0", "Validate demo data contracts and print statistics"),
        ("validate-data", "Alias for p0"),
    ):
        p0_parser = subparsers.add_parser(name, help=help_text)
        p0_parser.add_argument("--holdout", action="store_true", help=holdout_help)
    run_parser = subparsers.add_parser("run", help="Run rule-based P1 pipeline for one inquiry")
    run_parser.add_argument("inquiry_id", help="Inquiry ID, for example INQ-SYN-001")
    run_parser.add_argument("--holdout", action="store_true", help=holdout_help)
    run_parser.add_argument(
        "--llm",
        action="store_true",
        help="Enable P5 LLM draft polishing (provider via LLM_PROVIDER env, default mock)",
    )
    eval_parser = subparsers.add_parser("eval", help="Evaluate P1 pipeline against gold answers")
    eval_parser.add_argument("--holdout", action="store_true", help=holdout_help)
    eval_parser.add_argument(
        "--details",
        action="store_true",
        help="Print full per-inquiry evaluation JSON",
    )
    eval_parser.add_argument(
        "--max-failures",
        type=int,
        default=5,
        help="Maximum failed inquiry IDs to print in summary mode",
    )

    args = parser.parse_args(argv)

    if args.command in {"p0", "validate-data"}:
        summary = validate_demo_data(dataset=dataset_from(args))
        print_summary(summary)
        return 0 if summary["ok"] else 1

    if args.command == "run":
        try:
            gateway = build_gateway() if args.llm else None
            result = run_inquiry_pipeline(
                args.inquiry_id, dataset=dataset_from(args), gateway=gateway
            )
        except ValueError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "eval":
        report = evaluate_all(dataset=dataset_from(args))
        if args.details:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print_eval_summary(report, max_failures=args.max_failures)
        return 0 if report["summary"]["failed"] == 0 else 1

    parser.print_help()
    return 1


def dataset_from(args: argparse.Namespace) -> str:
    return "holdout" if getattr(args, "holdout", False) else "default"


def print_summary(summary: dict) -> None:
    print("P0 Data Contract Validation")
    print(f"dataset: {summary.get('dataset', 'default')}")
    print()

    print("Files:")
    for label, relative_path in summary["files"].items():
        print(f"  {label}: {relative_path}")
    print()

    print("Counts:")
    for label, count in summary["counts"].items():
        print(f"  {label}: {count}")
    print()

    print("ID Alignment:")
    alignment = summary["id_alignment"]
    print(f"  inquiries_and_gold_answers_match: {alignment['inquiries_and_gold_answers_match']}")
    print(f"  first_inquiry_id: {alignment['first_inquiry_id']}")
    print(f"  last_inquiry_id: {alignment['last_inquiry_id']}")

    if summary["warnings"]:
        print()
        print("Warnings:")
        for warning in summary["warnings"]:
            print(f"  - {warning}")

    if summary["errors"]:
        print()
        print("Errors:")
        for error in summary["errors"]:
            print(f"  - {error}")

    print()
    print(f"Result: {'OK' if summary['ok'] else 'FAILED'}")


def print_eval_summary(report: dict, max_failures: int) -> None:
    summary = report["summary"]
    print("P2 Evaluation Summary")
    print(f"dataset: {report.get('dataset', 'default')}")
    print()
    for key, value in summary.items():
        print(f"  {key}: {value}")

    failures = [result for result in report["results"] if not result["passed"]]
    if failures:
        print()
        print(f"Failures (showing up to {max_failures}):")
        for result in failures[:max_failures]:
            reasons = failure_reasons(result)
            print(f"  - {result['inquiry_id']}: {', '.join(reasons)}")

    print()
    print(f"Result: {'OK' if not failures else 'FAILED'}")


def failure_reasons(result: dict) -> list[str]:
    reasons = []
    if result["field_check"]["accuracy"] != 1:
        fields = [failure["field"] for failure in result["field_check"]["failures"]]
        reasons.append(f"field mismatches={fields}")

    product_check = result["product_candidate_check"]
    if not product_check["all_gold_present"]:
        reasons.append(f"product candidates missing={product_check['false_negatives']}")

    # Risk flags and missing fields gate on both misses and false positives, so
    # report each side separately to make the failure actionable.
    risk_check = result["risk_flag_check"]
    if not risk_check["all_gold_present"]:
        reasons.append(f"risk flags missing={risk_check['false_negatives']}")
    if risk_check["false_positives"]:
        reasons.append(f"risk false positives={risk_check['false_positives']}")

    missing_check = result["missing_field_check"]
    if not missing_check["all_gold_present"]:
        reasons.append(f"missing fields not detected={missing_check['false_negatives']}")
    if missing_check["false_positives"]:
        reasons.append(f"missing-field false positives={missing_check['false_positives']}")

    draft_check = result["draft_safety_check"]
    if not draft_check["ok"]:
        codes = [violation["code"] for violation in draft_check["violations"]]
        reasons.append(f"draft safety violations={codes}")
    return reasons


if __name__ == "__main__":
    sys.exit(main())
