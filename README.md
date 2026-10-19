<div align="right"><sub>中文见 <a href="README_CN.md">README_CN.md</a></sub></div>

# AgenticX Decision

A small, local-first decision-audit harness built on AgenticX. It demonstrates how a decision workflow can keep deterministic rules in code, give the model bounded context, attach position-aware evidence, and block outputs missing basic structural requirements.

> Research prototype. The repository contains no customer documents, credentials, or production service configuration. The web console is intentionally local-only and has no authentication.

## What it demonstrates

- bounded retrieval instead of sending an entire document to every model call;
- hand-written rule tools for numeric, date, and field-presence checks;
- fail-closed validation when a required tool call, evidence citation, or JSON result is missing;
- an SSE web console for rules, workspaces, verdicts, evidence, and token usage;
- an offline mock mode that runs without an API key.

The code is domain-neutral at the engine boundary. It can be adapted to document review, procurement review, or other evidence-backed decision workflows by replacing the rule specifications and input adapters.

## Quick start

Requires Python 3.10+ and Git. Installation uses only public packages and a pinned [AgenticX source revision](https://github.com/DemonDamon/AgenticX/commit/a4d7caf29c9ce96f7b79ec2584b2f83f9ebdabe0).

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

    # Offline chain check and local console; no credentials or network calls.
    python mztdemo.py --mock
    python app.py --mock
    # open http://127.0.0.1:8620

Mock uses only `sample_data.py`: invented text, rules, and scripted model responses. It executes real search and rule tools but does not measure model quality, latency, or token costs. The console starts with the three synthetic rules; custom rules require live mode.

The validator currently checks JSON, a nonempty evidence field, and required tool-call presence. It does not verify quote fidelity, successful tool completion, or agreement between a verdict and the tool result.

For a live run, configure the model through environment variables or the local settings flow. Never commit keys or client material. The console binds to 127.0.0.1 by default; do not expose it directly to a network.

Live configuration (the `.env.example` file is a reference; it is not auto-loaded):

    export MZT_LLM_KEY='<your-local-key>'
    export MZT_LLM_BASE_URL='https://your-provider.example/v1'
    export MZT_LLM_MODEL='<your-model-id>'
    export MZT_PDF='/absolute/path/to/your/synthetic_report.pdf'
    python mztdemo.py

Alternatively run `python setup_key.py`. Never put credentials in endpoint URLs. Global configuration is inherited by the decompose/main/vision stages; `MZT_<STAGE>_BASE_URL`, `_MODEL`, `_KEY` override it. `MZT_CONFIG_DIR` isolates configuration from the default home directory.

Offline verification:

    python -m unittest discover -s tests -v
    python mztdemo_v2.py --mock
    python mztdemo_v3_baseline.py --mock
    python cost.py calc --in 1000 --out 200 --preset example

The cost preset is invented, not a provider quote. Live cross-file audits require a local PDF package (`MZT_MATERIAL_ROOT`) and a configured vision-capable model.

## Repository layout

- engine.py — retrieval, rule tools, AgenticX ReAct execution, validation, and SSE events.
- app.py — local FastAPI console.
- decomposer.py — maps natural-language rules to validated data specifications; it does not generate executable code.
- cost.py — recomputes usage and cost summaries from local run logs.
- docs/ — public experiment and extension notes; all examples are synthetic.

## Data and privacy

Put private documents under data/ and local outputs under results/. Both are ignored by Git. Do not commit PDFs, screenshots, extracted text, model responses, logs, API keys, or endpoint credentials. Use environment variables or a local file with restrictive permissions for credentials.

This project is not an access-control layer, a compliance certification, or a production deployment template. Review and adapt the threat model before using it with sensitive material.

## License

Apache-2.0. See LICENSE.

## Contributing

Please open an issue before adding a new provider, rule template, or data adapter. Contributions should include offline tests and must use synthetic fixtures only.
