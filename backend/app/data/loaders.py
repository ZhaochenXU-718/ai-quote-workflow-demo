from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Demo data is intentionally stored as flat files so the first pipeline can run
# without databases or external services.
DATA_ROOT = Path("sample-data/manufacturing_export")

DATA_PATHS = {
    "products": Path("products/products.csv"),
    "product_docs": Path("products/product_docs.md"),
    "risk_rules": Path("rules/risk_rules.yaml"),
    "inquiries": Path("inquiries/synthetic_inquiries.jsonl"),
    "gold_answers": Path("eval/gold_answers.jsonl"),
    "email_templates": Path("templates/email_templates.md"),
}


@dataclass(frozen=True)
class DemoData:
    paths: dict[str, Path]
    products: list[dict[str, str]]
    product_docs: dict[str, str]
    risk_rules: list[dict[str, str]]
    inquiries: list[dict[str, Any]]
    gold_answers: list[dict[str, Any]]
    email_templates: list[str]


def resolve_data_path(root_dir: Path, relative_path: Path) -> Path:
    return root_dir / DATA_ROOT / relative_path


def read_text(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"Missing required file: {file_path}")
    return file_path.read_text(encoding="utf-8")


def parse_csv(text: str) -> list[dict[str, str]]:
    rows = list(csv.DictReader(text.splitlines()))
    return [dict(row) for row in rows]


def parse_jsonl(text: str, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSONL in {label} at line {index}: {error}") from error
    return rows


def parse_risk_rules_yaml(text: str) -> list[dict[str, str]]:
    # TODO: Replace this tiny parser with a typed config loader once we allow
    # third-party dependencies. It only supports the current risk_rules.yaml
    # shape and should not be treated as a general YAML implementation.
    rules: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        id_match = re.match(r"^\s*-\s+id:\s*(.+)$", line)
        if id_match:
            current = {"id": strip_yaml_value(id_match.group(1))}
            rules.append(current)
            continue

        field_match = re.match(r"^\s{4}([A-Za-z_]+):\s*(.*)$", line)
        if field_match and current is not None:
            current[field_match.group(1)] = strip_yaml_value(field_match.group(2))

    return rules


def strip_yaml_value(value: str) -> str:
    trimmed = value.strip()
    if len(trimmed) >= 2 and trimmed[0] == trimmed[-1] and trimmed[0] in {"'", '"'}:
        return trimmed[1:-1]
    return trimmed


def parse_product_docs(text: str) -> dict[str, str]:
    # TODO: Product docs are split by "## PRODUCT_ID" only for the P3 MVP.
    # A real knowledge layer should store chunk metadata, version, source
    # ownership, and product/catalog links explicitly.
    docs: dict[str, str] = {}
    sections = re.split(r"\n(?=##\s+)", text)
    for section in sections:
        match = re.search(r"^##\s+([A-Z0-9-]+)", section, re.MULTILINE)
        if match:
            docs[match.group(1)] = section.strip()
    return docs


def parse_email_template_names(text: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"^##\s+(.+)$", text, re.MULTILINE)]


def load_demo_data(root_dir: Path | None = None) -> DemoData:
    root = root_dir or Path.cwd()
    paths = {key: resolve_data_path(root, value) for key, value in DATA_PATHS.items()}

    products = parse_csv(read_text(paths["products"]))
    product_docs = parse_product_docs(read_text(paths["product_docs"]))
    risk_rules = parse_risk_rules_yaml(read_text(paths["risk_rules"]))
    inquiries = parse_jsonl(read_text(paths["inquiries"]), str(DATA_PATHS["inquiries"]))
    gold_answers = parse_jsonl(read_text(paths["gold_answers"]), str(DATA_PATHS["gold_answers"]))
    email_templates = parse_email_template_names(read_text(paths["email_templates"]))

    return DemoData(
        paths=paths,
        products=products,
        product_docs=product_docs,
        risk_rules=risk_rules,
        inquiries=inquiries,
        gold_answers=gold_answers,
        email_templates=email_templates,
    )
