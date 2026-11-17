# Recorded demo review

Completed November 17, 2026.

## Delivered media

The file `../artifacts/demo.mp4` is a walkthrough of an actual recorded audit. The disclosure stays on screen in every scene. Screenshots and data come from the saved audit; only camera framing and editorial text are animated.

| Property | Verified value |
|---|---|
| Duration | 54.000 seconds |
| Video | H.264, 1920 × 1080, 30 fps |
| Audio | AAC, 48 kHz, stereo |
| File size | 9,102,096 bytes |
| SHA-256 | `6b017652b534812a8e61c913fd82c6193982dd7da43bb06bc28d48c2673fae18` |

FFprobe output is saved in `media-info.json`. The render completed with 1,620 frames in 26.3 seconds; its log is `render.log`.

## Source integrity

The source audit is `857949de-0d18-4951-9598-cef63cba4e55`. It finished 500 of 500 rows, with 340 alive and 160 slowing down. The source report records at least four verified signal observations for every row: 333 rows have four, and 167 have five. The five signal slots are checked for each posting, including shared employer context joined from TinySet.

The saved resume comparison preserved 490 completed results and the original rows, then reached 500 completed results. The exported CSV preview displays the first three real rows and their actual verdicts and dates.

`assets/export.csv` and `assets/audit-report.json` were refreshed from the final root artifacts generated at 12:53:22 UTC. Input count, output count, verdict totals, completion gates, and displayed CSV values were compared before refreshing. None of the displayed values changed, so the verified MP4 remains valid. `facts.json` carries the final report metadata.

Posting and intake evidence does not establish genuine vacancy intent, recruiter response, or successful application submission. This limitation appears in the evidence scene.

## Checks and visual review

`check.json` reports successful lint, runtime, layout, contrast, craft, and audio checks, with zero errors and warnings. Contrast passed 25 of 25 checks. Craft sampled 432 positions. The optional motion check was disabled, so this review does not claim a motion audit passed.

The saved `snapshot-review.json` covers 12 beat frames and 25 frames around the five cuts. The beat, seam, and phone-scale contact sheets were inspected. Evidence, export, and resume frames were also decoded directly from the delivered MP4 at 27, 37, and 50 seconds and inspected.

The weakest shot is the import mapping scene: the real form is dense and its smallest labels are difficult to read at phone scale. The headline, recorded-run disclosure, and the later export and resume claims remain readable. The evidence drawer is enlarged and reframed to show the source records.

The temporary HyperFrames preview on port 3018 returned HTTP 200 and was stopped after verification.

## Audio and tooling limits

The locally generated harmonic bed and tonal cues measured −38.1 dB mean and −22.4 dB peak. It is intentionally quiet. Sound was measured with FFmpeg and was not listened to; no listening review is claimed.

HyperFrames CLI 0.8.212 was used. The standalone skill freshness lookup failed. The animation-map helper failed because `@hyperframes/producer` and `@hyperframes/core` were unavailable; it did not run. Composition checks, the actual render, saved contact sheets, and decoded MP4 inspection succeeded independently.

This demo required no paid TinyFish or media generation calls.
