# Sequential vs classifier-tool architecture

Boundary: finalized text request to the first non-empty main-model response token.

Sequential uses the separate configured utterance-classifier model, then starts a fresh main-model response request. The classifier-tool architecture asks the main model itself to provide classification fields as mandatory tool arguments, validates them locally without another model request, and resumes that same main-model conversation.

| Median interval | Sequential | Classifier tool |
|---|---:|---:|
| Main model → classifier tool call | n/a | 12.3941s |
| Separate classifier / tool validation | 16.3214s | 0.0002s |
| Context resolution | 0.0001s | 0.3088s |
| Main model start/resume → first token | 1.8560s | 1.2107s |
| **Total → first token** | **19.7597s** | **15.7474s** |

Classifier-tool was faster in 6/9 paired samples.
Median classifier-tool saving: 4.2830s.
The resumed response stage was faster in 6/9 pairs, with a median saving of 0.4933s.
Classification accuracy: sequential 7/9 (77.8%); classifier-tool 9/9 (100.0%).

## Per-case medians

| Case | Sequential total | Tool total | Sequential response stage | Tool response stage |
|---|---:|---:|---:|---:|
| artwork_information | 19.7597s | 13.8795s | 0.9457s | 1.1385s |
| greeting | 9.3717s | 15.7474s | 1.5248s | 1.0315s |
| highlights_tour | 35.7605s | 32.0157s | 16.8950s | 13.9212s |

## Interpretation

The classifier-tool architecture had the lower paired median end-to-end time to the first response token in this run.
The classifier-tool architecture had the lower paired median response-stage latency. This isolates whether reusing the main model's classification conversation helped its subsequent response begin.
Latency and classification accuracy must be considered together; a faster invalid classification is not a successful sample.

## Paired samples

| Case | Run | Sequential | Classifier tool | Tool saving |
|---|---:|---:|---:|---:|
| artwork_information | 1 | 21.0948s | 14.4455s | 6.6493s |
| artwork_information | 2 | 19.7597s | 13.8795s | 5.8802s |
| artwork_information | 3 | 16.1030s | 9.5572s | 6.5458s |
| greeting | 1 | 9.3717s | 15.7474s | -6.3757s |
| greeting | 2 | 20.4207s | 16.6168s | 3.8039s |
| greeting | 3 | 8.6743s | 13.2806s | -4.6063s |
| highlights_tour | 1 | 35.7605s | 31.4775s | 4.2830s |
| highlights_tour | 2 | 37.1222s | 32.0157s | 5.1065s |
| highlights_tour | 3 | 3.2766s | 53.4465s | -50.1699s |
