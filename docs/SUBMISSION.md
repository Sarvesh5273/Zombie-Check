# Zombie Check — submission package

## Working build and proof

Repository: https://github.com/Sarvesh5273/Zombie-Check

Primary demo: 500 distinct official job postings from Stripe, Datadog and Cloudflare. Input/provenance under examples/; completed CSV, evidence JSONL, run report, export verification and resume proof under artifacts/. Local recorded walkthrough and editable source are included under demo/ and artifacts/demo.mp4 when rendering completes.

Result recorded November 17, 2026: **500/500 verdicts,340 alive, 160 slowing down, 0 unresolved**. Each row has five checked categories and at least four verified observations. Original cells/order were independently verified.

“Slowing down” in job mode means a still-public posting first published over 90 days ago. It is a caution heuristic, not a claim that hiring intent is fake. Exact employer/role/intake and observed timestamps were independently reconciled against the 500 saved fresh sources.

## Build description

Zombie Check accepts company/tool/vendor or job CSVs, maps arbitrary headings, and returns the original spreadsheet with verdicts, dates, reasons, confidence and evidence columns. A source drawer distinguishes exact posting evidence, shared employer context, unavailable signals and actual rendered-control inspection.

SQLite checkpoints preserve original rows, source responses, results, remote TinySet IDs, progress and spending reservations. An interrupted run resumes without repeating completed rows or blindly recreating paid research. The real resume proof kept 490 finished results unchanged while the remaining ten finished.

## TinyFish use and endpoint scope

- TinySet researches 3 distinct employers in saved dataset 141b44ef-9950-4adb-81c8-3f779e06d94e. Exact name/domain reconciliation and fresh Fetch validation precede the join to 500 roles. Each role's availability/intake is checked independently.
- TinyFetch uses ttl=0 for official pages, full ATS boards and exact role details. Per-source errors and returned URLs remain available.
- TinySearch finds missing official changelogs and an exact Japanese route where language metadata was inconsistent. Search snippets are discovery only.
- TinyAgent's completed six-step run verified visible controls on Datadog posting 6009779's Japanese application page. No fields were filled or submitted.
- TinyBrowser inspects visible registration/control scopes, rejects newsletter-only forms, and records session cleanup. The Stripe job inspection was inconclusive because only a newsletter form was seen; it is not presented as successful application submission.

Search, Fetch, Agent and Browser performed meaningful work. Multiple TinySet routes are not counted as different scoring categories. Points and acceptance remain the judges' decision.

The TinySet scope is employer research shared across jobs, not 500 independent vacancy investigations. The bounty's “fill hundreds” wording may be interpreted more strictly; this is disclosed rather than hidden.

## Accuracy and edge cases

- Ten default-route 404s resolved to verified exact localized pages, with the originals retained.
- Complete official boards, role IDs, employers, title/canonical routes and intake definitions are reconciled.
- Blocks, timeouts, partial feeds and identity conflicts do not become proof of death.
- Application question configuration, visible controls and successful backend submission are separate observations.
- Blog-only closure and changelog code-example dates caused false claims during review; both were corrected and regression-tested.
- Company mode handles closure, parking, acquisitions and rebrands conservatively; its older 500 company experiment remains partial.
- Current job adapter: Greenhouse. Other ATS providers require an adapter and surface for review.
- The independent real Figma pilot uses custom headers and native URLs without supplied API/ID fields.

## Reproduction

```sh
git clone https://github.com/Sarvesh5273/Zombie-Check.git
cd Zombie-Check
export TINYFISH_API_KEY='your_personal_key'
python3 -m zombiecheck serve --port 8765
```

Upload examples/jobs-500.csv, select job mode, and map the supplied fields. Use a personal funded cap appropriate to current account allowances; saved proof files can be inspected without launching another audit.

```sh
python3 -m unittest discover -q
python3 scripts/verify_export.py --input examples/jobs-500.csv \
  --output artifacts/jobs-audited.csv --report artifacts/jobs-run-report.json
```

## Recorded walkthrough

Show the untouched 500-row input and mappings, actual completed ledger, row evidence, clean CSV export, and saved 490→500 resume comparison. The walkthrough represents a recorded audit, not a fabricated live run.

## Exact LinkedIn draft — approval required before posting

I built Zombie Check for the TinyFish bounty.

It takes a company or job CSV, checks live sources, and returns the original spreadsheet with verdicts, dates and evidence links.

The real demo audits 500 distinct official job posts: 340 alive and 160 slowing down, with no unresolved rows. “Slowing down” is a disclosed 90-day posting-age caution, not proof of a ghost vacancy.

TinySet researches each employer once; its sourced context is joined to the jobs while each posting and application configuration is checked separately. TinySearch and TinyFetch verify official sources; TinyAgent and TinyBrowser inspect difficult public forms without submitting anything.

The strongest part was recovery and evidence:490 completed results stayed unchanged when the remaining ten finished, and independent review reconciled all 500 posting IDs, employers, intake fields and dates.

Code, audited CSV and proof: https://github.com/Sarvesh5273/Zombie-Check

Tag the actual TinyFish company page when posting: https://www.linkedin.com/company/tinyfish-ai/

## Exact Discord #showcase draft — approval required before sending

**Zombie Check — live evidence for an old spreadsheet**

Build and proof: https://github.com/Sarvesh5273/Zombie-Check

500 distinct official job postings audited: 340 alive, 160 slowing down, 0 unresolved. Original cells/order preserved; five signal categories checked and at least four verified observations per row.

TinySet researches 3 employers once and shares verified context across their jobs. Exact posting availability/intake are checked independently. Search, Fetch, Agent and Browser contribute to source discovery, verification and difficult forms.

Includes audited CSV, full evidence, run/export reports, real 490→500 resume proof, and an independently mapped Figma pilot.

Limits: Greenhouse posting adapter;90-day age is a caution heuristic. Public posting/intake health cannot prove funded vacancies, recruiter intent or successful submissions.

## Submission checklist

- [x] Real 500-row completed CSV and original-preservation proof.
- [x] Evidence, dates, identity/intake checks and live-source review.
- [x] Resumability demonstrated on actual work.
- [x] Meaningful TinySet role and endpoint scope disclosed.
- [x] Budget below the chosen $5 ceiling, recorded as conservative allocations.
- [ ] Repository publication and walkthrough verified.
- [ ] User confirms individual/program eligibility and one submission per bounty.
- [ ] Exact LinkedIn copy approved/published with TinyFish tag.
- [ ] Exact Discord copy approved/shared to #showcase.
- [ ] Final bounty submission approved/sent and receipt verified.

The local report's submission_ready field means data gates passed. Social and final submission obligations remain separate.
