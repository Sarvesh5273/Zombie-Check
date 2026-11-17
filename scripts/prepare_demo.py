#!/usr/bin/env python3
"""Prepare a reproducible public company-list input, never verdicts.

Downloads the yc-oss public API, selects a deterministic sample by public ID,
and exports only names, websites, batch, ID, and source URL. Directory status,
hiring, team size, descriptions, and activity dates are deliberately excluded.
This source is an input list; all signs of life must be checked separately.
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

SOURCE_URL = "https://yc-oss.github.io/api/companies/all.json"
SOURCE_REPOSITORY = "https://github.com/yc-oss/api"
SOURCE_DOCUMENTATION = "https://raw.githubusercontent.com/yc-oss/api/main/README.md"


def eligible_company(row, first_year, last_year):
    """Select on public list scope only, never alive/dead or hiring status."""
    batch = str(row.get("batch", ""))
    years = re.findall(r"\b(?:19|20)\d{2}\b", batch)
    if not years or not first_year <= int(years[-1]) <= last_year:
        return False
    categories = [str(row.get("industry", ""))] + list(row.get("industries") or [])
    if not any(category == "B2B" or category.startswith("B2B ->") for category in categories):
        return False
    name = str(row.get("name") or "").strip()
    website = str(row.get("website") or "").strip()
    parsed = urlparse(website)
    return bool(name and row.get("id") is not None and parsed.scheme in ("http", "https") and parsed.hostname and "." in parsed.hostname)


def select_companies(companies, count, first_year, last_year, seed):
    eligible = [row for row in companies if eligible_company(row, first_year, last_year)]
    if len(eligible) < count:
        raise ValueError(f"Only {len(eligible)} eligible public companies; cannot produce {count} real rows")
    # Hash rank is deterministic and does not correlate with directory status.
    ranked = sorted(eligible, key=lambda row: hashlib.sha256(f"{seed}:{row['id']}".encode()).hexdigest())
    selected = ranked[:count]
    # Output has natural public-ID order; the chosen set remains a hash sample.
    return sorted(selected, key=lambda row: int(row["id"])), len(eligible)


def make_csv(companies):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["company", "website", "yc_batch", "yc_id", "source_url"])
    for row in companies:
        writer.writerow([str(row["name"]).strip(), str(row["website"]).strip(), row["batch"], row["id"],
                         row.get("url") or SOURCE_REPOSITORY])
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="examples/yc-b2b-500.csv")
    parser.add_argument("--rows", type=int, default=500)
    parser.add_argument("--first-year", type=int, default=2019)
    parser.add_argument("--last-year", type=int, default=2026)
    parser.add_argument("--seed", default="zombie-check-bounty-2026-11-17")
    parser.add_argument("--source-file", help="Optional previously downloaded public API JSON; no network request")
    args = parser.parse_args()
    if args.rows < 1 or args.first_year > args.last_year:
        parser.error("Choose a positive row count and valid year range")
    if args.source_file:
        raw = Path(args.source_file).read_bytes()
    else:
        request = urllib.request.Request(SOURCE_URL, headers={"Accept": "application/json", "User-Agent": "ZombieCheck-demo-preparation/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read(30 * 1024 * 1024)
    source = json.loads(raw)
    if not isinstance(source, list):
        raise ValueError("Expected the public companies API to return an array")
    selected, eligible = select_companies(source, args.rows, args.first_year, args.last_year, args.seed)
    csv_text = make_csv(selected)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(csv_text, encoding="utf-8")
    provenance = {
        "name": f"YC B2B companies, {args.first_year}–{args.last_year}: deterministic {args.rows}-row sample",
        "source_url": SOURCE_URL,
        "source_repository": SOURCE_REPOSITORY,
        "source_documentation": SOURCE_DOCUMENTATION,
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "csv_sha256": hashlib.sha256(csv_text.encode()).hexdigest(),
        "source_company_count": len(source),
        "eligible_company_count": eligible,
        "exported_rows": len(selected),
        "selection": {"industry": "B2B", "first_batch_year": args.first_year, "last_batch_year": args.last_year,
                      "requires_public_website": True, "rank": "SHA-256(seed:public_yc_id)", "seed": args.seed,
                      "output_order": "public YC ID ascending"},
        "exported_fields": ["company", "website", "yc_batch", "yc_id", "source_url"],
        "excluded_fields": ["status", "isHiring", "team_size", "long_description", "one_liner", "launched_at"],
        "source_license": "No LICENSE file was found at repository root when checked on 2026-11-17. This export contains public factual names, URLs, batch labels and IDs only; no repository source code or company descriptions.",
        "notes": ["Source is a community maintained unofficial YC API, not an official YC status feed.",
                  "Directory data establishes the list to audit only; it must not determine any verdict.",
                  "No alive/dead, hiring, funding or latest-activity filter was used.",
                  "Raw source JSON is processed in memory and is not distributed with the demo."]
    }
    metadata_path = destination.with_suffix(".provenance.json")
    metadata_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({"csv": str(destination), "provenance": str(metadata_path), "rows": len(selected), "eligible": eligible,
                      "source_company_count": len(source), "csv_sha256": provenance["csv_sha256"]}))


if __name__ == "__main__":
    main()

