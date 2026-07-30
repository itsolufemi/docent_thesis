# Context-resolver self-routing experiment

## Architecture

```text
final utterance
→ current subject lookup
→ vector retrieval and keyword fallback
→ explicit candidate-subject list
→ one main-model conversation
→ hidden self-routing metadata
→ operational tools when required
→ spoken response
```

The active query, turn-buffer, and streaming turn-buffer routes do not invoke the utterance classifier. The resolver gathers evidence and subjects only; it does not classify or mutate the conversation tree.

Self-routing metadata remains observational. `candidate_subject_reference` and `should_update_subject` do not change state. Registered conversation-tree tools remain the only model-controlled mutation mechanism.

## Test design

Each profile processed three repetitions of:

- `Tell me about The Arab Tent.`
- `Hi, how are you?`
- `What painting is this?`, with `painting:581` preloaded as the current subject
- `Start a highlights tour.`
- `[unintelligible background noise]`

The benchmark measured route validity and accuracy, retrieval claims, candidate selection, proposed actions, operational tools, self-routing latency, first spoken content, complete response latency, and route-header leakage.

## Tuned results

| Profile | Valid blocks | Route | Retrieval available | Retrieval used | Candidate | Action | Tool | Route time | First speech | Complete response |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Gemma 4, thinking disabled** | **15/15** | **15/15** | **15/15** | 12/15 | **15/15** | **15/15** | **15/15** | **2.8693s** | **3.0214s** | **3.6106s** |
| Gemma 4, thinking enabled | 15/15 | 15/15 | 15/15 | **13/15** | 15/15 | 15/15 | 15/15 | 4.9869s | 5.3757s | 5.3095s |
| GPT-OSS 120B, thinking disabled | 15/15 | 12/15 | 15/15 | 12/15 | 11/15 | 13/15 | 12/15 | 4.4612s | 4.4612s | 5.5679s |

Noise responses can correctly contain no spoken content, so first-speech medians exclude the three noise samples. Complete-response medians include them.

All 45 tuned responses produced schema-valid metadata. No route header reached the spoken response or dialogue history.

## Gemma 4 without thinking by case

| Case | Route metadata | First speech | Complete response |
|---|---:|---:|---:|
| Artwork information | 2.8693s | 2.8693s | 7.1542s |
| Greeting | 3.1655s | 3.1656s | 3.7173s |
| Current subject | **1.3074s** | **1.3074s** | **1.6186s** |
| Highlights tour | 3.1677s | 5.8626s | 6.1301s |
| Noise | 2.8385s | no speech | 2.9183s |

The current-subject path is particularly strong: the resolver supplied `painting:581` directly, and Gemma selected it correctly in all three samples without vector-search ambiguity.

## Prompt correction

The first Gemma/no-thinking matrix used a weaker routing instruction. The model executed tour tools before producing metadata and then classified the post-tool stage rather than the original visitor request. It also described noise correctly in its reason while selecting `response_request`.

The prompt was corrected to:

- classify the original user utterance even after a tool result;
- define every route enum explicitly;
- retain `call_to_action` and `proposed_action` after tool execution;
- count retrieved subjects used in tool arguments as retrieval use.

After that correction:

```text
route accuracy:          9/15 → 15/15
proposed-action accuracy:12/15 → 15/15
tool accuracy:          15/15 → 15/15
```

Tool events are now held at the query-engine boundary until the self-routing event has been emitted, ensuring the externally visible stream order is:

```text
response_started
→ self_routing
→ tool events, if any
→ spoken content
→ response_complete
```

## Remaining retrieval-use limitation

Gemma without thinking marked all three tour samples as `retrieval_used=false`. However, every successful `create_conversation_branch` call used retrieved subjects:

- `painting:474` — Venus in Search of Cupid Surprises Diana
- `painting:900` — Queen Victoria

This is an inaccurate self-report, not a retrieval or tool failure. Thinking enabled corrected one of the three tour claims but introduced major latency outliers and is not worthwhile.

`retrieval_used` should therefore remain debug-only. If it becomes operationally important, the backend can derive tool-level retrieval use deterministically by comparing tool references with supplied candidate references.

## GPT-OSS findings

GPT-OSS was less reliable:

- two of three tour requests were labelled `response_request`;
- all tour sequences required invalid tool-call retries, so strict tool correctness was 0/3 for that case;
- one greeting and two tour/noise samples selected irrelevant `painting:581` candidates;
- one noise sample was treated as a response request;
- tour latency reached a 17.0526-second median to first speech.

## Comparison with previous architectures

Using the three shared non-noise cases:

| Architecture | Median to first user-facing token |
|---|---:|
| **Context-resolver self-routing, Gemma 4** | **3.1559s** |
| Earlier model self-routing, Gemma 4 | 4.1499s |
| Separate classifier then Gemma response | 4.5502s |
| Mandatory classifier tool then Gemma resume | 5.9249s |

These experiments occurred in different cloud windows, so the differences are indicative rather than a controlled paired test. Nevertheless, the context-resolver design currently has the strongest combination of latency, route accuracy, candidate selection, and operational-tool behavior.

## Recommendation

Continue with:

```text
OLLAMA_MODEL=gemma4:cloud
OLLAMA_MAIN_THINK=false
```

This is the best-performing architecture tested so far. Before replacing the sequential production classifier permanently:

1. run the larger utterance-routing accuracy suite;
2. derive tool-level retrieval use deterministically rather than trusting self-report;
3. test candidate rejection with a broader range of greetings, noise, and unrelated conversation;
4. run a same-session paired comparison against the sequential classifier architecture.

## Reports

- `context_self_routing_gemma4_think_false_confirmation.json` and `.md`
- `context_self_routing_gemma4_think_true.json` and `.md`
- `context_self_routing_gpt_oss_think_false.json` and `.md`
- `context_self_routing_gemma4_think_false.json` and `.md` — initial prompt iteration
