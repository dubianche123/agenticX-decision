# Security policy

## Scope

This repository is a local research prototype. The web console reads files from a local data directory and can hold model credentials in local configuration. It is not designed to be exposed as a public service.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Contact the repository owner privately through GitHub with:

- a short description and affected file or endpoint;
- reproduction steps that use synthetic data only;
- the impact and any suggested mitigation.

Do not include API keys, customer documents, personal data, or confidential endpoints in a report.

## Safe-use requirements

- Keep the console bound to 127.0.0.1 unless you add authentication and an explicit deployment review.
- Use synthetic fixtures for issues and pull requests.
- Never commit credentials, PDFs, screenshots, extracted text, model responses, logs, or generated result files.
- Rotate a credential immediately if it is ever exposed.
