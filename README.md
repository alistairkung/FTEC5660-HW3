# FTEC5660 Homework 3: Fisher's 15-Point Investment Agent

Build a LangChain agent that researches a company with tools and applies the
framework from Philip Fisher's *Common Stocks and Uncommon Profits* (Part One,
Chapter 3 "What to buy: the fifteen points to look for in a common stock", and
Chapter 4 "What to buy: applying this to your own needs"). You choose 3 of
Fisher's 15 points and decide yourself what PASS means for each. For every
company your agent gives a PASS/FAIL verdict on your 3 points and a short
summary.

The companies are fictional, so the model cannot answer from memory. Unlike a
pile of reports, the evidence is spread over three sources, and your agent has
to go and get it with tools, the way Fisher's "scuttlebutt" method sends an
investor to talk to customers, competitors, suppliers and staff.

## Data and tools

`public_test/` has one folder per company. Your code receives four tools per
company (built by the provided code in `hw3.py`):

| Tool | What it gives you |
| --- | --- |
| `list_documents()` | the company's six documents and their dates |
| `read_document(name)` | one document: the 2025 letter to shareholders, four earnings calls (Q3 2025 to Q2 2026) and a news file (July 2025 to July 2026) |
| `sql_query(query)` | one read-only SQLite query on the company's database; at most 50 rows come back, so use `SUM`, `GROUP BY` and `WHERE` |
| `interview(role, topic)` | what one person says about the company; at most **10 interviews per company** |

The documents are what management says. Management's own claims (such as "we
have never cut research" or "our people are our greatest strength") are not
evidence on their own: check them against the database and the interviews.

**Database tables** (amounts in USD thousands; dates `YYYY-MM-DD`, months
`YYYY-MM`, quarters like `2025Q3`; the fiscal year is the calendar year):

| Table | Columns |
| --- | --- |
| `company` | name, industry |
| `industry_medians` | industry, revenue_growth_2y_pct, new_product_share_pct, new_product_sales_per_rd, operating_margin_pct (one row per industry; use the row for the company's own industry) |
| `orders` | order_id, order_date, product, customer, amount, note (about 3,000 to 4,000 orders from January 2023 to June 2026; revenue is the sum of order amounts) |
| `products` | product, launch_date |
| `monthly_costs` | month, cost_of_sales, selling_admin, research_development |
| `quarterly_cash` | quarter, operating_cash_flow, capex, cash_end |
| `capex_plan` | year, planned_capex (2026 to 2028) |
| `returns` | month, units_shipped, units_returned |
| `insider_trades` | trade_date, person, title, side (`buy` or `sell`), shares, price |

**Terms used in the data.**

| Term | Meaning |
| --- | --- |
| FY2025 | Fiscal year 2025. Here the fiscal year is the calendar year, so FY2025 is January to December 2025. |
| Quarter | Three months of the year: Q1 is January to March, Q2 April to June, Q3 July to September and Q4 October to December. The database writes `2025Q3`; the documents write "third quarter 2025". |
| Amounts | The database is in **USD thousands** (676,100 means US$676.1 million). The documents use USD millions. |
| Revenue | Money from sales: the sum of `amount` in `orders`. |
| Cost of sales | The cost of making the products that were sold. |
| Selling and admin | The cost of selling and of running the company (sales staff, offices, management). |
| R&D | Research and development spending, mainly on new products. |
| Operating margin | Operating profit as a share of revenue: (revenue − cost of sales − selling and admin − R&D) ÷ revenue. |
| Operating cash flow | Cash that the day-to-day business brings in during a quarter. |
| Cash at the end of a quarter | The cash the company holds on the last day of that quarter (`cash_end`). |
| Capex | Capital expenditure: spending on factories, machines and other long-term assets. `capex_plan` holds the planned capex for 2026 to 2028. |
| Return rate | Units returned ÷ units shipped, from the `returns` table. |
| Industry median | The middle value for companies in the same industry, from `industry_medians`. |
| Insider | A director or senior manager of the company. `insider_trades` lists the shares they bought (`buy`) or sold (`sell`). |
| Earnings call | A meeting each quarter where management presents the quarter's results to investors. Each call quotes that quarter's revenue. |

**Interviews.** Roles: `customer`, `current_employee`, `former_employee`,
`competitor`, `supplier`. Topics: `sales_team`, `working_conditions`,
`top_management`, `decision_making`, `competitive_edge`. Only some people know
about each topic; the others say they can't comment, and that answer still
uses up one interview.

| Topic | Who knows about it |
| --- | --- |
| `sales_team` | customer, competitor |
| `working_conditions` | current_employee, former_employee |
| `top_management` | former_employee, supplier |
| `decision_making` | supplier, customer |
| `competitive_edge` | competitor, customer |

People who know about a topic always agree with each other, so one good answer
is enough.

## Choose your 3 points and your rules

Pick any 3 of Fisher's 15 points and write them in `CHOSEN_POINTS` near the
top of `hw3.py`, e.g. `CHOSEN_POINTS = [1, 7, 15]`. The full questions are in
`FISHER_POINTS` in `hw3.py` and in the book.

| # | Fisher's point | Where the evidence is |
| --- | --- | --- |
| 1 | Market potential for sales growth | database |
| 2 | New products as current lines mature | database |
| 3 | Effective research and development | database |
| 4 | Above-average sales organization | interviews (`sales_team`) |
| 5 | Worthwhile profit margin | database |
| 6 | Maintaining or improving margins | database |
| 7 | Labour and personnel relations | interviews (`working_conditions`) |
| 8 | Executive relations | interviews (`top_management`) |
| 9 | Depth of management | interviews (`decision_making`) |
| 10 | Cost analysis and accounting controls | earnings calls, checked against the database |
| 11 | Advantage over competitors | interviews (`competitive_edge`) |
| 12 | Long-range outlook on profits | database |
| 13 | Growth without dilutive equity financing | database |
| 14 | Management talks freely about troubles | earnings calls, checked against the database |
| 15 | Management of unquestionable integrity | news file, checked against the database |

For each of your points, **you design the rule**: which evidence to use, what
to compute or whom to ask, and where the line between PASS and FAIL lies. PASS
means the company looks favourable on that point, as Fisher would see it.

We grade your verdicts against our own answer key. It uses one fixed rule per
point, which we do not publish, and the data never puts a company close to
the line of that rule, so a sensible reading of Fisher usually gives the same
answer. **Test your rules on the public answers**:
`public_test/ground_truth.json` gives the expected verdict on all 15 points
for each of the 20 public companies, and every point fails in 6 of them. If
your rule disagrees with the public answers, rethink it.

**Tip: calculate with tools, not in your head.** Do every sum, ratio and
comparison in SQL or Python, including the number of days between two dates
(SQLite's `julianday()` gives a date as a number of days).

## Student task

Fill in the three places in `hw3.py` marked `### YOUR CODE HERE`. You may add
imports, constants and helper functions above them, but do not change the
provided code below them:

- `CHOSEN_POINTS` lists your 3 points.
- `build_agent()` creates your model and anything else you need once.
- `analyze_companies(agent, companies)` receives
  `{company_folder: [list_documents, read_document, sql_query, interview]}`
  and returns, for every company,
  `{"points": {1: "PASS", 7: "FAIL", 15: "PASS"}, "summary": "..."}` (here with
  `CHOSEN_POINTS = [1, 7, 15]`).

Use the course techniques that fit your points: tool use for the database and
the interviews, planning which interviews to spend, routing each point to the
right source, prompt chaining, parallel calls, reflection to check your
answers, or a combination. Your code must read company data **only through
the four tools**; do not open `company.db` or `interviews.dat` yourself. Do
not hard-code folder names, company names or the public answers.

## Setup and public test

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "DEEPSEEK_API_KEY=your_key_here" > .env
python3 hw3.py --data-folder public_test
```

Use your own DeepSeek API key (from https://platform.deepseek.com). The
required model is `deepseek-v4-flash`. We grade with our own key, so never put
a key in your code; `.env` must stay out of git.

The program creates `results.csv` with the columns `company`, `points`,
`points_correct`, `point_errors`, `interviews_used` and `summary`, and prints
the point score on your 3 points (the percentage after "balanced"). The point
score is the average of two shares: the share of truly passing verdicts that
you marked PASS and the share of truly failing verdicts that you marked FAIL.
For example, 90% and 60% give (90% + 60%) / 2 = 75%, and marking every point
PASS gives (100% + 0%) / 2 = 50%. Once `CHOSEN_POINTS` is set, the starter
runs before you add any API code (it returns no verdicts, so it scores 0%).

`public_test/ground_truth.json` gives the expected verdicts on all 15 points
for each public company. Grading uses a private set of about 20 unseen
companies with the same tools and the same answer key rules, but different
names and wording, and scores your 3 points only.

## Homework 3 solution

### My 3 points and rules

I chose three complementary aspects of Fisher's framework, each grounded in a different kind of supplied evidence. The rules deliberately use observable indicators rather than asking the model to make unsupported general investment judgements.

| Point | Why I chose it | Evidence used | PASS rule |
| --- | --- | --- | --- |
| **4 — Above-average sales organisation** | Sales capability is difficult to judge from financial figures alone, so I wanted to apply Fisher's scuttlebutt approach to first-hand accounts of how the company serves customers. | A customer interview on `sales_team`, with a competitor interview only if the validated customer assessment is uncertain. | PASS when a validated interview assessment finds concrete favourable evidence of knowledgeable sales support, consultative problem-solving, customer value or sales effectiveness. Otherwise a supported negative assessment is FAIL; unresolved evidence remains explicitly marked as such internally. |
| **5 — Worthwhile profit margins** | I wanted a transparent, reproducible financial test rather than relying on the model's subjective view of whether a margin is good. An industry-relative benchmark accounts for differences in what constitutes a worthwhile margin across sectors. | SQL-derived FY2025 revenue and operating costs, plus the median operating margin for the company's own industry. | PASS when FY2025 operating margin is **greater than or equal to** the matching industry median. The `IndustryMarginStrategy` performs the calculation with Python `Decimal`. |
| **14 — Management talks openly about difficulties** | I chose this to examine whether management is candid when performance is disappointing, a dimension neither sales interviews nor margin calculations capture. I scoped the test to measurable returns/quality setbacks so that omissions could be checked against actual events. | SQL-derived quarterly units shipped and returned, compared with a pooled preceding-four-quarter baseline; complete same-quarter earnings calls for quarters with detected anomalies. | PASS if no quarterly return-rate anomaly is detected, or if management acknowledges **every** detected anomaly in the relevant earnings call. An anomaly means the current rate is at least twice the pooled preceding-four-quarter rate; if both current and baseline returns are zero, no anomaly is recorded. |

For Point 14, this is a deliberately narrow, evidence-testable proxy for Fisher's broader concern about management transparency, not a claim to assess every form of nondisclosure.

### Design

The agent uses a modular, evidence-first design: `hw3.py` delegates construction to a bootstrap layer, while `CompanyAnalyzer` runs the three point-specific specialists for each company, with at most two companies in flight. Each specialist retrieves evidence exclusively through the lecturer-provided, company-scoped tools and returns a shared `PointResult` containing its verdict, execution status, provenance and diagnostics. The methods deliberately differ by question: Point 4 uses a bounded LLM interpretation of customer interviews, with a competitor follow-up when the validated assessment is uncertain; Point 5 calculates an industry-relative operating margin deterministically using SQL evidence and Python `Decimal`; and Point 14 first detects anomalous return rates in Python, then asks an LLM to assess acknowledgement in the corresponding complete earnings call only where necessary. Python validates the model's quotation, speaker and period before the company-level result is assembled. Langfuse optionally traces the evidence retrieval, model decisions and usage without being required for normal execution.

```mermaid
flowchart TD
    B["hw3.build_agent → bootstrap"] --> C["CompanyAnalyzer: at most two companies"]
    T["Company-scoped supplied tools"] --> C

    subgraph P4["Point 4 — Sales organisation"]
        I4["Interview customer: sales_team"] --> L4["LLM: structured sales assessment"]
        L4 --> V4["Python: validate source and exact quotation"]
        V4 --> U4{"Validated UNCERTAIN?"}
        U4 -->|yes| F4["Interview competitor; reassess and validate; bounded adjudication if needed"]
    end

    subgraph P5["Point 5 — Profit margins"]
        S5["SQL: aggregate FY2025 financials and matching industry median"]
        S5 --> D5["Python Decimal: operating margin ≥ industry median"]
    end

    subgraph P14["Point 14 — Returns disclosure"]
        S14["SQL: quarterly returns and shipments"] --> D14["Python: compare rate with 2× pooled prior-four-quarter baseline"]
        D14 --> A14{"Any anomalies?"}
        A14 -->|no| N14["Scoped PASS: no documents or LLM calls"]
        A14 -->|yes| R14["Read complete earnings call for each anomalous quarter"]
        R14 --> L14["LLM: is the measured setback acknowledged?"]
        L14 --> V14["Python: validate document, period, management speaker and quotation"]
        V14 --> G14["Python: all acknowledged → PASS; any unacknowledged → FAIL; uncertainty stays explicit"]
    end

    C --> I4
    C --> S5
    C --> S14
    U4 -->|no| O["Shared PointResult: verdict, status, provenance and diagnostics"]
    F4 --> O
    D5 --> O
    N14 --> O
    G14 --> O
    O --> P["CompanyAnalyzer: assemble verdicts and summary; label unresolved FAIL fallbacks"]
    P --> CSV["Unchanged lecturer runner → results.csv"]
    C -.-> LF["Optional Langfuse: tools, models, decisions and usage"]
```

### Design reflection — simplifying Point 14

Point 14 was the hardest part to scope. My initial attempt tried to evaluate management transparency broadly by extracting claims, comparing them with financial performance and adjudicating whether management was candid. That design became increasingly elaborate, yet the evaluation remained unreliable: semantically unrelated facts were sometimes treated as contradictions, relevant metrics were missing, and repeated model-based repair did not resolve the underlying judgement problem. I used Langfuse traces to inspect where the pipeline failed rather than adding more reasoning stages or token budget. The eventual solution narrowed the claim to something the supplied evidence could support: whether management acknowledged objectively measured returns/quality setbacks in the relevant quarter's earnings call. A deterministic return-rate check now decides whether an LLM assessment is needed at all. This is a deliberately scoped interpretation of Fisher's Point 14, not a general-purpose test of management honesty; the simplification made the reasoning easier to audit and test.

### Results

I evaluated the agent on all 20 public companies using the lecturer’s runner:

```bash
python hw3.py --data-folder public_test
```

The agent produced **60/60 correct verdicts**, achieving **100% accuracy and balanced accuracy**.

| Fisher point | Correct verdicts | PASS recall | FAIL recall | Balanced accuracy |
| --- | ---: | ---: | ---: | ---: |
| 4 — Sales organisation | 20/20 | 14/14 | 6/6 | 100% |
| 5 — Worthwhile profit margins | 20/20 | 14/14 | 6/6 | 100% |
| 14 — Management transparency | 20/20 | 14/14 | 6/6 | 100% |
| **Overall** | **60/60** | **42/42** | **18/18** | **100%** |

There were **no disagreements with the public answers**, missing verdicts or operational failures. No correct answers depended on fallback FAIL responses. Two end-to-end runs produced identical verdicts, including a fresh-checkout run that completed in **18.22 seconds** using only the required dependencies and DeepSeek API key.

The traced run required **32 model calls**: 20 for sales-interview interpretation and 12 for returns-disclosure assessment. Point 5 required no model calls. Eight companies had no return-rate anomalies, so their Point 14 assessments required neither document retrieval nor model inference. Total recorded usage was **30,410 tokens**.

For Point 5, the industry strategy achieved **100% balanced accuracy**, compared with **52.38%** for the historical strategy. On this dataset, improving margins could still be below industry standards, while declining margins could remain worthwhile.

These results demonstrate agreement with the public dataset, but do not guarantee private-set performance. In particular, the Point 14 rule assesses disclosure of measured returns/quality setbacks rather than every aspect of management transparency.
