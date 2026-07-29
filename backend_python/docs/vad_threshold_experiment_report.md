# Fixed VAD silence-threshold experiment

Date: 29 July 2026

Branch: `main`

## Objective

Evaluate fixed acoustic end-of-speech thresholds of:

```text
200 ms
300 ms
400 ms
450 ms
500 ms
600 ms
```

The experiment measured:

- acoustic segment splits;
- premature conversational turn finalisations;
- Faster Whisper word accuracy;
- whether optimized TRP correctly retained incomplete utterances;
- deterministic silence saved relative to the existing 600 ms threshold;
- additional ASR and TRP work caused by shorter thresholds.

## Important architectural constraint

The backend currently defines:

```python
MIN_SEMANTIC_CHECK_SILENCE_MS = 300
```

Consequently, a 200 ms acoustic segment can be produced and transcribed, but
the current turn detector returns `continue_listening` without calling TRP.
The frontend only schedules continued-silence reevaluation after
`await_more_speech`, not after `continue_listening`.

Therefore, 200 ms is not a functional finalisation threshold under the
current frontend/backend contract. Supporting it would require a semantic-gate
and timer-policy change in addition to changing the AudioWorklet constant.

## Method

The benchmark mirrored the production AudioWorklet:

- 16 kHz PCM16 mono audio;
- 128-sample worklet frames;
- RMS speech threshold of `0.02`;
- 40 ms required speech onset;
- 250 ms pre-roll;
- the candidate fixed silence threshold;
- the real Faster Whisper transcription service;
- the real conversation turn buffer;
- the optimized structured-streaming Gemma 4 TRP service.

Controlled fixtures were generated with the selected Google Chirp voice,
`en-GB-Chirp3-HD-Aoede`. Leading and trailing silence around each synthesised
phrase was trimmed, and known zero-valued pauses were inserted between phrase
parts.

### Fixtures

| Fixture | Phrase before pause | Nominal inserted pause | Continuation | First phrase status |
|---|---|---:|---|---|
| Complete request | `Tell me about The Arab Tent.` | None | None | Complete |
| Incomplete 250 | `Could you tell me about` | 250 ms | `The Arab Tent?` | Incomplete |
| Incomplete 350 | `Could you tell me about` | 350 ms | `The Arab Tent?` | Incomplete |
| Incomplete 450 | `Could you tell me about` | 450 ms | `The Arab Tent?` | Incomplete |
| Unfinished clause | `I think that` | 350 ms | `the painting is beautiful.` | Incomplete |
| Complete clause | `The Arab Tent is remarkable.` | 350 ms | `Its interior is richly decorated.` | Semantically complete |

The nominal inserted pause is not identical to the effective worklet silence.
Each generated phrase retains a small 40 ms boundary pad, and low-amplitude
speech can fall below the RMS threshold. This is intentional: the worklet
responds to acoustic energy, not to the known fixture edit point.

The initial matrix evaluated 200, 300, 400 and 600 ms. A targeted follow-up
then evaluated 450 and 500 ms against the same cached fixtures and services.

## Results

All 36 threshold/fixture conditions completed successfully.

Faster Whisper recovered every expected word in every condition:

```text
mean word error rate = 0.0
```

Punctuation sometimes differed across split segments, but the lexical content
was preserved.

### Threshold summary

| Threshold | Conditions completed | Pause fixtures acoustically split | Premature turn finalisations | Incomplete split prefixes correctly retained | Final turns resolved | Guaranteed saving |
|---:|---:|---:|---:|---:|---:|---:|
| 200 ms | 6/6 | 5/5 | 0 | 0/4 | 0/6 | 400 ms |
| 300 ms | 6/6 | 5/5 | **1** | **4/4** | 6/6 | **300 ms** |
| 400 ms | 6/6 | 4/5 | **1** | **3/3** | 6/6 | **200 ms** |
| 450 ms | 6/6 | 3/5 | **1** | **2/2** | 6/6 | **150 ms** |
| 500 ms | 6/6 | **1/5** | **0** | **1/1** | 6/6 | **100 ms** |
| 600 ms | 6/6 | 0/5 | 0 | Not exercised | 6/6 | Baseline |

The zero premature-finalisation count at 200 ms is not a success: no condition
could finalise at all because TRP was gated off below 300 ms.

### 200 ms

Every fixture was transcribed correctly, and all five fixtures containing an
inserted pause were divided into two acoustic segments. Every turn-buffer
decision was:

```text
continue_listening
```

TRP was never called, including for the complete request and final complete
segments. The current application would leave these turns unresolved.

Verdict: **not compatible with the current architecture**.

### 300 ms

All pause-bearing fixtures split acoustically. The four incomplete prefixes
were handled correctly:

```text
Could you tell me about
-> await_more_speech
-> append continuation
-> finalise_turn
```

and:

```text
I think that
-> await_more_speech
-> append continuation
-> finalise_turn
```

The optimized TRP assigned the incomplete prefixes a probability of `0.1`,
then assigned the accumulated complete utterances probabilities between
`0.85` and `0.95`.

The complete-clause fixture behaved differently:

```text
The Arab Tent is remarkable.
-> finalise_turn

Its interior is richly decorated.
-> separate finalise_turn
```

TRP assigned the first clause `0.95`, which is semantically reasonable from
the text it had received. Nevertheless, relative to the intended fixture, this
was a premature finalisation.

300 ms produced 11 acoustic segments and 11 TRP evaluations across six
fixtures, compared with six segments and six evaluations at 600 ms.

Verdict: **strong latency candidate, but not yet safe as an unconditional
production threshold**.

### 400 ms

The 250 ms fixture remained one segment, while the longer and acoustically
quiet pause fixtures still split. All three split incomplete prefixes were
correctly retained by TRP.

The complete-clause fixture was again prematurely finalised. Raising the
threshold from 300 to 400 ms therefore reduced splitting but did not remove
the principal semantic failure in this small set.

400 ms produced 10 acoustic segments and 10 TRP evaluations.

Verdict: **more conservative acoustically, but did not eliminate premature
semantic finalisation in this experiment**.

### 450 ms

Three pause-bearing fixtures still split:

- the 450 ms incomplete request;
- the unfinished-clause fixture;
- the complete-clause fixture.

TRP correctly returned `await_more_speech` for both incomplete prefixes, with
probability `0.1`, and finalised their accumulated continuations. The complete
first clause was again assigned `0.95` and prematurely finalised.

450 ms produced nine acoustic segments and nine TRP evaluations. It saved a
fixed 150 ms relative to baseline but did not remove the semantic failure
observed at 300 and 400 ms.

Verdict: **not preferable to 500 ms in this fixture set**.

### 500 ms

Only the longest incomplete-pause fixture split. Its first segment:

```text
Could you tell me about...
```

received:

```text
trp_probability = 0.1
decision = await_more_speech
```

After appending `The Arab Tent.`, the accumulated turn received probability
`0.95` and finalised correctly.

The unfinished-clause and complete-clause fixtures both remained intact as
single acoustic segments. No premature finalisation occurred, every final
turn resolved, and word error rate remained zero.

500 ms produced seven acoustic segments and seven TRP evaluations, only one
more than the 600 ms baseline. Its recorded median TRP/turn-processing time
was 0.8803 seconds, although cloud model timings should not be used to infer a
causal threshold effect.

Verdict: **strongest conservative fixed-threshold candidate tested**.

### 600 ms

No fixture split. All six complete accumulated utterances finalised, and word
accuracy remained exact.

Verdict: **safest tested fixed threshold, with no latency improvement**.

## Latency interpretation

The deterministic benefit applies at the final pause:

| Threshold | Silence saved on every completed turn |
|---:|---:|
| 200 ms | 400 ms |
| 300 ms | 300 ms |
| 400 ms | 200 ms |
| 450 ms | 150 ms |
| 500 ms | 100 ms |
| 600 ms | 0 ms |

However, shorter thresholds can create additional Whisper and TRP work at
internal pauses:

| Threshold | Total segments/evaluations across six fixtures |
|---:|---:|
| 200 ms | 11 segments, 0 TRP calls |
| 300 ms | 11 segments, 11 TRP calls |
| 400 ms | 10 segments, 10 TRP calls |
| 450 ms | 9 segments, 9 TRP calls |
| 500 ms | 7 segments, 7 TRP calls |
| 600 ms | 6 segments, 6 TRP calls |

Thus, 300 ms guarantees a 300 ms earlier acoustic boundary for a simple
complete utterance, but may nearly double ASR and TRP work for speech
containing internal pauses. The application can preserve obvious incomplete
turns correctly, yet the additional processing can outweigh the fixed silence
saving.

Cloud timing was too variable to rank thresholds by total model latency. The
recorded run included a failed unrecorded warm-up and one 15.44-second TRP
outlier, while all 24 recorded conditions themselves completed. The fixed
silence saving, split count, decisions, and transcription accuracy are the
reliable measurements from this experiment.

## Recommendation

Do not change production directly from 600 to 200 ms. It is incompatible with
the current 300 ms semantic gate and would require additional architectural
work.

Do not yet promote 300, 400 or 450 ms as an unconditional production
threshold. All allowed TRP to protect clearly incomplete fragments, but all
prematurely finalised a semantically complete first clause when the synthetic
speaker continued after the pause. TRP cannot infer unobserved future speech
when the available text already forms a valid turn.

500 ms is now the strongest conservative candidate. It saved a deterministic
100 ms, avoided the complete-clause premature finalisation, preserved exact
word transcription, and required only one additional ASR/TRP segment across
the six fixtures.

The evidence supports this next sequence:

1. Retain 600 ms as the production default for now.
2. Put 500 ms behind the first conservative experimental configuration flag.
3. Retain 300 ms as the aggressive research condition when the objective is
   to quantify the maximum fixed-threshold saving.
4. Collect real human speech containing:
   - incomplete clauses;
   - word-search hesitations;
   - between-sentence pauses;
   - short contextual answers;
   - naturally slow speech.
5. Require at least one protection mechanism before rolling out thresholds
   below 500 ms:
   - a short provisional-finalisation grace period;
   - cancellation/rejoining when speech resumes before response commitment;
   - partial ASR that distinguishes projected completion before acoustic
     finalisation.

If the immediate goal is a controlled latency demonstration rather than a
production default, 300 ms is the best experimental setting: it saves 300 ms
and the optimized TRP correctly retained all four incomplete split prefixes.
The complete-clause failure must remain visible in any evaluation.

## Implementation decision

Following review of the 450 and 500 ms follow-up, the project selected 500 ms
as the production pause threshold. This deliberately accepts a conservative
100 ms improvement while avoiding every premature finalisation in the
controlled fixture set.

The implementation now uses 500 ms consistently in:

- the AudioWorklet speech-end detector;
- the React VAD silence fallback;
- audio-segment finalisation;
- continued-silence accounting;
- the full voice-pipeline timing harness.

The backend semantic-check minimum remains 300 ms, and forced finalisation
remains 1,800 ms.

## Limitations

- The fixtures use one synthetic British voice, not a population of visitors.
- Nominal pause duration differs slightly from effective RMS silence.
- Six fixtures are enough for architectural screening, not a production error
  rate.
- The experiment did not include background noise, reverberation, accents,
  breath noise, or microphone variability.
- It evaluated textual response timing only, not TTS playback.

The user does not need to record incomplete utterances for this preliminary
test. Real user recordings are still required before deciding that a shorter
threshold is safe for deployment.

## Artifacts

Benchmark:

```text
scripts/benchmark_vad_thresholds.py
```

Raw results:

```text
tmp/latency/vad_threshold_benchmark.json
tmp/latency/vad_threshold_benchmark_450_500.json
```

Generated audio fixtures:

```text
tmp/vad_thresholds/
```
