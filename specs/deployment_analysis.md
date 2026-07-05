# calc_agent Deployment Architecture

This document outlines the production deployment architecture and infrastructure requirements for `calc_agent` using the Google ADK and `agents-cli`.

## 1. Deployment Target: Google Kubernetes Engine (GKE)
`calc_agent` must be deployed to a GKE cluster (`--deployment-target gke`) rather than Cloud Run or Vertex Agent Runtime. 

**Rationale (Code Execution Security):**
The agent tests unverified LLM-generated Python code in `sandbox_executor.py`. Executing untrusted code within the main application container is a severe security risk. By deploying to GKE, the agent can natively utilize the ADK's `GkeCodeExecutor`. The executor securely spawns isolated, ephemeral `gvisor` Pods (Kubernetes Jobs) to run the code. The Job isolates the untrusted execution and is automatically garbage-collected by Kubernetes after execution, providing maximum security natively.

## 2. Persistent Storage: Firestore
The `CalculatorStore` must be migrated from writing to a local `calculators_db.json` file to using Google Cloud Firestore. 

**Rationale (Concurrency & Ephemerality):**
Cloud deployment environments use stateless containers, meaning local file writes are lost on restart or scale-down. Additionally, reading/writing a single monolithic JSON file introduces severe concurrency issues—if multiple users generate calculators simultaneously, they will overwrite each other's data. Firestore provides a concurrency-safe NoSQL document database, allowing the system to safely store and retrieve individual `CalculatorDefinition` objects independently.

**Deployment Requirements:**
* Refactor `app/calculator_store.py` to use the `google-cloud-firestore` SDK.
* Enable the Firestore API in the GCP project.
* Grant the deployment service account (`app_sa`) the `roles/datastore.user` IAM permission via Terraform so it has authorization to interact with Firestore.

## 3. Session State Management
`calc_agent` does **not** require persistent user session history.

**Implementation Details:**
* Conversation state will remain purely in-memory (`session_service_uri = None` in `app/fast_api_app.py`).
* If a Pod restarts, active conversational context is lost, which is acceptable for this application's use case.
* We do **not** need to provision Cloud SQL, avoiding the operational overhead of managing a relational database and proxy sidecars.

## 4. Compute and Scaling Requirements
The multi-agent workflow utilizes the ADK `JoinNode` to parallelize the `script_generator` and `test_generator` nodes. Running multiple LLM generation streams concurrently consumes a significant amount of memory.

**Deployment Requirements:**
When configuring the Kubernetes `Deployment` manifests in the Terraform configuration (`deployment/terraform/single-project/service.tf`), the container resource requests and limits must be explicitly scaled up to prevent Out-of-Memory (OOM) crashes during peak parallel generation:
* **CPU:** 4 vCPU (Limit)
* **Memory:** 16Gi (Limit)

## 5. Authentication & Authorization Setup

`calc_agent` requires secure access to both Google's LLMs (Vertex AI / Gemini API) and Firestore. The transition from local development to production deployment is handled seamlessly by the Google Cloud SDKs and ADK scaffolding.

### Vertex AI / LLM Authentication
* **Local Development:** The `google.genai` SDK uses your personal Application Default Credentials (ADC) obtained via `gcloud auth application-default login`.
* **Production (GKE):** No code changes are required. The ADK Terraform configuration automatically creates a dedicated GCP service account (`app_sa`) with the `roles/aiplatform.user` role. It binds this GCP account to the Kubernetes Pod via **Workload Identity**. When the container runs, the SDK automatically detects the Workload Identity environment and authenticates as `app_sa`.

### Alternative: Using an API Key
If you prefer to use a standard Gemini Developer API key instead of Vertex AI / ADC:
* Do not hardcode the key.
* Save the key in GCP Secret Manager: `echo -n "KEY" | gcloud secrets create GEMINI_API_KEY_SECRET --data-file=-`
* Pass the secret during deployment: `agents-cli deploy --deployment-target gke --secrets "GEMINI_API_KEY=GEMINI_API_KEY_SECRET:latest"`
* Terraform will automatically grant `app_sa` the `secretAccessor` permission and securely inject `GEMINI_API_KEY` into the container's environment variables, where the SDK will automatically pick it up.

### Firestore Authentication & Configuration
Firestore authentication follows the exact same "ADC to Workload Identity" flow, but our specific implementation requires configuring closed security rules and targeting our named database.

* **Project & Database Identifiers:**
  * **Project ID:** `manyculator`
  * **Database ID:** `calculators` (Note: Because this is a named database and not `(default)`, the Python SDK must be explicitly initialized with `db = firestore.Client(database="calculators")`).
* **Security Rules:** Because `calc_agent` accesses Firestore via the Python Server SDK, it completely bypasses Firestore Security Rules and relies solely on IAM. Therefore, the database's security rules should be completely locked down (`allow read, write: if false;`) to prevent any public client-side access.
* **Local Development:** Ensure your personal Google account has the `roles/datastore.user` role. Run `gcloud auth application-default login` to read/write locally.
* **Production (GKE):** In your Terraform configuration (`deployment/terraform/iam.tf`), explicitly grant the runtime service account access to Firestore:
  ```hcl
  resource "google_project_iam_member" "firestore_user" {
    project = var.project_id
    role    = "roles/datastore.user"
    member  = "serviceAccount:${google_service_account.app_sa.email}"
  }
  ```
Once deployed, the `google-cloud-firestore` Python SDK will automatically authenticate via Workload Identity using the `app_sa` credentials. No manual keys are ever passed to the client.
