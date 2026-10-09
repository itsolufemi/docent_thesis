# Framework

This directory contains the reusable FastAPI conversation framework used by
the applications in this repository. Docent-specific behavior and data live
under `apps/docent`; the framework provides the conversation engine, generic
retrieval capabilities, model integrations, configuration, and HTTP/WebSocket
composition.

## Layout

- `core_engine/` — provider-neutral routes, schemas, conversation state,
  prompting, tools, and orchestration services.
- `extensions/retrieval/` — domain-agnostic indexing and retrieval schemas and
  services.
- `models/` — speech recognition, Smart Turn, and text-to-speech providers and
  factories.
- `orchestrators/` — reserved for higher-level workflow integrations.
- `tests/live/` — working area for new or actively revised tests.
- `tests/_archive/` — function-grouped long-term test, benchmark, fixture, and
  result library.
- `tests/runtime_logs/` — generated logs when the application context is
  `core`.
- `config.py` — environment-backed settings and application-specific runtime
  log path selection.
- `app_factory.py` — application-agnostic FastAPI composition factory.
- `requirements.txt` — pinned Python dependencies.

Application entry points live outside the framework:

- `apps/docent/server.py` composes the framework with Docent services and
  routes.
- `apps/def_conv_app/server.py` composes only domain-neutral framework
  capabilities for development and testing.

## Development startup

From the repository root, the preferred command is:

```powershell
.\apps\docent\start.ps1
```

To start only the API manually:

```powershell
$env:PYTHONPATH = (Get-Location).Path
Set-Location framework
& .\venv\Scripts\python.exe -m uvicorn apps.docent.server:app --reload `
    --reload-dir . `
    --reload-dir ..\apps\docent
```

The API is served at `http://localhost:8000`; its health endpoint is
`GET /api/health`.

For the framework-only Swagger and API, replace the Uvicorn target with
`apps.def_conv_app.server:app` and the application reload directory with
`..\apps\def_conv_app`.

## Application provider isolation

`create_framework_app()` creates a fresh transcription stack and TTS service
for each application by default. Applications may instead inject a
`TranscriptionStack` and `TextToSpeechService`, including providers selected
with `create_transcription_stack()` and `create_tts_service()`.

Injected providers are treated as externally owned and are not closed when an
application stops. Set `close_transcription_stack_on_shutdown=True` or
`close_tts_service_on_shutdown=True` to transfer ownership to that application.
This allows applications to use independent providers or deliberately share
them without one application's shutdown invalidating another.

## Configuration

Copy `framework/.env.example` to `framework/.env` and adjust provider settings
for the local machine. Runtime logs default to the Docent application context.
Set `RUNTIME_LOG_APPLICATION=core` when a framework test should write conversation
or optional Moonshine audio logs beneath `framework/tests/runtime_logs`.

## Tests

Tests are retained as an on-demand library under `tests/_archive`, grouped by
function. Place session work in `tests/live`, then move completed tests and
their outputs into the appropriate archive group. Archived tests may represent
older interfaces and should be reviewed before reuse.
