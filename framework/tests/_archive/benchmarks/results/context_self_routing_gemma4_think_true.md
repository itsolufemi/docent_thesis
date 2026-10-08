# Context-resolver self-routing benchmark

Model: `gemma4:cloud`

Thinking: `True`

| Metric | Result |
|---|---:|
| Valid route blocks | 15/15 |
| Route accuracy | 15/15 |
| Retrieval-available accuracy | 15/15 |
| Retrieval-used accuracy | 13/15 |
| Candidate-subject accuracy | 15/15 |
| Proposed-action accuracy | 15/15 |
| Tool accuracy | 15/15 |
| Median self-routing time | 4.9869s |
| Median first spoken time | 5.3757s |
| Median complete response | 5.3095s |
| Route-header leaks | 0 |

## Samples

| Case | Run | Valid | Route | Retrieval used | Candidate | Tool | Route time | First speech | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| artwork_information | 1 | True | True | True | True | True | 3.2297s | 3.2522s | 4.1822s |
| greeting | 1 | True | True | True | True | True | 26.8135s | 26.8135s | 27.1708s |
| current_subject | 1 | True | True | True | True | True | 2.6308s | 2.6309s | 2.8437s |
| highlights_tour | 1 | True | True | False | True | True | 17.5946s | 21.0901s | 21.5381s |
| noise | 1 | True | True | True | True | True | 2.9144s | Nones | 2.9871s |
| artwork_information | 2 | True | True | True | True | True | 3.9907s | 3.9907s | 4.8411s |
| greeting | 2 | True | True | True | True | True | 4.8153s | 4.8153s | 5.0128s |
| current_subject | 2 | True | True | True | True | True | 5.7645s | 5.7645s | 6.0338s |
| highlights_tour | 2 | True | True | False | True | True | 33.4257s | 48.3565s | 48.6626s |
| noise | 2 | True | True | True | True | True | 2.6759s | Nones | 2.7635s |
| artwork_information | 3 | True | True | True | True | True | 7.1873s | 7.2269s | 8.2629s |
| greeting | 3 | True | True | True | True | True | 3.6753s | 3.6753s | 3.8627s |
| current_subject | 3 | True | True | True | True | True | 4.9869s | 4.9869s | 5.3095s |
| highlights_tour | 3 | True | True | True | True | True | 22.3916s | 24.7827s | 25.1501s |
| noise | 3 | True | True | True | True | True | 5.3628s | Nones | 5.4903s |
