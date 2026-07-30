# Context-resolver self-routing benchmark

Model: `gemma4:cloud`

Thinking: `False`

| Metric | Result |
|---|---:|
| Valid route blocks | 15/15 |
| Route accuracy | 15/15 |
| Retrieval-available accuracy | 15/15 |
| Retrieval-used accuracy | 12/15 |
| Candidate-subject accuracy | 15/15 |
| Proposed-action accuracy | 15/15 |
| Tool accuracy | 15/15 |
| Median self-routing time | 2.8693s |
| Median first spoken time | 3.0214s |
| Median complete response | 3.6106s |
| Route-header leaks | 0 |

## Samples

| Case | Run | Valid | Route | Retrieval used | Candidate | Tool | Route time | First speech | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| artwork_information | 1 | True | True | True | True | True | 2.2528s | 2.2528s | 3.5577s |
| greeting | 1 | True | True | True | True | True | 1.4623s | 1.4624s | 1.7472s |
| current_subject | 1 | True | True | True | True | True | 1.0028s | 1.0028s | 1.1841s |
| highlights_tour | 1 | True | True | False | True | True | 18.4473s | 21.1311s | 21.5066s |
| noise | 1 | True | True | True | True | True | 2.8385s | Nones | 2.9183s |
| artwork_information | 2 | True | True | True | True | True | 3.0648s | 3.1559s | 7.2387s |
| greeting | 2 | True | True | True | True | True | 13.3671s | 13.4614s | 14.2995s |
| current_subject | 2 | True | True | True | True | True | 1.3074s | 1.3074s | 1.6186s |
| highlights_tour | 2 | True | True | False | True | True | 1.8701s | 2.9815s | 3.1822s |
| noise | 2 | True | True | True | True | True | 3.6274s | Nones | 3.7082s |
| artwork_information | 3 | True | True | True | True | True | 2.8693s | 2.8693s | 7.1542s |
| greeting | 3 | True | True | True | True | True | 3.1655s | 3.1656s | 3.7173s |
| current_subject | 3 | True | True | True | True | True | 3.0613s | 3.0614s | 3.6106s |
| highlights_tour | 3 | True | True | False | True | True | 3.1677s | 5.8626s | 6.1301s |
| noise | 3 | True | True | True | True | True | 2.106s | Nones | 2.1801s |
