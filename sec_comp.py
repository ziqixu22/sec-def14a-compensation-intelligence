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
FIELDS = ("salary", "bonus", "stock_awards", "option_awards", "non_equity_incentive", "all_other", "total")
EXPORT_FIELDS = ("accession", "row_number", "company", "filing_date", "filing_url", "executive", "pay_year", *FIELDS, "raw_row", "review_status")


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
                        "non_equity_incentive", "total"}
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
      non_equity_incentive REAL, all_other REAL, total REAL,
      raw_row TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'needs_review'
        CHECK(review_status IN ('needs_review','approved','rejected')),
      PRIMARY KEY(accession,row_number)
    );
    """)
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
    with connect() as con:
        for filing in con.execute("SELECT * FROM filings").fetchall():
            if con.execute("SELECT 1 FROM compensation WHERE accession=? LIMIT 1", (filing["accession"],)).fetchone():
                continue  # Preserve previous manual review.
            try:
                html = Path(filing["local_path"]).read_text(encoding="utf-8", errors="replace")
                rows = candidates(html)
                if not rows:
                    raise ValueError("No simple Summary Compensation Table candidate; inspect source manually")
                for number, row in enumerate(rows, 1):
                    con.execute("""INSERT INTO compensation
                      (accession,row_number,executive,pay_year,salary,bonus,stock_awards,
                       option_awards,non_equity_incentive,all_other,total,raw_row)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (filing["accession"], number, row["executive"], row["pay_year"],
                       *(row[field] for field in FIELDS), row["raw_row"]))
                con.execute("UPDATE filings SET extraction_error=NULL WHERE accession=?", (filing["accession"],))
                print(f"{filing['accession']}: {len(rows)} candidates (review required)")
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
          c.non_equity_incentive,c.all_other,c.total,c.raw_row,c.review_status
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
                                          values[-1] is None):
                raise ValueError(f"Incomplete approved record: {row['accession']}")
            result = con.execute("""UPDATE compensation SET executive=?,pay_year=?,salary=?,bonus=?,
              stock_awards=?,option_awards=?,non_equity_incentive=?,all_other=?,total=?,review_status=?
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
    commands.add_parser("extract")
    commands.add_parser("export")
    commands.add_parser("scan-narrative")
    commands.add_parser("import-reviews").add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command == "fetch":
        fetch(set(args.years))
    elif args.command == "extract":
        extract()
    elif args.command == "export":
        export()
    elif args.command == "scan-narrative":
        scan_narrative()
    else:
        import_reviews(args.path)
