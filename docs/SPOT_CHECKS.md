# Evidence review — Zombie Check

## Completed 500-job audit

**[Certain] The exported job audit contains 500 distinct original postings, 500 completed verdicts and at least four verified signal observations on every row.** The company audit recorded later in this document is a separate, incomplete diagnostic. It is not the 500-row completion proof.

**[Likely] Bounty acceptance still depends on how judges interpret TinySet's scope and application operability.** TinySet researched three employers. Their sourced context is joined to 500 independently checked roles. The bulk intake check establishes an exact posting's public application-question configuration. It does not prove backend acceptance, funded headcount or recruiter attention.

- Audit ID: `857949de-0d18-4951-9598-cef63cba4e55`.
- Input: [jobs-500.csv](../examples/jobs-500.csv), with [input provenance](../examples/jobs-500.provenance.json).
- Output: [jobs-audited.csv](../artifacts/jobs-audited.csv), with [row evidence](../artifacts/jobs-evidence.jsonl).
- Final report generated: **November 17, 2026, 12:47:28 UTC**.
- Source-review method: reread the final CSV, all 500 saved TinyFetch role responses, the context-refinement proof, and the recorded Agent/Browser observations. These source responses were fetched live during this audit using `ttl=0`. This final review did not refetch them or incur additional paid usage.

### Independent checks

| Check | Result | Evidence |
|---|---:|---|
| Input and output data rows | 500 / 500 | Direct CSV readback |
| Distinct composite provider/employer/job IDs | 500 | Direct input readback |
| Original headers, cells and row order preserved | Pass | Direct CSV readback with UTF-8 BOM handling |
| Completed row states | 500 | Final JSONL readback |
| Verdict distribution | 340 alive; 160 slowing down; 0 zombie | Final JSONL readback |
| Verified observations per row | 167 rows have 5; 333 rows have 4 | Independently counted `verified=true` signal records |
| All five signal kinds attempted | 500 / 500 | Final JSONL readback |
| Saved live detail response exists | 500 / 500 | Stored TinyFetch source readback |
| Top-level posting ID matches the original ID | 500 / 500 | Parsed source `id`, excluding nested metadata IDs |
| Source employer matches the original employer | 500 / 500 | Parsed source `company_name` |
| Intake includes first name, last name and email fields | 500 / 500 | Parsed top-level `questions[].fields[]` |
| Exported latest activity matches source update date | 500 / 500 | Parsed `updated_at` compared with output date |
| Original publication timestamp matches saved role age source | 500 / 500 | Parsed `first_published` compared with saved timestamp |
| Complete original-row preservation after resume | Pass | [jobs-resume-proof.json](../artifacts/jobs-resume-proof.json) |
| Previously completed results preserved during resume | 490 / 490 | Same resume proof, before optional inspection/context enrichment |
| Final structural export verification | Pass; zero row issues | [jobs-export-verification.json](../artifacts/jobs-export-verification.json) |

The structural export verifier does not refetch source URLs. Source identity and dates were checked separately above. Passing the application's `submission_ready` field is not a TinyFish team approval.

### What the signals mean

| Signal | Checked scope | Evidence and limit |
|---|---|---|
| Jobs | Each exact role | Official board membership plus matching detail ID, employer and URL |
| Signup/intake | Each exact role | Public ATS question definitions for that ID; rendered control/backend operability remains separate |
| Blog | Shared employer context | Official article/index with verified dated activity |
| Release | Shared employer context | Official changelog with verified dated activity |
| Social/developer activity | Shared employer context | Official ownership and dated activity required; Datadog/Cloudflare observations remain unknown where ownership was not verified |

**[Certain] All 500 rows have individually checked jobs and intake observations, plus verified employer blog and release observations.** Stripe's 167 rows additionally have verified official GitHub activity. The 333 Datadog/Cloudflare rows retain attempted, unverified social observations without counting them as verified.

The input has **167 Stripe**, **167 Datadog** and **166 Cloudflare** roles. TinySet dataset `141b44ef-9950-4adb-81c8-3f779e06d94e` matched all three employers. It produced employer source candidates, which TinyFetch subsequently verified. The export's `tinyset_scope` and individual signal `scope`/`shared` fields disclose this join. It should not be described as 500 TinySet vacancy records.

### Representative exact-role source checks

The dates below come from each role's freshly fetched ATS record. Every selected record contains exact-role application field definitions. Links point to the actual detail evidence and resolved public page.

| Row | Employer and exact ID | First published | Latest role update | Verdict | Sources |
|---|---|---|---|---|---|
| R000001 | Stripe 8236491 | October 2, 2026 | November 12, 2026 | Alive, age 45 days | [Detail/intake](https://boards-api.greenhouse.io/v1/boards/stripe/jobs/8236491?questions=true), [resolved role page](https://stripe.com/careers/listing/specialist-solutions-architect-crypto/8236491?gh_jid=8236491) |
| R000002 | Datadog 6512321 | January 7, 2025 | November 5, 2026 | Slowing down, age 678 days | [Detail/intake](https://boards-api.greenhouse.io/v1/boards/datadog/jobs/6512321?questions=true), [role page](https://careers.datadoghq.com/detail/6512321/?gh_jid=6512321) |
| R000003 | Cloudflare 8059775 | July 14, 2026 | November 13, 2026 | Slowing down, age 125 days | [Detail/intake](https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs/8059775?questions=true), [resolved role page](https://job-boards.greenhouse.io/cloudflare/jobs/8059775?gh_jid=8059775) |
| R000059 | Datadog 8206923 | September 17, 2026 | November 5, 2026 | Alive, age 61 days | [Detail/intake](https://boards-api.greenhouse.io/v1/boards/datadog/jobs/8206923?questions=true), [Korean role page](https://careers.datadoghq.com/ko/detail/8206923/?gh_jid=8206923) |
| R000329 | Datadog 8113562 | August 7, 2026 | November 5, 2026 | Slowing down, age 102 days | [Detail/intake](https://boards-api.greenhouse.io/v1/boards/datadog/jobs/8113562?questions=true), [Japanese role page](https://careers.datadoghq.com/ja/detail/8113562/) |

**[Certain] “Slowing down” in job mode is the disclosed >90-day original-publication heuristic.** It flags an old public advertisement. The 160 flags do not establish 160 ghost vacancies. A later administrative `updated_at` timestamp or recent employer article does not reset the original posting age. The row's `latest_activity_date` records that role update, while employer activity dates remain in their own columns.

### Redirect and locale findings

- **Stripe R000001:** the original `jobs/search?gh_jid=8236491` URL redirects to a careers listing retaining exact ID 8236491 and its title, “Specialist Solutions Architect, Crypto.”
- **Cloudflare R000003:** `boards.greenhouse.io` redirects to `job-boards.greenhouse.io` with employer and exact posting ID retained. Source title differs from the input only by trailing whitespace. The misleading title-change note was removed in the final export.
- **Datadog R000059:** the default route returned 404. The exact ATS response supplies language `ko`; its Korean route contains the same ID, title “Customer Success Manager,” and Seoul location. The original failure remains recorded.
- **Datadog R000329:** both the default and metadata-derived English route returned 404. TinySearch found the actual Japanese route; TinyFetch confirmed exact ID 8113562, title “Regional Manager, Sales Engineering - Public Sector,” and Tokyo. The source metadata still says `en`; the successful route came from Search, not correct language metadata. Both missing-route observations and the discovery trail remain in the evidence.

### Employer date refinements

- **Datadog blog:** the undated index was followed to the actual linked [Auto-Processing article](https://www.datadoghq.com/blog/auto-processing-log-pipelines/). Fresh page metadata records **November 16, 2026**. A sample log date in the article is not used as publication activity.
- **Cloudflare release:** the live [changelog](https://developers.cloudflare.com/changelog/) contains dated **November 16, 2026** entries, agreeing with publication metadata. Its code examples contain `compatibility_date: 2026-11-17`; that example date was rejected as release activity.
- **Stripe release:** the source index was followed to the linked [documentation changelog](https://docs.stripe.com/changelog), containing the actual version heading `2026-10-28.endive`. Latest dated release found here is **October 28, 2026**.
- **Stripe developer activity:** the [official GitHub profile](https://github.com/stripe), linked from the employer site, shows repository updates on **November 17, 2026**. This indicates developer activity, without establishing vacancy intent.

The [context-refinement proof](../artifacts/context-refinement-proof.json) records **500 enhanced rows**, **zero new datasets**, **zero role API refetches**, and **unchanged role core data**. These dates are the latest activity found in the inspected sources, not a claim of exhaustive company-wide newest activity.

### Final evidence-display corrections

**[Certain] The final export removes 32 whitespace-only title-change notes without changing any verdict.** The source's original text is still retained. A final readback found zero remaining title-change notes in this demo.

The initial ATS snippets sometimes began at nested metadata IDs or demographic questions. Final job excerpts now expose the actual top-level posting ID, employer, title, canonical URL and timestamps. Final intake excerpts expose the exact posting ID, top-level question count and applicant question labels. Readback of R000001, R000002, R000003 and R000329 confirms these corrections. The original source responses remain available for full inspection.

### Rendered application inspections

- [Agent inspection](../artifacts/job-agent-verification.json): exact Datadog role **6009779**, “Customer Success Associate,” resolved to the Japanese route. On November 17, 2026, the Agent observed actual applicant fields including name, email, phone and resume upload. This is a targeted rendered-form observation for one role, not evidence for every Datadog form.
- [Browser inspection](../artifacts/job-browser-verification.json): exact Stripe role **8236491** was visited. Only a newsletter email form was observed. The app correctly retained `verified=false`; this does not verify a role-specific rendered application form. The browser session was closed.

Both inspections left fields empty and submitted no applications. Bulk role intake remains labeled **“ATS question configuration only”** unless a separately recorded rendered observation supports more.

### Limits that must remain in the submission

1. This completed demonstration covers **500 real jobs at three employers**. The 500-company run remains incomplete.
2. The job adapter supports arbitrary Greenhouse-compatible inputs. Other ATS formats require additional adapters; “works on any job board” would overstate support.
3. The demo has no real zombie verdicts. Closed/removed-job logic is exercised by regressions, and the historical company diagnostic contains real closure/parking evidence, but neither is a completed real 500-row zombie-discovery run.
4. Public application configuration and a rendered form do not prove successful backend submission or genuine vacancy intent.
5. TinySet scope and shared evidence are disclosed. Whether that meets the bounty's intended hundreds-of-rows TinySet expectation is a judging uncertainty.

## Historical company diagnostic

The following section preserves the earlier six-company findings and its original status/time. Later fixes and the completed job proof do not retroactively certify this company audit.

Audit ID: `967f3deb-4210-4fd1-95b5-a7423b03bcbf`  
Input: `examples/yc-b2b-500.csv`  
Rules inspected: **1.2**  
Selection/read date: **2026-11-17**  
Fresh TinyFetch request started: **2026-11-17T11:16:16.183Z**  
Fresh TinyFetch request finished: **2026-11-17T11:16:34.430Z**  
Request: `ttl=0`, ten cited URLs, nine fetched pages and one explicit 404.

## Council finding

**[Certain] The sampled results contain material evidence errors and a missed discontinuation notice. Do not treat this as a completed or validated 500-row audit.** The saved selection showed 17 done, 22 review and 461 pending rows; the run was paused. Six actual nonblank verdicts were selected across alive, slowing down, zombie and acquisition states, preferring rules version 1.2. This is a targeted diagnostic sample, not a random accuracy estimate.

No audit records, verdicts or backend files were edited by this reviewer. No paid TinySet, Browser, Agent or Research calls were made. The correction findings were sent to the implementation owner immediately after the saved-data inspection and again after fresh source reads.

## Row findings

### R000003 — Pengram

- Original identity: **Pengram**, `http://pengramar.com`; input position 3.
- Saved conclusion: **zombie**, high confidence; reason: “Explicit closure/discontinuation evidence.” Checked at `2026-11-17T11:10:37.356650+00:00`.
- Cited evidence: live YC profile at https://www.ycombinator.com/companies/pengram and an unavailable original homepage.
- **[Certain] Observed now:** the YC profile names Pengram, links `http://pengramar.com`, and states **“Status:Inactive”**. Fresh Fetch of the homepage returned `page_not_found`, HTTP 404.
- **[Likely] Assessment:** these support corroborated inactivity of the original listing. They do not constitute an explicit shutdown announcement, and a 404 cannot prove there is no rebrand or successor. The saved reason overstates its evidence; lower confidence or perform identity follow-up before treating closure as confirmed.
- Latest activity date: empty; no verified dated activity was established in these sources. Keep it empty rather than copying a founding or audit date.

### R000004 — Comradery

- Original identity: **Comradery**, `https://comradery.com`; input position 4.
- Saved conclusion: **slowing down**, low confidence, review required. Checked at `2026-11-17T11:10:39.365081+00:00`.
- **[Certain] Observed now:** the original live homepage contains an explicit notice: **“Unfortunately, Comradery is no longer running”**. It describes considering open sourcing and suggests a different hosted community product.
- **[Certain] Correction needed:** the saved limited-activity interpretation misses direct original-product discontinuation evidence. The homepage staying reachable does not mean the hosted product operates. Evaluate the shutdown notice as such; the linked alternative is a recommendation, not an established rebrand/operating successor.
- Source: https://comradery.com ; fresh final URL remains the same.
- Latest activity date: empty. The homepage footer year is not a publication date for the shutdown notice.

### R000006 — Ascen

- Original identity: **Ascen**, `https://ascen.com`; input position 6.
- Saved conclusion: **alive**, medium confidence, latest activity `2026-11-03`. Checked at `2026-11-17T11:14:43.257573+00:00`.
- Cited activity: https://www.ascen.com/blog/pricing-staffing-agency-expanding-us-into .
- **[Certain] Observed now:** this is an Ascen-branded official article titled **“How To Price For Your Staffing Agency When Expanding Into the US”** and dated **November 3, 2026**.
- **[Likely] Assessment:** the alive conclusion is supported by recent official activity, and the exact saved activity date is supported. This spot check does not establish that it is the newest article anywhere, or confirm account registration/hiring.
- **[Certain] Source-display improvement:** the saved short quote contains the article headline but omits the date. Show the date/byline passage alongside the headline so a judge can verify the recorded date immediately.

### R000005 — DevFlight

- Original identity: **DevFlight**, `https://devflight.com`; input position 5.
- Saved conclusion: **slowing down**, low confidence/review required; identity **acquired_operating**, verified. Checked at `2026-11-17T11:10:41.394642+00:00`.
- Saved identity source: https://startups.fru.dev/companies/devflight .
- **[Certain] Observed now:** that third-party portfolio page describes DevFlight as inactive according to YC. Its acquisitions/status table concerns other companies, and its marketing excerpt uses “acquire” for JuziBot's customer activity. It does not establish an acquisition of DevFlight.
- **[Certain] Correction needed:** remove the verified-acquisition conclusion. Matching a company name anywhere on a long portfolio page plus a generic acquisition term elsewhere is not identity evidence.
- **[Certain] Observed on the original site:** https://devflight.com/ is reachable and describes security-playbook automation with an early-access signup list. The page also discusses shutting down servers as a product capability; that is not company closure.
- **[Likely] Assessment:** reachable marketing copy with limited verified activity can reasonably remain a review case. It does not prove active customers, working product onboarding or acquired-product continuity.
- Latest activity date: empty; no suitable dated original-company activity was established in these two pages.

### R000007 — Postscript

- Original identity: **Postscript**, `https://postscript.io`; input position 7.
- Saved conclusion: **alive**, medium confidence; reason relies on verified onboarding or hiring. Latest activity `2025-12-16`. Checked at `2026-11-17T11:14:43.829897+00:00`.
- Sources checked: https://postscript.io/careers and https://postscript.io/blog/onsite-opt-in-meets-alia-popups .
- **[Certain] Date check:** the cited official article has an explicit publication date **December 16, 2025**, and Fetch's publication metadata agrees. The date is correctly copied from that article, but this check cannot establish it is the latest company activity.
- **[Certain] Hiring gap:** the careers page says **“Learn more about our team and explore open roles.”** It contains team/benefit copy and links to `#grnhse_app` and a YC jobs page. The returned source contains no actual open-role listings or positive open-role count.
- **[Certain] Correction needed:** the CTA alone does not verify currently open jobs. Follow and verify the embedded ATS/listings before setting jobs active. Do not mark a company's hiring active merely because its careers navigation exists.
- **[Likely] Assessment:** Postscript may indeed be operating, but the saved alive rationale is not yet supported by the hiring evidence used. Keep the conclusion reviewable until an operational/recent source supports it.

### R000008 — Avalanche

- Original identity: **Avalanche**, `https://useavalanche.com`; input position 8.
- Saved conclusion: **zombie**, high confidence, reason: explicit closure; identity remains **same**. Checked at `2026-11-17T11:10:43.542302+00:00`.
- Saved closure source is a PC Gamer article about **Avalanche Studios**, the game developer, closing its Liverpool studio.
- **[Certain] Identity failure:** the article concerns a different organization sharing the name. It also describes office closure/layoffs and continued operations at other locations, not the original company's shutdown. Reject it as evidence for `useavalanche.com`.
- **[Certain] Fresh original-domain evidence:** https://useavalanche.com/ has a GoDaddy title naming the domain as for sale. The body identifies **“UseAvalanche.com”** followed by **“is for sale!”**, with purchase/lease options.
- **[Likely] Assessment:** a zombie/parked-original-domain result is supported by this parking evidence, but its current source/rationale is wrong. Set identity to parked using the exact domain-sale evidence, and remove the unrelated studios closure claim. No operating successor was established by these checks.
- Latest activity date: empty; the date of the unrelated studios article must not become activity for this original entity.

## Fresh source ledger

All requests below were part of the single fresh Fetch call at the timestamps above. A fresh read confirms what the page currently says; it does not make third-party status information current by itself.

| # | Requested URL | Final URL | Result |
|---|---|---|---|
| 1 | https://www.ycombinator.com/companies/pengram | https://www.ycombinator.com/companies/pengram | Fetched |
| 2 | http://pengramar.com | — | 404 page_not_found |
| 3 | https://comradery.com | https://comradery.com | Fetched |
| 4 | https://www.ascen.com/blog/pricing-staffing-agency-expanding-us-into | https://www.ascen.com/blog/pricing-staffing-agency-expanding-us-into | Fetched |
| 5 | https://devflight.com | https://devflight.com/ | Fetched |
| 6 | https://startups.fru.dev/companies/devflight | https://startups.fru.dev/companies/devflight | Fetched |
| 7 | https://postscript.io/careers | https://postscript.io/careers | Fetched |
| 8 | https://postscript.io/blog/onsite-opt-in-meets-alia-popups | https://postscript.io/blog/onsite-opt-in-meets-alia-popups | Fetched |
| 9 | https://useavalanche.com | https://useavalanche.com/ | Fetched |
| 10 | https://pcgamer.com/gaming-industry/2-months-after-halting-work-on-its-latest-project-just-cause-developer-avalanche-is-closing-its-liverpool-studio-and-laying-off-employees-in-malmo-and-stockholm | https://www.pcgamer.com/gaming-industry/2-months-after-halting-work-on-its-latest-project-just-cause-developer-avalanche-is-closing-its-liverpool-studio-and-laying-off-employees-in-malmo-and-stockholm/ | Fetched |

## Corrections to verify before resuming/claiming completion

1. Bind closure/acquisition passages to the exact original entity and relationship in the same local passage; same-name entities and unrelated sidebar rows must not qualify.
2. Recognize explicit original-product “no longer running” notices and parked-domain titles/body split over multiple lines.
3. Verify actual open jobs instead of a generic careers CTA; read the linked ATS/embedded source when available.
4. Use distinct confidence/rationale for corroborated directory inactivity versus explicit company/product closure.
5. Include the activity date's supporting passage in exported evidence, and keep “latest found” distinct from an exhaustive newest-activity claim.
6. Re-run the affected saved rows after fixes and retain this diagnostic snapshot as the before-state. Do not overwrite it into a passing report without repeating source review.

**[Certain] Full-run status remains unproven.** Only six selected saved conclusions and ten cited URLs were inspected. This document does not certify the remaining rows, four-signal coverage across all 500, full TinySet scope, successful resume, or bounty approval.

