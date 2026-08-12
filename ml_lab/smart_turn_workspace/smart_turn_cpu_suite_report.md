# Smart Turn v3.2 CPU accuracy and latency checkpoint

## Decision

Smart Turn is fast enough for Docent's local CPU, but this preliminary suite
does not support replacing the existing TRP path outright.

The safest next integration experiment is a high-confidence fast path:

```text
200 ms VAD pause
→ Smart Turn
    ├─ probability >= 0.90 → accept turn as complete
    └─ probability < 0.90  → retain the existing fallback path
```

No incomplete recording in this suite reached 0.90. This would therefore
have produced zero premature finalisations while immediately accepting 11 of
the 22 complete recordings. It is an experimental policy, not a production
threshold, until it passes a larger human-recorded suite.

## Test design

- Model: `smart-turn-v3.2-cpu.onnx`
- Runtime: ONNX Runtime 1.28.0, CPU provider
- Hardware: Intel Core i7-1185G7, 4 cores / 8 logical processors
- Python: 3.14.4
- Completion threshold: 0.50
- Audio cases: 40
- Complete labels: 22
- Incomplete labels: 18
- Warm-ups: 2 per recording
- Measured predictions: 10 per recording, 400 total
- Session lifecycle: one persistent ONNX session

The suite contains:

- 32 Google Chirp recordings across Aoede and Achernar;
- seven existing pause and fragment fixtures;
- one human-recorded Docent voice request.

The synthetic recordings make this a repeatable preliminary checkpoint.
They do not replace a multi-speaker, human-recorded evaluation.

## Classification result

| Metric | Result |
|---|---:|
| Correct | 33 / 40 |
| Accuracy | 82.50% |
| Balanced accuracy | 83.08% |
| Complete recall | 77.27% |
| Incomplete recall | 88.89% |
| Complete precision | 89.47% |
| Premature finalisations | 2 / 18 incomplete cases |
| Delayed finalisations | 5 / 22 complete cases |

The two premature finalisations were:

| Case | Completion probability |
|---|---:|
| “If we move to the next room…” — Aoede | 88.97% |
| “The artist who painted it…” — Achernar | 75.08% |

The five complete utterances predicted incomplete were:

| Case | Completion probability |
|---|---:|
| “Give me a highlights tour.” — Aoede | 10.65% |
| “Yes.” — Aoede | 20.76% |
| “The Arab Tent is remarkable.” — Aoede | 12.68% |
| “No, thank you.” — Aoede | 48.03% |
| “Give me a highlights tour.” — Achernar | 2.81% |

All eight non-new fixtures passed, including:

- the human “Tell me about The Swing” recording;
- complete requests containing 250, 350 and 450 ms internal pauses;
- the two existing incomplete clause fragments.

## Voice sensitivity

| Source or voice | Correct | Accuracy |
|---|---:|---:|
| Aoede synthetic cases | 11 / 16 | 68.75% |
| Achernar synthetic cases | 14 / 16 | 87.50% |
| Existing fixtures | 7 / 7 | 100% |
| Human recording | 1 / 1 | 100% |

The same text sometimes received very different probabilities across the two
voices. That is expected for an audio-native model, but it means text-only
test coverage cannot establish deployment safety.

## CPU latency

Across all 400 measured ONNX predictions:

| Measurement | Time |
|---|---:|
| Median inference | 125.31 ms |
| P95 inference | 220.18 ms |
| Median of per-case complete local paths | 229.57 ms |

Model download and one-time ONNX session construction are excluded. The
complete local path includes WAV loading, resampling/padding, Whisper feature
extraction and ONNX inference.

The latency result is suitable for a local adaptive endpoint experiment:

```text
200 ms silence trigger
+ approximately 230 ms Smart Turn
= approximately 430 ms to a provisional completion decision
```

## Replacement assessment

### Direct replacement

Not recommended yet. An 11.11% premature-finalisation rate on the incomplete
subset is too high, even though both errors came from synthetic recordings.

### High-confidence fast path

Promising. At a completion threshold of 0.90:

- 11 complete recordings would finalise immediately;
- zero incomplete recordings would finalise;
- the remaining 29 recordings would retain the existing conservative path.

This can reduce latency for high-confidence turns without removing the
current safety net.

### Evidence still required

Record a human suite with multiple speakers and natural conversational
prosody, especially:

- trailing conjunctions and subordinate clauses;
- mid-turn hesitation pauses;
- commands such as “Give me a highlights tour”;
- one-word acknowledgements and short contextual answers;
- changes in microphone distance and background noise.

Premature finalisation should be evaluated separately and weighted more
heavily than delayed finalisation.
