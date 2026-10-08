# Docent

Docent is a voice-first conversational museum guide developed as a thesis
prototype. A visitor can speak naturally about artworks, pause and continue a
turn, interrupt or backchannel while the guide is speaking, and receive a
retrieval-grounded streamed response as text and speech.

The repository is a small monorepo containing:

- a React/Vite browser client;
- a FastAPI conversation backend;
- the Docent museum-guide application and artwork data;
- local and remote model-provider integrations;
- benchmark scripts and retained experiment reports.

## Current request flow

```text
microphone
→ browser VAD and PCM16 streaming
→ Smart Turn acoustic completion candidate
→ selected speech-to-text provider
→ accumulated textual turn buffer
→ semantic turn-completion check
→ context resolution
→ artwork vector retrieval when required
→ streamed main-model response
→ sentence-level streamed TTS
→ browser text and audio playback
```

Conversation identity is maintained with a `conversation_id` browser cookie.
The browser creates no conversation explicitly: the first request creates one,
and subsequent requests reuse the cookie.

## Repository layout

```text
docent_thesis/
├── framework/
│   ├── core_engine/   Provider-neutral conversation contracts,
│   │                        routes, state and orchestration
│   ├── extensions/          Generic retrieval/indexing implementation
│   ├── models/              ASR, Smart Turn and TTS implementations/factories
│   ├── tests/               Live test workspace and function-grouped archive
│   ├── config.py            Environment-backed application settings
│   ├── requirements.txt     Pinned Python dependencies
│   └── server.py            FastAPI composition root
├── apps/
│   └── docent/              Docent application package
│       ├── api/             Artwork and retrieval routes
│       ├── config/          Docent-specific profiles
│       ├── data/            Artwork corpus and generated vector store
│       ├── frontend/        React/Vite client and AudioWorklets
│       ├── schemas/         Museum-domain data contracts
│       ├── scripts/         Docent vector-store builder
│       ├── services/        Prompt, context and retrieval services
│       └── start.ps1        Windows development launcher
├── _LAB/                    Smart Turn benchmark workspace and reports
```

`core_engine` describes what the conversational application needs.
Concrete model/provider implementations live under `framework/models`.
The `apps/docent` package supplies the museum-specific application built
on those capabilities.

## Prerequisites

For the configuration committed in `.env.example`, install:

- **Git**;
- **Python 3.14** (the pinned environment was developed on Python 3.14);
- **Node.js 20 LTS or newer**, with npm;
- **Ollama**, running locally;
- a Chromium-based browser with microphone access;
- an internet connection for Ollama Cloud and first-time model downloads.

The default development configuration uses:

- `gemma4:cloud` for the main response and semantic turn decisions;
- `nomic-embed-text` for vector embeddings;
- Moonshine for streaming speech recognition;
- local Faster Whisper as the batch/fallback transcription service;
- Smart Turn v3.2 through the tracked CPU ONNX model;
- Kyutai Pocket TTS with the `jane` voice.

The first startup can be slower because Moonshine, Faster Whisper and Pocket
TTS may download or initialise model assets.

## First-time installation

### 1. Clone the repository

```powershell
git clone https://github.com/itsolufemi/docent_thesis.git
Set-Location docent_thesis
```

### 2. Create the backend virtual environment

From the repository root:

```powershell
py -3.14 -m venv framework\venv
& .\framework\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\framework\requirements.txt
```

If PowerShell blocks virtual-environment activation, enable scripts for the
current shell only:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### 3. Install the client dependencies

```powershell
npm ci --prefix apps/docent/frontend
```

The tracked `package-lock.json` makes `npm ci` the reproducible installation
command. Use `npm install --prefix apps/docent/frontend` only when intentionally
updating client dependencies.

### 4. Create the environment files

Copy the backend template:

```powershell
Copy-Item .\framework\.env.example .\framework\.env
```

Copy the client template:

```powershell
Copy-Item .\apps\docent\frontend\.env.example .\apps\docent\frontend\.env
```

The client should use:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

Use one hostname consistently. Do not alternate between `localhost` and
`127.0.0.1` during one conversation because browser cookies are host-specific.

### 5. Install and prepare Ollama

Install Ollama from <https://ollama.com/> and sign in for cloud-model access.
Then obtain the models used by the default configuration:

```powershell
ollama signin
ollama pull gemma4:cloud
ollama pull nomic-embed-text
```

Ensure Ollama is running before building the index or starting the backend:

```powershell
ollama serve
```

If the Ollama desktop application is already running, a second `ollama serve`
process is unnecessary.

### 6. Build the Docent vector index

Generated vector-index files are deliberately excluded from Git. Build them
once after cloning, while Ollama and `nomic-embed-text` are available:

```powershell
& .\framework\venv\Scripts\python.exe `
    .\apps\docent\scripts\build_docent_vector_store.py
```

The command creates:

```text
apps/docent/data/vector_store/docent_vector_index.json
apps/docent/data/vector_store/docent_vector_embeddings.npy
```

Rebuild the index whenever the artwork corpus or embedding model changes.

## Starting the application

### Windows: combined launcher

From the repository root:

```powershell
.\apps\docent\start.ps1
```

This opens separate PowerShell windows for:

- FastAPI at `http://localhost:8000`;
- React/Vite at `http://localhost:5173`.

The launcher sets the Python import path for the `apps.docent` package and
configures Uvicorn to watch both `framework` and `apps/docent`.

### Manual startup

Use two terminals.

Backend terminal, from the repository root:

```powershell
$env:PYTHONPATH = (Get-Location).Path
Set-Location framework
& .\venv\Scripts\python.exe -m uvicorn server:app --reload `
    --reload-dir . `
    --reload-dir ..\apps\docent
```

Frontend terminal, from the repository root:

```powershell
npm --prefix apps/docent/frontend run dev
```

Open:

- application: <http://localhost:5173>
- FastAPI documentation: <http://localhost:8000/docs>
- backend health check: <http://localhost:8000/api/health>

Allow microphone access when prompted by the browser.

## Configuration

Backend configuration is read from `framework/.env`. The complete
baseline is in `framework/.env.example`.

### Language models and embeddings

| Setting | Purpose | Default example |
|---|---|---|
| `OLLAMA_BASE_URL` | Ollama API location | `http://localhost:11434` |
| `OLLAMA_MODEL` | Main response model | `gemma4:cloud` |
| `OLLAMA_TRP_MODEL` | Semantic turn-completion model | `gemma4:cloud` |
| `OLLAMA_EMBEDDING_MODEL` | Vector embedding model | `nomic-embed-text` |
| `OLLAMA_MAIN_THINK` | Main-model thinking mode | `false` |

Context resolution explicitly disables thinking for its compact routing
request. The main streamed response retains the configured main-model setting.

### Speech-to-text providers

Set `TRANSCRIPTION_BACKEND` to one of:

| Value | Behaviour |
|---|---|
| `moonshine` | Streaming Moonshine with local Faster Whisper for batch uploads |
| `whisper` | Local Faster Whisper batch/final-segment path |
| `qmul_whisper` | Remote QMUL Whisper Large-v3 stream with Moonshine live fallback |

`moonshine` is the portable default for another machine.

The QMUL provider is institution-specific. It requires:

- access to the configured QMUL JupyterHub account;
- a running compatible Whisper server in that account;
- `QMUL_JUPYTER_TOKEN` in
  `framework/models/whisper_large_v3_qmul/.env`;
- sufficient remote GPU memory.

It should not be selected for a general installation. If the remote model
cannot load, the backend logs a non-fatal warm-up failure and the live path is
configured to use Moonshine as its fallback.

### Smart Turn

Smart Turn is controlled by:

```dotenv
SMART_TURN_ENABLED=true
SMART_TURN_MODEL_PATH=models/smart-turn-v3.2-cpu.onnx
SMART_TURN_THRESHOLD=0.50
SMART_TURN_MAX_AUDIO_SECONDS=8.0
```

The ONNX model is tracked in the repository. Smart Turn supplies an acoustic
completion candidate; the textual turn buffer and semantic completion logic
remain responsible for assembling and finalising the visitor's full turn.

### Text-to-speech providers

Set `TTS_BACKEND` to:

| Value | Behaviour |
|---|---|
| `kyutai_pocket` | Local Pocket TTS streaming; portable default |
| `google` | Google Cloud Chirp streaming |

Default local configuration:

```dotenv
TTS_BACKEND=kyutai_pocket
TTS_MODEL=english
TTS_VOICE=jane
TTS_LANGUAGE_CODE=en-GB
TTS_QUANTIZE=false
```

Google Chirp requires Google Cloud Application Default Credentials, an enabled
Text-to-Speech API and a project with suitable access/billing. A tested voice
configuration is:

```dotenv
TTS_BACKEND=google
TTS_VOICE=en-GB-Chirp3-HD-Aoede
TTS_LANGUAGE_CODE=en-GB
```

Authenticate before startup with:

```powershell
gcloud auth application-default login
```

### Startup warm-ups

The backend can warm ASR, Smart Turn, retrieval, the main LLM and TTS
concurrently. Warm-up settings are in `.env.example`:

```dotenv
WARM_UP_MOONSHINE_ON_STARTUP=true
WARM_UP_SMART_TURN_ON_STARTUP=true
WARM_UP_RETRIEVAL_ON_STARTUP=true
WARM_UP_LLM_ON_STARTUP=true
WARM_UP_TTS_ON_STARTUP=true
```

LLM and TTS warm-ups make real provider requests. Set individual flags to
`false` when diagnosing startup or avoiding cloud usage. A warm-up failure is
logged but does not prevent FastAPI from starting.

### Runtime logs

Conversation logging is configured with:

```dotenv
CONVERSATION_LOGGING_ENABLED=true
RUNTIME_LOG_APPLICATION=docent
# Optional explicit override; otherwise the application selector chooses the path.
# CONVERSATION_LOG_DIRECTORY=apps/docent/runtime_logs/conversations
```

Runtime logs and optional Moonshine input recordings are excluded from Git.
Use `RUNTIME_LOG_APPLICATION=core` for core-engine feature tests; those logs go
to `framework/tests/runtime_logs/conversations`. The default `docent` context
writes to `apps/docent/runtime_logs/conversations`.

Moonshine input-audio capture is disabled by default:

```dotenv
MOONSHINE_AUDIO_LOGGING_ENABLED=false
```

When enabled, it follows `RUNTIME_LOG_APPLICATION`: core audio goes to
`framework/tests/runtime_logs/moonshine_audio`, while Docent audio goes to
`apps/docent/runtime_logs/moonshine_audio`. The directory is created automatically
when Moonshine starts saving audio. `MOONSHINE_SAVE_INPUT_WAV_PATH` can still
override that location.

## Browser interaction

The client provides:

- continuous microphone capture and voice-activity detection;
- accumulated multi-segment spoken turns;
- Smart Turn candidate evaluation;
- streamed assistant text;
- progressive sentence-level TTS;
- temporary audio ducking for possible backchannels/interruption;
- cancellation of active LLM and TTS work when the visitor takes the floor;
- visible transcription, turn and timing diagnostics.

The application uses browser cookies, WebSockets and AudioWorklets. Use the
same origin consistently and avoid private/incognito policies that block
same-site cookies.

## Testing

### Backend

The long-term test library is grouped by function under
`framework/tests/_archive`. New or actively revised tests belong in
`framework/tests/live` until they are classified. Run a targeted archived
test from `framework` by file path:

```powershell
Set-Location framework
& .\venv\Scripts\python.exe .\tests\_archive\conversation\test_context_resolution.py
```

Additional focused suites include:

```powershell
& .\venv\Scripts\python.exe .\tests\_archive\api_routes\test_audio_stream_route.py
& .\venv\Scripts\python.exe .\tests\_archive\api_routes\test_tts_stream_route.py
& .\venv\Scripts\python.exe .\tests\_archive\streaming_and_audio\test_transcription_lifecycle.py
```

Some explicitly named integration tests make real Ollama, Google or QMUL
requests and require their corresponding services and credentials. Inspect a
test module before enabling its integration environment flag.

### Client

From the repository root:

```powershell
npm --prefix apps/docent/frontend run test:vad
npm --prefix apps/docent/frontend run test:sentences
npm --prefix apps/docent/frontend run test:tts-client
npm --prefix apps/docent/frontend run test:turn-client
npm --prefix apps/docent/frontend run test:audio-client
npm --prefix apps/docent/frontend run build
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'apps'`

Start through `apps/docent/start.ps1`, or set the repository root before starting
Uvicorn manually:

```powershell
$env:PYTHONPATH = (Resolve-Path ..).Path
```

when the current directory is `framework`.

### Vector index is missing

Confirm that both generated files exist in `apps/docent/data/vector_store`, then
rerun the vector-store build command while Ollama is running.

### Ollama request fails

Check:

```powershell
ollama list
ollama ps
```

Confirm the configured model names and sign in again if a cloud model returns
an authorization error.

### Startup appears slow

First startup may load/download local models and make cloud warm-up requests.
The backend prints a per-component warm-up summary. Disable individual warm-up
flags temporarily to isolate a provider.

### QMUL Whisper never becomes ready

Check the remote Whisper log. The most recently observed failure was CUDA GPU
out-of-memory during Large-v3 loading; increasing the local health timeout will
not repair a remote process that has already exited.

### Browser conversation appears to disappear

Do not alternate between:

```text
http://localhost:5173
http://127.0.0.1:5173
```

Cookies are host-specific.

## Reproducibility notes

A fresh clone contains source code, artwork data, the Smart Turn ONNX model,
tests and experiment reports. It does **not** contain:

- `framework/.env`;
- `apps/docent/frontend/.env`;
- provider credentials or QMUL tokens;
- generated Docent vector embeddings;
- model caches downloaded by Whisper, Moonshine or Pocket TTS;
- an authenticated/running Ollama installation.

Consequently, cloning is the first step rather than the entire installation.
Following the setup sequence above should reproduce the portable
Moonshine/Pocket configuration. QMUL Whisper and Google Chirp require external
accounts and cannot be reproduced from repository contents alone.
