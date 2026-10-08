# Balanced TRP accuracy experiment

Date: 29 July 2026

Branch: `voice-pipeline-timing-test`

## Objective

Compare:

- `gemma4:cloud`
- `gpt-oss:20b-cloud`

Both models used the structured TRP request profile. Thinking was disabled for
Gemma and set to `low` for GPT-OSS.

## Evaluation set

The suite contained 20 cases:

- 10 complete utterances.
- 10 incomplete utterances.

The cases covered:

- Questions.
- Statements.
- Commands.
- Context-dependent short answers.
- Trailing prepositions.
- Unfinished clauses and predicates.
- Unfinished questions.
- Subordinate clauses.
- Unfinished comparisons.

Each model received the same cases. The 40 requests were randomised to reduce
systematic ordering effects. One unrecorded warm-up was performed per model.

## Operational results

These results use the application's existing decision rule:

```text
turn_complete = trp_probability >= 0.70
```

| Model | Valid | Accuracy | Complete recall | Incomplete recall | False waits | Premature finalisations |
|---|---:|---:|---:|---:|---:|---:|
| `gemma4:cloud` | 20/20 | **100%** | 100% | 100% | 0 | 0 |
| `gpt-oss:20b-cloud` | 20/20 | **35%** | 50% | 20% | 5 | 8 |

Premature finalisation is the more serious error for natural turn-taking:
the assistant begins responding while the visitor is still constructing the
utterance. GPT-OSS produced eight such errors.

## Latency

| Model | Median | Mean | p95 | Minimum | Maximum |
|---|---:|---:|---:|---:|---:|
| `gemma4:cloud` | **1.2980 s** | **1.6856 s** | **2.6579 s** | 0.9277 s | 6.0655 s |
| `gpt-oss:20b-cloud` | 1.8085 s | 1.8568 s | 2.4879 s | 0.9636 s | 2.7836 s |

Class-specific medians:

| Model | Complete cases | Incomplete cases |
|---|---:|---:|
| `gemma4:cloud` | 1.4024 s | 1.2359 s |
| `gpt-oss:20b-cloud` | 1.7500 s | 1.8799 s |

In this larger interleaved suite, Gemma was faster at the median as well as
more accurate. This differs from the earlier five-run single-utterance timing
sample and demonstrates the variability of the cloud endpoints.

## GPT-OSS probability incompatibility

GPT-OSS's explanations were semantically correct, but its probability values
were frequently reversed relative to the application's definition.

Example incomplete fragment:

```json
{
  "utterance": "Tell me about",
  "trp_probability": 0.95,
  "turn_complete": false,
  "reason": "The utterance ends abruptly with a preposition and lacks a specific topic, indicating it is incomplete."
}
```

Example complete question:

```json
{
  "utterance": "Who painted The Swing?",
  "trp_probability": 0.0,
  "turn_complete": true,
  "reason": "The utterance is a complete question."
}
```

The structured response's raw `turn_complete` Boolean was hidden by the
benchmark's thresholding step, matching production behaviour. A repeat
diagnostic preserved both values:

| GPT-OSS decision source | Accuracy |
|---|---:|
| Raw model `turn_complete` Boolean | **20/20 — 100%** |
| `trp_probability >= 0.70` | **8/20 — 40%** |

The repeat diagnostic had a 1.3740-second median and a 4.0166-second p95.

GPT-OSS therefore understood the completion task but did not use
`trp_probability` consistently with the service's expected direction.

## Verdict

`gemma4:cloud` is the best current TRP model:

- 100% accuracy on this balanced suite.
- No premature finalisations.
- No unnecessary waits.
- Faster median latency than GPT-OSS in the interleaved comparison.
- Compatible with the existing probability threshold.

GPT-OSS should not replace Gemma under the current service contract. It could
be reconsidered only after one of these changes is evaluated:

1. Trust the structured `turn_complete` Boolean instead of recomputing it.
2. Redefine the prompt's probability direction more explicitly and verify
   calibration on a larger suite.
3. Remove the probability field and request only the operational Boolean.

The first option would have achieved 100% on this suite, but it represents a
service-contract change and needs a larger repeat evaluation before adoption.
