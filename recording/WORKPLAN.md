# Real app screen recording

Status: completed and verified on November 17, 2026. Final capture: `app-recording-silent.mp4`.

The requested output is a continuous recording of the real Zombie Check app at `http://127.0.0.1:8765`. It shows the already completed audit `857949de-0d18-4951-9598-cef63cba4e55`, which completed earlier. No presentation composition or simulated progress is used.

## Sequence

1. Show the app welcome and upload the actual `examples/jobs-500.csv` through its file input.
2. Show and operate the actual list type and CSV column mapping controls; inspect the real input preview and cost cap.
3. Close the import preview without starting an audit. Open the saved completed audit from the sidebar.
4. Show its actual totals, original ledger, and alive/slowing-down filters.
5. Search for and open exact row `R000329`; inspect the preserved missing default route and verified Japanese route, followed by all five signal records and their source URLs.
6. Open the actual run report and inspect completion gates and service usage.
7. Download the real CSV from the app. Open the actual saved resume proof JSON in the browser's file view, then end on the complete ledger.

## Capture contract

- 1920 × 1080 browser viewport, silent continuous screen capture, approximately 90 seconds with readable holds.
- Real mouse, native select controls, file upload, filter, scroll, and download actions.
- The only optional capture overlay is a small cursor indicator whose location follows real mouse events.
- All requests are logged. The browser permits local GET requests, local POST `/api/preview`, and GET of the single saved resume proof file; other requests are blocked.
- Audit and row data are read before and after capture and compared. No audit creation, start, pause, resume, or paid API call is made.
- Save actual action timestamps for later narration alignment. Preserve raw WebM and convert continuously to silent H.264 MP4 without cuts or invented frames.
- Inspect decoded frames and FFprobe output before handoff.

Recorder: `../scripts/record_app.mjs`. Output: this directory. The application server is parent-owned and remains running.

## Verification

- Actual MP4: H.264, 1920 × 1080, 30 fps, 95.833333 seconds, 2,875 frames, 6,104,961 bytes; no audio stream.
- Eight frames decoded from the MP4 and inspected at 9, 14, 30, 46, 60, 70, 85, and 94 seconds.
- Actual CSV download: 500 rows, final-export cells match, original cells/order preserved.
- Zero blocked requests and zero browser runtime errors in the final capture. Before/after audit and row hashes match; audit ID list is unchanged.
- Sources: `capture-proof.json`, `audit-no-mutation-proof.json`, `export-proof.json`, `media-info.json`, and `action-timestamps.json`.

The first dropdown-keyboard attempts and a local codec mismatch failed verification. Their evidence was kept locally. Only the final verified continuous capture is the delivered video; failed takes and runtime caches should be excluded from Git.
