# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Main FastAPI entrypoint for the Manyculator Agent backend.

This module initializes the FastAPI server, configures the Google ADK environment
(including custom Firestore session routing and telemetry), and exposes the native
agent endpoints (`/run_sse`, `/sessions`). 

It also provides custom application endpoints (`/evaluate`, `/schema`) for the
frontend to execute generated calculators in a secure sandbox and retrieve their UIs.
"""

import os

import google.auth
from fastapi import FastAPI, HTTPException
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging

from pydantic import BaseModel
from typing import Dict, Any
from app.app_utils.telemetry import setup_telemetry
from app.tools.crud_tools import get_calculator
from app.services.sandbox_executor import execute_calculation
from app.calculator_store import store

# ---------------------------------------------------------------------------
# Setup & Initialization
# ---------------------------------------------------------------------------

setup_telemetry()
_, project_id = google.auth.default()
logging_client = google_cloud_logging.Client()
logger = logging_client.logger(__name__)

allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else ["*"]
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ADK session configuration
# Default: Use custom Firestore service for persistent sessions (required for multi-worker cloud deployments)
session_service_uri = "firestore://default"
# Local Testing: Uncomment the line below to switch to in-memory RAM sessions (fast, but causes 404s in multi-worker environments)
# session_service_uri = "memory://shared"

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

# Initialize the ADK-wrapped FastAPI application
app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True, # Enables the built-in /dev-ui playground
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=True,
)
app.title = "Manyculator Agent API"
app.description = "API for orchestrating calculator generation and sandboxed execution."

# ---------------------------------------------------------------------------
# Custom Endpoints
# ---------------------------------------------------------------------------

class EvaluateRequest(BaseModel):
    """Payload for executing a generated calculator."""
    inputs: Dict[str, Any]


@app.post("/evaluate/{calculator_id}")
def evaluate_calculator(calculator_id: str, request: EvaluateRequest) -> dict:
    """Execute a generated calculator's Python script securely in the sandbox.
    
    Args:
        calculator_id: The UUID of the generated calculator to run.
        request: A dictionary of inputs matching the calculator's required parameters.
        
    Returns:
        A dictionary containing the mathematical results under the 'outputs' key.
        
    Raises:
        HTTPException 404: If the calculator does not exist.
        HTTPException 400: If the calculation fails or inputs are invalid.
        HTTPException 500: If the backend fails to load the execution script.
    """
    # Retrieve base metadata to ensure calculator exists
    calc_data = get_calculator(calculator_id)
    if "error" in calc_data:
        raise HTTPException(status_code=404, detail=calc_data["error"])
        
    # We must access the original logic script from the store
    calc = store.get(calculator_id)
    if not calc or not calc.script:
        raise HTTPException(status_code=500, detail="Calculator logic script is missing.")
        
    # Run the untrusted script in the strict sandbox (gVisor if on GKE)
    result = execute_calculation(calc.script, request.inputs)
    
    # Handle structured execution errors gracefully
    if "error" in result:
        detail = result["error"]
        if "raw_output" in result:
            detail += f" Raw Output: {result['raw_output']}"
        raise HTTPException(status_code=400, detail=detail)
        
    return {"outputs": result}


@app.get("/schema/{calculator_id}")
def get_a2ui_schema(calculator_id: str) -> Any:
    """Retrieve the declarative A2UI layout schema for a generated calculator.
    
    This endpoint allows frontends to dynamically render the user interface
    (inputs, buttons, layouts) required to interact with the target calculator.
    
    Args:
        calculator_id: The UUID of the calculator to retrieve the schema for.
        
    Returns:
        The raw A2UI JSON schema.
        
    Raises:
        HTTPException 404: If the calculator does not exist.
    """
    calc_data = get_calculator(calculator_id)
    if "error" in calc_data:
        raise HTTPException(status_code=404, detail=calc_data["error"])
        
    return calc_data["a2ui_schema"]


# ---------------------------------------------------------------------------
# Server Startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
