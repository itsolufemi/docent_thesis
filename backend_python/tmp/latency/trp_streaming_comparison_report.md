# Gemma 4 TRP streaming comparison

Date: 29 July 2026

Branch: `voice-pipeline-timing-test`

## Objective

Compare otherwise identical `gemma4:cloud` structured TRP requests:

1. Non-streaming response.
2. Streaming response.

Both modes used:

- `think: false`
- Temperature zero.
- A 160-token generation limit.
- The same JSON schema.
- The same 20 balanced complete/incomplete utterances.
- Randomised, interleaved request order.

## Accuracy and reliability

| Mode | Valid cases | Correct cases |
|---|---:|---:|
| Non-streaming | 20/20 | 20/20 |
| Streaming | 20/20 | 20/20 |

An earlier exploratory pass produced one 30-second streaming timeout. The
corrected recorded pass completed all 20 streaming requests successfully.
Cloud tail-latency monitoring remains advisable.

## End-to-end request latency

| Mode | Median | Mean | p95 | Minimum | Maximum |
|---|---:|---:|---:|---:|---:|
| Non-streaming | 1.4967 s | 1.9130 s | 4.8570 s | 1.0923 s | 6.7539 s |
| Streaming, response complete | 1.2603 s | 1.4551 s | 2.1356 s | 0.9515 s | 2.5131 s |

Comparing aggregate medians, the fully completed streaming response was
0.2364 seconds, or 15.8%, faster.

## Streaming milestones

| Streaming milestone | Median | p95 | Safe to use? |
|---|---:|---:|---|
| First content chunk | 0.7563 s | 1.6380 s | No |
| Probability and Boolean fields observed | 0.9598 s | 1.7871 s | Potentially, with a robust incremental parser |
| Fully valid schema-checked JSON | **1.1458 s** | **2.0616 s** | **Yes** |
| Ollama `done` response | 1.2603 s | 2.1356 s | Yes |

The first content chunk cannot safely drive the turn decision because the
required fields may be absent or incomplete.

## Paired case comparison

Each utterance had one non-streaming and one streaming request.

| Comparison | Result |
|---|---:|
| Valid pairs | 20 |
| Streaming valid JSON faster | 15/20 cases |
| Median paired valid-JSON saving | **0.1880 s** |
| Mean paired valid-JSON saving | 0.5689 s |
| Streaming decision fields faster | 19/20 cases |
| Median paired decision-field saving | **0.4053 s** |

The paired valid-JSON result is the fairest conservative estimate. Aggregate
median differences are more sensitive to the non-streaming mode's cloud
outliers.

## Recommendation

Use the streaming structured profile for production TRP:

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

Accumulate streamed response fragments and validate the complete
`TRPPrediction` object after every content fragment. Return and close the
stream as soon as the full JSON object passes schema validation.

Do not initially act on regex-extracted partial fields. That path offered a
larger 0.4053-second median saving, but it depends on key order and incomplete
JSON. It can be evaluated later with a proper incremental JSON parser.

## Expected benefit

The conservative expected reduction is approximately:

- 0.188 seconds median on paired cases.
- 0.236 seconds when comparing aggregate medians.
- Roughly 13–16% of the TRP request duration.

Streaming is beneficial, but the main latency gain still comes from disabling
thinking and enforcing structured output.
