# Benchmark results

Each result belongs to the benchmark script with the matching filename prefix or descriptive name in the parent `benchmarks` folder.

| Result name or prefix | Producing script |
| --- | --- |
| `00_context_resolver_*` | `../00_context_resolver_benchmark.py` |
| `01_startup_latency_*` | `../01_startup_latency_benchmark.py` |
| `02_remote_idle_*` | `../02_remote_idle_latency_benchmark.py` |
| `03_full_system_cold_start_*` | `../03_full_system_cold_start_benchmark.py` |
| `04_main_llm_first_cold_start_*` | `../04_main_llm_first_cold_start_benchmark.py` |
| `05_direct_routing_comparison_*` | `../05_direct_routing_comparison_benchmark.py` |
| `classifier_streaming_*` | `../benchmark_classifier_streaming.py` |
| `context_self_routing_*` | `../benchmark_context_self_routing.py` |
| `moonshine_streaming_*` | `../benchmark_moonshine_streaming.py` |
| `trp_balanced_accuracy*` | `../benchmark_trp_accuracy.py` |
| `trp_model_benchmark*` | `../benchmark_trp_models.py` |
| `trp_streaming_comparison*` | `../benchmark_trp_streaming.py` |
| `vad_threshold_benchmark*` | `../benchmark_vad_thresholds.py` |
| `latest_voice_trace*` | `../measure_voice_pipeline.py` |

## Reports

| Report | Associated benchmark scripts |
| --- | --- |
| `optimized_voice_pipeline_timing_report.md` | `../measure_voice_pipeline.py` |
| `trp_streaming_latency_report.md` | `../benchmark_trp_models.py`, `../benchmark_trp_accuracy.py`, `../benchmark_trp_streaming.py`, and `../measure_voice_pipeline.py` |
| `vad_threshold_experiment_report.md` | `../benchmark_vad_thresholds.py` |
