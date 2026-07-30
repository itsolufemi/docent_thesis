# Experiment A — classifier tool routing

Commit: `f6f5602acfbeba769f4b40208dad3eca7edf1a3f`

Permanent tag: `experiment/classification-mitigation-A`

Architecture:

```text
final utterance
→ main-model request
→ mandatory classify_utterance tool call
→ local validation and context resolution
→ resume the same main-model conversation
→ streamed response
```

The corrected experiment confirmed that the tool did not invoke a hidden
classifier model. With Gemma 4 and thinking disabled it remained slower than
the sequential classifier architecture: 5.9249 seconds median versus 4.5502
seconds, and it won only 2 of 9 paired samples.

The principal comparison is:

```text
reports/classifier_architecture_model_comparison.md
```

The `code/` directory contains a Git mailbox patch that recreates the exact
experiment from baseline `d96e67d7`.

