from google.adk.workflow import node
from google.adk.events.event import Event
from google.adk.agents.context import Context
from typing import Any
import logging

from ..config import settings
from ..services.sandbox_executor import check_sandbox

logger = logging.getLogger(__name__)

@node
def sandbox_check(ctx: Context, node_input: Any) -> Event:
    """Check if the sandbox executor is working before starting the workflow."""
    # Extract text from node_input (types.Content or str)
    user_prompt = ""
    if hasattr(node_input, "parts") and node_input.parts:
        parts = []
        for part in node_input.parts:
            if hasattr(part, "text") and part.text:
                parts.append(part.text)
        user_prompt = "".join(parts)
    elif isinstance(node_input, str):
        user_prompt = node_input
    elif isinstance(node_input, dict):
        user_prompt = node_input.get("text", str(node_input))
    else:
        user_prompt = str(node_input)

    if not settings.check_sandbox_on_start:
        return Event(output=user_prompt, route="OK", state={"user_prompt": user_prompt})
        
    if settings.trace_enabled:
        logger.info(f"\n[TRACE] \033[96m⚙ Checking Sandbox Readiness...\033[0m")
        
    if check_sandbox():
        if settings.trace_enabled:
            logger.info(f"\n[TRACE]   \033[92m✓ Sandbox OK\033[0m")
        return Event(output=user_prompt, route="OK", state={"user_prompt": user_prompt})
    else:
        if settings.trace_enabled:
            logger.info(f"\n[TRACE]   \033[91m✗ Sandbox check failed\033[0m")
        return Event(
            output={"error": "Sandbox check failed. Please ensure the sandbox is properly configured."},
            route="FAIL"
        )
