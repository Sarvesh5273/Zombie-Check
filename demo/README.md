# Zombie Check recorded demo

This project creates a 54-second walkthrough of a recorded audit. It is not a live screen recording. All screenshots and data are real saved artifacts; the camera and editorial text are animated, the row counts are not.

## Files

- index.html: root HyperFrames composition.
- compositions/: six editable scene files.
- build_demo.py: assembles the scenes and derives data from the real export/report/resume proof.
- capture-ui.mjs: optional read-only screenshot refresh; blocks audit mutation requests.
- assets/input.csv: the actual 500-row input.
- assets/export.csv: the actual returned spreadsheet.
- assets/audit-report.json and resume-proof.json: real run and interruption proof.
- assets/bed.wav: deterministic procedural audio generated locally.
- facts.json: values used in the walkthrough.

## Render

From the repository root:

    python3 demo/build_demo.py
    npx --yes hyperframes@0.8.212 check demo --json
    npx --yes hyperframes@0.8.212 preview demo --background --port 3018
    npx --yes hyperframes@0.8.212 render demo --workers 2 --quality looks --output artifacts/demo.mp4

Node 22+, FFmpeg, and a Chromium browser are needed. Rendering uses local assets. No TinyFish paid calls or generated-media providers are required.

To refresh screenshots from a locally running audit server, first start Zombie Check, then:

    node demo/capture-ui.mjs YOUR_AUDIT_ID

That script only reads audit state and previews the existing input CSV; its browser interceptor blocks start/pause/resume/create requests.

## Source and audio notes

The screenshot source is the completed job audit documented in assets/audit-report.json. The CSV data preview uses real exported values. Resume facts come from the saved comparison file.

Local Inter fonts and GSAP are staged from the installed HyperFrames package. The official ui-focus-zoom source is retained as a reference for camera motion. The harmonic bed and tonal marks are synthesized by build_demo.py, without external music or voice generation.

The installed HyperFrames CLI was pinned to 0.8.212. Usage lookup returned unknown, and the standalone general-video freshness check could not reach its manifest. The build uses the explicitly loaded local composition contract and the pinned CLI.
