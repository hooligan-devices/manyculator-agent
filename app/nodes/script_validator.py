"""Script Validator — Deterministic Function Node for fast syntax/structural checks.

This node is a critical cost-optimization gate in the workflow graph. It sits
between `script_generator` (LLM Agent) and `script_judge` (LLM Agent), running
a **deterministic** sandbox validation that catches syntax errors, import errors,
and structural issues WITHOUT consuming LLM tokens.

Fail-Fast Strategy:
    The Script Judge is an expensive LLM call that evaluates code quality,
    correctness, and adherence to the blueprint. Sending a script with a
    ``SyntaxError`` to the Judge wastes both tokens and latency. This node
    eliminates that waste by catching obvious failures cheaply via the GKE
    gVisor sandbox (see ``sandbox_executor.validate_script``).

Routing (three possible outcomes):
    - ``'VALID'``  → Script passed structural checks. Forwarded to
      ``script_validator_router``, which routes onward to the Script Judge.
    - ``'RETRY'``  → Script failed but retries remain (up to
      ``settings.max_generation_retries``, currently 8). Routes back to
      ``script_generator`` with the error stored in state so the LLM can
      self-correct.
    - ``'FAIL'``   → Retries exhausted. Routes to ``generation_failed``
      terminal node.

Workflow position::

    script_generator ──► **script_validator** ──► script_validator_router
                             │        ▲                    │
                             │ RETRY  │                    │ VALID
                             └────────┘                    ▼
                                                    script_judge
"""

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
    """Run deterministic validation on the generated script via the GKE sandbox.

    Reads the script produced by ``script_generator`` from workflow state,
    sends it to the sandbox executor for structural validation (syntax,
    imports, basic structure), and routes based on the result.

    Args:
        ctx: ADK workflow context providing access to shared
            ``CalculatorWorkflowState`` via ``ctx.state``.
        node_input: Upstream node output (unused — this node reads directly
            from state because the script_generator stores its output there).

    Returns:
        Event: Contains a ``route`` string (``'VALID'``, ``'RETRY'``, or
        ``'FAIL'``) and updated state fields. On retry, the
        ``script_validation_error`` state key carries the error message back
        to ``script_generator`` so the LLM can incorporate it into its next
        attempt.
    """

    # --- Extract the generated script from workflow state ---
    # The script_generator stores its output as either a dict (when parsed
    # from JSON) or a Pydantic model (ScriptGeneratorOutput). We handle
    # both formats defensively, with a str() fallback for unexpected types.
    script_output = ctx.state.get("script_generator_output", {})
    if isinstance(script_output, dict):
        script_content = script_output.get("script_content", "")
    elif hasattr(script_output, "script_content"):
        # Pydantic model path — attribute access on the model instance.
        script_content = script_output.script_content
    else:
        # Fallback: coerce to string so validate_script always gets a str.
        script_content = str(script_output)

    # Track how many generation→validation cycles have occurred so far.
    retry_count = ctx.state.get("generation_retry_count", 0)

    if settings.trace_enabled:
        logger.info(f"\n[TRACE] \033[96m⚙ Validating Script Deterministically...\033[0m")

    # --- Sandbox validation ---
    # Delegates to sandbox_executor.validate_script(), which ships the code
    # to a GKE gVisor pod. The pod runs the script in a restricted Python
    # environment and reports syntax errors, import failures, and missing
    # required structures (e.g. a `calculate` entry-point function).
    result = validate_script(script_content)

    # --- Route based on validation outcome ---
    if result.get("passed"):
        if settings.trace_enabled:
            logger.info(f"\n[TRACE]   \033[92m✓ Script Syntax OK\033[0m")
        # Clear any stale error from a previous retry so downstream nodes
        # don't see outdated validation messages.
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
            # RETRY path: feed the error back to script_generator via state.
            # The script_generator's prompt template reads
            # `script_validation_error` and includes it as corrective context,
            # enabling the LLM to self-correct in its next generation attempt.
            return Event(
                output={"status": "RETRY"},
                route="RETRY",
                state={
                    "generation_retry_count": retry_count + 1,
                    "script_validation_error": error_msg
                }
            )
        else:
            # FAIL path: retries exhausted — terminate the workflow branch.
            # No state update needed; the generation_failed node handles
            # composing the final error response to the user.
            return Event(
                output={"error": f"Script validation failed after retries: {error_msg}"},
                route="FAIL"
            )
