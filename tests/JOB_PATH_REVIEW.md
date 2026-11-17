# Independent review: job-post audit path

This is a design review, not an implemented or completed job audit. It uses the bounty text supplied in chat and the current PLAN.md. No paid calls or live applications were made.

## Judgment

**[Certain] A present listing and reachable application form establish an operational advertisement/application intake. They do not establish an actual vacancy, hiring intent, or that submitted applications are reviewed.** Export and demo wording must preserve this distinction. “Ghost-job detector” is too strong unless the finding is explicitly limited to stale/closed/unavailable advertisements.

**[Likely] Employer research can legitimately be shared across 500 distinct real job IDs.** A company blog, release, and social check are facts about the employer; reuse their live evidence in each relevant row. Each exact job still needs its own listing and application checks. Preserve the original CSV, including duplicates, but a demonstration created by repeating a handful of job IDs does not prove meaningful 500-entity coverage.

**[Certain] The job-post option is allowed by the supplied bounty.** It does not remove the requirements for four live signal records per row, evidence-backed conclusions, reliable resume, arbitrary inputs, and meaningful TinySet use.

**[Likely] A TinySet employer-research stage is an honest minimum-cost architecture, but the broader “fill signs of life for hundreds of rows” expectation remains an approval risk.** Report the exact number of employers TinySet researched and the exact number of distinct roles inspected. Do not call employer joins “500 TinySet job rows” or package hundreds of unrelated entities into a string cell to evade per-row pricing.

## Evidence identity and record contract

Identity is `(verified employer/board identity, provider job ID)`, not title alone. Store original job URL, original ID, title, location, canonical role URL, verified official careers-to-ATS relationship, and any explicit migration/repost mapping. An ATS hostname alone is not sufficient to identify the employer.

Each signal records `status`, `source_url`, `checked_at`, supporting text or structured lookup, `verified`, and an actual observed activity date when available. Negative board evidence additionally records the searched exact ID, board scope, pagination completeness, page count, and snapshot reference/hash. Search snippets are discovery only.

## Required signal set

| Signal | Required live evidence | Can be shared? |
|---|---|---|
| Exact listing | Official role page/feed record matches employer and exact ID/title/location | No |
| Application intake | Role-specific apply route/form is reachable, belongs to that same job, and offers actual applicant fields | No |
| Role freshness | Documented posting/update field or publication metadata with an exact date and recorded semantics | No |
| Employer blog/news or release | Official source with verified activity/date; does not establish a vacancy | Yes |
| Employer social/developer activity | Official ownership plus source/date; does not establish a vacancy | Yes |

Check all five. A source with no published date can be recorded as checked/unknown, but must not be made active merely to hit a count. Employer careers/board evidence may be recorded additionally; do not count two copies of “this role exists” as independent signals. More employer signals cannot replace missing role identity/application checks.

## Decision order

| Priority | Exact condition | Verdict and interpretation |
|---|---|---|
| 1 | Employer/role identity unresolved, sources conflict, or required core checks blocked/incomplete | Withhold definitive verdict; `review_required=true`. Unresolved identity is not evidence of slowing. |
| 2 | Current official board is complete for all relevant locations/pages and exact ID is absent, plus the direct exact role returns terminal 404/410 or explicitly says closed/no longer accepting applications | `zombie`: the original advertisement is removed/closed. This is not proof the employer never intended to hire. |
| 3 | Exact listing and application intake remain operational; verified role posting/activity is over 90 days old | `slowing down`: stale advertisement flag. The 90-day threshold is a disclosed heuristic, not proof of a ghost job. |
| 4 | Exact listing and role-specific application intake both verified, without a stale-date trigger | `alive`: applications appear available. Unknown date lowers confidence and leaves the date blank; it does not manufacture recency. |
| 5 | Listing present but apply route broken/unavailable, or board absence cannot be proved completely | Review, not zombie. Do not collapse a form/transport problem into confirmed role closure. |

If the product must display one of the three labels for unresolved rows, mark it provisional with `review_required=true` and keep the submission-completion gate false. A definitive “slowing down” label for unresolved identity would invent a fact.

Keep actual posting date and updated date separately. An `updated_at` field, automated repost, or tracking URL must not erase original age without documented semantics. Use job-specific dated activity for the row's `latest_activity_date`; keep employer activity dates in their own columns so recent employer news cannot make an old job appear fresh. Never use audit date, copyright, or a future deadline as an activity date.

Before a negative verdict, obtain a fresh complete board snapshot close in time to the direct missing/closed check. Reused employer snapshots remain useful, but an old board snapshot cannot prove current absence. Store the observation window explicitly and refresh stale negative evidence.

## Regression matrix before implementation is called complete

1. Exact ID present + matching role form available → alive, with no claim of an actual vacancy.
2. Listing age 90 versus 91 days → disclosed boundary behavior; latest employer blog does not override role age.
3. Missing posting date → no invented date or recency.
4. Exact closed role + complete-board absence → zombie; source lookup and direct closure evidence retained.
5. Direct 404 + partial/truncated board → review, not zombie.
6. 403, bot block, timeout, login wall, malformed JSON, and temporary 5xx → never zombie.
7. Same title with different IDs/locations/employers → no identity merging or borrowing application forms.
8. HTTP 200 generic careers page or soft 404 → not a verified exact role.
9. Role present + broken apply route → review; generic “Apply” navigation is insufficient.
10. Redirect/rebrand/ATS migration → verify exact role continuity; unrelated parent or successor roles cannot substitute.
11. Reposted role/new ID → keep original mapping and actual dates; similar title alone is insufficient.
12. Recent employer release/social activity cannot establish job hiring intent or reset stale role age.
13. 500 distinct real job IDs across fewer employers → all originals preserved; shared employer evidence correctly joined; distinct-role count reported separately from row count.
14. Duplicate input IDs → preserve rows, reuse checks, and report duplicates honestly; do not inflate demonstrated scale.
15. Pause/restart → no duplicate role processing or paid research; negative board evidence refreshed when required.
16. TinySet unexpected employer/domain → reject the join; record real researched count and scope.
17. Application inspection → zero application submissions, accounts created, or applicant personal data collected.

## Recommendation to implementation owner

Add an explicit job-post mode and validate a small official-ATS pilot before launching the 500-role run. Treat it as an additional supported input path, not as a way to silently call the unfinished 500-company run complete. A real completed job audit can satisfy the allowed job-post demonstration, provided every required gate and the TinySet scope disclosure pass.
