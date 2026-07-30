# Model self-routing benchmark

Model: `gemma4:cloud`

Thinking: `True`

Architecture: retrieval prefetch followed by one main-model conversation that emits a hidden route header and the spoken answer.

| Metric | Result |
|---|---:|
| Valid route blocks | 12/12 |
| Label agreement | 7/12 |
| Tool correctness | 12/12 |
| Median time to route block | 8.0717s |
| Median time to first spoken token | 9.4632s |
| Median full response time | 12.6225s |
| Route-header leaks | 0 |

## Samples

| Case | Run | Valid | Agrees | Tool correct | Route | First spoken | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| artwork_information | 1 | True | False | True | response_request | 7.8026s | 9.5134s |
| greeting | 1 | True | True | True | response_request | 4.2329s | 4.4543s |
| highlights_tour | 1 | True | False | True | call_to_action | 50.8205s | 54.7808s |
| noise | 1 | True | True | True | noise | 24.6036s | 24.7842s |
| artwork_information | 2 | True | True | True | response_request | 5.9383s | 7.3305s |
| greeting | 2 | True | True | True | response_request | 4.2585s | 4.4472s |
| highlights_tour | 2 | True | False | True | call_to_action | 29.8578s | 35.4792s |
| noise | 2 | True | True | True | noise | 28.127s | 29.0904s |
| artwork_information | 3 | True | False | True | response_request | 4.7591s | 5.7917s |
| greeting | 3 | True | True | True | response_request | 9.5673s | 15.7127s |
| highlights_tour | 3 | True | False | True | call_to_action | 9.3592s | 12.508s |
| noise | 3 | True | True | True | noise | 12.1927s | 12.7369s |
