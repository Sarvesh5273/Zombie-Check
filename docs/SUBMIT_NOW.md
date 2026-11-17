# Submit Zombie Check

The user will publish the posts and submit the entry manually. No posts or entry have been sent by the agent.

## 1. LinkedIn

Copy linkedin-post.txt. Attach artifacts/demo.mp4 (54 seconds, 1080p). Tag the actual TinyFish company profile: https://www.linkedin.com/company/tinyfish-ai/ . Publish publicly and copy the post link.

## 2. TinyFish Discord

Copy discord-post.txt into the TinyFish server’s #showcase channel. Include the repository link and attach the demo if convenient. Copy the message link.

## 3. Bounty form

Open https://www.tinybounties.com/ , sign into your program account and open the claimed Zombie Check bounty.

Use these values wherever the form asks for them:

- Build name: Zombie Check
- Type: Spreadsheet Tool / API
- Working build: https://github.com/Sarvesh5273/Zombie-Check
- Demo: your public LinkedIn video post, or https://github.com/Sarvesh5273/Zombie-Check/blob/main/artifacts/demo.mp4
- Real input: examples/jobs-500.csv
- Audited output: artifacts/jobs-audited.csv
- Sources/full evidence: artifacts/jobs-evidence.jsonl and docs/SPOT_CHECKS.md
- Completion/export checks: artifacts/jobs-run-report.json and artifacts/jobs-export-verification.json
- Resume proof: artifacts/jobs-resume-proof.json
- Endpoints used: Search, Fetch, Agent and Browser; TinySet is the required dataset component. Do not count dataset routes as separate endpoint categories.
- Social links: your LinkedIn post and Discord message links

## Short build explanation

Zombie Check audits company or job CSVs against live sources and preserves every original cell and row. The real job demo returned 500 verdicts: 340 alive and 160 slowing down, with five checked signal categories and at least four verified observations per row. Exact role IDs, employers, intake fields and timestamps were independently reconciled. A real resume kept 490 completed results unchanged while the remaining ten finished.

TinySet researches three employers once; verified employer context is shared across their jobs while each posting and intake is checked independently. TinyFetch uses ttl=0, TinySearch resolves missing sources/routes, and Agent/Browser inspect difficult public forms. The 90-day age flag is a caution heuristic; posting health does not prove genuine hiring intent or successful application processing. The exact posting adapter currently supports Greenhouse.

## Final check

- LinkedIn post is public and includes the real TinyFish tag.
- Discord message is in #showcase.
- Both links and the repository open correctly.
- The form accurately discloses three-employer TinySet scope and the posting-age heuristic.
- Review the whole entry, submit once and save its confirmation/receipt.

Supplied deadline: November 17, 2026, 11:59 PM Pacific = November 18, 2026, 1:29 PM India time.
