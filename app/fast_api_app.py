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
import os

import google.auth
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging

from pydantic import BaseModel
from typing import Dict, Any
from app.app_utils.telemetry import setup_telemetry
from app.tools.crud_tools import get_calculator
from app.services.sandbox_executor import execute_calculation

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
# In-memory session configuration - no persistent storage
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=True,
)
app.title = "calc_agent"
app.description = "API for interacting with the Agent calc_agent"


class EvaluateRequest(BaseModel):
    inputs: Dict[str, Any]

@app.post("/evaluate/{calculator_id}")
def evaluate_calculator(calculator_id: str, request: EvaluateRequest) -> dict:
    from fastapi import HTTPException
    
    # Retrieve from DB
    calc_data = get_calculator(calculator_id)
    if "error" in calc_data:
        raise HTTPException(status_code=404, detail=calc_data["error"])
        
    # We must access the original script, which wasn't fully exposed by get_calculator
    # Let's import the store directly to get the raw object
    from app.calculator_store import store
    calc = store.get(calculator_id)
    if not calc or not calc.script:
        raise HTTPException(status_code=500, detail="Calculator logic script is missing.")
        
    result = execute_calculation(calc.script, request.inputs)
    
    if "error" in result:
        detail = result["error"]
        if "raw_output" in result:
            detail += f" Raw Output: {result['raw_output']}"
        raise HTTPException(status_code=400, detail=detail)
        
    return {"outputs": result}


@app.get("/schema/{calculator_id}")
def get_a2ui_schema(calculator_id: str) -> Any:
    """Retrieve the A2UI schema of a specific calculator.
    
    Args:
        calculator_id: The UUID of the calculator to retrieve the schema for.
    """
    from fastapi import HTTPException
    
    calc_data = get_calculator(calculator_id)
    if "error" in calc_data:
        raise HTTPException(status_code=404, detail=calc_data["error"])
        
    return calc_data["a2ui_schema"]


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
