# Manyculator Agent

## Overview
The `calc_agent` is the core backend component responsible for generating custom interactive calculators based on natural language user intent. It leverages a graph-based workflow architecture powered by Google ADK to orchestrate LLM calls for intent analysis, live value resolution, Python script generation, and UI schema generation.

A defining feature of this agent is its strict **Sandbox Execution** and **A2UI-compliant** output. The architecture isolates script validation using deterministic structural checks before applying a reasoning LLM Judge to verify intent alignment. The generated output is instantly renderable by any standard A2UI frontend.

---

## Architecture & Data Models

### State Management
State is tracked through the graph using the `CalculatorWorkflowState` Pydantic model ([generation.py](../app/models/generation.py)), which manages the prompt, blueprint, generated script, and retry counters.

### Data Models
*   `CalculatorDefinition` ([calculator.py](../app/models/calculator.py)): Represents the final calculator, including parameter definitions, the generated python `script`, and the strict `a2ui_schema`.
*   `ParameterDef` ([calculator.py](../app/models/calculator.py)): A flattened Pydantic schema strictly enforcing component-specific properties via `Optional` fields and prompt descriptions.
*   `ValidationRules` ([calculator.py](../app/models/calculator.py)): Holds validation ranges like min, max, step, required, and regex patterns.

### System Workflow

![architecture.png](img/architecture.png)

Here is a step-by-step breakdown of the agentic workflow:

- **Check Sandbox Health** *(Function Node, Debug Only)*: Runs a simple Python script in the sandbox on startup to verify the execution environment is healthy.
- **Blueprint Generator & Intent Router** *(Agent Node)*: Creates a structured blueprint from the user's intent. This serves as the single source of truth for the rest of the workflow, defining parameters, computation logic, and edge cases. It also acts as an intent router — if the prompt is not related to building a calculator, it halts the workflow and returns an error.
- **Script Generator & UI Schema Generator** *(Agent Nodes)*: These run in parallel, generating their respective outputs based on the shared blueprint.
- **Script Validator & UI Schema Validator** *(Function Nodes)*: These run deterministic checks *before* any LLM judgment. The Script Validator uses the sandbox to catch syntax errors, while the UI Schema Validator validates the JSON structure against the A2UI SDK. Failing fast deterministically saves expensive LLM tokens and latency.
- **Script Judge** *(Agent Node)*: Evaluates if the generated Python script correctly handles the exact data shapes and component IDs defined in the UI schema. It acts as the final gatekeeper to ensure front-to-back compatibility.
- **Save Calculator** *(Function Node)*: Saves the finalized calculator script and UI schema to the database.
- **Join Calculator ID & UI Schema** *(Function Node)*: Constructs the final JSON payload containing the new Calculator ID and Schema.

**External API Endpoints**:
- **Evaluate Inputs** (`POST /evaluate/{id}`): Retrieves the calculator script, injects the user's inputs, executes it securely in the GKE sandbox, and returns the computed result.
- **Fetch Schema** (`GET /schema/{id}`): Retrieves the A2UI schema for a specific calculator from Firestore.
- **Create Session** (`POST /sessions`): Generates and returns a unique session ID, natively provided by the ADK framework.

---

## Authentication (Application Default Credentials)

This project (including local development, Firestore database connections, and Vertex AI LLM routing) relies universally on **Application Default Credentials (ADC)**. This architecture ensures you do not need to manage raw API keys or service account JSON files across different environments.

**To set up ADC locally:**
1. Install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) (`gcloud`).
2. Initialize and authenticate with your Google account:
   ```bash
   gcloud auth application-default login
   ```
3. Set your active project (the one containing your Firestore DB and Vertex AI API quota):
   ```bash
   gcloud config set project YOUR_PROJECT_ID
   ```
*Note: When deployed to Google Cloud (e.g., GKE or Cloud Run), ADC is provided automatically by the attached compute Service Account, requiring zero key configuration.*

---

## Database Setup (Firestore)

The agent automatically persists all generated calculator scripts and UI schemas to Google Cloud Firestore so they can be retrieved and executed by the frontend.

1. **Enable Firestore API** in your Google Cloud Project.
2. **Create a Named Database**:
   * Go to the Firestore console in GCP.
   * Click **Create Database**.
   * Set the **Database ID** strictly to `calculators` (the codebase specifically routes to this named database, *not* the `(default)` database).
   * Choose **Native mode** and select your preferred region.
3. **Authentication**: The backend connects automatically using ADC. As long as you have completed the `gcloud auth application-default login` step above and your Google user has Firestore read/write permissions, the connection will succeed without extra configuration.

---

## Getting Started (Local Development)

### Prerequisites
*   **Python 3.11+** and the **`uv`** package manager.
*   **Google Cloud credentials** configured via [Application Default Credentials (ADC)](#authentication-application-default-credentials).
*   **Firestore Database** created and configured (see [Database Setup](#database-setup-firestore)).

### Setup
1. Clone the repository and navigate into it.
2. Install dependencies using `uv`:
   ```bash
   uv sync
   ```
3. Configure Environment Variables:
   * Copy the example configuration: `cp .env.example .env`
   * Open `.env` and configure your GCP variables (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`). The `google-genai` SDK will automatically route requests through the ADC you set up earlier.

4. Start the FastAPI server:
   ```bash
   uv run uvicorn app.fast_api_app:app --reload --host 0.0.0.0 --port 8000
   ```
5. Access the API and Playground:
   * The core agent API is now running and accessible at `http://127.0.0.1:8000/`.
   * **Interactive Playground**: You can instantly chat with the agent and test the UI by visiting the built-in playground at `http://127.0.0.1:8000/dev-ui/?app=app`. 
     * *Note:* Because the `web=True` flag is preset in `app/fast_api_app.py`, you do **not** need to run the `agents-cli playground` command explicitly; the dev-ui is bundled directly into the FastAPI server.
     * *Note:* To use the dev-ui playground correctly, ensure you have the `google-agents-cli` installed globally. If you haven't installed it yet, run: `uv tool install google-agents-cli`.

---

## Consumer App Integration Guide

The integration guide for consumer applications has been moved to a separate document. Please refer to [Consumer App Integration Guide](specs/app_integration.md) for full details on establishing sessions, generating calculators, retrieving UI schemas, and evaluating inputs.

---

## Security & Operational Mechanics

### The Dual-Executor Security Model
The app automatically toggles between two code executors based on the environment:
*   **Production (GKE)**: Automatically utilizes `GkeCodeExecutor` ([sandbox_executor.py](../app/services/sandbox_executor.py)), which securely spawns isolated, ephemeral `gvisor` Pods (Kubernetes Jobs) to run LLM-generated code.
*   **Local Development**: Defaults to `DummyExecutor`, using Python's raw `exec()` in the local runtime.
    > [!WARNING]
    > Running the agent locally executes untrusted LLM-generated Python code directly on your machine. This is for testing only.

### Firestore Persistence
Calculators are persisted in **Google Cloud Firestore** under a dedicated database:
*   **Database ID**: `calculators`
*   **Collection**: `calculators`
*   Configured inside [calculator_store.py](../app/calculator_store.py).

---

## Testing Strategy
*   **Unit & Integration Tests**: Executed via Pytest at [tests/integration/](../tests/integration/).
    ```bash
    uv run pytest tests/unit tests/integration
    ```
*   **LLM Evaluation Suite**: Run via the ADK quality flywheel to evaluate generation performance.
    ```bash
    agents-cli eval generate
    agents-cli eval grade
    ```

---

## Architectural Decision Records (ADRs)

### ADR 9: Simplified Parallel Architecture (2026-06-28)
*   **Decision**: Removed LLM-based `test_generator` and `test_judge` nodes in favor of a deterministic `script_validator` (compilation) and a reasoning `script_judge` (static alignment check).
*   **Context**: LLMs struggle to generate unit tests for themselves without falling into infinite hallucination loops. The simplified graph validates structural correctness first, allows parallel UI/Script generation, and then judges them for cross-compatibility before saving.
