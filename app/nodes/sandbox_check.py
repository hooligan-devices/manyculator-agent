"""Sandbox Check — optional startup health-check Function Node.

A debug option that verifies the sandbox execution environment is healthy 
before starting any agent workflow.

This is a deterministic (non-LLM) workflow node that sits at the very
beginning of the calculator generation workflow graph. When the feature
flag ``settings.check_sandbox_on_start`` is enabled, the workflow edge
graph wires START → sandbox_check → blueprint_generator; otherwise
START connects directly to blueprint_generator and this node is skipped.

The node verifies sandbox health by executing ``print('ok')`` inside a
GKE gVisor pod via :func:`~app.services.sandbox_executor.check_sandbox`.
"""

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
    """Verify GKE sandbox readiness and forward the user prompt.

    As the first node in the workflow, this function is responsible for
    extracting the raw user prompt from whatever ``node_input`` format
    the ADK framework provides, and (optionally) confirming that the
    GKE gVisor sandbox can execute code before any downstream nodes
    attempt to use it.

    Args:
        ctx: ADK workflow context. Not directly used here but required
            by the ``@node`` decorator signature.
        node_input: The initial user input forwarded by the ADK
            framework. Its concrete type varies depending on the
            ingress path — see the inline parsing comments below.

    Returns:
        An ``Event`` with one of two routes:

        * ``"OK"`` — sandbox is healthy (or check is disabled). The
          ``output`` carries the extracted user prompt string, and
          ``state["user_prompt"]`` is set for downstream nodes.
        * ``"FAIL"`` — sandbox health-check failed. The ``output``
          carries an error dict and no ``user_prompt`` is persisted.

    Note:
        When ``settings.check_sandbox_on_start`` is False the sandbox
        check is bypassed entirely — the node still runs (if wired) to
        extract the prompt, but returns ``"OK"`` immediately without
        calling into the sandbox executor.
    """

    # ------------------------------------------------------------------
    # User-prompt extraction
    # ------------------------------------------------------------------
    # The ADK framework does not guarantee a single input type for the
    # first node in a Workflow graph. Depending on the client (API,
    # playground, tests) and whether middleware has pre-processed the
    # message, ``node_input`` may arrive as:
    #
    #   1. ``google.genai.types.Content`` — the standard ADK message
    #      envelope. Contains a ``.parts`` list of Part objects, each
    #      of which may carry a ``.text`` attribute.
    #   2. ``str`` — a plain string when the framework short-circuits
    #      Content wrapping (e.g. single-turn text-only input).
    #   3. ``dict`` — occasionally seen when input is deserialised from
    #      JSON without being hydrated into a Content proto.
    #
    # We handle all three to keep the node robust against upstream
    # framework changes.
    # ------------------------------------------------------------------
    user_prompt = ""
    if hasattr(node_input, "parts") and node_input.parts:
        # Case 1: types.Content — concatenate text from all parts.
        parts = []
        for part in node_input.parts:
            if hasattr(part, "text") and part.text:
                parts.append(part.text)
        user_prompt = "".join(parts)
    elif isinstance(node_input, str):
        # Case 2: plain string — use directly.
        user_prompt = node_input
    elif isinstance(node_input, dict):
        # Case 3: raw dict — prefer a "text" key, fall back to repr.
        user_prompt = node_input.get("text", str(node_input))
    else:
        # Fallback: coerce unknown types to string so we never crash.
        user_prompt = str(node_input)

    # Fast-path: if the sandbox check is disabled, skip straight to the
    # blueprint_generator by returning "OK" with the extracted prompt.
    if not settings.check_sandbox_on_start:
        return Event(output=user_prompt, route="OK", state={"user_prompt": user_prompt})

    # --- Sandbox health check ----------------------------------------
    # Trace logs use ANSI escape codes for terminal colour:
    #   \033[96m = cyan (info), \033[92m = green (success),
    #   \033[91m = red (failure), \033[0m = reset.
    if settings.trace_enabled:
        logger.info(f"\n[TRACE] \033[96m⚙ Checking Sandbox Readiness...\033[0m")

    if check_sandbox():
        if settings.trace_enabled:
            logger.info(f"\n[TRACE]   \033[92m✓ Sandbox OK\033[0m")
        return Event(output=user_prompt, route="OK", state={"user_prompt": user_prompt})
    else:
        # Route to generation_failed — the user sees a clear error
        # message and the workflow terminates without proceeding.
        if settings.trace_enabled:
            logger.info(f"\n[TRACE]   \033[91m✗ Sandbox check failed\033[0m")
        return Event(
            output={"error": "Sandbox check failed. Please ensure the sandbox is properly configured."},
            route="FAIL"
        )
