# Experiment C — context-resolver self-routing

Commit: `fdbfd4809269aaf2d6f4a96895e31d8d7048c56e`

Permanent tag: `experiment/classification-mitigation-C`

Architecture:

```text
final utterance
→ current-subject lookup
→ vector retrieval and keyword fallback
→ explicit candidate-subject list
→ one streaming main-model conversation
→ hidden self-routing metadata
→ operational tools
→ spoken response
```

This was the selected experiment and was merged into `main`.

Gemma 4 with thinking disabled achieved:

- 15/15 valid routing blocks;
- 15/15 route accuracy;
- 15/15 candidate-subject accuracy;
- 15/15 proposed-action accuracy;
- 15/15 operational-tool correctness;
- no routing-header leakage;
- 2.8693-second median route time;
- 3.0214-second median first spoken content.

The remaining limitation was `retrieval_used` self-reporting, which was correct
in 12/15 samples. It remains debug-only and can later be derived
deterministically from tool arguments.

The principal comparison is:

```text
reports/context_self_routing_comparison.md
```

The `code/` directory contains a Git mailbox patch that recreates the exact
experiment from baseline `d96e67d7`.

