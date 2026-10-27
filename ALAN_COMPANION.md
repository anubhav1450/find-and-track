# Find&Track companion for Alan

A reusable Alan skill plus a small local persistence bridge. Alan reads and reasons about a job; Find&Track previews, deduplicates and saves approved records, preserving their application state.

## Try it in Alan

1. Open this repository as the project folder in Alan and select **This computer**. This first version uses local execution, not the hosted personal app.
2. Import `skills/find-track` through Alan's Skills page, or select it as a project skill if discovered. Importing an entire repository is not necessary.
3. Ask: **Use find-track with its demo workspace. Read my sample profile and assess examples/alan-demo/job.json. Show the findings before saving.**
4. After reviewing the findings, ask Alan to save the exact proposal. Refresh the demo dashboard: the job should appear.
5. To test live research, give Alan a public employer posting or paste its complete JD. Access depends on the tools enabled in that Alan session; blocked pages require pasted text.

Official setup references: [Skills](https://docs.tryalan.ai/docs/skills/skills), [local execution](https://docs.tryalan.ai/docs/cloud-and-local/local-execution).

## Deterministic local walkthrough

```sh
python3 tools/findtrack.py demo
python3 tools/findtrack.py profile
python3 tools/findtrack.py preview --job examples/alan-demo/job.json
```

Read the returned assessment and proposal. After approval, use the returned `proposalFile` and `approvalDigest`:

```sh
python3 tools/findtrack.py save --proposal <proposalFile> --approval <approvalDigest>
python3 tools/findtrack.py serve
```

Open http://127.0.0.1:8766. The example is clearly labelled fictional. Running demo initialization again does not reset records. Proposal and database files stay under ignored `work/alan-demo/`. The bridge never writes a new job as Applied.

## What this proves

A saved profile can drive repeatable assessment; an approved result can appear in a persistent dashboard; duplicate saves preserve progress; edited proposals and stale profiles are rejected. The same UI remains useful after an Alan session ends.

## What this does not prove

The CLI is not a search engine, an LLM or a complete eligibility engine. Its keyword comparison is a starting point for Alan's review. There is no new hosted MCP endpoint, automatic Gmail monitor or multi-user cloud connector in this slice. Actual invocation from Alan must be verified separately from command-line tests; do not present a simulated agent run as a real Alan integration.
