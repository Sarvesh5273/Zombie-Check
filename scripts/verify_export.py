"""Independent structural verification of an actual Zombie Check CSV export.

This does not fetch live pages or certify factual accuracy. It verifies original
cells/order/counts, required result fields, source structure, and report gates.
No data is uploaded. Default exit status is nonzero if any submission gate fails.
"""
import argparse
import csv
import datetime as dt
import io
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from zombiecheck.ingest import parse_csv

SIGNALS = ("blog", "release", "jobs", "social", "signup")
VERDICTS = {"alive", "slowing down", "zombie"}


def valid_source(url):
    parsed = urlparse(str(url or "").strip())
    return parsed.scheme in ("http", "https") and bool(parsed.hostname) and not parsed.username and not parsed.password


def added_column(output_headers, input_headers, name):
    candidate = name
    while candidate in input_headers:
        candidate = "zc_" + candidate
    return output_headers.index(candidate) if candidate in output_headers[len(input_headers):] else None


def verify(input_path, output_path, report_path=None, minimum_rows=500):
    parsed = parse_csv(Path(input_path).read_text(encoding="utf-8-sig"))
    input_headers, original_rows = parsed["headers"], parsed["rows"]
    output = list(csv.reader(io.StringIO(Path(output_path).read_text(encoding="utf-8-sig"))))
    issues = []
    if not output:
        return {"submission_structure_pass": False, "issues": ["Output CSV is empty"]}
    headers, rows = output[0], output[1:]
    original_width = len(input_headers)
    gates = {
        "at_least_500_rows": len(original_rows) >= minimum_rows,
        "row_count_preserved": len(rows) == len(original_rows),
        "original_headers_preserved": headers[:original_width] == input_headers,
        "original_cells_and_order_preserved": len(rows) == len(original_rows) and all(
            actual[:original_width] == expected for actual, expected in zip(rows, original_rows)),
        "output_headers_unique": len(headers) == len(set(headers)),
        "output_rows_have_correct_width": all(len(row) == len(headers) for row in rows),
    }
    required = ("row_id", "verdict", "latest_activity_date", "evidence_links", "review_required",
                "signals_checked", "signals_verified", "checked_at")
    required += tuple(f"{s}_{key}" for s in SIGNALS for key in ("status", "evidence_url", "verified"))
    columns = {name: added_column(headers, input_headers, name) for name in required}
    missing = [name for name, index in columns.items() if index is None]
    gates["required_columns_present"] = not missing
    if missing:
        issues.append("Missing result columns: " + ", ".join(missing))
    row_issues = []
    unique_ids = set()
    today = dt.datetime.now(dt.timezone.utc).date()
    if not missing:
        for position, row in enumerate(rows, 1):
            if len(row) != len(headers):
                row_issues.append({"row": position, "issues": ["Ragged output row"]})
                continue
            def get(key): return row[columns[key]]
            problems = []
            expected_id = "R%06d" % position
            if get("row_id") != expected_id:
                problems.append("Input row ID/order mismatch")
            if get("row_id") in unique_ids:
                problems.append("Duplicate input row ID")
            unique_ids.add(get("row_id"))
            if get("verdict") not in VERDICTS:
                problems.append("Missing or invalid verdict")
            if get("review_required").strip().lower() not in ("false", "0"):
                problems.append("Unresolved review")
            try:
                checks = int(get("signals_checked"))
                if checks < 4 or checks > 5:
                    problems.append("Expected at least four, and no more than five, completed signal checks")
            except ValueError:
                problems.append("signals_checked is not an integer")
            observed_sources = [get(f"{s}_evidence_url") for s in SIGNALS if get(f"{s}_status")]
            if len([u for u in observed_sources if valid_source(u)]) < 4:
                problems.append("Fewer than four signal checks have public source URLs")
            evidence = [u.strip() for u in get("evidence_links").split(" | ") if u.strip()]
            if not evidence or not all(valid_source(u) for u in evidence):
                problems.append("Verdict has missing or invalid evidence URLs")
            if not get("checked_at"):
                problems.append("Missing audit timestamp")
            date_text = get("latest_activity_date")
            if date_text:
                try:
                    actual_date = dt.date.fromisoformat(date_text)
                    if actual_date > today:
                        problems.append("Latest activity date is in the future")
                except ValueError:
                    problems.append("Latest activity date is not an ISO calendar date")
            if problems:
                row_issues.append({"row": position, "row_id": get("row_id"), "issues": problems})
    gates["every_row_has_verdict_checks_and_sources"] = not missing and not row_issues
    if report_path:
        report = json.loads(Path(report_path).read_text())
        gates["run_report_matches_row_count"] = report.get("input_rows") == len(original_rows) and report.get("output_rows") == len(rows)
        gates["run_report_submission_ready"] = report.get("submission_ready") is True
        gates["run_report_tinyset_used"] = report.get("gates", {}).get("tinyset_used") is True
        if not all(value is True for value in report.get("gates", {}).values()):
            issues.append("Run report has failed or unavailable submission gates")
    else:
        gates["run_report_supplied"] = False
        issues.append("Supply --report to verify TinySet use and the actual run's completion gates")
    for gate, passes in gates.items():
        if not passes:
            issues.append("Failed gate: " + gate)
    return {"submission_structure_pass": all(gates.values()), "input_rows": len(original_rows),
            "output_rows": len(rows), "gates": gates, "rows_with_issues": len(row_issues),
            "row_issues": row_issues[:100], "row_issues_truncated": len(row_issues) > 100,
            "issues": issues,
            "limitations": ["Source URLs are structurally checked, not fetched by this verifier.",
                            "A separate live spot-check must confirm dates, identity, and supporting quote accuracy."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report")
    parser.add_argument("--minimum-rows", type=int, default=500)
    args = parser.parse_args()
    result = verify(args.input, args.output, args.report, args.minimum_rows)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["submission_structure_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
