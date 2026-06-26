# Demo 构建计划

日期：2026-06-23

目标：逐步构建“制造业出口询盘-报价”Demo，先完成一条可评测的后端流水线，再做 RAG、LLM 和 Web 工作台。

## 总体原则

先做能跑、能评测、能解释的系统骨架，再做界面和模型增强。

代码注释原则：

- 不做逐行解释，只在业务边界、临时实现、风险控制和后续替换点处写必要注释。
- 当前为了 Demo 快速验证而硬编码、简化或不完全符合最终预期的地方，需要用 `TODO` 标明后续演进方向。
- 后续新增代码也沿用这个原则，优先让模块职责、数据边界和替换路径在代码里可读。

不一开始做：

- 漂亮但无业务闭环的 UI。
- 复杂 RAG。
- 完全自主 Agent。
- 真实 CRM/ERP 集成。
- 登录、多租户、复杂权限。
- 自动价格决策。

第一阶段重点证明：

```text
数据能读 -> 流程能跑 -> 风险能控 -> 输出能评测
```

## P0：数据与契约校验

状态：已完成，已用 Python 重写。

目标：确认 Demo 的输入、知识、规则和标准答案稳定可用。

需要完成：

1. 读取 `sample-data/manufacturing_export/products/products.csv`。
2. 读取 `sample-data/manufacturing_export/products/product_docs.md`。
3. 读取 `sample-data/manufacturing_export/rules/risk_rules.yaml`。
4. 读取 `sample-data/manufacturing_export/inquiries/synthetic_inquiries.jsonl`。
5. 读取 `sample-data/manufacturing_export/eval/gold_answers.jsonl`。
6. 检查 `inquiry_id` 是否一一对应。
7. 输出数据统计。

验收标准：

- 所有文件可解析。
- 询盘和标准答案 ID 完全对齐。
- 能输出产品数量、询盘数量、标准答案数量、规则数量。

实现文件：

- `backend/app/cli.py`
- `backend/app/data/loaders.py`
- `backend/app/p0/validate_data.py`

运行命令：

```bash
python3 -m backend.app.cli p0
```

当前校验结果：

```text
products: 12
product_docs: 12
risk_rules: 10
inquiries: 50
gold_answers: 50
email_templates: 6
inquiries_and_gold_answers_match: True
Result: OK
```

## P1：规则版最小流水线

状态：已完成。

目标：不用 LLM，先做确定性 baseline，定义系统骨架。

流程：

```text
inquiry email
-> field extraction
-> product candidate matching
-> risk rule detection
-> clarification question generation
-> result JSON
```

需要完成：

1. 从 email body 中抽取产品、数量、国家、尺寸、材质、压力等级、连接方式、认证、交期。
2. 根据产品词和规格匹配候选产品。
3. 根据风险规则识别缺字段、短交期、认证不支持、低于 MOQ、非标规格等问题。
4. 生成澄清问题。
5. 输出结构化 JSON。

验收标准：

- 输入一个 `inquiry_id`，能输出解析结果。
- 输出包含字段抽取、候选产品、风险标记、澄清问题。
- 不依赖模型 API。

实现文件：

- `backend/app/cli.py`
- `backend/app/p1/rule_pipeline.py`

运行命令：

```bash
python3 -m backend.app.cli run INQ-SYN-001
```

当前能力：

- 抽取产品、数量、国家、应用、尺寸、材质、压力等级、连接方式、认证、交期。
- 根据产品类型、材质、连接方式匹配候选产品。
- 命中缺字段、短交期、认证不支持、低于 MOQ、非标材质、非标尺寸、多产品询盘、过度承诺（restricted_claim，识别客户索要 guarantee/legally binding 等承诺）、价格承诺审批等风险规则（risk_rules.yaml 里 10 条规则现已全部为活规则，无死规则）。
- 生成澄清问题。
- 输出结构化 JSON。

当前限制：

- 依赖固定关键词和正则，只适合当前合成数据和少量模板句式。
- 产品识别依赖 `PRODUCT_GROUPS`，无法覆盖真实客户的同义词、错拼、缩写、型号表达和多语言表达。
- 字段抽取对句式很敏感，例如应用场景目前主要依赖 `for a/an ... in {country}` 这类模式。
- 多产品询盘只能粗略识别，尚不能稳定拆分多个 line items。
- 非标需求、附件表格、邮件线程、报价历史上下文、隐含需求都无法可靠处理。
- 规则匹配无法理解复杂语义，只能作为 baseline、兜底和可解释约束。

替换路径：

- P2 先用评测脚手架量化这些规则的失败类型和准确率，避免只凭主观感觉判断。
- P3 会引入检索和引用，让产品知识匹配不只依赖硬编码候选表。
- P5 会通过模型网关引入 LLM/结构化抽取能力，逐步替换当前正则式自然语言抽取。
- 后续真实 POC 阶段需要用客户脱敏样本重建字段 Schema、行业词典、抽取 prompt、评测集和人工审批规则。
- 即使引入 LLM，风险规则仍应保留为确定性校验、审批约束和安全兜底。

## P2：评测脚手架

状态：已完成。

目标：每次改代码都能知道系统有没有变好。

需要完成：

1. 读取系统输出和 `gold_answers.jsonl`。
2. 比较字段抽取结果。
3. 比较候选产品是否包含 gold candidate。
4. 比较风险规则是否命中。
5. 比较缺失字段是否识别。
6. 为每条询盘输出评测结果。
7. 输出整体指标。

建议指标：

| 指标 | 说明 |
|---|---|
| field_accuracy | 核心字段抽取准确率 |
| product_candidate_hit_rate | 候选产品命中率 |
| product_candidate_precision / recall / f1 | 候选产品精确率/召回率/F1 |
| risk_flag_precision / recall / f1 | 风险规则精确率/召回率/F1 |
| risk_false_positive_inquiries | 出现风险误报的询盘数 |
| missing_field_precision / recall / f1 | 缺失字段精确率/召回率/F1 |
| missing_field_false_positive_inquiries | 出现缺失字段误报的询盘数 |
| pass_rate | 综合通过率 |

pass 判定策略：

- 字段抽取必须完全正确。
- 风险规则、缺失字段必须精确匹配（既不漏报也不误报），因为这两类误报对应“狼来了”和幻觉澄清问题，是高风险输出。
- 候选产品只按召回率把关：检索阶段允许多返回候选交人工筛选，因此只报告其 precision/F1，不据此判失败。

验收标准：

- 能对 50 条询盘跑批量评测。
- 能输出整体指标和失败案例。

实现文件：

- `backend/app/cli.py`
- `backend/app/p2/evaluate.py`

运行命令：

```bash
python3 -m backend.app.cli eval
python3 -m backend.app.cli eval --details
```

当前指标：

```text
total_inquiries: 50
passed: 50
failed: 0
pass_rate: 1.0
field_accuracy: 1.0
product_candidate_hit_rate: 1.0
product_candidate_precision: 1.0
product_candidate_recall: 1.0
product_candidate_f1: 1.0
risk_flag_precision: 1.0
risk_flag_recall: 1.0
risk_flag_f1: 1.0
risk_false_positive_inquiries: 0
missing_field_precision: 1.0
missing_field_recall: 1.0
missing_field_f1: 1.0
missing_field_false_positive_inquiries: 0
```

precision 全为 1.0 说明 P1 pipeline 与 generator 的输出是精确相等（不只是 gold ⊆ predicted 的超集），因此加入误报门槛后 pass_rate 仍为 1.0。

当前边界：

- 这组满分指标只说明 P1 pipeline 与当前合成数据/标准答案一致，适合作为工程回归基线。
- 因为合成数据和 gold labels 都来自同一套规则体系，所以该指标不能证明系统能处理真实客户询盘。
- 评测现在同时度量 precision/recall/F1 并把误报纳入 pass 判定：之后替换正则抽取、加入 RAG/LLM 时，过度命中（误报、幻觉缺失字段）会直接判失败，而不再被只看召回的旧逻辑掩盖。
- 但 precision 指标仍受同源数据局限：它能挡住“相对当前 gold 的回归”，不能证明对真实询盘的精确率。仍需人工改写样本、扰动样本、真实脱敏样本评估泛化能力（这由下面的 holdout 评测集承担）。

### P2 补充：手写 holdout 评测集

状态：已完成。

目标：用一套**脱离 generator、人工撰写 gold** 的询盘，度量系统的泛化能力，打破“自证”闭环。

设计：

- 数据位置：`sample-data/manufacturing_export/eval/holdout/`（`inquiries.jsonl` + `gold_answers.jsonl` + `README.md`）。
- 共用同一套产品/规则/文档知识库，只替换询盘+gold；通过 `load_demo_data(dataset="holdout")` 切换。
- 17 条询盘，每条针对 P1 正则 baseline 的一个已知弱点：单位不是 `pcs`、尺寸用英寸、交期用“three weeks”、产品缩写（SS/S\\S）、引用历史串扰、`and` 连接的多产品、`316L` 材质表达、应用语句不在模板句式内、`DN 50` 带空格，以及德/西/法/阿四种多语言询盘；其中 2 条预期通过——1 条“接近模板”的对照样本，1 条英文“要求 guarantee”的样本（用于正向验证 `restricted_claim` 护栏能正确触发）。
- gold 是人工真值，**不允许为了让 baseline 通过而反向调参**（那会重新引入过拟合）。

运行命令：

```bash
python3 -m backend.app.cli p0 --holdout
python3 -m backend.app.cli eval --holdout
python3 -m backend.app.cli run INQ-HOLD-001 --holdout
```

当前 baseline 结果（与 default 满分形成对照）：

```text
total_inquiries: 17
passed: 2            (对照样本 INQ-HOLD-011 + restricted_claim 正向样本 INQ-HOLD-017)
pass_rate: 0.1176
field_accuracy: 0.8235
product_candidate_precision: 0.6667  recall: 0.5556  f1: 0.6061
risk_flag_precision: 0.6047  recall: 0.8387  f1: 0.7027  (12 条出现误报)
missing_field_precision: 0.4167  recall: 1.0  f1: 0.5883  (7 条出现误报)
```

说明：

- default=1.0 与 holdout≈0.12 的落差，就是当前系统真实泛化能力的诚实度量。
- holdout 是诊断集，不是回归门槛：`eval --holdout` 在有失败时退出码非 0 属于预期；回归门槛仍是 default `eval`（必须保持全绿）。
- 后续 P3 检索增强、P5 引入 LLM 后应重跑 holdout 看趋势；真实 POC 阶段再用客户脱敏样本替换/扩充这套 holdout。

## P3：证据检索 / 引用 MVP

状态：已完成。

目标：先实现轻量证据检索和引用，不急着上向量库。

背景说明：

- P1 当前已经做了一种非常简陋的候选检索：`PRODUCT_GROUPS + products.csv filter`。
- P1 的候选检索用于回答“可能匹配哪些产品”。
- P3 的证据检索用于回答“为什么这些产品是候选，依据来自哪份资料”。
- 因此 P3 不是从零开始做所有检索，而是先补齐候选产品背后的引用证据。

P3 会对 P1 做轻度重构，但不改变现有 CLI 输出主结构和评测入口：

```text
parser
-> candidate_retriever
-> evidence_retriever
-> risk_checker
-> question_generator
```

重构边界：

- 保留当前正则版字段抽取，后续 P5 再替换。
- 将 `match_products` / `PRODUCT_GROUPS` 的职责抽成 `candidate_retriever`。
- 新增 `evidence_retriever`，根据候选产品和询盘上下文返回引用资料。
- 保留风险规则、澄清问题和回复策略逻辑。
- 保持 P2 评测命令继续可用。

第一版证据检索方式：

- 根据候选产品 ID 检索 `product_docs.md` 对应片段。
- 使用询盘关键词补充检索 `product_docs.md`。
- 返回引用片段。

暂不做：

- embedding。
- 向量库。
- rerank。
- 大规模知识库。

需要完成：

1. 把 `product_docs.md` 按产品切成片段。
2. 将 P1 的候选产品匹配抽成候选检索模块。
3. 根据候选产品 ID 找到对应知识片段。
4. 根据询盘关键词补充检索。
5. 在 pipeline 输出中新增 `evidence` / `citations`。
6. 输出引用来源、引用文本和匹配原因。

验收标准：

- 每个候选产品能返回对应产品知识片段。
- `run INQ-SYN-001` 输出中包含 `evidence.citations`。
- P0、P1、P2 现有命令仍然正常。
- P2 指标不因重构下降。
- 后续 P4 回复草稿可引用这些片段。

实现文件：

- `backend/app/p1/candidate_retriever.py`
- `backend/app/p1/rule_pipeline.py`
- `backend/app/p3/evidence_retriever.py`

运行命令：

```bash
python3 -m backend.app.cli run INQ-SYN-001
python3 -m backend.app.cli eval
```

当前能力：

- 已将 P1 的候选产品匹配拆成 `candidate_retriever`。
- 已新增 `evidence_retriever`。
- Pipeline 输出中新增 `evidence.retrieval_mode` 和 `evidence.citations`。
- 候选产品文档通过 `matched_by=["candidate_product"]` 返回。
- 询盘关键词命中的补充文档通过 `matched_by=["keyword"]` 返回。
- citation 包含 `source_id`、`source`、`text`、`matched_by`、`matched_terms` 和 `score`。

当前验证结果：

```text
P0: OK
P1 run INQ-SYN-001: 输出包含 evidence.citations
P2 eval: pass_rate 1.0，指标未回退
```

当前边界：

- 关键词补充检索是简单字符串匹配，可能返回相似但不是最终候选的产品资料。
- 后续 P4 生成回复时，应优先使用 `matched_by=["candidate_product"]` 的 citation。
- 当前证据检索不负责决定最终产品，只负责提供可审查的资料来源。

与向量库的区别：

- 当前 P3 是 ID/关键词驱动的轻量证据检索，不需要 embedding、向量库或 rerank。
- 向量库适合未来文档规模变大、查询语义更复杂、需要跨文档相似检索时再引入。
- 未来更完整的检索层应演进为：结构化过滤 + 关键词检索 + 向量检索 + rerank。

## P4：模板版回复草稿生成

状态：已完成。

目标：先用模板生成可控草稿，再考虑 LLM 润色。

流程：

```text
matched product + missing fields + risk flags
-> select email template
-> fill template
-> reply draft
```

需要完成：

1. 根据风险选择模板。
2. 填充候选产品、缺失字段、澄清问题。
3. 明确禁止承诺最终价格。
4. 明确禁止承诺未经确认的交期。
5. 输出 reply draft。

验收标准：

- 至少能生成标准回复、缺参数回复、交期需确认回复、认证需确认回复。
- 回复中不出现最终报价承诺。
- 回复中不承诺高风险交期。

实现文件：

- `backend/app/p4/reply_generator.py`
- `backend/app/p1/rule_pipeline.py`
- `backend/app/data/loaders.py`
- `sample-data/manufacturing_export/templates/email_templates.md`

当前能力：

- Pipeline 输出中新增 `reply_draft`。
- `reply_draft.subject` / `reply_draft.body` 是客户邮件草稿。
- `reply_draft.supporting_citations` 优先使用 `matched_by=["candidate_product"]` 的 citation，避免把关键词补充资料误当成最终候选。
- `reply_draft.blocked_commitments` 明确列出不能承诺的事项，例如 `final_price`、`requested_delivery`、`certification_confirmation`、`guarantee_or_binding_commitment`。
- `reply_draft.safety_notes` 给内部人工审批使用，不混入客户邮件正文。
- 客户正文只用产品描述（名称+规格），不暴露内部 SKU id；`product_id` 仅保留在内部 `supporting_citations` 里。
- default 样本可触发 5 类模板：标准回复、缺参数回复、交期确认回复、认证确认回复、过度承诺审查回复（restricted_claim）。
- 新增确定性「草稿安全闸」`backend/app/p4/draft_safety.py`：对客户正文做不依赖 gold 的硬性校验——
  正文不得出现金额/货币、不得有第一人称承诺（we guarantee/confirm/commit/...），且 policy 要求的护栏
  （价格复核、交期复核、binding commitment 复核）必须在场。结果写入 `reply_draft.safety`，并接入 P2
  pass 判定（`draft_safety_pass_rate` / `draft_safety_violation_inquiries`）。这道闸是 P5 LLM 输出必须复用的同一道。

当前边界：

- P4 仍然是模板填充，不做语言润色、语义改写或多语言回复。
- `customer_name` 暂时固定为 `Customer`，后续需要从邮件签名、CRM 或人工输入中获取。
- 模板按优先级单选：当多个风险并存（例如同时缺参数 + 认证不支持）时，正文只走最高优先级模板，
  次要风险（如认证）只进 `blocked_commitments`，不一定出现在客户正文里。价格/交期/承诺三类靠
  `append_policy_guardrails` 无条件补段兜底，认证暂未单独兜底。
- 草稿只表达“潜在匹配”和“待确认事项”，不决定最终产品型号、最终价格、最终交期或认证可行性。
- 后续 P5 可用 LLM 做措辞润色，但必须保留 `reply_policy`、`blocked_commitments`、人工审批约束，
  并让 LLM 产出过同一道 `draft_safety` 安全闸，不通过即回退模板版或打回人工。

运行命令：

```bash
python3 -m backend.app.cli run INQ-SYN-001
python3 -m backend.app.cli run INQ-SYN-002
python3 -m backend.app.cli run INQ-SYN-005
python3 -m backend.app.cli run INQ-SYN-010
```

## P5：模型网关

状态：进行中。第一增量（模型网关 + 草稿润色）已完成。

目标：在明确边界内引入 LLM。

模型服务选型：

- P5 第一版优先直连 DeepSeek 官方 API，默认模型建议使用 `deepseek-v4-flash`。
- 兜底模型保留 `deepseek-v4-pro`，只在 JSON 解析失败、低置信度样本、复杂 holdout 样本或人工指定时调用。
- 注意 `deepseek-v4-*` 是推理模型：响应里思维链在 `reasoning_content`、最终答案在 `content`，两者分开；
  `max_tokens` 把思维链也算进去。网关只取 `content` 用于业务（`reasoning_content` 只记日志/调试），
  `max_tokens` 要留足空间避免被思维链吃光（验证脚本用 16 会得到空 `content`，已改为 256），
  并按延迟/成本权衡是否需要思考模式。
- 当前不优先使用百炼等聚合平台；聚合平台的价值主要在后续企业 POC 的多模型切换、统一账单、企业采购、权限管理和云服务集成。
- 代码层面仍按 OpenAI-compatible provider 设计，避免和某一家供应商强绑定。后续如需切到百炼、千问、Kimi、GLM，只改 `base_url`、`model`、`api_key` 等配置，不改业务流程。
- API Key 不写入代码、不提交 Git，只通过本地环境变量或 `.env` 注入。

建议配置：

```text
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_FALLBACK_MODEL=deepseek-v4-pro
LLM_API_KEY=...
```

未来如果改走百炼一类聚合平台，可切换为：

```text
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=deepseek-v4-flash 或 qwen3.6-flash
LLM_FALLBACK_MODEL=deepseek-v4-pro 或 qwen3.7-plus
LLM_API_KEY=...
```

可引入的模型能力：

- 结构化字段抽取增强。
- 草稿润色。
- 澄清问题改写。
- 摘要生成。

不让 LLM 决定：

- 最终价格。
- 最终交期。
- 最终产品型号。
- 是否可以跳过人工审批。

需要完成：

1. 封装模型调用接口。
2. 支持 mock provider，方便无 API key 时本地跑。
3. 支持真实 provider，后续接入模型 API。
4. 输出保留 prompt、输入、输出、模型名和耗时。
5. 支持模型 fallback：默认便宜模型失败或置信度低时，再调用更强模型。
6. 记录每次调用的 token usage、耗时、provider、model、是否 fallback，方便后续算成本和调优。
7. LLM 产出必须过确定性校验后才能采用（运行时只此一处检测）：
   - 草稿润色结果复用 `backend/app/p4/draft_safety.check_reply_draft`；违规（金额/承诺/缺护栏）时把违规明细
     追加进 prompt 让模型重写（有限次），用尽仍不过则回退模板草稿。绝不透出不安全内容。
   - LLM 字段抽取结果仍要过 Schema/枚举/单位校验和正则兜底；风险规则始终在 LLM 之后再跑一遍。
8. model id 核实情况（对照 https://api-docs.deepseek.com/zh-cn/ ，2026-06）：
   - DeepSeek 当前真实模型为 `deepseek-v4-flash`、`deepseek-v4-pro`；旧的 `deepseek-chat` / `deepseek-reasoner`
     将于 2026/07/24 弃用（分别对应 v4-flash 的非思考/思考模式）。base_url `https://api.deepseek.com`，OpenAI 兼容。
   - 百炼/千问那组 id（`qwen3.6-flash` 等）仍是占位名，切换前再去阿里云文档核实。
   - 用 `scripts/check_deepseek_api.py` 可先验证 key、余额和一次最小推理调用是否通。

验收标准：

- 无模型 API 时系统仍可跑 baseline。
- 有模型 API 时可增强草稿和字段抽取。
- 默认模型失败时可以自动或手动切换 fallback 模型。
- LLM 润色后的草稿仍 100% 通过 `draft_safety` 安全闸；任何违规都不会进入可发送草稿。
- 指标判读要区分两条路：
  - 确定性 baseline 仍跑 default 作回归基线（必须保持满分，含 draft_safety）。
  - LLM 增强路线主要看 holdout 的新旧指标对比来判断是否真的提升泛化能力；
    不能用 default 的精确匹配给 LLM 抽取打分——default gold 与 generator 同源，LLM 即使更准、
    只要字符串不同也会“回退”，那是套套逻辑而非真实退步。

当前能力（第一增量）：

- `backend/app/p5/model_gateway.py`：OpenAI 兼容网关，`ModelConfig` 从 env/`.env` 读配置，
  `MockProvider`（离线确定性，echo 用户消息）+ `DeepSeekProvider`（stdlib urllib）+ 失败 fallback。
  响应只取 `content`，`reasoning_content` 单独保留；记录 provider/model/latency/usage/used_fallback。
- `backend/app/p5/reply_polish.py`：第一个接入能力是**草稿润色**。**LLM 只润色正文 `body_main`，确定性护栏
  （价格/交期/承诺免责段）由我们在 LLM 之后再追加**——护栏不进 LLM 编辑范围，避免它换措辞导致"护栏缺失"的误拒。
  安全检测**运行时只做一次，检最终草稿**（变量最大的是模型输出）；对 LLM 输出实际只强制负向不变量（不得加
  金额/承诺），正向护栏因为是我们拼的，恒满足。模板草稿按构造可信、运行时不再重复检测。LLM 输出不过安全闸时
  **不直接丢弃**，而是把"违反了哪些规则 + 细节"追加进对话**让模型重写**（`LLM_MAX_REPAIR_ATTEMPTS` 次，默认 1）；
  重试用尽仍不过，才回退**模板草稿作为终极兜底**（绝不透出不安全内容）。`reply_draft.polish` 记录 `applied`、
  `reason` 和逐次 `attempts`（含每次的 `safety_ok` 与 `violations`）。
- 安全检测分层：**运行时**只检模型输出；**评测层（P2 eval）**独立对确定性模板草稿做 safety 检测，作为模板
  回归保护（防止改模板/护栏时引入违规）。两者职责分开，运行时逻辑只有一处检测。
- opt-in：pipeline 默认不调用 LLM（`gateway=None`）；CLI `run --llm` 才启用，默认 `LLM_PROVIDER=mock`。
  因此 default eval 仍是纯确定性回归基线，不回退、不误花 API。

配置（env / `.env`，key 不进 Git）：

```text
LLM_PROVIDER=mock           # 或 deepseek
LLM_MODEL=deepseek-v4-flash
LLM_FALLBACK_MODEL=deepseek-v4-pro
LLM_API_KEY=...             # 或复用 DEEPSEEK_API_KEY
LLM_MAX_TOKENS=1024         # 需含思维链
LLM_MAX_REPAIR_ATTEMPTS=1   # 安全闸失败后让模型重写的次数（0=不重写直接回退模板）
```

运行命令：

```bash
uv run python -m backend.app.cli run --llm INQ-SYN-001                 # 默认 mock，离线
LLM_PROVIDER=deepseek uv run python -m backend.app.cli run --llm INQ-SYN-001   # 真实 DeepSeek
```

当前边界 / 下一步：

- 目前只接了草稿润色一个能力；字段抽取增强、澄清问题改写尚未接入。
- `eval` 仍走确定性路径；LLM 路线的「holdout 新旧指标对比」还没做（下一增量）。
- fallback 目前只在调用失败/空输出时触发；基于置信度的 fallback 待后续。

## P6：最小 Web 工作台

目标：让 Demo 可以被非技术用户看懂。

页面结构：

- 左侧：询盘列表。
- 中间：原始 email。
- 右侧：抽取字段、候选产品、引用、风险、草稿。
- 底部：人工编辑、通过、导出。

暂不做：

- 登录。
- 多租户。
- 复杂权限。
- 真实邮件发送。
- 真实 CRM/ERP 写入。

验收标准：

- 用户能选择一条询盘。
- 页面能展示完整流水线结果。
- 用户能编辑草稿并导出。

## P7：导出与演示脚本

目标：形成可演示闭环。

需要完成：

1. 导出邮件草稿。
2. 导出结构化 JSON。
3. 编写 Demo script。
4. 准备 3 类演示样本：
   - 标准询盘。
   - 缺参数询盘。
   - 高风险询盘。
5. 准备失败案例，用于展示系统边界。

验收标准：

- 5 分钟内能演示从输入到审批导出的完整流程。
- 能说明系统不会自动承诺价格、交期和认证。
- 能展示评测指标。

## 第一阶段建议范围

先完成：

```text
P0 + P1 + P2 + P3 + P4
```

也就是：

- 数据校验。
- 规则版流水线。
- 批量评测。
- 轻量检索。
- 模板回复。

完成后应具备：

```text
node demo-cli.js run INQ-SYN-001
node demo-cli.js eval
```

或等价命令。

## 暂定里程碑

### Milestone 1：CLI Baseline

范围：

- P0
- P1
- P2

交付：

- 命令行输入 `inquiry_id`，输出解析、匹配、风险和评测。
- 能批量评测 50 条询盘。

### Milestone 2：Retrieval + Reply Draft

范围：

- P3
- P4

交付：

- 有产品知识引用。
- 有模板回复草稿。
- 回复符合风险规则。

### Milestone 3：LLM Enhancement

范围：

- P5

交付：

- 模型网关。
- mock provider。
- 可选真实 provider。

### Milestone 4：Web Demo

范围：

- P6
- P7

交付：

- 最小工作台。
- 可演示闭环。

## 当前下一步

下一步建议从 Milestone 1 开始：

1. 建立项目代码结构。
2. 实现数据 loader。
3. 实现数据契约校验。
4. 实现第一版规则解析器。
5. 实现第一版评测脚手架。
