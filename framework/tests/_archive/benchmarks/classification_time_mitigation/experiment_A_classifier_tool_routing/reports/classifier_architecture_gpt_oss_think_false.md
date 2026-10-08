# Sequential vs classifier-tool architecture

Boundary: finalized text request to the first non-empty main-model response token.

Sequential uses the separate configured utterance-classifier model, then starts a fresh main-model response request. The classifier-tool architecture asks the main model itself to provide classification fields as mandatory tool arguments, validates them locally without another model request, and resumes that same main-model conversation.

| Median interval | Sequential | Classifier tool |
|---|---:|---:|
| Main model → classifier tool call | n/a | 3.8700s |
| Separate classifier / tool validation | 1.0144s | 0.0002s |
| Context resolution | 0.3824s | 0.3813s |
| Main model start/resume → first token | 9.7215s | 2.5047s |
| **Total → first token** | **11.7966s** | **6.8083s** |

Classifier-tool was faster in 2/9 paired samples.
Median classifier-tool saving: -1.8217s.
The resumed response stage was faster in 6/9 pairs, with a median saving of 0.4246s.
Classification accuracy: sequential 9/9 (100.0%); classifier-tool 8/9 (88.9%).

## Per-case medians

| Case | Sequential total | Tool total | Sequential response stage | Tool response stage |
|---|---:|---:|---:|---:|
| artwork_information | 16.1720s | 6.8083s | 13.4556s | 2.5047s |
| greeting | 2.1957s | 4.8071s | 1.3606s | 1.0043s |
| highlights_tour | 12.4808s | 16.1142s | 10.4212s | 10.5694s |

## Interpretation

The sequential architecture had the lower paired median end-to-end time to the first response token in this run.
The classifier-tool architecture had the lower paired median response-stage latency. This isolates whether reusing the main model's classification conversation helped its subsequent response begin.
Latency and classification accuracy must be considered together; a faster invalid classification is not a successful sample.

## Paired samples

| Case | Run | Sequential | Classifier tool | Tool saving |
|---|---:|---:|---:|---:|
| artwork_information | 1 | 3.7018s | 6.8083s | -3.1065s |
| artwork_information | 2 | 16.1720s | 6.8842s | 9.2878s |
| artwork_information | 3 | 18.4986s | 4.4197s | 14.0789s |
| greeting | 1 | 2.0141s | 3.8358s | -1.8217s |
| greeting | 2 | 2.1957s | 4.8071s | -2.6114s |
| greeting | 3 | 2.9268s | 5.3290s | -2.4022s |
| highlights_tour | 1 | 15.9763s | 16.3006s | -0.3243s |
| highlights_tour | 2 | 11.7966s | 12.9437s | -1.1471s |
| highlights_tour | 3 | 12.4808s | 16.1142s | -3.6334s |
