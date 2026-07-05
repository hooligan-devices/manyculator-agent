# Manyculator - calc_agent

## High-Level Overview
The `calc_agent` is the core backend component responsible for generating custom interactive calculators based on natural language user intent. It leverages a graph-based workflow architecture powered by Google ADK to orchestrate LLM calls for intent analysis, live value resolution, Python script generation, testing, and UI schema generation.

A defining feature of this agent is its strict **Sandbox Execution** and **A2UI-compliant** output. The architecture isolates script validation using deterministic structural checks before applying a reasoning LLM Judge to verify intent alignment. The generated output is instantly renderable by any standard A2UI frontend.

## Architecture & Data Models

### State Management
State is tracked through the graph using the `CalculatorWorkflowState` Pydantic model (`app/models/generation.py`), which manages the prompt, blueprint, generated script, and retry counters.

### Data Models
- `CalculatorDefinition`: Represents the final calculator, including parameter definitions, the generated python `script`, and the strict `a2ui_schema`.
- `ParameterDef`: A flattened Pydantic schema strictly enforcing component-specific properties via `Optional` fields and prompt descriptions.
- `A2UIComponent` / `A2UIPayload`: Strict Pydantic models enforcing the A2UI specification for layout, data bindings, and action events.

### Workflow Graph: Simplified Architecture
The workflow removes brittle LLM-based test generation in favor of deterministic validation and parallel graph execution:

1. **Sandbox Check** (`sandbox_check`):
   - Fast-fails if the execution environment is misconfigured.
2. **Parallel Generation**:
   - `ui_schema_generator`: Generates the A2UI JSON schema containing a unified `description` field.
   - `script_generator`: Concurrently generates the calculation Python script.
3. **Deterministic Validation** (`script_validator`):
   - Compiles the generated script in a secure sandbox using `exec()` to verify syntax and ensure `calculate(inputs)` is callable.
   - Fails fast (without LLM calls) on syntax errors, routing back to `script_generator`.
4. **The Judge** (`script_judge`):
   - A reasoning model that compares the generated script, blueprint, and UI schema to ensure inputs/outputs align properly.
   - Triggers targeted retries if the business logic or schema mapping is flawed.

### Frontend Integration (A2UI)
The `ui_schema_generator` outputs a standard A2UI flat array of components.
- **Layouts**: E.g., `Column` points to children via string IDs.
- **Inputs**: `TextField` and `ChoicePicker` bind directly to parameters via JSON pointers (e.g., `"value": {"path": "/weight"}`).
- **Interactivity**: An injected `Button` component fires an `"action": {"event": {"name": "calculate", ...}}`. The frontend catches this event and posts the data model to the execution endpoint.
- **Strict Validation**: Before finalizing the UI layout, the JSON payload is validated directly against the official `a2ui.schema.manager`. If the LLM produces a non-compliant schema, the validator blocks it and forces a retry loop.

## Interfaces & APIs

### 1. Agent Workflow (SSE Stream)
- Exposed automatically by the ADK `FastAPI` wrapper on `POST /apps/app/users/{user_id}/sessions/{session_id}/messages` (or `POST /run_sse`).
- Frontend apps send a prompt payload and receive a Server-Sent Events (SSE) stream of the graph's execution.
- The final event from `persist_and_respond` contains the `calculator_id`.

### 2. Execution Endpoint
- `POST /evaluate/{calculator_id}`
- Receives the A2UI data model: `{"inputs": {"weight": 70, "height": 175}}`
- Loads the calculator's `script` from the Google Cloud Firestore database (`calculators` collection).
- Executes the Python calculation logic inside the secure Sandbox (or local executor).
- Returns results matching the A2UI component IDs: `{"outputs": {"bmi_result_text": 24.2}}`
- If the calculation script yields a dictionary containing an `"error"` key (due to script-defined input validation), the endpoint returns a `400 Bad Request` with the error message so the frontend can catch and display it natively.

## Security & Operational Mechanics

### 1. The Dual-Executor Security Model
The app automatically toggles between two code executors based on the environment:
- If deployed to Kubernetes (`KUBERNETES_SERVICE_HOST` is present), it spins up the secure `GkeCodeExecutor`.
- If running locally, it defaults to a `DummyExecutor` which uses Python's raw `exec()` to run LLM-generated code. **Warning**: Running the agent locally exposes your machine to arbitrary code execution; it is for trusted prototyping only.

### 2. Multi-Tiered Model Routing
The graph routes workloads to highly specialized, tiered models (configured in `config.py`) to optimize cost and speed:
- `model_coding` (`gemini-2.5-pro`): Heavy lifting (script generation).
- `model_reasoning` (`gemini-3.5-flash`): Intent parsing and Judging.
- `model_tooling` (`gemini-2.5-flash-lite`): Fast, low-latency UI schemas.

### 3. Frontend Code Hiding
When the API fetches a calculator, it intentionally strips the raw Python `script` from the payload, returning only the `a2ui_schema` and parameters. This enforces a strict separation of concerns where the frontend is physically prevented from seeing or executing the code itself.

## Persistence
Calculators are saved natively to **Google Cloud Firestore** (under the `calculators` collection) via the `CalculatorStore` singleton located in `app/calculator_store.py`. This ensures full scalability and accessibility from any deployed frontend client, as opposed to local JSON files.

## Testing Strategy
- **Generation Tests (LLM Eval)**: The ADK Eval framework runs server-side evaluation of the generation pipeline via `eval_config.yaml`.
- **Sandbox Checks**: Deterministic structure validation of scripts using local compilation.
- **Unit and Integration**: Standard Pytest suite for API endpoints and workflow routing logic.

---

## Deployment Guide
The `calc_agent` is configured for **Google Kubernetes Engine (GKE)** target deployment.

### 1. Prerequisites
- `google-agents-cli` CLI tool installed (`uv tool install google-agents-cli`).
- Configured active `gcloud` project targeting the Google Cloud Project (`manyculator`).
- Google Cloud services enabled: `cloudbuild.googleapis.com`, `secretmanager.googleapis.com`, and GKE access.

### 2. Manual/CLI Deployment
To deploy the agent to the dev/production environment on GKE:
```bash
agents-cli deploy --no-confirm-project
```
This automated command triggers the following workflow:
1. **Terraform Apply**: Initializes and applies the GKE infrastructure configs in `deployment/terraform/single-project/`.
2. **Cloud Build**: Bundles the code source, builds the Docker container, and tags/pushes it to Artifact Registry (`us-east1-docker.pkg.dev/manyculator/calc-agent/calc-agent:latest`).
3. **Kustomize / Manifest Rollout**: Automatically applies the updated deployment image to GKE.
4. **Environment Injection**: Sets environment variables (like `AGENT_VERSION` and `APP_URL`).
5. **Rollout Verification**: Waits for GKE rolling update to complete and displays the internal service IP.

### 3. Secrets Management & Third-Party LLMs
ADK's integration with Google Kubernetes Engine relies on native Workload Identity. Because of this:
- **Native Gemini Models**: Do NOT require any manual API keys or secrets. The underlying Kubernetes Service Account (`calc-agent-app`) is automatically granted `roles/aiplatform.user` by Terraform, allowing secure, seamless access to Vertex AI models.
- **Third-Party Models (LiteLLM)**: If using models via LiteLLM (e.g., OpenRouter, OpenAI, Anthropic), explicit API keys are required. During deployment, the `agents-cli deploy` tool automatically syncs your local `.env` variables to Google Cloud Secret Manager. **Important**: You must ensure the Secret Manager API (`secretmanager.googleapis.com`) is enabled in your Google Cloud Project before deploying, otherwise the secrets will silently fail to sync and the agent will encounter authentication errors.

### 4. Sandbox Configuration
No manual configuration is required for the code execution sandbox on deployment. The Terraform scripts automatically create a Kubernetes `Role` (`sandbox_role`) and `RoleBinding` (`sandbox_binding`) within the namespace. This securely grants the deployed agent's ServiceAccount the permissions required to dynamically spin up Kubernetes Jobs (`GkeCodeExecutor`) for running calculator logic and validating scripts.

### 5. Accessing the Deployed Service
Since the GKE service runs internally (default IP `10.0.0.5`), you can port-forward it locally to test or connect with the client app:
```bash
kubectl port-forward svc/calc-agent 8080:8080 -n calc-agent
```

---

## Architectural Decision Records (ADRs)

### ADR 9: Simplified Parallel Architecture (2026-06-28)
**Decision:** Removed `test_generator` and `test_judge` in favor of a deterministic `script_validator` (compilation) and an LLM-based `script_judge` (alignment check).
**Context:** LLMs struggle to generate tests for themselves without falling into hallucination loops. The simplified graph validates structural correctness first, allows parallel UI/Script generation, and then judges them for cross-compatibility before saving.
