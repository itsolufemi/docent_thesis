# backend_python

This folder contains the FastAPI backend service for the project.
It is organized around routers in `api/`, request/response schemas in `schemas/`, and business logic in `services/`.

**summary**
`- server.py starts the backend`
`- api/ receives requests`
`- schemas/ define data contracts`
`- services/ perform work`
`- data/ stores facts`
`- memory/ will track state`
`- orchestrators/ will decide flow`
`- rag/ will retrieve knowledge`

**Top-level file tree (backend_python/)**

- `.env`
- `api/`
  - `__init__.py`       - package initializer for API routes
  - `routes_health.py`  - health endpoint router
  - `routes_query.py`   - query endpoint router
  - `routes_llm.py`     - LLM / language model endpoint router
- `config.py`            - settings and configuration
- `memory/`              - local persistent memory store
- `orchestrators/`       - orchestration logic and workflow coordination
- `rag/`                 - retrieval-augmented generation helpers
- `README.md`            - backend docs
- `requirements.txt`     - Python dependencies
- `schemas/`
  - `__init__.py`
  - `query_schemas.py`   - request/response schemas for query route
  - `llm_schemas.py`     - request/response schemas for LLM route
- `server.py`            - FastAPI app, CORS, router registration
- `services/`
  - `__init__.py`
  - `query_service.py`   - business logic for query responses
  - `llm_service.py`     - LLM helper service
  - `prompt_service.py`  - prompt construction logic
- `utils/`               - utility modules
- `venv/`                - virtual environment (not checked into VCS)
- `__pycache__/`         - Python bytecode cache

**Request flow: example `POST /api/query`**

server.py
  includes query_router

api/routes_query.py
  receives the HTTP request

schemas/query_schemas.py
  validates the request body

services/query_service.py
  generates the response

api/routes_query.py
  returns the response

FastAPI
  sends JSON back to the client


Full request flow description description:

1. Client (React) sends POST to `/api/query` with JSON body matching `QueryRequest` (schema in `schemas/query_schemas.py`). Example body:

```json
{ "text": "tell me about this painting" }
```

2. `server.py` has `app.include_router(query_router)` which registers the route defined in `api/routes_query.py`.

3. `api/routes_query.py` receives the request as a `QueryRequest` object (Pydantic). It calls into `services.query_service.generate_basic_response(request.text)` to compute the answer.

4. The service returns a string `response_text` which the route wraps in a `QueryResponse` Pydantic model and returns to the client.

   - Note: `schemas/query_schemas.py` defines the expected fields. Keep returned keys consistent with the model (e.g. `received` vs `request`). Mismatches will raise validation errors (HTTP 500 during development). See `api/routes_query.py` for the exact return shape.

5. FastAPI serializes the `QueryResponse` model to JSON and sends it back to the client.

**Health check**

- `GET /api/health` implemented in `api/routes_health.py` returns a small JSON object with `status`, `service` and `environment`.

**Troubleshooting**

- If you see Pydantic `ValidationError` complaining about missing fields, verify `schemas/*.py` and the data keys returned by routes match exactly.
- When editing route or schema filenames, restart uvicorn (or rely on `--reload`).
- Ensure CORS origins in `server.py` include the client origin (Vite default `http://localhost:5173`).

**Useful commands**

```bash
# start server
uvicorn server:app --reload

# run tests (if any)
pytest
```

**Run (development)**

1. Create and activate a virtual environment and install requirements:

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Unix
source venv/bin/activate
pip install -r requirements.txt
```

2. Run the server with auto-reload:

```bash
uvicorn server:app --reload --port 8000
```

3. The client expects CORS origins at `http://localhost:5173` (see `server.py`).
# Utterance-routing modes

The voice turn pipeline supports two routing modes through:

```text
UTTERANCE_ROUTING_MODE=sequential
```

Available values:

- `sequential` keeps the established classifier → context resolution → response path.
- `classifier_tool` enables the experimental mandatory first-round `classify_utterance` tool.

The `classifier_tool` implementation exposes only the classifier tool during the mandatory first round. The main model must place both the unchanged utterance and its classification in the tool arguments. The backend validates and normalises those arguments without making a separate classifier-model request, resolves context from the result, and resumes the same main-model conversation to stream the assistant response.

The main Ollama model and reasoning profile are configured independently:

```text
OLLAMA_MODEL=gemma4:cloud
OLLAMA_MAIN_THINK=false
```

Both the mandatory classifier-tool round and subsequent streamed response rounds use this profile unless an experiment explicitly supplies an override.
