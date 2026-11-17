# Real-list demo inputs

`yc-b2b-500.csv` contains exactly 500 publicly listed YC B2B companies with websites, sampled across 2019–2026 batches by a fixed hash of public YC ID. It supplies the names and URLs to audit; it contains **no verdicts or cached activity labels**.

The sample was selected without filtering for company status, hiring or known activity. It includes company name, website, batch, public ID and source URL only. The actual audit must obtain every signal from live pages.

`yc-b2b-500.provenance.json` describes the source, retrieval time, selection, excluded fields and hashes. Reproduce with `python3 scripts/prepare_demo.py` from the repository root. Since the upstream list changes, the included CSV and hash identify the specific demonstrated input.

Source: https://yc-oss.github.io/api/companies/all.json
Community repository: https://github.com/yc-oss/api

The source repository's root listing had no LICENSE file when checked on 2026-11-17. These examples contain factual list fields, not copied repository source code or company descriptions.

