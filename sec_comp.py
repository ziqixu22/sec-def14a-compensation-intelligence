#!/usr/bin/env python3
"""Small, review-first SEC DEF 14A compensation data mart."""
import argparse
import csv
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "out"
DB = ROOT / "data" / "compensation.sqlite"
FIELDS = ("salary", "bonus", "stock_awards", "option_awards", "non_equity_incentive", "pension_change", "all_other", "total")
EXPORT_FIELDS = ("accession", "row_number", "company", "filing_date", "filing_url", "executive", "pay_year", *FIELDS, "raw_row", "review_status", "approval_method")


def clean(value):
    return re.sub(r"\s+", " ", value).strip()


def money(value):
    value = clean(value).replace("$", "").replace(",", "").replace(" ", "")
    if value in ("", "-", "—", "–", "N/A"):
        return None
    if not re.fullmatch(r"\(?\d+(?:\.\d+)?\)?", value):
        return None
    return -float(value[1:-1]) if value.startswith("(") else float(value)


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.depth = 0
        self.table = None
        self.row = None
        self.cell = None
        self.spans = None
        self.text_before = ""

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.table = {"context": self.text_before[-600:], "rows": []}
        elif self.depth == 1 and tag == "tr":
            self.row = []
        elif self.depth == 1 and tag in ("th", "td") and self.row is not None:
            self.cell = []
            attributes = dict(attrs)
            self.spans = (max(1, int(attributes.get("colspan", "1"))),
                          max(1, int(attributes.get("rowspan", "1"))))

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)
        elif self.depth == 0:
            self.text_before = (self.text_before + " " + data)[-1200:]

    def handle_endtag(self, tag):
        if self.depth == 1 and tag in ("th", "td") and self.cell is not None and self.row is not None:
            self.row.append((clean(" ".join(self.cell)), *self.spans))
            self.cell = None
        elif self.depth == 1 and tag == "tr" and self.row is not None and self.table is not None:
            if any(cell[0] for cell in self.row):
                self.table["rows"].append(self.row)
            self.row = None
        elif tag == "table" and self.depth:
            self.depth -= 1
            if self.depth == 0 and self.table is not None:
                self.tables.append(self.table)
                self.table = None


def column_name(label):
    label = re.sub(r"\s+", "", label).lower()
    if "name" in label and ("position" in label or "principal" in label):
        return "executive"
    if label == "year" or "fiscalyear" in label:
        return "pay_year"
    if "non-equity" in label or "nonequity" in label:
        return "non_equity_incentive"
    if "stockaward" in label:
        return "stock_awards"
    if "optionaward" in label:
        return "option_awards"
    if "allother" in label:
        return "all_other"
    if "changeinpension" in label:
        return "pension_change"
    if "salary" in label:
        return "salary"
    if "bonus" in label:
        return "bonus"
    if label == "total" or re.match(r"total\(\$?\)(?:\(\d+\))?$", label) or re.match(r"total\(\d+\)\(\$\)$", label):
        return "total"
    return None


def expand_rows(rows):
    """Expand HTML row/column spans, retaining the first value of each range."""
    pending = {}
    expanded = []
    for row in rows:
        grid = {}
        for position, (value, remaining) in pending.items():
            grid[position] = value
        next_pending = {pos: (value, remaining - 1) for pos, (value, remaining) in pending.items()
                        if remaining > 1}
        position = 0
        for value, width, height in row:
            while position in grid:
                position += 1
            for offset in range(width):
                grid[position + offset] = value
                if height > 1:
                    next_pending[position + offset] = (value, height - 1)
            position += width
        expanded.append([grid.get(i, "") for i in range(max(grid, default=-1) + 1)])
        pending = next_pending
    return expanded


def candidates(html):
    parser = Tables()
    parser.feed(html)
    found = []
    for table in parser.tables:
        rows = expand_rows(table["rows"])
        for header_index, row in enumerate(rows[:8]):
            columns = [column_name(cell) for cell in row]
            required = {"executive", "pay_year", "salary", "stock_awards", "option_awards",
                        "non_equity_incentive", "pension_change", "all_other", "total"}
            if not required.issubset(columns):
                continue
            if "summary compensation" not in table["context"].lower() and "summary compensation" not in " ".join(" ".join(r) for r in rows[:3]).lower():
                continue
            for body in rows[header_index + 1:]:
                item = {}
                for index, field in enumerate(columns):
                    if field and index < len(body) and field not in item and body[index]:
                        item[field] = body[index]
                year = clean(item.get("pay_year", ""))
                name = clean(item.get("executive", ""))
                match = re.fullmatch(r"(20\d{2})(?:\s*\(\d+\))?", year)
                if not match or not name:
                    continue
                record = {"executive": name, "pay_year": int(match.group(1)),
                          "raw_row": " | ".join(value for i, value in enumerate(body)
                                                if value and (i == 0 or value != body[i-1]))}
                for field in FIELDS:
                    record[field] = money(item.get(field, ""))
                if record["total"] is not None:
                    components = sum(record[field] or 0 for field in FIELDS if field != "total")
                    record["reconciled"] = abs(components - record["total"]) <= 1
                    found.append(record)
            if found:
                return found
    return found


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS filings (
      accession TEXT PRIMARY KEY, company TEXT NOT NULL, cik INTEGER NOT NULL,
      filing_date TEXT NOT NULL, filing_url TEXT NOT NULL, local_path TEXT NOT NULL,
      extraction_error TEXT
    );
    CREATE TABLE IF NOT EXISTS compensation (
      accession TEXT NOT NULL REFERENCES filings(accession),
      row_number INTEGER NOT NULL, executive TEXT NOT NULL, pay_year INTEGER NOT NULL,
      salary REAL, bonus REAL, stock_awards REAL, option_awards REAL,
      non_equity_incentive REAL, pension_change REAL, all_other REAL, total REAL,
      raw_row TEXT NOT NULL, approval_method TEXT,
      review_status TEXT NOT NULL DEFAULT 'needs_review'
        CHECK(review_status IN ('needs_review','approved','rejected')),
      PRIMARY KEY(accession,row_number)
    );
    """)
    if "pension_change" not in {row[1] for row in con.execute("PRAGMA table_info(compensation)")}:
        con.execute("ALTER TABLE compensation ADD COLUMN pension_change REAL")
    if "approval_method" not in {row[1] for row in con.execute("PRAGMA table_info(compensation)")}:
        con.execute("ALTER TABLE compensation ADD COLUMN approval_method TEXT")
    return con


def get(url, agent):
    request = Request(url, headers={"User-Agent": agent, "Accept-Encoding": "identity"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def fetch(years):
    agent = os.environ.get("SEC_USER_AGENT", "")
    if not re.search(r"[^\s@]+@[^\s@]+", agent):
        raise SystemExit("Set SEC_USER_AGENT to an identifying name and real contact email.")
    RAW.mkdir(parents=True, exist_ok=True)
    with connect() as con, (ROOT / "companies.csv").open(newline="") as stream:
        for company in csv.DictReader(stream):
            cik = int(company["cik"])
            submissions_url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
            recent = json.loads(get(submissions_url, agent))["filings"]["recent"]
            time.sleep(1)
            for i, (form, date) in enumerate(zip(recent["form"], recent["filingDate"])):
                if form != "DEF 14A" or int(date[:4]) not in years:
                    continue
                accession = recent["accessionNumber"][i]
                document = recent["primaryDocument"][i]
                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{document}"
                path = RAW / f"{accession}.html"
                if not path.exists():
                    path.write_bytes(get(url, agent))
                    time.sleep(1)
                con.execute("""INSERT INTO filings(accession,company,cik,filing_date,filing_url,local_path)
                               VALUES(?,?,?,?,?,?) ON CONFLICT(accession) DO UPDATE SET
                               filing_url=excluded.filing_url,local_path=excluded.local_path""",
                            (accession, company["company"], cik, date, url, str(path)))
                print(f"Cached {company['company']} {date}: {accession}")


def extract():
    with (ROOT / "companies.csv").open(newline="", encoding="utf-8") as stream:
        ceos = {row["company"]: row["ceo_name"] for row in csv.DictReader(stream)}
    with connect() as con:
        for filing in con.execute("SELECT * FROM filings").fetchall():
            if not filing["local_path"]:
                continue  # The reviewed bootstrap row has no cached HTML yet.
            try:
                html = Path(filing["local_path"]).read_text(encoding="utf-8", errors="replace")
                rows = candidates(html)
                if not rows:
                    raise ValueError("No Summary Compensation Table candidate; inspect source manually")
                latest_pay_year = int(filing["filing_date"][:4]) - 1
                ceo_rows = [row for row in rows if row["executive"].startswith(ceos.get(filing["company"], "\0"))
                            and row["pay_year"] == latest_pay_year]
                unambiguous_ceo = len(ceo_rows) == 1
                for number, row in enumerate(rows, 1):
                    auto_approved = (unambiguous_ceo and row is ceo_rows[0] and row["reconciled"]
                                     and 100_000 <= row["total"] <= 200_000_000)
                    con.execute("""INSERT OR IGNORE INTO compensation
                      (accession,row_number,executive,pay_year,salary,bonus,stock_awards,
                       option_awards,non_equity_incentive,pension_change,all_other,total,raw_row,review_status,approval_method)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (filing["accession"], number, row["executive"], row["pay_year"],
                       *(row[field] for field in FIELDS), row["raw_row"],
                       "approved" if auto_approved else "needs_review",
                       "rule_reconciled" if auto_approved else None))
                con.execute("UPDATE filings SET extraction_error=NULL WHERE accession=?", (filing["accession"],))
                print(f"{filing['accession']}: {len(rows)} candidates; unambiguous latest-year CEO: {unambiguous_ceo}")
            except (OSError, ValueError) as exc:
                con.execute("UPDATE filings SET extraction_error=? WHERE accession=?", (str(exc), filing["accession"]))
                print(f"{filing['accession']}: {exc}")


def write_csv(path, fields, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def export():
    with connect() as con:
        rows = [dict(row) for row in con.execute("""SELECT c.accession,c.row_number,f.company,f.filing_date,f.filing_url,
          c.executive,c.pay_year,c.salary,c.bonus,c.stock_awards,c.option_awards,
          c.non_equity_incentive,c.pension_change,c.all_other,c.total,c.raw_row,c.review_status,c.approval_method
          FROM compensation c JOIN filings f USING(accession)
          ORDER BY f.company,c.pay_year DESC,c.row_number""")]
        write_csv(OUT / "review_queue.csv", EXPORT_FIELDS, rows)
        write_csv(OUT / "bi_compensation.csv", EXPORT_FIELDS,
                  (row for row in rows if row["review_status"] == "approved"))
        exceptions = [dict(row) for row in con.execute(
            "SELECT accession,company,filing_url,extraction_error FROM filings WHERE extraction_error IS NOT NULL")]
        write_csv(OUT / "exceptions.csv",
                  ("accession", "company", "filing_url", "extraction_error"), exceptions)
        print(f"{len(rows)} candidates, {sum(r['review_status'] == 'approved' for r in rows)} approved, {len(exceptions)} exceptions")


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "ix:header"):
            self.hidden += 1
        if tag in ("p", "div", "tr", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "ix:header"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def scan_narrative():
    """Retrieve reviewable passages, never infer metrics/weights without a human."""
    terms = ("return on equity", "relative tsr", "performance net income roe",
             "performance shares", "annual cash bonus")
    results = []
    with connect() as con:
        for filing in con.execute("SELECT * FROM filings").fetchall():
            try:
                html = Path(filing["local_path"]).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            parser = VisibleText()
            parser.feed(html)
            lines = [clean(line) for line in "".join(parser.parts).splitlines()]
            lines = [line for line in lines if line]
            seen = set()
            for index, line in enumerate(lines):
                passage = clean(" ".join(lines[max(0, index - 1): index + 2]))[:1000]
                for term in terms:
                    if term in line.lower() and (term, passage) not in seen:
                        results.append({"company": filing["company"], "filing_date": filing["filing_date"],
                                        "filing_url": filing["filing_url"], "term": term,
                                        "evidence_passage": passage, "review_status": "needs_review"})
                        seen.add((term, passage))
    write_csv(OUT / "narrative_review_queue.csv",
              ("company", "filing_date", "filing_url", "term", "evidence_passage", "review_status"), results)
    print(f"{len(results)} narrative passages for review")


def seed_reference():
    """Load the source-checked demo rows into the same mart as live extraction."""
    with (ROOT / "data" / "verified_ceo.csv").open(newline="", encoding="utf-8") as stream, connect() as con:
        for row in csv.DictReader(stream):
            con.execute("""INSERT INTO filings(accession,company,cik,filing_date,filing_url,local_path)
              VALUES(?,?,?,?,?,?) ON CONFLICT(accession) DO NOTHING""",
              (row["accession"], row["company"], int(row["cik"]), row["filing_date"],
               row["filing_url"], ""))
            amounts = [money(row[field]) for field in FIELDS]
            if any(value is None for value in amounts) or abs(sum(amounts[:-1]) - amounts[-1]) > 1:
                raise ValueError(f"Invalid reference row: {row['company']} {row['pay_year']}")
            con.execute("""INSERT OR IGNORE INTO compensation
              (accession,row_number,executive,pay_year,salary,bonus,stock_awards,option_awards,
               non_equity_incentive,pension_change,all_other,total,raw_row,review_status,approval_method)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (row["accession"], -int(row["pay_year"]), row["executive"], int(row["pay_year"]),
               *amounts, "Reference: " + row["verification"], "approved", "manual_source_check"))


def verify_live():
    """A scheduled run cannot pass by exporting only the reviewed bootstrap sample."""
    with connect() as con:
        companies = {row[0] for row in con.execute("SELECT DISTINCT company FROM filings")}
        parsed = {row[0] for row in con.execute("""SELECT DISTINCT f.company FROM filings f
            JOIN compensation c USING(accession) WHERE c.row_number > 0 AND f.extraction_error IS NULL""")}
        if companies - parsed:
            raise ValueError(f"No live parsed DEF 14A for: {', '.join(sorted(companies - parsed))}")
        with (ROOT / "data" / "verified_ceo.csv").open(newline="", encoding="utf-8") as stream:
            references = list(csv.DictReader(stream))
        matched = []
        for reference in references:
            rows = con.execute("""SELECT * FROM compensation
                WHERE accession=? AND row_number>0 AND pay_year=? AND executive LIKE ?""",
                (reference["accession"], int(reference["pay_year"]), reference["executive"] + "%")).fetchall()
            if len(rows) != 1:
                raise ValueError(f"Expected one live CEO row for {reference['company']} {reference['pay_year']}; got {len(rows)}")
            row = rows[0]
            mismatched = [field for field in FIELDS
                          if (row[field] or 0) != (money(reference[field]) or 0)]
            if mismatched:
                raise ValueError(f"Live SEC values differ from reviewed reference for {reference['company']} {reference['pay_year']}: {mismatched}")
            matched.append(f"{reference['company']} {reference['pay_year']}")
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "live_validation.json").write_text(json.dumps({"matched_references": matched,
            "parsed_companies": sorted(parsed), "reference_count": len(matched)}, indent=2) + "\n", encoding="utf-8")
        print(f"Live SEC parser matched {len(matched)} source-checked CEO-year rows field by field")


def import_reviews(path):
    with connect() as con, path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            status = row["review_status"]
            if status == "needs_review":
                continue
            if status not in ("approved", "rejected"):
                raise ValueError(f"Invalid review_status: {status}")
            values = [money(row[field]) for field in FIELDS]
            if status == "approved" and (not row["executive"].strip() or
                                          not re.fullmatch(r"20\d{2}", row["pay_year"]) or
                                          values[-1] is None or
                                          abs(sum(value or 0 for value in values[:-1]) - values[-1]) > 1):
                raise ValueError(f"Incomplete approved record: {row['accession']}")
            result = con.execute("""UPDATE compensation SET executive=?,pay_year=?,salary=?,bonus=?,
              stock_awards=?,option_awards=?,non_equity_incentive=?,pension_change=?,all_other=?,total=?,review_status=?,approval_method='analyst'
              WHERE accession=? AND row_number=? AND raw_row=?""",
              (row["executive"], int(row["pay_year"]), *values, status, row["accession"],
               int(row["row_number"]), row["raw_row"]))
            if result.rowcount != 1:
                raise ValueError(f"Record not found or ambiguous: {row['accession']}")
    print("Reviews imported; run export again.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch").add_argument("--years", type=int, nargs="+", required=True)
    commands.add_parser("run").add_argument("--years", type=int, nargs="+", required=True)
    commands.add_parser("extract")
    commands.add_parser("export")
    commands.add_parser("scan-narrative")
    commands.add_parser("seed-reference")
    commands.add_parser("import-reviews").add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command == "fetch":
        fetch(set(args.years))
    elif args.command == "run":
        seed_reference()
        fetch(set(args.years))
        extract()
        verify_live()
        scan_narrative()
        export()
        from build_analysis import build
        build()
    elif args.command == "extract":
        extract()
    elif args.command == "export":
        export()
    elif args.command == "scan-narrative":
        scan_narrative()
    elif args.command == "seed-reference":
        seed_reference()
    else:
        import_reviews(args.path)
