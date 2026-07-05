# Manyculator README Structure

Based on the architecture and goals of the **Manyculator** project, here is a suggested structure for a comprehensive GitHub `README.md` that effectively explains both the end-user value and the complex agentic system under the hood:

### 1. Title & Hero Section
*   **Project Name & Tagline**: (e.g., "Manyculator: Infinite Dynamic Calculators on Demand")
*   **Hero Image/GIF**: A quick visual showing a user typing a prompt ("I need a paint calculator") and the system rendering a fully functional UI and calculation logic in seconds.
*   **Badges**: Build status, License, Frameworks used (Google ADK, FastAPI).

### 2. What is Manyculator? (Overview)
*   A brief, high-level summary of what the project does.
*   **The Core Problem**: Why building custom calculators manually is tedious.
*   **The Solution**: An autonomous multi-agent system that interprets user intent, designs a data model, writes the underlying Python logic, and generates a declarative UI schema for instant frontend rendering.

### 3. Key Features
*   **Natural Language to App**: Just describe the math/calculator you want.
*   **A2UI Framework Integration**: Decoupled, server-driven UI generation that safely renders complex interfaces without shipping arbitrary Javascript to the client.
*   **Secure Code Sandboxing**: Python calculation scripts are executed safely in isolated environments (e.g., GKE with gVisor).
*   **Self-Healing Generation**: Built-in Judge and Validation agents that detect missing logic, schema mismatches, or syntax errors, automatically prompting the generator to fix itself before showing the user.

### 4. Architecture & How It Works
*   **System Diagram**: A high-level Mermaid.js diagram or image showing the pipeline.
*   **The Agentic Pipeline**: Briefly explain the node workflow:
    1.  **Intent Analyzer**: Understands what the user wants.
    2.  **Blueprint Generator**: Defines the inputs/outputs and data types.
    3.  **Parallel Generation**: 
        *   *Script Generator*: Writes the python logic.
        *   *UI Schema Generator*: Maps the blueprint to A2UI components.
    4.  **Script Judge & Validation**: Evaluates the script against the schema and runs sandboxed tests.
*   **Database**: Mention the use of Firestore for persisting calculator definitions.

### 5. Getting Started (Local Development)

#### Prerequisites
*   **Python 3.11+** and the **`uv`** package manager.
*   Google Cloud credentials (if using Vertex AI) or a Gemini API Key.

#### Backend Setup
1. Clone the repository and navigate into it.
2. Install dependencies using `uv`:
   ```bash
   uv sync
   ```
3. Configure Environment Variables:
   * Copy the example configuration: `cp .env.example .env`
   * Open `.env` and configure your LLM provider.
   * **For Vertex AI (Default):** Set `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION`. Make sure you are authenticated via `gcloud auth application-default login`.
   * **For Gemini API Studio:** Comment out the Vertex lines and provide your `GEMINI_API_KEY`.
4. Start the FastAPI server:
   ```bash
   uv run uvicorn app.fast_api_app:app --reload --host 0.0.0.0 --port 8000
   ```

### 6. Deployment
*   Brief instructions on how this is deployed in production.
*   Mentioning the specific requirements for the GKE executor (for safe code evaluation) vs the local dummy executor.

### 7. The Journey / Architectural Decisions (Optional but highly recommended)
*   A "Behind the Scenes" section summarizing key lessons from development (e.g., why the Test Suite Generator was removed in favor of a static blueprint-based judge, why generation was parallelized). This provides huge value to other developers learning from your repository.

### 8. Contributing & License
*   How others can run evaluations or add new A2UI components.
*   Standard open-source license information.
