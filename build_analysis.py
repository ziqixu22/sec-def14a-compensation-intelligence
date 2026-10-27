#!/usr/bin/env python3
"""Validate the SEC-reviewed sample and produce portable BI inputs and a report."""
import csv
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
from sec_comp import connect, seed_reference

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = DATA / "out"
COMPONENTS = ("salary", "bonus", "stock_awards", "option_awards",
              "non_equity_incentive", "pension_change", "all_other")


def read_csv(name):
    with (DATA / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(name, rows):
    with (OUT / name).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def build():
    seed_reference()
    names = {r["company"]: r["ceo_name"] for r in read_csv("../companies.csv")}
    with connect() as con:
        approved = [dict(r) for r in con.execute("""SELECT f.company,f.cik,f.filing_date,c.accession,f.filing_url,
            c.executive,c.pay_year,c.salary,c.bonus,c.stock_awards,c.option_awards,
            c.non_equity_incentive,c.pension_change,c.all_other,c.total,c.approval_method,c.row_number
            FROM compensation c JOIN filings f USING(accession)
            WHERE c.review_status='approved' ORDER BY f.filing_date DESC,(c.row_number>0) DESC,c.row_number ASC""")]
    selected = {}
    for r in approved:
        if not r["executive"].startswith(names.get(r["company"], "\0")):
            continue
        key = (r["company"], int(r["pay_year"]))
        selected.setdefault(key, r)  # Newest filing; live parsed row wins on a tie.
    rows = []
    for r in selected.values():
        row = {key: r[key] for key in ("company", "cik", "filing_date", "accession", "filing_url",
                                     "executive", "pay_year", *COMPONENTS, "total")}
        row["role"] = "CEO"
        row["verification"] = r["approval_method"]
        rows.append(row)
    incentives = read_csv("incentive_evidence.csv")
    if not rows:
        raise ValueError("No approved CEO records in the data mart")
    if len({(r["company"], r["executive"], r["pay_year"]) for r in rows}) != len(rows):
        raise ValueError("Duplicate company/executive/pay year; select the most recent reviewed filing")
    for row in rows:
        if not row["filing_url"].startswith("https://www.sec.gov/Archives/"):
            raise ValueError("Missing SEC provenance")
        if sum(int(row[x] or 0) for x in COMPONENTS) != int(row["total"]):
            raise ValueError(f"Component reconciliation failed: {row['company']} {row['pay_year']}")
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv("powerbi_compensation.csv", rows)
    write_csv("powerbi_incentives.csv", incentives)

    indexed = {(r["company"], int(r["pay_year"])): r for r in rows}
    ordered = sorted(rows, key=lambda r: (r["company"], int(r["pay_year"])))
    max_total = max(int(r["total"]) for r in rows)
    table = []
    bars = []
    for r in ordered:
        company, year, total = r["company"], int(r["pay_year"]), int(r["total"])
        prev = indexed.get((company, year - 1))
        change = (total / int(prev["total"]) - 1) * 100 if prev else None
        growth = "—" if change is None else f"{change:+.1f}%"
        equity = (int(r["stock_awards"]) + int(r["option_awards"])) / total * 100
        table.append(f'<tr><td>{escape(company)}</td><td>{year}</td><td>${total:,.0f}</td>'
                     f'<td>{growth}</td><td>{equity:.1f}%</td><td><a href="{escape(r["filing_url"])}">SEC filing</a></td></tr>')
        width = 100 * total / max_total
        bars.append(f'<div class="barrow"><span>{escape(company)} {year}</span>'
                    f'<div class="track"><div class="bar {company.lower()}" style="width:{width:.1f}%"></div></div>'
                    f'<strong>${total/1e6:.2f}m</strong></div>')
    insight = []
    for company in sorted({r["company"] for r in rows}):
        years = sorted(year for name, year in indexed if name == company)
        if len(years) > 1 and years[-1] - 1 in years:
            a, b = indexed[(company, years[-1] - 1)], indexed[(company, years[-1])]
            change = (int(b["total"]) / int(a["total"]) - 1) * 100
            insight.append(f"{company}: {years[-1]} CEO SCT total {change:+.1f}% year over year")
    evidence = "".join(f'<tr><td>{escape(r["company"])}</td><td>{escape(r["plan"])}</td>'
                       f'<td>{escape(r["metric"])}</td><td>{escape(r["weight_pct"] or "—")}</td>'
                       f'<td>{escape(r["evidence_summary"])}</td>'
                       f'<td><a href="{escape(r["filing_url"])}">SEC filing</a></td></tr>'
                       for r in incentives)
    html = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SEC executive pay | reviewed sample</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;background:#f5f7fb;color:#14233b;margin:0}}
main{{max-width:1100px;margin:auto;padding:42px 22px}}h1{{font-size:2rem;margin-bottom:4px}}h2{{margin-top:36px}}
.lead{{color:#50627b}}.card{{background:white;border-radius:14px;padding:24px;box-shadow:0 2px 12px #10204012;margin:18px 0}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.metric{{font-size:1.7rem;font-weight:700;color:#1554a5}}
table{{width:100%;border-collapse:collapse;font-size:.93rem}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #e2e8f0;vertical-align:top}}
.overflow{{overflow-x:auto}}.barrow{{display:grid;grid-template-columns:150px 1fr 75px;align-items:center;gap:10px;margin:11px 0}}
.track{{height:22px;background:#e9edf5;border-radius:5px}}.bar{{height:100%;background:#1875bb;border-radius:5px}}
.bar.travelers{{background:#27a489}}.note{{color:#526177;font-size:.88rem}}a{{color:#1454aa}}
@media(max-width:700px){{.grid{{grid-template-columns:1fr}}.barrow{{grid-template-columns:105px 1fr 70px;font-size:.8rem}}}}</style>
<main><h1>SEC 高管薪酬情报｜复现样本</h1><p class="lead">DEF 14A · {len(set(r['company'] for r in rows))} 家财产险公司 · {min(int(r['pay_year']) for r in rows)}–{max(int(r['pay_year']) for r in rows)} 薪酬年度 · SEC Summary Compensation Table</p>
<div class="grid"><div class="card"><div class="metric">{len(set(r['company'] for r in rows))}</div>公司</div><div class="card"><div class="metric">{len(rows)}</div>已批准记录</div>
<div class="card"><div class="metric">100%</div>组成项与披露总额核对一致</div></div>
<section class="card"><h2>CEO 披露薪酬总额</h2>{''.join(bars)}<p class="note">单位：美元。薪酬年度不是文件提交年度；SCT 采用授予日会计价值，不代表实际兑现收入。</p></section>
<section class="card"><h2>变化与薪酬结构</h2><div class="overflow"><table><thead><tr><th>公司</th><th>年度</th><th>SCT 总额</th><th>同比</th><th>股权授予价值占比</th><th>原文</th></tr></thead>
<tbody>{''.join(table)}</tbody></table></div><p class="note">同比仅比较同一公司、同一位 CEO。{'; '.join(insight)}。</p></section>
<section class="card"><h2>激励方案披露摘录</h2><div class="overflow"><table><thead><tr><th>公司</th><th>计划</th><th>指标/形式</th><th>占比 %</th><th>证据摘要</th><th>原文</th></tr></thead>
<tbody>{evidence}</tbody></table></div><p class="note">Allstate 的 60/40 是绩效股的考核指标权重；Travelers 的 60/40 是长期激励授予价值的形式占比，口径不同，不应直接横向比较。</p></section>
<section class="card"><h2>业务解读与边界</h2><p>两家公司 2025 年的 CEO 披露总额走势不同。表内股权价值取决于授予日估值，非股权激励和养老金变动也会影响同比；因此不能仅凭总额推断经营绩效或实际到手金额。</p>
<p>这是一份两家公司示范样本，不能代表行业平均水平。候选表格抽取须与 SEC 原文核对；跨文件的重复薪酬年度按最新核对版本保留。节省工时需另做人工与自动化加审核的计时对照。</p></section>
<p class="note">数据文件：powerbi_compensation.csv、powerbi_incentives.csv；生成：python3 build_analysis.py。</p></main></html>'''
    (OUT / "report.html").write_text(html, encoding="utf-8")
    (OUT / "status.json").write_text(json.dumps({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "approved_ceo_years": len(rows),
        "companies": sorted({r["company"] for r in rows}),
        "pay_years": sorted({int(r["pay_year"]) for r in rows}),
        "approval_methods": {method: sum(r["verification"] == method for r in rows)
                             for method in sorted({r["verification"] for r in rows})},
        "filing_urls": sorted({r["filing_url"] for r in rows}),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Validated {len(rows)} approved SEC records; wrote two Power BI CSV files and report.html")


if __name__ == "__main__":
    build()
