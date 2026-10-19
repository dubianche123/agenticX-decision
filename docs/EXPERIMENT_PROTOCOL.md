# Public experiment protocol

This document describes a synthetic, reproducible protocol for testing evidence-backed decision workflows built on AgenticX. It contains no customer names, customer files, private endpoints, or measured results from confidential workloads.

## Goal

Compare two methods on the same synthetic document set:

1. a bounded pipeline with retrieval, deterministic rule tools, evidence validation, and an isolated AgenticX ReAct run per item;
2. a baseline that sends the full synthetic document to the model and performs no tool or evidence validation.

The comparison is about control placement and auditability, not about a particular model provider.

## Synthetic input

The offline fixture is `sample_data.py`; its text, dates, counts, rules,
and scripted responses are entirely invented. Nothing is derived from a
customer report. E1 executes actual tool calls; E2 mock checks only the
code comparator; E3 mock replays model answers. These are regression
checks, not measurements of OCR, model accuracy, throughput, or cost.

For live experiments, create synthetic PDFs under ignored `data/` and
set `MZT_PDF` (E1/E3) or `MZT_MATERIAL_ROOT` (E2). Text-only `.txt` inputs
are not accepted by the live PDF adapters.

Use synthetic organizations and invented documents. Do not copy customer material into this repository or into an issue, pull request, screenshot, log, or benchmark artifact.

## Experiment A: bounded rule audit

For each item, create a fresh ReActAgent instance. The agent receives a search tool and, for deterministic items, one hand-written rule tool. The final response must be JSON with an item identifier, verdict, evidence quote, and reason.

Example deterministic tools include:

- numeric range and parity checks;
- date deadline checks;
- required-field presence checks.

The validator must block a result when the required rule tool was not called, the evidence field is empty, or the output is not valid JSON.

## Experiment B: cross-document audit

Use a synthetic report plus synthetic attachments. The pipeline has three explicit phases:

1. text retrieval locates the claim and the relevant attachment;
2. an optional vision adapter inspects a scanned synthetic attachment;
3. a code rule compares the claim with the evidence and owns the final deterministic verdict.

A missing text layer is a routing signal for the vision phase, not a reason to retry indefinitely.

## Experiment C: full-text baseline

Use the same synthetic inputs and labels as Experiment A. Inline the full synthetic document for each request, do not expose rule tools, and do not run evidence validation. Record the failure mode rather than presenting the baseline as a production-quality method.

## Usage accounting

Record prompt tokens, completion tokens, cache metadata when the provider supplies it, tool calls, blocked results, and evidence references. Provider cache behavior is provider-dependent; do not turn a single run into a universal cost claim.

## Acceptance criteria

- every accepted verdict has an evidence reference;
- inspect deterministic outputs against the tool result; current structural validation alone does not enforce agreement;
- missing tool calls and malformed outputs are blocked;
- the offline mock path runs without credentials;
- no generated artifact contains private input material.

## Running locally

    python mztdemo.py --mock
    python app.py --mock

The mock path is the public regression check. Live model runs require local credentials and must use synthetic input when producing shareable artifacts.

## Current validation limits

`validate_item` checks JSON, a nonempty evidence field, and the presence of a required tool-call event. It does not check quote fidelity, successful tool completion, or verdict agreement. Treat these as additional experimental acceptance checks, not established guarantees.
