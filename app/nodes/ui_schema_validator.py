"""UI Schema Validator — deterministic Function Node in the calculator workflow.

This node sits immediately after the ``ui_schema_generator`` LLM Agent Node
and acts as a quality gate for the generated A2UI JSON. Its responsibilities:

1. **Normalize** the raw LLM output into the ``<a2ui-json>`` tag format that
   the A2UI SDK parser expects (different models format output differently).
2. **Parse** the normalized text with the SDK's ``parse_response()`` to
   extract individual A2UI JSON component blocks.
3. **Validate** each extracted component against the selected A2UI catalog's
   JSON-Schema validator.
4. **Route** the workflow based on the validation outcome:
   - ``VALID``  → JoinNode (continue to next stage)
   - ``RETRY``  → back to ``ui_schema_generator`` with the error message
   - ``FAIL``   → ``generation_failed`` (retries exhausted)

The validated schema is persisted in workflow state (``a2ui_schema``) so that
downstream nodes (``script_judge``, ``persist_and_respond``) can consume it
without re-parsing.
"""

import re
import logging
from typing import Any
from google.adk.workflow import node
from google.adk.events.event import Event
from google.adk.agents.context import Context
from a2ui.parser.parser import parse_response

from .ui_schema_generator import schema_manager
from ..config import settings

logger = logging.getLogger(__name__)

def _wrap_a2ui_json_tags(text: str) -> str:
    """Wraps raw JSON output or markdown blocks in `<a2ui-json>` tags.
    
    A2UI SDK's `parse_response` requires A2UI JSON components to be enclosed in
    `<a2ui-json>` and `</a2ui-json>` tags. However, different LLMs generate different
    output formats: some use markdown code blocks (```json ... ```), while others (like
    Gemini 3.5 Flash) output raw JSON arrays or objects directly.
    
    This helper normalizes the response by ensuring the JSON payload is wrapped
    with the correct tags regardless of model formatting preferences.
    """
    text = text.strip()
    if "<a2ui-json>" in text:
        return text

    if "```json" in text:
        return text.replace("```json", "<a2ui-json>").replace("```", "</a2ui-json>")
    
    if text.startswith("[") and text.endswith("]"):
        return f"<a2ui-json>{text}</a2ui-json>"
    
    if text.startswith("{") and text.endswith("}"):
        return f"<a2ui-json>{text}</a2ui-json>"
    
    json_match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
    if json_match:
        return f"<a2ui-json>{json_match.group(1)}</a2ui-json>"
        
    return text

@node
def ui_schema_validator(ctx: Context, node_input: Any) -> Event:
    """Validates LLM-generated A2UI JSON and routes the workflow accordingly.

    This is a deterministic Function Node — no LLM calls happen here. It acts
    as the quality gate between the ``ui_schema_generator`` (LLM Agent Node)
    and the rest of the pipeline. Validation failures trigger a retry loop
    that sends the error message back to the LLM so it can self-correct.

    Args:
        ctx: ADK workflow context. Used to read/write shared workflow state
            (``generation_retry_count``, ``ui_validation_error``, ``a2ui_schema``).
        node_input: The upstream node's output. Can arrive as:
            - A ``dict`` keyed by the upstream node name (``ui_schema_generator``).
            - An object with a ``.text`` attribute (ADK LLM response wrapper).
            - A plain string.

    Returns:
        An ``Event`` with one of three routes:
        - ``VALID``  — schema is correct; ``a2ui_schema`` stored in state.
        - ``RETRY``  — schema invalid but retries remain; error stored in
          ``ui_validation_error`` for the LLM to read on the next attempt.
        - ``FAIL``   — retries exhausted; propagates error to
          ``generation_failed`` node.

    Note:
        The validated ``a2ui_schema`` list persisted in state is consumed by
        two downstream nodes:
        - ``script_judge`` — uses it to verify the generated script is
          compatible with the UI schema.
        - ``persist_and_respond`` — bundles it into the final calculator
          response payload.
    """
    # --- 1. Extract raw text from the upstream node output ---
    # ADK may deliver the input in several forms depending on the upstream
    # node type; we normalise to a plain string here.
    llm_output_text = node_input.get("ui_schema_generator", "") if isinstance(node_input, dict) else str(node_input)
    if hasattr(node_input, "text"):
        llm_output_text = node_input.text

    # --- 2. Normalize LLM output to <a2ui-json> tag format ---
    # Different models wrap JSON differently (markdown fences, raw arrays, etc.).
    # The SDK parser strictly requires <a2ui-json> tags.
    llm_output_text = _wrap_a2ui_json_tags(llm_output_text)

    # Retrieve the active A2UI catalog — its validator enforces the
    # JSON-Schema for the chosen component set.
    selected_catalog = schema_manager.get_selected_catalog()
    a2ui_schema = []  # Accumulates validated A2UI component dicts
    
    retry_count = ctx.state.get("generation_retry_count", 0)

    try:
        # --- 3. Parse: extract A2UI JSON blocks from the tagged text ---
        response_parts = parse_response(llm_output_text)
        if not response_parts:
            raise ValueError("No A2UI JSON blocks found in the response.")
            
        # --- 4. Validate each component against the catalog schema ---
        # A single response may contain multiple A2UI JSON blocks; the LLM
        # sometimes returns a list of components (array) or a single object.
        for part in response_parts:
            if part.a2ui_json:
                if isinstance(part.a2ui_json, list):
                    # Array of components — validate each individually
                    for msg in part.a2ui_json:
                        selected_catalog.validator.validate(msg)
                    a2ui_schema.extend(part.a2ui_json)
                else:
                    # Single component object
                    selected_catalog.validator.validate(part.a2ui_json)
                    a2ui_schema.append(part.a2ui_json)
        
        # --- 5a. Success: persist validated schema and advance the workflow ---
        # Clear any previous validation error so the judge/downstream nodes
        # don't see stale error state from an earlier retry.
        return Event(
            output=a2ui_schema, 
            route="VALID",
            state={"ui_validation_error": "", "a2ui_schema": a2ui_schema}
        )
        
    except Exception as e:
        # Catches both JSON-Schema validation errors (from the catalog
        # validator) and structural parse errors (from parse_response).
        logger.error(f"A2UI Validation Error: {e}")

        # --- 5b. Failure with retries remaining: loop back to the LLM ---
        if retry_count < settings.max_generation_retries:
            return Event(
                route="RETRY",
                output={"status": "RETRY"},
                state={
                    "generation_retry_count": retry_count + 1,
                    # Store the error so ui_schema_generator's prompt can
                    # include it, giving the LLM context to self-correct.
                    "ui_validation_error": str(e)
                }
            )
        else:
            # --- 5c. Failure with retries exhausted: abort generation ---
            return Event(route="FAIL", output={"error": str(e)})
