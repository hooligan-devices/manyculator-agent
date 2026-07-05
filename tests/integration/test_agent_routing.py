import pytest
import asyncio
from unittest.mock import patch
from google.adk.agents.context import Context
from app.models.generation import CalculatorWorkflowState
from app.agent import (
    script_judge_router,
    script_validator_router,
    intent_router,
)
from app.config import settings

class MockActions:
    def __init__(self):
        self.state_delta = {}
        self.route = ""

class MockContext:
    def __init__(self, state_dict):
        self.state = state_dict
        self.actions = MockActions()

def get_mock_context(state_dict):
    """Helper to mock ADK Context state."""
    return MockContext(state_dict)

def run_node_sync(node_obj, ctx, node_input):
    async def _run():
        events = []
        async for e in node_obj._run_impl(ctx=ctx, node_input=node_input):
            events.append(e)
        return events[0]
    return asyncio.run(_run())

def test_script_judge_router_passes():
    """Test that a VALID verdict from the script judge routes to VALID."""
    ctx = get_mock_context({"script_judge_output": {"verdict": "VALID"}})
    event = run_node_sync(script_judge_router, ctx, {})
    assert event.actions.route == "VALID"
    assert event.output["status"] == "VALID"

def test_script_judge_router_fails_and_retries():
    """Test that INVALID verdict increments retry count and routes INVALID."""
    ctx = get_mock_context({
        "script_judge_output": {"verdict": "INVALID", "feedback": "Missing key"},
        "generation_retry_count": 0
    })
    event = run_node_sync(script_judge_router, ctx, {})
    assert event.actions.route == "INVALID"
    assert event.actions.state_delta["script_judge_feedback"] == "Missing key"
    assert event.actions.state_delta["generation_retry_count"] == 1

def test_script_judge_router_fails_final():
    """Test that max retries causes a FAIL route."""
    ctx = get_mock_context({
        "script_judge_output": {"verdict": "INVALID", "feedback": "Missing key"},
        "generation_retry_count": settings.max_generation_retries
    })
    event = run_node_sync(script_judge_router, ctx, {})
    assert event.actions.route == "FAIL"

def test_script_validator_router_first_run_valid():
    """Test that first-run valid script goes to join."""
    ctx = get_mock_context({})
    event = run_node_sync(script_validator_router, ctx, {"status": "VALID"})
    assert event.actions.route == "FIRST_RUN_VALID"

def test_script_validator_router_retry_valid():
    """Test that on retry (judge already ran), valid script goes directly to judge."""
    ctx = get_mock_context({"script_judge_output": {"verdict": "INVALID"}})
    event = run_node_sync(script_validator_router, ctx, {"status": "VALID"})
    assert event.actions.route == "RETRY_VALID"

def test_script_validator_router_retry_invalid():
    """Test that invalid script routes back to generator."""
    ctx = get_mock_context({})
    event = run_node_sync(script_validator_router, ctx, {"status": "RETRY"})
    assert event.actions.route == "RETRY_INVALID"

def test_script_validator_router_fail():
    """Test that failed validation routes to FAIL."""
    ctx = get_mock_context({})
    event = run_node_sync(script_validator_router, ctx, {"status": "FAIL"})
    assert event.actions.route == "FAIL"

def test_intent_router_calculator():
    """Test that calculator requests route to CALCULATOR."""
    ctx = get_mock_context({"blueprint": {"is_calculator": True}})
    event = run_node_sync(intent_router, ctx, {})
    assert event.actions.route == "CALCULATOR"

def test_intent_router_not_calculator():
    """Test that non-calculator requests route to NOT_CALCULATOR."""
    ctx = get_mock_context({"blueprint": {"is_calculator": False}})
    event = run_node_sync(intent_router, ctx, {})
    assert event.actions.route == "NOT_CALCULATOR"
