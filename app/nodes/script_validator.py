from google.adk.workflow import node
from google.adk.events.event import Event
from google.adk.agents.context import Context
from typing import Any
import logging

from ..config import settings
from ..services.sandbox_executor import validate_script

logger = logging.getLogger(__name__)

@node
def script_validator(ctx: Context, node_input: Any) -> Event:
    """Deterministically checks if the generated script is structurally valid."""
    
    script_output = ctx.state.get("script_generator_output", {})
    if isinstance(script_output, dict):
        script_content = script_output.get("script_content", "")
    elif hasattr(script_output, "script_content"):
        script_content = script_output.script_content
    else:
        script_content = str(script_output)
        
    retry_count = ctx.state.get("generation_retry_count", 0)
    
    if settings.trace_enabled:
        logger.info(f"\n[TRACE] \033[96m⚙ Validating Script Deterministically...\033[0m")
        
    result = validate_script(script_content)
    
    if result.get("passed"):
        if settings.trace_enabled:
            logger.info(f"\n[TRACE]   \033[92m✓ Script Syntax OK\033[0m")
        return Event(
            output={"status": "VALID"},
            route="VALID",
            state={"script_validation_error": ""}
        )
    else:
        error_msg = result.get("error", "Unknown validation error")
        if settings.trace_enabled:
            logger.info(f"\n[TRACE]   \033[91m✗ Script Syntax Error: {error_msg}\033[0m")
            
        if retry_count < settings.max_generation_retries:
            return Event(
                output={"status": "RETRY"},
                route="RETRY",
                state={
                    "generation_retry_count": retry_count + 1,
                    "script_validation_error": error_msg
                }
            )
        else:
            return Event(
                output={"error": f"Script validation failed after retries: {error_msg}"},
                route="FAIL"
            )
