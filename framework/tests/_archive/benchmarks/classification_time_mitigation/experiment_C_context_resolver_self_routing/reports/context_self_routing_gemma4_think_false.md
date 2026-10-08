# Context-resolver self-routing benchmark

Model: `gemma4:cloud`

Thinking: `False`

| Metric | Result |
|---|---:|
| Valid route blocks | 15/15 |
| Route accuracy | 9/15 |
| Retrieval-available accuracy | 15/15 |
| Retrieval-used accuracy | 12/15 |
| Candidate-subject accuracy | 15/15 |
| Proposed-action accuracy | 12/15 |
| Tool accuracy | 15/15 |
| Median self-routing time | 2.6691s |
| Median first spoken time | 2.6766s |
| Median complete response | 3.6797s |
| Route-header leaks | 0 |

## Samples

| Case | Run | Valid | Route | Retrieval used | Candidate | Tool | Route time | First speech | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| artwork_information | 1 | True | True | True | True | True | 4.7086s | 4.7086s | 10.1231s |
| greeting | 1 | True | True | True | True | True | 1.5793s | 1.5793s | 1.8488s |
| current_subject | 1 | True | True | True | True | True | 1.7523s | 1.7523s | 2.0163s |
| highlights_tour | 1 | True | False | False | True | True | 3.1289s | 3.129s | 5.1142s |
| noise | 1 | True | False | True | True | True | 2.9509s | 3.0413s | 3.6496s |
| artwork_information | 2 | True | True | True | True | True | 2.0741s | 2.115s | 4.7091s |
| greeting | 2 | True | True | True | True | True | 1.9245s | 1.9245s | 2.1452s |
| current_subject | 2 | True | True | True | True | True | 1.0813s | 1.0813s | 1.265s |
| highlights_tour | 2 | True | False | False | True | True | 4.2772s | 4.2772s | 4.8305s |
| noise | 2 | True | False | True | True | True | 44.3413s | 44.3413s | 46.3358s |
| artwork_information | 3 | True | True | True | True | True | 2.629s | 2.629s | 6.8089s |
| greeting | 3 | True | True | True | True | True | 2.9535s | 2.9535s | 3.6797s |
| current_subject | 3 | True | True | True | True | True | 37.879s | 37.879s | 38.0902s |
| highlights_tour | 3 | True | False | False | True | True | 2.6691s | 2.6766s | 3.1824s |
| noise | 3 | True | False | True | True | True | 2.3351s | 2.3351s | 2.7036s |
