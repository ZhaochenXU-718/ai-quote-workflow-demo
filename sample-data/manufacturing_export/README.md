# Manufacturing Export Demo Data

This dataset is for the manufacturing export inquiry-to-quote demo.

Status: synthetic demo dataset, first version.

## Purpose

The dataset validates the first workflow chain:

```text
inquiry parsing -> product retrieval -> risk checks -> reply draft -> human approval -> export
```

It is designed to test system behavior without using any real customer, supplier, pricing, or company-confidential data.

## Important Boundaries

- All rows marked `synthetic` are mock data.
- Price bands are illustrative and must not be used as market prices.
- The dataset is not intended to produce real quotations.
- The dataset validates workflow feasibility, not real quotation accuracy.
- Real quotation accuracy must be validated later with customer-approved, desensitized data.

## Current Files

```text
sample-data/manufacturing_export/
  README.md
  products/
    products.csv
    product_docs.md
  inquiries/
    synthetic_inquiries.jsonl
  eval/
    gold_answers.jsonl
  rules/
    risk_rules.yaml
  templates/
    email_templates.md

scripts/
  generate_manufacturing_export_data.py
```

## File Roles

| File | Role | Used By |
|---|---|---|
| `products/products.csv` | Product master data for exact matching and structured filtering | Retrieval, product matching, risk checks |
| `products/product_docs.md` | Product knowledge snippets for RAG retrieval | Knowledge retrieval, citation display |
| `inquiries/synthetic_inquiries.jsonl` | Synthetic customer inquiry emails | Demo runtime input |
| `eval/gold_answers.jsonl` | Gold labels for each synthetic inquiry | Evaluation and regression testing |
| `rules/risk_rules.yaml` | Quotation risk rules | Risk checker and reply policy |
| `templates/email_templates.md` | English email templates | Reply draft generation |
| `../../scripts/generate_manufacturing_export_data.py` | Reproducible data generator | Regenerating inquiries and gold labels |

## Dataset Size

Current version:

- 12 synthetic product SKUs.
- 12 product knowledge snippets.
- 10 risk rules.
- 6 email templates.
- 50 synthetic inquiries.
- 50 gold-answer records.

The `inquiry_id` values in `synthetic_inquiries.jsonl` and `gold_answers.jsonl` are aligned:

```text
INQ-SYN-001 ... INQ-SYN-050
```

## Product Data Structure

File: `products/products.csv`

Fields:

| Field | Meaning |
|---|---|
| `product_id` | Internal product ID used for matching |
| `product_name` | Product display name |
| `category` | Product category, such as `ball_valve` or `check_valve` |
| `material` | Main material, such as `SS304`, `SS316`, `WCB`, `brass`, `ductile_iron` |
| `size_range` | Supported size range, such as `DN15-DN50` |
| `pressure_rating` | Supported pressure rating, such as `PN16` |
| `connection_type` | Connection type, such as `threaded`, `flanged`, `wafer`, `lug` |
| `certifications` | Supported certifications, separated by `;` |
| `moq` | Minimum order quantity |
| `standard_lead_time_days` | Standard lead time in days |
| `price_band_usd` | Synthetic price band for demo only |
| `notes` | Product note |
| `source_type` | Data origin, currently `synthetic` |
| `source_url` | Source URL if later derived from public material |

Example:

```csv
product_id,product_name,category,material,size_range,pressure_rating,connection_type,certifications,moq,standard_lead_time_days,price_band_usd,notes,source_type,source_url
SV-BV-100,Stainless Steel Ball Valve,ball_valve,SS304,DN15-DN50,PN16,threaded,CE,100,20,8-18,standard threaded ball valve,synthetic,
```

## Product Knowledge Structure

File: `products/product_docs.md`

Each product has a short knowledge snippet. These snippets are used as the first RAG corpus.

Expected retrieval use:

- Retrieve product facts.
- Show citations in generated draft.
- Support product matching reasons.
- Provide standard lead time, MOQ, pressure rating, connection type, and certification evidence.

## Inquiry Data Structure

File: `inquiries/synthetic_inquiries.jsonl`

Each line is one JSON object representing a synthetic customer email.

Fields:

| Field | Meaning |
|---|---|
| `inquiry_id` | Shared ID used to join with gold answers |
| `synthetic` | Always `true` for this version |
| `language` | Inquiry language, currently `en` |
| `channel` | Input channel, currently `email` |
| `customer_country` | Customer country |
| `subject` | Email subject |
| `body` | Email body to be parsed by the system |

Example:

```json
{
  "inquiry_id": "INQ-SYN-001",
  "synthetic": true,
  "language": "en",
  "channel": "email",
  "customer_country": "Germany",
  "subject": "Inquiry for stainless steel ball valves",
  "body": "Hi,\n\nWe are looking for 500 pcs stainless steel ball valves for a water treatment project in Germany.\n\nRequired specifications: size DN50, CE certification.\n\nPlease quote your best price and confirm whether delivery within 15 days is possible.\n\nBest regards,\n\nPurchasing Team"
}
```

## Gold Answer Structure

File: `eval/gold_answers.jsonl`

Each line is one JSON object representing the expected answer for the corresponding inquiry.

Main sections:

| Field | Meaning |
|---|---|
| `inquiry_id` | Shared ID with `synthetic_inquiries.jsonl` |
| `gold_field_extraction` | Expected parsed business fields |
| `gold_product_match` | Expected candidate products and matching reasons |
| `gold_risk_flags` | Expected risk-rule hits |
| `gold_clarification_questions` | Expected clarification questions |
| `expected_reply_policy` | Expected reply constraints |

`gold_field_extraction.line_items[]` fields:

| Field | Meaning |
|---|---|
| `product_name` | Parsed product request |
| `quantity` | Parsed quantity |
| `size` | Parsed DN size, if provided |
| `material_grade` | Parsed material, if provided |
| `pressure_rating` | Parsed pressure rating, if provided |
| `connection_type` | Parsed connection type, if provided |
| `certification` | Parsed certification, if provided |
| `requested_delivery_days` | Parsed requested delivery time |
| `missing_fields` | Required fields absent from the inquiry |

`expected_reply_policy` fields:

| Field | Meaning |
|---|---|
| `can_generate_reply_draft` | Whether the system may generate a draft |
| `must_not_commit_final_price` | Whether final price commitment is forbidden |
| `must_not_commit_requested_delivery` | Whether requested delivery commitment is forbidden |
| `must_require_human_approval` | Whether human approval is required |

## Risk Rule Structure

File: `rules/risk_rules.yaml`

Each rule has:

| Field | Meaning |
|---|---|
| `id` | Stable risk-rule ID |
| `description` | Human-readable rule definition |
| `severity` | `low`, `medium`, or `high` |
| `action` | Suggested system action |

Current rules cover:

- Missing required specifications.
- Requested delivery shorter than standard lead time.
- Unsupported certification.
- Quantity below MOQ.
- Final price commitment requiring approval.
- Non-standard material.
- Non-standard size.
- Multi-product inquiry.
- Unclear application.
- Unsupported claims.

## Template Structure

File: `templates/email_templates.md`

Current templates:

- Standard Quote Reply.
- Missing Specification Clarification.
- Delivery Confirmation Required.
- Certification Confirmation Required.
- Restricted Commitment Review Required.
- Follow-up Email.

Templates are for draft generation only. The system should still apply risk rules and require human approval before sending.

## Data Generation

Generation script:

```text
scripts/generate_manufacturing_export_data.py
```

Run (from anywhere; paths are anchored to the repo root):

```bash
python3 scripts/generate_manufacturing_export_data.py
```

The generator reuses the same CSV loader as the runtime (`backend/app/data/loaders.py`),
so there is a single CSV parser, not a separate one. It is an independent
codification of the expected gold and must stay in sync with the risk rules in
`backend/app/p1/rule_pipeline.py`; regenerating leaves the committed dataset
byte-identical.

Generated outputs:

```text
sample-data/manufacturing_export/inquiries/synthetic_inquiries.jsonl
sample-data/manufacturing_export/eval/gold_answers.jsonl
```

The generator reads:

```text
sample-data/manufacturing_export/products/products.csv
```

Then creates:

- Synthetic inquiry emails.
- Gold field extraction labels.
- Candidate product matches.
- Risk flags.
- Clarification questions.
- Reply policy expectations.

## Demo Usage

Runtime inputs:

1. Load `products/products.csv`.
2. Load `products/product_docs.md` into the retrieval layer.
3. Load `rules/risk_rules.yaml`.
4. Load `templates/email_templates.md`.
5. Select one line from `inquiries/synthetic_inquiries.jsonl` as the customer email input.

Expected runtime outputs:

1. Parsed fields.
2. Candidate product matches.
3. Retrieved product snippets with citations.
4. Risk flags.
5. Clarification questions.
6. Draft reply.
7. Human approval state.

Evaluation inputs:

1. System output for each inquiry.
2. Matching record from `eval/gold_answers.jsonl`.

Evaluation checks:

- Field extraction accuracy.
- Product candidate match.
- Risk flag detection.
- Clarification question coverage.
- Reply policy compliance.

## Known Limitations

- The default dev set is synthetic and simplified; its gold shares the
  generator's logic, so its 100% scores are a regression baseline only, not
  proof of real-world accuracy.
- Only English inquiries are included in the default set (the holdout adds one
  German case).
- Product data covers 12 SKUs, not the planned 30 SKUs.
- Historical quotation data has not been generated yet.
- Gold labels in the default set are generated by a rule-based script and should
  be manually reviewed before serious evaluation.
- Price bands are illustrative and should not be shown as real market prices.

A hand-written **holdout** generalization set now exists at
`eval/holdout/` (see its `README.md`). Unlike the default set, its gold is
human-written and independent of the generator, so it is expected to score
below the dev set and serves as the honest generalization signal.

## Next Steps

1. Manually review 10-20 `gold_answers.jsonl` records.
2. Expand product master data from 12 SKUs to 30 SKUs.
3. Generate synthetic historical quotes.
4. Grow the hand-written holdout set at `eval/holdout/` (done: first 13 cases).
5. Add more multilingual inquiries (the holdout currently has one German case).
6. Add attachment-style inquiries that reference a product table or spec sheet.
7. Build the first parser/retrieval/risk-check pipeline against this dataset (done: P1-P3).
