# Classifier request-profile benchmark

Model: `gemma4:cloud`. Cases: 20. Each legacy/optimized pair ran back-to-back, with first-run order alternated between cases.

| Profile | Valid | Exact accuracy | Median | Mean | P95 |
|---|---:|---:|---:|---:|---:|
| Legacy non-streaming | 20/20 | 100% | 2.9459s | 3.2844s | 7.2669s |
| Optimized structured streaming | 20/20 | 100% | 1.8014s | 2.9731s | 6.3747s |

## Paired latency

- Median saving: 0.3323s (15.4%).
- Mean saving: 0.3113s.
- Optimized faster in 10/20 valid pairs.

## Interpretation

- Both profiles produced valid, exact decisions on all 20 cases.
- Aggregate median request-to-output latency fell by 1.1445s (38.9%).
- The paired median is the more conservative estimate because cloud latency varied substantially between individual requests.
- The optimized response requests only the five fields required for routing. `is_relevant`, `should_ignore`, `confidence`, and `reason` are derived or defaulted server-side.

## Cases

| Case | Legacy | Optimized | Saving | Legacy correct | Optimized correct |
|---|---:|---:|---:|---:|---:|
| greeting | 4.0561s | 1.2207s | 2.8354s | True | True |
| artwork_information | 3.3255s | 1.2547s | 2.0708s | True | True |
| artist_information | 2.0367s | 1.2734s | 0.7633s | True | True |
| next_artwork | 1.3269s | 2.0233s | -0.6964s | True | True |
| highlights_tour | 4.2522s | 18.2705s | -14.0183s | True | True |
| stop_tour | 2.5951s | 3.6977s | -1.1026s | True | True |
| spoken_correction | 1.4809s | 1.5795s | -0.0986s | True | True |
| artwork_comparison | 1.2893s | 5.7486s | -4.4593s | True | True |
| painting_interpretation | 1.5810s | 2.3257s | -0.7447s | True | True |
| room_information | 3.6666s | 1.2732s | 2.3934s | True | True |
| portrait_tour | 2.4971s | 1.1965s | 1.3006s | True | True |
| close_current_tour | 3.0567s | 3.4764s | -0.4197s | True | True |
| previous_artwork | 4.1140s | 1.1298s | 2.9842s | True | True |
| repeat_request | 3.0950s | 3.8200s | -0.7250s | True | True |
| museum_hours | 4.2421s | 1.3997s | 2.8424s | True | True |
| artist_comparison | 2.3684s | 0.9500s | 1.4184s | True | True |
| interrupt_stop | 2.8352s | 3.1609s | -0.3257s | True | True |
| interrupt_redirect | 7.1832s | 1.0818s | 6.1014s | True | True |
| backchannel_right | 1.8281s | 2.1272s | -0.2991s | True | True |
| backchannel_i_see | 8.8581s | 2.4523s | 6.4058s | True | True |

## Latency trends by utterance type

The results suggest some differences by classification task, although the sample contains only one optimized measurement per utterance and cloud latency varied substantially. These figures should therefore be treated as preliminary tendencies rather than causal findings.

| Optimized category | Cases | Median latency | Mean latency |
|---|---:|---:|---:|
| Retrieval required | 10 | 1.2733s | 3.4774s |
| Retrieval not required | 10 | 2.2898s | 2.4688s |
| Response request | 13 | 1.3997s | 2.0768s |
| Interruption | 3 | 1.5795s | 1.9407s |
| Call to action | 4 | 3.5870s | 6.6603s |
| No candidate subjects | 10 | 2.2898s | 2.4688s |
| One candidate subject | 8 | 1.2733s | 3.5094s |
| Two candidate subjects | 2 | 3.3493s | 3.3493s |

### Retrieval decisions

Requests classified as requiring retrieval had a lower optimized median than requests not requiring retrieval. This does not mean retrieval itself was faster. The measured interval ended when the classifier produced its output; no vector search or evidence processing occurred inside it.

Explicit factual requests often presented comparatively easy classification cues: a recognizable information request, a named subject, a retrieval decision, and no structural action. Examples included:

| Case | Optimized latency |
|---|---:|
| Greeting | 1.2207s |
| Artwork information | 1.2547s |
| Artist information | 1.2734s |
| Room information | 1.2732s |
| Museum hours | 1.3997s |

The legacy profile showed almost no median difference between retrieval and non-retrieval decisions:

| Legacy category | Median latency |
|---|---:|
| Retrieval required | 2.9113s |
| Retrieval not required | 2.9460s |

This further indicates that the observed optimized difference should not be interpreted as an inherent cost of retrieval classification.

### Structural actions

Calls to action were the slowest routing category by median. These cases require the model to distinguish an ordinary conversational request from one of the domain's permitted structural actions and, when appropriate, select the correct action name.

| Case | Optimized latency |
|---|---:|
| Portrait tour | 1.1965s |
| Close current tour | 3.4764s |
| Stop tour | 3.6977s |
| Highlights tour | 18.2705s |

The highlights-tour measurement is a clear cloud-latency outlier and substantially inflates the category mean. Nevertheless, the two tour-closing decisions also took longer than the optimized overall median.

### Context-sensitive short utterances

Short utterances were not automatically faster. Backchannels such as “Right.” and “I see.” are lexically simple but pragmatically ambiguous because the classifier must decide whether they acknowledge the assistant, interrupt it, or introduce a new turn.

| Case | Optimized latency |
|---|---:|
| Backchannel: “Right.” | 2.1272s |
| Backchannel: “I see.” | 2.4523s |

### Subject extraction

The experiment did not establish that extracting more candidate subjects inherently increases latency. The two cases containing two extracted subjects produced sharply different results:

| Case | Subjects | Optimized latency |
|---|---|---:|
| Artist comparison | Fragonard, Boucher | 0.9500s |
| Artwork comparison | The Arab Tent, Guernica | 5.7486s |

The difference is too large to attribute credibly to one additional subject token. Cloud variability is the more plausible explanation.

### Preliminary conclusion

Explicit factual requests with named subjects appear to be straightforward classifier decisions. Structural actions and context-dependent conversational signals appear harder. Actual retrieval complexity has no effect within this benchmark because retrieval occurs after the measured classifier boundary.

A stronger category-level conclusion would require multiple repetitions of every utterance under comparable cloud conditions. The present experiment establishes useful hypotheses for that larger benchmark but does not prove that utterance type alone caused the observed latency differences.
