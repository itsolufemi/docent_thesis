# Model self-routing benchmark

Model: `gpt-oss:120b-cloud`

Thinking: `False`

Architecture: retrieval prefetch followed by one main-model conversation that emits a hidden route header and the spoken answer.

| Metric | Result |
|---|---:|
| Valid route blocks | 12/12 |
| Label agreement | 6/12 |
| Tool correctness | 9/12 |
| Median time to route block | 5.3198s |
| Median time to first spoken token | 5.3198s |
| Median full response time | 6.583s |
| Route-header leaks | 0 |

## Samples

| Case | Run | Valid | Agrees | Tool correct | Route | First spoken | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| artwork_information | 1 | True | True | True | response_request | 6.7764s | 9.3751s |
| greeting | 1 | True | True | True | response_request | 5.0724s | 5.3852s |
| highlights_tour | 1 | True | False | False | call_to_action | 6.0564s | 6.6073s |
| noise | 1 | True | True | True | noise | 5.7415s | 5.964s |
| artwork_information | 2 | True | True | True | response_request | 5.3514s | 7.2799s |
| greeting | 2 | True | True | True | response_request | 4.4718s | 4.7383s |
| highlights_tour | 2 | True | False | False | call_to_action | 5.2882s | 6.734s |
| noise | 2 | True | False | True | response_request | 5.2685s | 5.5195s |
| artwork_information | 3 | True | True | True | response_request | 5.1084s | 6.5586s |
| greeting | 3 | True | False | True | response_request | 7.2088s | 7.462s |
| highlights_tour | 3 | True | False | False | call_to_action | 6.6224s | 7.5281s |
| noise | 3 | True | False | True | response_request | 5.1231s | 5.4107s |
