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
    """Validates the generated A2UI schema and drives the retry loop if invalid."""
    llm_output_text = node_input.get("ui_schema_generator", "") if isinstance(node_input, dict) else str(node_input)
    if hasattr(node_input, "text"):
        llm_output_text = node_input.text

    llm_output_text = _wrap_a2ui_json_tags(llm_output_text)

    selected_catalog = schema_manager.get_selected_catalog()
    a2ui_schema = []
    
    retry_count = ctx.state.get("generation_retry_count", 0)

    try:
        response_parts = parse_response(llm_output_text)
        if not response_parts:
            raise ValueError("No A2UI JSON blocks found in the response.")
            
        for part in response_parts:
            if part.a2ui_json:
                if isinstance(part.a2ui_json, list):
                    for msg in part.a2ui_json:
                        selected_catalog.validator.validate(msg)
                    a2ui_schema.extend(part.a2ui_json)
                else:
                    selected_catalog.validator.validate(part.a2ui_json)
                    a2ui_schema.append(part.a2ui_json)
        
        # Save schema to state so the judge can read it on retries
        return Event(
            output=a2ui_schema, 
            route="VALID",
            state={"ui_validation_error": "", "a2ui_schema": a2ui_schema}
        )
        
    except Exception as e:
        logger.error(f"A2UI Validation Error: {e}")
        if retry_count < settings.max_generation_retries:
            return Event(
                route="RETRY",
                output={"status": "RETRY"},
                state={
                    "generation_retry_count": retry_count + 1,
                    "ui_validation_error": str(e)
                }
            )
        else:
            return Event(route="FAIL", output={"error": str(e)})
