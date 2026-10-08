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
- `server.py` — FastAPI composition root. It connects the framework to the
  Docent application package.
- `requirements.txt` — pinned Python dependencies.

## Development startup

From the repository root, the preferred command is:

```powershell
.\apps\docent\start.ps1
```

To start only the API manually:

```powershell
$env:PYTHONPATH = (Get-Location).Path
Set-Location framework
& .\venv\Scripts\python.exe -m uvicorn server:app --reload `
    --reload-dir . `
    --reload-dir ..\apps\docent
```

The API is served at `http://localhost:8000`; its health endpoint is
`GET /api/health`.

## Configuration

Copy `framework/.env.example` to `framework/.env` and adjust provider settings
for the local machine. Runtime logs default to the Docent application context.
Set `APPLICATION_CONTEXT=core` when a framework test should write conversation
or optional Moonshine audio logs beneath `framework/tests/runtime_logs`.

## Tests

Tests are retained as an on-demand library under `tests/_archive`, grouped by
function. Place session work in `tests/live`, then move completed tests and
their outputs into the appropriate archive group. Archived tests may represent
older interfaces and should be reviewed before reuse.
