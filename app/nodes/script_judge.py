"""Script Judge — the final LLM quality gate before calculator persistence.

This ADK Agent node acts as an independent reviewer that evaluates the
generated Python script against the blueprint and UI schema *before* the
workflow proceeds to the persist_and_respond node. It is intentionally a
separate LLM call (potentially using a different, cheaper model via
``settings.model_script_judge``) so that the generator and evaluator are
decoupled — a pattern that improves reliability by preventing the generator
from self-approving its own mistakes.

Workflow position::

    script_validator ──► script_judge ──► script_judge_router
                                              │          │
                                           VALID      INVALID
                                              │          │
                                    persist_and_respond  script_generator
                                                         (retry with feedback)

Key design decisions:

* **Dynamic instruction function** — Unlike the other Agent nodes that use
  static instruction strings, the judge needs to embed the current blueprint,
  script, and UI schema into its prompt. A callable ``instruction`` lets us
  read these from ``ctx.state`` at invocation time.

* **No ``output_key``** — The judge's structured output (``ScriptJudgeOutput``)
  is *not* written to state via ``output_key``. Instead, the downstream
  ``script_judge_router`` reads it from ``ctx.state['script_judge_output']``
  (the ADK default key derived from the agent name) and routes to either
  ``persist_and_respond`` (VALID) or back to ``script_generator`` (INVALID).

* **Three-criteria evaluation** — The prompt encodes three explicit pass/fail
  checks (blueprint coverage, I/O binding match, exhaustive output keys) so
  the judge produces actionable, targeted feedback the generator can act on
  in a retry loop.
"""

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types
from ..config import settings
from ..models.generation import ScriptJudgeOutput


def script_judge_instruction(ctx):
    """Build the judge's instruction prompt by interpolating current workflow state.

    This is passed as a callable to ``Agent(instruction=...)``. ADK invokes it
    with the current ``InvocationContext`` each time the agent runs, giving us
    access to the latest state values.

    The function must handle **multiple data formats** for each state variable
    because the values may arrive as:
      - Pydantic model instances (first run, set by an upstream Agent node),
      - Plain dicts (after a round-trip through JSON state serialization), or
      - Raw strings (edge-case fallback / unexpected state shapes).

    Args:
        ctx: ADK ``InvocationContext`` providing access to ``ctx.state``, the
            shared workflow state dictionary (``CalculatorWorkflowState``).

    Returns:
        A fully-interpolated instruction string containing the blueprint,
        A2UI schema, and generated script, plus the three evaluation criteria
        the LLM must check.
    """

    # --- 1. Extract the blueprint ---
    # May be a Pydantic model (has model_dump_json) or a plain dict/str after
    # state serialization. We normalize to a JSON string for prompt embedding.
    blueprint = ctx.state.get("blueprint", "")
    if hasattr(blueprint, "model_dump_json"):
        # Pydantic model — serialize to JSON string directly.
        blueprint = blueprint.model_dump_json()
    else:
        # Already a dict or str — str() is safe for both.
        blueprint = str(blueprint)

    # --- 2. Extract the generated script content ---
    # The script_generator stores its output as a ScriptGeneratorOutput model,
    # but by the time the judge runs it may have been serialized to a dict.
    # We defensively handle model, dict, and raw-string forms.
    script_output = ctx.state.get("script_generator_output", {})
    if isinstance(script_output, dict):
        script_content = script_output.get("script_content", "")
    elif hasattr(script_output, "script_content"):
        # Still a Pydantic model instance — access the attribute directly.
        script_content = script_output.script_content
    else:
        # Unexpected type — last-resort fallback so the judge still gets *something*.
        script_content = str(script_output)

    # --- 3. Extract the A2UI schema ---
    # Get schema from validator node input if available, or from state.
    # The schema is typically a list of A2UI component dicts, but may already
    # be a JSON string if it came from an earlier serialization step.
    a2ui_schema = ctx.state.get("a2ui_schema", "Schema not generated yet")
    if isinstance(a2ui_schema, list) or isinstance(a2ui_schema, dict):
        import json
        a2ui_schema = json.dumps(a2ui_schema, indent=2)

    # --- 4. Compose the evaluation prompt ---
    # The prompt embeds all three artifacts and defines the three-criteria
    # checklist the LLM must evaluate:
    #   Criterion 1 — Blueprint coverage: does the script do what the user asked?
    #   Criterion 2 — I/O binding match: do calculate() inputs/outputs align
    #                 with the A2UI schema bindings exactly?
    #   Criterion 3 — Exhaustive output keys: does every execution path
    #                 (including error branches) return ALL expected output keys
    #                 so the frontend never has unresolved loading states?
    return f"""You are an expert Python judge and architect.
    
    You must evaluate the generated python script to ensure it correctly implements the provided blueprint and integrates perfectly with the provided UI schema.
    
    ### Blueprint
    ```json
    {blueprint}
    ```
    
    ### UI Schema (A2UI)
    ```json
    {a2ui_schema}
    ```
    
    ### Generated Python Script
    ```python
    {script_content}
    ```
    
    Check the following three criteria:
    1. Does the script fully reflect the blueprint and completely cover it? (Does it do what it's supposed to do?)
    2. Does the script perfectly match the UI schema? The `calculate(inputs)` function MUST correctly extract the inputs exactly as defined in the UI schema bindings, and its return dictionary MUST exactly match the paths expected by the output text elements in the schema.
    3. Does the script include ALL output keys defined in the schema in its return dictionary on EVERY execution path (both success and error cases)? If the script returns early due to an error, it MUST still return fallback values for all expected output keys to resolve frontend loading states (e.g. returning `\"\"` for strings or `0` for numeric fields on failure).
    
    If ALL THREE criteria are met, return 'VALID' as your verdict.
    If ANY criteria fails, return 'INVALID' and provide extremely clear feedback on what is wrong and exactly how the script generator should fix it in the next iteration.
    """


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------
# The script_judge Agent node. Key configuration choices:
#   - model: Uses `model_script_judge` from settings, which may be a different
#     (often cheaper/faster) model than the generators, since evaluation is
#     less creative and more analytical.
#   - instruction: A callable (not a string) so we can dynamically interpolate
#     state variables into the prompt at invocation time.
#   - output_schema: Forces structured JSON output matching ScriptJudgeOutput
#     (verdict + feedback), which the script_judge_router parses downstream.
#   - output_key is intentionally NOT set: the router reads the output from
#     the ADK-default state key 'script_judge_output'.
script_judge = Agent(
    name="script_judge",
    model=settings.model_script_judge,
    instruction=script_judge_instruction,
    output_schema=ScriptJudgeOutput,
)
