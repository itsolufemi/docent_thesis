# Experiment B — model self-routing

Commit: `e7496306cb4659e47bafc85541d3fabe4394a96b`

Permanent tag: `experiment/classification-mitigation-B`

Architecture:

```text
final utterance
→ unconditional context and retrieval prefetch
→ one main-model conversation
→ hidden route header
→ operational tools
→ streamed spoken response
```

Gemma 4 with thinking disabled was the strongest profile. It produced valid
route blocks in all 12 samples, executed all operational tools correctly, and
reached first spoken content in a 3.2880-second median. Strict routing agreement
was 8/12 because retrieval-use reporting and one noise classification remained
inconsistent.

The principal comparison is:

```text
reports/model_self_routing_comparison.md
```

The `code/` directory contains a Git mailbox patch that recreates the exact
experiment from baseline `d96e67d7`.

