# Independent review — Zombie Check

Reviewed on 2026-11-17. This records observed risks and the proof still required. It is not an approval certificate.

## Current recommendation

Do not submit until a real 500-row run passes the strict export/report gates and its verdicts survive manual source checks. A 500-row CSV and passing fixture tests are not evidence of a finished 500-row live audit.

## Requirements and evidence

| Bounty requirement | Observed evidence | Remaining gate |
|---|---|---|
| Accept CSV or Google Sheet of at least 500 rows | CSV ingestion implementation; real `examples/yc-b2b-500.csv` prepared | Run this input end to end and verify original cells/order |
| Four signs of life checked for each row | Five signal categories implemented | Confirm actual per-row sources/checks in the live export, including unavailable signals |
| Same spreadsheet plus verdict, latest activity date and evidence links | Export implementation exists | Every row must have a defensible verdict; no missing rows, invented dates or contradictory evidence |
| Real list demonstration | Public yc-oss input with 500 company names/URLs and recorded provenance | Attach actual live output, source snapshots, run report and demo |
| Uses TinySet | Parent's live pilot returned three companies; structured URL discovery implemented | Record actual dataset IDs, returned/matched counts and exactly which rows TinySet researched |
| Evidence behind every verdict | Per-signal records and source URLs implemented | Spot-check subject, quotation, date and ownership; do not count a URL alone as proof |
| Live sources | TinyFetch client sends `ttl=0` | Preserve timestamps/raw responses; separate input-directory fields from live evidence |
| Redirects, acquisitions, rebrands, parked domains | Detection and identity logic implemented | Demonstrate old identity versus operating successor; parent-company activity must not rescue a dead product |
| Reliable 500+ completion and resume | SQLite checkpoints and saved remote dataset IDs implemented | Interrupt a real run, restart with the same audit ID, show no duplicate paid creation and no lost rows |
| Any input | Header mapping and stable row IDs implemented | Run a second independent input, including duplicates, same-name/different-domain entries and missing URLs |

## Concrete evidence risks sent to the implementation owner

The initial code review found the following; the owner is correcting them. Retest after changes rather than marking them fixed here from intent alone.

1. **Closure scope.** The initial `apply_identity_evidence()` accepted a company name anywhere on a page plus generic closure language elsewhere. A page discussing a retired feature or another company's closure could produce a false zombie. Match the original company/product and actual closure action in the supporting passage. “We are closing a funding round” is not company closure.
2. **Rebrand identity.** A mention of rebranding initially set `verified=true` without establishing the actual successor canonical domain. The redirect and identity announcement must agree, and successor activity must apply to the same product.
3. **Official signal ownership.** The initial URL discovery accepted arbitrary off-domain blog/careers links from a homepage. Partner blogs, portfolio pages, author profiles and unrelated repositories can be linked without being company-owned signals. Validate the ownership relationship and preserve its evidence.
4. **Signup false positives.** Newsletter copy or a homepage “Sign up” CTA cannot establish a functioning registration form. A browser check should identify the actual registration fields and enabled entry controls, without submitting data. Describe it as form availability unless backend account creation was actually tested.
5. **Signal independence.** Blog and release categories that cite the same page/date do not become two independent activity sources merely because two columns are populated. Show actual source coverage and avoid inflating confidence from duplicate observations.
6. **Dates.** Copyright/footer dates, privacy-policy effective dates, upcoming events and a date guessed from a month-only label cannot be the latest activity date. Date support must be in activity context and associated with the source being evaluated.
7. **Silent incompleteness.** A blank verdict or `review_required=true` is an unresolved row. Keep the honest review state, but do not claim it passes “a verdict on every row.” A full input-sized export alone does not prove full completion.

## TinySet scope and minimum-cost tradeoff

Official TinySet documentation currently lists 250 rows per dataset, ten columns including the key, and three active runs per account. It does not document a CSV row-write/import endpoint. The integration therefore supplies an exact entity manifest, reconciles returned names/domains, and verifies returned URLs. The parent pilot showed that instruction-following and identity mapping cannot be assumed.

The literal submission requirement is **“Uses TinySet, with a short explanation of how it is used.”** It does not explicitly require every original row to be a TinySet-generated row. However, the brief also says **“Fill in the signs of life for hundreds of rows at once, every value with its source”** and **“Use TinySet for this one.”**

**Assessment:** a meaningful TinySet triage stage is a reasonable interpretation of the literal requirement, but approval under the broader brief is uncertain. Do not call a small triage run “TinySet enrichment of all 500 rows.” Disclose the exact count and role. If hundreds of TinySet-researched entities are required by the organizers, the $5 cap conflicts with the recorded $0.10/row rate; 200 TinySet entities cost $20 and 500 cost $50 before other services. Do not disguise grouped entities, duplicate rows or padded usage to evade pricing/scoring.

## Endpoint-scoring caution

The supplied rulebook enumerates **Search, Fetch, Agent, Browser and Monitor** for points. TinySet is mandatory on this special bounty but is not listed in that generic endpoint parenthetical. Do not assume TinySet automatically counts toward the tier, and do not count dataset create/get/rows routes as separate meaningful endpoint categories.

A useful additional Browser stage can inspect real signup forms; an Agent stage can handle dynamic/ambiguous flows. Those can contribute meaningfully if actually used and recorded. A Monitor does not help a one-time spreadsheet audit merely by being invoked, and padding it should be avoided.

## Real input provenance

Prepared `examples/yc-b2b-500.csv` on 2026-11-17 from:

- Public companies JSON: https://yc-oss.github.io/api/companies/all.json
- Community API repository: https://github.com/yc-oss/api
- Source documentation: https://raw.githubusercontent.com/yc-oss/api/main/README.md

The fetched source contained 6,398 publicly listed companies; 2,520 met the input scope (B2B, 2019–2026 batch year, name and public website). The sample uses SHA-256 ranking of the fixed seed and public YC ID and exports the first 500 by that rank, then sorts the chosen set by public YC ID. This chooses the list independently of known status/hiring labels.

Exported fields are `company`, `website`, `yc_batch`, `yc_id` and `source_url`. No source status, hiring, team size, description or activity date is passed to the classifier. The raw source is processed in memory and is not distributed. A GitHub root-directory read on 2026-11-17 found no LICENSE file. This local demo copies factual list fields only, not repository source code or company descriptions.

`examples/yc-b2b-500.provenance.json` records retrieval time, exact source and CSV SHA-256, scope and field exclusions. Reproduce with:

```sh
python3 scripts/prepare_demo.py
```

Re-fetching a changing source can yield a changed sample; the included CSV and its hash identify the demonstrated input snapshot.

## Manual review set before claiming completion

- Ten deterministic sampled rows, selected before examining their verdicts.
- Every zombie and every acquisition/rebrand/parked-domain verdict.
- Every contradictory source, unsupported date, missing/blocked page and same-name mismatch.
- At least one completed row before and after the real interruption test.
- Signup examples: actual registration form, newsletter-only CTA, retired product redirect, blocked page.

For each reviewed row, record input identity, verdict, source URLs, observed supporting passages, activity-date support, signal coverage and accept/correction status in the final run artifacts. Never edit a verdict merely to satisfy a count gate.

