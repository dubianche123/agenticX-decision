# Public release checklist

Review date: 2026-10-19. See PUBLIC_RELEASE_REVIEW.md for scope and limits.

- [x] Sanitize source, documentation, configuration defaults, model presets, examples and mock outputs.
- [x] Replace private excerpts and measurements with invented fixtures and explicit labels.
- [x] Scan all available historical blobs and commit messages for credentials.
- [x] Check historical business information separately from credential detection.
- [x] Install public upstream AgenticX in an isolated Python 3.11 environment.
- [x] Pass all 10 offline/privacy tests, including all three CLI mock paths.
- [x] Verify local console binding and settings redaction.
- [x] Record direct dependency licenses and validation limitations.
- [x] Prepare publication from a new root commit containing only the audited snapshot.
- [x] Select a separate public destination: `dubianche123/agenticX-decision`.

This checklist covers the prepared release content. The public snapshot excludes private data, local settings, output files, environments and previous development history. Publication is verified against the remote after upload.
