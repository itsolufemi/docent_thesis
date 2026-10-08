# Corrected classifier architecture comparison

## Experimental question

The benchmark compares two genuinely different architectures from a finalised text request to the first non-empty main-model response token:

1. **Sequential:** a separate optimised `gemma4:cloud` utterance-classifier request, context resolution, then a fresh streamed request to the selected main model.
2. **Unified classifier tool:** the selected main model itself supplies the utterance classification as mandatory `classify_utterance` tool arguments. The backend only validates and normalises those arguments, resolves context, then resumes the same main-model conversation.

The unified tool no longer invokes `classify_docent_utterance()` or any other classifier model. Its measured tool execution time is therefore local validation time, approximately 0.2 ms.

Each matrix contains three repetitions of:

- an artwork retrieval request;
- a greeting that does not need retrieval;
- a tour action that needs retrieval and further tool handling.

Both architectures use streaming for the main-model response, and the execution order alternates within pairs.

## Corrected results

| Main-model profile | Sequential median total | Unified median total | Unified classification round | Unified resumed response | Paired unified wins | Median paired saving | Accuracy sequential / unified |
|---|---:|---:|---:|---:|---:|---:|---:|
| Gemma 4, thinking disabled, confirmation | **4.5502s** | 5.9249s | 1.9536s | 2.2762s | 2/9 | -1.0725s | 9/9 / 9/9 |
| Gemma 4, thinking enabled | **8.2438s** | 11.1269s | 3.1614s | 5.9179s | 4/9 | -0.9105s | 9/9 / 9/9 |
| GPT-OSS 120B, thinking disabled | 11.7966s | **6.8083s** | 3.8700s | 2.5047s | 2/9 | -1.8217s | 9/9 / 8/9 |

The GPT-OSS row illustrates why the pooled median alone is unsafe: although its unified pooled median was lower, the unified architecture lost seven of nine exact paired comparisons. Large, uneven response-stage outliers changed the pooled ordering. The paired result is the stronger architectural comparison.

## Gemma 4 no-thinking confirmation by case

| Case | Sequential median | Unified median | Difference in favour of unified |
|---|---:|---:|---:|
| Artwork information | **4.5502s** | 5.9249s | -1.3747s |
| Greeting | **3.8486s** | 4.0166s | -0.1680s |
| Highlights tour | **6.6295s** | 10.7506s | -4.1211s |

The unified classifier was accurate in all confirmation samples, but continuation did not materially accelerate the response stage: the median resumed response was 2.2762 seconds versus 2.3096 seconds for a fresh sequential response. Its 33 ms pooled advantage was overwhelmed by the added mandatory main-model classification round and tour variability.

## Cloud-variance observation

The first corrected Gemma 4 no-thinking matrix ran during a severe cloud slowdown:

| Metric | First run | Confirmation |
|---|---:|---:|
| Separate classifier median | 16.3214s | 1.7594s |
| Unified classification-round median | 12.3941s | 1.9536s |
| Sequential total median | 19.7597s | 4.5502s |
| Unified total median | 15.7474s | 5.9249s |

That first matrix also produced two incorrect classifications from the separate classifier. It remains preserved as load/variance evidence, but it should not be used as the production latency estimate. The confirmation run, collected immediately after the GPT-OSS and thinking-enabled matrices, had 18/18 correct classifications across both architectures.

## Accuracy observations

- Gemma 4 no-thinking confirmation: both architectures were 9/9 correct.
- Gemma 4 thinking enabled: both architectures were 9/9 correct.
- GPT-OSS unified: 8/9 correct. One highlights-tour result selected the correct action but incorrectly set `requires_retrieval=false`.
- The severely delayed first Gemma no-thinking matrix was 7/9 sequential and 9/9 unified.

This is a small routing suite, not a sufficient classifier-quality evaluation. It is useful for detecting protocol failures and major regressions, but the broader utterance-classifier suite is still required before changing production architecture.

## Recommendation

Retain the **sequential architecture with Gemma 4 thinking disabled** for the current main system.

The corrected unified architecture now faithfully implements the intended design, but the confirmation data does not show a latency advantage:

- it won only 2/9 paired Gemma no-thinking samples;
- its median paired result was 1.0725 seconds slower;
- reusing classification history saved essentially nothing at the median response boundary;
- its tour path showed the largest penalty and variability.

Keep `classifier_tool` as an experimental routing mode for future prompt/model work. Do not select it merely from the old benchmark: that implementation still made a hidden separate classifier request and did not test the architecture described here.

## Reports

- `classifier_architecture_gemma4_think_false_confirmation.json` and `.md`: recommended comparison run.
- `classifier_architecture_gemma4_think_false.json` and `.md`: corrected but cloud-degraded run.
- `classifier_architecture_gemma4_think_true.json` and `.md`: Gemma thinking-enabled run.
- `classifier_architecture_gpt_oss_think_false.json` and `.md`: GPT-OSS 120B run.
- `classifier_tool_checkpoint.json`: corrected three-case live protocol smoke test.
