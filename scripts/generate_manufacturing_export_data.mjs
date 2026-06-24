import fs from "node:fs";
import path from "node:path";

// Historical data-generation script for the first synthetic dataset.
// TODO: Runtime demo development has moved to Python. If we need to regenerate
// or expand datasets, replace this with a Python fixture generator driven by
// scenario config, not hardcoded JavaScript arrays.

const root = process.cwd();
const dataDir = path.join(root, "sample-data/manufacturing_export");
const productCsvPath = path.join(dataDir, "products/products.csv");
const inquiriesPath = path.join(dataDir, "inquiries/synthetic_inquiries.jsonl");
const goldPath = path.join(dataDir, "eval/gold_answers.jsonl");

function parseCsv(text) {
  const [headerLine, ...lines] = text.trim().split(/\r?\n/);
  const headers = headerLine.split(",");
  return lines.map((line) => {
    const cells = line.split(",");
    return Object.fromEntries(headers.map((header, index) => [header, cells[index] ?? ""]));
  });
}

const products = parseCsv(fs.readFileSync(productCsvPath, "utf8"));
const productById = Object.fromEntries(products.map((product) => [product.product_id, product]));

const candidateGroups = {
  stainless_ball_valve: ["SV-BV-100", "SV-BV-200"],
  butterfly_valve: ["SV-BF-100", "SV-BF-200"],
  check_valve: ["SV-CV-100", "SV-CV-200"],
  gate_valve: ["SV-GV-100", "SV-GV-200"],
  solenoid_valve: ["SV-SV-100", "SV-SV-200"],
  flange: ["SV-FT-100"],
};

const scenarios = [
  ["stainless_ball_valve", "Germany", "water treatment project", 500, "DN50", null, null, null, "CE", 15],
  ["stainless_ball_valve", "United Arab Emirates", "desalination plant", 80, "DN80", "SS316", "PN25", "flanged", "RoHS", 35],
  ["stainless_ball_valve", "Spain", "industrial water line", 40, "DN25", "SS304", "PN16", "threaded", "CE", 25],
  ["stainless_ball_valve", "Mexico", null, 30, null, null, null, null, "CE", 20],
  ["stainless_ball_valve", "Brazil", "chemical dosing skid", 60, "DN150", "SS316", "PN25", "flanged", "CE", 25],
  ["butterfly_valve", "Saudi Arabia", "HVAC project", 120, "DN150", "ductile iron", "PN16", "wafer", "CE", 30],
  ["butterfly_valve", "South Africa", "municipal water pipeline", 25, "DN350", "ductile iron", "PN16", "lug", "WRAS", 20],
  ["butterfly_valve", "India", null, 60, "DN80", null, "PN16", null, "CE", 25],
  ["butterfly_valve", "Thailand", "cooling water system", 20, "DN450", "ductile iron", "PN16", "lug", "CE", 45],
  ["butterfly_valve", "Chile", "water treatment upgrade", 100, "DN100", "ductile iron", "PN16", "wafer", "FDA", 30],
  ["check_valve", "Germany", "oil pipeline maintenance", 35, "DN100", "WCB", "PN16", "flanged", "CE", 28],
  ["check_valve", "France", "compact pump station", 120, "DN40", "SS304", "PN16", "threaded", "RoHS", 18],
  ["check_valve", "United States", null, 20, "DN200", null, null, "flanged", "CE", 20],
  ["check_valve", "Italy", "food-grade process line", 70, "DN80", "SS304", "PN16", "threaded", "FDA", 25],
  ["check_valve", "Vietnam", "water booster system", 10, "DN50", "WCB", "PN16", "flanged", "CE", 35],
  ["gate_valve", "Turkey", "industrial pipeline shutoff", 24, "DN150", "WCB", "PN16", "flanged", "CE", 45],
  ["gate_valve", "Netherlands", "corrosive media pipeline", 25, "DN100", "SS316", "PN25", "flanged", "RoHS", 30],
  ["gate_valve", "Poland", null, 15, "DN80", null, "PN16", "flanged", "CE", 40],
  ["gate_valve", "Egypt", "irrigation pumping station", 12, "DN350", "WCB", "PN16", "flanged", "CE", 35],
  ["gate_valve", "Canada", "industrial plant expansion", 22, "DN50", "SS304", "PN25", "flanged", "CE", 50],
  ["solenoid_valve", "Singapore", "water control cabinet", 300, "DN25", "brass", "PN10", "threaded", "CE", 20],
  ["solenoid_valve", "Malaysia", "food-grade filling line", 90, "DN50", "SS304", "PN16", "threaded", "RoHS", 18],
  ["solenoid_valve", "Indonesia", null, 50, "DN15", null, null, null, "CE", 10],
  ["solenoid_valve", "Australia", "air control system", 150, "DN40", "brass", "PN10", "threaded", "UL", 25],
  ["solenoid_valve", "Philippines", "clean water dosing line", 70, "DN100", "SS304", "PN16", "threaded", "CE", 30],
  ["flange", "Germany", "pipe installation project", 1000, "DN100", "SS304", "PN16", "flanged", "CE", 20],
  ["flange", "Spain", "stainless steel piping project", 150, "DN150", "SS316", "PN16", "flanged", "CE", 15],
  ["flange", "Mexico", null, 80, null, "SS304", null, "flanged", "CE", 12],
  ["flange", "Saudi Arabia", "pipeline maintenance", 220, "DN250", "SS304", "PN16", "flanged", "CE", 18],
  ["flange", "UAE", "water treatment skid", 50, "DN50", "SS304", "PN16", "flanged", "RoHS", 10],
  ["stainless_ball_valve", "Colombia", "water treatment project", 200, "DN25", "SS304", "PN16", "threaded", "CE", 22],
  ["stainless_ball_valve", "Morocco", "chemical plant utility line", 55, "DN100", "SS316", "PN25", "flanged", "CE", 20],
  ["butterfly_valve", "Peru", "mining water pipeline", 75, "DN200", "ductile iron", "PN16", null, "CE", 25],
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
  ["stainless_ball_valve", "France", null, 10, null, null, null, null, null, null],
  ["butterfly_valve", "Germany", null, 10, null, null, null, null, null, null],
  ["check_valve", "Italy", null, 10, null, null, null, null, null, null],
  ["gate_valve", "Netherlands", null, 10, null, null, null, null, null, null],
  ["solenoid_valve", "Poland", null, 10, null, null, null, null, null, null],
];

function productPhrase(group) {
  return {
    stainless_ball_valve: "stainless steel ball valves",
    butterfly_valve: "butterfly valves",
    check_valve: "check valves",
    gate_valve: "gate valves",
    solenoid_valve: "solenoid valves",
    flange: "stainless steel flanges",
  }[group];
}

function parseDn(value) {
  const match = String(value || "").match(/DN(\d+)/i);
  return match ? Number(match[1]) : null;
}

function sizeInRange(size, range) {
  const requested = parseDn(size);
  const [min, max] = String(range || "").split("-").map(parseDn);
  if (!requested || !min || !max) return true;
  return requested >= min && requested <= max;
}

function splitCerts(value) {
  return String(value || "")
    .split(";")
    .map((cert) => cert.trim())
    .filter(Boolean);
}

function candidateProducts(group, material, connection) {
  const ids = candidateGroups[group];
  let candidates = ids.map((id) => productById[id]).filter(Boolean);
  if (material) {
    const materialMatches = candidates.filter((product) => product.material.toLowerCase() === material.toLowerCase());
    if (materialMatches.length) candidates = materialMatches;
  }
  if (connection) {
    const connectionMatches = candidates.filter((product) => product.connection_type.toLowerCase() === connection.toLowerCase());
    if (connectionMatches.length) candidates = connectionMatches;
  }
  return candidates;
}

function missingFields({ size, material, pressure, connection }) {
  const missing = [];
  if (!size) missing.push("size");
  if (!material) missing.push("material grade");
  if (!pressure) missing.push("pressure rating");
  if (!connection) missing.push("connection type");
  return missing;
}

function riskFlags(scenario, candidates, missing) {
  const [group, , application, quantity, size, material, pressure, connection, certification, deliveryDays, extra] = scenario;
  const flags = [];
  if (missing.length) {
    flags.push({
      rule_id: "missing_required_specs",
      severity: "high",
      reason: `Missing required quotation fields: ${missing.join(", ")}.`,
    });
  }
  if (!application) {
    flags.push({
      rule_id: "unclear_application",
      severity: "medium",
      reason: "Application or operating environment is not provided.",
    });
  }
  if (deliveryDays !== null && candidates.some((product) => Number(deliveryDays) < Number(product.standard_lead_time_days))) {
    flags.push({
      rule_id: "delivery_shorter_than_standard",
      severity: "high",
      reason: "Requested delivery time is shorter than at least one matched product's standard lead time.",
    });
  }
  if (certification && candidates.every((product) => !splitCerts(product.certifications).includes(certification))) {
    flags.push({
      rule_id: "certification_not_supported",
      severity: "high",
      reason: `Requested certification ${certification} is not listed for the matched product candidates.`,
    });
  }
  if (candidates.some((product) => Number(quantity) < Number(product.moq))) {
    flags.push({
      rule_id: "quantity_below_moq",
      severity: "medium",
      reason: "Requested quantity is below MOQ for at least one matched product candidate.",
    });
  }
  if (material && candidates.every((product) => product.material.toLowerCase() !== material.toLowerCase())) {
    flags.push({
      rule_id: "non_standard_material",
      severity: "medium",
      reason: `Requested material ${material} is outside matched product candidate materials.`,
    });
  }
  if (size && candidates.every((product) => !sizeInRange(size, product.size_range))) {
    flags.push({
      rule_id: "non_standard_size",
      severity: "medium",
      reason: `Requested size ${size} is outside matched product candidate size ranges.`,
    });
  }
  if (extra && /also|alternative/i.test(extra)) {
    flags.push({
      rule_id: "multi_product_inquiry",
      severity: "low",
      reason: "Inquiry includes additional product or alternative product request.",
    });
  }
  flags.push({
    rule_id: "price_commitment_required_approval",
    severity: "high",
    reason: "AI-generated reply must not commit final price without human approval.",
  });
  return flags;
}

function buildBody(scenario) {
  const [group, country, application, quantity, size, material, pressure, connection, certification, deliveryDays, extra] = scenario;
  const parts = [
    "Hi,",
    `We are looking for ${quantity} pcs ${productPhrase(group)}${application ? ` for a ${application} in ${country}` : ` for a project in ${country}`}.`,
  ];
  const specs = [];
  if (size) specs.push(`size ${size}`);
  if (material) specs.push(`material ${material}`);
  if (pressure) specs.push(`pressure rating ${pressure}`);
  if (connection) specs.push(`${connection} connection`);
  if (certification) specs.push(`${certification} certification`);
  if (specs.length) parts.push(`Required specifications: ${specs.join(", ")}.`);
  if (deliveryDays !== null) parts.push(`Please quote your best price and confirm whether delivery within ${deliveryDays} days is possible.`);
  else parts.push("Please quote your best price and let us know what information you need from our side.");
  if (extra) parts.push(extra);
  parts.push("Best regards,", "Purchasing Team");
  return parts.join("\n\n");
}

function clarificationQuestions(missing, deliveryDays, candidates) {
  const questions = [];
  for (const field of missing) {
    if (field === "size") questions.push("Please confirm the required valve size, for example DN50.");
    if (field === "material grade") questions.push("Please confirm the required material grade, such as SS304, SS316, WCB, brass, or ductile iron.");
    if (field === "pressure rating") questions.push("Please confirm the required pressure rating, such as PN10, PN16, or PN25.");
    if (field === "connection type") questions.push("Please confirm the required connection type, such as threaded, flanged, wafer, or lug.");
  }
  if (deliveryDays !== null && candidates.some((product) => Number(deliveryDays) < Number(product.standard_lead_time_days))) {
    questions.push(`Please confirm whether the requested ${deliveryDays}-day delivery schedule is mandatory or flexible.`);
  }
  return questions;
}

const inquiries = [];
const goldAnswers = [];

scenarios.forEach((scenario, index) => {
  const [group, country, application, quantity, size, material, pressure, connection, certification, deliveryDays] = scenario;
  const inquiryId = `INQ-SYN-${String(index + 1).padStart(3, "0")}`;
  const candidates = candidateProducts(group, material, connection);
  const missing = missingFields({ size, material, pressure, connection });
  const flags = riskFlags(scenario, candidates, missing);
  const shouldNotSelect = missing.length > 0 || flags.some((flag) => flag.severity === "high" && flag.rule_id !== "price_commitment_required_approval");

  inquiries.push({
    inquiry_id: inquiryId,
    synthetic: true,
    language: "en",
    channel: "email",
    customer_country: country,
    subject: `Inquiry for ${productPhrase(group)}`,
    body: buildBody(scenario),
  });

  goldAnswers.push({
    inquiry_id: inquiryId,
    gold_field_extraction: {
      request_type: "quote_request",
      customer_country: country,
      application,
      line_items: [
        {
          product_name: productPhrase(group).replace(/s$/, ""),
          quantity,
          size,
          material_grade: material,
          pressure_rating: pressure,
          connection_type: connection,
          certification,
          requested_delivery_days: deliveryDays,
          missing_fields: missing,
        },
      ],
    },
    gold_product_match: {
      primary_candidates: candidates.map((product) => ({
        product_id: product.product_id,
        reason: `${product.product_name}, material ${product.material}, size range ${product.size_range}, ${product.pressure_rating}, ${product.connection_type} connection, certifications ${product.certifications}, standard lead time ${product.standard_lead_time_days} days.`,
      })),
      should_not_select_final_product_without_clarification: shouldNotSelect,
    },
    gold_risk_flags: flags,
    gold_clarification_questions: clarificationQuestions(missing, deliveryDays, candidates),
    expected_reply_policy: {
      can_generate_reply_draft: true,
      must_not_commit_final_price: true,
      must_not_commit_requested_delivery: flags.some((flag) => flag.rule_id === "delivery_shorter_than_standard"),
      must_require_human_approval: true,
    },
  });
});

fs.mkdirSync(path.dirname(inquiriesPath), { recursive: true });
fs.mkdirSync(path.dirname(goldPath), { recursive: true });
fs.writeFileSync(inquiriesPath, inquiries.map((item) => JSON.stringify(item)).join("\n") + "\n");
fs.writeFileSync(goldPath, goldAnswers.map((item) => JSON.stringify(item)).join("\n") + "\n");

console.log(`Generated ${inquiries.length} inquiries -> ${path.relative(root, inquiriesPath)}`);
console.log(`Generated ${goldAnswers.length} gold answers -> ${path.relative(root, goldPath)}`);
