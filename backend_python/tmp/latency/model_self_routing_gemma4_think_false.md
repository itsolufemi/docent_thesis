# Model self-routing benchmark

Model: `gemma4:cloud`

Thinking: `False`

Architecture: retrieval prefetch followed by one main-model conversation that emits a hidden route header and the spoken answer.

| Metric | Result |
|---|---:|
| Valid route blocks | 12/12 |
| Label agreement | 8/12 |
| Tool correctness | 12/12 |
| Median time to route block | 3.1167s |
| Median time to first spoken token | 3.288s |
| Median full response time | 4.0289s |
| Route-header leaks | 0 |

## Samples

| Case | Run | Valid | Agrees | Tool correct | Route | First spoken | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| artwork_information | 1 | True | True | True | response_request | 5.3233s | 8.0391s |
| greeting | 1 | True | True | True | response_request | 3.1932s | 4.1591s |
| highlights_tour | 1 | True | False | True | call_to_action | 5.6359s | 6.3267s |
| noise | 1 | True | False | True | response_request | 3.3828s | 3.8986s |
| artwork_information | 2 | True | True | True | response_request | 2.5725s | 3.8693s |
| greeting | 2 | True | True | True | response_request | 2.4693s | 2.7369s |
| highlights_tour | 2 | True | False | True | call_to_action | 4.1499s | 4.592s |
| noise | 2 | True | True | True | noise | 2.9581s | 3.1464s |
| artwork_information | 3 | True | True | True | response_request | 6.2406s | 7.9958s |
| greeting | 3 | True | True | True | response_request | 2.4721s | 2.6876s |
| highlights_tour | 3 | True | False | True | call_to_action | 8.6694s | 8.8845s |
| noise | 3 | True | True | True | noise | 3.1221s | 3.5368s |
