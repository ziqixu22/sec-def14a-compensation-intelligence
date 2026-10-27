# SEC DEF 14A Executive Compensation Intelligence

An independent, review-first reproduction of an insurance executive compensation research workflow. Inconsistent spreadsheets and manual proxy-file reading motivate a small, source-linked data mart. The demo compares the same CEOs at Allstate and Travelers over pay years 2023–2025 using their 2026 proxy statements. It uses only public SEC disclosures and does not contain employer data.

## What is implemented

| Stage | Method | Output |
| --- | --- | --- |
| Filing discovery | SEC submissions API, CIK and DEF 14A filing-year filter | Filing metadata and cached primary HTML |
| Numeric extraction | HTML table header detection with `rowspan` and `colspan` expansion | SQLite candidate rows and review queue |
| Narrative discovery | Keyword windows around ROE, TSR, performance shares and bonuses | Source-linked passages for analyst review |
| Quality control | Raw row and filing URL retained; analyst approval before BI export | Approved-only CSV and exceptions file |
| Analysis | Component-total reconciliation and CEO-year uniqueness check | Six reviewed records, two Power BI CSVs and an HTML report |

The quantitative and narrative paths are deliberately separate. A keyword hit is evidence to inspect, not an automatically verified metric or weight. An extracted table row is a candidate until approved. No LLM API, OCR, hosted warehouse or cloud scheduler is needed for this small cohort.

## Reproduce the reviewed demo offline

Python 3.11+ is sufficient; there are no third-party packages.

```bash
python3 build_analysis.py
python3 -m unittest discover -s tests -v
```

Open `data/out/report.html`. The generator reads `data/verified_ceo.csv` and `data/incentive_evidence.csv`, checks that compensation components sum to the disclosed total and that `(company, executive, pay_year)` is unique, then writes `data/out/powerbi_compensation.csv` and `data/out/powerbi_incentives.csv`. The six CEO-year rows were manually checked against the 2026 [Allstate](https://www.sec.gov/Archives/edgar/data/899051/000089905126000063/all-20260410.htm) and [Travelers](https://www.sec.gov/Archives/edgar/data/86312/000008631226000103/trv-20260406.htm) Summary Compensation Tables. Each row retains its source URL. The reviewed demo is a bootstrap sample, not a claim that live bulk retrieval and approval succeeded on this machine.

## Update from SEC filings

Use your real name and contact email in the SEC User-Agent. The address below is a placeholder.

```bash
export SEC_USER_AGENT="Your Name contact@your-domain.example"
python3 sec_comp.py fetch --years 2026 2027
python3 sec_comp.py extract
python3 sec_comp.py scan-narrative
python3 sec_comp.py export
```

`fetch` caches primary HTML and conservatively spaces SEC requests. `extract` stores possible Summary Compensation Table rows in SQLite without overriding prior reviews. `scan-narrative` writes `data/out/narrative_review_queue.csv`. `export` writes `review_queue.csv`, `bi_compensation.csv` (approved rows only) and `exceptions.csv`. Check candidates against the linked filings, correct any fields and set `review_status` to `approved` or `rejected` before importing them:

```bash
python3 sec_comp.py import-reviews data/out/review_queue.csv
python3 sec_comp.py export
```

`filings` is keyed by accession; `compensation` is keyed by accession and row number. Filing year and pay year are different. When successive filings repeat a pay year, choose the latest reviewed version for a company/executive/pay-year analytical view rather than counting both. Unsupported PDF-only, image or unusual layouts require manual handling.

## Power BI build guide

Import both `data/out/powerbi_*.csv` files in Power BI Desktop. Set `pay_year` to whole number and the compensation amounts to currency. Use:

1. A line or clustered column chart with `pay_year` on the X axis, `company` as legend and `total` as value, filtered to `role = CEO`.
2. A stacked column chart for salary, stock awards, option awards, non-equity incentive, pension change and other compensation.
3. An incentive evidence table with company, plan, metric, weight, summary and the filing URL.

Calculate year-over-year change only within the same company and executive, leaving the first year blank. Allstate's disclosed 60/40 split is a performance-share *metric weighting*; Travelers' 60/40 split is the *mix of performance shares and options* by grant-date value. They are different concepts.

The included HTML report is a cross-platform preview, not a `.pbix` dashboard. No Power BI Desktop file has been built or published.

## Findings and limitations

For this six-row sample, 2025 CEO Summary Compensation Table totals changed by approximately **-14.3% for Allstate** and **+17.0% for Travelers** versus 2024. These are descriptive comparisons for two companies, not an industry estimate. Equity awards use grant-date accounting values; SCT total is neither realized pay nor a causal measure of business performance.

The parser has four passing tests using synthetic and real-filing-shaped fixtures. The live SEC fetch-and-parse path has not been verified end to end in the current environment because command-line network access was unavailable. Source-reviewed demo values and the live-update pipeline should therefore be described separately. Manual review time and time savings have not been measured. A fair efficiency study would time manual lookup and extraction versus automated extraction **plus review** on the same filings, and track coverage and correction rates.

## Resume-safe wording

> Built a review-first SEC DEF 14A executive compensation workflow with Python and SQLite, including merged-cell table parsing and source-linked incentive disclosure search; verified six CEO-year records across Allstate and Travelers (2023–2025) and produced Power BI-ready datasets and a trend report.

This is an independent reproduction. Do not describe it as a deployed employer system, a published `.pbix` dashboard, an LLM-based extraction system, or a quantified reduction in research time.
