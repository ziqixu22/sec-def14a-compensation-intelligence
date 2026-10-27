import unittest
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sec_comp
from sec_comp import candidates, money


class ParsingTest(unittest.TestCase):
    def test_summary_table_not_performance_table(self):
        html = """<p>Summary Compensation Table</p><table>
        <tr><th>Name and Principal Position</th><th>Year</th><th>Salary ($)</th><th>Stock Awards ($)</th><th>Option Awards ($)</th><th>Non-Equity Incentive Plan Compensation ($)</th><th>Change in Pension Value ($)</th><th>All Other Compensation ($)</th><th>Total ($)</th></tr>
        <tr><td>Jane CEO</td><td>2025</td><td>$1,000,000</td><td>$2,000,000</td><td>—</td><td>—</td><td>—</td><td>—</td><td>$3,000,000</td></tr>
        </table>"""
        rows = candidates(html)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total"], 3000000)
        self.assertIsNone(rows[0]["bonus"])

    def test_spans_and_carried_name_in_real_filing_shape(self):
        html = """<p>Summary Compensation Table</p><table>
        <tr><th colspan="3">Name and Principal Position</th><th colspan="3">Year</th>
        <th colspan="3">Salary ($)</th><th colspan="3">Bonus ($)</th>
        <th colspan="3">Stock Awards ($)(3)</th><th colspan="3">Option Awards ($)(4)</th>
        <th colspan="3">Non-Equity Incentive Plan Compensation ($)(5)</th>
        <th colspan="3">Change in Pension Value ($)(6)</th><th colspan="3">All Other Compensation ($)(7)</th>
        <th colspan="3">Total ($)</th></tr>
        <tr><td rowspan="2" colspan="3">Thomas J. Wilson Chair, President and Chief Executive Officer</td>
        <td colspan="3">2025</td><td colspan="2">1,465,385</td><td></td>
        <td colspan="2">—</td><td></td><td colspan="2">10,886,400</td><td></td>
        <td colspan="2">4,530,227</td><td></td><td colspan="2">5,597,235</td><td></td>
        <td colspan="2">—</td><td></td><td colspan="2">441,651</td><td></td>
        <td colspan="2">22,920,898</td><td></td></tr>
        <tr><td colspan="3">2024</td><td colspan="2">1,417,308</td><td></td>
        <td colspan="2">—</td><td></td><td colspan="2">11,899,608</td><td></td>
        <td colspan="2">4,736,259</td><td></td><td colspan="2">8,003,038</td><td></td>
        <td colspan="2">596,827</td><td></td><td colspan="2">91,255</td><td></td>
        <td colspan="2">26,744,295</td><td></td></tr></table>"""
        rows = candidates(html)
        self.assertEqual([r["pay_year"] for r in rows], [2025, 2024])
        self.assertEqual([r["total"] for r in rows], [22920898, 26744295])
        self.assertEqual(rows[1]["executive"], rows[0]["executive"])
        self.assertTrue(all(r["reconciled"] for r in rows))

    def test_compact_travelers_headers(self):
        html = """<p>Summary Compensation Table</p><table><tr>
        <th>Name andPrincipal Position</th><th>Year</th><th>Salary($)</th><th>Bonus($)</th>
        <th>StockAwards(1)($)</th><th>OptionAwards(2)($)</th>
        <th>Non-EquityIncentive PlanCompensation(3)($)</th><th>Change inPension Value($)</th><th>All OtherCompensation($)</th><th>Total($)</th></tr>
        <tr><td>Alan D. Schnitzer Chairman and Chief Executive Officer</td><td>2025</td>
        <td>1,450,000</td><td>—</td><td>9,417,364</td><td>6,100,056</td>
        <td>9,000,000</td><td>858,190</td><td>143,146</td><td>26,968,756</td></tr></table>"""
        self.assertEqual(candidates(html)[0]["total"], 26968756)

    def test_reference_import_is_idempotent_and_source_linked(self):
        old_db = sec_comp.DB
        with tempfile.TemporaryDirectory() as directory:
            sec_comp.DB = Path(directory) / "test.sqlite"
            try:
                sec_comp.seed_reference()
                sec_comp.seed_reference()
                with sec_comp.connect() as con:
                    self.assertEqual(con.execute("SELECT count(*) FROM filings").fetchone()[0], 2)
                    self.assertEqual(con.execute("SELECT count(*) FROM compensation").fetchone()[0], 6)
                    self.assertEqual(con.execute("SELECT count(*) FROM compensation WHERE review_status='approved' AND approval_method='manual_source_check'").fetchone()[0], 6)
            finally:
                sec_comp.DB = old_db

    def test_money(self):
        self.assertEqual(money("(1,500)"), -1500)
        self.assertIsNone(money("—"))
        self.assertIsNone(money("$abc"))


if __name__ == "__main__":
    unittest.main()
