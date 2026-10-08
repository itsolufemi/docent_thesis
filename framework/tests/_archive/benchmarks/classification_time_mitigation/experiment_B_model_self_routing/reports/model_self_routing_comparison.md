# Model self-routing experiment

## Architecture

This branch removes the utterance classifier from the active request flow:

```text
final transcript
→ unconditional context/retrieval prefetch
→ one main-model conversation
→ hidden route header
→ operational tools when requested
→ streamed spoken response
```

The classifier implementation remains in the repository but is not wired into the query, turn-buffer, or streaming turn-buffer routes. A regression test patches `route_utterance()` and confirms that the model-routing resolver never calls it.

The model must begin its first assistant output with:

```text
<route>{valid ModelRouteAssessment JSON}</route>
```

The route parser withholds this header from the user and TTS, emits a `route_assessment` streaming event, and releases only the following spoken text. Malformed or missing headers do not cause a retry or discard an otherwise valid answer.

## Test design

Each model profile processed three repetitions of four labelled cases:

- artwork information requiring retrieved context;
- a greeting not requiring retrieval;
- a highlights-tour action requiring an operational branch tool;
- an unintelligible noise transcript.

Measurements begin at the finalised text request and include retrieval.

## Summary

| Profile | Valid route blocks | Strict route agreement | Tool correctness | Median route block | Median first speech | Median full response |
|---|---:|---:|---:|---:|---:|---:|
| **Gemma 4, thinking disabled** | **12/12** | **8/12** | **12/12** | **3.1167s** | **3.2880s** | **4.0289s** |
| Gemma 4, thinking enabled | 12/12 | 7/12 | 12/12 | 8.0717s | 9.4632s | 12.6225s |
| GPT-OSS 120B, thinking disabled | 12/12 | 6/12 | 9/12 | 5.3198s | 5.3198s | 6.5830s |

All 36 responses produced schema-valid route blocks, and no route header leaked into the stored or spoken response.

## Per-case median time to first speech

| Case | Gemma 4, no thinking | Gemma 4, thinking | GPT-OSS 120B |
|---|---:|---:|---:|
| Artwork information | 5.3233s | 5.9383s | 5.3514s |
| Greeting | **2.4721s** | 4.2585s | 5.0724s |
| Highlights tour | **5.6359s** | 29.8578s | 6.0564s |
| Noise | **3.1221s** | 24.6036s | 5.2685s |

For the same three non-noise case types used in the preceding architecture experiment, Gemma 4 without thinking had a 4.1499-second median to first spoken content. The earlier sequential Gemma confirmation measured 4.5502 seconds to its first response token. This suggests a modest approximately 0.40-second advantage, but the runs occurred in different cloud windows and should not be treated as a controlled paired result.

## Routing findings

### Gemma 4 without thinking

- Artwork and greeting routing agreed in all six samples.
- It correctly labelled all three tour requests as `call_to_action`, populated `start_highlights_tour`, and successfully called `create_conversation_branch`.
- It nevertheless reported `retrieval_required=false` and `retrieved_context_used=false` for every tour.
- The generated tour branches contained subjects from the retrieved evidence, demonstrating that the model's self-report was inconsistent with its actual behavior.
- Two of three noise samples were correct. One described the input as background noise but incorrectly used `response_request` with `should_ignore=false`.

Strict agreement is therefore 8/12, while high-level route-type agreement is 11/12 and operational correctness is 12/12.

### Gemma 4 with thinking

- Protocol validity and tool execution remained perfect.
- It did not improve routing agreement.
- Tour latency became extreme: the median was 29.8578 seconds to first speech, with one sample taking 50.8205 seconds.
- Thinking is not suitable for this latency-sensitive path.

### GPT-OSS 120B without thinking

- All route blocks were valid.
- It failed to invoke the tour branch tool in all three action samples.
- It produced inconsistent retrieval claims for one greeting and two noise samples.
- Stable latency did not compensate for weaker routing and operational behavior.

## Interpretation

The single-request architecture is technically successful:

- there is no separate classifier request;
- metadata arrives before spoken content;
- parsing adds no second model round;
- operational tools remain controlled;
- malformed metadata can fail open;
- internal headers are not stored or spoken.

However, model-generated routing metadata is not yet reliable enough to act as authoritative control state. The largest problem is not route type: it is the model's inconsistent account of whether prefetched context was required or used. For now, treat the assessment as observational/debug metadata and continue to let explicit operational tools control state mutation.

## Recommendation

Use **Gemma 4 Cloud with thinking disabled** for any further work on this architecture.

It was the fastest profile, had perfect schema validity, executed all operational tools correctly, and achieved the best strict agreement. Before considering this a replacement for the sequential classifier, run a larger routing suite and clarify the semantics of:

```text
retrieval_required
retrieved_context_used
```

A useful refinement would distinguish:

```text
retrieval_was_needed_for_answer
supplied_context_was_used
```

and explicitly require the second field to reflect evidence actually used in the answer or tool arguments.

## Raw reports

- `model_self_routing_gemma4_think_false.json` and `.md`
- `model_self_routing_gemma4_think_true.json` and `.md`
- `model_self_routing_gpt_oss_think_false.json` and `.md`
