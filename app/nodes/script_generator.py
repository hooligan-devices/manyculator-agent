"""
Script Generator Agent Node

This file defines the `script_generator` Agent Node for the ADK Workflow.
Role: It acts as an LLM-powered code generator that consumes the structural
`blueprint` (from state) and produces a sandboxed Python calculation script.

Key ADK Mechanics:
- It uses `include_contents='none'` to prevent conversation history from being sent.
  This saves tokens and prevents the model from being confused by stale code from previous turns.
  Instead, all required context is injected directly into the system prompt via template variables.
- It sits in a retry loop: If `script_validator` (syntax error) or `script_judge` (logic error)
  fail the generated script, their feedback is routed back here via the `script_validation_error`
  and `script_judge_feedback` state variables.

Template Variables:
- `{blueprint}`: (Required) The single source of truth for parameter types and mathematical logic.
- `{script_validation_error?}`: (Optional) Python syntax or execution error from the sandbox.
- `{script_judge_feedback?}`: (Optional) Feedback from the LLM judge regarding schema mismatch.
- `{generated_script?}`: (Optional) The previously generated script (if any) to provide context for fixes.

Output:
- The output is validated against `ScriptGeneratorOutput` schema.
- The `output_key="script_generator_output"` ensures the result is automatically stored in `ctx.state`.
"""



from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types
from ..models.generation import ScriptGeneratorOutput
from ..config import settings


script_generator = Agent(
    name="script_generator",
    # Uses a model optimized for coding tasks (do not change)
    model=settings.model_coding,
    # Crucial for token savings: Context comes entirely from state-injected templates, not conversation history.
    include_contents='none',
    instruction=(
        "You are an expert Python developer. Your task is to generate the calculation script.\n\n"
        # ── Required state: the structured blueprint from blueprint_generator ──
        "=== BLUEPRINT ===\n"
        "{blueprint}\n"                       # Always present — the calculator specification.
        "=================\n\n"
        # ── Optional state: populated only on retry from script_validator ──
        "=== SCRIPT VALIDATION ERROR ===\n"
        "{script_validation_error?}\n"        # Syntax / structural errors from script_validator.
        "===============================\n\n"  # The `?` suffix tells ADK this field may be empty.
        # ── Optional state: populated only on retry from script_judge ──
        "=== SCRIPT JUDGE FEEDBACK ===\n"
        "{script_judge_feedback?}\n"          # Semantic / logic feedback from script_judge.
        "=============================\n\n"
        # ── Optional state: the previously generated script for incremental fixes ──
        "=== PREVIOUS SCRIPT ===\n"
        "{generated_script?}\n"               # The last script attempt; empty on first run.
        "=======================\n\n"
        "INSTRUCTIONS:\n"
        "1. Generate the calculation script based strictly on the BLUEPRINT.\n"
        # [WHY] Ensures the script matches the expected signature for the sandbox executor.
        "2. The script must expose exactly one entrypoint function: `def calculate(inputs: dict) -> dict:`\n"
        # [WHY] A2UI data binding requires exact key matching. If keys differ, values won't render.
        "3. The keys extracted from `inputs` and returned in the result dict MUST exactly match the parameter names in the blueprint.\n"
        "4. You must STRICTLY implement the error_handling_strategy defined in the blueprint when invalid inputs are encountered.\n"
        "5. If a SCRIPT VALIDATION ERROR is present, it means your previous script failed syntax or structure checks. Fix it immediately.\n"
        "6. If SCRIPT JUDGE FEEDBACK is present, it means your script did not properly match the UI schema or blueprint. Follow the feedback to fix the script.\n"
        # [WHY] HTTP JSON payloads often send inputs as strings; proactive casting prevents TypeErrors during math ops.
        "7. You MUST aggressively cast all numerical inputs from the dictionary to float before performing math operations to prevent TypeError from string payloads.\n"
        # [WHY] ChoicePickers in A2UI return arrays even for single-select. Unwrapping is required before logic.
        "8. For any 'choice' parameters defined with `data_type: list`, the input dictionary will contain a list of strings (e.g., `[\"kg\"]`). You MUST extract the first element of the list before using it in your logic.\n"
        # [WHY] Frontend loading states (spinners) depend on receiving a value for every expected key. Returning early breaks the UI.
        "9. You MUST include ALL keys defined as 'result' parameters in the blueprint in your final return dictionary on EVERY execution path (both success and error paths). To clear loading states on the frontend, you must always return a fallback value or empty state for all result fields even if an error occurs, or vice versa (e.g. returning `\"\"` for strings or `0` for numeric results on failure)."
    ),
    # Enforces structured output format
    output_schema=ScriptGeneratorOutput,
    # Automatically saves the output to ctx.state["script_generator_output"]
    output_key="script_generator_output",
)
