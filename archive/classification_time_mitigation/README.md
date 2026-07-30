# Classification latency mitigation experiments

This archive preserves the three classifier-latency architectures evaluated
from the common baseline commit:

```text
d96e67d707dd18b18b9cd636baec540db9ab1e0c
```

## Experiment index

| Experiment | Architecture | Commit | Permanent tag | Outcome |
|---|---|---|---|---|
| A | Mandatory classifier tool inside the main-model conversation | `f6f5602a` | `experiment/classification-mitigation-A` | Accurate with Gemma 4, but slower than the separate classifier |
| B | Main-model self-routing after unconditional retrieval | `e7496306` | `experiment/classification-mitigation-B` | Technically successful, but routing self-reports remained inconsistent |
| C | Context resolver supplies explicit evidence and candidate subjects; main model self-routes | `fdbfd480` | `experiment/classification-mitigation-C` | Selected architecture; merged into `main` |

Each experiment directory contains:

- a Git mailbox patch under `code/`;
- human-readable Markdown reports under `reports/`;
- raw JSON benchmark observations under `reports/`.

The patch recreates the complete experiment commit when applied to the common
baseline:

```powershell
git switch --detach d96e67d7
git switch -c restored-experiment
git am archive\classification_time_mitigation\<experiment>\code\0001-*.patch
```

The permanent tags provide the simplest way to inspect an experiment directly:

```powershell
git switch --detach experiment/classification-mitigation-A
```

## External full-source archive

A separate local archive was created at:

```text
C:\Users\itsol\Documents\docent_thesis_experiment_archive_2026-07-30
```

It contains a full tracked-source ZIP for each experiment and a verified Git
bundle containing complete history for all three experiment branches.

The repository archive is intentionally patch-based rather than storing three
additional full codebase copies inside Git. This keeps the repository compact
while preserving exact, reconstructable code. The external ZIPs provide the
immediately browsable full-source copies.

## Overall finding

The selected configuration was:

```text
context-resolver self-routing
Gemma 4 Cloud
streaming enabled
thinking disabled
```

Its tuned benchmark produced 15/15 valid route blocks, 15/15 route accuracy,
15/15 candidate-subject accuracy, 15/15 action accuracy, and 15/15 operational
tool correctness. Median time to the route block was 2.8693 seconds and median
time to first spoken content was 3.0214 seconds.

