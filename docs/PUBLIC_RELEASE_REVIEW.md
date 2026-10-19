# Public release review — 2026-10-19

## Audited content

The release contains only source, documentation, a reference environment file, tests and invented fixtures. Removed source-level private endpoints, provider-specific commercial settings, private dependency references, report excerpts and workload measurements. No customer input files are included.

E1 uses actual AgenticX search/rule orchestration with scripted responses. E2 mock checks the deterministic comparator only. E3 mock replays invented baseline answers. Token counters are zero in offline mode. These are regression fixtures, not performance or accuracy evidence. The live adapters still require locally configured PDFs and credentials; no paid model run or private workload was executed during this review.

## Validation performed

- Fresh Python 3.11 environment, installing requirements.txt from public sources; AgenticX 0.6.5 at the pinned public source revision.
- `python -m unittest discover -s tests -v`: 10 tests passed, including socket-denied CLI runs, selected-rule SSE results, configuration isolation, global/stage key redaction, restrictive settings permissions and path containment.
- Python source compilation and Git whitespace checks passed.
- Gitleaks 8.30.1, checksum verified: no credential findings in Git diff history; all 31 unique blobs reachable from the 16 pre-review commits plus all commit messages were also separately scanned. No findings means no detector matches, not proof that credentials never existed elsewhere.
- Current release tree separately scanned before packaging. Private business references were reviewed separately because credential detectors do not identify them.

## Release isolation

This release starts from a new root commit containing the audited files only.
Previous development history was not imported. Private inputs, local settings,
run outputs, virtual environments and historical Git objects are excluded.
A separate local backup preserves the private development history.

The public snapshot has no customer workload results. The detector scans and
manual review described above were performed before publication.

## Direct dependency license inventory

Installed package metadata reported: AgenticX 0.6.5 and OpenAI 2.54.0 — Apache-2.0; pypdf 6.21.1 and Uvicorn 0.54.0 — BSD-3-Clause; FastAPI 0.146.0 and LiteLLM 1.106.0 — MIT. PyMuPDF 1.28.2 reports dual AGPL-3.0/commercial licensing. Dependency licenses remain their own; this project's Apache-2.0 license does not replace them. Dependencies are installed separately and are not vendored in the release snapshot.

## Known runtime limits

The console remains a local, unauthenticated research prototype. Validation checks JSON, nonempty evidence and required tool-call presence; it does not establish quote fidelity, successful tool completion or verdict agreement. Custom live rules and vision quality need their own evaluation. Keep client materials, keys, responses and logs out of future commits.
