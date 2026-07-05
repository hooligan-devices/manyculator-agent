import datetime
import uuid
import os
import google.auth
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.workflow import Workflow, JoinNode, RetryConfig, node, DEFAULT_ROUTE
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.apps import App
from google.genai import types
from typing import Any

# Authenticate context since ADK requires project set
try:
    _, project_id = google.auth.default()
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
except Exception:
    pass

from .models.generation import CalculatorWorkflowState
from .nodes import (
    blueprint_generator,
    script_generator,
    ui_schema_generator,
    sandbox_check,
    script_validator,
    script_judge,
    ui_schema_validator,
)
from .tools.crud_tools import get_calculator, delete_calculator, list_calculators
from .config import settings

join_first_run = JoinNode(name="join_first_run")

@node
def script_validator_router(ctx: Context, node_input: Any) -> Event:
    """Route based on script_validator result."""
    if node_input.get("status") == "VALID":
        # If script judge has already run once, we are in a retry loop from the judge.
        # So we skip join_first_run and go straight to script_judge.
        if ctx.state.get("script_judge_output"):
            return Event(output={"status": "RETRY_VALID"}, route="RETRY_VALID")
        else:
            return Event(output={"status": "FIRST_RUN_VALID"}, route="FIRST_RUN_VALID")
    elif node_input.get("status") == "RETRY":
        return Event(output={"status": "RETRY_INVALID"}, route="RETRY_INVALID")
    else:
        return Event(output={"status": "FAIL"}, route="FAIL")

@node
def script_judge_router(ctx: Context, node_input: Any) -> Event:
    """Route based on script_judge verdict."""
    output = ctx.state.get("script_judge_output", {})
    verdict = output.get("verdict", "")
    
    if verdict == "INVALID":
        retry_count = ctx.state.get("generation_retry_count", 0)
        if retry_count >= settings.max_generation_retries:
            return Event(output={"status": "FAIL"}, route="FAIL")
        return Event(
            output={"status": "INVALID"},
            state={
                "script_judge_feedback": output.get("feedback", ""),
                "generation_retry_count": retry_count + 1
            },
            route="INVALID"
        )
    else:
        return Event(output={"status": "VALID"}, route="VALID")

@node
def persist_and_respond(ctx: Context, node_input: Any) -> Event:
    """Save calculator and compose final response."""
    import logging
    from .calculator_store import store
    from .models.calculator import CalculatorDefinition, CalculatorStatus
    
    logger = logging.getLogger(__name__)
    
    calc_id = ctx.state.get("calculator_id")
    if not calc_id:
        calc_id = str(uuid.uuid4())
        
    # Extract description from Text component in schema
    a2ui_schema = ctx.state.get("a2ui_schema", [])
    desc = "A custom calculator"
    for msg in a2ui_schema:
        if isinstance(msg, dict) and "updateComponents" in msg:
            components = msg["updateComponents"].get("components", [])
            for comp in components:
                if isinstance(comp, dict) and comp.get("id") in ("description", "description-text"):
                    text_val = comp.get("text", "")
                    if isinstance(text_val, str) and text_val:
                        desc = text_val
                        break
            else:
                continue
            break
            
    # Extract script
    script = ctx.state.get("script_generator_output", {})
    if isinstance(script, dict):
        script_content = script.get("script_content", "")
    elif hasattr(script, "script_content"):
        script_content = script.script_content
    else:
        script_content = str(script)
        
    # Extract parameters
    analysis = ctx.state.get("blueprint", {})
    parameters = []
    if isinstance(analysis, dict):
        parameters = analysis.get("parameters", [])
    elif hasattr(analysis, "parameters"):
        parameters = analysis.parameters
    
    calc = CalculatorDefinition(
        id=calc_id,
        name="Generated Calculator",
        description=str(desc),
        created_at=datetime.datetime.now(),
        updated_at=datetime.datetime.now(),
        status=CalculatorStatus.ACTIVE,
        parameters=parameters,
        script=str(script_content),
        a2ui_schema=a2ui_schema,
        original_prompt=ctx.state.get("user_prompt", "")
    )
    store.save(calc)
    
    return Event(
        output={
            "calculator_id": calc.id, 
            "a2ui_schema": calc.a2ui_schema
        },
        state={"calculator_id": calc.id}
    )

@node
def reject_response(ctx: Context, node_input: Any) -> Event:
    return Event(output={"error": "Not a valid calculator request."})

@node
def generation_failed(ctx: Context, node_input: Any) -> Event:
    return Event(output={"error": "Calculator generation failed, please try again."})

@node
def intent_router(ctx: Context, node_input: Any) -> Event:
    analysis = ctx.state.get("blueprint", {})
    is_calc = False
    if isinstance(analysis, dict):
        is_calc = analysis.get("is_calculator", False)
    else:
        is_calc = getattr(analysis, "is_calculator", False)
        
    if is_calc:
        return Event(output=node_input, route="CALCULATOR")
    return Event(output=node_input, route="NOT_CALCULATOR")

# --- Workflow Graph ---
edges = []

if settings.check_sandbox_on_start:
    edges.extend([
        # Startup phase with sandbox check
        ("START", sandbox_check),
        (sandbox_check, {
            "OK": blueprint_generator,
            DEFAULT_ROUTE: generation_failed
        }),
    ])
else:
    edges.extend([
        # Direct startup without sandbox check
        ("START", blueprint_generator),
    ])

edges.extend([
    (blueprint_generator, intent_router),
    (intent_router, {
        "CALCULATOR": (ui_schema_generator, script_generator),
        DEFAULT_ROUTE: reject_response
    }),
    
    # UI Schema Branch
    (ui_schema_generator, ui_schema_validator),
    (ui_schema_validator, {
        "VALID": join_first_run,
        "RETRY": ui_schema_generator,
        DEFAULT_ROUTE: generation_failed
    }),
    
    # Script Branch
    (script_generator, script_validator),
    (script_validator, script_validator_router),
    (script_validator_router, {
        "FIRST_RUN_VALID": join_first_run,
        "RETRY_VALID": script_judge,
        "RETRY_INVALID": script_generator,
        DEFAULT_ROUTE: generation_failed
    }),
    
    # Merge & Judge
    (join_first_run, script_judge),
    (script_judge, script_judge_router),
    (script_judge_router, {
        "VALID": persist_and_respond,
        "INVALID": script_generator,
        DEFAULT_ROUTE: generation_failed
    }),
])

root_workflow = Workflow(
    name="calculator_generator",
    state_schema=CalculatorWorkflowState,
    edges=edges
)

from .plugins.trace_plugin import TracePlugin

app = App(
    root_agent=root_workflow,
    name="app",
    plugins=[TracePlugin()]
)
