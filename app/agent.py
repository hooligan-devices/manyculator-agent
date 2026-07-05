"""
Manyculator Agent Workflow Orchestrator

This module defines the core ADK Workflow graph that orchestrates the calculator generation pipeline.
It acts as the central router and state manager for the entire multi-agent system.

Workflow Architecture:
1. Startup: Conditional sandbox health check (`sandbox_check`). This is an optional debug step (useful for verifying pod readiness on fresh deploys) toggled via `settings.check_sandbox_on_start` in `config.py`.
2. Intent Analysis: Blueprint generation and is_calculator validation (`intent_router`).
3. Parallel Generation Branches:
   a) Script Branch: `script_generator` -> `script_validator` (fast fail) -> `script_judge`
   b) UI Branch: `ui_schema_generator` -> `ui_schema_validator`
4. Joining: Both branches must succeed (`join_first_run`) before the `script_judge` runs.
5. Retries: If validation or judging fails, the workflow loops back to the respective generator.
6. Persistence: On overall success, `persist_and_respond` saves to Firestore.

All nodes communicate exclusively via `ctx.state`, sharing variables like `blueprint`,
`script_generator_output`, and validation errors.
"""

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

# ── GCP Auth Bootstrap ─────────────────────────────────────────────────
# ADK requires GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION to be set
# at import time. We auto-detect them from Application Default Credentials
# (ADC) so the developer doesn't need to export them manually.
# "global" is used as the location to avoid model 404 errors that occur
# when region-specific endpoints (e.g. us-east1) lack the target model.
try:
    _, project_id = google.auth.default()
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
except Exception:
    pass  # Silently continue — env vars may already be set (e.g. in CI/GKE)

from .models.generation import CalculatorWorkflowState
# Import all LLM Agent nodes and deterministic Function nodes that make up
# the workflow graph. Each node is defined in its own module under app/nodes/.
from .nodes import (
    blueprint_generator,   # LLM Agent: analyses user prompt → structured blueprint
    script_generator,      # LLM Agent: generates Python calculation script
    ui_schema_generator,   # LLM Agent: generates A2UI declarative UI schema
    sandbox_check,         # Function: health-checks the gVisor sandbox pod
    script_validator,      # Function: validates script in sandboxed execution
    script_judge,          # LLM Agent: LLM-as-a-judge for script quality review
    ui_schema_validator,   # Function: Pydantic-validates A2UI schema structure
)
from .tools.crud_tools import get_calculator, delete_calculator, list_calculators
from .config import settings

# ── JoinNode ───────────────────────────────────────────────────────────
# Synchronizes the two parallel branches (script branch + UI schema branch)
# before the judge can evaluate. Both branches must reach this node before
# the workflow proceeds to script_judge.
# NOTE: This join is only used on the first run. During retry loops, the
# script branch bypasses this node (via RETRY_VALID route) because the
# UI schema is already validated and doesn't need to be re-joined.
join_first_run = JoinNode(name="join_first_run")

# ══════════════════════════════════════════════════════════════════════════
# Router Nodes — Deterministic routing logic between workflow stages.
# These nodes inspect workflow state and the output of the previous node
# to decide which edge to follow in the DAG.
# ══════════════════════════════════════════════════════════════════════════

@node
def script_validator_router(ctx: Context, node_input: Any) -> Event:
    """Route based on deterministic script validation result.
    
    Args:
        ctx (Context): The ADK context.
        node_input (Any): The event output from `script_validator`.
        
    Returns:
        Event: Routing event to FIRST_RUN_VALID, RETRY_VALID, RETRY_INVALID, or FAIL.
        
    Note:
        Differentiates between a first-time generation (must wait for UI schema at `join_first_run`)
        and a retry loop triggered by the LLM judge (can bypass the join and go straight back to `script_judge`).
    """
    if node_input.get("status") == "VALID":
        # If script judge has already run once, we are in a retry loop from the judge.
        # So we skip join_first_run and go straight to script_judge.
        if ctx.state.get("script_judge_output"):
            return Event(output={"status": "RETRY_VALID"}, route="RETRY_VALID")
        else:
            return Event(output={"status": "FIRST_RUN_VALID"}, route="FIRST_RUN_VALID")
    elif node_input.get("status") == "RETRY":
        # Route back to script_generator with error in state
        return Event(output={"status": "RETRY_INVALID"}, route="RETRY_INVALID")
    else:
        # Max retries exceeded
        return Event(output={"status": "FAIL"}, route="FAIL")

@node
def script_judge_router(ctx: Context, node_input: Any) -> Event:
    """Route based on LLM script judge verdict.
    
    Args:
        ctx (Context): The ADK context containing `script_judge_output` in state.
        node_input (Any): The output from the script_judge agent.
        
    Returns:
        Event: Routes to VALID if the judge approves, or INVALID to loop back to generator.
    """
    output = ctx.state.get("script_judge_output", {})
    verdict = output.get("verdict", "")
    
    if verdict == "INVALID":
        retry_count = ctx.state.get("generation_retry_count", 0)
        if retry_count >= settings.max_generation_retries:
            return Event(output={"status": "FAIL"}, route="FAIL")
        # Increment retry count and pass judge feedback to state for script_generator
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

# ══════════════════════════════════════════════════════════════════════════
# Terminal Nodes — Leaf nodes of the workflow DAG that produce final
# responses. Each returns an Event with output but no outgoing route.
# ══════════════════════════════════════════════════════════════════════════

@node
def persist_and_respond(ctx: Context, node_input: Any) -> Event:
    """Save the fully validated calculator to the database and compose final response.
    
    Extracts the generated script, A2UI schema, and blueprint parameters from state,
    constructs a CalculatorDefinition, persists it using the calculator_store, and
    returns the UUID and UI schema to the client.
    """
    import logging
    from .calculator_store import store
    from .models.calculator import CalculatorDefinition, CalculatorStatus
    
    logger = logging.getLogger(__name__)
    
    # Reuse existing ID if present (e.g., from a previous partial run),
    # otherwise generate a fresh UUID.
    calc_id = ctx.state.get("calculator_id")
    if not calc_id:
        calc_id = str(uuid.uuid4())
        
    # Extract description specifically from the generated Text component in the A2UI schema
    # (provides a more accurate user-facing description than the blueprint's internal one)
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
                # Inner loop didn't break → description not in this message.
                continue
            # Inner loop broke → we found the description; exit outer loop.
            break
            
    # Extract the generated Python script content.
    # Defensive type handling: state values may be dicts (from JSON
    # deserialization) or Pydantic model instances (from direct assignment).
    script = ctx.state.get("script_generator_output", {})
    if isinstance(script, dict):
        script_content = script.get("script_content", "")
    elif hasattr(script, "script_content"):
        script_content = script.script_content
    else:
        script_content = str(script)
        
    # Extract parameter definitions from the blueprint.
    # Same defensive handling for dict vs Pydantic model.
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
    """Terminal node for rejecting off-topic (non-calculator) requests."""
    return Event(output={"error": "Not a valid calculator request."})

@node
def generation_failed(ctx: Context, node_input: Any) -> Event:
    """Terminal node for exhaustion of generation/validation retries."""
    return Event(output={"error": "Calculator generation failed, please try again."})

@node
def intent_router(ctx: Context, node_input: Any) -> Event:
    """Routes based on the 'is_calculator' flag in the blueprint.
    
    Determines if the prompt actually describes a calculation tool.
    If so, continues to parallel generation branches. Otherwise, routes to rejection.
    """
    analysis = ctx.state.get("blueprint", {})
    is_calc = False
    if isinstance(analysis, dict):
        is_calc = analysis.get("is_calculator", False)
    else:
        is_calc = getattr(analysis, "is_calculator", False)
        
    if is_calc:
        return Event(output=node_input, route="CALCULATOR")
    return Event(output=node_input, route="NOT_CALCULATOR")

# ══════════════════════════════════════════════════════════════════════════
# Workflow Graph Definition
#
# The DAG is constructed as a list of edge tuples. Each tuple is either:
#   (source, target)             — unconditional edge
#   (source, {route: target})    — conditional edge keyed by route string
#   (source, (t1, t2))           — fan-out to parallel branches
#
# DEFAULT_ROUTE acts as the fallback when no named route matches, similar
# to a default case in a switch statement. It is used here to route
# unexpected/unrecoverable states to the `generation_failed` terminal.
# ══════════════════════════════════════════════════════════════════════════

edges = []

# ── Phase 0 (optional): Sandbox Health Check ──────────────────────────
# When enabled, verifies the gVisor sandbox pod is reachable before
# committing to expensive LLM calls. Useful in GKE deployments where
# the sandbox pod may not be ready yet.
if settings.check_sandbox_on_start:
    edges.extend([
        ("START", sandbox_check),
        (sandbox_check, {
            "OK": blueprint_generator,
            DEFAULT_ROUTE: generation_failed  # Sandbox unhealthy → abort early
        }),
    ])
else:
    # Skip health check — go straight to blueprint generation.
    edges.extend([
        ("START", blueprint_generator),
    ])

edges.extend([
    # ── Phase 1: Intent Analysis ──────────────────────────────────────
    (blueprint_generator, intent_router),
    (intent_router, {
        # Fan-out: CALCULATOR intent launches both generation branches
        # concurrently as a tuple of targets.
        "CALCULATOR": (ui_schema_generator, script_generator),
        DEFAULT_ROUTE: reject_response  # Non-calculator → reject terminal
    }),
    
    # ── Phase 2a: UI Schema Branch (parallel) ─────────────────────────
    # Generates and validates the A2UI declarative UI schema.
    # On validation failure, retries by looping back to the generator.
    (ui_schema_generator, ui_schema_validator),
    (ui_schema_validator, {
        "VALID": join_first_run,          # Schema OK → wait at join
        "RETRY": ui_schema_generator,     # Fixable error → regenerate
        DEFAULT_ROUTE: generation_failed   # Unrecoverable → abort
    }),
    
    # ── Phase 2b: Script Branch (parallel) ────────────────────────────
    # Generates, sandbox-validates, and routes the Python script.
    # script_validator_router handles the first-run vs retry-loop fork.
    (script_generator, script_validator),
    (script_validator, script_validator_router),
    (script_validator_router, {
        "FIRST_RUN_VALID": join_first_run,  # First pass OK → wait at join
        "RETRY_VALID": script_judge,        # Retry pass OK → skip join, go to judge
        "RETRY_INVALID": script_generator,  # Validation failed → regenerate script
        DEFAULT_ROUTE: generation_failed     # Unrecoverable → abort
    }),
    
    # ── Phase 3: Join & Quality Gate ──────────────────────────────────
    # Both branches converge here; the judge performs a holistic review.
    (join_first_run, script_judge),
    (script_judge, script_judge_router),
    (script_judge_router, {
        "VALID": persist_and_respond,       # Approved → save & return
        "INVALID": script_generator,        # Rejected → retry with feedback
        DEFAULT_ROUTE: generation_failed     # Retries exhausted → abort
    }),
])

root_workflow = Workflow(
    name="calculator_generator",
    state_schema=CalculatorWorkflowState,  # Pydantic model tracking all intermediate artifacts
    edges=edges
)

from .plugins.trace_plugin import TracePlugin

app = App(
    root_agent=root_workflow,
    name="app",
    plugins=[TracePlugin()]
)
