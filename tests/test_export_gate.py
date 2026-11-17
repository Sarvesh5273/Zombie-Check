"""Structural-verifier fixture tests; no live-data claims or paid calls."""
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_export import verify
from tests.test_core import csv_text, result_fixture
from zombiecheck.ingest import export_csv, map_rows, parse_csv


class ExportGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = csv_text([["Fixture Company %d" % i, "https://c%d.example" % i, "Original %d" % i]
                           for i in range(500)])
        parsed = parse_csv(source)
        rows = map_rows(parsed, 0, 1)
        for row in rows:
            row.update(status="done", result=result_fixture())
        self.original = self.root / "input.csv"
        self.output = self.root / "output.csv"
        self.report = self.root / "report.json"
        self.original.write_text(source)
        self.output.write_text(export_csv(parsed["headers"], rows))
        self.report.write_text(json.dumps({"input_rows": 500, "output_rows": 500,
            "submission_ready": True, "gates": {"tinyset_used": True}}))

    def tearDown(self):
        self.temp.cleanup()

    def gate(self):
        return verify(self.original,self.output,self.report)

    def mutate(self,change):
        data=list(csv.reader(io.StringIO(self.output.read_text())))
        change(data)
        out=io.StringIO(newline="")
        csv.writer(out).writerows(data)
        self.output.write_text(out.getvalue())

    def test_structurally_valid_500_fixture_is_valid(self):
        self.assertTrue(self.gate()["submission_structure_pass"])
        self.assertIn("not fetched",self.gate()["limitations"][0])

    def test_changed_original_cell_fails(self):
        self.mutate(lambda data: data[250].__setitem__(0,"Substituted company"))
        self.assertFalse(self.gate()["gates"]["original_cells_and_order_preserved"])

    def test_missing_row_fails(self):
        self.mutate(lambda data:data.pop())
        self.assertFalse(self.gate()["gates"]["row_count_preserved"])

    def test_missing_verdict_fails(self):
        def change(data):data[1][data[0].index("verdict")]=""
        self.mutate(change)
        self.assertFalse(self.gate()["submission_structure_pass"])
        self.assertEqual(self.gate()["rows_with_issues"],1)

    def test_missing_source_urls_fail(self):
        def change(data):
            for kind in ("signup","blog"):
                data[1][data[0].index(kind+"_evidence_url")]=""
        self.mutate(change)
        self.assertFalse(self.gate()["submission_structure_pass"])

    def test_false_run_report_fails(self):
        self.report.write_text(json.dumps({"input_rows":500,"output_rows":500,"submission_ready":False,"gates":{"tinyset_used":True}}))
        self.assertFalse(self.gate()["submission_structure_pass"])


if __name__=="__main__":unittest.main()
