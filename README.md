<div align="center">

<img src="docs/assets/overview.svg" alt="AgenticX Decision: retrieve document evidence, execute code rules, inspect structured results" width="100%" />

# AgenticX Decision

**Document review with explicit tools, bounded context, and evidence you can inspect.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![AgenticX](https://img.shields.io/badge/Built%20on-AgenticX-5B7FFF)](https://github.com/DemonDamon/AgenticX)
[![License](https://img.shields.io/badge/License-Apache--2.0-2EA98B)](LICENSE)
[![Demo](https://img.shields.io/badge/Offline%20demo-Synthetic%20data-8B6FC0)](#try-it-locally)

[Quick start](#try-it-locally) · [How it works](#how-it-works) · [Live configuration](#connect-a-model) · [中文说明](README_CN.md)

</div>

AgenticX Decision is a local research harness for evidence-backed document review. An agent searches a document, invokes hand-written rule tools, and produces a structured result for inspection. A small web console makes rules, evidence, blocked results, and usage visible in one workflow.

The project explores a practical split: **models retrieve and interpret; Python tools calculate explicit checks; reviewers inspect the evidence and outcome.** It provides working examples of this pattern, with clear limits on what the current validator enforces.

## What you can try

| Capability | What is implemented |
| --- | --- |
| Rule specification | Map natural-language rules to a JSON template specification; no executable code generation |
| Bounded retrieval | Extract a local PDF's text, then search for keyword snippets with character offsets |
| Deterministic tools | Numeric range/parity, date deadlines, and required-field checks |
| Semantic review | An isolated AgenticX ReAct run with retrieved context for each item |
| Cross-document review | Locate a claim and attachment, inspect rendered pages with a vision model, then compare counts in Python |
| Local console | Rule editing, PDF/package workspaces, streamed results, evidence, and usage summaries |
| Experiment scripts | Bounded audit, cross-file comparison, and full-text baseline entrypoints |

**Scope:** a research prototype, not a production review service. The public examples are entirely invented. No customer documents, confidential workload measurements, credentials, or production endpoint settings are included.

## How it works

Each item gets its own ReAct run. Deterministic rules map to a small tool rather than asking the model to calculate the check itself.

![Single-item audit flow](docs/assets/audit-flow.svg)

<sub>[Mermaid source](docs/assets/audit-flow.mmd)</sub>

The structural check blocks malformed JSON, an empty evidence field, or a missing required rule-tool call. **It does not yet verify that a quote matches the source, that the tool completed successfully, or that the final verdict agrees with the tool result.** Those checks remain reviewer responsibilities and extension points.

### Cross-document path

A separate runner handles rules where the main document makes a claim that must be checked against an attachment.

![Cross-document verification flow](docs/assets/cross-file-flow.svg)

<sub>[Mermaid source](docs/assets/cross-file-flow.mmd)</sub>

The live path needs local PDFs and a vision-capable model. The cross-file `--mock` example tests the code comparator only; it does not run OCR or evaluate a vision model.

## Try it locally

Requires **Python 3.10+ and Git**; the release was verified with Python 3.11. Installation fetches public dependencies, including a pinned [AgenticX source revision](https://github.com/DemonDamon/AgenticX/commit/a4d7caf29c9ce96f7b79ec2584b2f83f9ebdabe0).

```bash
git clone https://github.com/dubianche123/agenticX-decision-public.git
cd agenticX-decision-public

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the synthetic audit. No key, private files, or model requests.
python mztdemo.py --mock

# Start the local console.
python app.py --mock
```

Open **http://127.0.0.1:8620**. Keep the three preloaded synthetic rules, choose the offline demo workspace, and run the audit. If the port is occupied, use `python app.py --mock --port 9000`.

### What the demo shows

| Invented input | Example rule | Expected result |
| --- | --- | --- |
| Member count: 31 | Between 3 and 15, and odd | 不合格 — fails the range check |
| Report year: 2030; date: 2031-04-12 | Due by June 30 of the following year | 合格 — before the deadline |
| Approval pending; supporting basis missing | Unresolved approval requires review | 存疑 — needs follow-up |

Example result excerpt:

```json
{
  "item_id": "sample_number",
  "type": "rule:numeric_range",
  "agent_verdict": "不合格",
  "evidence": "[位置≈86] 成员人数：31",
  "blocked": false,
  "mock": true
}
```

Mock mode executes real AgenticX orchestration, search, and rule tools with **scripted model replies** from [sample_data.py](sample_data.py). It is a regression demonstration, not a model benchmark; it establishes no accuracy, latency, or cost claim. Offline rule decomposition returns a fixed example mapping, and newly saved custom rules are explicitly blocked in offline audit mode. Use live mode to evaluate your own rules.

## Connect a model

Use an OpenAI-compatible provider. Configure it through `python setup_key.py`, the console's settings dialog, or environment variables:

```bash
export MZT_LLM_KEY='<your-local-key>'
export MZT_LLM_BASE_URL='https://your-provider.example/v1'
export MZT_LLM_MODEL='<your-model-id>'
export MZT_PDF='/absolute/path/to/your/synthetic_report.pdf'

python mztdemo.py
# Or launch the console without --mock:
python app.py
```

The CLI audit uses the example rules; adapt them for your own evaluation. The console lets you define rules and choose PDFs under `data/`. For cross-document runs, point `MZT_MATERIAL_ROOT` at a local material package and configure the vision stage.

| Setting | Purpose |
| --- | --- |
| `MZT_LLM_KEY`, `MZT_LLM_BASE_URL`, `MZT_LLM_MODEL` | Global model configuration |
| `MZT_<STAGE>_KEY`, `MZT_<STAGE>_BASE_URL`, `MZT_<STAGE>_MODEL` | Override `DECOMPOSE`, `MAIN`, or `VISION`; unset fields inherit global settings |
| `MZT_DATA_DIR` | Local console workspaces and saved rules; defaults to `data/` |
| `MZT_PDF` | Input PDF for the bounded audit and full-text baseline |
| `MZT_MATERIAL_ROOT` | PDF package for the cross-document CLI |
| `MZT_CONFIG_DIR` | Optional directory for local settings; otherwise stored in the user home directory |

[.env.example](.env.example) is a reference and **is not automatically loaded**. Export variables explicitly. Keep keys out of endpoint URLs. Live runs send selected document content to the provider you configure.

## Experiments and checks

| Command | What it exercises |
| --- | --- |
| `python mztdemo.py --mock` | Search, numeric/date tools, and semantic replay through AgenticX |
| `python mztdemo_v2.py --mock` | Synthetic claim/evidence count comparison in Python |
| `python mztdemo_v3_baseline.py --mock` | Scripted full-text baseline responses |
| `python -m unittest discover -s tests -v` | Offline execution, SSE selection, key redaction, settings isolation, and path containment |
| `python cost.py calc --in 1000 --out 200 --preset example` | Token-cost arithmetic with invented unit prices |

Remove `--mock` for live experiments after configuring inputs and models. Do not compare mock outputs with live measurements. The included cost preset is **not a provider quote**; use your own current rates for real calculations. See the [experiment protocol](docs/EXPERIMENT_PROTOCOL.md) for a controlled comparison.

## Explore the code

```text
.
├── app.py                       Local FastAPI console
├── engine.py                    Retrieval, rule tools, ReAct runners, validation, SSE
├── decomposer.py                Natural-language rule → JSON specification
├── sample_data.py               Invented text, rules, and scripted responses
├── mzt_common.py                Local configuration and PDF helpers
├── mztdemo.py                    E1 · bounded audit
├── mztdemo_v2.py                 E2 · cross-document audit
├── mztdemo_v3_baseline.py        E3 · full-text baseline
├── cost.py                      Token-cost arithmetic
├── setup_key.py                 Local provider configuration
├── static/                      Console interface
├── tests/                       Synthetic offline/privacy regressions
└── docs/                        Protocol, release notes, and diagram assets
```

To add a deterministic check, implement a hand-written tool in [engine.py](engine.py), register its template, and extend the specification catalog in [decomposer.py](decomposer.py). Add synthetic cases for the expected verdict and failure paths. Keep rule specifications as data.

## Boundaries and data handling

- The console binds to `127.0.0.1` and has no authentication. Keep it local.
- Put private inputs in `data/`, outputs in `results/`, and credentials in environment variables or restricted local settings. These locations are ignored by Git.
- Source-text offsets support inspection; they are not page coordinates or proof that an LLM quote is faithful.
- Live semantic and vision outputs need evaluation on your own inputs. The structural validator does not establish legal or business correctness.
- Contributions and shareable artifacts must use invented data. Do not commit private PDFs, extracted text, model responses, keys, or logs.

Read the [security policy](SECURITY.md) and [release review](docs/PUBLIC_RELEASE_REVIEW.md) for the current scope.

## License and contributions

The project source is [Apache-2.0](LICENSE). Dependencies retain their own licenses; the [release review](docs/PUBLIC_RELEASE_REVIEW.md#direct-dependency-license-inventory) includes the direct dependency inventory.

Issues and contributions are welcome for new rule templates, input adapters, and stronger validation. Include a reproducible synthetic example and relevant offline checks.
