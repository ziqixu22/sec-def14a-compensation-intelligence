# SEC DEF 14A Executive Compensation Intelligence

A source-linked, review-first reproduction of an insurance executive compensation research workflow. It turns inconsistent spreadsheet and proxy-file work into a small SQLite data mart and Power BI-ready exports. It uses public SEC filings only, with no employer data.

## Current verified scope

- Five companies (AIG, Allstate, Hartford, MetLife, Travelers), CEO pay years 2023–2025: 15 approved company-year rows. Fourteen source-checked rows matched the live SEC parser field by field; the five latest-year rows were also rule-reconciled.
- GitHub Actions [refresh run #9](https://github.com/ziqixu22/sec-def14a-compensation-intelligence/actions/runs/40476796562) succeeded, parsed the 2025/2026 DEF 14A files, and published both CSVs. The monthly schedule is configured; its first scheduled execution has not occurred yet.

The [status file](data/out/status.json) and [live validation file](data/out/live_validation.json) record the current cohort and fourteen reference matches with no unresolved extraction exceptions in run #9. Filing year differs from pay year. MetLife is a life insurer, so avoid treating all five companies as a uniform peer benchmark.

## Pipeline and controls

| Stage | Method | Output |
| --- | --- | --- |
| Discover and fetch | SEC submissions API, CIK and DEF 14A filing-year filter; identifying User-Agent and paced requests | Filing metadata and cached primary HTML |
| Parse | Summary Compensation Table header detection with merged-cell expansion | SQLite candidate rows and source-linked review queue |
| Approve | Unique known latest-year CEO, component-total reconciliation, broad bounds; other rows wait for analyst review | Approved-only CSV, exceptions and raw-row provenance |
| Scan narrative | Keyword passages and nearby percentage candidates | Narrative and structured incentive candidate review queues; percentage candidates are not approved weights |
| Analyze | One selected filing per company/pay year, reconciliation and year-over-year comparison only with a prior year | Two [Power BI CSVs](data/out/powerbi_compensation.csv) and an [HTML preview](data/out/report.html) |

An extracted row is not accepted merely because a table looks plausible. A keyword passage is evidence to inspect, not a verified plan metric. The reviewed incentive evidence CSV now has 19 entries across AIG, Allstate, Hartford and Travelers; MetLife incentives are not yet structured. Its `weight_basis` distinguishes scorecard/PSU metric weight from LTI award mix. The build rejects duplicate records, unreviewed or unsupported sources, invalid weights and incomplete disclosed groups. No LLM API, OCR, or hosted warehouse is used for this small cohort.

## Reproduce

Python 3.11+; no third-party packages for the current HTML pipeline:

```bash
python3 build_analysis.py
python3 -m unittest discover -s tests -v
```

The offline build seeds fourteen source-checked CEO-year rows, validates component totals, and writes the exports and preview. Offline bootstrap is not proof of live parsing. To fetch live SEC filings, provide a real name and contact email in `SEC_USER_AGENT` (the example is a placeholder):

```bash
export SEC_USER_AGENT="Your Name contact@your-domain.example"
python3 sec_comp.py run --years 2025 2026
```

The GitHub workflow uses the repository secret rather than committing contact information. It runs on the 15th of each month and can be dispatched manually. It uploads review, structured candidate and exception queues as artifacts, and publishes approved outputs only after `verify_live()` checks parsed coverage and all fourteen source-checked CEO rows. Review candidate records before promoting them:

```bash
python3 sec_comp.py import-reviews data/out/review_queue.csv
python3 sec_comp.py export
```

Rows retain SEC filing URL, accession and raw table text. `filings` is keyed by accession; `compensation` is keyed by accession and row number. Successive filings can repeat a pay year, so the analytical export selects the newest approved version.

## Power BI report design

The [Power BI report](https://app.powerbi.com/groups/me/reports/7ad0a331-a1e7-4b9e-bce3-909fe251c02c?experience=power-bi) and [dashboard](https://app.powerbi.com/groups/me/dashboards/a7f92383-365c-400d-962f-700aa967f1e7?experience=power-bi) are saved in the owner's personal workspace. The semantic model connects anonymously to the two public raw GitHub CSV URLs. Direct local Excel upload was rejected by Power BI Service, which requires Excel to reside in OneDrive or SharePoint for that route. The report contains a compensation trend and detail page plus an incentive evidence page; the dashboard has a pinned compensation page and a separate incentive evidence table tile. Open the report for the full-width evidence table. The model has a daily 13:00 UTC refresh schedule and owner failure notifications. Manual refresh after run #9 completed at 2026-10-27 03:55:51 in the Power BI workspace display timezone. The report displayed all 19 incentive entries, including AIG and Hartford, while the compensation page retained all 15 CEO-year rows. The next scheduled refresh has not yet occurred.

For a separate Power BI build, import `data/out/powerbi_compensation.csv` and `data/out/powerbi_incentives.csv`. Set `pay_year` to a categorical whole number and amounts to currency. The published report has the trend, compensation detail and incentive evidence. A composition chart remains an optional extension:

1. CEO SCT total by `pay_year`, with company legend, filtered to `role = CEO`.
2. Optional compensation composition: salary, stock awards, option awards, non-equity incentive, pension change and all other.
3. Source-linked incentive evidence table with plan, metric, weight, summary and filing URL. The published Power BI semantic model retained its original eight-column schema after the CSV gained `weight_basis`; the plan name and evidence summary still distinguish metric weighting from award mix. The exported CSV and HTML preview contain the explicit basis field.

For a year-over-year measure, compare only within the same company and CEO, leaving the first available year blank. The published trend visual shows yearly totals; it does not include a separate year-over-year measure. Allstate's disclosed 60/40 split is a performance-share **metric weighting**; Travelers' 60/40 split is the **mix of performance shares and options** by grant-date value. They are different concepts.

The source CSV is refreshed monthly by GitHub Actions. Power BI's daily import schedule follows it; until a successful refresh completes, the model continues to show the previously imported data. These are two separate schedules, not an event-triggered integration.

## Findings and remaining work

Allstate 2025 CEO SCT total was approximately 14.3% below 2024, and Travelers was 17.0% above 2024. MetLife now has approved 2023–2025 pay years. Equity awards use grant-date accounting values; SCT total is neither realized pay nor a causal measure of business performance.

The five-company live run and Power BI manual refresh after run #9 have been verified, with 15 compensation rows and 19 incentive entries shown in the report. An actual future scheduled GitHub run and scheduled Power BI refresh remain unobserved. Unusual layouts, CEO succession and new or changed incentive plans require analyst review. Nearby percentages enter a candidate queue because they may refer to payout ranges or award mix rather than metric weight; only source-checked evidence enters the published incentives CSV. The reviewed AIG and Hartford 2025-plan metrics do not imply a general automatic approval capability. No manual review time or efficiency savings have been measured; a fair study should compare manual extraction with automation **plus review** on the same files and report coverage and correction rates.

## Resume wording

> Built a SEC DEF 14A executive compensation pipeline with Python, SQLite and GitHub Actions; validated 15 CEO-year records for five insurers against SEC filings, including 14 field-by-field reference checks, and published a two-page Power BI report and dashboard with a scheduled-refresh semantic model.

This is an independent reproduction. Do not describe it as a deployed employer system, a fully automated incentive-metric extractor, or a quantified reduction in research time.
