# Smart Turn v3.2 benchmark

This workspace measures Smart Turn directly from labelled audio. It is
intentionally separate from the Docent FastAPI, Whisper, retrieval, and LLM
pipeline.

## JupyterHub GPU run

Open `smart_turn_bench.ipynb` with the school GPU kernel and run all cells.
The notebook installs the minimal inference dependencies, confirms that the
ONNX CUDA provider is active, downloads the official v3.2 GPU model from
Hugging Face, and benchmarks every case in `audio_manifest.csv`.

The initial manifest contains the existing Docent timing fixture:

```text
audio/voice_request.wav
→ “Tell me about The Swing.”
→ expected complete
```

Results are written to:

```text
results/smart_turn_gpu_results.json
```

Each case records the completion probability and decision, plus separate
audio-loading, feature-extraction, ONNX inference, and end-to-end timings.
The script performs warm-up runs before recording latency so GPU
initialisation does not distort the steady-state median. Model download and
ONNX session construction are reported separately.

## Add benchmark recordings

Copy each 16 kHz mono WAV into `audio/` and add a row to
`audio_manifest.csv`:

```csv
case_id,audio_path,expected_label,transcript,category
trailing_because,audio/trailing_because.wav,incomplete,I wanted to ask because…,trailing_conjunction
```

Use `complete` or `incomplete` for `expected_label`. The same manifest and
recordings can later be run on the Surface with:

```powershell
python benchmark_smart_turn.py --model cpu --output results/smart_turn_cpu_results.json
```

The CPU run automatically downloads `smart-turn-v3.2-cpu.onnx`; the GPU run
uses `smart-turn-v3.2-gpu.onnx`.
