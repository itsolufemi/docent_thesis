# Sequential vs classifier-tool architecture

Boundary: finalized text request to the first non-empty main-model response token.

Sequential uses the separate configured utterance-classifier model, then starts a fresh main-model response request. The classifier-tool architecture asks the main model itself to provide classification fields as mandatory tool arguments, validates them locally without another model request, and resumes that same main-model conversation.

| Median interval | Sequential | Classifier tool |
|---|---:|---:|
| Main model → classifier tool call | n/a | 1.9536s |
| Separate classifier / tool validation | 1.7594s | 0.0002s |
| Context resolution | 0.9409s | 1.0522s |
| Main model start/resume → first token | 2.3096s | 2.2762s |
| **Total → first token** | **4.5502s** | **5.9249s** |

Classifier-tool was faster in 2/9 paired samples.
Median classifier-tool saving: -1.0725s.
The resumed response stage was faster in 3/9 pairs, with a median saving of -0.1804s.
Classification accuracy: sequential 9/9 (100.0%); classifier-tool 9/9 (100.0%).

## Per-case medians

| Case | Sequential total | Tool total | Sequential response stage | Tool response stage |
|---|---:|---:|---:|---:|
| artwork_information | 4.5502s | 5.9249s | 1.3158s | 2.2762s |
| greeting | 3.8486s | 4.0166s | 1.3664s | 1.6552s |
| highlights_tour | 6.6295s | 10.7506s | 3.9595s | 8.0866s |

## Interpretation

The sequential architecture had the lower paired median end-to-end time to the first response token in this run.
The sequential architecture had the lower paired median response-stage latency. This isolates whether reusing the main model's classification conversation helped its subsequent response begin.
Latency and classification accuracy must be considered together; a faster invalid classification is not a successful sample.

## Paired samples

| Case | Run | Sequential | Classifier tool | Tool saving |
|---|---:|---:|---:|---:|
| artwork_information | 1 | 4.5502s | 4.5151s | 0.0351s |
| artwork_information | 2 | 4.8524s | 5.9249s | -1.0725s |
| artwork_information | 3 | 3.7773s | 7.1730s | -3.3957s |
| greeting | 1 | 4.3064s | 3.4555s | 0.8509s |
| greeting | 2 | 3.8486s | 4.0166s | -0.1680s |
| greeting | 3 | 2.7722s | 4.4015s | -1.6293s |
| highlights_tour | 1 | 6.6295s | 6.6546s | -0.0251s |
| highlights_tour | 2 | 8.3137s | 13.1071s | -4.7934s |
| highlights_tour | 3 | 6.1924s | 10.7506s | -4.5582s |
