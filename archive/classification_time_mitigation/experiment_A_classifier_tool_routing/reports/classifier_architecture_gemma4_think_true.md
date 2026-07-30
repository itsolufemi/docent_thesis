# Sequential vs classifier-tool architecture

Boundary: finalized text request to the first non-empty main-model response token.

Sequential uses the separate configured utterance-classifier model, then starts a fresh main-model response request. The classifier-tool architecture asks the main model itself to provide classification fields as mandatory tool arguments, validates them locally without another model request, and resumes that same main-model conversation.

| Median interval | Sequential | Classifier tool |
|---|---:|---:|
| Main model → classifier tool call | n/a | 3.1614s |
| Separate classifier / tool validation | 1.6061s | 0.0002s |
| Context resolution | 0.8959s | 0.8239s |
| Main model start/resume → first token | 6.4480s | 5.9179s |
| **Total → first token** | **8.2438s** | **11.1269s** |

Classifier-tool was faster in 4/9 paired samples.
Median classifier-tool saving: -0.9105s.
The resumed response stage was faster in 6/9 pairs, with a median saving of 1.4354s.
Classification accuracy: sequential 9/9 (100.0%); classifier-tool 9/9 (100.0%).

## Per-case medians

| Case | Sequential total | Tool total | Sequential response stage | Tool response stage |
|---|---:|---:|---:|---:|
| artwork_information | 7.5226s | 9.4538s | 5.1509s | 4.7155s |
| greeting | 4.6687s | 6.3706s | 3.4189s | 2.5697s |
| highlights_tour | 15.4524s | 17.8553s | 12.4784s | 12.6843s |

## Interpretation

The sequential architecture had the lower paired median end-to-end time to the first response token in this run.
The classifier-tool architecture had the lower paired median response-stage latency. This isolates whether reusing the main model's classification conversation helped its subsequent response begin.
Latency and classification accuracy must be considered together; a faster invalid classification is not a successful sample.

## Paired samples

| Case | Run | Sequential | Classifier tool | Tool saving |
|---|---:|---:|---:|---:|
| artwork_information | 1 | 7.3845s | 11.1269s | -3.7424s |
| artwork_information | 2 | 14.8260s | 7.8321s | 6.9939s |
| artwork_information | 3 | 7.5226s | 9.4538s | -1.9312s |
| greeting | 1 | 8.2438s | 6.3706s | 1.8732s |
| greeting | 2 | 4.6687s | 4.5025s | 0.1662s |
| greeting | 3 | 4.0717s | 15.6426s | -11.5709s |
| highlights_tour | 1 | 16.9448s | 17.8553s | -0.9105s |
| highlights_tour | 2 | 9.0399s | 42.0962s | -33.0563s |
| highlights_tour | 3 | 15.4524s | 11.7300s | 3.7224s |
