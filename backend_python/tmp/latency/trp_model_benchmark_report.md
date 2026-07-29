# TRP cloud-model timing experiment

Date: 29 July 2026

Branch: `voice-pipeline-timing-test`

## Test input

The fixed 1.32-second voice fixture says:

> Tell me about The Swing.

Faster Whisper consistently produced:

> Tell me about the swing.

The measured endpoint is immediately after the TRP decision, before the
utterance classifier begins.

## Method

- 1.32 seconds of spoken audio.
- 0.60-second VAD turn-boundary silence.
- Three warmed Whisper measurements.
- One unrecorded warm-up request per TRP model.
- Five recorded TRP requests per model.
- Model order randomised independently in each round.
- Temperature set to zero.
- All responses validated against the existing `TRPPrediction` schema.
- Expected decision for this complete request: `turn_complete = true`.

Two request profiles were measured:

1. **Current service profile** — the request currently made by
   `predict_transition_relevance()`, including its 80-token generation limit.
2. **Structured TRP profile** — Ollama structured JSON output, 160 generated
   tokens, thinking disabled where supported, and GPT-OSS reasoning set to
   `low`.

## Current service profile

| Rank | Model | Valid runs | Correct runs | Median TRP | Range of valid runs | Median voice-to-classifier boundary |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `gemma4:cloud` | 4/5 | 4/5 | 7.1845 s | 6.3514–10.5072 s | 9.6817 s |
| 2 | `gemma4:31b-cloud` | 3/5 | 3/5 | 11.3011 s | 4.7974–15.4048 s | 13.7983 s |
| — | `gpt-oss:20b-cloud` | 0/5 | 0/5 | No valid result | — | — |
| — | `gemini-3-flash-preview:latest` | 0/5 | 0/5 | Retired | — | — |
| — | `qwen3.5:cloud` | 0/5 | 0/5 | Subscription unavailable | — | — |

GPT-OSS used its generation budget for mandatory reasoning and returned empty
answer content under the current request. It therefore cannot replace Gemma
without changing the TRP request profile.

## Structured TRP profile

The shared median pre-TRP portion was 2.5794 seconds:

- Voice: 1.3200 seconds
- VAD silence: 0.6000 seconds
- Whisper: 0.6594 seconds median

| Speed rank | Model | Valid runs | Correct runs | Median TRP | Mean TRP | Range | Median voice-to-classifier boundary |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `gpt-oss:20b-cloud` | 5/5 | 4/5 | **1.6046 s** | 1.8044 s | 1.4114–2.3612 s | **4.1840 s** |
| 2 | `gemma4:cloud` | 5/5 | 5/5 | 9.5670 s | 12.5257 s | 7.2915–21.9001 s | 12.1464 s |
| 3 | `gemma4:31b-cloud` | 5/5 | 5/5 | 10.1459 s | 10.8125 s | 5.6125–16.2587 s | 12.7253 s |
| — | `gemini-3-flash-preview:latest` | 0/5 | 0/5 | Retired | — | — | — |
| — | `qwen3.5:cloud` | 0/5 | 0/5 | Subscription unavailable | — | — | — |

## Availability findings

- `gemini-3-flash-preview:cloud` was not present as a pullable manifest.
  Its default cloud alias pulled successfully, but every request returned
  `410 Gone`: the model was retired on 15 July 2026.
- `qwen3.5:cloud` pulled successfully, but every request returned `403`:
  the current Ollama account requires a subscription upgrade for access.
- `gpt-oss:20b-cloud`, `gemma4:cloud`, and `gemma4:31b-cloud` were available.

## Interpretation

`gpt-oss:20b-cloud` is the decisive latency winner under a TRP-specific
structured request. Its median TRP latency was approximately six times faster
than `gemma4:cloud`.

It is not yet the safest production choice because one of five GPT-OSS runs
returned a contradictory probability:

- `trp_probability = 0.1`
- reason: “The utterance is a complete request.”

The current service thresholds the probability and therefore classified that
run as incomplete. Before changing `OLLAMA_TRP_MODEL`, GPT-OSS should pass a
larger accuracy set containing both complete and incomplete utterances.

For immediate drop-in use with no code changes, `gemma4:cloud` remains the
best of the available compatible models. For the next experiment,
`gpt-oss:20b-cloud` is the strongest candidate.
