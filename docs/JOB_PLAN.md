# Additional 500-job demonstration plan

Prepared 2026-11-17. This adds a job-post demonstration; it does not replace the existing company-list app or erase its audit findings.

## Feasibility finding

**[Certain] Three official public Greenhouse boards supplied 1,648 unique postings at retrieval.** A deterministic 500-row input is now saved as `examples/jobs-500.csv`, with `examples/jobs-500.provenance.json`.

| Employer | Public board token | Postings at retrieval | Rows selected |
|---|---|---|---|
| Stripe | `stripe` | 794 | 167 |
| Datadog | `datadog` | 380 | 167 |
| Cloudflare | `cloudflare` | 474 | 166 |
| Total | | 1,648 | 500 |

Public feed and metadata requests completed at `2026-11-17T11:37:07.629575+00:00`. The returned board metadata names matched the employers. Counts can change after this timestamp; the included CSV/hash identifies the demonstrated source snapshot.

**[Likely] This is the lowest-cost useful additional track:** employer blog/release/social context can be researched once per employer and joined to its jobs, while each job's availability and application configuration are checked independently. Three employer rows at the recorded TinySet rate cost approximately $0.30 before optional browser/agent checks; the actual bill must be measured. This is meaningful shared evidence, not 500 duplicate TinySet rows or a claim that three requests independently researched 500 unique vacancies.

## Source and public API contract

Primary documentation fetched fresh: https://developers.greenhouse.io/job-board.html . The documented public GET endpoints expose published job lists and job details. Only application submission POST requires Basic Auth; this workflow must never call that POST.

| Read | Public endpoint |
|---|---|
| Board metadata | `GET https://boards-api.greenhouse.io/v1/boards/{token}` |
| Published jobs | `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` |
| Exact posting and intake questions | `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{id}?questions=true` |

Confirmed feeds:

- https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true
- https://boards-api.greenhouse.io/v1/boards/datadog/jobs?content=true
- https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs?content=true

Official careers pages were also fetched fresh during source discovery:

- https://stripe.com/careers
- https://careers.datadoghq.com/
- https://www.cloudflare.com/careers/

The fifth/last primary-source Fetch URL in this discovery pass was a real selected Stripe detail:

https://boards-api.greenhouse.io/v1/boards/stripe/jobs/8236491?questions=true

**[Certain] That response identified Stripe job 8236491, “Specialist Solutions Architect, Crypto,” with `company_name=Stripe`, a first-published timestamp of `2026-10-02T12:06:44-04:00`, an administrative updated timestamp of `2026-11-12T10:24:09-05:00`, and sixteen application question definitions.** Required questions included name, email, phone and resume/CV. This is a public read of question definitions; no candidate information was supplied or collected.

## What the input contains

The original CSV columns are:

`employer,title,job_url,job_id,employer_website,board_url,job_api_url,source_url,listed_updated_at`

- `job_id` is an immutable composite key: `greenhouse:{board_token}:{posting_id}`.
- `job_url` is the exact public posting URL returned by the employer's feed; some employers host their own frontend with a `gh_jid` query parameter.
- `board_url` is the official employer careers entry used for discovery/provenance.
- `job_api_url` points to the exact public detail/questions endpoint for later fresh checks.
- `source_url` identifies the original official listing feed.
- `listed_updated_at` records the feed's observed administrative timestamp. It must not be treated as proof of fresh hiring intent or a newly created role.

Selection is round-robin across SHA-256-ranked postings within each employer. It uses a fixed seed plus provider/token/job ID, not age, status, known vacancy intent or a desired verdict. The script requires 500 actual unique IDs and fails rather than filling with fabricated rows. Source descriptions are processed in memory and are not included in the distributed input.

Reproduce from the repository root:

```sh
python3 scripts/prepare_jobs.py
```

Inspect live feed availability without writing a CSV:

```sh
python3 scripts/prepare_jobs.py --probe
```

The default employers are example-source configuration only. `--boards-json path.json` accepts a JSON array of `{employer, token, website, careers_url}` for other Greenhouse employers. Job-audit runtime must parse the supplied posting/provider identity and support arbitrary input mappings rather than hardcoding these three employers.

## Proposed additional workflow

1. **Preserve input.** Import the nine columns unchanged, assign immutable local row IDs, and explicitly select a jobs mode. Keep the existing company mode available.
2. **Group employer context.** Derive employer identity from each supplied website and official ATS metadata. Reject conflicting employer/token names or same-name organizations without evidence.
3. **Research context with TinySet.** For each unique employer, obtain exact official blog/news, release/changelog, social/repository and identity URLs/dates. Persist the dataset/run IDs. Join those results to that employer's postings with shared-source IDs and check times.
4. **Verify contextual pages fresh.** Fetch the cited pages with TinyFetch `ttl=0`, check ownership and date support, and store the actual page observations once within the audit. Every inherited cell should retain its source URL/time and be labeled employer context.
5. **Verify each posting fresh.** Fetch the exact job API/page. Match posting ID, employer, title and canonical URL to the original. A generic careers page or another role cannot substitute for that posting.
6. **Inspect application intake independently.** Fetch `questions=true` for every posting and record configured question/control definitions. Where necessary, use Browser/Agent to inspect the actual rendered application flow without filling/submitting forms. A question schema alone does not prove the rendered form or backend acceptance works.
7. **Evaluate availability/age.** Compare the exact posting to the employer's newly fetched published list, detect explicit closed/removed/no-longer-accepting notices, and record first-published/admin-update dates separately. Handle expired deadlines, evergreen pools and renamed job titles without inferring intent.
8. **Checkpoint all levels.** Persist employer research and each job's verification separately. On restart, reuse completed work and remote IDs; retry only unresolved steps with bounded backoff. No duplicate paid dataset creation.
9. **Export and review.** Return the same 500 rows with verdict, actual activity dates, per-signal sources, rationale/confidence, posting status, intake scope, employer-context fields and review state. Demonstrate resume and run a second independent input.

## Four signals per posting — honest interpretation

Recommended recorded signal groups:

| Signal | Scope | What it can establish |
|---|---|---|
| Exact role still publicly listed | Job-specific | Employer ATS still serves this posting ID/title |
| Application intake configuration | Job-specific | Questions/entry are present; optional browser inspection establishes visible controls |
| Employer blog/news activity | Shared employer context | Recent public company communication |
| Employer release/changelog activity | Shared employer context | Recent product/developer operation |
| Official social/repository activity | Shared employer context | Recent public company/developer activity, when verifiable |
| First-published and update history | Job-specific | Observable posting age/change; no automatic intent conclusion |

**[Likely] Shared employer context can count as distinct life-signal categories for a job row when clearly labeled and joined with its original source.** However, employer activity does not prove that a particular vacancy is real. The posting availability and application checks are mandatory per job; four employer URLs copied into every row would be an inadequate ghost-job detector.

Board membership and exact job detail are corroboration of the same availability signal, not two independent signals just because they use two endpoints. A questions schema and visible form are complementary intake evidence, not proof that an application would be accepted or read.

If any category is unavailable, record what was checked and why; do not inflate successful coverage with a generic homepage or make a failed request count as affirmative evidence. Preserve review state until the run's promised coverage is actually achieved.

## Verdict scope for jobs

The labels must describe **public posting health**, not claim privileged knowledge of recruiter intent:

- **Alive:** the exact posting remains available through its official source and intake is observably configured/reachable, with supporting context. State that real vacancy/funding/response intent is unverified.
- **Slowing down:** the posting remains public but activity/age/intake evidence warrants caution or review. Age alone is not proof of a ghost job; evergreen and talent-pool posts may be intentional.
- **Zombie:** explicit closed/removed/no-longer-accepting evidence, or the exact ID is absent from a healthy official board and its detail is missing after appropriate retries. An employer may remain alive while a posting is dead.
- **Unresolved:** blocked/mismatched/contradictory sources stay reviewable. Do not silently coerce them to zombie to satisfy a count requirement.

A publicly listed role **does not prove** a funded headcount, a recruiter reviewing applications, a forthcoming hire or a non-ghost vacancy. Do not market this demonstration as definitively detecting hidden hiring intent. It can detect stale/closed/broken public postings and expose evidence-based warning signals.

## TinySet compliance risk

The bounty explicitly accepts job-post/ghost-job inputs. It literally requires using TinySet with an explanation, and broader wording asks TinySet to fill signs of life for hundreds of rows. A relational enrichment of 500 job rows from three shared employer records is efficient and meaningful, but acceptance of that interpretation is a judging question. Disclose the three researched employers and all independent per-job checks. Do not say TinySet independently investigated 500 vacancies, manufacture 500 duplicate employer rows, or claim a new scoring endpoint for repeated dataset routes.

If the organizers require one paid TinySet row per job, this low-cost approach does not meet that additional requirement. Preserve the limitation explicitly; do not pad usage to hide it.

## Demonstration and exit gates

- [x] Real 500-row input from official public feeds, 500 distinct posting keys, neutral selection and provenance.
- [x] Primary API/docs and one real job/questions response confirmed.
- [ ] Jobs-mode runtime accepts the original CSV and arbitrary mapped/provider-compatible inputs.
- [ ] TinySet employer research performs meaningful work and records actual dataset IDs/counts.
- [ ] Every exact posting independently rechecked live.
- [ ] At least four genuine signal categories/checks per job recorded with source and scope.
- [ ] Application/intake assertions precisely supported; no forms submitted or candidate information collected.
- [ ] Same input/output rows, original columns/cells/order retained.
- [ ] Full output has defensible verdicts and honest confidence/review states.
- [ ] Closed posting and redirect/intake failure examples demonstrated from real evidence; no fabricated source fixtures presented as live data.
- [ ] Real interrupt/resume proof preserves employer and job checkpoints.
- [ ] Independent spot checks pass, including stale/closed/evergreen or same-name edge cases.
- [ ] Final endpoint usage, costs and TinySet fan-out scope accurately documented.

**[Certain] The prepared input and API feasibility checks are not the completed 500-row audit.** Implementation and live verification remain with the main build owner; this reviewer has not modified the company app or saved audit.

