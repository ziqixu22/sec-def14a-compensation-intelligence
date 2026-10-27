# SEC DEF 14A Executive Compensation Intelligence

A source-linked, review-first reproduction of an insurance executive compensation research workflow. It turns inconsistent spreadsheet and proxy-file work into a small SQLite data mart and Power BI-ready exports. It uses public SEC filings only, with no employer data.

## Current verified scope

- Allstate and Travelers: CEO pay years 2023–2025; all six rows from 2026 proxy statements matched manually checked reference values field by field.
- MetLife: CEO pay year 2025 from its 2026 proxy statement; the row passed automated component-to-total reconciliation, unique known CEO, latest-year, and plausibility rules. It does not yet have a separate manual reference check.
- Seven approved CEO-year rows across three companies. Four historical rows have `manual_source_check`; three latest-year rows have `rule_reconciled` provenance.
- GitHub Actions [refresh run #5](https://github.com/ziqixu22/sec-def14a-compensation-intelligence/actions/runs/40449087945) successfully fetched and parsed current SEC filings. The monthly schedule is configured; its first scheduled execution has not occurred yet.

The [status file](data/out/status.json) and [live validation file](data/out/live_validation.json) record the current cohort and six reference matches. Filing year differs from pay year. MetLife is a life insurer; Allstate and Travelers are P&C insurers, so avoid treating their totals as a uniform peer benchmark.

## Pipeline and controls

| Stage | Method | Output |
| --- | --- | --- |
| Discover and fetch | SEC submissions API, CIK and DEF 14A filing-year filter; identifying User-Agent and paced requests | Filing metadata and cached primary HTML |
| Parse | Summary Compensation Table header detection with merged-cell expansion | SQLite candidate rows and source-linked review queue |
| Approve | Unique known latest-year CEO, component-total reconciliation, broad bounds; other rows wait for analyst review | Approved-only CSV, exceptions and raw-row provenance |
| Scan narrative | Keyword passages around incentive terms | Narrative review queue, without inferred metrics or weights |
| Analyze | One selected filing per company/pay year, reconciliation and year-over-year comparison only with a prior year | Two [Power BI CSVs](data/out/powerbi_compensation.csv) and an [HTML preview](data/out/report.html) |

An extracted row is not accepted merely because a table looks plausible. A keyword passage is evidence to inspect, not a verified plan metric. The reviewed incentive evidence CSV has two-company examples; MetLife incentives are not yet structured. No LLM API, OCR, or hosted warehouse is used for this small cohort.

## Reproduce

Python 3.11+; no third-party packages for the current HTML pipeline:

```bash
python3 build_analysis.py
python3 -m unittest discover -s tests -v
```

The offline build seeds the six source-checked Allstate and Travelers CEO-year rows, validates component totals, and writes the exports and preview. To fetch live SEC filings, provide a real name and contact email in `SEC_USER_AGENT` (the example is a placeholder):

```bash
export SEC_USER_AGENT="Your Name contact@your-domain.example"
python3 sec_comp.py run --years 2025 2026
```

The GitHub workflow uses the repository secret rather than committing contact information. It runs on the 15th of each month and can be dispatched manually. It uploads review and exception queues as artifacts, and publishes approved outputs only after `verify_live()` checks parsed coverage and all six Allstate/Travelers source-checked CEO rows. Review candidate records before promoting them:

```bash
python3 sec_comp.py import-reviews data/out/review_queue.csv
python3 sec_comp.py export
```

Rows retain SEC filing URL, accession and raw table text. `filings` is keyed by accession; `compensation` is keyed by accession and row number. Successive filings can repeat a pay year, so the analytical export selects the newest approved version.

## Power BI report design

Import `data/out/powerbi_compensation.csv` and `data/out/powerbi_incentives.csv` in Power BI Service or Desktop. Set `pay_year` to whole number and amounts to currency. Suggested visuals:

1. CEO SCT total by `pay_year`, with company legend, filtered to `role = CEO`.
2. Compensation composition: salary, stock awards, option awards, non-equity incentive, pension change and all other.
3. Source-linked incentive evidence table with plan, metric, weight, summary and filing URL.

Calculate year-over-year only within the same company and CEO, leaving the first available year blank. Allstate's disclosed 60/40 split is a performance-share **metric weighting**; Travelers' 60/40 split is the **mix of performance shares and options** by grant-date value. They are different concepts.

The HTML preview is available now. A Power BI Service report has not yet been published. The signed-in personal workspace is available, but browser file upload requires enabling the ChatGPT Chrome extension's **Allow access to file URLs** setting. A seven-row Excel import file was prepared locally for the next upload attempt.

## Findings and remaining work

Allstate 2025 CEO SCT total was approximately 14.3% below 2024, and Travelers was 17.0% above 2024. MetLife has only one approved pay year, so no year-over-year figure is reported. Equity awards use grant-date accounting values; SCT total is neither realized pay nor a causal measure of business performance.

The original five-company, fully automated target remains unfinished. AIG and Hartford, PDF-only or unusual layouts, CEO succession, structured incentive-plan metrics, and corresponding checks need further implementation. Narrative hits require analyst review. No manual review time or efficiency savings have been measured; a fair study should compare manual extraction with automation **plus review** on the same files and report coverage and correction rates.

## Resume wording

> Built a monthly SEC DEF 14A executive compensation pipeline with Python, SQLite and GitHub Actions; parsed CEO pay for three insurers, matched six Allstate/Travelers CEO-year records against source-checked references, and produced source-linked Power BI datasets and a trend report.

This is an independent reproduction. Do not describe it as a deployed employer system, a published `.pbix` dashboard, a fully automated incentive-metric extractor, or a quantified reduction in research time.
