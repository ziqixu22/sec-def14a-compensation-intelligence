# SEC DEF 14A Executive Compensation Intelligence

A source-linked, review-first reproduction of an insurance executive compensation research workflow. It turns inconsistent spreadsheet and proxy-file work into a small SQLite data mart and Power BI-ready exports. It uses public SEC filings only, with no employer data.

## Current verified scope

- Allstate and Travelers: CEO pay years 2023–2025; all six rows from 2026 proxy statements matched manually checked reference values field by field.
- MetLife: CEO pay year 2025 from its 2026 proxy statement; the row passed automated component-to-total reconciliation, unique known CEO, latest-year, and plausibility rules. It does not yet have a separate manual reference check.
- The latest published GitHub outputs have seven CEO-year rows across three companies until the expanded live refresh succeeds. AIG and Hartford 2023–2025 reference values were checked against their 2026 SEC Summary Compensation Tables and added to the validation gate; local parser fixtures pass, but live extraction and publication are pending.
- GitHub Actions [refresh run #5](https://github.com/ziqixu22/sec-def14a-compensation-intelligence/actions/runs/40449087945) successfully fetched and parsed current SEC filings. The monthly schedule is configured; its first scheduled execution has not occurred yet.

The [status file](data/out/status.json) and [live validation file](data/out/live_validation.json) record the current cohort and six reference matches. Filing year differs from pay year. MetLife is a life insurer; Allstate and Travelers are P&C insurers, so avoid treating their totals as a uniform peer benchmark.

## Pipeline and controls

| Stage | Method | Output |
| --- | --- | --- |
| Discover and fetch | SEC submissions API, CIK and DEF 14A filing-year filter; identifying User-Agent and paced requests | Filing metadata and cached primary HTML |
| Parse | Summary Compensation Table header detection with merged-cell expansion | SQLite candidate rows and source-linked review queue |
| Approve | Unique known latest-year CEO, component-total reconciliation, broad bounds; other rows wait for analyst review | Approved-only CSV, exceptions and raw-row provenance |
| Scan narrative | Keyword passages and nearby percentage candidates | Narrative and structured incentive candidate review queues; percentage candidates are not approved weights |
| Analyze | One selected filing per company/pay year, reconciliation and year-over-year comparison only with a prior year | Two [Power BI CSVs](data/out/powerbi_compensation.csv) and an [HTML preview](data/out/report.html) |

An extracted row is not accepted merely because a table looks plausible. A keyword passage is evidence to inspect, not a verified plan metric. The reviewed incentive evidence CSV has two-company examples; MetLife incentives are not yet structured. No LLM API, OCR, or hosted warehouse is used for this small cohort.

## Reproduce

Python 3.11+; no third-party packages for the current HTML pipeline:

```bash
python3 build_analysis.py
python3 -m unittest discover -s tests -v
```

The offline build seeds twelve source-checked Allstate, Travelers, AIG and Hartford CEO-year rows, validates component totals, and writes the exports and preview. Offline bootstrap is not proof of live parsing. To fetch live SEC filings, provide a real name and contact email in `SEC_USER_AGENT` (the example is a placeholder):

```bash
export SEC_USER_AGENT="Your Name contact@your-domain.example"
python3 sec_comp.py run --years 2025 2026
```

The GitHub workflow uses the repository secret rather than committing contact information. It runs on the 15th of each month and can be dispatched manually. It uploads review, structured candidate and exception queues as artifacts, and publishes approved outputs only after `verify_live()` checks parsed coverage and all twelve source-checked CEO rows, including AIG and Hartford. Review candidate records before promoting them:

```bash
python3 sec_comp.py import-reviews data/out/review_queue.csv
python3 sec_comp.py export
```

Rows retain SEC filing URL, accession and raw table text. `filings` is keyed by accession; `compensation` is keyed by accession and row number. Successive filings can repeat a pay year, so the analytical export selects the newest approved version.

## Power BI report design

The [Power BI report](https://app.powerbi.com/groups/me/reports/7ad0a331-a1e7-4b9e-bce3-909fe251c02c?experience=power-bi) and [dashboard](https://app.powerbi.com/groups/me/dashboards/a7f92383-365c-400d-962f-700aa967f1e7?experience=power-bi) are saved in the owner's personal workspace. The semantic model connects anonymously to the two public raw GitHub CSV URLs. Direct local Excel upload was rejected by Power BI Service, which requires Excel to reside in OneDrive or SharePoint for that route. The report contains a compensation trend and detail page plus an incentive evidence page; the dashboard has a pinned compensation page. The model has a daily 13:00 UTC refresh schedule and owner failure notifications. A successful post-change scheduled refresh has not yet been observed.

For a separate Power BI build, import `data/out/powerbi_compensation.csv` and `data/out/powerbi_incentives.csv`. Set `pay_year` to a categorical whole number and amounts to currency. Visuals:

1. CEO SCT total by `pay_year`, with company legend, filtered to `role = CEO`.
2. Compensation composition: salary, stock awards, option awards, non-equity incentive, pension change and all other.
3. Source-linked incentive evidence table with plan, metric, weight, summary and filing URL.

Calculate year-over-year only within the same company and CEO, leaving the first available year blank. Allstate's disclosed 60/40 split is a performance-share **metric weighting**; Travelers' 60/40 split is the **mix of performance shares and options** by grant-date value. They are different concepts.

The source CSV is refreshed monthly by GitHub Actions. Power BI's daily import schedule follows it; until a successful refresh completes, the model continues to show the previously imported data. These are two separate schedules, not an event-triggered integration.

## Findings and remaining work

Allstate 2025 CEO SCT total was approximately 14.3% below 2024, and Travelers was 17.0% above 2024. MetLife has only one approved pay year, so no year-over-year figure is reported. Equity awards use grant-date accounting values; SCT total is neither realized pay nor a causal measure of business performance.

The live five-company run and downstream Power BI update still require verification. Unusual layouts, CEO succession, and structured incentive-plan weights require analyst review. Nearby percentages enter a candidate queue because they may refer to payout ranges or award mix rather than metric weight. No manual review time or efficiency savings have been measured; a fair study should compare manual extraction with automation **plus review** on the same files and report coverage and correction rates.

## Resume wording

> Built a SEC DEF 14A executive compensation pipeline with Python, SQLite and GitHub Actions, source-checked CEO pay references for four insurers, and published a two-page Power BI report with a scheduled-refresh semantic model. Live five-company validation remains in progress.

This is an independent reproduction. Do not describe it as a deployed employer system, a fully automated incentive-metric extractor, or a quantified reduction in research time.
