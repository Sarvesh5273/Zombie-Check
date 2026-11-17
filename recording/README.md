# Real app recording

`app-recording-silent.mp4` is a continuous recording of the actual local Zombie Check app, captured on November 17, 2026. It shows the real import controls and a saved audit that completed earlier. It contains no presentation scenes, simulated progress, or injected product data. The small capture-only cursor follows real mouse events.

The audio track is intentionally absent. The narration scripts in this directory are prepared separately for user-generated ElevenLabs audio.

## Files

| File | Purpose |
|---|---|
| `app-recording-silent.mp4` | Delivered continuous screen recording |
| `raw/` | Original browser WebM, retained locally |
| `action-timestamps.json` | Actual UI actions and readable holds for narration alignment |
| `capture-proof.json` | Requests, actual mappings, screenshots, and media verification |
| `audit-no-mutation-proof.json` | Before/after audit and row hashes plus allowed non-read request |
| `downloaded-audit.csv` | Real CSV downloaded through the app's Export CSV button |
| `export-proof.json` | 500-row download and original-cell preservation checks |
| `media-info.json` | Actual FFprobe stream and container metadata |
| `review-frames/` | Eight decoded MP4 frames and visual contact sheet |
| `WORKPLAN.md` | Capture sequence and verification status |

## Verified delivery

H.264, 1920 × 1080, 30 fps, 95.833333 seconds, 2,875 video frames, and 6,104,961 bytes. No audio stream is present. MP4 SHA-256: `4bbe5220311afd0d8431027953f8ee47d982ae32bc1520a4811631fc3eebd761`.

The final capture logged zero blocked requests and zero runtime errors. The actual audit, 500 rows, and existing audit IDs are identical before and after recording. The only non-read request is the original CSV sent to the app's `/api/preview` endpoint. No audit was created, started, paused, or resumed, and no paid service was called.

The actual export matches the final saved export cell for cell, including all 500 original rows and their order. Row R000329 shows the retained default-route failure, actual recovered Japanese route, cautious age-based verdict, source links, and the limits of application-intake evidence. The resume segment opens the actual saved `artifacts/jobs-resume-proof.json` through Chrome's file view.

## Reproduce

Keep the existing local server running at `http://127.0.0.1:8765`, then run from the repository root:

    node scripts/record_app.mjs

The script uses the installed Playwright module and Google Chrome. It records the browser content continuously, saves a raw WebM, and converts it to H.264 without cuts. Its route interceptor blocks every audit mutation and external request; only local reads, CSV preview, and the one saved resume JSON file are permitted.

This host's Playwright expects FFmpeg with VP8 encoding. The recorder uses the full installed `/opt/homebrew/bin/ffmpeg` through a workspace-local runtime symlink, because the minimal cached FFmpeg exposes VP9 only. `capture-preflight.mjs` verified a real 1920 × 1080 VP8 file before the final take.

Only the final verified video should be used. Failed attempts, the raw recording, preflight output, and runtime cache are local verification material and should be excluded from Git. The application server remains running.
