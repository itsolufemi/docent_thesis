# Smart Turn Human Speech Experiment

## Purpose

This experiment evaluated whether Smart Turn v3.2 could replace the cloud-based
Gemma 4 turn-relevance prediction step in Docent. Unlike the preliminary suite,
all 40 recordings in this experiment were human-recorded.

## Method

- Model: `smart-turn-v3.2-cpu.onnx`
- Runtime: ONNX Runtime, CPU execution provider
- Audio: 16 kHz mono PCM16 WAV
- Cases: 40 total
- Expected complete: 20
- Expected incomplete: 20
- Decision threshold: 0.50
- Warm-up runs: 2 per recording
- Measured runs: 10 per recording

The suite included complete questions and commands, short contextual responses,
hesitations, internal pauses, trailing clauses, conjunctions, and deliberately
incomplete utterances.

## Results

| Measurement | Human suite | Preliminary synthetic suite |
|---|---:|---:|
| Correct | 34/40 | 33/40 |
| Accuracy | **85.0%** | 82.5% |
| Delayed finalisations | 1/20 | 5/22 |
| Premature finalisations | 5/20 | 2/18 |

The median Smart Turn inference time was **135.16 ms**. The median of the
per-recording complete local paths—including audio loading, feature extraction,
and inference—was **243.45 ms**.

## Error analysis

Only one complete utterance was marked incomplete:

- “Yes.” — completion probability 12.68%

Five incomplete utterances were marked complete:

- “The artist who painted it…” — 98.65%
- “Before we continue…” — 98.93%
- “When the collection first opened…” — 98.65%
- “Although the painting looks simple…” — 97.86%
- “Compared with the other works…” — 95.23%

Therefore, the improved overall accuracy did not produce a safer error profile.
The main remaining risk is premature finalisation of subordinate or
continuation-projecting clauses. Raising the threshold modestly does not solve
this because these errors have very high completion probabilities.

## Interpretation

Smart Turn performs quickly enough for local deployment and recognises completed
human turns very reliably. It could remove Whisper and the Gemma 4 cloud request
from the turn-completion decision, substantially reducing latency.

However, immediately accepting a `complete` result after an aggressive 200 ms
pause is not yet justified. The human suite produced a 25% premature
finalisation rate on deliberately incomplete examples.

## Recommendation

Begin with a monitored experimental integration at the existing 500 ms silence
boundary:

```text
500 ms silence
→ local Smart Turn processing (~243 ms median)
→ complete: finalise the turn
→ incomplete: continue listening or apply a longer fallback timeout
```

This should provide a provisional decision approximately **743 ms after speech
ends**, while avoiding the latency of Whisper plus the Gemma 4 TRP request.

Log the probability, decision, silence duration, and any subsequent user
continuation during live conversations. Do not yet use Smart Turn as an
unrestricted 200 ms endpoint detector. Reassess that option after collecting
natural in-application speech containing subordinate clauses and mid-turn
pauses.

## Conclusion

Smart Turn is suitable for a controlled Docent integration trial. The human
suite supports replacing the cloud TRP for latency evaluation, but it does not
yet support aggressive early finalisation without monitoring and fallback
behaviour.

