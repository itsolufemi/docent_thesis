# TRP model selection and streaming latency report

Date: 29 July 2026

Branch: `voice-pipeline-timing-test`

## Executive summary

This report records the full sequence of transition relevance prediction
(TRP) experiments:

1. initial timing and availability screening across five Ollama cloud models;
2. balanced accuracy testing of the two strongest available candidates;
3. streaming versus non-streaming testing of the selected model.

The initial screening included `gemini-3-flash-preview:latest`,
`gpt-oss:20b-cloud`, `gemma4:cloud`, `gemma4:31b-cloud`, and
`qwen3.5:cloud`. Gemini 3 Flash Preview had already been retired, while Qwen
3.5 required account or subscription access that was unavailable to the test
profile. GPT-OSS was initially the fastest available structured model, but
failed the application's probability-based contract on the balanced suite.
Gemma 4 was both faster and fully accurate in that larger comparison and was
therefore selected for the streaming experiment.

The final experiment compared streaming and non-streaming Ollama requests
using `gemma4:cloud`. Both profiles disabled thinking, enforced the same
structured JSON schema, and ran against the same balanced set of 20 complete
and incomplete utterances.

Both profiles classified all 20 cases correctly. Streaming made a fully
validated TRP result available sooner in 15 of the 20 paired comparisons.
The conservative paired median reduction was 188 milliseconds. Comparing the
aggregate medians, streaming made validated JSON available 351 milliseconds
earlier.

The recommended production profile is therefore:

- `gemma4:cloud`;
- streaming enabled;
- thinking disabled;
- temperature zero;
- a 160-token output limit;
- structured JSON output;
- early return only after the accumulated response validates as a complete
  `TRPPrediction`.

## Purpose

The TRP model runs after speech transcription and before the utterance
classifier, retrieval, and main response model. Its latency is directly added
to the interval between the user pausing and the system deciding whether it
may respond.

The test asked whether streamed generation could safely reduce that interval.
The important distinction was between:

1. receiving the first content fragment;
2. observing individual decision fields in incomplete JSON;
3. receiving a complete, schema-valid TRP object;
4. waiting for Ollama's final `done` event.

Only the third milestone was selected for production use. It provides an
earlier result without making a decision from malformed or incomplete JSON.

## Experiment 1: initial cloud-model screening

### Voice input and measurement boundary

The first experiment used a fixed 1.32-second recording:

> Tell me about The Swing.

Faster Whisper consistently transcribed it as:

> Tell me about the swing.

Timing ended immediately after the TRP decision, before the utterance
classifier began. The shared median time before TRP was 2.5794 seconds:

- spoken audio: 1.3200 seconds;
- VAD finalisation silence: 0.6000 seconds;
- Faster Whisper transcription: 0.6594 seconds median.

Each model received one unrecorded warm-up followed by five recorded calls.
Model order was randomised independently in each round. The expected result
was a complete turn.

### Candidate availability

| Candidate | Availability | Outcome |
|---|---|---|
| `gemini-3-flash-preview:latest` | Unavailable | Every request returned `410 Gone`; the endpoint reported that the preview model had been retired on 15 July 2026 |
| `gpt-oss:20b-cloud` | Available | Required a structured request and low reasoning to return usable answer content within the generation budget |
| `gemma4:cloud` | Available | Compatible with both request profiles |
| `gemma4:31b-cloud` | Available | Compatible, but generally slower than the standard Gemma 4 cloud alias |
| `qwen3.5:cloud` | Access restricted | The model pulled, but every inference request returned `403 Forbidden`; the current Ollama user profile required additional subscription access |

The name recorded by the benchmark was **Gemini 3 Flash Preview**, not a
Gemma 3 model. Similarly, the fifth candidate was **Qwen 3.5 Cloud**. These
exact model identifiers are retained so the experiment can be reproduced or
audited.

### Baseline service profile

The first pass reproduced the service profile that existed before this work:
non-streaming generation, prompt-only JSON instructions, and an 80-token
output limit.

| Rank | Model | Valid | Correct | Median TRP | Valid range | Median voice-to-classifier boundary |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `gemma4:cloud` | 4/5 | 4/5 | 7.1845 s | 6.3514-10.5072 s | 9.6817 s |
| 2 | `gemma4:31b-cloud` | 3/5 | 3/5 | 11.3011 s | 4.7974-15.4048 s | 13.7983 s |
| - | `gpt-oss:20b-cloud` | 0/5 | 0/5 | No valid result | - | - |
| - | `gemini-3-flash-preview:latest` | 0/5 | 0/5 | Retired | - | - |
| - | `qwen3.5:cloud` | 0/5 | 0/5 | Access restricted | - | - |

GPT-OSS spent the limited generation budget on mandatory reasoning and
returned empty answer content. This showed that comparing models under the old
profile alone would be misleading.

### Structured low-reasoning profile

The candidates were then tested with a TRP-specific structured schema, a
160-token limit, temperature zero, and reduced reasoning. Thinking was
disabled for Gemma and set to `low` for GPT-OSS.

| Speed rank | Model | Valid | Correct | Median TRP | Mean TRP | Valid range | Median voice-to-classifier boundary |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `gpt-oss:20b-cloud` | 5/5 | 4/5 | **1.6046 s** | 1.8044 s | 1.4114-2.3612 s | **4.1840 s** |
| 2 | `gemma4:cloud` | 5/5 | 5/5 | 9.5670 s | 12.5257 s | 7.2915-21.9001 s | 12.1464 s |
| 3 | `gemma4:31b-cloud` | 5/5 | 5/5 | 10.1459 s | 10.8125 s | 5.6125-16.2587 s | 12.7253 s |
| - | `gemini-3-flash-preview:latest` | 0/5 | 0/5 | Retired | - | - | - |
| - | `qwen3.5:cloud` | 0/5 | 0/5 | Access restricted | - | - | - |

GPT-OSS was the clear latency leader in this small, single-utterance sample.
It nevertheless produced one contradictory result: its explanation described
a complete request, while `trp_probability` was `0.1`. Because production
derives completion from `trp_probability >= 0.70`, a larger balanced
evaluation was required before selecting it.

## Experiment 2: balanced model accuracy

The second experiment compared `gemma4:cloud` and `gpt-oss:20b-cloud` across
20 cases:

- 10 complete utterances;
- 10 incomplete utterances;
- questions, statements, requests and contextual short answers;
- trailing prepositions and unfinished clauses, predicates, questions,
  comparisons, and subordinate clauses.

The 40 requests were randomly interleaved, with one unrecorded warm-up per
model. Gemma used `think: false`; GPT-OSS used `think: "low"`. Operational
accuracy was calculated using the production rule:

```text
turn_complete = trp_probability >= 0.70
```

### Balanced operational accuracy

| Model | Valid | Accuracy | Complete recall | Incomplete recall | False waits | Premature finalisations |
|---|---:|---:|---:|---:|---:|---:|
| `gemma4:cloud` | 20/20 | **100%** | 100% | 100% | 0 | 0 |
| `gpt-oss:20b-cloud` | 20/20 | **35%** | 50% | 20% | 5 | 8 |

Premature finalisation is the more serious failure in a spoken interface
because it causes the assistant to respond while the visitor is still
speaking. GPT-OSS caused eight such errors under the existing service
contract.

### Balanced latency

| Model | Median | Mean | p95 | Minimum | Maximum |
|---|---:|---:|---:|---:|---:|
| `gemma4:cloud` | **1.2980 s** | **1.6856 s** | 2.6579 s | 0.9277 s | 6.0655 s |
| `gpt-oss:20b-cloud` | 1.8085 s | 1.8568 s | **2.4879 s** | 0.9636 s | 2.7836 s |

In this larger interleaved evaluation, Gemma 4 was faster at the median as
well as substantially more accurate. The difference from the earlier
five-request sample illustrates the variability of cloud inference and the
danger of selecting a model from one complete utterance alone.

### GPT-OSS contract incompatibility

GPT-OSS generally understood the linguistic task, but often used the
probability in the opposite direction from the application's definition. A
repeat diagnostic preserved the raw Boolean instead of immediately applying
the probability threshold:

| GPT-OSS decision source | Accuracy |
|---|---:|
| Raw model `turn_complete` Boolean | **20/20 (100%)** |
| `trp_probability >= 0.70` | **8/20 (40%)** |

The diagnostic repeat had a 1.3740-second median and a 4.0166-second p95.
GPT-OSS could be reconsidered if the service contract changed to trust the
Boolean or if its probability calibration were redesigned and validated.
Under the existing contract, Gemma 4 was the safe production selection.

## Experiment 3: Gemma 4 streaming comparison

### Profiles compared

The two request profiles were identical except for the `stream` setting.

```json
{
  "model": "gemma4:cloud",
  "stream": true,
  "think": false,
  "format": {
    "type": "object",
    "properties": {
      "trp_probability": {
        "type": "number",
        "minimum": 0,
        "maximum": 1
      },
      "turn_complete": {
        "type": "boolean"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "trp_probability",
      "turn_complete",
      "reason"
    ]
  },
  "options": {
    "temperature": 0,
    "num_predict": 160
  }
}
```

The non-streaming control used the same body with `"stream": false`.

### Streaming method

- Model: `gemma4:cloud`
- Cases: 20 balanced complete and incomplete utterances
- Context: each case retained its supplied recent-turn context
- Ordering: streaming and non-streaming requests were randomly interleaved
- Warm-up: one request per profile before recording
- Random seed: `20260729`
- Temperature: `0`
- Maximum generated tokens: `160`
- Thinking: disabled
- Decision threshold: `0.70`
- Request timeout in the benchmark: 30 seconds

For streaming requests, the benchmark timestamped:

- first non-empty response fragment;
- first point at which probability and Boolean fields were visible;
- first point at which the accumulated response passed JSON parsing and
  `TRPPrediction` validation;
- the final Ollama `done` event.

The benchmark did not act on partial fields. They were measured only to
quantify the theoretical benefit of a future incremental parser.

### Streaming results

#### Accuracy

| Mode | Valid responses | Correct classifications |
|---|---:|---:|
| Non-streaming | 20/20 | 20/20 |
| Streaming | 20/20 | 20/20 |

Streaming did not reduce accuracy or structured-response validity in the
recorded run.

#### End-to-end request latency

| Mode | Median | Mean | p95 | Minimum | Maximum |
|---|---:|---:|---:|---:|---:|
| Non-streaming | 1.4967 s | 1.9130 s | 4.8570 s | 1.0923 s | 6.7539 s |
| Streaming, response complete | 1.2603 s | 1.4551 s | 2.1356 s | 0.9515 s | 2.5131 s |

The completed streaming response had an aggregate median 236 milliseconds
lower than the non-streaming response, a reduction of approximately 15.8%.

#### Streaming milestones

| Milestone | Median | p95 | Production suitability |
|---|---:|---:|---|
| First content fragment | 0.7563 s | 1.6380 s | Insufficient for a decision |
| Probability and Boolean visible | 0.9598 s | 1.7871 s | Not yet robust |
| Fully valid `TRPPrediction` JSON | **1.1458 s** | **2.0616 s** | **Recommended** |
| Ollama `done` event | 1.2603 s | 2.1356 s | Safe but unnecessarily later |

Complete validated JSON was available a median 114.5 milliseconds before the
stream's final `done` event.

#### Paired comparison

| Measurement | Result |
|---|---:|
| Valid paired cases | 20 |
| Streaming valid JSON faster | 15/20 |
| Median paired valid-JSON saving | **0.1880 s** |
| Mean paired valid-JSON saving | 0.5689 s |
| Partial decision fields faster | 19/20 |
| Median partial-field saving | 0.4053 s |

The paired median saving of 188 milliseconds is the most conservative
estimate because it compares both modes on the same utterance. The larger
aggregate difference is influenced by several slower cloud responses in the
non-streaming sample.

### Comparison with the original voice-pipeline boundary

The original voice-pipeline experiment measured from the beginning of the
recorded request to the point immediately before the utterance classifier:

```text
spoken audio
-> VAD finalisation silence
-> Faster Whisper
-> TRP
-> classifier boundary
```

Its median Gemma 4 timing was:

| Stage | Stage duration | Cumulative time |
|---|---:|---:|
| Spoken fixture | 1.3200 s | 1.3200 s |
| VAD finalisation silence | 0.6000 s | 1.9200 s |
| Faster Whisper | 0.5772 s | 2.4972 s |
| Original Gemma 4 TRP request | 7.1845 s | **9.6817 s** |

The streaming comparison isolated the TRP request rather than replaying the
audio fixture. To make the two experiments comparable, the safest calculation
holds the original audio, VAD and Whisper timings constant and substitutes the
new median time to fully validated streaming JSON:

| Stage | Stage duration | Cumulative time |
|---|---:|---:|
| Spoken fixture | 1.3200 s | 1.3200 s |
| VAD finalisation silence | 0.6000 s | 1.9200 s |
| Faster Whisper | 0.5772 s | 2.4972 s |
| Optimised streaming TRP | 1.1458 s | **3.6430 s** |

On this normalised comparison:

- classifier-boundary latency falls from 9.6817 to 3.6430 seconds;
- the reduction is 6.0387 seconds, or approximately **62.4%**;
- the boundary is reached approximately **2.66 times faster**;
- the TRP stage itself falls from 7.1845 to 1.1458 seconds, an approximately
  **84.1%** reduction.

The streaming milestones would map onto the original fixture as follows:

| Streaming milestone | TRP time | Projected cumulative time | Safe decision? |
|---|---:|---:|---|
| First content | 0.7563 s | 3.2535 s | No |
| Probability and Boolean visible | 0.9598 s | 3.4570 s | Not with the current parser |
| Fully valid JSON | 1.1458 s | **3.6430 s** | **Yes** |
| Stream `done` | 1.2603 s | 3.7575 s | Yes |

This is a normalised projection, not a new end-to-end audio replay. Cloud
latency varied materially between experiments, so the 62.4% figure should not
be treated as a guaranteed production percentile. A production-path smoke
request using the implemented profile completed in 1.2716 seconds; combined
with the original pre-TRP stages, that individual result would place the
classifier boundary at approximately 3.7688 seconds.

The optimisation also changes where the remaining delay lies. In the original
measurement, TRP accounted for approximately 74.2% of the classifier-boundary
time. Under the normalised optimised profile, audio, VAD and transcription
together account for approximately 68.5%, while TRP accounts for approximately
31.5%. Further end-to-end gains will therefore depend increasingly on acoustic
segmentation and transcription rather than TRP alone.

The production profile was subsequently rerun through the full voice harness.
The same 1.32-second fixture was processed three times through the real audio
and conversation WebSockets using one backend process. The first run included
cold service effects; runs two and three reused the loaded Whisper model and
in-memory vector index.

### Observed full-pipeline rerun

| Measurement | Run 1 | Run 2 | Run 3 | Median |
|---|---:|---:|---:|---:|
| Voice plus VAD boundary | 1.9417 s | 1.9492 s | 1.9446 s | 1.9446 s |
| Whisper interval | 2.6163 s | 0.6525 s | 0.5949 s | 0.6525 s |
| Optimised TRP and turn evaluation | 1.1513 s | 0.8868 s | 0.9457 s | **0.9457 s** |
| Turn finalised from voice onset | 5.7109 s | 3.4904 s | 3.4872 s | **3.4904 s** |
| Classifier interval | 1.3963 s | 4.8504 s | 1.7893 s | 1.7893 s |
| Classifier complete from voice onset | 7.1072 s | 8.3408 s | 5.2765 s | 7.1072 s |
| Vector retrieval | 3.7476 s | 0.4051 s | 0.3041 s | 0.4051 s |
| Query start to first text | 16.1754 s | 1.5677 s | 1.9368 s | 1.9368 s |
| First assistant text from voice onset | 23.2829 s | 9.9087 s | 7.2135 s | **9.9087 s** |
| Complete response from voice onset | 23.5022 s | 10.5291 s | 7.6326 s | **10.5291 s** |

Run 1 made two invalid `create_conversation_branch` tool calls. Those extra
model rounds made its 23.5022-second result a behavioural outlier. Run 2 had
no tool calls, but the classifier cloud request rose to 4.8504 seconds. Run 3
had neither issue and completed the textual request in 7.6326 seconds.

The original and optimised three-run medians compare as follows:

| Boundary or stage | Original | Optimised | Change |
|---|---:|---:|---:|
| TRP and turn evaluation | 1.3408 s | **0.9457 s** | **-0.3951 s (-29.5%)** |
| Turn finalised from voice onset | 5.0680 s | **3.4904 s** | **-1.5776 s (-31.1%)** |
| Classifier boundary | 7.1233 s | 7.1072 s | -0.0161 s |
| First assistant text | 10.0776 s | **9.9087 s** | -0.1689 s (-1.7%) |
| Complete assistant text | 10.5214 s | 10.5291 s | +0.0077 s |

The direct production-path conclusion is therefore that the optimised TRP
performed materially better: its observed median interval fell by 395
milliseconds, or 29.5%. This is a smaller improvement than the earlier
normalised projection because the original full-pipeline traces happened
during a much faster Gemma cloud period than the initial 7.1845-second model
screening.

### Interpreting cumulative turn latency

The 3.4904-second median turn-finalisation boundary does **not** mean turn
finalisation takes another 3.49 seconds after transcription. It is cumulative
from voice onset and contains:

```text
approximately 1.32 s spoken audio
+ approximately 0.60 s VAD silence
+ approximately 0.65 s warmed Whisper
+ approximately 0.95 s TRP and turn evaluation
= approximately 3.5 s to turn finalisation
```

Once a transcript was available, the optimised service generally required
about 0.9-1.15 seconds to obtain and apply the TRP result.

The classifier boundary is cumulative in the same way:

```text
voice + VAD + Whisper + TRP
-> turn finalised
-> classifier cloud request
-> classifier boundary
```

The classifier itself ranged from 1.3963 to 4.8504 seconds. Later response
generation ranged even more widely when tool-call retries occurred. These
downstream fluctuations were larger than the approximately 0.4 seconds saved
by TRP and therefore concealed that saving in the median full-response time.
They do not indicate a TRP regression.

At the end of this experiment, the practical latency ladder was:

```text
VAD silence:              fixed 600 ms
Warmed Whisper:           approximately 600-650 ms
Optimised TRP:            approximately 900-950 ms
Cloud classifier:         approximately 1.4-4.9 s observed
Warmed retrieval:         approximately 300-400 ms
Main response generation: approximately 1.5-2.0 s normally,
                          substantially longer with tool retries
```

All three traces classified the request as a retrieval-backed response
request, but the current vector store did not contain a source for The Swing.
The resulting source-free answers and Run 1's malformed branch-tool calls are
downstream functional observations, not failures of the TRP experiment. A
retrievable subject such as The Arab Tent would be appropriate for a future
retrieval and response-generation evaluation, but is not required to establish
the TRP result.

The complete trace-by-trace analysis is also retained in
[`optimized_voice_pipeline_timing_report.md`](optimized_voice_pipeline_timing_report.md).

### Streaming reliability observation

An exploratory pass encountered one streaming request that reached the
30-second timeout. The corrected recorded pass completed all 20 streaming
requests successfully. This does not invalidate the result, but it shows that
cloud tail latency should be monitored separately from median latency.

The production request retains a finite timeout. Operational telemetry should
eventually record timeout rate, p95 and p99 latency, and whether a fallback
turn decision was required.

## Recommended implementation

The production TRP request should:

1. send the structured streaming profile shown above;
2. accumulate each non-empty `response` fragment in order;
3. attempt JSON parsing and `TRPPrediction` validation after each fragment;
4. continue reading when the buffer is incomplete or invalid;
5. return immediately once a complete object validates;
6. close the HTTP response instead of waiting for the final `done` event;
7. preserve the existing probability threshold as the authoritative
   `turn_complete` calculation;
8. fail explicitly if the stream ends without valid structured JSON.

The threshold remains authoritative because it gives the application one
stable decision rule even if the model's raw Boolean and probability disagree:

```python
prediction.turn_complete = (
    prediction.trp_probability >= threshold
)
```

## Changes implemented

The production TRP service now uses:

- `"stream": true`;
- `"think": false`;
- the tested structured JSON schema;
- `temperature: 0`;
- `num_predict: 160`;
- incremental accumulation and full Pydantic validation;
- early response closure after the first valid object.

The change is isolated to the TRP request. It does not alter:

- the primary assistant-response model;
- the utterance classifier;
- transcription;
- retrieval;
- TTS streaming.

Unit coverage verifies the request profile, early return, response closure,
threshold authority, and failure when a stream never yields valid JSON.

## Reproduction

From `backend_python`, the initial baseline screening can be reproduced with:

```powershell
python scripts\benchmark_trp_models.py --request-profile current
```

The structured screening can be reproduced with:

```powershell
python scripts\benchmark_trp_models.py `
  --request-profile structured `
  --output tmp/latency/trp_model_benchmark_structured.json
```

The balanced Gemma 4 and GPT-OSS suite can be reproduced with:

```powershell
python scripts\benchmark_trp_accuracy.py
```

The final streaming comparison can be reproduced with:

```powershell
python scripts\benchmark_trp_streaming.py
```

The recorded raw artifacts are:

```text
tmp/latency/trp_model_benchmark.json
tmp/latency/trp_model_benchmark_structured.json
tmp/latency/trp_balanced_accuracy.json
tmp/latency/trp_gpt_boolean_diagnostic.json
tmp/latency/trp_streaming_comparison.json
tmp/latency/optimized_voice_trace.json
tmp/latency/optimized_voice_trace_2.json
tmp/latency/optimized_voice_trace_3.json
```

The production unit tests can be run with:

```powershell
python -m unittest tests.test_trp_service -v
```

## Conclusion

The experiments produced the following selection and validation sequence:

1. Gemini 3 Flash Preview could not be evaluated because it had been retired,
   and Qwen 3.5 Cloud could not be evaluated because the Ollama user profile
   lacked the required access.
2. GPT-OSS was promising in the first small timing sample, but its probability
   calibration produced only 35% operational accuracy and eight premature
   finalisations in the balanced suite.
3. Gemma 4 achieved 20/20 balanced accuracy and remained compatible with the
   application's probability threshold. Its structured streaming profile
   then reduced safe decision latency by approximately 188 milliseconds on
   the median paired case.
4. In the subsequent full production voice traces, the implemented profile
   reduced the observed median TRP/turn-evaluation interval from 1.3408 to
   0.9457 seconds, a 29.5% improvement. Overall response latency remained
   approximately 10.53 seconds at the median because classifier and main-model
   variance were larger than the TRP saving.

Structured streaming with thinking disabled is therefore the best tested
production profile for `gemma4:cloud`. Streaming should be treated as an
incremental improvement rather than the dominant latency optimisation:
disabling thinking and enforcing concise structured output remain the larger
profile-level gains.
