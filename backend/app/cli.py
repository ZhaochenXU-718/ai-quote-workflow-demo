from __future__ import annotations

import argparse
import json
import sys

from backend.app.p0.validate_data import validate_demo_data
from backend.app.p1.rule_pipeline import run_inquiry_pipeline
from backend.app.p2.evaluate import evaluate_all


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manufacturing export demo CLI")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("p0", help="Validate demo data contracts and print statistics")
    subparsers.add_parser("validate-data", help="Alias for p0")
    run_parser = subparsers.add_parser("run", help="Run rule-based P1 pipeline for one inquiry")
    run_parser.add_argument("inquiry_id", help="Inquiry ID, for example INQ-SYN-001")
    eval_parser = subparsers.add_parser("eval", help="Evaluate P1 pipeline against gold answers")
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
        summary = validate_demo_data()
        print_summary(summary)
        return 0 if summary["ok"] else 1

    if args.command == "run":
        try:
            result = run_inquiry_pipeline(args.inquiry_id)
        except ValueError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "eval":
        report = evaluate_all()
        if args.details:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print_eval_summary(report, max_failures=args.max_failures)
        return 0 if report["summary"]["failed"] == 0 else 1

    parser.print_help()
    return 1


def print_summary(summary: dict) -> None:
    print("P0 Data Contract Validation")
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
    if not result["product_candidate_check"]["all_gold_present"]:
        reasons.append("product candidates missing")
    if not result["risk_flag_check"]["all_gold_present"]:
        reasons.append("risk flags missing")
    if not result["missing_field_check"]["all_gold_present"]:
        reasons.append("missing fields not fully detected")
    return reasons


if __name__ == "__main__":
    sys.exit(main())
