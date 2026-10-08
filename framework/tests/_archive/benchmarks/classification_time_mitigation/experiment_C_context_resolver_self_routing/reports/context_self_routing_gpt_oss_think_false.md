# Context-resolver self-routing benchmark

Model: `gpt-oss:120b-cloud`

Thinking: `False`

| Metric | Result |
|---|---:|
| Valid route blocks | 15/15 |
| Route accuracy | 12/15 |
| Retrieval-available accuracy | 15/15 |
| Retrieval-used accuracy | 12/15 |
| Candidate-subject accuracy | 11/15 |
| Proposed-action accuracy | 13/15 |
| Tool accuracy | 12/15 |
| Median self-routing time | 4.4612s |
| Median first spoken time | 4.4612s |
| Median complete response | 5.5679s |
| Route-header leaks | 0 |

## Samples

| Case | Run | Valid | Route | Retrieval used | Candidate | Tool | Route time | First speech | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| artwork_information | 1 | True | True | True | True | True | 4.347s | 4.347s | 6.3242s |
| greeting | 1 | True | True | True | False | True | 4.4612s | 4.4612s | 4.7223s |
| current_subject | 1 | True | True | True | True | True | 1.8344s | 1.8344s | 3.0315s |
| highlights_tour | 1 | True | False | False | False | False | 17.6762s | 17.6762s | 18.8252s |
| noise | 1 | True | False | False | False | True | 5.6819s | 5.682s | 7.1828s |
| artwork_information | 2 | True | True | True | True | True | 5.482s | 5.482s | 7.3884s |
| greeting | 2 | True | True | True | True | True | 2.9985s | 2.9985s | 3.2561s |
| current_subject | 2 | True | True | True | True | True | 2.0522s | 2.0522s | 3.1008s |
| highlights_tour | 2 | True | True | False | True | False | 13.4821s | 13.4821s | 15.4121s |
| noise | 2 | True | True | True | True | True | 4.8866s | 4.8866s | 5.1459s |
| artwork_information | 3 | True | True | True | True | True | 3.6078s | 3.6078s | 5.6197s |
| greeting | 3 | True | True | True | True | True | 3.8423s | 3.8424s | 4.0529s |
| current_subject | 3 | True | True | True | True | True | 3.1683s | 3.1783s | 4.7022s |
| highlights_tour | 3 | True | False | True | False | False | 17.0525s | 17.0526s | 18.9288s |
| noise | 3 | True | True | True | True | True | 5.3288s | 5.3288s | 5.5679s |
